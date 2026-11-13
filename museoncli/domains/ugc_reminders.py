"""Reminders: the team's Feishu reminders and digests, and automatic nudges to creators.

The same routes the web's Campaign settings (提醒 / 自动提醒) call, under
``/api/v2/ugc/campaigns/{campaign_id}``:

- ``reminder-settings``: the project's own reminder policy, a layer over the
  organization's. A field set to inherit falls back to it. Saving replaces the
  layer and fails if someone saved since your read (``expected_updated_at``).
- ``reminder-settings/test``, ``reminder-subscription`` and
  ``reminder-delegations``: MuseOn staff only, as in the web.
- ``auto-nudge``: when creators flagged by a creator check (not set up, quiet,
  ...) get an automatic Discord reminder. Changing it changes what creators are
  sent, so it takes --yes; without it the command only previews.

Reading and saving the project's policy is the Campaign's operations team's
(owner, admin, or an operator on it).
"""

from __future__ import annotations

import argparse
import re
from datetime import datetime
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
    schema,
    uuid_arg,
    uuid_property,
    with_notes,
)
from museoncli.execution import CommandContext, direct_enveloped

WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
TASK_KINDS = [
    "manual",
    "review_creative",
    "review_application",
    "judge_attribution",
    "fix_invitation",
    "fix_authorization",
    "account_authorization_lost",
    "chase_contract",
    "fix_activation",
    "review_warmup",
    "await_warmup",
    "set_payscale",
    "judge_pay_rule",
    "review_compliance",
    "approve_payout",
    "fix_discord",
    "await_discord",
    "review_viral",
    "report_client",
]
CHECKS = ["cant_track", "not_signed", "not_set_up", "quiet", "not_healthy"]
SWITCH = ["on", "off", "inherit"]
INHERIT = "inherit"
NONE = "none"
POLICY_FIELDS = [
    "timezone",
    "workdays",
    "off_days",
    "feishu_enabled",
    "overdue_escalation",
    "task_kinds",
    "morning_digest",
    "evening_digest",
    "digest_rules",
]
_CLOCK = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
_TEAM = " For the Campaign's operations team (owner, admin, or an operator on it)."
_STAFF = " MuseOn staff only, as in the web."


def _base(campaign_id: str) -> str:
    return f"/ugc/campaigns/{campaign_id}"


async def _settings(ctx: CommandContext, campaign_id: str) -> dict[str, Any]:
    found = await ctx.api_data_v2(ctx.cfg, "GET", f"{_base(campaign_id)}/reminder-settings")
    return found if isinstance(found, dict) else {}


def _layer(settings: dict[str, Any]) -> dict[str, Any]:
    found = settings.get("campaign_layer")
    return found if isinstance(found, dict) else {}


def _settings_line(settings: dict[str, Any]) -> dict[str, Any]:
    return {
        key: settings.get(key)
        for key in ("covered", "uncovered", "effective", "next_digests", "subscribed")
    }


# -- executors ---------------------------------------------------------------


async def _execute_get(ctx: CommandContext) -> Any:
    return await _settings(ctx, ctx.arguments["campaign_id"])


def policy_write(layer: dict[str, Any], edits: dict[str, Any]) -> dict[str, Any]:
    """The project's layer with the edits applied, as the whole-layer write takes it."""
    body = {field: layer.get(field) for field in POLICY_FIELDS}
    if isinstance(body.get("digest_rules"), list):
        body["digest_rules"] = [
            {"id": rule.get("id"), "time": rule.get("time")}
            for rule in body["digest_rules"]
            if isinstance(rule, dict)
        ]
    for field, value in edits.items():
        if field == "digest_times":
            body["digest_rules"] = _digest_rules(value, body.get("digest_rules"))
        else:
            body[field] = value
    body["expected_updated_at"] = layer.get("updated_at")
    return body


def _digest_rules(times: list[str] | None, current: Any) -> list[dict[str, str]] | None:
    if times is None:
        return None
    known = {rule.get("time"): rule.get("id") for rule in current or [] if isinstance(rule, dict)}
    return [
        {"id": known.get(time) or f"cli-{time.replace(':', '')}", "time": time}
        for time in dict.fromkeys(times)
    ]


