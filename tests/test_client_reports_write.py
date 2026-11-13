from __future__ import annotations

import pytest
from routes_stub import ORG, Server, assert_organization_only, body, query, run, refused

CAMPAIGN = "11111111-1111-4111-8111-111111111111"
REPORT = "77777777-7777-4777-8777-777777777777"
BASE = f"/api/v2/ugc/agency/campaigns/{CAMPAIGN}/client-reports"
CUSTOMER = {"id": "oc_client", "name": "Client group", "channel": "feishu", "status": "connected"}
INTERNAL = {"id": "oc_team", "name": "Team group", "channel": "feishu", "status": "connected"}


def _report(**extra) -> dict:
    return {
        "id": REPORT,
        "campaignId": CAMPAIGN,
        "type": "daily",
        "title": "Daily 11-12",
        "markdown": "# Views 1,000",
        "dataScope": "all",
        "publicLink": None,
        "appearance": {"language": "zh", "channel": "feishu"},
        "languageVariants": {},
        "periodStart": "2026-11-12",
        "periodEnd": "2026-11-13",
        "revision": 4,
        "status": "ready",
        "actionCapabilities": {"send": {"enabled": True, "blockers": []}},
        **extra,
    }


def _communication(**extra) -> dict:
    return {
        "campaignId": CAMPAIGN,
        "version": 9,
        "internalGroup": INTERNAL,
        "customerGroup": None,
        "weeklyMeeting": {
            "id": "m1",
            "weekday": 2,
            "timezone": "Asia/Shanghai",
            "effectiveFrom": "2026-10-01",
            "generateTime": "08:00",
            "operatorDueTime": "11:00",
        },
        "timezone": None,
        "weeklySchedule": None,
        "dailyGenerateTime": "09:00",
        "dailyOperatorDueTime": "12:00",
        "dailyReviewDueTime": "18:00",
        "ownerUserId": None,
        "reviewerUserId": None,
        "defaultAppearance": {"language": "zh"},
        "enabledReportTypes": ["daily"],
        "reportDataScope": "approved",
        "automationEnabled": True,
        "taskCardsEnabled": False,
        "taskCardsSince": None,
        "ownerUserIds": [],
        "reviewerUserIds": [],
        **extra,
    }


def _workspace(report: dict | None = None, **communication) -> dict:
    return {
        "communication": _communication(**communication),
        "reports": [report or _report()],
        "candidates": [CUSTOMER, INTERNAL],
        "capabilities": {},
        "persistence": "server",
    }


def _assert_operator_organization(server: Server) -> None:
    assert_organization_only(server)
    for request in server.requests:
        # The route's name for the operator organization; its value is the organization.
        assert query(request)["agency_workspace_id"] == ORG


def test_send_without_yes_is_refused_with_a_preview_of_where_it_would_go(monkeypatch: pytest.MonkeyPatch) -> None:
    server = Server({("GET", BASE): _workspace(customerGroup=CUSTOMER)})

    result = refused(monkeypatch, server, ["ugc", "client-report", "+send", "--campaign-id", CAMPAIGN, "--id", REPORT])

    assert server.writes() == []
    assert query(server.requests[0])["report_id"] == REPORT
    assert result["data"]["dry_run"] is True
    assert result["data"]["destination"] == "Client group"
    assert any("--yes" in step for step in result["next_steps"])
    _assert_operator_organization(server)


def test_send_with_yes_carries_revision_binding_and_a_stable_key(monkeypatch: pytest.MonkeyPatch) -> None:
    server = Server(
        {
            ("GET", BASE): _workspace(customerGroup=CUSTOMER),
            ("POST", f"{BASE}/{REPORT}/actions/send"): _report(status="sent"),
        }
    )

    result = run(
        monkeypatch, server, ["ugc", "client-report", "+send", "--campaign-id", CAMPAIGN, "--id", REPORT, "--yes"]
    )

    assert body(server.writes()[0]) == {
        "expectedRevision": 4,
        "bindingVersion": 9,
        # The same revision and settings give the same key: a rerun never sends twice.
        "idempotencyKey": f"cli:send:{REPORT}:4:9",
    }
    assert result["data"]["report"]["status"] == "sent"
    _assert_operator_organization(server)


def test_send_test_goes_to_the_test_action(monkeypatch: pytest.MonkeyPatch) -> None:
    server = Server({("GET", BASE): _workspace(), ("POST", f"{BASE}/{REPORT}/actions/test"): _report()})

    run(
        monkeypatch,
        server,
        ["ugc", "client-report", "+send", "--campaign-id", CAMPAIGN, "--id", REPORT, "--test", "--yes"],
    )

    assert [request.url.path for request in server.writes()] == [f"{BASE}/{REPORT}/actions/test"]


def test_blocked_send_is_reported_in_the_preview(monkeypatch: pytest.MonkeyPatch) -> None:
    blocked = _report(actionCapabilities={"send": {"enabled": False, "blockers": [{"code": "not_approved"}]}})
    server = Server({("GET", BASE): _workspace(blocked)})

    result = refused(monkeypatch, server, ["ugc", "client-report", "+send", "--campaign-id", CAMPAIGN, "--id", REPORT])

    assert any("not_approved" in warning for warning in result["warnings"])


def test_skip_sends_its_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    server = Server({("GET", BASE): _workspace(), ("POST", f"{BASE}/{REPORT}/actions/skip"): _report()})

    run(
        monkeypatch,
        server,
        ["ugc", "client-report", "+skip", "--campaign-id", CAMPAIGN, "--id", REPORT, "--reason", " Paused "],
    )

    assert body(server.writes()[0])["reason"] == "Paused"


