"""Broadcasts: one message to many of a UGC Campaign's creators on Discord at once.

The same routes the web's Campaign 运营 → 广播 tab calls:
``/api/v2/ugc/campaigns/{campaign_id}/broadcasts`` and ``/broadcast-audience``.
A broadcast is written as a draft, then sent now or scheduled; a sent one can be
withdrawn (its messages are deleted) and its failed deliveries retried. Targets:
every creator's private channel or only some, direct messages to every creator
(at most 200), public channels of the Campaign's server, optionally narrowed to
personas.

For the Campaign's operations team (owner, admin, or an operator on it); a
member reads nothing here. Sending, scheduling, withdrawing, discarding and
retrying take --yes; without it they fail with
confirmation_required and return their dry run as preview. Files are added in the
browser: the upload is bound to the web page, so the CLI keeps a draft's files
as they are.
"""

from __future__ import annotations

import argparse
from datetime import datetime
from typing import Any

from museoncli.domains._model import CommandSpec, Domain
from museoncli.domains._shared import _direct_output_schema
from museoncli.domains._writes import (
    DRY_RUN,
    add_confirm,
    add_dry_run,
    ask_first,
    ask_then_yes,
    previewing,
    read_text,
    schema,
    uuid_arg,
    uuid_property,
    with_notes,
)
from museoncli.execution import CommandContext, compact_params, direct_enveloped

PURPOSES = ["notice", "recruitment"]
STATUSES = ["draft", "scheduled", "dispatched", "withdrawn", "discarded"]
PAGE_LIMIT = 50
BODY_MAX = 4000
SELECTION_FIELDS = (
    "body",
    "purpose",
    "to_all_private_channels",
    "private_channel_ids",
    "to_all_direct_messages",
    "guild_channel_ids",
    "mention_creators",
    "persona_ids",
)
_ROLE = (
    " For the Campaign's operations team (owner, admin, or an operator on it); others are refused."
)


def _base(campaign_id: str) -> str:
    return f"/ugc/campaigns/{campaign_id}"


def _path(args: dict[str, Any], suffix: str = "") -> str:
    return f"{_base(args['campaign_id'])}/broadcasts/{args['id']}{suffix}"


async def _get(ctx: CommandContext, path: str, params: dict[str, Any] | None = None) -> Any:
    return await ctx.api_data_v2(ctx.cfg, "GET", path, params=params)


async def _audience(ctx: CommandContext, campaign_id: str, purpose: str) -> dict[str, Any]:
    found = await _get(ctx, f"{_base(campaign_id)}/broadcast-audience", {"purpose": purpose})
    return found if isinstance(found, dict) else {}


async def _detail(ctx: CommandContext) -> dict[str, Any]:
    found = await _get(ctx, _path(ctx.arguments))
    return found if isinstance(found, dict) else {}


def _broadcast(detail: dict[str, Any]) -> dict[str, Any]:
    found = detail.get("broadcast")
    return found if isinstance(found, dict) else {}


def _line(broadcast: dict[str, Any]) -> dict[str, Any]:
    return {
        key: broadcast.get(key)
        for key in (
            "id",
            "purpose",
            "status",
            "body",
            "scheduled_at",
            "dispatched_at",
            "updated_at",
            "allowed_actions",
            "progress",
        )
    }


