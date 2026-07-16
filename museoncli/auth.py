from __future__ import annotations

import base64
import hashlib
import http.server
import os
import queue
import secrets
import threading
import time
import webbrowser
from dataclasses import dataclass
from sys import stderr
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from museoncli import __version__
from museoncli.config import (
    DEFAULT_WORKSPACE_NAME,
    AuthState,
    Config,
    PendingAuthState,
    WorkspaceState,
    save_config,
)

AGENT_CLI_API_SCOPE = "agent_cli.access"


@dataclass(frozen=True)
class PkceMaterial:
    verifier: str
    challenge: str


@dataclass(frozen=True)
class CallbackResult:
    code: str | None = None
    error: str | None = None
    cli_state: str | None = None


def make_pkce() -> PkceMaterial:
    verifier = base64.urlsafe_b64encode(os.urandom(48)).decode("ascii").rstrip("=")
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return PkceMaterial(verifier=verifier, challenge=challenge)


def build_authorize_url(
    *,
    supabase_url: str,
    provider: str,
    redirect_to: str,
    challenge: str,
) -> str:
    params = {
        "provider": provider,
        "redirect_to": redirect_to,
        "code_challenge": challenge,
        "code_challenge_method": "s256",
    }
    return f"{supabase_url.rstrip('/')}/auth/v1/authorize?{urlencode(params)}"


