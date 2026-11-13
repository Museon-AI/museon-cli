"""Media collections: named groups of media, as the Media page's collections are.

Every route but the list is addressed by the collection id, and the list is the
organization's (``/collections/organizations/{organization_id}``). Reading takes any
organization role; changing a collection or its media takes owner, admin or operator
(asset edit), which the server decides.

``+create`` makes a collection in the selected organization: the server stores it in the
caller's own workspace of that organization, so no workspace is named.
"""

from __future__ import annotations

import argparse
from typing import Any

from museoncli.domains._model import CommandSpec, Domain
from museoncli.domains._org_commands import (
    DRY_RUN_PROPERTY,
    PAGE_PROPERTIES,
    add_page_arguments,
    add_structured_arguments,
    api_error_type,
    merged_input,
    output_schema,
    page_query,
    reject_unknown,
    require,
    require_organization,
    schema,
    string_list,
    string_property,
    uuid_property,
    with_notes,
)
from museoncli.execution import CommandContext, direct_enveloped

_MAX_MEDIA = 100
_COLLECTION_ID = uuid_property("Collection ID (data.data[].id of media collection +list).")
_MEDIA_IDS = {
    "type": "array",
    "items": {"type": "string", "format": "uuid"},
    "minItems": 1,
    "maxItems": _MAX_MEDIA,
    "description": (
        "Media IDs (media +get / media +upload). Repeat --media-id for several, up to 100."
    ),
}
_EDIT_ROLE = " Needs owner, admin or operator."

_LIST = dict(PAGE_PROPERTIES)
_GET = {"id": _COLLECTION_ID}
_LIST_MEDIA = {"id": _COLLECTION_ID, **PAGE_PROPERTIES}
_CREATE = {
    "name": string_property("Collection name.", max_length=200),
    "dry_run": DRY_RUN_PROPERTY,
}
_UPDATE = {
    "id": _COLLECTION_ID,
    "name": string_property("New collection name.", max_length=200),
}
_DELETE = {"id": _COLLECTION_ID, "dry_run": DRY_RUN_PROPERTY}
_ADD = {"id": _COLLECTION_ID, "media_ids": _MEDIA_IDS}
_REMOVE = {"id": _COLLECTION_ID, "media_ids": _MEDIA_IDS, "dry_run": DRY_RUN_PROPERTY}


def _path(collection_id: str, suffix: str = "") -> str:
    return f"/collections/{collection_id}{suffix}"


# -- executors ---------------------------------------------------------------


async def _execute_list(ctx: CommandContext) -> Any:
    organization_id = require_organization(ctx)
    return await ctx.api_data(
        ctx.cfg,
        "GET",
        f"/collections/organizations/{organization_id}",
        params=page_query(ctx.arguments),
    )


async def _execute_get(ctx: CommandContext) -> Any:
    return await ctx.api_data(ctx.cfg, "GET", _path(ctx.arguments["id"]))


async def _execute_list_media(ctx: CommandContext) -> Any:
    return await ctx.api_data(
        ctx.cfg, "GET", _path(ctx.arguments["id"], "/media"), params=page_query(ctx.arguments)
    )


async def _execute_create(ctx: CommandContext) -> Any:
    data = await ctx.api_data(
        ctx.cfg, "POST", "/collections", json_body={"name": ctx.arguments["name"]}
    )
    return (
        data,
        [
            "Creating has no idempotency key: after an unknown outcome, run media collection "
            "+list before trying again, or a second collection of the same name appears."
        ],
        ["museoncli media collection +add --id <collection id> --media-id <media id>"],
    )


async def _execute_update(ctx: CommandContext) -> Any:
    return await ctx.api_data(
        ctx.cfg, "PUT", _path(ctx.arguments["id"]), json_body={"name": ctx.arguments["name"]}
    )


async def _execute_add(ctx: CommandContext) -> Any:
    data = await ctx.api_data(
        ctx.cfg,
        "POST",
        _path(ctx.arguments["id"], "/media/bulk"),
        json_body={"media_ids": ctx.arguments["media_ids"]},
    )
    return data, [], [f"museoncli media collection +list-media --id {ctx.arguments['id']}"]


