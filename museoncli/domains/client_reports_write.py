"""Client report writes: the report settings, generating a report, editing it, and its review flow.

The same routes the web's 客户报告 (``/reports``, a Campaign's report editor)
calls: ``/api/v2/ugc/agency/campaigns/{campaign_id}/client-reports``. They are the
operations team's: the selected organization must be the operator organization
running the Campaign (owner, admin or an operator on it), and the server decides.
The routes still name that organization ``agency_workspace_id`` in the query; the
value is the organization id (X-Organization-Id), never a workspace.

A report goes draft -> (request review) -> approved -> sent, or is skipped.
Writes carry the server's guards: the report's ``revision`` and the settings'
``version`` (CAS), and an idempotency key derived from the report, its revision
and the action, so running the same command again after a lost answer never
sends twice. Sending to the client's group, asking for review in the internal
group and a test send all take --yes; without it they fail with
confirmation_required and return their dry run as preview.

Not here: one-off reports for any period (staff, signed-in browser only), the
internal group's creation and the Feishu task-card switches.
"""

from __future__ import annotations

import argparse
import re
from typing import Any

from museoncli.domains._model import CommandSpec, Domain
from museoncli.domains._shared import _direct_output_schema
from museoncli.domains._writes import (
    DRY_RUN,
    add_confirm,
    add_dry_run,
    ask_first,
    ask_then_yes,
    changes,
    previewing,
    read_text,
    require_organization,
    schema,
    uuid_arg,
    uuid_property,
    with_notes,
)
from museoncli.execution import CommandContext, compact_params

REPORT_TYPES = ["daily", "weekly", "monthly", "wrapup"]
SCHEDULED_TYPES = ["daily", "weekly"]
LANGUAGES = ["zh", "en"]
DATA_SCOPES = ["all", "approved"]
WEEKDAYS = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"]
"""Index = the server's weekday number (Sunday = 0)."""
NONE = "none"
_CLOCK = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
_REPORT_FIELDS = (
    "id",
    "type",
    "title",
    "status",
    "revision",
    "periodStart",
    "periodEnd",
    "approvedRevision",
    "publicLink",
    "messageUrl",
)
_ROLE = (
    " For the operations team of the Campaign (owner, admin, or an operator on it) in the "
    "operator organization; others are refused."
)


def _base(campaign_id: str) -> str:
    return f"/ugc/agency/campaigns/{campaign_id}/client-reports"


def _query(ctx: CommandContext, **extra: Any) -> dict[str, Any]:
    # The route's own name for the operator organization's id.
    return compact_params({"agency_workspace_id": require_organization(ctx), **extra})


def _unwrap(value: Any) -> Any:
    if isinstance(value, dict) and set(value) == {"data"}:
        return value["data"]
    return value


async def _workspace(ctx: CommandContext, campaign_id: str, report_id: str | None = None) -> dict:
    found = _unwrap(
        await ctx.api_data_v2(
            ctx.cfg, "GET", _base(campaign_id), params=_query(ctx, report_id=report_id)
        )
    )
    return found if isinstance(found, dict) else {}


async def _post(ctx: CommandContext, campaign_id: str, suffix: str, body: dict[str, Any]) -> Any:
    return _unwrap(
        await ctx.api_data_v2(
            ctx.cfg, "POST", _base(campaign_id) + suffix, params=_query(ctx), json_body=body
        )
    )


def _reports(workspace: dict[str, Any]) -> list[dict[str, Any]]:
    reports = workspace.get("reports")
    return [item for item in reports if isinstance(item, dict)] if isinstance(reports, list) else []


def _communication(workspace: dict[str, Any]) -> dict[str, Any]:
    found = workspace.get("communication")
    return found if isinstance(found, dict) else {}


def _report_line(report: dict[str, Any]) -> dict[str, Any]:
    return {key: report.get(key) for key in _REPORT_FIELDS}


async def _report(ctx: CommandContext) -> tuple[dict[str, Any], dict[str, Any]]:
    """The report and its campaign's report settings, in one read."""
    args = ctx.arguments
    workspace = await _workspace(ctx, args["campaign_id"], args["id"])
    report = next((item for item in _reports(workspace) if item.get("id") == args["id"]), None)
    if report is None:
        raise RuntimeError("not_found: report_not_found: no such report in this Campaign")
    return report, _communication(workspace)


def _expected_revision(args: dict[str, Any], report: dict[str, Any]) -> tuple[int, list[str]]:
    current = int(report.get("revision") or 0)
    expected = args.get("expected_revision")
    if expected is None:
        return current, []
    if expected != current:
        return expected, [
            f"The report is at revision {current}, not {expected}: someone changed it since your "
            "read. The server refuses the write (revision_conflict); read it again first."
        ]
    return expected, []


