"""Warmup HTTP contracts: mixed query/body, CAS and activation consent."""

import asyncio
import json

import httpx
import pytest

from museoncli.config import AuthState, Config, WorkspaceState
import museoncli.main as cli

W = "40000000-0000-4000-8000-000000000004"
ID = "10000000-0000-4000-8000-000000000001"
ACCOUNT = "20000000-0000-4000-8000-000000000002"
FORMAT = "30000000-0000-4000-8000-000000000003"
BASE = "/api/v2/pool-account-warmup"
PATH = BASE + "/strategies/" + ID
CONFIG = {
    "name": "Example warmup",
    "content": {"format_ids": [FORMAT], "hook_ids": []},
    "onboard_rule": {"qualified_post_count": 3, "views_strictly_greater_than": 100},
    "terminate_rule": {
        "consecutive_low_view_days": 3,
        "views_strictly_less_than": 10,
        "max_action_days": 14,
        "evidence_maturity_hours": 0,
    },
    "publish_time": "09:30",
    "campaign_id": None,
    "confirm_demo_reuse_for_automation": False,
}
CREATE = {
    **CONFIG,
    "accounts": [{"pool_account_id": ACCOUNT, "timezone": "Asia/Shanghai"}],
    "action_type": "ai-hook",
}
# Expected HTTP shapes are written independently of the production route table.
CASES = [
    ("get", {"id": ID}, "GET", PATH, {"workspace_id": W}, None),
    (
        "create",
        CREATE,
        "POST",
        BASE + "/strategies",
        {},
        {**CREATE, "action_type": "ai_hook", "workspace_id": W},
    ),
    (
        "replace",
        {"id": ID, **CREATE, "expected_version": 3},
        "PUT",
        PATH,
        {},
        {**CREATE, "action_type": "ai_hook", "workspace_id": W, "expected_version": 3},
    ),
    (
        "configure",
        {"id": ID, **CONFIG, "expected_version": 4},
        "PATCH",
        PATH + "/configuration",
        {},
        {**CONFIG, "workspace_id": W, "expected_version": 4},
    ),
    (
        "accounts",
        {
            "id": ID,
            "status": ["warming", "terminated"],
            "device_kind": "real-device",
            "page": 2,
            "page_size": 10,
            "search": "example",
        },
        "GET",
        PATH + "/accounts",
        {
            "workspace_id": W,
            "status": ["warming", "terminated"],
            "device_kind": "real_device",
            "page": 2,
            "page_size": 10,
            "search": "example",
        },
        None,
    ),
    (
        "add-accounts",
        {"id": ID, "accounts": CREATE["accounts"], "expected_version": 5},
        "POST",
        PATH + "/accounts",
        {},
        {"accounts": CREATE["accounts"], "expected_version": 5, "workspace_id": W},
    ),
    (
        "remove-accounts",
        {"id": ID, "pool_account_ids": [ACCOUNT], "expected_version": 6},
        "POST",
        PATH + "/accounts/remove",
        {},
        {"pool_account_ids": [ACCOUNT], "expected_version": 6, "workspace_id": W},
    ),
    (
        "account-stats",
        {"id": ID, "pool_account_ids": [ACCOUNT, FORMAT]},
        "GET",
        PATH + "/account-stats",
        {"workspace_id": W, "pool_account_ids": [ACCOUNT, FORMAT]},
        None,
    ),
    (
        "readiness",
        {"pool_account_ids": [ACCOUNT], "action_type": "ai-hook"},
        "POST",
        BASE + "/accounts/readiness",
        {},
        {"workspace_id": W, "pool_account_ids": [ACCOUNT], "action_type": "ai_hook"},
    ),
    ("preview", {"id": ID}, "POST", PATH + "/preview", {"workspace_id": W}, {}),
    (
        "check-and-start",
        {"id": ID, "expected_version": 7, "expected_format_revisions": {FORMAT: "rev-2"}},
        "POST",
        PATH + "/check-and-start",
        {"workspace_id": W},
        {"expected_version": 7, "expected_format_revisions": {FORMAT: "rev-2"}},
    ),
    (
        "activate",
        {"id": ID, "expected_version": 8},
        "POST",
        PATH + "/activate",
        {"workspace_id": W},
        {"expected_version": 8},
    ),
    (
        "pause",
        {"id": ID, "expected_version": 9},
        "POST",
        PATH + "/pause",
        {"workspace_id": W},
        {"expected_version": 9},
    ),
    (
        "resume",
        {"id": ID, "expected_version": 10, "campaign_id": FORMAT},
        "POST",
        PATH + "/resume",
        {"workspace_id": W},
        {"expected_version": 10, "campaign_id": FORMAT},
    ),
    (
        "reset",
        {"id": ID, "pool_account_ids": [ACCOUNT]},
        "POST",
        PATH + "/journeys/reset",
        {},
        {"workspace_id": W, "pool_account_ids": [ACCOUNT]},
    ),
    ("journey-get", {"id": ID}, "GET", BASE + "/journeys/" + ID, {"workspace_id": W}, None),
    ("deletion-preview", {"id": ID}, "GET", PATH + "/deletion", {"workspace_id": W}, None),
    (
        "delete",
        {"id": ID, "expected_version": 11},
        "DELETE",
        PATH,
        {"workspace_id": W, "expected_version": 11},
        {},
    ),
]
CONFIRM = {"remove-accounts", "check-and-start", "activate", "pause", "resume", "reset", "delete"}
READS = {
    "get",
    "accounts",
    "account-stats",
    "readiness",
    "preview",
    "journey-get",
    "deletion-preview",
}
CLIENT = httpx.AsyncClient


