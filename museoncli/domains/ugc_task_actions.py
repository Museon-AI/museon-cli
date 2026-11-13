"""UGC task writes: claim, release, comment, due date, assignees, reminders and actions.

The same routes as the web's task center (`/api/v2/ugc/tasks/{id}/...`). Due date,
assignees and actions compare-and-set on the task's `updated_at`: pass the one you
read (`--expected-updated-at`), or the CLI reads the task and uses the current one.
"""

from __future__ import annotations

import argparse
import json
import re
from typing import Any

from museoncli.domains._model import CommandSpec, Domain
from museoncli.domains._shared import _direct_output_schema
from museoncli.domains._ugc_writes import (
    DRY_RUN,
    OUTBOUND,
    OUTBOUND_NOTE,
    ROLE_TASK,
    WRITE,
    _ask_next_step,
    _get,
    _schema,
    _uuid,
    _uuid_property,
    _with_notes,
    add_dry_run,
    add_yes,
    call,
    kebab,
    pick,
    text,
    uuids,
)
from museoncli.execution import CommandContext, compact_params

_TASK_FIELDS = (
    "id",
    "kind",
    "status",
    "queue",
    "campaign_id",
    "due_at",
    "overdue",
    "assignee_user_ids",
    "claimed_by_user_id",
    "claimed_until",
    "updated_at",
    "actions",
)
# Fields the action body takes besides `expected_updated_at` (TaskActionWrite).
ACTION_FIELDS = frozenset(
    {
        "attachments",
        "ban",
        "brief_id",
        "card",
        "comments",
        "content_id",
        "creative_id",
        "creator_messages",
        "creator_social_account_id",
        "expected_account_updated_at",
        "expected_card_version",
        "expected_enrollment_updated_at",
        "expected_proof_event_id",
        "historical_approval",
        "intent_id",
        "matches",
        "notes",
        "pay_rate_id",
        "payscale_id",
        "tag_ids",
        "with_content_ids",
    }
)
_ACTION = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
NONE = "none"


async def _task(ctx: CommandContext, task_id: str) -> dict[str, Any]:
    task = await _get(ctx, f"/tasks/{task_id}")
    return task if isinstance(task, dict) else {}


def _summary(task: dict[str, Any]) -> dict[str, Any]:
    line = pick(task, *_TASK_FIELDS)
    line["actions"] = [kebab(action) for action in task.get("actions") or []]
    return line


def _closed(task: dict[str, Any]) -> list[str]:
    status = task.get("status")
    if status and status != "open":
        return [f"The task is {status}; the workbench refuses changes to a closed task."]
    return []


async def _expected_updated_at(ctx: CommandContext) -> tuple[str | None, dict[str, Any] | None]:
    """The updated_at to compare-and-set on, and the task when it had to be read."""
    args = ctx.arguments
    if args.get("expected_updated_at") and not args.get("dry_run"):
        return args["expected_updated_at"], None
    task = await _task(ctx, args["id"])
    return args.get("expected_updated_at") or task.get("updated_at"), task


def _stale(task: dict[str, Any] | None, expected: str | None) -> list[str]:
    if task and expected and task.get("updated_at") and task["updated_at"] != expected:
        return [
            "The task changed since your read (updated_at differs); the workbench will refuse "
            "the write. Read it again and decide on the current version."
        ]
    return []


# -- executors -----------------------------------------------------------------


async def _execute_claim(ctx: CommandContext) -> Any:
    args = ctx.arguments
    task = await _task(ctx, args["id"])
    data: dict[str, Any] = {"dry_run": args["dry_run"], "task": _summary(task)}
    warnings = _closed(task)
    if task.get("claimed_by_user_id"):
        warnings.append(
            "The task is already claimed (claimed_by_user_id); claiming it again renews a claim "
            "you hold and is refused when someone else holds it."
        )
    if args["dry_run"]:
        return data, warnings, [_ask_next_step("the task")]
    data["task"] = _summary(await call(ctx, "POST", f"/tasks/{args['id']}/claim"))
    return data, warnings, []


async def _execute_release(ctx: CommandContext) -> Any:
    args = ctx.arguments
    task = await _task(ctx, args["id"])
    data: dict[str, Any] = {"dry_run": args["dry_run"], "task": _summary(task)}
    if not task.get("claimed_by_user_id"):
        return data, ["Nobody holds a claim on this task; nothing was written."], []
    if args["dry_run"]:
        return data, [], [_ask_next_step("the task and its claim")]
    data["task"] = _summary(await call(ctx, "DELETE", f"/tasks/{args['id']}/claim"))
    return data, [], []