def _capability(report: dict[str, Any], action: str) -> dict[str, Any]:
    found = (report.get("actionCapabilities") or {}).get(action)
    return found if isinstance(found, dict) else {}


def _blocked(report: dict[str, Any], action: str) -> list[str]:
    capability = _capability(report, action)
    if capability.get("enabled", True):
        return []
    codes = [item.get("code") for item in capability.get("blockers") or [] if isinstance(item, dict)]
    return [f"The server would refuse {action} now: {', '.join(map(str, codes)) or 'blocked'}."]


def _group_name(group: Any) -> str | None:
    return group.get("name") if isinstance(group, dict) else None


# -- executors: reports ------------------------------------------------------


async def _execute_create(ctx: CommandContext) -> Any:
    args = ctx.arguments
    body = compact_params(
        {
            "type": args["type"],
            "date": args["date"],
            "language": args.get("language"),
            "title": args.get("title"),
            "markdown": args.get("markdown"),
            "idempotencyKey": args.get("idempotency_key"),
        }
    )
    if not args.get("dry_run"):
        return await _post(ctx, args["campaign_id"], "", body), [], []
    workspace = await _workspace(ctx, args["campaign_id"])
    communication = _communication(workspace)
    same_type = [
        _report_line(item)
        for item in _reports(workspace)
        if item.get("type") == args["type"]
        and str(item.get("periodStart")) <= args["date"] <= str(item.get("periodEnd"))
    ]
    data = {
        "dry_run": True,
        "would_generate": {key: body.get(key) for key in ("type", "date", "language")},
        "enabled_report_types": communication.get("enabledReportTypes"),
        "existing_reports_for_date": same_type,
    }
    warnings = (
        ["A report of this type already covers that date; generating answers with it."]
        if same_type
        else []
    )
    return data, warnings, [ask_first("the report that would be generated")]


async def _execute_update(ctx: CommandContext) -> Any:
    args = ctx.arguments
    report, _ = await _report(ctx)
    expected, warnings = _expected_revision(args, report)
    after = {
        "title": args.get("title", report.get("title")),
        "markdown": args.get("markdown", report.get("markdown")),
    }
    diff = changes(report, after, ["title", "markdown"])
    data: dict[str, Any] = {
        "dry_run": bool(args.get("dry_run")),
        "report": _report_line(report),
        "changes": [
            {**item, "before": _clip(item["before"]), "after": _clip(item["after"])}
            for item in diff
        ],
    }
    if not diff:
        return data, ["Nothing differs from the saved report; nothing was written."], []
    if args.get("dry_run"):
        return data, warnings, [ask_first("these changes")]
    body = {
        key: report.get(key)
        for key in ("dataScope", "appearance", "publicLink", "languageVariants")
        if key in report
    }
    body.update(after)
    body["expectedRevision"] = expected
    data["report"] = _unwrap(
        await ctx.api_data_v2(
            ctx.cfg,
            "PATCH",
            f"{_base(args['campaign_id'])}/{args['id']}",
            params=_query(ctx),
            json_body=body,
        )
    )
    return data, [], []


def _clip(value: Any, limit: int = 400) -> Any:
    if isinstance(value, str) and len(value) > limit:
        return f"{value[:limit]}... ({len(value)} characters)"
    return value


async def _execute_regenerate(ctx: CommandContext) -> Any:
    args = ctx.arguments
    report, _ = await _report(ctx)
    expected, warnings = _expected_revision(args, report)
    data: dict[str, Any] = {"dry_run": bool(args.get("dry_run")), "report": _report_line(report)}
    if args.get("dry_run"):
        return (
            data,
            [*warnings, "Regenerating replaces the report's text with a fresh draft from the data."],
            [ask_first("the report that would be rewritten")],
        )
    data["report"] = await _post(
        ctx,
        args["campaign_id"],
        f"/{args['id']}/regenerate",
        {"expectedRevision": expected, "idempotencyKey": f"cli:regenerate:{args['id']}:{expected}"},
    )
    return data, [], []


