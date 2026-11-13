"""Analytics board writes: create, rename and re-filter, change the data source, delete.

The same routes the web's 分析看板 (``/analytics``) calls: ``/api/v1/analytics-dashboards``.
A board is made in the selected organization (``organization_id``, as the web's
new interface makes it) and reads 1 to 10 Campaigns of one type, or UGC and
content tracking Campaigns together (``mixed``). Its filters are the layout it
opens with: dates, platform, post scope, accounts, metric thresholds, the
metrics shown and the trend chart's daily or running-total reading.

Who may: whoever edits the board (owner, admin, or an operator who holds every
Campaign on it); a member reads only. The server decides.

Not here: the public share link. The server opens and closes it for a signed-in
person only (an API key is refused), so it stays in the browser.
"""

from __future__ import annotations

import argparse
from typing import Any

from museoncli.domains._model import CommandSpec, Domain
from museoncli.domains._shared import _direct_output_schema, dekebab, kebab_choices
from museoncli.domains._writes import (
    DRY_RUN,
    add_confirm,
    add_dry_run,
    ask_first,
    ask_then_yes,
    changes,
    previewing,
    require_organization,
    schema,
    uuid_arg,
    uuid_property,
    with_notes,
)
from museoncli.execution import CommandContext, compact_params

CAMPAIGN_TYPES = [
    "tracking",
    "ugc",
    "influencer",
    "ads",
    "product_seeding",
    "pvp",
    "sound_promotion",
    "posting_only",
    "media_sourcing",
    "mixed",
]
PLATFORMS = ["tiktok", "instagram", "youtube", "facebook"]
ALL_PLATFORMS = "all"
POST_SCOPES = ["all", "approved"]
CHART_MODES = ["daily", "total"]
METRICS = [
    "views",
    "avg_views",
    "likes",
    "comments",
    "shares",
    "collects",
    "high_intent_engagement",
    "high_intent_rate",
    "engagement_rate",
    "collect_like_ratio",
    "collect_view_ratio",
]
MAX_CAMPAIGNS = 10
NONE = "none"
FILTER_FIELDS = [
    "date_from",
    "date_to",
    "platform",
    "post_scope",
    "accounts",
    "thresholds",
    "metrics",
    "chart_mode",
]
DEFAULT_FILTERS: dict[str, Any] = {
    "date_from": None,
    "date_to": None,
    "platform": None,
    "post_scope": "all",
    "accounts": [],
    "thresholds": {},
    "metrics": [],
    "chart_mode": "daily",
}


def _path(board_id: str) -> str:
    return f"/analytics-dashboards/{board_id}"


async def _board(ctx: CommandContext, board_id: str) -> dict[str, Any]:
    board = await ctx.api_data(ctx.cfg, "GET", _path(board_id))
    return board if isinstance(board, dict) else {}


def _summary(board: dict[str, Any]) -> dict[str, Any]:
    campaigns = board.get("campaigns") if isinstance(board.get("campaigns"), list) else []
    return {
        "id": board.get("id"),
        "name": board.get("name"),
        "campaign_type": board.get("campaign_type"),
        "campaigns": [
            {key: item.get(key) for key in ("id", "name", "campaign_type", "available")}
            for item in campaigns
            if isinstance(item, dict)
        ],
        "is_public": board.get("is_public"),
    }


def _current_filters(board: dict[str, Any]) -> dict[str, Any]:
    stored = board.get("filters") if isinstance(board.get("filters"), dict) else {}
    return {field: stored.get(field, DEFAULT_FILTERS[field]) for field in FILTER_FIELDS}


# -- executors ---------------------------------------------------------------


async def _execute_create(ctx: CommandContext) -> Any:
    args = ctx.arguments
    body = {
        "name": args["name"],
        "campaign_type": args["campaign_type"],
        "campaign_ids": args["campaign_ids"],
        "organization_id": require_organization(ctx),
        **({"filters": {**DEFAULT_FILTERS, **args["filters"]}} if args.get("filters") else {}),
    }
    if args.get("dry_run"):
        return {"dry_run": True, "board": body}, [], [ask_first("the board's name and Campaigns")]
    board = await ctx.api_data(ctx.cfg, "POST", "/analytics-dashboards", json_body=body)
    return board, [], []


async def _execute_update(ctx: CommandContext) -> Any:
    args = ctx.arguments
    board = await _board(ctx, args["id"])
    before = {"name": board.get("name"), **_current_filters(board)}
    edits = args.get("filters") or {}
    filters = {**_current_filters(board), **edits}
    after = {"name": args.get("name") or board.get("name"), **filters}
    diff = changes(before, after, ["name", *FILTER_FIELDS])
    data: dict[str, Any] = {
        "dry_run": bool(args.get("dry_run")),
        "board": _summary(board),
        "changes": diff,
    }
    if not diff:
        return data, ["Nothing differs from the board as saved; nothing was written."], []
    if args.get("dry_run"):
        return data, [], [ask_first("these changes")]
    body = compact_params(
        {"name": args.get("name"), "filters": filters if edits else None}
    )
    data["board"] = await ctx.api_data(ctx.cfg, "PATCH", _path(args["id"]), json_body=body)
    return data, [], []


