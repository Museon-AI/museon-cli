from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys

import pytest

from museoncli.config import AuthState, Config, PendingAuthState, WorkspaceState
from museoncli.domains import ROUTINE_INSTRUCTION_MAX_LENGTH
import museoncli.main as main_module
from museoncli.main import build_parser, reason_from_exception
from museoncli import envelopes as envelopes_module
from museoncli import execution as execution_module
from museoncli.domains import get_command_spec
from museoncli.domains import evaluator as evaluator_module
from museoncli.domains import social_account as social_account_module
from museoncli.execution import CommandContext


def _domain_ctx(command_name, *, cfg, workspace_id, arguments):
    return CommandContext(
        cfg=cfg,
        spec=get_command_spec(command_name),
        args=None,
        arguments=arguments,
        workspace_id=workspace_id,
        api_data=main_module.api_data,
        api_data_v2=main_module.api_data_v2,
        upload_media_file=main_module.upload_media_file,
        upload_artifact_file=main_module.upload_artifact_file,
    )


def _run_connect_link(cfg, *, command_name, workspace_id, arguments):
    executor = {
        "social-account.connect-link-create": social_account_module._execute_connect_link_create,
        "social-account.connect-link-status": social_account_module._execute_connect_link_status,
    }[command_name]
    return executor(
        _domain_ctx(command_name, cfg=cfg, workspace_id=workspace_id, arguments=arguments)
    )


def parse(argv: list[str]):
    return build_parser().parse_args(argv)


class _FakeManifestResponse:
    def __init__(self, status_code: int, payload: object) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> object:
        return self._payload


class _FakeManifestClient:
    calls: list[dict[str, object]] = []
    response = _FakeManifestResponse(200, {"tag_name": "v0.1.17"})

    def __init__(self, **kwargs: object) -> None:
        self.calls.append({"init": kwargs})

    async def __aenter__(self) -> "_FakeManifestClient":
        return self

    async def __aexit__(self, *args: object) -> None:
        del args

    async def get(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
    ) -> _FakeManifestResponse:
        self.calls.append({"url": url, "headers": headers})
        return self.response


def test_base_commands_remain_available() -> None:
    for command in ["version", "whoami", "health"]:
        args = parse([command])

        assert args.command == command


