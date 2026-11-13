"""UGC personas: the organization's list of creator personas that Formats and enrollments name.

These are the UGC workbench's personas (`/api/v2/ugc/personas`), as the web's
/formats page manages them. `ai-slideshow asset persona` is the slideshow
persona, a different list. The workbench decides who may write (owner, admin
and operators edit; members read).
"""

from __future__ import annotations

import argparse
from typing import Any

from museoncli.domains import _ugc_write as w
from museoncli.domains._model import CommandSpec
from museoncli.domains.ugc import _with_notes
from museoncli.execution import CommandContext, direct_enveloped

_LINE = ("id", "title", "description", "updated_at")


def _line(persona: dict[str, Any]) -> dict[str, Any]:
    return {key: persona.get(key) for key in _LINE}


async def _personas(ctx: CommandContext) -> list[dict[str, Any]]:
    page = await w.call(ctx, "GET", "/personas")
    return w._dicts(page.get("items") if isinstance(page, dict) else None)


def _find(personas: list[dict[str, Any]], persona_id: str) -> dict[str, Any]:
    found = next((item for item in personas if item.get("id") == persona_id), None)
    if found is None:
        raise RuntimeError("not_found: persona_not_found: no such persona in this organization")
    return found


def _taken(personas: list[dict[str, Any]], title: str, *, other_than: str | None = None) -> bool:
    wanted = title.casefold()
    return any(
        str(item.get("title") or "").casefold() == wanted and item.get("id") != other_than
        for item in personas
    )


async def _execute_list(ctx: CommandContext) -> Any:
    personas = await _personas(ctx)
    return {"items": [_line(item) for item in personas], "count": len(personas)}


async def _execute_create(ctx: CommandContext) -> Any:
    args = ctx.arguments
    personas = await _personas(ctx)
    body = {"title": args["title"], "description": args.get("description") or ""}
    data: dict[str, Any] = {"dry_run": args["dry_run"], "persona": body}
    if _taken(personas, body["title"]):
        raise RuntimeError(
            f"conflict: persona_title_taken: the organization already has a persona titled "
            f"{body['title']!r}."
        )
    if args["dry_run"]:
        return data, [], w.ask("the new persona")
    data["persona"] = _line(await w.call(ctx, "POST", "/personas", body=body))
    return data, [], []


async def _execute_update(ctx: CommandContext) -> Any:
    args = ctx.arguments
    personas = await _personas(ctx)
    persona = _find(personas, args["id"])
    edits = args["edits"]
    diff = w.changes(persona, {**persona, **edits}, list(edits))
    data: dict[str, Any] = {"dry_run": args["dry_run"], "persona": _line(persona), "changes": diff}
    if not diff:
        return data, [w.nothing_to_write("the current persona")], []
    if "title" in edits and _taken(personas, edits["title"], other_than=args["id"]):
        raise RuntimeError(
            f"conflict: persona_title_taken: another persona is titled {edits['title']!r}."
        )
    warnings = ["Every Format, enrollment and Campaign naming this persona shows the change."]
    if args["dry_run"]:
        return data, warnings, w.ask("the persona changes")
    data["persona"] = _line(await w.call(ctx, "PATCH", f"/personas/{args['id']}", body=edits))
    return data, [], []


async def _execute_delete(ctx: CommandContext) -> Any:
    args = ctx.arguments
    persona = _find(await _personas(ctx), args["id"])
    data: dict[str, Any] = {"dry_run": args["dry_run"], "persona": _line(persona)}
    warnings = [
        "Deleting is permanent. A persona a Campaign, an enrollment or a Format still names is "
        "refused (persona_in_use); move those first."
    ]
    if args["dry_run"]:
        return data, warnings, w.ask("the persona that would be deleted")
    await w.call(ctx, "DELETE", f"/personas/{args['id']}")
    data["deleted"] = True
    return data, [], []


# -- arguments ---------------------------------------------------------------


def _title(value: str) -> str:
    title = value.strip()
    if not title:
        raise ValueError("--title must not be blank.")
    return title


def _description(value: str) -> str:
    if len(value) > 2000:
        raise ValueError("--description is at most 2000 characters.")
    return value


def _add_list_arguments(parser: argparse.ArgumentParser) -> None:
    del parser


def _build_list_arguments(args: argparse.Namespace) -> dict[str, Any]:
    del args
    return {}


def _add_create_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--title", required=True)
    parser.add_argument("--description")
    w.add_dry_run(parser)