async def _execute_set_source(ctx: CommandContext) -> Any:
    args = ctx.arguments
    board = await _board(ctx, args["id"])
    current = _summary(board)
    before_ids = [item.get("id") for item in current["campaigns"]]
    data: dict[str, Any] = {
        "dry_run": bool(args.get("dry_run")),
        "board": current,
        "campaign_type": {"before": board.get("campaign_type"), "after": args["campaign_type"]},
        "campaigns_added": [cid for cid in args["campaign_ids"] if cid not in before_ids],
        "campaigns_removed": [cid for cid in before_ids if cid not in args["campaign_ids"]],
    }
    if (
        not data["campaigns_added"]
        and not data["campaigns_removed"]
        and board.get("campaign_type") == args["campaign_type"]
    ):
        return data, ["The board already reads exactly these Campaigns; nothing was written."], []
    if args.get("dry_run"):
        return data, [], [ask_first("which Campaigns the board would read")]
    data["board"] = await ctx.api_data(
        ctx.cfg,
        "PUT",
        f"{_path(args['id'])}/data-source",
        json_body={"campaign_type": args["campaign_type"], "campaign_ids": args["campaign_ids"]},
    )
    return data, [], []


async def _execute_delete(ctx: CommandContext) -> Any:
    args = ctx.arguments
    board = await _board(ctx, args["id"])
    data: dict[str, Any] = {"dry_run": bool(args.get("dry_run")), "board": _summary(board)}
    warnings = (
        ["The board has a public share link; deleting the board ends it."]
        if board.get("is_public")
        else []
    )
    if args.get("dry_run"):
        return data, warnings, [ask_then_yes("which board would be deleted")]
    await ctx.api_data(ctx.cfg, "DELETE", _path(args["id"]))
    data["deleted"] = True
    return data, [], []


# -- arguments ---------------------------------------------------------------


def _add_filter_arguments(parser: argparse.ArgumentParser, *, clearable: bool) -> None:
    parser.add_argument("--date-from")
    parser.add_argument("--date-to")
    platforms = [*PLATFORMS, ALL_PLATFORMS] if clearable else PLATFORMS
    parser.add_argument("--platform", choices=platforms)
    parser.add_argument("--post-scope", choices=POST_SCOPES)
    parser.add_argument("--account-id", action="append", dest="account_ids")
    parser.add_argument("--metric", action="append", dest="metrics")
    parser.add_argument("--threshold", action="append", dest="thresholds")
    parser.add_argument("--chart-mode", choices=CHART_MODES)


def _optional_text(value: str | None) -> str | None:
    return None if value is None or value.strip().lower() == NONE else value


def _thresholds(values: list[str]) -> dict[str, float]:
    found: dict[str, float] = {}
    for value in values:
        key, separator, number = value.partition("=")
        if not separator:
            raise ValueError(f"--threshold takes METRIC-min=N or METRIC-max=N, got {value!r}.")
        try:
            found[dekebab(key.strip()) or ""] = float(number)
        except ValueError:
            raise ValueError(f"--threshold {value!r}: {number!r} is not a number.") from None
    return found


def _is_none(values: list[str] | None) -> bool:
    return values == [NONE]


def _filter_edits(args: argparse.Namespace) -> dict[str, Any]:
    """Only the filters passed; ``none`` (or ``--platform all``) clears one."""
    edits: dict[str, Any] = {}
    for field in ("date_from", "date_to"):
        value = getattr(args, field)
        if value is not None:
            edits[field] = _optional_text(value)
    if args.platform is not None:
        edits["platform"] = None if args.platform == ALL_PLATFORMS else args.platform
    if args.post_scope is not None:
        edits["post_scope"] = args.post_scope
    if args.chart_mode is not None:
        edits["chart_mode"] = args.chart_mode
    if args.account_ids is not None:
        edits["accounts"] = (
            [] if _is_none(args.account_ids)
            else [uuid_arg(value, flag="--account-id") for value in args.account_ids]
        )
    if args.metrics is not None:
        if _is_none(args.metrics):
            edits["metrics"] = []
        else:
            metrics = [dekebab(value) for value in args.metrics]
            unknown = [value for value in metrics if value not in METRICS]
            if unknown:
                raise ValueError(
                    f"--metric {unknown[0]!r} is not a board metric; use one of "
                    + ", ".join(kebab_choices(METRICS))
                    + "."
                )
            edits["metrics"] = metrics
    if args.thresholds is not None:
        edits["thresholds"] = {} if _is_none(args.thresholds) else _thresholds(args.thresholds)
    return edits


