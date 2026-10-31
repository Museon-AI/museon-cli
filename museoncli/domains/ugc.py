"""UGC workbench commands: campaigns, roster, briefs, creatives and assignments.

Every call goes straight to the UGC workbench (``/api/v2/ugc``), which
authorizes the CLI's API key with the same workspace role as the web app. The
ids are UGC campaign ids (``marketing_campaigns.id``), not campaign-monitor
collection ids.

The workbench has no confirmation step of its own. The agreed rule is that the
Agent runs a write with ``--dry-run`` first, shows the user what it returned and
asks before writing. So every write here except the file upload reads the live
state on ``--dry-run`` (``dry_run_reads_server``) and writes nothing.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx

from museoncli.domains._model import CommandSpec, Domain
from museoncli.domains._shared import _direct_output_schema, dekebab, kebab_choices
from museoncli.envelopes import direct_api_envelope
from museoncli.execution import CommandContext, Executor, compact_params, direct_enveloped
from museoncli.paging import MAX_ALL_PAGES

_PAGE_LIMIT = 100
"""The workbench's largest page (`MAX_PAGE_LIMIT`)."""

CAMPAIGN_STATUSES = ["draft", "active", "paused", "complete", "archived"]
ENROLLMENT_STATUSES = [
    "participating",
    "pending",
    "rejected",
    "onboarding",
    "active",
    "paused",
    "removed",
]
BRIEF_STATUSES = ["active", "archived"]
CREATIVE_REVIEW_STATUSES = ["needs_review", "approved", "rejected", "excluded"]
ASSIGNMENT_PRIORITIES = ["high", "normal", "low"]
WITHDRAWN = "withdrawn"
DOCUMENT_FIELDS = ("title", "content", "references", "required_caption", "require_ad_disclosure")
CAPTION_RULE_FIELDS = {"required_caption", "require_ad_disclosure"}
NONE = "none"

_CONFIRM_FIRST = (
    " The Agent runs it with --dry-run first, shows the user the result and asks "
    "before running it without --dry-run; the workbench itself asks nothing."
)


# -- small helpers -----------------------------------------------------------


def _uuid(value: Any, *, flag: str) -> str:
    try:
        return str(UUID(str(value)))
    except (TypeError, ValueError):
        raise ValueError(
            f"{flag} must be a canonical UUID (e.g. 72defd40-39ad-40d3-8105-8f23a9a016da), "
            f"got {value!r}. Look the ID up first with the matching +list command."
        ) from None


def _plural(count: int, one: str, many: str) -> str:
    return f"{count} {one if count == 1 else many}"


async def _get(ctx: CommandContext, path: str, params: dict[str, Any] | None = None) -> Any:
    return await ctx.api_data_v2(ctx.cfg, "GET", f"/ugc{path}", params=params)


async def _send(ctx: CommandContext, method: str, path: str, body: dict[str, Any]) -> Any:
    return await ctx.api_data_v2(ctx.cfg, method, f"/ugc{path}", json_body=body)