class _CallbackServer:
    def __init__(self, *, host: str, port: int, expected_state: str) -> None:
        self.host = host
        self.port = port
        self.expected_state = expected_state
        self.results: queue.Queue[CallbackResult] = queue.Queue(maxsize=1)
        self.httpd: http.server.ThreadingHTTPServer | None = None
        self.thread: threading.Thread | None = None

    @property
    def callback_url(self) -> str:
        if self.httpd is None:
            return f"http://{self.host}:{self.port}/callback"
        return f"http://{self.host}:{self.httpd.server_port}/callback"

    def start(self) -> None:
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: Any) -> None:
                return

            def do_GET(self) -> None:
                parsed = urlparse(self.path)
                decoded = parse_qs(parsed.query)
                result = CallbackResult(
                    code=_first_query_value(decoded, "code"),
                    error=_first_query_value(decoded, "error_description")
                    or _first_query_value(decoded, "error"),
                    cli_state=_first_query_value(decoded, "cli_state"),
                )
                ok = (
                    result.error is None
                    and result.cli_state == outer.expected_state
                    and result.code
                )
                body = (
                    "Museon CLI login complete. You can close this tab."
                    if ok
                    else "Museon CLI login failed. Return to the terminal."
                )
                self.send_response(200 if ok else 400)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write(body.encode("utf-8"))
                outer.results.put(result)

        self.httpd = http.server.ThreadingHTTPServer((self.host, self.port), Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def wait(self, *, timeout_seconds: int) -> CallbackResult:
        try:
            return self.results.get(timeout=timeout_seconds)
        finally:
            if self.httpd is not None:
                self.httpd.shutdown()


async def run_pkce_login(
    *,
    config: Config,
    provider: str = "google",
    host: str = "127.0.0.1",
    port: int = 0,
    timeout_seconds: int = 300,
    open_browser: bool = True,
    prompt_workspace: bool = True,
) -> dict[str, Any]:
    if not config.supabase_url or not config.supabase_anon_key:
        raise RuntimeError(
            "Supabase config is missing. Set MUSEON_SUPABASE_URL and "
            "MUSEON_SUPABASE_ANON_KEY, or run `museoncli config set`."
        )
    pkce = make_pkce()
    cli_state = secrets.token_urlsafe(24)
    server = _CallbackServer(host=host, port=port, expected_state=cli_state)
    server.start()
    redirect_to = f"{server.callback_url}?{urlencode({'cli_state': cli_state})}"
    authorize_url = build_authorize_url(
        supabase_url=config.supabase_url,
        provider=provider,
        redirect_to=redirect_to,
        challenge=pkce.challenge,
    )
    if open_browser:
        webbrowser.open(authorize_url)
    else:
        print(authorize_url, file=stderr, flush=True)

    callback = server.wait(timeout_seconds=timeout_seconds)
    if callback.error:
        raise RuntimeError(callback.error)
    if callback.cli_state != cli_state:
        raise RuntimeError("OAuth callback cli_state mismatch.")
    if not callback.code:
        raise RuntimeError("OAuth callback did not include an authorization code.")

    token_payload = await exchange_pkce_code(
        config=config,
        auth_code=callback.code,
        verifier=pkce.verifier,
    )
    now = int(time.time())
    expires_in = int(token_payload.get("expires_in") or 0)
    config.auth = AuthState(
        access_token=token_payload.get("access_token"),
        refresh_token=token_payload.get("refresh_token"),
        expires_at=now + expires_in if expires_in else None,
        user=_safe_user(token_payload.get("user")),
    )
    whoami = await api_get(config=config, path="/agent-cli/whoami")
    workspace = choose_workspace(
        whoami.get("data", {}).get("workspaces") or [], prompt=prompt_workspace
    )
    if workspace:
        config.workspace = WorkspaceState(
            id=workspace.get("id"),
            name=workspace.get("name"),
            organization_id=workspace.get("organization_id"),
            organization_name=workspace.get("organization_name"),
        )
    save_config(config)
    return {
        "authenticated": True,
        "auth_method": "bearer",
        "user": _safe_user(config.auth.user),
        "workspace": workspace,
    }


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
    timeout_seconds: int = 0,
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
            "site_url": config.site_url,
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
        config.auth = AuthState(api_key=api_key, user=user)
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


async def exchange_pkce_code(
    *,
    config: Config,
    auth_code: str,
    verifier: str,
) -> dict[str, Any]:
    url = f"{config.supabase_url.rstrip('/')}/auth/v1/token?grant_type=pkce"
    headers = {
        "apikey": config.supabase_anon_key or "",
        "Authorization": f"Bearer {config.supabase_anon_key}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            url, headers=headers, json={"auth_code": auth_code, "code_verifier": verifier}
        )
    if response.status_code >= 400:
        raise RuntimeError(f"Supabase token exchange failed: HTTP {response.status_code}")
    return response.json()


async def refresh_access_token(config: Config) -> bool:
    """Exchange the stored refresh token for a fresh access token.

    Returns True when new tokens were persisted; False means the caller should
    surface the original auth failure (no refresh token, API-key auth, or the
    refresh itself was rejected).
    """
    refresh_token = config.auth.refresh_token
    if (
        not refresh_token
        or config.auth.api_key
        or not config.supabase_url
        or not config.supabase_anon_key
    ):
        return False
    url = f"{config.supabase_url.rstrip('/')}/auth/v1/token?grant_type=refresh_token"
    headers = {
        "apikey": config.supabase_anon_key,
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                url, headers=headers, json={"refresh_token": refresh_token}
            )
    except httpx.HTTPError:
        return False
    if response.status_code >= 400:
        return False
    payload = response.json()
    access_token = payload.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        return False
    config.auth.access_token = access_token
    next_refresh = payload.get("refresh_token")
    if isinstance(next_refresh, str) and next_refresh:
        config.auth.refresh_token = next_refresh
    expires_at = payload.get("expires_at")
    if isinstance(expires_at, int):
        config.auth.expires_at = expires_at
    save_config(config)
    return True


async def api_get(*, config: Config, path: str) -> dict[str, Any]:
    headers = auth_headers(config)
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(f"{config.api_base_url.rstrip('/')}{path}", headers=headers)
    if response.status_code >= 400:
        raise RuntimeError(f"API request failed: HTTP {response.status_code} {response.text[:200]}")
    return response.json()


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
    if config.auth.api_key:
        headers = {"X-API-KEY": config.auth.api_key}
    elif config.auth.access_token:
        headers = {"Authorization": f"Bearer {config.auth.access_token}"}
    else:
        return {}
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


def choose_workspace(workspaces: list[dict[str, Any]], *, prompt: bool) -> dict[str, Any] | None:
    if not workspaces:
        return None
    for workspace in workspaces:
        if _is_default_workspace(workspace):
            return workspace
    if not prompt or len(workspaces) == 1:
        return workspaces[0]
    print("Select workspace:", flush=True)
    for idx, workspace in enumerate(workspaces, start=1):
        print(f"{idx}. {workspace.get('name')} ({workspace.get('id')})", flush=True)
    while True:
        raw = input("Workspace number: ").strip()
        try:
            index = int(raw)
        except ValueError:
            continue
        if 1 <= index <= len(workspaces):
            return workspaces[index - 1]


def _safe_user(user: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(user, dict):
        return None
    return {"id": user.get("id"), "email": user.get("email")}


def _verification_url(start: dict[str, Any]) -> str:
    return str(start.get("verification_uri_complete") or start.get("verification_uri") or "")


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _workspace_name_key(value: Any) -> str:
    return "".join(character for character in str(value or "").casefold() if character.isalnum())


def _is_default_workspace(workspace: dict[str, Any]) -> bool:
    return bool(workspace.get("is_default")) or _workspace_name_key(
        workspace.get("name")
    ) == _workspace_name_key(DEFAULT_WORKSPACE_NAME)


async def _sleep(seconds: float) -> None:
    import asyncio

    await asyncio.sleep(seconds)


def _first_query_value(values: dict[str, list[str]], key: str) -> str | None:
    item = values.get(key)
    if not item:
        return None
    return item[0]
