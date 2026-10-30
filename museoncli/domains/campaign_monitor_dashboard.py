"""Campaign Dashboard reads: the same API routes the Museon web Dashboard reads.

Each command calls the route the Agency workbench or the Brand View calls for the
same figures, so what a login may read is decided by the server exactly as it is
in the browser: a Brand member reads the Brand View's figures, the Agency team
also reads settlement, activity, operations and audience, and a share-only or
unrelated caller reads nothing. A refusal is the server's ``not_found``.

``--id`` is the campaign as ``campaign-monitor +list`` returns it (its monitor
collection). Routes keyed by the UGC campaign resolve it first with one read of
``/ugc/collections/{id}/campaign``; Agency-wide routes read the caller's Agency
organization from ``/ugc/agency/me``.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from museoncli.domains._model import CommandSpec, Domain
from museoncli.domains._shared import _direct_output_schema
from museoncli.domains.hireaicreator import D, TZ, U, _load, _wire, arr, enum, obj
from museoncli.envelopes import direct_api_envelope
from museoncli.execution import CommandContext

Target = Literal["collection", "campaign", "agency", "workspace"]
Paging = Literal["offset", "cursor"] | None

S = {"type": "string", "minLength": 1, "maxLength": 300}
B = {"type": "boolean"}
PAGE = {"type": "integer", "minimum": 1}
PAGE_SIZE = {"type": "integer", "minimum": 1, "maximum": 100}
SCOPE = enum("all", "approved")
CAMPAIGN_ID = {**U, "description": "Campaign id as campaign-monitor +list returns it."}
DATE_FROM = {**D, "description": "Published on or after (YYYY-MM-DD)."}
DATE_TO = {**D, "description": "Published on or before (YYYY-MM-DD)."}
TIMEZONE = {**TZ, "description": "IANA timezone the dates are read in (default UTC)."}
PLATFORM = {**S, "description": "One platform, e.g. tiktok or instagram."}
SCOPE_DOC = {
    **SCOPE,
    "description": "UGC campaigns: approved reads confirmed posts only; all adds those awaiting review.",
}

POST_SORTS = tuple(
    f"{metric}-{direction}"
    for metric in (
        "published-at",
        "title",
        "views",
        "likes",
        "comments",
        "shares",
        "collects",
        "high-intent-engagement",
        "engagement-rate",
        "collect-like-ratio",
        "collect-view-ratio",
    )
    for direction in ("desc", "asc")
)

EXECUTORS: dict[str, Any] = {}


@dataclass(frozen=True, slots=True)
class Route:
    """One API read: its version, path template and the wire query it sends."""

    path: str
    query: dict[str, Any]
    version: int = 2


Build = Callable[[dict[str, Any]], Route]


def _read(
    resource: str,
    action: str,
    target: Target,
    properties: dict[str, Any],
    route: Build,
    *,
    summary: str,
    example: str,
    required: tuple[str, ...] = (),
    paging: Paging = None,
    flags: dict[str, str] | None = None,
    check: Callable[[dict[str, Any]], None] | None = None,
) -> CommandSpec:
    props = dict(properties)
    if target in ("collection", "campaign"):
        props = {"id": CAMPAIGN_ID, **props}
        required = ("id", *required)
    if paging == "offset":
        props.update(page=PAGE, page_size=PAGE_SIZE)
    elif paging == "cursor":
        props.update(cursor={**S, "maxLength": 2000}, page_size=PAGE_SIZE)
    schema = obj(props, required)
    name = f"{Domain.CAMPAIGN_MONITOR.value}.{resource}-{action}"
    aliases = flags or {}

    def add_arguments(parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--args-json")
        parser.add_argument("--args-file")
        for key, field in props.items():
            kind = field["type"]
            base = next(x for x in kind if x != "null") if isinstance(kind, list) else kind
            kwargs: dict[str, Any] = {"dest": key, "default": argparse.SUPPRESS}
            item = field["items"] if base == "array" else field
            if base == "boolean":
                kwargs["action"] = argparse.BooleanOptionalAction
            elif base == "array":
                kwargs["action"] = "append"
            elif base == "integer":
                kwargs["type"] = int
            if "enum" in item:
                kwargs["choices"] = [value for value in item["enum"] if value is not None]
            if field.get("description"):
                kwargs["help"] = field["description"]
            parser.add_argument(aliases.get(key, "--" + key.replace("_", "-")), **kwargs)

    def build(args: argparse.Namespace) -> dict[str, Any]:
        payload = _load(args, props, required)
        if check is not None:
            check(payload)
        return payload

    async def execute(ctx: CommandContext) -> dict[str, Any]:
        arguments = _wire(dict(ctx.arguments), schema)
        ids = await _resolve(ctx, target, arguments)
        query = dict(arguments)
        for key in ("id", "page", "page_size", "cursor"):
            query.pop(key, None)
        planned = route({**query, **ids})
        wire = {**planned.query}
        if paging == "offset":
            size = arguments.get("page_size") or 50
            wire.update(offset=(arguments.get("page", 1) - 1) * size, limit=size)
        elif paging == "cursor":
            wire.update(cursor=arguments.get("cursor"), limit=arguments.get("page_size") or 50)
        call = ctx.api_data_v2 if planned.version == 2 else ctx.api_data
        raw = await call(
            ctx.cfg,
            "GET",
            planned.path.format(**ids, **query),
            params={key: value for key, value in wire.items() if value is not None},
        )
        return direct_api_envelope(name, ctx.workspace_id, raw, site_url=ctx.cfg.site_url)

    EXECUTORS[name] = execute
    return CommandSpec(
        domain=Domain.CAMPAIGN_MONITOR,
        resource=resource,
        shortcut="+" + action,
        summary=summary,
        risk_level="read",
        execution="direct",
        adapter_tool_name=f"campaign_monitor_{resource.replace('-', '_')}_{action.replace('-', '_')}",
        input_schema=schema,
        output_schema=_direct_output_schema("Unmodified Museon API read model."),
        examples=[example],
        add_arguments=add_arguments,
        build_arguments=build,
    )


async def _resolve(
    ctx: CommandContext, target: Target, arguments: dict[str, Any]
) -> dict[str, Any]:
    """The path ids a route is addressed by, read from the server where needed."""
    if target == "collection":
        return {"collection_id": arguments["id"]}
    if target == "campaign":
        viewed = await ctx.api_data_v2(
            ctx.cfg, "GET", f"/ugc/collections/{arguments['id']}/campaign"
        )
        campaign_id = viewed.get("id") if isinstance(viewed, dict) else None
        if not campaign_id:
            raise RuntimeError("not_found: no UGC campaign stands for this campaign id")
        return {"collection_id": arguments["id"], "campaign_id": campaign_id}
    if target == "agency":
        view = await ctx.api_data_v2(ctx.cfg, "GET", "/ugc/agency/me")
        if not isinstance(view, dict) or not view.get("enabled") or not view.get("organization_id"):
            raise RuntimeError("forbidden: this login is not on an Agency team")
        return {"agency_id": view["organization_id"]}
    if not ctx.workspace_id:
        raise RuntimeError("missing_workspace")
    return {"workspace_id": ctx.workspace_id}


def _approved(arguments: dict[str, Any]) -> str | None:
    return "linked" if arguments.get("scope") == "approved" else None


def _window(arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        "date_from": arguments.get("date_from"),
        "date_to": arguments.get("date_to"),
        "all_time": arguments.get("all_time"),
        "timezone": arguments.get("timezone"),
        "platform": arguments.get("platform"),
    }


def _post_status(arguments: dict[str, Any]) -> dict[str, Any]:
    """The Content tab's scope and status, as the web Dashboard sends them."""
    approved, status = arguments.get("scope") == "approved", arguments.get("status")
    if approved and status in ("confirmation", "not_counted"):
        raise ValueError("approved posts are confirmed and counted: only --status review applies")
    return {
        "link_status": "linked"
        if approved
        else "excluded"
        if status == "not_counted"
        else "not_excluded",
        "awaiting": status if status in ("confirmation", "review") else None,
    }


