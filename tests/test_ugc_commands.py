from __future__ import annotations

import asyncio
from typing import Any

import pytest

from museoncli import main as main_module
from museoncli.config import Config, WorkspaceState
from museoncli.main import build_parser

CAMPAIGN = "10000000-0000-4000-8000-000000000001"
BRIEF = "20000000-0000-4000-8000-000000000001"
OTHER_BRIEF = "20000000-0000-4000-8000-000000000002"
CREATIVE = "30000000-0000-4000-8000-000000000001"
DOC_PATH = f"/ugc/campaigns/{CAMPAIGN}/brief-documents/{BRIEF}"
ASSIGNMENTS_PATH = f"/ugc/campaigns/{CAMPAIGN}/assignments"


def _brief_view(*, version: int = 3) -> dict[str, Any]:
    return {
        "brief": {"id": BRIEF, "title": "Morning hook", "current_version": version},
        "current": {
            "version": version,
            "content": "Open on the alarm.",
            # A library file as a version stores it, plus the legacy video field.
            "references": [{"kind": "video", "url": "https://cdn.example/a.mp4", "note": None}],
            "reference_video_url": "https://www.tiktok.com/@a/video/1",
            "required_caption": "#ad",
            "require_ad_disclosure": False,
        },
        "versions": [],
        "copy_required": False,
    }


def _assignment(brief_id: str, status: str, counted: int, limit: int | None, n: int) -> dict:
    return {
        "id": f"50000000-0000-4000-8000-00000000000{n}",
        "enrollment_id": f"40000000-0000-4000-8000-00000000000{n}",
        "brief_id": brief_id,
        "status": status,
        "videos_counted": counted,
        "video_limit": limit,
        "due_at": None,
        "priority": "normal",
        "note": None,
    }


class _Workbench:
    """Answers by (method, path); records every call."""

    def __init__(self, routes: dict[tuple[str, str], Any]) -> None:
        self.routes = routes
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, cfg: Config, method: str, path: str, **kwargs: Any) -> Any:
        del cfg
        self.calls.append({"method": method, "path": path, **kwargs})
        answer = self.routes[(method, path)]
        return answer(kwargs) if callable(answer) else answer

    def writes(self) -> list[dict[str, Any]]:
        return [call for call in self.calls if call["method"] != "GET"]


def _run(monkeypatch: pytest.MonkeyPatch, workbench: _Workbench, argv: list[str]) -> dict:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="Workspace", organization_id="org-1")
    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data_v2", workbench)
    return asyncio.run(main_module.dispatch(build_parser().parse_args(argv)))


def _paged(pages: list[list[dict[str, Any]]]):
    def answer(kwargs: dict[str, Any]) -> dict[str, Any]:
        index = int(kwargs["params"].get("cursor") or 0)
        more = index + 1 < len(pages)
        return {"items": pages[index], "next_cursor": str(index + 1) if more else None}

    return answer


def _update_argv(*extra: str) -> list[str]:
    return [
        "ugc", "brief", "+update", "--campaign-id", CAMPAIGN, "--id", BRIEF,
        "--expected-version", "3", *extra,
    ]


def test_brief_update_dry_run_diffs_only_passed_fields_and_writes_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workbench = _Workbench(
        {
            ("GET", DOC_PATH): _brief_view(),
            ("GET", ASSIGNMENTS_PATH): _paged(
                [
                    [_assignment(BRIEF, "assigned", 0, 2, 1), _assignment(BRIEF, "withdrawn", 1, 2, 2)],
                    [_assignment(BRIEF, "delivered", 2, None, 3), _assignment(OTHER_BRIEF, "assigned", 0, 1, 4)],
                ]
            ),
        }
    )

    result = _run(
        monkeypatch,
        workbench,
        _update_argv("--required-caption", "#ad #brand", "--title", "Morning hook", "--dry-run"),
    )

    assert workbench.writes() == []
    assert result["command"] == "ugc.brief-update"
    data = result["data"]
    assert data["dry_run"] is True
    assert data["brief"] == {"id": BRIEF, "title": "Morning hook", "current_version": 3}
    # The unchanged title is not a change; the caption is.
    assert data["changes"] == [
        {"field": "required_caption", "before": "#ad", "after": "#ad #brand"}
    ]
    # Every page read; the withdrawn one and the other brief's do not count.
    assert data["live_assignments"] == 2
    assert any("new caption rule" in warning for warning in result["warnings"])
    assert any(
        warning.startswith("2 creators are working on this brief; without --notify")
        for warning in result["warnings"]
    )
    assert len(result["next_steps"]) == 1
    assert "whether to notify" in result["next_steps"][0]
    assert "museoncli" not in result["next_steps"][0]


