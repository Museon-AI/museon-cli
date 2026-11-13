"""Shared pieces of the UGC workbench's day-to-day write commands.

The task, enrollment, review, messaging and recruiting modules (``ugc_*``) call
the routes the web app calls (``/api/v2/ugc``), with the same compare-and-set
and idempotency inputs. Each write reads the live state on ``--dry-run``
(``dry_run_reads_server``); a command that tells the creator something, or cannot
be undone from the CLI, also needs ``--yes``, and without it answers with that
same dry run as its preview.
"""

from __future__ import annotations

import argparse
import re
import uuid as uuid_module
from collections.abc import Iterable
from typing import Any

from museoncli.domains.ugc import (
    _ask_next_step,
    _dicts,
    _get,
    _plural,
    _schema,
    _uuid,
    _uuid_property,
    _with_notes,
)
from museoncli.execution import CommandContext, compact_params
from museoncli.paging import MAX_ALL_PAGES

__all__ = [
    "CAMPAIGN_ID",
    "DRY_RUN",
    "WRITE",
    "OUTBOUND",
    "ROLE_TASK",
    "ROLE_ENROLLMENT",
    "ROLE_MESSAGE",
    "ROLE_REVIEW",
    "ROLE_COUNTING",
    "ROLE_TEAM",
    "OUTBOUND_NOTE",
    "new_key",
    "kebab",
    "same_key_next_step",
    "add_dry_run",
    "add_yes",
    "call",
    "find_paged",
    "idempotency_key",
    "uuids",
    "uuid_or_none",
    "text",
    "pick",
    "require_found",
    "_ask_next_step",
    "_dicts",
    "_get",
    "_plural",
    "_schema",
    "_uuid",
    "_uuid_property",
    "_with_notes",
]

_PAGE_LIMIT = 100

CAMPAIGN_ID = _uuid_property(
    "UGC campaign ID (from ugc campaign +list), not a campaign-monitor collection id."
)
DRY_RUN = {
    "type": "boolean",
    "default": False,
    "description": "Read the current state and show what would change, without writing anything.",
}

WRITE: dict[str, Any] = {
    "risk_level": "write",
    "execution": "direct",
    "supports_dry_run": True,
    "dry_run_reads_server": True,
}
OUTBOUND: dict[str, Any] = {
    "risk_level": "destructive",
    "execution": "direct",
    "supports_dry_run": True,
    "dry_run_reads_server": True,
    "requires_confirmation": True,
}

# Who may run it: the server decides per request; these lines only tell the Agent.
ROLE_TASK = (
    " Role: owner or admin; an operator on Campaigns they are assigned to (PM/OP); "
    "members only read."
)
ROLE_ENROLLMENT = (
    " Role: owner, admin, or an operator assigned to the Campaign (the operating team); "
    "members and Brand viewers cannot."
)
ROLE_MESSAGE = (
    " Role: owner, admin, or an operator assigned to the Campaign; members cannot message "
    "creators."
)
ROLE_REVIEW = (
    " Role: owner, admin, an operator assigned to the Campaign, or a Brand editor on a "
    "shared Campaign; members only read."
)
ROLE_COUNTING = ROLE_REVIEW
ROLE_TEAM = (
    " Role: the operating team only (owner, admin, or an operator assigned to the "
    "Campaign); Brand editors cannot."
)
OUTBOUND_NOTE = (
    " Run it with --dry-run (or without --yes, which answers with the same preview), "
    "show the user, and rerun with --yes once they agree."
)


def add_dry_run(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--dry-run", action="store_true")


def add_yes(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--yes", action="store_true")


async def call(
    ctx: CommandContext,
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    *,
    idempotency_key: str | None = None,
) -> Any:
    """One workbench write. Never retried: the caller decides what an unknown outcome means."""
    return await ctx.api_data_v2(
        ctx.cfg,
        method,
        f"/ugc{path}",
        json_body=body,
        **({"idempotency_key": idempotency_key} if idempotency_key else {}),
    )


async def find_paged(
    ctx: CommandContext,
    path: str,
    wanted: Iterable[str],
    *,
    params: dict[str, Any] | None = None,
) -> tuple[dict[str, dict[str, Any]], bool]:
    """Page a cursor list until every wanted id is seen; bounded by MAX_ALL_PAGES.

    Returns the rows found by id and whether the read reached the end (or found all).
    """
    wanted_ids = set(wanted)
    found: dict[str, dict[str, Any]] = {}
    cursor: str | None = None
    for _ in range(MAX_ALL_PAGES):
        page = await _get(
            ctx, path, compact_params({**(params or {}), "limit": _PAGE_LIMIT, "cursor": cursor})
        )
        page = page if isinstance(page, dict) else {}
        for item in _dicts(page.get("items")):
            if item.get("id") in wanted_ids:
                found[str(item["id"])] = item
        if len(found) == len(wanted_ids):
            return found, True
        cursor = page.get("next_cursor")
        if not cursor:
            return found, True
    return found, False


def require_found(
    found: dict[str, dict[str, Any]], wanted: Iterable[str], *, what: str, where: str
) -> None:
    missing = [value for value in wanted if value not in found]
    if missing:
        raise RuntimeError(
            f"not_found: {what}_not_found: no such {what.replace('_', ' ')} in {where}: "
            + ", ".join(missing)
        )


def uuids(values: Iterable[str] | None, *, flag: str, limit: int) -> list[str]:
    """Canonical, de-duplicated UUIDs in the order given."""
    result = list(dict.fromkeys(_uuid(value, flag=flag) for value in values or ()))
    if not result:
        raise ValueError(f"Pass at least one {flag}.")
    if len(result) > limit:
        raise ValueError(f"At most {limit} {flag} values per request; split the list.")
    return result


def uuid_or_none(value: str, *, flag: str) -> str | None:
    return None if value.strip().lower() == "none" else _uuid(value, flag=flag)


def text(value: str | None, *, flag: str, limit: int, required: bool = False) -> str | None:
    """Trimmed text within the server's length limit; blank is None (or refused)."""
    if value is None:
        if required:
            raise ValueError(f"{flag} is required.")
        return None
    stripped = value.strip()
    if not stripped:
        if required:
            raise ValueError(f"{flag} must not be blank.")
        return None
    if len(stripped) > limit:
        raise ValueError(f"{flag} is {len(stripped)} characters; the limit is {limit}.")
    return stripped


_KEY = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")


def idempotency_key(value: str | None) -> str | None:
    if value is None:
        return None
    key = value.strip()
    if not _KEY.match(key):
        raise ValueError(
            "--idempotency-key must be 1-128 characters of letters, digits, '_', '.', ':' or '-'."
        )
    return key


def new_key(prefix: str) -> str:
    return f"museoncli:{prefix}:{uuid_module.uuid4()}"


def pick(row: dict[str, Any] | None, *fields: str) -> dict[str, Any]:
    row = row if isinstance(row, dict) else {}
    return {field: row.get(field) for field in fields}


def kebab(value: str | None) -> str | None:
    return value.replace("_", "-") if isinstance(value, str) else value


def same_key_next_step(key: str) -> str:
    return (
        f"If the outcome is unknown (timeout, network error), retry with --idempotency-key {key} "
        "and the same text; a new key sends a second message."
    )

