from __future__ import annotations

import asyncio

import pytest

from museoncli import __version__
from museoncli.config import AuthState, Config, OrganizationState, PendingAuthState
import museoncli.auth as auth_module
from museoncli.auth import auth_headers


def test_auth_headers_uses_scoped_api_key() -> None:
    cfg = Config()
    cfg.auth = AuthState(api_key="api-key")

    assert auth_headers(cfg) == {"X-API-KEY": "api-key", "X-CLI-Version": __version__}


def test_auth_headers_adds_usage_context_when_available() -> None:
    cfg = Config()
    cfg.auth = AuthState(api_key="api-key")
    cfg.organization = OrganizationState(id="org-selected")
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
        "X-Organization-Id": "org-selected",
        "X-Museon-Conversation-Id": "conv-1",
        "X-Museon-Usage-Business-Type": "agent_session",
        "X-Museon-Usage-Business-Id": "conv-1",
        "X-Museon-Sandbox-Id": "sandbox-1",
        "X-Museon-Actor-Id": "actor-1",
        # Usage attribution stays; X-Museon-Workspace-Id is no longer sent.
        "X-Museon-Organization-Id": "org-1",
    }


def test_auth_headers_address_no_organization_and_no_workspace_when_none_is_selected() -> None:
    cfg = Config.from_dict({"workspace": {"id": "ws-022-without-organization"}})
    cfg.auth = AuthState(api_key="api-key")

    assert auth_headers(cfg) == {"X-API-KEY": "api-key", "X-CLI-Version": __version__}


def test_auth_headers_do_not_authenticate_with_usage_context_only() -> None:
    cfg = Config()
    cfg.runtime_context = {"conversation_id": "conv-1"}

    assert auth_headers(cfg) == {}


@pytest.mark.parametrize("expires_at", [999, 1000])
def test_auth_headers_rejects_expired_credentials(
    expires_at: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = Config(auth=AuthState(api_key="expired-key", expires_at=expires_at))
    monkeypatch.setattr(auth_module.time, "time", lambda: 1000)

    assert auth_headers(cfg) == {}


def test_auth_headers_accepts_credentials_before_expiration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config(auth=AuthState(api_key="current-key", expires_at=1001))
    monkeypatch.setattr(auth_module.time, "time", lambda: 1000)

    assert auth_headers(cfg) == {
        "X-API-KEY": "current-key",
        "X-CLI-Version": __version__,
    }


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
            "requested_organization_id": None,
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
            "credential_expires_at": "2026-10-01T00:00:00+00:00",
            "user": {"id": "user-1", "email": "staff@museon.ai"},
            "organization": {"id": "org-1", "name": "MuseOn"},
        }

    monkeypatch.setattr(auth_module, "api_post_public", fake_post_public)
    monkeypatch.setattr(auth_module, "api_get_public", fake_get_public)
    monkeypatch.setattr(auth_module.webbrowser, "open", lambda url: True)
    monkeypatch.setattr(auth_module, "save_config", lambda value: saved.append(value.auth))

    result = asyncio.run(auth_module.run_web_approval_login(config=cfg))

    assert result["auth_method"] == "api_key"
    assert cfg.auth.api_key == "raw-api-key"
    assert cfg.auth.expires_at == 1790812800
    assert cfg.organization == OrganizationState(id="org-1", name="MuseOn")
    assert result["organization"] == {"id": "org-1", "name": "MuseOn"}
    assert "workspace" not in result
    assert saved[-1].api_key == "raw-api-key"


def test_web_approval_start_stores_pending_state_without_returning_device_code(
    monkeypatch,
) -> None:
    cfg = Config()
    cfg.api_base_url = "https://api.museon.ai/api/v1"
    cfg.site_url = "https://museon.ai"
    cfg.organization = OrganizationState(id="org-member", name="Member Org")
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
            "requested_organization_id": "org-member",
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
            "organization": {"id": "org-1", "name": "MuseOn"},
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
    assert cfg.organization == OrganizationState(id="org-1", name="MuseOn")
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


def test_web_approval_finish_wait_defaults_to_five_minutes(monkeypatch) -> None:
    cfg = Config()
    cfg.pending_auth = PendingAuthState(device_code="device-1", expires_at=2000)
    captured: dict[str, int | float | bool | str] = {}

    async def fake_poll_until_terminal(**kwargs):
        captured.update(kwargs)
        return {"authenticated": True, "status": "approved"}

    monkeypatch.setattr(auth_module.time, "time", lambda: 1000)
    monkeypatch.setattr(
        auth_module,
        "poll_web_approval_until_terminal",
        fake_poll_until_terminal,
    )

    result = asyncio.run(auth_module.finish_pending_web_approval_login(config=cfg, wait=True))

    assert result["status"] == "approved"
    assert captured["timeout_seconds"] == 300


