"""Formats (脚本, code name `brief`): the organization's library and a Campaign's links to it.

`ugc brief-library ...` works on the organization's Format library, as the web's
/formats page does: list, read, create, edit (a new version), archive and copy.
`ugc brief +create/+link/+unlink/+copy` work inside one Campaign, as its Formats
step does. These are the UGC Formats; `ai-slideshow asset format` is the
slideshow one, a different thing. Who may write is decided by the server
(owner, admin and operators edit Formats; members read).
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from museoncli.domains import _ugc_write as w
from museoncli.domains._model import CommandSpec
from museoncli.domains.ugc import (
    _brief_line,
    _plural,
    _references,
    _with_notes,
    brief_document,
    merge_document,
    write_reference,
)
from museoncli.execution import CommandContext, compact_params, direct_enveloped

BRIEF_STATUSES = ["active", "archived"]
_PAGE_LIMIT = 100


def _linked(view: dict[str, Any]) -> list[str]:
    return [str(item) for item in view.get("linked_campaign_ids") or []]


async def _library_brief(ctx: CommandContext, brief_id: str) -> dict[str, Any]:
    view = await w.call(ctx, "GET", f"/briefs/{brief_id}")
    if not isinstance(view, dict) or not isinstance(view.get("brief"), dict):
        raise RuntimeError("not_found: brief_not_found: no such Format in this organization")
    return view


def _summary(view: dict[str, Any]) -> dict[str, Any]:
    return _brief_line(view.get("brief") or {})


def _check_version(view: dict[str, Any], expected: int) -> int:
    current = (view.get("brief") or {}).get("current_version")
    if current != expected:
        raise RuntimeError(
            f"conflict: brief_version_conflict: the Format is at version {current}, not "
            f"{expected}. Read it again and redo the change on that version."
        )
    return int(current)


def _shared_warning(view: dict[str, Any]) -> list[str]:
    linked = _linked(view)
    if not linked:
        return []
    more = " or more" if view.get("has_more_campaigns") else ""
    return [f"{_plural(len(linked), 'Campaign uses', 'Campaigns use')}{more} this Format; the change reaches every one of them."]


# -- library -------------------------------------------------------------------


async def _execute_library_list(ctx: CommandContext) -> Any:
    args = ctx.arguments
    if not ctx.organization_id:
        raise RuntimeError(
            "missing_organization: select one with `museoncli org select` or pass --organization-id"
        )
    page = await w.call(
        ctx,
        "GET",
        f"/organizations/{ctx.organization_id}/briefs",
        params=compact_params(
            {
                "status": args.get("status"),
                "search": args.get("search"),
                "cursor": args.get("cursor"),
                "limit": args.get("page_size"),
            }
        ),
    )
    page = page if isinstance(page, dict) else {}
    return {
        "items": [_brief_line(item) for item in w._dicts(page.get("items"))],
        "next_cursor": page.get("next_cursor"),
    }


async def _execute_library_get(ctx: CommandContext) -> Any:
    args = ctx.arguments
    view = await _library_brief(ctx, args["id"])
    summary = view["brief"]
    wanted = args.get("version") or summary.get("current_version")
    versions = [*w._dicts(view.get("versions")), *([view["current"]] if isinstance(view.get("current"), dict) else [])]
    version = next((item for item in versions if item.get("version") == wanted), None)
    if version is None:
        raise RuntimeError(f"not_found: brief_version_not_found: the Format has no version {wanted}")
    return {
        "brief": summary,
        "version": version,
        "is_current": wanted == summary.get("current_version"),
        "document": brief_document(view),
        "linked_campaign_ids": _linked(view),
        "has_more_campaigns": bool(view.get("has_more_campaigns")),
        "media": view.get("media") or [],
    }


async def _execute_library_create(ctx: CommandContext) -> Any:
    args = ctx.arguments
    key = w.idempotency_key(args)
    document = args.get("document") or {}
    data: dict[str, Any] = {"dry_run": args["dry_run"], "document": document, "idempotency_key": key}
    if args["dry_run"]:
        return data, [], w.ask("the new Format")
    view = await w.call(
        ctx,
        "POST",
        "/briefs",
        body=document,
        params={"organization_id": ctx.organization_id} if ctx.organization_id else None,
        idempotency_key=key,
    )
    data["brief"] = _summary(view if isinstance(view, dict) else {})
    return data, [], [w.retry_note(key)]


async def _execute_library_update(ctx: CommandContext) -> Any:
    args = ctx.arguments
    view = await _library_brief(ctx, args["id"])
    version = _check_version(view, args["expected_version"])
    merged, diff = merge_document(brief_document(view), args["edits"])
    data: dict[str, Any] = {
        "dry_run": args["dry_run"],
        "brief": _summary(view),
        "changes": diff,
        "linked_campaign_ids": _linked(view),
    }
    if not diff:
        return data, [w.nothing_to_write("the current version")], []
    warnings = _shared_warning(view)
    if args["dry_run"]:
        return data, warnings, w.ask("these changes")
    written = await w.call(
        ctx, "PATCH", f"/briefs/{args['id']}", body={**merged, "expected_version": version}
    )
    data["brief"] = _summary(written if isinstance(written, dict) else {})
    return data, warnings, []


async def _execute_library_archive(ctx: CommandContext) -> Any:
    args = ctx.arguments
    view = await _library_brief(ctx, args["id"])
    version = _check_version(view, args["expected_version"])
    data: dict[str, Any] = {
        "dry_run": args["dry_run"],
        "brief": _summary(view),
        "linked_campaign_ids": _linked(view),
    }
    if view["brief"].get("status") == "archived":
        return data, ["The Format is already archived; nothing was written."], []
    warnings = [
        "Archiving takes the Format out of the library list; there is no restore command, the "
        "web app has none either.",
        *_shared_warning(view),
    ]
    if args["dry_run"]:
        return data, warnings, w.ask("the Format that would be archived")
    written = await w.call(
        ctx, "POST", f"/briefs/{args['id']}/archive", params={"expected_version": version}
    )
    data["brief"] = _brief_line(written if isinstance(written, dict) else {})
    return data, [], []


async def _execute_library_copy(ctx: CommandContext) -> Any:
    args = ctx.arguments
    view = await _library_brief(ctx, args["id"])
    version = args.get("version") or view["brief"].get("current_version")
    key = w.idempotency_key(args)
    data: dict[str, Any] = {
        "dry_run": args["dry_run"],
        "source": _summary(view),
        "version": version,
        "idempotency_key": key,
    }
    if args["dry_run"]:
        return data, [], w.ask("the Format and version that would be copied")
    written = await w.call(
        ctx, "POST", f"/briefs/{args['id']}/copy", params={"version": version}, idempotency_key=key
    )
    data["brief"] = _summary(written if isinstance(written, dict) else {})
    return data, [], [w.retry_note(key)]


# -- inside a campaign -------------------------------------------------------


async def _campaign_briefs(ctx: CommandContext, campaign_id: str) -> list[dict[str, Any]]:
    return w._dicts(await w.call(ctx, "GET", f"/campaigns/{campaign_id}/briefs"))


async def _execute_campaign_create(ctx: CommandContext) -> Any:
    args = ctx.arguments
    campaign_id = args["campaign_id"]
    briefs = await _campaign_briefs(ctx, campaign_id)
    key = w.idempotency_key(args)
    body = {**args["document"], **({"persona_id": args["persona_id"]} if args.get("persona_id") else {})}
    data: dict[str, Any] = {"dry_run": args["dry_run"], "document": body, "idempotency_key": key}
    warnings = (
        [f"The Campaign already links a Format titled {body['title']!r}."]
        if any(item.get("title") == body["title"] and item.get("status") == "active" for item in briefs)
        else []
    )
    if args["dry_run"]:
        return data, warnings, w.ask("the new Format")
    view = await w.call(
        ctx, "POST", f"/campaigns/{campaign_id}/brief-documents", body=body, idempotency_key=key
    )
    data["brief"] = _summary(view if isinstance(view, dict) else {})
    return data, warnings, [w.retry_note(key)]


async def _execute_campaign_link(ctx: CommandContext) -> Any:
    args = ctx.arguments
    campaign_id, brief_id = args["campaign_id"], args["id"]
    view = await _library_brief(ctx, brief_id)
    linked = {item.get("id"): item for item in await _campaign_briefs(ctx, campaign_id)}
    replaces = args.get("replaces")
    data: dict[str, Any] = {
        "dry_run": args["dry_run"],
        "brief": _summary(view),
        "replaces": _brief_line(linked[replaces]) if replaces in linked else replaces,
    }
    if brief_id in linked and not replaces:
        return data, ["The Campaign already links this Format; nothing was written."], []
    warnings = []
    if replaces and replaces not in linked:
        warnings.append("The Campaign does not link the Format to replace; the workbench refuses it.")
    if args["dry_run"]:
        return data, warnings, w.ask("which Format the Campaign would link")
    await w.call(
        ctx,
        "PUT",
        f"/campaigns/{campaign_id}/brief-links/{brief_id}",
        params={"replaces": replaces} if replaces else None,
    )
    data["linked"] = True
    return data, [], []


async def _execute_campaign_unlink(ctx: CommandContext) -> Any:
    args = ctx.arguments
    campaign_id, brief_id = args["campaign_id"], args["id"]
    linked = {item.get("id"): item for item in await _campaign_briefs(ctx, campaign_id)}
    data: dict[str, Any] = {"dry_run": args["dry_run"], "brief": _brief_line(linked.get(brief_id) or {"id": brief_id})}
    if brief_id not in linked:
        return data, ["The Campaign does not link this Format; nothing was written."], []
    warnings = ["The Format stays in the library; only this Campaign stops using it."]
    if args["dry_run"]:
        return data, warnings, w.ask("which Format the Campaign would stop using")
    await w.call(ctx, "DELETE", f"/campaigns/{campaign_id}/brief-links/{brief_id}")
    data["unlinked"] = True
    return data, [], []


async def _execute_campaign_copy(ctx: CommandContext) -> Any:
    args = ctx.arguments
    campaign_id, brief_id = args["campaign_id"], args["id"]
    view = await _library_brief(ctx, brief_id)
    version = args.get("version") or view["brief"].get("current_version")
    key = w.idempotency_key(args)
    keep_source = bool(args["keep_source"])
    data: dict[str, Any] = {
        "dry_run": args["dry_run"],
        "source": _summary(view),
        "version": version,
        "persona_id": args.get("persona_id"),
        "keep_source": keep_source,
        "idempotency_key": key,
    }
    warnings = [
        "The copy is linked beside the source."
        if keep_source
        else "The copy replaces the source's link in this Campaign; other Campaigns keep the source."
    ]
    if args["dry_run"]:
        return data, warnings, w.ask("the Format copy")
    params = compact_params(
        {"version": version, "persona_id": args.get("persona_id"), "keep_source": "true" if keep_source else None}
    )
    written = await w.call(
        ctx,
        "POST",
        f"/campaigns/{campaign_id}/brief-documents/{brief_id}/copy",
        params=params,
        idempotency_key=key,
    )
    data["brief"] = _summary(written if isinstance(written, dict) else {})
    return data, [], [w.retry_note(key)]


# -- arguments ---------------------------------------------------------------


def _add_document_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--title", required=True)
    content = parser.add_mutually_exclusive_group(required=True)
    content.add_argument("--content")
    content.add_argument("--content-file")
    parser.add_argument("--references-json")
    parser.add_argument("--required-caption")
    parser.add_argument("--require-ad-disclosure", action="store_true")


def _document(args: argparse.Namespace) -> dict[str, Any]:
    title = args.title.strip()
    if not title or len(title) > 200:
        raise ValueError("--title must not be blank, at most 200 characters.")
    content = (
        Path(args.content_file).expanduser().read_text(encoding="utf-8")
        if args.content_file
        else args.content
    )
    if len(content) > 20000:
        raise ValueError("The Format's body is at most 20000 characters.")
    references = [write_reference(item) for item in _references(args.references_json)] if args.references_json else []
    if len(references) > 20:
        raise ValueError("At most 20 references.")
    caption = (args.required_caption or "").strip() or None
    if caption and len(caption) > 2200:
        raise ValueError("--required-caption is at most 2200 characters.")
    return {
        "title": title,
        "content": content,
        "references": references,
        "required_caption": caption,
        "require_ad_disclosure": bool(args.require_ad_disclosure),
    }


def _add_library_list_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--status", choices=BRIEF_STATUSES)
    parser.add_argument("--search")
    parser.add_argument("--cursor")
    parser.add_argument("--page-size", type=int, default=50)


def _build_library_list_arguments(args: argparse.Namespace) -> dict[str, Any]:
    if not 1 <= args.page_size <= _PAGE_LIMIT:
        raise ValueError(f"--page-size must be between 1 and {_PAGE_LIMIT}.")
    return compact_params(
        {"status": args.status, "search": args.search, "cursor": args.cursor, "page_size": args.page_size}
    )


def _add_library_get_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--id", required=True)
    parser.add_argument("--version", type=int)


def _build_library_get_arguments(args: argparse.Namespace) -> dict[str, Any]:
    return compact_params({"id": w._uuid(args.id, flag="--id"), "version": args.version})


def _add_library_create_arguments(parser: argparse.ArgumentParser) -> None:
    _add_document_arguments(parser)
    w.add_idempotency_key(parser)
    w.add_dry_run(parser)


def _build_library_create_arguments(args: argparse.Namespace) -> dict[str, Any]:
    return {"document": _document(args), **w.build_idempotency_key(args), "dry_run": bool(args.dry_run)}


def _add_library_update_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--id", required=True)
    parser.add_argument("--expected-version", type=int, required=True)
    parser.add_argument("--title")
    content = parser.add_mutually_exclusive_group()
    content.add_argument("--content")
    content.add_argument("--content-file")
    parser.add_argument("--references-json")
    parser.add_argument("--required-caption")
    parser.add_argument("--require-ad-disclosure", action=argparse.BooleanOptionalAction, default=None)
    w.add_dry_run(parser)


def _build_library_update_arguments(args: argparse.Namespace) -> dict[str, Any]:
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
        "id": w._uuid(args.id, flag="--id"),
        "expected_version": args.expected_version,
        "edits": edits,
        "dry_run": bool(args.dry_run),
    }


def _add_library_archive_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--id", required=True)
    parser.add_argument("--expected-version", type=int, required=True)
    w.add_dry_run(parser)
    w.add_yes(parser)


def _build_library_archive_arguments(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "id": w._uuid(args.id, flag="--id"),
        "expected_version": args.expected_version,
        "dry_run": bool(args.dry_run),
    }


def _add_library_copy_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--id", required=True)
    parser.add_argument("--version", type=int)
    w.add_idempotency_key(parser)
    w.add_dry_run(parser)


def _build_library_copy_arguments(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "id": w._uuid(args.id, flag="--id"),
        **({"version": args.version} if args.version else {}),
        **w.build_idempotency_key(args),
        "dry_run": bool(args.dry_run),
    }


def _add_campaign_create_arguments(parser: argparse.ArgumentParser) -> None:
    w.add_campaign_id(parser)
    _add_document_arguments(parser)
    parser.add_argument("--persona-id")
    w.add_idempotency_key(parser)
    w.add_dry_run(parser)


def _build_campaign_create_arguments(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "campaign_id": w._uuid(args.campaign_id, flag="--campaign-id"),
        "document": _document(args),
        **({"persona_id": w._uuid(args.persona_id, flag="--persona-id")} if args.persona_id else {}),
        **w.build_idempotency_key(args),
        "dry_run": bool(args.dry_run),
    }


def _add_link_arguments(*, unlink: bool):
    def add(parser: argparse.ArgumentParser) -> None:
        w.add_campaign_id(parser)
        parser.add_argument("--id", required=True)
        if not unlink:
            parser.add_argument("--replaces")
        w.add_dry_run(parser)
        if unlink:
            w.add_yes(parser)

    return add


def _build_link_arguments(args: argparse.Namespace) -> dict[str, Any]:
    out: dict[str, Any] = {
        "campaign_id": w._uuid(args.campaign_id, flag="--campaign-id"),
        "id": w._uuid(args.id, flag="--id"),
        "dry_run": bool(args.dry_run),
    }
    if getattr(args, "replaces", None):
        out["replaces"] = w._uuid(args.replaces, flag="--replaces")
    return out


def _add_campaign_copy_arguments(parser: argparse.ArgumentParser) -> None:
    w.add_campaign_id(parser)
    parser.add_argument("--id", required=True)
    parser.add_argument("--version", type=int)
    parser.add_argument("--persona-id")
    parser.add_argument("--keep-source", action="store_true")
    w.add_idempotency_key(parser)
    w.add_dry_run(parser)


def _build_campaign_copy_arguments(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "campaign_id": w._uuid(args.campaign_id, flag="--campaign-id"),
        "id": w._uuid(args.id, flag="--id"),
        **({"version": args.version} if args.version else {}),
        **({"persona_id": w._uuid(args.persona_id, flag="--persona-id")} if args.persona_id else {}),
        "keep_source": bool(args.keep_source),
        **w.build_idempotency_key(args),
        "dry_run": bool(args.dry_run),
    }


# -- specs -------------------------------------------------------------------

_ROLE = " Role: owner, admin or operator; the server decides."
_ID = w.uuid_property("Format (brief) ID.")
_DOCUMENT = {
    "title": {"type": "string", "maxLength": 200, "description": "Format title."},
    "content": {"type": "string", "maxLength": 20000, "description": "The Format's body, Markdown."},
    "content_file": {"type": "string", "description": "Path to a UTF-8 file holding the Markdown body."},
    "references_json": {
        "type": "string",
        "description": (
            'JSON array of references (at most 20): {"type":"link","url"}, '
            '{"type":"file","media_id"} or {"type":"stored","kind","url","name"}, each with an '
            "optional note. Upload a file first with ugc brief +upload-media."
        ),
    },
    "required_caption": {"type": "string", "maxLength": 2200, "description": "Caption every post must carry."},
    "require_ad_disclosure": {"type": "boolean", "description": "Posts must carry an ad disclosure."},
}
_VERSION = {"type": "integer", "minimum": 1, "description": "Version to use; the current one when left out."}
_EXPECTED_VERSION = {
    "type": "integer",
    "minimum": 0,
    "description": "current_version from your latest read; the write fails instead of acting on a newer version.",
}


def specs() -> list[CommandSpec]:
    c, b, o, p = w.CAMPAIGN, w.BRIEF, w.OTHER, w.PERSONA
    return [
        w.spec(
            resource="brief-library",
            shortcut="+list",
            summary=(
                "List the organization's Format (脚本) library, newest first: the whole library "
                "for its owners, admins and operators, otherwise the Formats of the Campaigns "
                "the caller reads. --status archived lists archived ones instead."
            ),
            adapter="ugc_brief_library_list",
            properties={
                "status": {"type": "string", "enum": BRIEF_STATUSES, "description": "active (default) or archived."},
                "search": {"type": "string", "maxLength": 200, "description": "Title search."},
                "cursor": {"type": ["string", "null"], "description": "next_cursor from the previous page."},
                "page_size": {"type": "integer", "minimum": 1, "maximum": _PAGE_LIMIT, "default": 50},
            },
            required=[],
            output_description="Format lines (items: id, title, status, persona_id, current_version, ...) and next_cursor.",
            examples=["museoncli ugc brief-library +list --search hook"],
            add_arguments=_add_library_list_arguments,
            build_arguments=_build_library_list_arguments,
            kind=w.READ,
        ),
        w.spec(
            resource="brief-library",
            shortcut="+get",
            summary=(
                "Read one Format of the organization's library: its current version (or "
                "--version N), the editable document, and which Campaigns use it."
            ),
            adapter="ugc_brief_library_get",
            properties={"id": _ID, "version": _VERSION},
            required=["id"],
            output_description="brief, version, is_current, document, linked_campaign_ids, has_more_campaigns, media.",
            examples=[f"museoncli ugc brief-library +get --id {b}"],
            add_arguments=_add_library_get_arguments,
            build_arguments=_build_library_get_arguments,
            kind=w.READ,
        ),
        w.spec(
            resource="brief-library",
            shortcut="+create",
            summary=(
                "Create a Format in the organization's library (not yet used by any Campaign; "
                "link it with ugc brief +link). --dry-run returns the document without writing."
                + w.CONFIRM_FIRST + _ROLE
            ),
            adapter="ugc_brief_library_create",
            properties={**_DOCUMENT, "idempotency_key": w.IDEMPOTENCY_KEY, "dry_run": w.DRY_RUN},
            required=["title"],
            output_description="dry_run, document, idempotency_key, brief.",
            examples=["museoncli ugc brief-library +create --title 'Morning routine' --content-file ./format.md --dry-run"],
            add_arguments=_add_library_create_arguments,
            build_arguments=_build_library_create_arguments,
            kind=w.WRITE,
        ),
        w.spec(
            resource="brief-library",
            shortcut="+update",
            summary=(
                "Edit a library Format as a new version: only the fields passed change. Every "
                "Campaign using it gets the new version. --dry-run returns the changes and the "
                "Campaigns using it without writing." + w.CONFIRM_FIRST + _ROLE
            ),
            adapter="ugc_brief_library_update",
            properties={
                "id": _ID,
                "expected_version": _EXPECTED_VERSION,
                **{key: value for key, value in _DOCUMENT.items()},
                "dry_run": w.DRY_RUN,
            },
            required=["id", "expected_version"],
            output_description="dry_run, brief, changes (field, before, after), linked_campaign_ids.",
            examples=[f"museoncli ugc brief-library +update --id {b} --expected-version 2 --title 'Morning hook' --dry-run"],
            add_arguments=_add_library_update_arguments,
            build_arguments=_build_library_update_arguments,
            kind=w.WRITE,
        ),
        w.spec(
            resource="brief-library",
            shortcut="+archive",
            summary=(
                "Archive a library Format: it leaves the library list (there is no restore). "
                "--dry-run returns it and the Campaigns using it without writing." + w.CONFIRM_YES + _ROLE
            ),
            adapter="ugc_brief_library_archive",
            properties={"id": _ID, "expected_version": _EXPECTED_VERSION, "dry_run": w.DRY_RUN},
            required=["id", "expected_version"],
            output_description="dry_run, brief, linked_campaign_ids.",
            examples=[f"museoncli ugc brief-library +archive --id {b} --expected-version 2 --dry-run"],
            add_arguments=_add_library_archive_arguments,
            build_arguments=_build_library_archive_arguments,
            kind=w.DESTRUCTIVE,
        ),
        w.spec(
            resource="brief-library",
            shortcut="+copy",
            summary=(
                "Duplicate a library Format (its current version, or --version N) as a new "
                "Format in the library. --dry-run returns the source without writing."
                + w.CONFIRM_FIRST + _ROLE
            ),
            adapter="ugc_brief_library_copy",
            properties={"id": _ID, "version": _VERSION, "idempotency_key": w.IDEMPOTENCY_KEY, "dry_run": w.DRY_RUN},
            required=["id"],
            output_description="dry_run, source, version, idempotency_key, brief (the copy).",
            examples=[f"museoncli ugc brief-library +copy --id {b} --dry-run"],
            add_arguments=_add_library_copy_arguments,
            build_arguments=_build_library_copy_arguments,
            kind=w.WRITE,
        ),
        w.spec(
            resource="brief",
            shortcut="+create",
            summary=(
                "Write a new Format inside a UGC Campaign (linked to it at once), optionally for "
                "one of its personas (--persona-id). --dry-run returns the document without "
                "writing." + w.CONFIRM_FIRST + _ROLE
            ),
            adapter="ugc_brief_create",
            properties={
                "campaign_id": w.CAMPAIGN_ID,
                **_DOCUMENT,
                "persona_id": w.uuid_property("The Campaign persona the Format is written for."),
                "idempotency_key": w.IDEMPOTENCY_KEY,
                "dry_run": w.DRY_RUN,
            },
            required=["campaign_id", "title"],
            output_description="dry_run, document, idempotency_key, brief.",
            examples=[f"museoncli ugc brief +create --campaign-id {c} --title 'Unboxing' --content 'Open the box on camera.' --persona-id {p} --dry-run"],
            add_arguments=_add_campaign_create_arguments,
            build_arguments=_build_campaign_create_arguments,
            kind=w.WRITE,
        ),
        w.spec(
            resource="brief",
            shortcut="+link",
            summary=(
                "Link a library Format to a UGC Campaign; --replaces swaps out one it already "
                "links. --dry-run returns the Format without writing." + w.CONFIRM_FIRST + _ROLE
            ),
            adapter="ugc_brief_link",
            properties={
                "campaign_id": w.CAMPAIGN_ID,
                "id": _ID,
                "replaces": w.uuid_property("A Format the Campaign links that this one replaces."),
                "dry_run": w.DRY_RUN,
            },
            required=["campaign_id", "id"],
            output_description="dry_run, brief, replaces, linked.",
            examples=[f"museoncli ugc brief +link --campaign-id {c} --id {b} --dry-run"],
            add_arguments=_add_link_arguments(unlink=False),
            build_arguments=_build_link_arguments,
            kind=w.WRITE,
        ),
        w.spec(
            resource="brief",
            shortcut="+unlink",
            summary=(
                "Stop a UGC Campaign using a Format; it stays in the library. --dry-run returns "
                "the Format without writing." + w.CONFIRM_YES + _ROLE
            ),
            adapter="ugc_brief_unlink",
            properties={"campaign_id": w.CAMPAIGN_ID, "id": _ID, "dry_run": w.DRY_RUN},
            required=["campaign_id", "id"],
            output_description="dry_run, brief, unlinked.",
            examples=[f"museoncli ugc brief +unlink --campaign-id {c} --id {b} --dry-run"],
            add_arguments=_add_link_arguments(unlink=True),
            build_arguments=_build_link_arguments,
            kind=w.DESTRUCTIVE,
        ),
        w.spec(
            resource="brief",
            shortcut="+copy",
            summary=(
                "Copy a Format version into a UGC Campaign, optionally for another persona: the "
                "copy replaces the source's link here, or with --keep-source sits beside it (the "
                "source may then be any library Format). --dry-run returns the source without "
                "writing." + w.CONFIRM_FIRST + _ROLE
            ),
            adapter="ugc_brief_copy",
            properties={
                "campaign_id": w.CAMPAIGN_ID,
                "id": _ID,
                "version": _VERSION,
                "persona_id": w.uuid_property("The persona the copy is written for; the source's when left out."),
                "keep_source": {"type": "boolean", "default": False, "description": "Link the copy beside the source."},
                "idempotency_key": w.IDEMPOTENCY_KEY,
                "dry_run": w.DRY_RUN,
            },
            required=["campaign_id", "id"],
            output_description="dry_run, source, version, persona_id, keep_source, idempotency_key, brief.",
            examples=[f"museoncli ugc brief +copy --campaign-id {c} --id {o} --keep-source --persona-id {p} --dry-run"],
            add_arguments=_add_campaign_copy_arguments,
            build_arguments=_build_campaign_copy_arguments,
            kind=w.WRITE,
        ),
    ]


EXECUTORS = {
    "ugc.brief-library-list": direct_enveloped(_execute_library_list),
    "ugc.brief-library-get": direct_enveloped(_execute_library_get),
    "ugc.brief-library-create": _with_notes(_execute_library_create),
    "ugc.brief-library-update": _with_notes(_execute_library_update),
    "ugc.brief-library-archive": _with_notes(_execute_library_archive),
    "ugc.brief-library-copy": _with_notes(_execute_library_copy),
    "ugc.brief-create": _with_notes(_execute_campaign_create),
    "ugc.brief-link": _with_notes(_execute_campaign_link),
    "ugc.brief-unlink": _with_notes(_execute_campaign_unlink),
    "ugc.brief-copy": _with_notes(_execute_campaign_copy),
}