def test_update_with_a_stale_revision_warns_and_sends_it(monkeypatch: pytest.MonkeyPatch) -> None:
    server = Server({("GET", BASE): _workspace(), ("PATCH", f"{BASE}/{REPORT}"): _report(revision=5)})
    argv = ["ugc", "client-report", "+update", "--campaign-id", CAMPAIGN, "--id", REPORT,
            "--title", "Daily 11-12 (final)", "--expected-revision", "3"]

    preview = run(monkeypatch, server, [*argv, "--dry-run"])
    assert server.writes() == []
    assert any("revision 4, not 3" in warning for warning in preview["warnings"])

    run(monkeypatch, server, argv)

    sent = body(server.writes()[0])
    assert sent["expectedRevision"] == 3
    assert sent["title"] == "Daily 11-12 (final)"
    # The rest of the document travels back unchanged.
    assert sent["markdown"] == "# Views 1,000"
    assert sent["appearance"] == {"language": "zh", "channel": "feishu"}


def test_refresh_dry_run_asks_the_server_preview_and_never_applies(monkeypatch: pytest.MonkeyPatch) -> None:
    proposal = {
        "id": "99999999-9999-4999-8999-999999999999",
        "changes": [
            {"id": "views", "label": "Views", "before": "1,000", "after": "1,200"},
            {"id": "posts", "label": "Posts", "before": "3", "after": "4"},
        ],
    }
    server = Server(
        {
            ("GET", BASE): _workspace(),
            ("POST", f"{BASE}/{REPORT}/refresh-preview"): proposal,
            ("POST", f"{BASE}/{REPORT}/refresh-apply"): _report(revision=5),
        }
    )
    argv = ["ugc", "client-report", "+refresh", "--campaign-id", CAMPAIGN, "--id", REPORT, "--keep-change", "posts"]

    preview = run(monkeypatch, server, [*argv, "--dry-run"])
    assert [request.url.path for request in server.writes()] == [f"{BASE}/{REPORT}/refresh-preview"]
    assert [change["apply"] for change in preview["data"]["changes"]] == [True, False]

    run(monkeypatch, server, argv)

    apply = body(server.writes()[-1])
    assert apply["proposalId"] == proposal["id"]
    assert apply["choices"] == [{"id": "views", "useSource": True}, {"id": "posts", "useSource": False}]
    assert apply["expectedRevision"] == 4


def test_create_dry_run_lists_reports_covering_the_date(monkeypatch: pytest.MonkeyPatch) -> None:
    server = Server({("GET", BASE): _workspace()})

    result = run(
        monkeypatch,
        server,
        ["ugc", "client-report", "+create", "--campaign-id", CAMPAIGN, "--type", "daily",
         "--date", "2026-11-12", "--dry-run"],
    )

    assert server.writes() == []
    assert [item["id"] for item in result["data"]["existing_reports_for_date"]] == [REPORT]


def test_create_posts_the_report_request(monkeypatch: pytest.MonkeyPatch) -> None:
    server = Server({("POST", BASE): _report(status="draft")})

    run(
        monkeypatch,
        server,
        ["ugc", "client-report", "+create", "--campaign-id", CAMPAIGN, "--type", "weekly",
         "--date", "2026-11-12", "--language", "en"],
    )

    assert body(server.requests[0]) == {"type": "weekly", "date": "2026-11-12", "language": "en"}
    _assert_operator_organization(server)


def test_config_update_writes_the_settings_back_with_its_version(monkeypatch: pytest.MonkeyPatch) -> None:
    server = Server(
        {
            ("GET", BASE): _workspace(),
            ("PUT", f"{BASE}/communication"): _communication(version=10),
        }
    )

    result = run(
        monkeypatch,
        server,
        ["ugc", "client-report-config", "+update", "--campaign-id", CAMPAIGN, "--enable", "weekly",
         "--weekly-weekday", "fri", "--customer-group-id", "oc_client", "--daily-due-time", "13:00"],
    )

    sent = body(server.writes()[0])
    assert sent["expectedVersion"] == 9
    written = sent["communication"]
    assert written["enabledReportTypes"] == ["daily", "weekly"]
    # An older Campaign's weekly schedule comes from its meeting, then the edit applies.
    assert written["weeklySchedule"] == {"weekday": 5, "generateTime": "08:00", "submissionDueTime": "11:00"}
    assert written["customerGroup"] == CUSTOMER
    assert written["dailyOperatorDueTime"] == "13:00"
    assert written["timezone"] == "Asia/Shanghai"
    # Read-only and derived fields never travel back.
    for derived in ("automationEnabled", "taskCardsSince", "ownerUserIds", "reviewerUserIds"):
        assert derived not in written
    assert {item["field"] for item in result["data"]["changes"]} >= {
        "enabled_report_types", "weekly_weekday", "customer_group", "daily_due_time",
    }
    _assert_operator_organization(server)


def test_config_update_refuses_a_group_the_campaign_cannot_use(monkeypatch: pytest.MonkeyPatch) -> None:
    server = Server({("GET", BASE): _workspace()})

    with pytest.raises(ValueError, match="not one of the groups"):
        run(
            monkeypatch,
            server,
            ["ugc", "client-report-config", "+update", "--campaign-id", CAMPAIGN, "--customer-group-id", "oc_x"],
        )
    assert server.writes() == []
