"""The JSON output contract: error envelope, exit codes and pagination.

Agents branch on these fields and exit codes. Each case pins a regression that
was observed: class names as reasons (`RuntimeError`), argparse text on stderr
instead of JSON, and three incompatible page shapes.
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

import pytest

import museoncli.main as main_module
import museoncli.paging as paging
from museoncli.main import ApiRequestError


def _run_main(monkeypatch, capsys, argv, error: Exception | None = None):
    async def fake_dispatch(_args: Any) -> dict[str, Any]:
        assert error is not None
        raise error

    monkeypatch.setattr(main_module, "dispatch_with_notices", fake_dispatch)
    monkeypatch.setattr(sys, "argv", ["museoncli", *argv])
    with pytest.raises(SystemExit) as exc_info:
        main_module.main()
    return exc_info.value.code, json.loads(capsys.readouterr().out)


@pytest.mark.parametrize(
    "error,reason,exit_code,server_code,retryable",
    [
        (
            ApiRequestError(409, {"code": "version_conflict", "message": "Video version conflict"}),
            "conflict",
            5,
            "version_conflict",
            False,
        ),
        (ApiRequestError(404, "Test group not found"), "not_found", 3, None, False),
        (ApiRequestError(502, "bad gateway"), "server_error", 1, None, True),
        (ApiRequestError(429, "slow down"), "rate_limited", 1, None, True),
        (RuntimeError("missing_auth"), "missing_auth", 4, None, False),
        (RuntimeError("boom"), "command_failed", 1, None, False),
    ],
)
def test_failures_share_one_envelope_and_a_meaningful_exit_code(
    monkeypatch, capsys, error, reason, exit_code, server_code, retryable
) -> None:
    code, payload = _run_main(monkeypatch, capsys, ["hireaicreator", "video", "+get", "--id", "x"], error)

    assert code == exit_code
    assert payload["ok"] is False
    assert payload["command"] == "hireaicreator.video-get"
    # Released fields keep their meaning; `error` adds the stable shape.
    assert payload["reason"] == reason
    assert "detail" in payload
    assert payload["error"]["code"] == reason
    assert payload["error"]["retryable"] is retryable
    assert payload["error"].get("server_code") == server_code
    assert payload["error"]["message"]


def test_usage_errors_are_json_on_stdout_with_exit_code_2(monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "argv", ["museoncli", "hireaicreator", "video", "+get", "--bogus", "1"])
    with pytest.raises(SystemExit) as exc_info:
        main_module.main()
    captured = capsys.readouterr()

    assert exc_info.value.code == 2
    assert captured.err == ""
    payload = json.loads(captured.out)
    assert payload["reason"] == "usage_error"
    assert payload["command"] == "hireaicreator.video-get"
    assert "--bogus" in payload["error"]["message"]
    assert "hireaicreator video +get --help" in payload["error"]["hint"]


@pytest.mark.parametrize(
    "result,expected",
    [
        (
            {"data": {"items": [1], "total": 12, "page": 1, "page_size": 5, "has_more": True}},
            {"page": 1, "page_size": 5, "total": 12, "has_more": True},
        ),
        (
            {"data": {"items": [1], "pagination": {"page": 2, "page_size": 5, "total": 7, "total_pages": 2}}},
            {"page": 2, "page_size": 5, "total": 7, "total_pages": 2, "has_more": False},
        ),
        (
            {"data": {"data": [1]}, "pagination": {"page": 1, "limit": 20, "total": 45}},
            {"page": 1, "page_size": 20, "total": 45, "has_more": True},
        ),
        ({"data": {"id": "x"}}, None),
    ],
)
def test_page_info_normalizes_every_page_shape(result, expected) -> None:
    assert paging.page_info(result) == expected


def _pages(pages: list[dict[str, Any]], calls: list[dict[str, Any]]):
    async def run(arguments: dict[str, Any]) -> dict[str, Any]:
        calls.append(arguments)
        return pages[len(calls) - 1]

    return run


def test_all_follows_has_more_and_merges_records() -> None:
    calls: list[dict[str, Any]] = []
    pages = [
        {"data": {"items": [1, 2], "total": 3, "page": 1, "page_size": 2, "has_more": True}},
        {"data": {"items": [3], "total": 3, "page": 2, "page_size": 2, "has_more": False}},
    ]
    merged = asyncio.run(paging.collect_all_pages(_pages(pages, calls), {"page_size": 2}))

    assert [call["page"] for call in calls] == [1, 2]
    assert merged["data"]["items"] == [1, 2, 3]
    assert merged["page_info"] == {
        "all_pages": True,
        "pages_fetched": 2,
        "items": 3,
        "complete": True,
        "total": 3,
    }


def test_all_stops_on_a_short_page_without_pagination_facts() -> None:
    calls: list[dict[str, Any]] = []
    pages = [{"data": [1, 2]}, {"data": [3]}]
    merged = asyncio.run(
        paging.collect_all_pages(_pages(pages, calls), {"page": {"page": 1, "page_size": 2}})
    )

    assert [call["page"]["page"] for call in calls] == [1, 2]
    assert merged["data"] == [1, 2, 3]
    assert merged["page_info"]["complete"] is True


def test_all_reports_hitting_its_cap_instead_of_claiming_completeness(monkeypatch) -> None:
    monkeypatch.setattr(paging, "MAX_ALL_PAGES", 2)
    calls: list[dict[str, Any]] = []
    page = {"data": {"items": [1], "has_more": True}}
    merged = asyncio.run(paging.collect_all_pages(_pages([page, page, page], calls), {}))

    assert len(calls) == 2
    assert merged["page_info"]["complete"] is False
    assert any("--all stopped" in warning for warning in merged["warnings"])


def test_slideshow_generation_keeps_its_run_and_links_after_the_domain_move() -> None:
    """Known regression: detection still named the retired `generation.create`, so
    `ai-slideshow generation +create` lost its run and frontend links in CLI 2.0."""
    from museoncli.domains import schema_payload
    from museoncli.envelopes import domain_command_envelope

    envelope = domain_command_envelope(
        "ai-slideshow.generation-create",
        {"result": {"generation_id": "11111111-1111-4111-8111-111111111111", "status": "queued"}},
    )

    assert envelope["run"] is not None
    assert envelope["run"]["id"] == "11111111-1111-4111-8111-111111111111"
    assert schema_payload("ai-slideshow.generation-get").get("frontend_url_templates")
    assert schema_payload("ai-slideshow.asset-get").get("frontend_url_templates")


def test_an_old_command_name_still_runs_and_warns(monkeypatch, capsys) -> None:
    async def fake_dispatch(args: Any) -> dict[str, Any]:
        return {"command": args.domain_command, "data": {"id": "x"}, "warnings": []}

    monkeypatch.setattr(main_module, "dispatch_with_notices", fake_dispatch)
    monkeypatch.setattr(sys, "argv", ["museoncli", "hireaicreator", "video", "+render-get", "--id", "x"])
    main_module.main()
    payload = json.loads(capsys.readouterr().out)

    assert payload["ok"] is True
    assert payload["command"] == "hireaicreator.video-get-render"
    assert payload["warnings"] == [
        "`museoncli hireaicreator video +render-get` is deprecated and will be removed; "
        "use `museoncli hireaicreator video +get-render` (same inputs and output)."
    ]
