"""Analytics board reads: the 分析 page (/analytics) of the new interface.

A board is a saved view over several Campaigns with its own filters. The routes the
web calls: ``/api/v1/analytics-dashboards`` (the organization's boards and those
shared into it), ``/api/v1/analytics-dashboards/{id}`` (one board: its Campaigns and
saved filters), and for its figures the collection-set reads the board page makes
over the board's Campaigns (``/monitor-collection-sets/...``): daily trends, the
period's core metrics, the posts and the creators. Everyone in the organization
reads its boards (members too); what each board's figures show is decided per
Campaign by the server, exactly as on the board page.
"""

from __future__ import annotations

from typing import Any

from museoncli.domains._model import CommandSpec, Domain
from museoncli.domains._org_reads import (
    PAGE,
    PAGE_SIZE,
    D,
    TZ,
    Route,
    choice,
    get,
    read,
    require_organization,
    text,
    uuid,
)
from museoncli.execution import CommandContext

EXECUTORS: dict[str, Any] = {}

BOARDS = "/analytics-dashboards"
BOARD_ID = uuid("Board id from analytics board +list.")
WIDGETS = ("trends", "core-metrics", "content", "creators")
PLATFORMS = ("tiktok", "instagram", "youtube", "facebook")


def _window(arguments: dict[str, Any], board: dict[str, Any]) -> tuple[Any, Any]:
    saved = board.get("filters") if isinstance(board.get("filters"), dict) else {}
    return (
        arguments.get("date_from") or saved.get("date_from"),
        arguments.get("date_to") or saved.get("date_to"),
    )


def _collections(board: dict[str, Any]) -> list[str]:
    campaigns = board.get("campaigns") if isinstance(board.get("campaigns"), list) else []
    return sorted(
        {
            item["monitor_collection_id"]
            for item in campaigns
            if isinstance(item, dict)
            and item.get("available", True)
            and item.get("monitor_collection_id")
        }
    )


def _link_status(arguments: dict[str, Any], board: dict[str, Any]) -> str:
    saved = board.get("filters") if isinstance(board.get("filters"), dict) else {}
    scope = arguments.get("scope") or saved.get("post_scope") or "all"
    return "linked" if scope == "approved" else "not_excluded"


async def _data(ctx: CommandContext, arguments: dict[str, Any]) -> Any:
    board = await get(ctx, Route(BOARDS + "/{id}", version=1), {"id": arguments["id"]})
    board = board if isinstance(board, dict) else {}
    collections = _collections(board)
    if not collections:
        raise RuntimeError("not_found: the board has no Campaign the caller can read")
    widget = arguments.get("widget") or "trends"
    date_from, date_to = _window(arguments, board)
    saved = board.get("filters") if isinstance(board.get("filters"), dict) else {}
    common = {
        "collection_id": collections,
        "timezone": arguments.get("timezone"),
        "link_status": _link_status(arguments, board),
    }
    platform = arguments.get("platform") or saved.get("platform")
    if widget == "core_metrics":
        if not (date_from and date_to):
            raise ValueError("core-metrics needs --date-from and --date-to (the board saved none)")
        route = Route(
            "/monitor-collection-sets/report/widgets/core-metrics",
            {**common, "current_period_start": date_from, "current_period_end": date_to},
            version=1,
        )
    else:
        query = {
            **common,
            "date_from": date_from,
            "date_to": date_to,
            "platform": platform,
            "performance_as_of": "latest",
        }
        if widget in ("content", "creators"):
            query.update(
                page=arguments.get("page", 1),
                limit=arguments.get("page_size") or 50,
                search=arguments.get("search"),
                sort=arguments.get("sort"),
            )
        suffix = {"trends": "content-trends", "content": "content", "creators": "creators"}[widget]
        route = Route(f"/monitor-collection-sets/{suffix}", query)
    figures = await get(ctx, route)
    return {
        "board": {key: board.get(key) for key in ("id", "name", "campaign_type", "filters")},
        "widget": widget.replace("_", "-"),
        "collection_ids": collections,
        "data": figures,
    }


def specs() -> list[CommandSpec]:
    analytics = Domain.ANALYTICS
    return [
        read(
            EXECUTORS,
            analytics,
            "board",
            "list",
            summary=(
                "List the organization's analytics boards and those shared into it: name, type "
                "(ugc, tracking or mixed), Campaigns and saved filters. Every member reads them."
            ),
            properties={},
            execute=lambda ctx, a: get(
                ctx,
                Route(
                    BOARDS,
                    {"scope": "organization", "organization_id": require_organization(ctx)},
                    version=1,
                ),
            ),
            example="museoncli analytics board +list",
            output="The boards (a list).",
        ),
        read(
            EXECUTORS,
            analytics,
            "board",
            "get",
            summary=(
                "Read one analytics board: its Campaigns (with each one's collection and whether "
                "the caller can still read it) and saved filters (dates, platform, post scope, "
                "accounts, thresholds)."
            ),
            properties={"id": BOARD_ID},
            required=("id",),
            route=lambda a: Route(BOARDS + "/{id}", version=1),
            example="museoncli analytics board +get --id <board_id>",
        ),
        read(
            EXECUTORS,
            analytics,
            "board",
            "get-data",
            summary=(
                "Read a board's figures over all its Campaigns, as the board page does: daily "
                "trends (default), the period's core metrics, the posts, or the creators. Uses "
                "the board's saved dates, platform and post scope unless the flags override them."
            ),
            properties={
                "id": BOARD_ID,
                "widget": choice("What to read (default trends).", *WIDGETS),
                "date_from": {**D, "description": "Start day (default: the board's saved one)."},
                "date_to": {**D, "description": "End day (default: the board's saved one)."},
                "timezone": {**TZ, "description": "IANA timezone the days are read in."},
                "platform": choice("Only this platform.", *PLATFORMS),
                "scope": choice(
                    "approved: confirmed posts only; all: also those awaiting review "
                    "(default: the board's saved scope).",
                    "approved",
                    "all",
                ),
                "search": text("content / creators: title, handle or name contains this."),
                "sort": text("content / creators: a sort the board page offers, e.g. views_desc."),
                "page": PAGE,
                "page_size": PAGE_SIZE,
            },
            required=("id",),
            execute=_data,
            example=(
                "museoncli analytics board +get-data --id <board_id> --widget core-metrics "
                "--date-from 2026-11-01 --date-to 2026-11-12"
            ),
            output="data.board, data.widget, data.collection_ids and data.data (the figures).",
        ),
    ]
