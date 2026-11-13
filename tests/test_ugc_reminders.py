from __future__ import annotations

import pytest
from routes_stub import Server, assert_organization_only, body, run, refused

CAMPAIGN = "11111111-1111-4111-8111-111111111111"
BASE = f"/api/v2/ugc/campaigns/{CAMPAIGN}"
DELEGATION = "99999999-9999-4999-8999-999999999993"
LAYER = {
    "timezone": None,
    "workdays": ["mon", "tue", "wed", "thu", "fri"],
    "off_days": None,
    "feishu_enabled": None,
    "overdue_escalation": True,
    "task_kinds": None,
    "morning_digest": None,
    "evening_digest": None,
    "digest_rules": [{"id": "am", "time": "09:00"}],
    "updated_at": "2026-11-11T02:00:00Z",
}


def _settings(**layer) -> dict:
    return {
        "covered": True,
        "uncovered": [],
        "campaign_layer": {**LAYER, **layer},
        "effective": {"feishu_enabled": False},
        "delegations": [{"id": DELEGATION, "user_id": "u1", "delegate_user_id": "u2"}],
        "subscribed": False,
    }


def test_reminder_update_replaces_the_layer_with_its_version(monkeypatch: pytest.MonkeyPatch) -> None:
    server = Server(
        {
            ("GET", f"{BASE}/reminder-settings"): _settings(),
            ("PUT", f"{BASE}/reminder-settings"): _settings(feishu_enabled=True),
        }
    )

    run(
        monkeypatch,
        server,
        ["ugc", "reminder", "+update", "--campaign-id", CAMPAIGN, "--feishu", "on",
         "--workday", "inherit", "--digest-time", "09:00", "--digest-time", "17:30",
         "--task-kind", "review-creative"],
    )

    sent = body(server.writes()[0])
    assert sent["expected_updated_at"] == "2026-11-11T02:00:00Z"
    assert sent["feishu_enabled"] is True
    assert sent["workdays"] is None  # inherit
    assert sent["task_kinds"] == ["review_creative"]
    # A time already in the layer keeps its rule id.
    assert sent["digest_rules"] == [{"id": "am", "time": "09:00"}, {"id": "cli-1730", "time": "17:30"}]
    # Fields not passed stay as stored: the write replaces the whole layer.
    assert sent["overdue_escalation"] is True
    assert "updated_at" not in sent
    assert_organization_only(server)


def test_reminder_update_dry_run_writes_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    server = Server({("GET", f"{BASE}/reminder-settings"): _settings()})

    result = run(
        monkeypatch, server, ["ugc", "reminder", "+update", "--campaign-id", CAMPAIGN, "--feishu", "off", "--dry-run"]
    )

    assert server.writes() == []
    assert result["data"]["changes"] == [{"field": "feishu_enabled", "before": None, "after": False}]


def test_reminder_update_rejects_an_unknown_task_kind(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValueError, match="--task-kind"):
        run(monkeypatch, Server({}), ["ugc", "reminder", "+update", "--campaign-id", CAMPAIGN, "--task-kind", "x"])


def test_auto_nudge_without_yes_is_refused_with_a_preview_then_writes_with_its_version(monkeypatch: pytest.MonkeyPatch) -> None:
    current = {
        "checks": ["not_set_up"],
        "days": ["mon"],
        "send_at": "10:00",
        "timezone": "Asia/Shanghai",
        "updated_at": "2026-11-01T00:00:00Z",
        "next_send_at": None,
        "recent": [],
    }
    server = Server({("GET", f"{BASE}/auto-nudge"): current, ("PUT", f"{BASE}/auto-nudge"): current})
    argv = ["ugc", "auto-nudge", "+update", "--campaign-id", CAMPAIGN, "--check", "quiet", "--day", "thu", "--day", "mon"]

    preview = refused(monkeypatch, server, argv)
    assert server.writes() == []
    assert preview["data"]["dry_run"] is True

    run(monkeypatch, server, [*argv, "--yes"])

    assert body(server.writes()[0]) == {
        "checks": ["quiet"],
        "days": ["mon", "thu"],
        "send_at": "10:00",
        "timezone": "Asia/Shanghai",
        "expected_updated_at": "2026-11-01T00:00:00Z",
    }


def test_auto_nudge_off_clears_the_days(monkeypatch: pytest.MonkeyPatch) -> None:
    current = {"checks": ["quiet"], "days": ["mon"], "send_at": "10:00", "timezone": "UTC", "updated_at": None}
    server = Server({("GET", f"{BASE}/auto-nudge"): current, ("PUT", f"{BASE}/auto-nudge"): current})

    run(monkeypatch, server, ["ugc", "auto-nudge", "+update", "--campaign-id", CAMPAIGN, "--off", "--yes"])

    assert body(server.writes()[0])["days"] == []


def test_delegation_cancel_unknown_is_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    server = Server({("GET", f"{BASE}/reminder-settings"): _settings()})

    with pytest.raises(RuntimeError, match="not_found"):
        run(
            monkeypatch,
            server,
            ["ugc", "reminder-delegation", "+cancel", "--campaign-id", CAMPAIGN,
             "--id", "99999999-9999-4999-8999-999999999990", "--yes"],
        )
    assert server.writes() == []


def test_delegation_cancel_with_yes_deletes_it(monkeypatch: pytest.MonkeyPatch) -> None:
    server = Server(
        {
            ("GET", f"{BASE}/reminder-settings"): _settings(),
            ("DELETE", f"{BASE}/reminder-delegations/{DELEGATION}"): {"delegations": []},
        }
    )

    result = run(
        monkeypatch,
        server,
        ["ugc", "reminder-delegation", "+cancel", "--campaign-id", CAMPAIGN, "--id", DELEGATION, "--yes"],
    )

    assert result["data"]["delegations"] == []


def test_reminder_test_needs_yes(monkeypatch: pytest.MonkeyPatch) -> None:
    server = Server(
        {
            ("GET", f"{BASE}/reminder-settings"): _settings(),
            ("POST", f"{BASE}/reminder-settings/test"): {"outcome": "no_direct_chat"},
        }
    )

    refused(monkeypatch, server, ["ugc", "reminder", "+test", "--campaign-id", CAMPAIGN])
    assert server.writes() == []

    result = run(monkeypatch, server, ["ugc", "reminder", "+test", "--campaign-id", CAMPAIGN, "--yes"])
    assert result["data"]["test"] == {"outcome": "no_direct_chat"}
    assert any("Mel" in warning for warning in result["warnings"])