async def _execute_comment(ctx: CommandContext) -> Any:
    args = ctx.arguments
    task = await _task(ctx, args["id"])
    data: dict[str, Any] = {
        "dry_run": args["dry_run"],
        "task": _summary(task),
        "comment": args["body"],
    }
    if args["dry_run"]:
        return data, [], [_ask_next_step("the comment")]
    data["task"] = _summary(
        await call(ctx, "POST", f"/tasks/{args['id']}/comments", {"body": args["body"]})
    )
    return data, [], []


async def _execute_set_due(ctx: CommandContext) -> Any:
    args = ctx.arguments
    expected, task = await _expected_updated_at(ctx)
    data: dict[str, Any] = {
        "dry_run": args["dry_run"],
        "task": _summary(task) if task else {"id": args["id"]},
        "before": (task or {}).get("due_at"),
        "after": args["due_at"],
    }
    warnings = _closed(task or {}) + _stale(task, expected)
    if args["dry_run"]:
        return data, warnings, [_ask_next_step("the due date before and after")]
    data["task"] = _summary(
        await call(
            ctx,
            "PUT",
            f"/tasks/{args['id']}/due",
            {"due_at": args["due_at"], "expected_updated_at": expected},
        )
    )
    return data, warnings, []


async def _execute_set_assignees(ctx: CommandContext) -> Any:
    args = ctx.arguments
    expected, task = await _expected_updated_at(ctx)
    assignees = list(args.get("assignee_user_ids") or [])
    data: dict[str, Any] = {
        "dry_run": args["dry_run"],
        "task": _summary(task) if task else {"id": args["id"]},
        "before": (task or {}).get("assignee_user_ids"),
        "after": assignees,
    }
    warnings = _closed(task or {}) + _stale(task, expected)
    if args["dry_run"]:
        return data, warnings, [_ask_next_step("the assignees before and after")]
    data["task"] = _summary(
        await call(
            ctx,
            "PUT",
            f"/tasks/{args['id']}/assignee",
            {"assignee_user_ids": assignees, "expected_updated_at": expected},
        )
    )
    return data, warnings, []


async def _execute_defer_reminder(ctx: CommandContext) -> Any:
    args = ctx.arguments
    task = await _task(ctx, args["id"])
    body = compact_params({"remind_at": args.get("remind_at"), "reason": args.get("reason")})
    data: dict[str, Any] = {"dry_run": args["dry_run"], "task": _summary(task), "deferral": body}
    if args["dry_run"]:
        return data, _closed(task), [_ask_next_step("when the reminder comes back")]
    data["deferral"] = await call(ctx, "POST", f"/tasks/{args['id']}/reminder-deferrals", body)
    return data, [], []


def action_body(
    task: dict[str, Any], fields: dict[str, Any], expected: str | None
) -> dict[str, Any]:
    """The action body the web sends: the fields given, plus the versions the task carries.

    A `judge_attribution` decision is made on the card version the task shows, and
    picking a payment structure on the application revision (as the web does).
    """
    body = dict(fields)
    context = task.get("context") if isinstance(task.get("context"), dict) else {}
    if task.get("kind") == "judge_attribution" and "expected_card_version" not in body:
        body["expected_card_version"] = context.get("card_version")
    if body.get("payscale_id") and "expected_enrollment_updated_at" not in body:
        body["expected_enrollment_updated_at"] = context.get("enrollment_updated_at")
    body["expected_updated_at"] = expected
    return body


async def _execute_run_action(ctx: CommandContext) -> Any:
    args = ctx.arguments
    task = await _task(ctx, args["id"])
    action = str(args["action"]).replace("-", "_")
    expected = args.get("expected_updated_at") or task.get("updated_at")
    fields = dict(args.get("fields") or {})
    if args.get("comments") is not None:
        fields["comments"] = args["comments"]
    body = action_body(task, fields, expected)
    data: dict[str, Any] = {
        "dry_run": args["dry_run"],
        "task": _summary(task),
        "action": kebab(action),
        "body": body,
    }
    warnings = _closed(task) + _stale(task, args.get("expected_updated_at"))
    available = [str(item) for item in task.get("actions") or []]
    if task and action not in available:
        raise RuntimeError(
            f"conflict: task_action_unavailable: this task offers "
            f"{', '.join(kebab(item) or '' for item in available) or 'no actions'}, not "
            f"{kebab(action)}. Read the task again."
        )
    if args["dry_run"]:
        return data, warnings, [_ask_next_step("the task, the action and what it sends")]
    result = await call(ctx, "POST", f"/tasks/{args['id']}/actions/{action}", body)
    data["result"] = result
    return data, warnings, []


