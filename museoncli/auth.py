from __future__ import annotations

import time
import webbrowser
from datetime import datetime
from sys import stderr
from typing import Any

import httpx

from museoncli import __version__
from museoncli.config import AuthState, Config, PendingAuthState, WorkspaceState, save_config

AGENT_CLI_API_SCOPE = "agent_cli.access"


async def run_web_approval_login(
    *,
    config: Config,
    timeout_seconds: int = 300,
    open_browser: bool = True,
    poll_interval_seconds: float = 2.0,
) -> dict[str, Any]:
    start = await begin_web_approval(config=config)
    verification_url = _verification_url(start)
    print(f"Open this URL to authorize Museon CLI:\n{verification_url}", file=stderr, flush=True)
    user_code = start.get("user_code")
    if user_code:
        print(f"Code: {user_code}", file=stderr, flush=True)
    if open_browser:
        webbrowser.open(verification_url)

    return await poll_web_approval_until_terminal(
        config=config,
        device_code=str(start["device_code"]),
        timeout_seconds=timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
        server_poll_interval_seconds=float(start.get("interval") or 0),
        clear_pending=True,
    )


async def start_web_approval_login(*, config: Config) -> dict[str, Any]:
    start = await begin_web_approval(config=config)
    expires_in = int(start.get("expires_in") or 0)
    expires_at = int(time.time()) + expires_in if expires_in else None
    config.pending_auth = PendingAuthState(
        device_code=str(start["device_code"]),
        user_code=_optional_text(start.get("user_code")),
        verification_uri=_optional_text(start.get("verification_uri")),
        verification_uri_complete=_optional_text(start.get("verification_uri_complete")),
        expires_at=expires_at,
        interval=float(start.get("interval") or 0) or None,
    )
    save_config(config)
    return {
        "authenticated": False,
        "status": "pending",
        "verification_uri": config.pending_auth.verification_uri,
        "verification_uri_complete": config.pending_auth.verification_uri_complete,
        "user_code": config.pending_auth.user_code,
        "expires_at": config.pending_auth.expires_at,
        "expires_in": expires_in,
        "interval": config.pending_auth.interval,
    }


async def finish_pending_web_approval_login(
    *,
    config: Config,
    wait: bool = False,
    timeout_seconds: int = 300,
    poll_interval_seconds: float = 2.0,
) -> dict[str, Any]:
    pending = config.pending_auth
    device_code = pending.device_code
    if not device_code:
        raise RuntimeError("No pending Museon CLI authorization. Run `museoncli auth start` first.")
    if pending.expires_at and pending.expires_at <= int(time.time()):
        config.pending_auth = PendingAuthState()
        save_config(config)
        return {"authenticated": False, "status": "expired"}
    if wait and timeout_seconds > 0:
        return await poll_web_approval_until_terminal(
            config=config,
            device_code=device_code,
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
            server_poll_interval_seconds=pending.interval or 0,
            clear_pending=True,
        )
    poll = await poll_web_approval_once(config=config, device_code=device_code)
    status_value = str(poll.get("status") or "")
    if status_value == "pending":
        return {
            "authenticated": False,
            "status": "pending",
            "verification_uri": pending.verification_uri,
            "verification_uri_complete": pending.verification_uri_complete,
            "user_code": pending.user_code,
            "expires_at": pending.expires_at,
        }
    return complete_web_approval_poll(config=config, poll=poll, clear_pending=True)


async def begin_web_approval(*, config: Config) -> dict[str, Any]:
    start = await api_post_public(
        config=config,
        path="/agent-cli/auth/device/start",
        json_body={
            "requested_workspace_id": config.workspace.id,
            "requested_scopes": [AGENT_CLI_API_SCOPE],
        },
    )
    device_code = str(start.get("device_code") or "")
    if not device_code:
        raise RuntimeError("CLI authorization did not return a device code.")
    if not _verification_url(start):
        raise RuntimeError("CLI authorization did not return a verification URL.")
    return start


