"""Product CTA targets: what a post points viewers to (title, Markdown body, images).

Routes are the product's (``/products/{product_id}/cta-targets``), as the product page
calls them. Listing, creating and editing targets is staff only today; retiring one takes
owner, admin or operator (product edit). The server decides both.
"""

from __future__ import annotations

import argparse
from typing import Any

from museoncli.domains._model import CommandSpec, Domain
from museoncli.domains._org_commands import (
    add_structured_arguments,
    merged_input,
    output_schema,
    reject_unknown,
    require,
    schema,
    string_list,
    string_property,
    uuid_property,
    with_notes,
)
from museoncli.execution import CommandContext, direct_enveloped

_MAX_ASSETS = 20
_STATUSES = ["active", "retired"]

_PRODUCT_ID = uuid_property("Product ID (ai-slideshow asset +list --type product).")
_TARGET_ID = uuid_property("CTA target ID (data[].id of ai-slideshow cta-target +list).")
_FIELDS = {
    "title": string_property("Target title.", max_length=200),
    "content_markdown": string_property("Target body in Markdown.", max_length=10000),
    "sort_order": {"type": "integer", "minimum": 0, "description": "Position among targets."},
    "media_ids": {
        "type": "array",
        "items": {"type": "string", "format": "uuid"},
        "maxItems": _MAX_ASSETS,
        "description": (
            "Images shown with the target, in order (media +upload / media +import). Repeat "
            "--media-id; on +update the list replaces the current images."
        ),
    },
}
_LIST = {"product_id": _PRODUCT_ID}
_CREATE = {"product_id": _PRODUCT_ID, **_FIELDS}
_UPDATE = {
    "product_id": _PRODUCT_ID,
    "id": _TARGET_ID,
    **_FIELDS,
    "status": {"type": "string", "enum": _STATUSES, "description": "active or retired."},
}
_RETIRE = {"product_id": _PRODUCT_ID, "id": _TARGET_ID}
_STAFF = " Staff only (the server refuses other callers)."


def _path(product_id: str, suffix: str = "") -> str:
    return f"/products/{product_id}/cta-targets{suffix}"


def _body(arguments: dict[str, Any]) -> dict[str, Any]:
    body = {
        key: arguments[key]
        for key in ("title", "content_markdown", "sort_order", "status")
        if key in arguments
    }
    if "media_ids" in arguments:
        body["assets"] = [
            {"media_id": media_id, "sort_order": index}
            for index, media_id in enumerate(arguments["media_ids"])
        ]
    return body


async def _execute_list(ctx: CommandContext) -> Any:
    return await ctx.api_data(ctx.cfg, "GET", _path(ctx.arguments["product_id"]))


async def _execute_create(ctx: CommandContext) -> Any:
    data = await ctx.api_data(
        ctx.cfg, "POST", _path(ctx.arguments["product_id"]), json_body=_body(ctx.arguments)
    )
    return (
        data,
        [
            "Creating has no idempotency key: after an unknown outcome, run ai-slideshow "
            "cta-target +list before trying again."
        ],
        [],
    )


async def _execute_update(ctx: CommandContext) -> Any:
    args = ctx.arguments
    return await ctx.api_data(
        ctx.cfg, "PATCH", _path(args["product_id"], f"/{args['id']}"), json_body=_body(args)
    )


async def _execute_retire(ctx: CommandContext) -> Any:
    args = ctx.arguments
    return await ctx.api_data(
        ctx.cfg, "POST", _path(args["product_id"], f"/{args['id']}:retire"), json_body={}
    )


# -- arguments ---------------------------------------------------------------


def _add_product(parser: argparse.ArgumentParser) -> None:
    add_structured_arguments(parser)
    parser.add_argument("--product-id")


