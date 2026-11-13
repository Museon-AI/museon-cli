"""What the board, client report, broadcast and reminder writes share.

Every write here previews before it writes. ``--dry-run`` reads the live state
and reports what would happen, writing nothing (``dry_run_reads_server``). A
command that sends something (to creators, a client or a Feishu group) or
cannot be undone also takes ``--yes``: without it the command returns the same
preview instead of failing, so the Agent always has something to show the user
before asking. Nothing here retries a write.
"""

from __future__ import annotations

import argparse
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any
from uuid import UUID

from museoncli.envelopes import direct_api_envelope
from museoncli.execution import CommandContext, Executor

Notes = tuple[Any, list[str], list[str]]


def uuid_arg(value: Any, *, flag: str) -> str:
    try:
        return str(UUID(str(value)))
    except (TypeError, ValueError):
        raise ValueError(
            f"{flag} must be a canonical UUID (e.g. 72defd40-39ad-40d3-8105-8f23a9a016da), "
            f"got {value!r}. Look the ID up first with the matching +list or +get command."
        ) from None


def add_dry_run(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--dry-run", action="store_true")


def add_confirm(parser: argparse.ArgumentParser) -> None:
    add_dry_run(parser)
    parser.add_argument("--yes", action="store_true")


def previewing(args: argparse.Namespace) -> bool:
    """True unless the user confirmed with --yes (and did not ask for --dry-run).

    Dispatch reads ``args.dry_run`` after building the arguments, so a preview
    taken for a missing --yes skips its ``confirmation_required`` gate and runs
    the executor, which reads and writes nothing.
    """
    preview = bool(getattr(args, "dry_run", False)) or not bool(getattr(args, "yes", False))
    args.dry_run = preview
    return preview


def with_notes(fn: Callable[[CommandContext], Awaitable[Notes]]) -> Executor:
    """An executor whose function returns ``(data, warnings, next_steps)``."""

    async def run(ctx: CommandContext) -> dict[str, Any]:
        data, warnings, next_steps = await fn(ctx)
        envelope = direct_api_envelope(ctx.spec.schema_name, data, site_url=ctx.cfg.site_url)
        envelope["warnings"] = [*envelope["warnings"], *warnings]
        envelope["next_steps"] = [*envelope["next_steps"], *next_steps]
        return envelope

    return run


def ask_first(what: str) -> str:
    return f"Show the user {what} and ask them to confirm before running it without --dry-run."


def ask_then_yes(what: str) -> str:
    return f"Nothing was written. Show the user {what}, ask them, then run it again with --yes."


def read_text(value: str | None, file_path: str | None, *, flag: str) -> str | None:
    if value is not None and file_path is not None:
        raise ValueError(f"Pass {flag} or {flag}-file, not both.")
    if file_path is not None:
        return Path(file_path).read_text(encoding="utf-8")
    return value


def require_organization(ctx: CommandContext) -> str:
    if not ctx.organization_id:
        raise RuntimeError(
            "missing_organization: select one with `museoncli org select` or pass --organization-id"
        )
    return ctx.organization_id


def changes(before: dict[str, Any], after: dict[str, Any], fields: list[str]) -> list[dict[str, Any]]:
    return [
        {"field": field, "before": before.get(field), "after": after.get(field)}
        for field in fields
        if before.get(field) != after.get(field)
    ]


def schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required}


def uuid_property(description: str) -> dict[str, Any]:
    return {"type": "string", "format": "uuid", "description": description}


DRY_RUN = {
    "type": "boolean",
    "default": False,
    "description": "Read the current state and show what would happen, without writing anything.",
}
