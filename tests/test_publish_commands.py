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
        ({"media_id": MEDIA}, "exactly one of file, media_id"),
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


def test_photo_set_uploads_each_image_once_and_keeps_their_order(monkeypatch, tmp_path):
    uploads = []
    submissions = []
    ids = iter(
        [
            "61000000-0000-4000-8000-000000000001",
            "61000000-0000-4000-8000-000000000002",
            "61000000-0000-4000-8000-000000000003",
        ]
    )

    def handler(request):
        if request.url.path.endswith("/media/upload"):
            uploads.append(request.content)
            assert b'name="media_type"\r\n\r\nimage' in request.content
            return httpx.Response(
                200, json={"success": True, "data": {"asset": {"media_id": next(ids)}}}
            )
        submissions.append(json.loads(request.content))
        if len(submissions) == 1:
            raise httpx.ReadTimeout("response lost", request=request)
        return httpx.Response(
            200, json={"success": True, "task_id": TASK, "total_jobs": 1, "message": "ok"}
        )

    args = setup(monkeypatch, tmp_path, handler)
    images = []
    for name in ("slide-1.jpg", "slide-2.jpg", "slide-3.jpg"):
        image = tmp_path / name
        image.write_bytes(name.encode())
        images.append(str(image))
    args["items"] = [
        {
            "image_files": images,
            "account_ids": [ACCOUNT],
            "caption": "three things I wish I knew",
            "scheduled_at": "2030-10-01T18:00:00+08:00",
        }
    ]
    with pytest.raises(httpx.ReadTimeout):
        invoke(args)
    invoke(args)

    assert len(uploads) == 3
    assert submissions[0] == submissions[1]
    (item,) = submissions[1]["items"]
    assert item["content_type"] == "image"
    assert item["image_media_ids"] == [
        "61000000-0000-4000-8000-000000000001",
        "61000000-0000-4000-8000-000000000002",
        "61000000-0000-4000-8000-000000000003",
    ]
    assert item["content_id"] == item["image_media_ids"][0]


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"image_media_ids": [MEDIA]}, "exactly one of"),
        ({"file": None, "image_media_ids": [MEDIA, MEDIA]}, "must not repeat"),
        ({"file": None, "image_media_ids": [MEDIA], "product_id": "123"}, "video posts"),
    ],
)
def test_photo_set_inputs_that_cannot_post_fail_before_any_request(
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


def test_music_url_sends_the_post_whose_sound_the_cloud_phone_reuses(monkeypatch, tmp_path):
    submissions = []

    def handler(request):
        submissions.append(json.loads(request.content))
        return httpx.Response(
            200, json={"success": True, "task_id": TASK, "total_jobs": 1, "message": "ok"}
        )

    args = setup(monkeypatch, tmp_path, handler)
    args["items"] = [
        {
            "image_media_ids": [MEDIA],
            "account_ids": [ACCOUNT],
            "caption": "three things I wish I knew",
            "scheduled_at": "2030-10-01T18:00:00+08:00",
            "music_url": "https://www.tiktok.com/@someone/photo/7339393672959757570?lang=en",
        }
    ]
    invoke(args)

    (item,) = submissions[0]["items"]
    assert item["bgm_config"] == {"ref_video_id": "7339393672959757570"}


@pytest.mark.parametrize(
    ("music_url", "message"),
    [
        ("https://www.tiktok.com/music/original-sound-7082972948549733126", "not a sound page"),
        ("https://vm.tiktok.com/ZMabc123/", "short links"),
        ("7339393672959757570", "TikTok post link"),
        ("https://www.instagram.com/reel/7339393672959757570/", "TikTok post link"),
    ],
)
def test_music_url_that_is_not_a_tiktok_post_fails_before_any_request(
    monkeypatch, tmp_path, music_url, message
):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(500)

    args = setup(monkeypatch, tmp_path, handler)
    args["items"][0]["music_url"] = music_url
    with pytest.raises(ValueError, match=message):
        invoke(args)
    assert requests == []


def test_job_reads_keep_the_delivery_report_but_not_provider_identity(monkeypatch, tmp_path):
    reported = {
        "result": "succeeded",
        "error_code": None,
        "error_message": None,
        "settled_at": "2030-10-01T18:05:00Z",
    }
    verification = {
        "deadline_at": "2030-10-01T19:05:00Z",
        "last_outcome": "not_found",
        "last_checked_at": "2030-10-01T18:10:00Z",
        "platform_content_id": None,
    }
    jobs = [
        {
            "id": TASK,
            "status": "processing",
            "provider": "internal-vendor",
            "delivery": {"stage": "verifying", "provider": reported, "verification": verification},
        },
        {"id": MEDIA, "status": "published", "delivery": None},
    ]

    def handler(request):
        assert request.url.path == "/api/v2/pool-accounts/jobs"
        return httpx.Response(
            200, json={"items": jobs, "total": 2, "page": 1, "page_size": 20, "has_more": False}
        )

    setup(monkeypatch, tmp_path, handler)
    result = asyncio.run(cli.dispatch(cli.build_parser().parse_args(["publish", "job", "+list"])))

    verifying, legacy = result["data"]["items"]
    assert verifying == {
        "id": TASK,
        "status": "processing",
        "delivery": {"stage": "verifying", "upstream": reported, "verification": verification},
    }
    assert legacy == {"id": MEDIA, "status": "published", "delivery": None}
