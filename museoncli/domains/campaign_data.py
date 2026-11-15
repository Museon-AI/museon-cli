"""A Campaign's figures and, for a tracking Campaign, what it tracks.

Both kinds: the daily summary, period performance, breakdowns, and the posts and
creators a Campaign covers (`campaign content +list`, `campaign creator +list`). Only a
content tracking Campaign takes creators and posts by hand (`+add` / `+remove`); a UGC
Campaign's posts come from its creators' enrollments, so those writes refuse it, as the
web does. Every command takes the Campaign as `--campaign-id` (from `campaign +list`).
"""

from __future__ import annotations

from museoncli.execution import agent_domain_result, compact_params

from museoncli.execution import (
    CommandContext,
    direct_enveloped,
)

import argparse
from typing import Any
from museoncli.domains._model import CommandSpec, Domain
from museoncli.domains._shared import (
    _add_common_adapter_arguments,
    _direct_output_schema,
    _load_structured_args,
    _without_none,
)


def _add_campaign_id_arguments(parser: argparse.ArgumentParser) -> None:
    _add_common_adapter_arguments(parser)
    parser.add_argument("--campaign-id", required=True)


def _build_campaign_id_arguments(args: argparse.Namespace) -> dict[str, Any]:
    payload = _load_structured_args(args)
    payload["campaign_id"] = args.campaign_id
    return payload


def _add_campaign_date_range_arguments(parser: argparse.ArgumentParser) -> None:
    _add_campaign_id_arguments(parser)
    parser.add_argument("--date-from")
    parser.add_argument("--date-to")


def _build_campaign_date_range_arguments(
    args: argparse.Namespace,
) -> dict[str, Any]:
    payload = _build_campaign_id_arguments(args)
    payload.update(_without_none({"date_from": args.date_from, "date_to": args.date_to}))
    return payload


def _add_campaign_breakdown_arguments(parser: argparse.ArgumentParser) -> None:
    _add_campaign_date_range_arguments(parser)
    parser.add_argument("--by", choices=["brief", "persona", "tag", "creator-tag", "source-video"])
    parser.add_argument("--link-status", dest="link_status", choices=["linked"])
    parser.add_argument("--platform")
    parser.add_argument("--timezone")


def _build_campaign_breakdown_arguments(args: argparse.Namespace) -> dict[str, Any]:
    payload = _build_campaign_date_range_arguments(args)
    payload.update(
        _without_none(
            {
                "by": args.by,
                "link_status": args.link_status,
                "platform": args.platform,
                "timezone": args.timezone,
            }
        )
    )
    return payload


def _campaign_breakdown_input_schema() -> dict[str, Any]:
    schema = _campaign_date_range_input_schema()
    schema["properties"].update(
        {
            "by": {
                "type": ["string", "null"],
                "enum": ["brief", "persona", "tag", "creator-tag", "source-video", None],
                "description": (
                    "Dimension. A ugc campaign takes brief (default), persona or tag; any "
                    "other type (tracking) takes creator-tag (default) or source-video. "
                    "See +list-dimensions."
                ),
            },
            "link_status": {
                "type": ["string", "null"],
                "enum": ["linked", None],
                "description": (
                    "UGC campaigns only: 'linked' reads the approved posts only; omit for "
                    "every counted post (approved + awaiting review)."
                ),
            },
            "platform": {"type": ["string", "null"]},
            "timezone": {
                "type": ["string", "null"],
                "description": "IANA timezone for the publication dates (default UTC).",
            },
        }
    )
    return schema


def _add_campaign_paged_tracking_arguments(
    parser: argparse.ArgumentParser,
) -> None:
    _add_campaign_date_range_arguments(parser)
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--page-size", type=int, default=20)
    parser.add_argument("--search")
    parser.add_argument("--platform")
    parser.add_argument("--sort")
    parser.add_argument("--link-status", dest="link_status", choices=["linked"])


def _add_campaign_creator_list_arguments(
    parser: argparse.ArgumentParser,
) -> None:
    _add_campaign_paged_tracking_arguments(parser)


def _build_campaign_creator_list_arguments(
    args: argparse.Namespace,
) -> dict[str, Any]:
    payload = _build_campaign_date_range_arguments(args)
    payload.update(
        _without_none(
            {
                "page": args.page,
                "page_size": args.page_size,
                "search": args.search,
                "platform": args.platform,
                "sort": args.sort,
                "link_status": args.link_status,
            }
        )
    )
    return payload


def _add_campaign_content_list_arguments(parser: argparse.ArgumentParser) -> None:
    _add_campaign_paged_tracking_arguments(parser)
    parser.add_argument("--creator-id", dest="creator_id")
    parser.add_argument("--views-min", dest="views_min", type=int)
    parser.add_argument("--views-max", dest="views_max", type=int)
    parser.add_argument("--likes-min", dest="likes_min", type=int)
    parser.add_argument("--likes-max", dest="likes_max", type=int)

    parser.add_argument("--timezone", default="UTC")
    parser.add_argument("--brief-id")
    parser.add_argument("--persona-id")
    parser.add_argument("--ugc-creator-id")
    parser.add_argument("--review-status", choices=["approved", "awaiting-review"])