async def _execute_delete(ctx: CommandContext) -> Any:
    args = ctx.arguments
    collection = await ctx.api_data(ctx.cfg, "GET", _path(args["id"]))
    if args.get("dry_run"):
        return (
            {"dry_run": True, "would_delete": collection},
            [],
            [
                "Show the user the collection and its media_count, then run again with --yes. "
                "The media stay in the library; only the collection goes."
            ],
        )
    await ctx.api_data(ctx.cfg, "DELETE", _path(args["id"]))
    return {"deleted": True, "collection": collection}, [], []


async def _execute_remove(ctx: CommandContext) -> Any:
    args = ctx.arguments
    collection = await ctx.api_data(ctx.cfg, "GET", _path(args["id"]))
    if args.get("dry_run"):
        return (
            {"dry_run": True, "collection": collection, "would_remove": args["media_ids"]},
            [],
            ["Show the user which media leave the collection, then run again with --yes."],
        )
    api_error = api_error_type()
    removed: list[str] = []
    failed: list[dict[str, Any]] = []
    # One DELETE per media, in order; a media already gone answers 404 and is reported, so a
    # rerun of the same list is safe.
    for media_id in args["media_ids"]:
        try:
            await ctx.api_data(ctx.cfg, "DELETE", _path(args["id"], f"/media/{media_id}"))
        except api_error as exc:
            failed.append(
                {
                    "media_id": media_id,
                    "http_status": getattr(exc, "status_code", None),
                    "detail": getattr(exc, "detail", str(exc)),
                }
            )
        else:
            removed.append(media_id)
    warnings = (
        [f"{len(failed)} of {len(args['media_ids'])} media were not removed; see data.failed."]
        if failed
        else []
    )
    return {"collection_id": args["id"], "removed": removed, "failed": failed}, warnings, []


# -- arguments ---------------------------------------------------------------


def _add_id(parser: argparse.ArgumentParser) -> None:
    add_structured_arguments(parser)
    parser.add_argument("--id")


def _add_list_arguments(parser: argparse.ArgumentParser) -> None:
    add_structured_arguments(parser)
    add_page_arguments(parser)


def _build_list_arguments(args: argparse.Namespace) -> dict[str, Any]:
    payload = merged_input(args, ("page", "page_size", "search"))
    reject_unknown(payload, _LIST)
    page_query(payload)
    return payload


def _build_get_arguments(args: argparse.Namespace) -> dict[str, Any]:
    payload = merged_input(args, ("id",))
    reject_unknown(payload, _GET)
    require(payload, "id")
    return payload


def _add_list_media_arguments(parser: argparse.ArgumentParser) -> None:
    _add_id(parser)
    add_page_arguments(parser)


def _build_list_media_arguments(args: argparse.Namespace) -> dict[str, Any]:
    payload = merged_input(args, ("id", "page", "page_size", "search"))
    reject_unknown(payload, _LIST_MEDIA)
    require(payload, "id")
    page_query(payload)
    return payload


def _add_create_arguments(parser: argparse.ArgumentParser) -> None:
    add_structured_arguments(parser)
    parser.add_argument("--name")
    parser.add_argument("--dry-run", action="store_true")


def _build_create_arguments(args: argparse.Namespace) -> dict[str, Any]:
    payload = merged_input(args, ("name",))
    reject_unknown(payload, _CREATE)
    require(payload, "name")
    name = str(payload["name"]).strip()
    if not 1 <= len(name) <= 200:
        raise ValueError("--name must be 1-200 characters.")
    payload["name"] = name
    payload["dry_run"] = bool(getattr(args, "dry_run", False) or payload.get("dry_run"))
    return payload


def _add_update_arguments(parser: argparse.ArgumentParser) -> None:
    _add_id(parser)
    parser.add_argument("--name")
    parser.add_argument("--dry-run", action="store_true")


