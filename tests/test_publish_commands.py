"""Scheduling local videos must survive retries without a second post."""

import asyncio
import json

import httpx
import pytest

import museoncli.main as cli
from museoncli.config import AuthState, Config, WorkspaceState

WS = "40000000-0000-4000-8000-000000000004"
ACCOUNT = "50000000-0000-4000-8000-000000000005"
OTHER_ACCOUNT = "50000000-0000-4000-8000-000000000006"
MEDIA = "60000000-0000-4000-8000-000000000006"
TASK = "70000000-0000-4000-8000-000000000007"
HTTP_CLIENT = httpx.AsyncClient


def invoke(arguments, *extra):
    return asyncio.run(
        cli.dispatch(
            cli.build_parser().parse_args(
                ["publish", "post", "+schedule", "--args-json", json.dumps(arguments), *extra]
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
        "idempotency_key": "tiktok-batch-0001",
        "items": [
            {
                "file": str(video),
                "account_ids": [ACCOUNT, OTHER_ACCOUNT],
                "caption": "Morning routine #fyp",
                "scheduled_at": "2030-10-01T18:00:00+08:00",
            }
        ],
    }


def test_lost_response_reuses_upload_and_resends_the_exact_keyed_body(monkeypatch, tmp_path):
    uploads = []
    submissions = []

    def handler(request):
        if request.url.path.endswith("/media/upload"):
            uploads.append(request)
            return httpx.Response(
                200, json={"success": True, "data": {"asset": {"media_id": MEDIA}}}
            )
        assert request.url.path == "/api/v2/pool-accounts/publish"
        assert request.headers["Idempotency-Key"] == "tiktok-batch-0001"
        submissions.append(json.loads(request.content))
        if len(submissions) == 1:
            raise httpx.ReadTimeout("response lost", request=request)
        return httpx.Response(
            200, json={"success": True, "task_id": TASK, "total_jobs": 2, "message": "ok"}
        )

    args = setup(monkeypatch, tmp_path, handler)
    with pytest.raises(httpx.ReadTimeout):
        invoke(args)
    result = invoke(args)

    assert len(uploads) == 1
    assert submissions[0] == submissions[1]
    body = submissions[1]
    assert body["workspace_id"] == WS and body["publish_immediately"] is False
    assert [(item["account_id"], item["content_id"]) for item in body["items"]] == [
        (ACCOUNT, MEDIA),
        (OTHER_ACCOUNT, MEDIA),
    ]
    assert {item["scheduled_at"] for item in body["items"]} == {"2030-10-01T18:00:00+08:00"}
    assert result["data"]["task_id"] == TASK
    # A completed receipt answers locally; a changed intent cannot reuse the key.
    assert invoke(args) == result
    assert len(submissions) == 2
    args["items"][0]["caption"] = "Different intent"
    with pytest.raises(ValueError, match="Idempotency"):
        invoke(args)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"media_id": MEDIA}, "exactly one of file or media_id"),
        ({"scheduled_at": None}, "scheduled_at"),
        ({"account_ids": [ACCOUNT] * 101}, "invalid item count"),
    ],
)
def test_ambiguous_or_oversized_batches_fail_before_any_request(
    monkeypatch, tmp_path, change, message
):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(500)

    args = setup(monkeypatch, tmp_path, handler)
    item = {**args["items"][0], **change}
    args["items"] = [{key: value for key, value in item.items() if value is not None}]
    with pytest.raises(ValueError, match=message):
        invoke(args)
    assert requests == []


def test_now_publishes_at_once_and_rejects_a_scheduled_time(monkeypatch, tmp_path):
    submissions = []

    def handler(request):
        if request.url.path.endswith("/media/upload"):
            return httpx.Response(
                200, json={"success": True, "data": {"asset": {"media_id": MEDIA}}}
            )
        submissions.append(json.loads(request.content))
        return httpx.Response(
            200, json={"success": True, "task_id": TASK, "total_jobs": 2, "message": "ok"}
        )

    args = setup(monkeypatch, tmp_path, handler)
    with pytest.raises(ValueError, match="scheduled_at"):
        invoke({**args, "now": True})
    assert submissions == []
    del args["items"][0]["scheduled_at"]
    assert invoke({**args, "now": True})["data"]["task_id"] == TASK
    assert submissions[0]["publish_immediately"] is True
