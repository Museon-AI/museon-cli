from __future__ import annotations

import argparse
import asyncio
import json
import mimetypes
import os
import sys
from contextvars import ContextVar
import time
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx

from museoncli import __version__
from museoncli.auth import (
    auth_headers,
    finish_pending_web_approval_login,
    run_web_approval_login,
    start_web_approval_login,
)
from museoncli.config import (
    AuthState,
    Config,
    PendingAuthState,
    WorkspaceState,
    delete_auth_credentials,
    load_config,
    save_config,
    update_config,
)
from museoncli.domains import (
    add_domain_command_parsers,
    command_executor,
    command_payload,
    get_command_spec,
    schema_payload,
)
from museoncli.domains.asset import validate_asset_write_arguments
from museoncli.envelopes import (
    domain_command_dry_run_envelope,
)
from museoncli.execution import (
    CommandContext,
    agent_domain_result,
)
from museoncli.large_json import render_json
from museoncli.setup_agent import SUPPORTED_AGENTS, install_agent_skill


_API_CONNECT_MAX_ATTEMPTS = 3
_API_CONNECT_RETRY_BASE_DELAY_SECONDS = 0.25
_ACTIVE_COMMAND_NAME: ContextVar[str | None] = ContextVar(
    "museoncli_active_command_name", default=None
)
DEFAULT_CLI_RELEASE_MANIFEST_URL = "https://pypi.org/pypi/museoncli/json"
PYPI_PROJECT_URL = "https://pypi.org/project/museoncli/"


def main() -> None:
    _configure_utf8_stdout()
    parser = build_parser()
    argv = sys.argv[1:]
    args = parser.parse_args([item for item in argv if item != "--json"])
    args.json = True
    try:
        result = asyncio.run(dispatch_with_notices(args))
    except KeyboardInterrupt:
        emit({"ok": False, "reason": "interrupted"})
        raise SystemExit(130) from None
    except Exception as exc:
        emit({"ok": False, "reason": reason_from_exception(exc), "detail": str(exc)})
        raise SystemExit(1) from None
    if result is not None:
        if not emit(
            {"ok": True, **result},
            command_hint=getattr(args, "domain_command", None),
        ):
            raise SystemExit(1)


def _configure_utf8_stdout() -> None:
    """Keep the machine-readable output contract UTF-8 across host locales."""
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if not callable(reconfigure):
        return
    try:
        reconfigure(encoding="utf-8")
    except (AttributeError, OSError, ValueError):
        pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="museoncli")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Accepted for compatibility. JSON output is always emitted.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("version")
    sub.add_parser("whoami")
    sub.add_parser("health")
    schema = sub.add_parser("schema")
    schema.add_argument("name", nargs="?")

    setup = sub.add_parser("setup")
    setup.add_argument(
        "--agent",
        nargs="?",
        const="auto",
        default="auto",
        choices=["auto", "all", *SUPPORTED_AGENTS],
        help="Install the bundled Skill for a detected or named host Agent.",
    )
    setup.add_argument("--force", action="store_true")

    config = sub.add_parser("config")
    config_sub = config.add_subparsers(dest="config_command", required=True)
    config_sub.add_parser("get")
    config_set = config_sub.add_parser("set")
    config_set.add_argument("--api-base-url")
    config_set.add_argument("--site-url")

    auth = sub.add_parser("auth")
    auth_sub = auth.add_subparsers(dest="auth_command", required=True)
    login = auth_sub.add_parser("login")
    login.add_argument("--timeout", type=int, default=300)
    login.add_argument("--poll-interval", type=float, default=2.0)
    login.add_argument("--no-browser", action="store_true")
    auth_sub.add_parser("start")
    finish = auth_sub.add_parser("finish")
    finish.add_argument("--wait", action="store_true")
    finish.add_argument("--timeout", type=int, default=300)
    finish.add_argument("--poll-interval", type=float, default=2.0)
    auth_sub.add_parser("status")
    auth_sub.add_parser("logout")

    workspace = sub.add_parser("workspace")
    workspace_sub = workspace.add_subparsers(dest="workspace_command", required=True)
    workspace_sub.add_parser("list")
    workspace_sub.add_parser("current")
    select = workspace_sub.add_parser("select")
    select.add_argument("--id")
    select.add_argument("--name")

    add_domain_command_parsers(sub)

    return parser


