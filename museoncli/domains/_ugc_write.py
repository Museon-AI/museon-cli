"""Shared pieces of the UGC workbench write commands (Campaign lifecycle, setup, Formats, personas).

Every write follows the workbench rule `ugc.py` states: the Agent runs it with
``--dry-run`` first, which reads the live state and writes nothing, shows the user
what it returned and asks before running it for real. A write carries the
compare-and-set token its route takes (``expected_status``, ``expected_updated_at``
or ``expected_version``): from ``--expected-*`` when the caller read it earlier,
otherwise from the read this command makes just before writing.
"""

from __future__ import annotations

import argparse
import json
import re
import uuid
from pathlib import Path
from typing import Any

from museoncli.domains._model import CommandSpec, Domain
from museoncli.domains._shared import _direct_output_schema
from museoncli.domains.ugc import _CAMPAIGN_ID, _DRY_RUN, _ask_next_step, _dicts, _uuid
from museoncli.execution import CommandContext

DOMAIN = Domain.UGC
NONE = "none"
CONFIRM_FIRST = (
    " The Agent runs it with --dry-run first, shows the user the result and asks "
    "before running it without --dry-run; the workbench itself asks nothing."
)
CONFIRM_YES = CONFIRM_FIRST + " Then pass --yes."
PLATFORMS = ["tiktok", "instagram", "youtube", "facebook"]
"""The posting platforms a new Campaign starts on, in the product's order (`PLATFORM_ORDER`)."""

# Example ids every spec shows.
CAMPAIGN = "11111111-1111-4111-8111-111111111111"
BRIEF = "22222222-2222-4222-8222-222222222222"
OTHER = "33333333-3333-4333-8333-333333333333"
PERSONA = "66666666-6666-4666-8666-666666666666"
USER = "77777777-7777-4777-8777-777777777777"

WRITE = {
    "risk_level": "write",
    "execution": "direct",
    "supports_dry_run": True,
    "dry_run_reads_server": True,
}
CONFIRMED_WRITE = {**WRITE, "requires_confirmation": True}
"""A write that reaches people outside (opens recruiting, sends DMs, builds a Discord server)."""
DESTRUCTIVE = {**WRITE, "risk_level": "destructive", "requires_confirmation": True}
READ = {"risk_level": "read", "execution": "direct"}


# -- requests ----------------------------------------------------------------


async def call(
    ctx: CommandContext,
    method: str,
    path: str,
    *,
    body: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
) -> Any:
    """One workbench request under `/api/v2/ugc`. Never retried here."""
    kwargs: dict[str, Any] = {}
    if body is not None:
        kwargs["json_body"] = body
    if params:
        kwargs["params"] = params
    if idempotency_key is not None:
        kwargs["idempotency_key"] = idempotency_key
    return await ctx.api_data_v2(ctx.cfg, method, f"/ugc{path}", **kwargs)


async def read_campaign(ctx: CommandContext, campaign_id: str) -> dict[str, Any]:
    """The Campaign page's one read (`CampaignView`)."""
    view = await call(ctx, "GET", f"/campaigns/{campaign_id}")
    if not isinstance(view, dict) or not isinstance(view.get("campaign"), dict):
        raise RuntimeError("not_found: campaign_not_found: no such UGC campaign")
    return view


_CAMPAIGN_LINE = (
    "id",
    "name",
    "campaign_type",
    "status",
    "monitor_collection_id",
    "product_id",
    "updated_at",
)


def campaign_line(summary: Any) -> dict[str, Any]:
    """A Campaign as these commands report it; the workspace it sits in is not shown."""
    summary = summary if isinstance(summary, dict) else {}
    return {key: summary.get(key) for key in _CAMPAIGN_LINE}


def idempotency_key(args: dict[str, Any]) -> str:
    return str(args.get("idempotency_key") or uuid.uuid4())


def retry_note(key: str) -> str:
    return (
        f"If this write's outcome is unknown (timeout, dropped connection), run it again with "
        f"--idempotency-key {key}: the workbench then returns the first result instead of "
        "creating a second one."
    )


# -- checks and diffs ---------------------------------------------------------


def check_token(name: str, current: Any, expected: Any) -> Any:
    """The CAS token to send: the caller's, refused here when the live one moved on."""
    if expected is None:
        return current
    if expected != current:
        raise RuntimeError(
            f"conflict: {name}_changed: it changed since your read ({name} is now {current!r}, "
            f"not {expected!r}). Read it again and redo the change on the current state."
        )
    return expected


