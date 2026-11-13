"""UGC content review and counting: verdicts, feedback threads, counting, split and merge.

The web's content review routes. A verdict and every feedback thread or reply is
read by the creator, so those need --yes; splitting, merging and taking posts out of
the count cannot be undone from the CLI, so they do too. Counting a video again or
stopping it is a plain write (the creator is not told).
"""

from __future__ import annotations

import argparse
from typing import Any

from museoncli.domains._model import CommandSpec, Domain
from museoncli.domains._shared import _direct_output_schema, dekebab, kebab_choices
from museoncli.domains._ugc_writes import (
    CAMPAIGN_ID,
    DRY_RUN,
    OUTBOUND,
    OUTBOUND_NOTE,
    ROLE_COUNTING,
    ROLE_REVIEW,
    ROLE_TEAM,
    WRITE,
    _ask_next_step,
    _dicts,
    _get,
    _plural,
    _schema,
    _uuid,
    _uuid_property,
    _with_notes,
    add_dry_run,
    add_yes,
    call,
    idempotency_key,
    new_key,
    pick,
    same_key_next_step,
    text,
    uuids,
)
from museoncli.execution import CommandContext, compact_params

REVIEW_STATUSES = ["needs_review", "approved", "rejected", "excluded"]
DECISIONS = {"approve": "approved", "reject": "rejected"}
THREAD_STATUSES = ["open", "resolved"]
_CREATIVE_FIELDS = (
    "id",
    "ugc_creator_id",
    "brief_id",
    "review_status",
    "review_note",
    "source_url",
    "updated_at",
)


async def _creatives(ctx: CommandContext, ids: list[str]) -> dict[str, dict[str, Any]]:
    """The campaign's creatives by id (one unpaged read, as ugc creative +list does)."""
    rows = _dicts(await _get(ctx, f"/campaigns/{ctx.arguments['campaign_id']}/creatives"))
    found = {str(row.get("id")): row for row in rows if row.get("id") in ids}
    missing = [value for value in ids if value not in found]
    if missing:
        raise RuntimeError(
            "not_found: creative_not_found: no such creative in this campaign: "
            + ", ".join(missing)
        )
    return found


# -- executors -----------------------------------------------------------------


async def _execute_review(ctx: CommandContext) -> Any:
    args = ctx.arguments
    creative = (await _creatives(ctx, [args["id"]]))[args["id"]]
    expected = args.get("expected_status") or creative.get("review_status") or "needs_review"
    body = compact_params(
        {
            "decision": args["decision"],
            "expected_status": expected,
            "note": args.get("note"),
            "review_classification": args.get("review_classification"),
        }
    )
    data: dict[str, Any] = {
        "dry_run": args["dry_run"],
        "creative": pick(creative, *_CREATIVE_FIELDS),
        "body": body,
    }
    warnings: list[str] = []
    if args["decision"] == "rejected":
        warnings.append(
            "Rejecting sends the creator the note and puts their assignment back in progress."
        )
    else:
        warnings.append("Approving tells the creator the video was approved.")
    if creative.get("review_status") not in (None, expected):
        warnings.append(
            f"The creative is {creative.get('review_status')}, not {expected}; the workbench "
            "will refuse the verdict."
        )
    if args["dry_run"]:
        return data, warnings, [_ask_next_step("the verdict and the note the creator reads")]
    written = await call(ctx, "POST", f"/creatives/{args['id']}/review", body)
    data["creative"] = pick(written, *_CREATIVE_FIELDS) if isinstance(written, dict) else written
    return data, [], []


async def _execute_set_counting(ctx: CommandContext) -> Any:
    args = ctx.arguments
    creative = (await _creatives(ctx, [args["id"]]))[args["id"]]
    data: dict[str, Any] = {
        "dry_run": args["dry_run"],
        "creative": pick(creative, *_CREATIVE_FIELDS),
        "counted": args["counted"],
    }
    warnings: list[str] = []
    if creative.get("review_status") not in ("approved", "excluded", None):
        warnings.append(
            "Only an approved or excluded video moves; the workbench refuses this one "
            "(invalid_transition)."
        )
    if not args["counted"]:
        warnings.append(
            "Stopping the count is refused while a payout pays for the video or its posts."
        )
    if args["dry_run"]:
        return data, warnings, [_ask_next_step("the video and whether it would count")]
    data["result"] = await call(
        ctx,
        "PUT",
        f"/campaigns/{args['campaign_id']}/creatives/{args['id']}/counting",
        {"counted": args["counted"]},
    )
    return data, [], []


