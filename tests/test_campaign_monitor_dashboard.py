"""Campaign Dashboard reads call the web Dashboard's own routes, addressed as it addresses them.

A command that sent the monitor collection id where the route wants the UGC campaign id,
or the wrong review filter, would answer an empty page or a 404 rather than fail loudly,
so the request each one sends is pinned here.
"""

import asyncio

import httpx
import pytest

import museoncli.main as cli
from museoncli.config import AuthState, Config, WorkspaceState

W = "40000000-0000-4000-8000-000000000004"
COLLECTION = "10000000-0000-4000-8000-000000000001"
CAMPAIGN = "20000000-0000-4000-8000-000000000002"
AGENCY = "30000000-0000-4000-8000-000000000003"
CONTENT = "50000000-0000-4000-8000-000000000005"
CREATOR = "60000000-0000-4000-8000-000000000006"
CLIENT = httpx.AsyncClient


@pytest.fixture
def server(monkeypatch):
    state = {"requests": [], "agency": {"enabled": True, "organization_id": AGENCY}}
    monkeypatch.setattr(
        cli,
        "load_config",
        lambda: Config(
            api_base_url="https://api.example.test/api/v1",
            workspace=WorkspaceState(id=W),
            auth=AuthState(api_key="test-key"),
        ),
    )

    def handle(request: httpx.Request) -> httpx.Response:
        state["requests"].append(request)
        if request.url.path == f"/api/v2/ugc/collections/{COLLECTION}/campaign":
            return httpx.Response(200, json={"id": CAMPAIGN, "campaign_type": "ugc"})
        if request.url.path == "/api/v2/ugc/agency/me":
            return httpx.Response(200, json=state["agency"])
        return httpx.Response(200, json={"items": [], "next_cursor": None})

    monkeypatch.setattr(
        cli.httpx, "AsyncClient", lambda **kw: CLIENT(**kw, transport=httpx.MockTransport(handle))
    )
    return state


def run(*argv: str) -> dict:
    return asyncio.run(cli.dispatch(cli.build_parser().parse_args(["campaign-monitor", *argv])))


def fail(*argv: str) -> dict:
    """The failure as the CLI prints it: the stable error envelope."""
    with pytest.raises(Exception) as raised:
        run(*argv)
    return cli.error_envelope(raised.value, command=None)[0]


def last(server: dict) -> httpx.Request:
    return server["requests"][-1]


def query(request: httpx.Request) -> dict[str, list[str]]:
    params: dict[str, list[str]] = {}
    for key, value in request.url.params.multi_items():
        params.setdefault(key, []).append(value)
    return params


@pytest.mark.parametrize(
    ("flags", "expected"),
    [
        ([], {"link_status": ["not_excluded"]}),
        (
            ["--status", "confirmation"],
            {"link_status": ["not_excluded"], "awaiting": ["confirmation"]},
        ),
        (["--status", "review"], {"link_status": ["not_excluded"], "awaiting": ["review"]}),
        (["--status", "not-counted"], {"link_status": ["excluded"]}),
        (["--scope", "approved"], {"link_status": ["linked"]}),
        (
            ["--scope", "approved", "--status", "review"],
            {"link_status": ["linked"], "awaiting": ["review"]},
        ),
    ],
)
def test_videos_read_the_ugc_campaign_with_the_content_tabs_filters(server, flags, expected):
    run(
        "video",
        "+list",
        "--id",
        COLLECTION,
        "--sort",
        "views-desc",
        "--page",
        "3",
        "--page-size",
        "20",
        *flags,
    )

    resolve, read = server["requests"]
    assert resolve.url.path == f"/api/v2/ugc/collections/{COLLECTION}/campaign"
    assert read.url.path == f"/api/v2/ugc/agency/campaigns/{CAMPAIGN}/content"
    params = query(read)
    assert params.pop("source") == ["merged"] and params.pop("date_field") == ["post_date"]
    assert params.pop("sort") == ["views_desc"]
    assert (params.pop("offset"), params.pop("limit")) == (["40"], ["20"])
    assert params == expected


@pytest.mark.parametrize("status", ["confirmation", "not-counted"])
def test_approved_videos_refuse_a_status_they_cannot_have(server, status):
    result = fail("video", "+list", "--id", COLLECTION, "--scope", "approved", "--status", status)

    assert result["ok"] is False and result["reason"] == "invalid_input"
    assert server["requests"] == []


