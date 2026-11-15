"""Campaign Dashboard reads: the tabs the web shows for one Campaign, and the money pages.

Each command calls the route the web calls for the same figures, so what a login
may read is decided by the server exactly as it is in the browser, in whichever
organization the command acts in: the Campaign's own organization by role (owner,
admin, the Campaign's operators, members read figures only), a Campaign shared in by
the share's tier (the operator tier also reads settlement, payouts, enrollments and
creator checks), and an unrelated caller nothing. A refusal is the server's
``not_found``.

``--campaign-id`` is the Campaign's id as ``campaign +list`` returns it, for both kinds
(UGC and tracking). Organization-wide routes are addressed by the organization the
command acts in (``X-Organization-Id``: ``museoncli org select`` or
``--organization-id``).

Two reads of the UGC Operations tab live in ``ugc`` beside the writes they feed
(``ugc assignment +list``, ``ugc creator-check``); they are declared here because
they read the same routes the same way.
"""

from __future__ import annotations

from typing import Any

from museoncli.domains._model import CommandSpec, Domain
from museoncli.domains._org_reads import Route, read
from museoncli.domains.hireaicreator import D, TZ, U, arr, enum

S = {"type": "string", "minLength": 1, "maxLength": 300}
B = {"type": "boolean"}
SCOPE = enum("all", "approved")
CAMPAIGN_ID = {**U, "description": "The Campaign's ID, from campaign +list."}
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

CAMPAIGN = "/ugc/campaigns/{campaign_id}"
AGENCY_CONTENT = "/ugc/agency/campaigns/{campaign_id}"
AGENCY = "/ugc/agency/{organization_id}"


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

#: The Format and organization analytics reads take an explicit window or all time,
#: never a guessed default (the service answers `analytics_date_range_required`).
REQUIRED_WINDOW = {
    **WINDOW,
    "date_from": {
        **D,
        "description": "Published on or after (YYYY-MM-DD). Required with --date-to unless --all-time.",
    },
    "date_to": {
        **D,
        "description": "Published on or before (YYYY-MM-DD). Required with --date-from unless --all-time.",
    },
    "all_time": {
        **B,
        "description": "Every post ever published, instead of --date-from/--date-to.",
    },
}


def _check_window(payload: dict[str, Any]) -> None:
    """Both dates, or --all-time: say so before the request instead of the service's 422."""
    dated = [payload.get(key) is not None for key in ("date_from", "date_to")]
    if payload.get("all_time") is True:
        if any(dated):
            raise ValueError(
                "--all-time reads every post ever published: drop --date-from/--date-to, "
                "or drop --all-time to read a window"
            )
        return
    if not all(dated):
        raise ValueError(
            "this read needs a window: --date-from and --date-to (YYYY-MM-DD, both), "
            "or --all-time for every post ever published"
        )


def _campaign_read(
    resource: str,
    action: str,
    properties: dict[str, Any],
    route: Any,
    *,
    summary: str,
    example: str,
    required: tuple[str, ...] = (),
    domain: Domain = Domain.CAMPAIGN,
    **options: Any,
) -> CommandSpec:
    """A read of one Campaign, addressed by --campaign-id."""
    return read(
        EXECUTORS,
        domain,
        resource,
        action,
        summary=summary,
        properties={"campaign_id": CAMPAIGN_ID, **properties},
        required=("campaign_id", *required),
        route=route,
        example=example,
        **options,
    )


