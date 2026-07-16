from __future__ import annotations

import asyncio
from urllib.parse import parse_qs, urlparse

from museoncli import __version__
from museoncli.config import AuthState, Config, PendingAuthState, WorkspaceState
import museoncli.auth as auth_module
from museoncli.auth import auth_headers, build_authorize_url, choose_workspace, make_pkce


def test_authorize_url_uses_pkce_without_oauth_state() -> None:
    pkce = make_pkce()
    url = build_authorize_url(
        supabase_url="https://example.supabase.co",
        provider="google",
        redirect_to="http://127.0.0.1:5000/callback?cli_state=nonce",
        challenge=pkce.challenge,
    )

    query = parse_qs(urlparse(url).query)

    assert query["provider"] == ["google"]
    assert query["code_challenge"] == [pkce.challenge]
    assert query["code_challenge_method"] == ["s256"]
    assert "state" not in query
    assert "cli_state=nonce" in query["redirect_to"][0]


def test_choose_workspace_prefers_museon_official() -> None:
    workspace = choose_workspace(
        [
            {"id": "ws-other", "name": "Other"},
            {"id": "ws-official", "name": "MuseOn Official"},
        ],
        prompt=False,
    )

    assert workspace == {"id": "ws-official", "name": "MuseOn Official"}


def test_choose_workspace_accepts_legacy_museon_official_casing() -> None:
    workspace = choose_workspace(
        [
            {"id": "ws-other", "name": "Other"},
            {"id": "ws-official", "name": "Museon Official"},
        ],
        prompt=False,
    )

    assert workspace == {"id": "ws-official", "name": "Museon Official"}


def test_auth_headers_prefers_api_key() -> None:
    cfg = Config()
    cfg.auth = AuthState(access_token="bearer-token", api_key="api-key")

    assert auth_headers(cfg) == {"X-API-KEY": "api-key", "X-CLI-Version": __version__}


def test_auth_headers_adds_usage_context_when_available() -> None:
    cfg = Config()
    cfg.auth = AuthState(api_key="api-key")
    cfg.workspace = WorkspaceState(id="ws-selected")
    cfg.runtime_context = {
        "conversation_id": "conv-1",
        "sandbox_id": "sandbox-1",
        "actor_id": "actor-1",
        "organization_id": "org-1",
        "workspace_id": "ws-runtime",
    }

    assert auth_headers(cfg) == {
        "X-API-KEY": "api-key",
        "X-CLI-Version": __version__,
        "X-Museon-Conversation-Id": "conv-1",
        "X-Museon-Usage-Business-Type": "agent_session",
        "X-Museon-Usage-Business-Id": "conv-1",
        "X-Museon-Sandbox-Id": "sandbox-1",
        "X-Museon-Actor-Id": "actor-1",
        "X-Museon-Organization-Id": "org-1",
        "X-Museon-Workspace-Id": "ws-runtime",
    }


def test_auth_headers_do_not_fallback_usage_context_to_selected_workspace() -> None:
    cfg = Config()
    cfg.auth = AuthState(api_key="api-key")
    cfg.workspace = WorkspaceState(id="ws-selected")

    assert auth_headers(cfg) == {"X-API-KEY": "api-key", "X-CLI-Version": __version__}


def test_auth_headers_do_not_authenticate_with_usage_context_only() -> None:
    cfg = Config()
    cfg.runtime_context = {"conversation_id": "conv-1"}

    assert auth_headers(cfg) == {}


