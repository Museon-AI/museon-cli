from __future__ import annotations

import asyncio
from typing import Any

import pytest

from museoncli import main as main_module
from museoncli.config import Config, WorkspaceState
from museoncli.domains import command_payload, schema_payload

ANALYSIS_ID = "11111111-1111-4111-8111-111111111111"
ITEM_ID = "33333333-3333-4333-8333-333333333333"


def _parse(argv: list[str]):
    return main_module.build_parser().parse_args(argv)


def _config() -> Config:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="Workspace", organization_id="org-1")
    return cfg


def test_start_accepts_post_and_profile_urls_without_server_strategy() -> None:
    args = _parse(
        [
            "research",
            "+social-media-hook-analyze",
            "--url",
            "https://www.instagram.com/reel/post-1/",
            "--profile-url",
            "https://www.instagram.com/creator/",
            "--limit-per-profile",
            "10",
            "--max-items",
            "18",
            "--idempotency-key",
            "hook-analysis-1",
        ]
    )

    payload = command_payload(args)
    assert payload == {
        "post_urls": ["https://www.instagram.com/reel/post-1/"],
        "profile_urls": ["https://www.instagram.com/creator/"],
        "limit_per_profile": 10,
        "max_items": 18,
        "idempotency_key": "hook-analysis-1",
    }
    schema = schema_payload("research.social-media-hook-analyze")["input_schema"]
    assert "selection" not in schema["properties"]
    assert "decision" not in schema["properties"]


def test_start_requires_at_least_one_source() -> None:
    args = _parse(
        [
            "research",
            "+social-media-hook-analyze",
            "--idempotency-key",
            "hook-analysis-empty",
        ]
    )
    with pytest.raises(ValueError, match="url or --profile-url"):
        command_payload(args)


def test_source_builds_agent_prefiltered_candidate_payload() -> None:
    args = _parse(
        [
            "research",
            "+social-media-hook-source",
            "--url",
            "https://www.instagram.com/reel/post-1/",
            "--url",
            "https://www.instagram.com/reel/post-2/",
            "--max-items",
            "10",
            "--idempotency-key",
            "home-source-1",
        ]
    )

    assert command_payload(args) == {
        "candidate_urls": [
            "https://www.instagram.com/reel/post-1/",
            "https://www.instagram.com/reel/post-2/",
        ],
        "max_items": 10,
        "idempotency_key": "home-source-1",
    }
    schema = schema_payload("research.social-media-hook-source")
    assert schema["execution"] == "async_run"
    assert schema["input_schema"]["properties"]["candidate_urls"]["minItems"] == 1