def reach(selection: dict[str, Any], audience: dict[str, Any]) -> dict[str, Any]:
    """Who a selection would reach now, from the audience read (counts, not names)."""
    personas = {
        str(item.get("persona_id")): item
        for item in audience.get("personas") or []
        if isinstance(item, dict)
    }
    chosen = [personas[pid] for pid in selection.get("persona_ids") or [] if pid in personas]

    def count(field: str) -> int:
        if chosen:
            return sum(int(item.get(field) or 0) for item in chosen)
        return int(audience.get(field) or 0)

    channels = {
        str(item.get("channel_id")): item.get("name")
        for item in audience.get("channels") or []
        if isinstance(item, dict)
    }
    return {
        "private_channels": (
            count("private_channels")
            if selection.get("to_all_private_channels")
            else len(selection.get("private_channel_ids") or [])
        ),
        "direct_messages": count("direct_messages") if selection.get("to_all_direct_messages") else 0,
        "public_channels": [
            {"channel_id": cid, "name": channels.get(cid)}
            for cid in selection.get("guild_channel_ids") or []
        ],
        "personas": [item.get("title") for item in chosen],
        "mention_creators": bool(selection.get("mention_creators")),
    }


def _reach_warnings(selection: dict[str, Any], audience: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    numbers = reach(selection, audience)
    limit = int(audience.get("direct_message_limit") or 200)
    if numbers["direct_messages"] > limit:
        warnings.append(
            f"{numbers['direct_messages']} direct messages exceed the limit of {limit}; "
            "the server refuses the send (broadcast_too_many_direct_messages)."
        )
    if not (numbers["private_channels"] or numbers["direct_messages"] or numbers["public_channels"]):
        warnings.append("It reaches nobody: pick private channels, direct messages or channels.")
    known = {str(item.get("channel_id")) for item in audience.get("channels") or [] if isinstance(item, dict)}
    unknown = [cid for cid in selection.get("guild_channel_ids") or [] if known and cid not in known]
    if unknown:
        warnings.append(f"Channel {unknown[0]} is not a public channel of the Campaign's server.")
    if selection.get("purpose") == "recruitment" and audience.get("recruitment_blockers"):
        warnings.append(
            "Recruitment is blocked now: " + ", ".join(map(str, audience["recruitment_blockers"]))
        )
    if audience.get("channels_unavailable"):
        warnings.append("Discord did not answer for the channel list; channel names are missing.")
    return warnings


def _selection(current: dict[str, Any], edits: dict[str, Any]) -> dict[str, Any]:
    merged = {field: current.get(field) for field in SELECTION_FIELDS if field in current}
    merged.update(edits)
    return merged


def _write_body(selection: dict[str, Any], attachments: list[Any]) -> dict[str, Any]:
    body = {field: selection[field] for field in SELECTION_FIELDS if field in selection}
    body["attachments"] = [
        {"upload_id": item.get("upload_id")} for item in attachments if isinstance(item, dict)
    ]
    return body


# -- executors: reads --------------------------------------------------------


async def _execute_audience(ctx: CommandContext) -> Any:
    args = ctx.arguments
    return await _audience(ctx, args["campaign_id"], args.get("purpose", "notice"))


async def _execute_list(ctx: CommandContext) -> Any:
    args = ctx.arguments
    return await _get(
        ctx,
        f"{_base(args['campaign_id'])}/broadcasts",
        compact_params(
            {
                "status": args.get("statuses"),
                "purpose": args.get("purpose"),
                "cursor": args.get("cursor"),
                "limit": args.get("page_size"),
            }
        ),
    )


async def _execute_get(ctx: CommandContext) -> Any:
    return await _detail(ctx)


# -- executors: writes -------------------------------------------------------


async def _execute_create(ctx: CommandContext) -> Any:
    args = ctx.arguments
    selection = {"purpose": "notice", "mention_creators": True, **args.get("selection", {})}
    if not args.get("dry_run"):
        created = await ctx.api_data_v2(
            ctx.cfg,
            "POST",
            f"{_base(args['campaign_id'])}/broadcasts",
            json_body=_write_body(selection, []),
        )
        return created, [], ["Nothing is sent yet: run +send (now) or +schedule (later)."]
    audience = await _audience(ctx, args["campaign_id"], selection["purpose"])
    data = {"dry_run": True, "draft": selection, "would_reach_now": reach(selection, audience)}
    return data, _reach_warnings(selection, audience), [ask_first("the draft and who it would reach")]


async def _execute_update(ctx: CommandContext) -> Any:
    args = ctx.arguments
    current = _broadcast(await _detail(ctx))
    selection = _selection(current, args.get("selection", {}))
    changed = [
        {"field": field, "before": current.get(field), "after": selection.get(field)}
        for field in SELECTION_FIELDS
        if current.get(field) != selection.get(field)
    ]
    data: dict[str, Any] = {
        "dry_run": bool(args.get("dry_run")),
        "broadcast": _line(current),
        "changes": changed,
    }
    if not changed:
        return data, ["Nothing differs from the saved draft; nothing was written."], []
    warnings = []
    if current.get("status") != "draft":
        warnings.append(
            f"The broadcast is {current.get('status')}; only a draft can be edited "
            "(+unschedule a scheduled one first)."
        )
    if args.get("dry_run"):
        audience = await _audience(ctx, args["campaign_id"], selection.get("purpose") or "notice")
        data["would_reach_now"] = reach(selection, audience)
        return data, [*warnings, *_reach_warnings(selection, audience)], [ask_first("these changes")]
    data["broadcast"] = await ctx.api_data_v2(
        ctx.cfg, "PUT", _path(args), json_body=_write_body(selection, current.get("attachments") or [])
    )
    return data, [], []


def _confirmed(action: str, *, what: str, allowed: str | None, warn: str | None = None):
    async def run(ctx: CommandContext) -> Any:
        args = ctx.arguments
        detail = await _detail(ctx)
        current = _broadcast(detail)
        data: dict[str, Any] = {
            "dry_run": bool(args.get("dry_run")),
            "action": action,
            "broadcast": _line(current),
        }
        warnings: list[str] = []
        if allowed is not None and allowed not in (current.get("allowed_actions") or [allowed]):
            warnings.append(
                f"The broadcast is {current.get('status')}; the server refuses {action} now."
            )
        body: dict[str, Any] | None = None
        if action in ("send", "schedule"):
            audience = await _audience(ctx, args["campaign_id"], current.get("purpose") or "notice")
            data["would_reach_now"] = reach(current, audience)
            warnings += _reach_warnings(current, audience)
        if action == "send":
            body = compact_params(
                {
                    "expected_updated_at": current.get("updated_at"),
                    "expected_campaign_updated_at": (
                        audience.get("campaign_updated_at")
                        if current.get("purpose") == "recruitment"
                        else None
                    ),
                }
            )
        if action == "schedule":
            data["scheduled_at"] = args["scheduled_at"]
            body = {"scheduled_at": args["scheduled_at"]}
        if action == "retry":
            failed = [
                item for item in detail.get("deliveries") or []
                if isinstance(item, dict) and item.get("can_retry")
            ]
            data["retryable_deliveries"] = len(failed)
            if not failed:
                warnings.append("No delivery can be retried; nothing would be sent.")
        if warn:
            warnings.append(warn)
        if args.get("dry_run"):
            return data, warnings, [ask_then_yes(what)]
        method, suffix = ("DELETE", "") if action == "discard" else ("POST", f"/{action}")
        data["broadcast"] = await ctx.api_data_v2(
            ctx.cfg,
            method,
            _path(args, suffix),
            **({"json_body": body} if body is not None else {}),
        )
        return data, [], []

    return run


async def _execute_unschedule(ctx: CommandContext) -> Any:
    args = ctx.arguments
    current = _broadcast(await _detail(ctx))
    data: dict[str, Any] = {"dry_run": bool(args.get("dry_run")), "broadcast": _line(current)}
    if current.get("status") != "scheduled":
        return data, [f"The broadcast is {current.get('status')}, not scheduled; nothing to cancel."], []
    if args.get("dry_run"):
        return data, [], [ask_first("the schedule that would be cancelled")]
    data["broadcast"] = await ctx.api_data_v2(ctx.cfg, "POST", _path(args, "/unschedule"))
    return data, [], []


# -- arguments ---------------------------------------------------------------


def _add_campaign_id(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--campaign-id", required=True)


def _campaign(args: argparse.Namespace) -> dict[str, Any]:
    return {"campaign_id": uuid_arg(args.campaign_id, flag="--campaign-id")}


def _add_id(parser: argparse.ArgumentParser) -> None:
    _add_campaign_id(parser)
    parser.add_argument("--id", required=True)


def _ids(args: argparse.Namespace) -> dict[str, Any]:
    return {**_campaign(args), "id": uuid_arg(args.id, flag="--id")}


def _add_audience_arguments(parser: argparse.ArgumentParser) -> None:
    _add_campaign_id(parser)
    parser.add_argument("--purpose", choices=PURPOSES, default="notice")


def _build_audience_arguments(args: argparse.Namespace) -> dict[str, Any]:
    return {**_campaign(args), "purpose": args.purpose}


def _add_list_arguments(parser: argparse.ArgumentParser) -> None:
    _add_campaign_id(parser)
    parser.add_argument("--status", action="append", choices=STATUSES, dest="statuses")
    parser.add_argument("--purpose", choices=PURPOSES)
    parser.add_argument("--cursor")
    parser.add_argument("--page-size", type=int, default=20)


def _build_list_arguments(args: argparse.Namespace) -> dict[str, Any]:
    if not 1 <= args.page_size <= PAGE_LIMIT:
        raise ValueError(f"--page-size must be between 1 and {PAGE_LIMIT}.")
    return compact_params(
        {
            **_campaign(args),
            "statuses": args.statuses,
            "purpose": args.purpose,
            "cursor": args.cursor,
            "page_size": args.page_size,
        }
    )


def _add_get_arguments(parser: argparse.ArgumentParser) -> None:
    _add_id(parser)


def _add_selection_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--body")
    parser.add_argument("--body-file")
    parser.add_argument("--purpose", choices=PURPOSES)
    parser.add_argument(
        "--to-all-private-channels", action=argparse.BooleanOptionalAction, default=None
    )
    parser.add_argument("--private-channel-id", action="append", dest="private_channel_ids")
    parser.add_argument(
        "--to-all-direct-messages", action=argparse.BooleanOptionalAction, default=None
    )
    parser.add_argument("--channel-id", action="append", dest="guild_channel_ids")
    parser.add_argument("--persona-id", action="append", dest="persona_ids")
    parser.add_argument("--mention-creators", action=argparse.BooleanOptionalAction, default=None)


def _discord_id(value: str, *, flag: str) -> str:
    cleaned = value.strip()
    if not cleaned.isdigit() or not 17 <= len(cleaned) <= 20:
        raise ValueError(f"{flag} takes a Discord channel id (17-20 digits), got {value!r}.")
    return cleaned


def _selection_edits(args: argparse.Namespace) -> dict[str, Any]:
    edits: dict[str, Any] = {}
    body = read_text(args.body, args.body_file, flag="--body")
    if body is not None:
        if len(body.strip()) > BODY_MAX:
            raise ValueError(f"--body is {len(body.strip())} characters; at most {BODY_MAX}.")
        edits["body"] = body
    for name in ("purpose", "to_all_private_channels", "to_all_direct_messages", "mention_creators"):
        value = getattr(args, name)
        if value is not None:
            edits[name] = value
    if args.private_channel_ids is not None:
        edits["private_channel_ids"] = [
            _discord_id(value, flag="--private-channel-id") for value in args.private_channel_ids
        ]
    if args.guild_channel_ids is not None:
        edits["guild_channel_ids"] = [
            _discord_id(value, flag="--channel-id") for value in args.guild_channel_ids
        ]
    if args.persona_ids is not None:
        edits["persona_ids"] = list(
            dict.fromkeys(uuid_arg(value, flag="--persona-id") for value in args.persona_ids)
        )
    return edits


def _add_create_arguments(parser: argparse.ArgumentParser) -> None:
    _add_campaign_id(parser)
    _add_selection_arguments(parser)
    add_dry_run(parser)


def _build_create_arguments(args: argparse.Namespace) -> dict[str, Any]:
    selection = _selection_edits(args)
    if not (selection.get("body") or "").strip():
        raise ValueError("Pass the message with --body or --body-file.")
    return {**_campaign(args), "selection": selection, "dry_run": bool(args.dry_run)}


def _add_update_arguments(parser: argparse.ArgumentParser) -> None:
    _add_id(parser)
    _add_selection_arguments(parser)
    add_dry_run(parser)


def _build_update_arguments(args: argparse.Namespace) -> dict[str, Any]:
    selection = _selection_edits(args)
    if not selection:
        raise ValueError(
            "Pass at least one change: --body, --purpose, --to-all-private-channels, "
            "--private-channel-id, --to-all-direct-messages, --channel-id, --persona-id or "
            "--mention-creators."
        )
    return {**_ids(args), "selection": selection, "dry_run": bool(args.dry_run)}


def _add_confirmed_arguments(parser: argparse.ArgumentParser) -> None:
    _add_id(parser)
    add_confirm(parser)


def _build_confirmed_arguments(args: argparse.Namespace) -> dict[str, Any]:
    return {**_ids(args), "dry_run": previewing(args)}


def _add_schedule_arguments(parser: argparse.ArgumentParser) -> None:
    _add_confirmed_arguments(parser)
    parser.add_argument("--at", required=True, dest="scheduled_at")


def _build_schedule_arguments(args: argparse.Namespace) -> dict[str, Any]:
    try:
        moment = datetime.fromisoformat(args.scheduled_at)
    except ValueError:
        raise ValueError(
            f"--at takes a time with a timezone offset, e.g. 2026-11-14T10:00:00+08:00; got "
            f"{args.scheduled_at!r}."
        ) from None
    if moment.tzinfo is None:
        raise ValueError("--at needs a timezone offset, e.g. 2026-11-14T10:00:00+08:00.")
    return {**_build_confirmed_arguments(args), "scheduled_at": moment.isoformat()}


def _add_unschedule_arguments(parser: argparse.ArgumentParser) -> None:
    _add_id(parser)
    add_dry_run(parser)


def _build_unschedule_arguments(args: argparse.Namespace) -> dict[str, Any]:
    return {**_ids(args), "dry_run": bool(args.dry_run)}


# -- schemas -----------------------------------------------------------------

_CAMPAIGN_ID = uuid_property("UGC campaign ID (ugc campaign +list).")
_BROADCAST_ID = uuid_property("Broadcast ID (ugc broadcast +list or +create).")
_SELECTION = {
    "type": "object",
    "description": "The draft's content and targets; on +update only the fields passed change.",
    "properties": {
        "body": {
            "type": "string",
            "maxLength": BODY_MAX,
            "description": "Markdown; mentions typed in it never ping.",
        },
        "purpose": {"type": "string", "enum": PURPOSES},
        "to_all_private_channels": {
            "type": "boolean",
            "description": "Every participating creator's private channel.",
        },
        "private_channel_ids": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Only these private channels (private_channel_options of +audience).",
        },
        "to_all_direct_messages": {
            "type": "boolean",
            "description": "A direct message to every participating creator (at most 200).",
        },
        "guild_channel_ids": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Public channels of the Campaign's server (channels of +audience).",
        },
        "persona_ids": {
            "type": "array",
            "items": {"type": "string", "format": "uuid"},
            "description": "Only creators of these personas (personas of +audience).",
        },
        "mention_creators": {
            "type": "boolean",
            "description": "@ each creator in their private channel (default on).",
        },
    },
}
_ID_INPUT = {"campaign_id": _CAMPAIGN_ID, "id": _BROADCAST_ID, "dry_run": DRY_RUN}
_VIEW_OUT = _direct_output_schema("action, broadcast (status, progress, allowed_actions).")