# -- arguments -----------------------------------------------------------------


def _add_id(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--id", required=True)


def _id_args(args: argparse.Namespace) -> dict[str, Any]:
    return {"id": _uuid(args.id, flag="--id"), "dry_run": bool(args.dry_run)}


def _add_plain(parser: argparse.ArgumentParser) -> None:
    _add_id(parser)
    add_dry_run(parser)


def _add_comment(parser: argparse.ArgumentParser) -> None:
    _add_plain(parser)
    parser.add_argument("--body", required=True)


def _build_comment(args: argparse.Namespace) -> dict[str, Any]:
    return {**_id_args(args), "body": text(args.body, flag="--body", limit=5000, required=True)}


def _add_expected(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--expected-updated-at")


def _add_set_due(parser: argparse.ArgumentParser) -> None:
    _add_plain(parser)
    parser.add_argument("--due-at", required=True)
    _add_expected(parser)


def _build_set_due(args: argparse.Namespace) -> dict[str, Any]:
    due = args.due_at.strip()
    return {
        **_id_args(args),
        "due_at": None if due.lower() == NONE else due,
        **compact_params({"expected_updated_at": args.expected_updated_at}),
    }


def _add_set_assignees(parser: argparse.ArgumentParser) -> None:
    _add_plain(parser)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--assignee-user-id", action="append", dest="assignee_user_ids")
    group.add_argument("--unassign", action="store_true")
    _add_expected(parser)


def _build_set_assignees(args: argparse.Namespace) -> dict[str, Any]:
    assignees = (
        []
        if args.unassign
        else uuids(args.assignee_user_ids, flag="--assignee-user-id", limit=20)
    )
    return {
        **_id_args(args),
        "assignee_user_ids": assignees,
        **compact_params({"expected_updated_at": args.expected_updated_at}),
    }


def _add_defer_reminder(parser: argparse.ArgumentParser) -> None:
    _add_plain(parser)
    parser.add_argument("--remind-at")
    parser.add_argument("--reason")


def _build_defer_reminder(args: argparse.Namespace) -> dict[str, Any]:
    if args.reason is not None and args.remind_at is None:
        raise ValueError("--reason goes with --remind-at (a later deferral the same day).")
    return {
        **_id_args(args),
        **compact_params(
            {
                "remind_at": args.remind_at,
                "reason": text(args.reason, flag="--reason", limit=500),
            }
        ),
    }


def _add_run_action(parser: argparse.ArgumentParser) -> None:
    _add_plain(parser)
    parser.add_argument("--action", required=True)
    parser.add_argument("--comments")
    parser.add_argument(
        "--fields-json",
        help=(
            "JSON object of the action's other inputs (creative_id, brief_id, content_id, "
            "payscale_id, creator_messages...); see `museoncli schema ugc.task-run-action`."
        ),
    )
    _add_expected(parser)
    add_yes(parser)


def _build_run_action(args: argparse.Namespace) -> dict[str, Any]:
    action = args.action.strip().lower()
    if not _ACTION.match(action):
        raise ValueError("--action must be one of the task's actions, e.g. approve or attach-unpaid.")
    fields: dict[str, Any] = {}
    if args.fields_json is not None:
        try:
            fields = json.loads(args.fields_json)
        except ValueError as exc:
            raise ValueError("--fields-json must be valid JSON.") from exc
        if not isinstance(fields, dict):
            raise ValueError("--fields-json must be a JSON object.")
        unknown = sorted(set(fields) - ACTION_FIELDS)
        if unknown:
            raise ValueError(
                f"--fields-json has fields the action does not take: {', '.join(unknown)}. "
                "expected_updated_at goes in --expected-updated-at."
            )
    if args.comments is not None and "comments" in fields:
        raise ValueError("Pass the comments once: --comments or comments in --fields-json.")
    return {
        **_id_args(args),
        "action": action,
        **compact_params(
            {
                "comments": text(args.comments, flag="--comments", limit=5000),
                "fields": fields or None,
                "expected_updated_at": args.expected_updated_at,
            }
        ),
    }


# -- specs ---------------------------------------------------------------------

_TASK_ID = _uuid_property("Task ID (from the task list or a task's id).")
_EXPECTED = {
    "type": "string",
    "format": "date-time",
    "description": (
        "updated_at of the task from your latest read; the write fails if the task changed "
        "since. Read from the task when left out."
    ),
}
_TASK_OUTPUT = (
    "dry_run and task (id, kind, status, queue, campaign_id, due_at, overdue, "
    "assignee_user_ids, claimed_by_user_id, claimed_until, updated_at, actions)"
)


def specs() -> list[CommandSpec]:
    domain = Domain.UGC
    task = "66666666-6666-4666-8666-666666666666"
    user = "77777777-7777-4777-8777-777777777777"
    return [
        CommandSpec(
            domain=domain,
            resource="task",
            shortcut="+claim",
            summary=(
                "Claim a UGC task so teammates see you are on it (the web's Claim). --dry-run "
                "shows the task and who holds it now." + ROLE_TASK
            ),
            adapter_tool_name="ugc_task_claim",
            input_schema=_schema({"id": _TASK_ID, "dry_run": DRY_RUN}, ["id"]),
            output_schema=_direct_output_schema(_TASK_OUTPUT + "."),
            examples=[f"museoncli ugc task +claim --id {task}"],
            add_arguments=_add_plain,
            build_arguments=_id_args,
            **WRITE,
        ),
        CommandSpec(
            domain=domain,
            resource="task",
            shortcut="+release",
            summary="Release your claim on a UGC task so someone else can take it." + ROLE_TASK,
            adapter_tool_name="ugc_task_release",
            input_schema=_schema({"id": _TASK_ID, "dry_run": DRY_RUN}, ["id"]),
            output_schema=_direct_output_schema(_TASK_OUTPUT + "."),
            examples=[f"museoncli ugc task +release --id {task}"],
            add_arguments=_add_plain,
            build_arguments=_id_args,
            **WRITE,
        ),
        CommandSpec(
            domain=domain,
            resource="task",
            shortcut="+comment",
            summary=(
                "Add a comment to a UGC task's thread; teammates see it, the creator does not."
                + ROLE_TASK
            ),
            adapter_tool_name="ugc_task_comment",
            input_schema=_schema(
                {
                    "id": _TASK_ID,
                    "body": {"type": "string", "minLength": 1, "maxLength": 5000},
                    "dry_run": DRY_RUN,
                },
                ["id", "body"],
            ),
            output_schema=_direct_output_schema(_TASK_OUTPUT + " and comment."),
            examples=[f"museoncli ugc task +comment --id {task} --body 'Chased on Discord'"],
            add_arguments=_add_comment,
            build_arguments=_build_comment,
            **WRITE,
        ),
        CommandSpec(
            domain=domain,
            resource="task",
            shortcut="+set-due",
            summary=(
                "Set or clear (--due-at none) a UGC task's due time, compare-and-set on the "
                "task's updated_at. --dry-run shows the due time before and after." + ROLE_TASK
            ),
            adapter_tool_name="ugc_task_set_due",
            input_schema=_schema(
                {
                    "id": _TASK_ID,
                    "due_at": {
                        "type": ["string", "null"],
                        "format": "date-time",
                        "description": "Due time with a timezone offset; 'none' clears it.",
                    },
                    "expected_updated_at": _EXPECTED,
                    "dry_run": DRY_RUN,
                },
                ["id", "due_at"],
            ),
            output_schema=_direct_output_schema(_TASK_OUTPUT + ", before and after."),
            examples=[
                f"museoncli ugc task +set-due --id {task} --due-at 2026-11-20T18:00:00+08:00 "
                "--dry-run"
            ],
            add_arguments=_add_set_due,
            build_arguments=_build_set_due,
            **WRITE,
        ),
        CommandSpec(
            domain=domain,
            resource="task",
            shortcut="+set-assignees",
            summary=(
                "Replace a UGC task's assignees (at most 20 organization members) or clear them "
                "with --unassign, compare-and-set on the task's updated_at." + ROLE_TASK
            ),
            adapter_tool_name="ugc_task_set_assignees",
            input_schema=_schema(
                {
                    "id": _TASK_ID,
                    "assignee_user_ids": {
                        "type": "array",
                        "items": {"type": "string", "format": "uuid"},
                        "maxItems": 20,
                        "description": "User IDs of the new assignees; the whole set.",
                    },
                    "unassign": {"type": "boolean", "description": "Leave the task unassigned."},
                    "expected_updated_at": _EXPECTED,
                    "dry_run": DRY_RUN,
                },
                ["id"],
            ),
            output_schema=_direct_output_schema(_TASK_OUTPUT + ", before and after."),
            examples=[f"museoncli ugc task +set-assignees --id {task} --assignee-user-id {user}"],
            add_arguments=_add_set_assignees,
            build_arguments=_build_set_assignees,
            **WRITE,
        ),
        CommandSpec(
            domain=domain,
            resource="task",
            shortcut="+defer-reminder",
            summary=(
                "Snooze a UGC task's reminder: 30 minutes for the day's first deferral; a later "
                "one the same day names --remind-at and --reason." + ROLE_TASK
            ),
            adapter_tool_name="ugc_task_defer_reminder",
            input_schema=_schema(
                {
                    "id": _TASK_ID,
                    "remind_at": {
                        "type": "string",
                        "format": "date-time",
                        "description": "When to remind again (later deferrals the same day).",
                    },
                    "reason": {"type": "string", "maxLength": 500},
                    "dry_run": DRY_RUN,
                },
                ["id"],
            ),
            output_schema=_direct_output_schema("dry_run, task and deferral (task_id, remind_at)."),
            examples=[f"museoncli ugc task +defer-reminder --id {task}"],
            add_arguments=_add_defer_reminder,
            build_arguments=_build_defer_reminder,
            **WRITE,
        ),
        CommandSpec(
            domain=domain,
            resource="task",
            shortcut="+run-action",
            summary=(
                "Run one of a UGC task's actions (the task's actions list them: approve, "
                "reject, attach, skip, resend, send, approve-warmup...), as the web's task "
                "buttons do. Many tell the creator (a rejection's --comments go to them). "
                "The CLI fills the task's card version and application revision like the web; "
                "other inputs go in --fields-json." + OUTBOUND_NOTE + ROLE_TASK
            ),
            adapter_tool_name="ugc_task_run_action",
            input_schema=_schema(
                {
                    "id": _TASK_ID,
                    "action": {
                        "type": "string",
                        "description": "One of the task's actions (kebab or snake case).",
                    },
                    "comments": {
                        "type": "string",
                        "maxLength": 5000,
                        "description": "Reviewer comments; a rejection's comments go to the creator.",
                    },
                    "fields": {
                        "type": "object",
                        "description": (
                            "Other action inputs (--fields-json): creative_id, brief_id, "
                            "content_id, with_content_ids, payscale_id, creator_messages, notes, "
                            "tag_ids, card, intent_id, creator_social_account_id, "
                            "expected_proof_event_id, expected_account_updated_at, matches, "
                            "pay_rate_id, ban, attachments, historical_approval."
                        ),
                    },
                    "expected_updated_at": _EXPECTED,
                    "dry_run": DRY_RUN,
                },
                ["id", "action"],
            ),
            output_schema=_direct_output_schema(
                "dry_run, task, action, body and result (task, closed_task_ids, opened_task_ids)."
            ),
            examples=[
                f"museoncli ugc task +run-action --id {task} --action reject "
                "--comments 'Show the product in the first 3 seconds' --dry-run",
                f"museoncli ugc task +run-action --id {task} --action attach "
                '--fields-json \'{"creative_id":"33333333-3333-4333-8333-333333333333"}\' --yes',
            ],
            add_arguments=_add_run_action,
            build_arguments=_build_run_action,
            **OUTBOUND,
        ),
    ]


EXECUTORS = {
    "ugc.task-claim": _with_notes(_execute_claim),
    "ugc.task-release": _with_notes(_execute_release),
    "ugc.task-comment": _with_notes(_execute_comment),
    "ugc.task-set-due": _with_notes(_execute_set_due),
    "ugc.task-set-assignees": _with_notes(_execute_set_assignees),
    "ugc.task-defer-reminder": _with_notes(_execute_defer_reminder),
    "ugc.task-run-action": _with_notes(_execute_run_action),
}