@pytest.fixture
def requests(monkeypatch):
    seen = []
    cfg = Config(
        api_base_url="https://api.example.test/api/v1",
        workspace=WorkspaceState(id=W),
        auth=AuthState(api_key="test-key"),
    )
    monkeypatch.setattr(cli, "load_config", lambda: cfg)

    def handle(request):
        seen.append(request)
        if request.method == "DELETE":
            return httpx.Response(204)
        return httpx.Response(
            200,
            json={
                "id": ID,
                "status": "draft",
                "version": 12,
                "started": False,
                "blocker_codes": ["content_not_ready"],
            },
        )

    monkeypatch.setattr(
        cli.httpx, "AsyncClient", lambda **kw: CLIENT(**kw, transport=httpx.MockTransport(handle))
    )
    return seen


def run(action, payload, *flags):
    args = cli.build_parser().parse_args(
        ["hireaicreator", "warmup", "+" + action, "--args-json", json.dumps(payload), *flags]
    )
    return asyncio.run(cli.dispatch(args))


@pytest.mark.parametrize("action,payload,method,path,query,body", CASES, ids=[c[0] for c in CASES])
def test_http_contract(requests, action, payload, method, path, query, body):
    result = run(action, payload, *(["--yes"] if action in CONFIRM else []))
    assert result["command"] == "hireaicreator.warmup-" + action
    assert len(requests) == 1
    req = requests[0]
    assert (req.method, req.url.path) == (method, path)
    expected = [(k, str(x)) for k, v in query.items() for x in (v if isinstance(v, list) else [v])]
    assert sorted(req.url.params.multi_items()) == sorted(expected)
    assert (json.loads(req.content) if req.content else None) in (
        [None, {}] if body == {} else [body]
    )
    assert "Idempotency-Key" not in req.headers
    assert req.headers["X-Museon-CLI-Command"] == "hireaicreator.warmup-" + action
    if action == "check-and-start":
        assert result["data"]["started"] is False
        assert result["data"]["blocker_codes"] == ["content_not_ready"]


@pytest.mark.parametrize("action,payload", [(c[0], c[1]) for c in CASES if c[0] not in READS])
def test_dry_run_never_calls_api(requests, action, payload):
    run(action, payload, "--dry-run")
    assert requests == []


@pytest.mark.parametrize("action,payload", [(c[0], c[1]) for c in CASES if c[0] in CONFIRM])
def test_sensitive_writes_require_confirmation(requests, action, payload):
    with pytest.raises(RuntimeError, match="confirmation_required"):
        run(action, payload)
    assert requests == []


@pytest.mark.parametrize(
    "action,payload",
    [
        ("activate", {"id": ID}),
        ("delete", {"id": ID, "expected_version": 0}),
        ("create", {**CREATE, "publish_time": "25:00"}),
        ("create", {**CREATE, "accounts": [{"pool_account_id": ACCOUNT, "timezone": "Not/AZone"}]}),
        (
            "check-and-start",
            {"id": ID, "expected_version": 1, "expected_format_revisions": {"not-uuid": "rev"}},
        ),
        ("reset", {"id": ID, "pool_account_ids": []}),
        ("create", {**CREATE, "idempotency_key": "not-supported"}),
    ],
)
def test_invalid_input_rejected_before_http(requests, action, payload):
    with pytest.raises(ValueError):
        run(action, payload, *(["--yes"] if action in CONFIRM else []))
    assert requests == []


def test_explicit_workspace_overrides_saved_default(requests):
    run("get", {"id": ID, "workspace_id": FORMAT})
    assert requests[0].url.params["workspace_id"] == FORMAT


@pytest.mark.parametrize("status", [403, 409])
def test_rejection_is_not_automatically_refreshed_or_retried(monkeypatch, status):
    calls = []
    cfg = Config(
        api_base_url="https://api.example.test/api/v1",
        workspace=WorkspaceState(id=W),
        auth=AuthState(api_key="test-key"),
    )
    monkeypatch.setattr(cli, "load_config", lambda: cfg)

    def reject(request):
        calls.append(request)
        return httpx.Response(
            status, json={"detail": {"code": "version_conflict" if status == 409 else "forbidden"}}
        )

    monkeypatch.setattr(
        cli.httpx, "AsyncClient", lambda **kw: CLIENT(**kw, transport=httpx.MockTransport(reject))
    )
    with pytest.raises(RuntimeError if status == 403 else cli.ApiRequestError):
        run("activate", {"id": ID, "expected_version": 1}, "--yes")
    assert len(calls) == 1
    assert json.loads(calls[0].content)["expected_version"] == 1