def specs() -> list[CommandSpec]:
    domain = Domain.UGC
    campaign = "11111111-1111-4111-8111-111111111111"
    broadcast = "88888888-8888-4888-8888-888888888888"
    read = {"risk_level": "read", "execution": "direct"}
    write = {
        "risk_level": "write",
        "execution": "direct",
        "supports_dry_run": True,
        "dry_run_reads_server": True,
    }
    confirmed = {**write, "requires_confirmation": True}
    destructive = {**confirmed, "risk_level": "destructive"}
    spec = {"domain": domain, "resource": "broadcast"}
    return [
        CommandSpec(
            **spec,  # type: ignore[arg-type]
            shortcut="+audience",
            summary=(
                "Preview who a broadcast can reach now: how many private channels and direct "
                "messages, the server's public channels, each persona's counts, the private "
                "channel options and anything blocking a recruitment post." + _ROLE
            ),
            adapter_tool_name="ugc_broadcast_audience",
            input_schema=schema(
                {"campaign_id": _CAMPAIGN_ID, "purpose": {"type": "string", "enum": PURPOSES}},
                ["campaign_id"],
            ),
            output_schema=_direct_output_schema(
                "private_channels, direct_messages, direct_message_limit, channels, personas, "
                "private_channel_options, recruitment_blockers."
            ),
            examples=[f"museoncli ugc broadcast +audience --campaign-id {campaign}"],
            add_arguments=_add_audience_arguments,
            build_arguments=_build_audience_arguments,
            **read,  # type: ignore[arg-type]
        ),
        CommandSpec(
            **spec,  # type: ignore[arg-type]
            shortcut="+list",
            summary=(
                "List a Campaign's broadcasts, newest first, with status and delivery progress."
                + _ROLE
            ),
            adapter_tool_name="ugc_broadcast_list",
            input_schema=schema(
                {
                    "campaign_id": _CAMPAIGN_ID,
                    "statuses": {"type": "array", "items": {"type": "string", "enum": STATUSES}},
                    "purpose": {"type": "string", "enum": PURPOSES},
                    "cursor": {"type": ["string", "null"], "description": "next_cursor from the previous page."},
                    "page_size": {"type": "integer", "minimum": 1, "maximum": PAGE_LIMIT, "default": 20},
                },
                ["campaign_id"],
            ),
            output_schema=_direct_output_schema("items (broadcasts) and next_cursor."),
            examples=[f"museoncli ugc broadcast +list --campaign-id {campaign} --status draft"],
            add_arguments=_add_list_arguments,
            build_arguments=_build_list_arguments,
            **read,  # type: ignore[arg-type]
        ),
        CommandSpec(
            **spec,  # type: ignore[arg-type]
            shortcut="+get",
            summary=(
                "One broadcast: its content and targets, every delivery's outcome (sent, failed, "
                "withdrawn, with a Discord link) and its history." + _ROLE
            ),
            adapter_tool_name="ugc_broadcast_get",
            input_schema=schema({"campaign_id": _CAMPAIGN_ID, "id": _BROADCAST_ID}, ["campaign_id", "id"]),
            output_schema=_direct_output_schema("broadcast, deliveries, history, attachment_previews."),
            examples=[f"museoncli ugc broadcast +get --campaign-id {campaign} --id {broadcast}"],
            add_arguments=_add_get_arguments,
            build_arguments=_ids,
            **read,  # type: ignore[arg-type]
        ),
        CommandSpec(
            **spec,  # type: ignore[arg-type]
            shortcut="+create",
            summary=(
                "Write a broadcast draft: the message and its targets (all or some private "
                "channels, direct messages to all, public channels, narrowed to personas). Nothing "
                "is sent until +send or +schedule. --dry-run shows who it would reach now." + _ROLE
            ),
            adapter_tool_name="ugc_broadcast_create",
            input_schema=schema(
                {"campaign_id": _CAMPAIGN_ID, "selection": _SELECTION, "dry_run": DRY_RUN},
                ["campaign_id", "selection"],
            ),
            output_schema=_direct_output_schema("The draft as saved (id, status draft, targets)."),
            examples=[
                f'museoncli ugc broadcast +create --campaign-id {campaign} --body "New brief is up, '
                'check your channel." --to-all-private-channels --dry-run'
            ],
            add_arguments=_add_create_arguments,
            build_arguments=_build_create_arguments,
            **write,  # type: ignore[arg-type]
        ),
        CommandSpec(
            **spec,  # type: ignore[arg-type]
            shortcut="+update",
            summary=(
                "Change a draft broadcast's message or targets; fields not passed keep their "
                "value and its files stay. --dry-run returns the changes and who it would reach."
                + _ROLE
            ),
            adapter_tool_name="ugc_broadcast_update",
            input_schema=schema(
                {**_ID_INPUT, "selection": _SELECTION}, ["campaign_id", "id", "selection"]
            ),
            output_schema=_direct_output_schema("broadcast and changes (field, before, after)."),
            examples=[
                f"museoncli ugc broadcast +update --campaign-id {campaign} --id {broadcast} "
                "--no-to-all-direct-messages --dry-run"
            ],
            add_arguments=_add_update_arguments,
            build_arguments=_build_update_arguments,
            **write,  # type: ignore[arg-type]
        ),
        CommandSpec(
            **spec,  # type: ignore[arg-type]
            shortcut="+send",
            summary=(
                "Send a draft or scheduled broadcast now; the recipients are fixed at this moment. "
                "Without --yes it is refused with a preview of the message and who it would reach." + _ROLE
            ),
            adapter_tool_name="ugc_broadcast_send",
            input_schema=schema(_ID_INPUT, ["campaign_id", "id"]),
            output_schema=_VIEW_OUT,
            examples=[
                f"museoncli ugc broadcast +send --campaign-id {campaign} --id {broadcast}",
                f"museoncli ugc broadcast +send --campaign-id {campaign} --id {broadcast} --yes",
            ],
            add_arguments=_add_confirmed_arguments,
            build_arguments=_build_confirmed_arguments,
            **confirmed,  # type: ignore[arg-type]
        ),
        CommandSpec(
            **spec,  # type: ignore[arg-type]
            shortcut="+schedule",
            summary=(
                "Schedule a draft broadcast (or move its schedule); it is sent within a minute of "
                "--at and its content locks until +unschedule. Without --yes it is refused with a preview."
                + _ROLE
            ),
            adapter_tool_name="ugc_broadcast_schedule",
            input_schema=schema(
                {
                    **_ID_INPUT,
                    "scheduled_at": {
                        "type": "string",
                        "format": "date-time",
                        "description": "When to send, in the future, with a timezone offset.",
                    },
                },
                ["campaign_id", "id", "scheduled_at"],
            ),
            output_schema=_VIEW_OUT,
            examples=[
                f"museoncli ugc broadcast +schedule --campaign-id {campaign} --id {broadcast} "
                "--at 2026-11-14T10:00:00+08:00 --yes"
            ],
            add_arguments=_add_schedule_arguments,
            build_arguments=_build_schedule_arguments,
            **confirmed,  # type: ignore[arg-type]
        ),
        CommandSpec(
            **spec,  # type: ignore[arg-type]
            shortcut="+unschedule",
            summary=(
                "Cancel a scheduled broadcast; it is a draft again and can be edited. --dry-run "
                "shows it without writing." + _ROLE
            ),
            adapter_tool_name="ugc_broadcast_unschedule",
            input_schema=schema(_ID_INPUT, ["campaign_id", "id"]),
            output_schema=_VIEW_OUT,
            examples=[
                f"museoncli ugc broadcast +unschedule --campaign-id {campaign} --id {broadcast} --dry-run"
            ],
            add_arguments=_add_unschedule_arguments,
            build_arguments=_build_unschedule_arguments,
            **write,  # type: ignore[arg-type]
        ),
        CommandSpec(
            **spec,  # type: ignore[arg-type]
            shortcut="+retry",
            summary=(
                "Send a dispatched broadcast's failed deliveries again. Without --yes it is refused with a preview of "
                "how many can be retried." + _ROLE
            ),
            adapter_tool_name="ugc_broadcast_retry",
            input_schema=schema(_ID_INPUT, ["campaign_id", "id"]),
            output_schema=_VIEW_OUT,
            examples=[f"museoncli ugc broadcast +retry --campaign-id {campaign} --id {broadcast} --yes"],
            add_arguments=_add_confirmed_arguments,
            build_arguments=_build_confirmed_arguments,
            **confirmed,  # type: ignore[arg-type]
        ),
        CommandSpec(
            **spec,  # type: ignore[arg-type]
            shortcut="+withdraw",
            summary=(
                "Take a sent broadcast back: its sent messages are deleted from Discord and queued "
                "ones never go. Cannot be undone. Without --yes it is refused with a preview of the broadcast."
                + _ROLE
            ),
            adapter_tool_name="ugc_broadcast_withdraw",
            input_schema=schema(_ID_INPUT, ["campaign_id", "id"]),
            output_schema=_VIEW_OUT,
            examples=[
                f"museoncli ugc broadcast +withdraw --campaign-id {campaign} --id {broadcast} --yes"
            ],
            add_arguments=_add_confirmed_arguments,
            build_arguments=_build_confirmed_arguments,
            **destructive,  # type: ignore[arg-type]
        ),
        CommandSpec(
            **spec,  # type: ignore[arg-type]
            shortcut="+discard",
            summary=(
                "Discard a draft broadcast; it stays in the list as discarded and can no longer be "
                "sent. Without --yes it is refused with a preview of the draft." + _ROLE
            ),
            adapter_tool_name="ugc_broadcast_discard",
            input_schema=schema(_ID_INPUT, ["campaign_id", "id"]),
            output_schema=_VIEW_OUT,
            examples=[
                f"museoncli ugc broadcast +discard --campaign-id {campaign} --id {broadcast} --yes"
            ],
            add_arguments=_add_confirmed_arguments,
            build_arguments=_build_confirmed_arguments,
            **destructive,  # type: ignore[arg-type]
        ),
    ]


EXECUTORS = {
    "ugc.broadcast-audience": direct_enveloped(_execute_audience),
    "ugc.broadcast-list": direct_enveloped(_execute_list),
    "ugc.broadcast-get": direct_enveloped(_execute_get),
    "ugc.broadcast-create": with_notes(_execute_create),
    "ugc.broadcast-update": with_notes(_execute_update),
    "ugc.broadcast-send": with_notes(
        _confirmed("send", what="the message and who it would reach", allowed="send")
    ),
    "ugc.broadcast-schedule": with_notes(
        _confirmed("schedule", what="the message, when it goes and who it would reach", allowed="schedule")
    ),
    "ugc.broadcast-unschedule": with_notes(_execute_unschedule),
    "ugc.broadcast-retry": with_notes(
        _confirmed("retry", what="how many deliveries would be retried", allowed=None)
    ),
    "ugc.broadcast-withdraw": with_notes(
        _confirmed(
            "withdraw",
            what="the broadcast whose messages would be deleted",
            allowed="withdraw",
            warn="Withdrawing deletes the messages creators already received.",
        )
    ),
    "ugc.broadcast-discard": with_notes(
        _confirmed("discard", what="the draft that would be discarded", allowed="discard")
    ),
}
