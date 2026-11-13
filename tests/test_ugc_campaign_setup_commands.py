"""Batch 4 UGC writes: Campaign lifecycle, setup, Formats and personas.

Each test drives the real CLI entry point over a mocked HTTP transport, so the
method, path, query, body and headers asserted are the ones that would go out.
"""

from __future__ import annotations

import json
import sys
from typing import Any
from urllib.parse import parse_qsl

import httpx
import pytest

import museoncli.main as cli
from museoncli.config import AuthState, Config, OrganizationState

ORG = "70000000-0000-4000-8000-000000000001"
HOME = "70000000-0000-4000-8000-000000000009"
CAMPAIGN = "10000000-0000-4000-8000-000000000001"
BRIEF = "20000000-0000-4000-8000-000000000001"
OTHER_BRIEF = "20000000-0000-4000-8000-000000000002"
PERSONA = "60000000-0000-4000-8000-000000000001"
OTHER_PERSONA = "60000000-0000-4000-8000-000000000002"
USER_A = "80000000-0000-4000-8000-000000000001"
USER_B = "80000000-0000-4000-8000-000000000002"
TARGET = "90000000-0000-4000-8000-000000000001"
RULE = "90000000-0000-4000-8000-000000000002"
SCALE = "90000000-0000-4000-8000-000000000003"
RATE = "90000000-0000-4000-8000-000000000004"
HOST = "api.example.test"
UGC = "/api/v2/ugc"
UPDATED = "2026-11-10T08:00:00+00:00"
LATER = "2026-11-12T08:00:00+00:00"
_REAL_CLIENT = httpx.AsyncClient


class Server:
    """Answers by (method, path); records every request."""

    def __init__(self, routes: dict[tuple[str, str], Any]) -> None:
        self.routes = routes
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        key = (request.method, request.url.path)
        if key not in self.routes:
            return httpx.Response(404, json={"detail": {"code": "not_routed"}})
        answer = self.routes[key]
        if callable(answer):
            answer = answer(request)
        if answer is None:
            return httpx.Response(204)
        if isinstance(answer, tuple):
            return httpx.Response(answer[0], json=answer[1])
        return httpx.Response(200, json=answer)

    def writes(self) -> list[httpx.Request]:
        return [request for request in self.requests if request.method != "GET"]

    def only_write(self) -> httpx.Request:
        writes = self.writes()
        assert len(writes) == 1, [(r.method, r.url.path) for r in writes]
        return writes[0]


def body(request: httpx.Request) -> Any:
    return json.loads(request.content) if request.content else None


def query(request: httpx.Request) -> dict[str, str]:
    return dict(parse_qsl(request.url.query.decode()))


def run(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    server: Server,
    argv: list[str],
) -> tuple[int, dict[str, Any]]:
    monkeypatch.setenv("MUSEONCLI_UPDATE_CHECK", "0")
    cfg = Config(
        api_base_url=f"https://{HOST}/api/v1",
        auth=AuthState(api_key="test-only"),
        organization=OrganizationState(id=ORG, name="MuseOn"),
    )
    monkeypatch.setattr(cli, "load_config", lambda: cfg)
    monkeypatch.setattr(
        cli.httpx,
        "AsyncClient",
        lambda **kw: _REAL_CLIENT(**kw, transport=httpx.MockTransport(server)),
    )
    monkeypatch.setattr(sys, "argv", ["museoncli", *argv])
    code = 0
    try:
        cli.main()
    except SystemExit as exited:
        code = int(exited.code or 0)
    payload = json.loads(capsys.readouterr().out)
    for request in server.requests:
        assert request.headers.get("X-Organization-Id") == ORG
        assert "workspace" not in request.url.query.decode()
        assert not any("workspace" in name.lower() for name in request.headers)
        assert b"workspace_id" not in request.content
    return code, payload