def test_web_approval_login_stores_api_key(monkeypatch) -> None:
    cfg = Config()
    cfg.api_base_url = "https://api.museon.ai/api/v1"
    cfg.site_url = "https://museon.ai"
    saved: list[AuthState] = []

    async def fake_post_public(
        *,
        config: Config,
        path: str,
        json_body: dict | None = None,
    ) -> dict:
        assert config is cfg
        assert path == "/agent-cli/auth/device/start"
        assert json_body == {
            "requested_workspace_id": None,
            "site_url": "https://museon.ai",
            "requested_scopes": [auth_module.AGENT_CLI_API_SCOPE],
        }
        return {
            "device_code": "device-1",
            "user_code": "MUSEON-ABC123",
            "verification_uri_complete": "https://museon.ai/cli/authorize?device_code=device-1",
            "interval": 0,
        }

    async def fake_get_public(
        *,
        config: Config,
        path: str,
        params: dict | None = None,
    ) -> dict:
        assert config is cfg
        assert path == "/agent-cli/auth/device/poll"
        assert params == {"device_code": "device-1"}
        return {
            "status": "approved",
            "api_key": "raw-api-key",
            "key_prefix": "museon_test",
            "user": {"id": "user-1", "email": "staff@museon.ai"},
            "workspace": {
                "id": "workspace-1",
                "name": "MuseOn Official",
                "organization_id": "org-1",
                "organization_name": "MuseOn",
            },
        }

    monkeypatch.setattr(auth_module, "api_post_public", fake_post_public)
    monkeypatch.setattr(auth_module, "api_get_public", fake_get_public)
    monkeypatch.setattr(auth_module.webbrowser, "open", lambda url: True)
    monkeypatch.setattr(auth_module, "save_config", lambda value: saved.append(value.auth))

    result = asyncio.run(auth_module.run_web_approval_login(config=cfg))

    assert result["auth_method"] == "api_key"
    assert cfg.auth.api_key == "raw-api-key"
    assert cfg.workspace.id == "workspace-1"
    assert cfg.workspace.organization_name == "MuseOn"
    assert saved[-1].api_key == "raw-api-key"


def test_web_approval_start_stores_pending_state_without_returning_device_code(
    monkeypatch,
) -> None:
    cfg = Config()
    cfg.api_base_url = "https://api.museon.ai/api/v1"
    cfg.site_url = "https://museon.ai"
    cfg.workspace = WorkspaceState(
        id="workspace-member",
        name="Member Workspace",
        organization_id="org-1",
    )
    saved: list[PendingAuthState] = []

    async def fake_post_public(
        *,
        config: Config,
        path: str,
        json_body: dict | None = None,
    ) -> dict:
        assert config is cfg
        assert path == "/agent-cli/auth/device/start"
        assert json_body == {
            "requested_workspace_id": "workspace-member",
            "site_url": "https://museon.ai",
            "requested_scopes": [auth_module.AGENT_CLI_API_SCOPE],
        }
        return {
            "device_code": "device-1",
            "user_code": "MUSEON-ABC123",
            "verification_uri": "https://museon.ai/cli/authorize",
            "verification_uri_complete": "https://museon.ai/cli/authorize?device_code=device-1",
            "expires_in": 600,
            "interval": 2,
        }

    monkeypatch.setattr(auth_module, "api_post_public", fake_post_public)
    monkeypatch.setattr(auth_module.time, "time", lambda: 1000)
    monkeypatch.setattr(
        auth_module,
        "save_config",
        lambda value: saved.append(value.pending_auth),
    )

    result = asyncio.run(auth_module.start_web_approval_login(config=cfg))

    assert result == {
        "authenticated": False,
        "status": "pending",
        "verification_uri": "https://museon.ai/cli/authorize",
        "verification_uri_complete": "https://museon.ai/cli/authorize?device_code=device-1",
        "user_code": "MUSEON-ABC123",
        "expires_at": 1600,
        "expires_in": 600,
        "interval": 2.0,
    }
    assert "device_code" not in result
    assert cfg.pending_auth.device_code == "device-1"
    assert saved[-1].device_code == "device-1"