def changes(before: dict[str, Any], after: dict[str, Any], fields: Any) -> list[dict[str, Any]]:
    return [
        {"field": field, "before": before.get(field), "after": after.get(field)}
        for field in fields
        if before.get(field) != after.get(field)
    ]


def nothing_to_write(what: str = "the current state") -> str:
    return f"Nothing differs from {what}; nothing was written."


def ask(what: str) -> list[str]:
    return [_ask_next_step(what)]


def optional_int(value: str | None, *, flag: str, minimum: int = 0) -> Any:
    """`None` when not passed, `NONE` sentinel cleared to null, else a whole number."""
    if value is None:
        return ...
    if value.strip().lower() == NONE:
        return None
    try:
        number = int(value)
    except ValueError:
        raise ValueError(f"{flag} must be a whole number or 'none'.") from None
    if number < minimum:
        raise ValueError(f"{flag} must be at least {minimum}.")
    return number


def optional_text(value: str | None) -> Any:
    """`...` when not passed; blank or `none` clears it to null."""
    if value is None:
        return ...
    text = value.strip()
    return None if not text or text.lower() == NONE else text


def json_value(value: str | None, *, flag: str) -> Any:
    if value is None:
        return ...
    try:
        return json.loads(value)
    except ValueError:
        raise ValueError(f"{flag} must be valid JSON.") from None


def json_object(value: str | None, *, flag: str) -> dict[str, Any] | None:
    parsed = json_value(value, flag=flag)
    if parsed is ...:
        return None
    if not isinstance(parsed, dict):
        raise ValueError(f"{flag} must be a JSON object.")
    return parsed


def read_text(path: str) -> str:
    return Path(path).expanduser().read_text(encoding="utf-8")


def uuids(values: list[str] | None, *, flag: str) -> list[str]:
    return list(dict.fromkeys(_uuid(value, flag=flag) for value in values or []))


def passed(values: dict[str, Any]) -> dict[str, Any]:
    """Drop the `...` placeholders of flags that were not passed."""
    return {key: value for key, value in values.items() if value is not ...}


SNOWFLAKE = re.compile(r"^[0-9]{17,20}$")


# -- arguments ---------------------------------------------------------------


def add_campaign_id(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--campaign-id", required=True)


def add_dry_run(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--dry-run", action="store_true")


def add_yes(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--yes", action="store_true")


def add_idempotency_key(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--idempotency-key")


def build_idempotency_key(args: argparse.Namespace) -> dict[str, Any]:
    key = (args.idempotency_key or "").strip()
    if args.idempotency_key is not None and not key:
        raise ValueError("--idempotency-key must not be blank.")
    if len(key) > 128:
        raise ValueError("--idempotency-key must be at most 128 characters.")
    return {"idempotency_key": key} if key else {}


# -- schemas -----------------------------------------------------------------


def uuid_property(description: str) -> dict[str, Any]:
    return {"type": "string", "format": "uuid", "description": description}


def schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required}


CAMPAIGN_ID = _CAMPAIGN_ID
DRY_RUN = _DRY_RUN
IDEMPOTENCY_KEY = {
    "type": "string",
    "maxLength": 128,
    "description": (
        "Key for this create; rerun with the same key after an unknown outcome to get the "
        "first result back. A fresh one is made when left out."
    ),
}
EXPECTED_UPDATED_AT = {
    "type": "string",
    "description": (
        "updated_at from your latest read (the dry run returns it); the write fails instead of "
        "overwriting a newer change. Left out, the value this command reads first is used."
    ),
}


def output(description: str) -> dict[str, Any]:
    return _direct_output_schema(description)


def spec(
    *,
    resource: str,
    shortcut: str,
    summary: str,
    adapter: str,
    properties: dict[str, Any],
    required: list[str],
    output_description: str,
    examples: list[str],
    add_arguments: Any,
    build_arguments: Any,
    kind: dict[str, Any],
) -> CommandSpec:
    return CommandSpec(
        domain=DOMAIN,
        resource=resource,
        shortcut=shortcut,
        summary=summary,
        adapter_tool_name=adapter,
        input_schema=schema(properties, required),
        output_schema=output(output_description),
        examples=examples,
        add_arguments=add_arguments,
        build_arguments=build_arguments,
        **kind,
    )


__all__ = [
    "CAMPAIGN",
    "CAMPAIGN_ID",
    "CONFIRMED_WRITE",
    "CONFIRM_FIRST",
    "CONFIRM_YES",
    "DESTRUCTIVE",
    "DRY_RUN",
    "EXPECTED_UPDATED_AT",
    "IDEMPOTENCY_KEY",
    "NONE",
    "PLATFORMS",
    "READ",
    "WRITE",
    "_dicts",
    "_uuid",
]
