"""UGC creator messaging: nudges, project messages, video messages and card resends.

Everything here reaches the creator, so every command needs --yes; without it (or with
--dry-run) the CLI answers with a preview read from the same routes the web shows
first: which checks hold, the conversation, the delivery ledger.
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
    ROLE_MESSAGE,
    _ask_next_step,
    _dicts,
    _get,
    _schema,
    _uuid,
    _uuid_property,
    _with_notes,
    add_dry_run,
    add_yes,
    call,
    idempotency_key,
    kebab,
    new_key,
    pick,
    same_key_next_step,
    text,
)
from museoncli.execution import CommandContext, compact_params

CHECKS = ["cant_track", "not_signed", "not_set_up", "quiet", "not_healthy"]
CARDS = ["contract_card", "onboarding_card"]


# -- nudges --------------------------------------------------------------------


async def _execute_nudge(ctx: CommandContext) -> Any:
    args = ctx.arguments
    checks = await _get(ctx, f"/enrollments/{args['id']}/creator-checks")
    rows = _dicts(checks.get("items") if isinstance(checks, dict) else None)
    row = next((item for item in rows if item.get("kind") == args["check"]), None)
    data: dict[str, Any] = {
        "dry_run": args["dry_run"],
        "check": kebab(args["check"]),
        "holds": row is not None,
        "creator": pick(row, "creator_id", "creator_name", "nudge", "last_nudged_at"),
    }
    warnings: list[str] = []
    if row is None:
        warnings.append(
            "This check does not hold for the creator now; the workbench refuses the nudge "
            "(nudge_not_applicable)."
        )
    elif row.get("nudge") == "nudged_today":
        warnings.append("The creator was already nudged today; the workbench refuses another.")
    elif row.get("nudge") == "unavailable":
        warnings.append(
            "No Discord channel to nudge in (Discord onboarding off or no Discord identity)."
        )
    if args["dry_run"]:
        return data, warnings, [_ask_next_step("whom this reminds and about what")]
    data["nudge"] = await call(
        ctx, "POST", f"/enrollments/{args['id']}/nudges", {"check": args["check"]}
    )
    return data, [], []


async def _execute_bulk_nudge(ctx: CommandContext) -> Any:
    args = ctx.arguments
    summary = await _get(ctx, f"/campaigns/{args['campaign_id']}/creator-checks/summary")
    summary = summary if isinstance(summary, dict) else {}
    check = args.get("check")
    counts = {kebab(key): summary.get(key) for key in ([check] if check else CHECKS)}
    data: dict[str, Any] = {
        "dry_run": args["dry_run"],
        "check": kebab(check) if check else "every-check",
        "creators_per_check": counts,
        "as_of": summary.get("as_of"),
    }
    warnings = [
        "Each creator a check holds for gets a Discord reminder; anyone already nudged today "
        "or without a channel is skipped. One creator with two checks counts in both."
    ]
    if args["dry_run"]:
        return data, warnings, [_ask_next_step("how many creators each reminder reaches")]
    data["result"] = await call(
        ctx,
        "POST",
        f"/campaigns/{args['campaign_id']}/nudges",
        compact_params({"check": check}),
    )
    return data, [], []


# -- messages ------------------------------------------------------------------


async def _execute_send(ctx: CommandContext) -> Any:
    args = ctx.arguments
    key = args.get("idempotency_key") or new_key("message")
    if args.get("creative_id"):
        return await _send_about_creative(ctx, key)
    page = await _get(ctx, f"/enrollments/{args['enrollment_id']}/conversation", {"limit": 1})
    conversation = page.get("conversation") if isinstance(page, dict) else None
    conversation = conversation if isinstance(conversation, dict) else {}
    data: dict[str, Any] = {
        "dry_run": args["dry_run"],
        "conversation": pick(
            conversation, "enrollment_id", "campaign_name", "enrollment_status", "can_send", "blockers"
        ),
        "body": args["body"],
        "idempotency_key": key,
    }
    warnings = [
        "The creator reads this on their MuseOn project page; it is not pushed to Discord or email."
    ]
    if conversation and not conversation.get("can_send"):
        warnings.append(
            "The conversation does not accept messages now ("
            + ", ".join(str(item) for item in conversation.get("blockers") or [])
            + ")."
        )
    if args["dry_run"]:
        return data, warnings, [_ask_next_step("the message and who reads it")]
    data["message"] = await call(
        ctx,
        "POST",
        f"/enrollments/{args['enrollment_id']}/conversation/messages",
        {"body": args["body"], "submission_key": key},
    )
    return data, [], [same_key_next_step(key)]


async def _send_about_creative(ctx: CommandContext, key: str) -> Any:
    args = ctx.arguments
    creatives = _dicts(await _get(ctx, f"/campaigns/{args['campaign_id']}/creatives"))
    creative = next((row for row in creatives if row.get("id") == args["creative_id"]), None)
    if creative is None:
        raise RuntimeError("not_found: creative_not_found: no such creative in this campaign")
    data: dict[str, Any] = {
        "dry_run": args["dry_run"],
        "creative": pick(creative, "id", "ugc_creator_id", "review_status", "source_url"),
        "body": args["body"],
        "idempotency_key": key,
    }
    warnings = ["The creator reads this on the video and it is pushed to their Discord channel."]
    if args["dry_run"]:
        return data, warnings, [_ask_next_step("the message and the video it is about")]
    data["message"] = await call(
        ctx,
        "POST",
        f"/campaigns/{args['campaign_id']}/creatives/{args['creative_id']}/creator-messages",
        {"body": args["body"]},
        idempotency_key=key,
    )
    return data, [], [same_key_next_step(key)]


async def _deliveries(ctx: CommandContext) -> list[dict[str, Any]]:
    view = await _get(ctx, f"/enrollments/{ctx.arguments['enrollment_id']}/messages")
    return _dicts(view.get("deliveries") if isinstance(view, dict) else None)


async def _execute_resend_card(ctx: CommandContext) -> Any:
    args = ctx.arguments
    card = args["kind"]
    deliveries = [row for row in await _deliveries(ctx) if card in str(row.get("kind") or "")]
    data: dict[str, Any] = {
        "dry_run": args["dry_run"],
        "kind": kebab(card),
        "earlier_deliveries": [pick(row, "intent_id", "kind", "status", "error_code") for row in deliveries],
    }
    warnings = ["The creator gets the card again; the delivery ledger picks the channel."]
    if args["dry_run"]:
        return data, warnings, [_ask_next_step("which card the creator would get again")]
    data["result"] = await call(
        ctx, "POST", f"/enrollments/{args['enrollment_id']}/messages/resend", {"kind": card}
    )
    return data, [], []


async def _execute_retry(ctx: CommandContext) -> Any:
    args = ctx.arguments
    delivery = next(
        (row for row in await _deliveries(ctx) if row.get("intent_id") == args["id"]), None
    )
    if delivery is None:
        raise RuntimeError(
            "not_found: message_not_found: this enrollment has no message " + args["id"]
        )
    data: dict[str, Any] = {
        "dry_run": args["dry_run"],
        "delivery": pick(delivery, "intent_id", "kind", "status", "error_code"),
    }
    if args["dry_run"]:
        return data, ["Retrying delivers the message to the creator again."], [
            _ask_next_step("which message would be delivered again")
        ]
    data["result"] = await call(
        ctx, "POST", f"/enrollments/{args['enrollment_id']}/messages/{args['id']}/retry"
    )
    return data, [], []


# -- arguments -----------------------------------------------------------------


def _add_nudge(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--id", required=True)
    parser.add_argument("--check", required=True, choices=kebab_choices(CHECKS))
    add_dry_run(parser)
    add_yes(parser)


def _nudge_args(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "id": _uuid(args.id, flag="--id"),
        "check": dekebab(args.check),
        "dry_run": bool(args.dry_run),
    }


def _add_bulk_nudge(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--check", choices=kebab_choices(CHECKS))
    add_dry_run(parser)
    add_yes(parser)


def _bulk_nudge_args(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "campaign_id": _uuid(args.campaign_id, flag="--campaign-id"),
        "dry_run": bool(args.dry_run),
        **compact_params({"check": dekebab(args.check)}),
    }


def _add_send(parser: argparse.ArgumentParser) -> None:
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--enrollment-id")
    target.add_argument("--creative-id")
    parser.add_argument("--campaign-id")
    parser.add_argument("--body", required=True)
    parser.add_argument("--idempotency-key")
    add_dry_run(parser)
    add_yes(parser)


def _send_args(args: argparse.Namespace) -> dict[str, Any]:
    about_creative = args.creative_id is not None
    if about_creative and args.campaign_id is None:
        raise ValueError("--creative-id needs --campaign-id (the video's UGC campaign).")
    if not about_creative and args.campaign_id is not None:
        raise ValueError("--campaign-id goes with --creative-id; a project message needs only --enrollment-id.")
    return {
        **(
            {
                "campaign_id": _uuid(args.campaign_id, flag="--campaign-id"),
                "creative_id": _uuid(args.creative_id, flag="--creative-id"),
            }
            if about_creative
            else {"enrollment_id": _uuid(args.enrollment_id, flag="--enrollment-id")}
        ),
        "body": text(
            args.body, flag="--body", limit=2100 if about_creative else 5000, required=True
        ),
        "dry_run": bool(args.dry_run),
        **compact_params({"idempotency_key": idempotency_key(args.idempotency_key)}),
    }


def _add_resend_card(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--enrollment-id", required=True)
    parser.add_argument("--kind", required=True, choices=kebab_choices(CARDS))
    add_dry_run(parser)
    add_yes(parser)


def _resend_card_args(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "enrollment_id": _uuid(args.enrollment_id, flag="--enrollment-id"),
        "kind": dekebab(args.kind),
        "dry_run": bool(args.dry_run),
    }


def _add_retry(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--enrollment-id", required=True)
    parser.add_argument("--id", required=True)
    add_dry_run(parser)
    add_yes(parser)


def _retry_args(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "enrollment_id": _uuid(args.enrollment_id, flag="--enrollment-id"),
        "id": _uuid(args.id, flag="--id"),
        "dry_run": bool(args.dry_run),
    }


# -- specs ---------------------------------------------------------------------

_ENROLLMENT_ID = _uuid_property("Enrollment ID (from ugc enrollment +list).")
_CHECK = {
    "type": "string",
    "enum": kebab_choices(CHECKS),
    "description": (
        "Creator check to remind about: cant-track (accounts not trackable), not-signed "
        "(contract), not-set-up, quiet (no recent posts), not-healthy (account health)."
    ),
}


def specs() -> list[CommandSpec]:
    domain = Domain.UGC
    campaign = "11111111-1111-4111-8111-111111111111"
    creative = "33333333-3333-4333-8333-333333333333"
    enrollment = "44444444-4444-4444-8444-444444444444"
    intent = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
    return [
        CommandSpec(
            domain=domain,
            resource="enrollment",
            shortcut="+nudge",
            summary=(
                "Remind one creator about a check that holds for them, in their private "
                "Discord channel (once a day per creator). The preview shows whether the "
                "check holds and whether a nudge is possible." + OUTBOUND_NOTE + ROLE_MESSAGE
            ),
            adapter_tool_name="ugc_enrollment_nudge",
            input_schema=_schema(
                {"id": _ENROLLMENT_ID, "check": _CHECK, "dry_run": DRY_RUN}, ["id", "check"]
            ),
            output_schema=_direct_output_schema("dry_run, check, holds, creator and nudge."),
            examples=[
                f"museoncli ugc enrollment +nudge --id {enrollment} --check not-signed --dry-run"
            ],
            add_arguments=_add_nudge,
            build_arguments=_nudge_args,
            **OUTBOUND,
        ),
        CommandSpec(
            domain=domain,
            resource="enrollment",
            shortcut="+bulk-nudge",
            summary=(
                "Remind every creator of a UGC campaign a check holds for (every check when "
                "--check is left out), skipping those already nudged today. The preview counts "
                "the creators per check." + OUTBOUND_NOTE + ROLE_MESSAGE
            ),
            adapter_tool_name="ugc_enrollment_bulk_nudge",
            input_schema=_schema(
                {"campaign_id": CAMPAIGN_ID, "check": _CHECK, "dry_run": DRY_RUN},
                ["campaign_id"],
            ),
            output_schema=_direct_output_schema(
                "dry_run, check, creators_per_check, as_of and result (sent)."
            ),
            examples=[
                f"museoncli ugc enrollment +bulk-nudge --campaign-id {campaign} --check quiet "
                "--dry-run"
            ],
            add_arguments=_add_bulk_nudge,
            build_arguments=_bulk_nudge_args,
            **OUTBOUND,
        ),
        CommandSpec(
            domain=domain,
            resource="message",
            shortcut="+send",
            summary=(
                "Send a creator a message: --enrollment-id writes to their project conversation "
                "(read on their MuseOn project page); --campaign-id with --creative-id writes "
                "about one video and pushes it to their Discord. An idempotency key makes a "
                "retry safe; the CLI makes one when left out and returns it."
                + OUTBOUND_NOTE + ROLE_MESSAGE
            ),
            adapter_tool_name="ugc_message_send",
            input_schema=_schema(
                {
                    "enrollment_id": _ENROLLMENT_ID,
                    "campaign_id": CAMPAIGN_ID,
                    "creative_id": _uuid_property("Creative (video) the message is about."),
                    "body": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 5000,
                        "description": "Message text (at most 2100 characters about a video).",
                    },
                    "idempotency_key": {
                        "type": "string",
                        "maxLength": 128,
                        "description": "Stable key for this message; retry with the same key and text.",
                    },
                    "dry_run": DRY_RUN,
                },
                ["body"],
            )
            | {
                "oneOf": [
                    {"required": ["enrollment_id"]},
                    {"required": ["campaign_id", "creative_id"]},
                ]
            },
            output_schema=_direct_output_schema(
                "dry_run, conversation or creative, body, idempotency_key and message."
            ),
            examples=[
                f"museoncli ugc message +send --enrollment-id {enrollment} "
                "--body 'Your contract is ready to sign' --dry-run",
                f"museoncli ugc message +send --campaign-id {campaign} --creative-id {creative} "
                "--body 'Can you reupload in 9:16?' --yes",
            ],
            add_arguments=_add_send,
            build_arguments=_send_args,
            **OUTBOUND,
        ),
        CommandSpec(
            domain=domain,
            resource="message",
            shortcut="+resend-card",
            summary=(
                "Send a creator their contract card or onboarding card again; the preview lists "
                "the earlier deliveries of that card." + OUTBOUND_NOTE + ROLE_MESSAGE
            ),
            adapter_tool_name="ugc_message_resend_card",
            input_schema=_schema(
                {
                    "enrollment_id": _ENROLLMENT_ID,
                    "kind": {"type": "string", "enum": kebab_choices(CARDS)},
                    "dry_run": DRY_RUN,
                },
                ["enrollment_id", "kind"],
            ),
            output_schema=_direct_output_schema("dry_run, kind, earlier_deliveries and result."),
            examples=[
                f"museoncli ugc message +resend-card --enrollment-id {enrollment} "
                "--kind contract-card --dry-run"
            ],
            add_arguments=_add_resend_card,
            build_arguments=_resend_card_args,
            **OUTBOUND,
        ),
        CommandSpec(
            domain=domain,
            resource="message",
            shortcut="+retry",
            summary=(
                "Retry delivering one failed message to a creator (--id is the delivery's "
                "intent_id from the enrollment's message ledger)." + OUTBOUND_NOTE + ROLE_MESSAGE
            ),
            adapter_tool_name="ugc_message_retry",
            input_schema=_schema(
                {
                    "enrollment_id": _ENROLLMENT_ID,
                    "id": _uuid_property("intent_id of the delivery to retry."),
                    "dry_run": DRY_RUN,
                },
                ["enrollment_id", "id"],
            ),
            output_schema=_direct_output_schema("dry_run, delivery and result."),
            examples=[
                f"museoncli ugc message +retry --enrollment-id {enrollment} --id {intent} --dry-run"
            ],
            add_arguments=_add_retry,
            build_arguments=_retry_args,
            **OUTBOUND,
        ),
    ]


EXECUTORS = {
    "ugc.enrollment-nudge": _with_notes(_execute_nudge),
    "ugc.enrollment-bulk-nudge": _with_notes(_execute_bulk_nudge),
    "ugc.message-send": _with_notes(_execute_send),
    "ugc.message-resend-card": _with_notes(_execute_resend_card),
    "ugc.message-retry": _with_notes(_execute_retry),
}