def test_web_approval_finish_stores_api_key_and_clears_pending(monkeypatch) -> None:
    cfg = Config()
    cfg.pending_auth = PendingAuthState(
        device_code="device-1",
        verification_uri_complete="https://museon.ai/cli/authorize?device_code=device-1",
        expires_at=2000,
        interval=0,
    )
    saved: list[tuple[AuthState, PendingAuthState]] = []

    async def fake_get_public(
        *,
        config: Config,
        path: str,
        params: dict | None = None,
    ) -> dict:
        assert config is cfg
        assert path == "/agent-cli/auth/device/poll"
        assert params == {"device_code": "device-1"}
        return {
            "status": "approved",
            "api_key": "raw-api-key",
            "key_prefix": "museon_test",
            "user": {"id": "user-1", "email": "staff@museon.ai"},
            "workspace": {
                "id": "workspace-1",
                "name": "MuseOn Official",
                "organization_id": "org-1",
                "organization_name": "MuseOn",
            },
        }

    monkeypatch.setattr(auth_module, "api_get_public", fake_get_public)
    monkeypatch.setattr(auth_module.time, "time", lambda: 1000)
    monkeypatch.setattr(
        auth_module,
        "save_config",
        lambda value: saved.append((value.auth, value.pending_auth)),
    )

    result = asyncio.run(auth_module.finish_pending_web_approval_login(config=cfg))

    assert result["status"] == "approved"
    assert result["auth_method"] == "api_key"
    assert cfg.auth.api_key == "raw-api-key"
    assert cfg.workspace.id == "workspace-1"
    assert cfg.workspace.organization_name == "MuseOn"
    assert cfg.pending_auth.device_code is None
    assert saved[-1][0].api_key == "raw-api-key"
    assert saved[-1][1].device_code is None


def test_web_approval_finish_returns_pending_without_blocking(monkeypatch) -> None:
    cfg = Config()
    cfg.pending_auth = PendingAuthState(
        device_code="device-1",
        user_code="MUSEON-ABC123",
        verification_uri_complete="https://museon.ai/cli/authorize?device_code=device-1",
        expires_at=2000,
    )

    async def fake_get_public(
        *,
        config: Config,
        path: str,
        params: dict | None = None,
    ) -> dict:
        return {"status": "pending"}

    monkeypatch.setattr(auth_module, "api_get_public", fake_get_public)
    monkeypatch.setattr(auth_module.time, "time", lambda: 1000)

    result = asyncio.run(auth_module.finish_pending_web_approval_login(config=cfg))

    assert result == {
        "authenticated": False,
        "status": "pending",
        "verification_uri": None,
        "verification_uri_complete": "https://museon.ai/cli/authorize?device_code=device-1",
        "user_code": "MUSEON-ABC123",
        "expires_at": 2000,
    }
    assert cfg.pending_auth.device_code == "device-1"


def test_refresh_access_token_persists_new_tokens(monkeypatch) -> None:
    import asyncio

    from museoncli import auth as auth_module

    cfg = Config()
    cfg.supabase_url = "https://sb.example"
    cfg.supabase_anon_key = "anon"
    cfg.auth.access_token = "old-access"
    cfg.auth.refresh_token = "old-refresh"

    class _Resp:
        status_code = 200

        @staticmethod
        def json() -> dict:
            return {
                "access_token": "new-access",
                "refresh_token": "new-refresh",
                "expires_at": 1234,
            }

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, headers=None, json=None):
            assert url.endswith("/auth/v1/token?grant_type=refresh_token")
            assert json == {"refresh_token": "old-refresh"}
            return _Resp()

    saved: list[Config] = []
    monkeypatch.setattr(auth_module.httpx, "AsyncClient", _Client)
    monkeypatch.setattr(auth_module, "save_config", lambda c: saved.append(c))

    assert asyncio.run(auth_module.refresh_access_token(cfg)) is True
    assert cfg.auth.access_token == "new-access"
    assert cfg.auth.refresh_token == "new-refresh"
    assert cfg.auth.expires_at == 1234
    assert saved == [cfg]


