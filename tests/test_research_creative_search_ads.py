from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from museoncli import main as main_module
from museoncli.config import Config, WorkspaceState
from museoncli.domains import command_payload, schema_payload


TASK_ID = "11111111-1111-4111-8111-111111111111"


def _parse(argv: list[str]):
    return main_module.build_parser().parse_args(argv)


def _config() -> Config:
    cfg = Config()
    cfg.workspace = WorkspaceState(
        id="workspace-1",
        name="Workspace",
        organization_id="org-1",
    )
    return cfg


def test_creative_search_ads_parser_builds_server_payload() -> None:
    args = _parse(
        [
            "research",
            "+creative-search-ads",
            "--idempotency-key",
            "ads-search-1",
            "--keyword",
            "eco soap",
            "--keyword",
            "refill soap",
            "--ad-platform",
            "meta-ads",
            "--media-type",
            "photo",
            "--limit",
            "25",
        ]
    )

    assert args.domain_command == "research.creative-search-ads"
    assert command_payload(args) == {
        "idempotency_key": "ads-search-1",
        "keywords": ["eco soap", "refill soap"],
        "ad_platforms": ["meta_ads"],
        "media_types": ["photo"],
        "limit_per_platform": 25,
    }


def test_creative_search_ads_parser_applies_safe_defaults() -> None:
    args = _parse(
        [
            "research",
            "+creative-search-ads",
            "--idempotency-key",
            "ads-search-defaults",
            "--keyword",
            "eco soap",
        ]
    )

    assert command_payload(args) == {
        "idempotency_key": "ads-search-defaults",
        "keywords": ["eco soap"],
        "ad_platforms": ["meta_ads", "tiktok_ads"],
        "media_types": ["video"],
        "limit_per_platform": 20,
    }


def test_creative_search_ads_parser_requires_idempotency_key() -> None:
    args = _parse(
        [
            "research",
            "+creative-search-ads",
            "--keyword",
            "eco soap",
        ]
    )

    with pytest.raises(ValueError, match="idempotency-key"):
        command_payload(args)


def test_creative_search_ads_accepts_idempotency_key_from_structured_args() -> None:
    args = _parse(
        [
            "research",
            "+creative-search-ads",
            "--args-json",
            json.dumps(
                {
                    "idempotency_key": "ads-search-structured",
                    "keywords": ["eco soap"],
                }
            ),
        ]
    )

    assert command_payload(args) == {
        "idempotency_key": "ads-search-structured",
        "keywords": ["eco soap"],
        "ad_platforms": ["meta_ads", "tiktok_ads"],
        "media_types": ["video"],
        "limit_per_platform": 20,
    }


@pytest.mark.parametrize("idempotency_key", [123, "   ", "x" * 241])
def test_creative_search_ads_rejects_invalid_structured_idempotency_key(
    idempotency_key: object,
) -> None:
    args = _parse(
        [
            "research",
            "+creative-search-ads",
            "--args-json",
            json.dumps(
                {
                    "idempotency_key": idempotency_key,
                    "keywords": ["eco soap"],
                }
            ),
        ]
    )

    with pytest.raises(ValueError, match="idempotency-key"):
        command_payload(args)


@pytest.mark.parametrize(
    "keywords",
    [
        [123],
        ["x" * 201],
    ],
)
def test_creative_search_ads_rejects_invalid_structured_keywords(
    keywords: list[Any],
) -> None:
    args = _parse(
        [
            "research",
            "+creative-search-ads",
            "--idempotency-key",
            "ads-search-invalid",
            "--args-json",
            json.dumps({"keywords": keywords}),
        ]
    )

    with pytest.raises(ValueError):
        command_payload(args)


@pytest.mark.parametrize(
    ("flag", "value"),
    [
        ("--page", "0"),
        ("--page-size", "101"),
    ],
)
def test_creative_search_ads_results_rejects_invalid_pagination(
    flag: str,
    value: str,
) -> None:
    args = _parse(
        [
            "research",
            "+creative-search-ads-results",
            "--id",
            TASK_ID,
            flag,
            value,
        ]
    )

    with pytest.raises(ValueError):
        command_payload(args)


def test_creative_search_ads_results_defaults_to_analysis_eligible_matches() -> None:
    args = _parse(
        [
            "research",
            "+creative-search-ads-results",
            "--id",
            TASK_ID,
        ]
    )

    payload = command_payload(args)
    schema = schema_payload("research.creative-search-ads-results")

    assert payload["relevance"] == "matched"
    assert schema["input_schema"]["properties"]["relevance"] == {
        "type": "string",
        "enum": ["matched", "all"],
        "default": "matched",
        "description": (
            "Use matched for analysis-eligible results. Use all only to inspect "
            "fallback search candidates, which may be unrelated."
        ),
    }
    assert "do not infer causality" in schema["summary"]
    assert "source item IDs" in schema["output_schema"]["description"]

    all_candidates = command_payload(
        _parse(
            [
                "research",
                "+creative-search-ads-results",
                "--id",
                TASK_ID,
                "--relevance",
                "all",
            ]
        )
    )
    assert all_candidates["relevance"] == "all"