async def _execute_update(ctx: CommandContext) -> Any:
    args = ctx.arguments
    settings = await _settings(ctx, args["campaign_id"])
    layer = _layer(settings)
    body = policy_write(layer, args.get("edits") or {})
    diff = changes({field: layer.get(field) for field in POLICY_FIELDS}, body, POLICY_FIELDS)
    data: dict[str, Any] = {
        "dry_run": bool(args.get("dry_run")),
        "campaign_layer": layer,
        "effective": settings.get("effective"),
        "changes": diff,
    }
    if not diff:
        return data, ["Nothing differs from the project's saved reminders; nothing was written."], []
    warnings = []
    if settings.get("covered") is False:
        warnings.append(
            "Reminders do not run for this project now ("
            + ", ".join(map(str, settings.get("uncovered") or []))
            + "); the settings are kept for when they do."
        )
    if args.get("dry_run"):
        return data, warnings, [ask_first("these changes (null means inherit)")]
    saved = await ctx.api_data_v2(
        ctx.cfg, "PUT", f"{_base(args['campaign_id'])}/reminder-settings", json_body=body
    )
    saved = saved if isinstance(saved, dict) else {}
    data["campaign_layer"] = _layer(saved)
    data["effective"] = saved.get("effective")
    return data, warnings, []


async def _execute_test(ctx: CommandContext) -> Any:
    args = ctx.arguments
    settings = await _settings(ctx, args["campaign_id"])
    data: dict[str, Any] = {"dry_run": bool(args.get("dry_run")), **_settings_line(settings)}
    if args.get("dry_run"):
        return data, [], [
            ask_then_yes("that a test of the group's reminders goes to their own chat with Mel")
        ]
    result = await ctx.api_data_v2(
        ctx.cfg, "POST", f"{_base(args['campaign_id'])}/reminder-settings/test"
    )
    data["test"] = result
    warnings = (
        ["No chat with Mel yet: open one with Mel in Feishu once, then try again."]
        if isinstance(result, dict) and result.get("outcome") == "no_direct_chat"
        else []
    )
    return data, warnings, []


async def _execute_subscribe(ctx: CommandContext) -> Any:
    args = ctx.arguments
    settings = await _settings(ctx, args["campaign_id"])
    data: dict[str, Any] = {
        "dry_run": bool(args.get("dry_run")),
        "subscribed": {"before": settings.get("subscribed"), "after": args["subscribed"]},
    }
    if settings.get("subscribed") == args["subscribed"]:
        return data, ["Already so; nothing was written."], []
    if args.get("dry_run"):
        return data, [], [ask_first("the change")]
    saved = await ctx.api_data_v2(
        ctx.cfg,
        "PUT",
        f"{_base(args['campaign_id'])}/reminder-subscription",
        json_body={"subscribed": args["subscribed"]},
    )
    data["subscribed"]["after"] = saved.get("subscribed") if isinstance(saved, dict) else None
    return data, [], []


async def _execute_delegation_create(ctx: CommandContext) -> Any:
    args = ctx.arguments
    body = {
        key: args[key] for key in ("user_id", "delegate_user_id", "starts_at", "ends_at")
    }
    if args.get("dry_run"):
        settings = await _settings(ctx, args["campaign_id"])
        overlapping = [
            item
            for item in settings.get("delegations") or []
            if isinstance(item, dict) and str(item.get("user_id")) == args["user_id"]
        ]
        data = {"dry_run": True, "delegation": body, "existing_for_user": overlapping}
        return data, [], [ask_first("who covers whose reminders, and when")]
    saved = await ctx.api_data_v2(
        ctx.cfg, "POST", f"{_base(args['campaign_id'])}/reminder-delegations", json_body=body
    )
    delegations = saved.get("delegations") if isinstance(saved, dict) else None
    return {"delegations": delegations}, [], []


