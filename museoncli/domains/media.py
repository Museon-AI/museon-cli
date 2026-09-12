"""Small file primitives backed by the existing media API."""

from __future__ import annotations

import argparse
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from museoncli.domains._model import CommandSpec, Domain
from museoncli.domains._shared import _direct_output_schema, _uuid_id_schema, _without_none
from museoncli.execution import CommandContext, direct_enveloped


def _upload_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--workspace-id")
    parser.add_argument("--file", required=True)
    parser.add_argument("--media-type", choices=["image", "video", "audio", "file"], required=True)
    parser.add_argument(
        "--file-id", help="Stable UUID for a private general-file upload; generated if omitted."
    )
    parser.add_argument("--title")
    parser.add_argument("--description")
    parser.add_argument("--dry-run", action="store_true")


def _upload_payload(args: argparse.Namespace) -> dict[str, Any]:
    if args.media_type != "file" and args.file_id is not None:
        raise ValueError("--file-id only applies to --media-type file")
    if args.media_type == "file" and args.description is not None:
        raise ValueError("General files do not accept --description")
    file_id = str(UUID(args.file_id)) if args.file_id else str(uuid4())
    return _without_none(
        {
            "file_id": file_id if args.media_type == "file" else None,
            "file": args.file,
            "media_type": args.media_type,
            "title": args.title,
            "description": args.description,
        }
    )


def _import_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--workspace-id")
    parser.add_argument("--url", required=True, help="Direct image URL; not video or audio.")
    parser.add_argument("--source-page-url")
    parser.add_argument("--dry-run", action="store_true")


def _import_payload(args: argparse.Namespace) -> dict[str, Any]:
    for value in (args.url, args.source_page_url):
        if value is not None:
            parsed = urlsplit(value)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError("media +import requires absolute HTTP(S) URLs.")
    return _without_none({"url": args.url, "source_page_url": args.source_page_url})


def _get_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--workspace-id")
    parser.add_argument("--id", required=True)
    parser.add_argument("--kind", choices=["media", "file"], default="media")


def _get_payload(args: argparse.Namespace) -> dict[str, Any]:
    return {"id": args.id, "kind": args.kind}


async def _upload(ctx: CommandContext) -> Any:
    if not ctx.workspace_id:
        raise RuntimeError("missing_workspace")
    if ctx.arguments["media_type"] == "file":
        try:
            receipt = await ctx.upload_artifact_file(
                ctx.cfg, workspace_id=ctx.workspace_id, arguments=ctx.arguments
            )
            if (
                not isinstance(receipt, dict)
                or receipt.get("artifact_id") != ctx.arguments["file_id"]
                or receipt.get("workspace_id") != ctx.workspace_id
                or receipt.get("kind") != "file"
                or receipt.get("is_public") is not False
            ):
                raise RuntimeError("File receipt did not contain the submitted artifact identity")
            return receipt
        except Exception as exc:
            raise RuntimeError(
                f"file_upload_unverified: artifact_id={ctx.arguments['file_id']}; "
                f"read media +get --kind file --id with this ID before retrying; cause={exc}"
            ) from exc
    response = await ctx.upload_media_file(
        ctx.cfg, workspace_id=ctx.workspace_id, arguments=ctx.arguments
    )
    if not isinstance(response, dict) or response.get("success") is not True:
        raise RuntimeError("media_upload_failed")
    return response.get("data")


async def _import(ctx: CommandContext) -> Any:
    if not ctx.workspace_id:
        raise RuntimeError("missing_workspace")
    receipt = await ctx.api_data(
        ctx.cfg,
        "POST",
        "/agent-cli/assets",
        json_body={
            "workspace_id": ctx.workspace_id,
            "type": "media",
            "payload": ctx.arguments,
        },
    )
    asset = receipt.get("asset") if isinstance(receipt, dict) else None
    media_id = asset.get("media_id") if isinstance(asset, dict) else None
    try:
        UUID(str(media_id))
    except (ValueError, TypeError, AttributeError):
        raise RuntimeError(
            "media_import_unverified: receipt has no valid media_id; do not retry the write blindly"
        ) from None
    return receipt