def _campaign_ids(args: argparse.Namespace) -> list[str]:
    ids = list(dict.fromkeys(uuid_arg(value, flag="--campaign-id") for value in args.campaign_ids))
    if not 1 <= len(ids) <= MAX_CAMPAIGNS:
        raise ValueError(f"Pick 1 to {MAX_CAMPAIGNS} Campaigns (--campaign-id, repeated).")
    return ids


def _add_create_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--name", required=True)
    parser.add_argument("--campaign-id", action="append", dest="campaign_ids", required=True)
    parser.add_argument("--campaign-type", choices=kebab_choices(CAMPAIGN_TYPES), required=True)
    _add_filter_arguments(parser, clearable=False)
    add_dry_run(parser)


def _name(value: str) -> str:
    cleaned = value.strip()
    if not 1 <= len(cleaned) <= 80:
        raise ValueError("--name must be 1 to 80 characters.")
    return cleaned


def _build_create_arguments(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "name": _name(args.name),
        "campaign_ids": _campaign_ids(args),
        "campaign_type": dekebab(args.campaign_type),
        "filters": _filter_edits(args),
        "dry_run": bool(args.dry_run),
    }


def _add_update_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--id", required=True)
    parser.add_argument("--name")
    _add_filter_arguments(parser, clearable=True)
    add_dry_run(parser)


def _build_update_arguments(args: argparse.Namespace) -> dict[str, Any]:
    filters = _filter_edits(args)
    name = _name(args.name) if args.name is not None else None
    if name is None and not filters:
        raise ValueError(
            "Pass --name or at least one filter (--date-from, --date-to, --platform, "
            "--post-scope, --account-id, --metric, --threshold, --chart-mode)."
        )
    return compact_params(
        {
            "id": uuid_arg(args.id, flag="--id"),
            "name": name,
            "filters": filters,
            "dry_run": bool(args.dry_run),
        }
    )


def _add_set_source_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--id", required=True)
    parser.add_argument("--campaign-id", action="append", dest="campaign_ids", required=True)
    parser.add_argument("--campaign-type", choices=kebab_choices(CAMPAIGN_TYPES), required=True)
    add_dry_run(parser)


def _build_set_source_arguments(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "id": uuid_arg(args.id, flag="--id"),
        "campaign_ids": _campaign_ids(args),
        "campaign_type": dekebab(args.campaign_type),
        "dry_run": bool(args.dry_run),
    }


def _add_delete_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--id", required=True)
    add_confirm(parser)


def _build_delete_arguments(args: argparse.Namespace) -> dict[str, Any]:
    return {"id": uuid_arg(args.id, flag="--id"), "dry_run": previewing(args)}


# -- schemas -----------------------------------------------------------------

_BOARD_ID = uuid_property("Board ID (the id a board read or +create returned).")
_CAMPAIGN_IDS = {
    "type": "array",
    "items": {"type": "string", "format": "uuid"},
    "minItems": 1,
    "maxItems": MAX_CAMPAIGNS,
    "description": (
        "The Campaigns the board reads (marketing campaign ids, as ugc campaign +list "
        "returns them), 1 to 10."
    ),
}
_CAMPAIGN_TYPE = {
    "type": "string",
    "enum": kebab_choices(CAMPAIGN_TYPES),
    "description": "The Campaigns' one type; mixed for UGC and content tracking Campaigns together.",
}
_FILTERS = {
    "type": "object",
    "description": (
        "The filters the board opens with. Only the ones passed change; none clears a date, "
        "the accounts, metrics or thresholds, and --platform all clears the platform."
    ),
    "properties": {
        "date_from": {"type": ["string", "null"], "format": "date"},
        "date_to": {"type": ["string", "null"], "format": "date"},
        "platform": {"type": ["string", "null"], "enum": [*PLATFORMS, None]},
        "post_scope": {
            "type": "string",
            "enum": POST_SCOPES,
            "description": "approved shows confirmed posts only (UGC and mixed boards).",
        },
        "accounts": {"type": "array", "items": {"type": "string", "format": "uuid"}, "maxItems": 50},
        "thresholds": {
            "type": "object",
            "description": "METRIC_min / METRIC_max floors and ceilings, e.g. views_min: 1000.",
        },
        "metrics": {"type": "array", "items": {"type": "string"}, "maxItems": 20},
        "chart_mode": {
            "type": "string",
            "enum": CHART_MODES,
            "description": "The trend chart plots each day, or the running total.",
        },
    },
}
_ROLE = (
    " Needs edit rights on the board (owner or admin; an operator who holds its Campaigns); "
    "a member is refused."
)


