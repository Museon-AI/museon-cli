from __future__ import annotations

import argparse
import asyncio
import json
import mimetypes
import os
import sys
from contextvars import ContextVar
from dataclasses import asdict
import time
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx

from museoncli import __version__, updates
from museoncli.auth import (
    ORGANIZATION_HEADER,
    auth_headers,
    finish_pending_web_approval_login,
    run_web_approval_login,
    start_web_approval_login,
)
from museoncli.config import (
    AuthState,
    Config,
    OrganizationState,
    PendingAuthState,
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
from museoncli.domains._legacy_workspace import (
    ORGANIZATION_WORKSPACE_MISMATCH_MESSAGE,
    keeps_workspace,
    with_workspace_key,
    workspace_flag_notice,
)
from museoncli.envelopes import (
    domain_command_dry_run_envelope,
)
from museoncli.execution import (
    CommandContext,
    agent_domain_result,
)
from museoncli.large_json import render_json
from museoncli.paging import collect_all_pages, page_info
from museoncli.setup_agent import SUPPORTED_AGENTS, install_agent_skill, stale_skill_agents


_API_CONNECT_MAX_ATTEMPTS = 3
_API_CONNECT_RETRY_BASE_DELAY_SECONDS = 0.25
_ACTIVE_COMMAND_NAME: ContextVar[str | None] = ContextVar(
    "museoncli_active_command_name", default=None
)
# What bootstrap learned about releases before dispatch (None: a host imported main).
_ACTIVE_UPDATE: ContextVar[dict[str, Any] | None] = ContextVar(
    "museoncli_active_update", default=None
)
# --organization-id of the running command; overrides the selected organization.
_ACTIVE_ORGANIZATION_ID: ContextVar[str | None] = ContextVar(
    "museoncli_active_organization_id", default=None
)


class ApiRequestError(RuntimeError):
    """HTTP error that preserves an agent-readable structured API detail."""

    def __init__(self, status_code: int, detail: Any) -> None:
        self.status_code = status_code
        self.detail = detail
        rendered = (
            json.dumps(detail, ensure_ascii=False, sort_keys=True)
            if isinstance(detail, dict | list)
            else str(detail)
        )
        super().__init__(f"HTTP {status_code}: {rendered}")


class CliOutdatedError(ApiRequestError):
    """HTTP 426: the server no longer accepts this CLI version."""

    def __init__(self, detail: dict[str, Any]) -> None:
        super().__init__(426, detail)

    def __str__(self) -> str:
        return str(self.detail.get("message") or "cli_outdated")


def cli_outdated_error(response: httpx.Response) -> CliOutdatedError:
    """Turn any 426 answer (agent-cli, /api/v2, uploads) into one readable failure."""
    payload = response_error_payload(response)
    body = payload if isinstance(payload, dict) else {}
    minimum = body.get("minimum_version")
    received = body.get("received_version") or __version__
    install_hint = body.get("install_hint") or (
        "Run `museoncli upgrade` (it prints the command when your installer must run it), "
        "then retry."
    )
    required = f" (minimum supported: {minimum})" if minimum else ""
    return CliOutdatedError(
        {
            "code": "cli_outdated",
            "message": (
                f"Museon CLI {received} is no longer supported by the Museon API{required}. "
                f"{install_hint}"
            ),
            "minimum_version": minimum,
            "received_version": received,
            "install_hint": install_hint,
        }
    )


# Messages for server codes whose body carries no readable text of its own.
_SERVER_CODE_MESSAGES = {
    "organization_workspace_mismatch": ORGANIZATION_WORKSPACE_MISMATCH_MESSAGE,
}


# Exit codes are part of the output contract (docs/cli-surface-conventions.md).
EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_USAGE = 2
EXIT_NOT_FOUND = 3
EXIT_AUTH_REQUIRED = 4
EXIT_CONFLICT = 5
EXIT_INTERRUPTED = 130

_EXIT_CODE_BY_REASON = {
    "usage_error": EXIT_USAGE,
    "not_found": EXIT_NOT_FOUND,
    "missing_auth": EXIT_AUTH_REQUIRED,
    "unauthorized": EXIT_AUTH_REQUIRED,
    "conflict": EXIT_CONFLICT,
}
_RETRYABLE_REASONS = frozenset(
    {"service_unavailable", "server_error", "rate_limited", "network_error"}
)


class UsageError(SystemExit):
    """Invalid command line; reported through the JSON error contract.

    It stays a ``SystemExit`` with code 2 so programmatic ``parse_args`` callers
    keep argparse's behavior; ``main`` renders it as JSON on stdout.
    """

    def __init__(
        self, message: str, *, usage: str | None = None, command: str | None = None
    ) -> None:
        super().__init__(EXIT_USAGE)
        self.message = message
        self.usage = usage
        self.command = command

    def __str__(self) -> str:
        return self.message


class JsonArgumentParser(argparse.ArgumentParser):
    """Keep usage errors on the JSON stdout contract instead of argparse's stderr text."""

    def error(self, message: str) -> Any:  # type: ignore[override]
        # A domain command's parser is named after its CLI path, so a missing
        # required flag still reports which command it belongs to.
        try:
            command: str | None = get_command_spec(self.prog).schema_name
        except (KeyError, ValueError):
            command = None
        raise UsageError(message, usage=self.format_usage().strip(), command=command)


def main(*, update: dict[str, Any] | None = None) -> None:
    _configure_utf8_stdout()
    argv = sys.argv[1:]
    parser = build_parser()
    try:
        args, extras = parser.parse_known_args([item for item in argv if item != "--json"])
        if extras:
            raise UsageError(
                f"unrecognized arguments: {' '.join(extras)}",
                command=invoked_command_name(args),
            )
    except UsageError as exc:
        payload, code = error_envelope(exc, command=exc.command)
        emit(payload)
        raise SystemExit(code) from None
    args.json = True
    command = invoked_command_name(args)
    deprecations = deprecation_notices(args)
    for notice in deprecations:
        print(f"museoncli: {notice}", file=sys.stderr, flush=True)
    _ACTIVE_UPDATE.set(update)
    try:
        result = asyncio.run(dispatch(args))
    except KeyboardInterrupt:
        emit(
            {
                "ok": False,
                "command": command,
                "reason": "interrupted",
                "error": {"code": "interrupted", "message": "interrupted", "retryable": True},
            }
        )
        raise SystemExit(EXIT_INTERRUPTED) from None
    except Exception as exc:
        payload, code = error_envelope(exc, command=command)
        if deprecations:
            payload["warnings"] = deprecations
        emit(with_notice(payload, args, update))
        raise SystemExit(code) from None
    if result is not None and deprecations:
        result = {**result, "warnings": [*(result.get("warnings") or []), *deprecations]}
    if result is not None:
        if not emit(
            with_notice({"ok": True, **result}, args, update),
            command_hint=getattr(args, "domain_command", None),
        ):
            raise SystemExit(1)


def with_notice(
    payload: dict[str, Any], args: argparse.Namespace, update: dict[str, Any] | None
) -> dict[str, Any]:
    """Tell the Agent, via `_notice`, what changed about the CLI and its Skills.

    `update`: a newer release exists that this installation did not install.
    `updated`: the CLI upgraded itself (once). `skills`: see `skills_notice`.
    """
    notice = updates.release_notices(update)
    skills = skills_notice(args, update)
    if skills:
        notice["skills"] = skills
    return {**payload, "_notice": notice} if notice else payload


def skills_notice(
    args: argparse.Namespace, update: dict[str, Any] | None
) -> dict[str, Any] | None:
    """Keep the Agent's installed Skills on this CLI's version.

    Skills that `setup` installed are synced automatically, like the CLI itself; the
    Agent still holds the old text in its conversation, so it is told to re-read it.
    Pinned installs (MUSEONCLI_UPDATE_CHECK=0) are only reminded, on every command.
    """
    status = (update or {}).get("status", "managed_externally")
    # Host-managed runtimes and source checkouts ship their Skills themselves.
    if args.command == "setup" or status == "managed_externally":
        return None
    try:
        stale = stale_skill_agents()
    except (OSError, RuntimeError):
        return None  # Skill maintenance must never break the user's command.
    if not stale:
        return None
    updated = []
    if status != "disabled":
        for agent in stale:
            try:
                install_agent_skill(agent)
            except (OSError, RuntimeError):
                continue
            updated.append(agent)
            print(f"Museon CLI: updated Agent Skills for {agent}.", file=sys.stderr)
    stale = [agent for agent in stale if agent not in updated]
    notice: dict[str, Any] = {"cli_version": __version__}
    messages = []
    if updated:
        notice["updated"] = updated
        messages.append(
            f"Museon Agent Skills were updated to match Museon CLI {__version__}. "
            "Re-read the Museon Skill you are using before relying on it "
            "(some hosts need a restart to reload it)."
        )
    if stale:
        command = " && ".join(f"museoncli setup --agent {agent}" for agent in stale)
        notice["stale"] = stale
        notice["command"] = command
        messages.append(
            f"Installed Museon Agent Skills do not match Museon CLI {__version__}. "
            f"After the current task, run: {command}; then re-read the updated Skill."
        )
    notice["message"] = " ".join(messages)
    return notice


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
    parser = JsonArgumentParser(prog="museoncli")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Accepted for compatibility. JSON output is always emitted.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser(
        "version",
        help="This CLI's version, the latest release, and how to upgrade.",
    )
    sub.add_parser(
        "upgrade",
        help="Upgrade to the latest stable release, or print the command your installer needs.",
    )
    sub.add_parser("whoami")
    sub.add_parser("health")
    schema = sub.add_parser(
        "schema",
        description=(
            "Describe commands. NAME is a capability key (hireaicreator.video-get), "
            "a domain (hireaicreator), or a CLI path (hireaicreator video +get)."
        ),
    )
    schema.add_argument("name", nargs="?")
    schema.add_argument("path_rest", nargs="*", help=argparse.SUPPRESS)

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

    org = sub.add_parser(
        "org",
        help="List, show or select the organization commands act in.",
        description=(
            "The selected organization is sent with every request as X-Organization-Id; "
            "your role and Campaign scope in it decide what you can see and change."
        ),
    )
    org_sub = org.add_subparsers(dest="org_command", required=True)
    org_sub.add_parser("list", help="Organizations this login can act in.")
    org_sub.add_parser("current", help="The selected organization.")
    org_select = org_sub.add_parser("select", help="Select the organization to act in.")
    org_select_target = org_select.add_mutually_exclusive_group(required=True)
    org_select_target.add_argument("--id", help="Organization ID (from `museoncli org list`).")
    org_select_target.add_argument("--name", help="Exact organization name.")

    add_domain_command_parsers(sub)

    return parser


async def dispatch(args: argparse.Namespace) -> dict[str, Any] | None:
    cfg = load_config()
    if args.command == "version":
        update = _ACTIVE_UPDATE.get()
        return {
            "data": {
                "cli_version": __version__,
                "api_base_url": cfg.api_base_url,
                **updates.describe(update),
                "update": update or {"status": "managed_externally"},
            }
        }
    if args.command == "upgrade":
        # Bootstrap already installed a uv tool release before dispatch; report it.
        return {"data": updates.upgrade_result(_ACTIVE_UPDATE.get())}
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
        sync_current_organization_from_whoami(cfg, data)
        return {"data": whoami_view(data)}
    if args.command == "org":
        return await dispatch_org(args, cfg)
    if args.command == "schema":
        name = " ".join([args.name, *getattr(args, "path_rest", [])]) if args.name else None
        return {"data": schema_payload(name)}
    if getattr(args, "domain_command", None):
        return await dispatch_domain_command(args, cfg)
    raise RuntimeError(f"Unknown command: {args.command}")


async def dispatch_config(args: argparse.Namespace) -> dict[str, Any]:
    cfg = load_config()
    if args.config_command == "get":
        return {"data": cfg.safe_dict()}
    if cfg.auth.is_host_managed():
        raise RuntimeError("managed_auth")
    cfg = update_config(
        api_base_url=args.api_base_url,
        site_url=args.site_url,
    )
    return {"data": cfg.safe_dict()}


async def dispatch_auth(args: argparse.Namespace, cfg: Config) -> dict[str, Any]:
    if args.auth_command != "status" and cfg.auth.is_host_managed():
        raise RuntimeError("managed_auth")
    if args.auth_command == "logout":
        delete_auth_credentials()
        cfg.auth = AuthState()
        cfg.organization = OrganizationState()
        cfg.pending_auth = PendingAuthState()
        save_config(cfg)
        return {"data": {"authenticated": False}}
    if args.auth_command == "status":
        clear_expired_pending_web_approval(cfg)
        auth_expired = cfg.auth.is_expired()
        authenticated = bool(auth_headers(cfg))
        status = {
            "authenticated": authenticated,
            "status": (
                "expired"
                if auth_expired
                else "authenticated"
                if authenticated
                else "unauthenticated"
            ),
            "reason": cfg.auth.resolution_error or ("credential_expired" if auth_expired else None),
            "auth_method": auth_method(cfg),
            "expires_at": cfg.auth.expires_at,
            "user": safe_user(cfg.auth.user),
            "organization": organization_view(cfg),
            "pending_web_approval": pending_web_approval_status(cfg),
        }
        if cfg.auth.provider is not None:
            status["credential_provider"] = cfg.auth.provider
        if cfg.auth.managed_by is not None:
            status["managed_by"] = cfg.auth.managed_by
        if cfg.auth.version is not None:
            status["version"] = cfg.auth.version
        return {"data": status}
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
        return {"data": data, "organization": data.get("organization")}
    data = await run_web_approval_login(
        config=cfg,
        timeout_seconds=args.timeout,
        open_browser=not args.no_browser,
        poll_interval_seconds=args.poll_interval,
    )
    return {"data": data, "organization": data.get("organization")}


def organization_view(cfg: Config) -> dict[str, Any] | None:
    return asdict(cfg.organization) if cfg.organization.id else None


# whoami also lists workspaces for CLIs older than 0.23; this CLI never shows them.
# Organization rows stay as the server sends them: hireaicreator `actor +preview-assign`
# still reads a row's default_workspace_id for its --target-workspace-id.
_WHOAMI_KEYS = ("user", "organizations", "default_organization_id", "default_organization_name")


def organizations_from_whoami(data: dict[str, Any]) -> tuple[list[dict[str, Any]], str | None]:
    """Organizations a login can act in, and its default one."""
    rows = [
        row
        for row in data.get("organizations") or []
        if isinstance(row, dict) and row.get("id")
    ]
    default_id = data.get("default_organization_id") or next(
        (row["id"] for row in rows if row.get("is_default")), None
    )
    return rows, default_id


def whoami_view(data: Any) -> Any:
    """The login and its organizations; never the workspaces the server also lists."""
    if not isinstance(data, dict):
        return data
    organizations, default_id = organizations_from_whoami(data)
    return {
        **{key: data.get(key) for key in _WHOAMI_KEYS},
        "organizations": organizations,
        "default_organization_id": default_id,
    }


async def dispatch_org(args: argparse.Namespace, cfg: Config) -> dict[str, Any]:
    if args.org_command == "current":
        current = organization_view(cfg)
        return {"organization": current, "data": current}
    data = await api_data(cfg, "GET", "/agent-cli/whoami")
    organizations, default_id = organizations_from_whoami(data)
    if args.org_command == "list":
        sync_current_organization_from_whoami(cfg, data)
        return {
            "data": {"organizations": organizations, "default_organization_id": default_id},
            "organization": organization_view(cfg),
        }
    if args.id:
        matches = [row for row in organizations if row.get("id") == args.id]
    else:
        matches = [row for row in organizations if row.get("name") == args.name]
    if not matches:
        raise RuntimeError(
            "not_found: organization is not available to the current credential; "
            "run `museoncli org list`"
        )
    if len(matches) > 1:
        raise RuntimeError(
            f"conflict: {len(matches)} organizations are named {args.name!r}; select one with --id"
        )
    selected = matches[0]
    cfg.organization = OrganizationState(id=selected.get("id"), name=selected.get("name"))
    save_config(cfg)
    return {"organization": organization_view(cfg), "data": selected}


def sync_current_organization_from_whoami(cfg: Config, data: dict[str, Any]) -> bool:
    """Refresh the selected organization's name from the server."""
    if not cfg.organization.id:
        return False
    organizations, _ = organizations_from_whoami(data)
    row = next((row for row in organizations if row["id"] == cfg.organization.id), None)
    next_organization = (
        OrganizationState(id=row["id"], name=row.get("name")) if row is not None else None
    )
    if next_organization is None or next_organization == cfg.organization:
        return False
    cfg.organization = next_organization
    save_config(cfg)
    return True


async def api_data(
    cfg: Config,
    method: str,
    path: str,
    *,
    json_body: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    unwrap_success: bool = True,
    idempotency_key: str | None = None,
) -> Any:
    return await _api_request(
        cfg,
        method,
        f"{cfg.api_base_url.rstrip('/')}{path}",
        json_body=json_body,
        params=params,
        unwrap_success=unwrap_success,
        **({"idempotency_key": idempotency_key} if idempotency_key is not None else {}),
    )


async def download_api_file(
    cfg: Config,
    path: str,
    *,
    params: dict[str, Any],
    destination: Path,
    max_bytes: int,
    allowed_content_types: set[str] | None = None,
) -> dict[str, Any]:
    """Stream one authenticated API response to a caller-owned temporary file."""
    if not auth_headers(cfg):
        raise RuntimeError("missing_auth")
    url = f"{cfg.api_base_url.rstrip('/')}{path}"
    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream(
            "GET", url, headers=_request_headers(cfg), params=params
        ) as response:
            if response.status_code >= 400:
                await response.aread()
                if response.status_code == 401:
                    raise RuntimeError("unauthorized")
                if response.status_code == 403:
                    raise RuntimeError(forbidden_error_message(response))
                if response.status_code == 426:
                    raise cli_outdated_error(response)
                raise ApiRequestError(response.status_code, response_error_payload(response))
            content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
            if content_type not in (allowed_content_types or {
                "video/mp4",
                "video/quicktime",
                "video/webm",
                "video/x-msvideo",
            }):
                raise RuntimeError("unsupported_media_type")
            declared_length = response.headers.get("content-length")
            if declared_length:
                try:
                    if int(declared_length) < 1 or int(declared_length) > max_bytes:
                        raise RuntimeError("invalid_media_size")
                except ValueError as exc:
                    raise RuntimeError("invalid_content_length") from exc
            written = 0
            with os.fdopen(os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as output:
                async for chunk in response.aiter_bytes():
                    written += len(chunk)
                    if written > max_bytes:
                        raise RuntimeError("media_too_large")
                    output.write(chunk)
                output.flush()
                os.fsync(output.fileno())
            if written < 1 or (declared_length and written != int(declared_length)):
                raise RuntimeError("media_length_mismatch")
            return {"content_type": content_type, "bytes": written}


async def _api_request(
    cfg: Config,
    method: str,
    url: str,
    *,
    json_body: dict[str, Any] | None,
    params: dict[str, Any] | None,
    unwrap_success: bool,
    idempotency_key: str | None = None,
) -> Any:
    if not auth_headers(cfg):
        raise RuntimeError("missing_auth")
    response = await _api_send(
        cfg, method, url, json_body=json_body, params=params,
        **({"idempotency_key": idempotency_key} if idempotency_key is not None else {}),
    )
    if response.status_code == 401:
        raise RuntimeError("unauthorized")
    if response.status_code == 403:
        raise RuntimeError(forbidden_error_message(response))
    if response.status_code == 426:
        raise cli_outdated_error(response)
    if response.status_code >= 400:
        raise ApiRequestError(response.status_code, response_error_payload(response))
    if response.status_code == 204:
        return None
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
    idempotency_key: str | None = None,
) -> httpx.Response:
    last_error: httpx.ConnectError | httpx.ConnectTimeout | None = None
    for attempt in range(1, _API_CONNECT_MAX_ATTEMPTS + 1):
        try:
            async with httpx.AsyncClient(timeout=None) as client:
                return await client.request(
                    method,
                    url,
                    headers={**_request_headers(cfg), **({"Idempotency-Key": idempotency_key} if idempotency_key is not None else {})},
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
    organization_id = _ACTIVE_ORGANIZATION_ID.get()
    if headers and organization_id:
        headers[ORGANIZATION_HEADER] = organization_id
    return headers


async def api_data_v2(
    cfg: Config,
    method: str,
    path: str,
    *,
    json_body: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    unwrap_success: bool = True,
    idempotency_key: str | None = None,
) -> Any:
    return await _api_request(
        cfg,
        method,
        f"{api_version_base_url(cfg, version='v2')}{path}",
        json_body=json_body,
        params=params,
        unwrap_success=unwrap_success,
        **({"idempotency_key": idempotency_key} if idempotency_key is not None else {}),
    )


def api_version_base_url(cfg: Config, *, version: str) -> str:
    base = cfg.api_base_url.rstrip("/")
    if base.endswith("/api/v1"):
        return f"{base[: -len('/api/v1')]}/api/{version}"
    return f"{base}/api/{version}"


def organization_id_arg(args: argparse.Namespace, arguments: dict[str, Any]) -> str | None:
    """--organization-id (or organization_id in --args-json); it never travels in a body."""
    value = getattr(args, "organization_id", None) or arguments.pop("organization_id", None)
    if value is None:
        return None
    _validate_uuid_value("organization_id", value)
    return str(value)


def envelope_organization(
    cfg: Config, organization_id: str | None
) -> dict[str, Any] | None:
    """The organization a command addressed, for the envelope's ``organization`` key."""
    if organization_id and organization_id != cfg.organization.id:
        return {"id": organization_id, "name": None}
    return organization_view(cfg)


def with_organization_key(result: Any, organization: dict[str, Any] | None) -> Any:
    """Put ``organization`` right after the envelope's ``command`` key."""
    if not isinstance(result, dict) or "command" not in result or "organization" in result:
        return result
    output: dict[str, Any] = {}
    for key, value in result.items():
        output[key] = value
        if key == "command":
            output["organization"] = organization
    return output


# Museon resource IDs are always canonical UUIDs, but agent-driven callers have
# sent placeholders ("?") and free-form text ("Page 2: 50 accounts") where IDs
# belong. Validate by key name before any HTTP call so the agent gets a
# self-correcting error instead of a production 4xx/500.
_UUID_SCALAR_ARGUMENT_KEYS = frozenset(
    {
        "id",
        "account_id",
        "campaign_id",
        "creator_id",
        "content_id",
        "version_id",
        "schedule_item_id",
        "task_id",
        "job_id",
        "operation_id",
        "plan_id",
        "run_id",
        "persona_id",
        "product_id",
        "format_id",
        "topic_direction_id",
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
        "resume_format_ids",
        "resume_topic_ids",
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
    arguments: dict[str, Any],
    workspace_id: str | None = None,
) -> Any:
    """Upload one media file. ``workspace_id`` is only ever given by hireaicreator."""
    media_type = str(arguments.get("media_type") or "image")
    path = Path(str(arguments.get("file") or "")).expanduser()
    if not path.is_file():
        raise RuntimeError(f"media file not found: {path}")
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    form_data = {
        **({"workspace_id": workspace_id} if workspace_id else {}),
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
    if response.status_code == 426:
        raise cli_outdated_error(response)
    if response.status_code >= 400:
        raise ApiRequestError(response.status_code, response_error_payload(response))
    receipt = response.json()
    if not isinstance(receipt, dict) or receipt.get("success") is not True:
        raise RuntimeError("media_upload_failed")
    data = receipt.get("data")
    asset = data.get("asset") if isinstance(data, dict) else None
    media_id = asset.get("media_id") if isinstance(asset, dict) else None
    try:
        UUID(str(media_id))
    except (ValueError, TypeError, AttributeError):
        raise RuntimeError(
            "media_upload_unverified: receipt has no valid media_id; "
            "do not retry the write blindly"
        ) from None
    return receipt


async def upload_artifact_file(
    cfg: Config,
    *,
    arguments: dict[str, Any],
) -> Any:
    path = Path(str(arguments.get("file") or "")).expanduser()
    if not path.is_file():
        raise RuntimeError(f"artifact file not found: {path}")
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    private_media_file = arguments.get("media_type") == "file"
    form_data: dict[str, str] = {}
    if private_media_file:
        form_data["file_id"] = str(arguments["file_id"])
    else:
        form_data.update(
            {
                "artifact_type": str(arguments.get("artifact_type") or "file"),
                "source_file_path": str(arguments.get("file") or path.name),
                "public": "true" if bool(arguments.get("public", True)) else "false",
            }
        )
        for form_key, argument_key in (("artifact_id", "artifact_id"), ("title", "title")):
            value = arguments.get(argument_key)
            if value is not None:
                form_data[form_key] = str(value)
        for form_key, argument_key in (
            ("runtime_context_json", "runtime_context"),
            ("metadata_json", "metadata"),
        ):
            value = arguments.get(argument_key)
            if isinstance(value, dict):
                form_data[form_key] = json.dumps(
                    value, ensure_ascii=False, separators=(",", ":")
                )
    if private_media_file and arguments.get("title") is not None:
        form_data["title"] = str(arguments["title"])
    if not auth_headers(cfg):
        raise RuntimeError("missing_auth")
    with path.open("rb") as handle:
        files = {"file": (path.name, handle, content_type)}
        async with httpx.AsyncClient(timeout=None) as client:
            response = await client.post(
                (
                    f"{cfg.api_base_url.rstrip()}/media/files"
                    if private_media_file
                    else f"{cfg.api_base_url.rstrip()}/agent-cli/artifacts/upload"
                ),
                headers=_request_headers(cfg),
                data=form_data,
                files=files,
            )
    if response.status_code == 401:
        raise RuntimeError("unauthorized")
    if response.status_code == 403:
        raise RuntimeError(forbidden_error_message(response))
    if response.status_code == 426:
        raise cli_outdated_error(response)
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
    if cfg.auth.method:
        return cfg.auth.method
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
    if isinstance(exc, UsageError):
        return "usage_error"
    if isinstance(exc, CliOutdatedError):
        return "cli_outdated"
    if isinstance(exc, ApiRequestError):
        if exc.status_code in {400, 422}:
            return "invalid_input"
        if exc.status_code == 404:
            return "not_found"
        if exc.status_code == 409:
            return "conflict"
        if exc.status_code == 429:
            return "rate_limited"
        if exc.status_code == 503:
            return "service_unavailable"
        if exc.status_code >= 500:
            return "server_error"
    if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout)):
        return "network_error"
    text = str(exc)
    for prefixed_reason in ("not_found", "conflict", "missing_organization", "network_error"):
        if text == prefixed_reason or text.startswith(f"{prefixed_reason}:"):
            return prefixed_reason
    if text in {
        "missing_auth",
        "unauthorized",
        "forbidden",
        "confirmation_required",
        "cli_outdated",
        "managed_auth",
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
    # A class name ("RuntimeError") told callers nothing; keep a stable category.
    return "command_failed" if isinstance(exc, RuntimeError) else "internal_error"


def exception_detail(exc: Exception) -> Any:
    return exc.detail if isinstance(exc, ApiRequestError) else str(exc)


def error_envelope(exc: Exception, *, command: str | None) -> tuple[dict[str, Any], int]:
    """Render one failure as the JSON error contract and its exit code.

    ``reason`` and ``detail`` keep their released meaning; ``error`` adds a stable
    shape: ``code`` (the same category as ``reason``), a readable ``message``, the
    server's own ``server_code`` when it sent one, ``http_status`` and ``retryable``.
    """
    reason = reason_from_exception(exc)
    detail = exception_detail(exc)
    message = _error_message(detail)
    error: dict[str, Any] = {"code": reason, "message": message.removeprefix(f"{reason}: ")}
    if isinstance(exc, ApiRequestError):
        error["http_status"] = exc.status_code
    if isinstance(detail, dict) and isinstance(detail.get("code"), str) and detail["code"]:
        error["server_code"] = detail["code"]
        if detail["code"] in _SERVER_CODE_MESSAGES and not detail.get("message"):
            error["message"] = _SERVER_CODE_MESSAGES[detail["code"]]
    if isinstance(exc, CliOutdatedError):
        error["hint"] = exc.detail.get("install_hint")
    error["retryable"] = reason in _RETRYABLE_REASONS
    payload: dict[str, Any] = {
        "ok": False,
        "command": command,
        "reason": reason,
        "detail": detail,
        "error": error,
    }
    if isinstance(exc, UsageError):
        if exc.usage:
            payload["usage"] = exc.usage
        error["hint"] = _usage_hint(command)
    return payload, _EXIT_CODE_BY_REASON.get(reason, EXIT_FAILURE)


def _usage_hint(command: str | None) -> str:
    if command:
        try:
            return f"Run `{get_command_spec(command).cli_path} --help` or `museoncli schema {command}`."
        except ValueError:
            pass
    return "Run `museoncli --help` or `museoncli schema` to list commands."


def _error_message(detail: Any) -> str:
    if isinstance(detail, dict):
        for key in ("message", "detail", "error"):
            value = detail.get(key)
            if isinstance(value, str) and value:
                return value
        return json.dumps(detail, ensure_ascii=False, sort_keys=True)[:500]
    if isinstance(detail, list):
        return json.dumps(detail, ensure_ascii=False)[:500]
    return str(detail)


def deprecation_notices(args: argparse.Namespace) -> list[str]:
    """Warn when a command was invoked through a name or flag it is moving away from."""
    notices: list[str] = []
    legacy = getattr(args, "legacy_invocation", None)
    command = getattr(args, "domain_command", None)
    if legacy and command:
        notices.append(
            f"`{legacy}` is deprecated and will be removed; use "
            f"`{get_command_spec(command).cli_path}` (same inputs and output)."
        )
    if command:
        notice = workspace_flag_notice(get_command_spec(command), getattr(args, "workspace_id", None))
        if notice:
            notices.append(notice)
    return notices


def invoked_command_name(args: argparse.Namespace) -> str | None:
    """Name the invoked command: a capability key, or ``<command>.<subcommand>``."""
    domain_command = getattr(args, "domain_command", None)
    if domain_command:
        return str(domain_command)
    command = getattr(args, "command", None)
    if not command:
        return None
    for attribute in ("auth_command", "org_command", "config_command"):
        subcommand = getattr(args, attribute, None)
        if subcommand:
            return f"{command}.{subcommand}"
    return str(command)


def forbidden_error_message(response: httpx.Response) -> str:
    detail = response_error_detail(response)
    if not detail:
        return "forbidden"
    return f"forbidden: {detail}"


def response_error_payload(response: httpx.Response) -> Any:
    try:
        payload = response.json()
    except Exception:
        return response.text[:500].strip() or f"HTTP {response.status_code}"
    if isinstance(payload, dict) and "detail" in payload:
        return payload["detail"]
    return payload


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
    organization_id = organization_id_arg(args, arguments)
    if not keeps_workspace(spec.domain) and "workspace_id" in arguments:
        raise ValueError(
            "workspace_id is not an input: MuseOn addresses organizations. Drop it, and pass "
            "--organization-id (or select one with `museoncli org select`) to act in another "
            "organization."
        )
    # HireAICreator validates declared UUID fields in its strict recursive schema.
    # Its account_id is an API string, and public collection tokens are not UUIDs.
    if spec.domain.value not in {"hireaicreator", "cloud-phone"}:
        validate_uuid_arguments(arguments)
    organization = envelope_organization(cfg, organization_id)

    def envelope(result: Any) -> Any:
        return with_workspace_key(spec, with_organization_key(result, organization), arguments)

    dry_run = bool(getattr(args, "dry_run", False))
    if dry_run and not spec.dry_run_reads_server:
        if spec.domain.value == "cloud-phone":
            from museoncli.domains.cloud_phone import redact

            arguments = redact(arguments)
        return envelope(domain_command_dry_run_envelope(spec.schema_name, arguments))
    if spec.requires_confirmation and not dry_run and not getattr(args, "yes", False):
        raise RuntimeError("confirmation_required")
    executor = command_executor(spec.schema_name)

    async def run(page_arguments: dict[str, Any]) -> dict[str, Any]:
        ctx = CommandContext(
            cfg=cfg,
            spec=spec,
            args=args,
            arguments=page_arguments,
            organization_id=organization_id or cfg.organization.id,
            api_data=api_data,
            api_data_v2=api_data_v2,
            upload_media_file=upload_media_file,
            upload_artifact_file=upload_artifact_file,
            download_api_file=download_api_file,
        )
        return await executor(ctx)

    command_token = _ACTIVE_COMMAND_NAME.set(spec.schema_name)
    organization_token = _ACTIVE_ORGANIZATION_ID.set(organization_id)
    try:
        if getattr(args, "all", False):
            return envelope(await collect_all_pages(run, arguments))
        result = await run(arguments)
    finally:
        _ACTIVE_ORGANIZATION_ID.reset(organization_token)
        _ACTIVE_COMMAND_NAME.reset(command_token)
    if isinstance(result, dict) and "page_info" not in result:
        info = page_info(result)
        if info:
            result["page_info"] = info
    return envelope(result)


if __name__ == "__main__":
    main()