async def dispatch(args: argparse.Namespace) -> dict[str, Any] | None:
    cfg = load_config()
    if args.command == "version":
        return {"data": {"cli_version": __version__, "api_base_url": cfg.api_base_url}}
    if args.command == "config":
        return await dispatch_config(args)
    if args.command == "setup":
        return {"data": install_agent_skill(args.agent, force=args.force)}
    if args.command == "auth":
        return await dispatch_auth(args, cfg)
    if args.command == "health":
        root = api_root(cfg)
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(f"{root}/health")
        return {
            "data": {"status_code": response.status_code, "healthy": response.status_code < 500}
        }
    if args.command == "whoami":
        data = await api_data(cfg, "GET", "/agent-cli/whoami")
        sync_current_workspace_from_whoami(cfg, data)
        return {"data": data}
    if args.command == "workspace":
        return await dispatch_workspace(args, cfg)
    if args.command == "schema":
        return {"data": schema_payload(args.name)}
    if getattr(args, "domain_command", None):
        return await dispatch_domain_command(args, cfg)
    raise RuntimeError(f"Unknown command: {args.command}")


async def dispatch_with_notices(args: argparse.Namespace) -> dict[str, Any] | None:
    result = await dispatch(args)
    if result is None or not command_uses_network(args):
        return result
    return await attach_update_notice(result)


def command_uses_network(args: argparse.Namespace) -> bool:
    """Return whether the requested command already performs remote IO.

    Update checks must never turn local-only commands into network operations.
    Network-backed commands still receive update notices without adding a new
    privacy or reliability characteristic to the invocation.
    """

    if args.command in {"health", "whoami"}:
        return True
    if args.command == "workspace":
        return args.workspace_command in {"list", "select"}
    if args.command == "auth":
        return args.auth_command in {"login", "start", "finish"}
    domain_command = getattr(args, "domain_command", None)
    if domain_command:
        spec = get_command_spec(domain_command)
        return spec.transport != "local_process" and not getattr(args, "dry_run", False)
    return False


async def attach_update_notice(result: dict[str, Any]) -> dict[str, Any]:
    try:
        notice = await check_cli_update_notice(load_config())
    except Exception:
        return result
    if not notice:
        return result
    return {**result, "_notice": {"update": notice}}


async def check_cli_update_notice(cfg: Config) -> dict[str, Any] | None:
    if not cli_update_check_enabled():
        return None
    manifest_url = cli_update_manifest_url()
    manifest = await fetch_cli_release_manifest(manifest_url)
    if not isinstance(manifest, dict):
        return None
    info = manifest.get("info") if isinstance(manifest.get("info"), dict) else {}
    latest_version = str(info.get("version") or manifest.get("version") or "").strip()
    if not latest_version or not is_newer_cli_version(latest_version, __version__):
        return None
    return {
        "current_version": __version__,
        "latest_version": latest_version,
        "message": (
            f"Museon CLI {latest_version} is available. "
            "Run `uv tool upgrade museoncli` or `pipx upgrade museoncli`, "
            "then restart the host Agent."
        ),
        "source": "pypi",
        "manifest_url": manifest_url,
        "project_url": PYPI_PROJECT_URL,
        "restart_required": True,
    }


def cli_update_check_enabled() -> bool:
    value = os.environ.get("MUSEONCLI_UPDATE_CHECK", "1").strip().lower()
    return value not in {"0", "false", "no", "off"}


def cli_update_manifest_url() -> str:
    return os.environ.get("MUSEONCLI_UPDATE_MANIFEST_URL", DEFAULT_CLI_RELEASE_MANIFEST_URL).strip()


async def fetch_cli_release_manifest(manifest_url: str) -> dict[str, Any] | None:
    if not manifest_url:
        return None
    try:
        async with httpx.AsyncClient(timeout=2.0, follow_redirects=True) as client:
            response = await client.get(manifest_url, headers={"Accept": "application/json"})
        if response.status_code >= 400:
            return None
        payload = response.json()
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def is_newer_cli_version(latest_version: str, current_version: str) -> bool:
    latest = cli_version_tuple(latest_version)
    current = cli_version_tuple(current_version)
    if latest is None or current is None:
        return False
    width = max(len(latest), len(current))
    return latest + (0,) * (width - len(latest)) > current + (0,) * (width - len(current))


def cli_version_tuple(value: str) -> tuple[int, ...] | None:
    version = value.strip().removeprefix("v").split("-", 1)[0]
    if not version:
        return None
    parts = version.split(".")
    if any(not part.isdigit() for part in parts):
        return None
    return tuple(int(part) for part in parts)