def _dicts(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


async def _campaign_briefs(ctx: CommandContext, campaign_id: str) -> list[dict[str, Any]]:
    """Every brief the campaign links, archived ones included, in one read."""
    return _dicts(await _get(ctx, f"/campaigns/{campaign_id}/briefs"))


async def _campaign_assignments(
    ctx: CommandContext,
    campaign_id: str,
    *,
    enrollment_ids: list[str] | None = None,
    until: Callable[[dict[str, Any]], bool] | None = None,
) -> tuple[list[dict[str, Any]], bool]:
    """Every assignment of the campaign, page after page; `until` stops at a match.

    Returns the rows and whether the read reached the end (or the match).
    """
    rows: list[dict[str, Any]] = []
    cursor: str | None = None
    for _ in range(MAX_ALL_PAGES):
        page = await _get(
            ctx,
            f"/campaigns/{campaign_id}/assignments",
            compact_params(
                {"limit": _PAGE_LIMIT, "cursor": cursor, "enrollment_ids": enrollment_ids}
            ),
        )
        items = _dicts(page.get("items") if isinstance(page, dict) else None)
        rows.extend(items)
        if until is not None and any(until(item) for item in items):
            return rows, True
        cursor = page.get("next_cursor") if isinstance(page, dict) else None
        if not cursor:
            return rows, True
    return rows, False


def _incomplete_warning(rows: list[dict[str, Any]]) -> str:
    return (
        f"Stopped after {MAX_ALL_PAGES} pages ({len(rows)} assignments); the counts "
        "below miss the rest."
    )


def _live(row: dict[str, Any]) -> bool:
    return row.get("status") != WITHDRAWN


def _envelope(
    ctx: CommandContext, data: Any, warnings: list[str], next_steps: list[str]
) -> dict[str, Any]:
    envelope = direct_api_envelope(
        ctx.spec.schema_name, ctx.workspace_id, data, site_url=ctx.cfg.site_url
    )
    envelope["warnings"] = [*envelope["warnings"], *warnings]
    envelope["next_steps"] = [*envelope["next_steps"], *next_steps]
    return envelope


def _with_notes(
    fn: Callable[[CommandContext], Any],
) -> Executor:
    """An executor whose function returns `(data, warnings, next_steps)`."""

    async def run(ctx: CommandContext) -> dict[str, Any]:
        data, warnings, next_steps = await fn(ctx)
        return _envelope(ctx, data, warnings, next_steps)

    return run


def _ask_next_step(what: str) -> str:
    return f"Show the user {what} and ask them to confirm before running it without --dry-run."


# -- brief documents ---------------------------------------------------------


def write_reference(reference: dict[str, Any]) -> dict[str, Any]:
    """A version's reference in the shape the document write takes back.

    A version stores a library file as `{kind, url}`; the write names it as a
    `stored` reference, exactly as the web editor does (`lib/ugc/brief-document.ts`).
    """
    if "type" in reference:
        shaped = dict(reference)
    else:
        shaped = {
            "type": "stored",
            "kind": reference.get("kind"),
            "url": reference.get("url"),
            "note": reference.get("note"),
            "name": reference.get("name"),
        }
    return {key: value for key, value in shaped.items() if value is not None}


def brief_document(view: dict[str, Any]) -> dict[str, Any]:
    """The editable document of a brief's current version (`BriefDocumentWrite` fields).

    A legacy `reference_video_url` becomes a link reference, as the web editor
    turns it into one on its first save.
    """
    brief = view.get("brief") if isinstance(view.get("brief"), dict) else {}
    current = view.get("current") if isinstance(view.get("current"), dict) else {}
    references = [write_reference(item) for item in _dicts(current.get("references"))]
    legacy = current.get("reference_video_url")
    if legacy and not any(
        item.get("type") == "link" and item.get("url") == legacy for item in references
    ):
        references.append({"type": "link", "url": legacy})
    return {
        "title": brief.get("title") or "",
        "content": current.get("content") or "",
        "references": references,
        "required_caption": current.get("required_caption"),
        "require_ad_disclosure": bool(current.get("require_ad_disclosure")),
    }


def merge_document(
    current: dict[str, Any], edits: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """The current document with only the edited fields replaced, and what changed."""
    merged = dict(current)
    changes: list[dict[str, Any]] = []
    for field in DOCUMENT_FIELDS:
        if field not in edits:
            continue
        value = edits[field]
        if field == "references":
            value = [write_reference(item) for item in value]
        merged[field] = value
        if value != current.get(field):
            changes.append({"field": field, "before": current.get(field), "after": value})
    return merged, changes


def _brief_line(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        key: summary.get(key)
        for key in (
            "id",
            "title",
            "status",
            "persona_id",
            "current_version",
            "description",
            "attachment_count",
            "updated_at",
        )
    }


# -- progress ----------------------------------------------------------------

_ASSIGNMENT_ROW_FIELDS = (
    "id",
    "enrollment_id",
    "status",
    "videos_counted",
    "video_limit",
    "due_at",
    "priority",
    "note",
)


def brief_progress(
    briefs: list[dict[str, Any]],
    assignments: list[dict[str, Any]],
    *,
    brief_id: str | None = None,
) -> list[dict[str, Any]]:
    """Per brief: its live (not withdrawn) assignments and their raw counts.

    `video_limit_total` adds up the limits that are set; `unlimited_assignments`
    counts the live assignments with no limit, which the total cannot hold.
    """
    by_brief: dict[str, list[dict[str, Any]]] = {}
    for row in assignments:
        by_brief.setdefault(str(row.get("brief_id")), []).append(row)
    order = [str(item.get("id")) for item in briefs]
    order += [key for key in by_brief if key not in order]
    titles = {str(item.get("id")): item for item in briefs}
    output: list[dict[str, Any]] = []
    for key in order:
        if brief_id is not None and key != brief_id:
            continue
        rows = by_brief.get(key, [])
        live = [row for row in rows if _live(row)]
        limits = [row.get("video_limit") for row in live]
        brief = titles.get(key, {})
        output.append(
            {
                "brief_id": key,
                "title": brief.get("title"),
                "status": brief.get("status"),
                "current_version": brief.get("current_version"),
                "assignments": len(live),
                "withdrawn_assignments": len(rows) - len(live),
                "videos_counted": sum(int(row.get("videos_counted") or 0) for row in live),
                "video_limit_total": sum(int(limit) for limit in limits if limit is not None),
                "unlimited_assignments": sum(1 for limit in limits if limit is None),
                "rows": [{field: row.get(field) for field in _ASSIGNMENT_ROW_FIELDS} for row in live],
            }
        )
    return output


# -- executors: reads ------------------------------------------------------


async def _execute_campaign_list(ctx: CommandContext) -> Any:
    if not ctx.workspace_id:
        raise RuntimeError("missing_workspace")
    args = ctx.arguments
    return await _get(
        ctx,
        f"/workspaces/{ctx.workspace_id}/campaigns",
        compact_params(
            {
                "campaign_type": "ugc",
                "status": args.get("status"),
                "cursor": args.get("cursor"),
                "limit": args.get("page_size"),
            }
        ),
    )


def _enrollment_row(item: dict[str, Any]) -> dict[str, Any]:
    creator = item.get("creator") if isinstance(item.get("creator"), dict) else {}
    return {
        "enrollment_id": item.get("id"),
        "status": item.get("status"),
        "persona_id": item.get("persona_id"),
        "ugc_creator_id": creator.get("id"),
        "display_name": creator.get("display_name"),
        "accounts": [
            {
                "platform": account.get("platform"),
                "username": account.get("username"),
                "status": account.get("status"),
            }
            for account in _dicts(item.get("accounts"))
        ],
    }


async def _execute_enrollment_list(ctx: CommandContext) -> Any:
    args = ctx.arguments
    page = await _get(
        ctx,
        f"/campaigns/{args['campaign_id']}/enrollments",
        compact_params(
            {
                "status": args.get("status"),
                "q": args.get("search"),
                "cursor": args.get("cursor"),
                "limit": args.get("page_size"),
            }
        ),
    )
    page = page if isinstance(page, dict) else {}
    return {
        "items": [_enrollment_row(item) for item in _dicts(page.get("items"))],
        "next_cursor": page.get("next_cursor"),
    }


async def _execute_brief_list(ctx: CommandContext) -> Any:
    args = ctx.arguments
    briefs = await _campaign_briefs(ctx, args["campaign_id"])
    status = args.get("status")
    return {
        "items": [
            _brief_line(item) for item in briefs if status is None or item.get("status") == status
        ]
    }


async def _execute_brief_get(ctx: CommandContext) -> Any:
    args = ctx.arguments
    view = await _get(ctx, f"/campaigns/{args['campaign_id']}/brief-documents/{args['id']}")
    summary = view.get("brief") if isinstance(view.get("brief"), dict) else {}
    wanted = args.get("version") or summary.get("current_version")
    version = next(
        (item for item in _dicts(view.get("versions")) if item.get("version") == wanted), None
    )
    if version is None:
        raise RuntimeError(f"not_found: brief_version_not_found: the brief has no version {wanted}")
    return {
        "brief": summary,
        "version": version,
        "is_current": wanted == summary.get("current_version"),
        "document": brief_document(view),
        "copy_required": bool(view.get("copy_required")),
        "media": view.get("media") or [],
    }


async def _execute_brief_progress(ctx: CommandContext) -> Any:
    args = ctx.arguments
    campaign_id = args["campaign_id"]
    briefs = await _campaign_briefs(ctx, campaign_id)
    assignments, complete = await _campaign_assignments(ctx, campaign_id)
    rows = brief_progress(briefs, assignments, brief_id=args.get("brief_id"))
    if args.get("brief_id") and not rows:
        raise RuntimeError("not_found: brief_not_found: the campaign does not link this brief")
    warnings = [] if complete else [_incomplete_warning(assignments)]
    return {"briefs": rows}, warnings, []


def filter_creatives(creatives: list[dict[str, Any]], brief_id: str | None) -> list[dict[str, Any]]:
    """`none` keeps the creatives without a brief; a UUID keeps that brief's."""
    if brief_id is None:
        return creatives
    wanted = None if brief_id == NONE else brief_id
    return [item for item in creatives if item.get("brief_id") == wanted]


async def _execute_creative_list(ctx: CommandContext) -> Any:
    args = ctx.arguments
    creatives = _dicts(
        await _get(
            ctx,
            f"/campaigns/{args['campaign_id']}/creatives",
            compact_params({"review_status": args.get("review_status")}),
        )
    )
    items = filter_creatives(creatives, args.get("brief_id"))
    return {"items": items, "count": len(items)}


# -- executors: writes -------------------------------------------------------


async def _execute_creative_set_brief(ctx: CommandContext) -> Any:
    args = ctx.arguments
    campaign_id, creative_id, brief_id = args["campaign_id"], args["id"], args["brief_id"]
    creatives = _dicts(await _get(ctx, f"/campaigns/{campaign_id}/creatives"))
    creative = next((item for item in creatives if item.get("id") == creative_id), None)
    if creative is None:
        raise RuntimeError("not_found: creative_not_found: no such creative in this campaign")
    briefs = {item.get("id"): item for item in await _campaign_briefs(ctx, campaign_id)}
    before = creative.get("brief_id")

    def brief_ref(value: Any) -> dict[str, Any]:
        return {"brief_id": value, "title": (briefs.get(value) or {}).get("title")}

    data: dict[str, Any] = {
        "dry_run": args["dry_run"],
        "creative": {
            key: creative.get(key)
            for key in ("id", "ugc_creator_id", "brief_assignment_id", "review_status")
        },
        "before": brief_ref(before),
        "after": brief_ref(brief_id),
    }
    if before == brief_id:
        return data, ["The creative already cites this brief; nothing was written."], []
    warnings: list[str] = []
    if creative.get("brief_assignment_id"):
        warnings.append(
            "This creative was delivered against an assignment and keeps that assignment's "
            "brief; the workbench refuses the change (creative_brief_from_assignment)."
        )
    if brief_id not in briefs:
        warnings.append(
            "The campaign does not link this brief; the workbench refuses it "
            "(brief_not_in_campaign)."
        )
    if args["dry_run"]:
        return data, warnings, [_ask_next_step("the brief before and after")]
    data["creative"] = await _send(
        ctx,
        "PUT",
        f"/creatives/{creative_id}/brief",
        {"brief_id": brief_id, "expected_brief_id": before},
    )
    return data, warnings, []


async def _execute_creative_apply_default_briefs(ctx: CommandContext) -> Any:
    args = ctx.arguments
    dry_run = bool(args["dry_run"])
    result = await _send(
        ctx,
        "POST",
        f"/campaigns/{args['campaign_id']}/creatives/default-briefs",
        {"dry_run": dry_run},
    )
    result = result if isinstance(result, dict) else {}
    warnings: list[str] = []
    ambiguous = int(result.get("ambiguous") or 0)
    without = int(result.get("without_assignment") or 0)
    if ambiguous:
        warnings.append(
            f"{_plural(ambiguous, 'brief-less creative has', 'brief-less creatives have')} "
            "more than one live assignment, so no default applies; link them one at a time "
            "with +set-brief."
        )
    if without:
        warnings.append(
            f"{_plural(without, 'brief-less creative has', 'brief-less creatives have')} "
            "no live assignment in this campaign; link them one at a time with +set-brief."
        )
    linked = _dicts(result.get("linked"))
    if linked:
        # The route answers ids only; one read of the brief list names them.
        titles = {
            item.get("id"): item.get("title")
            for item in await _campaign_briefs(ctx, args["campaign_id"])
        }
        result["linked"] = [
            {**item, "brief_title": titles.get(item.get("brief_id"))} for item in linked
        ]
    if dry_run and linked:
        return result, warnings, [_ask_next_step("which creatives would be linked to which brief")]
    if not linked:
        warnings.append("No creative gets a default brief; nothing was written.")
    return result, warnings, []


async def _execute_brief_update(ctx: CommandContext) -> Any:
    args = ctx.arguments
    campaign_id, brief_id = args["campaign_id"], args["id"]
    dry_run, notify = bool(args["dry_run"]), bool(args["notify"])
    path = f"/campaigns/{campaign_id}/brief-documents/{brief_id}"
    view = await _get(ctx, path)
    summary = view.get("brief") if isinstance(view.get("brief"), dict) else {}
    current_version = summary.get("current_version")
    if current_version != args["expected_version"]:
        raise RuntimeError(
            f"conflict: brief_version_conflict: the brief is at version {current_version}, "
            f"not {args['expected_version']}. Read it again with +get and redo the edit on "
            "that version."
        )
    merged, changes = merge_document(brief_document(view), args["edits"])
    assignments, complete = await _campaign_assignments(ctx, campaign_id)
    live = sum(1 for row in assignments if row.get("brief_id") == brief_id and _live(row))
    data: dict[str, Any] = {
        "dry_run": dry_run,
        "brief": {"id": brief_id, "title": summary.get("title"), "current_version": current_version},
        "changes": changes,
        "live_assignments": live,
    }
    warnings = [] if complete else [_incomplete_warning(assignments)]
    if view.get("copy_required"):
        warnings.append(
            "Another campaign also uses this brief, so the workbench refuses to edit it here "
            "(brief_shared_outside_campaign); it has to be copied into this campaign first."
        )
    if not changes:
        warnings.append("Nothing differs from the current version; nothing was written.")
        return data, warnings, []
    if any(change["field"] in CAPTION_RULE_FIELDS for change in changes):
        warnings.append(
            "The caption rule changes: posts collected from now on are checked against the "
            "new caption rule."
        )
    data["notify"] = notify
    creators = _plural(live, "creator is", "creators are")
    if dry_run:
        if live and not notify:
            warnings.append(
                f"{creators} working on this brief; without --notify they will not be told "
                "it changed."
            )
        ask = (
            "Show the user these changes and ask them to confirm, and whether to notify the "
            "creators working on this brief, before running it without --dry-run."
            if live
            else _ask_next_step("these changes")
        )
        return data, warnings, [ask]
    body: dict[str, Any] = {**merged, "expected_version": current_version}
    if notify:
        # Sent only when asked: a workbench without the field still takes a plain edit.
        body["notify"] = True
    updated = await _send(ctx, "PATCH", path, body)
    written = updated.get("brief") if isinstance(updated, dict) else None
    if isinstance(written, dict):
        data["brief"] = {
            "id": written.get("id"),
            "title": written.get("title"),
            "current_version": written.get("current_version"),
        }
    if live and not notify:
        warnings.append(f"{creators} working on this brief and were not told it changed.")
    return data, warnings, []


async def _execute_brief_upload_media(ctx: CommandContext) -> Any:
    args = ctx.arguments
    path = Path(args["file"])
    session = await _send(
        ctx,
        "POST",
        f"/campaigns/{args['campaign_id']}/brief-media/uploads",
        {
            "content_type": args["content_type"],
            "size_bytes": args["size_bytes"],
            "filename": args["filename"],
        },
    )
    if not isinstance(session, dict) or not session.get("upload_url") or not session.get("url"):
        raise RuntimeError("brief_media_upload_failed: the workbench returned no upload session")
    await _put_file(
        str(session["upload_url"]),
        path,
        content_type=str(session.get("content_type") or ""),
        size_bytes=int(args["size_bytes"]),
    )
    reference: dict[str, Any] = {"type": "stored", "kind": session.get("kind"), "url": session["url"]}
    if session.get("kind") == "file":
        reference["name"] = args["filename"]
    data = {
        "reference": reference,
        "kind": session.get("kind"),
        "url": session["url"],
        "size_bytes": args["size_bytes"],
    }
    return data, [], [
        "Add data.reference to the brief's current references (document.references of "
        "+get) and pass the whole list as --references-json to +update."
    ]


async def _file_chunks(path: Path) -> AsyncIterator[bytes]:
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            yield chunk


async def _put_file(url: str, path: Path, *, content_type: str, size_bytes: int) -> None:
    """Send the bytes to the upload session. No Museon credential goes to it."""
    async with httpx.AsyncClient(timeout=None) as client:
        response = await client.put(
            url,
            content=_file_chunks(path),
            headers={"Content-Type": content_type, "Content-Length": str(size_bytes)},
        )
    if response.status_code >= 400:
        raise RuntimeError(f"brief_media_upload_failed: HTTP {response.status_code}")


async def _execute_assignment_create(ctx: CommandContext) -> Any:
    args = ctx.arguments
    campaign_id, brief_id = args["campaign_id"], args["brief_id"]
    enrollment_ids: list[str] = args["enrollment_ids"]
    terms = {key: args.get(key) for key in ("due_at", "video_limit", "note", "priority")}
    body = {"brief_id": brief_id, "enrollment_ids": enrollment_ids, **compact_params(terms)}
    if not args["dry_run"]:
        return await _send(ctx, "POST", f"/campaigns/{campaign_id}/assignments", body), [], []
    briefs = {item.get("id"): item for item in await _campaign_briefs(ctx, campaign_id)}
    existing, _ = await _campaign_assignments(ctx, campaign_id, enrollment_ids=enrollment_ids)
    held = {row.get("enrollment_id"): row for row in existing if row.get("brief_id") == brief_id}
    brief = briefs.get(brief_id) or {}
    data = {
        "dry_run": True,
        "brief": {"id": brief_id, "title": brief.get("title"), "status": brief.get("status")},
        "terms": terms,
        "enrollments": [
            {
                "enrollment_id": enrollment_id,
                "existing_assignment": (
                    {"id": held[enrollment_id].get("id"), "status": held[enrollment_id].get("status")}
                    if enrollment_id in held
                    else None
                ),
            }
            for enrollment_id in enrollment_ids
        ],
    }
    warnings: list[str] = []
    if not brief:
        warnings.append(
            "The campaign does not link this brief; the workbench refuses the whole request."
        )
    holding = sum(1 for row in held.values() if _live(row))
    if holding:
        warnings.append(
            f"{_plural(holding, 'creator already holds', 'creators already hold')} this brief "
            "(not withdrawn); the workbench answers brief_already_assigned for them."
        )
    return data, warnings, [_ask_next_step("the brief, the terms and who would get it")]


async def _find_assignment(ctx: CommandContext) -> dict[str, Any]:
    args = ctx.arguments
    assignment_id = args["id"]
    rows, _ = await _campaign_assignments(
        ctx, args["campaign_id"], until=lambda row: row.get("id") == assignment_id
    )
    found = next((row for row in rows if row.get("id") == assignment_id), None)
    if found is None:
        raise RuntimeError("not_found: assignment_not_found: no such assignment in this campaign")
    return found


_TERM_FIELDS = ("due_at", "video_limit", "note", "priority")


async def _execute_assignment_update_terms(ctx: CommandContext) -> Any:
    args = ctx.arguments
    assignment = await _find_assignment(ctx)
    before = {field: assignment.get(field) for field in _TERM_FIELDS}
    after = {**before, **args["edits"]}
    changes = [
        {"field": field, "before": before[field], "after": after[field]}
        for field in _TERM_FIELDS
        if field in args["edits"] and after[field] != before[field]
    ]
    data: dict[str, Any] = {
        "dry_run": args["dry_run"],
        "assignment": {
            key: assignment.get(key) for key in ("id", "enrollment_id", "brief_id", "status")
        },
        "changes": changes,
    }
    if not changes:
        return data, ["Nothing differs from the current terms; nothing was written."], []
    warnings = ["Saving sends the creator one updated Brief card."]
    if args["dry_run"]:
        return data, warnings, [_ask_next_step("these changes")]
    data["assignment"] = await _send(ctx, "PUT", f"/assignments/{args['id']}/terms", after)
    return data, [], []


async def _execute_assignment_withdraw(ctx: CommandContext) -> Any:
    args = ctx.arguments
    assignment = await _find_assignment(ctx)
    data: dict[str, Any] = {
        "dry_run": args["dry_run"],
        "assignment": {
            key: assignment.get(key)
            for key in ("id", "enrollment_id", "brief_id", "status", "videos_counted")
        },
    }
    if assignment.get("status") == WITHDRAWN:
        return data, ["The assignment is already withdrawn; nothing was written."], []
    if args["dry_run"]:
        return data, [], [_ask_next_step("which creator loses which brief")]
    data["assignment"] = await _send(
        ctx,
        "POST",
        f"/assignments/{args['id']}/withdraw",
        {"expected_status": assignment.get("status")},
    )
    return data, [], []


# -- arguments ---------------------------------------------------------------


def _add_campaign_id(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--campaign-id", required=True)


def _add_cursor_paging(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--cursor")
    parser.add_argument("--page-size", type=int, default=50)


def _add_dry_run(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--dry-run", action="store_true")


def _campaign_args(args: argparse.Namespace) -> dict[str, Any]:
    return {"campaign_id": args.campaign_id}


def _page_size(args: argparse.Namespace) -> int:
    if not 1 <= args.page_size <= _PAGE_LIMIT:
        raise ValueError(f"--page-size must be between 1 and {_PAGE_LIMIT}.")
    return int(args.page_size)


def _add_campaign_list_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--workspace-id")
    parser.add_argument("--status", choices=CAMPAIGN_STATUSES)
    _add_cursor_paging(parser)


def _build_campaign_list_arguments(args: argparse.Namespace) -> dict[str, Any]:
    return compact_params(
        {
            "workspace_id": args.workspace_id,
            "status": args.status,
            "cursor": args.cursor,
            "page_size": _page_size(args),
        }
    )


def _add_enrollment_list_arguments(parser: argparse.ArgumentParser) -> None:
    _add_campaign_id(parser)
    parser.add_argument("--status", choices=ENROLLMENT_STATUSES)
    parser.add_argument("--search")
    _add_cursor_paging(parser)


def _build_enrollment_list_arguments(args: argparse.Namespace) -> dict[str, Any]:
    return compact_params(
        {
            **_campaign_args(args),
            "status": args.status,
            "search": args.search,
            "cursor": args.cursor,
            "page_size": _page_size(args),
        }
    )


def _add_brief_list_arguments(parser: argparse.ArgumentParser) -> None:
    _add_campaign_id(parser)
    parser.add_argument("--status", choices=BRIEF_STATUSES)


def _build_brief_list_arguments(args: argparse.Namespace) -> dict[str, Any]:
    return compact_params({**_campaign_args(args), "status": args.status})


def _add_brief_get_arguments(parser: argparse.ArgumentParser) -> None:
    _add_campaign_id(parser)
    parser.add_argument("--id", required=True)
    parser.add_argument("--version", type=int)


def _build_brief_get_arguments(args: argparse.Namespace) -> dict[str, Any]:
    return compact_params({**_campaign_args(args), "id": args.id, "version": args.version})


def _add_brief_progress_arguments(parser: argparse.ArgumentParser) -> None:
    _add_campaign_id(parser)
    parser.add_argument("--brief-id")


def _build_brief_progress_arguments(args: argparse.Namespace) -> dict[str, Any]:
    brief_id = _uuid(args.brief_id, flag="--brief-id") if args.brief_id else None
    return compact_params({**_campaign_args(args), "brief_id": brief_id})


def _add_creative_list_arguments(parser: argparse.ArgumentParser) -> None:
    _add_campaign_id(parser)
    parser.add_argument("--review-status", choices=kebab_choices(CREATIVE_REVIEW_STATUSES))
    parser.add_argument("--brief-id")


def _build_creative_list_arguments(args: argparse.Namespace) -> dict[str, Any]:
    brief_id = args.brief_id
    if brief_id is not None and brief_id != NONE:
        brief_id = _uuid(brief_id, flag="--brief-id")
    return compact_params(
        {
            **_campaign_args(args),
            "review_status": dekebab(args.review_status),
            "brief_id": brief_id,
        }
    )


def _add_creative_set_brief_arguments(parser: argparse.ArgumentParser) -> None:
    _add_campaign_id(parser)
    parser.add_argument("--id", required=True)
    parser.add_argument("--brief-id", required=True)
    _add_dry_run(parser)


def _build_creative_set_brief_arguments(args: argparse.Namespace) -> dict[str, Any]:
    return {
        **_campaign_args(args),
        "id": _uuid(args.id, flag="--id"),
        "brief_id": _uuid(args.brief_id, flag="--brief-id"),
        "dry_run": bool(args.dry_run),
    }


def _add_campaign_write_arguments(parser: argparse.ArgumentParser) -> None:
    _add_campaign_id(parser)
    _add_dry_run(parser)


def _build_campaign_write_arguments(args: argparse.Namespace) -> dict[str, Any]:
    return {**_campaign_args(args), "dry_run": bool(args.dry_run)}


def _add_brief_update_arguments(parser: argparse.ArgumentParser) -> None:
    _add_campaign_id(parser)
    parser.add_argument("--id", required=True)
    parser.add_argument("--expected-version", type=int, required=True)
    parser.add_argument("--title")
    content = parser.add_mutually_exclusive_group()
    content.add_argument("--content")
    content.add_argument("--content-file")
    parser.add_argument("--references-json")
    parser.add_argument("--required-caption")
    parser.add_argument(
        "--require-ad-disclosure", action=argparse.BooleanOptionalAction, default=None
    )
    parser.add_argument("--notify", action="store_true")
    _add_dry_run(parser)


def _references(value: str) -> list[dict[str, Any]]:
    try:
        parsed = json.loads(value)
    except ValueError as exc:
        raise ValueError("--references-json must be valid JSON.") from exc
    if not isinstance(parsed, list) or not all(isinstance(item, dict) for item in parsed):
        raise ValueError("--references-json must be a JSON array of reference objects.")
    return parsed


def _build_brief_update_arguments(args: argparse.Namespace) -> dict[str, Any]:
    edits: dict[str, Any] = {}
    if args.title is not None:
        edits["title"] = args.title
    if args.content is not None:
        edits["content"] = args.content
    if args.content_file is not None:
        edits["content"] = Path(args.content_file).expanduser().read_text(encoding="utf-8")
    if args.references_json is not None:
        edits["references"] = _references(args.references_json)
    if args.required_caption is not None:
        edits["required_caption"] = args.required_caption.strip() or None
    if args.require_ad_disclosure is not None:
        edits["require_ad_disclosure"] = bool(args.require_ad_disclosure)
    if not edits:
        raise ValueError(
            "Pass at least one field to change: --title, --content/--content-file, "
            "--references-json, --required-caption or --[no-]require-ad-disclosure."
        )
    return {
        **_campaign_args(args),
        "id": _uuid(args.id, flag="--id"),
        "expected_version": args.expected_version,
        "edits": edits,
        "notify": bool(args.notify),
        "dry_run": bool(args.dry_run),
    }


def _add_brief_upload_media_arguments(parser: argparse.ArgumentParser) -> None:
    _add_campaign_id(parser)
    parser.add_argument("--file", required=True)
    _add_dry_run(parser)


def _build_brief_upload_media_arguments(args: argparse.Namespace) -> dict[str, Any]:
    path = Path(args.file).expanduser()
    if not path.is_file():
        raise ValueError(f"--file is not a readable file: {path}")
    size = path.stat().st_size
    if size < 1:
        raise ValueError("--file is empty.")
    return {
        **_campaign_args(args),
        "file": str(path),
        "filename": path.name,
        "size_bytes": size,
        # Empty for a type the system does not know: the workbench then goes by the extension.
        "content_type": mimetypes.guess_type(path.name)[0] or "",
    }


def _optional_int(value: str, *, flag: str) -> int | None:
    if value.strip().lower() == NONE:
        return None
    try:
        return int(value)
    except ValueError:
        raise ValueError(f"{flag} must be a whole number or 'none'.") from None


def _add_terms_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--video-limit")
    parser.add_argument("--due-at")
    parser.add_argument("--note")
    parser.add_argument("--priority", choices=ASSIGNMENT_PRIORITIES)


def _terms(args: argparse.Namespace) -> dict[str, Any]:
    """Only the terms the caller passed; `none` (or a blank note) clears one."""
    edits: dict[str, Any] = {}
    if args.video_limit is not None:
        edits["video_limit"] = _optional_int(args.video_limit, flag="--video-limit")
    if args.due_at is not None:
        edits["due_at"] = None if args.due_at.strip().lower() == NONE else args.due_at
    if args.note is not None:
        edits["note"] = args.note.strip() or None
    if args.priority is not None:
        edits["priority"] = args.priority
    return edits


def _add_assignment_create_arguments(parser: argparse.ArgumentParser) -> None:
    _add_campaign_id(parser)
    parser.add_argument("--brief-id", required=True)
    parser.add_argument("--enrollment-id", action="append", dest="enrollment_ids", required=True)
    _add_terms_arguments(parser)
    _add_dry_run(parser)


def _build_assignment_create_arguments(args: argparse.Namespace) -> dict[str, Any]:
    enrollment_ids = list(
        dict.fromkeys(_uuid(value, flag="--enrollment-id") for value in args.enrollment_ids)
    )
    if len(enrollment_ids) > 200:
        raise ValueError("At most 200 --enrollment-id values per request; split the list.")
    return {
        **_campaign_args(args),
        "brief_id": _uuid(args.brief_id, flag="--brief-id"),
        "enrollment_ids": enrollment_ids,
        **_terms(args),
        "dry_run": bool(args.dry_run),
    }


def _add_assignment_id_arguments(parser: argparse.ArgumentParser) -> None:
    _add_campaign_id(parser)
    parser.add_argument("--id", required=True)
    _add_dry_run(parser)


def _add_assignment_update_terms_arguments(parser: argparse.ArgumentParser) -> None:
    _add_assignment_id_arguments(parser)
    _add_terms_arguments(parser)


def _build_assignment_update_terms_arguments(args: argparse.Namespace) -> dict[str, Any]:
    edits = _terms(args)
    if not edits:
        raise ValueError(
            "Pass at least one term to change: --video-limit, --due-at, --note or --priority."
        )
    return {
        **_campaign_args(args),
        "id": _uuid(args.id, flag="--id"),
        "edits": edits,
        "dry_run": bool(args.dry_run),
    }


def _add_assignment_withdraw_arguments(parser: argparse.ArgumentParser) -> None:
    _add_assignment_id_arguments(parser)
    parser.add_argument("--yes", action="store_true")


def _build_assignment_withdraw_arguments(args: argparse.Namespace) -> dict[str, Any]:
    return {
        **_campaign_args(args),
        "id": _uuid(args.id, flag="--id"),
        "dry_run": bool(args.dry_run),
    }


# -- schemas -----------------------------------------------------------------


def _uuid_property(description: str) -> dict[str, Any]:
    return {"type": "string", "format": "uuid", "description": description}


_CAMPAIGN_ID = _uuid_property(
    "UGC campaign ID (marketing campaign id from ugc campaign +list), not a "
    "campaign-monitor collection id."
)
_DRY_RUN = {
    "type": "boolean",
    "default": False,
    "description": "Read the current state and show what would change, without writing anything.",
}
_PAGING = {
    "cursor": {"type": ["string", "null"], "description": "next_cursor from the previous page."},
    "page_size": {"type": "integer", "minimum": 1, "maximum": _PAGE_LIMIT, "default": 50},
}
_TERMS = {
    "video_limit": {
        "type": ["integer", "string", "null"],
        "description": "At most this many videos (1-1000); 'none' lifts the limit.",
    },
    "due_at": {
        "type": ["string", "null"],
        "format": "date-time",
        "description": "Due time with a timezone offset; 'none' clears it.",
    },
    "note": {
        "type": ["string", "null"],
        "maxLength": 1000,
        "description": "Tips sent to the creator with the Brief card; blank clears it.",
    },
    "priority": {"type": "string", "enum": ASSIGNMENT_PRIORITIES},
}


def _schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required}


def specs() -> list[CommandSpec]:
    domain = Domain.UGC
    read = {"risk_level": "read", "execution": "direct"}
    write = {
        "risk_level": "write",
        "execution": "direct",
        "supports_dry_run": True,
        "dry_run_reads_server": True,
    }
    campaign = "11111111-1111-4111-8111-111111111111"
    brief = "22222222-2222-4222-8222-222222222222"
    creative = "33333333-3333-4333-8333-333333333333"
    enrollment = "44444444-4444-4444-8444-444444444444"
    assignment = "55555555-5555-4555-8555-555555555555"
    return [
        CommandSpec(
            domain=domain,
            resource="campaign",
            shortcut="+list",
            summary=(
                "List the active workspace's UGC campaigns, newest first. Their ids are what "
                "every other ugc command takes as --campaign-id."
            ),
            adapter_tool_name="ugc_campaign_list",
            input_schema=_schema(
                {
                    "workspace_id": _uuid_property("Workspace ID; defaults to the selected one."),
                    "status": {
                        "type": ["string", "null"],
                        "enum": [*CAMPAIGN_STATUSES, None],
                        "description": "Only campaigns in this status; archived ones only when asked.",
                    },
                    **_PAGING,
                },
                [],
            ),
            output_schema=_direct_output_schema("A page of UGC campaigns: items and next_cursor."),
            examples=["museoncli ugc campaign +list --status active"],
            add_arguments=_add_campaign_list_arguments,
            build_arguments=_build_campaign_list_arguments,
            **read,  # type: ignore[arg-type]
        ),
        CommandSpec(
            domain=domain,
            resource="enrollment",
            shortcut="+list",
            summary=(
                "List a UGC campaign's roster: enrollment id, status, persona, creator name and "
                "accounts, newest first. Use it to find the enrollment ids to assign a brief to; "
                "participating is onboarding, active and paused together."
            ),
            adapter_tool_name="ugc_enrollment_list",
            input_schema=_schema(
                {
                    "campaign_id": _CAMPAIGN_ID,
                    "status": {
                        "type": ["string", "null"],
                        "enum": [*ENROLLMENT_STATUSES, None],
                        "description": "Only enrollments in this status.",
                    },
                    "search": {"type": ["string", "null"], "description": "Creator name search."},
                    **_PAGING,
                },
                ["campaign_id"],
            ),
            output_schema=_direct_output_schema("Roster rows (items) and next_cursor."),
            examples=[f"museoncli ugc enrollment +list --campaign-id {campaign} --status participating"],
            add_arguments=_add_enrollment_list_arguments,
            build_arguments=_build_enrollment_list_arguments,
            **read,  # type: ignore[arg-type]
        ),
        CommandSpec(
            domain=domain,
            resource="brief",
            shortcut="+list",
            summary=(
                "List the briefs a UGC campaign links, archived ones included: id, title, "
                "persona, status and current version."
            ),
            adapter_tool_name="ugc_brief_list",
            input_schema=_schema(
                {
                    "campaign_id": _CAMPAIGN_ID,
                    "status": {
                        "type": ["string", "null"],
                        "enum": [*BRIEF_STATUSES, None],
                        "description": "Only briefs in this status.",
                    },
                },
                ["campaign_id"],
            ),
            output_schema=_direct_output_schema("Brief lines (items)."),
            examples=[f"museoncli ugc brief +list --campaign-id {campaign} --status active"],
            add_arguments=_add_brief_list_arguments,
            build_arguments=_build_brief_list_arguments,
            **read,  # type: ignore[arg-type]
        ),
        CommandSpec(
            domain=domain,
            resource="brief",
            shortcut="+get",
            summary=(
                "Read one brief of a UGC campaign: its current version (or --version N) and, as "
                "document, the editable fields of the current version that +update changes."
            ),
            adapter_tool_name="ugc_brief_get",
            input_schema=_schema(
                {
                    "campaign_id": _CAMPAIGN_ID,
                    "id": _uuid_property("Brief ID."),
                    "version": {
                        "type": ["integer", "null"],
                        "minimum": 1,
                        "description": "Version number to read; the current one when left out.",
                    },
                },
                ["campaign_id", "id"],
            ),
            output_schema=_direct_output_schema(
                "brief, version, is_current, document, copy_required and media."
            ),
            examples=[f"museoncli ugc brief +get --campaign-id {campaign} --id {brief}"],
            add_arguments=_add_brief_get_arguments,
            build_arguments=_build_brief_get_arguments,
            **read,  # type: ignore[arg-type]
        ),
        CommandSpec(
            domain=domain,
            resource="brief",
            shortcut="+progress",
            summary=(
                "Read how far each brief of a UGC campaign has got: per brief, its live (not "
                "withdrawn) assignments, the videos they count and their video limits, plus "
                "one row per assignment. Raw counts only; nothing is judged owed or late."
            ),
            adapter_tool_name="ugc_brief_progress",
            input_schema=_schema(
                {
                    "campaign_id": _CAMPAIGN_ID,
                    "brief_id": _uuid_property("Only this brief."),
                },
                ["campaign_id"],
            ),
            output_schema=_direct_output_schema(
                "briefs: brief_id, title, status, current_version, assignments, "
                "withdrawn_assignments, videos_counted, video_limit_total (set limits only), "
                "unlimited_assignments and rows."
            ),
            examples=[f"museoncli ugc brief +progress --campaign-id {campaign}"],
            add_arguments=_add_brief_progress_arguments,
            build_arguments=_build_brief_progress_arguments,
            **read,  # type: ignore[arg-type]
        ),
        CommandSpec(
            domain=domain,
            resource="creative",
            shortcut="+list",
            summary=(
                "List a UGC campaign's creatives (submitted cuts) with the brief each one cites. "
                "--brief-id none keeps the ones that cite no brief yet."
            ),
            adapter_tool_name="ugc_creative_list",
            input_schema=_schema(
                {
                    "campaign_id": _CAMPAIGN_ID,
                    "review_status": {
                        "type": ["string", "null"],
                        "enum": [*kebab_choices(CREATIVE_REVIEW_STATUSES), None],
                        "description": "Only creatives in this review status.",
                    },
                    "brief_id": {
                        "type": ["string", "null"],
                        "description": "Only creatives citing this brief ID; 'none' for those citing none.",
                    },
                },
                ["campaign_id"],
            ),
            output_schema=_direct_output_schema("Creatives (items) and count."),
            examples=[f"museoncli ugc creative +list --campaign-id {campaign} --brief-id none"],
            add_arguments=_add_creative_list_arguments,
            build_arguments=_build_creative_list_arguments,
            **read,  # type: ignore[arg-type]
        ),
        CommandSpec(
            domain=domain,
            resource="creative",
            shortcut="+set-brief",
            summary=(
                "Set which brief a UGC creative cites; a creative delivered against an "
                "assignment keeps that assignment's brief. --dry-run returns the brief before "
                "and after without writing." + _CONFIRM_FIRST
            ),
            adapter_tool_name="ugc_creative_set_brief",
            input_schema=_schema(
                {
                    "campaign_id": _CAMPAIGN_ID,
                    "id": _uuid_property("Creative ID."),
                    "brief_id": _uuid_property("The brief the creative should cite."),
                    "dry_run": _DRY_RUN,
                },
                ["campaign_id", "id", "brief_id"],
            ),
            output_schema=_direct_output_schema("creative, before and after."),
            examples=[
                f"museoncli ugc creative +set-brief --campaign-id {campaign} --id {creative} "
                f"--brief-id {brief} --dry-run"
            ],
            add_arguments=_add_creative_set_brief_arguments,
            build_arguments=_build_creative_set_brief_arguments,
            **write,  # type: ignore[arg-type]
        ),
        CommandSpec(
            domain=domain,
            resource="creative",
            shortcut="+apply-default-briefs",
            summary=(
                "Link every brief-less creative of a UGC campaign whose creator has exactly one "
                "live assignment there to that assignment's brief. --dry-run asks the workbench "
                "which creatives it would link, without writing." + _CONFIRM_FIRST
            ),
            adapter_tool_name="ugc_creative_apply_default_briefs",
            input_schema=_schema({"campaign_id": _CAMPAIGN_ID, "dry_run": _DRY_RUN}, ["campaign_id"]),
            output_schema=_direct_output_schema(
                "linked (creative_id, brief_id, brief_title), ambiguous, without_assignment, dry_run."
            ),
            examples=[
                f"museoncli ugc creative +apply-default-briefs --campaign-id {campaign} --dry-run"
            ],
            add_arguments=_add_campaign_write_arguments,
            build_arguments=_build_campaign_write_arguments,
            **write,  # type: ignore[arg-type]
        ),
        CommandSpec(
            domain=domain,
            resource="brief",
            shortcut="+update",
            summary=(
                "Edit a UGC campaign's brief as a new version: only the fields passed change, "
                "the rest of the current version is kept. --dry-run returns the changes and how "
                "many creators are working on the brief, without writing; --notify sends each "
                "of them a brief-updated card." + _CONFIRM_FIRST + " Ask the user too whether "
                "to notify those creators."
            ),
            adapter_tool_name="ugc_brief_update",
            input_schema=_schema(
                {
                    "campaign_id": _CAMPAIGN_ID,
                    "id": _uuid_property("Brief ID."),
                    "expected_version": {
                        "type": "integer",
                        "minimum": 0,
                        "description": (
                            "current_version from your latest read; the edit fails instead "
                            "of overwriting a newer version."
                        ),
                    },
                    "title": {"type": "string", "maxLength": 200, "description": "Brief title."},
                    "content": {
                        "type": "string",
                        "maxLength": 20000,
                        "description": "The brief's body, Markdown (replaces the whole body).",
                    },
                    "content_file": {
                        "type": "string",
                        "description": "Path to a UTF-8 file holding the Markdown body.",
                    },
                    "references_json": {
                        "type": "string",
                        "description": (
                            "JSON array replacing every reference (at most 20): "
                            '{"type":"link","url"}, {"type":"file","media_id"} or '
                            '{"type":"stored","kind","url","name"}, each with an optional note. '
                            "Start from document.references of +get."
                        ),
                    },
                    "required_caption": {
                        "type": "string",
                        "maxLength": 2200,
                        "description": "Caption every post must carry; blank removes it.",
                    },
                    "require_ad_disclosure": {
                        "type": "boolean",
                        "description": "Whether posts must carry an ad disclosure.",
                    },
                    "notify": {
                        "type": "boolean",
                        "default": False,
                        "description": (
                            "Send every creator on a live assignment of this brief a "
                            "'Your brief was updated' card."
                        ),
                    },
                    "dry_run": _DRY_RUN,
                },
                ["campaign_id", "id", "expected_version"],
            ),
            output_schema=_direct_output_schema(
                "dry_run, brief (id, title, current_version), changes (field, before, after), "
                "live_assignments, notify."
            ),
            examples=[
                f"museoncli ugc brief +update --campaign-id {campaign} --id {brief} "
                "--expected-version 3 --required-caption '#ad @brand' --dry-run"
            ],
            add_arguments=_add_brief_update_arguments,
            build_arguments=_build_brief_update_arguments,
            **write,  # type: ignore[arg-type]
        ),
        CommandSpec(
            domain=domain,
            resource="brief",
            shortcut="+upload-media",
            summary=(
                "Upload an image, video or file to a UGC campaign's brief library and return "
                "the reference to add to --references-json of +update. Uploading changes no "
                "brief by itself. Its --dry-run only checks the file locally; the Agent asks the "
                "user before uploading."
            ),
            adapter_tool_name="ugc_brief_upload_media",
            input_schema=_schema(
                {
                    "campaign_id": _CAMPAIGN_ID,
                    "file": {"type": "string", "description": "Path of the local file to upload."},
                },
                ["campaign_id", "file"],
            ),
            output_schema=_direct_output_schema("reference, kind, url and size_bytes."),
            examples=[
                f"museoncli ugc brief +upload-media --campaign-id {campaign} --file ./hook.mp4"
            ],
            add_arguments=_add_brief_upload_media_arguments,
            build_arguments=_build_brief_upload_media_arguments,
            risk_level="write",
            execution="direct",
            supports_dry_run=True,
        ),
        CommandSpec(
            domain=domain,
            resource="assignment",
            shortcut="+create",
            summary=(
                "Assign one brief to one or more of a UGC campaign's enrollments, with optional "
                "video limit, due time, note and priority. --dry-run returns the brief, the "
                "terms and who would get it, with any assignment of this brief they already "
                "hold, without writing." + _CONFIRM_FIRST
            ),
            adapter_tool_name="ugc_assignment_create",
            input_schema=_schema(
                {
                    "campaign_id": _CAMPAIGN_ID,
                    "brief_id": _uuid_property("The brief to assign."),
                    "enrollment_ids": {
                        "type": "array",
                        "items": {"type": "string", "format": "uuid"},
                        "minItems": 1,
                        "maxItems": 200,
                        "description": "Enrollment IDs from ugc enrollment +list",
                    },
                    **_TERMS,
                    "dry_run": _DRY_RUN,
                },
                ["campaign_id", "brief_id", "enrollment_ids"],
            ),
            output_schema=_direct_output_schema(
                "results: enrollment_id, assigned, assignment_id, error_code per enrollment."
            ),
            examples=[
                f"museoncli ugc assignment +create --campaign-id {campaign} --brief-id {brief} "
                f"--enrollment-id {enrollment} --video-limit 3 --dry-run"
            ],
            add_arguments=_add_assignment_create_arguments,
            build_arguments=_build_assignment_create_arguments,
            **write,  # type: ignore[arg-type]
        ),
        CommandSpec(
            domain=domain,
            resource="assignment",
            shortcut="+update-terms",
            summary=(
                "Change an assignment's video limit, due time, note or priority; terms not "
                "passed keep their value. Saving sends the creator one updated brief card. "
                "--dry-run returns the changes without writing." + _CONFIRM_FIRST
            ),
            adapter_tool_name="ugc_assignment_update_terms",
            input_schema=_schema(
                {
                    "campaign_id": _CAMPAIGN_ID,
                    "id": _uuid_property("Assignment ID (rows of ugc brief +progress)."),
                    **_TERMS,
                    "dry_run": _DRY_RUN,
                },
                ["campaign_id", "id"],
            ),
            output_schema=_direct_output_schema("assignment and changes (field, before, after)."),
            examples=[
                f"museoncli ugc assignment +update-terms --campaign-id {campaign} "
                f"--id {assignment} --due-at 2026-11-07T18:00:00+08:00 --dry-run"
            ],
            add_arguments=_add_assignment_update_terms_arguments,
            build_arguments=_build_assignment_update_terms_arguments,
            **write,  # type: ignore[arg-type]
        ),
        CommandSpec(
            domain=domain,
            resource="assignment",
            shortcut="+withdraw",
            summary=(
                "Withdraw an assignment: the creator no longer has the brief. --dry-run returns "
                "the assignment without writing." + _CONFIRM_FIRST + " Then pass --yes."
            ),
            adapter_tool_name="ugc_assignment_withdraw",
            input_schema=_schema(
                {
                    "campaign_id": _CAMPAIGN_ID,
                    "id": _uuid_property("Assignment ID (rows of ugc brief +progress)."),
                    "dry_run": _DRY_RUN,
                },
                ["campaign_id", "id"],
            ),
            output_schema=_direct_output_schema("assignment as it stands after the withdrawal."),
            examples=[
                f"museoncli ugc assignment +withdraw --campaign-id {campaign} --id {assignment} "
                "--dry-run"
            ],
            add_arguments=_add_assignment_withdraw_arguments,
            build_arguments=_build_assignment_withdraw_arguments,
            risk_level="destructive",
            requires_confirmation=True,
            execution="direct",
            supports_dry_run=True,
            dry_run_reads_server=True,
        ),
    ]


EXECUTORS = {
    "ugc.campaign-list": direct_enveloped(_execute_campaign_list),
    "ugc.enrollment-list": direct_enveloped(_execute_enrollment_list),
    "ugc.brief-list": direct_enveloped(_execute_brief_list),
    "ugc.brief-get": direct_enveloped(_execute_brief_get),
    "ugc.brief-progress": _with_notes(_execute_brief_progress),
    "ugc.creative-list": direct_enveloped(_execute_creative_list),
    "ugc.creative-set-brief": _with_notes(_execute_creative_set_brief),
    "ugc.creative-apply-default-briefs": _with_notes(_execute_creative_apply_default_briefs),
    "ugc.brief-update": _with_notes(_execute_brief_update),
    "ugc.brief-upload-media": _with_notes(_execute_brief_upload_media),
    "ugc.assignment-create": _with_notes(_execute_assignment_create),
    "ugc.assignment-update-terms": _with_notes(_execute_assignment_update_terms),
    "ugc.assignment-withdraw": _with_notes(_execute_assignment_withdraw),
}