def test_api_data_maps_401_to_unauthorized_without_retry(monkeypatch) -> None:
    import asyncio

    import museoncli.main as main_module

    cfg = Config()
    cfg.auth.api_key = "expired"

    class _Resp:
        def __init__(self, status_code, payload):
            self.status_code = status_code
            self._payload = payload
            self.text = str(payload)

        def json(self):
            return self._payload

    calls: list[str] = []

    async def fake_send(cfg_arg, method, url, *, json_body, params):
        calls.append(url)
        return _Resp(401, {})

    monkeypatch.setattr(main_module, "_api_send", fake_send)

    with pytest.raises(RuntimeError, match="unauthorized"):
        asyncio.run(main_module.api_data(cfg, "GET", "/agent-cli/whoami"))
    assert len(calls) == 1


def test_api_data_does_not_send_expired_credentials(monkeypatch) -> None:
    import museoncli.main as main_module

    cfg = Config(auth=AuthState(api_key="expired", expires_at=1000))
    sent = False

    async def fake_send(cfg_arg, method, url, *, json_body, params):
        nonlocal sent
        del cfg_arg, method, url, json_body, params
        sent = True
        raise AssertionError("expired credentials must fail before network IO")

    monkeypatch.setattr(auth_module.time, "time", lambda: 1000)
    monkeypatch.setattr(main_module, "_api_send", fake_send)

    with pytest.raises(RuntimeError, match="missing_auth"):
        asyncio.run(main_module.api_data(cfg, "GET", "/agent-cli/whoami"))
    assert sent is False


@pytest.mark.parametrize(
    ("caller", "path", "url_path"),
    [
        ("api_data", "/agent-cli/whoami", "/api/v1/agent-cli/whoami"),
        ("api_data_v2", "/ugc/agency/me", "/api/v2/ugc/agency/me"),
    ],
)
def test_426_reads_the_same_on_agent_cli_and_v2_routes(monkeypatch, caller, path, url_path) -> None:
    import httpx

    import museoncli.main as main_module

    cfg = Config(api_base_url="https://api.example.test/api/v1", auth=AuthState(api_key="token"))
    seen: list[httpx.Request] = []

    def outdated(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            426,
            json={
                "detail": {
                    "reason": "cli_outdated",
                    "minimum_version": "0.24.0",
                    "received_version": "0.22.3",
                    "install_hint": "Run `uv tool upgrade museoncli`, then retry.",
                }
            },
        )

    client = httpx.AsyncClient
    monkeypatch.setattr(
        main_module.httpx,
        "AsyncClient",
        lambda **kw: client(**kw, transport=httpx.MockTransport(outdated)),
    )

    with pytest.raises(main_module.CliOutdatedError) as excinfo:
        asyncio.run(getattr(main_module, caller)(cfg, "GET", path))

    assert seen[0].url.path == url_path
    payload, code = main_module.error_envelope(excinfo.value, command="whoami")
    assert code == 1
    assert payload["reason"] == "cli_outdated"
    assert payload["error"] == {
        "code": "cli_outdated",
        "message": (
            "Museon CLI 0.22.3 is no longer supported by the Museon API (minimum supported: "
            "0.24.0). Run `uv tool upgrade museoncli`, then retry."
        ),
        "http_status": 426,
        "server_code": "cli_outdated",
        "retryable": False,
        "hint": "Run `uv tool upgrade museoncli`, then retry.",
    }


def test_organization_workspace_mismatch_is_explained(monkeypatch) -> None:
    import museoncli.main as main_module

    exc = main_module.ApiRequestError(409, {"code": "organization_workspace_mismatch"})
    payload, code = main_module.error_envelope(exc, command="media.get")

    assert code == main_module.EXIT_CONFLICT
    assert payload["reason"] == "conflict"
    assert payload["error"]["server_code"] == "organization_workspace_mismatch"
    assert "--workspace-id" in payload["error"]["message"]
    assert "organization" in payload["error"]["message"]


def test_api_send_retries_connect_errors(monkeypatch) -> None:
    import asyncio

    import museoncli.main as main_module

    cfg = Config()
    cfg.auth.api_key = "token"
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


def test_approval_prefers_the_organization_a_new_server_returns(monkeypatch) -> None:
    cfg = Config()
    monkeypatch.setattr(auth_module, "save_config", lambda value: None)

    result = auth_module.complete_web_approval_poll(
        config=cfg,
        poll={
            "status": "approved",
            "api_key": "raw-api-key",
            "workspace": {"id": "ws-1", "organization_id": "org-1", "organization_name": "Old"},
            "organization": {"id": "org-1", "name": "MuseOn"},
        },
        clear_pending=False,
    )

    assert cfg.organization == OrganizationState(id="org-1", name="MuseOn")
    assert result["organization"] == {"id": "org-1", "name": "MuseOn"}
    assert "workspace" not in result
