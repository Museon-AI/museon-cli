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
        ["media", "+import", "--url", "https://example.com/a.jpg", "--dry-run"],
        ["media", "+upload", "--file", "./video.mp4", "--media-type", "video", "--dry-run"],
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


def test_host_managed_auth_blocks_config_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config(
        auth=AuthState(
            method="agent_capability",
            provider="agent_session",
            managed_by="agents_host",
        )
    )
    monkeypatch.setattr(main_module, "load_config", lambda: cfg)

    with pytest.raises(RuntimeError, match="managed_auth"):
        asyncio.run(
            main_module.dispatch_config(
                argparse.Namespace(config_command="set"),
            )
        )


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


def test_host_managed_auth_status_is_explicit_and_mutations_are_blocked() -> None:
    cfg = Config(
        auth=AuthState(
            api_key="mcap_current",
            method="agent_capability",
            provider="agent_session",
            managed_by="agents_host",
            expires_at=4_000_000_000,
            version="lease-current",
            persistable=False,
        )
    )

    result = asyncio.run(main_module.dispatch_auth(argparse.Namespace(auth_command="status"), cfg))

    assert result["data"]["authenticated"] is True
    assert result["data"]["auth_method"] == "agent_capability"
    assert result["data"]["credential_provider"] == "agent_session"
    assert result["data"]["managed_by"] == "agents_host"
    assert result["data"]["version"] == "lease-current"
    for command in ("login", "start", "finish", "logout"):
        with pytest.raises(RuntimeError, match="managed_auth"):
            asyncio.run(main_module.dispatch_auth(argparse.Namespace(auth_command=command), cfg))


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
            "--skill-name",
            "chocolate-color-strategy",
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
        "skill_name": "chocolate-color-strategy",
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


def test_request_headers_include_active_cli_command() -> None:
    cfg = Config()
    cfg.auth = AuthState(api_key="api-key")
    token = main_module._ACTIVE_COMMAND_NAME.set("media.get")
    try:
        headers = main_module._request_headers(cfg)
    finally:
        main_module._ACTIVE_COMMAND_NAME.reset(token)

    assert headers["X-Museon-CLI-Command"] == "media.get"


_BATCH_ACCOUNT_UPDATES_JSON = (
    '[{"account_id":"ac000000-0000-4000-8000-000000000001","bio":"AI assistant"}]'
)


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
            "--views-min",
            "10000",
            "--likes-min",
            "10",
            "--likes-max",
            "99",
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
        "views_min": 10000,
        "likes_min": 10,
        "likes_max": 99,
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
    content_list = main_module.schema_payload("campaign-monitor.content-list")
    properties = content_list["input_schema"]["properties"]
    assert properties["views_min"]["minimum"] == 0
    assert properties["likes_min"]["minimum"] == 0
    assert properties["likes_max"]["minimum"] == 0


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
        "artifacts",
        "media",
        "social-account",
        "hireaicreator",
        "ai-slideshow",
        "campaign-monitor",
        "skills",
        "staff-ops",
        "routines",
    ]
    assert [item["name"] for item in result["data"]["commands"]["research"]] == [
        "research.web-research",
        "research.social-media-search",
        "research.social-media-hook-analyze",
        "research.social-media-hook-source",
        "research.social-media-hook-analyze-seen",
        "research.social-media-hook-analyze-get",
        "research.social-media-hook-analyze-poll",
        "research.social-media-hook-analyze-results",
        "research.social-media-hook-analyze-media-get",
        "research.community-search",
        "research.creative-search-ads",
        "research.creative-search-ads-get",
        "research.creative-search-ads-results",
        "research.visual-analyze",
    ]
    assert [item["name"] for item in result["data"]["commands"]["content-analysis"]] == [
        "content-analysis.run",
        "content-analysis.get",
        "content-analysis.list",
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
    assert properties["skill_name"]["pattern"] == "^[a-z0-9][a-z0-9_-]{0,79}$"
    assert properties["skill_name"]["maxLength"] == 80
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
    assert any("media +import --url" in item for item in result["data"]["examples"])
    assert "adapter" not in result["data"]


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
    assert props["mode"] == {"type": "string", "enum": ["ad-hoc"]}
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
    assert "museoncli routines +list --mode ad-hoc --page-size 20" in result["data"]["examples"]


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
            "--skill-name",
            "chocolate-color-strategy",
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
                    "skill_name": "chocolate-color-strategy",
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


def test_schema_exposes_frontend_url_templates_for_campaigns_and_accounts() -> None:
    campaign_schema = main_module.schema_payload("campaign-monitor.summary")

    assert "/campaigns/{campaign_id}/creators" in {
        template["path_template"] for template in campaign_schema["frontend_url_templates"]
    }
    assert "/campaigns/{campaign_id}/analytics" in {
        template["path_template"] for template in campaign_schema["frontend_url_templates"]
    }
    assert "/campaigns/{campaign_id}/settlement" not in {
        template["path_template"] for template in campaign_schema["frontend_url_templates"]
    }


def test_schema_catalog_summaries_include_frontend_url_templates() -> None:
    catalog = main_module.schema_payload()

    campaign_get = next(
        item
        for item in catalog["commands"]["campaign-monitor"]
        if item["name"] == "campaign-monitor.get"
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

    args = parse(["media", "+get", "--id", "?"])
    with pytest.raises(ValueError, match="id"):
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


def test_destructive_specs_require_confirmation_and_dry_run() -> None:
    from museoncli.domains import command_specs

    for spec in command_specs():
        if spec.risk_level == "destructive":
            assert spec.requires_confirmation, spec.schema_name
            assert spec.supports_dry_run, spec.schema_name
