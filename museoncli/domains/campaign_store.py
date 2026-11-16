"""Museon's synced store, read by one creator (social account) or one post.

Not scoped to one Campaign: `campaign creator +get` / `+get-performance` read a social
account by `--creator-id` (the creator_social_account_id `campaign creator +list` returns,
the same flag every `campaign creator` command and `campaign post +list` take), and
`campaign post` reads the posts Museon has synced, by creator or by post (`--content-id`).
The old `--id` spelling still answers, hidden, with a deprecation warning. Nothing here
fetches the platform live; `research +search-social-media` discovers outside Museon.
"""

from __future__ import annotations

from museoncli.execution import agent_domain_result, compact_params

from museoncli.execution import (
    CommandContext,
    direct_enveloped,
)

import argparse
from datetime import date
from typing import Any
from museoncli.domains._model import CommandSpec, Domain
from museoncli.domains._shared import (
    _add_common_adapter_arguments,
    _direct_output_schema,
    add_renamed_id_flag,
    _load_structured_args,
    _without_none,
)


def _add_social_media_creator_get_arguments(parser: argparse.ArgumentParser) -> None:
    _add_common_adapter_arguments(parser)
    add_renamed_id_flag(
        parser,
        "--creator-id",
        dest="creator_id",
        help=(
            "The creator's social account ID (creator_social_account_id from campaign "
            "creator +list), not a campaign ID."
        ),
    )


def _build_social_media_creator_get_arguments(args: argparse.Namespace) -> dict[str, Any]:
    payload = _load_structured_args(args)
    payload["creator_id"] = args.creator_id
    return payload


def _add_social_media_post_list_arguments(parser: argparse.ArgumentParser) -> None:
    _add_common_adapter_arguments(parser)
    parser.add_argument(
        "--creator-id",
        required=True,
        help=(
            "The creator's social account ID (creator_social_account_id from campaign "
            "creator +list), not a campaign ID."
        ),
    )
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--page-size", type=int, default=20)


def _build_social_media_post_list_arguments(args: argparse.Namespace) -> dict[str, Any]:
    payload = _load_structured_args(args)
    payload.update(
        {
            "creator_id": args.creator_id,
            "page": args.page,
            "page_size": args.page_size,
        }
    )
    return payload


def _add_social_media_creator_performance_get_arguments(
    parser: argparse.ArgumentParser,
) -> None:
    _add_social_media_creator_get_arguments(parser)
    parser.add_argument(
        "--date-from",
        help="First day of the window, YYYY-MM-DD (required; the window is at most 180 days).",
    )
    parser.add_argument(
        "--date-to",
        help="Last day of the window, YYYY-MM-DD (required; on or after --date-from).",
    )
    parser.add_argument("--limit", type=int, default=100)


def _build_social_media_creator_performance_get_arguments(
    args: argparse.Namespace,
) -> dict[str, Any]:
    payload = _build_social_media_creator_get_arguments(args)
    payload.update(
        _without_none(
            {
                "date_from": args.date_from,
                "date_to": args.date_to,
                "limit": args.limit,
            }
        )
    )
    _check_creator_performance_window(payload)
    return payload


CREATOR_PERFORMANCE_MAX_DAYS = 180


def _check_creator_performance_window(payload: dict[str, Any]) -> None:
    """The server needs both dates (inclusive, at most 180 days); say so before the request."""
    date_from, date_to = payload.get("date_from"), payload.get("date_to")
    if not date_from or not date_to:
        raise ValueError(
            "campaign creator +get-performance needs --date-from and --date-to "
            "(YYYY-MM-DD, inclusive, at most 180 days apart), e.g. "
            "--date-from 2026-10-01 --date-to 2026-10-28"
        )
    try:
        start, end = date.fromisoformat(str(date_from)), date.fromisoformat(str(date_to))
    except ValueError as exc:
        raise ValueError("--date-from and --date-to must be dates in YYYY-MM-DD format") from exc
    if end < start:
        raise ValueError("--date-to must be on or after --date-from")
    if (end - start).days + 1 > CREATOR_PERFORMANCE_MAX_DAYS:
        raise ValueError(
            f"the window may span at most {CREATOR_PERFORMANCE_MAX_DAYS} days (inclusive); "
            "read a longer history in several windows"
        )


def _add_social_media_post_get_arguments(parser: argparse.ArgumentParser) -> None:
    _add_common_adapter_arguments(parser)
    add_renamed_id_flag(
        parser,
        "--content-id",
        dest="content_id",
        help="The post's content id (content_id from campaign content +list or post +list).",
    )


def _build_social_media_post_get_arguments(args: argparse.Namespace) -> dict[str, Any]:
    payload = _load_structured_args(args)
    payload["content_id"] = args.content_id
    return payload


def _add_social_media_post_performance_get_arguments(parser: argparse.ArgumentParser) -> None:
    _add_social_media_post_get_arguments(parser)
    parser.add_argument("--date-from")
    parser.add_argument("--date-to")
    parser.add_argument("--limit", type=int, default=30)