def test_schema_output_is_utf8_when_host_encoding_is_cp1252() -> None:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "cp1252"
    env["MUSEON_JSON_OFFLOAD_ENABLED"] = "false"

    result = subprocess.run(
        [sys.executable, "-c", "from museoncli.main import main; main()", "schema"],
        check=True,
        encoding="utf-8",
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["data"]["commands"]


def test_routines_list_parser_uses_standard_pagination() -> None:
    args = parse(
        [
            "routines",
            "+list",
            "--workspace-id",
            "70000000-0000-4000-8000-000000000001",
            "--mode",
            "ad-hoc",
            "--status",
            "active",
            "--search",
            "daily",
            "--page",
            "2",
            "--page-size",
            "10",
        ]
    )

    assert args.command == "routines"
    assert args.domain_command == "routines.list"
    assert args.shortcut == "+list"
    assert args.workspace_id == "70000000-0000-4000-8000-000000000001"
    assert args.mode == "ad-hoc"
    assert args.status == "active"
    assert args.search == "daily"
    assert args.page == 2
    assert args.page_size == 10
    assert not hasattr(args, "offset")
    assert not hasattr(args, "limit")


def test_routines_write_parser_accepts_other_scope_without_delivery_mode() -> None:
    args = parse(
        [
            "routines",
            "+create-ad-hoc",
            "--name",
            "Daily check",
            "--instruction",
            "Check daily.",
            "--trigger-config-json",
            '{"schema_version":1,"kind":"recurring","timezone":"UTC","cron":"0 9 * * *"}',
            "--other-scope-conversation-id",
            "70000000-0000-4000-8000-000000000077",
        ]
    )

    assert args.other_scope_conversation_id == "70000000-0000-4000-8000-000000000077"
    assert args.result_delivery_mode is None
    assert not hasattr(args, "target_channel_id")
    assert not hasattr(args, "target_platform_chat_type")


def test_routines_write_parser_accepts_result_delivery_mode() -> None:
    args = parse(
        [
            "routines",
            "+create-ad-hoc",
            "--name",
            "Daily check",
            "--instruction",
            "Check daily.",
            "--trigger-config-json",
            '{"schema_version":1,"kind":"recurring","timezone":"UTC","cron":"0 9 * * *"}',
            "--other-scope-conversation-id",
            "70000000-0000-4000-8000-000000000077",
            "--result-delivery-mode",
            "deferred-root-result",
        ]
    )

    assert args.result_delivery_mode == "deferred-root-result"


def test_routines_claim_managed_parser_is_not_available() -> None:
    with pytest.raises(SystemExit):
        parse(["routines", "+claim-managed", "routine-1"])


def test_routine_turn_context_preserves_source_default_delivery() -> None:
    cfg = Config()
    cfg.runtime_context = {
        "source_conversation_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    }

    context = execution_module.routine_turn_context(cfg, arguments={})

    assert context == {
        "source_conversation_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    }


def test_routine_turn_context_defaults_other_scope_to_deferred_root_result() -> None:
    context = execution_module.routine_turn_context(
        Config(),
        arguments={
            "other_scope_conversation_id": "70000000-0000-4000-8000-000000000077",
        },
    )

    assert context == {
        "other_scope_conversation_id": "70000000-0000-4000-8000-000000000077",
        "result_delivery_mode": "deferred_root_result",
    }


def test_routine_turn_context_falls_back_to_sandbox_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    monkeypatch.setenv("MUSEON_CONVERSATION_ID", "session-conversation-1")
    monkeypatch.setenv("MUSEON_SCOPE_CONVERSATION_ID", "scope-conversation-1")
    monkeypatch.setenv("MUSEON_SANDBOX_ID", "sandbox-1")

    context = execution_module.routine_turn_context(cfg)

    assert context == {
        "conversation_id": "session-conversation-1",
        "source_conversation_id": "scope-conversation-1",
    }


def test_cli_version_comparison_uses_numeric_order() -> None:
    assert main_module.is_newer_cli_version("0.1.16", "0.1.9") is True
    assert main_module.is_newer_cli_version("v0.2.0", "0.1.99") is True
    assert main_module.is_newer_cli_version("0.1.16", "0.1.16") is False
    assert main_module.is_newer_cli_version("0.1.2", "0.1.16") is False
    assert main_module.is_newer_cli_version("latest", "0.1.16") is False


def test_cli_update_notice_reads_github_release_when_explicitly_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _FakeManifestClient.calls = []
    _FakeManifestClient.response = _FakeManifestResponse(
        200,
        {
            "tag_name": "v0.1.17",
            "html_url": "https://github.com/Museon-AI/museon-cli/releases/tag/v0.1.17",
        },
    )
    cfg = Config(site_url="https://museon.ai")

    monkeypatch.setenv("MUSEONCLI_UPDATE_CHECK", "true")
    monkeypatch.delenv("MUSEONCLI_UPDATE_MANIFEST_URL", raising=False)
    monkeypatch.setattr(main_module, "__version__", "0.1.16")
    monkeypatch.setattr(main_module.httpx, "AsyncClient", _FakeManifestClient)

    notice = asyncio.run(main_module.check_cli_update_notice(cfg))

    assert notice is not None
    assert notice["current_version"] == "0.1.16"
    assert notice["latest_version"] == "0.1.17"
    assert notice["source"] == "github_release"
    assert notice["manifest_url"] == main_module.DEFAULT_CLI_RELEASE_MANIFEST_URL
    assert notice["project_url"].endswith("/releases/tag/v0.1.17")
    expected_upgrade = (
        'uv tool install "https://github.com/Museon-AI/museon-cli/releases/'
        'download/v0.1.17/museoncli-0.1.17-py3-none-any.whl" --force'
    )
    assert expected_upgrade in notice["message"]
    assert notice["upgrade_command"] == expected_upgrade
    assert "token=" not in json.dumps(notice).lower()
    assert _FakeManifestClient.calls[-1]["url"] == main_module.DEFAULT_CLI_RELEASE_MANIFEST_URL


def test_cli_update_notice_is_silent_when_manifest_is_current(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _FakeManifestClient.calls = []
    _FakeManifestClient.response = _FakeManifestResponse(200, {"tag_name": "v0.1.16"})

    monkeypatch.setenv("MUSEONCLI_UPDATE_CHECK", "true")
    monkeypatch.setattr(main_module, "__version__", "0.1.16")
    monkeypatch.setattr(main_module.httpx, "AsyncClient", _FakeManifestClient)

    assert asyncio.run(main_module.check_cli_update_notice(Config())) is None


def test_cli_update_notice_is_silent_when_manifest_fetch_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _FakeManifestClient.calls = []
    _FakeManifestClient.response = _FakeManifestResponse(404, {"error": "not_found"})

    monkeypatch.setenv("MUSEONCLI_UPDATE_CHECK", "true")
    monkeypatch.setattr(main_module, "__version__", "0.1.16")
    monkeypatch.setattr(main_module.httpx, "AsyncClient", _FakeManifestClient)

    assert asyncio.run(main_module.check_cli_update_notice(Config())) is None


def test_cli_update_notice_is_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MUSEONCLI_UPDATE_CHECK", raising=False)

    assert asyncio.run(main_module.check_cli_update_notice(Config())) is None


def test_cli_update_notice_gives_one_wheel_upgrade_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _FakeManifestClient.calls = []
    _FakeManifestClient.response = _FakeManifestResponse(200, {"tag_name": "v0.1.17"})
    monkeypatch.setenv("MUSEONCLI_UPDATE_CHECK", "true")
    monkeypatch.setattr(main_module, "__version__", "0.1.16")
    monkeypatch.setattr(main_module.httpx, "AsyncClient", _FakeManifestClient)

    notice = asyncio.run(main_module.check_cli_update_notice(Config()))

    assert notice is not None
    assert notice["upgrade_command"] == (
        'uv tool install "https://github.com/Museon-AI/museon-cli/releases/'
        'download/v0.1.17/museoncli-0.1.17-py3-none-any.whl" --force'
    )
    assert "npm" not in notice["message"].lower()


def test_dispatch_with_notices_attaches_update_notice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_dispatch(args: argparse.Namespace) -> dict[str, object]:
        del args
        return {"data": {"cli_version": "0.1.16"}}

    async def fake_notice(cfg: Config) -> dict[str, object]:
        del cfg
        return {"latest_version": "0.1.17"}

    monkeypatch.setattr(main_module, "dispatch", fake_dispatch)
    monkeypatch.setattr(main_module, "load_config", Config)
    monkeypatch.setattr(main_module, "check_cli_update_notice", fake_notice)

    result = asyncio.run(main_module.dispatch_with_notices(parse(["health"])))

    assert result == {
        "data": {"cli_version": "0.1.16"},
        "_notice": {"update": {"latest_version": "0.1.17"}},
    }


@pytest.mark.parametrize(
    "argv",
    [
        ["version"],
        ["config", "get"],
        ["setup", "--agent", "codex"],
        ["schema"],
        ["auth", "status"],
        ["auth", "logout"],
        ["workspace", "current"],
        ["artifacts", "+validate", "--file", "./report.md"],
        ["artifacts", "+share", "--artifact-id", "artifact-1", "--dry-run"],
    ],
)
def test_dispatch_with_notices_keeps_local_commands_offline(
    argv: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_dispatch(args: argparse.Namespace) -> dict[str, object]:
        del args
        return {"data": {"local": True}}

    async def unexpected_notice(cfg: Config) -> dict[str, object]:
        del cfg
        raise AssertionError("local command attempted an update check")

    monkeypatch.setattr(main_module, "dispatch", fake_dispatch)
    monkeypatch.setattr(main_module, "check_cli_update_notice", unexpected_notice)

    result = asyncio.run(main_module.dispatch_with_notices(parse(argv)))

    assert result == {"data": {"local": True}}


def test_schema_parser_supports_optional_command_name() -> None:
    list_args = parse(["schema"])
    command_args = parse(["schema", "research.web-research"])

    assert list_args.command == "schema"
    assert list_args.name is None
    assert command_args.command == "schema"
    assert command_args.name == "research.web-research"


def test_setup_parser_supports_named_agent_and_force() -> None:
    args = parse(["setup", "--agent", "codex", "--force"])

    assert args.command == "setup"
    assert args.agent == "codex"
    assert args.force is True


def test_config_get_parser() -> None:
    args = parse(["config", "get"])

    assert args.command == "config"
    assert args.config_command == "get"


def test_config_set_parser() -> None:
    args = parse(
        [
            "config",
            "set",
            "--api-base-url",
            "https://api.example.com/api/v1",
            "--site-url",
            "https://app.example.com",
        ]
    )

    assert args.command == "config"
    assert args.config_command == "set"
    assert args.api_base_url == "https://api.example.com/api/v1"
    assert args.site_url == "https://app.example.com"


def test_auth_login_defaults_to_web_approval() -> None:
    args = parse(["auth", "login"])

    assert args.command == "auth"
    assert args.auth_command == "login"
    assert args.timeout == 300


def test_auth_start_parser() -> None:
    args = parse(["auth", "start"])

    assert args.command == "auth"
    assert args.auth_command == "start"


def test_auth_status_clears_expired_pending_authorization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    cfg.auth.api_key = "museon_test_key"
    cfg.pending_auth = PendingAuthState(
        device_code="stale-device",
        user_code="MUSEON-STALE",
        expires_at=1000,
    )
    saved: list[PendingAuthState] = []
    monkeypatch.setattr(main_module.time, "time", lambda: 1001)
    monkeypatch.setattr(
        main_module,
        "save_config",
        lambda value: saved.append(value.pending_auth),
    )

    result = asyncio.run(
        main_module.dispatch_auth(
            argparse.Namespace(auth_command="status"),
            cfg,
        )
    )

    assert result["data"]["authenticated"] is True
    assert result["data"]["pending_web_approval"] == {
        "active": False,
        "expires_at": None,
        "user_code": None,
    }
    assert cfg.pending_auth.device_code is None
    assert saved[-1].device_code is None


def test_auth_status_reports_expired_credential_without_authenticating(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config(
        auth=AuthState(
            api_key="expired-key",
            expires_at=1000,
            user={"id": "user-1", "email": "user@example.com"},
        )
    )
    monkeypatch.setattr(main_module.time, "time", lambda: 1000)

    result = asyncio.run(
        main_module.dispatch_auth(
            argparse.Namespace(auth_command="status"),
            cfg,
        )
    )

    assert result["data"] == {
        "authenticated": False,
        "status": "expired",
        "reason": "credential_expired",
        "auth_method": "api_key",
        "expires_at": 1000,
        "user": {"id": "user-1", "email": "user@example.com"},
        "workspace": {
            "id": None,
            "name": None,
            "organization_id": None,
            "organization_name": None,
        },
        "pending_web_approval": {
            "active": False,
            "expires_at": None,
            "user_code": None,
        },
    }


def test_auth_finish_parser_supports_optional_wait() -> None:
    args = parse(["auth", "finish", "--wait", "--timeout", "30", "--poll-interval", "0.5"])

    assert args.command == "auth"
    assert args.auth_command == "finish"
    assert args.wait is True
    assert args.timeout == 30
    assert args.poll_interval == 0.5


def test_auth_finish_wait_defaults_to_five_minutes() -> None:
    args = parse(["auth", "finish", "--wait"])

    assert args.wait is True
    assert args.timeout == 300


def test_workspace_commands_remain_available() -> None:
    current = parse(["workspace", "current"])
    list_args = parse(["workspace", "list"])
    selected = parse(["workspace", "select", "--id", "workspace-1"])

    assert current.command == "workspace"
    assert current.workspace_command == "current"
    assert list_args.workspace_command == "list"
    assert selected.workspace_command == "select"
    assert selected.id == "workspace-1"


def test_workspace_select_stores_organization_name(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = Config()
    saved: list[WorkspaceState] = []

    async def fake_api_data(
        cfg_arg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
    ) -> dict[str, object]:
        del cfg_arg, json_body, params
        assert method == "GET"
        assert path == "/agent-cli/whoami"
        return {
            "workspaces": [
                {
                    "id": "workspace-1",
                    "name": "MuseOn Official",
                    "organization_id": "org-1",
                    "organization_name": "MuseOn",
                }
            ]
        }

    monkeypatch.setattr(main_module, "api_data", fake_api_data)
    monkeypatch.setattr(main_module, "save_config", lambda value: saved.append(value.workspace))

    result = asyncio.run(
        main_module.dispatch_workspace(parse(["workspace", "select", "--id", "workspace-1"]), cfg)
    )

    assert result["workspace"]["organization_name"] == "MuseOn"
    assert cfg.workspace.organization_name == "MuseOn"
    assert saved[-1].organization_name == "MuseOn"


def test_whoami_refreshes_current_workspace_organization_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    cfg.workspace = WorkspaceState(
        id="workspace-1",
        name="MuseOn Official",
        organization_id="org-1",
    )
    saved: list[WorkspaceState] = []

    async def fake_api_data(
        cfg_arg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
    ) -> dict[str, object]:
        del cfg_arg, json_body, params
        assert method == "GET"
        assert path == "/agent-cli/whoami"
        return {
            "workspaces": [
                {
                    "id": "workspace-1",
                    "name": "MuseOn Official",
                    "organization_id": "org-1",
                    "organization_name": "MuseOn",
                }
            ]
        }

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)
    monkeypatch.setattr(main_module, "save_config", lambda value: saved.append(value.workspace))

    result = asyncio.run(main_module.dispatch(parse(["whoami"])))

    assert result is not None
    assert result["data"]["workspaces"][0]["organization_name"] == "MuseOn"
    assert cfg.workspace.organization_name == "MuseOn"
    assert saved[-1].organization_name == "MuseOn"


def test_social_account_connect_link_create_direct_command_uses_agent_cli_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1")
    calls: list[dict[str, object]] = []

    async def fake_api_data(
        cfg_arg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
    ) -> dict[str, object]:
        del cfg_arg, params
        calls.append({"method": method, "path": path, "json_body": json_body})
        return {
            "domain": "social-auth",
            "operation": "link-create",
            "result": {"id": "link-1", "status": "pending"},
        }

    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    result = asyncio.run(
        _run_connect_link(
            cfg,
            command_name="social-account.connect-link-create",
            workspace_id="workspace-1",
            arguments={"platform": "tiktok", "expires_in_days": 7},
        )
    )

    assert result == {"id": "link-1", "status": "pending"}
    assert calls == [
        {
            "method": "POST",
            "path": "/agent-cli/social-auth/connect-links",
            "json_body": {
                "workspace_id": "workspace-1",
                "payload": {"platform": "tiktok", "expires_in_days": 7},
            },
        }
    ]


def test_social_account_connect_link_create_direct_command_includes_runtime_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1")
    cfg.runtime_context = {
        "conversation_id": "conversation-1",
        "source_channel_message_id": "message-1",
        "origin_turn_id": "turn-1",
    }
    calls: list[dict[str, object]] = []

    async def fake_api_data(
        cfg_arg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
    ) -> dict[str, object]:
        del cfg_arg, params
        calls.append({"method": method, "path": path, "json_body": json_body})
        return {
            "domain": "social-auth",
            "operation": "link-create",
            "result": {"id": "link-1", "status": "pending"},
        }

    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    result = asyncio.run(
        _run_connect_link(
            cfg,
            command_name="social-account.connect-link-create",
            workspace_id="workspace-1",
            arguments={"platform": "instagram"},
        )
    )

    assert result == {"id": "link-1", "status": "pending"}
    assert calls == [
        {
            "method": "POST",
            "path": "/agent-cli/social-auth/connect-links",
            "json_body": {
                "workspace_id": "workspace-1",
                "payload": {
                    "platform": "instagram",
                    "turn_context": {
                        "conversation_id": "conversation-1",
                        "source_channel_message_id": "message-1",
                        "origin_turn_id": "turn-1",
                    },
                },
            },
        }
    ]


def test_social_account_connect_link_create_direct_command_for_managed_oauth_forwards_args(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1")
    calls: list[dict[str, object]] = []

    async def fake_api_data(
        cfg_arg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
    ) -> dict[str, object]:
        del cfg_arg, params
        calls.append({"method": method, "path": path, "json_body": json_body})
        return {
            "domain": "social-auth",
            "operation": "link-create",
            "result": {
                "id": "22222222-2222-4222-8222-222222222222",
                "url": "https://oauth.example/connect/instagram",
                "status_check_supported": True,
            },
        }

    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    result = asyncio.run(
        _run_connect_link(
            cfg,
            command_name="social-account.connect-link-create",
            workspace_id="workspace-1",
            arguments={
                "platform": "instagram",
                "expires_in_days": 7,
                "redirect_url": "https://app.example.com/oauth/callback",
            },
        )
    )

    assert result == {
        "id": "22222222-2222-4222-8222-222222222222",
        "url": "https://oauth.example/connect/instagram",
        "status_check_supported": True,
    }
    assert calls == [
        {
            "method": "POST",
            "path": "/agent-cli/social-auth/connect-links",
            "json_body": {
                "workspace_id": "workspace-1",
                "payload": {
                    "platform": "instagram",
                    "expires_in_days": 7,
                    "redirect_url": "https://app.example.com/oauth/callback",
                },
            },
        }
    ]


def test_social_account_connect_link_status_wait_polls_until_completed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    responses = iter(
        [
            {"domain": "social-auth", "operation": "link-status", "result": {"status": "pending"}},
            {
                "domain": "social-auth",
                "operation": "link-status",
                "result": {"status": "completed", "connected": {"username": "creator"}},
            },
        ]
    )
    calls: list[dict[str, object]] = []

    async def fake_api_data(
        cfg_arg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
    ) -> dict[str, object]:
        del cfg_arg, json_body
        calls.append({"method": method, "path": path, "params": params})
        return next(responses)

    async def fake_sleep(_: float) -> None:
        return None

    monkeypatch.setattr(main_module, "api_data", fake_api_data)
    monkeypatch.setattr(main_module.asyncio, "sleep", fake_sleep)

    result = asyncio.run(
        _run_connect_link(
            cfg,
            command_name="social-account.connect-link-status",
            workspace_id="workspace-1",
            arguments={
                "link_id": "11111111-1111-4111-8111-111111111111",
                "wait": True,
                "timeout": 5,
                "poll_interval": 0.1,
            },
        )
    )

    assert result == {"status": "completed", "connected": {"username": "creator"}}
    assert len(calls) == 2
    assert calls[0]["path"] == (
        "/agent-cli/social-auth/connect-links/11111111-1111-4111-8111-111111111111/status"
    )


def test_research_search_parser_is_hidden() -> None:
    with pytest.raises(SystemExit):
        parse(["research", "+search", "--query", "Museon AI", "--source", "web", "--limit", "3"])


def test_research_web_research_parser() -> None:
    args = parse(
        [
            "research",
            "+web-research",
            "--query",
            "Museon AI",
            "--url",
            "https://example.com",
            "--include",
            "search-results",
            "--include",
            "site-visual-assets",
            "--limit",
            "3",
        ]
    )

    assert args.command == "research"
    assert args.shortcut == "+web-research"
    assert args.domain_command == "research.web-research"
    assert args.query == "Museon AI"
    assert args.url == "https://example.com"
    assert args.include == ["search-results", "site-visual-assets"]
    assert args.limit == 3
    assert args.max_retries == 3


def test_research_web_research_schema_exposes_retry_default() -> None:
    schema = main_module.schema_payload("research.web-research")

    assert schema["input_schema"]["properties"]["max_retries"]["default"] == 3


def test_research_social_media_search_parser() -> None:
    args = parse(
        [
            "research",
            "+social-media-search",
            "--platform",
            "tiktok",
            "--intent",
            "keyword-search",
            "--query",
            "skincare routine",
            "--content-type",
            "image",
            "--limit",
            "3",
        ]
    )

    assert args.command == "research"
    assert args.shortcut == "+social-media-search"
    assert args.domain_command == "research.social-media-search"
    assert args.platform == "tiktok"
    assert args.intent == "keyword-search"
    assert args.query == "skincare routine"
    assert args.content_type == "image"
    assert args.limit == 3


def test_research_social_media_search_parser_accepts_xhs() -> None:
    args = parse(
        [
            "research",
            "+social-media-search",
            "--platform",
            "xhs",
            "--intent",
            "keyword-search",
            "--query",
            "coffee shop decor",
            "--content-type",
            "image",
            "--time-window",
            "week",
            "--sort",
            "latest",
        ]
    )

    assert args.domain_command == "research.social-media-search"
    assert args.platform == "xhs"
    assert args.intent == "keyword-search"
    assert args.query == "coffee shop decor"
    assert args.content_type == "image"
    assert args.time_window == "week"
    assert args.sort == "latest"


def test_research_social_media_search_parser_accepts_xhs_post() -> None:
    args = parse(
        [
            "research",
            "+social-media-search",
            "--platform",
            "xhs",
            "--intent",
            "post",
            "--query",
            "6900c677000000000303418e",
        ]
    )

    assert args.domain_command == "research.social-media-search"
    assert args.platform == "xhs"
    assert args.intent == "post"
    assert args.query == "6900c677000000000303418e"


def test_research_social_media_search_schema_exposes_xhs_detail_intents() -> None:
    schema = main_module.schema_payload("research.social-media-search")
    intent_schema = schema["input_schema"]["properties"]["intent"]
    max_retries_schema = schema["input_schema"]["properties"]["max_retries"]
    description = intent_schema["description"]

    assert {"profile", "post", "creator-posts"}.issubset(set(intent_schema["enum"]))
    assert "XHS/RedNote supports keyword-search, post, profile, and creator-posts" in description
    assert max_retries_schema["default"] == 3


def test_research_social_media_search_help_shows_numeric_bounds(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit):
        parse(["research", "+social-media-search", "--help"])

    out = capsys.readouterr().out
    assert "--content-chars 0-4000" in out
    assert "Maximum returned content characters (0-4000; default:" in out
    assert "800)." in out
    assert "--timeout 5-60" in out
    assert "Per-attempt timeout seconds (5-60; default: 10)." in out


def test_research_social_media_search_rejects_out_of_range_content_chars(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit):
        parse(
            [
                "research",
                "+social-media-search",
                "--platform",
                "tiktok",
                "--intent",
                "post",
                "--query",
                "https://www.tiktok.com/t/example/",
                "--content-chars",
                "6000",
            ]
        )

    assert "--content-chars must be <= 4000" in capsys.readouterr().err


def test_research_social_media_search_rejects_out_of_range_timeout(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit):
        parse(
            [
                "research",
                "+social-media-search",
                "--platform",
                "tiktok",
                "--intent",
                "post",
                "--query",
                "https://www.tiktok.com/t/example/",
                "--timeout",
                "120",
            ]
        )

    assert "--timeout must be <= 60" in capsys.readouterr().err


def test_research_community_search_parser() -> None:
    args = parse(
        [
            "research",
            "+community-search",
            "--platform",
            "reddit",
            "--intent",
            "keyword-search",
            "--query",
            "AI video agent",
            "--search-type",
            "community",
            "--cursor",
            "after-1",
            "--limit",
            "3",
        ]
    )

    assert args.command == "research"
    assert args.max_retries == 3
    assert args.shortcut == "+community-search"
    assert args.domain_command == "research.community-search"
    assert args.platform == "reddit"
    assert args.intent == "keyword-search"
    assert args.query == "AI video agent"
    assert args.search_type == "community"
    assert args.cursor == "after-1"
    assert args.limit == 3


def test_research_community_search_schema_exposes_retry_default() -> None:
    schema = main_module.schema_payload("research.community-search")

    assert schema["input_schema"]["properties"]["max_retries"]["default"] == 3


def test_research_visual_analyze_parser() -> None:
    args = parse(
        [
            "research",
            "+visual-analyze",
            "--media",
            "https://example.com/a.png",
            "--prompt",
            "Assess this image.",
        ]
    )

    assert args.command == "research"
    assert args.shortcut == "+visual-analyze"
    assert args.domain_command == "research.visual-analyze"
    assert args.media_urls == ["https://example.com/a.png"]
    assert args.prompt == "Assess this image."


def test_content_analysis_run_parser() -> None:
    args = parse(
        [
            "content-analysis",
            "+run",
            "--type",
            "reverse-ai-prompt",
            "--url",
            "https://www.instagram.com/reel/ABC123/",
            "--wait",
            "--timeout",
            "120",
        ]
    )

    assert args.command == "content-analysis"
    assert args.shortcut == "+run"
    assert args.domain_command == "content-analysis.run"
    assert main_module.command_payload(args) == {
        "type": "reverse-ai-prompt",
        "url": "https://www.instagram.com/reel/ABC123/",
        "force_reanalysis": False,
        "wait": True,
        "wait_timeout_seconds": 120,
        "poll_interval_seconds": 2.0,
    }


def test_content_analysis_run_requires_one_source() -> None:
    args = parse(
        [
            "content-analysis",
            "+run",
            "--type",
            "content-analysis",
            "--url",
            "https://www.tiktok.com/@creator/video/123",
            "--media-id",
            "media-1",
        ]
    )

    with pytest.raises(ValueError, match="exactly one source"):
        main_module.command_payload(args)


def test_social_account_connect_link_create_parser() -> None:
    args = parse(
        [
            "social-account",
            "+connect-link-create",
            "--platform",
            "tiktok",
            "--expires-in-days",
            "3",
            "--dry-run",
        ]
    )

    assert args.command == "social-account"
    assert args.shortcut == "+connect-link-create"
    assert args.domain_command == "social-account.connect-link-create"
    assert main_module.command_payload(args) == {
        "platform": "tiktok",
        "expires_in_days": 3,
    }
    assert args.dry_run is True


def test_social_account_connect_link_create_managed_oauth_parser() -> None:
    args = parse(
        [
            "social-account",
            "+connect-link-create",
            "--platform",
            "facebook",
            "--redirect-url",
            "https://app.example.com/oauth/callback",
        ]
    )

    assert args.command == "social-account"
    assert args.shortcut == "+connect-link-create"
    assert args.domain_command == "social-account.connect-link-create"
    assert main_module.command_payload(args) == {
        "platform": "facebook",
        "expires_in_days": 7,
        "redirect_url": "https://app.example.com/oauth/callback",
    }


def test_social_account_connect_link_create_x_parser() -> None:
    args = parse(
        [
            "social-account",
            "+connect-link-create",
            "--platform",
            "x",
        ]
    )

    assert args.command == "social-account"
    assert args.shortcut == "+connect-link-create"
    assert args.domain_command == "social-account.connect-link-create"
    assert main_module.command_payload(args) == {
        "platform": "x",
        "expires_in_days": 7,
    }


def test_social_account_connect_link_create_managed_oauth_next_steps_include_status_poll() -> None:
    steps = envelopes_module._social_auth_next_steps(
        "social-account.connect-link-create",
        {
            "id": "22222222-2222-4222-8222-222222222222",
            "url": "https://oauth.example/connect/facebook",
            "status_check_supported": True,
        },
    )

    assert steps == [
        "Open the returned url to authorize: https://oauth.example/connect/facebook",
        (
            "Poll with: museoncli social-account +connect-link-status "
            "--id 22222222-2222-4222-8222-222222222222 --wait --timeout 300"
        ),
    ]


def test_social_account_connect_link_status_parser() -> None:
    args = parse(
        [
            "social-account",
            "+connect-link-status",
            "--id",
            "11111111-1111-4111-8111-111111111111",
            "--wait",
            "--timeout",
            "300",
            "--poll-interval",
            "0.5",
        ]
    )

    assert args.command == "social-account"
    assert args.shortcut == "+connect-link-status"
    assert args.domain_command == "social-account.connect-link-status"
    assert main_module.command_payload(args) == {
        "link_id": "11111111-1111-4111-8111-111111111111",
        "wait": True,
        "timeout": 300,
        "poll_interval": 0.5,
    }


def test_social_account_connect_schema_is_discoverable() -> None:
    schema = main_module.schema_payload("social-account")

    assert schema["domain"] == "social-account"
    shortcuts = [item["shortcut"] for item in schema["commands"]]
    assert "+connect-link-create" in shortcuts
    assert "+connect-link-status" in shortcuts
    assert "+performance-get" in shortcuts


def test_asset_list_parser() -> None:
    args = parse(["asset", "+list", "--type", "product", "--page-size", "3", "--search", "Museon"])

    assert args.command == "asset"
    assert args.shortcut == "+list"
    assert args.domain_command == "asset.list"
    assert args.asset_type == "product"
    assert args.page_size == 3
    assert args.search == "Museon"


def test_asset_list_parser_accepts_repeated_search_terms() -> None:
    args = parse(
        [
            "asset",
            "+list",
            "--type",
            "topic",
            "--search-term",
            "scenic",
            "--search-term",
            "nature",
            "--search-term",
            "scenic",
        ]
    )

    assert main_module.command_payload(args)["filters"]["search_terms"] == [
        "scenic",
        "nature",
    ]


def test_asset_list_parser_rejects_mixed_search_modes() -> None:
    with pytest.raises(SystemExit):
        parse(
            [
                "asset",
                "+list",
                "--type",
                "topic",
                "--search",
                "scenic",
                "--search-term",
                "nature",
            ]
        )


def test_asset_list_schema_explains_repeated_search_terms() -> None:
    schema = main_module.schema_payload("asset.list")
    properties = schema["input_schema"]["properties"]

    assert "One free-text search term" in properties["search"]["description"]
    assert properties["search_terms"]["maxItems"] == 20
    assert "Repeat --search-term" in properties["search_terms"]["description"]


def test_asset_product_create_schema_exposes_canonical_categories() -> None:
    schema = main_module.schema_payload("asset.create")
    product_condition = schema["input_schema"]["allOf"][0]
    product_payload = product_condition["then"]["properties"]["payload"]

    assert product_payload["required"] == ["name", "category", "description"]
    assert "LEARNING_PLATFORMS" in product_payload["properties"]["category"]["enum"]
    assert "SKILL_TRAINING" in product_payload["properties"]["category"]["enum"]
    assert "EDUCATION" not in product_payload["properties"]["category"]["enum"]


def test_asset_create_help_explains_product_category_discovery(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit):
        parse(["asset", "+create", "--help"])

    output = capsys.readouterr().out
    assert "Product requires name, category, and description" in output
    assert "asset +options" in output
    assert "--field category" in output
    assert "authoritative server validation" in output


def test_asset_options_parser() -> None:
    args = parse(
        [
            "asset",
            "+options",
            "--type",
            "product",
            "--field",
            "category",
            "--query",
            "edtech",
        ]
    )

    assert args.domain_command == "asset.options"
    assert main_module.command_payload(args) == {
        "type": "product",
        "field": "category",
        "query": "edtech",
    }


def test_asset_list_rejects_too_many_search_terms() -> None:
    argv = ["asset", "+list", "--type", "topic"]
    for index in range(21):
        argv.extend(["--search-term", f"term-{index}"])

    with pytest.raises(ValueError, match="at most 20"):
        main_module.command_payload(parse(argv))


def test_request_headers_include_active_cli_command() -> None:
    cfg = Config()
    cfg.auth = AuthState(api_key="api-key")
    token = main_module._ACTIVE_COMMAND_NAME.set("asset.list")
    try:
        headers = main_module._request_headers(cfg)
    finally:
        main_module._ACTIVE_COMMAND_NAME.reset(token)

    assert headers["X-Museon-CLI-Command"] == "asset.list"


def test_asset_list_format_parser() -> None:
    args = parse(["asset", "+list", "--type", "format", "--scope", "workspace"])

    assert args.command == "asset"
    assert args.shortcut == "+list"
    assert args.domain_command == "asset.list"
    assert args.asset_type == "format"
    assert args.scope == "workspace"


def test_asset_create_topic_parser() -> None:
    args = parse(
        [
            "asset",
            "+create",
            "--type",
            "topic",
            "--title",
            "Morning routine",
            "--narrative",
            "A compact routine story.",
            "--keyword",
            "routine",
            "--dry-run",
        ]
    )

    assert args.command == "asset"
    assert args.shortcut == "+create"
    assert args.domain_command == "asset.create"
    assert args.asset_type == "topic"
    assert args.title == "Morning routine"
    assert args.dry_run is True


def test_asset_create_topic_direction_parser() -> None:
    args = parse(
        [
            "asset",
            "+create",
            "--type",
            "topic-direction",
            "--title",
            "Recipe",
            "--description",
            "Everyday recipe direction.",
            "--tag",
            "food",
            "--dry-run",
        ]
    )

    assert args.command == "asset"
    assert args.shortcut == "+create"
    assert args.domain_command == "asset.create"
    assert args.asset_type == "topic-direction"
    assert args.title == "Recipe"
    assert args.tags == ["food"]


def test_asset_create_args_json_merges_with_flags() -> None:
    args = parse(
        [
            "asset",
            "+create",
            "--type",
            "persona",
            "--args-json",
            '{"payload":{"description":"v1"}}',
            "--name",
            "Taylor",
            "--tag",
            "fitness",
            "--dry-run",
        ]
    )

    assert main_module.command_payload(args) == {
        "type": "persona",
        "payload": {
            "name": "Taylor",
            "description": "v1",
            "tags": ["fitness"],
        },
    }


def test_asset_create_accepts_format_and_media_types() -> None:
    format_args = parse(
        [
            "asset",
            "+create",
            "--type",
            "format",
            "--url",
            "https://www.tiktok.com/@example/photo/123",
        ]
    )
    media_url_args = parse(
        ["asset", "+create", "--type", "media", "--url", "https://example.com/a.jpg"]
    )
    media_file_args = parse(
        ["asset", "+create", "--type", "media", "--file", "./a.png", "--media-type", "image"]
    )

    assert format_args.domain_command == "asset.create"
    assert format_args.asset_type == "format"
    assert media_url_args.domain_command == "asset.create"
    assert media_url_args.asset_type == "media"
    assert media_file_args.domain_command == "asset.create"
    assert media_file_args.asset_type == "media"


def test_asset_create_format_url_parser() -> None:
    args = parse(
        [
            "asset",
            "+create",
            "--type",
            "format",
            "--url",
            "https://www.tiktok.com/@example/photo/123",
            "--source-kind",
            "tiktok",
        ]
    )

    assert args.command == "asset"
    assert args.shortcut == "+create"
    assert args.domain_command == "asset.create"
    assert args.asset_type == "format"
    assert args.urls == ["https://www.tiktok.com/@example/photo/123"]
    assert args.source_kind == "tiktok"


def test_asset_update_format_analysis_markdown_parser() -> None:
    args = parse(
        [
            "asset",
            "+update",
            "--type",
            "format",
            "--id",
            "f0000000-0000-4000-8000-000000000001",
            "--title",
            "Fast proof grid",
            "--analysis-markdown",
            "Use a clear before/after arc.",
        ]
    )

    assert args.command == "asset"
    assert args.shortcut == "+update"
    assert args.domain_command == "asset.update"
    assert args.asset_type == "format"
    assert main_module.command_payload(args) == {
        "type": "slideshow_soul_skin_format",
        "id": "f0000000-0000-4000-8000-000000000001",
        "payload": {
            "title": "Fast proof grid",
            "format_json": {"md": "Use a clear before/after arc."},
        },
    }


def test_asset_media_commands_parse() -> None:
    listed = parse(
        ["asset", "+list", "--type", "media", "--media-type", "image", "--page-size", "10"]
    )
    item = parse(
        ["asset", "+get", "--type", "media", "--id", "3ed10000-0000-4000-8000-000000000001"]
    )
    imported = parse(["asset", "+create", "--type", "media", "--url", "https://example.com/a.jpg"])
    uploaded = parse(["asset", "+create", "--type", "media", "--file", "./a.png", "--title", "A"])
    deleted = parse(
        ["asset", "+delete", "--type", "media", "--id", "3ed10000-0000-4000-8000-000000000001"]
    )

    assert listed.domain_command == "asset.list"
    assert listed.asset_type == "media"
    assert listed.media_type == "image"
    assert item.domain_command == "asset.get"
    assert item.asset_type == "media"
    assert imported.domain_command == "asset.create"
    assert imported.asset_type == "media"
    assert uploaded.domain_command == "asset.create"
    assert uploaded.asset_type == "media"
    assert deleted.domain_command == "asset.delete"
    assert deleted.asset_type == "media"


def test_generation_create_parser_uses_direct_asset_ids() -> None:
    args = parse(
        [
            "generation",
            "+create",
            "--type",
            "slideshow",
            "--format-id",
            "format-1",
            "--topic-id",
            "topic-1",
            "--persona-id",
            "persona-1",
            "--product-id",
            "product-1",
            "--notes",
            "focus on proof",
            "--metadata-json",
            '{"operator":"cli"}',
            "--dry-run",
        ]
    )

    assert args.command == "generation"
    assert args.shortcut == "+create"
    assert args.domain_command == "generation.create"
    assert main_module.command_payload(args) == {
        "type": "slideshow",
        "format_id": "format-1",
        "content_topic_id": "topic-1",
        "persona_id": "persona-1",
        "product_id": "product-1",
        "custom_prompt": "focus on proof",
        "metadata": {"operator": "cli"},
    }
    assert args.dry_run is True


def test_generation_create_parser_supports_account_source() -> None:
    args = parse(
        [
            "generation",
            "+create",
            "--account-id",
            "account-1",
            "--format-id",
            "format-1",
            "--content-topic-id",
            "topic-1",
        ]
    )

    assert main_module.command_payload(args) == {
        "type": "slideshow",
        "pool_account_id": "account-1",
        "format_id": "format-1",
        "content_topic_id": "topic-1",
    }


def test_generation_create_rejects_missing_direct_persona() -> None:
    args = parse(
        [
            "generation",
            "+create",
            "--format-id",
            "format-1",
            "--topic-id",
            "topic-1",
        ]
    )

    with pytest.raises(ValueError, match="--persona-id"):
        main_module.command_payload(args)


def test_generation_get_list_parsers_and_retry_is_not_exposed() -> None:
    get_args = parse(["generation", "+get", "--id", "generation-1"])
    list_args = parse(
        [
            "generation",
            "+list",
            "--format-id",
            "format-1",
            "--topic-id",
            "topic-1",
            "--status",
            "done",
            "--page-size",
            "5",
        ]
    )

    assert get_args.domain_command == "generation.get"
    assert main_module.command_payload(get_args) == {
        "type": "slideshow",
        "generation_id": "generation-1",
    }
    assert list_args.domain_command == "generation.list"
    assert main_module.command_payload(list_args) == {
        "type": "slideshow",
        "format_id": "format-1",
        "content_topic_id": "topic-1",
        "status": "done",
        "page": 1,
        "page_size": 5,
    }
    with pytest.raises(SystemExit):
        parse(["generation", "+retry", "--id", "generation-1"])


def test_asset_create_format_media_parser() -> None:
    args = parse(
        [
            "asset",
            "+create",
            "--type",
            "format",
            "--media-id",
            "3ed10000-0000-4000-8000-000000000001",
            "--media-id",
            "3ed10000-0000-4000-8000-000000000002",
            "--post-range",
            "0:1",
            "--post-range",
            "1:2",
        ]
    )

    assert args.command == "asset"
    assert args.shortcut == "+create"
    assert args.domain_command == "asset.create"
    assert args.asset_type == "format"
    assert args.media_ids == [
        "3ed10000-0000-4000-8000-000000000001",
        "3ed10000-0000-4000-8000-000000000002",
    ]
    assert args.post_ranges == ["0:1", "1:2"]


def test_asset_create_format_media_rejects_non_half_open_ranges() -> None:
    args = parse(
        [
            "asset",
            "+create",
            "--type",
            "format",
            "--media-id",
            "3ed10000-0000-4000-8000-000000000001",
            "--media-id",
            "3ed10000-0000-4000-8000-000000000002",
            "--post-range",
            "0:0",
            "--post-range",
            "1:2",
        ]
    )

    with pytest.raises(ValueError, match="START < END"):
        main_module.command_payload(args)


def test_social_account_list_parser() -> None:
    args = parse(
        [
            "social-account",
            "+list",
            "--platform",
            "tiktok",
            "--plan-status",
            "with-plan",
            "--allocation-type",
            "account-publish",
            "--search",
            "taylor",
            "--search-term",
            "@nowherepages",
            "--search-term",
            "paper",
            "--tag",
            "coohom",
            "--group-name",
            "GeeLark Team A",
            "--lookup-status",
            "found",
            "--public-only",
            "--has-device",
        ]
    )

    assert args.command == "social-account"
    assert args.shortcut == "+list"
    assert args.domain_command == "social-account.list"
    assert args.plan_status == "with-plan"
    assert args.allocation_type == "account-publish"
    assert main_module.command_payload(args) == {
        "platform": "tiktok",
        "search": "taylor",
        "search_terms": ["@nowherepages", "paper"],
        "automation_status": "with-plan",
        "allocation_type": "account_publish",
        "tag": "coohom",
        "group_name": "GeeLark Team A",
        "lookup_status": "found",
        "is_active": True,
        "is_public": True,
        "has_device": True,
        "page": 1,
        "page_size": 100,
    }


def test_social_account_list_rejects_staff_global_filters() -> None:
    # persona-tag / customer are staff-global ops labels; the agent tier must
    # not expose them (2026-07-08 exposure contract).
    with pytest.raises(SystemExit):
        parse(["social-account", "+list", "--persona-tag", "TECNO"])
    with pytest.raises(SystemExit):
        parse(["social-account", "+list", "--customer", "Medeo"])


def test_social_account_list_schema_includes_batch_search_terms() -> None:
    schema = main_module.schema_payload("social-account.list")

    properties = schema["input_schema"]["properties"]
    assert properties["search_terms"]["type"] == ["array", "null"]
    assert properties["search_terms"]["maxItems"] == 100
    assert "Repeat --search-term" in properties["search_terms"]["description"]
    assert "do not scan pages" in properties["search_terms"]["description"]


def test_social_account_list_rejects_too_many_search_terms() -> None:
    argv = ["social-account", "+list"]
    for index in range(101):
        argv.extend(["--search-term", f"handle_{index}"])
    args = parse(argv)

    with pytest.raises(ValueError, match="at most 100"):
        main_module.command_payload(args)


def test_social_account_assets_set_parser() -> None:
    args = parse(
        [
            "social-account",
            "+assets-set",
            "--id",
            "ac000000-0000-4000-8000-000000000001",
            "--product-id",
            "9d000000-0000-4000-8000-000000000001",
            "--format-id",
            "f0000000-0000-4000-8000-000000000001",
            "--content-topic-id",
            "70000000-0000-4000-8000-000000000001",
        ]
    )

    assert main_module.command_payload(args) == {
        "account_id": "ac000000-0000-4000-8000-000000000001",
        "changes": {
            "product_id": "9d000000-0000-4000-8000-000000000001",
            "format_ids": ["f0000000-0000-4000-8000-000000000001"],
            "content_topic_ids": ["70000000-0000-4000-8000-000000000001"],
        },
    }


def test_social_account_version_create_parser() -> None:
    args = parse(
        [
            "social-account",
            "+version-create",
            "--id",
            "ac000000-0000-4000-8000-000000000001",
            "--rules-json",
            '[{"name":"Daily","timezone":"UTC"}]',
            "--change-note",
            "daily plan",
        ]
    )

    assert main_module.command_payload(args) == {
        "account_id": "ac000000-0000-4000-8000-000000000001",
        "schedule_rules": [{"name": "Daily", "timezone": "UTC"}],
        "change_note": "daily plan",
    }


def test_social_account_schedule_create_parser() -> None:
    args = parse(
        [
            "social-account",
            "+schedule-create",
            "--id",
            "ac000000-0000-4000-8000-000000000001",
            "--scheduled-at",
            "2026-06-10T10:00:00Z",
            "--format-id",
            "f0000000-0000-4000-8000-000000000001",
            "--content-topic-id",
            "70000000-0000-4000-8000-000000000001",
            "--hashtag",
            "ai",
            "--required-mention",
            "@brand",
            "--required-hashtag",
            "launch",
            "--music-name",
            "Demo Sound",
            "--music-ref-video-id",
            "ref-video-1",
        ]
    )

    assert main_module.command_payload(args) == {
        "account_id": "ac000000-0000-4000-8000-000000000001",
        "schedule_item": {
            "scheduled_at": "2026-06-10T10:00:00Z",
            "timezone": "UTC",
            "format_id": "f0000000-0000-4000-8000-000000000001",
            "content_topic_id": "70000000-0000-4000-8000-000000000001",
            "hashtags": ["ai"],
            "required_mentions": ["@brand"],
            "required_hashtags": ["launch"],
            "bgm_by_platform": {
                "tiktok": {
                    "music_name": "Demo Sound",
                    "ref_video_id": "ref-video-1",
                }
            },
            "status": "scheduled",
        },
    }


def test_social_account_schedule_generate_parser_creates_new_generation() -> None:
    args = parse(
        [
            "social-account",
            "+schedule-generate",
            "--id",
            "account-1",
            "--schedule-item-id",
            "schedule-1",
            "--notes",
            "focus on UGC angle",
            "--metadata-json",
            '{"operator":"cli"}',
        ]
    )

    assert args.command == "social-account"
    assert args.shortcut == "+schedule-generate"
    assert args.domain_command == "social-account.schedule-generate"
    assert main_module.command_payload(args) == {
        "account_id": "account-1",
        "schedule_item_id": "schedule-1",
        "generation": {
            "custom_prompt": "focus on UGC angle",
            "metadata": {"operator": "cli"},
        },
    }


def test_social_account_profile_edit_draft_parser_supports_avatar_target() -> None:
    args = parse(
        [
            "social-account",
            "+profile-edit-draft",
            "--id",
            "ac000000-0000-4000-8000-000000000001",
            "--target",
            "avatar",
            "--prompt",
            "friendly late-night chef portrait",
        ]
    )

    assert args.command == "social-account"
    assert args.shortcut == "+profile-edit-draft"
    assert args.domain_command == "social-account.profile-edit-draft"
    assert main_module.command_payload(args) == {
        "account_id": "ac000000-0000-4000-8000-000000000001",
        "profile_edit": {
            "prompt": "friendly late-night chef portrait",
            "targets": ["avatar"],
        },
    }


def test_social_account_profile_edit_draft_defaults_to_text_targets() -> None:
    args = parse(
        [
            "social-account",
            "+profile-edit-draft",
            "--id",
            "ac000000-0000-4000-8000-000000000001",
            "--prompt",
            "friendly AI meeting assistant",
        ]
    )

    assert main_module.command_payload(args)["profile_edit"] == {
        "prompt": "friendly AI meeting assistant",
        "targets": ["nickName", "bio"],
    }


def test_social_account_profile_edit_submit_parser() -> None:
    args = parse(
        [
            "social-account",
            "+profile-edit-submit",
            "--id",
            "ac000000-0000-4000-8000-000000000001",
            "--nick-name",
            "Notta AI",
            "--bio",
            "Meeting notes and translated summaries.",
            "--wait",
            "--timeout",
            "30",
            "--poll-interval",
            "1",
        ]
    )

    assert args.command == "social-account"
    assert args.shortcut == "+profile-edit-submit"
    assert args.domain_command == "social-account.profile-edit-submit"
    assert main_module.command_payload(args) == {
        "account_id": "ac000000-0000-4000-8000-000000000001",
        "profile_edit": {
            "nick_name": "Notta AI",
            "bio": "Meeting notes and translated summaries.",
        },
        "wait": True,
        "wait_timeout_seconds": 30.0,
        "poll_interval_seconds": 1.0,
    }


def test_social_account_profile_edit_submit_parser_accepts_avatar_url() -> None:
    args = parse(
        [
            "social-account",
            "+profile-edit-submit",
            "--id",
            "ac000000-0000-4000-8000-000000000001",
            "--avatar-url",
            "https://cdn.example.com/avatar.png",
        ]
    )

    assert main_module.command_payload(args) == {
        "account_id": "ac000000-0000-4000-8000-000000000001",
        "profile_edit": {"avatar_url": "https://cdn.example.com/avatar.png"},
        "wait": False,
        "wait_timeout_seconds": 300.0,
        "poll_interval_seconds": 5.0,
    }


def test_social_account_profile_edit_status_parser() -> None:
    args = parse(
        [
            "social-account",
            "+profile-edit-status",
            "--id",
            "73000000-0000-4000-8000-000000000001",
        ]
    )

    assert args.command == "social-account"
    assert args.shortcut == "+profile-edit-status"
    assert args.domain_command == "social-account.profile-edit-status"
    assert main_module.command_payload(args) == {"task_id": "73000000-0000-4000-8000-000000000001"}


def test_social_account_profile_edit_status_rejects_placeholder_task_id() -> None:
    args = parse(["social-account", "+profile-edit-status", "--id", "?"])
    cfg = Config()

    with pytest.raises(ValueError, match="task_id must be a canonical UUID"):
        asyncio.run(main_module.dispatch_domain_command(args, cfg))


_BATCH_ACCOUNT_UPDATES_JSON = (
    '[{"account_id":"ac000000-0000-4000-8000-000000000001",'
    '"bio":"AI assistant"}]'
)


def test_social_account_profile_edit_batch_submit_parser() -> None:
    args = parse(
        [
            "social-account",
            "+profile-edit-batch-submit",
            "--account-updates",
            _BATCH_ACCOUNT_UPDATES_JSON,
            "--update-bio",
        ]
    )

    assert args.command == "social-account"
    assert args.shortcut == "+profile-edit-batch-submit"
    assert args.domain_command == "social-account.profile-edit-batch-submit"
    payload = main_module.command_payload(args)
    assert payload["account_updates"] == [
        {"account_id": "ac000000-0000-4000-8000-000000000001", "bio": "AI assistant"}
    ]
    assert payload["update_bio"] is True
    assert payload["update_nick_name"] is False
    assert payload["wait"] is False


def test_social_account_profile_edit_batch_submit_parser_with_wait() -> None:
    args = parse(
        [
            "social-account",
            "+profile-edit-batch-submit",
            "--account-updates",
            _BATCH_ACCOUNT_UPDATES_JSON,
            "--update-bio",
            "--wait",
            "--timeout",
            "60",
        ]
    )

    payload = main_module.command_payload(args)
    assert payload["wait"] is True
    assert payload["wait_timeout_seconds"] == 60.0


def test_social_account_profile_edit_batch_submit_rejects_empty_updates() -> None:
    args = parse(
        [
            "social-account",
            "+profile-edit-batch-submit",
            "--account-updates",
            "[]",
            "--update-bio",
        ]
    )
    with pytest.raises(ValueError, match="non-empty JSON array"):
        main_module.command_payload(args)


def test_social_account_profile_edit_batch_submit_rejects_invalid_json() -> None:
    args = parse(
        [
            "social-account",
            "+profile-edit-batch-submit",
            "--account-updates",
            "not-json",
            "--update-bio",
        ]
    )
    with pytest.raises(ValueError, match="must be valid JSON"):
        main_module.command_payload(args)


def test_dispatch_social_account_profile_edit_batch_submit_uses_agent_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="Workspace", organization_id="org-1")
    calls: list[dict[str, object]] = []

    async def fake_api_data(
        cfg_arg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
        unwrap_success: bool = True,
    ) -> dict[str, object]:
        del cfg_arg, params, unwrap_success
        calls.append({"method": method, "path": path, "json_body": json_body})
        return {
            "domain": "social-account",
            "operation": "profile-edit-batch-submit",
            "result": {
                "task_id": "73000000-0000-4000-8000-000000000001",
                "status": "pending",
            },
        }

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    args = parse(
        [
            "social-account",
            "+profile-edit-batch-submit",
            "--account-updates",
            _BATCH_ACCOUNT_UPDATES_JSON,
            "--update-bio",
        ]
    )
    result = asyncio.run(main_module.dispatch(args))

    assert result["command"] == "social-account.profile-edit-batch-submit"
    # The routine-wakeup path copies watch_command verbatim, so it must use the
    # flag the status command actually accepts (--id, not --task-id).
    assert result["run"] == {
        "id": "73000000-0000-4000-8000-000000000001",
        "type": "pool_account_profile_edit",
        "status": "pending",
        "watch_command": (
            "museoncli social-account +profile-edit-status "
            "--id 73000000-0000-4000-8000-000000000001"
        ),
    }
    assert calls == [
        {
            "method": "POST",
            "path": "/agent-cli/social-accounts/profile-edit/tasks",
            "json_body": {
                "workspace_id": "workspace-1",
                "payload": {
                    "account_updates": [
                        {
                            "account_id": "ac000000-0000-4000-8000-000000000001",
                            "bio": "AI assistant",
                        }
                    ],
                    "update_nick_name": False,
                    "update_bio": True,
                    "update_avatar": False,
                },
            },
        }
    ]


def test_profile_edit_run_status_distinguishes_failed_provider_result() -> None:
    run = envelopes_module._profile_edit_run_from_data(
        {
            "task_id": "73000000-0000-4000-8000-000000000001",
            "status": "running",
            "provider_status": {
                "summary": {
                    "total": 1,
                    "completed": 0,
                    "failed": 1,
                    "pending": 0,
                    "settled": True,
                }
            },
        }
    )

    assert run is not None
    assert run["status"] == "failed"


def test_profile_edit_run_status_distinguishes_partial_failure() -> None:
    run = envelopes_module._profile_edit_run_from_data(
        {
            "task_id": "73000000-0000-4000-8000-000000000001",
            "provider_status": {
                "summary": {
                    "total": 2,
                    "completed": 1,
                    "failed": 1,
                    "pending": 0,
                    "settled": True,
                }
            },
        }
    )

    assert run is not None
    assert run["status"] == "partial_failed"


def test_provider_projection_preserves_semantic_result_fields() -> None:
    projected = envelopes_module.without_provider_metadata(
        {
            "provider": "internal-vendor",
            "source": "tiktok_photos",
            "items": [{"id": "post-1", "play_count": 120_000}],
            "pagination": {"cursor": "next-page"},
            "coverage": {"kind": "sampled", "complete": False},
            "provider_status": {"summary": {"settled": True}},
            "provider_status_code": 429,
            "retryable": True,
            "error_category": "rate_limited",
        }
    )

    assert projected == {
        "source": "tiktok_photos",
        "items": [{"id": "post-1", "play_count": 120_000}],
        "pagination": {"cursor": "next-page"},
        "coverage": {"kind": "sampled", "complete": False},
        "delivery_status": {"summary": {"settled": True}},
        "upstream_status_code": 429,
        "retryable": True,
        "error_category": "rate_limited",
    }


def test_campaign_monitor_post_resolve_parser() -> None:
    args = parse(
        [
            "campaign-monitor",
            "+post-resolve",
            "--schedule-item-id",
            "5c000000-0000-4000-8000-000000000001",
        ]
    )

    assert args.command == "campaign-monitor"
    assert args.shortcut == "+post-resolve"
    assert args.domain_command == "campaign-monitor.post-resolve"
    assert main_module.command_payload(args) == {
        "schedule_item_id": "5c000000-0000-4000-8000-000000000001"
    }


def test_campaign_monitor_post_performance_parser() -> None:
    args = parse(
        [
            "campaign-monitor",
            "+post-performance-get",
            "--id",
            "c0000000-0000-4000-8000-000000000001",
            "--date-from",
            "2026-06-01",
            "--limit",
            "10",
        ]
    )

    assert args.command == "campaign-monitor"
    assert args.shortcut == "+post-performance-get"
    assert args.domain_command == "campaign-monitor.post-performance-get"
    assert main_module.command_payload(args) == {
        "content_id": "c0000000-0000-4000-8000-000000000001",
        "date_from": "2026-06-01",
        "limit": 10,
    }


def test_dispatch_campaign_monitor_post_list_warns_about_synced_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="Workspace", organization_id="org-1")
    creator_id = "c1000000-0000-4000-8000-000000000001"
    calls: list[dict[str, object]] = []

    async def fake_api_data(
        cfg_arg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
        unwrap_success: bool = True,
    ) -> dict[str, object]:
        del cfg_arg, json_body, unwrap_success
        calls.append({"method": method, "path": path, "params": params})
        return {
            "domain": "campaign-monitor",
            "operation": "post-list",
            "result": {
                "creator_id": creator_id,
                "items": [],
                "pagination": {"page": 1, "page_size": 20, "total": 0},
            },
        }

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    args = parse(
        [
            "campaign-monitor",
            "+post-list",
            "--creator-id",
            creator_id,
        ]
    )
    result = asyncio.run(main_module.dispatch(args))

    assert result["command"] == "campaign-monitor.post-list"
    assert result["data"]["items"] == []
    assert result["warnings"] == [
        (
            "This command reads Museon's synced monitor store only; use "
            "campaign-monitor +content-list/+creator-list/+summary for "
            "campaign-scoped collections and research +social-media-search "
            "for external discovery."
        )
    ]
    assert calls == [
        {
            "method": "GET",
            "path": f"/agent-cli/social-media/creators/{creator_id}/posts",
            "params": {"workspace_id": "workspace-1", "page": 1, "page_size": 20},
        }
    ]


def test_campaign_monitor_content_list_parser() -> None:
    args = parse(
        [
            "campaign-monitor",
            "+content-list",
            "--id",
            "campaign-1",
            "--creator-id",
            "c4000000-0000-4000-8000-000000000001",
            "--platform",
            "tiktok",
            "--date-from",
            "2026-06-01",
            "--page-size",
            "10",
            "--sort",
            "views_desc",
        ]
    )

    assert args.command == "campaign-monitor"
    assert args.shortcut == "+content-list"
    assert args.domain_command == "campaign-monitor.content-list"
    assert main_module.command_payload(args) == {
        "campaign_id": "campaign-1",
        "date_from": "2026-06-01",
        "page": 1,
        "page_size": 10,
        "platform": "tiktok",
        "sort": "views_desc",
        "creator_id": "c4000000-0000-4000-8000-000000000001",
    }


def test_campaign_monitor_schema_exposes_tracking_commands() -> None:
    schema = main_module.schema_payload("campaign-monitor")

    assert schema["domain"] == "campaign-monitor"
    assert [command["name"] for command in schema["commands"]] == [
        "campaign-monitor.list",
        "campaign-monitor.get",
        "campaign-monitor.creator-list",
        "campaign-monitor.creator-add",
        "campaign-monitor.creator-remove",
        "campaign-monitor.content-list",
        "campaign-monitor.content-add",
        "campaign-monitor.content-remove",
        "campaign-monitor.content-batch-remove",
        "campaign-monitor.summary",
        "campaign-monitor.creator-get",
        "campaign-monitor.post-list",
        "campaign-monitor.creator-performance-get",
        "campaign-monitor.post-get",
        "campaign-monitor.post-performance-get",
        "campaign-monitor.post-resolve",
    ]


@pytest.mark.parametrize(
    "shortcut,args",
    [
        ("+format-import-url", ["--url", "https://www.tiktok.com/@example/photo/123"]),
        ("+format-import-media", ["--media-id", "3ed10000-0000-4000-8000-000000000001"]),
        ("+media-import-url", ["--url", "https://example.com/a.jpg"]),
        ("+media-upload", ["--file", "./a.png"]),
    ],
)
def test_asset_legacy_special_commands_are_not_exposed(
    shortcut: str,
    args: list[str],
) -> None:
    with pytest.raises(SystemExit):
        parse(["asset", shortcut, *args])


def test_skills_get_parser() -> None:
    args = parse(
        [
            "skills",
            "+get",
            "--name",
            "social-persona-account-analysis",
            "--offset",
            "10",
            "--limit",
            "20",
        ]
    )

    assert args.command == "skills"
    assert args.shortcut == "+get"
    assert args.domain_command == "skills.get"
    assert args.name == "social-persona-account-analysis"
    assert args.offset == 10
    assert args.limit == 20


def test_skills_create_parser_reads_inline_content() -> None:
    args = parse(
        [
            "skills",
            "+create",
            "--name",
            "social-persona-account-analysis",
            "--content",
            "# Skill",
            "--workspace-id",
            "workspace-1",
            "--reference-json",
            '{"docs":["https://example.com"]}',
            "--is-public",
        ]
    )

    assert args.command == "skills"
    assert args.shortcut == "+create"
    assert args.domain_command == "skills.create"
    assert args.name == "social-persona-account-analysis"
    assert args.workspace_id == "workspace-1"
    assert args.content == "# Skill"
    assert args.reference_json == '{"docs":["https://example.com"]}'
    assert args.is_active is True
    assert args.is_public is True


def test_skills_create_parser_rejects_invalid_reference_json() -> None:
    args = parse(
        [
            "skills",
            "+create",
            "--name",
            "social-persona-account-analysis",
            "--content",
            "# Skill",
            "--reference-json",
            "{bad",
        ]
    )

    with pytest.raises(ValueError, match="--reference-json must be valid JSON"):
        get_command_spec(args.domain_command).build_arguments(args)


def test_skills_update_parser_can_deactivate_and_unpublish() -> None:
    args = parse(
        [
            "skills",
            "+update",
            "--name",
            "social-persona-account-analysis",
            "--no-is-active",
            "--no-is-public",
            "--reference-json",
            "null",
        ]
    )

    assert args.command == "skills"
    assert args.shortcut == "+update"
    assert args.domain_command == "skills.update"
    assert args.name == "social-persona-account-analysis"
    assert args.is_active is False
    assert args.is_public is False
    assert get_command_spec(args.domain_command).build_arguments(args)["reference"] is None


def test_evaluator_create_parser_defaults_private() -> None:
    args = parse(
        [
            "evaluator",
            "+create",
            "--kind",
            "content_generation",
            "--name",
            "Content quality",
            "--prompt",
            "Score the generated content.",
        ]
    )

    assert args.command == "evaluator"
    assert args.shortcut == "+create"
    assert args.domain_command == "evaluator.create"
    assert args.kind == "content_generation"
    assert args.name == "Content quality"
    assert args.prompt == "Score the generated content."
    assert args.is_public is False


def test_evaluator_parser_rejects_model_config_flags() -> None:
    with pytest.raises(SystemExit):
        parse(
            [
                "evaluator",
                "+create",
                "--kind",
                "content_generation",
                "--name",
                "Content quality",
                "--prompt",
                "Score the generated content.",
                "--model-config-json",
                '{"model":"gpt-4.1-mini"}',
            ]
        )

    with pytest.raises(SystemExit):
        parse(
            [
                "evaluator",
                "+update",
                "--id",
                "10000000-0000-4000-8000-000000000001",
                "--model-config-json",
                '{"model":"gpt-4.1-mini"}',
            ]
        )


def test_evaluator_update_parser_can_publish_and_activate() -> None:
    args = parse(
        [
            "evaluator",
            "+update",
            "--id",
            "10000000-0000-4000-8000-000000000001",
            "--kind",
            "brand_voice_review",
            "--is-public",
            "--is-active",
        ]
    )

    assert args.command == "evaluator"
    assert args.shortcut == "+update"
    assert args.domain_command == "evaluator.update"
    assert args.evaluator_type_id == "10000000-0000-4000-8000-000000000001"
    assert args.kind == "brand_voice_review"
    assert args.is_public is True
    assert args.is_active is True
    assert main_module.command_payload(args) == {
        "evaluator_type_id": "10000000-0000-4000-8000-000000000001",
        "kind": "brand_voice_review",
        "is_active": True,
        "is_public": True,
    }


def test_evaluator_run_parser_accepts_text_media_and_extra_context() -> None:
    args = parse(
        [
            "evaluator",
            "+run",
            "--id",
            "10000000-0000-4000-8000-000000000001",
            "--text",
            "Generated copy",
            "--media-id",
            "20000000-0000-4000-8000-000000000001",
            "--extra-context-json",
            '{"channel":"tiktok"}',
        ]
    )

    assert args.command == "evaluator"
    assert args.shortcut == "+run"
    assert args.domain_command == "evaluator.run"
    assert args.evaluator_type_id == "10000000-0000-4000-8000-000000000001"
    assert args.text == "Generated copy"
    assert args.media_ids == ["20000000-0000-4000-8000-000000000001"]
    assert args.extra_context_json == '{"channel":"tiktok"}'


@pytest.mark.parametrize(
    "argv",
    [
        ["tools", "list"],
        ["tools", "describe", "search"],
        ["tools", "call", "search"],
        ["tool", "call", "search"],
        ["jobs", "get", "job-1"],
        ["jobs", "watch", "job-1"],
        ["job", "watch", "job-1"],
        ["skills", "list"],
        ["skills", "read", "/museoncli/skills/foo/SKILL.md"],
    ],
)
def test_legacy_public_commands_are_removed(argv: list[str]) -> None:
    with pytest.raises(SystemExit):
        parse(argv)


def test_schema_lists_fixed_domains_and_research_commands() -> None:
    result = asyncio.run(main_module.dispatch(argparse.Namespace(command="schema", name=None)))

    assert result["data"]["domains"] == [
        "research",
        "content-analysis",
        "asset",
        "artifacts",
        "generation",
        "social-account",
        "account-publish",
        "campaign-monitor",
        "skills",
        "evaluator",
        "routines",
        "account-operation",
    ]
    assert [item["name"] for item in result["data"]["commands"]["research"]] == [
        "research.web-research",
        "research.social-media-search",
        "research.community-search",
        "research.visual-analyze",
    ]
    assert [item["name"] for item in result["data"]["commands"]["content-analysis"]] == [
        "content-analysis.run",
        "content-analysis.get",
        "content-analysis.list",
    ]
    assert [item["name"] for item in result["data"]["commands"]["asset"]] == [
        "asset.list",
        "asset.get",
        "asset.get-batch",
        "asset.options",
        "asset.create",
        "asset.update",
        "asset.delete",
    ]
    assert [item["name"] for item in result["data"]["commands"]["generation"]] == [
        "generation.create",
        "generation.get",
        "generation.list",
    ]
    assert [item["name"] for item in result["data"]["commands"]["social-account"]] == [
        "social-account.list",
        "social-account.get",
        "social-account.connect-link-create",
        "social-account.connect-link-status",
        "social-account.performance-get",
        "social-account.assets-get",
        "social-account.assets-set",
        "social-account.bgm-asset-list",
        "social-account.bgm-asset-create",
        "social-account.config-get",
        "social-account.config-update",
        "social-account.config-batch-update",
        "social-account.version-list",
        "social-account.version-get",
        "social-account.version-create",
        "social-account.version-activate",
        "social-account.schedule-list",
        "social-account.schedule-get",
        "social-account.schedule-generate",
        "social-account.schedule-create",
        "social-account.schedule-update",
        "social-account.schedule-delete",
        "social-account.profile-edit-draft",
        "social-account.profile-edit-submit",
        "social-account.profile-edit-batch-submit",
        "social-account.profile-edit-status",
        "social-account.avatar-generate-batch",
        "social-account.avatar-generate-status",
    ]
    assert [item["name"] for item in result["data"]["commands"]["campaign-monitor"]] == [
        "campaign-monitor.list",
        "campaign-monitor.get",
        "campaign-monitor.creator-list",
        "campaign-monitor.creator-add",
        "campaign-monitor.creator-remove",
        "campaign-monitor.content-list",
        "campaign-monitor.content-add",
        "campaign-monitor.content-remove",
        "campaign-monitor.content-batch-remove",
        "campaign-monitor.summary",
        "campaign-monitor.creator-get",
        "campaign-monitor.post-list",
        "campaign-monitor.creator-performance-get",
        "campaign-monitor.post-get",
        "campaign-monitor.post-performance-get",
        "campaign-monitor.post-resolve",
    ]
    assert "social-media" not in result["data"]["commands"]
    assert [item["name"] for item in result["data"]["commands"]["skills"]] == [
        "skills.list",
        "skills.get",
        "skills.create",
        "skills.update",
    ]
    assert [item["name"] for item in result["data"]["commands"]["evaluator"]] == [
        "evaluator.kind-list",
        "evaluator.list",
        "evaluator.get",
        "evaluator.create",
        "evaluator.update",
        "evaluator.run",
        "evaluator.run-list",
        "evaluator.run-get",
    ]
    assert [item["name"] for item in result["data"]["commands"]["routines"]] == [
        "routines.list",
        "routines.get",
        "routines.create-ad-hoc",
        "routines.create-draft",
        "routines.accept-draft",
        "routines.rebuild-ad-hoc",
        "routines.cancel",
        "routines.pause",
        "routines.resume",
        "routines.memory-get",
        "routines.record",
    ]


def test_content_analysis_run_schema_exposes_source_and_wait_contract() -> None:
    result = asyncio.run(
        main_module.dispatch(argparse.Namespace(command="schema", name="content-analysis.run"))
    )

    data = result["data"]
    input_schema = data["input_schema"]
    properties = input_schema["properties"]

    assert data["risk_level"] == "write"
    assert data["execution"] == "async_run"
    assert properties["type"]["enum"] == ["content-analysis", "reverse-ai-prompt"]
    assert properties["media_type"]["enum"] == ["video"]
    assert properties["media_type"]["default"] == "video"
    assert input_schema["oneOf"] == [
        {"required": ["url"]},
        {"required": ["media_id"]},
        {"required": ["file"]},
    ]
    assert "share_url" in data["output_schema"]["description"]
    assert "public_token" in data["output_schema"]["description"]
    assert properties["wait_timeout_seconds"]["maximum"] == 300
    assert properties["poll_interval_seconds"]["maximum"] == 10


def test_schema_returns_one_command_contract() -> None:
    result = asyncio.run(
        main_module.dispatch(argparse.Namespace(command="schema", name="research.visual-analyze"))
    )

    assert result["data"]["name"] == "research.visual-analyze"
    assert result["data"]["shortcut"] == "+visual-analyze"
    assert result["data"]["risk_level"] == "read"
    assert "credit_cost" not in result["data"]  # costs are a server-side concern
    assert "usd_cost" not in result["data"]
    assert "Museon media" in result["data"]["summary"]
    properties = result["data"]["input_schema"]["properties"]
    assert {"model", "temperature", "max_output_tokens"}.isdisjoint(properties)
    assert any("asset +create --type media --url" in item for item in result["data"]["examples"])
    assert "adapter" not in result["data"]


def test_schema_marks_generation_starters_as_async() -> None:
    generation = asyncio.run(
        main_module.dispatch(argparse.Namespace(command="schema", name="generation.create"))
    )
    schedule_generate = asyncio.run(
        main_module.dispatch(
            argparse.Namespace(command="schema", name="social-account.schedule-generate")
        )
    )

    assert generation["data"]["execution"] == "async_run"
    assert schedule_generate["data"]["execution"] == "async_run"
    assert generation["data"]["output_schema"]["properties"]["run"]["type"] == "object"


def test_schema_exposes_profile_edit_avatar_draft_target() -> None:
    result = asyncio.run(
        main_module.dispatch(
            argparse.Namespace(command="schema", name="social-account.profile-edit-draft")
        )
    )

    targets_schema = result["data"]["input_schema"]["properties"]["profile_edit"]["properties"][
        "targets"
    ]
    assert targets_schema["items"]["enum"] == ["nickName", "bio", "avatar"]
    assert targets_schema["default"] == ["nickName", "bio"]


def test_schema_returns_long_skill_description_limit() -> None:
    result = asyncio.run(
        main_module.dispatch(argparse.Namespace(command="schema", name="skills.create"))
    )

    assert result["data"]["input_schema"]["properties"]["description"]["maxLength"] == 20000
    assert "reference" in result["data"]["input_schema"]["properties"]
    assert "workspace_id" in result["data"]["input_schema"]["properties"]
    assert result["data"]["input_schema"]["properties"]["is_active"] == {
        "type": "boolean",
        "default": True,
    }


def test_schema_returns_domain_command_catalog() -> None:
    result = asyncio.run(main_module.dispatch(argparse.Namespace(command="schema", name="skills")))

    assert result["data"]["domain"] == "skills"
    assert [item["name"] for item in result["data"]["commands"]] == [
        "skills.list",
        "skills.get",
        "skills.create",
        "skills.update",
    ]
    assert all("adapter" not in item for item in result["data"]["commands"])


def test_schema_returns_evaluator_command_catalog() -> None:
    result = asyncio.run(
        main_module.dispatch(argparse.Namespace(command="schema", name="evaluator"))
    )

    assert result["data"]["domain"] == "evaluator"
    assert [item["name"] for item in result["data"]["commands"]] == [
        "evaluator.kind-list",
        "evaluator.list",
        "evaluator.get",
        "evaluator.create",
        "evaluator.update",
        "evaluator.run",
        "evaluator.run-list",
        "evaluator.run-get",
    ]
    assert all("adapter" not in item for item in result["data"]["commands"])


def test_schema_hides_evaluator_model_config_inputs() -> None:
    create = asyncio.run(
        main_module.dispatch(argparse.Namespace(command="schema", name="evaluator.create"))
    )
    update = asyncio.run(
        main_module.dispatch(argparse.Namespace(command="schema", name="evaluator.update"))
    )

    assert "model_config" not in create["data"]["input_schema"]["properties"]
    assert "model_config" not in update["data"]["input_schema"]["properties"]
    assert "model config" not in update["data"]["summary"]


@pytest.mark.parametrize(
    "argv",
    [
        [
            "research",
            "+visual-analyze",
            "--media",
            "https://example.com/image.png",
            "--prompt",
            "Analyze this",
            "--args-json",
            '{"model":"server-model"}',
        ],
        [
            "generation",
            "+create",
            "--schedule-item-id",
            "schedule-1",
            "--args-json",
            '{"image_model":"server-model"}',
        ],
        [
            "asset",
            "+create",
            "--type",
            "format",
            "--url",
            "https://www.tiktok.com/@example/photo/123",
            "--args-json",
            '{"payload":{"analysis_model":"server-model"}}',
        ],
        [
            "social-account",
            "+schedule-generate",
            "--id",
            "account-1",
            "--schedule-item-id",
            "schedule-1",
            "--args-json",
            '{"generation":{"text_model":"server-model"}}',
        ],
    ],
)
def test_public_commands_reject_server_model_controls_in_structured_args(
    argv: list[str],
) -> None:
    with pytest.raises(ValueError, match="server-controlled"):
        main_module.command_payload(parse(argv))


def test_schema_returns_routines_command_catalog() -> None:
    result = asyncio.run(
        main_module.dispatch(argparse.Namespace(command="schema", name="routines"))
    )

    assert result["data"]["domain"] == "routines"
    assert [item["name"] for item in result["data"]["commands"]] == [
        "routines.list",
        "routines.get",
        "routines.create-ad-hoc",
        "routines.create-draft",
        "routines.accept-draft",
        "routines.rebuild-ad-hoc",
        "routines.cancel",
        "routines.pause",
        "routines.resume",
        "routines.memory-get",
        "routines.record",
    ]


def test_schema_returns_routines_list_standard_pagination_contract() -> None:
    result = asyncio.run(
        main_module.dispatch(argparse.Namespace(command="schema", name="routines.list"))
    )

    props = result["data"]["input_schema"]["properties"]
    assert "offset" not in props
    assert "limit" not in props
    assert props["mode"] == {"type": "string", "enum": ["ad_hoc"]}
    assert props["status"] == {
        "type": "string",
        "enum": ["draft", "active", "disabled", "archived"],
    }
    assert props["search"] == {"type": "string"}
    assert props["page"] == {"type": "integer", "minimum": 1, "default": 1}
    assert props["page_size"] == {
        "type": "integer",
        "minimum": 1,
        "maximum": 100,
        "default": 20,
    }
    assert "Lifecycle writes are only allowed on routines you own" in result["data"]["summary"]
    assert "museoncli routines +list --mode ad_hoc --page-size 20" in result["data"]["examples"]


def test_dispatch_routines_list_uses_standard_pagination(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    calls: list[dict[str, object]] = []

    async def fake_api_data(
        cfg_arg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
    ) -> dict[str, object]:
        del cfg_arg, json_body
        calls.append({"method": method, "path": path, "params": params})
        return {
            "items": [],
            "page": 2,
            "page_size": 10,
            "total": 0,
            "total_pages": 1,
            "has_more": False,
        }

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    args = parse(
        [
            "routines",
            "+list",
            "--workspace-id",
            "70000000-0000-4000-8000-000000000001",
            "--mode",
            "ad-hoc",
            "--status",
            "active",
            "--search",
            "daily",
            "--page",
            "2",
            "--page-size",
            "10",
        ]
    )
    result = asyncio.run(main_module.dispatch(args))

    assert result == {
        "command": "routines.list",
        "workspace": {"id": "70000000-0000-4000-8000-000000000001"},
        "data": {
            "items": [],
            "page": 2,
            "page_size": 10,
            "total": 0,
            "total_pages": 1,
            "has_more": False,
        },
        "run": None,
        "warnings": [],
        "next_steps": [],
    }
    assert calls == [
        {
            "method": "GET",
            "path": "/agent-cli/routines",
            "params": {
                "workspace_id": "70000000-0000-4000-8000-000000000001",
                "mode": "ad_hoc",
                "status": "active",
                "search": "daily",
                "page": 2,
                "page_size": 10,
            },
        }
    ]
    sent_params = calls[0]["params"]
    assert isinstance(sent_params, dict)
    assert "offset" not in sent_params
    assert "limit" not in sent_params


def test_dispatch_routines_list_adds_schedule_refs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="Workspace", organization_id="org-1")

    async def fake_api_data(
        cfg_arg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
    ) -> dict[str, object]:
        del cfg_arg, method, path, json_body, params
        return {
            "items": [
                {
                    "id": "routine id/with slash",
                    "name": "Daily [Growth]\nReview",
                    "created_by_user_id": "user-1",
                    "owner_display_name": "Owner One",
                    "active_trigger": {
                        "source_conversation_id": "conversation-1",
                        "target_conversation_id": "conversation-target",
                    },
                },
                {
                    "id": "routine-2",
                },
            ],
            "page": 1,
            "page_size": 20,
            "total": 2,
            "total_pages": 1,
            "has_more": False,
        }

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    result = asyncio.run(main_module.dispatch(parse(["routines", "+list"])))

    assert result["data"]["items"][0]["ref"] == (
        "[Daily \\[Growth\\] Review](https://www.museon.ai/routines/routine%20id%2Fwith%20slash)"
    )
    assert result["data"]["items"][0]["owner_label"] == "Owner One"
    assert result["data"]["items"][0]["anchor_label"] == (
        "source=conversation-1; target=conversation-target"
    )
    assert result["data"]["items"][1]["ref"] == (
        "[routine-2](https://www.museon.ai/routines/routine-2)"
    )


def test_dispatch_routines_get_adds_schedule_ref(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="Workspace", organization_id="org-1")

    async def fake_api_data(
        cfg_arg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
    ) -> dict[str, object]:
        del cfg_arg, method, path, json_body, params
        return {
            "id": "routine-1",
            "name": "Morning schedule",
            "created_by_user_id": "user-1",
            "owner_display_name": None,
            "active_trigger": {
                "source_channel_message_id": "message-1",
                "target_channel_id": "channel-1",
                "target_channel_chat_id": "chat-1",
            },
        }

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    result = asyncio.run(main_module.dispatch(parse(["routines", "+get", "--id", "routine-1"])))

    assert result["data"]["ref"] == ("[Morning schedule](https://www.museon.ai/routines/routine-1)")
    assert result["data"]["owner_label"] == "user-1"
    assert result["data"]["anchor_label"] == "source=message:message-1; target=channel-1/chat-1"


@pytest.mark.parametrize(
    ("argv", "workspace_location"),
    [
        (["routines", "+list"], "params"),
        (["routines", "+get", "--id", "routine-1"], "params"),
        (
            [
                "routines",
                "+create-ad-hoc",
                "--name",
                "Daily check",
                "--instruction",
                "Check daily.",
                "--trigger-config-json",
                '{"schema_version":1,"kind":"recurring","timezone":"UTC","cron":"0 9 * * *"}',
            ],
            "json_body",
        ),
        (
            [
                "routines",
                "+create-draft",
                "--name",
                "Daily check",
                "--instruction",
                "Check daily.",
                "--trigger-config-json",
                '{"schema_version":1,"kind":"recurring","timezone":"UTC","cron":"0 9 * * *"}',
            ],
            "json_body",
        ),
        (["routines", "+accept-draft", "--id", "routine-1"], "params"),
        (
            [
                "routines",
                "+rebuild-ad-hoc",
                "--id",
                "routine-1",
                "--name",
                "Daily check",
                "--instruction",
                "Check daily.",
                "--trigger-config-json",
                '{"schema_version":1,"kind":"recurring","timezone":"UTC","cron":"0 9 * * *"}',
            ],
            "json_body",
        ),
        (["routines", "+cancel", "--id", "routine-1"], "params"),
        (["routines", "+pause", "--id", "routine-1"], "params"),
        (["routines", "+resume", "--id", "routine-1"], "params"),
        (["routines", "+memory-get", "--id", "routine-1"], "params"),
        (["routines", "+record", "output", "--id", "routine-1", "--content", "Done"], "params"),
    ],
)
def test_dispatch_routines_use_selected_workspace_when_workspace_id_is_omitted(
    monkeypatch: pytest.MonkeyPatch,
    argv: list[str],
    workspace_location: str,
) -> None:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="Workspace", organization_id="org-1")
    calls: list[dict[str, object]] = []

    async def fake_api_data(
        cfg_arg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
    ) -> dict[str, object]:
        del cfg_arg
        calls.append({"method": method, "path": path, "json_body": json_body, "params": params})
        return {"ok": True}

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    result = asyncio.run(main_module.dispatch(parse(argv)))

    assert result["data"] == {"ok": True}
    assert result["command"].startswith("routines.")
    target = calls[0][workspace_location]
    assert isinstance(target, dict)
    assert target["workspace_id"] == "workspace-1"


def test_dispatch_routines_workspace_id_arg_overrides_selected_workspace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="Workspace", organization_id="org-1")
    calls: list[dict[str, object]] = []

    async def fake_api_data(
        cfg_arg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
    ) -> dict[str, object]:
        del cfg_arg, method, path, params
        calls.append({"json_body": json_body})
        return {"ok": True}

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    asyncio.run(
        main_module.dispatch(
            parse(
                [
                    "routines",
                    "+create-ad-hoc",
                    "--workspace-id",
                    "70000000-0000-4000-8000-000000000099",
                    "--name",
                    "Daily check",
                    "--instruction",
                    "Check daily.",
                    "--trigger-config-json",
                    '{"schema_version":1,"kind":"recurring","timezone":"UTC","cron":"0 9 * * *"}',
                ]
            )
        )
    )

    assert calls == [
        {
            "json_body": {
                "workspace_id": "70000000-0000-4000-8000-000000000099",
                "name": "Daily check",
                "instruction": "Check daily.",
                "trigger_config": {
                    "schema_version": 1,
                    "kind": "recurring",
                    "timezone": "UTC",
                    "cron": "0 9 * * *",
                },
                "idempotency_key": None,
                "turn_context": {},
            }
        }
    ]


def test_dispatch_routines_create_ad_hoc_adds_other_scope_to_turn_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="Workspace", organization_id="org-1")
    cfg.runtime_context = {
        "conversation_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "channel_id": "70000000-0000-4000-8000-000000000077",
        "source_channel_message_id": "99999999-9999-9999-9999-999999999999",
        "source_external_message_id": "om_x",
        "origin_turn_id": "turn:99999999-9999-9999-9999-999999999999",
    }
    calls: list[dict[str, object]] = []

    async def fake_api_data(
        cfg_arg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
    ) -> dict[str, object]:
        del cfg_arg, method, path, params
        calls.append({"json_body": json_body})
        return {"ok": True}

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    asyncio.run(
        main_module.dispatch(
            parse(
                [
                    "routines",
                    "+create-ad-hoc",
                    "--name",
                    "Daily check",
                    "--instruction",
                    "Check daily.",
                    "--trigger-config-json",
                    '{"schema_version":1,"kind":"recurring","timezone":"UTC","cron":"0 9 * * *"}',
                    "--other-scope-conversation-id",
                    "70000000-0000-4000-8000-000000000088",
                ]
            )
        )
    )

    json_body = calls[0]["json_body"]
    assert isinstance(json_body, dict)
    turn_context = json_body["turn_context"]
    assert isinstance(turn_context, dict)
    assert turn_context == {
        "conversation_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "source_channel_message_id": "99999999-9999-9999-9999-999999999999",
        "source_external_message_id": "om_x",
        "origin_turn_id": "turn:99999999-9999-9999-9999-999999999999",
        "other_scope_conversation_id": "70000000-0000-4000-8000-000000000088",
        "result_delivery_mode": "deferred_root_result",
    }


def test_schema_returns_routines_create_ad_hoc_contract() -> None:
    result = asyncio.run(
        main_module.dispatch(argparse.Namespace(command="schema", name="routines.create-ad-hoc"))
    )

    assert result["data"]["name"] == "routines.create-ad-hoc"
    assert result["data"]["shortcut"] == "+create-ad-hoc"
    assert result["data"]["risk_level"] == "write"
    props = result["data"]["input_schema"]["properties"]
    assert "trigger_config_json" in props
    assert "other_scope_conversation_id" in props
    assert "result_delivery_mode" in props
    assert "target_channel_chat_id" not in props
    assert "target_conversation_id" not in props
    assert "target_channel_id" not in props
    assert "target_platform_chat_type" not in props
    assert "target_delivery_mode" not in props
    assert props["result_delivery_mode"]["enum"] == [
        "deferred-session-result",
        "deferred-root-result",
    ]
    assert "default" not in props["result_delivery_mode"]
    assert props["instruction"]["maxLength"] == ROUTINE_INSTRUCTION_MAX_LENGTH
    assert props["trigger_config"]["oneOf"][0]["properties"]["schema_version"]["const"] == 1
    assert "museoncli routines +create-ad-hoc" in result["data"]["examples"][0]


def test_schema_returns_routines_create_draft_contract() -> None:
    result = asyncio.run(
        main_module.dispatch(argparse.Namespace(command="schema", name="routines.create-draft"))
    )

    assert result["data"]["name"] == "routines.create-draft"
    assert result["data"]["shortcut"] == "+create-draft"
    assert result["data"]["risk_level"] == "write"
    props = result["data"]["input_schema"]["properties"]
    assert "trigger_config_json" in props
    assert "other_scope_conversation_id" in props
    assert "result_delivery_mode" in props
    assert "target_channel_chat_id" not in props
    assert "target_conversation_id" not in props
    assert "target_channel_id" not in props
    assert "target_platform_chat_type" not in props
    assert "target_delivery_mode" not in props
    assert props["instruction"]["maxLength"] == ROUTINE_INSTRUCTION_MAX_LENGTH
    assert "museoncli routines +create-draft" in result["data"]["examples"][0]


def test_schema_returns_routines_accept_draft_contract() -> None:
    result = asyncio.run(
        main_module.dispatch(argparse.Namespace(command="schema", name="routines.accept-draft"))
    )

    assert result["data"]["name"] == "routines.accept-draft"
    assert result["data"]["shortcut"] == "+accept-draft"
    assert result["data"]["risk_level"] == "write"
    assert result["data"]["input_schema"]["required"] == ["routine_id"]
    assert "museoncli routines +accept-draft" in result["data"]["examples"][0]


def test_schema_returns_routines_rebuild_ad_hoc_contract() -> None:
    result = asyncio.run(
        main_module.dispatch(argparse.Namespace(command="schema", name="routines.rebuild-ad-hoc"))
    )

    assert result["data"]["name"] == "routines.rebuild-ad-hoc"
    assert result["data"]["shortcut"] == "+rebuild-ad-hoc"
    assert result["data"]["risk_level"] == "write"
    props = result["data"]["input_schema"]["properties"]
    assert "memory_content" in props
    assert "drop_memory" in props
    assert "other_scope_conversation_id" in props
    assert "result_delivery_mode" in props
    assert "target_channel_chat_id" not in props
    assert "target_conversation_id" not in props
    assert "target_channel_id" not in props
    assert "target_platform_chat_type" not in props
    assert "target_delivery_mode" not in props
    assert "museoncli routines +rebuild-ad-hoc" in result["data"]["examples"][0]


def test_schema_does_not_expose_routines_claim_managed_contract() -> None:
    with pytest.raises(ValueError, match="Unknown command schema"):
        asyncio.run(
            main_module.dispatch(
                argparse.Namespace(command="schema", name="routines.claim-managed")
            )
        )


def test_schema_returns_routines_memory_get_contract() -> None:
    result = asyncio.run(
        main_module.dispatch(argparse.Namespace(command="schema", name="routines.memory-get"))
    )

    assert result["data"]["name"] == "routines.memory-get"
    assert result["data"]["shortcut"] == "+memory-get"
    assert result["data"]["risk_level"] == "read"
    assert result["data"]["input_schema"]["required"] == ["routine_id"]
    assert "museoncli routines +memory-get" in result["data"]["examples"][0]


@pytest.mark.parametrize(
    ("schema_name", "shortcut"),
    [
        ("routines.pause", "pause"),
        ("routines.resume", "resume"),
    ],
)
def test_schema_returns_routines_pause_resume_contract(
    schema_name: str,
    shortcut: str,
) -> None:
    result = asyncio.run(
        main_module.dispatch(argparse.Namespace(command="schema", name=schema_name))
    )

    assert result["data"]["name"] == schema_name
    assert result["data"]["shortcut"] == f"+{shortcut}"
    assert result["data"]["risk_level"] == "write"
    assert result["data"]["input_schema"]["required"] == ["routine_id"]
    assert f"museoncli routines +{shortcut}" in result["data"]["examples"][0]


def test_dispatch_routines_accept_draft_calls_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="Workspace", organization_id="org-1")
    calls: list[dict[str, object]] = []

    async def fake_api_data(
        cfg_arg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
    ) -> dict[str, object]:
        del cfg_arg
        calls.append({"method": method, "path": path, "json_body": json_body, "params": params})
        return {"routine": {"id": "routine-1", "status": "active"}, "trigger": {"id": "trigger-1"}}

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    result = asyncio.run(
        main_module.dispatch(
            parse(
                [
                    "routines",
                    "+accept-draft",
                    "--id",
                    "routine-1",
                    "--workspace-id",
                    "70000000-0000-4000-8000-000000000001",
                ]
            )
        )
    )

    assert result["command"] == "routines.accept-draft"
    assert result["data"]["routine"]["status"] == "active"
    assert calls == [
        {
            "method": "POST",
            "path": "/agent-cli/routines/routine-1/accept-draft",
            "json_body": {},
            "params": {"workspace_id": "70000000-0000-4000-8000-000000000001"},
        }
    ]


@pytest.mark.parametrize("command", ["pause", "resume"])
def test_dispatch_routines_pause_resume_calls_api(
    monkeypatch: pytest.MonkeyPatch,
    command: str,
) -> None:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="Workspace", organization_id="org-1")
    calls: list[dict[str, object]] = []

    async def fake_api_data(
        cfg_arg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
    ) -> dict[str, object]:
        del cfg_arg, json_body
        calls.append({"method": method, "path": path, "params": params})
        return {"routine": {"id": "routine-1", "status": "active"}}

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    result = asyncio.run(
        main_module.dispatch(
            parse(
                [
                    "routines",
                    f"+{command}",
                    "--id",
                    "routine-1",
                    "--workspace-id",
                    "70000000-0000-4000-8000-000000000001",
                ]
            )
        )
    )

    assert result["command"] == f"routines.{command}"
    assert result["data"]["routine"]["id"] == "routine-1"
    assert calls == [
        {
            "method": "POST",
            "path": f"/agent-cli/routines/routine-1/{command}",
            "params": {"workspace_id": "70000000-0000-4000-8000-000000000001"},
        }
    ]