async def _get(ctx: CommandContext) -> Any:
    if not ctx.workspace_id:
        raise RuntimeError("missing_workspace")
    return await ctx.api_data(
        ctx.cfg,
        "GET",
        (
            f"/agent-artifacts/{ctx.arguments['id']}"
            if ctx.arguments["kind"] == "file"
            else f"/agent-cli/assets/media/{ctx.arguments['id']}"
        ),
        params={"workspace_id": ctx.workspace_id},
    )


def _generate_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--workspace-id")
    parser.add_argument("--type", choices=["image", "video"], required=True)
    parser.add_argument("--prompt", required=True)
    parser.add_argument(
        "--model", choices=["gpt-image-2.5-flare", "gpt-image-2.5-sunburst", "kling-3.0-standard"]
    )
    parser.add_argument("--duration-seconds", type=int)
    parser.add_argument("--aspect-ratio", choices=["9:16", "16:9", "1:1"])
    parser.add_argument("--idempotency-key", required=True)
    parser.add_argument("--dry-run", action="store_true")


def _generate_payload(args: argparse.Namespace) -> dict[str, Any]:
    if not args.prompt.strip() or len(args.prompt) > 2500:
        raise ValueError("prompt must contain 1–2500 characters")
    if not args.idempotency_key.strip() or len(args.idempotency_key) > 240:
        raise ValueError("idempotency key must contain 1–240 characters")
    if args.type == "image":
        if args.duration_seconds is not None or args.aspect_ratio is not None:
            raise ValueError("image uses 1024x1024; video options are not accepted")
        model = args.model or "gpt-image-2.5-flare"
        if model == "kling-3.0-standard":
            raise ValueError("Kling is a video model")
    else:
        model = args.model or "kling-3.0-standard"
        if model != "kling-3.0-standard":
            raise ValueError("video requires kling-3.0-standard")
        if args.duration_seconds is not None and not 3 <= args.duration_seconds <= 15:
            raise ValueError("Kling duration must be 3–15 seconds")
    return _without_none(
        {
            "type": args.type,
            "prompt": args.prompt,
            "model": model,
            "duration_seconds": args.duration_seconds,
            "aspect_ratio": args.aspect_ratio,
            "idempotency_key": args.idempotency_key,
        }
    )


def _status_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--workspace-id")
    parser.add_argument("--task-id", required=True)


def _status_payload(args: argparse.Namespace) -> dict[str, Any]:
    return {"task_id": str(UUID(args.task_id))}


async def _generate(ctx: CommandContext) -> Any:
    if not ctx.workspace_id:
        raise RuntimeError("missing_workspace")
    body = {key: value for key, value in ctx.arguments.items() if key != "idempotency_key"}
    body["workspace_id"] = ctx.workspace_id
    receipt = await ctx.api_data(
        ctx.cfg,
        "POST",
        "/media/generations",
        json_body=body,
        idempotency_key=ctx.arguments["idempotency_key"],
    )
    try:
        if not isinstance(receipt, dict) or receipt.get("workspace_id") != ctx.workspace_id:
            raise ValueError("workspace mismatch")
        UUID(str(receipt.get("task_id")))
        UUID(str(receipt.get("media_id")))
    except (ValueError, TypeError, AttributeError):
        raise RuntimeError(
            "media_generation_unverified: preserve this Idempotency-Key and retry "
            "only the identical request; do not submit with a new key"
        ) from None
    return receipt


async def _status(ctx: CommandContext) -> Any:
    if not ctx.workspace_id:
        raise RuntimeError("missing_workspace")
    return await ctx.api_data(
        ctx.cfg,
        "GET",
        f"/media/generations/{ctx.arguments['task_id']}",
        params={"workspace_id": ctx.workspace_id},
    )