async def dispatch_config(args: argparse.Namespace) -> dict[str, Any]:
    if args.config_command == "get":
        return {"data": load_config().safe_dict()}
    cfg = update_config(
        api_base_url=args.api_base_url,
        site_url=args.site_url,
    )
    return {"data": cfg.safe_dict()}


async def dispatch_auth(args: argparse.Namespace, cfg: Config) -> dict[str, Any]:
    if args.auth_command == "logout":
        delete_auth_credentials()
        cfg.auth = AuthState()
        cfg.workspace = WorkspaceState()
        cfg.pending_auth = PendingAuthState()
        save_config(cfg)
        return {"data": {"authenticated": False}}
    if args.auth_command == "status":
        clear_expired_pending_web_approval(cfg)
        auth_expired = cfg.auth.is_expired()
        authenticated = bool(auth_headers(cfg))
        return {
            "data": {
                "authenticated": authenticated,
                "status": (
                    "expired"
                    if auth_expired
                    else "authenticated"
                    if authenticated
                    else "unauthenticated"
                ),
                "reason": "credential_expired" if auth_expired else None,
                "auth_method": auth_method(cfg),
                "expires_at": cfg.auth.expires_at,
                "user": safe_user(cfg.auth.user),
                "workspace": cfg.workspace.__dict__,
                "pending_web_approval": pending_web_approval_status(cfg),
            }
        }
    if args.auth_command == "start":
        data = await start_web_approval_login(config=cfg)
        return {"data": data}
    if args.auth_command == "finish":
        data = await finish_pending_web_approval_login(
            config=cfg,
            wait=args.wait,
            timeout_seconds=args.timeout,
            poll_interval_seconds=args.poll_interval,
        )
        return {"data": data, "workspace": data.get("workspace")}
    data = await run_web_approval_login(
        config=cfg,
        timeout_seconds=args.timeout,
        open_browser=not args.no_browser,
        poll_interval_seconds=args.poll_interval,
    )
    return {"data": data, "workspace": data.get("workspace")}


async def dispatch_workspace(args: argparse.Namespace, cfg: Config) -> dict[str, Any]:
    if args.workspace_command == "current":
        return {"workspace": cfg.workspace.__dict__, "data": cfg.workspace.__dict__}
    data = await api_data(cfg, "GET", "/agent-cli/whoami")
    workspaces = data.get("workspaces") or []
    if args.workspace_command == "list":
        sync_current_workspace_from_whoami(cfg, data)
        return {"data": {"workspaces": workspaces}, "workspace": cfg.workspace.__dict__}
    selected = None
    for workspace in workspaces:
        if args.id and workspace.get("id") == args.id:
            selected = workspace
            break
        if args.name and workspace.get("name") == args.name:
            selected = workspace
            break
    if selected is None:
        raise RuntimeError("Workspace not found.")
    cfg.workspace = WorkspaceState(
        id=selected.get("id"),
        name=selected.get("name"),
        organization_id=selected.get("organization_id"),
        organization_name=selected.get("organization_name"),
    )
    save_config(cfg)
    return {"workspace": selected, "data": selected}


def sync_current_workspace_from_whoami(cfg: Config, data: dict[str, Any]) -> bool:
    current_id = cfg.workspace.id
    if not current_id:
        return False
    workspaces = data.get("workspaces")
    if not isinstance(workspaces, list):
        return False
    for raw in workspaces:
        if not isinstance(raw, dict) or raw.get("id") != current_id:
            continue
        next_workspace = WorkspaceState(
            id=raw.get("id"),
            name=raw.get("name"),
            organization_id=raw.get("organization_id"),
            organization_name=raw.get("organization_name"),
        )
        if next_workspace == cfg.workspace:
            return False
        cfg.workspace = next_workspace
        save_config(cfg)
        return True
    return False


async def api_data(
    cfg: Config,
    method: str,
    path: str,
    *,
    json_body: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    unwrap_success: bool = True,
) -> Any:
    return await _api_request(
        cfg,
        method,
        f"{cfg.api_base_url.rstrip('/')}{path}",
        json_body=json_body,
        params=params,
        unwrap_success=unwrap_success,
    )