def _add_campaign_content_remove_arguments(parser: argparse.ArgumentParser) -> None:
    _add_campaign_id_arguments(parser)
    parser.add_argument("--collection-content-id", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--yes", action="store_true")


def _add_campaign_content_batch_remove_arguments(
    parser: argparse.ArgumentParser,
) -> None:
    _add_campaign_id_arguments(parser)
    parser.add_argument("--collection-content-ids", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--yes", action="store_true")


def _build_campaign_content_list_arguments(
    args: argparse.Namespace,
) -> dict[str, Any]:
    payload = _build_campaign_date_range_arguments(args)
    payload.update(
        _without_none(
            {
                "page": args.page,
                "page_size": args.page_size,
                "search": args.search,
                "platform": args.platform,
                "sort": args.sort,
                "creator_id": args.creator_id,
                "timezone": args.timezone,
                "brief_id": args.brief_id,
                "persona_id": args.persona_id,
                "ugc_creator_id": args.ugc_creator_id,
                "review_status": args.review_status,
                "views_min": args.views_min,
                "views_max": args.views_max,
                "likes_min": args.likes_min,
                "likes_max": args.likes_max,
                "link_status": args.link_status,
            }
        )
    )
    return payload


def _build_campaign_content_remove_arguments(
    args: argparse.Namespace,
) -> dict[str, Any]:
    payload = _load_structured_args(args)
    payload.update(
        {
            "campaign_id": args.campaign_id,
            "collection_content_id": args.collection_content_id,
            "dry_run": bool(args.dry_run),
        }
    )
    return payload


def _build_campaign_content_batch_remove_arguments(
    args: argparse.Namespace,
) -> dict[str, Any]:
    payload = _load_structured_args(args)
    payload.update(
        {
            "campaign_id": args.campaign_id,
            "collection_content_ids": _collection_content_ids_csv(args.collection_content_ids),
            "dry_run": bool(args.dry_run),
        }
    )
    return payload


def _collection_content_ids_csv(value: str) -> list[str]:
    collection_content_ids: list[str] = []
    seen: set[str] = set()
    for raw_id in value.split(","):
        collection_content_id = raw_id.strip()
        if collection_content_id and collection_content_id not in seen:
            seen.add(collection_content_id)
            collection_content_ids.append(collection_content_id)
    return collection_content_ids


def _add_campaign_creator_add_arguments(parser: argparse.ArgumentParser) -> None:
    _add_campaign_id_arguments(parser)
    parser.add_argument("--url", action="append", dest="creator_urls")
    parser.add_argument("--creator-id", action="append", dest="creator_ids")
    parser.add_argument("--hashtag", action="append", dest="hashtags")
    parser.add_argument("--no-sync", action="store_true", dest="no_sync")
    parser.add_argument("--dry-run", action="store_true")


def _build_campaign_creator_add_arguments(args: argparse.Namespace) -> dict[str, Any]:
    payload = _build_campaign_id_arguments(args)
    payload.update(
        _without_none(
            {
                "creator_urls": list(args.creator_urls) if args.creator_urls else None,
                "creator_ids": list(args.creator_ids) if args.creator_ids else None,
                "hashtags": list(args.hashtags) if args.hashtags else None,
            }
        )
    )
    if getattr(args, "no_sync", False):
        payload["sync"] = False
    if not payload.get("creator_urls") and not payload.get("creator_ids"):
        raise ValueError("Provide at least one --url or --creator-id.")
    return payload


def _add_campaign_creator_remove_arguments(parser: argparse.ArgumentParser) -> None:
    _add_campaign_id_arguments(parser)
    parser.add_argument("--creator-id", dest="creator_social_account_id", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--yes", action="store_true")


def _build_campaign_creator_remove_arguments(
    args: argparse.Namespace,
) -> dict[str, Any]:
    payload = _load_structured_args(args)
    payload.update(
        {
            "campaign_id": args.campaign_id,
            "creator_social_account_id": args.creator_social_account_id,
            "dry_run": bool(args.dry_run),
        }
    )
    return payload


def _add_campaign_content_add_arguments(parser: argparse.ArgumentParser) -> None:
    _add_campaign_id_arguments(parser)
    parser.add_argument("--url", action="append", dest="content_urls")
    parser.add_argument("--content-id", action="append", dest="content_ids")
    parser.add_argument("--no-sync", action="store_true", dest="no_sync")
    parser.add_argument("--dry-run", action="store_true")


def _build_campaign_content_add_arguments(args: argparse.Namespace) -> dict[str, Any]:
    payload = _build_campaign_id_arguments(args)
    payload.update(
        _without_none(
            {
                "content_urls": list(args.content_urls) if args.content_urls else None,
                "content_ids": list(args.content_ids) if args.content_ids else None,
            }
        )
    )
    if getattr(args, "no_sync", False):
        payload["sync"] = False
    if not payload.get("content_urls") and not payload.get("content_ids"):
        raise ValueError("Provide at least one --url or --content-id.")
    return payload


def _add_campaign_summary_arguments(parser: argparse.ArgumentParser) -> None:
    _add_campaign_date_range_arguments(parser)
    parser.add_argument("--granularity", default="day")
    parser.add_argument("--search")
    parser.add_argument("--platform")
    parser.add_argument("--metrics")
    parser.add_argument("--creator-id", dest="creator_id")

    parser.add_argument("--timezone", default="UTC")


def _build_campaign_summary_arguments(args: argparse.Namespace) -> dict[str, Any]:
    payload = _build_campaign_date_range_arguments(args)
    payload.update(
        _without_none(
            {
                "timezone": args.timezone,
                "granularity": args.granularity,
                "search": args.search,
                "platform": args.platform,
                "metrics": args.metrics,
                "creator_id": args.creator_id,
            }
        )
    )
    return payload


def _add_campaign_period_performance_arguments(
    parser: argparse.ArgumentParser,
) -> None:
    _add_campaign_id_arguments(parser)
    parser.add_argument("--period-start", dest="current_period_start", required=True)
    parser.add_argument("--period-end", dest="current_period_end", required=True)
    parser.add_argument("--timezone", default="UTC")


def _build_campaign_period_performance_arguments(
    args: argparse.Namespace,
) -> dict[str, Any]:
    payload = _build_campaign_id_arguments(args)
    payload.update(
        {
            "current_period_start": args.current_period_start,
            "current_period_end": args.current_period_end,
            "timezone": args.timezone,
        }
    )
    return payload




def _campaign_id_input_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "campaign_id": {
                "type": "string",
                "minLength": 1,
                "description": "The Campaign's ID (either kind), from campaign +list.",
            }
        },
        "required": ["campaign_id"],
    }


def _campaign_date_range_input_schema() -> dict[str, Any]:
    schema = _campaign_id_input_schema()
    schema["properties"].update(
        {
            "date_from": {"type": ["string", "null"]},
            "date_to": {"type": ["string", "null"]},
        }
    )
    return schema


def _campaign_paged_input_schema() -> dict[str, Any]:
    schema = _campaign_date_range_input_schema()
    schema["properties"].update(
        {
            "page": {"type": "integer", "minimum": 1, "default": 1},
            "page_size": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
            "search": {"type": ["string", "null"]},
            "platform": {"type": ["string", "null"]},
            "sort": {"type": ["string", "null"]},
            "link_status": {
                "type": ["string", "null"],
                "enum": ["linked", None],
                "description": (
                    "UGC campaigns only: 'linked' keeps the approved posts (the Campaign "
                    "page's Approved scope); omit for every counted post."
                ),
            },
        }
    )
    return schema


def _campaign_creator_list_input_schema() -> dict[str, Any]:
    schema = _campaign_paged_input_schema()
    return schema


def _campaign_content_list_input_schema() -> dict[str, Any]:
    schema = _campaign_paged_input_schema()
    schema["properties"].update(
        {
            "timezone": {"type": "string", "default": "UTC"},
            "brief_id": {"type": ["string", "null"], "format": "uuid"},
            "persona_id": {"type": ["string", "null"], "format": "uuid"},
            "ugc_creator_id": {
                "type": ["string", "null"],
                "format": "uuid",
                "description": "UGC person ID, distinct from the social account --creator-id.",
            },
            "review_status": {
                "type": ["string", "null"],
                "enum": ["approved", "awaiting-review", None],
            },
            "creator_id": {"type": ["string", "null"]},
            "views_min": {"type": ["integer", "null"], "minimum": 0},
            "views_max": {"type": ["integer", "null"], "minimum": 0},
            "likes_min": {"type": ["integer", "null"], "minimum": 0},
            "likes_max": {"type": ["integer", "null"], "minimum": 0},
        }
    )
    return schema


def _campaign_content_remove_input_schema() -> dict[str, Any]:
    schema = _campaign_id_input_schema()
    schema["properties"].update(
        {
            "collection_content_id": {"type": "string", "minLength": 1},
            "dry_run": {"type": "boolean", "default": False},
        }
    )
    schema["required"].append("collection_content_id")
    return schema


def _campaign_content_batch_remove_input_schema() -> dict[str, Any]:
    schema = _campaign_id_input_schema()
    schema["properties"].update(
        {
            "collection_content_ids": {
                "type": "array",
                "items": {"type": "string", "minLength": 1},
                "minItems": 1,
                "maxItems": 100,
            },
            "dry_run": {"type": "boolean", "default": False},
        }
    )
    schema["required"].append("collection_content_ids")
    return schema


def _campaign_creator_add_input_schema() -> dict[str, Any]:
    schema = _campaign_id_input_schema()
    schema["properties"].update(
        {
            "creator_urls": {
                "type": ["array", "null"],
                "items": {"type": "string"},
                "description": (
                    "Public creator profile URLs to track. Resolved in a background "
                    "task (response data.url_import_task); verify later with campaign creator +list."
                ),
            },
            "creator_ids": {
                "type": ["array", "null"],
                "items": {"type": "string"},
                "description": "Existing creator_social_account ids already known to Museon.",
            },
            "hashtags": {
                "type": ["array", "null"],
                "items": {"type": "string"},
                "description": "Optional hashtags: only the creators' posts with one of them are tracked.",
            },
            "sync": {"type": "boolean", "default": True},
        }
    )
    return schema


def _campaign_creator_remove_input_schema() -> dict[str, Any]:
    schema = _campaign_id_input_schema()
    schema["properties"].update(
        {
            "creator_social_account_id": {"type": "string", "minLength": 1},
            "dry_run": {"type": "boolean", "default": False},
        }
    )
    schema["required"].append("creator_social_account_id")
    return schema


def _campaign_content_add_input_schema() -> dict[str, Any]:
    schema = _campaign_id_input_schema()
    schema["properties"].update(
        {
            "content_urls": {
                "type": ["array", "null"],
                "items": {"type": "string"},
                "description": (
                    "Public post/video URLs to track. Resolved in a background task "
                    "(response data.url_import_task); verify later with campaign content +list."
                ),
            },
            "content_ids": {
                "type": ["array", "null"],
                "items": {"type": "string"},
                "description": "Existing content ids already known to Museon (field `id` from campaign content +list).",
            },
            "sync": {"type": "boolean", "default": True},
        }
    )
    return schema


def _campaign_summary_input_schema() -> dict[str, Any]:
    schema = _campaign_date_range_input_schema()
    schema["properties"].update(
        {
            "timezone": {"type": "string", "default": "UTC"},
            "granularity": {"type": "string", "default": "day"},
            "search": {"type": ["string", "null"]},
            "platform": {"type": ["string", "null"]},
            "metrics": {"type": ["string", "null"]},
            "creator_id": {"type": ["string", "null"]},
        }
    )
    return schema


def _campaign_period_performance_input_schema() -> dict[str, Any]:
    schema = _campaign_id_input_schema()
    schema["properties"].update(
        {
            "current_period_start": {
                "type": "string",
                "format": "date",
                "description": "Inclusive current-period publication start date.",
            },
            "current_period_end": {
                "type": "string",
                "format": "date",
                "description": (
                    "Inclusive current-period publication end date and performance snapshot cutoff."
                ),
            },
            "timezone": {
                "type": "string",
                "default": "UTC",
                "description": "IANA timezone used to interpret publication dates.",
            },
        }
    )
    schema["required"].extend(["current_period_start", "current_period_end"])
    return schema


def specs() -> list[CommandSpec]:
    return [
        CommandSpec(
            domain=Domain.CAMPAIGN,
            shortcut="+list-dimensions",
            summary=(
                "Read what a campaign's posts can be broken down by, before analysing "
                "them. Returns campaign_type and post_scopes: a ugc campaign offers "
                "brief (each with the persona it is under), persona and tag over "
                "approved (--link-status linked) or all posts; a tracking campaign "
                "offers creator_tag over all posts."
            ),
            risk_level="read",
            execution="direct",
            adapter_tool_name="campaign_dimensions",
            input_schema=_campaign_id_input_schema(),
            output_schema=_direct_output_schema(
                "Campaign type, post scopes, and dimension values returned by Museon API."
            ),
            examples=[
                "museoncli campaign +list-dimensions --campaign-id <campaign_id>",
            ],
            add_arguments=_add_campaign_id_arguments,
            build_arguments=_build_campaign_id_arguments,
        ),
        CommandSpec(
            domain=Domain.CAMPAIGN,
            shortcut="+get-breakdown",
            summary=(
                "Group a campaign's counted posts by one dimension: brief, persona (the "
                "brief's) or tag for a ugc campaign, creator-tag or source-video for a "
                "tracking one. Rows are bucket value (carries it), unassigned (approved, "
                "without one) or awaiting_review (ugc, not approved yet), each with posts, "
                "creators, measured_posts, metric sums and median_views. Tags overlap: rows "
                "can outnumber totals, which count each post once."
            ),
            risk_level="read",
            execution="direct",
            adapter_tool_name="campaign_breakdown",
            input_schema=_campaign_breakdown_input_schema(),
            output_schema=_direct_output_schema(
                "Breakdown rows, totals and the post scope returned by Museon API."
            ),
            examples=[
                (
                    "museoncli campaign +get-breakdown --campaign-id <campaign_id> --by brief "
                    "--link-status linked --date-from 2026-10-01 --date-to 2026-10-28"
                ),
                "museoncli campaign +get-breakdown --campaign-id <campaign_id> --by creator-tag",
                "museoncli campaign +get-breakdown --campaign-id <campaign_id> --by source-video",
            ],
            add_arguments=_add_campaign_breakdown_arguments,
            build_arguments=_build_campaign_breakdown_arguments,
        ),
        CommandSpec(
            domain=Domain.CAMPAIGN,
            shortcut="+get-summary",
            summary=(
                "Read a Campaign's daily content-trend totals over a date window (the "
                "Dashboard's KPI tiles and trend). This is not the Analytics Period "
                "Performance comparison; use +get-period-performance for period-end "
                "snapshots and previous-period deltas."
            ),
            risk_level="read",
            execution="direct",
            adapter_tool_name="campaign_summary",
            input_schema=_campaign_summary_input_schema(),
            output_schema=_direct_output_schema("Daily totals and the window, from Museon API."),
            examples=[
                (
                    "museoncli campaign +get-summary --campaign-id <campaign_id> "
                    "--date-from 2026-06-01 --date-to 2026-06-08"
                ),
            ],
            add_arguments=_add_campaign_summary_arguments,
            build_arguments=_build_campaign_summary_arguments,
        ),
        CommandSpec(
            domain=Domain.CAMPAIGN,
            shortcut="+get-period-performance",
            summary=(
                "Read the Campaign Analytics Period Performance snapshot. The requested "
                "period end is the current performance cutoff; Museon derives the "
                "immediately preceding equal-length period and returns metric start/end "
                "values, changes, comparison rates, trends, coverage, and scope metadata."
            ),
            risk_level="read",
            execution="direct",
            adapter_tool_name="campaign_period_performance",
            input_schema=_campaign_period_performance_input_schema(),
            output_schema=_direct_output_schema(
                "Campaign period-performance snapshot returned by Museon API."
            ),
            examples=[
                (
                    "museoncli campaign +get-period-performance --campaign-id <campaign_id> "
                    "--period-start 2026-09-14 --period-end 2026-09-20 "
                    "--timezone Asia/Shanghai"
                ),
            ],
            add_arguments=_add_campaign_period_performance_arguments,
            build_arguments=_build_campaign_period_performance_arguments,
        ),
        CommandSpec(
            domain=Domain.CAMPAIGN,
            resource="creator",
            shortcut="+list",
            summary=(
                "List the creators (social accounts) a Campaign covers, with their post "
                "figures in the window. A row's creator_social_account_id is what "
                "campaign creator +get, +remove and campaign content +list --creator-id take."
            ),
            risk_level="read",
            execution="direct",
            adapter_tool_name="campaign_creator_list",
            input_schema=_campaign_creator_list_input_schema(),
            output_schema=_direct_output_schema("The Campaign's creators, from Museon API."),
            examples=[
                "museoncli campaign creator +list --campaign-id <campaign_id> --sort views_desc",
            ],
            add_arguments=_add_campaign_creator_list_arguments,
            build_arguments=_build_campaign_creator_list_arguments,
        ),
        CommandSpec(
            domain=Domain.CAMPAIGN,
            resource="creator",
            shortcut="+add",
            summary=(
                "Track creators in a tracking Campaign so their matching posts sync in going "
                "forward. --url imports new creators by public profile URL via a "
                "background task (response data.url_import_task); --creator-id attaches "
                "creators already known to Museon. Verify with campaign creator +list later. "
                "A UGC Campaign's creators join through enrollments, so it refuses one."
            ),
            risk_level="write",
            supports_dry_run=True,
            execution="direct",
            adapter_tool_name="campaign_creator_add",
            input_schema=_campaign_creator_add_input_schema(),
            output_schema=_direct_output_schema(
                "Add summary: requested ids/urls, creator_id_task, url_import_task."
            ),
            examples=[
                (
                    "museoncli campaign creator +add --campaign-id <campaign_id> "
                    "--url https://www.tiktok.com/@creator1"
                ),
                (
                    "museoncli campaign creator +add --campaign-id <campaign_id> "
                    "--creator-id <creator_social_account_id>"
                ),
            ],
            add_arguments=_add_campaign_creator_add_arguments,
            build_arguments=_build_campaign_creator_add_arguments,
        ),
        CommandSpec(
            domain=Domain.CAMPAIGN,
            resource="creator",
            shortcut="+remove",
            summary=(
                "Stop tracking a creator in a tracking Campaign: its posts that came from "
                "this creator leave the Campaign and it resyncs. This does NOT delete the "
                "creator's social-platform account; explicit operator confirmation is "
                "required before running with --yes. Tracking is organization-wide, so the "
                "creator stays tracked wherever another Campaign follows them. --creator-id "
                "is the creator_social_account_id from campaign creator +list. A UGC "
                "Campaign's creators leave through ugc enrollment +remove."
            ),
            risk_level="destructive",
            requires_confirmation=True,
            supports_dry_run=True,
            execution="direct",
            adapter_tool_name="campaign_creator_remove",
            input_schema=_campaign_creator_remove_input_schema(),
            output_schema=_direct_output_schema(
                "Creator removal payload: what was removed and its scope note."
            ),
            examples=[
                (
                    "museoncli campaign creator +remove --campaign-id <campaign_id> "
                    "--creator-id <creator_social_account_id> --dry-run"
                ),
            ],
            add_arguments=_add_campaign_creator_remove_arguments,
            build_arguments=_build_campaign_creator_remove_arguments,
        ),
        CommandSpec(
            domain=Domain.CAMPAIGN,
            resource="content",
            shortcut="+list",
            summary=(
                "List the posts a Campaign covers, either kind, with their figures: filter by "
                "window, platform, creator, views and likes; a UGC Campaign also by Format "
                "(--brief-id), persona, UGC creator and review status. A row's "
                "collection_content_id is what campaign content +remove takes."
            ),
            risk_level="read",
            execution="direct",
            adapter_tool_name="campaign_content_list",
            input_schema=_campaign_content_list_input_schema(),
            output_schema=_direct_output_schema("The Campaign's posts, from Museon API."),
            examples=[
                (
                    "museoncli campaign content +list "
                    "--campaign-id <campaign_id> --date-from 2026-06-16 --date-to 2026-07-15 "
                    "--views-min 10000 --likes-min 10 --likes-max 99 "
                    "--sort views_desc --page-size 100"
                ),
            ],
            add_arguments=_add_campaign_content_list_arguments,
            build_arguments=_build_campaign_content_list_arguments,
        ),
        CommandSpec(
            domain=Domain.CAMPAIGN,
            resource="content",
            shortcut="+add",
            summary=(
                "Track individual posts in a tracking Campaign. --url imports new posts by "
                "public URL via a background task (response data.url_import_task); "
                "--content-id attaches posts already known to Museon. Verify with campaign "
                "content +list later. A UGC Campaign's posts come from its creators, so it "
                "refuses one."
            ),
            risk_level="write",
            supports_dry_run=True,
            execution="direct",
            adapter_tool_name="campaign_content_add",
            input_schema=_campaign_content_add_input_schema(),
            output_schema=_direct_output_schema(
                "Add summary: requested ids/urls, content_id_task, url_import_task."
            ),
            examples=[
                (
                    "museoncli campaign content +add --campaign-id <campaign_id> "
                    "--url https://www.tiktok.com/@creator/video/123"
                ),
                (
                    "museoncli campaign content +add --campaign-id <campaign_id> "
                    "--content-id <content_id>"
                ),
            ],
            add_arguments=_add_campaign_content_add_arguments,
            build_arguments=_build_campaign_content_add_arguments,
        ),
        CommandSpec(
            domain=Domain.CAMPAIGN,
            resource="content",
            shortcut="+remove",
            summary=(
                "Remove one post from a tracking Campaign (soft delete of its place in the "
                "Campaign); it does NOT delete the original social-platform post. Explicit "
                "operator confirmation is required before running with --yes. "
                "--collection-content-id comes from campaign content +list; the response "
                "lists what was removed and what was missing. A UGC Campaign stops counting "
                "a post with ugc post +stop-counting instead."
            ),
            risk_level="destructive",
            requires_confirmation=True,
            supports_dry_run=True,
            execution="direct",
            adapter_tool_name="campaign_content_remove",
            input_schema=_campaign_content_remove_input_schema(),
            output_schema=_direct_output_schema("Removed and missing posts, from Museon API."),
            examples=[
                (
                    "museoncli campaign content +remove --campaign-id <campaign_id> "
                    "--collection-content-id <collection_content_id> --dry-run"
                ),
            ],
            add_arguments=_add_campaign_content_remove_arguments,
            build_arguments=_build_campaign_content_remove_arguments,
        ),
        CommandSpec(
            domain=Domain.CAMPAIGN,
            resource="content",
            shortcut="+bulk-remove",
            summary=(
                "Remove up to 100 posts from a tracking Campaign at once (soft delete of "
                "their place in the Campaign); it does NOT delete the original "
                "social-platform posts. Explicit operator confirmation is required before "
                "running with --yes. Split more than 100 into several calls; the response "
                "lists what was removed and what was missing. --collection-content-ids come "
                "from campaign content +list."
            ),
            risk_level="destructive",
            requires_confirmation=True,
            supports_dry_run=True,
            execution="direct",
            adapter_tool_name="campaign_content_bulk_remove",
            input_schema=_campaign_content_batch_remove_input_schema(),
            output_schema=_direct_output_schema("Removed and missing posts, from Museon API."),
            examples=[
                (
                    "museoncli campaign content +bulk-remove --campaign-id <campaign_id> "
                    "--collection-content-ids <collection_content_id_1>,<collection_content_id_2> "
                    "--dry-run"
                ),
            ],
            add_arguments=_add_campaign_content_batch_remove_arguments,
            build_arguments=_build_campaign_content_batch_remove_arguments,
        ),
    ]


# ---- executors ----
async def _execute_content_remove(ctx: CommandContext) -> Any:
    cfg = ctx.cfg
    arguments = ctx.arguments
    api_data = ctx.api_data
    campaign_id = str(arguments.get("campaign_id") or "")
    collection_content_id = str(arguments.get("collection_content_id") or "")
    return agent_domain_result(
        await api_data(
            cfg,
            "POST",
            f"/agent-cli/campaign-monitors/{campaign_id}/content/batch-remove",
            json_body={
                "payload": {"collection_content_ids": [collection_content_id]},
            },
        )
    )


async def _execute_content_batch_remove(ctx: CommandContext) -> Any:
    cfg = ctx.cfg
    arguments = ctx.arguments
    api_data = ctx.api_data
    campaign_id = str(arguments.get("campaign_id") or "")
    raw_ids = arguments.get("collection_content_ids")
    if isinstance(raw_ids, list):
        collection_content_ids = _dedupe_collection_content_ids(raw_ids)
    else:
        collection_content_ids = _collection_content_ids_csv(str(raw_ids or ""))
    return agent_domain_result(
        await api_data(
            cfg,
            "POST",
            f"/agent-cli/campaign-monitors/{campaign_id}/content/batch-remove",
            json_body={
                "payload": {"collection_content_ids": collection_content_ids},
            },
        )
    )


async def _execute_content_list(ctx: CommandContext) -> Any:
    cfg = ctx.cfg
    arguments = ctx.arguments
    api_data = ctx.api_data
    base_params: dict[str, Any] = {}
    campaign_id = str(arguments.get("campaign_id") or "")
    date_params = {
        **base_params,
        "date_from": arguments.get("date_from"),
        "date_to": arguments.get("date_to"),
    }
    return agent_domain_result(
        await api_data(
            cfg,
            "GET",
            f"/agent-cli/campaign-monitors/{campaign_id}/content",
            params=compact_params(
                {
                    **date_params,
                    "page": arguments.get("page", 1),
                    "page_size": arguments.get("page_size", 20),
                    "search": arguments.get("search"),
                    "platform": arguments.get("platform"),
                    "sort": arguments.get("sort"),
                    "creator_id": arguments.get("creator_id"),
                    "timezone": arguments.get("timezone"),
                    "brief_id": arguments.get("brief_id"),
                    "persona_id": arguments.get("persona_id"),
                    "ugc_creator_id": arguments.get("ugc_creator_id"),
                    "review_status": (
                        arguments["review_status"].replace("-", "_")
                        if arguments.get("review_status")
                        else None
                    ),
                    "views_min": arguments.get("views_min"),
                    "views_max": arguments.get("views_max"),
                    "likes_min": arguments.get("likes_min"),
                    "likes_max": arguments.get("likes_max"),
                    "link_status": arguments.get("link_status"),
                }
            ),
        )
    )


async def _execute_creator_list(ctx: CommandContext) -> Any:
    cfg = ctx.cfg
    arguments = ctx.arguments
    api_data = ctx.api_data
    base_params: dict[str, Any] = {}
    campaign_id = str(arguments.get("campaign_id") or "")
    date_params = {
        **base_params,
        "date_from": arguments.get("date_from"),
        "date_to": arguments.get("date_to"),
    }
    return agent_domain_result(
        await api_data(
            cfg,
            "GET",
            f"/agent-cli/campaign-monitors/{campaign_id}/creators",
            params=compact_params(
                {
                    **date_params,
                    "page": arguments.get("page", 1),
                    "page_size": arguments.get("page_size", 20),
                    "search": arguments.get("search"),
                    "platform": arguments.get("platform"),
                    "sort": arguments.get("sort"),
                    "link_status": arguments.get("link_status"),
                }
            ),
        )
    )




async def _execute_dimensions(ctx: CommandContext) -> Any:
    cfg = ctx.cfg
    arguments = ctx.arguments
    api_data = ctx.api_data
    campaign_id = str(arguments.get("campaign_id") or "")
    return agent_domain_result(
        await api_data(
            cfg,
            "GET",
            f"/agent-cli/campaign-monitors/{campaign_id}/dimensions",
        )
    )


async def _execute_breakdown(ctx: CommandContext) -> Any:
    cfg = ctx.cfg
    arguments = ctx.arguments
    api_data = ctx.api_data
    campaign_id = str(arguments.get("campaign_id") or "")
    return agent_domain_result(
        await api_data(
            cfg,
            "GET",
            f"/agent-cli/campaign-monitors/{campaign_id}/breakdown",
            params=compact_params(
                {
                    # The API names the dimensions as +list-dimensions returns them.
                    "by": str(arguments["by"]).replace("-", "_") if arguments.get("by") else None,
                    "date_from": arguments.get("date_from"),
                    "date_to": arguments.get("date_to"),
                    "link_status": arguments.get("link_status"),
                    "platform": arguments.get("platform"),
                    "timezone": arguments.get("timezone"),
                }
            ),
        )
    )




async def _execute_summary(ctx: CommandContext) -> Any:
    cfg = ctx.cfg
    arguments = ctx.arguments
    api_data = ctx.api_data
    base_params: dict[str, Any] = {}
    campaign_id = str(arguments.get("campaign_id") or "")
    date_params = {
        **base_params,
        "date_from": arguments.get("date_from"),
        "date_to": arguments.get("date_to"),
    }
    return agent_domain_result(
        await api_data(
            cfg,
            "GET",
            f"/agent-cli/campaign-monitors/{campaign_id}/summary",
            params=compact_params(
                {
                    **date_params,
                    "timezone": arguments.get("timezone", "UTC"),
                    "granularity": arguments.get("granularity", "day"),
                    "search": arguments.get("search"),
                    "platform": arguments.get("platform"),
                    "metrics": arguments.get("metrics"),
                    "creator_id": arguments.get("creator_id"),
                }
            ),
        )
    )


async def _execute_period_performance(ctx: CommandContext) -> Any:
    cfg = ctx.cfg
    arguments = ctx.arguments
    api_data = ctx.api_data
    campaign_id = str(arguments.get("campaign_id") or "")
    return agent_domain_result(
        await api_data(
            cfg,
            "GET",
            f"/agent-cli/campaign-monitors/{campaign_id}/period-performance",
            params={
                "current_period_start": arguments["current_period_start"],
                "current_period_end": arguments["current_period_end"],
                "timezone": arguments.get("timezone", "UTC"),
            },
        )
    )


async def _execute_creator_add(ctx: CommandContext) -> Any:
    cfg = ctx.cfg
    arguments = ctx.arguments
    api_data = ctx.api_data
    campaign_id = str(arguments.get("campaign_id") or "")
    payload = compact_params(
        {
            "creator_urls": arguments.get("creator_urls"),
            "creator_ids": arguments.get("creator_ids"),
            "hashtags": arguments.get("hashtags"),
        }
    )
    if arguments.get("sync") is not None:
        payload["sync"] = bool(arguments["sync"])
    return agent_domain_result(
        await api_data(
            cfg,
            "POST",
            f"/agent-cli/campaign-monitors/{campaign_id}/creators",
            json_body={"payload": payload},
        )
    )


async def _execute_creator_remove(ctx: CommandContext) -> Any:
    cfg = ctx.cfg
    arguments = ctx.arguments
    api_data = ctx.api_data
    campaign_id = str(arguments.get("campaign_id") or "")
    creator_social_account_id = str(arguments.get("creator_social_account_id") or "")
    return agent_domain_result(
        await api_data(
            cfg,
            "POST",
            f"/agent-cli/campaign-monitors/{campaign_id}/creators/{creator_social_account_id}/remove",
            json_body={"payload": {}},
        )
    )


async def _execute_content_add(ctx: CommandContext) -> Any:
    cfg = ctx.cfg
    arguments = ctx.arguments
    api_data = ctx.api_data
    campaign_id = str(arguments.get("campaign_id") or "")
    payload = compact_params(
        {
            "content_urls": arguments.get("content_urls"),
            "content_ids": arguments.get("content_ids"),
        }
    )
    if arguments.get("sync") is not None:
        payload["sync"] = bool(arguments["sync"])
    return agent_domain_result(
        await api_data(
            cfg,
            "POST",
            f"/agent-cli/campaign-monitors/{campaign_id}/content",
            json_body={"payload": payload},
        )
    )


def _dedupe_collection_content_ids(raw_ids: list[Any]) -> list[str]:
    collection_content_ids: list[str] = []
    seen: set[str] = set()
    for raw_id in raw_ids:
        collection_content_id = str(raw_id).strip()
        if collection_content_id and collection_content_id not in seen:
            seen.add(collection_content_id)
            collection_content_ids.append(collection_content_id)
    return collection_content_ids


async def _require_tracking(ctx: CommandContext) -> None:
    """Refuse a UGC Campaign: its creators and posts come through enrollments, as on the web."""
    campaign_id = str(ctx.arguments.get("campaign_id") or "")
    header = await ctx.api_data_v2(ctx.cfg, "GET", f"/ugc/collections/{campaign_id}/campaign")
    if isinstance(header, dict) and header.get("campaign_type") == "ugc":
        raise ValueError(
            "This is a UGC Campaign: its creators join through enrollments (ugc invitation, "
            "ugc recruit-link, ugc enrollment) and their posts are counted through review "
            "(ugc creative, ugc post +stop-counting). Creators and posts are added to or "
            "removed from content tracking Campaigns only."
        )


def _tracking_only(execute: Any) -> Any:
    async def run(ctx: CommandContext) -> Any:
        await _require_tracking(ctx)
        return await execute(ctx)

    return run


EXECUTORS = {
    "campaign.list-dimensions": direct_enveloped(_execute_dimensions),
    "campaign.get-breakdown": direct_enveloped(_execute_breakdown),
    "campaign.get-summary": direct_enveloped(_execute_summary),
    "campaign.get-period-performance": direct_enveloped(_execute_period_performance),
    "campaign.creator-list": direct_enveloped(_execute_creator_list),
    "campaign.creator-add": direct_enveloped(_tracking_only(_execute_creator_add)),
    "campaign.creator-remove": direct_enveloped(_tracking_only(_execute_creator_remove)),
    "campaign.content-list": direct_enveloped(_execute_content_list),
    "campaign.content-add": direct_enveloped(_tracking_only(_execute_content_add)),
    "campaign.content-remove": direct_enveloped(_tracking_only(_execute_content_remove)),
    "campaign.content-bulk-remove": direct_enveloped(_tracking_only(_execute_content_batch_remove)),
}