async def poll_web_approval_until_terminal(
    *,
    config: Config,
    device_code: str,
    timeout_seconds: int,
    poll_interval_seconds: float,
    server_poll_interval_seconds: float = 0,
    clear_pending: bool = False,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    effective_poll_interval = server_poll_interval_seconds or poll_interval_seconds
    while True:
        if time.monotonic() >= deadline:
            raise RuntimeError("Timed out waiting for CLI authorization.")
        poll = await poll_web_approval_once(config=config, device_code=device_code)
        status_value = str(poll.get("status") or "")
        if status_value == "pending":
            await _sleep(effective_poll_interval)
            continue
        return complete_web_approval_poll(config=config, poll=poll, clear_pending=clear_pending)


async def poll_web_approval_once(*, config: Config, device_code: str) -> dict[str, Any]:
    return await api_get_public(
        config=config,
        path="/agent-cli/auth/device/poll",
        params={"device_code": device_code},
    )


def complete_web_approval_poll(
    *,
    config: Config,
    poll: dict[str, Any],
    clear_pending: bool,
) -> dict[str, Any]:
    status_value = str(poll.get("status") or "")
    if status_value == "approved":
        api_key = str(poll.get("api_key") or "")
        if not api_key:
            raise RuntimeError("CLI authorization completed without an API key.")
        user = _safe_user(poll.get("user"))
        workspace = poll.get("workspace") if isinstance(poll.get("workspace"), dict) else None
        credential_expires_at = _timestamp(poll.get("credential_expires_at"))
        config.auth = AuthState(
            api_key=api_key,
            expires_at=credential_expires_at,
            user=user,
        )
        if workspace:
            config.workspace = WorkspaceState(
                id=workspace.get("id"),
                name=workspace.get("name"),
                organization_id=workspace.get("organization_id"),
                organization_name=workspace.get("organization_name"),
            )
        if clear_pending:
            config.pending_auth = PendingAuthState()
        save_config(config)
        return {
            "authenticated": True,
            "status": "approved",
            "auth_method": "api_key",
            "user": user,
            "workspace": workspace,
            "key_prefix": poll.get("key_prefix"),
            "credential_expires_at": poll.get("credential_expires_at"),
        }
    if clear_pending and status_value in {"consumed", "expired", "denied"}:
        config.pending_auth = PendingAuthState()
        save_config(config)
    if status_value == "consumed":
        raise RuntimeError("This CLI authorization was already used. Run auth start again.")
    if status_value == "expired":
        raise RuntimeError("CLI authorization expired. Run auth start again.")
    if status_value == "denied":
        raise RuntimeError("CLI authorization was denied.")
    raise RuntimeError(f"Unexpected CLI authorization status: {status_value or 'unknown'}")


async def api_get_public(
    *,
    config: Config,
    path: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(
            f"{config.api_base_url.rstrip('/')}{path}",
            params=params,
        )
    if response.status_code >= 400:
        raise RuntimeError(f"API request failed: HTTP {response.status_code} {response.text[:200]}")
    payload = response.json()
    return payload.get("data") if isinstance(payload, dict) and "data" in payload else payload


async def api_post_public(
    *,
    config: Config,
    path: str,
    json_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"{config.api_base_url.rstrip('/')}{path}",
            json=json_body,
        )
    if response.status_code >= 400:
        raise RuntimeError(f"API request failed: HTTP {response.status_code} {response.text[:200]}")
    payload = response.json()
    return payload.get("data") if isinstance(payload, dict) and "data" in payload else payload


def auth_headers(config: Config) -> dict[str, str]:
    if not config.auth.api_key or config.auth.is_expired():
        return {}
    headers = {"X-API-KEY": config.auth.api_key}
    headers["X-CLI-Version"] = __version__
    headers.update(_usage_context_headers(config))
    return headers


def _usage_context_headers(config: Config) -> dict[str, str]:
    runtime_context = config.runtime_context if isinstance(config.runtime_context, dict) else {}
    conversation_id = _optional_text(runtime_context.get("conversation_id"))
    sandbox_id = _optional_text(runtime_context.get("sandbox_id"))
    actor_id = _optional_text(runtime_context.get("actor_id"))
    organization_id = _optional_text(runtime_context.get("organization_id"))
    workspace_id = _optional_text(runtime_context.get("workspace_id"))

    headers: dict[str, str] = {}
    if conversation_id:
        headers["X-Museon-Conversation-Id"] = conversation_id
        headers["X-Museon-Usage-Business-Type"] = "agent_session"
        headers["X-Museon-Usage-Business-Id"] = conversation_id
    if sandbox_id:
        headers["X-Museon-Sandbox-Id"] = sandbox_id
    if actor_id:
        headers["X-Museon-Actor-Id"] = actor_id
    if organization_id:
        headers["X-Museon-Organization-Id"] = organization_id
    if workspace_id:
        headers["X-Museon-Workspace-Id"] = workspace_id
    return headers


def _safe_user(user: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(user, dict):
        return None
    return {"id": user.get("id"), "email": user.get("email")}


def _verification_url(start: dict[str, Any]) -> str:
    return str(start.get("verification_uri_complete") or start.get("verification_uri") or "")


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _timestamp(value: Any) -> int | None:
    text = _optional_text(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return int(parsed.timestamp())


async def _sleep(seconds: float) -> None:
    import asyncio

    await asyncio.sleep(seconds)