def _build_social_media_post_performance_get_arguments(
    args: argparse.Namespace,
) -> dict[str, Any]:
    payload = _build_social_media_post_get_arguments(args)
    payload.update(
        _without_none(
            {
                "date_from": args.date_from,
                "date_to": args.date_to,
                "limit": args.limit,
            }
        )
    )
    return payload


def _add_social_media_post_resolve_arguments(parser: argparse.ArgumentParser) -> None:
    _add_common_adapter_arguments(parser)
    parser.add_argument("--schedule-item-id", required=True)


def _build_social_media_post_resolve_arguments(args: argparse.Namespace) -> dict[str, Any]:
    payload = _load_structured_args(args)
    payload["schedule_item_id"] = args.schedule_item_id
    return payload


def _social_media_creator_get_input_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "creator_id": {
                "type": "string",
                "minLength": 1,
                "description": "The creator's social account ID (not a campaign ID).",
            }
        },
        "required": ["creator_id"],
    }


def _social_media_post_list_input_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "creator_id": {
                "type": "string",
                "minLength": 1,
                "description": "The creator's social account ID (not a campaign ID).",
            },
            "page": {"type": "integer", "minimum": 1, "default": 1},
            "page_size": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
        },
        "required": ["creator_id"],
    }


def _social_media_creator_performance_get_input_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "creator_id": {
                "type": "string",
                "minLength": 1,
                "description": "The creator's social account ID (not a campaign ID).",
            },
            "date_from": {
                "type": "string",
                "format": "date",
                "description": "First day, YYYY-MM-DD (required; window at most 180 days).",
            },
            "date_to": {
                "type": "string",
                "format": "date",
                "description": "Last day, YYYY-MM-DD (required; on or after date_from).",
            },
            "limit": {"type": "integer", "minimum": 1, "maximum": 500, "default": 100},
        },
        "required": ["creator_id", "date_from", "date_to"],
    }


def _social_media_post_get_input_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {"content_id": {"type": "string", "minLength": 1}},
        "required": ["content_id"],
    }


def _social_media_post_performance_get_input_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "content_id": {"type": "string", "minLength": 1},
            "date_from": {"type": ["string", "null"]},
            "date_to": {"type": ["string", "null"]},
            "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 30},
        },
        "required": ["content_id"],
    }


def _social_media_post_resolve_input_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {"schedule_item_id": {"type": "string", "minLength": 1}},
        "required": ["schedule_item_id"],
    }


def specs() -> list[CommandSpec]:
    return [
        CommandSpec(
            domain=Domain.CAMPAIGN,
            resource="creator",
            shortcut="+get",
            summary=(
                "Read one social account's profile from Museon's store, by the "
                "creator_social_account_id campaign creator +list returns."
            ),
            risk_level="read",
            execution="direct",
            adapter_tool_name="social_media_creator_get",
            input_schema=_social_media_creator_get_input_schema(),
            output_schema=_direct_output_schema("Creator profile payload returned by Museon API."),
            examples=[
                "museoncli campaign creator +get --creator-id <creator_social_account_id>",
            ],
            add_arguments=_add_social_media_creator_get_arguments,
            build_arguments=_build_social_media_creator_get_arguments,
        ),
        CommandSpec(
            domain=Domain.CAMPAIGN,
            resource="post",
            shortcut="+list",
            summary=(
                "List Museon-synced posts for one organization-visible social account; "
                "not a live platform-history fetch."
            ),
            risk_level="read",
            execution="direct",
            adapter_tool_name="social_media_post_list",
            input_schema=_social_media_post_list_input_schema(),
            output_schema=_direct_output_schema("Post list payload returned by Museon API."),
            examples=[
                (
                    "museoncli campaign post +list --creator-id "
                    "<creator_social_account_id> --page-size 20"
                ),
            ],
            add_arguments=_add_social_media_post_list_arguments,
            build_arguments=_build_social_media_post_list_arguments,
        ),
        CommandSpec(
            domain=Domain.CAMPAIGN,
            resource="creator",
            shortcut="+get-performance",
            summary=(
                "Read local synced performance history for one organization-visible social account. "
                "Both --date-from and --date-to are required (inclusive, at most 180 days)."
            ),
            risk_level="read",
            execution="direct",
            adapter_tool_name="social_media_creator_performance_get",
            input_schema=_social_media_creator_performance_get_input_schema(),
            output_schema=_direct_output_schema(
                "Creator performance history payload returned by Museon API."
            ),
            examples=[
                (
                    "museoncli campaign creator +get-performance "
                    "--creator-id <creator_social_account_id> --date-from 2026-10-01 --date-to 2026-10-28"
                ),
            ],
            add_arguments=_add_social_media_creator_performance_get_arguments,
            build_arguments=_build_social_media_creator_performance_get_arguments,
        ),
        CommandSpec(
            domain=Domain.CAMPAIGN,
            resource="post",
            shortcut="+get",
            summary="Read one post Museon has synced, by its content id.",
            risk_level="read",
            execution="direct",
            adapter_tool_name="social_media_post_get",
            input_schema=_social_media_post_get_input_schema(),
            output_schema=_direct_output_schema("Post detail payload returned by Museon API."),
            examples=["museoncli campaign post +get --content-id <content_id>"],
            add_arguments=_add_social_media_post_get_arguments,
            build_arguments=_build_social_media_post_get_arguments,
        ),
        CommandSpec(
            domain=Domain.CAMPAIGN,
            resource="post",
            shortcut="+get-performance",
            summary="Read the performance history Museon synced for one post, by its content id.",
            risk_level="read",
            execution="direct",
            adapter_tool_name="social_media_post_performance_get",
            input_schema=_social_media_post_performance_get_input_schema(),
            output_schema=_direct_output_schema(
                "Post performance history payload returned by Museon API."
            ),
            examples=[
                ("museoncli campaign post +get-performance --content-id <content_id> --limit 10"),
            ],
            add_arguments=_add_social_media_post_performance_get_arguments,
            build_arguments=_build_social_media_post_performance_get_arguments,
        ),
        CommandSpec(
            domain=Domain.CAMPAIGN,
            resource="post",
            shortcut="+resolve",
            summary="Find the post an account publish schedule item became, once it is published.",
            risk_level="read",
            execution="direct",
            adapter_tool_name="social_media_post_resolve",
            input_schema=_social_media_post_resolve_input_schema(),
            output_schema=_direct_output_schema(
                "Schedule item to post resolution payload returned by Museon API."
            ),
            examples=[
                ("museoncli campaign post +resolve --schedule-item-id <schedule_item_id>"),
            ],
            add_arguments=_add_social_media_post_resolve_arguments,
            build_arguments=_build_social_media_post_resolve_arguments,
        ),
    ]


