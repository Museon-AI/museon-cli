"""One read command over one web route, addressed by the organization (no workspace).

The read modules of coverage batch 1 (tasks, Campaign setup, conversations, creators,
client reports, analytics boards, organization settings) each call the route the web
page already calls. A command declares its flags as a JSON schema; the same object can
come from ``--args-json`` / ``--args-file``. ``{organization_id}`` in a route's path is
the organization the command acts in (``X-Organization-Id``, from ``museoncli org
select`` or ``--organization-id``); every other ``{name}`` is the command's input.

What a login may read is the server's to decide, exactly as on the web: a refusal is
the server's ``not_found`` / ``forbidden``, never a client-side role table.
"""

from __future__ import annotations

import argparse
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from museoncli.domains._model import CommandSpec, Domain
from museoncli.domains._shared import _direct_output_schema
from museoncli.domains.hireaicreator import _load, _wire, obj
from museoncli.envelopes import direct_api_envelope
from museoncli.execution import CommandContext

Paging = Literal["cursor", "offset"] | None

PAGE_SIZE_MAX = 100
S = {"type": "string", "minLength": 1, "maxLength": 300}
B = {"type": "boolean"}
U = {"type": "string", "format": "uuid"}
D = {"type": "string", "format": "date"}
TZ = {"type": "string", "format": "timezone"}
PAGE = {"type": "integer", "minimum": 1, "description": "Page number, starting at 1."}
PAGE_SIZE = {
    "type": "integer",
    "minimum": 1,
    "maximum": PAGE_SIZE_MAX,
    "description": f"Records per page (1-{PAGE_SIZE_MAX}, default 50).",
}
CURSOR = {**S, "maxLength": 2000, "description": "next_cursor from the previous page."}


def uuid(description: str) -> dict[str, Any]:
    return {**U, "description": description}


def text(description: str, *, max_length: int = 200) -> dict[str, Any]:
    return {**S, "maxLength": max_length, "description": description}


def choice(description: str, *values: str) -> dict[str, Any]:
    """An enum flag: kebab-case on the CLI, snake_case on the wire (`_wire`)."""
    return {"type": "string", "enum": list(values), "description": description}


@dataclass(frozen=True, slots=True)
class Route:
    """One API read: its path template, the wire query, and the API version."""

    path: str
    query: dict[str, Any] = field(default_factory=dict)
    version: int = 2


Build = Callable[[dict[str, Any]], Route]
Execute = Callable[[CommandContext, dict[str, Any]], Awaitable[Any]]


def require_organization(ctx: CommandContext) -> str:
    if not ctx.organization_id:
        raise RuntimeError(
            "missing_organization: select one with `museoncli org select` or pass --organization-id"
        )
    return ctx.organization_id


async def get(ctx: CommandContext, route: Route, arguments: dict[str, Any] | None = None) -> Any:
    """Send one route's GET: its path filled from the organization and `arguments`."""
    values = dict(arguments or {})
    if "{organization_id}" in route.path:
        values["organization_id"] = require_organization(ctx)
    call = ctx.api_data_v2 if route.version == 2 else ctx.api_data
    return await call(
        ctx.cfg,
        "GET",
        route.path.format(**values),
        params={key: value for key, value in route.query.items() if value is not None} or None,
    )


def read(
    executors: dict[str, Any],
    domain: Domain,
    resource: str,
    action: str,
    *,
    summary: str,
    properties: dict[str, Any],
    example: str,
    route: Build | None = None,
    execute: Execute | None = None,
    required: tuple[str, ...] = (),
    paging: Paging = None,
    flags: dict[str, str | tuple[str, ...]] | None = None,
    check: Callable[[dict[str, Any]], None] | None = None,
    output: str = "Unmodified Museon API read model.",
) -> CommandSpec:
    """A read command: one `route` (or a bounded `execute` over several), registered in
    `executors` under its schema name."""
    if (route is None) == (execute is None):
        raise ValueError("a read names exactly one of route and execute")
    props = dict(properties)
    if paging == "cursor":
        props.update(cursor=CURSOR, page_size=PAGE_SIZE)
    elif paging == "offset":
        props.update(page=PAGE, page_size=PAGE_SIZE)
    schema = obj(props, required)
    name = f"{domain.value}.{resource}-{action}"
    aliases = flags or {}

    def add_arguments(parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--args-json")
        parser.add_argument("--args-file")
        for key, prop in props.items():
            kind = prop["type"]
            base = next(x for x in kind if x != "null") if isinstance(kind, list) else kind
            kwargs: dict[str, Any] = {"dest": key, "default": argparse.SUPPRESS}
            item = prop["items"] if base == "array" else prop
            if base == "boolean":
                kwargs["action"] = argparse.BooleanOptionalAction
            elif base == "array":
                kwargs["action"] = "append"
            elif base == "integer":
                kwargs["type"] = int
            if "enum" in item:
                kwargs["choices"] = [value for value in item["enum"] if value is not None]
            if prop.get("description"):
                kwargs["help"] = prop["description"]
            options = aliases.get(key, "--" + key.replace("_", "-"))
            parser.add_argument(*((options,) if isinstance(options, str) else options), **kwargs)

    def build(args: argparse.Namespace) -> dict[str, Any]:
        payload = _load(args, props, required)
        if check is not None:
            check(payload)
        return payload

    async def run(ctx: CommandContext) -> dict[str, Any]:
        arguments = _wire(dict(ctx.arguments), schema)
        if execute is not None:
            data = await execute(ctx, arguments)
        else:
            assert route is not None
            planned = route(arguments)
            query = dict(planned.query)
            size = arguments.get("page_size") or 50
            if paging == "cursor":
                query.update(cursor=arguments.get("cursor"), limit=size)
            elif paging == "offset":
                query.update(offset=(arguments.get("page", 1) - 1) * size, limit=size)
            data = await get(ctx, Route(planned.path, query, planned.version), arguments)
        return direct_api_envelope(name, data, site_url=ctx.cfg.site_url)

    executors[name] = run
    return CommandSpec(
        domain=domain,
        resource=resource,
        shortcut="+" + action,
        summary=summary,
        risk_level="read",
        execution="direct",
        adapter_tool_name=f"{domain.value}_{resource}_{action}".replace("-", "_"),
        input_schema=schema,
        output_schema=_direct_output_schema(output),
        examples=[example],
        add_arguments=add_arguments,
        build_arguments=build,
    )
