"""2.0.1: one flag per id, one list shape per kind, a window before the read, an import's outcome.

- A social account is `--creator-id` and a post `--content-id` across `campaign creator` /
  `campaign post`; the old `--id` keeps answering with a deprecation warning.
- `campaign creator +list` / `campaign content +list` answer `data.items` and
  `data.source_kind` for UGC and tracking Campaigns alike.
- `campaign format +list` / `campaign analytics +get` refuse a read without a window before
  any request (the service answered `analytics_date_range_required`).
- `campaign content +add` / `campaign creator +add` say how to read what became of the
  queued import, and `--wait` reports each URL that failed.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from museoncli import main as main_module
from museoncli.config import Config, OrganizationState
from museoncli.domains import campaign_data
from museoncli.main import build_parser, deprecation_notices

CAMPAIGN_ID = "10000000-0000-4000-8000-000000000001"
ACCOUNT_ID = "20000000-0000-4000-8000-000000000001"
CONTENT_ID = "30000000-0000-4000-8000-000000000001"
TASK_ID = "40000000-0000-4000-8000-000000000001"
BAD_URL = "https://www.example.com/not-a-post"


def parse(argv: list[str]) -> Any:
    return build_parser().parse_args(argv)


def _cfg() -> Config:
    cfg = Config()
    cfg.organization = OrganizationState(id="org-1", name="MuseOn")
    return cfg


def _header(kind: str) -> Any:
    async def header(cfg: Config, method: str, path: str, **_: Any) -> dict[str, Any]:
        del cfg
        assert (method, path) == ("GET", f"/ugc/collections/{CAMPAIGN_ID}/campaign")
        return {"id": CAMPAIGN_ID, "campaign_type": kind}

    return header


def _run(monkeypatch: pytest.MonkeyPatch, argv: list[str], api: Any, kind: str = "tracking") -> Any:
    monkeypatch.setattr(main_module, "load_config", _cfg)
    monkeypatch.setattr(main_module, "api_data", api)
    monkeypatch.setattr(main_module, "api_data_v2", _header(kind))
    return asyncio.run(main_module.dispatch(parse(argv)))


class _Recorder:
    def __init__(self, response: Any) -> None:
        self.response = response
        self.calls: list[tuple[str, str, Any]] = []

    async def __call__(self, cfg: Config, method: str, path: str, **kwargs: Any) -> Any:
        del cfg
        self.calls.append((method, path, kwargs.get("params")))
        return self.response(path) if callable(self.response) else self.response


# -- one flag per id --------------------------------------------------------------------


@pytest.mark.parametrize(
    "argv,path",
    [
        (["campaign", "creator", "+get"], f"/agent-cli/social-media/creators/{ACCOUNT_ID}"),
        (
            [
                "campaign",
                "creator",
                "+get-performance",
                "--date-from",
                "2026-10-01",
                "--date-to",
                "2026-10-28",
            ],
            f"/agent-cli/social-media/creators/{ACCOUNT_ID}/performance",
        ),
    ],
)
def test_creator_reads_take_creator_id_and_still_answer_to_id(
    monkeypatch: pytest.MonkeyPatch, argv: list[str], path: str
) -> None:
    for flag, warned in (("--creator-id", False), ("--id", True)):
        recorder = _Recorder({"id": ACCOUNT_ID})
        args = parse([*argv, flag, ACCOUNT_ID])
        assert args.creator_id == ACCOUNT_ID
        assert bool(deprecation_notices(args)) is warned
        _run(monkeypatch, [*argv, flag, ACCOUNT_ID], recorder)
        assert recorder.calls[0][1] == path


@pytest.mark.parametrize("action", ["+get", "+get-performance"])
def test_post_reads_take_content_id_and_still_answer_to_id(
    monkeypatch: pytest.MonkeyPatch, action: str
) -> None:
    new = parse(["campaign", "post", action, "--content-id", CONTENT_ID])
    old = parse(["campaign", "post", action, "--id", CONTENT_ID])
    assert new.content_id == old.content_id == CONTENT_ID
    assert deprecation_notices(new) == []
    assert deprecation_notices(old) == [
        "`--id` is deprecated here and will be removed; use `--content-id` (same value)."
    ]
    recorder = _Recorder({"id": CONTENT_ID})
    _run(monkeypatch, ["campaign", "post", action, "--content-id", CONTENT_ID], recorder)
    assert recorder.calls[0][1].startswith(f"/agent-cli/social-media/posts/{CONTENT_ID}")


def test_renamed_id_is_hidden_from_help_and_still_required() -> None:
    parser = build_parser()
    for argv in (["campaign", "creator", "+get"], ["campaign", "post", "+get"]):
        with pytest.raises(SystemExit):
            parser.parse_args(argv)
    sub = parser._subparsers._group_actions[0].choices["campaign"]  # noqa: SLF001
    help_text = (
        sub._subparsers._group_actions[0].choices["creator"]  # noqa: SLF001
        ._subparsers._group_actions[0].choices["+get"]  # noqa: SLF001
        .format_help()
    )
    assert "--creator-id" in help_text
    assert "--id " not in help_text


# -- one list shape for both kinds --------------------------------------------------------


def _creators_page(path: str) -> dict[str, Any]:
    assert path == f"/agent-cli/campaign-monitors/{CAMPAIGN_ID}/creators"
    return {
        "domain": "campaign-monitor",
        "result": {
            "data": {
                "creators": [
                    {
                        "id": ACCOUNT_ID,
                        "creator_social_account_id": ACCOUNT_ID,
                        "platform": "tiktok",
                        "username": "handle",
                        "views": 120,
                        "membership_created_at": "2026-11-01T00:00:00+00:00",
                        "performance": {"views": 120, "likes": 7},
                        "monitor_id": "internal",
                    }
                ],
                "collection": {"id": CAMPAIGN_ID, "title": "Launch"},
            },
            "pagination": {"page": 1, "limit": 1, "total": 3, "total_pages": 3},
            "meta": {"is_stale": False},
        },
    }


@pytest.mark.parametrize("kind", ["ugc", "tracking"])
def test_creator_list_answers_one_shape_for_either_kind(
    monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    result = _run(
        monkeypatch,
        ["campaign", "creator", "+list", "--campaign-id", CAMPAIGN_ID, "--page-size", "1"],
        _Recorder(_creators_page),
        kind,
    )

    data = result["data"]
    assert data["source_kind"] == kind
    assert data["campaign"] == {"id": CAMPAIGN_ID, "title": "Launch"}
    (item,) = data["items"]
    assert set(item) == {*campaign_data.CREATOR_ITEM_FIELDS, "source_kind"}
    assert item["creator_social_account_id"] == ACCOUNT_ID
    assert (item["views"], item["likes"], item["added_at"]) == (
        120,
        7,
        "2026-11-01T00:00:00+00:00",
    )
    assert (data["total"], data["page"], data["page_size"], data["has_more"]) == (3, 1, 1, True)
    assert result["page_info"]["has_more"] is True


def test_creator_list_all_follows_pages_of_the_normalized_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def page(path: str) -> dict[str, Any]:
        body = _creators_page(path)
        return body

    recorder = _Recorder(page)
    pages = iter([1, 2, 3])

    async def api(cfg: Config, method: str, path: str, **kwargs: Any) -> Any:
        body = await recorder(cfg, method, path, **kwargs)
        number = next(pages)
        body["result"]["pagination"]["page"] = number
        return body

    result = _run(
        monkeypatch,
        ["campaign", "creator", "+list", "--campaign-id", CAMPAIGN_ID, "--page-size", "1", "--all"],
        api,
    )
    assert len(result["data"]["items"]) == 3
    assert result["page_info"]["complete"] is True


def test_empty_ugc_content_list_points_at_the_content_tab(monkeypatch: pytest.MonkeyPatch) -> None:
    empty = {
        "data": {"content": [], "collection": {"id": CAMPAIGN_ID, "title": "UGC"}},
        "pagination": {"page": 1, "limit": 20, "total": 0, "total_pages": 0},
    }
    argv = ["campaign", "content", "+list", "--campaign-id", CAMPAIGN_ID]

    ugc = _run(monkeypatch, argv, _Recorder(empty), "ugc")
    assert ugc["data"]["items"] == [] and ugc["data"]["source_kind"] == "ugc"
    assert any("campaign video +list" in step for step in ugc["next_steps"])

    tracking = _run(monkeypatch, argv, _Recorder(empty), "tracking")
    assert not any("campaign video +list" in step for step in tracking["next_steps"])


# -- a window before the read -------------------------------------------------------------


@pytest.mark.parametrize(
    "argv",
    [
        ["campaign", "format", "+list", "--campaign-id", CAMPAIGN_ID],
        ["campaign", "format", "+list", "--campaign-id", CAMPAIGN_ID, "--date-from", "2026-10-01"],
        [
            "campaign",
            "format-post",
            "+list",
            "--campaign-id",
            CAMPAIGN_ID,
            "--brief-id",
            CONTENT_ID,
        ],
        ["campaign", "analytics", "+get"],
        ["campaign", "analytics", "+get", "--all-time", "--date-from", "2026-10-01"],
    ],
)
def test_window_reads_refuse_before_any_request(
    monkeypatch: pytest.MonkeyPatch, argv: list[str]
) -> None:
    async def explode(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("no request without a window")

    monkeypatch.setattr(main_module, "load_config", _cfg)
    monkeypatch.setattr(main_module, "api_data", explode)
    monkeypatch.setattr(main_module, "api_data_v2", explode)
    with pytest.raises(ValueError, match="--all-time"):
        asyncio.run(main_module.dispatch(parse(argv)))


@pytest.mark.parametrize(
    "window",
    [["--all-time"], ["--date-from", "2026-10-01", "--date-to", "2026-10-28"]],
)
def test_window_reads_send_a_window(monkeypatch: pytest.MonkeyPatch, window: list[str]) -> None:
    sent: list[dict[str, Any]] = []

    async def api(cfg: Config, method: str, path: str, **kwargs: Any) -> Any:
        sent.append(kwargs.get("params") or {})
        return {"items": []}

    monkeypatch.setattr(main_module, "load_config", _cfg)
    monkeypatch.setattr(main_module, "api_data_v2", api)
    asyncio.run(
        main_module.dispatch(
            parse(["campaign", "format", "+list", "--campaign-id", CAMPAIGN_ID, *window])
        )
    )
    assert sent[0].get("all_time") is True or sent[0].get("date_from") == "2026-10-01"


# -- what became of an import -------------------------------------------------------------


def _task(status: str, *, failures: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    summary = {"total": 2, "succeeded": 1, "failed": 1, "skipped": 0} if failures else {}
    return {
        "data": {
            "id": TASK_ID,
            "type": "bulk_add_content",
            "collection_id": CAMPAIGN_ID,
            "status": status,
            "result": {"summary": summary, "details": {"failures": failures or []}},
        }
    }


def _add_api(task_states: list[dict[str, Any]]) -> tuple[_Recorder, Any]:
    states = iter(task_states)

    def respond(path: str) -> Any:
        if path == f"/agent-cli/campaign-monitors/{CAMPAIGN_ID}/content":
            return {
                "domain": "campaign-monitor",
                "result": {
                    "campaign_id": CAMPAIGN_ID,
                    "requested_content_urls": [BAD_URL],
                    "content_id_task": None,
                    "url_import_task": {"task": {"id": TASK_ID, "status": "pending"}},
                },
            }
        assert path == f"/tasks/{TASK_ID}"
        return next(states)

    return _Recorder(respond), respond


ADD = ["campaign", "content", "+add", "--campaign-id", CAMPAIGN_ID, "--url", BAD_URL]


def test_add_without_wait_says_how_to_read_the_outcome(monkeypatch: pytest.MonkeyPatch) -> None:
    recorder, _ = _add_api([])
    result = _run(monkeypatch, ADD, recorder)

    assert [call[1] for call in recorder.calls] == [
        f"/agent-cli/campaign-monitors/{CAMPAIGN_ID}/content"
    ]
    assert any(f"campaign import +get --id {TASK_ID}" in step for step in result["next_steps"])


def test_add_wait_reports_each_failed_url(monkeypatch: pytest.MonkeyPatch) -> None:
    failure = {"reference": BAD_URL, "reference_type": "url", "message": "Invalid content id"}
    recorder, _ = _add_api([_task("running"), _task("completed", failures=[failure])])
    slept: list[float] = []

    async def no_sleep(seconds: float) -> None:
        slept.append(seconds)

    monkeypatch.setattr(campaign_data.asyncio, "sleep", no_sleep)
    result = _run(monkeypatch, [*ADD, "--wait", "--poll-interval", "1"], recorder)

    (outcome,) = result["data"]["imports"]
    assert outcome["status"] == "completed" and outcome["done"] is True
    assert outcome["summary"]["failed"] == 1
    assert outcome["failures"] == [failure]
    assert result["warnings"] == [f"Not imported: {BAD_URL}: Invalid content id"]
    assert slept == [1.0]


def test_add_wait_that_times_out_says_how_to_keep_checking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorder, _ = _add_api([_task("running")])
    ticks = iter([0.0, 10.0])
    monkeypatch.setattr(campaign_data, "_clock", lambda: next(ticks))
    result = _run(monkeypatch, [*ADD, "--wait", "--timeout", "5", "--poll-interval", "1"], recorder)

    assert result["data"]["imports"][0]["done"] is False
    assert any("still running" in warning for warning in result["warnings"])
    assert any(f"campaign import +get --id {TASK_ID}" in step for step in result["next_steps"])


def test_import_get_reads_the_task_and_refuses_other_tasks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failure = {"reference": BAD_URL, "reference_type": "url", "message": "Invalid content id"}
    result = _run(
        monkeypatch,
        ["campaign", "import", "+get", "--id", TASK_ID],
        _Recorder(_task("completed", failures=[failure])),
    )
    assert result["data"]["kind"] == "content"
    assert result["data"]["failures"] == [failure]

    other = {"data": {"id": TASK_ID, "type": "sync_collection", "status": "completed"}}
    with pytest.raises(ValueError, match="not a creator or post import"):
        _run(monkeypatch, ["campaign", "import", "+get", "--id", TASK_ID], _Recorder(other))