# ---- executors ----
async def _execute_creator_get(ctx: CommandContext) -> Any:
    cfg = ctx.cfg
    arguments = ctx.arguments
    api_data = ctx.api_data
    creator_id = str(arguments.get("creator_id") or "")
    return agent_domain_result(
        await api_data(
            cfg,
            "GET",
            f"/agent-cli/social-media/creators/{creator_id}",
        )
    )


async def _execute_creator_performance_get(ctx: CommandContext) -> Any:
    cfg = ctx.cfg
    arguments = ctx.arguments
    api_data = ctx.api_data
    creator_id = str(arguments.get("creator_id") or "")
    return agent_domain_result(
        await api_data(
            cfg,
            "GET",
            f"/agent-cli/social-media/creators/{creator_id}/performance",
            params=compact_params(
                {
                    "date_from": arguments.get("date_from"),
                    "date_to": arguments.get("date_to"),
                    "limit": arguments.get("limit", 100),
                }
            ),
        )
    )


async def _execute_post_get(ctx: CommandContext) -> Any:
    cfg = ctx.cfg
    arguments = ctx.arguments
    api_data = ctx.api_data
    content_id = str(arguments.get("content_id") or "")
    return agent_domain_result(
        await api_data(
            cfg,
            "GET",
            f"/agent-cli/social-media/posts/{content_id}",
        )
    )


async def _execute_post_list(ctx: CommandContext) -> Any:
    cfg = ctx.cfg
    arguments = ctx.arguments
    api_data = ctx.api_data
    creator_id = str(arguments.get("creator_id") or "")
    return agent_domain_result(
        await api_data(
            cfg,
            "GET",
            f"/agent-cli/social-media/creators/{creator_id}/posts",
            params=compact_params(
                {
                    "page": arguments.get("page", 1),
                    "page_size": arguments.get("page_size", 20),
                }
            ),
        )
    )


async def _execute_post_performance_get(ctx: CommandContext) -> Any:
    cfg = ctx.cfg
    arguments = ctx.arguments
    api_data = ctx.api_data
    content_id = str(arguments.get("content_id") or "")
    return agent_domain_result(
        await api_data(
            cfg,
            "GET",
            f"/agent-cli/social-media/posts/{content_id}/performance",
            params=compact_params(
                {
                    "date_from": arguments.get("date_from"),
                    "date_to": arguments.get("date_to"),
                    "limit": arguments.get("limit", 30),
                }
            ),
        )
    )


async def _execute_post_resolve(ctx: CommandContext) -> Any:
    cfg = ctx.cfg
    arguments = ctx.arguments
    api_data = ctx.api_data
    schedule_item_id = str(arguments.get("schedule_item_id") or "")
    return agent_domain_result(
        await api_data(
            cfg,
            "GET",
            "/agent-cli/social-media/posts/resolve",
            params={"schedule_item_id": schedule_item_id},
        )
    )


EXECUTORS = {
    "campaign.creator-get": direct_enveloped(_execute_creator_get),
    "campaign.creator-get-performance": direct_enveloped(_execute_creator_performance_get),
    "campaign.post-list": direct_enveloped(_execute_post_list),
    "campaign.post-get": direct_enveloped(_execute_post_get),
    "campaign.post-get-performance": direct_enveloped(_execute_post_performance_get),
    "campaign.post-resolve": direct_enveloped(_execute_post_resolve),
}