@pytest.mark.parametrize(
    ("argv", "path", "expected"),
    [
        (
            ["roster", "+list", "--sort", "avg-views", "--cursor", "c1", "--page-size", "25"],
            f"/api/v2/ugc/campaigns/{CAMPAIGN}/roster",
            {"sort": ["avg_views"], "cursor": ["c1"], "limit": ["25"]},
        ),
        (
            ["video", "+get", "--content-id", CONTENT, "--section", "daily", "--scope", "approved"],
            f"/api/v2/ugc/agency/campaigns/{CAMPAIGN}/content/{CONTENT}/detail/daily",
            {"link_status": ["linked"]},
        ),
        (
            [
                "audience",
                "+get",
                "--by",
                "period",
                "--date-from",
                "2026-10-01",
                "--date-to",
                "2026-10-28",
            ],
            f"/api/v2/ugc/campaigns/{CAMPAIGN}/analytics/period-audience",
            {"date_from": ["2026-10-01"], "date_to": ["2026-10-28"]},
        ),
        (
            ["settlement", "+get", "--date-from", "2026-10-01", "--date-to", "2026-10-31"],
            f"/api/v2/ugc/campaigns/{CAMPAIGN}/payouts/preview/summary",
            {"period_start": ["2026-10-01"], "period_end": ["2026-10-31"]},
        ),
        (
            [
                "settlement",
                "+get",
                "--date-from",
                "2026-10-01",
                "--date-to",
                "2026-10-31",
                "--creator-id",
                CREATOR,
                "--timezone",
                "Asia/Shanghai",
            ],
            f"/api/v2/ugc/campaigns/{CAMPAIGN}/payouts/preview",
            {
                "period_start": ["2026-10-01"],
                "period_end": ["2026-10-31"],
                "ugc_creator_id": [CREATOR],
                "tz": ["Asia/Shanghai"],
            },
        ),
        (
            ["creator-check", "+list", "--kind", "not-in-discord"],
            f"/api/v2/ugc/campaigns/{CAMPAIGN}/creator-checks",
            {"kind": ["not_in_discord"], "limit": ["50"]},
        ),
        (
            ["assignment", "+list", "--status", "in-progress"],
            f"/api/v2/ugc/campaigns/{CAMPAIGN}/assignments",
            {"status": ["in_progress"], "limit": ["50"]},
        ),
    ],
)
def test_ugc_campaign_reads_are_addressed_by_the_resolved_campaign(server, argv, path, expected):
    resource, action, *flags = argv
    run(resource, action, "--id", COLLECTION, *flags)

    assert [r.url.path for r in server["requests"]] == [
        f"/api/v2/ugc/collections/{COLLECTION}/campaign",
        path,
    ]
    assert query(last(server)) == expected


@pytest.mark.parametrize(
    ("widget", "path", "expected"),
    [
        (
            "cumulative-views",
            "cumulative-views",
            {"date_from": ["2026-10-01"], "date_to": ["2026-10-28"]},
        ),
        (
            "content-tiers",
            "content-tier-breakdown",
            {"current_period_start": ["2026-10-01"], "current_period_end": ["2026-10-28"]},
        ),
        (
            "creator-countries",
            "creator-country-distribution",
            {"current_period_start": ["2026-10-01"], "current_period_end": ["2026-10-28"]},
        ),
    ],
)
def test_report_widgets_read_the_collection_on_v1_with_each_widgets_window(
    server, widget, path, expected
):
    run(
        "report",
        "+get",
        "--id",
        COLLECTION,
        "--widget",
        widget,
        "--date-from",
        "2026-10-01",
        "--date-to",
        "2026-10-28",
        "--scope",
        "approved",
    )

    (request,) = server["requests"]
    assert request.url.path == f"/api/v1/monitor-collections/{COLLECTION}/report/widgets/{path}"
    assert query(request) == {**expected, "link_status": ["linked"]}


def test_agency_reads_are_addressed_by_the_callers_agency(server):
    run("agency-campaign", "+list", "--campaign-type", "ugc", "--with-progress")

    me, read = server["requests"]
    assert me.url.path == "/api/v2/ugc/agency/me"
    assert read.url.path == f"/api/v2/ugc/agency/{AGENCY}/campaigns/progress"


def test_a_login_off_the_agency_team_is_refused_before_any_agency_read(server):
    server["agency"] = {"enabled": False, "organization_id": None}

    result = fail("agency-analytics", "+get", "--all-time")

    assert result["ok"] is False and result["reason"] == "forbidden"
    assert [r.url.path for r in server["requests"]] == ["/api/v2/ugc/agency/me"]


def test_payments_read_the_selected_workspace(server):
    run("payment", "+list", "--bucket", "pending-approval")

    (request,) = server["requests"]
    assert request.url.path == "/api/v2/ugc/payments"
    assert query(request) == {"workspace_id": [W], "bucket": ["pending_approval"], "limit": ["50"]}


def test_a_campaign_no_ugc_campaign_stands_for_is_not_found(server, monkeypatch):
    def handle(request: httpx.Request) -> httpx.Response:
        server["requests"].append(request)
        return httpx.Response(
            404, json={"code": "campaign_not_found", "message": "campaign_not_found"}
        )

    monkeypatch.setattr(
        cli.httpx, "AsyncClient", lambda **kw: CLIENT(**kw, transport=httpx.MockTransport(handle))
    )

    result = fail("payout", "+list", "--id", COLLECTION)

    assert result["ok"] is False and result["reason"] == "not_found"
    assert len(server["requests"]) == 1, "nothing is read past the campaign that is not there"
    assert result["error"]["server_code"] == "campaign_not_found"