async def _execute_refresh(ctx: CommandContext) -> Any:
    args = ctx.arguments
    report, _ = await _report(ctx)
    expected, warnings = _expected_revision(args, report)
    proposal = await _post(
        ctx,
        args["campaign_id"],
        f"/{args['id']}/refresh-preview",
        {"expectedRevision": expected, "idempotencyKey": f"cli:refresh:{args['id']}:{expected}"},
    )
    proposal = proposal if isinstance(proposal, dict) else {}
    keep = set(args.get("keep_change_ids") or [])
    found = [item for item in proposal.get("changes") or [] if isinstance(item, dict)]
    unknown = keep - {str(item.get("id")) for item in found}
    if unknown:
        raise ValueError(f"--keep-change {sorted(unknown)[0]!r} is not a change of this refresh.")
    data: dict[str, Any] = {
        "dry_run": bool(args.get("dry_run")),
        "report": _report_line(report),
        "changes": [
            {**{key: item.get(key) for key in ("id", "label", "before", "after")},
             "apply": str(item.get("id")) not in keep}
            for item in found
        ],
    }
    if not found:
        return data, ["The report already shows the latest figures; nothing to refresh."], []
    if args.get("dry_run"):
        return (
            data,
            warnings,
            [ask_first("the figures that would change (--keep-change keeps one as written)")],
        )
    data["report"] = await _post(
        ctx,
        args["campaign_id"],
        f"/{args['id']}/refresh-apply",
        {
            "expectedRevision": expected,
            "proposalId": proposal.get("id"),
            "choices": [
                {"id": item.get("id"), "useSource": str(item.get("id")) not in keep}
                for item in found
            ],
            "idempotencyKey": f"cli:refresh-apply:{args['id']}:{expected}",
        },
    )
    return data, [], []


def _action_executor(action: str, *, what: str):
    async def run(ctx: CommandContext) -> Any:
        args = ctx.arguments
        report, communication = await _report(ctx)
        expected, warnings = _expected_revision(args, report)
        server_action = "test" if action == "send" and args.get("test") else action
        binding = int(communication.get("version") or 0)
        destination = {
            "send": _group_name(communication.get("customerGroup")),
            "request_review": _group_name(communication.get("internalGroup")),
            "test": "your own chat with Mel",
        }.get(server_action)
        data: dict[str, Any] = {
            "dry_run": bool(args.get("dry_run")),
            "action": server_action,
            "report": _report_line(report),
            **({"destination": destination} if destination else {}),
        }
        warnings = [*warnings, *_blocked(report, server_action)]
        if args.get("dry_run"):
            step = (
                ask_then_yes(what)
                if server_action in {"send", "request_review", "test"}
                else ask_first(what)
            )
            return data, warnings, [step]
        key = args.get("idempotency_key") or (
            f"cli:{server_action}:{args['id']}:{expected}:{binding}"
        )
        data["report"] = await _post(
            ctx,
            args["campaign_id"],
            f"/{args['id']}/actions/{server_action}",
            compact_params(
                {
                    "expectedRevision": expected,
                    "bindingVersion": binding,
                    "idempotencyKey": key,
                    "reason": args.get("reason"),
                }
            ),
        )
        return data, [], []

    return run


# -- executors: settings -----------------------------------------------------


def _weekly_schedule(communication: dict[str, Any]) -> dict[str, Any]:
    """The weekly schedule the web saves (an older Campaign's comes from its weekly meeting)."""
    if isinstance(communication.get("weeklySchedule"), dict):
        return dict(communication["weeklySchedule"])
    meeting = communication.get("weeklyMeeting") or {}
    weekday = 5 if meeting.get("weekday") is None else (int(meeting["weekday"]) + 6) % 7
    if meeting.get("weekendPolicy") == "advance_to_friday" and weekday in (0, 6):
        weekday = 5
    return {
        "weekday": weekday,
        "generateTime": meeting.get("generateTime") or "09:00",
        "submissionDueTime": meeting.get("operatorDueTime") or "12:00",
    }


def _enabled_types(communication: dict[str, Any]) -> list[str]:
    """The report types that actually run, as the web reads them."""
    running = communication.get("weeklySchedule") is not None or bool(
        communication.get("automationEnabled")
    )
    return [
        kind
        for kind in communication.get("enabledReportTypes") or []
        if kind in SCHEDULED_TYPES and running
    ]


_WRITE_KEYS = (
    "campaignId",
    "version",
    "internalGroup",
    "customerGroup",
    "weeklyMeeting",
    "ownerUserId",
    "reviewerUserId",
    "defaultAppearance",
    "reportDataScope",
    "taskCardsEnabled",
    "taskCardKinds",
    "webNotificationKinds",
    "taskCardsStopped",
    "dailyGenerateTime",
    "dailyOperatorDueTime",
    "dailyReviewDueTime",
)


def settings_write(communication: dict[str, Any]) -> dict[str, Any]:
    """The settings as the web writes them back: everything it read, nothing derived."""
    meeting = communication.get("weeklyMeeting") or {}
    return {
        **{key: communication.get(key) for key in _WRITE_KEYS if key in communication},
        "enabledReportTypes": _enabled_types(communication),
        "timezone": communication.get("timezone") or meeting.get("timezone"),
        "weeklySchedule": _weekly_schedule(communication),
    }