def _generation_specs() -> list[CommandSpec]:
    return [
        CommandSpec(
            domain=Domain.MEDIA,
            shortcut="+generate",
            risk_level="write",
            summary="Submit prompt image (GPT Image 2.5) or text video (Kling 3); requires configured model credits. Receipt is not completion: read media +status then +get.",
            execution="direct",
            adapter_tool_name="media_generate",
            input_schema={
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": ["image", "video"]},
                    "prompt": {"type": "string", "minLength": 1, "maxLength": 2500},
                    "model": {
                        "type": "string",
                        "enum": [
                            "gpt-image-2.5-flare",
                            "gpt-image-2.5-sunburst",
                            "kling-3.0-standard",
                        ],
                    },
                    "duration_seconds": {"type": "integer", "minimum": 3, "maximum": 15},
                    "aspect_ratio": {"type": "string", "enum": ["9:16", "16:9", "1:1"]},
                    "idempotency_key": {"type": "string", "minLength": 1, "maxLength": 240},
                },
                "required": ["type", "prompt", "idempotency_key"],
                "additionalProperties": False,
            },
            output_schema=_direct_output_schema(
                "Durable task receipt; unknown is not safe to resubmit."
            ),
            examples=[
                "museoncli media +generate --type image --prompt 'A blue cup' --idempotency-key draft-01"
            ],
            add_arguments=_generate_args,
            build_arguments=_generate_payload,
            supports_dry_run=True,
        ),
        CommandSpec(
            domain=Domain.MEDIA,
            shortcut="+status",
            risk_level="read",
            summary="Read durable generation phase, effective model parameters, errors and media readiness.",
            execution="direct",
            adapter_tool_name="media_status",
            input_schema={
                "type": "object",
                "properties": {"task_id": _uuid_id_schema("Generation task UUID.")},
                "required": ["task_id"],
                "additionalProperties": False,
            },
            output_schema=_direct_output_schema("Generation ledger readback."),
            examples=["museoncli media +status --task-id <task_id>"],
            add_arguments=_status_args,
            build_arguments=_status_payload,
        ),
    ]


def specs() -> list[CommandSpec]:
    return _generation_specs() + [
        CommandSpec(
            domain=Domain.MEDIA,
            shortcut="+upload",
            summary="Upload local image/video/audio or a private general file. General files return artifact_id, with expiring download URL; read with --kind file. Read the returned media ID with media +get; upload success does not prove business generation or delivery completion.",
            risk_level="write",
            execution="direct",
            adapter_tool_name="media_upload",
            input_schema={
                "type": "object",
                "properties": {
                    "file": {"type": "string"},
                    "file_id": _uuid_id_schema(
                        "Stable private-file identity; returned as artifact_id."
                    ),
                    "media_type": {"type": "string", "enum": ["image", "video", "audio", "file"]},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                },
                "required": ["file", "media_type"],
                "additionalProperties": False,
            },
            output_schema=_direct_output_schema(
                "Media upload returns asset.media_id; private general-file upload returns kind=file and artifact_id, workspace_id, is_public=false, and an expiring download_url."
            ),
            examples=[
                "museoncli media +upload --file ./clip.mp4 --media-type video --title Reference"
            ],
            add_arguments=_upload_args,
            build_arguments=_upload_payload,
            supports_dry_run=True,
        ),
        CommandSpec(
            domain=Domain.MEDIA,
            shortcut="+import",
            summary="Import an image from a direct HTTP(S) URL. This API supports images only; upload local video/audio files with media +upload.",
            risk_level="write",
            execution="direct",
            adapter_tool_name="media_import",
            input_schema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "format": "uri"},
                    "source_page_url": {"type": "string", "format": "uri"},
                },
                "required": ["url"],
                "additionalProperties": False,
            },
            output_schema=_direct_output_schema(
                "Existing image import receipt; asset contains the returned media ID."
            ),
            examples=["museoncli media +import --url https://example.com/reference.jpg"],
            add_arguments=_import_args,
            build_arguments=_import_payload,
            supports_dry_run=True,
        ),
        CommandSpec(
            domain=Domain.MEDIA,
            shortcut="+get",
            summary="Read one media record in the selected workspace. Business output completion must be verified through its owning domain.",
            risk_level="read",
            execution="direct",
            adapter_tool_name="media_get",
            input_schema={
                "type": "object",
                "properties": {
                    "id": _uuid_id_schema("Media or explicitly selected file UUID."),
                    "kind": {"type": "string", "enum": ["media", "file"], "default": "media"},
                },
                "required": ["id"],
                "additionalProperties": False,
            },
            output_schema=_direct_output_schema("Existing media record returned by the API."),
            examples=["museoncli media +get --id <media_id>"],
            add_arguments=_get_args,
            build_arguments=_get_payload,
        ),
    ]


EXECUTORS = {
    "media.generate": direct_enveloped(_generate),
    "media.status": direct_enveloped(_status),
    "media.upload": direct_enveloped(_upload),
    "media.import": direct_enveloped(_import),
    "media.get": direct_enveloped(_get),
}
