"""Local video delivery must resume uploads without duplicating publication tasks."""

import asyncio
import json
from datetime import datetime

import httpx
import pytest

import museoncli.main as cli
from museoncli.config import AuthState, Config, WorkspaceState

WS = "40000000-0000-4000-8000-000000000004"
ACCOUNT = "50000000-0000-4000-8000-000000000005"
MEDIA = "60000000-0000-4000-8000-000000000006"
HTTP_CLIENT = httpx.AsyncClient


def invoke(arguments):
    return asyncio.run(
        cli.dispatch(
            cli.build_parser().parse_args(
                ["hireaicreator", "video", "+publish-local", "--args-json", json.dumps(arguments)]
            )
        )
    )


def setup(monkeypatch, tmp_path, handler):
    cfg = Config(
        api_base_url="https://api.example.test/api/v1",
        workspace=WorkspaceState(id=WS),
        auth=AuthState(api_key="test-only"),
    )
    monkeypatch.setattr(cli, "load_config", lambda: cfg)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setattr(
        cli.httpx,
        "AsyncClient",
        lambda **kwargs: HTTP_CLIENT(**kwargs, transport=httpx.MockTransport(handler)),
    )
    video = tmp_path / "finished.mp4"
    video.write_bytes(b"local-video-fixture")
    return {
        "workspace_id": WS,
        "idempotency_key": "finished-video-batch-1",
        "items": [
            {
                "file": str(video),
                "account_ids": [ACCOUNT],
                "caption": "Finished local video",
                "now": True,
                "schedule_timezone": "Asia/Shanghai",
            }
        ],
    }


def test_unknown_submission_outcome_reuses_upload_and_exact_body(monkeypatch, tmp_path):
    uploads = []
    submissions = []

    def handler(request):
        if request.url.path.endswith("publication-settings:read"):
            assert json.loads(request.content) == {"workspace_id": WS, "account_ids": [ACCOUNT]}
            return httpx.Response(200, json={"items": [{"id": ACCOUNT, "ready": True}]})
        if request.url.path.endswith("/media/upload"):
            uploads.append(request)
            assert b"local-video-fixture" in request.content
            return httpx.Response(
                200, json={"success": True, "data": {"asset": {"media_id": MEDIA}}}
            )
        assert request.url.path == "/api/v2/ai-hook-videos/from-upload"
        assert request.headers["Idempotency-Key"] == "finished-video-batch-1"
        submissions.append(json.loads(request.content))
        if len(submissions) == 1:
            return httpx.Response(409, json={"detail": "temporarily unavailable"})
        return httpx.Response(200, json={"items": [{"id": "video-1", "status": "scheduled"}]})

    args = setup(monkeypatch, tmp_path, handler)
    with pytest.raises(Exception):
        invoke(args)
    result = invoke(args)
    assert len(uploads) == 1 and len(submissions) == 2
    assert submissions[0] == submissions[1]
    item = submissions[1]["items"][0]
    assert item["media_id"] == MEDIA and item["publishing_account_ids"] == [ACCOUNT]
    assert (
        item["caption"] == "Finished local video" and item["schedule_timezone"] == "Asia/Shanghai"
    )
    assert datetime.fromisoformat(item["scheduled_at"]).tzinfo is not None
    assert result["data"]["items"][0]["status"] == "scheduled"
    assert invoke(args) == result
    assert len(submissions) == 2
    args["items"][0]["caption"] = "Different intent"
    with pytest.raises(ValueError, match="Idempotency"):
        invoke(args)


def test_unready_account_never_uploads_or_submits(monkeypatch, tmp_path):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"items": [{"id": ACCOUNT, "ready": False}]})

    args = setup(monkeypatch, tmp_path, handler)
    with pytest.raises(ValueError, match="not ready"):
        invoke(args)
    assert len(requests) == 1 and requests[0].url.path.endswith("publication-settings:read")


def test_explicit_schedule_and_dry_run_do_not_change_publication_semantics(monkeypatch, tmp_path):
    calls = []

    def handler(request):
        calls.append(request)
        if request.url.path.endswith("publication-settings:read"):
            return httpx.Response(200, json={"items": [{"id": ACCOUNT, "ready": True}]})
        if request.url.path.endswith("/media/upload"):
            return httpx.Response(
                200, json={"success": True, "data": {"asset": {"media_id": MEDIA}}}
            )
        assert (
            json.loads(request.content)["items"][0]["scheduled_at"] == "2030-10-01T18:00:00+08:00"
        )
        return httpx.Response(200, json={"items": []})

    args = setup(monkeypatch, tmp_path, handler)
    args["items"][0].pop("now")
    args["items"][0]["scheduled_at"] = "2030-10-01T18:00:00+08:00"
    asyncio.run(
        cli.dispatch(
            cli.build_parser().parse_args(
                [
                    "hireaicreator",
                    "video",
                    "+publish-local",
                    "--args-json",
                    json.dumps(args),
                    "--dry-run",
                ]
            )
        )
    )
    assert not calls
    invoke(args)
    assert len(calls) == 3


def test_explicit_workspace_overrides_selected_workspace(monkeypatch, tmp_path):
    requested = "70000000-0000-4000-8000-000000000007"
    seen = []

    def handler(request):
        seen.append(request)
        assert request.url.path.endswith("publication-settings:read")
        assert json.loads(request.content)["workspace_id"] == requested
        return httpx.Response(200, json={"items": [{"id": ACCOUNT, "ready": False}]})

    args = setup(monkeypatch, tmp_path, handler)
    args["workspace_id"] = requested
    with pytest.raises(ValueError, match="not ready"):
        invoke(args)
    assert len(seen) == 1