def test_creative_search_ads_schema_is_discoverable_and_provider_neutral() -> None:
    schema = schema_payload("research.creative-search-ads")

    assert schema["risk_level"] == "write"
    assert schema["execution"] == "async_run"
    assert schema["supports_dry_run"] is True
    assert "idempotency_key" in schema["input_schema"]["required"]
    assert "provider" not in json.dumps(schema).lower()


def test_creative_search_ads_dry_run_makes_no_api_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail_api(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("dry-run must not call the API")

    monkeypatch.setattr(main_module, "load_config", _config)
    monkeypatch.setattr(main_module, "api_data", fail_api)

    result = asyncio.run(
        main_module.dispatch(
            _parse(
                [
                    "research",
                    "+creative-search-ads",
                    "--idempotency-key",
                    "ads-search-dry-run",
                    "--keyword",
                    "eco soap",
                    "--dry-run",
                ]
            )
        )
    )

    assert result is not None
    assert result["data"]["dry_run"] is True
    assert result["data"]["would_execute"] == "research.creative-search-ads"


def test_dispatch_creative_search_ads_returns_async_run(
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
        calls.append(
            {
                "method": method,
                "path": path,
                "json_body": json_body,
                "params": params,
            }
        )
        return {
            "domain": "research",
            "operation": "creative-search-ads",
            "result": {
                "id": TASK_ID,
                "type": "creative_search_ads",
                "status": "pending",
            },
        }

    monkeypatch.setattr(main_module, "load_config", _config)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    result = asyncio.run(
        main_module.dispatch(
            _parse(
                [
                    "research",
                    "+creative-search-ads",
                    "--idempotency-key",
                    "ads-search-dispatch-1",
                    "--keyword",
                    "eco soap",
                ]
            )
        )
    )

    assert result is not None
    assert result["run"] == {
        "id": TASK_ID,
        "type": "creative_search_ads",
        "status": "pending",
        "watch_command": (f"museoncli research +creative-search-ads-get --id {TASK_ID}"),
        "recommended_wakeup_delay_seconds": 20,
    }
    assert result["next_steps"] == [
        (
            "Schedule a wakeup in 20 seconds, then poll with: "
            f"museoncli research +creative-search-ads-get --id {TASK_ID}"
        )
    ]
    assert calls == [
        {
            "method": "POST",
            "path": "/agent-cli/research/creative-search-ads",
            "json_body": {
                "workspace_id": "workspace-1",
                "payload": {
                    "idempotency_key": "ads-search-dispatch-1",
                    "keywords": ["eco soap"],
                    "ad_platforms": ["meta_ads", "tiktok_ads"],
                    "media_types": ["video"],
                    "limit_per_platform": 20,
                },
            },
            "params": None,
        }
    ]


def test_dispatch_creative_search_ads_get_stops_polling_when_terminal(
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
        calls.append({"method": method, "path": path, "params": params})
        return {
            "domain": "research",
            "operation": "creative-search-ads-get",
            "result": {
                "id": TASK_ID,
                "type": "creative_search_ads",
                "status": "completed",
                "result": {"stats": {"total": 1}},
            },
        }

    monkeypatch.setattr(main_module, "load_config", _config)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    result = asyncio.run(
        main_module.dispatch(_parse(["research", "+creative-search-ads-get", "--id", TASK_ID]))
    )

    assert result is not None
    assert result["run"]["status"] == "completed"
    assert "recommended_wakeup_delay_seconds" not in result["run"]
    assert result["next_steps"] == []
    assert calls == [
        {
            "method": "GET",
            "path": f"/agent-cli/research/creative-search-ads/{TASK_ID}",
            "params": {"workspace_id": "workspace-1"},
        }
    ]


def test_dispatch_creative_search_ads_results_uses_pagination_query(
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
        calls.append({"method": method, "path": path, "params": params})
        return {
            "domain": "research",
            "operation": "creative-search-ads-results",
            "result": {
                "items": [],
                "total": 0,
                "page": 2,
                "page_size": 10,
                "has_more": False,
            },
        }

    monkeypatch.setattr(main_module, "load_config", _config)
    monkeypatch.setattr(main_module, "api_data", fake_api_data)

    result = asyncio.run(
        main_module.dispatch(
            _parse(
                [
                    "research",
                    "+creative-search-ads-results",
                    "--id",
                    TASK_ID,
                    "--ad-platform",
                    "tiktok-ads",
                    "--time-range",
                    "30d",
                    "--page",
                    "2",
                    "--page-size",
                    "10",
                    "--sort-by",
                    "first-seen-at",
                ]
            )
        )
    )

    assert result is not None
    assert result["run"] is None
    assert calls == [
        {
            "method": "GET",
            "path": f"/agent-cli/research/creative-search-ads/{TASK_ID}/results",
            "params": {
                "workspace_id": "workspace-1",
                "platform": "tiktok_ads",
                "time_range": "30d",
                "page": 2,
                "page_size": 10,
                "sort_by": "first_seen_at",
                "relevance": "matched",
            },
        }
    ]