def test_brief_update_sends_the_whole_document_with_only_the_edit_changed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patched: dict[str, Any] = {}

    def patch(kwargs: dict[str, Any]) -> dict[str, Any]:
        patched.update(kwargs["json_body"])
        return {"brief": {"id": BRIEF, "title": "Morning hook", "current_version": 4}}

    workbench = _Workbench(
        {
            ("GET", DOC_PATH): _brief_view(),
            ("GET", ASSIGNMENTS_PATH): _paged([[]]),
            ("PATCH", DOC_PATH): patch,
        }
    )

    result = _run(monkeypatch, workbench, _update_argv("--content", "Open on the coffee."))

    assert patched == {
        "title": "Morning hook",
        "content": "Open on the coffee.",
        "references": [
            {"type": "stored", "kind": "video", "url": "https://cdn.example/a.mp4"},
            {"type": "link", "url": "https://www.tiktok.com/@a/video/1"},
        ],
        "required_caption": "#ad",
        "require_ad_disclosure": False,
        "expected_version": 3,
    }
    assert result["data"]["brief"]["current_version"] == 4
    assert result["data"]["live_assignments"] == 0


def test_brief_update_without_changes_or_on_a_moved_version_writes_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workbench = _Workbench(
        {("GET", DOC_PATH): _brief_view(), ("GET", ASSIGNMENTS_PATH): _paged([[]])}
    )
    result = _run(monkeypatch, workbench, _update_argv("--required-caption", "#ad"))
    assert result["data"]["changes"] == []
    assert workbench.writes() == []

    workbench = _Workbench({("GET", DOC_PATH): _brief_view(version=4)})
    with pytest.raises(RuntimeError, match="^conflict: brief_version_conflict"):
        _run(monkeypatch, workbench, _update_argv("--title", "New"))
    assert workbench.writes() == []


def test_brief_progress_sums_live_assignments_per_brief(monkeypatch: pytest.MonkeyPatch) -> None:
    briefs = [
        {"id": BRIEF, "title": "Morning hook", "status": "active", "current_version": 3},
        {"id": OTHER_BRIEF, "title": "Night hook", "status": "archived", "current_version": 1},
    ]
    workbench = _Workbench(
        {
            ("GET", f"/ugc/campaigns/{CAMPAIGN}/briefs"): briefs,
            ("GET", ASSIGNMENTS_PATH): _paged(
                [
                    [_assignment(BRIEF, "assigned", 1, 3, 1), _assignment(BRIEF, "withdrawn", 5, 9, 2)],
                    [_assignment(BRIEF, "delivered", 2, None, 3), _assignment(BRIEF, "in_progress", 0, 2, 4)],
                ]
            ),
        }
    )

    result = _run(monkeypatch, workbench, ["ugc", "brief", "+progress", "--campaign-id", CAMPAIGN])

    morning, night = result["data"]["briefs"]
    assert {key: morning[key] for key in morning if key != "rows"} == {
        "brief_id": BRIEF,
        "title": "Morning hook",
        "status": "active",
        "current_version": 3,
        "assignments": 3,
        "withdrawn_assignments": 1,
        "videos_counted": 3,
        "video_limit_total": 5,
        "unlimited_assignments": 1,
    }
    assert [row["status"] for row in morning["rows"]] == ["assigned", "delivered", "in_progress"]
    assert night["assignments"] == 0 and night["rows"] == []


def test_creative_list_brief_none_keeps_only_brief_less_creatives(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    creatives = [
        {"id": CREATIVE, "brief_id": None},
        {"id": "30000000-0000-4000-8000-000000000002", "brief_id": BRIEF},
    ]
    workbench = _Workbench({("GET", f"/ugc/campaigns/{CAMPAIGN}/creatives"): creatives})
    argv = ["ugc", "creative", "+list", "--campaign-id", CAMPAIGN]

    none = _run(monkeypatch, workbench, [*argv, "--brief-id", "none"])
    one = _run(monkeypatch, workbench, [*argv, "--brief-id", BRIEF.upper()])

    assert [item["id"] for item in none["data"]["items"]] == [CREATIVE]
    assert [item["brief_id"] for item in one["data"]["items"]] == [BRIEF]