async def _execute_delegation_cancel(ctx: CommandContext) -> Any:
    args = ctx.arguments
    settings = await _settings(ctx, args["campaign_id"])
    found = next(
        (
            item
            for item in settings.get("delegations") or []
            if isinstance(item, dict) and str(item.get("id")) == args["id"]
        ),
        None,
    )
    if found is None:
        raise RuntimeError("not_found: reminder delegation not found (or already over)")
    data: dict[str, Any] = {"dry_run": bool(args.get("dry_run")), "delegation": found}
    if args.get("dry_run"):
        return data, [], [ask_then_yes("the delegation that would end")]
    saved = await ctx.api_data_v2(
        ctx.cfg,
        "DELETE",
        f"{_base(args['campaign_id'])}/reminder-delegations/{args['id']}",
    )
    data["delegations"] = saved.get("delegations") if isinstance(saved, dict) else None
    return data, [], []


async def _auto_nudge(ctx: CommandContext, campaign_id: str) -> dict[str, Any]:
    found = await ctx.api_data_v2(ctx.cfg, "GET", f"{_base(campaign_id)}/auto-nudge")
    return found if isinstance(found, dict) else {}


async def _execute_auto_nudge_get(ctx: CommandContext) -> Any:
    return await _auto_nudge(ctx, ctx.arguments["campaign_id"])


_NUDGE_FIELDS = ["checks", "days", "send_at", "timezone"]


async def _execute_auto_nudge_update(ctx: CommandContext) -> Any:
    args = ctx.arguments
    current = await _auto_nudge(ctx, args["campaign_id"])
    before = {field: current.get(field) for field in _NUDGE_FIELDS}
    after = {**before, **(args.get("edits") or {})}
    diff = changes(before, after, _NUDGE_FIELDS)
    data: dict[str, Any] = {
        "dry_run": bool(args.get("dry_run")),
        "auto_nudge": {**before, "next_send_at": current.get("next_send_at")},
        "changes": diff,
    }
    if not diff:
        return data, ["Nothing differs from the saved auto nudge; nothing was written."], []
    warnings = []
    if after.get("days") and not after.get("checks"):
        warnings.append("Days with no check are refused: pass --check for who gets nudged.")
    if args.get("dry_run"):
        turning = "off" if not after.get("days") else "on"
        return data, warnings, [
            ask_then_yes(f"the change (it turns automatic creator nudges {turning})")
        ]
    body = {
        "checks": after.get("checks") or [],
        "days": after.get("days") or [],
        "send_at": after.get("send_at") or "10:00",
        "timezone": after.get("timezone") or "UTC",
        "expected_updated_at": current.get("updated_at"),
    }
    data["auto_nudge"] = await ctx.api_data_v2(
        ctx.cfg, "PUT", f"{_base(args['campaign_id'])}/auto-nudge", json_body=body
    )
    return data, warnings, []


# -- arguments ---------------------------------------------------------------


