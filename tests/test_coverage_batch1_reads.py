"""Batch 1 reads call the web's own routes, addressed by the organization, never a workspace.

A read that sent the wrong id, the wrong query name or no organization would answer an
empty page or a 404 rather than fail loudly, so the request each command sends is
pinned here, with the envelope it returns.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest

import museoncli.main as cli
from museoncli.config import AuthState, Config, OrganizationState

ORG = "70000000-0000-4000-8000-000000000001"
CAMPAIGN = "20000000-0000-4000-8000-000000000002"
TASK = "30000000-0000-4000-8000-000000000003"
ENROLLMENT = "40000000-0000-4000-8000-000000000004"
CREATOR = "50000000-0000-4000-8000-000000000005"
BOARD = "60000000-0000-4000-8000-000000000006"
REPORT = "80000000-0000-4000-8000-000000000008"
COLLECTION_A = "90000000-0000-4000-8000-00000000000a"
COLLECTION_B = "90000000-0000-4000-8000-00000000000b"
CLIENT = httpx.AsyncClient

BOARD_BODY = {
    "id": BOARD,
    "name": "Q4",
    "campaign_type": "mixed",
    "campaigns": [
        {"id": CAMPAIGN, "monitor_collection_id": COLLECTION_B, "available": True},
        {"id": "x", "monitor_collection_id": COLLECTION_A, "available": True},
        {"id": "y", "monitor_collection_id": "gone", "available": False},
    ],
    "filters": {
        "date_from": "2026-11-01",
        "date_to": "2026-11-10",
        "platform": None,
        "post_scope": "approved",
    },
}
REPORTS_BODY = {
    "communication": {"version": 3, "daily": True},
    "capabilities": {"edit": {"allowed": True}},
    "candidates": [],
    "internal_group_access": None,
    "reports": [
        {"id": REPORT, "type": "daily", "title": "Day", "status": "ready", "markdown": "# hi"},
        {"id": "other", "type": "weekly", "title": "Week", "status": "sent", "markdown": "# w"},
    ],
}


@pytest.fixture
def server(monkeypatch):
    state: dict[str, Any] = {"requests": [], "refuse": set()}
    monkeypatch.setattr(
        cli,
        "load_config",
        lambda: Config(
            api_base_url="https://api.example.test/api/v1",
            organization=OrganizationState(id=ORG, name="Brand"),
            auth=AuthState(api_key="test-key"),
        ),
    )

    def handle(request: httpx.Request) -> httpx.Response:
        state["requests"].append(request)
        path = request.url.path
        if any(path.endswith(suffix) for suffix in state["refuse"]):
            return httpx.Response(404, json={"code": "campaign_not_found"})
        if path == f"/api/v1/analytics-dashboards/{BOARD}":
            return httpx.Response(200, json=BOARD_BODY)
        if path.endswith("/client-reports"):
            return httpx.Response(200, json=REPORTS_BODY)
        if path.endswith("/events"):
            return httpx.Response(200, json=[{"type": "comment", "body": "ok"}])
        return httpx.Response(200, json={"items": [], "next_cursor": None})

    monkeypatch.setattr(
        cli.httpx, "AsyncClient", lambda **kw: CLIENT(**kw, transport=httpx.MockTransport(handle))
    )
    return state


def run(*argv: str) -> dict:
    return asyncio.run(cli.dispatch(cli.build_parser().parse_args(list(argv))))


def fail(*argv: str) -> dict:
    with pytest.raises(Exception) as raised:
        run(*argv)
    return cli.error_envelope(raised.value, command=None)[0]


def query(request: httpx.Request) -> dict[str, list[str]]:
    params: dict[str, list[str]] = {}
    for key, value in request.url.params.multi_items():
        params.setdefault(key, []).append(value)
    return params


def assert_organization_only(request: httpx.Request) -> None:
    assert request.method == "GET"
    assert request.headers["X-Organization-Id"] == ORG
    assert not [name for name in request.headers if "workspace" in name.lower()]
    assert not [key for key in request.url.params if "workspace" in key]


@pytest.mark.parametrize(
    ("argv", "path", "expected"),
    [
        (
            ["ugc", "task", "+list"],
            f"/api/v2/ugc/agency/{ORG}/tasks",
            {"limit": ["50"]},
        ),
        (
            [
                "ugc",
                "task",
                "+list",
                "--queue",
                "client-reports",
                "--campaign-id",
                CAMPAIGN,
                "--actor",
                "operator",
                "--scope",
                "my-campaigns",
                "--country",
                "US",
                "--country",
                "GB",
                "--posted-from",
                "2026-11-01",
                "--timezone",
                "Asia/Shanghai",
                "--sort",
                "newest",
                "--page-size",
                "20",
                "--cursor",
                "c1",
            ],
            f"/api/v2/ugc/agency/{ORG}/tasks",
            {
                "queue": ["client_reports"],
                "campaign": [CAMPAIGN],
                "actor": ["operator"],
                "scope": ["my_campaigns"],
                "country": ["US", "GB"],
                "posted_from": ["2026-11-01"],
                "timezone": ["Asia/Shanghai"],
                "sort": ["newest"],
                "limit": ["20"],
                "cursor": ["c1"],
            },
        ),
        (
            ["ugc", "task-summary", "+get", "--scope", "all"],
            f"/api/v2/ugc/agency/{ORG}/tasks/summary",
            {"scope": ["all"]},
        ),
        (
            ["ugc", "campaign-settings", "+get", "--campaign-id", CAMPAIGN],
            f"/api/v2/ugc/campaigns/{CAMPAIGN}",
            {},
        ),
        (
            ["ugc", "campaign-staff", "+list", "--campaign-id", CAMPAIGN],
            f"/api/v2/ugc/campaigns/{CAMPAIGN}/staff",
            {},
        ),
        (
            ["ugc", "delivery-target", "+list", "--campaign-id", CAMPAIGN],
            f"/api/v2/ugc/campaigns/{CAMPAIGN}/targets",
            {},
        ),
        (
            ["ugc", "payscale", "+list", "--campaign-id", CAMPAIGN],
            f"/api/v2/ugc/campaigns/{CAMPAIGN}/payscales",
            {},
        ),
        (
            ["ugc", "contract-template", "+get", "--campaign-id", CAMPAIGN],
            f"/api/v2/ugc/campaigns/{CAMPAIGN}/contract-template",
            {},
        ),
        (
            ["ugc", "discord-server", "+get", "--campaign-id", CAMPAIGN],
            f"/api/v2/ugc/campaigns/{CAMPAIGN}/discord/guild-link",
            {},
        ),
        (
            ["ugc", "dm-rule", "+list", "--campaign-id", CAMPAIGN],
            f"/api/v2/ugc/campaigns/{CAMPAIGN}/dm-rules",
            {},
        ),
        (
            ["ugc", "dm-automation", "+list", "--campaign-id", CAMPAIGN],
            f"/api/v2/ugc/campaigns/{CAMPAIGN}/dm-automations",
            {},
        ),
        (
            ["ugc", "message", "+list", "--enrollment-id", ENROLLMENT, "--page-size", "10"],
            f"/api/v2/ugc/enrollments/{ENROLLMENT}/conversation",
            {"limit": ["10"]},
        ),
        (
            ["ugc", "enrollment", "+get-contract", "--enrollment-id", ENROLLMENT],
            f"/api/v2/ugc/enrollments/{ENROLLMENT}/contract",
            {},
        ),
        (
            ["ugc", "creator", "+list", "--search", "maya"],
            f"/api/v2/ugc/agency/{ORG}/creators",
            {"q": ["maya"], "limit": ["50"]},
        ),
        (
            ["ugc", "creator", "+get", "--id", CREATOR],
            f"/api/v2/ugc/agency/{ORG}/creators/{CREATOR}",
            {},
        ),
        (
            ["analytics", "board", "+list"],
            "/api/v1/analytics-dashboards",
            {"scope": ["organization"], "organization_id": [ORG]},
        ),
        (
            ["analytics", "board", "+get", "--id", BOARD],
            f"/api/v1/analytics-dashboards/{BOARD}",
            {},
        ),
        (
            ["organization", "member", "+list"],
            f"/api/v1/organizations/{ORG}/members",
            {},
        ),
        (
            ["organization", "billing", "+get"],
            f"/api/v1/billing/organizations/{ORG}/overview",
            {},
        ),
    ],
)
def test_each_read_calls_the_webs_route(server, argv, path, expected):
    result = run(*argv)

    (request,) = server["requests"]
    assert request.url.path == path
    assert query(request) == expected
    assert_organization_only(request)
    assert set(result) == {"command", "data", "next_steps", "run", "warnings", "organization"}
    assert result["organization"]["id"] == ORG
    assert result["data"] in ({"items": [], "next_cursor": None}, BOARD_BODY)


def test_a_task_is_read_with_its_events(server):
    result = run("ugc", "task", "+get", "--id", TASK)

    task, events = server["requests"]
    assert task.url.path == f"/api/v2/ugc/tasks/{TASK}"
    assert events.url.path == f"/api/v2/ugc/tasks/{TASK}/events"
    assert result["data"]["events"] == [{"type": "comment", "body": "ok"}]
    for request in server["requests"]:
        assert_organization_only(request)


def test_a_task_without_events_is_one_read(server):
    result = run("ugc", "task", "+get", "--id", TASK, "--no-with-events")

    assert [r.url.path for r in server["requests"]] == [f"/api/v2/ugc/tasks/{TASK}"]
    assert set(result["data"]) == {"task"}


def test_campaign_setup_reads_every_section_and_reports_the_unreadable(server):
    """A member reads the Campaign view but not its operations: the command answers what
    the caller may read, with the rest under `unavailable`, instead of failing."""
    server["refuse"] = {"/payscales", "/staff"}

    result = run("ugc", "campaign-setup", "+get", "--campaign-id", CAMPAIGN)

    paths = sorted(
        r.url.path.removeprefix(f"/api/v2/ugc/campaigns/{CAMPAIGN}") for r in server["requests"]
    )
    assert paths == sorted(
        [
            "",
            "/staff",
            "/targets",
            "/payscales",
            "/contract-template",
            "/discord/guild-link",
            "/dm-rules",
            "/dm-automations",
        ]
    )
    data = result["data"]
    assert set(data["unavailable"]) == {"payscales", "staff"}
    assert data["unavailable"]["payscales"]["http_status"] == 404
    assert data["unavailable"]["payscales"]["code"] == "campaign_not_found"
    assert "settings" in data["sections"] and "contract-template" in data["sections"]


def test_campaign_setup_reads_only_the_named_sections(server):
    run(
        "ugc",
        "campaign-setup",
        "+get",
        "--campaign-id",
        CAMPAIGN,
        "--section",
        "contract-template",
        "--section",
        "dm-rules",
    )

    assert sorted(r.url.path for r in server["requests"]) == [
        f"/api/v2/ugc/campaigns/{CAMPAIGN}/contract-template",
        f"/api/v2/ugc/campaigns/{CAMPAIGN}/dm-rules",
    ]


def test_campaign_setup_with_nothing_readable_fails(server):
    server["refuse"] = {""}

    result = fail("ugc", "campaign-setup", "+get", "--campaign-id", CAMPAIGN, "--section", "staff")

    assert result["ok"] is False and result["reason"] == "not_found"


def test_client_reports_name_the_organization_and_list_summaries(server):
    result = run("ugc", "client-report", "+list", "--campaign-id", CAMPAIGN, "--status", "ready")

    (request,) = server["requests"]
    assert request.url.path == f"/api/v2/ugc/agency/campaigns/{CAMPAIGN}/client-reports"
    assert query(request) == {"organization_id": [ORG]}
    assert_organization_only(request)
    assert [item["id"] for item in result["data"]["items"]] == [REPORT]
    assert "markdown" not in result["data"]["items"][0]


def test_a_client_report_is_read_in_full(server):
    result = run("ugc", "client-report", "+get", "--campaign-id", CAMPAIGN, "--report-id", REPORT)

    (request,) = server["requests"]
    assert query(request) == {"organization_id": [ORG], "report_id": [REPORT]}
    assert result["data"]["markdown"] == "# hi"


def test_a_report_the_campaign_does_not_have_is_not_found(server):
    other = "80000000-0000-4000-8000-0000000000ff"

    result = fail("ugc", "client-report", "+get", "--campaign-id", CAMPAIGN, "--report-id", other)

    assert result["reason"] == "not_found"


def test_client_report_settings_carry_their_version(server):
    result = run("ugc", "client-report-config", "+get", "--campaign-id", CAMPAIGN)

    assert result["data"]["communication"] == {"version": 3, "daily": True}
    assert "reports" not in result["data"]


def test_board_figures_read_the_boards_campaigns_with_its_saved_filters(server):
    result = run("analytics", "board", "+get-data", "--id", BOARD)

    board, figures = server["requests"]
    assert board.url.path == f"/api/v1/analytics-dashboards/{BOARD}"
    assert figures.url.path == "/api/v2/monitor-collection-sets/content-trends"
    assert query(figures) == {
        "collection_id": [COLLECTION_A, COLLECTION_B],
        "link_status": ["linked"],
        "date_from": ["2026-11-01"],
        "date_to": ["2026-11-10"],
        "performance_as_of": ["latest"],
    }
    assert result["data"]["collection_ids"] == [COLLECTION_A, COLLECTION_B]
    for request in server["requests"]:
        assert_organization_only(request)


def test_board_core_metrics_take_the_period_and_flags_override_the_board(server):
    run(
        "analytics",
        "board",
        "+get-data",
        "--id",
        BOARD,
        "--widget",
        "core-metrics",
        "--date-from",
        "2026-10-01",
        "--scope",
        "all",
        "--timezone",
        "UTC",
    )

    _, figures = server["requests"]
    assert figures.url.path == "/api/v1/monitor-collection-sets/report/widgets/core-metrics"
    assert query(figures) == {
        "collection_id": [COLLECTION_A, COLLECTION_B],
        "timezone": ["UTC"],
        "link_status": ["not_excluded"],
        "current_period_start": ["2026-10-01"],
        "current_period_end": ["2026-11-10"],
    }


def test_board_posts_page_through_the_set(server):
    run(
        "analytics",
        "board",
        "+get-data",
        "--id",
        BOARD,
        "--widget",
        "content",
        "--page",
        "2",
        "--page-size",
        "25",
        "--platform",
        "tiktok",
    )

    _, figures = server["requests"]
    assert figures.url.path == "/api/v2/monitor-collection-sets/content"
    assert query(figures)["page"] == ["2"]
    assert query(figures)["limit"] == ["25"]
    assert query(figures)["platform"] == ["tiktok"]


@pytest.mark.parametrize(
    "argv",
    [
        ["ugc", "task", "+list"],
        ["ugc", "creator", "+list"],
        ["analytics", "board", "+list"],
        ["organization", "member", "+list"],
        ["ugc", "client-report", "+list", "--campaign-id", CAMPAIGN],
    ],
)
def test_organization_addressed_reads_need_an_organization(server, monkeypatch, argv):
    monkeypatch.setattr(
        cli,
        "load_config",
        lambda: Config(
            api_base_url="https://api.example.test/api/v1", auth=AuthState(api_key="test-key")
        ),
    )

    result = fail(*argv)

    assert result["reason"] == "missing_organization"
    assert server["requests"] == []


def test_another_organization_can_be_named_for_one_call(server):
    other = "70000000-0000-4000-8000-0000000000ff"

    run("organization", "member", "+list", "--organization-id", other)

    (request,) = server["requests"]
    assert request.url.path == f"/api/v1/organizations/{other}/members"
    assert request.headers["X-Organization-Id"] == other