def _settings_view(write: dict[str, Any]) -> dict[str, Any]:
    schedule = write.get("weeklySchedule") or {}
    weekday = schedule.get("weekday")
    return {
        "enabled_report_types": write.get("enabledReportTypes"),
        "timezone": write.get("timezone"),
        "daily_generate_time": write.get("dailyGenerateTime"),
        "daily_due_time": write.get("dailyOperatorDueTime"),
        "weekly_weekday": WEEKDAYS[weekday] if isinstance(weekday, int) and 0 <= weekday <= 6 else None,
        "weekly_generate_time": schedule.get("generateTime"),
        "weekly_due_time": schedule.get("submissionDueTime"),
        "data_scope": write.get("reportDataScope"),
        "language": (write.get("defaultAppearance") or {}).get("language"),
        "customer_group": _group_name(write.get("customerGroup")),
        "internal_group": _group_name(write.get("internalGroup")),
        "owner_user_id": write.get("ownerUserId"),
        "reviewer_user_id": write.get("reviewerUserId"),
    }


def _pick_group(candidates: list[Any], group_id: str, *, flag: str) -> dict[str, Any] | None:
    if group_id == NONE:
        return None
    for group in candidates:
        if isinstance(group, dict) and str(group.get("id")) == group_id:
            return group
    names = ", ".join(
        f"{item.get('id')} ({item.get('name')})" for item in candidates if isinstance(item, dict)
    )
    raise ValueError(
        f"{flag} {group_id!r} is not one of the groups this Campaign can use"
        + (f": {names}." if names else "; none was found.")
    )


def apply_settings_edits(
    write: dict[str, Any], edits: dict[str, Any], candidates: list[Any]
) -> dict[str, Any]:
    after = {**write, "weeklySchedule": dict(write.get("weeklySchedule") or {})}
    enabled = [kind for kind in after.get("enabledReportTypes") or []]
    for kind in edits.get("enable") or []:
        if kind not in enabled:
            enabled.append(kind)
    enabled = [kind for kind in enabled if kind not in (edits.get("disable") or [])]
    after["enabledReportTypes"] = [kind for kind in SCHEDULED_TYPES if kind in enabled]
    simple = {
        "timezone": "timezone",
        "daily_generate_time": "dailyGenerateTime",
        "daily_due_time": "dailyOperatorDueTime",
        "data_scope": "reportDataScope",
    }
    for edit, key in simple.items():
        if edit in edits:
            after[key] = edits[edit]
    weekly = {
        "weekly_weekday": "weekday",
        "weekly_generate_time": "generateTime",
        "weekly_due_time": "submissionDueTime",
    }
    for edit, key in weekly.items():
        if edit in edits:
            after["weeklySchedule"][key] = edits[edit]
    if "language" in edits:
        after["defaultAppearance"] = {**(after.get("defaultAppearance") or {}), "language": edits["language"]}
    for edit, key in (("owner_user_id", "ownerUserId"), ("reviewer_user_id", "reviewerUserId")):
        if edit in edits:
            after[key] = None if edits[edit] == NONE else edits[edit]
    for edit, key, flag in (
        ("customer_group_id", "customerGroup", "--customer-group-id"),
        ("internal_group_id", "internalGroup", "--internal-group-id"),
    ):
        if edit in edits:
            after[key] = _pick_group(candidates, edits[edit], flag=flag)
    return after


async def _execute_config_update(ctx: CommandContext) -> Any:
    args = ctx.arguments
    workspace = await _workspace(ctx, args["campaign_id"])
    communication = _communication(workspace)
    candidates = workspace.get("candidates") if isinstance(workspace.get("candidates"), list) else []
    before = settings_write(communication)
    after = apply_settings_edits(before, args.get("edits") or {}, candidates)
    view_before, view_after = _settings_view(before), _settings_view(after)
    diff = changes(view_before, view_after, list(view_after))
    data: dict[str, Any] = {
        "dry_run": bool(args.get("dry_run")),
        "version": communication.get("version"),
        "settings": view_before,
        "changes": diff,
    }
    if not diff:
        return data, ["Nothing differs from the saved settings; nothing was written."], []
    warnings = []
    if "daily" in view_after["enabled_report_types"] and not view_after["customer_group"]:
        warnings.append("No client group is bound: reports are generated but cannot be sent.")
    if args.get("dry_run"):
        return data, warnings, [ask_first("these changes")]
    saved = _unwrap(
        await ctx.api_data_v2(
            ctx.cfg,
            "PUT",
            f"{_base(args['campaign_id'])}/communication",
            params=_query(ctx),
            json_body={"expectedVersion": int(communication.get("version") or 0), "communication": after},
        )
    )
    data["settings"] = _settings_view(settings_write(saved if isinstance(saved, dict) else {}))
    data["version"] = saved.get("version") if isinstance(saved, dict) else None
    return data, warnings, []