def test_source_dispatches_to_sourcing_boundary(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    async def fake_api_data(
        _cfg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        calls.append({"method": method, "path": path, "json_body": json_body, "params": params})
        return {
            "domain": "research",
            "operation": "social-media-hook-source",
            "result": {
                "id": ANALYSIS_ID,
                "status": "queued",
                "terminal": False,
                "poll_after_seconds": 5,
                "sourcing": {"initial_unseen_count": 1},
            },
        }

    monkeypatch.setattr(main_module, "load_config", _config)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)
    result = asyncio.run(
        main_module.dispatch(
            _parse(
                [
                    "research",
                    "+social-media-hook-source",
                    "--url",
                    "https://www.instagram.com/reel/post-1/",
                    "--idempotency-key",
                    "home-source-dispatch",
                ]
            )
        )
    )

    assert result["run"]["id"] == ANALYSIS_ID
    assert calls[0]["path"] == "/agent-cli/research/social-media-hook-source"
    assert calls[0]["json_body"]["payload"]["candidate_urls"] == [
        "https://www.instagram.com/reel/post-1/"
    ]


def test_seen_parser_builds_ordered_url_payload_and_read_schema() -> None:
    args = _parse(
        [
            "research",
            "+social-media-hook-analyze-seen",
            "--url",
            "https://www.instagram.com/reel/post-1/",
            "--url",
            "https://www.instagram.com/reel/post-2/",
            "--workspace-id",
            "workspace-2",
        ]
    )

    assert args.domain_command == "research.social-media-hook-analyze-seen"
    assert args.workspace_id == "workspace-2"
    assert command_payload(args) == {
        "urls": [
            "https://www.instagram.com/reel/post-1/",
            "https://www.instagram.com/reel/post-2/",
        ]
    }
    schema = schema_payload("research.social-media-hook-analyze-seen")
    assert schema["risk_level"] == "read"
    assert schema["execution"] == "direct"
    assert schema["input_schema"]["properties"]["urls"]["maxItems"] == 40


@pytest.mark.parametrize("count", [0, 41])
def test_seen_requires_one_to_forty_urls(count: int) -> None:
    argv = ["research", "+social-media-hook-analyze-seen"]
    for index in range(count):
        argv.extend(["--url", f"https://www.instagram.com/reel/post-{index}/"])

    with pytest.raises(ValueError, match="1 to 40"):
        command_payload(_parse(argv))


def test_seen_dispatch_posts_workspace_scoped_batch(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    async def fake_api_data(
        _cfg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        calls.append({"method": method, "path": path, "json_body": json_body, "params": params})
        return {
            "domain": "research",
            "operation": "social-media-hook-analyze-seen",
            "result": {"items": []},
        }

    monkeypatch.setattr(main_module, "load_config", _config)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)
    result = asyncio.run(
        main_module.dispatch(
            _parse(
                [
                    "research",
                    "+social-media-hook-analyze-seen",
                    "--url",
                    "https://www.instagram.com/reel/post-1/",
                    "--workspace-id",
                    "workspace-override",
                ]
            )
        )
    )

    assert result["command"] == "research.social-media-hook-analyze-seen"
    assert calls == [
        {
            "method": "POST",
            "path": "/agent-cli/research/social-media-hook-analyze-seen",
            "json_body": {
                "workspace_id": "workspace-override",
                "payload": {"urls": ["https://www.instagram.com/reel/post-1/"]},
            },
            "params": None,
        }
    ]


def test_poll_collects_up_to_twenty_ids() -> None:
    args = _parse(
        [
            "research",
            "+social-media-hook-analyze-poll",
            "--id",
            ANALYSIS_ID,
            "--id",
            "22222222-2222-4222-8222-222222222222",
        ]
    )
    assert command_payload(args)["analysis_ids"] == [
        ANALYSIS_ID,
        "22222222-2222-4222-8222-222222222222",
    ]


def test_start_dispatch_returns_proactive_poll_envelope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []

    async def fake_api_data(
        _cfg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        calls.append({"method": method, "path": path, "json_body": json_body, "params": params})
        return {
            "domain": "research",
            "operation": "social-media-hook-analyze",
            "result": {
                "id": ANALYSIS_ID,
                "type": "social_hook_analysis",
                "status": "queued",
                "terminal": False,
                "poll_after_seconds": 5,
            },
        }

    monkeypatch.setattr(main_module, "load_config", _config)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    result = asyncio.run(
        main_module.dispatch(
            _parse(
                [
                    "research",
                    "+social-media-hook-analyze",
                    "--url",
                    "https://www.instagram.com/reel/post-1/",
                    "--idempotency-key",
                    "hook-analysis-dispatch",
                ]
            )
        )
    )

    assert result["run"] == {
        "id": ANALYSIS_ID,
        "type": "social_hook_analysis",
        "status": "queued",
        "watch_command": (f"museoncli research +social-media-hook-analyze-get --id {ANALYSIS_ID}"),
        "recommended_wakeup_delay_seconds": 5,
    }
    assert calls[0]["path"] == "/agent-cli/research/social-media-hook-analyze"


def test_results_uses_stable_pagination_query(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    async def fake_api_data(
        _cfg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        calls.append({"method": method, "path": path, "params": params})
        return {
            "domain": "research",
            "operation": "social-media-hook-analyze-results",
            "result": {"items": [], "pagination": {"page": 2, "page_size": 10}},
        }

    monkeypatch.setattr(main_module, "load_config", _config)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)
    asyncio.run(
        main_module.dispatch(
            _parse(
                [
                    "research",
                    "+social-media-hook-analyze-results",
                    "--id",
                    ANALYSIS_ID,
                    "--page",
                    "2",
                    "--page-size",
                    "10",
                ]
            )
        )
    )
    assert calls == [
        {
            "method": "GET",
            "path": f"/agent-cli/research/social-media-hook-analyze/{ANALYSIS_ID}/results",
            "params": {"workspace_id": "workspace-1", "page": 2, "page_size": 10},
        }
    ]


def test_media_get_atomically_writes_video(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    calls: list[dict[str, Any]] = []
    destination = tmp_path / "hook.mp4"

    async def fake_download(_cfg, path, *, params, destination, max_bytes):
        calls.append({"path": path, "params": params, "max_bytes": max_bytes})
        destination.write_bytes(b"video")
        return {"content_type": "video/mp4", "bytes": 5}

    monkeypatch.setattr(main_module, "load_config", _config)
    monkeypatch.setattr(main_module, "download_api_file", fake_download)
    result = asyncio.run(
        main_module.dispatch(
            _parse(
                [
                    "research",
                    "+social-media-hook-analyze-media-get",
                    "--id",
                    ANALYSIS_ID,
                    "--item-id",
                    ITEM_ID,
                    "--output",
                    str(destination),
                ]
            )
        )
    )

    assert destination.read_bytes() == b"video"
    assert result["data"]["path"] == str(destination)
    assert calls == [
        {
            "path": (
                f"/agent-cli/research/social-media-hook-analyze/{ANALYSIS_ID}/items/{ITEM_ID}/media"
            ),
            "params": {"workspace_id": "workspace-1"},
            "max_bytes": 30 * 1024 * 1024,
        }
    ]


def test_media_get_preserves_existing_output_and_cleans_partial(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    destination = tmp_path / "hook.mp4"
    destination.write_bytes(b"existing")

    monkeypatch.setattr(main_module, "load_config", _config)
    with pytest.raises(RuntimeError, match="output_exists"):
        asyncio.run(
            main_module.dispatch(
                _parse(
                    [
                        "research",
                        "+social-media-hook-analyze-media-get",
                        "--id",
                        ANALYSIS_ID,
                        "--item-id",
                        ITEM_ID,
                        "--output",
                        str(destination),
                    ]
                )
            )
        )
    assert destination.read_bytes() == b"existing"
    assert list(tmp_path.glob("*.part")) == []
