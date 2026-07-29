"""Product CTA target commands backed by the public v1 API."""

from __future__ import annotations

import argparse
from typing import Any

from museoncli.domains._model import CommandSpec, Domain
from museoncli.domains._shared import _direct_output_schema
from museoncli.execution import CommandContext, redacted_direct_enveloped


def _csv(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in str(value).split(",") if item.strip()]


def _uuid_property(description: str) -> dict[str, Any]:
    return {"type": "string", "format": "uuid", "description": description}


def _asset_schema() -> dict[str, Any]:
    return {
        "type": "array",
        "items": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "media_id": _uuid_property("Uploaded media id"),
                "sort_order": {"type": "integer", "minimum": 0},
            },
            "required": ["media_id", "sort_order"],
        },
    }


def _add_list_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--product-id", required=True)


def _build_list_arguments(args: argparse.Namespace) -> dict[str, Any]:
    return {"product_id": args.product_id}


def _add_create_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--product-id", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--content-markdown", required=True)
    parser.add_argument("--asset-ids")
    parser.add_argument("--dry-run", action="store_true")


def _assets(value: str | None) -> list[dict[str, Any]]:
    return [
        {"media_id": media_id, "sort_order": index} for index, media_id in enumerate(_csv(value))
    ]


def _build_create_arguments(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "product_id": args.product_id,
        "title": args.title,
        "content_markdown": args.content_markdown,
        "assets": _assets(args.asset_ids),
        "dry_run": args.dry_run,
    }


def _add_update_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--product-id", required=True)
    parser.add_argument("--cta-target-id", required=True)
    parser.add_argument("--title")
    parser.add_argument("--content-markdown")
    parser.add_argument("--asset-ids")
    parser.add_argument("--dry-run", action="store_true")


def _build_update_arguments(args: argparse.Namespace) -> dict[str, Any]:
    mutable: dict[str, Any] = {}
    if args.title is not None:
        mutable["title"] = args.title
    if args.content_markdown is not None:
        mutable["content_markdown"] = args.content_markdown
    if args.asset_ids is not None:
        mutable["assets"] = _assets(args.asset_ids)
    if not mutable:
        raise ValueError("product +cta-target-update requires at least one mutable flag.")
    return {
        "product_id": args.product_id,
        "cta_target_id": args.cta_target_id,
        **mutable,
        "dry_run": args.dry_run,
    }


def specs() -> list[CommandSpec]:
    asset_note = (
        "Upload assets with the asset domain first to obtain media ids; "
        "this command only references them."
    )
    return [
        CommandSpec(
            domain=Domain.PRODUCT,
            shortcut="+cta-target-list",
            summary=f"List CTA targets for a Product. {asset_note}",
            risk_level="read",
            execution="direct",
            adapter_tool_name="product_cta_target_list",
            input_schema={
                "type": "object",
                "properties": {"product_id": _uuid_property("Product id")},
                "required": ["product_id"],
            },
            output_schema=_direct_output_schema("Product CTA targets."),
            examples=[
                "museoncli product +cta-target-list "
                "--product-id 22222222-2222-4222-8222-222222222222"
            ],
            add_arguments=_add_list_arguments,
            build_arguments=_build_list_arguments,
        ),
        CommandSpec(
            domain=Domain.PRODUCT,
            shortcut="+cta-target-create",
            summary=f"Create a CTA target for a Product. {asset_note}",
            risk_level="write",
            execution="direct",
            adapter_tool_name="product_cta_target_create",
            input_schema={
                "type": "object",
                "properties": {
                    "product_id": _uuid_property("Product id"),
                    "title": {"type": "string", "minLength": 1, "maxLength": 200},
                    "content_markdown": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 10000,
                    },
                    "assets": _asset_schema(),
                    "dry_run": {"type": "boolean", "default": False},
                },
                "required": ["product_id", "title", "content_markdown"],
            },
            output_schema=_direct_output_schema("Created Product CTA target."),
            examples=[
                "museoncli product +cta-target-create "
                "--product-id 22222222-2222-4222-8222-222222222222 "
                "--title 'Shop now' --content-markdown 'See the collection.'"
            ],
            add_arguments=_add_create_arguments,
            build_arguments=_build_create_arguments,
            supports_dry_run=True,
        ),
        CommandSpec(
            domain=Domain.PRODUCT,
            shortcut="+cta-target-update",
            summary=f"Patch supplied CTA target fields. {asset_note}",
            risk_level="write",
            execution="direct",
            adapter_tool_name="product_cta_target_update",
            input_schema={
                "type": "object",
                "properties": {
                    "product_id": _uuid_property("Product id"),
                    "cta_target_id": _uuid_property("CTA target id"),
                    "title": {"type": "string", "minLength": 1, "maxLength": 200},
                    "content_markdown": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 10000,
                    },
                    "assets": _asset_schema(),
                    "dry_run": {"type": "boolean", "default": False},
                },
                "required": ["product_id", "cta_target_id"],
            },
            output_schema=_direct_output_schema("Updated Product CTA target."),
            examples=[
                "museoncli product +cta-target-update "
                "--product-id 22222222-2222-4222-8222-222222222222 "
                "--cta-target-id 33333333-3333-4333-8333-333333333333 "
                "--asset-ids ''"
            ],
            add_arguments=_add_update_arguments,
            build_arguments=_build_update_arguments,
            supports_dry_run=True,
        ),
    ]


async def _execute_list(ctx: CommandContext) -> Any:
    return await ctx.api_data(
        ctx.cfg,
        "GET",
        f"/products/{ctx.arguments['product_id']}/cta-targets",
    )


async def _execute_create(ctx: CommandContext) -> Any:
    return await ctx.api_data(
        ctx.cfg,
        "POST",
        f"/products/{ctx.arguments['product_id']}/cta-targets",
        json_body={
            "title": ctx.arguments["title"],
            "content_markdown": ctx.arguments["content_markdown"],
            "assets": ctx.arguments["assets"],
        },
    )


async def _execute_update(ctx: CommandContext) -> Any:
    body = {
        key: value
        for key, value in ctx.arguments.items()
        if key in {"title", "content_markdown", "assets"}
    }
    return await ctx.api_data(
        ctx.cfg,
        "PATCH",
        (f"/products/{ctx.arguments['product_id']}/cta-targets/{ctx.arguments['cta_target_id']}"),
        json_body=body,
    )


EXECUTORS = {
    "product.cta-target-list": redacted_direct_enveloped(_execute_list, redact_api_errors=True),
    "product.cta-target-create": redacted_direct_enveloped(_execute_create, redact_api_errors=True),
    "product.cta-target-update": redacted_direct_enveloped(_execute_update, redact_api_errors=True),
}