def specs() -> list[CommandSpec]:
    domain = Domain.ANALYTICS
    board = "66666666-6666-4666-8666-666666666666"
    campaign = "11111111-1111-4111-8111-111111111111"
    other = "22222222-2222-4222-8222-222222222222"
    write = {
        "risk_level": "write",
        "execution": "direct",
        "supports_dry_run": True,
        "dry_run_reads_server": True,
    }
    return [
        CommandSpec(
            domain=domain,
            resource="board",
            shortcut="+create",
            summary=(
                "Create a multi-Campaign analytics board in the selected organization: a name, "
                "1 to 10 Campaigns of one type (mixed for UGC and tracking together) and, "
                "optionally, the filters it opens with. --dry-run shows the board without "
                "creating it." + _ROLE
            ),
            adapter_tool_name="analytics_board_create",
            input_schema=schema(
                {
                    "name": {"type": "string", "minLength": 1, "maxLength": 80},
                    "campaign_ids": _CAMPAIGN_IDS,
                    "campaign_type": _CAMPAIGN_TYPE,
                    "filters": _FILTERS,
                    "dry_run": DRY_RUN,
                },
                ["name", "campaign_ids", "campaign_type"],
            ),
            output_schema=_direct_output_schema("The board as saved (id, name, campaigns, filters)."),
            examples=[
                f'museoncli analytics board +create --name "Q4 UGC" --campaign-type ugc '
                f"--campaign-id {campaign} --campaign-id {other} --post-scope approved --dry-run"
            ],
            add_arguments=_add_create_arguments,
            build_arguments=_build_create_arguments,
            **write,  # type: ignore[arg-type]
        ),
        CommandSpec(
            domain=domain,
            resource="board",
            shortcut="+update",
            summary=(
                "Rename a board or change the filters it opens with (dates, platform, post scope, "
                "accounts, thresholds, metrics, chart mode); filters not passed keep their value. "
                "--dry-run returns the changes without writing." + _ROLE
            ),
            adapter_tool_name="analytics_board_update",
            input_schema=schema(
                {
                    "id": _BOARD_ID,
                    "name": {"type": "string", "minLength": 1, "maxLength": 80},
                    "filters": _FILTERS,
                    "dry_run": DRY_RUN,
                },
                ["id"],
            ),
            output_schema=_direct_output_schema("board and changes (field, before, after)."),
            examples=[
                f"museoncli analytics board +update --id {board} --date-from 2026-11-01 "
                "--metric views --metric engagement-rate --threshold views-min=1000 --dry-run"
            ],
            add_arguments=_add_update_arguments,
            build_arguments=_build_update_arguments,
            **write,  # type: ignore[arg-type]
        ),
        CommandSpec(
            domain=domain,
            resource="board",
            shortcut="+set-source",
            summary=(
                "Replace the Campaigns a board reads (its data source) and their type. "
                "--dry-run returns the Campaigns added and removed without writing." + _ROLE
            ),
            adapter_tool_name="analytics_board_set_source",
            input_schema=schema(
                {
                    "id": _BOARD_ID,
                    "campaign_ids": _CAMPAIGN_IDS,
                    "campaign_type": _CAMPAIGN_TYPE,
                    "dry_run": DRY_RUN,
                },
                ["id", "campaign_ids", "campaign_type"],
            ),
            output_schema=_direct_output_schema(
                "board, campaign_type before/after, campaigns_added, campaigns_removed."
            ),
            examples=[
                f"museoncli analytics board +set-source --id {board} --campaign-type mixed "
                f"--campaign-id {campaign} --campaign-id {other} --dry-run"
            ],
            add_arguments=_add_set_source_arguments,
            build_arguments=_build_set_source_arguments,
            **write,  # type: ignore[arg-type]
        ),
        CommandSpec(
            domain=domain,
            resource="board",
            shortcut="+delete",
            summary=(
                "Delete a board (its share link ends with it); the Campaigns and their data stay. "
                "Without --yes it is refused with a preview of the board it would delete." + _ROLE
            ),
            adapter_tool_name="analytics_board_delete",
            input_schema=schema({"id": _BOARD_ID, "dry_run": DRY_RUN}, ["id"]),
            output_schema=_direct_output_schema("board, and deleted: true once it is gone."),
            examples=[f"museoncli analytics board +delete --id {board} --yes"],
            add_arguments=_add_delete_arguments,
            build_arguments=_build_delete_arguments,
            risk_level="destructive",
            requires_confirmation=True,
            execution="direct",
            supports_dry_run=True,
            dry_run_reads_server=True,
        ),
    ]


EXECUTORS = {
    "analytics.board-create": with_notes(_execute_create),
    "analytics.board-update": with_notes(_execute_update),
    "analytics.board-set-source": with_notes(_execute_set_source),
    "analytics.board-delete": with_notes(_execute_delete),
}