async def _execute_merge(ctx: CommandContext) -> Any:
    args = ctx.arguments
    merged: list[str] = args["merged_creative_ids"]
    rows = await _creatives(ctx, list(dict.fromkeys([args["id"], *merged])))
    target = rows[args["id"]]
    data: dict[str, Any] = {
        "dry_run": args["dry_run"],
        "into": pick(target, *_CREATIVE_FIELDS),
        "merged": [pick(rows[key], *_CREATIVE_FIELDS) for key in merged],
    }
    others = [key for key in merged if rows[key].get("ugc_creator_id") != target.get("ugc_creator_id")]
    if others:
        raise RuntimeError(
            "conflict: video_merge_unavailable: only videos of the same creator merge; "
            + ", ".join(others)
            + " belong to someone else."
        )
    warnings = [
        f"Every post of {_plural(len(merged), 'video', 'videos')} moves into the target and the "
        "emptied videos are deleted; the CLI cannot undo it."
    ]
    if args["dry_run"]:
        return data, warnings, [_ask_next_step("which videos merge into which")]
    data["result"] = await call(
        ctx,
        "POST",
        f"/campaigns/{args['campaign_id']}/creatives/{args['id']}/merge",
        {"merged_creative_ids": merged},
    )
    return data, [], []


async def _execute_stop_counting(ctx: CommandContext) -> Any:
    args = ctx.arguments
    ids: list[str] = args["ids"]
    campaign = args["campaign_id"]
    data: dict[str, Any] = {"dry_run": args["dry_run"], "content_ids": ids}
    warnings = [
        f"{_plural(len(ids), 'post stops', 'posts stop')} counting toward the Campaign and its "
        "settlement; a post a payout already pays for refuses the whole request. The CLI "
        "cannot count them again."
    ]
    if args["dry_run"]:
        # No per-post read: the workbench decides each post when it is sent.
        return data, warnings, [_ask_next_step("which posts would stop counting")]
    if len(ids) == 1:
        data["result"] = await call(ctx, "POST", f"/campaigns/{campaign}/posts/{ids[0]}/not-counted")
    else:
        data["result"] = await call(
            ctx, "POST", f"/campaigns/{campaign}/posts/not-counted", {"content_ids": ids}
        )
    return data, [], []


async def _execute_split(ctx: CommandContext) -> Any:
    args = ctx.arguments
    data: dict[str, Any] = {"dry_run": args["dry_run"], "content_id": args["id"]}
    warnings = [
        "The post becomes a video of its own under the same Format; the CLI cannot merge it "
        "back except with ugc creative +merge."
    ]
    if args["dry_run"]:
        return data, warnings, [_ask_next_step("which post would become its own video")]
    data["result"] = await call(
        ctx, "POST", f"/campaigns/{args['campaign_id']}/posts/{args['id']}/split"
    )
    return data, [], []


def _thread_path(args: dict[str, Any]) -> str:
    return f"/campaigns/{args['campaign_id']}/creatives/{args['creative_id']}/feedback-threads"


async def _execute_thread_create(ctx: CommandContext) -> Any:
    args = ctx.arguments
    creative = (await _creatives(ctx, [args["creative_id"]]))[args["creative_id"]]
    key = args.get("idempotency_key") or new_key("feedback-thread")
    body = compact_params({"body": args["body"], "time_ms": args.get("time_ms")})
    data: dict[str, Any] = {
        "dry_run": args["dry_run"],
        "creative": pick(creative, *_CREATIVE_FIELDS),
        "body": body,
        "idempotency_key": key,
    }
    warnings = ["The creator reads this thread on the video and it is pushed to their Discord."]
    if args["dry_run"]:
        return data, warnings, [_ask_next_step("the feedback the creator would read")]
    data["thread"] = await call(ctx, "POST", _thread_path(args), body, idempotency_key=key)
    return data, [], [same_key_next_step(key)]