def test_dispatch_generation_create_uses_generation_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="Workspace", organization_id="org-1")
    format_id = "11000000-0000-4000-8000-000000000001"
    topic_id = "22000000-0000-4000-8000-000000000001"
    persona_id = "33000000-0000-4000-8000-000000000001"
    product_id = "44000000-0000-4000-8000-000000000001"
    calls: list[dict[str, object]] = []

    async def fake_api_data(
        cfg_arg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
    ) -> dict[str, object]:
        del cfg_arg, params
        calls.append({"method": method, "path": path, "json_body": json_body})
        return {
            "tool_name": "generation_create",
            "workspace": {"id": "workspace-1", "name": "Workspace"},
            "result": {
                "ok": True,
                "tool_name": "generation_create",
                "type": "slideshow_generation",
                "operation": "create",
                "resource": {
                    "id": "generation-1",
                    "status": "pending",
                    "content_topic_snapshot": {"title": "Cold brew launch"},
                },
            },
        }

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    args = parse(
        [
            "generation",
            "+create",
            "--format-id",
            format_id,
            "--topic-id",
            topic_id,
            "--persona-id",
            persona_id,
            "--product-id",
            product_id,
            "--notes",
            "focus on proof",
        ]
    )
    result = asyncio.run(main_module.dispatch(args))

    assert result["command"] == "generation.create"
    assert result["data"]["resource"]["id"] == "generation-1"
    assert result["data"]["resource"]["ref"] == (
        "[Cold brew launch](https://www.museon.ai/generations/generation-1)"
    )
    assert result["run"] == {
        "id": "generation-1",
        "type": "slideshow_generation",
        "status": "pending",
        "watch_command": "museoncli generation +get --type slideshow --id generation-1",
        "recommended_wakeup_delay_seconds": 300,
        "ref": "[Cold brew launch](https://www.museon.ai/generations/generation-1)",
    }
    assert result["next_steps"] == [
        (
            "Include run.ref in the customer-facing final response now. Tell the customer "
            "generation is in progress and this link shows live generation progress."
        ),
        (
            "Schedule a wakeup in 300 seconds, then poll with: "
            "museoncli generation +get --type slideshow --id generation-1"
        ),
    ]
    assert calls == [
        {
            "method": "POST",
            "path": "/agent-cli/tools/generation_create/call",
            "json_body": {
                "arguments": {
                    "type": "slideshow",
                    "format_id": format_id,
                    "content_topic_id": topic_id,
                    "persona_id": persona_id,
                    "product_id": product_id,
                    "custom_prompt": "focus on proof",
                },
                "workspace_id": "workspace-1",
                "runtime_context": None,
                "wait": False,
                "wait_timeout_seconds": 0,
                "poll_interval_seconds": 2.0,
            },
        }
    ]


