"""Read the organization's artifacts: the list and one artifact, as the /artifacts page does.

The list is the organization route (``/agent-artifacts/organizations/{organization_id}``):
the artifacts of every place in the organization the caller reaches. One artifact is read by
its id; the server finds where it lives from the addressed organization.

There is no delete: the API has no route that deletes an artifact. Revoke a public link with
``artifacts +unshare`` instead.
"""

from __future__ import annotations

import argparse
from typing import Any

from museoncli.domains._model import CommandSpec, Domain
from museoncli.domains._org_commands import (
    PAGE_PROPERTIES,
    add_page_arguments,
    add_structured_arguments,
    merged_input,
    output_schema,
    page_query,
    reject_unknown,
    require,
    require_organization,
    schema,
    uuid_property,
)
from museoncli.execution import CommandContext, direct_enveloped

_LIST_PROPERTIES = dict(PAGE_PROPERTIES)
_GET_PROPERTIES = {"id": uuid_property("Artifact ID (data.items[].id of artifacts +list).")}


async def _execute_list(ctx: CommandContext) -> Any:
    organization_id = require_organization(ctx)
    query = page_query(ctx.arguments)
    raw = await ctx.api_data(
        ctx.cfg,
        "GET",
        f"/agent-artifacts/organizations/{organization_id}",
        params=query,
    )
    if isinstance(raw, dict):
        # The route answers {items, total}; page and size make page_info complete.
        raw = {**raw, "page": query["page"], "page_size": query["limit"]}
    return raw


async def _execute_get(ctx: CommandContext) -> Any:
    return await ctx.api_data(ctx.cfg, "GET", f"/agent-artifacts/{ctx.arguments['id']}")


def _add_list_arguments(parser: argparse.ArgumentParser) -> None:
    add_structured_arguments(parser)
    add_page_arguments(parser)


def _build_list_arguments(args: argparse.Namespace) -> dict[str, Any]:
    payload = merged_input(args, ("page", "page_size", "search"))
    reject_unknown(payload, _LIST_PROPERTIES)
    page_query(payload)
    return payload


def _add_get_arguments(parser: argparse.ArgumentParser) -> None:
    add_structured_arguments(parser)
    parser.add_argument("--id", help="ID of the artifact to read.")


def _build_get_arguments(args: argparse.Namespace) -> dict[str, Any]:
    payload = merged_input(args, ("id",))
    reject_unknown(payload, _GET_PROPERTIES)
    require(payload, "id")
    return payload


def specs() -> list[CommandSpec]:
    return [
        CommandSpec(
            domain=Domain.ARTIFACTS,
            shortcut="+list",
            summary=(
                "List the organization's artifacts (reports and files uploaded with "
                "artifacts +upload), newest first, with title, type, is_public and public_url. "
                "Any organization role can read. Page with --page/--page-size or --all."
            ),
            risk_level="read",
            execution="direct",
            adapter_tool_name="artifact_list",
            input_schema=schema(_LIST_PROPERTIES),
            output_schema=output_schema(
                "data.items (id, title, artifact_type, is_public, public_url, created_at, "
                "updated_at), data.total, data.page, data.page_size."
            ),
            examples=[
                "museoncli artifacts +list --page-size 20",
                "museoncli artifacts +list --search weekly --all",
            ],
            add_arguments=_add_list_arguments,
            build_arguments=_build_list_arguments,
        ),
        CommandSpec(
            domain=Domain.ARTIFACTS,
            shortcut="+get",
            summary=(
                "Read one artifact: Markdown body (or download_url for a file), title, version, "
                "is_public and public_url. Any organization role can read."
            ),
            risk_level="read",
            execution="direct",
            adapter_tool_name="artifact_get",
            input_schema=schema(_GET_PROPERTIES, ["id"]),
            output_schema=output_schema(
                "data: id, title, artifact_type, render_kind, markdown or download_url, version, "
                "is_public, public_url."
            ),
            examples=["museoncli artifacts +get --id 72defd40-39ad-40d3-8105-8f23a9a016da"],
            add_arguments=_add_get_arguments,
            build_arguments=_build_get_arguments,
        ),
    ]


EXECUTORS = {
    "artifacts.list": direct_enveloped(_execute_list),
    "artifacts.get": direct_enveloped(_execute_get),
}