async def _execute_thread_reply(ctx: CommandContext) -> Any:
    args = ctx.arguments
    thread = await _get(ctx, f"{_thread_path(args)}/{args['id']}")
    key = args.get("idempotency_key") or new_key("feedback-reply")
    data: dict[str, Any] = {
        "dry_run": args["dry_run"],
        "thread": pick(thread, "id", "status", "body", "updated_at"),
        "reply": args["body"],
        "idempotency_key": key,
    }
    warnings = ["The creator reads the reply in the video's thread."]
    if args["dry_run"]:
        return data, warnings, [_ask_next_step("the reply the creator would read")]
    data["reply"] = await call(
        ctx,
        "POST",
        f"{_thread_path(args)}/{args['id']}/replies",
        {"body": args["body"]},
        idempotency_key=key,
    )
    return data, [], [same_key_next_step(key)]


async def _execute_thread_set_status(ctx: CommandContext) -> Any:
    args = ctx.arguments
    thread = await _get(ctx, f"{_thread_path(args)}/{args['id']}")
    thread = thread if isinstance(thread, dict) else {}
    data: dict[str, Any] = {
        "dry_run": args["dry_run"],
        "thread": pick(thread, "id", "status", "body", "updated_at"),
        "after": args["status"],
    }
    if thread.get("status") == args["status"]:
        return data, [f"The thread is already {args['status']}; nothing was written."], []
    if args["dry_run"]:
        return data, [], [_ask_next_step("the thread and its new status")]
    data["thread"] = await call(
        ctx,
        "PUT",
        f"{_thread_path(args)}/{args['id']}/resolution",
        {"status": args["status"], "expected_updated_at": thread.get("updated_at")},
    )
    return data, [], []


# -- arguments -----------------------------------------------------------------