def specs() -> list[CommandSpec]:
    return [
        # -- the Dashboard tabs ----------------------------------------------------
        _campaign_read(
            "video",
            "list",
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
                AGENCY_CONTENT + "/content",
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
                "--status confirmation, review or not-counted. A tracking Campaign's posts are "
                "campaign content +list."
            ),
            example=(
                "museoncli campaign video +list --campaign-id <campaign_id> --date-from 2026-10-01 "
                "--date-to 2026-10-28 --sort views-desc"
            ),
            paging="offset",
            check=_check_post_status,
        ),
        _campaign_read(
            "video",
            "get",
            {
                "content_id": {**U, "description": "The post's content id from video +list."},
                "section": {
                    **enum("detail", "summary", "daily", "insights"),
                    "description": "detail (default), summary, daily metrics or platform insights.",
                },
                "scope": SCOPE_DOC,
            },
            lambda a: Route(
                AGENCY_CONTENT
                + "/content/{content_id}/detail"
                + ("" if a.get("section") in (None, "detail") else "/" + a["section"]),
                {"link_status": _approved(a) or "not_excluded"},
            ),
            summary="Read one UGC post's detail, summary, daily metrics or insights, as its post drawer does.",
            example=(
                "museoncli campaign video +get --campaign-id <campaign_id> --content-id <content_id> "
                "--section daily"
            ),
            required=("content_id",),
        ),
        _campaign_read(
            "roster",
            "list",
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
                CAMPAIGN + "/roster",
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
            example="museoncli campaign roster +list --campaign-id <campaign_id> --sort views",
            paging="cursor",
        ),
        _campaign_read(
            "format",
            "list",
            {**REQUIRED_WINDOW, "scope": SCOPE_DOC},
            lambda a: Route(
                AGENCY_CONTENT + "/format-performance", {**_window(a), "link_status": _approved(a)}
            ),
            summary=(
                "Read a UGC campaign's performance by Format (brief): posts, views and engagement "
                "per Format. Needs --date-from and --date-to, or --all-time."
            ),
            example="museoncli campaign format +list --campaign-id <campaign_id> --all-time",
            check=_check_window,
        ),
        _campaign_read(
            "format-post",
            "list",
            {
                **REQUIRED_WINDOW,
                "scope": SCOPE_DOC,
                "brief_id": {**U, "description": "The Format from format +list."},
            },
            lambda a: Route(
                AGENCY_CONTENT + "/format-performance/{brief_id}/posts",
                {**_window(a), "link_status": _approved(a)},
            ),
            summary=(
                "List the posts behind one Format's figures in format +list, over the same "
                "window: --date-from and --date-to, or --all-time."
            ),
            example=(
                "museoncli campaign format-post +list --campaign-id <campaign_id> "
                "--brief-id <brief_id> --all-time"
            ),
            required=("brief_id",),
            paging="offset",
            check=_check_window,
        ),
        _campaign_read(
            "report",
            "get",
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
                "/monitor-collections/{campaign_id}/report/widgets/"
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
                "museoncli campaign report +get --campaign-id <campaign_id> --widget content-tiers "
                "--date-from 2026-10-01 --date-to 2026-10-28"
            ),
            required=("widget", "date_from", "date_to"),
        ),
        _campaign_read(
            "creator-tag",
            "list",
            {},
            lambda a: Route("/monitor-collections/{campaign_id}/creator-tags", {}),
            summary="List the creator tags set on a campaign's accounts.",
            example="museoncli campaign creator-tag +list --campaign-id <campaign_id>",
        ),
        _campaign_read(
            "audience",
            "get",
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
                CAMPAIGN
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
                "museoncli campaign audience +get --campaign-id <campaign_id> --by period "
                "--date-from 2026-10-01 --date-to 2026-10-28"
            ),
            required=("date_from", "date_to"),
        ),
        # -- money: the organization's payments, a Campaign's settlement --------
        read(
            EXECUTORS,
            Domain.CAMPAIGN,
            "payment",
            "list",
            summary=(
                "List the organization's creator payments, as the Payments page does. The "
                "operating organization's team (owner, admin, operators on their Campaigns) "
                "only, as on the web."
            ),
            properties={
                "bucket": enum("pending-approval", "owed", "overdue", "sending", "paid"),
                "date_from": DATE_FROM,
                "date_to": DATE_TO,
                "search": S,
            },
            route=lambda a: Route(
                "/ugc/payments",
                {
                    "bucket": a.get("bucket"),
                    "date_from": a.get("date_from"),
                    "date_to": a.get("date_to"),
                    "q": a.get("search"),
                },
            ),
            example="museoncli campaign payment +list --bucket owed",
            paging="cursor",
        ),
        read(
            EXECUTORS,
            Domain.CAMPAIGN,
            "payment-summary",
            "get",
            summary=(
                "Read the organization's payment totals, as the Payments header shows them. The "
                "operating organization's team only, as on the web."
            ),
            properties={"date_from": DATE_FROM, "date_to": DATE_TO},
            route=lambda a: Route(
                "/ugc/payments/summary",
                {"date_from": a.get("date_from"), "date_to": a.get("date_to")},
            ),
            example="museoncli campaign payment-summary +get",
        ),
        _campaign_read(
            "settlement",
            "get",
            {
                "date_from": {**D, "description": "Settlement period start (YYYY-MM-DD)."},
                "date_to": {**D, "description": "Settlement period end (YYYY-MM-DD)."},
                "timezone": TIMEZONE,
                "creator_id": {**U, "description": "One UGC creator's lines and evidence."},
            },
            lambda a: Route(
                CAMPAIGN
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
                "creator's figures, or one creator's lines with --creator-id. The Campaign's "
                "team: owner, admin and its operators, or a share's operator tier."
            ),
            example=(
                "museoncli campaign settlement +get --campaign-id <campaign_id> "
                "--date-from 2026-10-01 --date-to 2026-10-31"
            ),
            required=("date_from", "date_to"),
        ),
        _campaign_read(
            "payout",
            "list",
            {"status": enum("pending", "confirmed", "approved", "rejected")},
            lambda a: Route(CAMPAIGN + "/payouts", {"status": a.get("status")}),
            summary=(
                "List a UGC campaign's settled payouts and their lines. The Campaign's team: "
                "owner, admin and its operators, or a share's operator tier."
            ),
            example="museoncli campaign payout +list --campaign-id <campaign_id> --status confirmed",
        ),
        _campaign_read(
            "activity",
            "list",
            {"search": {**S, "description": "Only changes to creators whose name contains this."}},
            lambda a: Route(CAMPAIGN + "/activity", {"q": a.get("search")}),
            summary=(
                "List a UGC campaign's activity log, newest first. The owning organization's "
                "team only (a share does not open it, as on the web)."
            ),
            example="museoncli campaign activity +list --campaign-id <campaign_id>",
            paging="cursor",
        ),
        read(
            EXECUTORS,
            Domain.CAMPAIGN,
            "analytics",
            "get",
            summary=(
                "Read the organization's analytics over all its UGC campaigns: views, engagement, "
                "creators, posts and spend, over --date-from/--date-to or --all-time. The "
                "operating organization's team only, as on the web."
            ),
            properties={
                **REQUIRED_WINDOW,
                "scope": SCOPE_DOC,
                "date_basis": {
                    **enum("upload", "view"),
                    "description": "upload: posts published in the window; view: views gained in it.",
                },
            },
            route=lambda a: Route(
                AGENCY + "/analytics",
                {**_window(a), "date_basis": a.get("date_basis"), "link_status": _approved(a)},
            ),
            example=(
                "museoncli campaign analytics +get --date-from 2026-10-01 --date-to 2026-10-28"
            ),
            check=_check_window,
        ),
        # -- the UGC Operations tab's reads, in ugc beside their writes ----------
        _campaign_read(
            "assignment",
            "list",
            {"status": enum("assigned", "in-progress", "delivered", "withdrawn")},
            lambda a: Route(CAMPAIGN + "/assignments", {"status": a.get("status")}),
            summary=(
                "List a UGC campaign's brief assignments and what is due. The owning "
                "organization's team only (a share does not open it, as on the web)."
            ),
            example="museoncli ugc assignment +list --campaign-id <campaign_id> --status assigned",
            paging="cursor",
            domain=Domain.UGC,
        ),
        _campaign_read(
            "creator-check",
            "get",
            {},
            lambda a: Route(CAMPAIGN + "/creator-checks/summary", {}),
            summary=(
                "Count a UGC campaign's creators per check: can't track, not set up, not in Discord, "
                "quiet, not healthy. The Campaign's team, or a share's operator tier."
            ),
            example="museoncli ugc creator-check +get --campaign-id <campaign_id>",
            domain=Domain.UGC,
        ),
        _campaign_read(
            "creator-check",
            "list",
            {"kind": enum("cant-track", "not-set-up", "not-in-discord", "quiet", "not-healthy")},
            lambda a: Route(CAMPAIGN + "/creator-checks", {"kind": a["kind"]}),
            summary=(
                "List the creators one check holds for. The Campaign's team, or a share's "
                "operator tier."
            ),
            example="museoncli ugc creator-check +list --campaign-id <campaign_id> --kind quiet",
            required=("kind",),
            paging="cursor",
            domain=Domain.UGC,
        ),
    ]
