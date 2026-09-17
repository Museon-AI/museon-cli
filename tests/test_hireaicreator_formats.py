"""Format maintenance contracts including explicit empty-vs-null edits."""

import asyncio
import json

import httpx
import pytest

import museoncli.main as cli
from museoncli.config import AuthState, Config, WorkspaceState

W = "40000000-0000-4000-8000-000000000004"
ID = "10000000-0000-4000-8000-000000000001"
CLIENT = httpx.AsyncClient


@pytest.fixture
def requests(monkeypatch):
    seen = []
    monkeypatch.setattr(
        cli,
        "load_config",
        lambda: Config(
            api_base_url="https://api.example.test/api/v1",
            workspace=WorkspaceState(id=W),
            auth=AuthState(api_key="test-key"),
        ),
    )

    def handle(request):
        seen.append(request)
        return (
            httpx.Response(204)
            if request.method == "DELETE"
            else httpx.Response(200, json={"id": ID, "status": "processing"})
        )

    monkeypatch.setattr(
        cli.httpx, "AsyncClient", lambda **kw: CLIENT(**kw, transport=httpx.MockTransport(handle))
    )
    return seen


def run(action, payload, *flags):
    return asyncio.run(
        cli.dispatch(
            cli.build_parser().parse_args(
                [
                    "hireaicreator",
                    "format",
                    "+" + action,
                    "--args-json",
                    json.dumps(payload),
                    *flags,
                ]
            )
        )
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "Renamed", "expected_version": 2},
        {"viral_playbook_override": ""},
        {"viral_playbook_override": None, "pov_id": ID},
        {"bgm_id": ID, "expected_version": None},
    ],
)
def test_patch_preserves_omissions_nulls_and_empty_string(requests, payload):
    run("patch", {"id": ID, **payload})
    r = requests[0]
    assert (r.method, r.url.path) == ("PATCH", "/api/v2/ai-hook-formats/" + ID)
    assert dict(r.url.params) == {"workspace_id": W}
    assert json.loads(r.content) == payload
    assert "Idempotency-Key" not in r.headers


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"name": " "},
        {"bgm_id": None},
        {"expected_version": 2},
        {"name": "name", "expected_version": 0},
    ],
)
def test_empty_or_invalid_patch_never_calls_api(requests, payload):
    with pytest.raises(ValueError):
        run("patch", {"id": ID, **payload})
    assert not requests


@pytest.mark.parametrize("step", ["ingest", "hook", "pov", "bgm", "viral"])
def test_retry_requires_confirmation_and_sends_exact_step(requests, step):
    with pytest.raises(RuntimeError, match="confirmation_required"):
        run("retry", {"id": ID, "step": step})
    assert not requests
    run("retry", {"id": ID, "step": step}, "--yes")
    r = requests[0]
    assert r.url.path == "/api/v2/ai-hook-formats/" + ID + "/retry"
    assert dict(r.url.params) == {"workspace_id": W}
    assert json.loads(r.content) == {"step": step}


@pytest.mark.parametrize(
    "action,payload",
    [
        ("patch", {"id": ID, "name": "Name"}),
        ("retry", {"id": ID, "step": "hook"}),
        ("delete", {"id": ID}),
    ],
)
def test_dry_run_does_not_send(requests, action, payload):
    run(action, payload, "--dry-run")
    assert not requests


def test_delete_204_and_confirmation(requests):
    with pytest.raises(RuntimeError, match="confirmation_required"):
        run("delete", {"id": ID})
    assert not requests
    result = run("delete", {"id": ID}, "--yes")
    assert result["data"] is None
    assert requests[0].method == "DELETE"
    assert dict(requests[0].url.params) == {"workspace_id": W}


def test_readiness_is_body_scoped_read_and_tags_is_query_scoped(requests):
    run("warmup-readiness", {"format_ids": [ID]})
    r = requests[0]
    assert r.method == "POST" and r.url.path == "/api/v2/ai-hook-formats/warmup-readiness"
    assert not r.url.query
    assert json.loads(r.content) == {"format_ids": [ID], "workspace_id": W}
    run("tags", {})
    assert requests[1].method == "GET"
    assert requests[1].url.path == "/api/v2/ai-hook-formats/tags"
    assert dict(requests[1].url.params) == {"workspace_id": W}