async def _api_request(
    cfg: Config,
    method: str,
    url: str,
    *,
    json_body: dict[str, Any] | None,
    params: dict[str, Any] | None,
    unwrap_success: bool,
) -> Any:
    if not auth_headers(cfg):
        raise RuntimeError("missing_auth")
    response = await _api_send(cfg, method, url, json_body=json_body, params=params)
    if response.status_code == 401:
        raise RuntimeError("unauthorized")
    if response.status_code == 403:
        raise RuntimeError(forbidden_error_message(response))
    if response.status_code == 426:
        raise RuntimeError(f"cli_outdated: {response.text[:500]}")
    if response.status_code >= 400:
        raise RuntimeError(f"HTTP {response.status_code}: {response.text[:500]}")
    payload = response.json()
    if unwrap_success and isinstance(payload, dict) and "success" in payload:
        if not payload.get("success"):
            raise RuntimeError(str(payload.get("message") or "api_error"))
        return payload.get("data")
    return payload


async def _api_send(
    cfg: Config,
    method: str,
    url: str,
    *,
    json_body: dict[str, Any] | None,
    params: dict[str, Any] | None,
) -> httpx.Response:
    last_error: httpx.ConnectError | httpx.ConnectTimeout | None = None
    for attempt in range(1, _API_CONNECT_MAX_ATTEMPTS + 1):
        try:
            async with httpx.AsyncClient(timeout=None) as client:
                return await client.request(
                    method,
                    url,
                    headers=_request_headers(cfg),
                    json=json_body,
                    params=params,
                )
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            last_error = exc
            if attempt >= _API_CONNECT_MAX_ATTEMPTS:
                raise
            await asyncio.sleep(_API_CONNECT_RETRY_BASE_DELAY_SECONDS * attempt)
    if last_error is not None:
        raise last_error
    raise RuntimeError("api_request_not_sent")


def _request_headers(cfg: Config) -> dict[str, str]:
    headers = auth_headers(cfg)
    command_name = _ACTIVE_COMMAND_NAME.get()
    if headers and command_name:
        headers["X-Museon-CLI-Command"] = command_name
    return headers


async def api_data_v2(
    cfg: Config,
    method: str,
    path: str,
    *,
    json_body: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    unwrap_success: bool = True,
) -> Any:
    return await _api_request(
        cfg,
        method,
        f"{api_version_base_url(cfg, version='v2')}{path}",
        json_body=json_body,
        params=params,
        unwrap_success=unwrap_success,
    )


def api_version_base_url(cfg: Config, *, version: str) -> str:
    base = cfg.api_base_url.rstrip("/")
    if base.endswith("/api/v1"):
        return f"{base[: -len('/api/v1')]}/api/{version}"
    return f"{base}/api/{version}"


def workspace_id_arg_or_selected(args: argparse.Namespace, cfg: Config) -> str | None:
    return getattr(args, "workspace_id", None) or cfg.workspace.id


# Museon resource IDs are always canonical UUIDs, but agent-driven callers have
# sent placeholders ("?") and free-form text ("Page 2: 50 accounts") where IDs
# belong. Validate by key name before any HTTP call so the agent gets a
# self-correcting error instead of a production 4xx/500.
_UUID_SCALAR_ARGUMENT_KEYS = frozenset(
    {
        "id",
        "account_id",
        "workspace_id",
        "campaign_id",
        "creator_id",
        "content_id",
        "version_id",
        "schedule_item_id",
        "task_id",
        "job_id",
        "persona_id",
        "product_id",
        "format_id",
        "topic_direction_id",
        "persona_experiment_id",
        "evaluator_type_id",
        "creative_research_snapshot_id",
        "slideshow_generation_id",
        "artifact_id",
    }
)
_UUID_LIST_ARGUMENT_KEYS = frozenset(
    {
        "format_ids",
        "content_topic_ids",
        "media_ids",
        "brand_logo_media_ids",
        "product_image_media_ids",
        "website_screenshot_media_ids",
        "app_screenshot_media_ids",
        "uploaded_media_ids",
        "topic_ids",
        "account_ids",
        "add_format_ids",
        "add_topic_ids",
        "pause_format_ids",
        "pause_topic_ids",
    }
)
# asset_media_ids uses the composite "ASSET_TYPE:MEDIA_ID" form, so it is
# intentionally excluded from plain-UUID validation.
_UUID_NESTED_ARGUMENT_KEYS = ("changes", "payload")


def _uuid_argument_error(field: str, value: Any) -> ValueError:
    return ValueError(
        f"{field} must be a canonical UUID "
        f"(e.g. 72defd40-39ad-40d3-8105-8f23a9a016da), got {value!r}. "
        "Placeholder values such as '?' are not accepted. If you do not know "
        "the ID yet, look it up first with the matching +list/+get command; "
        "to leave an optional field unchanged, omit it entirely."
    )