def _build_create_arguments(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "title": _title(args.title),
        **({"description": _description(args.description)} if args.description is not None else {}),
        "dry_run": bool(args.dry_run),
    }


def _add_update_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--id", required=True)
    parser.add_argument("--title")
    parser.add_argument("--description")
    w.add_dry_run(parser)


def _build_update_arguments(args: argparse.Namespace) -> dict[str, Any]:
    edits: dict[str, Any] = {}
    if args.title is not None:
        edits["title"] = _title(args.title)
    if args.description is not None:
        edits["description"] = _description(args.description)
    if not edits:
        raise ValueError("Pass --title or --description.")
    return {"id": w._uuid(args.id, flag="--id"), "edits": edits, "dry_run": bool(args.dry_run)}


def _add_delete_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--id", required=True)
    w.add_dry_run(parser)
    w.add_yes(parser)


def _build_delete_arguments(args: argparse.Namespace) -> dict[str, Any]:
    return {"id": w._uuid(args.id, flag="--id"), "dry_run": bool(args.dry_run)}


# -- specs -------------------------------------------------------------------

_ROLE = " Role: owner, admin or operator; the server decides."
_ID = w.uuid_property("UGC persona ID (from ugc persona +list).")


def specs() -> list[CommandSpec]:
    p = w.PERSONA
    return [
        w.spec(
            resource="persona",
            shortcut="+list",
            summary=(
                "List the organization's UGC personas (the creator types Formats and enrollments "
                "name): id, title and description. Not the ai-slideshow personas."
            ),
            adapter="ugc_persona_list",
            properties={},
            required=[],
            output_description="Personas (items: id, title, description, updated_at) and count.",
            examples=["museoncli ugc persona +list"],
            add_arguments=_add_list_arguments,
            build_arguments=_build_list_arguments,
            kind=w.READ,
        ),
        w.spec(
            resource="persona",
            shortcut="+create",
            summary=(
                "Add a UGC persona to the organization; titles are unique. --dry-run returns it "
                "without writing." + w.CONFIRM_FIRST + _ROLE
            ),
            adapter="ugc_persona_create",
            properties={
                "title": {"type": "string", "description": "Persona title, unique in the organization."},
                "description": {"type": "string", "maxLength": 2000, "description": "Who this creator is."},
                "dry_run": w.DRY_RUN,
            },
            required=["title"],
            output_description="dry_run and persona.",
            examples=["museoncli ugc persona +create --title 'Busy mom' --description 'Parents of toddlers' --dry-run"],
            add_arguments=_add_create_arguments,
            build_arguments=_build_create_arguments,
            kind=w.WRITE,
        ),
        w.spec(
            resource="persona",
            shortcut="+update",
            summary=(
                "Rename a UGC persona or change its description; only the fields passed change. "
                "--dry-run returns the changes without writing." + w.CONFIRM_FIRST + _ROLE
            ),
            adapter="ugc_persona_update",
            properties={
                "id": _ID,
                "title": {"type": "string", "description": "New title."},
                "description": {"type": "string", "maxLength": 2000, "description": "New description."},
                "dry_run": w.DRY_RUN,
            },
            required=["id"],
            output_description="dry_run, persona and changes.",
            examples=[f"museoncli ugc persona +update --id {p} --title 'Working mom' --dry-run"],
            add_arguments=_add_update_arguments,
            build_arguments=_build_update_arguments,
            kind=w.WRITE,
        ),
        w.spec(
            resource="persona",
            shortcut="+delete",
            summary=(
                "Delete a UGC persona nothing names any more (no Campaign, enrollment or Format). "
                "--dry-run returns it without writing." + w.CONFIRM_YES + _ROLE
            ),
            adapter="ugc_persona_delete",
            properties={"id": _ID, "dry_run": w.DRY_RUN},
            required=["id"],
            output_description="dry_run, persona and deleted.",
            examples=[f"museoncli ugc persona +delete --id {p} --dry-run"],
            add_arguments=_add_delete_arguments,
            build_arguments=_build_delete_arguments,
            kind=w.DESTRUCTIVE,
        ),
    ]


EXECUTORS = {
    "ugc.persona-list": direct_enveloped(_execute_list),
    "ugc.persona-create": _with_notes(_execute_create),
    "ugc.persona-update": _with_notes(_execute_update),
    "ugc.persona-delete": _with_notes(_execute_delete),
}