def _build_update_arguments(args: argparse.Namespace) -> dict[str, Any]:
    payload = merged_input(args, ("id", "name"))
    reject_unknown(payload, _UPDATE)
    require(payload, "id", "name")
    name = str(payload["name"]).strip()
    if not 1 <= len(name) <= 200:
        raise ValueError("--name must be 1-200 characters.")
    payload["name"] = name
    return payload


def _add_delete_arguments(parser: argparse.ArgumentParser) -> None:
    _add_id(parser)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--yes", action="store_true")


def _build_delete_arguments(args: argparse.Namespace) -> dict[str, Any]:
    payload = merged_input(args, ("id",))
    reject_unknown(payload, _DELETE)
    require(payload, "id")
    payload["dry_run"] = bool(getattr(args, "dry_run", False) or payload.get("dry_run"))
    return payload


def _add_media_arguments(parser: argparse.ArgumentParser) -> None:
    _add_id(parser)
    parser.add_argument("--media-id", dest="media_ids", action="append")
    parser.add_argument("--dry-run", action="store_true")


def _add_remove_arguments(parser: argparse.ArgumentParser) -> None:
    _add_media_arguments(parser)
    parser.add_argument("--yes", action="store_true")


def _media_payload(args: argparse.Namespace, properties: dict[str, Any]) -> dict[str, Any]:
    payload = merged_input(args, ("id", "media_ids"))
    reject_unknown(payload, properties)
    require(payload, "id", "media_ids")
    payload["media_ids"] = string_list(payload["media_ids"], field="--media-id", maximum=_MAX_MEDIA)
    require(payload, "media_ids")
    return payload


def _build_add_arguments(args: argparse.Namespace) -> dict[str, Any]:
    return _media_payload(args, _ADD)


def _build_remove_arguments(args: argparse.Namespace) -> dict[str, Any]:
    payload = _media_payload(args, _REMOVE)
    payload["dry_run"] = bool(getattr(args, "dry_run", False) or payload.get("dry_run"))
    return payload


# -- specs -------------------------------------------------------------------

_EXAMPLE_ID = "72defd40-39ad-40d3-8105-8f23a9a016da"
_EXAMPLE_MEDIA = "5b0b2f3e-8c1d-4f0a-9d7e-2a6c1e4b9f10"