def _validate_uuid_value(field: str, value: Any) -> None:
    if value is None:
        return
    try:
        UUID(str(value))
    except (TypeError, ValueError):
        raise _uuid_argument_error(field, value) from None


def _validate_uuid_mapping(arguments: dict[str, Any], *, prefix: str = "") -> None:
    for key, value in arguments.items():
        field = f"{prefix}{key}"
        if key in _UUID_SCALAR_ARGUMENT_KEYS:
            _validate_uuid_value(field, value)
        elif key in _UUID_LIST_ARGUMENT_KEYS:
            if value is None:
                continue
            if not isinstance(value, list):
                raise _uuid_argument_error(field, value)
            for index, item in enumerate(value):
                _validate_uuid_value(f"{field}[{index}]", item)


def validate_uuid_arguments(arguments: dict[str, Any]) -> None:
    _validate_uuid_mapping(arguments)
    for nested_key in _UUID_NESTED_ARGUMENT_KEYS:
        nested = arguments.get(nested_key)
        if isinstance(nested, dict):
            _validate_uuid_mapping(nested, prefix=f"{nested_key}.")


async def upload_media_file(
    cfg: Config,
    *,
    workspace_id: str,
    arguments: dict[str, Any],
) -> Any:
    media_type = str(arguments.get("media_type") or "image")
    path = Path(str(arguments.get("file") or "")).expanduser()
    if not path.is_file():
        raise RuntimeError(f"media file not found: {path}")
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    form_data = {
        "workspace_id": workspace_id,
        **{
            key: str(value)
            for key in ("title", "description")
            if (value := arguments.get(key)) is not None
        },
    }
    if not auth_headers(cfg):
        raise RuntimeError("missing_auth")
    with path.open("rb") as handle:
        files = {"file": (path.name, handle, content_type)}
        async with httpx.AsyncClient(timeout=None) as client:
            response = await client.post(
                f"{cfg.api_base_url.rstrip()}/agent-cli/assets/media/upload",
                headers=_request_headers(cfg),
                data={**form_data, "media_type": media_type},
                files=files,
            )
    if response.status_code == 401:
        raise RuntimeError("unauthorized")
    if response.status_code == 403:
        raise RuntimeError(forbidden_error_message(response))
    if response.status_code >= 400:
        raise RuntimeError(f"HTTP {response.status_code}: {response.text[:500]}")
    return response.json()


async def upload_artifact_file(
    cfg: Config,
    *,
    workspace_id: str | None,
    arguments: dict[str, Any],
) -> Any:
    if not workspace_id:
        raise RuntimeError("missing_workspace")
    path = Path(str(arguments.get("file") or "")).expanduser()
    if not path.is_file():
        raise RuntimeError(f"artifact file not found: {path}")
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    form_data: dict[str, str] = {
        "workspace_id": workspace_id,
        "artifact_type": str(arguments.get("artifact_type") or "file"),
        "source_file_path": str(arguments.get("file") or path.name),
        # Markdown customer deliverables are public by default; explicit false opts out.
        "public": "true" if bool(arguments.get("public", True)) else "false",
    }
    for form_key, argument_key in (
        ("artifact_id", "artifact_id"),
        ("title", "title"),
    ):
        value = arguments.get(argument_key)
        if value is not None:
            form_data[form_key] = str(value)
    for form_key, argument_key in (
        ("runtime_context_json", "runtime_context"),
        ("metadata_json", "metadata"),
    ):
        value = arguments.get(argument_key)
        if isinstance(value, dict):
            form_data[form_key] = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if not auth_headers(cfg):
        raise RuntimeError("missing_auth")
    with path.open("rb") as handle:
        files = {"file": (path.name, handle, content_type)}
        async with httpx.AsyncClient(timeout=None) as client:
            response = await client.post(
                f"{cfg.api_base_url.rstrip()}/agent-cli/artifacts/upload",
                headers=_request_headers(cfg),
                data=form_data,
                files=files,
            )
    if response.status_code == 401:
        raise RuntimeError("unauthorized")
    if response.status_code == 403:
        raise RuntimeError(forbidden_error_message(response))
    if response.status_code >= 400:
        raise RuntimeError(f"HTTP {response.status_code}: {response.text[:500]}")
    payload = response.json()
    if isinstance(payload, dict) and "success" in payload:
        if not payload.get("success"):
            raise RuntimeError(str(payload.get("message") or "api_error"))
        return agent_domain_result(payload.get("data"))
    return payload