def test_dispatch_generation_create_dry_run_does_not_call_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="Workspace", organization_id="org-1")
    format_id = "11000000-0000-4000-8000-000000000001"
    topic_id = "22000000-0000-4000-8000-000000000001"
    persona_id = "33000000-0000-4000-8000-000000000001"

    async def fake_api_data(*args: object, **kwargs: object) -> dict[str, object]:
        raise AssertionError("dry run should not call API")

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    args = parse(
        [
            "generation",
            "+create",
            "--format-id",
            format_id,
            "--topic-id",
            topic_id,
            "--persona-id",
            persona_id,
            "--dry-run",
        ]
    )
    result = asyncio.run(main_module.dispatch(args))

    assert result["command"] == "generation.create"
    assert result["data"]["dry_run"] is True
    assert result["data"]["arguments"] == {
        "type": "slideshow",
        "format_id": format_id,
        "content_topic_id": topic_id,
        "persona_id": persona_id,
    }


def test_dispatch_generation_get_and_list_add_markdown_refs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config(site_url="https://staging.museon.ai")
    cfg.workspace = WorkspaceState(id="workspace-1", name="Workspace", organization_id="org-1")

    async def fake_api_data(
        cfg_arg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
    ) -> dict[str, object]:
        del cfg_arg, method, json_body, params
        if path.endswith("/generation_get/call"):
            return {
                "tool_name": "generation_get",
                "result": {
                    "ok": True,
                    "resource": {"id": "generation 1", "name": "Launch [A]"},
                },
            }
        return {
            "tool_name": "generation_list",
            "result": {
                "ok": True,
                "items": [
                    {"id": "generation-2", "title": "Launch B"},
                    {"generation_id": "generation-3"},
                ],
            },
        }

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    get_result = asyncio.run(main_module.dispatch(parse(["generation", "+get", "--id", "gen-1"])))
    list_result = asyncio.run(main_module.dispatch(parse(["generation", "+list"])))

    assert get_result["data"]["resource"]["ref"] == (
        "[Launch \\[A\\]](https://staging.museon.ai/generations/generation%201)"
    )
    assert list_result["data"]["items"][0]["ref"] == (
        "[Launch B](https://staging.museon.ai/generations/generation-2)"
    )
    assert list_result["data"]["items"][1]["ref"] == (
        "[generation-3](https://staging.museon.ai/generations/generation-3)"
    )