def _add_campaign_id(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--campaign-id", required=True)


def _campaign(args: argparse.Namespace) -> dict[str, Any]:
    return {"campaign_id": uuid_arg(args.campaign_id, flag="--campaign-id")}


def _clock(value: str, *, flag: str) -> str:
    if not _CLOCK.fullmatch(value):
        raise ValueError(f"{flag} takes HH:MM (24-hour), got {value!r}.")
    return value


def _inherit_list(values: list[str] | None) -> bool:
    return values == [INHERIT]


def _add_update_arguments(parser: argparse.ArgumentParser) -> None:
    _add_campaign_id(parser)
    parser.add_argument("--timezone")
    parser.add_argument("--workday", action="append", dest="workdays")
    parser.add_argument("--off-day", action="append", dest="off_days")
    parser.add_argument("--feishu", choices=SWITCH)
    parser.add_argument("--overdue-escalation", choices=SWITCH)
    parser.add_argument("--task-kind", action="append", dest="task_kinds")
    parser.add_argument("--morning-digest")
    parser.add_argument("--evening-digest")
    parser.add_argument("--digest-time", action="append", dest="digest_times")
    add_dry_run(parser)


def _switch(value: str) -> bool | None:
    return None if value == INHERIT else value == "on"


def _list_edit(values: list[str], *, flag: str, allowed: list[str] | None = None) -> list[str] | None:
    """inherit -> null (fall back), none -> [] (nothing), otherwise the values."""
    if _inherit_list(values):
        return None
    if values == [NONE]:
        return []
    cleaned = [dekebab(value.strip()) or "" for value in values]
    if allowed is not None:
        unknown = [value for value in cleaned if value not in allowed]
        if unknown:
            raise ValueError(
                f"{flag} {unknown[0]!r} is not one of: " + ", ".join(kebab_choices(allowed)) + "."
            )
    return list(dict.fromkeys(cleaned))


def _build_update_arguments(args: argparse.Namespace) -> dict[str, Any]:
    edits: dict[str, Any] = {}
    if args.timezone is not None:
        edits["timezone"] = None if args.timezone == INHERIT else args.timezone
    if args.workdays is not None:
        edits["workdays"] = _list_edit(args.workdays, flag="--workday", allowed=WEEKDAYS)
    if args.off_days is not None:
        days = _list_edit(args.off_days, flag="--off-day")
        for day in days or []:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
                raise ValueError(f"--off-day takes YYYY-MM-DD, got {day!r}.")
        edits["off_days"] = days
    if args.feishu is not None:
        edits["feishu_enabled"] = _switch(args.feishu)
    if args.overdue_escalation is not None:
        edits["overdue_escalation"] = _switch(args.overdue_escalation)
    if args.task_kinds is not None:
        edits["task_kinds"] = _list_edit(args.task_kinds, flag="--task-kind", allowed=TASK_KINDS)
    for name in ("morning_digest", "evening_digest"):
        value = getattr(args, name)
        if value is not None:
            flag = "--" + name.replace("_", "-")
            edits[name] = None if value == INHERIT else _clock(value, flag=flag)
    if args.digest_times is not None:
        times = _list_edit(args.digest_times, flag="--digest-time")
        edits["digest_times"] = (
            None if times is None else [_clock(value, flag="--digest-time") for value in times]
        )
    if not edits:
        raise ValueError(
            "Pass at least one setting, e.g. --feishu on, --workday mon --workday fri, "
            "--digest-time 09:00, --task-kind review-creative (inherit falls back to the "
            "organization's)."
        )
    return {**_campaign(args), "edits": edits, "dry_run": bool(args.dry_run)}


def _add_campaign_only(parser: argparse.ArgumentParser) -> None:
    _add_campaign_id(parser)


def _add_test_arguments(parser: argparse.ArgumentParser) -> None:
    _add_campaign_id(parser)
    add_confirm(parser)


def _build_test_arguments(args: argparse.Namespace) -> dict[str, Any]:
    return {**_campaign(args), "dry_run": previewing(args)}


def _add_subscribe_arguments(parser: argparse.ArgumentParser) -> None:
    _add_campaign_id(parser)
    parser.add_argument("--subscribed", action=argparse.BooleanOptionalAction, required=True)
    add_dry_run(parser)


def _build_subscribe_arguments(args: argparse.Namespace) -> dict[str, Any]:
    return {**_campaign(args), "subscribed": bool(args.subscribed), "dry_run": bool(args.dry_run)}


def _moment(value: str, *, flag: str) -> str:
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        raise ValueError(f"{flag} takes a time with a timezone offset, got {value!r}.") from None
    if moment.tzinfo is None:
        raise ValueError(f"{flag} needs a timezone offset, e.g. 2026-11-20T00:00:00+08:00.")
    return moment.isoformat()


def _add_delegation_create_arguments(parser: argparse.ArgumentParser) -> None:
    _add_campaign_id(parser)
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--delegate-user-id", required=True)
    parser.add_argument("--starts-at", required=True)
    parser.add_argument("--ends-at", required=True)
    add_dry_run(parser)


def _build_delegation_create_arguments(args: argparse.Namespace) -> dict[str, Any]:
    starts = _moment(args.starts_at, flag="--starts-at")
    ends = _moment(args.ends_at, flag="--ends-at")
    if datetime.fromisoformat(ends) <= datetime.fromisoformat(starts):
        raise ValueError("--ends-at must be after --starts-at.")
    return {
        **_campaign(args),
        "user_id": uuid_arg(args.user_id, flag="--user-id"),
        "delegate_user_id": uuid_arg(args.delegate_user_id, flag="--delegate-user-id"),
        "starts_at": starts,
        "ends_at": ends,
        "dry_run": bool(args.dry_run),
    }


def _add_delegation_cancel_arguments(parser: argparse.ArgumentParser) -> None:
    _add_campaign_id(parser)
    parser.add_argument("--id", required=True)
    add_confirm(parser)


def _build_delegation_cancel_arguments(args: argparse.Namespace) -> dict[str, Any]:
    return {**_campaign(args), "id": uuid_arg(args.id, flag="--id"), "dry_run": previewing(args)}


def _add_auto_nudge_update_arguments(parser: argparse.ArgumentParser) -> None:
    _add_campaign_id(parser)
    parser.add_argument("--check", action="append", dest="checks", choices=kebab_choices(CHECKS))
    parser.add_argument("--day", action="append", dest="days", choices=WEEKDAYS)
    parser.add_argument("--send-at")
    parser.add_argument("--timezone")
    parser.add_argument("--off", action="store_true")
    add_confirm(parser)


def _build_auto_nudge_update_arguments(args: argparse.Namespace) -> dict[str, Any]:
    edits: dict[str, Any] = {}
    if args.off and args.days:
        raise ValueError("--off turns the auto nudge off; do not pass --day with it.")
    if args.off:
        edits["days"] = []
    if args.days:
        edits["days"] = [day for day in WEEKDAYS if day in args.days]
    if args.checks:
        edits["checks"] = list(dict.fromkeys(dekebab(check) for check in args.checks))
    if args.send_at is not None:
        edits["send_at"] = _clock(args.send_at, flag="--send-at")
    if args.timezone is not None:
        edits["timezone"] = args.timezone
    if not edits:
        raise ValueError("Pass --day/--check/--send-at/--timezone, or --off.")
    return {**_campaign(args), "edits": edits, "dry_run": previewing(args)}


# -- schemas -----------------------------------------------------------------

_CAMPAIGN_ID = uuid_property("UGC campaign ID (ugc campaign +list).")
_POLICY_EDITS = {
    "type": "object",
    "description": (
        "Only the fields passed change; null inherits the organization's value. timezone, "
        "workdays (mon..sun), off_days (YYYY-MM-DD), feishu_enabled, overdue_escalation, "
        "task_kinds ([] reminds of none), morning_digest / evening_digest (HH:MM), "
        "digest_times (HH:MM list; [] stops digests)."
    ),
}


def specs() -> list[CommandSpec]:
    domain = Domain.UGC
    campaign = "11111111-1111-4111-8111-111111111111"
    person = "99999999-9999-4999-8999-999999999991"
    delegate = "99999999-9999-4999-8999-999999999992"
    delegation = "99999999-9999-4999-8999-999999999993"
    read = {"risk_level": "read", "execution": "direct"}
    write = {
        "risk_level": "write",
        "execution": "direct",
        "supports_dry_run": True,
        "dry_run_reads_server": True,
    }
    confirmed = {**write, "requires_confirmation": True}
    campaign_only = schema({"campaign_id": _CAMPAIGN_ID}, ["campaign_id"])
    return [
        CommandSpec(
            domain=domain,
            resource="reminder",
            shortcut="+get",
            summary=(
                "A Campaign's team reminders: its own policy layer, the organization's it inherits, "
                "the effective policy, the next digests, what would be sent in the next 24 hours, "
                "delegations and whether you are subscribed." + _TEAM
            ),
            adapter_tool_name="ugc_reminder_get",
            input_schema=campaign_only,
            output_schema=_direct_output_schema(
                "covered, campaign_layer, workspace_layer, effective, next_digests, planned, delegations."
            ),
            examples=[f"museoncli ugc reminder +get --campaign-id {campaign}"],
            add_arguments=_add_campaign_only,
            build_arguments=_campaign,
            **read,  # type: ignore[arg-type]
        ),
        CommandSpec(
            domain=domain,
            resource="reminder",
            shortcut="+update",
            summary=(
                "Change a Campaign's own reminder policy: Feishu on/off, workdays, days off, which "
                "task kinds are reminded, digest times, overdue escalation, timezone. inherit falls "
                "back to the organization's. Fails if someone saved since your read. --dry-run "
                "returns the changes without writing." + _TEAM
            ),
            adapter_tool_name="ugc_reminder_update",
            input_schema=schema(
                {"campaign_id": _CAMPAIGN_ID, "edits": _POLICY_EDITS, "dry_run": DRY_RUN},
                ["campaign_id", "edits"],
            ),
            output_schema=_direct_output_schema("campaign_layer, effective and changes (field, before, after)."),
            examples=[
                f"museoncli ugc reminder +update --campaign-id {campaign} --feishu on "
                "--digest-time 09:30 --digest-time 17:30 --task-kind review-creative "
                "--task-kind report-client --dry-run"
            ],
            add_arguments=_add_update_arguments,
            build_arguments=_build_update_arguments,
            **write,  # type: ignore[arg-type]
        ),
        CommandSpec(
            domain=domain,
            resource="reminder",
            shortcut="+test",
            summary=(
                "Send yourself, in your own Feishu chat with Mel, what the group's reminders would "
                "say now (at most one a minute); nobody else gets it. Without --yes it only "
                "previews." + _STAFF
            ),
            adapter_tool_name="ugc_reminder_test",
            input_schema=schema({"campaign_id": _CAMPAIGN_ID, "dry_run": DRY_RUN}, ["campaign_id"]),
            output_schema=_direct_output_schema("test.outcome: sent, already_sent, no_direct_chat or unavailable."),
            examples=[f"museoncli ugc reminder +test --campaign-id {campaign} --yes"],
            add_arguments=_add_test_arguments,
            build_arguments=_build_test_arguments,
            **confirmed,  # type: ignore[arg-type]
        ),
        CommandSpec(
            domain=domain,
            resource="reminder",
            shortcut="+subscribe",
            summary=(
                "Turn your own direct-message list of this Campaign's tasks at each digest on "
                "(--subscribed) or off (--no-subscribed). --dry-run shows the change." + _STAFF
            ),
            adapter_tool_name="ugc_reminder_subscribe",
            input_schema=schema(
                {"campaign_id": _CAMPAIGN_ID, "subscribed": {"type": "boolean"}, "dry_run": DRY_RUN},
                ["campaign_id", "subscribed"],
            ),
            output_schema=_direct_output_schema("subscribed before and after."),
            examples=[f"museoncli ugc reminder +subscribe --campaign-id {campaign} --subscribed"],
            add_arguments=_add_subscribe_arguments,
            build_arguments=_build_subscribe_arguments,
            **write,  # type: ignore[arg-type]
        ),
        CommandSpec(
            domain=domain,
            resource="reminder-delegation",
            shortcut="+create",
            summary=(
                "While a team member is away, send their reminders (in the whole workspace of the "
                "Campaign) to a colleague; no access or approval moves. --dry-run shows the "
                "delegation and the member's current ones." + _STAFF
            ),
            adapter_tool_name="ugc_reminder_delegation_create",
            input_schema=schema(
                {
                    "campaign_id": _CAMPAIGN_ID,
                    "user_id": uuid_property("The member who is away."),
                    "delegate_user_id": uuid_property("Who gets their reminders meanwhile."),
                    "starts_at": {"type": "string", "format": "date-time"},
                    "ends_at": {"type": "string", "format": "date-time"},
                    "dry_run": DRY_RUN,
                },
                ["campaign_id", "user_id", "delegate_user_id", "starts_at", "ends_at"],
            ),
            output_schema=_direct_output_schema("delegations not over yet."),
            examples=[
                f"museoncli ugc reminder-delegation +create --campaign-id {campaign} --user-id {person} "
                f"--delegate-user-id {delegate} --starts-at 2026-11-20T00:00:00+08:00 "
                "--ends-at 2026-11-27T00:00:00+08:00 --dry-run"
            ],
            add_arguments=_add_delegation_create_arguments,
            build_arguments=_build_delegation_create_arguments,
            **write,  # type: ignore[arg-type]
        ),
        CommandSpec(
            domain=domain,
            resource="reminder-delegation",
            shortcut="+cancel",
            summary=(
                "End a reminder delegation now; the member gets their own reminders again. "
                "Without --yes it only shows the delegation." + _STAFF
            ),
            adapter_tool_name="ugc_reminder_delegation_cancel",
            input_schema=schema(
                {
                    "campaign_id": _CAMPAIGN_ID,
                    "id": uuid_property("Delegation ID (delegations of ugc reminder +get)."),
                    "dry_run": DRY_RUN,
                },
                ["campaign_id", "id"],
            ),
            output_schema=_direct_output_schema("delegation, and the delegations left."),
            examples=[
                f"museoncli ugc reminder-delegation +cancel --campaign-id {campaign} --id {delegation} --yes"
            ],
            add_arguments=_add_delegation_cancel_arguments,
            build_arguments=_build_delegation_cancel_arguments,
            **confirmed,  # type: ignore[arg-type]
        ),
        CommandSpec(
            domain=domain,
            resource="auto-nudge",
            shortcut="+get",
            summary=(
                "A Campaign's automatic creator nudges: which creator checks trigger one, on which "
                "days, at what local time, the next send and the latest sends." + _TEAM
            ),
            adapter_tool_name="ugc_auto_nudge_get",
            input_schema=campaign_only,
            output_schema=_direct_output_schema("checks, days, send_at, timezone, next_send_at, recent."),
            examples=[f"museoncli ugc auto-nudge +get --campaign-id {campaign}"],
            add_arguments=_add_campaign_only,
            build_arguments=_campaign,
            **read,  # type: ignore[arg-type]
        ),
        CommandSpec(
            domain=domain,
            resource="auto-nudge",
            shortcut="+update",
            summary=(
                "Change when creators get an automatic Discord nudge: the checks that trigger it "
                "(not set up, quiet, ...), the days, the creator's local send time, the fallback "
                "timezone; --off stops it. Values not passed keep theirs; fails if someone saved "
                "since your read. Without --yes it only previews." + _TEAM
            ),
            adapter_tool_name="ugc_auto_nudge_update",
            input_schema=schema(
                {
                    "campaign_id": _CAMPAIGN_ID,
                    "edits": {
                        "type": "object",
                        "description": (
                            "checks, days (mon..sun; [] is off), send_at (HH:MM), timezone."
                        ),
                    },
                    "dry_run": DRY_RUN,
                },
                ["campaign_id", "edits"],
            ),
            output_schema=_direct_output_schema("auto_nudge and changes (field, before, after)."),
            examples=[
                f"museoncli ugc auto-nudge +update --campaign-id {campaign} --check not-set-up "
                "--check quiet --day mon --day thu --send-at 10:00"
            ],
            add_arguments=_add_auto_nudge_update_arguments,
            build_arguments=_build_auto_nudge_update_arguments,
            **confirmed,  # type: ignore[arg-type]
        ),
    ]


EXECUTORS = {
    "ugc.reminder-get": direct_enveloped(_execute_get),
    "ugc.reminder-update": with_notes(_execute_update),
    "ugc.reminder-test": with_notes(_execute_test),
    "ugc.reminder-subscribe": with_notes(_execute_subscribe),
    "ugc.reminder-delegation-create": with_notes(_execute_delegation_create),
    "ugc.reminder-delegation-cancel": with_notes(_execute_delegation_cancel),
    "ugc.auto-nudge-get": direct_enveloped(_execute_auto_nudge_get),
    "ugc.auto-nudge-update": with_notes(_execute_auto_nudge_update),
}