def api_root(cfg: Config) -> str:
    suffix = "/api/v1"
    base = cfg.api_base_url.rstrip("/")
    return base[: -len(suffix)] if base.endswith(suffix) else base


def safe_user(user: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(user, dict):
        return None
    return {"id": user.get("id"), "email": user.get("email")}


def auth_method(cfg: Config) -> str:
    if cfg.auth.api_key:
        return "api_key"
    return "none"


def pending_web_approval_status(cfg: Config) -> dict[str, Any]:
    pending = cfg.pending_auth
    return {
        "active": bool(pending.device_code),
        "expires_at": pending.expires_at,
        "user_code": pending.user_code,
    }


def clear_expired_pending_web_approval(cfg: Config) -> None:
    expires_at = cfg.pending_auth.expires_at
    if not cfg.pending_auth.device_code or not expires_at or expires_at > int(time.time()):
        return
    cfg.pending_auth = PendingAuthState()
    save_config(cfg)


def reason_from_exception(exc: Exception) -> str:
    text = str(exc)
    if text in {
        "missing_auth",
        "unauthorized",
        "forbidden",
        "missing_workspace",
        "confirmation_required",
        "cli_outdated",
    }:
        return text
    if text.startswith("cli_outdated"):
        return "cli_outdated"
    if text.startswith("forbidden:"):
        return "forbidden"
    if isinstance(exc, ValueError):
        return "invalid_input"
    if text.startswith("HTTP 400") or text.startswith("HTTP 422"):
        return "invalid_input"
    if text.startswith("HTTP 404"):
        return "not_found"
    if text.startswith("HTTP 503"):
        return "service_unavailable"
    return exc.__class__.__name__


def forbidden_error_message(response: httpx.Response) -> str:
    detail = response_error_detail(response)
    if not detail:
        return "forbidden"
    return f"forbidden: {detail}"


def response_error_detail(response: httpx.Response) -> str | None:
    try:
        payload = response.json()
    except Exception:
        text = response.text[:500].strip()
        return text or None
    if not isinstance(payload, dict):
        return str(payload)[:500]
    detail = payload.get("detail")
    if isinstance(detail, dict):
        code = detail.get("code")
        if code == "routine_owner_mismatch":
            routine_name = detail.get("routine_name") or "unnamed routine"
            routine_id = detail.get("routine_id") or "unknown routine"
            owner_user_id = detail.get("owner_user_id") or "unknown owner"
            return (
                "routine_owner_mismatch: "
                f"{routine_name} ({routine_id}) is owned by user {owner_user_id}"
            )
        return json.dumps(detail, ensure_ascii=False, sort_keys=True)[:500]
    if detail is not None:
        return str(detail)[:500]
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)[:500]


def emit(payload: dict[str, Any], *, command_hint: str | None = None) -> bool:
    rendered = render_json(payload, command_hint=command_hint)
    print(rendered.text, flush=True)
    return not rendered.offload_failed


async def dispatch_domain_command(args: argparse.Namespace, cfg: Config) -> dict[str, Any]:
    spec = get_command_spec(args.domain_command)
    arguments = command_payload(args)
    validate_uuid_arguments(arguments)
    workspace_id = workspace_id_arg_or_selected(args, cfg)
    if getattr(args, "dry_run", False):
        if spec.schema_name.startswith("skills."):
            dry_run_workspace_id = workspace_id if spec.schema_name == "skills.create" else None
            return domain_command_dry_run_envelope(
                spec.schema_name, dry_run_workspace_id, arguments
            )
        if spec.schema_name in {"asset.create", "asset.update"}:
            validate_asset_write_arguments(
                workspace_id=workspace_id,
                arguments=arguments,
                command_name=spec.schema_name,
            )
        return domain_command_dry_run_envelope(spec.schema_name, workspace_id, arguments)
    if spec.requires_confirmation and not getattr(args, "yes", False):
        raise RuntimeError("confirmation_required")
    ctx = CommandContext(
        cfg=cfg,
        spec=spec,
        args=args,
        arguments=arguments,
        workspace_id=workspace_id,
        api_data=api_data,
        api_data_v2=api_data_v2,
        upload_media_file=upload_media_file,
        upload_artifact_file=upload_artifact_file,
    )
    command_token = _ACTIVE_COMMAND_NAME.set(spec.schema_name)
    try:
        return await command_executor(spec.schema_name)(ctx)
    finally:
        _ACTIVE_COMMAND_NAME.reset(command_token)


if __name__ == "__main__":
    main()