def test_api_version_base_url_derives_v2_from_v1_config() -> None:
    cfg = Config(api_base_url="https://api.example.com/api/v1")

    assert main_module.api_version_base_url(cfg, version="v2") == "https://api.example.com/api/v2"


def test_dispatch_skills_get_uses_agent_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    calls: list[dict[str, object]] = []

    async def fake_api_data(
        cfg_arg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
    ) -> dict[str, object]:
        del cfg_arg, json_body
        calls.append({"method": method, "path": path, "params": params})
        return {
            "name": "social-persona-account-analysis",
            "content": "# Social Persona Account Analysis",
            "version": "rev-1",
        }

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    args = parse(
        [
            "skills",
            "+get",
            "--name",
            "social-persona-account-analysis",
            "--offset",
            "10",
            "--limit",
            "20",
        ]
    )
    result = asyncio.run(main_module.dispatch(args))

    assert result["command"] == "skills.get"
    assert result["data"]["name"] == "social-persona-account-analysis"
    assert calls == [
        {
            "method": "GET",
            "path": "/agent-cli/skills/social-persona-account-analysis",
            "params": {"offset": 10, "limit": 20},
        }
    ]


def test_dispatch_skills_create_uses_agent_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="Workspace 1")
    calls: list[dict[str, object]] = []

    async def fake_api_data(
        cfg_arg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
    ) -> dict[str, object]:
        del cfg_arg, params
        calls.append({"method": method, "path": path, "json_body": json_body})
        return {
            "name": "social-persona-account-analysis",
            "content": "# Skill",
            "is_public": True,
        }

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    args = parse(
        [
            "skills",
            "+create",
            "--name",
            "social-persona-account-analysis",
            "--content",
            "# Skill",
            "--reference-json",
            '{"docs":["https://example.com"]}',
            "--is-public",
        ]
    )
    result = asyncio.run(main_module.dispatch(args))

    assert result["command"] == "skills.create"
    assert result["workspace"] == {"id": "workspace-1"}
    assert calls == [
        {
            "method": "POST",
            "path": "/agent-cli/skills",
            "json_body": {
                "name": "social-persona-account-analysis",
                "description": None,
                "content": "# Skill",
                "is_active": True,
                "is_public": True,
                "reference": {"docs": ["https://example.com"]},
                "workspace_id": "workspace-1",
            },
        }
    ]


def test_dispatch_skills_update_can_deactivate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    calls: list[dict[str, object]] = []

    async def fake_api_data(
        cfg_arg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
    ) -> dict[str, object]:
        del cfg_arg, params
        calls.append({"method": method, "path": path, "json_body": json_body})
        return {
            "name": "social-persona-account-analysis",
            "content": "",
            "is_active": False,
            "is_public": True,
        }

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    args = parse(
        [
            "skills",
            "+update",
            "--name",
            "social-persona-account-analysis",
            "--no-is-active",
        ]
    )
    result = asyncio.run(main_module.dispatch(args))

    assert result["command"] == "skills.update"
    assert calls == [
        {
            "method": "PATCH",
            "path": "/agent-cli/skills/social-persona-account-analysis",
            "json_body": {"is_active": False},
        }
    ]


def test_dispatch_evaluator_create_defaults_private(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="Workspace", organization_id="org-1")
    calls: list[dict[str, object]] = []

    async def fake_api_data(
        cfg_arg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
    ) -> dict[str, object]:
        del cfg_arg, params
        calls.append({"method": method, "path": path, "json_body": json_body})
        return {
            "id": "10000000-0000-4000-8000-000000000001",
            "kind": "content_generation",
            "name": "Content quality",
            "model_config": {"model": "gpt-4.1-mini"},
            "is_public": False,
        }

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    args = parse(
        [
            "evaluator",
            "+create",
            "--kind",
            "content_generation",
            "--name",
            "Content quality",
            "--prompt",
            "Score strictly.",
        ]
    )
    result = asyncio.run(main_module.dispatch(args))

    assert result["command"] == "evaluator.create"
    assert result["workspace"] == {"id": "workspace-1"}
    assert "model_config" not in result["data"]
    assert calls == [
        {
            "method": "POST",
            "path": "/agent-cli/evaluators",
            "json_body": {
                "workspace_id": "workspace-1",
                "kind": "content_generation",
                "name": "Content quality",
                "prompt": "Score strictly.",
                "is_public": False,
            },
        }
    ]


def test_evaluator_redacts_model_config_from_nested_outputs() -> None:
    payload = {
        "items": [
            {
                "id": "run-1",
                "model_config_snapshot": {"provider": "gemini", "model": "gemini-pro"},
                "result": {
                    "score": 80,
                    "nested": {"model_config": {"model": "gpt-4.1-mini"}},
                },
            }
        ]
    }

    assert evaluator_module._redact_evaluator_model_config(payload) == {
        "items": [{"id": "run-1", "result": {"score": 80, "nested": {}}}]
    }


def test_dispatch_evaluator_run_uses_agent_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="Workspace", organization_id="org-1")
    calls: list[dict[str, object]] = []

    async def fake_api_data(
        cfg_arg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
    ) -> dict[str, object]:
        del cfg_arg
        calls.append(
            {
                "method": method,
                "path": path,
                "json_body": json_body,
                "params": params,
            }
        )
        return {
            "id": "30000000-0000-4000-8000-000000000001",
            "status": "completed",
            "score": 0.82,
        }

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    args = parse(
        [
            "evaluator",
            "+run",
            "--id",
            "10000000-0000-4000-8000-000000000001",
            "--text",
            "Generated copy",
            "--media-id",
            "20000000-0000-4000-8000-000000000001",
            "--extra-context-json",
            '{"channel":"tiktok"}',
        ]
    )
    result = asyncio.run(main_module.dispatch(args))

    assert result["command"] == "evaluator.run"
    assert result["workspace"] == {"id": "workspace-1"}
    assert calls == [
        {
            "method": "POST",
            "path": "/agent-cli/evaluators/10000000-0000-4000-8000-000000000001/runs",
            "json_body": {
                "media_ids": ["20000000-0000-4000-8000-000000000001"],
                "text": "Generated copy",
                "extra_context": {"channel": "tiktok"},
            },
            "params": {"workspace_id": "workspace-1"},
        }
    ]


def test_dispatch_research_web_research_uses_agent_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="Workspace", organization_id="org-1")
    calls: list[dict[str, object]] = []

    async def fake_api_data(
        cfg_arg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
    ) -> dict[str, object]:
        del cfg_arg, params
        calls.append({"method": method, "path": path, "json_body": json_body})
        return {
            "domain": "research",
            "operation": "web-research",
            "result": {"ok": True, "evidence": {}},
        }

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    args = parse(
        [
            "research",
            "+web-research",
            "--query",
            "Museon AI",
            "--include",
            "search-results",
            "--limit",
            "3",
        ]
    )
    result = asyncio.run(main_module.dispatch(args))

    assert result["command"] == "research.web-research"
    assert result["data"] == {"ok": True, "evidence": {}}
    assert result["run"] is None
    assert calls == [
        {
            "method": "POST",
            "path": "/agent-cli/research/web-research",
            "json_body": {
                "workspace_id": "workspace-1",
                "payload": {
                    "query": "Museon AI",
                    "include": ["search_results"],
                    "limit": 3,
                    "content_chars": 800,
                    "region": "US",
                    "timeout": 45,
                    "max_retries": 3,
                },
            },
        }
    ]


def test_dispatch_research_social_media_search_uses_agent_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="Workspace", organization_id="org-1")
    calls: list[dict[str, object]] = []

    async def fake_api_data(
        cfg_arg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
    ) -> dict[str, object]:
        del cfg_arg, params
        calls.append({"method": method, "path": path, "json_body": json_body})
        return {
            "domain": "research",
            "operation": "social-media-search",
            "result": {"ok": True, "evidence": {"items": []}},
        }

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    args = parse(
        [
            "research",
            "+social-media-search",
            "--platform",
            "tiktok",
            "--intent",
            "keyword-search",
            "--query",
            "skincare routine",
            "--content-type",
            "image",
            "--limit",
            "3",
        ]
    )
    result = asyncio.run(main_module.dispatch(args))

    assert result["command"] == "research.social-media-search"
    assert result["data"] == {"ok": True, "evidence": {"items": []}}
    assert result["run"] is None
    assert calls == [
        {
            "method": "POST",
            "path": "/agent-cli/research/social-media-search",
            "json_body": {
                "workspace_id": "workspace-1",
                "payload": {
                    "platform": "tiktok",
                    "intent": "keyword_search",
                    "query": "skincare routine",
                    "limit": 3,
                    "content_chars": 800,
                    "region": "US",
                    "timeout": 10,
                    "max_retries": 3,
                    "sort": "relevance",
                    "time_window": "any",
                    "content_type": "image",
                },
            },
        }
    ]


def test_dispatch_research_community_search_uses_agent_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="Workspace", organization_id="org-1")
    calls: list[dict[str, object]] = []

    async def fake_api_data(
        cfg_arg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
    ) -> dict[str, object]:
        del cfg_arg, params
        calls.append({"method": method, "path": path, "json_body": json_body})
        return {
            "domain": "research",
            "operation": "community-search",
            "result": {"ok": True, "evidence": {"items": []}},
        }

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    args = parse(
        [
            "research",
            "+community-search",
            "--platform",
            "x",
            "--intent",
            "keyword-search",
            "--query",
            "AI video agent",
            "--limit",
            "3",
            "--cursor",
            "cursor-1",
            "--search-type",
            "post",
            "--allow-slow",
        ]
    )
    result = asyncio.run(main_module.dispatch(args))

    assert result["command"] == "research.community-search"
    assert result["data"] == {"ok": True, "evidence": {"items": []}}
    assert result["run"] is None
    assert calls == [
        {
            "method": "POST",
            "path": "/agent-cli/research/community-search",
            "json_body": {
                "workspace_id": "workspace-1",
                "payload": {
                    "platform": "x",
                    "intent": "keyword_search",
                    "query": "AI video agent",
                    "limit": 3,
                    "content_chars": 800,
                    "region": "US",
                    "timeout": 10,
                    "max_retries": 3,
                    "sort": "relevance",
                    "time_window": "any",
                    "cursor": "cursor-1",
                    "search_type": "post",
                    "allow_slow": True,
                },
            },
        }
    ]


def test_dispatch_research_visual_analyze_uses_agent_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="Workspace", organization_id="org-1")
    calls: list[dict[str, object]] = []

    async def fake_api_data(
        cfg_arg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
    ) -> dict[str, object]:
        del cfg_arg, params
        calls.append({"method": method, "path": path, "json_body": json_body})
        return {
            "domain": "research",
            "operation": "visual-analyze",
            "result": {"ok": True, "analysis": "Looks clean."},
        }

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    args = parse(
        [
            "research",
            "+visual-analyze",
            "--media-json",
            '[{"url":"https://example.com/a.png","label":"hero"}]',
            "--prompt",
            "Assess this image.",
        ]
    )
    result = asyncio.run(main_module.dispatch(args))

    assert result["command"] == "research.visual-analyze"
    assert result["data"] == {"ok": True, "analysis": "Looks clean."}
    assert calls[0]["path"] == "/agent-cli/research/visual-analyze"
    assert calls[0]["json_body"]["payload"] == {
        "media": [{"url": "https://example.com/a.png", "label": "hero"}],
        "prompt": "Assess this image.",
    }


def test_dispatch_content_analysis_run_uses_agent_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="Workspace", organization_id="org-1")
    calls: list[dict[str, object]] = []

    async def fake_api_data(
        cfg_arg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
    ) -> dict[str, object]:
        del cfg_arg, params
        calls.append({"method": method, "path": path, "json_body": json_body})
        return {
            "domain": "content-analysis",
            "operation": "run",
            "result": {
                "run_id": "11111111-1111-4111-8111-111111111111",
                "status": "completed",
                "analysis_type": "content-analysis",
                "cached": True,
            },
        }

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    args = parse(
        [
            "content-analysis",
            "+run",
            "--type",
            "content-analysis",
            "--media-id",
            "3ed10000-0000-4000-8000-000000000001",
        ]
    )
    result = asyncio.run(main_module.dispatch(args))

    assert result["command"] == "content-analysis.run"
    assert result["data"]["cached"] is True
    assert result["run"] == {
        "id": "11111111-1111-4111-8111-111111111111",
        "kind": "content_analysis",
        "type": "content-analysis",
        "status": "completed",
        "cached": True,
        "watch_command": (
            "museoncli content-analysis +get --id 11111111-1111-4111-8111-111111111111"
        ),
    }
    assert result["next_steps"] == []
    assert calls == [
        {
            "method": "POST",
            "path": "/agent-cli/content-analysis/runs",
            "json_body": {
                "workspace_id": "workspace-1",
                "payload": {
                    "type": "content-analysis",
                    "media_id": "3ed10000-0000-4000-8000-000000000001",
                    "force_reanalysis": False,
                    "wait": False,
                    "wait_timeout_seconds": 60,
                    "poll_interval_seconds": 2.0,
                },
            },
        }
    ]


def test_dispatch_content_analysis_file_uploads_media_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="Workspace", organization_id="org-1")
    upload_calls: list[dict[str, object]] = []
    api_calls: list[dict[str, object]] = []

    async def fake_upload_media_file(
        cfg_arg: Config,
        *,
        workspace_id: str,
        arguments: dict[str, object],
    ) -> dict[str, object]:
        del cfg_arg
        upload_calls.append({"workspace_id": workspace_id, "arguments": arguments})
        return {
            "success": True,
            "data": {
                "asset": {
                    "id": "3ed10000-0000-4000-8000-000000000001",
                    "type": "media",
                }
            },
        }

    async def fake_api_data(
        cfg_arg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
    ) -> dict[str, object]:
        del cfg_arg, params
        api_calls.append({"method": method, "path": path, "json_body": json_body})
        return {
            "domain": "content-analysis",
            "operation": "run",
            "result": {
                "run_id": "11111111-1111-4111-8111-111111111111",
                "status": "queued",
                "analysis_type": "reverse-ai-prompt",
                "cached": False,
            },
        }

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "upload_media_file", fake_upload_media_file)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    args = parse(
        [
            "content-analysis",
            "+run",
            "--type",
            "reverse-ai-prompt",
            "--file",
            "./creative.mp4",
            "--media-type",
            "video",
            "--title",
            "Creative",
        ]
    )
    result = asyncio.run(main_module.dispatch(args))

    assert result["run"]["status"] == "queued"
    assert result["next_steps"] == [
        "Poll with: museoncli content-analysis +get --id 11111111-1111-4111-8111-111111111111"
    ]
    assert upload_calls == [
        {
            "workspace_id": "workspace-1",
            "arguments": {"file": "./creative.mp4", "media_type": "video", "title": "Creative"},
        }
    ]
    assert api_calls[0]["json_body"] == {
        "workspace_id": "workspace-1",
        "payload": {
            "type": "reverse-ai-prompt",
            "force_reanalysis": False,
            "wait": False,
            "wait_timeout_seconds": 60,
            "poll_interval_seconds": 2.0,
            "media_id": "3ed10000-0000-4000-8000-000000000001",
        },
    }


def test_dispatch_content_analysis_get_and_list_use_agent_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="Workspace", organization_id="org-1")
    calls: list[dict[str, object]] = []

    async def fake_api_data(
        cfg_arg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
    ) -> dict[str, object]:
        del cfg_arg, json_body
        calls.append({"method": method, "path": path, "params": params})
        return {
            "domain": "content-analysis",
            "operation": "get" if path.endswith("11111111-1111-4111-8111-111111111111") else "list",
            "result": {"ok": True},
        }

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    get_args = parse(
        [
            "content-analysis",
            "+get",
            "--workspace-id",
            "workspace-override",
            "--id",
            "11111111-1111-4111-8111-111111111111",
        ]
    )
    list_args = parse(
        [
            "content-analysis",
            "+list",
            "--type",
            "content-analysis",
            "--source-type",
            "upload",
            "--page-size",
            "5",
        ]
    )

    assert asyncio.run(main_module.dispatch(get_args))["data"] == {"ok": True}
    assert asyncio.run(main_module.dispatch(list_args))["data"] == {"ok": True}
    assert calls == [
        {
            "method": "GET",
            "path": "/agent-cli/content-analysis/runs/11111111-1111-4111-8111-111111111111",
            "params": {"workspace_id": "workspace-override"},
        },
        {
            "method": "GET",
            "path": "/agent-cli/content-analysis/runs",
            "params": {
                "workspace_id": "workspace-1",
                "type": "content-analysis",
                "source_type": "upload",
                "page": 1,
                "page_size": 5,
            },
        },
    ]


def test_dispatch_social_account_list_uses_agent_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="Workspace", organization_id="org-1")
    calls: list[dict[str, object]] = []

    async def fake_api_data(
        cfg_arg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
        unwrap_success: bool = True,
    ) -> dict[str, object]:
        del cfg_arg, json_body
        calls.append(
            {
                "method": method,
                "path": path,
                "params": params,
                "unwrap_success": unwrap_success,
            }
        )
        return {
            "domain": "social-account",
            "operation": "list",
            "result": {"items": [], "total": 0, "page": 1, "page_size": 50, "has_more": False},
        }

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    args = parse(
        [
            "social-account",
            "+list",
            "--plan-status",
            "with-plan",
            "--allocation-type",
            "account-publish",
            "--search",
            "taylor",
            "--search-term",
            "@nowherepages",
            "--search-term",
            "paper",
            "--tag",
            "coohom",
            "--group-name",
            "GeeLark Team A",
            "--lookup-status",
            "found",
            "--private-only",
            "--without-device",
        ]
    )
    result = asyncio.run(main_module.dispatch(args))

    assert result["command"] == "social-account.list"
    assert result["data"]["items"] == []
    assert calls == [
        {
            "method": "GET",
            "path": "/agent-cli/social-accounts",
            "params": {
                "workspace_id": "workspace-1",
                "search": "taylor",
                "search_terms": ["@nowherepages", "paper"],
                "automation_status": "with-plan",
                "allocation_type": "account_publish",
                "tag": "coohom",
                "group_name": "GeeLark Team A",
                "lookup_status": "found",
                "is_active": True,
                "is_public": False,
                "has_device": False,
                "page": 1,
                "page_size": 100,
            },
            "unwrap_success": True,
        }
    ]


def test_dispatch_social_account_assets_set_uses_agent_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="Workspace", organization_id="org-1")
    calls: list[dict[str, object]] = []

    async def fake_api_data(
        cfg_arg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
        unwrap_success: bool = True,
    ) -> dict[str, object]:
        del cfg_arg, params, unwrap_success
        calls.append({"method": method, "path": path, "json_body": json_body})
        return {
            "domain": "social-account",
            "operation": "assets-set",
            "result": {
                "pool_account_id": "ac000000-0000-4000-8000-000000000001",
                "workspace_id": "workspace-1",
            },
        }

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    args = parse(
        [
            "social-account",
            "+assets-set",
            "--id",
            "ac000000-0000-4000-8000-000000000001",
            "--product-id",
            "9d000000-0000-4000-8000-000000000001",
            "--format-id",
            "f0000000-0000-4000-8000-000000000001",
            "--content-topic-id",
            "70000000-0000-4000-8000-000000000001",
        ]
    )
    result = asyncio.run(main_module.dispatch(args))

    assert result["command"] == "social-account.assets-set"
    assert calls == [
        {
            "method": "PUT",
            "path": "/agent-cli/social-accounts/ac000000-0000-4000-8000-000000000001/publish-assets",
            "json_body": {
                "workspace_id": "workspace-1",
                "payload": {
                    "product_id": "9d000000-0000-4000-8000-000000000001",
                    "format_ids": ["f0000000-0000-4000-8000-000000000001"],
                    "content_topic_ids": ["70000000-0000-4000-8000-000000000001"],
                },
            },
        },
    ]


def test_dispatch_social_account_assets_set_sends_managed_approval_after_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="Workspace", organization_id="org-1")
    calls: list[dict[str, object]] = []

    async def fake_api_data(
        cfg_arg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
        unwrap_success: bool = True,
    ) -> dict[str, object]:
        del cfg_arg, params, unwrap_success
        calls.append({"method": method, "path": path, "json_body": json_body})
        return {
            "domain": "social-account",
            "operation": "assets-set",
            "result": {"pool_account_id": "ac000000-0000-4000-8000-000000000001"},
        }

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    args = parse(
        [
            "social-account",
            "+assets-set",
            "--id",
            "ac000000-0000-4000-8000-000000000001",
            "--format-id",
            "f0000000-0000-4000-8000-000000000001",
            "--managed-operation-approved",
            "--approval-note",
            "User confirmed add/resume/pause impact",
        ]
    )
    asyncio.run(main_module.dispatch(args))

    assert calls[0]["json_body"] == {
        "workspace_id": "workspace-1",
        "payload": {
            "format_ids": ["f0000000-0000-4000-8000-000000000001"],
            "managed_operation_approved": True,
            "approval_note": "User confirmed add/resume/pause impact",
        },
    }


def test_dispatch_social_account_assets_set_tags_only_uses_workspace_tags_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="Workspace", organization_id="org-1")
    calls: list[dict[str, object]] = []

    async def fake_api_data(
        cfg_arg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
        unwrap_success: bool = True,
    ) -> dict[str, object]:
        del cfg_arg, params, unwrap_success
        calls.append({"method": method, "path": path, "json_body": json_body})
        return {
            "domain": "social-account",
            "operation": "workspace-tags-set",
            "result": {
                "account_id": "ac000000-0000-4000-8000-000000000001",
                "tags": ["coohom", "matrix-a"],
            },
        }

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    args = parse(
        [
            "social-account",
            "+assets-set",
            "--id",
            "ac000000-0000-4000-8000-000000000001",
            "--tag",
            "coohom",
            "--tag",
            "matrix-a",
        ]
    )
    result = asyncio.run(main_module.dispatch(args))

    assert result["command"] == "social-account.assets-set"
    assert result["data"]["tags"] == ["coohom", "matrix-a"]
    assert calls == [
        {
            "method": "PUT",
            "path": (
                "/agent-cli/social-accounts/ac000000-0000-4000-8000-000000000001/workspace-tags"
            ),
            "json_body": {"workspace_id": "workspace-1", "tags": ["coohom", "matrix-a"]},
        },
    ]


def test_dispatch_social_account_assets_set_clear_tags_sends_empty_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="Workspace", organization_id="org-1")
    calls: list[dict[str, object]] = []

    async def fake_api_data(
        cfg_arg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
        unwrap_success: bool = True,
    ) -> dict[str, object]:
        del cfg_arg, params, unwrap_success
        calls.append({"method": method, "path": path, "json_body": json_body})
        return {
            "domain": "social-account",
            "operation": "workspace-tags-set",
            "result": {"account_id": "ac000000-0000-4000-8000-000000000001", "tags": []},
        }

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    args = parse(
        [
            "social-account",
            "+assets-set",
            "--id",
            "ac000000-0000-4000-8000-000000000001",
            "--clear-tags",
        ]
    )
    result = asyncio.run(main_module.dispatch(args))

    assert result["command"] == "social-account.assets-set"
    assert calls[0]["json_body"] == {"workspace_id": "workspace-1", "tags": []}