def specs() -> list[CommandSpec]:
    base: dict[str, Any] = {"domain": Domain.MEDIA, "resource": "collection", "execution": "direct"}
    return [
        CommandSpec(
            **base,
            shortcut="+list",
            summary=(
                "List the organization's media collections with media_count and preview media. "
                "Any organization role can read. Page with --page/--page-size or --all."
            ),
            risk_level="read",
            adapter_tool_name="media_collection_list",
            input_schema=schema(_LIST),
            output_schema=output_schema("data.data (collections) and data.pagination."),
            examples=["museoncli media collection +list --search launch"],
            add_arguments=_add_list_arguments,
            build_arguments=_build_list_arguments,
        ),
        CommandSpec(
            **base,
            shortcut="+get",
            summary="Read one media collection with its media_count. Any organization role.",
            risk_level="read",
            adapter_tool_name="media_collection_get",
            input_schema=schema(_GET, ["id"]),
            output_schema=output_schema("data: id, name, media_count, content_count."),
            examples=[f"museoncli media collection +get --id {_EXAMPLE_ID}"],
            add_arguments=_add_id,
            build_arguments=_build_get_arguments,
        ),
        CommandSpec(
            **base,
            shortcut="+list-media",
            summary=(
                "List the media in one collection, in order, with media_url, media_type and "
                "thumbnail_url. Any organization role. Page with --page/--page-size or --all."
            ),
            risk_level="read",
            adapter_tool_name="media_collection_list_media",
            input_schema=schema(_LIST_MEDIA, ["id"]),
            output_schema=output_schema("data.data (collection media) and data.pagination."),
            examples=[f"museoncli media collection +list-media --id {_EXAMPLE_ID} --all"],
            add_arguments=_add_list_media_arguments,
            build_arguments=_build_list_media_arguments,
        ),
        CommandSpec(
            **base,
            shortcut="+create",
            summary=(
                "Create an empty media collection in the selected organization; fill it with "
                "+add. No idempotency key: after an unknown outcome, +list before retrying."
                + _EDIT_ROLE
            ),
            risk_level="write",
            adapter_tool_name="media_collection_create",
            input_schema=schema(_CREATE, ["name"]),
            output_schema=output_schema("data: the new collection (id, name, media_count)."),
            examples=["museoncli media collection +create --name 'Spring launch'"],
            add_arguments=_add_create_arguments,
            build_arguments=_build_create_arguments,
            supports_dry_run=True,
        ),
        CommandSpec(
            **base,
            shortcut="+update",
            summary="Rename a media collection." + _EDIT_ROLE,
            risk_level="write",
            adapter_tool_name="media_collection_update",
            input_schema=schema(_UPDATE, ["id", "name"]),
            output_schema=output_schema("data: the collection after the rename."),
            examples=[
                f"museoncli media collection +update --id {_EXAMPLE_ID} --name 'Spring launch'"
            ],
            add_arguments=_add_update_arguments,
            build_arguments=_build_update_arguments,
            supports_dry_run=True,
        ),
        CommandSpec(
            **base,
            shortcut="+delete",
            summary=(
                "Delete a media collection; its media stay in the library. --dry-run reads the "
                "collection and deletes nothing; show it to the user, then run with --yes."
                + _EDIT_ROLE
            ),
            risk_level="destructive",
            adapter_tool_name="media_collection_delete",
            input_schema=schema(_DELETE, ["id"]),
            output_schema=output_schema(
                "data.would_delete (dry run) or data.deleted and data.collection."
            ),
            examples=[
                f"museoncli media collection +delete --id {_EXAMPLE_ID} --dry-run",
                f"museoncli media collection +delete --id {_EXAMPLE_ID} --yes",
            ],
            add_arguments=_add_delete_arguments,
            build_arguments=_build_delete_arguments,
            supports_dry_run=True,
            dry_run_reads_server=True,
            requires_confirmation=True,
        ),
        CommandSpec(
            **base,
            shortcut="+add",
            summary=(
                "Add up to 100 media to a collection; media already in it are skipped "
                "(data.added, data.skipped), so a rerun is safe. Media must come from the same "
                "organization library as the collection." + _EDIT_ROLE
            ),
            risk_level="write",
            adapter_tool_name="media_collection_add",
            input_schema=schema(_ADD, ["id", "media_ids"]),
            output_schema=output_schema("data: added, skipped, message."),
            examples=[
                f"museoncli media collection +add --id {_EXAMPLE_ID} --media-id {_EXAMPLE_MEDIA}"
            ],
            add_arguments=_add_media_arguments,
            build_arguments=_build_add_arguments,
            supports_dry_run=True,
        ),
        CommandSpec(
            **base,
            shortcut="+remove",
            summary=(
                "Remove up to 100 media from a collection (the media stay in the library). "
                "--dry-run reads the collection and removes nothing; then run with --yes. Each "
                "media is removed on its own: data.removed and data.failed list the outcome."
                + _EDIT_ROLE
            ),
            risk_level="destructive",
            adapter_tool_name="media_collection_remove",
            input_schema=schema(_REMOVE, ["id", "media_ids"]),
            output_schema=output_schema("data: collection_id, removed, failed."),
            examples=[
                f"museoncli media collection +remove --id {_EXAMPLE_ID} "
                f"--media-id {_EXAMPLE_MEDIA} --yes"
            ],
            add_arguments=_add_remove_arguments,
            build_arguments=_build_remove_arguments,
            supports_dry_run=True,
            dry_run_reads_server=True,
            requires_confirmation=True,
        ),
    ]


EXECUTORS = {
    "media.collection-list": direct_enveloped(_execute_list),
    "media.collection-get": direct_enveloped(_execute_get),
    "media.collection-list-media": direct_enveloped(_execute_list_media),
    "media.collection-create": with_notes(_execute_create),
    "media.collection-update": direct_enveloped(_execute_update),
    "media.collection-add": with_notes(_execute_add),
    "media.collection-delete": with_notes(_execute_delete),
    "media.collection-remove": with_notes(_execute_remove),
}
