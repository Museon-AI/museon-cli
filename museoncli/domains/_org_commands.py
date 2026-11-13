"""Small building blocks for organization-addressed commands that call one web route.

The modules that use them (artifacts list/get, media collections, social account tags,
product CTA targets) send no workspace: the CLI names the organization with
``X-Organization-Id`` and the route resolves the rest. Inputs come from flags or from one
``--args-json`` / ``--args-file`` object; a key given both ways is an error.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Iterable
from typing import Any

from museoncli.domains._shared import _direct_output_schema, _load_structured_args
from museoncli.envelopes import direct_api_envelope
from museoncli.execution import CommandContext, Executor

MAX_PAGE_SIZE = 100


def uuid_property(description: str) -> dict[str, Any]:
    return {
        "type": "string",
        "format": "uuid",
        "description": (
            f"{description} Canonical UUID copied from a previous command response; never a "
            "placeholder."
        ),
    }


def string_property(description: str, *, max_length: int | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "string", "minLength": 1, "description": description}
    if max_length is not None:
        schema["maxLength"] = max_length
    return schema


def schema(properties: dict[str, Any], required: Iterable[str] = ()) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(required),
        "additionalProperties": False,
    }


PAGE_PROPERTIES: dict[str, Any] = {
    "page": {"type": "integer", "minimum": 1, "description": "Page number, starting at 1."},
    "page_size": {
        "type": "integer",
        "minimum": 1,
        "maximum": MAX_PAGE_SIZE,
        "description": "Records per page (1-100).",
    },
    "search": string_property("Free-text search on the name or title.", max_length=200),
}
DRY_RUN_PROPERTY = {"type": "boolean", "description": "Read and preview only; write nothing."}


def output_schema(description: str) -> dict[str, Any]:
    return _direct_output_schema(description)


def add_structured_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--args-json")
    parser.add_argument("--args-file")


def add_page_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--page", type=int)
    parser.add_argument("--page-size", type=int)
    parser.add_argument("--search")


def merged_input(args: argparse.Namespace, dests: Iterable[str]) -> dict[str, Any]:
    """Structured input, then each flag that was given; a key given both ways is refused."""
    if getattr(args, "args_json", None) and getattr(args, "args_file", None):
        raise ValueError("Use only one of --args-json and --args-file.")
    payload = _load_structured_args(args)
    for dest in dests:
        value = getattr(args, dest, None)
        if value is None or value is False or value == []:
            continue
        if dest in payload:
            raise ValueError(f"{dest} is given both as a flag and in --args-json/--args-file.")
        payload[dest] = value
    return payload


def reject_unknown(payload: dict[str, Any], properties: dict[str, Any]) -> None:
    unknown = sorted(set(payload) - set(properties) - {"organization_id"})
    if unknown:
        raise ValueError(f"Unknown input field(s): {', '.join(unknown)}.")


def require(payload: dict[str, Any], *names: str) -> None:
    missing = [name for name in names if payload.get(name) in (None, "", [])]
    if missing:
        flags = ", ".join("--" + name.replace("_", "-") for name in missing)
        raise ValueError(f"Missing required input: {flags}.")


def page_query(payload: dict[str, Any]) -> dict[str, Any]:
    """The web routes page with ``page`` + ``limit``; the CLI flag is ``--page-size``."""
    page = payload.get("page", 1)
    size = payload.get("page_size", 20)
    if not isinstance(page, int) or page < 1:
        raise ValueError("--page must be 1 or more.")
    if not isinstance(size, int) or not 1 <= size <= MAX_PAGE_SIZE:
        raise ValueError(f"--page-size must be between 1 and {MAX_PAGE_SIZE}.")
    search = payload.get("search")
    if search is not None and (not isinstance(search, str) or len(search) > 200):
        raise ValueError("--search must be text of at most 200 characters.")
    query: dict[str, Any] = {"page": page, "limit": size}
    if isinstance(search, str) and search.strip():
        query["search"] = search.strip()
    return query


def string_list(value: Any, *, field: str, maximum: int) -> list[str]:
    """Distinct non-empty strings in their given order."""
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{field} must be a list of strings.")
    output: list[str] = []
    for item in value:
        text = item.strip()
        if text and text not in output:
            output.append(text)
    if len(output) > maximum:
        raise ValueError(f"{field} takes at most {maximum} values.")
    return output


def require_organization(ctx: CommandContext) -> str:
    if not ctx.organization_id:
        raise RuntimeError(
            "missing_organization: select one with `museoncli org select` or pass --organization-id"
        )
    return ctx.organization_id


def with_notes(fn: Callable[[CommandContext], Any]) -> Executor:
    """An executor whose function returns ``(data, warnings, next_steps)``."""

    async def run(ctx: CommandContext) -> dict[str, Any]:
        data, warnings, next_steps = await fn(ctx)
        envelope = direct_api_envelope(ctx.spec.schema_name, data, site_url=ctx.cfg.site_url)
        envelope["warnings"] = [*envelope["warnings"], *warnings]
        envelope["next_steps"] = [*envelope["next_steps"], *next_steps]
        return envelope

    return run


def api_error_type() -> type[Exception]:
    # Late import: museoncli.main imports the domain registry.
    from museoncli.main import ApiRequestError

    return ApiRequestError