def _add_campaign(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--campaign-id", required=True)


def _campaign(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "campaign_id": _uuid(args.campaign_id, flag="--campaign-id"),
        "dry_run": bool(args.dry_run),
    }


def _add_one(parser: argparse.ArgumentParser) -> None:
    _add_campaign(parser)
    parser.add_argument("--id", required=True)
    add_dry_run(parser)


def _one(args: argparse.Namespace) -> dict[str, Any]:
    return {**_campaign(args), "id": _uuid(args.id, flag="--id")}


def _add_review(parser: argparse.ArgumentParser) -> None:
    _add_one(parser)
    parser.add_argument("--decision", required=True, choices=list(DECISIONS))
    parser.add_argument("--note")
    parser.add_argument("--strategist-original", action="store_true")
    parser.add_argument("--expected-status", choices=kebab_choices(REVIEW_STATUSES))
    add_yes(parser)


def _review_args(args: argparse.Namespace) -> dict[str, Any]:
    return {
        **_one(args),
        "decision": DECISIONS[args.decision],
        **compact_params(
            {
                "note": text(args.note, flag="--note", limit=5000),
                "review_classification": "strategist_original" if args.strategist_original else None,
                "expected_status": dekebab(args.expected_status),
            }
        ),
    }


def _add_set_counting(parser: argparse.ArgumentParser) -> None:
    _add_one(parser)
    parser.add_argument("--counted", action=argparse.BooleanOptionalAction, required=True)


def _set_counting_args(args: argparse.Namespace) -> dict[str, Any]:
    return {**_one(args), "counted": bool(args.counted)}


def _add_merge(parser: argparse.ArgumentParser) -> None:
    _add_one(parser)
    parser.add_argument(
        "--merged-creative-id", action="append", dest="merged_creative_ids", required=True
    )
    add_yes(parser)


def _merge_args(args: argparse.Namespace) -> dict[str, Any]:
    target = _one(args)
    merged = uuids(args.merged_creative_ids, flag="--merged-creative-id", limit=10)
    if target["id"] in merged:
        raise ValueError("--merged-creative-id must not include the target --id.")
    return {**target, "merged_creative_ids": merged}


def _add_stop_counting(parser: argparse.ArgumentParser) -> None:
    _add_campaign(parser)
    parser.add_argument("--id", action="append", dest="ids", required=True)
    add_dry_run(parser)
    add_yes(parser)


def _stop_counting_args(args: argparse.Namespace) -> dict[str, Any]:
    return {**_campaign(args), "ids": uuids(args.ids, flag="--id", limit=100)}


def _add_split(parser: argparse.ArgumentParser) -> None:
    _add_one(parser)
    add_yes(parser)


def _add_thread_create(parser: argparse.ArgumentParser) -> None:
    _add_campaign(parser)
    parser.add_argument("--creative-id", required=True)
    parser.add_argument("--body", required=True)
    parser.add_argument("--time-ms", type=int)
    parser.add_argument("--idempotency-key")
    add_dry_run(parser)
    add_yes(parser)


def _thread_create_args(args: argparse.Namespace) -> dict[str, Any]:
    if args.time_ms is not None and not 0 <= args.time_ms <= 2_147_483_647:
        raise ValueError("--time-ms must be a non-negative number of milliseconds.")
    return {
        **_campaign(args),
        "creative_id": _uuid(args.creative_id, flag="--creative-id"),
        "body": text(args.body, flag="--body", limit=4000, required=True),
        **compact_params(
            {
                "time_ms": args.time_ms,
                "idempotency_key": idempotency_key(args.idempotency_key),
            }
        ),
    }


def _add_thread_reply(parser: argparse.ArgumentParser) -> None:
    _add_thread_create(parser)
    parser.add_argument("--id", required=True)


def _thread_reply_args(args: argparse.Namespace) -> dict[str, Any]:
    if args.time_ms is not None:
        raise ValueError("--time-ms belongs to a new thread, not a reply.")
    return {**_thread_create_args(args), "id": _uuid(args.id, flag="--id")}


def _add_thread_set_status(parser: argparse.ArgumentParser) -> None:
    _add_campaign(parser)
    parser.add_argument("--creative-id", required=True)
    parser.add_argument("--id", required=True)
    parser.add_argument("--status", required=True, choices=THREAD_STATUSES)
    add_dry_run(parser)


def _thread_set_status_args(args: argparse.Namespace) -> dict[str, Any]:
    return {
        **_campaign(args),
        "creative_id": _uuid(args.creative_id, flag="--creative-id"),
        "id": _uuid(args.id, flag="--id"),
        "status": args.status,
    }


# -- specs ---------------------------------------------------------------------

_CREATIVE_ID = _uuid_property("Creative (video) ID from ugc creative +list.")
_IDEMPOTENCY = {
    "type": "string",
    "maxLength": 128,
    "description": (
        "Stable key for this message; the CLI makes one when left out and returns it. Retry an "
        "unknown outcome with the same key and text."
    ),
}


def specs() -> list[CommandSpec]:
    domain = Domain.UGC
    campaign = "11111111-1111-4111-8111-111111111111"
    creative = "33333333-3333-4333-8333-333333333333"
    other = "33333333-3333-4333-8333-333333333334"
    content = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    thread = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    return [
        CommandSpec(
            domain=domain,
            resource="creative",
            shortcut="+review",
            summary=(
                "Approve or reject a UGC creative (video), compare-and-set on its review status. "
                "The creator is told; a rejection sends them --note and puts their assignment "
                "back in progress. The team usually decides through the review task (ugc task "
                "+run-action); this is the direct verdict, also open to Brand editors on a "
                "shared Campaign." + OUTBOUND_NOTE + ROLE_REVIEW
            ),
            adapter_tool_name="ugc_creative_review",
            input_schema=_schema(
                {
                    "campaign_id": CAMPAIGN_ID,
                    "id": _CREATIVE_ID,
                    "decision": {"type": "string", "enum": list(DECISIONS)},
                    "note": {
                        "type": "string",
                        "description": "What the creator should change (sent with a rejection).",
                    },
                    "strategist_original": {
                        "type": "boolean",
                        "description": "Classify the video as the strategist's own original cut.",
                    },
                    "expected_status": {
                        "type": "string",
                        "enum": kebab_choices(REVIEW_STATUSES),
                        "description": "Review status you saw; read from the creative when left out.",
                    },
                    "dry_run": DRY_RUN,
                },
                ["campaign_id", "id", "decision"],
            ),
            output_schema=_direct_output_schema("dry_run, creative and body."),
            examples=[
                f"museoncli ugc creative +review --campaign-id {campaign} --id {creative} "
                "--decision reject --note 'Show the product in the first 3 seconds' --dry-run"
            ],
            add_arguments=_add_review,
            build_arguments=_review_args,
            **OUTBOUND,
        ),
        CommandSpec(
            domain=domain,
            resource="creative",
            shortcut="+set-counting",
            summary=(
                "Count an approved video again (--counted) or stop counting it (--no-counted); "
                "the creator is not told. Refused while a payout pays for it." + ROLE_TEAM
            ),
            adapter_tool_name="ugc_creative_set_counting",
            input_schema=_schema(
                {
                    "campaign_id": CAMPAIGN_ID,
                    "id": _CREATIVE_ID,
                    "counted": {"type": "boolean"},
                    "dry_run": DRY_RUN,
                },
                ["campaign_id", "id", "counted"],
            ),
            output_schema=_direct_output_schema(
                "dry_run, creative, counted and result (creative_id, counted, review_status)."
            ),
            examples=[
                f"museoncli ugc creative +set-counting --campaign-id {campaign} --id {creative} "
                "--no-counted --dry-run"
            ],
            add_arguments=_add_set_counting,
            build_arguments=_set_counting_args,
            **WRITE,
        ),
        CommandSpec(
            domain=domain,
            resource="creative",
            shortcut="+merge",
            summary=(
                "Merge up to 10 other videos of the same creator into this one: every post "
                "moves here and the emptied videos are deleted." + OUTBOUND_NOTE + ROLE_TEAM
            ),
            adapter_tool_name="ugc_creative_merge",
            input_schema=_schema(
                {
                    "campaign_id": CAMPAIGN_ID,
                    "id": _uuid_property("The video the others merge into."),
                    "merged_creative_ids": {
                        "type": "array",
                        "items": {"type": "string", "format": "uuid"},
                        "minItems": 1,
                        "maxItems": 10,
                        "description": "Videos of the same creator to merge in.",
                    },
                    "dry_run": DRY_RUN,
                },
                ["campaign_id", "id", "merged_creative_ids"],
            ),
            output_schema=_direct_output_schema("dry_run, into, merged and result."),
            examples=[
                f"museoncli ugc creative +merge --campaign-id {campaign} --id {creative} "
                f"--merged-creative-id {other} --dry-run"
            ],
            add_arguments=_add_merge,
            build_arguments=_merge_args,
            **OUTBOUND,
        ),
        CommandSpec(
            domain=domain,
            resource="post",
            shortcut="+stop-counting",
            summary=(
                "Take up to 100 posts out of what a UGC campaign counts (the web's not "
                "counted; repeat --id with content IDs). A post a payout pays for refuses the "
                "whole request." + OUTBOUND_NOTE + ROLE_COUNTING
            ),
            adapter_tool_name="ugc_post_stop_counting",
            input_schema=_schema(
                {
                    "campaign_id": CAMPAIGN_ID,
                    "ids": {
                        "type": "array",
                        "items": {"type": "string", "format": "uuid"},
                        "minItems": 1,
                        "maxItems": 100,
                        "description": "Content IDs of the posts (repeat --id).",
                    },
                    "dry_run": DRY_RUN,
                },
                ["campaign_id", "ids"],
            ),
            output_schema=_direct_output_schema(
                "dry_run, content_ids and result (an attribution, or outcomes per post)."
            ),
            examples=[
                f"museoncli ugc post +stop-counting --campaign-id {campaign} --id {content} --dry-run"
            ],
            add_arguments=_add_stop_counting,
            build_arguments=_stop_counting_args,
            **OUTBOUND,
        ),
        CommandSpec(
            domain=domain,
            resource="post",
            shortcut="+split",
            summary=(
                "Make one confirmed post a video of its own under the same Format (the web's "
                "split)." + OUTBOUND_NOTE + ROLE_TEAM
            ),
            adapter_tool_name="ugc_post_split",
            input_schema=_schema(
                {
                    "campaign_id": CAMPAIGN_ID,
                    "id": _uuid_property("Content ID of the post."),
                    "dry_run": DRY_RUN,
                },
                ["campaign_id", "id"],
            ),
            output_schema=_direct_output_schema("dry_run, content_id and result (attribution)."),
            examples=[
                f"museoncli ugc post +split --campaign-id {campaign} --id {content} --dry-run"
            ],
            add_arguments=_add_split,
            build_arguments=_one,
            **OUTBOUND,
        ),
        CommandSpec(
            domain=domain,
            resource="feedback-thread",
            shortcut="+create",
            summary=(
                "Start a feedback thread on a creative (optionally at --time-ms into the "
                "video); the creator reads it and it is pushed to their Discord." + OUTBOUND_NOTE
                + ROLE_REVIEW
            ),
            adapter_tool_name="ugc_feedback_thread_create",
            input_schema=_schema(
                {
                    "campaign_id": CAMPAIGN_ID,
                    "creative_id": _CREATIVE_ID,
                    "body": {"type": "string", "minLength": 1, "maxLength": 4000},
                    "time_ms": {
                        "type": "integer",
                        "minimum": 0,
                        "description": "Point in the video the feedback is about, in ms.",
                    },
                    "idempotency_key": _IDEMPOTENCY,
                    "dry_run": DRY_RUN,
                },
                ["campaign_id", "creative_id", "body"],
            ),
            output_schema=_direct_output_schema("dry_run, creative, body, idempotency_key, thread."),
            examples=[
                f"museoncli ugc feedback-thread +create --campaign-id {campaign} "
                f"--creative-id {creative} --body 'Cut the intro' --time-ms 2500 --dry-run"
            ],
            add_arguments=_add_thread_create,
            build_arguments=_thread_create_args,
            **OUTBOUND,
        ),
        CommandSpec(
            domain=domain,
            resource="feedback-thread",
            shortcut="+reply",
            summary=(
                "Reply in a creative's feedback thread; the creator reads it." + OUTBOUND_NOTE
                + ROLE_REVIEW
            ),
            adapter_tool_name="ugc_feedback_thread_reply",
            input_schema=_schema(
                {
                    "campaign_id": CAMPAIGN_ID,
                    "creative_id": _CREATIVE_ID,
                    "id": _uuid_property("Feedback thread ID."),
                    "body": {"type": "string", "minLength": 1, "maxLength": 4000},
                    "idempotency_key": _IDEMPOTENCY,
                    "dry_run": DRY_RUN,
                },
                ["campaign_id", "creative_id", "id", "body"],
            ),
            output_schema=_direct_output_schema(
                "dry_run, thread, reply and idempotency_key."
            ),
            examples=[
                f"museoncli ugc feedback-thread +reply --campaign-id {campaign} "
                f"--creative-id {creative} --id {thread} --body 'Looks good now' --dry-run"
            ],
            add_arguments=_add_thread_reply,
            build_arguments=_thread_reply_args,
            **OUTBOUND,
        ),
        CommandSpec(
            domain=domain,
            resource="feedback-thread",
            shortcut="+set-status",
            summary=(
                "Resolve a creative's feedback thread or open it again, compare-and-set on the "
                "thread's updated_at." + ROLE_REVIEW
            ),
            adapter_tool_name="ugc_feedback_thread_set_status",
            input_schema=_schema(
                {
                    "campaign_id": CAMPAIGN_ID,
                    "creative_id": _CREATIVE_ID,
                    "id": _uuid_property("Feedback thread ID."),
                    "status": {"type": "string", "enum": THREAD_STATUSES},
                    "dry_run": DRY_RUN,
                },
                ["campaign_id", "creative_id", "id", "status"],
            ),
            output_schema=_direct_output_schema("dry_run, thread and after."),
            examples=[
                f"museoncli ugc feedback-thread +set-status --campaign-id {campaign} "
                f"--creative-id {creative} --id {thread} --status resolved"
            ],
            add_arguments=_add_thread_set_status,
            build_arguments=_thread_set_status_args,
            **WRITE,
        ),
    ]


EXECUTORS = {
    "ugc.creative-review": _with_notes(_execute_review),
    "ugc.creative-set-counting": _with_notes(_execute_set_counting),
    "ugc.creative-merge": _with_notes(_execute_merge),
    "ugc.post-stop-counting": _with_notes(_execute_stop_counting),
    "ugc.post-split": _with_notes(_execute_split),
    "ugc.feedback-thread-create": _with_notes(_execute_thread_create),
    "ugc.feedback-thread-reply": _with_notes(_execute_thread_reply),
    "ugc.feedback-thread-set-status": _with_notes(_execute_thread_set_status),
}