def _check_post_status(payload: dict[str, Any]) -> None:
    if payload.get("scope") == "approved" and payload.get("status") in (
        "confirmation",
        "not-counted",
    ):
        raise ValueError("approved posts are confirmed and counted: only --status review applies")


WINDOW = {
    "date_from": DATE_FROM,
    "date_to": DATE_TO,
    "all_time": {**B, "description": "Every post ever published; ignores the dates."},
    "timezone": TIMEZONE,
    "platform": PLATFORM,
}


def specs() -> list[CommandSpec]:
    campaign = "/ugc/campaigns/{campaign_id}"
    agency_content = "/ugc/agency/campaigns/{campaign_id}"
    return [
        # -- what the Brand View and the Agency workbench both show ----------------
        _read(
            "campaign",
            "get",
            "collection",
            {},
            lambda a: Route("/ugc/collections/{collection_id}/campaign", {}),
            summary=(
                "Read a campaign's type (ugc or tracking), status, start date and UGC campaign "
                "identity, as its Dashboard header shows them."
            ),
            example="museoncli campaign-monitor campaign +get --id <campaign_id>",
        ),
        _read(
            "video",
            "list",
            "campaign",
            {
                **WINDOW,
                "scope": SCOPE_DOC,
                "status": {
                    **enum("confirmation", "review", "not-counted"),
                    "description": "What a post awaits, or the ones not counted.",
                },
                "creator_id": {**U, "description": "Only this UGC creator's posts."},
                "search": S,
                "sort": enum(*POST_SORTS),
            },
            lambda a: Route(
                agency_content + "/content",
                {
                    "source": "merged",
                    "date_field": "post_date",
                    **_window(a),
                    **_post_status(a),
                    "ugc_creator_id": a.get("creator_id"),
                    "search": a.get("search"),
                    "sort": a.get("sort"),
                },
            ),
            summary=(
                "List a UGC campaign's videos as its Content tab does: each creative once for its "
                "confirmed posts, and posts still awaiting confirmation or review. Filter by "
                "--status confirmation, review or not-counted. Tracking campaigns use +list-content."
            ),
            example=(
                "museoncli campaign-monitor video +list --id <campaign_id> --date-from 2026-10-01 "
                "--date-to 2026-10-28 --sort views-desc"
            ),
            paging="offset",
            check=_check_post_status,
        ),
        _read(
            "video",
            "get",
            "campaign",
            {
                "content_id": {**U, "description": "The post's content id from video +list."},
                "section": {
                    **enum("detail", "summary", "daily", "insights"),
                    "description": "detail (default), summary, daily metrics or platform insights.",
                },
                "scope": SCOPE_DOC,
            },
            lambda a: Route(
                agency_content
                + "/content/{content_id}/detail"
                + ("" if a.get("section") in (None, "detail") else "/" + a["section"]),
                {"link_status": _approved(a) or "not_excluded"},
            ),
            summary="Read one UGC post's detail, summary, daily metrics or insights, as its post drawer does.",
            example=(
                "museoncli campaign-monitor video +get --id <campaign_id> --content-id <content_id> "
                "--section daily"
            ),
            required=("content_id",),
        ),
        _read(
            "roster",
            "list",
            "campaign",
            {
                "date_from": DATE_FROM,
                "date_to": DATE_TO,
                "timezone": TIMEZONE,
                "platform": PLATFORM,
                "scope": SCOPE_DOC,
                "section": {
                    **enum("main", "removed"),
                    "description": "main (default): creators in the campaign; removed: those taken out.",
                },
                "search": S,
                "stage": arr(S, 0, 20),
                "basis": {**enum("post", "video"), "description": "Count posts or videos."},
                "sort": enum("views", "content-count", "avg-views", "engagement-rate"),
                "direction": enum("desc", "asc"),
            },
            lambda a: Route(
                campaign + "/roster",
                {
                    "scope": a.get("scope"),
                    "section": a.get("section"),
                    "date_from": a.get("date_from"),
                    "date_to": a.get("date_to"),
                    "timezone": a.get("timezone"),
                    "platform": a.get("platform"),
                    "q": a.get("search"),
                    "stage": a.get("stage"),
                    "basis": a.get("basis"),
                    "sort": a.get("sort"),
                    "direction": a.get("direction"),
                },
            ),
            summary=(
                "List a UGC campaign's creators as the By Creator tab does: one row per enrollment "
                "with its stage, tags and post figures."
            ),
            example="museoncli campaign-monitor roster +list --id <campaign_id> --sort views",
            paging="cursor",
        ),
        _read(
            "format",
            "list",
            "campaign",
            {**WINDOW, "scope": SCOPE_DOC},
            lambda a: Route(
                agency_content + "/format-performance", {**_window(a), "link_status": _approved(a)}
            ),
            summary="Read a UGC campaign's performance by Format (brief): posts, views and engagement per Format.",
            example="museoncli campaign-monitor format +list --id <campaign_id> --all-time",
        ),
        _read(
            "format-post",
            "list",
            "campaign",
            {
                **WINDOW,
                "scope": SCOPE_DOC,
                "brief_id": {**U, "description": "The Format from format +list."},
            },
            lambda a: Route(
                agency_content + "/format-performance/{brief_id}/posts",
                {**_window(a), "link_status": _approved(a)},
            ),
            summary="List the posts behind one Format's figures in format +list.",
            example="museoncli campaign-monitor format-post +list --id <campaign_id> --brief-id <brief_id>",
            required=("brief_id",),
            paging="offset",
        ),
        _read(
            "report",
            "get",
            "collection",
            {
                "widget": {
                    **enum("cumulative-views", "content-tiers", "creator-countries"),
                    "description": (
                        "cumulative-views: the long tail of views; content-tiers: posts by view tier; "
                        "creator-countries: views by creator audience country."
                    ),
                },
                "date_from": DATE_FROM,
                "date_to": DATE_TO,
                "timezone": TIMEZONE,
                "scope": SCOPE_DOC,
            },
            lambda a: Route(
                "/monitor-collections/{collection_id}/report/widgets/"
                + {
                    "cumulative_views": "cumulative-views",
                    "content_tiers": "content-tier-breakdown",
                    "creator_countries": "creator-country-distribution",
                }[a["widget"]],
                {
                    **(
                        {"date_from": a["date_from"], "date_to": a["date_to"]}
                        if a["widget"] == "cumulative_views"
                        else {
                            "current_period_start": a["date_from"],
                            "current_period_end": a["date_to"],
                        }
                    ),
                    "timezone": a.get("timezone"),
                    "link_status": _approved(a),
                },
                version=1,
            ),
            summary=(
                "Read one Analytics tab widget over a date window: cumulative views, content tiers "
                "or creator countries. Period-over-period core metrics are +get-period-performance."
            ),
            example=(
                "museoncli campaign-monitor report +get --id <campaign_id> --widget content-tiers "
                "--date-from 2026-10-01 --date-to 2026-10-28"
            ),
            required=("widget", "date_from", "date_to"),
        ),
        _read(
            "creator-tag",
            "list",
            "collection",
            {},
            lambda a: Route("/monitor-collections/{collection_id}/creator-tags", {}),
            summary="List the creator tags set on a campaign's accounts.",
            example="museoncli campaign-monitor creator-tag +list --id <campaign_id>",
        ),
        _read(
            "audience",
            "get",
            "campaign",
            {
                "by": {
                    **enum("day", "period"),
                    "description": (
                        "day: each trend day's audience (Brand View too); period: the audience map "
                        "and profile over the window (Agency team only)."
                    ),
                },
                "date_from": DATE_FROM,
                "date_to": DATE_TO,
                "platform": PLATFORM,
                "scope": SCOPE_DOC,
            },
            lambda a: Route(
                campaign
                + (
                    "/analytics/daily-audience"
                    if a.get("by") != "period"
                    else "/analytics/period-audience"
                ),
                {
                    "date_from": a["date_from"],
                    "date_to": a["date_to"],
                    "platform": a.get("platform"),
                    "link_status": _approved(a),
                },
            ),
            summary="Read a campaign's audience: by day as the trend tooltip shows it, or over the period.",
            example=(
                "museoncli campaign-monitor audience +get --id <campaign_id> --by period "
                "--date-from 2026-10-01 --date-to 2026-10-28"
            ),
            required=("date_from", "date_to"),
        ),
        _read(
            "payment",
            "list",
            "workspace",
            {
                "bucket": enum("pending-approval", "owed", "overdue", "sending", "paid"),
                "date_from": DATE_FROM,
                "date_to": DATE_TO,
                "search": S,
            },
            lambda a: Route(
                "/ugc/payments",
                {
                    "workspace_id": a["workspace_id"],
                    "bucket": a.get("bucket"),
                    "date_from": a.get("date_from"),
                    "date_to": a.get("date_to"),
                    "q": a.get("search"),
                },
            ),
            summary="List the selected workspace's creator payments, as its Payments page does.",
            example="museoncli campaign-monitor payment +list --bucket owed",
            paging="cursor",
        ),
        _read(
            "payment-summary",
            "get",
            "workspace",
            {"date_from": DATE_FROM, "date_to": DATE_TO},
            lambda a: Route(
                "/ugc/payments/summary",
                {
                    "workspace_id": a["workspace_id"],
                    "date_from": a.get("date_from"),
                    "date_to": a.get("date_to"),
                },
            ),
            summary="Read the selected workspace's payment totals, as the Payments page header shows them.",
            example="museoncli campaign-monitor payment-summary +get",
        ),
        # -- the Agency team's reads: settlement, operations, activity -------------
        _read(
            "settlement",
            "get",
            "campaign",
            {
                "date_from": {**D, "description": "Settlement period start (YYYY-MM-DD)."},
                "date_to": {**D, "description": "Settlement period end (YYYY-MM-DD)."},
                "timezone": TIMEZONE,
                "creator_id": {**U, "description": "One UGC creator's lines and evidence."},
            },
            lambda a: Route(
                campaign
                + ("/payouts/preview" if a.get("creator_id") else "/payouts/preview/summary"),
                {
                    "period_start": a["date_from"],
                    "period_end": a["date_to"],
                    "tz": a.get("timezone"),
                    "ugc_creator_id": [a["creator_id"]] if a.get("creator_id") else None,
                },
            ),
            summary=(
                "Read a UGC campaign's settlement for a period, as its Settlement tab does: every "
                "creator's figures, or one creator's lines with --creator-id. Agency team only."
            ),
            example=(
                "museoncli campaign-monitor settlement +get --id <campaign_id> "
                "--date-from 2026-10-01 --date-to 2026-10-31"
            ),
            required=("date_from", "date_to"),
        ),
        _read(
            "payout",
            "list",
            "campaign",
            {"status": enum("pending", "confirmed", "approved", "rejected")},
            lambda a: Route(campaign + "/payouts", {"status": a.get("status")}),
            summary="List a UGC campaign's settled payouts and their lines. Agency team only.",
            example="museoncli campaign-monitor payout +list --id <campaign_id> --status confirmed",
        ),
        _read(
            "activity",
            "list",
            "campaign",
            {"search": {**S, "description": "Only changes to creators whose name contains this."}},
            lambda a: Route(campaign + "/activity", {"q": a.get("search")}),
            summary="List a UGC campaign's activity log, newest first. Agency team only.",
            example="museoncli campaign-monitor activity +list --id <campaign_id>",
            paging="cursor",
        ),
        _read(
            "enrollment",
            "list",
            "campaign",
            {
                "status": enum(
                    "participating",
                    "pending",
                    "rejected",
                    "onboarding",
                    "active",
                    "paused",
                    "removed",
                ),
                "trial_only": B,
                "creator_id": {**U, "description": "One UGC creator's enrollment."},
                "search": S,
            },
            lambda a: Route(
                campaign + "/enrollments",
                {
                    "status": a.get("status"),
                    "trial_only": a.get("trial_only"),
                    "creator_id": a.get("creator_id"),
                    "q": a.get("search"),
                },
            ),
            summary=(
                "List a UGC campaign's enrollments with their stage, accounts, contract and Discord "
                "state, as the Operations tab does. Agency team only."
            ),
            example="museoncli campaign-monitor enrollment +list --id <campaign_id> --status participating",
            paging="cursor",
        ),
        _read(
            "assignment",
            "list",
            "campaign",
            {"status": enum("assigned", "in-progress", "delivered", "withdrawn")},
            lambda a: Route(campaign + "/assignments", {"status": a.get("status")}),
            summary="List a UGC campaign's brief assignments and what is due. Agency team only.",
            example="museoncli campaign-monitor assignment +list --id <campaign_id> --status assigned",
            paging="cursor",
        ),
        _read(
            "creator-check",
            "get",
            "campaign",
            {},
            lambda a: Route(campaign + "/creator-checks/summary", {}),
            summary=(
                "Count a UGC campaign's creators per check: can't track, not set up, not in Discord, "
                "quiet, not healthy. Agency team only."
            ),
            example="museoncli campaign-monitor creator-check +get --id <campaign_id>",
        ),
        _read(
            "creator-check",
            "list",
            "campaign",
            {"kind": enum("cant-track", "not-set-up", "not-in-discord", "quiet", "not-healthy")},
            lambda a: Route(campaign + "/creator-checks", {"kind": a["kind"]}),
            summary="List the creators one check holds for. Agency team only.",
            example="museoncli campaign-monitor creator-check +list --id <campaign_id> --kind quiet",
            required=("kind",),
            paging="cursor",
        ),
        _read(
            "agency-campaign",
            "list",
            "agency",
            {
                "search": S,
                "campaign_type": enum("ugc", "tracking"),
                "archived": B,
                "with_progress": {
                    **B,
                    "description": "Read each campaign's delivery progress instead of its settings.",
                },
            },
            lambda a: Route(
                "/ugc/agency/{agency_id}/campaigns"
                + ("/progress" if a.get("with_progress") else ""),
                {"archived": a.get("archived")}
                if a.get("with_progress")
                else {
                    "q": a.get("search"),
                    "campaign_type": a.get("campaign_type"),
                    "archived": a.get("archived"),
                },
            ),
            summary=(
                "List every campaign the Agency runs across its Brands, or their delivery progress "
                "with --with-progress. Agency team only."
            ),
            example="museoncli campaign-monitor agency-campaign +list --campaign-type ugc",
            paging="cursor",
        ),
        _read(
            "agency-analytics",
            "get",
            "agency",
            {
                **WINDOW,
                "scope": SCOPE_DOC,
                "date_basis": {
                    **enum("upload", "view"),
                    "description": "upload: posts published in the window; view: views gained in it.",
                },
            },
            lambda a: Route(
                "/ugc/agency/{agency_id}/analytics",
                {**_window(a), "date_basis": a.get("date_basis"), "link_status": _approved(a)},
            ),
            summary=(
                "Read the Agency's analytics over all its UGC campaigns: views, engagement, creators, "
                "posts and spend. Agency team only."
            ),
            example="museoncli campaign-monitor agency-analytics +get --date-from 2026-10-01 --date-to 2026-10-28",
        ),
    ]