def test_refresh_access_token_refuses_without_material() -> None:
    import asyncio

    from museoncli import auth as auth_module

    cfg = Config()
    cfg.auth.api_key = "api-key"
    cfg.auth.refresh_token = "r"
    cfg.supabase_url = "https://sb.example"
    cfg.supabase_anon_key = "anon"
    assert asyncio.run(auth_module.refresh_access_token(cfg)) is False

    cfg2 = Config()
    cfg2.supabase_url = "https://sb.example"
    cfg2.supabase_anon_key = "anon"
    assert asyncio.run(auth_module.refresh_access_token(cfg2)) is False


def test_api_data_retries_once_after_successful_refresh(monkeypatch) -> None:
    import asyncio

    import museoncli.main as main_module

    cfg = Config()
    cfg.auth.access_token = "expired"
    cfg.auth.refresh_token = "refresh"

    class _Resp:
        def __init__(self, status_code, payload):
            self.status_code = status_code
            self._payload = payload
            self.text = str(payload)

        def json(self):
            return self._payload

    responses = [_Resp(401, {}), _Resp(200, {"success": True, "data": {"ok": 1}})]
    calls: list[str] = []

    async def fake_send(cfg_arg, method, url, *, json_body, params):
        calls.append(url)
        return responses.pop(0)

    refreshed: list[bool] = []

    async def fake_refresh(cfg_arg):
        refreshed.append(True)
        return True

    monkeypatch.setattr(main_module, "_api_send", fake_send)
    monkeypatch.setattr(main_module, "refresh_access_token", fake_refresh)

    result = asyncio.run(main_module.api_data(cfg, "GET", "/agent-cli/whoami"))
    assert result == {"ok": 1}
    assert refreshed == [True]
    assert len(calls) == 2


def test_api_data_maps_426_to_cli_outdated(monkeypatch) -> None:
    import asyncio

    import museoncli.main as main_module
    import pytest as _pytest

    cfg = Config()
    cfg.auth.access_token = "token"

    class _Resp:
        status_code = 426
        text = '{"detail": {"reason": "cli_outdated", "minimum_version": "0.2.0"}}'

        def json(self):
            return {}

    async def fake_send(cfg_arg, method, url, *, json_body, params):
        return _Resp()

    async def fake_refresh(cfg_arg):
        raise AssertionError("426 must not trigger a token refresh")

    monkeypatch.setattr(main_module, "_api_send", fake_send)
    monkeypatch.setattr(main_module, "refresh_access_token", fake_refresh)

    with _pytest.raises(RuntimeError) as excinfo:
        asyncio.run(main_module.api_data(cfg, "GET", "/agent-cli/whoami"))
    assert main_module.reason_from_exception(excinfo.value) == "cli_outdated"
    assert "minimum_version" in str(excinfo.value)


def test_api_send_retries_connect_errors(monkeypatch) -> None:
    import asyncio

    import museoncli.main as main_module

    cfg = Config()
    cfg.auth.access_token = "token"
    calls: list[str] = []
    sleeps: list[float] = []

    class _Resp:
        status_code = 200
        text = '{"success": true}'

        def json(self):
            return {"success": True}

    class _Client:
        def __init__(self, *, timeout):
            assert timeout is None

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, *, headers, json, params):
            del method, headers, json, params
            calls.append(url)
            if len(calls) < 3:
                raise main_module.httpx.ConnectError("dial failed")
            return _Resp()

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(main_module.httpx, "AsyncClient", _Client)
    monkeypatch.setattr(main_module.asyncio, "sleep", fake_sleep)

    response = asyncio.run(
        main_module._api_send(  # noqa: SLF001
            cfg,
            "POST",
            "https://api.example.test/agent-cli/research",
            json_body={"ok": True},
            params=None,
        )
    )

    assert response.status_code == 200
    assert calls == [
        "https://api.example.test/agent-cli/research",
        "https://api.example.test/agent-cli/research",
        "https://api.example.test/agent-cli/research",
    ]
    assert sleeps == [0.25, 0.5]