# -- arguments ---------------------------------------------------------------


def _add_report_id(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--id", required=True)
    parser.add_argument("--expected-revision", type=int)


def _report_args(args: argparse.Namespace) -> dict[str, Any]:
    return compact_params(
        {
            "campaign_id": uuid_arg(args.campaign_id, flag="--campaign-id"),
            "id": uuid_arg(args.id, flag="--id"),
            "expected_revision": args.expected_revision,
        }
    )


def _add_create_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--type", choices=REPORT_TYPES, required=True)
    parser.add_argument("--date", required=True)
    parser.add_argument("--language", choices=LANGUAGES)
    parser.add_argument("--title")
    parser.add_argument("--markdown")
    parser.add_argument("--markdown-file")
    parser.add_argument("--idempotency-key")
    add_dry_run(parser)


def _date(value: str) -> str:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError(f"--date takes YYYY-MM-DD, got {value!r}.")
    return value


def _build_create_arguments(args: argparse.Namespace) -> dict[str, Any]:
    return compact_params(
        {
            "campaign_id": uuid_arg(args.campaign_id, flag="--campaign-id"),
            "type": args.type,
            "date": _date(args.date),
            "language": args.language,
            "title": args.title,
            "markdown": read_text(args.markdown, args.markdown_file, flag="--markdown"),
            "idempotency_key": args.idempotency_key,
            "dry_run": bool(args.dry_run),
        }
    )


def _add_update_arguments(parser: argparse.ArgumentParser) -> None:
    _add_report_id(parser)
    parser.add_argument("--title")
    parser.add_argument("--markdown")
    parser.add_argument("--markdown-file")
    add_dry_run(parser)


def _build_update_arguments(args: argparse.Namespace) -> dict[str, Any]:
    markdown = read_text(args.markdown, args.markdown_file, flag="--markdown")
    if args.title is None and markdown is None:
        raise ValueError("Pass --title, --markdown or --markdown-file.")
    if args.title is not None and not args.title.strip():
        raise ValueError("--title cannot be empty.")
    return compact_params(
        {**_report_args(args), "title": args.title, "markdown": markdown, "dry_run": bool(args.dry_run)}
    )


def _add_report_write_arguments(parser: argparse.ArgumentParser) -> None:
    _add_report_id(parser)
    add_dry_run(parser)


def _build_report_write_arguments(args: argparse.Namespace) -> dict[str, Any]:
    return {**_report_args(args), "dry_run": bool(args.dry_run)}


def _add_refresh_arguments(parser: argparse.ArgumentParser) -> None:
    _add_report_write_arguments(parser)
    parser.add_argument("--keep-change", action="append", dest="keep_change_ids")


def _build_refresh_arguments(args: argparse.Namespace) -> dict[str, Any]:
    return compact_params(
        {**_build_report_write_arguments(args), "keep_change_ids": args.keep_change_ids}
    )


def _add_skip_arguments(parser: argparse.ArgumentParser) -> None:
    _add_report_write_arguments(parser)
    parser.add_argument("--reason", required=True)


def _build_skip_arguments(args: argparse.Namespace) -> dict[str, Any]:
    if not args.reason.strip():
        raise ValueError("--reason cannot be empty: say why this report is skipped.")
    return {**_build_report_write_arguments(args), "reason": args.reason.strip()}


def _add_confirmed_arguments(parser: argparse.ArgumentParser) -> None:
    _add_report_id(parser)
    add_confirm(parser)


def _build_confirmed_arguments(args: argparse.Namespace) -> dict[str, Any]:
    return {**_report_args(args), "dry_run": previewing(args)}


def _add_send_arguments(parser: argparse.ArgumentParser) -> None:
    _add_confirmed_arguments(parser)
    parser.add_argument("--test", action="store_true")
    parser.add_argument("--idempotency-key")


def _build_send_arguments(args: argparse.Namespace) -> dict[str, Any]:
    return compact_params(
        {
            **_build_confirmed_arguments(args),
            "test": True if args.test else None,
            "idempotency_key": args.idempotency_key,
        }
    )


def _clock(value: str, *, flag: str) -> str:
    if not _CLOCK.fullmatch(value):
        raise ValueError(f"{flag} takes HH:MM (24-hour), got {value!r}.")
    return value


def _add_config_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--enable", action="append", choices=SCHEDULED_TYPES)
    parser.add_argument("--disable", action="append", choices=SCHEDULED_TYPES)
    parser.add_argument("--timezone")
    parser.add_argument("--daily-generate-time")
    parser.add_argument("--daily-due-time")
    parser.add_argument("--weekly-weekday", choices=WEEKDAYS)
    parser.add_argument("--weekly-generate-time")
    parser.add_argument("--weekly-due-time")
    parser.add_argument("--data-scope", choices=DATA_SCOPES)
    parser.add_argument("--language", choices=LANGUAGES)
    parser.add_argument("--customer-group-id")
    parser.add_argument("--internal-group-id")
    parser.add_argument("--owner-user-id")
    parser.add_argument("--reviewer-user-id")
    add_dry_run(parser)


def _person(value: str, *, flag: str) -> str:
    return NONE if value == NONE else uuid_arg(value, flag=flag)


def _build_config_arguments(args: argparse.Namespace) -> dict[str, Any]:
    edits: dict[str, Any] = {}
    both = set(args.enable or []) & set(args.disable or [])
    if both:
        raise ValueError(f"--enable and --disable both name {sorted(both)[0]}.")
    if args.enable:
        edits["enable"] = list(args.enable)
    if args.disable:
        edits["disable"] = list(args.disable)
    if args.timezone is not None:
        edits["timezone"] = args.timezone
    for name in ("daily_generate_time", "daily_due_time", "weekly_generate_time", "weekly_due_time"):
        value = getattr(args, name)
        if value is not None:
            edits[name] = _clock(value, flag="--" + name.replace("_", "-"))
    if args.weekly_weekday is not None:
        edits["weekly_weekday"] = WEEKDAYS.index(args.weekly_weekday)
    if args.data_scope is not None:
        edits["data_scope"] = args.data_scope
    if args.language is not None:
        edits["language"] = args.language
    for name in ("customer_group_id", "internal_group_id"):
        value = getattr(args, name)
        if value is not None:
            edits[name] = value.strip()
    for name in ("owner_user_id", "reviewer_user_id"):
        value = getattr(args, name)
        if value is not None:
            edits[name] = _person(value, flag="--" + name.replace("_", "-"))
    if not edits:
        raise ValueError(
            "Pass at least one setting to change, e.g. --enable daily, --daily-generate-time "
            "09:00, --weekly-weekday fri or --customer-group-id."
        )
    return {
        "campaign_id": uuid_arg(args.campaign_id, flag="--campaign-id"),
        "edits": edits,
        "dry_run": bool(args.dry_run),
    }


# -- schemas -----------------------------------------------------------------

_CAMPAIGN_ID = uuid_property(
    "UGC campaign ID (ugc campaign +list), the Campaign the reports are about."
)
_REPORT_ID = uuid_property("Client report ID (from the Campaign's report list).")
_EXPECTED_REVISION = {
    "type": "integer",
    "minimum": 1,
    "description": (
        "The report revision you read; the write fails if the report changed since. "
        "Omitted, the revision read just before the write is used."
    ),
}
_REPORT_INPUT = {"campaign_id": _CAMPAIGN_ID, "id": _REPORT_ID, "expected_revision": _EXPECTED_REVISION}
_REPORT_OUT = _direct_output_schema("report (id, type, status, revision, period) after the write.")


def specs() -> list[CommandSpec]:
    domain = Domain.UGC
    campaign = "11111111-1111-4111-8111-111111111111"
    report = "77777777-7777-4777-8777-777777777777"
    write = {
        "risk_level": "write",
        "execution": "direct",
        "supports_dry_run": True,
        "dry_run_reads_server": True,
    }
    confirmed = {**write, "requires_confirmation": True}
    report_spec = {"domain": domain, "resource": "client-report"}
    return [
        CommandSpec(
            **report_spec,  # type: ignore[arg-type]
            shortcut="+create",
            summary=(
                "Generate a client report now: the daily, weekly, monthly or wrap-up report of "
                "the period holding --date, drafted from the Campaign's data (or with your own "
                "--title/--markdown). Nothing is sent. Running it again for the same type and "
                "date answers with the same report. --dry-run lists the reports that already "
                "cover the date." + _ROLE
            ),
            adapter_tool_name="ugc_client_report_create",
            input_schema=schema(
                {
                    "campaign_id": _CAMPAIGN_ID,
                    "type": {"type": "string", "enum": REPORT_TYPES},
                    "date": {"type": "string", "format": "date", "description": "A day of the report's period."},
                    "language": {"type": "string", "enum": LANGUAGES},
                    "title": {"type": "string", "maxLength": 500},
                    "markdown": {"type": "string", "maxLength": 500000},
                    "idempotency_key": {"type": "string", "maxLength": 200},
                    "dry_run": DRY_RUN,
                },
                ["campaign_id", "type", "date"],
            ),
            output_schema=_direct_output_schema("The report as generated (id, status, revision, markdown)."),
            examples=[
                f"museoncli ugc client-report +create --campaign-id {campaign} --type daily "
                "--date 2026-11-12 --dry-run"
            ],
            add_arguments=_add_create_arguments,
            build_arguments=_build_create_arguments,
            **write,  # type: ignore[arg-type]
        ),
        CommandSpec(
            **report_spec,  # type: ignore[arg-type]
            shortcut="+update",
            summary=(
                "Edit a client report's title or Markdown body (a new revision; an approved report "
                "needs approving again). --dry-run returns the changes without writing." + _ROLE
            ),
            adapter_tool_name="ugc_client_report_update",
            input_schema=schema(
                {
                    **_REPORT_INPUT,
                    "title": {"type": "string", "minLength": 1, "maxLength": 500},
                    "markdown": {"type": "string", "maxLength": 500000},
                    "dry_run": DRY_RUN,
                },
                ["campaign_id", "id"],
            ),
            output_schema=_direct_output_schema("report and changes (field, before, after)."),
            examples=[
                f"museoncli ugc client-report +update --campaign-id {campaign} --id {report} "
                "--markdown-file report.md --expected-revision 3 --dry-run"
            ],
            add_arguments=_add_update_arguments,
            build_arguments=_build_update_arguments,
            **write,  # type: ignore[arg-type]
        ),
        CommandSpec(
            **report_spec,  # type: ignore[arg-type]
            shortcut="+regenerate",
            summary=(
                "Redraft a client report from the Campaign's current data, replacing its text. "
                "--dry-run shows the report without writing." + _ROLE
            ),
            adapter_tool_name="ugc_client_report_regenerate",
            input_schema=schema({**_REPORT_INPUT, "dry_run": DRY_RUN}, ["campaign_id", "id"]),
            output_schema=_REPORT_OUT,
            examples=[
                f"museoncli ugc client-report +regenerate --campaign-id {campaign} --id {report} --dry-run"
            ],
            add_arguments=_add_report_write_arguments,
            build_arguments=_build_report_write_arguments,
            **write,  # type: ignore[arg-type]
        ),
        CommandSpec(
            **report_spec,  # type: ignore[arg-type]
            shortcut="+refresh",
            summary=(
                "Update the figures in a client report to the latest data, keeping the rest of "
                "its text. --dry-run asks the server for the proposed changes (label, before, "
                "after) and writes nothing to the report; --keep-change keeps one figure as "
                "written." + _ROLE
            ),
            adapter_tool_name="ugc_client_report_refresh",
            input_schema=schema(
                {
                    **_REPORT_INPUT,
                    "keep_change_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Change ids (from the --dry-run) to leave as written.",
                    },
                    "dry_run": DRY_RUN,
                },
                ["campaign_id", "id"],
            ),
            output_schema=_direct_output_schema("report and changes (id, label, before, after, apply)."),
            examples=[
                f"museoncli ugc client-report +refresh --campaign-id {campaign} --id {report} --dry-run"
            ],
            add_arguments=_add_refresh_arguments,
            build_arguments=_build_refresh_arguments,
            **write,  # type: ignore[arg-type]
        ),
        CommandSpec(
            **report_spec,  # type: ignore[arg-type]
            shortcut="+request-review",
            summary=(
                "Ask the Campaign's reviewer to review a client report: posts it to the internal "
                "Feishu group. Without --yes it is refused with a preview of the report and the group." + _ROLE
            ),
            adapter_tool_name="ugc_client_report_request_review",
            input_schema=schema({**_REPORT_INPUT, "dry_run": DRY_RUN}, ["campaign_id", "id"]),
            output_schema=_REPORT_OUT,
            examples=[
                f"museoncli ugc client-report +request-review --campaign-id {campaign} --id {report} --yes"
            ],
            add_arguments=_add_confirmed_arguments,
            build_arguments=_build_confirmed_arguments,
            **confirmed,  # type: ignore[arg-type]
        ),
        CommandSpec(
            **report_spec,  # type: ignore[arg-type]
            shortcut="+approve",
            summary=(
                "Approve a client report's current revision (the Campaign's reviewer). Nothing is "
                "sent; +send does that. --dry-run shows the report without writing." + _ROLE
            ),
            adapter_tool_name="ugc_client_report_approve",
            input_schema=schema({**_REPORT_INPUT, "dry_run": DRY_RUN}, ["campaign_id", "id"]),
            output_schema=_REPORT_OUT,
            examples=[
                f"museoncli ugc client-report +approve --campaign-id {campaign} --id {report} --dry-run"
            ],
            add_arguments=_add_report_write_arguments,
            build_arguments=_build_report_write_arguments,
            **write,  # type: ignore[arg-type]
        ),
        CommandSpec(
            **report_spec,  # type: ignore[arg-type]
            shortcut="+skip",
            summary=(
                "Skip a client report (not sent for this period), with the reason. --dry-run "
                "shows the report without writing." + _ROLE
            ),
            adapter_tool_name="ugc_client_report_skip",
            input_schema=schema(
                {
                    **_REPORT_INPUT,
                    "reason": {"type": "string", "minLength": 1, "maxLength": 2000},
                    "dry_run": DRY_RUN,
                },
                ["campaign_id", "id", "reason"],
            ),
            output_schema=_REPORT_OUT,
            examples=[
                f"museoncli ugc client-report +skip --campaign-id {campaign} --id {report} "
                '--reason "Client paused the campaign this week" --dry-run'
            ],
            add_arguments=_add_skip_arguments,
            build_arguments=_build_skip_arguments,
            **write,  # type: ignore[arg-type]
        ),
        CommandSpec(
            **report_spec,  # type: ignore[arg-type]
            shortcut="+send",
            summary=(
                "Send an approved client report to the client's group, or with --test to your own "
                "chat with Mel only. Without --yes it is refused with a preview of the report, where it would go and "
                "anything blocking it. Sending the same revision again does not send twice." + _ROLE
            ),
            adapter_tool_name="ugc_client_report_send",
            input_schema=schema(
                {
                    **_REPORT_INPUT,
                    "test": {
                        "type": "boolean",
                        "description": "Send to your own chat with Mel instead of the client's group.",
                    },
                    "idempotency_key": {
                        "type": "string",
                        "minLength": 8,
                        "maxLength": 200,
                        "description": "Defaults to one per report revision, action and settings version.",
                    },
                    "dry_run": DRY_RUN,
                },
                ["campaign_id", "id"],
            ),
            output_schema=_direct_output_schema("action, destination and the report after sending."),
            examples=[
                f"museoncli ugc client-report +send --campaign-id {campaign} --id {report}",
                f"museoncli ugc client-report +send --campaign-id {campaign} --id {report} --yes",
            ],
            add_arguments=_add_send_arguments,
            build_arguments=_build_send_arguments,
            **confirmed,  # type: ignore[arg-type]
        ),
        CommandSpec(
            domain=domain,
            resource="client-report-config",
            shortcut="+update",
            summary=(
                "Change a Campaign's client report settings: which reports run (--enable/--disable "
                "daily, weekly), when they are generated and due, the weekly day, timezone, data "
                "scope, language, the client and internal Feishu groups, owner and reviewer. "
                "Settings not passed keep their value; the write fails if someone saved since "
                "your read. --dry-run returns the changes without writing." + _ROLE
            ),
            adapter_tool_name="ugc_client_report_config_update",
            input_schema=schema(
                {
                    "campaign_id": _CAMPAIGN_ID,
                    "edits": {
                        "type": "object",
                        "description": (
                            "enable/disable (daily, weekly), timezone, daily_generate_time, "
                            "daily_due_time, weekly_weekday, weekly_generate_time, weekly_due_time "
                            "(HH:MM), data_scope, language, customer_group_id / internal_group_id "
                            "(a group the Campaign can use, or none), owner_user_id, reviewer_user_id."
                        ),
                    },
                    "dry_run": DRY_RUN,
                },
                ["campaign_id", "edits"],
            ),
            output_schema=_direct_output_schema("version, settings and changes (field, before, after)."),
            examples=[
                f"museoncli ugc client-report-config +update --campaign-id {campaign} --enable daily "
                "--daily-generate-time 09:00 --daily-due-time 12:00 --dry-run"
            ],
            add_arguments=_add_config_arguments,
            build_arguments=_build_config_arguments,
            **write,  # type: ignore[arg-type]
        ),
    ]


EXECUTORS = {
    "ugc.client-report-create": with_notes(_execute_create),
    "ugc.client-report-update": with_notes(_execute_update),
    "ugc.client-report-regenerate": with_notes(_execute_regenerate),
    "ugc.client-report-refresh": with_notes(_execute_refresh),
    "ugc.client-report-request-review": with_notes(
        _action_executor("request_review", what="the report and the internal group it goes to")
    ),
    "ugc.client-report-approve": with_notes(
        _action_executor("approve", what="the report revision being approved")
    ),
    "ugc.client-report-skip": with_notes(_action_executor("skip", what="the report and the reason")),
    "ugc.client-report-send": with_notes(
        _action_executor("send", what="the report and where it would go")
    ),
    "ugc.client-report-config-update": with_notes(_execute_config_update),
}
