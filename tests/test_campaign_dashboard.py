"""Campaign reads call the web's own routes, addressed as the web addresses them.

A command that sent the wrong id, organization or review filter would answer an empty
page or a 404 rather than fail loudly, so the request each one sends is pinned here.
"""

import asyncio

import httpx
import pytest

import museoncli.main as cli
from museoncli.config import AuthState, Config, OrganizationState

CAMPAIGN = "20000000-0000-4000-8000-000000000002"
CONTENT = "50000000-0000-4000-8000-000000000005"
CREATOR = "60000000-0000-4000-8000-000000000006"
CLIENT = httpx.AsyncClient


@pytest.fixture
def server(monkeypatch):
    state = {"requests": [], "campaigns": []}
    monkeypatch.setattr(
        cli,
        "load_config",
        lambda: Config(
            api_base_url="https://api.example.test/api/v1",
            organization=OrganizationState(id="org-1", name="MuseOn"),
            auth=AuthState(api_key="test-key"),
        ),
    )

    def handle(request: httpx.Request) -> httpx.Response:
        state["requests"].append(request)
        if request.url.path == f"/api/v2/ugc/collections/{CAMPAIGN}/campaign":
            return httpx.Response(200, json={"id": CAMPAIGN, "campaign_type": "ugc"})
        if request.url.path == f"/api/v1/agent-cli/campaign-monitors/{CAMPAIGN}":
            tracking = {"domain": "campaign-monitor", "operation": "get", "result": {"id": CAMPAIGN}}
            return httpx.Response(200, json={"success": True, "data": tracking})
        return httpx.Response(200, json={"items": state["campaigns"], "next_cursor": None})

    monkeypatch.setattr(
        cli.httpx, "AsyncClient", lambda **kw: CLIENT(**kw, transport=httpx.MockTransport(handle))
    )
    return state


def run(*argv: str, domain: str = "campaign") -> dict:
    return asyncio.run(cli.dispatch(cli.build_parser().parse_args([domain, *argv])))


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
        "--campaign-id",
        CAMPAIGN,
        "--sort",
        "views-desc",
        "--page",
        "3",
        "--page-size",
        "20",
        *flags,
    )

    (read,) = server["requests"]
    assert read.url.path == f"/api/v2/ugc/agency/campaigns/{CAMPAIGN}/content"
    params = query(read)
    assert params.pop("source") == ["merged"] and params.pop("date_field") == ["post_date"]
    assert params.pop("sort") == ["views_desc"]
    assert (params.pop("offset"), params.pop("limit")) == (["40"], ["20"])
    assert params == expected


@pytest.mark.parametrize("status", ["confirmation", "not-counted"])
def test_approved_videos_refuse_a_status_they_cannot_have(server, status):
    result = fail(
        "video", "+list", "--campaign-id", CAMPAIGN, "--scope", "approved", "--status", status
    )

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
def test_campaign_reads_are_addressed_by_the_campaign_id(server, argv, path, expected):
    """One read each: the Campaign's id is what every route takes, nothing is resolved first."""
    domain = "ugc" if argv[0] in ("creator-check", "assignment") else "campaign"
    resource, action, *flags = argv
    run(resource, action, "--campaign-id", CAMPAIGN, *flags, domain=domain)

    assert [r.url.path for r in server["requests"]] == [path]
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
def test_report_widgets_read_v1_with_each_widgets_window(server, widget, path, expected):
    run(
        "report",
        "+get",
        "--campaign-id",
        CAMPAIGN,
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
    assert request.url.path == f"/api/v1/monitor-collections/{CAMPAIGN}/report/widgets/{path}"
    assert query(request) == {**expected, "link_status": ["linked"]}


def test_organization_reads_are_addressed_by_the_selected_organization(server):
    """A brand organization reads its own Campaigns and those shared into it as the web does:
    the path names the organization the command acts in, never only the operator one."""
    run("+list", "--with-progress")

    (read,) = server["requests"]
    assert read.url.path == "/api/v2/ugc/agency/org-1/campaigns/progress"
    assert read.headers["X-Organization-Id"] == "org-1"


def test_the_list_reads_both_kinds_and_narrows_on_request(server):
    server["campaigns"] = [
        {"id": "a", "campaign_type": "tracking", "status": "active"},
        {"id": "b", "campaign_type": "tracking", "status": "draft"},
    ]
    result = run("+list", "--type", "tracking", "--status", "active", "--search", "spring")

    (read,) = server["requests"]
    assert read.url.path == "/api/v2/ugc/agency/org-1/campaigns"
    assert query(read) == {"q": ["spring"], "campaign_type": ["tracking"], "limit": ["50"]}
    assert [item["id"] for item in result["data"]["items"]] == ["a"]

    run("+list", "--status", "archived")
    assert query(last(server)) == {"archived": ["true"], "limit": ["50"]}


def test_progress_refuses_filters_it_cannot_apply(server):
    result = fail("+list", "--with-progress", "--type", "ugc")

    assert result["reason"] == "invalid_input"
    assert server["requests"] == []


def test_get_reads_the_header_and_the_tracking_record(server):
    result = run("+get", "--campaign-id", CAMPAIGN)

    assert sorted(r.url.path for r in server["requests"]) == [
        f"/api/v1/agent-cli/campaign-monitors/{CAMPAIGN}",
        f"/api/v2/ugc/collections/{CAMPAIGN}/campaign",
    ]
    assert result["data"]["campaign"]["campaign_type"] == "ugc"
    assert result["data"]["tracking"] == {"id": CAMPAIGN}


@pytest.mark.parametrize(
    "argv", [["+list"], ["analytics", "+get", "--all-time"]]
)
def test_no_organization_at_all_is_refused_before_any_read(server, monkeypatch, argv):
    monkeypatch.setattr(
        cli,
        "load_config",
        lambda: Config(
            api_base_url="https://api.example.test/api/v1",
            auth=AuthState(api_key="test-key"),
        ),
    )

    result = fail(*argv)

    assert result["ok"] is False
    assert result["reason"] == "missing_organization", result
    assert server["requests"] == []


def test_payments_address_the_selected_organization(server):
    """The payments routes read X-Organization-Id; no workspace is looked up or sent."""
    run("payment", "+list", "--bucket", "pending-approval")

    (request,) = server["requests"]
    assert request.url.path == "/api/v2/ugc/payments"
    assert request.headers["X-Organization-Id"] == "org-1"
    assert query(request) == {"bucket": ["pending_approval"], "limit": ["50"]}


def test_a_campaign_the_caller_cannot_read_is_not_found(server, monkeypatch):
    def handle(request: httpx.Request) -> httpx.Response:
        server["requests"].append(request)
        return httpx.Response(
            404, json={"code": "campaign_not_found", "message": "campaign_not_found"}
        )

    monkeypatch.setattr(
        cli.httpx, "AsyncClient", lambda **kw: CLIENT(**kw, transport=httpx.MockTransport(handle))
    )

    result = fail("payout", "+list", "--campaign-id", CAMPAIGN)

    assert result["ok"] is False and result["reason"] == "not_found"
    assert len(server["requests"]) == 1
    assert result["error"]["server_code"] == "campaign_not_found"


def test_payments_read_another_organization_by_header(server):
    """A Brand reads another organization's payments with --organization-id, by header only."""
    other = "70000000-0000-4000-8000-000000000007"
    run("payment", "+list", "--organization-id", other)

    (request,) = server["requests"]
    assert request.headers["X-Organization-Id"] == other
    assert "workspace_id" not in query(request)
