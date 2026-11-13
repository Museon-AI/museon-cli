"""Publishing actions the web's calendar and batch pages offer: approve a schedule item, retry a batch.

``+schedule-approve`` approves one scheduled item of a pool account's publish plan (staff
only on the server). ``+retry-failed`` redrives the failed jobs of one batch publish. Both
work with the organization alone (``X-Organization-Id``): the item or batch is looked up
where it is held, inside that organization, and the body carries no workspace.
"""

from __future__ import annotations

import argparse
from typing import Any

from museoncli.domains._model import CommandSpec, Domain
from museoncli.domains._org_commands import (
    DRY_RUN_PROPERTY,
    add_structured_arguments,
    merged_input,
    output_schema,
    reject_unknown,
    require,
    schema,
    uuid_property,
    with_notes,
)
from museoncli.domains._writes import uuid_arg
from museoncli.execution import CommandContext

_ACCOUNT_ID = uuid_property("Pool account ID (ai-slideshow publish +list-schedules --id).")
_ITEM_ID = uuid_property("Schedule item ID (data[].id of ai-slideshow publish +list-schedules).")
_TASK_ID = uuid_property(
    "Parent task ID of the batch publish (the task_id publish post +schedule returned)."
)
_APPROVE = {"account_id": _ACCOUNT_ID, "schedule_item_id": _ITEM_ID, "dry_run": DRY_RUN_PROPERTY}
_RETRY = {"task_id": _TASK_ID, "dry_run": DRY_RUN_PROPERTY}
_STAFF = " Staff only (the server refuses other callers)."
_ROLE = " Needs owner, admin or operator."


# -- executors ---------------------------------------------------------------


async def _execute_approve(ctx: CommandContext) -> Any:
    args = ctx.arguments
    data = await ctx.api_data_v2(
        ctx.cfg,
        "POST",
        f"/pool-accounts/{args['account_id']}/publish-config/schedule-items/"
        f"{args['schedule_item_id']}/approve",
        json_body={},
    )
    return (
        data,
        [],
        [
            f"museoncli ai-slideshow publish +get-schedule --id {args['account_id']} "
            f"--schedule-item-id {args['schedule_item_id']}"
        ],
    )


async def _execute_retry_failed(ctx: CommandContext) -> Any:
    task_id = ctx.arguments["task_id"]
    if ctx.arguments.get("dry_run"):
        return (
            {
                "dry_run": True,
                "would_retry_failed_jobs_of": task_id,
                "confirm_no_duplicate": True,
            },
            [
                "Retrying publishes the batch's failed jobs again. Only retry when you know "
                "the failed jobs produced no post on the platform: --yes confirms that, and a "
                "job that did post would be posted twice."
            ],
            [
                "Check the failed jobs first (publish job +list --task-id), show the user, "
                "ask them, then run again with --yes."
            ],
        )
    data = await ctx.api_data(
        ctx.cfg,
        "POST",
        f"/pool-accounts/publish/{task_id}/retry-failed",
        json_body={"confirm_no_duplicate": True},
    )
    return (
        data,
        ["A retry is not idempotent: do not run it again until the jobs show their new state."],
        [f"museoncli publish job +list --task-id {task_id}"],
    )


# -- arguments ---------------------------------------------------------------


def _dry_run(args: argparse.Namespace, payload: dict[str, Any]) -> None:
    payload["dry_run"] = bool(getattr(args, "dry_run", False) or payload.get("dry_run"))


def _add_approve_arguments(parser: argparse.ArgumentParser) -> None:
    add_structured_arguments(parser)
    # --id matches the sibling publish +get-schedule / +generate-schedule commands.
    parser.add_argument("--account-id", "--id", dest="account_id")
    parser.add_argument("--schedule-item-id")
    parser.add_argument("--dry-run", action="store_true")


def _build_approve_arguments(args: argparse.Namespace) -> dict[str, Any]:
    payload = merged_input(args, ("account_id", "schedule_item_id"))
    reject_unknown(payload, _APPROVE)
    require(payload, "account_id", "schedule_item_id")
    payload["account_id"] = uuid_arg(payload["account_id"], flag="--account-id")
    payload["schedule_item_id"] = uuid_arg(payload["schedule_item_id"], flag="--schedule-item-id")
    _dry_run(args, payload)
    return payload


def _add_retry_arguments(parser: argparse.ArgumentParser) -> None:
    add_structured_arguments(parser)
    parser.add_argument("--task-id")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--yes", action="store_true")


def _build_retry_arguments(args: argparse.Namespace) -> dict[str, Any]:
    payload = merged_input(args, ("task_id",))
    reject_unknown(payload, _RETRY)
    require(payload, "task_id")
    payload["task_id"] = uuid_arg(payload["task_id"], flag="--task-id")
    _dry_run(args, payload)
    return payload


# -- specs -------------------------------------------------------------------

_EXAMPLE_ID = "72defd40-39ad-40d3-8105-8f23a9a016da"
_EXAMPLE_ITEM = "0d9c3b7a-1f2e-4c5d-8e9f-a0b1c2d3e4f5"


def specs() -> list[CommandSpec]:
    base: dict[str, Any] = {
        "domain": Domain.AI_SLIDESHOW,
        "resource": "publish",
        "execution": "direct",
    }
    return [
        CommandSpec(
            **base,
            shortcut="+schedule-approve",
            summary=(
                "Approve one scheduled item of a pool account's publish plan (an item whose "
                "account requires approval before publish), so it can go out at its time."
                + _STAFF
            ),
            risk_level="write",
            adapter_tool_name="social_account_schedule_approve",
            input_schema=schema(_APPROVE, ["account_id", "schedule_item_id"]),
            output_schema=output_schema("data: the schedule item after approval."),
            examples=[
                f"museoncli ai-slideshow publish +schedule-approve --account-id {_EXAMPLE_ID} "
                f"--schedule-item-id {_EXAMPLE_ITEM}"
            ],
            add_arguments=_add_approve_arguments,
            build_arguments=_build_approve_arguments,
            supports_dry_run=True,
        ),
        CommandSpec(
            **base,
            shortcut="+retry-failed",
            summary=(
                "Retry the failed jobs of one batch publish. Only for failures known to have "
                "produced no post: a job that did post would be posted twice. --dry-run shows "
                "the retry and writes nothing; show it to the user, then run with --yes, which "
                "is the server's duplicate-post confirmation." + _ROLE
            ),
            risk_level="destructive",
            adapter_tool_name="publish_batch_retry_failed",
            input_schema=schema(_RETRY, ["task_id"]),
            output_schema=output_schema(
                "data.would_retry_failed_jobs_of (dry run) or the redrive result."
            ),
            examples=[
                f"museoncli ai-slideshow publish +retry-failed --task-id {_EXAMPLE_ID} --dry-run",
                f"museoncli ai-slideshow publish +retry-failed --task-id {_EXAMPLE_ID} --yes",
            ],
            add_arguments=_add_retry_arguments,
            build_arguments=_build_retry_arguments,
            supports_dry_run=True,
            dry_run_reads_server=True,
            requires_confirmation=True,
        ),
    ]


EXECUTORS = {
    "ai-slideshow.publish-schedule-approve": with_notes(_execute_approve),
    "ai-slideshow.publish-retry-failed": with_notes(_execute_retry_failed),
}