def test_dispatch_social_account_assets_set_mixed_reports_per_section(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Allocated account: assets 409s but tags still apply — both reported."""
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="Workspace", organization_id="org-1")

    async def fake_api_data(
        cfg_arg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
        unwrap_success: bool = True,
    ) -> dict[str, object]:
        del cfg_arg, method, json_body, params, unwrap_success
        if path.endswith("/publish-assets"):
            raise RuntimeError('HTTP 409: {"detail":"Pool account is already allocated"}')
        return {
            "domain": "social-account",
            "operation": "workspace-tags-set",
            "result": {
                "account_id": "ac000000-0000-4000-8000-000000000001",
                "tags": ["coohom"],
            },
        }

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    args = parse(
        [
            "social-account",
            "+assets-set",
            "--id",
            "ac000000-0000-4000-8000-000000000001",
            "--tag",
            "coohom",
            "--persona-id",
            "9e000000-0000-4000-8000-000000000001",
        ]
    )
    result = asyncio.run(main_module.dispatch(args))

    sections = result["data"]
    assert sections["workspace_tags"]["ok"] is True
    assert sections["workspace_tags"]["data"]["tags"] == ["coohom"]
    assert sections["publish_assets"]["ok"] is False
    assert "409" in sections["publish_assets"]["error"]


def test_dispatch_social_account_version_create_uses_agent_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="Workspace", organization_id="org-1")
    calls: list[dict[str, object]] = []

    async def fake_api_data(
        cfg_arg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
        unwrap_success: bool = True,
    ) -> dict[str, object]:
        del cfg_arg, params, unwrap_success
        calls.append({"method": method, "path": path, "json_body": json_body})
        return {
            "domain": "social-account",
            "operation": "version-create",
            "result": {"id": "4e000000-0000-4000-8000-000000000001", "status": "draft"},
        }

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    args = parse(
        [
            "social-account",
            "+version-create",
            "--id",
            "ac000000-0000-4000-8000-000000000001",
            "--rules-json",
            '[{"name":"Daily"}]',
            "--change-note",
            "daily",
        ]
    )
    result = asyncio.run(main_module.dispatch(args))

    assert result["command"] == "social-account.version-create"
    assert calls == [
        {
            "method": "POST",
            "path": "/agent-cli/social-accounts/ac000000-0000-4000-8000-000000000001/publish-config/versions",
            "json_body": {
                "workspace_id": "workspace-1",
                "payload": {
                    "schedule_rules": [{"name": "Daily"}],
                    "change_note": "daily",
                },
            },
        }
    ]


def test_dispatch_social_account_schedule_delete_cancels_schedule_item(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="Workspace", organization_id="org-1")
    calls: list[dict[str, object]] = []

    async def fake_api_data(
        cfg_arg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
        unwrap_success: bool = True,
    ) -> dict[str, object]:
        del cfg_arg, params, unwrap_success
        calls.append({"method": method, "path": path, "json_body": json_body})
        return {
            "domain": "social-account",
            "operation": "schedule-delete",
            "result": {"id": "5c000000-0000-4000-8000-000000000001", "status": "cancelled"},
        }

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    args = parse(
        [
            "social-account",
            "+schedule-delete",
            "--id",
            "ac000000-0000-4000-8000-000000000001",
            "--schedule-item-id",
            "5c000000-0000-4000-8000-000000000001",
            "--reason",
            "not needed",
        ]
    )
    result = asyncio.run(main_module.dispatch(args))

    assert result["command"] == "social-account.schedule-delete"
    assert calls == [
        {
            "method": "PATCH",
            "path": "/agent-cli/social-accounts/ac000000-0000-4000-8000-000000000001/publish-config/schedule-items/5c000000-0000-4000-8000-000000000001",
            "json_body": {
                "workspace_id": "workspace-1",
                "payload": {
                    "status": "cancelled",
                    "override_reason": "not needed",
                },
            },
        }
    ]


def test_dispatch_social_account_profile_edit_draft_uses_agent_api_for_avatar(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="Workspace", organization_id="org-1")
    calls: list[dict[str, object]] = []

    async def fake_api_data(
        cfg_arg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
        unwrap_success: bool = True,
    ) -> dict[str, object]:
        del cfg_arg, params, unwrap_success
        calls.append({"method": method, "path": path, "json_body": json_body})
        return {
            "domain": "social-account",
            "operation": "profile-edit-draft",
            "result": {
                "drafts": [
                    {
                        "account_id": "ac000000-0000-4000-8000-000000000001",
                        "avatar_url": "https://cdn.example.com/avatar.png",
                    }
                ]
            },
        }

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    args = parse(
        [
            "social-account",
            "+profile-edit-draft",
            "--id",
            "ac000000-0000-4000-8000-000000000001",
            "--target",
            "avatar",
            "--prompt",
            "friendly late-night chef portrait",
        ]
    )
    result = asyncio.run(main_module.dispatch(args))

    assert result["command"] == "social-account.profile-edit-draft"
    assert result["data"]["drafts"][0]["avatar_url"] == "https://cdn.example.com/avatar.png"
    assert calls == [
        {
            "method": "POST",
            "path": "/agent-cli/social-accounts/ac000000-0000-4000-8000-000000000001/profile-edit/drafts",
            "json_body": {
                "workspace_id": "workspace-1",
                "payload": {
                    "prompt": "friendly late-night chef portrait",
                    "targets": ["avatar"],
                },
            },
        }
    ]


def test_dispatch_social_account_profile_edit_submit_uses_agent_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="Workspace", organization_id="org-1")
    calls: list[dict[str, object]] = []

    async def fake_api_data(
        cfg_arg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
        unwrap_success: bool = True,
    ) -> dict[str, object]:
        del cfg_arg, params, unwrap_success
        calls.append({"method": method, "path": path, "json_body": json_body})
        return {
            "domain": "social-account",
            "operation": "profile-edit-submit",
            "result": {
                "task_id": "73000000-0000-4000-8000-000000000001",
                "status": "pending",
            },
        }

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    args = parse(
        [
            "social-account",
            "+profile-edit-submit",
            "--id",
            "ac000000-0000-4000-8000-000000000001",
            "--nick-name",
            "Notta AI",
            "--bio",
            "Meeting notes and translated summaries.",
        ]
    )
    result = asyncio.run(main_module.dispatch(args))

    assert result["command"] == "social-account.profile-edit-submit"
    assert result["run"] == {
        "id": "73000000-0000-4000-8000-000000000001",
        "type": "pool_account_profile_edit",
        "status": "pending",
        "watch_command": (
            "museoncli social-account +profile-edit-status "
            "--id 73000000-0000-4000-8000-000000000001"
        ),
    }
    assert calls == [
        {
            "method": "POST",
            "path": "/agent-cli/social-accounts/ac000000-0000-4000-8000-000000000001/profile-edit/tasks",
            "json_body": {
                "workspace_id": "workspace-1",
                "payload": {
                    "nick_name": "Notta AI",
                    "bio": "Meeting notes and translated summaries.",
                },
            },
        }
    ]


def test_dispatch_social_account_profile_edit_submit_waits_for_geelark_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="Workspace", organization_id="org-1")
    calls: list[dict[str, object]] = []

    async def fake_api_data(
        cfg_arg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
        unwrap_success: bool = True,
    ) -> dict[str, object]:
        del cfg_arg, params, unwrap_success
        calls.append({"method": method, "path": path, "json_body": json_body})
        if path.endswith("/profile-edit/tasks"):
            return {
                "domain": "social-account",
                "operation": "profile-edit-submit",
                "result": {
                    "task_id": "73000000-0000-4000-8000-000000000001",
                    "status": "pending",
                },
            }
        return {
            "domain": "social-account",
            "operation": "profile-edit-status",
            "result": {
                "summary": {
                    "total": 1,
                    "completed": 1,
                    "failed": 0,
                    "pending": 0,
                    "settled": True,
                },
                "accounts": [{"status": "completed"}],
            },
        }

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    args = parse(
        [
            "social-account",
            "+profile-edit-submit",
            "--id",
            "ac000000-0000-4000-8000-000000000001",
            "--bio",
            "Meeting notes and translated summaries.",
            "--wait",
            "--timeout",
            "1",
            "--poll-interval",
            "0.25",
        ]
    )
    result = asyncio.run(main_module.dispatch(args))

    assert result["data"]["delivery_status"]["summary"]["settled"] is True
    assert calls == [
        {
            "method": "POST",
            "path": "/agent-cli/social-accounts/ac000000-0000-4000-8000-000000000001/profile-edit/tasks",
            "json_body": {
                "workspace_id": "workspace-1",
                "payload": {"bio": "Meeting notes and translated summaries."},
            },
        },
        {
            "method": "GET",
            "path": (
                "/agent-cli/social-accounts/profile-edit/tasks/73000000-0000-4000-8000-000000000001"
            ),
            "json_body": None,
        },
    ]


def test_social_account_avatar_generate_batch_parser() -> None:
    args = parse(
        [
            "social-account",
            "+avatar-generate-batch",
            "--id",
            "ac000000-0000-4000-8000-000000000001",
            "--id",
            "ac000000-0000-4000-8000-000000000002",
            "--prompt",
            "friendly late-night chef portrait",
        ]
    )

    assert args.command == "social-account"
    assert args.shortcut == "+avatar-generate-batch"
    assert args.domain_command == "social-account.avatar-generate-batch"
    payload = main_module.command_payload(args)
    assert payload["account_ids"] == [
        "ac000000-0000-4000-8000-000000000001",
        "ac000000-0000-4000-8000-000000000002",
    ]
    assert payload["prompt"] == "friendly late-night chef portrait"
    assert payload["wait"] is False
    assert payload["wait_timeout_seconds"] == 300.0
    assert payload["poll_interval_seconds"] == 5.0


def test_social_account_avatar_generate_status_parser() -> None:
    args = parse(
        [
            "social-account",
            "+avatar-generate-status",
            "--id",
            "73000000-0000-4000-8000-000000000001",
        ]
    )

    assert args.domain_command == "social-account.avatar-generate-status"
    assert main_module.command_payload(args) == {
        "task_id": "73000000-0000-4000-8000-000000000001"
    }


def test_dispatch_social_account_avatar_generate_batch_uses_agent_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="Workspace", organization_id="org-1")
    calls: list[dict[str, object]] = []

    async def fake_api_data(
        cfg_arg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
        unwrap_success: bool = True,
    ) -> dict[str, object]:
        del cfg_arg, params, unwrap_success
        calls.append({"method": method, "path": path, "json_body": json_body})
        return {
            "domain": "social-account",
            "operation": "avatar-generate-batch",
            "result": {
                "task_id": "73000000-0000-4000-8000-000000000001",
                "status": "pending",
            },
        }

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    args = parse(
        [
            "social-account",
            "+avatar-generate-batch",
            "--id",
            "ac000000-0000-4000-8000-000000000001",
            "--prompt",
            "friendly chef",
        ]
    )
    result = asyncio.run(main_module.dispatch(args))

    assert result["command"] == "social-account.avatar-generate-batch"
    # watch_command must use --id (the flag +avatar-generate-status accepts); the
    # routine-wakeup path copies it verbatim.
    assert result["run"] == {
        "id": "73000000-0000-4000-8000-000000000001",
        "type": "pool_account_avatar_generation",
        "status": "pending",
        "watch_command": (
            "museoncli social-account +avatar-generate-status "
            "--id 73000000-0000-4000-8000-000000000001"
        ),
    }
    assert calls == [
        {
            "method": "POST",
            "path": "/agent-cli/social-accounts/profile-edit/avatar-drafts",
            "json_body": {
                "workspace_id": "workspace-1",
                "payload": {
                    "account_ids": ["ac000000-0000-4000-8000-000000000001"],
                    "prompt": "friendly chef",
                },
            },
        }
    ]


def test_dispatch_social_account_avatar_generate_batch_waits_for_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="Workspace", organization_id="org-1")
    calls: list[dict[str, object]] = []

    async def fake_api_data(
        cfg_arg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
        unwrap_success: bool = True,
    ) -> dict[str, object]:
        del cfg_arg, params, unwrap_success
        calls.append({"method": method, "path": path})
        if method == "POST":
            return {
                "domain": "social-account",
                "operation": "avatar-generate-batch",
                "result": {
                    "task_id": "73000000-0000-4000-8000-000000000001",
                    "status": "pending",
                },
            }
        return {
            "domain": "social-account",
            "operation": "avatar-generate-status",
            "result": {
                "summary": {"total": 1, "succeeded": 1, "failed": 0, "settled": True},
                "accounts": [
                    {"account_id": "ac000000-0000-4000-8000-000000000001", "status": "completed"}
                ],
            },
        }

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    args = parse(
        [
            "social-account",
            "+avatar-generate-batch",
            "--id",
            "ac000000-0000-4000-8000-000000000001",
            "--prompt",
            "friendly chef",
            "--wait",
            "--timeout",
            "1",
            "--poll-interval",
            "0.25",
        ]
    )
    result = asyncio.run(main_module.dispatch(args))

    # without_provider_metadata renames provider_status -> delivery_status in the envelope.
    assert result["data"]["delivery_status"]["summary"]["settled"] is True
    assert calls == [
        {"method": "POST", "path": "/agent-cli/social-accounts/profile-edit/avatar-drafts"},
        {
            "method": "GET",
            "path": (
                "/agent-cli/social-accounts/profile-edit/avatar-drafts/"
                "73000000-0000-4000-8000-000000000001"
            ),
        },
    ]


def test_dispatch_social_account_avatar_generate_status_uses_agent_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="Workspace", organization_id="org-1")
    calls: list[dict[str, object]] = []

    async def fake_api_data(
        cfg_arg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
        unwrap_success: bool = True,
    ) -> dict[str, object]:
        del cfg_arg, json_body, params, unwrap_success
        calls.append({"method": method, "path": path})
        return {
            "domain": "social-account",
            "operation": "avatar-generate-status",
            "result": {
                "summary": {"total": 1, "succeeded": 1, "failed": 0, "settled": True},
                "accounts": [],
            },
        }

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    args = parse(
        [
            "social-account",
            "+avatar-generate-status",
            "--id",
            "73000000-0000-4000-8000-000000000001",
        ]
    )
    result = asyncio.run(main_module.dispatch(args))

    assert result["command"] == "social-account.avatar-generate-status"
    assert result["run"] is None
    assert calls == [
        {
            "method": "GET",
            "path": (
                "/agent-cli/social-accounts/profile-edit/avatar-drafts/"
                "73000000-0000-4000-8000-000000000001"
            ),
        }
    ]


def test_dispatch_social_account_profile_edit_status_uses_agent_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="Workspace", organization_id="org-1")
    calls: list[dict[str, object]] = []

    async def fake_api_data(
        cfg_arg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
        unwrap_success: bool = True,
    ) -> dict[str, object]:
        del cfg_arg, json_body, params, unwrap_success
        calls.append({"method": method, "path": path})
        return {
            "domain": "social-account",
            "operation": "profile-edit-status",
            "result": {"summary": {"settled": True}},
        }

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    args = parse(
        [
            "social-account",
            "+profile-edit-status",
            "--id",
            "73000000-0000-4000-8000-000000000001",
        ]
    )
    result = asyncio.run(main_module.dispatch(args))

    assert result["command"] == "social-account.profile-edit-status"
    assert result["data"]["summary"]["settled"] is True
    assert calls == [
        {
            "method": "GET",
            "path": (
                "/agent-cli/social-accounts/profile-edit/tasks/73000000-0000-4000-8000-000000000001"
            ),
        }
    ]


def test_dispatch_social_account_schedule_generate_uses_agent_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="Workspace", organization_id="org-1")
    calls: list[dict[str, object]] = []

    async def fake_api_data(
        cfg_arg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
        unwrap_success: bool = True,
    ) -> dict[str, object]:
        del cfg_arg, params, unwrap_success
        calls.append({"method": method, "path": path, "json_body": json_body})
        return {
            "domain": "social-account",
            "operation": "schedule-generate",
            "result": {
                "id": "generation-1",
                "schedule_item_id": "5c000000-0000-4000-8000-000000000001",
            },
        }

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    args = parse(
        [
            "social-account",
            "+schedule-generate",
            "--id",
            "ac000000-0000-4000-8000-000000000001",
            "--schedule-item-id",
            "5c000000-0000-4000-8000-000000000001",
            "--notes",
            "focus on UGC angle",
        ]
    )
    result = asyncio.run(main_module.dispatch(args))

    assert result["command"] == "social-account.schedule-generate"
    assert result["run"] == {
        "id": "generation-1",
        "type": "slideshow_generation",
        "status": None,
        "watch_command": "museoncli generation +get --type slideshow --id generation-1",
        "recommended_wakeup_delay_seconds": 300,
        "ref": "[generation-1](https://www.museon.ai/generations/generation-1)",
    }
    assert result["next_steps"] == [
        (
            "Include run.ref in the customer-facing final response now. Tell the customer "
            "generation is in progress and this link shows live generation progress."
        ),
        (
            "Schedule a wakeup in 300 seconds, then poll with: "
            "museoncli generation +get --type slideshow --id generation-1"
        ),
    ]
    assert calls == [
        {
            "method": "POST",
            "path": "/agent-cli/social-accounts/ac000000-0000-4000-8000-000000000001/publish-config/schedule-items/5c000000-0000-4000-8000-000000000001/generate",
            "json_body": {
                "workspace_id": "workspace-1",
                "payload": {
                    "custom_prompt": "focus on UGC angle",
                },
            },
        }
    ]


def test_dispatch_campaign_monitor_post_resolve_uses_agent_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="Workspace", organization_id="org-1")
    calls: list[dict[str, object]] = []

    async def fake_api_data(
        cfg_arg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
        unwrap_success: bool = True,
    ) -> dict[str, object]:
        del cfg_arg, json_body, unwrap_success
        calls.append({"method": method, "path": path, "params": params})
        return {
            "domain": "campaign-monitor",
            "operation": "post-resolve",
            "result": {"resolved": {"content_id": "c0000000-0000-4000-8000-000000000001"}},
        }

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    args = parse(
        [
            "campaign-monitor",
            "+post-resolve",
            "--schedule-item-id",
            "5c000000-0000-4000-8000-000000000001",
        ]
    )
    result = asyncio.run(main_module.dispatch(args))

    assert result["command"] == "campaign-monitor.post-resolve"
    assert result["data"]["resolved"]["content_id"] == "c0000000-0000-4000-8000-000000000001"
    assert calls == [
        {
            "method": "GET",
            "path": "/agent-cli/social-media/posts/resolve",
            "params": {
                "workspace_id": "workspace-1",
                "schedule_item_id": "5c000000-0000-4000-8000-000000000001",
            },
        }
    ]


def test_dispatch_campaign_monitor_post_performance_uses_agent_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="Workspace", organization_id="org-1")
    calls: list[dict[str, object]] = []

    async def fake_api_data(
        cfg_arg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
        unwrap_success: bool = True,
    ) -> dict[str, object]:
        del cfg_arg, json_body, unwrap_success
        calls.append({"method": method, "path": path, "params": params})
        return {
            "domain": "campaign-monitor",
            "operation": "post-performance-get",
            "result": {"content_id": "c0000000-0000-4000-8000-000000000001", "items": []},
        }

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    args = parse(
        [
            "campaign-monitor",
            "+post-performance-get",
            "--id",
            "c0000000-0000-4000-8000-000000000001",
            "--date-from",
            "2026-06-01",
            "--limit",
            "10",
        ]
    )
    result = asyncio.run(main_module.dispatch(args))

    assert result["command"] == "campaign-monitor.post-performance-get"
    assert result["data"]["content_id"] == "c0000000-0000-4000-8000-000000000001"
    assert result["warnings"] == [
        (
            "This command reads Museon's synced monitor store only; use "
            "campaign-monitor +content-list/+creator-list/+summary for "
            "campaign-scoped collections and research +social-media-search "
            "for external discovery."
        )
    ]
    assert calls == [
        {
            "method": "GET",
            "path": "/agent-cli/social-media/posts/c0000000-0000-4000-8000-000000000001/performance",
            "params": {
                "workspace_id": "workspace-1",
                "date_from": "2026-06-01",
                "limit": 10,
            },
        }
    ]


def test_dispatch_asset_list_product_uses_agent_assets_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="Workspace", organization_id="org-1")
    calls: list[dict[str, object]] = []

    async def fake_api_data(
        cfg_arg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
        unwrap_success: bool = True,
    ) -> dict[str, object]:
        del cfg_arg, json_body
        calls.append(
            {"method": method, "path": path, "params": params, "unwrap_success": unwrap_success}
        )
        return {
            "type": "product",
            "items": [],
            "pagination": {"total": 0, "page": 1, "page_size": 20, "total_pages": 1},
        }

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    args = parse(["asset", "+list", "--type", "product", "--search", "Museon"])
    result = asyncio.run(main_module.dispatch(args))

    assert result["command"] == "asset.list"
    assert result["data"]["items"] == []
    assert calls == [
        {
            "method": "GET",
            "path": "/agent-cli/assets",
            "params": {
                "type": "product",
                "workspace_id": "workspace-1",
                "search": "Museon",
                "page": 1,
                "page_size": 20,
            },
            "unwrap_success": True,
        }
    ]


def test_dispatch_asset_list_repeated_search_terms_use_one_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="Workspace", organization_id="org-1")
    calls: list[dict[str, object]] = []

    async def fake_api_data(
        cfg_arg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
        unwrap_success: bool = True,
    ) -> dict[str, object]:
        del cfg_arg, json_body, unwrap_success
        calls.append({"method": method, "path": path, "params": params})
        return {
            "type": "topic",
            "items": [],
            "pagination": {"total": 0, "page": 1, "page_size": 20, "total_pages": 1},
        }

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    args = parse(
        [
            "asset",
            "+list",
            "--type",
            "topic",
            "--search-term",
            "scenic",
            "--search-term",
            "nature",
        ]
    )
    asyncio.run(main_module.dispatch(args))

    assert calls[0]["params"] == {
        "type": "topic",
        "workspace_id": "workspace-1",
        "search_terms": ["scenic", "nature"],
        "page": 1,
        "page_size": 20,
    }


def test_dispatch_asset_list_format_uses_agent_assets_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="Workspace", organization_id="org-1")
    calls: list[dict[str, object]] = []

    async def fake_api_data(
        cfg_arg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
        unwrap_success: bool = True,
    ) -> dict[str, object]:
        del cfg_arg, method, json_body
        calls.append({"path": path, "params": params, "unwrap_success": unwrap_success})
        return {
            "type": "format",
            "items": [{"id": "f0000000-0000-4000-8000-000000000001"}],
            "pagination": {"page": 1, "page_size": 20, "has_more": False},
        }

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    args = parse(["asset", "+list", "--type", "format", "--scope", "public", "--search", "grid"])
    result = asyncio.run(main_module.dispatch(args))

    assert result["command"] == "asset.list"
    assert result["data"]["items"] == [
        {
            "id": "f0000000-0000-4000-8000-000000000001",
            "ref": (
                "[f0000000-0000-4000-8000-000000000001]"
                "(https://www.museon.ai/assets/formats/f0000000-0000-4000-8000-000000000001)"
            ),
        }
    ]
    assert calls == [
        {
            "path": "/agent-cli/assets",
            "params": {
                "type": "format",
                "workspace_id": "workspace-1",
                "scope": "public",
                "search": "grid",
                "page": 1,
                "page_size": 20,
            },
            "unwrap_success": True,
        }
    ]


def test_dispatch_asset_list_topic_uses_agent_assets_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="Workspace", organization_id="org-1")
    calls: list[dict[str, object]] = []

    async def fake_api_data(
        cfg_arg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
        unwrap_success: bool = True,
    ) -> dict[str, object]:
        del cfg_arg, json_body
        calls.append(
            {
                "method": method,
                "path": path,
                "params": params,
                "unwrap_success": unwrap_success,
            }
        )
        return {
            "type": "topic",
            "items": [{"id": "70000000-0000-4000-8000-000000000001"}],
            "pagination": {"page": 2, "page_size": 10, "total": 1},
        }

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    args = parse(
        [
            "asset",
            "+list",
            "--type",
            "topic",
            "--page",
            "2",
            "--page-size",
            "10",
            "--search",
            "routine",
            "--status",
            "active",
        ]
    )
    result = asyncio.run(main_module.dispatch(args))

    assert result["command"] == "asset.list"
    assert result["data"]["items"] == [
        {
            "id": "70000000-0000-4000-8000-000000000001",
            "ref": (
                "[70000000-0000-4000-8000-000000000001]"
                "(https://www.museon.ai/assets/topics/70000000-0000-4000-8000-000000000001)"
            ),
        }
    ]
    assert calls == [
        {
            "method": "GET",
            "path": "/agent-cli/assets",
            "params": {
                "type": "topic",
                "workspace_id": "workspace-1",
                "search": "routine",
                "status": "active",
                "page": 2,
                "page_size": 10,
            },
            "unwrap_success": True,
        }
    ]


def test_dispatch_asset_create_product_uses_agent_assets_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="Workspace", organization_id="org-1")
    calls: list[dict[str, object]] = []

    async def fake_api_data(
        cfg_arg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
        unwrap_success: bool = True,
    ) -> dict[str, object]:
        del cfg_arg, params
        calls.append(
            {
                "method": method,
                "path": path,
                "json_body": json_body,
                "unwrap_success": unwrap_success,
            }
        )
        return {
            "operation": "create",
            "type": "product",
            "asset": {"id": "9d000000-0000-4000-8000-000000000001", "name": "MuseOn"},
        }

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    args = parse(
        [
            "asset",
            "+create",
            "--type",
            "product",
            "--name",
            "MuseOn",
            "--category",
            "PRODUCTIVITY_TOOLS",
            "--description",
            "AI content ops.",
            "--brand-logo-media-id",
            "media-logo",
        ]
    )
    result = asyncio.run(main_module.dispatch(args))

    assert result["command"] == "asset.create"
    assert result["data"]["asset"]["id"] == "9d000000-0000-4000-8000-000000000001"
    assert result["data"]["asset"]["ref"] == (
        "[MuseOn](https://www.museon.ai/assets/products/9d000000-0000-4000-8000-000000000001)"
    )
    assert calls == [
        {
            "method": "POST",
            "path": "/agent-cli/assets",
            "json_body": {
                "type": "product",
                "workspace_id": "workspace-1",
                "payload": {
                    "name": "MuseOn",
                    "category": "PRODUCTIVITY_TOOLS",
                    "description": "AI content ops.",
                    "assets": [{"media_id": "media-logo", "asset_type": "brand_logo"}],
                },
            },
            "unwrap_success": True,
        }
    ]


def test_dispatch_asset_options_uses_agent_assets_options_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="Workspace", organization_id="org-1")
    calls: list[dict[str, object]] = []

    async def fake_api_data(
        cfg_arg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
        unwrap_success: bool = True,
    ) -> dict[str, object]:
        del cfg_arg, json_body
        calls.append(
            {
                "method": method,
                "path": path,
                "params": params,
                "unwrap_success": unwrap_success,
            }
        )
        return {
            "type": "product",
            "field": "category",
            "query": "edtech",
            "items": [
                {
                    "value": "LEARNING_PLATFORMS",
                    "label": "Learning Platforms",
                    "group": "Education & Learning",
                    "description": "Learning platform products.",
                }
            ],
        }

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    result = asyncio.run(
        main_module.dispatch(
            parse(
                [
                    "asset",
                    "+options",
                    "--type",
                    "product",
                    "--field",
                    "category",
                    "--query",
                    "edtech",
                ]
            )
        )
    )

    assert result["command"] == "asset.options"
    assert result["data"]["items"][0]["value"] == "LEARNING_PLATFORMS"
    assert calls == [
        {
            "method": "GET",
            "path": "/agent-cli/assets/options",
            "params": {
                "type": "product",
                "field": "category",
                "query": "edtech",
            },
            "unwrap_success": True,
        }
    ]


def test_dispatch_asset_create_bgm_uses_agent_assets_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="Workspace", organization_id="org-1")
    calls: list[dict[str, object]] = []

    async def fake_api_data(
        cfg_arg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
        unwrap_success: bool = True,
    ) -> dict[str, object]:
        del cfg_arg, params
        calls.append(
            {
                "method": method,
                "path": path,
                "json_body": json_body,
                "unwrap_success": unwrap_success,
            }
        )
        return {
            "operation": "create",
            "type": "bgm",
            "asset": {"id": "b0000000-0000-4000-8000-000000000001", "title": "Lofi ref"},
        }

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    args = parse(
        [
            "asset",
            "+create",
            "--type",
            "bgm",
            "--url",
            "https://www.tiktok.com/@a/video/123",
            "--title",
            "Lofi ref",
            "--description",
            "Soft morning loop",
            "--tag",
            "lofi",
            "--tag",
            "morning",
        ]
    )
    result = asyncio.run(main_module.dispatch(args))

    assert result["command"] == "asset.create"
    assert result["data"]["asset"]["id"] == "b0000000-0000-4000-8000-000000000001"
    assert calls == [
        {
            "method": "POST",
            "path": "/agent-cli/assets",
            "json_body": {
                "type": "bgm",
                "workspace_id": "workspace-1",
                "payload": {
                    "url": "https://www.tiktok.com/@a/video/123",
                    "title": "Lofi ref",
                    "description": "Soft morning loop",
                    "tags": ["lofi", "morning"],
                },
            },
            "unwrap_success": True,
        }
    ]


def test_dispatch_asset_create_tag_uses_agent_assets_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="Workspace", organization_id="org-1")
    calls: list[dict[str, object]] = []

    async def fake_api_data(
        cfg_arg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
        unwrap_success: bool = True,
    ) -> dict[str, object]:
        del cfg_arg, params
        calls.append(
            {
                "method": method,
                "path": path,
                "json_body": json_body,
                "unwrap_success": unwrap_success,
            }
        )
        return {
            "operation": "create",
            "type": "tag",
            "asset": {"id": "a0000000-0000-4000-8000-000000000001", "name": "lofi"},
        }

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    args = parse(
        [
            "asset",
            "+create",
            "--type",
            "tag",
            "--name",
            "lofi",
            "--description",
            "Calm BGM and topic tag.",
        ]
    )
    result = asyncio.run(main_module.dispatch(args))

    assert result["command"] == "asset.create"
    assert result["data"]["asset"]["id"] == "a0000000-0000-4000-8000-000000000001"
    assert calls == [
        {
            "method": "POST",
            "path": "/agent-cli/assets",
            "json_body": {
                "type": "tag",
                "workspace_id": "workspace-1",
                "payload": {
                    "name": "lofi",
                    "description": "Calm BGM and topic tag.",
                },
            },
            "unwrap_success": True,
        }
    ]


def test_dispatch_asset_update_persona_uses_agent_assets_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="Workspace", organization_id="org-1")
    calls: list[dict[str, object]] = []

    async def fake_api_data(
        cfg_arg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
        unwrap_success: bool = True,
    ) -> dict[str, object]:
        del cfg_arg, params
        calls.append(
            {
                "method": method,
                "path": path,
                "json_body": json_body,
                "unwrap_success": unwrap_success,
            }
        )
        return {
            "operation": "update",
            "type": "persona",
            "asset": {
                "id": "9e000000-0000-4000-8000-000000000001",
                "name": "Taylor",
                "tags": ["fitness"],
            },
        }

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    args = parse(
        [
            "asset",
            "+update",
            "--type",
            "persona",
            "--id",
            "9e000000-0000-4000-8000-000000000001",
            "--name",
            "Taylor",
            "--tag",
            "fitness",
            "--media-id",
            "media-look",
        ]
    )
    result = asyncio.run(main_module.dispatch(args))

    assert result["command"] == "asset.update"
    assert result["data"]["asset"]["id"] == "9e000000-0000-4000-8000-000000000001"
    assert result["data"]["asset"]["ref"] == (
        "[Taylor](https://www.museon.ai/assets/personas/9e000000-0000-4000-8000-000000000001)"
    )
    assert calls == [
        {
            "method": "PATCH",
            "path": "/agent-cli/assets/persona/9e000000-0000-4000-8000-000000000001",
            "json_body": {
                "type": "persona",
                "workspace_id": "workspace-1",
                "payload": {
                    "name": "Taylor",
                    "tags": ["fitness"],
                    "assets": [{"media_id": "media-look", "asset_type": "look_reference"}],
                },
            },
            "unwrap_success": True,
        }
    ]


def test_dispatch_asset_update_tag_uses_agent_assets_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="Workspace", organization_id="org-1")
    calls: list[dict[str, object]] = []

    async def fake_api_data(
        cfg_arg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
        unwrap_success: bool = True,
    ) -> dict[str, object]:
        del cfg_arg, params
        calls.append(
            {
                "method": method,
                "path": path,
                "json_body": json_body,
                "unwrap_success": unwrap_success,
            }
        )
        return {
            "operation": "update",
            "type": "tag",
            "asset": {
                "id": "a0000000-0000-4000-8000-000000000001",
                "name": "quiet-morning",
                "status": "archived",
            },
        }

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    args = parse(
        [
            "asset",
            "+update",
            "--type",
            "tag",
            "--id",
            "a0000000-0000-4000-8000-000000000001",
            "--name",
            "quiet-morning",
            "--status",
            "archived",
        ]
    )
    result = asyncio.run(main_module.dispatch(args))

    assert result["command"] == "asset.update"
    assert result["data"]["asset"]["status"] == "archived"
    assert calls == [
        {
            "method": "PATCH",
            "path": "/agent-cli/assets/tag/a0000000-0000-4000-8000-000000000001",
            "json_body": {
                "type": "tag",
                "workspace_id": "workspace-1",
                "payload": {
                    "name": "quiet-morning",
                    "status": "archived",
                },
            },
            "unwrap_success": True,
        }
    ]


def test_dispatch_asset_persona_rejects_unsupported_agent_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="Workspace", organization_id="org-1")

    async def fake_api_data(*args: object, **kwargs: object) -> dict[str, object]:
        raise AssertionError("unsupported payload should not call API")

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    args = parse(
        [
            "asset",
            "+create",
            "--type",
            "persona",
            "--payload-json",
            '{"name":"Taylor","platform":"tiktok"}',
        ]
    )

    with pytest.raises(RuntimeError, match="unsupported fields: platform"):
        asyncio.run(main_module.dispatch(args))


def test_dispatch_asset_persona_dry_run_rejects_unsupported_agent_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="Workspace", organization_id="org-1")

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)

    args = parse(
        [
            "asset",
            "+create",
            "--type",
            "persona",
            "--payload-json",
            '{"name":"Taylor","platform":"tiktok"}',
            "--dry-run",
        ]
    )

    with pytest.raises(RuntimeError, match="unsupported fields: platform"):
        asyncio.run(main_module.dispatch(args))


def test_dispatch_asset_product_dry_run_allows_missing_assets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="Workspace", organization_id="org-1")
    calls: list[dict[str, object]] = []

    async def fake_api_data(
        cfg_arg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
        unwrap_success: bool = True,
    ) -> dict[str, object]:
        del cfg_arg, params
        calls.append(
            {
                "method": method,
                "path": path,
                "json_body": json_body,
                "unwrap_success": unwrap_success,
            }
        )
        return {
            "operation": "validate",
            "type": "product",
            "dry_run": True,
            "valid": True,
            "normalized_payload": {
                "name": "MuseOn",
                "category": "PRODUCTIVITY_TOOLS",
                "description": "AI content ops.",
                "assets": [],
                "tags": [],
            },
        }

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    args = parse(
        [
            "asset",
            "+create",
            "--type",
            "product",
            "--name",
            "MuseOn",
            "--category",
            "PRODUCTIVITY_TOOLS",
            "--description",
            "AI content ops.",
            "--dry-run",
        ]
    )

    result = asyncio.run(main_module.dispatch(args))

    assert result["command"] == "asset.create"
    assert result["data"]["dry_run"] is True
    assert result["data"]["valid"] is True
    assert calls == [
        {
            "method": "POST",
            "path": "/agent-cli/assets:validate",
            "json_body": {
                "type": "product",
                "workspace_id": "workspace-1",
                "payload": {
                    "name": "MuseOn",
                    "category": "PRODUCTIVITY_TOOLS",
                    "description": "AI content ops.",
                },
            },
            "unwrap_success": True,
        },
    ]


def test_dispatch_asset_create_dry_run_does_not_call_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="Workspace", organization_id="org-1")

    async def fake_api_data(*args: object, **kwargs: object) -> dict[str, object]:
        raise AssertionError("dry-run should not call API")

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    args = parse(
        [
            "asset",
            "+create",
            "--type",
            "topic",
            "--title",
            "Morning routine",
            "--narrative",
            "A compact routine story.",
            "--keyword",
            "routine",
            "--dry-run",
        ]
    )
    result = asyncio.run(main_module.dispatch(args))

    assert result["command"] == "asset.create"
    assert result["data"]["dry_run"] is True
    assert result["data"]["arguments"] == {
        "type": "content_topic",
        "payload": {
            "topics": [
                {
                    "title": "Morning routine",
                    "narrative": "A compact routine story.",
                    "keywords": ["routine"],
                }
            ]
        },
    }


def test_dispatch_asset_create_topic_with_direction_dry_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="Workspace", organization_id="org-1")

    async def fake_api_data(*args: object, **kwargs: object) -> dict[str, object]:
        raise AssertionError("dry-run should not call API")

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    args = parse(
        [
            "asset",
            "+create",
            "--type",
            "topic",
            "--title",
            "Burger",
            "--narrative",
            "Fast burger recipe.",
            "--topic-direction-id",
            "direction-1",
            "--dry-run",
        ]
    )
    result = asyncio.run(main_module.dispatch(args))

    assert result["data"]["arguments"] == {
        "type": "content_topic",
        "payload": {
            "topics": [
                {
                    "title": "Burger",
                    "narrative": "Fast burger recipe.",
                    "topic_direction_id": "direction-1",
                }
            ]
        },
    }


def test_dispatch_asset_create_topic_direction_dry_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="Workspace", organization_id="org-1")

    async def fake_api_data(*args: object, **kwargs: object) -> dict[str, object]:
        raise AssertionError("dry-run should not call API")

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    args = parse(
        [
            "asset",
            "+create",
            "--type",
            "topic-direction",
            "--title",
            "Recipe",
            "--description",
            "Everyday recipe direction.",
            "--tag",
            "food",
            "--dry-run",
        ]
    )
    result = asyncio.run(main_module.dispatch(args))

    assert result["data"]["arguments"] == {
        "type": "content_topic_direction",
        "payload": {
            "title": "Recipe",
            "description": "Everyday recipe direction.",
            "tags": ["food"],
        },
    }


def test_dispatch_asset_get_topic_uses_agent_assets_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="Workspace", organization_id="org-1")
    calls: list[dict[str, object]] = []

    async def fake_api_data(
        cfg_arg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
        unwrap_success: bool = True,
    ) -> dict[str, object]:
        del cfg_arg, json_body
        calls.append(
            {
                "method": method,
                "path": path,
                "params": params,
                "unwrap_success": unwrap_success,
            }
        )
        return {"id": "70000000-0000-4000-8000-000000000001", "title": "Morning routine"}

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    args = parse(
        ["asset", "+get", "--type", "topic", "--id", "70000000-0000-4000-8000-000000000001"]
    )
    result = asyncio.run(main_module.dispatch(args))

    assert result["command"] == "asset.get"
    assert result["data"]["id"] == "70000000-0000-4000-8000-000000000001"
    assert calls == [
        {
            "method": "GET",
            "path": "/agent-cli/assets/topic/70000000-0000-4000-8000-000000000001",
            "params": {"workspace_id": "workspace-1"},
            "unwrap_success": True,
        }
    ]


@pytest.mark.parametrize(
    ("workspace_args", "expected_workspace_id"),
    [
        ([], "workspace-selected"),
        (
            ["--workspace-id", "20000000-0000-4000-8000-000000000001"],
            "20000000-0000-4000-8000-000000000001",
        ),
    ],
)
def test_dispatch_asset_get_batch_format_uses_one_request_and_preserves_ids(
    monkeypatch: pytest.MonkeyPatch,
    workspace_args: list[str],
    expected_workspace_id: str,
) -> None:
    first_id = "10000000-0000-4000-8000-000000000001"
    second_id = "10000000-0000-4000-8000-000000000002"
    cfg = Config()
    cfg.workspace = WorkspaceState(
        id="workspace-selected", name="Workspace", organization_id="org-1"
    )
    calls: list[dict[str, object]] = []

    async def fake_api_data(
        cfg_arg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
        unwrap_success: bool = True,
    ) -> dict[str, object]:
        del cfg_arg
        calls.append(
            {
                "method": method,
                "path": path,
                "json_body": json_body,
                "params": params,
                "unwrap_success": unwrap_success,
            }
        )
        return {
            "type": "format",
            "requested_ids": [first_id, second_id],
            "items": [{"id": second_id, "title": "Second"}],
            "missing_ids": [first_id],
        }

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    args = parse(
        [
            "asset",
            "+get-batch",
            "--type",
            "format",
            "--id",
            first_id,
            "--id",
            second_id,
            *workspace_args,
        ]
    )
    result = asyncio.run(main_module.dispatch(args))

    assert result["command"] == "asset.get-batch"
    assert result["data"]["missing_ids"] == [first_id]
    assert result["data"]["items"][0]["ref"].endswith(f"/assets/formats/{second_id})")
    assert calls == [
        {
            "method": "POST",
            "path": "/agent-cli/assets/format:batch-get",
            "json_body": {
                "type": "format",
                "workspace_id": expected_workspace_id,
                "ids": [first_id, second_id],
            },
            "params": None,
            "unwrap_success": True,
        }
    ]


def test_asset_get_batch_format_rejects_duplicate_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    format_id = "10000000-0000-4000-8000-000000000001"
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="Workspace", organization_id="org-1")
    monkeypatch.setattr(main_module, "load_config", lambda: cfg)

    args = parse(
        [
            "asset",
            "+get-batch",
            "--type",
            "format",
            "--id",
            format_id,
            "--id",
            format_id,
        ]
    )

    with pytest.raises(ValueError, match="must be unique"):
        asyncio.run(main_module.dispatch(args))


def test_asset_get_batch_schema_requires_native_batch_for_multiple_format_ids() -> None:
    schema = main_module.schema_payload("asset.get-batch")

    assert schema["input_schema"]["properties"]["format_ids"]["maxItems"] == 100
    assert schema["input_schema"]["properties"]["format_ids"]["uniqueItems"] is True
    assert "MUST use this command" in schema["summary"]


def test_dispatch_asset_create_topic_uses_agent_assets_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="Workspace", organization_id="org-1")
    calls: list[dict[str, object]] = []

    async def fake_api_data(
        cfg_arg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
        unwrap_success: bool = True,
    ) -> dict[str, object]:
        del cfg_arg, params
        calls.append(
            {
                "method": method,
                "path": path,
                "json_body": json_body,
                "unwrap_success": unwrap_success,
            }
        )
        return {
            "operation": "create",
            "type": "topic",
            "asset": {"created": 1, "items": [{"id": "70000000-0000-4000-8000-000000000001"}]},
        }

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    args = parse(
        [
            "asset",
            "+create",
            "--type",
            "topic",
            "--title",
            "Morning routine",
            "--narrative",
            "A compact routine story.",
            "--keyword",
            "routine",
        ]
    )
    result = asyncio.run(main_module.dispatch(args))

    assert result["command"] == "asset.create"
    assert result["data"]["asset"]["created"] == 1
    assert result["data"]["asset"]["items"][0]["ref"] == (
        "[70000000-0000-4000-8000-000000000001]"
        "(https://www.museon.ai/assets/topics/70000000-0000-4000-8000-000000000001)"
    )
    assert calls == [
        {
            "method": "POST",
            "path": "/agent-cli/assets",
            "json_body": {
                "type": "topic",
                "workspace_id": "workspace-1",
                "payload": {
                    "topics": [
                        {
                            "title": "Morning routine",
                            "narrative": "A compact routine story.",
                            "keywords": ["routine"],
                        }
                    ]
                },
            },
            "unwrap_success": True,
        }
    ]


def test_dispatch_asset_update_topic_uses_agent_assets_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="Workspace", organization_id="org-1")
    calls: list[dict[str, object]] = []

    async def fake_api_data(
        cfg_arg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
        unwrap_success: bool = True,
    ) -> dict[str, object]:
        del cfg_arg, params
        calls.append(
            {
                "method": method,
                "path": path,
                "json_body": json_body,
                "unwrap_success": unwrap_success,
            }
        )
        return {
            "operation": "update",
            "type": "topic",
            "asset": {"id": "70000000-0000-4000-8000-000000000001", "status": "inactive"},
        }

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    args = parse(
        [
            "asset",
            "+update",
            "--type",
            "topic",
            "--id",
            "70000000-0000-4000-8000-000000000001",
            "--payload-json",
            '{"status":"inactive"}',
        ]
    )
    result = asyncio.run(main_module.dispatch(args))

    assert result["command"] == "asset.update"
    assert result["data"]["asset"]["status"] == "inactive"
    assert result["data"]["asset"]["ref"] == (
        "[70000000-0000-4000-8000-000000000001]"
        "(https://www.museon.ai/assets/topics/70000000-0000-4000-8000-000000000001)"
    )
    assert calls == [
        {
            "method": "PATCH",
            "path": "/agent-cli/assets/topic/70000000-0000-4000-8000-000000000001",
            "json_body": {
                "type": "topic",
                "workspace_id": "workspace-1",
                "payload": {"status": "inactive"},
            },
            "unwrap_success": True,
        }
    ]


def test_dispatch_asset_update_format_uses_agent_assets_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="Workspace", organization_id="org-1")
    calls: list[dict[str, object]] = []

    async def fake_api_data(
        cfg_arg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
        unwrap_success: bool = True,
    ) -> dict[str, object]:
        del cfg_arg, params
        calls.append(
            {
                "method": method,
                "path": path,
                "json_body": json_body,
                "unwrap_success": unwrap_success,
            }
        )
        return {
            "operation": "update",
            "type": "format",
            "asset": {
                "id": "f0000000-0000-4000-8000-000000000001",
                "title": "Fast proof grid",
                "format_json": {"md": "Use a clear before/after arc."},
            },
        }

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    args = parse(
        [
            "asset",
            "+update",
            "--type",
            "format",
            "--id",
            "f0000000-0000-4000-8000-000000000001",
            "--title",
            "Fast proof grid",
            "--analysis-markdown",
            "Use a clear before/after arc.",
        ]
    )
    result = asyncio.run(main_module.dispatch(args))

    assert result["command"] == "asset.update"
    assert result["data"]["asset"]["format_json"] == {"md": "Use a clear before/after arc."}
    assert result["data"]["asset"]["ref"] == (
        "[Fast proof grid](https://www.museon.ai/assets/formats/"
        "f0000000-0000-4000-8000-000000000001)"
    )
    assert calls == [
        {
            "method": "PATCH",
            "path": "/agent-cli/assets/format/f0000000-0000-4000-8000-000000000001",
            "json_body": {
                "type": "format",
                "workspace_id": "workspace-1",
                "payload": {
                    "title": "Fast proof grid",
                    "format_json": {"md": "Use a clear before/after arc."},
                },
            },
            "unwrap_success": True,
        }
    ]


def test_dispatch_asset_create_format_url_calls_format_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="Workspace", organization_id="org-1")
    calls: list[dict[str, object]] = []

    async def fake_api_data(
        cfg_arg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
    ) -> dict[str, object]:
        del cfg_arg, params
        calls.append({"method": method, "path": path, "json_body": json_body})
        return {
            "operation": "create",
            "type": "format",
            "asset": {
                "format_id": "f0000000-0000-4000-8000-000000000001",
                "workspace_id": "workspace-1",
                "status": "analyzing",
                "source_kind": "tiktok",
                "source_url": "https://www.tiktok.com/@example/photo/123",
            },
        }

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    args = parse(
        [
            "asset",
            "+create",
            "--type",
            "format",
            "--url",
            "https://www.tiktok.com/@example/photo/123",
        ]
    )
    result = asyncio.run(main_module.dispatch(args))

    assert result["command"] == "asset.create"
    assert result["data"]["format_id"] == "f0000000-0000-4000-8000-000000000001"
    assert result["run"] == {
        "id": "f0000000-0000-4000-8000-000000000001",
        "type": "format_analysis",
        "status": "analyzing",
        "watch_command": "museoncli asset +get --type format --id f0000000-0000-4000-8000-000000000001",
    }
    assert calls == [
        {
            "method": "POST",
            "path": "/agent-cli/assets",
            "json_body": {
                "type": "format",
                "workspace_id": "workspace-1",
                "payload": {
                    "source_url": "https://www.tiktok.com/@example/photo/123",
                    "source_kind": "tiktok",
                },
            },
        }
    ]


def test_dispatch_asset_create_format_url_detects_instagram(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="Workspace", organization_id="org-1")
    calls: list[dict[str, object]] = []

    async def fake_api_data(
        cfg_arg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
    ) -> dict[str, object]:
        del cfg_arg, method, path, params
        calls.append({"json_body": json_body})
        return {
            "asset": {
                "format_id": "format-ig",
                "workspace_id": "workspace-1",
                "status": "analyzing",
            }
        }

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    args = parse(
        ["asset", "+create", "--type", "format", "--url", "https://www.instagram.com/p/abc/"]
    )
    result = asyncio.run(main_module.dispatch(args))

    assert result["run"]["id"] == "format-ig"
    assert calls[0]["json_body"]["payload"]["source_kind"] == "instagram"


def test_dispatch_asset_create_format_url_dry_run_does_not_call_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="Workspace", organization_id="org-1")

    async def fake_api_data(*args: object, **kwargs: object) -> dict[str, object]:
        raise AssertionError("dry-run should not call API")

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    args = parse(
        [
            "asset",
            "+create",
            "--type",
            "format",
            "--url",
            "https://www.instagram.com/p/abc/",
            "--dry-run",
        ]
    )
    result = asyncio.run(main_module.dispatch(args))

    assert result["command"] == "asset.create"
    assert result["data"]["dry_run"] is True
    assert result["data"]["arguments"] == {
        "type": "slideshow_soul_skin_format",
        "payload": {
            "source_url": "https://www.instagram.com/p/abc/",
            "source_kind": "instagram",
        },
    }


def test_dispatch_asset_create_format_url_cross_post(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="Workspace", organization_id="org-1")
    calls: list[dict[str, object]] = []

    async def fake_api_data(
        cfg_arg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
    ) -> dict[str, object]:
        del cfg_arg, method, path, params
        calls.append({"json_body": json_body})
        return {
            "asset": {
                "format_id": "format-cross",
                "workspace_id": "workspace-1",
                "status": "analyzing",
            }
        }

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    args = parse(
        [
            "asset",
            "+create",
            "--type",
            "format",
            "--url",
            "https://www.tiktok.com/@a/photo/1",
            "--url",
            "https://www.tiktok.com/@b/photo/2",
            "--instructions",
            "Compare shared structure.",
        ]
    )
    result = asyncio.run(main_module.dispatch(args))

    assert result["run"]["id"] == "format-cross"
    assert calls[0]["json_body"] == {
        "type": "format",
        "workspace_id": "workspace-1",
        "payload": {
            "source_kind": "cross_post",
            "tiktok_urls": [
                "https://www.tiktok.com/@a/photo/1",
                "https://www.tiktok.com/@b/photo/2",
            ],
            "instructions": "Compare shared structure.",
        },
    }


def test_dispatch_asset_create_format_media_cross_post(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="Workspace", organization_id="org-1")
    calls: list[dict[str, object]] = []

    async def fake_api_data(
        cfg_arg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
    ) -> dict[str, object]:
        del cfg_arg, method, path, params
        calls.append({"json_body": json_body})
        return {
            "asset": {
                "format_id": "format-media",
                "workspace_id": "workspace-1",
                "status": "analyzing",
            }
        }

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    args = parse(
        [
            "asset",
            "+create",
            "--type",
            "format",
            "--media-id",
            "3ed10000-0000-4000-8000-000000000001",
            "--media-id",
            "3ed10000-0000-4000-8000-000000000002",
            "--post-range",
            "0:1",
            "--post-range",
            "1:2",
        ]
    )
    result = asyncio.run(main_module.dispatch(args))

    assert result["command"] == "asset.create"
    assert result["run"]["id"] == "format-media"
    assert calls[0]["json_body"] == {
        "type": "format",
        "workspace_id": "workspace-1",
        "payload": {
            "uploaded_media_ids": [
                "3ed10000-0000-4000-8000-000000000001",
                "3ed10000-0000-4000-8000-000000000002",
            ],
            "source_kind": "cross_post",
            "uploaded_post_ranges": [
                {"start_index": 0, "end_index": 1},
                {"start_index": 1, "end_index": 2},
            ],
        },
    }


def test_dispatch_asset_create_media_url_calls_media_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="Workspace", organization_id="org-1")
    calls: list[dict[str, object]] = []

    async def fake_api_data(
        cfg_arg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
    ) -> dict[str, object]:
        del cfg_arg, params
        calls.append({"method": method, "path": path, "json_body": json_body})
        return {
            "operation": "create",
            "type": "media",
            "asset": {
                "media_id": "3ed10000-0000-4000-8000-000000000001",
                "media_url": "https://storage.example/a.jpg",
            },
        }

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    args = parse(["asset", "+create", "--type", "media", "--url", "https://example.com/a.jpg"])
    result = asyncio.run(main_module.dispatch(args))

    assert result["command"] == "asset.create"
    assert result["data"]["asset"]["media_id"] == "3ed10000-0000-4000-8000-000000000001"
    assert calls == [
        {
            "method": "POST",
            "path": "/agent-cli/assets",
            "json_body": {
                "type": "media",
                "workspace_id": "workspace-1",
                "payload": {"url": "https://example.com/a.jpg"},
            },
        }
    ]


def test_dispatch_asset_create_media_rejects_tag_flag() -> None:
    args = parse(
        [
            "asset",
            "+create",
            "--type",
            "media",
            "--url",
            "https://example.com/a.jpg",
            "--tag",
            "codex-smoke",
            "--dry-run",
        ]
    )

    with pytest.raises(ValueError, match="media does not support --tag"):
        asyncio.run(main_module.dispatch(args))


def test_dispatch_asset_list_media_preserves_pagination_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="Workspace", organization_id="org-1")
    calls: list[dict[str, object]] = []

    async def fake_api_data(
        cfg_arg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
        unwrap_success: bool = True,
    ) -> dict[str, object]:
        del cfg_arg, json_body
        calls.append(
            {
                "method": method,
                "path": path,
                "params": params,
                "unwrap_success": unwrap_success,
            }
        )
        return {
            "type": "media",
            "items": [{"id": "3ed10000-0000-4000-8000-000000000001"}],
            "pagination": {
                "total": 1,
                "page": 1,
                "page_size": 10,
                "total_pages": 1,
                "has_more": False,
            },
        }

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    args = parse(
        ["asset", "+list", "--type", "media", "--media-type", "image", "--page-size", "10"]
    )
    result = asyncio.run(main_module.dispatch(args))

    assert result["command"] == "asset.list"
    assert result["data"]["pagination"]["total"] == 1
    assert "ref" not in result["data"]["items"][0]
    assert calls == [
        {
            "method": "GET",
            "path": "/agent-cli/assets",
            "params": {
                "type": "media",
                "media_type": "image",
                "page": 1,
                "page_size": 10,
                "workspace_id": "workspace-1",
            },
            "unwrap_success": True,
        }
    ]


def test_dispatch_asset_list_adds_markdown_refs_for_embeddable_assets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="Workspace", organization_id="org-1")

    async def fake_api_data(
        cfg_arg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
        unwrap_success: bool = True,
    ) -> dict[str, object]:
        del cfg_arg, method, path, json_body, params, unwrap_success
        return {
            "type": "product",
            "items": [
                {
                    "id": "product 1)",
                    "title": "Acme (Pro)\n\tLaunch",
                },
                {"id": "1ed10000-0000-4000-8000-000000000002"},
                {"title": "Missing id"},
            ],
            "pagination": {"total": 3},
        }

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    args = parse(["asset", "+list", "--type", "product", "--page-size", "3"])
    result = asyncio.run(main_module.dispatch(args))

    assert result["data"]["items"][0]["ref"] == (
        "[Acme (Pro) Launch](https://www.museon.ai/assets/products/product%201%29)"
    )
    assert result["data"]["items"][1]["ref"] == (
        "[1ed10000-0000-4000-8000-000000000002]"
        "(https://www.museon.ai/assets/products/1ed10000-0000-4000-8000-000000000002)"
    )
    assert "ref" not in result["data"]["items"][2]


def test_dispatch_asset_get_media_calls_media_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="Workspace", organization_id="org-1")
    calls: list[dict[str, object]] = []

    async def fake_api_data(
        cfg_arg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
        unwrap_success: bool = True,
    ) -> dict[str, object]:
        del cfg_arg, json_body
        calls.append(
            {
                "method": method,
                "path": path,
                "params": params,
                "unwrap_success": unwrap_success,
            }
        )
        return {"id": "3ed10000-0000-4000-8000-000000000001"}

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    args = parse(
        ["asset", "+get", "--type", "media", "--id", "3ed10000-0000-4000-8000-000000000001"]
    )
    result = asyncio.run(main_module.dispatch(args))

    assert result["command"] == "asset.get"
    assert result["data"]["id"] == "3ed10000-0000-4000-8000-000000000001"
    assert "ref" not in result["data"]
    assert calls == [
        {
            "method": "GET",
            "path": "/agent-cli/assets/media/3ed10000-0000-4000-8000-000000000001",
            "params": {"workspace_id": "workspace-1"},
            "unwrap_success": True,
        }
    ]


def test_dispatch_asset_get_adds_markdown_ref_from_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="Workspace", organization_id="org-1")

    async def fake_api_data(
        cfg_arg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
        unwrap_success: bool = True,
    ) -> dict[str, object]:
        del cfg_arg, method, path, json_body, params, unwrap_success
        return {
            "id": "2ed10000-0000-4000-8000-000000000001",
            "name": "Taylor",
        }

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    args = parse(
        ["asset", "+get", "--type", "persona", "--id", "2ed10000-0000-4000-8000-000000000001"]
    )
    result = asyncio.run(main_module.dispatch(args))

    assert result["data"]["ref"] == (
        "[Taylor](https://www.museon.ai/assets/personas/2ed10000-0000-4000-8000-000000000001)"
    )


def test_asset_ref_transform_skips_unexpected_payload_shapes() -> None:
    assert envelopes_module.add_asset_refs(["not", "a", "resource"], asset_type="product") == [
        "not",
        "a",
        "resource",
    ]
    data = {"items": ["bad", {"name": "Missing id"}]}

    assert envelopes_module.add_asset_refs(data, asset_type="topic") == data
    assert data == {"items": ["bad", {"name": "Missing id"}]}


def test_dispatch_asset_create_media_file_calls_multipart_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="Workspace", organization_id="org-1")
    calls: list[dict[str, object]] = []

    async def fake_upload_media_file(
        cfg_arg: Config,
        *,
        workspace_id: str,
        arguments: dict[str, object],
    ) -> dict[str, object]:
        del cfg_arg
        calls.append({"workspace_id": workspace_id, "arguments": arguments})
        return {
            "media_id": "3ed10000-0000-4000-8000-000000000001",
            "media_url": "https://storage.example/a.jpg",
        }

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "upload_media_file", fake_upload_media_file)

    args = parse(["asset", "+create", "--type", "media", "--file", "./a.png", "--title", "A"])
    result = asyncio.run(main_module.dispatch(args))

    assert result["command"] == "asset.create"
    assert result["data"]["media_id"] == "3ed10000-0000-4000-8000-000000000001"
    assert calls == [
        {
            "workspace_id": "workspace-1",
            "arguments": {"file": "./a.png", "media_type": "image", "title": "A"},
        }
    ]


def test_dispatch_artifacts_upload_calls_multipart_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="Workspace", organization_id="org-1")
    calls: list[dict[str, object]] = []

    async def fake_upload_artifact_file(
        cfg_arg: Config,
        *,
        workspace_id: str | None,
        arguments: dict[str, object],
    ) -> dict[str, object]:
        del cfg_arg
        calls.append({"workspace_id": workspace_id, "arguments": arguments})
        return {
            "artifact": {
                "id": "4ed10000-0000-4000-8000-000000000001",
                "gcs_path": "agent-artifacts/4ed10000-0000-4000-8000-000000000001/report.md",
            },
            "url": "https://museon.ai/artifacts/4ed10000-0000-4000-8000-000000000001",
            "url_kind": "frontend",
        }

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "upload_artifact_file", fake_upload_artifact_file)

    args = parse(
        [
            "artifacts",
            "+upload",
            "--file",
            "./report.md",
            "--title",
            "Report",
            "--runtime-context-json",
            '{"turn_id":"turn-1"}',
        ]
    )
    result = asyncio.run(main_module.dispatch(args))

    assert result["command"] == "artifacts.upload"
    assert result["data"]["url_kind"] == "frontend"
    assert calls == [
        {
            "workspace_id": "workspace-1",
            "arguments": {
                "file": "./report.md",
                "artifact_type": "file",
                "title": "Report",
                "runtime_context": {"turn_id": "turn-1"},
                "public": True,
            },
        }
    ]


def test_artifacts_upload_schema_uses_artifact_id_for_replacement() -> None:
    schema = main_module.schema_payload("artifacts.upload")
    properties = schema["input_schema"]["properties"]

    assert "file" in properties
    assert "runtime_context" in properties
    assert "artifact_id" in properties
    assert properties["public"]["default"] is True
    assert "data.public_url" in schema["summary"]
    assert "data.url" in schema["summary"]
    assert "BOTH links" in schema["summary"]
    assert "public by default" in schema["summary"]
    assert "paste their ready-made ref" in schema["summary"]
    assert "generation +get/+list/+create" in schema["summary"]
    assert "paste each generation ref alone on" in schema["summary"]
    assert "do not hand-write generation links" in schema["summary"]
    assert "TikTok, Instagram, or YouTube URL" in schema["summary"]
    assert "data.public_url is the public share link" in schema["output_schema"]["description"]
    assert "workspace/private link" in schema["output_schema"]["description"]


def test_asset_schema_notes_resource_refs() -> None:
    list_schema = main_module.schema_payload("asset.list")
    get_schema = main_module.schema_payload("asset.get")

    assert "Each resource includes a ref" in list_schema["summary"]
    assert "Each resource includes a ref" in get_schema["summary"]
    assert "renders a full card" in list_schema["summary"]


def test_generation_schema_notes_refs_and_result_media() -> None:
    create_schema = main_module.schema_payload("generation.create")
    schedule_generate_schema = main_module.schema_payload("social-account.schedule-generate")
    profile_edit_schema = main_module.schema_payload("social-account.profile-edit-submit")
    get_schema = main_module.schema_payload("generation.get")
    list_schema = main_module.schema_payload("generation.list")

    assert "recommended wakeup delay" in create_schema["summary"]
    run_schema = create_schema["output_schema"]["properties"]["run"]
    assert "ref" in run_schema["properties"]
    assert "recommended_wakeup_delay_seconds" in run_schema["properties"]
    schedule_run_schema = schedule_generate_schema["output_schema"]["properties"]["run"]
    assert "recommended_wakeup_delay_seconds" in schedule_run_schema["properties"]
    profile_run_schema = profile_edit_schema["output_schema"]["properties"]["run"]
    assert "recommended_wakeup_delay_seconds" not in profile_run_schema["properties"]
    assert "ready-made generation ref" in get_schema["summary"]
    assert "result_preview_image_urls" in get_schema["summary"]
    assert "grid_media" in list_schema["summary"]
    assert "slide_media" in list_schema["summary"]


def test_schema_exposes_frontend_url_templates_for_assets() -> None:
    schema = main_module.schema_payload("asset.get")
    templates = schema["frontend_url_templates"]

    assert {
        template["applies_when"].get("type"): template["path_template"] for template in templates
    } == {
        "product": "/assets/products/{id}",
        "persona": "/assets/personas/{id}",
        "topic": "/assets/topics/{id}",
        "topic_direction": "/assets/topics",
        "format": "/assets/formats/{id}",
        "media": "/gallery",
    }
    assert all(template["url_template"].startswith("{frontend_origin}/") for template in templates)


def test_schema_exposes_frontend_url_templates_for_campaigns_and_accounts() -> None:
    campaign_schema = main_module.schema_payload("campaign-monitor.summary")
    account_schema = main_module.schema_payload("social-account.schedule-list")

    assert "/campaigns/{campaign_id}/creators" in {
        template["path_template"] for template in campaign_schema["frontend_url_templates"]
    }
    assert "/campaigns/{campaign_id}/analytics" in {
        template["path_template"] for template in campaign_schema["frontend_url_templates"]
    }
    assert "/campaigns/{campaign_id}/settlement" not in {
        template["path_template"] for template in campaign_schema["frontend_url_templates"]
    }
    assert "/social-accounts/pool-accounts/{account_id}/performance" in {
        template["path_template"] for template in account_schema["frontend_url_templates"]
    }
    assert "/social-accounts/calendar" in {
        template["path_template"] for template in account_schema["frontend_url_templates"]
    }


def test_schema_exposes_generation_detail_frontend_url_template() -> None:
    schema = main_module.schema_payload("generation.get")

    assert any(
        template["path_template"] == "/generations/{generation_id}"
        and template["requires_auth"] is False
        for template in schema["frontend_url_templates"]
    )


def test_schema_catalog_summaries_include_frontend_url_templates() -> None:
    catalog = main_module.schema_payload()

    asset_get = next(item for item in catalog["commands"]["asset"] if item["name"] == "asset.get")
    campaign_get = next(
        item
        for item in catalog["commands"]["campaign-monitor"]
        if item["name"] == "campaign-monitor.get"
    )

    assert any(
        template["path_template"] == "/assets/products/{id}"
        for template in asset_get["frontend_url_templates"]
    )
    assert any(
        template["path_template"] == "/campaigns/{campaign_id}/creators"
        for template in campaign_get["frontend_url_templates"]
    )


def test_routines_schema_notes_schedule_refs() -> None:
    list_schema = main_module.schema_payload("routines.list")
    get_schema = main_module.schema_payload("routines.get")

    assert "Each routine includes a ref" in list_schema["summary"]
    assert "Each routine includes a ref" in get_schema["summary"]
    assert "live schedule card" in list_schema["summary"]


def test_dispatch_asset_delete_calls_agent_assets_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="Workspace", organization_id="org-1")
    calls: list[dict[str, object]] = []

    async def fake_api_data(
        cfg_arg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
        unwrap_success: bool = True,
    ) -> dict[str, object]:
        del cfg_arg, json_body
        calls.append(
            {
                "method": method,
                "path": path,
                "params": params,
                "unwrap_success": unwrap_success,
            }
        )
        return {
            "operation": "delete",
            "type": "topic",
            "asset": {"id": "70000000-0000-4000-8000-000000000001"},
        }

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    args = parse(
        [
            "asset",
            "+delete",
            "--type",
            "topic",
            "--id",
            "70000000-0000-4000-8000-000000000001",
            "--yes",
        ]
    )
    result = asyncio.run(main_module.dispatch(args))

    assert result["command"] == "asset.delete"
    assert result["data"]["asset"]["id"] == "70000000-0000-4000-8000-000000000001"
    assert calls == [
        {
            "method": "DELETE",
            "path": "/agent-cli/assets/topic/70000000-0000-4000-8000-000000000001",
            "params": {"workspace_id": "workspace-1"},
            "unwrap_success": True,
        }
    ]


def test_http_validation_errors_map_to_invalid_input() -> None:
    assert reason_from_exception(RuntimeError("HTTP 422: invalid body")) == "invalid_input"
    assert reason_from_exception(RuntimeError("HTTP 400: bad request")) == "invalid_input"


def test_forbidden_owner_mismatch_error_is_readable() -> None:
    response = main_module.httpx.Response(
        403,
        json={
            "detail": {
                "code": "routine_owner_mismatch",
                "owner_user_id": "user-owner",
                "routine_id": "routine-1",
                "routine_name": "Daily report",
            }
        },
    )

    message = main_module.forbidden_error_message(response)

    assert message == (
        "forbidden: routine_owner_mismatch: Daily report (routine-1) is owned by user user-owner"
    )
    assert reason_from_exception(RuntimeError(message)) == "forbidden"


VALID_UUID = "72defd40-39ad-40d3-8105-8f23a9a016da"
VALID_UUID_2 = "fa21bd13-71bc-4068-aa20-d4e5dfd511ff"


def test_validate_uuid_arguments_rejects_placeholder_in_changes() -> None:
    with pytest.raises(ValueError, match="product_id"):
        main_module.validate_uuid_arguments(
            {"account_id": VALID_UUID, "changes": {"product_id": "?"}}
        )
    with pytest.raises(ValueError, match=r"format_ids\[0\]"):
        main_module.validate_uuid_arguments(
            {"account_id": VALID_UUID, "changes": {"format_ids": ["?"]}}
        )


def test_validate_uuid_arguments_rejects_freeform_account_id() -> None:
    with pytest.raises(ValueError, match="account_id"):
        main_module.validate_uuid_arguments({"account_id": "Page 2: 50 accounts"})


def test_validate_uuid_arguments_error_guides_recovery() -> None:
    with pytest.raises(ValueError) as excinfo:
        main_module.validate_uuid_arguments({"changes": {"product_id": "?"}})
    message = str(excinfo.value)
    assert "UUID" in message
    assert "omit" in message.lower()
    assert "look" in message.lower()


def test_validate_uuid_arguments_accepts_valid_and_clear_semantics() -> None:
    main_module.validate_uuid_arguments(
        {
            "account_id": VALID_UUID,
            "changes": {
                "persona_id": VALID_UUID,
                "product_id": None,
                "format_ids": [],
                "content_topic_ids": [VALID_UUID, VALID_UUID_2],
            },
        }
    )


def test_validate_uuid_arguments_ignores_non_uuid_keys() -> None:
    main_module.validate_uuid_arguments(
        {
            "type": "topic",
            "search": "Page 2: 50 accounts",
            "payload": {
                "name": "anything",
                "asset_media_ids": ["look_reference:not-a-plain-uuid"],
            },
        }
    )


def test_dispatch_domain_command_rejects_placeholder_before_api_call(monkeypatch) -> None:
    cfg = Config(workspace=WorkspaceState(id=VALID_UUID, name="ws", organization_id=None))
    calls: list[dict[str, object]] = []

    async def fake_api_data(*args, **kwargs):
        calls.append({"args": args, "kwargs": kwargs})
        return {}

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    args = parse(
        [
            "social-account",
            "+assets-set",
            "--id",
            VALID_UUID,
            "--product-id",
            "?",
        ]
    )
    with pytest.raises(ValueError, match="product_id"):
        asyncio.run(main_module.dispatch(args))
    assert calls == []


def test_reason_from_exception_maps_value_error_to_invalid_input() -> None:
    assert reason_from_exception(ValueError("product_id must be a UUID")) == "invalid_input"


def test_api_request_error_preserves_structured_validation_detail() -> None:
    detail = {
        "code": "invalid_enum",
        "field": "payload.category",
        "received": "EDUCATION",
        "suggested_values": ["LEARNING_PLATFORMS", "SKILL_TRAINING"],
    }
    error = main_module.ApiRequestError(422, detail)

    assert reason_from_exception(error) == "invalid_input"
    assert main_module.exception_detail(error) == detail


def test_asset_delete_without_yes_returns_confirmation_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="W", organization_id="org-1")

    async def explode(*args: object, **kwargs: object) -> object:
        raise AssertionError("confirmation gate must block the API call")

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", explode)

    args = parse(
        ["asset", "+delete", "--type", "topic", "--id", "70000000-0000-4000-8000-000000000001"]
    )
    with pytest.raises(RuntimeError, match="confirmation_required"):
        asyncio.run(main_module.dispatch(args))

    assert main_module.reason_from_exception(RuntimeError("confirmation_required")) == (
        "confirmation_required"
    )


def test_destructive_specs_require_confirmation_and_dry_run() -> None:
    from museoncli.domains import command_specs

    for spec in command_specs():
        if spec.risk_level == "destructive":
            assert spec.requires_confirmation, spec.schema_name
            assert spec.supports_dry_run, spec.schema_name


def test_dispatch_bgm_asset_commands_are_workspace_level(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: bgm-asset list/create wrongly demanded an account_id the
    parser never collected (inherited from the pre-executor dispatch chain)."""
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="W", organization_id="org-1")
    calls: list[dict[str, object]] = []

    async def fake_api_data(
        cfg_arg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
    ) -> dict[str, object]:
        calls.append({"method": method, "path": path, "json_body": json_body, "params": params})
        return {"domain": "social-account", "result": {"items": []}}

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    listed = asyncio.run(
        main_module.dispatch(parse(["social-account", "+bgm-asset-list", "--search", "lofi"]))
    )
    assert listed["command"] == "social-account.bgm-asset-list"
    assert calls[0]["method"] == "GET"
    assert calls[0]["path"] == "/agent-cli/bgm-assets"
    params = calls[0]["params"]
    assert isinstance(params, dict)
    assert params["workspace_id"] == "workspace-1"
    assert params["search"] == "lofi"

    created = asyncio.run(
        main_module.dispatch(
            parse(
                [
                    "social-account",
                    "+bgm-asset-create",
                    "--url",
                    "https://www.tiktok.com/@a/video/123",
                    "--title",
                    "Lofi ref",
                    "--description",
                    "Soft morning loop",
                ]
            )
        )
    )
    assert created["command"] == "social-account.bgm-asset-create"
    assert calls[1]["method"] == "POST"
    assert calls[1]["path"] == "/agent-cli/bgm-assets"
    body = calls[1]["json_body"]
    assert isinstance(body, dict)
    assert body.get("workspace_id") == "workspace-1"
    assert body.get("payload") == {
        "url": "https://www.tiktok.com/@a/video/123",
        "title": "Lofi ref",
        "description": "Soft morning loop",
    }
