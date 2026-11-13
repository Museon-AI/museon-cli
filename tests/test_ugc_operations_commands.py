"""Day-to-day UGC writes: tasks, enrollments, review, messaging, recruiting.

Each command calls the route the web calls, with the web's compare-and-set inputs, and
an outbound or irreversible one answers with its dry-run preview until --yes is given.
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

import httpx
import pytest

import museoncli.main as cli
from museoncli.config import AuthState, Config, OrganizationState
from museoncli.main import build_parser

ORG = "70000000-0000-4000-8000-000000000001"
CAMPAIGN = "10000000-0000-4000-8000-000000000001"
TASK = "60000000-0000-4000-8000-000000000001"
USER = "70000000-0000-4000-8000-000000000007"
ENROLLMENT = "40000000-0000-4000-8000-000000000001"
OTHER_ENROLLMENT = "40000000-0000-4000-8000-000000000002"
CREATIVE = "30000000-0000-4000-8000-000000000001"
OTHER_CREATIVE = "30000000-0000-4000-8000-000000000002"
THREAD = "b0000000-0000-4000-8000-000000000001"
CONTENT = "a0000000-0000-4000-8000-000000000001"
OTHER_CONTENT = "a0000000-0000-4000-8000-000000000002"
LINK = "d0000000-0000-4000-8000-000000000001"
INVITATION = "e0000000-0000-4000-8000-000000000001"
INTENT = "c0000000-0000-4000-8000-000000000001"
PERSONA = "80000000-0000-4000-8000-000000000001"
PAYSCALE = "90000000-0000-4000-8000-000000000001"
OLD_PAYSCALE = "90000000-0000-4000-8000-000000000002"
UPDATED = "2026-11-13T08:00:00+00:00"
ROSTER = f"/ugc/campaigns/{CAMPAIGN}/enrollments"
CREATIVES = f"/ugc/campaigns/{CAMPAIGN}/creatives"


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
    cfg.organization = OrganizationState(id=ORG, name="MuseOn")
    monkeypatch.setattr(cli, "load_config", lambda: cfg)
    monkeypatch.setattr(cli, "api_data_v2", workbench)
    return asyncio.run(cli.dispatch(build_parser().parse_args(argv)))


def _task(**extra: Any) -> dict[str, Any]:
    return {
        "id": TASK,
        "kind": "review_creative",
        "status": "open",
        "queue": "content_review",
        "campaign_id": CAMPAIGN,
        "due_at": None,
        "overdue": False,
        "assignee_user_ids": [],
        "claimed_by_user_id": None,
        "claimed_until": None,
        "updated_at": UPDATED,
        "actions": ["approve", "reject"],
        "context": {},
        **extra,
    }


def _enrollment(enrollment_id: str = ENROLLMENT, **extra: Any) -> dict[str, Any]:
    return {
        "id": enrollment_id,
        "status": "pending",
        "updated_at": UPDATED,
        "persona_id": None,
        "payscale_id": OLD_PAYSCALE,
        "contract_status": None,
        "creator": {"id": "c1", "display_name": "Ava"},
        "remove_blockers": [],
        "warmup_admit_blockers": [],
        "trial": None,
        **extra,
    }


def _roster(*rows: dict[str, Any]) -> Any:
    return {"items": list(rows), "next_cursor": None}


# -- tasks ---------------------------------------------------------------------


def test_task_claim_posts_to_the_claim_route(monkeypatch: pytest.MonkeyPatch) -> None:
    workbench = _Workbench(
        {
            ("GET", f"/ugc/tasks/{TASK}"): _task(),
            ("POST", f"/ugc/tasks/{TASK}/claim"): _task(claimed_by_user_id=USER),
        }
    )

    result = _run(monkeypatch, workbench, ["ugc", "task", "+claim", "--id", TASK])

    assert result["command"] == "ugc.task-claim"
    assert result["organization"] == {"id": ORG, "name": "MuseOn"}
    assert workbench.writes() == [
        {"method": "POST", "path": f"/ugc/tasks/{TASK}/claim", "json_body": None}
    ]
    assert result["data"]["task"]["claimed_by_user_id"] == USER


def test_task_release_deletes_the_claim(monkeypatch: pytest.MonkeyPatch) -> None:
    workbench = _Workbench(
        {
            ("GET", f"/ugc/tasks/{TASK}"): _task(claimed_by_user_id=USER),
            ("DELETE", f"/ugc/tasks/{TASK}/claim"): _task(),
        }
    )

    _run(monkeypatch, workbench, ["ugc", "task", "+release", "--id", TASK])

    assert [(call["method"], call["path"]) for call in workbench.writes()] == [
        ("DELETE", f"/ugc/tasks/{TASK}/claim")
    ]


def test_task_set_due_reads_the_version_it_compares_on(monkeypatch: pytest.MonkeyPatch) -> None:
    workbench = _Workbench(
        {
            ("GET", f"/ugc/tasks/{TASK}"): _task(),
            ("PUT", f"/ugc/tasks/{TASK}/due"): _task(due_at="2026-11-20T10:00:00+00:00"),
        }
    )

    _run(
        monkeypatch,
        workbench,
        ["ugc", "task", "+set-due", "--id", TASK, "--due-at", "2026-11-20T18:00:00+08:00"],
    )

    assert workbench.writes()[0]["json_body"] == {
        "due_at": "2026-11-20T18:00:00+08:00",
        "expected_updated_at": UPDATED,
    }


def test_task_set_due_with_expected_version_writes_without_a_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workbench = _Workbench({("PUT", f"/ugc/tasks/{TASK}/due"): _task()})

    _run(
        monkeypatch,
        workbench,
        [
            "ugc", "task", "+set-due", "--id", TASK, "--due-at", "none",
            "--expected-updated-at", "2026-11-12T00:00:00+00:00",
        ],
    )

    assert workbench.calls == [
        {
            "method": "PUT",
            "path": f"/ugc/tasks/{TASK}/due",
            "json_body": {"due_at": None, "expected_updated_at": "2026-11-12T00:00:00+00:00"},
        }
    ]


def test_task_set_assignees_replaces_the_set(monkeypatch: pytest.MonkeyPatch) -> None:
    workbench = _Workbench(
        {
            ("GET", f"/ugc/tasks/{TASK}"): _task(),
            ("PUT", f"/ugc/tasks/{TASK}/assignee"): _task(assignee_user_ids=[USER]),
        }
    )

    _run(
        monkeypatch,
        workbench,
        ["ugc", "task", "+set-assignees", "--id", TASK, "--assignee-user-id", USER],
    )

    assert workbench.writes()[0]["json_body"] == {
        "assignee_user_ids": [USER],
        "expected_updated_at": UPDATED,
    }


def test_task_comment_and_defer_send_their_bodies(monkeypatch: pytest.MonkeyPatch) -> None:
    workbench = _Workbench(
        {
            ("GET", f"/ugc/tasks/{TASK}"): _task(),
            ("POST", f"/ugc/tasks/{TASK}/comments"): _task(),
            ("POST", f"/ugc/tasks/{TASK}/reminder-deferrals"): {"task_id": TASK},
        }
    )

    _run(monkeypatch, workbench, ["ugc", "task", "+comment", "--id", TASK, "--body", " Chased "])
    _run(monkeypatch, workbench, ["ugc", "task", "+defer-reminder", "--id", TASK])

    assert [call["json_body"] for call in workbench.writes()] == [{"body": "Chased"}, {}]


def test_task_run_action_without_yes_answers_with_its_preview(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workbench = _Workbench({("GET", f"/ugc/tasks/{TASK}"): _task()})

    with pytest.raises(cli.ConfirmationRequired) as refused:
        _run(
            monkeypatch,
            workbench,
            ["ugc", "task", "+run-action", "--id", TASK, "--action", "reject", "--comments", "Redo"],
        )

    assert workbench.writes() == []
    preview = refused.value.preview
    assert preview["data"]["dry_run"] is True
    assert preview["data"]["body"] == {"comments": "Redo", "expected_updated_at": UPDATED}
    payload, code = cli.error_envelope(refused.value, command="ugc.task-run-action")
    assert payload["reason"] == "confirmation_required"
    assert payload["preview"] == preview
    assert "--yes" in payload["error"]["hint"]
    assert code == cli.EXIT_FAILURE


def test_task_run_action_fills_the_card_version_like_the_web(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = _task(
        kind="judge_attribution",
        actions=["attach", "attach_unpaid", "skip"],
        context={"card_version": "v7"},
    )
    workbench = _Workbench(
        {
            ("GET", f"/ugc/tasks/{TASK}"): task,
            ("POST", f"/ugc/tasks/{TASK}/actions/attach_unpaid"): {
                "task": {"id": TASK, "status": "done"},
                "closed_task_ids": [TASK],
                "opened_task_ids": [],
            },
        }
    )

    result = _run(
        monkeypatch,
        workbench,
        [
            "ugc", "task", "+run-action", "--id", TASK, "--action", "attach-unpaid",
            "--fields-json", json.dumps({"creative_id": CREATIVE}), "--yes",
        ],
    )

    assert workbench.writes()[0]["json_body"] == {
        "creative_id": CREATIVE,
        "expected_card_version": "v7",
        "expected_updated_at": UPDATED,
    }
    assert result["data"]["result"]["closed_task_ids"] == [TASK]


def test_task_run_action_refuses_an_action_the_task_does_not_offer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workbench = _Workbench({("GET", f"/ugc/tasks/{TASK}"): _task()})

    with pytest.raises(RuntimeError, match="task_action_unavailable"):
        _run(
            monkeypatch,
            workbench,
            ["ugc", "task", "+run-action", "--id", TASK, "--action", "skip", "--yes"],
        )
    assert workbench.writes() == []


def test_task_run_action_rejects_unknown_fields() -> None:
    with pytest.raises(ValueError, match="does not take: expected_updated_at"):
        cli.command_payload(
            build_parser().parse_args(
                [
                    "ugc", "task", "+run-action", "--id", TASK, "--action", "approve",
                    "--fields-json", json.dumps({"expected_updated_at": UPDATED}),
                ]
            )
        )


# -- enrollments ---------------------------------------------------------------


def test_enrollment_reject_sends_the_creator_note_with_the_status_it_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workbench = _Workbench(
        {
            ("GET", ROSTER): _roster(_enrollment()),
            ("POST", f"/ugc/enrollments/{ENROLLMENT}/reject"): _enrollment(status="rejected"),
        }
    )

    result = _run(
        monkeypatch,
        workbench,
        [
            "ugc", "enrollment", "+reject", "--campaign-id", CAMPAIGN, "--id", ENROLLMENT,
            "--note", "We are full", "--ban", "--yes",
        ],
    )

    assert workbench.writes()[0]["json_body"] == {
        "expected_status": "pending",
        "note": "We are full",
        "ban": True,
    }
    assert result["data"]["enrollment"]["status"] == "rejected"


def test_enrollment_reject_dry_run_says_the_note_goes_to_the_creator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workbench = _Workbench({("GET", ROSTER): _roster(_enrollment())})

    result = _run(
        monkeypatch,
        workbench,
        [
            "ugc", "enrollment", "+reject", "--campaign-id", CAMPAIGN, "--id", ENROLLMENT,
            "--note", "We are full", "--dry-run",
        ],
    )

    assert workbench.writes() == []
    assert any("written to the creator" in warning for warning in result["warnings"])


def test_enrollment_approve_with_expected_status_reads_only_that_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workbench = _Workbench(
        {
            ("GET", ROSTER): _roster(_enrollment()),
            ("POST", f"/ugc/enrollments/{ENROLLMENT}/approve"): _enrollment(status="onboarding"),
        }
    )

    _run(
        monkeypatch,
        workbench,
        [
            "ugc", "enrollment", "+approve", "--campaign-id", CAMPAIGN, "--id", ENROLLMENT,
            "--expected-status", "pending", "--yes",
        ],
    )

    assert workbench.calls[0]["params"] == {"status": "pending", "limit": 100}
    assert workbench.writes()[0]["json_body"] == {"expected_status": "pending"}


def test_enrollment_approve_refuses_one_that_moved_on(monkeypatch: pytest.MonkeyPatch) -> None:
    workbench = _Workbench({("GET", ROSTER): _roster(_enrollment(status="active"))})

    with pytest.raises(RuntimeError, match="invalid_transition"):
        _run(
            monkeypatch,
            workbench,
            ["ugc", "enrollment", "+approve", "--campaign-id", CAMPAIGN, "--id", ENROLLMENT, "--yes"],
        )
    assert workbench.writes() == []


def test_enrollment_pause_and_resume_compare_on_status(monkeypatch: pytest.MonkeyPatch) -> None:
    workbench = _Workbench(
        {
            ("GET", ROSTER): lambda kwargs: _roster(
                _enrollment(status="paused" if workbench.writes() else "active")
            ),
            ("POST", f"/ugc/enrollments/{ENROLLMENT}/pause"): _enrollment(status="paused"),
            ("POST", f"/ugc/enrollments/{ENROLLMENT}/resume"): _enrollment(status="active"),
        }
    )
    base = ["--campaign-id", CAMPAIGN, "--id", ENROLLMENT]

    _run(monkeypatch, workbench, ["ugc", "enrollment", "+pause", *base])
    _run(monkeypatch, workbench, ["ugc", "enrollment", "+resume", *base])

    assert [(call["path"], call["json_body"]) for call in workbench.writes()] == [
        (f"/ugc/enrollments/{ENROLLMENT}/pause", {"expected_status": "active"}),
        (f"/ugc/enrollments/{ENROLLMENT}/resume", {"expected_status": "paused"}),
    ]


def test_enrollment_admit_records_the_note_and_warmup_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workbench = _Workbench(
        {
            ("GET", ROSTER): _roster(_enrollment(status="onboarding")),
            ("POST", f"/ugc/enrollments/{ENROLLMENT}/admit"): _enrollment(status="active"),
        }
    )

    _run(
        monkeypatch,
        workbench,
        [
            "ugc", "enrollment", "+admit", "--campaign-id", CAMPAIGN, "--id", ENROLLMENT,
            "--note", "Signed in person", "--warmup-not-ready",
        ],
    )

    assert workbench.writes()[0]["json_body"] == {
        "expected_status": "onboarding",
        "note": "Signed in person",
        "expected_missing": ["warmup_not_ready"],
    }


def test_enrollment_remove_sends_each_rows_status_and_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    later = "2026-11-13T09:00:00+00:00"
    workbench = _Workbench(
        {
            ("GET", ROSTER): _roster(
                _enrollment(status="active"),
                _enrollment(OTHER_ENROLLMENT, status="paused", updated_at=later),
            ),
            ("POST", f"/ugc/campaigns/{CAMPAIGN}/enrollments/remove"): {
                "campaign_id": CAMPAIGN,
                "enrollment_ids": [ENROLLMENT, OTHER_ENROLLMENT],
            },
        }
    )

    _run(
        monkeypatch,
        workbench,
        [
            "ugc", "enrollment", "+remove", "--campaign-id", CAMPAIGN,
            "--id", ENROLLMENT, "--id", OTHER_ENROLLMENT, "--yes",
        ],
    )

    assert workbench.writes()[0]["json_body"] == {
        "items": [
            {"enrollment_id": ENROLLMENT, "expected_status": "active", "expected_updated_at": UPDATED},
            {"enrollment_id": OTHER_ENROLLMENT, "expected_status": "paused", "expected_updated_at": later},
        ]
    }


def test_enrollment_remove_without_yes_is_refused_and_writes_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workbench = _Workbench({("GET", ROSTER): _roster(_enrollment(status="active"))})

    with pytest.raises(cli.ConfirmationRequired) as refused:
        _run(
            monkeypatch,
            workbench,
            ["ugc", "enrollment", "+remove", "--campaign-id", CAMPAIGN, "--id", ENROLLMENT],
        )

    assert workbench.writes() == []
    assert refused.value.preview["data"]["enrollments"][0]["id"] == ENROLLMENT


def test_enrollment_remove_refuses_blocked_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    workbench = _Workbench(
        {("GET", ROSTER): _roster(_enrollment(status="active", remove_blockers=["post_in_payout"]))}
    )

    with pytest.raises(RuntimeError, match="removal_blocked"):
        _run(
            monkeypatch,
            workbench,
            ["ugc", "enrollment", "+remove", "--campaign-id", CAMPAIGN, "--id", ENROLLMENT, "--yes"],
        )
    assert workbench.writes() == []


def test_enrollment_not_in_the_campaign_is_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    workbench = _Workbench({("GET", ROSTER): _roster(_enrollment(OTHER_ENROLLMENT))})

    with pytest.raises(RuntimeError, match="not_found: enrollment_not_found"):
        _run(
            monkeypatch,
            workbench,
            ["ugc", "enrollment", "+pause", "--campaign-id", CAMPAIGN, "--id", ENROLLMENT],
        )


def test_enrollment_set_persona_and_payscale(monkeypatch: pytest.MonkeyPatch) -> None:
    workbench = _Workbench(
        {
            ("GET", ROSTER): _roster(_enrollment(status="active")),
            ("PUT", f"/ugc/campaigns/{CAMPAIGN}/enrollments/persona"): {"items": []},
            ("PATCH", f"/ugc/enrollments/{ENROLLMENT}"): _enrollment(payscale_id=PAYSCALE),
        }
    )
    base = ["--campaign-id", CAMPAIGN, "--id", ENROLLMENT]

    _run(monkeypatch, workbench, ["ugc", "enrollment", "+set-persona", *base, "--persona-id", "none"])
    _run(
        monkeypatch,
        workbench,
        ["ugc", "enrollment", "+set-payscale", *base, "--payscale-id", PAYSCALE],
    )

    assert [call["json_body"] for call in workbench.writes()] == [
        {"enrollment_ids": [ENROLLMENT], "persona_id": None},
        {"payscale_id": PAYSCALE, "expected_updated_at": UPDATED},
    ]


def test_enrollment_graduate_trial_sends_the_payscale_it_leaves(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trial = {"on_trial": True, "graduate_blockers": []}
    workbench = _Workbench(
        {
            ("GET", ROSTER): _roster(_enrollment(status="active", trial=trial)),
            ("POST", f"/ugc/enrollments/{ENROLLMENT}/graduate-trial"): _enrollment(),
        }
    )

    _run(
        monkeypatch,
        workbench,
        ["ugc", "enrollment", "+graduate-trial", "--campaign-id", CAMPAIGN, "--id", ENROLLMENT],
    )

    assert workbench.writes()[0]["json_body"] == {
        "expected_updated_at": UPDATED,
        "expected_payscale_id": OLD_PAYSCALE,
    }


# -- review and counting -------------------------------------------------------


def _creative(creative_id: str = CREATIVE, **extra: Any) -> dict[str, Any]:
    return {
        "id": creative_id,
        "ugc_creator_id": "c1",
        "review_status": "needs_review",
        "updated_at": UPDATED,
        **extra,
    }


def test_creative_review_reject_sends_the_note_and_status(monkeypatch: pytest.MonkeyPatch) -> None:
    workbench = _Workbench(
        {
            ("GET", CREATIVES): [_creative()],
            ("POST", f"/ugc/creatives/{CREATIVE}/review"): _creative(review_status="rejected"),
        }
    )

    _run(
        monkeypatch,
        workbench,
        [
            "ugc", "creative", "+review", "--campaign-id", CAMPAIGN, "--id", CREATIVE,
            "--decision", "reject", "--note", "Redo the hook", "--yes",
        ],
    )

    assert workbench.writes()[0]["json_body"] == {
        "decision": "rejected",
        "expected_status": "needs_review",
        "note": "Redo the hook",
    }


def test_creative_set_counting_and_merge(monkeypatch: pytest.MonkeyPatch) -> None:
    workbench = _Workbench(
        {
            ("GET", CREATIVES): [_creative(review_status="approved"), _creative(OTHER_CREATIVE)],
            ("PUT", f"{CREATIVES}/{CREATIVE}/counting"): {"counted": False},
            ("POST", f"{CREATIVES}/{CREATIVE}/merge"): {"id": "attr"},
        }
    )
    base = ["--campaign-id", CAMPAIGN, "--id", CREATIVE]

    _run(monkeypatch, workbench, ["ugc", "creative", "+set-counting", *base, "--no-counted"])
    _run(
        monkeypatch,
        workbench,
        ["ugc", "creative", "+merge", *base, "--merged-creative-id", OTHER_CREATIVE, "--yes"],
    )

    assert [call["json_body"] for call in workbench.writes()] == [
        {"counted": False},
        {"merged_creative_ids": [OTHER_CREATIVE]},
    ]


def test_creative_merge_refuses_another_creators_video(monkeypatch: pytest.MonkeyPatch) -> None:
    workbench = _Workbench(
        {("GET", CREATIVES): [_creative(), _creative(OTHER_CREATIVE, ugc_creator_id="c2")]}
    )

    with pytest.raises(RuntimeError, match="video_merge_unavailable"):
        _run(
            monkeypatch,
            workbench,
            [
                "ugc", "creative", "+merge", "--campaign-id", CAMPAIGN, "--id", CREATIVE,
                "--merged-creative-id", OTHER_CREATIVE, "--yes",
            ],
        )
    assert workbench.writes() == []


def test_post_stop_counting_uses_the_single_or_the_selection_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    posts = f"/ugc/campaigns/{CAMPAIGN}/posts"
    workbench = _Workbench(
        {
            ("POST", f"{posts}/{CONTENT}/not-counted"): {"id": "attr"},
            ("POST", f"{posts}/not-counted"): {"outcomes": {}},
            ("POST", f"{posts}/{CONTENT}/split"): {"id": "attr"},
        }
    )
    base = ["--campaign-id", CAMPAIGN, "--id", CONTENT]

    _run(monkeypatch, workbench, ["ugc", "post", "+stop-counting", *base, "--yes"])
    _run(
        monkeypatch,
        workbench,
        ["ugc", "post", "+stop-counting", *base, "--id", OTHER_CONTENT, "--yes"],
    )
    _run(monkeypatch, workbench, ["ugc", "post", "+split", *base, "--yes"])

    assert [(call["path"], call["json_body"]) for call in workbench.writes()] == [
        (f"{posts}/{CONTENT}/not-counted", None),
        (f"{posts}/not-counted", {"content_ids": [CONTENT, OTHER_CONTENT]}),
        (f"{posts}/{CONTENT}/split", None),
    ]


def test_feedback_thread_status_compares_on_the_thread_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = f"{CREATIVES}/{CREATIVE}/feedback-threads/{THREAD}"
    workbench = _Workbench(
        {
            ("GET", path): {"id": THREAD, "status": "open", "updated_at": UPDATED},
            ("PUT", f"{path}/resolution"): {"id": THREAD, "status": "resolved"},
        }
    )

    _run(
        monkeypatch,
        workbench,
        [
            "ugc", "feedback-thread", "+set-status", "--campaign-id", CAMPAIGN,
            "--creative-id", CREATIVE, "--id", THREAD, "--status", "resolved",
        ],
    )

    assert workbench.writes()[0]["json_body"] == {
        "status": "resolved",
        "expected_updated_at": UPDATED,
    }


def test_feedback_thread_create_carries_its_idempotency_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workbench = _Workbench(
        {
            ("GET", CREATIVES): [_creative()],
            ("POST", f"{CREATIVES}/{CREATIVE}/feedback-threads"): {"id": THREAD},
        }
    )

    result = _run(
        monkeypatch,
        workbench,
        [
            "ugc", "feedback-thread", "+create", "--campaign-id", CAMPAIGN,
            "--creative-id", CREATIVE, "--body", "Cut the intro", "--time-ms", "2500",
            "--idempotency-key", "thread-1", "--yes",
        ],
    )

    write = workbench.writes()[0]
    assert write["json_body"] == {"body": "Cut the intro", "time_ms": 2500}
    assert write["idempotency_key"] == "thread-1"
    assert "thread-1" in result["next_steps"][0]


# -- messaging -----------------------------------------------------------------


def test_message_send_to_a_project_conversation_uses_a_submission_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = f"/ugc/enrollments/{ENROLLMENT}/conversation"
    workbench = _Workbench(
        {
            ("GET", path): {"conversation": {"enrollment_id": ENROLLMENT, "can_send": True}},
            ("POST", f"{path}/messages"): {"id": "m1"},
        }
    )

    result = _run(
        monkeypatch,
        workbench,
        ["ugc", "message", "+send", "--enrollment-id", ENROLLMENT, "--body", "Hi", "--yes"],
    )

    body = workbench.writes()[0]["json_body"]
    assert body["body"] == "Hi"
    assert body["submission_key"].startswith("museoncli:message:")
    assert result["data"]["idempotency_key"] == body["submission_key"]


def test_message_send_about_a_video_sends_the_idempotency_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workbench = _Workbench(
        {
            ("GET", CREATIVES): [_creative()],
            ("POST", f"{CREATIVES}/{CREATIVE}/creator-messages"): {"id": "m1"},
        }
    )

    _run(
        monkeypatch,
        workbench,
        [
            "ugc", "message", "+send", "--campaign-id", CAMPAIGN, "--creative-id", CREATIVE,
            "--body", "Reupload in 9:16", "--idempotency-key", "msg-1", "--yes",
        ],
    )

    write = workbench.writes()[0]
    assert write["json_body"] == {"body": "Reupload in 9:16"}
    assert write["idempotency_key"] == "msg-1"


def test_message_send_without_yes_previews_and_sends_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = f"/ugc/enrollments/{ENROLLMENT}/conversation"
    workbench = _Workbench(
        {("GET", path): {"conversation": {"can_send": False, "blockers": ["campaign_read_only"]}}}
    )

    with pytest.raises(cli.ConfirmationRequired) as refused:
        _run(
            monkeypatch,
            workbench,
            ["ugc", "message", "+send", "--enrollment-id", ENROLLMENT, "--body", "Hi"],
        )

    assert workbench.writes() == []
    assert any("campaign_read_only" in warning for warning in refused.value.preview["warnings"])


def test_enrollment_nudges_one_creator_and_the_campaign(monkeypatch: pytest.MonkeyPatch) -> None:
    workbench = _Workbench(
        {
            ("GET", f"/ugc/enrollments/{ENROLLMENT}/creator-checks"): {
                "items": [{"kind": "not_signed", "nudge": "available"}]
            },
            ("POST", f"/ugc/enrollments/{ENROLLMENT}/nudges"): {"check": "not_signed"},
            ("GET", f"/ugc/campaigns/{CAMPAIGN}/creator-checks/summary"): {"quiet": 4},
            ("POST", f"/ugc/campaigns/{CAMPAIGN}/nudges"): {"sent": 4},
        }
    )

    _run(
        monkeypatch,
        workbench,
        ["ugc", "enrollment", "+nudge", "--id", ENROLLMENT, "--check", "not-signed", "--yes"],
    )
    result = _run(
        monkeypatch,
        workbench,
        ["ugc", "enrollment", "+bulk-nudge", "--campaign-id", CAMPAIGN, "--check", "quiet", "--yes"],
    )

    assert [call["json_body"] for call in workbench.writes()] == [
        {"check": "not_signed"},
        {"check": "quiet"},
    ]
    assert result["data"]["result"] == {"sent": 4}


def test_bulk_nudge_preview_counts_creators_per_check(monkeypatch: pytest.MonkeyPatch) -> None:
    workbench = _Workbench(
        {
            ("GET", f"/ugc/campaigns/{CAMPAIGN}/creator-checks/summary"): {
                "cant_track": 1, "not_signed": 2, "not_set_up": 0, "quiet": 4, "not_healthy": 0,
            }
        }
    )

    result = _run(
        monkeypatch,
        workbench,
        ["ugc", "enrollment", "+bulk-nudge", "--campaign-id", CAMPAIGN, "--dry-run"],
    )

    assert workbench.writes() == []
    assert result["data"]["creators_per_check"]["not-signed"] == 2


def test_message_resend_card_and_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    workbench = _Workbench(
        {
            ("GET", f"/ugc/enrollments/{ENROLLMENT}/messages"): {
                "deliveries": [{"intent_id": INTENT, "kind": "contract_card", "status": "failed"}]
            },
            ("POST", f"/ugc/enrollments/{ENROLLMENT}/messages/resend"): {"accepted": True},
            ("POST", f"/ugc/enrollments/{ENROLLMENT}/messages/{INTENT}/retry"): {"accepted": True},
        }
    )

    _run(
        monkeypatch,
        workbench,
        [
            "ugc", "message", "+resend-card", "--enrollment-id", ENROLLMENT,
            "--kind", "contract-card", "--yes",
        ],
    )
    _run(
        monkeypatch,
        workbench,
        ["ugc", "message", "+retry", "--enrollment-id", ENROLLMENT, "--id", INTENT, "--yes"],
    )

    assert [(call["path"], call["json_body"]) for call in workbench.writes()] == [
        (f"/ugc/enrollments/{ENROLLMENT}/messages/resend", {"kind": "contract_card"}),
        (f"/ugc/enrollments/{ENROLLMENT}/messages/{INTENT}/retry", None),
    ]


# -- recruiting ----------------------------------------------------------------


def _link(**extra: Any) -> dict[str, Any]:
    return {
        "id": LINK,
        "kind": "invite",
        "name": "TikTok ads",
        "group_name": "Wave1",
        "payscale_id": None,
        "auto_approve": True,
        "public_listing": False,
        "skip_trial": False,
        "status": "active",
        "updated_at": UPDATED,
        **extra,
    }


def test_recruit_link_create_list_and_discover(monkeypatch: pytest.MonkeyPatch) -> None:
    links = f"/ugc/campaigns/{CAMPAIGN}/recruitment-links"
    workbench = _Workbench(
        {
            ("POST", links): _link(),
            ("POST", f"{links}/discovery"): _link(kind="discover"),
            ("GET", links): {"items": [_link()], "discovery": None, "next_cursor": None},
        }
    )

    _run(
        monkeypatch,
        workbench,
        [
            "ugc", "recruit-link", "+create", "--campaign-id", CAMPAIGN, "--name", "TikTok ads",
            "--code", "tiktok2026", "--auto-approve",
        ],
    )
    _run(
        monkeypatch,
        workbench,
        ["ugc", "recruit-link", "+create", "--campaign-id", CAMPAIGN, "--kind", "discover"],
    )
    listed = _run(
        monkeypatch, workbench, ["ugc", "recruit-link", "+list", "--campaign-id", CAMPAIGN]
    )

    assert [call["json_body"] for call in workbench.writes()] == [
        {"code": "tiktok2026", "name": "TikTok ads", "auto_approve": True},
        None,
    ]
    assert workbench.calls[-1]["params"] == {"limit": 50}
    assert listed["data"]["items"][0]["id"] == LINK


def test_recruit_link_update_sends_every_setting_with_the_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    links = f"/ugc/campaigns/{CAMPAIGN}/recruitment-links"
    workbench = _Workbench(
        {
            ("GET", links): {"items": [_link()], "next_cursor": None},
            ("PUT", f"{links}/{LINK}"): _link(auto_approve=False),
            ("POST", f"{links}/{LINK}/revoke"): _link(status="revoked"),
        }
    )
    base = ["--campaign-id", CAMPAIGN, "--id", LINK]

    _run(monkeypatch, workbench, ["ugc", "recruit-link", "+update", *base, "--no-auto-approve"])
    _run(monkeypatch, workbench, ["ugc", "recruit-link", "+revoke", *base, "--yes"])

    assert [call["json_body"] for call in workbench.writes()] == [
        {
            "name": "TikTok ads",
            "group_name": "Wave1",
            "payscale_id": None,
            "auto_approve": False,
            "public_listing": False,
            "skip_trial": False,
            "expected_updated_at": UPDATED,
        },
        {"expected_updated_at": UPDATED},
    ]


def test_invitation_create_resend_and_revoke(monkeypatch: pytest.MonkeyPatch) -> None:
    invitations = f"/ugc/campaigns/{CAMPAIGN}/invitations"
    row = {"id": INVITATION, "address": "ava@example.com", "status": "open"}
    workbench = _Workbench(
        {
            ("POST", invitations): row,
            ("GET", invitations): {"items": [row], "next_cursor": None},
            ("POST", f"/ugc/invitations/{INVITATION}/resend"): row,
            ("POST", f"/ugc/invitations/{INVITATION}/revoke"): {**row, "status": "revoked"},
        }
    )
    base = ["--campaign-id", CAMPAIGN, "--id", INVITATION]

    _run(
        monkeypatch,
        workbench,
        [
            "ugc", "invitation", "+create", "--campaign-id", CAMPAIGN,
            "--email", "ava@example.com", "--yes",
        ],
    )
    _run(monkeypatch, workbench, ["ugc", "invitation", "+resend", *base, "--yes"])
    _run(monkeypatch, workbench, ["ugc", "invitation", "+revoke", *base, "--yes"])

    assert [(call["path"], call["json_body"]) for call in workbench.writes()] == [
        (invitations, {"channel": "email", "address": "ava@example.com"}),
        (f"/ugc/invitations/{INVITATION}/resend", {"expected_status": "open"}),
        (f"/ugc/invitations/{INVITATION}/revoke", {"expected_status": "open"}),
    ]


def test_invitation_preview_flags_an_open_invitation_to_the_address(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invitations = f"/ugc/campaigns/{CAMPAIGN}/invitations"
    workbench = _Workbench(
        {
            ("GET", invitations): {
                "items": [{"id": INVITATION, "address": "Ava@Example.com", "status": "open"}],
                "next_cursor": None,
            }
        }
    )

    result = _run(
        monkeypatch,
        workbench,
        [
            "ugc", "invitation", "+create", "--campaign-id", CAMPAIGN,
            "--email", "ava@example.com", "--dry-run",
        ],
    )

    assert workbench.writes() == []
    assert result["data"]["open_invitations_to_this_address"][0]["id"] == INVITATION


# -- the HTTP layer --------------------------------------------------------------


@pytest.mark.parametrize(
    ("argv", "method", "path", "idempotency_key"),
    [
        (
            ["ugc", "task", "+claim", "--id", TASK],
            "POST",
            f"/api/v2/ugc/tasks/{TASK}/claim",
            None,
        ),
        (
            [
                "ugc", "message", "+send", "--campaign-id", CAMPAIGN, "--creative-id", CREATIVE,
                "--body", "Hi", "--idempotency-key", "msg-1", "--yes",
            ],
            "POST",
            f"/api/v2/ugc/campaigns/{CAMPAIGN}/creatives/{CREATIVE}/creator-messages",
            "msg-1",
        ),
    ],
)
def test_writes_address_the_organization_and_carry_their_key(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
    method: str,
    path: str,
    idempotency_key: str | None,
) -> None:
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "GET" and request.url.path.endswith("/creatives"):
            data: Any = [_creative()]
        elif request.method == "GET":
            data = _task()
        else:
            data = {"id": "x"}
        return httpx.Response(200, json={"success": True, "data": data})

    client = httpx.AsyncClient
    monkeypatch.setattr(
        cli.httpx, "AsyncClient", lambda **kw: client(**kw, transport=httpx.MockTransport(handle))
    )
    cfg = Config(
        api_base_url="https://api.example.test/api/v1",
        auth=AuthState(api_key="test-only"),
        organization=OrganizationState(id=ORG, name="MuseOn"),
    )
    monkeypatch.setattr(cli, "load_config", lambda: cfg)
    monkeypatch.setattr(sys, "argv", ["museoncli", *argv])

    try:
        cli.main()
    except SystemExit as exited:
        assert exited.code in (0, None)
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert "workspace" not in payload
    write = next(request for request in requests if request.method != "GET")
    assert (write.method, write.url.path) == (method, path)
    for request in requests:
        assert request.headers["X-Organization-Id"] == ORG
        assert "workspace" not in request.url.query.decode()
        assert b"workspace_id" not in request.content
    assert write.headers.get("Idempotency-Key") == idempotency_key


def test_confirmation_refusal_prints_the_preview(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    workbench = _Workbench(
        {
            ("GET", f"/ugc/enrollments/{ENROLLMENT}/creator-checks"): {
                "items": [{"kind": "quiet", "nudge": "nudged_today"}]
            }
        }
    )
    cfg = Config(auth=AuthState(api_key="test-only"), organization=OrganizationState(id=ORG))
    monkeypatch.setattr(cli, "load_config", lambda: cfg)
    monkeypatch.setattr(cli, "api_data_v2", workbench)
    monkeypatch.setattr(
        sys, "argv", ["museoncli", "ugc", "enrollment", "+nudge", "--id", ENROLLMENT, "--check", "quiet"]
    )

    with pytest.raises(SystemExit) as exited:
        cli.main()

    payload = json.loads(capsys.readouterr().out)
    assert exited.value.code == cli.EXIT_FAILURE
    assert payload["ok"] is False
    assert payload["reason"] == "confirmation_required"
    assert payload["preview"]["data"]["holds"] is True
    assert any("already nudged today" in warning for warning in payload["preview"]["warnings"])
    assert workbench.writes() == []