@pytest.fixture
def cli_run(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    def go(server: Server, *argv: str) -> tuple[int, dict[str, Any]]:
        return run(monkeypatch, capsys, server, list(argv))

    return go


# -- Campaign lifecycle --------------------------------------------------------


def _summary(status: str = "draft", **extra: Any) -> dict[str, Any]:
    return {
        "id": CAMPAIGN,
        "name": "Spring",
        "campaign_type": "ugc",
        "status": status,
        "monitor_collection_id": "c0000000-0000-4000-8000-000000000001",
        "product_id": None,
        "updated_at": UPDATED,
        "workspace_id": HOME,
        **extra,
    }


def _settings(**extra: Any) -> dict[str, Any]:
    return {
        "name": "Spring",
        "campaign_type": "ugc",
        "allowed_platforms": ["tiktok", "instagram"],
        "content_languages": ["en"],
        "target_countries": ["US"],
        "required_platforms": ["tiktok"],
        "files_only": False,
        "content_intake": {"mode": "auto_sync", "caption_shortcut": None, "rule_description": None},
        "brief_mode": "written",
        "join_mode": "invite_only",
        "approval_mode": "manual",
        "stay_rules": {"allow_rejoin": False, "inactivity_days": 14, "max_videos_per_week": 5},
        "warmup_rules": {"enabled": False},
        "trial_rules": {"enabled": False},
        "post_grouping": "highest_platform",
        "view_tracking_days": 30,
        "pay_trial_reels": False,
        "payout_release": "manual",
        "budget_cap_cents": None,
        "discord_onboarding_enabled": True,
        # Read-only fields the write must not echo back.
        "public_token": "tok",
        "open_payscale_id": None,
        "attribution_starts_on": None,
        "brief_progress_days": [],
        "platform_pay_rules": None,
        "application_form": {"questions": []},
        **extra,
    }


def _view(status: str = "draft", *, ok: bool = True, **settings: Any) -> dict[str, Any]:
    return {
        "campaign": _summary(status),
        "settings": _settings(**settings),
        "launchability": {"ok": ok, "reasons": [] if ok else [{"code": "no_brief"}]},
    }


def _whoami(kind: str | None = None) -> dict[str, Any]:
    return {
        "success": True,
        "data": {
            "organizations": [
                {"id": ORG, "name": "MuseOn", "role": "admin", "default_workspace_id": HOME}
            ]
        },
    }


def _access(kind: str) -> dict[str, Any]:
    return {"organizations": {"items": [{"id": ORG, "kind": kind}]}}


def _create_routes(kind: str = "operator") -> dict[tuple[str, str], Any]:
    return {
        ("GET", "/api/v1/agent-cli/whoami"): _whoami(),
        ("GET", "/api/v1/users/me/access"): _access(kind),
        ("POST", f"{UGC}/workspaces/{HOME}/campaigns"): (201, _summary()),
    }


def test_campaign_create_ugc_posts_the_web_flows_draft_in_the_organizations_home(cli_run) -> None:
    server = Server(_create_routes())

    code, result = cli_run(server, "ugc", "campaign", "+create", "--name", " Spring ")

    assert code == 0, result
    sent = server.only_write()
    assert sent.url.path == f"{UGC}/workspaces/{HOME}/campaigns"
    assert body(sent) == {
        "name": "Spring",
        "campaign_type": "ugc",
        "product_id": None,
        "allowed_platforms": ["tiktok", "instagram", "youtube", "facebook"],
        "required_platforms": ["tiktok", "instagram"],
    }
    access = next(r for r in server.requests if r.url.path.endswith("/me/access"))
    assert query(access) == {"organization_id": ORG}
    assert result["data"]["campaign"]["id"] == CAMPAIGN
    assert "workspace_id" not in json.dumps(result)


def test_campaign_create_refuses_ugc_in_a_brand_organization(cli_run) -> None:
    server = Server(_create_routes(kind="brand"))

    code, result = cli_run(server, "ugc", "campaign", "+create", "--name", "Spring")

    assert code == cli.EXIT_FAILURE
    assert result["reason"] == "invalid_input"
    assert "--type tracking" in result["error"]["message"]
    assert server.writes() == []


def test_campaign_create_tracking_needs_no_kind_check_and_requires_no_platform(cli_run) -> None:
    server = Server(_create_routes(kind="brand"))

    code, _ = cli_run(server, "ugc", "campaign", "+create", "--name", "Mentions", "--type", "tracking")

    assert code == 0
    assert body(server.only_write())["required_platforms"] == []
    assert not any(r.url.path.endswith("/me/access") for r in server.requests)


def test_campaign_create_dry_run_writes_nothing(cli_run) -> None:
    server = Server(_create_routes())

    code, result = cli_run(server, "ugc", "campaign", "+create", "--name", "Spring", "--dry-run")

    assert code == 0
    assert server.writes() == []
    assert result["data"]["campaign"]["status"] == "draft"
    assert result["next_steps"]


def test_launch_without_yes_is_refused_before_any_request(cli_run) -> None:
    server = Server({("GET", f"{UGC}/campaigns/{CAMPAIGN}"): _view()})

    code, result = cli_run(server, "ugc", "campaign", "+launch", "--id", CAMPAIGN)

    assert code == cli.EXIT_FAILURE
    assert result["reason"] == "confirmation_required"
    assert server.requests == []


def test_launch_dry_run_reports_launchability_without_writing(cli_run) -> None:
    server = Server({("GET", f"{UGC}/campaigns/{CAMPAIGN}"): _view(ok=False)})

    code, result = cli_run(server, "ugc", "campaign", "+launch", "--id", CAMPAIGN, "--dry-run")

    assert code == 0
    assert server.writes() == []
    assert result["data"]["before"] == "draft" and result["data"]["after"] == "active"
    assert result["data"]["launchability"]["ok"] is False
    assert any("not ready to launch" in warning for warning in result["warnings"])


def test_launch_with_yes_sends_the_status_it_read(cli_run) -> None:
    server = Server(
        {
            ("GET", f"{UGC}/campaigns/{CAMPAIGN}"): _view(),
            ("POST", f"{UGC}/campaigns/{CAMPAIGN}/launch"): _summary("active"),
        }
    )

    code, result = cli_run(server, "ugc", "campaign", "+launch", "--id", CAMPAIGN, "--yes")

    assert code == 0
    assert body(server.only_write()) == {"expected_status": "draft"}
    assert result["data"]["after"] == "active"


@pytest.mark.parametrize(
    ("action", "status", "extra"),
    [("pause", "draft", []), ("archive", "active", ["--yes"]), ("restore", "complete", [])],
)
def test_a_move_the_status_does_not_allow_is_refused_without_writing(
    cli_run, action: str, status: str, extra: list[str]
) -> None:
    server = Server({("GET", f"{UGC}/campaigns/{CAMPAIGN}"): _view(status)})

    code, result = cli_run(server, "ugc", "campaign", f"+{action}", "--id", CAMPAIGN, *extra)

    assert code == cli.EXIT_CONFLICT
    assert result["reason"] == "conflict"
    assert "invalid_transition" in result["error"]["message"]
    assert server.writes() == []


def test_a_stale_expected_status_is_a_conflict(cli_run) -> None:
    server = Server({("GET", f"{UGC}/campaigns/{CAMPAIGN}"): _view("paused")})

    code, result = cli_run(
        server, "ugc", "campaign", "+pause", "--id", CAMPAIGN, "--expected-status", "active"
    )

    assert code == cli.EXIT_CONFLICT
    assert server.writes() == []


def test_archive_needs_yes_then_carries_the_status(cli_run) -> None:
    server = Server(
        {
            ("GET", f"{UGC}/campaigns/{CAMPAIGN}"): _view("complete"),
            ("POST", f"{UGC}/campaigns/{CAMPAIGN}/archive"): _summary("archived"),
        }
    )

    code, result = cli_run(server, "ugc", "campaign", "+archive", "--id", CAMPAIGN)
    assert result["reason"] == "confirmation_required"

    code, result = cli_run(server, "ugc", "campaign", "+archive", "--id", CAMPAIGN, "--yes")
    assert code == 0
    assert body(server.only_write()) == {"expected_status": "complete"}


def test_pause_and_resume_are_plain_writes(cli_run) -> None:
    server = Server(
        {
            ("GET", f"{UGC}/campaigns/{CAMPAIGN}"): _view("active"),
            ("POST", f"{UGC}/campaigns/{CAMPAIGN}/pause"): _summary("paused"),
        }
    )

    code, _ = cli_run(server, "ugc", "campaign", "+pause", "--id", CAMPAIGN)

    assert code == 0
    assert body(server.only_write()) == {"expected_status": "active"}


def test_rename_posts_the_new_name_and_skips_an_unchanged_one(cli_run) -> None:
    server = Server(
        {
            ("GET", f"{UGC}/campaigns/{CAMPAIGN}"): _view(),
            ("POST", f"{UGC}/campaigns/{CAMPAIGN}/rename"): _summary(name="Spring EU"),
        }
    )

    cli_run(server, "ugc", "campaign", "+rename", "--id", CAMPAIGN, "--name", "Spring")
    assert server.writes() == []

    code, _ = cli_run(server, "ugc", "campaign", "+rename", "--id", CAMPAIGN, "--name", "Spring EU")
    assert code == 0
    assert body(server.only_write()) == {"name": "Spring EU"}


# -- Campaign settings ---------------------------------------------------------


def _settings_routes(**settings: Any) -> dict[tuple[str, str], Any]:
    return {
        ("GET", f"{UGC}/campaigns/{CAMPAIGN}"): _view(**settings),
        ("PUT", f"{UGC}/campaigns/{CAMPAIGN}/settings"): _summary(updated_at=LATER),
        ("PATCH", f"{UGC}/campaigns/{CAMPAIGN}/pricing"): {"campaign_id": CAMPAIGN, "updated_at": LATER},
    }


def test_settings_update_writes_the_whole_object_with_only_the_edit_changed(cli_run) -> None:
    server = Server(_settings_routes())

    code, result = cli_run(
        server,
        "ugc", "campaign-settings", "+update", "--campaign-id", CAMPAIGN,
        "--approval-mode", "auto", "--budget-cap-cents", "500000", "--join-mode", "invite-only",
    )

    assert code == 0, result
    sent = body(server.only_write())
    expected = {
        key: value
        for key, value in _settings().items()
        if key
        not in {"public_token", "open_payscale_id", "attribution_starts_on", "brief_progress_days",
                "platform_pay_rules", "application_form"}
    }
    assert sent == {**expected, "approval_mode": "auto", "budget_cap_cents": 500000,
                    "expected_updated_at": UPDATED}
    assert [change["field"] for change in result["data"]["changes"]] == ["approval_mode", "budget_cap_cents"]


def test_settings_json_changes_only_the_nested_keys_given(cli_run) -> None:
    server = Server(_settings_routes())

    cli_run(
        server,
        "ugc", "campaign-settings", "+update", "--campaign-id", CAMPAIGN,
        "--settings-json", '{"stay_rules": {"inactivity_days": 7}}',
    )

    assert body(server.only_write())["stay_rules"] == {
        "allow_rejoin": False, "inactivity_days": 7, "max_videos_per_week": 5,
    }


def test_settings_update_refuses_a_stale_token_and_a_required_platform_not_allowed(cli_run) -> None:
    server = Server(_settings_routes())

    code, result = cli_run(
        server, "ugc", "campaign-settings", "+update", "--campaign-id", CAMPAIGN,
        "--approval-mode", "auto", "--expected-updated-at", "2026-01-01T00:00:00+00:00",
    )
    assert code == cli.EXIT_CONFLICT

    code, result = cli_run(
        server, "ugc", "campaign-settings", "+update", "--campaign-id", CAMPAIGN,
        "--required-platform", "youtube",
    )
    assert result["reason"] == "invalid_input"
    assert server.writes() == []


def test_settings_json_refuses_fields_with_their_own_flags(cli_run) -> None:
    code, result = cli_run(
        Server({}), "ugc", "campaign-settings", "+update", "--campaign-id", CAMPAIGN,
        "--settings-json", '{"approval_mode": "auto"}',
    )

    assert result["reason"] == "invalid_input"


def test_a_pay_rule_that_fits_the_stored_platforms_goes_first_and_hands_on_its_token(cli_run) -> None:
    server = Server(_settings_routes())
    rules = {"single_bps": 10000, "rules": [{"count": 2, "multiplier_bps": 12000, "platforms": ["tiktok", "instagram"]}]}

    code, _ = cli_run(
        server, "ugc", "campaign-settings", "+update", "--campaign-id", CAMPAIGN,
        "--approval-mode", "auto", "--platform-pay-rules-json", json.dumps(rules),
    )

    assert code == 0
    first, second = server.writes()
    assert (first.method, first.url.path) == ("PATCH", f"{UGC}/campaigns/{CAMPAIGN}/pricing")
    assert body(first) == {"platform_pay_rules": rules, "expected_updated_at": UPDATED}
    assert second.method == "PUT"
    assert body(second)["expected_updated_at"] == LATER


def test_a_pay_rule_on_a_newly_allowed_platform_goes_after_the_settings(cli_run) -> None:
    server = Server(_settings_routes())
    rules = {"single_bps": 10000, "rules": [{"count": 2, "multiplier_bps": 12000, "platforms": ["tiktok", "youtube"]}]}

    cli_run(
        server, "ugc", "campaign-settings", "+update", "--campaign-id", CAMPAIGN,
        "--allowed-platform", "tiktok", "--allowed-platform", "instagram", "--allowed-platform", "youtube",
        "--platform-pay-rules-json", json.dumps(rules),
    )

    first, second = server.writes()
    assert first.method == "PUT" and second.method == "PATCH"
    assert body(second)["expected_updated_at"] == LATER


def test_staff_set_replaces_one_role_and_keeps_the_other(cli_run) -> None:
    staff = {"managers": [{"id": USER_A, "name": "Ann"}], "operators": [{"id": USER_B, "name": "Bo"}], "updated_at": UPDATED}
    server = Server(
        {
            ("GET", f"{UGC}/campaigns/{CAMPAIGN}/staff"): staff,
            ("PUT", f"{UGC}/campaigns/{CAMPAIGN}/staff"): staff,
        }
    )

    code, _ = cli_run(
        server, "ugc", "campaign-staff", "+set", "--campaign-id", CAMPAIGN, "--manager-user-id", USER_B,
    )

    assert code == 0
    assert body(server.only_write()) == {
        "manager_user_ids": [USER_B], "operator_user_ids": [USER_B], "expected_updated_at": UPDATED,
    }


def _target(**extra: Any) -> dict[str, Any]:
    return {"id": TARGET, "target_views": 1000, "target_posts": None, "target_creators": None,
            "start_date": None, "due_date": "2026-12-31", "updated_at": UPDATED, **extra}


def test_delivery_target_create_needs_a_figure_and_posts_the_target(cli_run) -> None:
    server = Server(
        {
            ("GET", f"{UGC}/campaigns/{CAMPAIGN}/targets"): {"items": [], "started_on": None},
            ("POST", f"{UGC}/campaigns/{CAMPAIGN}/targets"): (201, _target()),
        }
    )

    _, result = cli_run(server, "ugc", "delivery-target", "+create", "--campaign-id", CAMPAIGN, "--due-date", "2026-12-31")
    assert result["reason"] == "invalid_input"

    code, _ = cli_run(
        server, "ugc", "delivery-target", "+create", "--campaign-id", CAMPAIGN,
        "--target-views", "1000", "--due-date", "2026-12-31",
    )
    assert code == 0
    assert body(server.only_write()) == {
        "target_views": 1000, "target_posts": None, "target_creators": None,
        "start_date": None, "due_date": "2026-12-31", "sets_campaign_start": False,
    }


def test_delivery_target_update_and_delete_carry_its_token(cli_run) -> None:
    server = Server(
        {
            ("GET", f"{UGC}/campaigns/{CAMPAIGN}/targets"): {"items": [_target()], "started_on": None},
            ("PUT", f"{UGC}/campaigns/{CAMPAIGN}/targets/{TARGET}"): _target(),
            ("DELETE", f"{UGC}/campaigns/{CAMPAIGN}/targets/{TARGET}"): None,
        }
    )

    cli_run(server, "ugc", "delivery-target", "+update", "--campaign-id", CAMPAIGN, "--id", TARGET,
            "--target-posts", "300", "--due-date", "none")
    sent = body(server.only_write())
    assert sent["target_posts"] == 300 and sent["due_date"] is None and sent["target_views"] == 1000
    assert sent["expected_updated_at"] == UPDATED

    server.requests.clear()
    _, result = cli_run(server, "ugc", "delivery-target", "+delete", "--campaign-id", CAMPAIGN, "--id", TARGET)
    assert result["reason"] == "confirmation_required"
    cli_run(server, "ugc", "delivery-target", "+delete", "--campaign-id", CAMPAIGN, "--id", TARGET, "--yes")
    deleted = server.only_write()
    assert deleted.method == "DELETE" and query(deleted) == {"expected_updated_at": UPDATED}


def test_contract_custom_dry_run_previews_without_saving_and_default_saves_the_source(cli_run) -> None:
    server = Server(
        {
            ("GET", f"{UGC}/campaigns/{CAMPAIGN}/contract-template"): {"source": "default", "body": None, "terms": []},
            ("POST", f"{UGC}/campaigns/{CAMPAIGN}/contract-template/preview"): {"body": "Hi Alex"},
            ("PUT", f"{UGC}/campaigns/{CAMPAIGN}/contract-template"): {"source": "custom"},
        }
    )
    terms = [{"name": "fee", "label": "Fee", "default_value": "$100", "states_pay": True}]

    code, result = cli_run(
        server, "ugc", "contract-template", "+set", "--campaign-id", CAMPAIGN, "--source", "custom",
        "--body", "Hi {{creator_name}}, fee {{fee}}", "--terms-json", json.dumps(terms), "--dry-run",
    )
    assert code == 0
    preview = server.only_write()
    assert preview.url.path.endswith("/contract-template/preview")
    assert body(preview) == {"body": "Hi {{creator_name}}, fee {{fee}}", "terms": terms}
    assert result["data"]["preview"] == {"body": "Hi Alex"}

    server.requests.clear()
    cli_run(server, "ugc", "contract-template", "+set", "--campaign-id", CAMPAIGN, "--source", "custom",
            "--body", "Hi", "--terms-json", "[]")
    assert body(server.only_write()) == {"source": "custom", "body": "Hi", "terms": []}


GUILD = "123456789012345678"
CHANNEL = "223456789012345678"


def test_discord_set_keeps_the_ids_of_the_same_server_and_clears_on_none(cli_run) -> None:
    link = {"guild_id": GUILD, "welcome_channel_id": CHANNEL, "help_channel_id": CHANNEL,
            "content_review_channel_id": None, "creator_role_id": CHANNEL, "visitor_role_id": None,
            "ops_role_id": None, "invite_url": "https://discord.gg/x"}
    server = Server(
        {
            ("GET", f"{UGC}/campaigns/{CAMPAIGN}/discord/guild-link"): link,
            ("PUT", f"{UGC}/campaigns/{CAMPAIGN}/discord/guild-link"): link,
        }
    )

    code, _ = cli_run(server, "ugc", "discord-server", "+set", "--campaign-id", CAMPAIGN,
                      "--guild-id", GUILD, "--help-channel-id", "none")

    assert code == 0
    assert body(server.only_write()) == {**link, "help_channel_id": None}


def test_discord_initialize_and_remove_need_yes(cli_run) -> None:
    server = Server(
        {
            ("GET", f"{UGC}/campaigns/{CAMPAIGN}/discord/guild-link"): None,
            ("POST", f"{UGC}/campaigns/{CAMPAIGN}/discord/guild/initialize"): {"guild_id": GUILD},
        }
    )

    _, result = cli_run(server, "ugc", "discord-server", "+initialize", "--campaign-id", CAMPAIGN, "--guild-id", GUILD)
    assert result["reason"] == "confirmation_required"
    _, result = cli_run(server, "ugc", "discord-server", "+remove", "--campaign-id", CAMPAIGN)
    assert result["reason"] == "confirmation_required"

    cli_run(server, "ugc", "discord-server", "+initialize", "--campaign-id", CAMPAIGN, "--guild-id", GUILD, "--yes")
    assert body(server.only_write()) == {"guild_id": GUILD}


def _dm_argv(*extra: str) -> list[str]:
    return ["ugc", "dm-rule", "+create", "--campaign-id", CAMPAIGN, "--keyword", "link",
            "--dm-message", "Here {{name}}", "--button-title", "Shop", *extra]


def test_dm_rule_create_checks_like_the_page_and_needs_yes(cli_run) -> None:
    server = Server(
        {
            ("GET", f"{UGC}/campaigns/{CAMPAIGN}/dm-rules"): [],
            ("POST", f"{UGC}/campaigns/{CAMPAIGN}/dm-rules"): (201, {"id": RULE}),
        }
    )

    _, result = cli_run(server, *_dm_argv("--destination-url", "http://brand.example", "--yes"))
    assert result["reason"] == "invalid_input"
    _, result = cli_run(server, *_dm_argv("--destination-url", "https://brand.example"))
    assert result["reason"] == "confirmation_required"

    code, _ = cli_run(server, *_dm_argv("--destination-url", "https://brand.example", "--utm-campaign", "spring", "--yes"))
    assert code == 0
    assert body(server.only_write()) == {
        "match_mode": "contains", "any_comment": False, "comment_replies": [], "utm_medium": "dm",
        "utm_campaign": "spring", "utm_parameters": ["utm_source", "utm_medium", "utm_campaign"],
        "utm_source_platform": "museon", "status": "active", "keywords": ["link"],
        "dm_message": "Here {{name}}", "button_title": "Shop", "destination_url": "https://brand.example",
    }


def test_dm_rule_update_sends_only_the_changed_fields(cli_run) -> None:
    rule = {"id": RULE, "keywords": ["link"], "match_mode": "contains", "any_comment": False,
            "dm_message": "Here", "comment_replies": [], "button_title": "Shop",
            "destination_url": "https://brand.example", "utm_medium": "dm", "utm_campaign": "x",
            "utm_parameters": ["utm_source"], "utm_source_platform": "museon", "status": "active",
            "updated_at": UPDATED}
    server = Server(
        {
            ("GET", f"{UGC}/campaigns/{CAMPAIGN}/dm-rules"): [rule],
            ("PATCH", f"{UGC}/campaigns/{CAMPAIGN}/dm-rules/{RULE}"): rule,
        }
    )

    cli_run(server, "ugc", "dm-rule", "+update", "--campaign-id", CAMPAIGN, "--id", RULE, "--status", "paused", "--yes")

    assert body(server.only_write()) == {"status": "paused", "expected_updated_at": UPDATED}


def _scales(kind: str = "custom") -> list[dict[str, Any]]:
    return [{"id": SCALE, "name": "Top", "kind": kind, "cap_per_creator_cents": 1000, "cap_reset_days": 30,
             "rates": [{"id": RATE, "kind": "anything_else", "name": "Per video", "base_fee_cents": 5000,
                        "base_rate_mode": "per_video", "base_min_views": 0}]}]


def test_payscale_update_sends_only_the_fields_passed_and_none_clears(cli_run) -> None:
    server = Server(
        {
            ("GET", f"{UGC}/campaigns/{CAMPAIGN}/payscales"): _scales(),
            ("PATCH", f"{UGC}/payscales/{SCALE}"): _scales()[0],
        }
    )

    cli_run(server, "ugc", "payscale", "+update", "--campaign-id", CAMPAIGN, "--id", SCALE,
            "--cap-per-creator-cents", "none")

    assert body(server.only_write()) == {"cap_per_creator_cents": None}


def test_payscale_delete_refuses_a_default_scale(cli_run) -> None:
    server = Server({("GET", f"{UGC}/campaigns/{CAMPAIGN}/payscales"): _scales(kind="default")})

    code, _ = cli_run(server, "ugc", "payscale", "+delete", "--campaign-id", CAMPAIGN, "--id", SCALE, "--yes")

    assert code == cli.EXIT_CONFLICT
    assert server.writes() == []


def test_pay_rate_update_previews_on_dry_run_and_writes_the_rate_whole(cli_run) -> None:
    server = Server(
        {
            ("GET", f"{UGC}/campaigns/{CAMPAIGN}/payscales"): _scales(),
            ("POST", f"{UGC}/campaigns/{CAMPAIGN}/pay-preview/draft"): {"points": []},
            ("PUT", f"{UGC}/pay-rates/{RATE}"): {"id": RATE},
        }
    )

    cli_run(server, "ugc", "pay-rate", "+update", "--campaign-id", CAMPAIGN, "--id", RATE,
            "--rate-json", '{"base_fee_cents": 6000}', "--dry-run")
    preview = server.only_write()
    assert preview.url.path.endswith("/pay-preview/draft")
    assert body(preview)["rate"]["kind"] == "anything_else"
    assert body(preview)["rate"]["base_fee_cents"] == 6000

    server.requests.clear()
    cli_run(server, "ugc", "pay-rate", "+update", "--campaign-id", CAMPAIGN, "--id", RATE,
            "--rate-json", '{"base_fee_cents": 6000}')
    sent = body(server.only_write())
    assert sent["base_fee_cents"] == 6000 and sent["name"] == "Per video" and "kind" not in sent


# -- Formats (briefs) ------------------------------------------------------------


def _brief_view(version: int = 2, status: str = "active") -> dict[str, Any]:
    return {
        "brief": {"id": BRIEF, "title": "Hook", "status": status, "current_version": version},
        "current": {"version": version, "content": "Open on it.", "references": [],
                    "required_caption": None, "require_ad_disclosure": False},
        "versions": [],
        "linked_campaign_ids": [CAMPAIGN],
    }


def test_brief_library_list_reads_the_organization_library(cli_run) -> None:
    server = Server({("GET", f"{UGC}/organizations/{ORG}/briefs"): {"items": [_brief_view()["brief"]], "next_cursor": None}})

    code, result = cli_run(server, "ugc", "brief-library", "+list", "--search", "hook", "--status", "archived")

    assert code == 0
    assert query(server.requests[0]) == {"status": "archived", "search": "hook", "limit": "50"}
    assert result["data"]["items"][0]["id"] == BRIEF


def test_brief_library_create_names_the_organization_and_an_idempotency_key(cli_run) -> None:
    server = Server({("POST", f"{UGC}/briefs"): (201, _brief_view(version=1))})

    code, result = cli_run(server, "ugc", "brief-library", "+create", "--title", "Hook",
                           "--content", "Open on it.", "--idempotency-key", "k-1")

    assert code == 0
    sent = server.only_write()
    assert query(sent) == {"organization_id": ORG}
    assert sent.headers["Idempotency-Key"] == "k-1"
    assert body(sent) == {"title": "Hook", "content": "Open on it.", "references": [],
                          "required_caption": None, "require_ad_disclosure": False}
    assert result["data"]["idempotency_key"] == "k-1"


def test_brief_library_update_checks_the_version_then_patches_the_merged_document(cli_run) -> None:
    server = Server(
        {
            ("GET", f"{UGC}/briefs/{BRIEF}"): _brief_view(),
            ("PATCH", f"{UGC}/briefs/{BRIEF}"): _brief_view(version=3),
        }
    )

    code, _ = cli_run(server, "ugc", "brief-library", "+update", "--id", BRIEF, "--expected-version", "1", "--title", "New")
    assert code == cli.EXIT_CONFLICT
    assert server.writes() == []

    code, result = cli_run(server, "ugc", "brief-library", "+update", "--id", BRIEF, "--expected-version", "2", "--title", "New")
    assert code == 0
    assert body(server.only_write()) == {"title": "New", "content": "Open on it.", "references": [],
                                         "required_caption": None, "require_ad_disclosure": False,
                                         "expected_version": 2}
    assert any("1 Campaign uses" in warning for warning in result["warnings"])


def test_brief_library_archive_needs_yes_and_sends_the_version(cli_run) -> None:
    server = Server(
        {
            ("GET", f"{UGC}/briefs/{BRIEF}"): _brief_view(),
            ("POST", f"{UGC}/briefs/{BRIEF}/archive"): _brief_view(status="archived")["brief"],
        }
    )

    _, result = cli_run(server, "ugc", "brief-library", "+archive", "--id", BRIEF, "--expected-version", "2")
    assert result["reason"] == "confirmation_required"

    cli_run(server, "ugc", "brief-library", "+archive", "--id", BRIEF, "--expected-version", "2", "--yes")
    assert query(server.only_write()) == {"expected_version": "2"}


def test_brief_library_copy_copies_the_current_version(cli_run) -> None:
    server = Server(
        {
            ("GET", f"{UGC}/briefs/{BRIEF}"): _brief_view(),
            ("POST", f"{UGC}/briefs/{BRIEF}/copy"): (201, _brief_view(version=1)),
        }
    )

    code, result = cli_run(server, "ugc", "brief-library", "+copy", "--id", BRIEF)

    assert code == 0
    sent = server.only_write()
    assert query(sent) == {"version": "2"}
    assert sent.headers["Idempotency-Key"] == result["data"]["idempotency_key"]


def test_brief_create_in_a_campaign_carries_the_persona_and_a_key(cli_run) -> None:
    server = Server(
        {
            ("GET", f"{UGC}/campaigns/{CAMPAIGN}/briefs"): [],
            ("POST", f"{UGC}/campaigns/{CAMPAIGN}/brief-documents"): (201, _brief_view(version=1)),
        }
    )

    code, _ = cli_run(server, "ugc", "brief", "+create", "--campaign-id", CAMPAIGN, "--title", "Hook",
                      "--content", "Open on it.", "--persona-id", PERSONA)

    assert code == 0
    sent = server.only_write()
    assert body(sent)["persona_id"] == PERSONA
    assert sent.headers["Idempotency-Key"]


def test_brief_link_replaces_and_unlink_needs_yes(cli_run) -> None:
    server = Server(
        {
            ("GET", f"{UGC}/briefs/{BRIEF}"): _brief_view(),
            ("GET", f"{UGC}/campaigns/{CAMPAIGN}/briefs"): [{"id": OTHER_BRIEF, "title": "Old", "status": "active"}],
            ("PUT", f"{UGC}/campaigns/{CAMPAIGN}/brief-links/{BRIEF}"): None,
            ("DELETE", f"{UGC}/campaigns/{CAMPAIGN}/brief-links/{OTHER_BRIEF}"): None,
        }
    )

    code, _ = cli_run(server, "ugc", "brief", "+link", "--campaign-id", CAMPAIGN, "--id", BRIEF, "--replaces", OTHER_BRIEF)
    assert code == 0
    assert query(server.only_write()) == {"replaces": OTHER_BRIEF}

    server.requests.clear()
    _, result = cli_run(server, "ugc", "brief", "+unlink", "--campaign-id", CAMPAIGN, "--id", OTHER_BRIEF)
    assert result["reason"] == "confirmation_required"
    cli_run(server, "ugc", "brief", "+unlink", "--campaign-id", CAMPAIGN, "--id", OTHER_BRIEF, "--yes")
    assert server.only_write().method == "DELETE"


def test_brief_copy_into_a_campaign_keeps_the_source_when_asked(cli_run) -> None:
    server = Server(
        {
            ("GET", f"{UGC}/briefs/{BRIEF}"): _brief_view(),
            ("POST", f"{UGC}/campaigns/{CAMPAIGN}/brief-documents/{BRIEF}/copy"): (201, _brief_view(version=1)),
        }
    )

    cli_run(server, "ugc", "brief", "+copy", "--campaign-id", CAMPAIGN, "--id", BRIEF,
            "--persona-id", PERSONA, "--keep-source")

    assert query(server.only_write()) == {"version": "2", "persona_id": PERSONA, "keep_source": "true"}


# -- Personas --------------------------------------------------------------------


def _personas() -> dict[str, Any]:
    return {"items": [
        {"id": PERSONA, "title": "Busy mom", "description": "", "updated_at": UPDATED},
        {"id": OTHER_PERSONA, "title": "Student", "description": "", "updated_at": UPDATED},
    ]}


def test_persona_create_refuses_a_taken_title_and_posts_a_new_one(cli_run) -> None:
    server = Server(
        {
            ("GET", f"{UGC}/personas"): _personas(),
            ("POST", f"{UGC}/personas"): (201, {"id": "x", "title": "Gamer"}),
        }
    )

    code, _ = cli_run(server, "ugc", "persona", "+create", "--title", "busy MOM")
    assert code == cli.EXIT_CONFLICT
    assert server.writes() == []

    code, _ = cli_run(server, "ugc", "persona", "+create", "--title", "Gamer", "--description", "Plays")
    assert code == 0
    assert body(server.only_write()) == {"title": "Gamer", "description": "Plays"}


def test_persona_update_patches_only_the_edit_and_delete_needs_yes(cli_run) -> None:
    server = Server(
        {
            ("GET", f"{UGC}/personas"): _personas(),
            ("PATCH", f"{UGC}/personas/{PERSONA}"): {"id": PERSONA, "title": "Working mom"},
            ("DELETE", f"{UGC}/personas/{PERSONA}"): None,
        }
    )

    cli_run(server, "ugc", "persona", "+update", "--id", PERSONA, "--title", "Working mom")
    assert body(server.only_write()) == {"title": "Working mom"}

    server.requests.clear()
    _, result = cli_run(server, "ugc", "persona", "+delete", "--id", PERSONA)
    assert result["reason"] == "confirmation_required"
    cli_run(server, "ugc", "persona", "+delete", "--id", PERSONA, "--yes")
    assert server.only_write().method == "DELETE"