def _add_fields(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--title")
    parser.add_argument("--content-markdown")
    parser.add_argument("--sort-order", type=int)
    parser.add_argument("--media-id", dest="media_ids", action="append")
    parser.add_argument("--dry-run", action="store_true")


def _add_create_arguments(parser: argparse.ArgumentParser) -> None:
    _add_product(parser)
    _add_fields(parser)


def _add_update_arguments(parser: argparse.ArgumentParser) -> None:
    _add_product(parser)
    parser.add_argument("--id")
    _add_fields(parser)
    parser.add_argument("--status", choices=_STATUSES)


def _add_retire_arguments(parser: argparse.ArgumentParser) -> None:
    _add_product(parser)
    parser.add_argument("--id")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--yes", action="store_true")


_FIELD_DESTS = ("title", "content_markdown", "sort_order", "media_ids")


def _check_fields(payload: dict[str, Any]) -> None:
    for key, limit in (("title", 200), ("content_markdown", 10000)):
        if key in payload and (
            not isinstance(payload[key], str) or not 1 <= len(payload[key].strip()) <= limit
        ):
            raise ValueError(f"--{key.replace('_', '-')} must be 1-{limit} characters.")
    if "sort_order" in payload and (
        not isinstance(payload["sort_order"], int) or payload["sort_order"] < 0
    ):
        raise ValueError("--sort-order must be 0 or more.")
    if "media_ids" in payload:
        payload["media_ids"] = string_list(
            payload["media_ids"], field="--media-id", maximum=_MAX_ASSETS
        )


def _build_list_arguments(args: argparse.Namespace) -> dict[str, Any]:
    payload = merged_input(args, ("product_id",))
    reject_unknown(payload, _LIST)
    require(payload, "product_id")
    return payload


def _build_create_arguments(args: argparse.Namespace) -> dict[str, Any]:
    payload = merged_input(args, ("product_id", *_FIELD_DESTS))
    reject_unknown(payload, _CREATE)
    require(payload, "product_id", "title", "content_markdown")
    _check_fields(payload)
    return payload


def _build_update_arguments(args: argparse.Namespace) -> dict[str, Any]:
    payload = merged_input(args, ("product_id", "id", *_FIELD_DESTS, "status"))
    reject_unknown(payload, _UPDATE)
    require(payload, "product_id", "id")
    _check_fields(payload)
    if "status" in payload and payload["status"] not in _STATUSES:
        raise ValueError("--status must be active or retired.")
    if not any(key in payload for key in (*_FIELD_DESTS, "status")):
        raise ValueError(
            "Nothing to change: give --title, --content-markdown, --sort-order, --media-id "
            "or --status."
        )
    return payload


def _build_retire_arguments(args: argparse.Namespace) -> dict[str, Any]:
    payload = merged_input(args, ("product_id", "id"))
    reject_unknown(payload, _RETIRE)
    require(payload, "product_id", "id")
    return payload


# -- specs -------------------------------------------------------------------

_P = "72defd40-39ad-40d3-8105-8f23a9a016da"
_T = "0d9c3b7a-1f2e-4c5d-8e9f-a0b1c2d3e4f5"


def specs() -> list[CommandSpec]:
    base: dict[str, Any] = {
        "domain": Domain.AI_SLIDESHOW,
        "resource": "cta-target",
        "execution": "direct",
    }
    return [
        CommandSpec(
            **base,
            shortcut="+list",
            summary=(
                "List a product's CTA targets (what its posts point viewers to): title, "
                "Markdown body, images and status." + _STAFF
            ),
            risk_level="read",
            adapter_tool_name="product_cta_target_list",
            input_schema=schema(_LIST, ["product_id"]),
            output_schema=output_schema("data: the product's CTA targets."),
            examples=[f"museoncli ai-slideshow cta-target +list --product-id {_P}"],
            add_arguments=_add_product,
            build_arguments=_build_list_arguments,
        ),
        CommandSpec(
            **base,
            shortcut="+create",
            summary=(
                "Create a CTA target for a product: title, Markdown body, optional ordered "
                "images. No idempotency key: after an unknown outcome, list before retrying."
                + _STAFF
            ),
            risk_level="write",
            adapter_tool_name="product_cta_target_create",
            input_schema=schema(_CREATE, ["product_id", "title", "content_markdown"]),
            output_schema=output_schema("data: the created CTA target."),
            examples=[
                f"museoncli ai-slideshow cta-target +create --product-id {_P} "
                "--title 'Try it free' --content-markdown 'Download at example.com'"
            ],
            add_arguments=_add_create_arguments,
            build_arguments=_build_create_arguments,
            supports_dry_run=True,
        ),
        CommandSpec(
            **base,
            shortcut="+update",
            summary=(
                "Change a CTA target's title, body, position, images (--media-id replaces "
                "them) or status. Only the given fields change." + _STAFF
            ),
            risk_level="write",
            adapter_tool_name="product_cta_target_update",
            input_schema=schema(_UPDATE, ["product_id", "id"]),
            output_schema=output_schema("data: the CTA target after the change."),
            examples=[
                f"museoncli ai-slideshow cta-target +update --product-id {_P} --id {_T} "
                "--title 'Start free today'"
            ],
            add_arguments=_add_update_arguments,
            build_arguments=_build_update_arguments,
            supports_dry_run=True,
        ),
        CommandSpec(
            **base,
            shortcut="+retire",
            summary=(
                "Retire a CTA target so new posts stop using it (requires --yes; confirm with "
                "the user first). Needs owner, admin or operator."
            ),
            risk_level="write",
            adapter_tool_name="product_cta_target_retire",
            input_schema=schema(_RETIRE, ["product_id", "id"]),
            output_schema=output_schema("data: the retired CTA target."),
            examples=[
                f"museoncli ai-slideshow cta-target +retire --product-id {_P} --id {_T} --yes"
            ],
            add_arguments=_add_retire_arguments,
            build_arguments=_build_retire_arguments,
            supports_dry_run=True,
            requires_confirmation=True,
        ),
    ]


EXECUTORS = {
    "ai-slideshow.cta-target-list": direct_enveloped(_execute_list),
    "ai-slideshow.cta-target-create": with_notes(_execute_create),
    "ai-slideshow.cta-target-update": direct_enveloped(_execute_update),
    "ai-slideshow.cta-target-retire": direct_enveloped(_execute_retire),
}
