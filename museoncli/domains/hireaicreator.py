"""HireAICreator resource commands: existing APIs and explicit inputs."""

from __future__ import annotations

import argparse
import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from museoncli.domains._model import CommandSpec, Domain
from museoncli.domains._shared import _direct_output_schema
from museoncli.envelopes import direct_api_envelope
from museoncli.execution import CommandContext

# Schemas describe the supported API subset. No server defaults are filled in:
# omitted, null, false and zero retain their distinct meanings.
S = {"type": "string", "minLength": 1}
U = {"type": "string", "format": "uuid"}
POSITIVE_INT = {"type": "integer", "minimum": 1}
B = {"type": "boolean"}
D = {"type": "string", "format": "date"}
DT = {"type": "string", "format": "date-time"}
TZ = {"type": "string", "format": "timezone"}


def obj(properties: dict[str, Any], required: tuple[str, ...] = ()) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(required),
        "additionalProperties": False,
    }


def arr(items: dict[str, Any], minimum: int = 0, maximum: int = 300) -> dict[str, Any]:
    return {"type": "array", "items": items, "minItems": minimum, "maxItems": maximum}


def nullable(schema: dict[str, Any]) -> dict[str, Any]:
    return {
        **schema,
        "type": [schema["type"], "null"],
        **({"enum": [*schema["enum"], None]} if "enum" in schema else {}),
    }


def enum(*values: str) -> dict[str, Any]:
    # CLI flags and structured input both use kebab-case; wire uses API enum values.
    return {"type": "string", "enum": list(values)}


PAGE = {"page": POSITIVE_INT, "page_size": {"type": "integer", "minimum": 1, "maximum": 100}}
SEARCH_PAGE = {**PAGE, "search": S}
ACTOR_GENDER = enum("female", "male", "androgynous")
ACTOR_AGE = enum("18-24", "25-34", "35-44", "45-54", "55-64", "65-plus")
ACTOR_GENERATION_ITEM = obj(
    {
        "persona_id": U,
        "presentation_gender": ACTOR_GENDER,
        "apparent_age_group": ACTOR_AGE,
        "name": nullable({"type": "string", "minLength": 1, "maxLength": 200}),
        "bio": nullable({"type": "string", "minLength": 1, "maxLength": 2000}),
        "prompt": nullable({"type": "string", "minLength": 1, "maxLength": 4000}),
        "actor_count": {"type": "integer", "minimum": 1, "maximum": 100},
    },
    ("persona_id", "presentation_gender", "apparent_age_group"),
)
DIRECTIONS = obj({"pov": nullable(S), "text_overlay": nullable(S), "caption": nullable(S)})
CLIP_RULE = obj(
    {
        "position": POSITIVE_INT,
        "tag_ids": arr(U, maximum=50),
        "selection_mode": enum("random", "manual"),
        "clip_id": nullable(U),
    },
    ("position",),
)
CREATIVE = obj(
    {
        "format_id": nullable(U),
        "reference_hook_id": nullable(U),
        "ai_hook_item_id": nullable(U),
        "hook_resolution": enum("original", "480p"),
        "demo_id": nullable(U),
        "clip_rules": nullable(arr(CLIP_RULE, 1, 50)),
        "pov_id": nullable(U),
        "pov_text": nullable(S),
        "composition_bgm_id": nullable(U),
    }
)
QUANTITY = obj(
    {
        "mode": enum("schedule", "fixed-count"),
        "start_date": nullable(D),
        "publishing_day_count": nullable(POSITIVE_INT),
        "posts_per_account_per_day": nullable(POSITIVE_INT),
        "content_count": nullable(POSITIVE_INT),
    },
    ("mode",),
)
SLOT = obj(
    {"publishing_account_id": S, "scheduled_at": DT}, ("publishing_account_id", "scheduled_at")
)
PLAN = {
    "campaign_id": nullable(U),
    "name": S,
    "quantity": QUANTITY,
    "publishing_account_ids": arr(S, 1),
    "creative_inputs": arr(CREATIVE, 1),
    "composition_source": enum("demo", "clips", "hook-only", "demo-only"),
    "category_selections": arr(obj({"key_id": U, "tag_ids": arr(U)}, ("key_id",))),
    "include_bgm": B,
    "schedule_timezone": nullable(TZ),
    "schedule_slots": nullable(arr(SLOT, 1)),
}
PLAN_REQUIRED = ("name", "quantity", "publishing_account_ids", "creative_inputs")
CLIP_ITEM = obj(
    {
        "client_key": S,
        "name": S,
        "source_video_media_id": U,
        "reusable": B,
        "usage_limit": {"type": "integer"},
        "description": {"type": "string"},
        "text_overlay_enabled": B,
        "text_overlay_input_mode": enum("direction", "draft-copy"),
        "duration_ms": nullable(POSITIVE_INT),
        "target_duration_ms": nullable({"type": "integer", "minimum": 100}),
        "width": nullable(POSITIVE_INT),
        "height": nullable(POSITIVE_INT),
        "tags": arr(obj({"key": S, "value": S}, ("key", "value")), 1, 50),
        "mapping_version": POSITIVE_INT,
        "relative_path": S,
    },
    (
        "client_key",
        "name",
        "source_video_media_id",
        "reusable",
        "usage_limit",
        "tags",
        "mapping_version",
        "relative_path",
    ),
)
ASSIGN_ITEM = obj(
    {"clip_id": U, "expected_version": POSITIVE_INT, "publishing_account_id": nullable(U)},
    ("clip_id", "expected_version"),
)
BULK_SLOT = obj(
    {
        "video_id": U,
        "expected_version": POSITIVE_INT,
        "publishing_account_id": S,
        "scheduled_at": DT,
        "schedule_timezone": TZ,
    },
    ("video_id", "expected_version", "publishing_account_id", "scheduled_at"),
)
FILTER = obj(
    {
        "time_zone": nullable(TZ),
        "publishing_account_ids": arr(S, maximum=5000),
        "device_kind": nullable(enum("cloud-phone", "real-device")),
        "scheduled_from": nullable(DT),
        "scheduled_to": nullable(DT),
        "video_ids": arr(U, maximum=5000),
    }
)
SHARE = {
    "collection_kind": enum("test-group", "warmup-plan", "video-filter"),
    "collection_id": nullable(U),
    "rotate": B,
    "video_filter": nullable(FILTER),
}
BATCH_STATUSES = (
    "queued",
    "running",
    "awaiting-review",
    "partially-completed",
    "completed",
    "failed",
    "cancelled",
)
ITEM_STATUSES = (
    "queued",
    "image-prompt-generating",
    "awaiting-image-prompt",
    "first-frame-generating",
    "awaiting-first-frame",
    "video-ready",
    "awaiting-video-submit",
    "video-generating",
    "completed",
    "failed",
    "cancelled",
)


def _validate(value: Any, schema: dict[str, Any], field: str = "input") -> None:
    kinds = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
    if value is None and "null" in kinds:
        return
    kind = next(k for k in kinds if k != "null")
    valid = {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "integer": type(value) is int,
        "boolean": type(value) is bool,
    }[kind]
    if not valid:
        raise ValueError(f"{field} must be {kind}")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{field} must be one of {schema['enum']}")
    if kind == "object":
        unknown = set(value) - set(schema["properties"])
        missing = set(schema["required"]) - set(value)
        if unknown or missing:
            raise ValueError(
                f"{field}: unknown fields {sorted(unknown)}; missing fields {sorted(missing)}"
            )
        for key, child in value.items():
            _validate(child, schema["properties"][key], f"{field}.{key}")
    elif kind == "array":
        if not schema.get("minItems", 0) <= len(value) <= schema.get("maxItems", len(value)):
            raise ValueError(f"{field} has an invalid item count")
        for child in value:
            _validate(child, schema["items"], f"{field}[]")
    elif kind == "integer" and not schema.get("minimum", value) <= value <= schema.get(
        "maximum", value
    ):
        raise ValueError(f"{field} is outside its allowed range")
    elif kind == "string":
        if len(value) < schema.get("minLength", 0) or len(value) > schema.get(
            "maxLength", len(value)
        ):
            raise ValueError(f"{field} has invalid length")
        fmt = schema.get("format")
        try:
            if fmt == "uuid":
                UUID(value)
            elif fmt == "date":
                date.fromisoformat(value)
            elif fmt == "date-time":
                if datetime.fromisoformat(value.replace("Z", "+00:00")).utcoffset() is None:
                    raise ValueError("timezone offset required")
            elif fmt == "timezone":
                ZoneInfo(value)
        except (ValueError, ZoneInfoNotFoundError) as exc:
            raise ValueError(f"{field}: invalid {fmt}") from exc


def _wire(value: Any, schema: dict[str, Any]) -> Any:
    if value is None:
        return None
    if isinstance(value, dict):
        return {key: _wire(child, schema["properties"][key]) for key, child in value.items()}
    if isinstance(value, list):
        return [_wire(child, schema["items"]) for child in value]
    return value.replace("-", "_") if "enum" in schema else value


def _load(
    args: argparse.Namespace, properties: dict[str, Any], required: tuple[str, ...]
) -> dict[str, Any]:
    if (
        getattr(args, "args_json", None) is not None
        and getattr(args, "args_file", None) is not None
    ):
        raise ValueError("Use exactly one of --args-json and --args-file")
    value = getattr(args, "args_json", None)
    if getattr(args, "args_file", None) is not None:
        value = Path(args.args_file).read_text(encoding="utf-8")
    payload = json.loads(value) if value is not None else {}
    if not isinstance(payload, dict):
        raise ValueError("HireAICreator structured input must be an object")
    for key in properties:
        if hasattr(args, key):
            if key in payload:
                raise ValueError(f"{key} is supplied both as JSON and a flag")
            payload[key] = getattr(args, key)
    _validate(payload, obj(properties, required))
    return payload


EXECUTORS: dict[str, Any] = {}


def _command(
    resource: str,
    action: str,
    method: str,
    path: str,
    properties: dict[str, Any],
    *,
    required: tuple[str, ...] = (),
    workspace: str = "query",
    version: int = 2,
    write: bool = False,
    idempotent: bool = False,
    summary: str,
    readback: str = "",
    path_key: str = "id",
    flags: dict[str, str] | None = None,
) -> CommandSpec:
    props = dict(properties)
    if "{" in path:
        props[path_key] = (
            {"type": "string", "minLength": 6, "maxLength": 100} if path_key == "token" else U
        )
        required = (path_key, *required)
    if workspace != "resource":
        props["workspace_id"] = U
    if idempotent:
        props["idempotency_key"] = {"type": "string", "minLength": 8, "maxLength": 200}
        required = (*required, "idempotency_key")
    schema = obj(props, required)
    name = f"hireaicreator.{resource}-{action}"
    aliases = flags or {}

    def add_arguments(parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--args-json")
        parser.add_argument("--args-file")
        for key, field in props.items():
            kind = field["type"]
            base = next((x for x in kind if x != "null"), None) if isinstance(kind, list) else kind
            if base == "object" or (base == "array" and field["items"]["type"] == "object"):
                continue
            option = aliases.get(key, "--" + key.replace("_", "-"))
            kwargs: dict[str, Any] = {"dest": key, "default": argparse.SUPPRESS}
            item = field["items"] if base == "array" else field
            if base == "boolean":
                kwargs["action"] = argparse.BooleanOptionalAction
            elif base == "array":
                kwargs["action"] = "append"
            elif base == "integer":
                kwargs["type"] = int
            if "enum" in item:
                kwargs["choices"] = [value for value in item["enum"] if value is not None]
            parser.add_argument(option, **kwargs)
        if write:
            parser.add_argument("--dry-run", action="store_true")

    def build(args: argparse.Namespace) -> dict[str, Any]:
        payload = _load(args, props, required)
        if path_key == "token" and not re.fullmatch(r"[A-Za-z0-9-]{6,100}", payload["token"]):
            raise ValueError("token must contain only letters, numbers and hyphens")
        if idempotent and any(c in payload["idempotency_key"] for c in "\r\n"):
            raise ValueError("idempotency key must not contain newlines")
        if resource == "account" and action == "list":
            if ("test_group_id" in payload) != ("test_group_assignment_state" in payload):
                raise ValueError(
                    "test_group_id and test_group_assignment_state must be supplied together"
                )
        return payload

    async def execute(ctx: CommandContext) -> dict[str, Any]:
        arguments = dict(ctx.arguments)
        actual_path = path.format(**arguments)
        if "{" in path:
            arguments.pop(path_key)
        key = arguments.pop("idempotency_key", None)
        scope = None
        if workspace != "resource":
            scope = arguments.pop("workspace_id", None) or ctx.workspace_id
            if not scope:
                raise RuntimeError("missing_workspace")
            arguments["workspace_id"] = scope
        wire = _wire(arguments, schema)
        call = ctx.api_data_v2 if version == 2 else ctx.api_data
        kwargs: dict[str, Any] = {"unwrap_success": True}
        if method == "GET":
            kwargs["params"] = wire
        else:
            kwargs["json_body"] = wire
        if key is not None:
            kwargs["idempotency_key"] = key
        raw = await call(ctx.cfg, method, actual_path, **kwargs)
        result = direct_api_envelope(name, scope, raw, site_url=ctx.cfg.site_url)
        if write:
            result["warnings"].append(
                "Receipt only; verify persisted state before dependent writes."
            )
            result["next_steps"].append(readback)
        return result

    EXECUTORS[name] = execute
    return CommandSpec(
        domain=Domain.HIRE_AI_CREATOR,
        resource=resource,
        shortcut="+" + action,
        summary=summary,
        risk_level="write" if write else "read",
        execution="direct",
        adapter_tool_name="ai_hook_" + resource.replace("-", "_") + "_" + action.replace("-", "_"),
        input_schema=schema,
        output_schema=_direct_output_schema("Unmodified API resource or receipt. " + readback),
        examples=[f"museoncli schema {name}"],
        add_arguments=add_arguments,
        build_arguments=build,
        supports_dry_run=write,
    )


def specs() -> list[CommandSpec]:
    return [
        _command(
            "account",
            "list",
            "GET",
            "/pool-accounts/workspace-accounts",
            {
                **SEARCH_PAGE,
                "search_terms": arr(S, maximum=100),
                "search_match": enum("exact", "fuzzy"),
                "operation_stage": arr(enum("warmup", "promotable", "unavailable", "unset")),
                "device_kind": arr(enum("cloud-phone", "real-device")),
                "platform": arr(S),
                "is_active": B,
                "has_actor": B,
                "has_persona": B,
                "actor_id": U,
                "persona_id": U,
                "test_group_id": U,
                "test_group_assignment_state": enum("assignable", "assigned"),
            },
            flags={"search_terms": "--search-term"},
            summary="Find exact account identities and current stage/assignment state; complete pagination before fixing a selection.",
        ),
        _command(
            "account",
            "assets-get",
            "GET",
            "/pool-accounts/{id}/publish-assets",
            {},
            summary="Read an account's Actor, Persona and other publish asset bindings.",
        ),
        _command(
            "account",
            "actor-set",
            "PUT",
            "/pool-accounts/{id}/publish-assets/actor",
            {"actor_id": U},
            required=("actor_id",),
            workspace="body",
            write=True,
            summary="Bind an existing Actor to an account; use its exact ID to resolve duplicate names.",
            readback="Read hireaicreator account +assets-get for the same account and workspace.",
        ),
        _command(
            "account",
            "persona-set",
            "PUT",
            "/pool-accounts/{id}/publish-assets/persona",
            {
                "persona_id": U,
                "managed_operation_approved": B,
                "approval_note": nullable({"type": "string", "maxLength": 500}),
            },
            required=("persona_id",),
            workspace="body",
            write=True,
            summary="Bind an existing Persona to an account. Managed-operation approval must be explicit.",
            readback="Read hireaicreator account +assets-get for the same account and workspace.",
        ),
        _command(
            "account",
            "eligibility",
            "POST",
            "/ai-hook-test-groups/account-eligibility",
            {
                "publishing_account_ids": arr(S, 1),
                "test_group_id": nullable(U),
            },
            workspace="body",
            required=("publishing_account_ids",),
            summary="Read eligibility and blockers for an explicit account set.",
        ),
        _command(
            "actor",
            "list",
            "GET",
            "/actors",
            {**SEARCH_PAGE, "source_persona_id": U},
            summary="List Actors (independent identities), optionally by source Persona.",
        ),
        _command(
            "actor",
            "get",
            "GET",
            "/actors/{id}",
            {},
            summary="Read one Actor; its ID is not a Persona ID.",
        ),
        _command(
            "actor",
            "from-persona",
            "POST",
            "/actors/from-persona",
            {
                "persona_id": U,
                "name": nullable({"type": "string", "minLength": 1, "maxLength": 200}),
                "bio": nullable({"type": "string", "minLength": 1, "maxLength": 2000}),
                "presentation_gender": ACTOR_GENDER,
                "apparent_age_group": ACTOR_AGE,
                "image_media_ids": arr(U, 1, 1),
            },
            required=(
                "persona_id",
                "presentation_gender",
                "apparent_age_group",
                "image_media_ids",
            ),
            workspace="body",
            write=True,
            summary="Create one Actor from an existing Persona and one workspace image.",
            readback="Read the returned Actor ID with actor +get. On an unknown outcome, reconcile before retrying because this endpoint has no idempotency key.",
        ),
        _command(
            "actor",
            "batch-create",
            "POST",
            "/actors/generation-batches",
            {"items": arr(ACTOR_GENERATION_ITEM, 1, 100)},
            required=("items",),
            workspace="body",
            write=True,
            idempotent=True,
            summary="Start Persona-based Actor generation. Generated images remain candidates until selected.",
            readback="Use actor +batch-get and actor +batch-items until candidates settle; select approved item IDs with actor +batch-select.",
        ),
        _command(
            "actor",
            "batch-get",
            "GET",
            "/actors/generation-batches/{batch_id}",
            {},
            workspace="resource",
            path_key="batch_id",
            summary="Read the status and counts of one Actor generation batch.",
        ),
        _command(
            "actor",
            "batch-items",
            "GET",
            "/actors/generation-batches/{batch_id}/items",
            {**PAGE, "status": enum("queued", "processing", "succeeded", "failed")},
            workspace="resource",
            path_key="batch_id",
            summary="Page through generated Actor candidates and their image/status details.",
        ),
        _command(
            "actor",
            "batch-select",
            "POST",
            "/actors/generation-batches/{batch_id}/select",
            {"item_ids": arr(U, 1, 100)},
            required=("item_ids",),
            workspace="resource",
            path_key="batch_id",
            write=True,
            summary="Turn explicitly chosen successful candidates into Actors.",
            readback="Read every returned Actor ID with actor +get. Reconcile an unknown outcome before retrying selection.",
        ),
        _command(
            "persona",
            "list",
            "GET",
            "/personas",
            {**SEARCH_PAGE, "tag": S},
            version=1,
            summary="List Personas and their actual identities.",
        ),
        _command(
            "persona",
            "get",
            "GET",
            "/personas/{id}",
            {},
            version=1,
            workspace="resource",
            summary="Read a Persona through resource access control; no workspace override.",
        ),
        _command(
            "format",
            "list",
            "GET",
            "/ai-hook-formats",
            {
                **SEARCH_PAGE,
                "status": enum("pending", "ingesting", "extracting", "ready", "failed"),
                "tag": S,
            },
            summary="List HireAICreator Formats, distinct from slideshow Formats.",
        ),
        _command(
            "format",
            "get",
            "GET",
            "/ai-hook-formats/{id}",
            {},
            summary="Read Format processing state and source resources.",
        ),
        _command(
            "format",
            "import-urls",
            "POST",
            "/ai-hook-formats/from-urls",
            {
                "urls": arr(S, 1, 50),
                "tags": arr(S, maximum=20),
                "extract_bgm": B,
            },
            required=("urls",),
            workspace="body",
            write=True,
            summary="Import Format source URLs asynchronously; acceptance is not ready content.",
            readback="Read each returned items[].id with hireaicreator format +get; require ready or report failed/pending.",
        ),
        _command(
            "hook",
            "list",
            "GET",
            "/ai-hooks",
            {
                **SEARCH_PAGE,
                "status": enum("pending", "preprocessing", "analyzing", "ready", "failed"),
                "source": enum("official", "custom"),
                "tag": S,
            },
            version=1,
            summary="List reference Hooks; distinguish Hook IDs from generated item IDs.",
        ),
        _command(
            "recipe",
            "list",
            "GET",
            "/ai-hook-recipes",
            {**SEARCH_PAGE, "category_tag_id": U},
            summary="List reusable Clip recipes.",
        ),
        _command(
            "recipe",
            "get",
            "GET",
            "/ai-hook-recipes/{id}",
            {},
            summary="Read one Recipe and its steps.",
        ),
        _command(
            "pov",
            "list",
            "GET",
            "/ai-hook-povs",
            {**SEARCH_PAGE, "tag": S},
            summary="List reusable POV text.",
        ),
        _command(
            "bgm",
            "list",
            "GET",
            "/bgm-assets",
            {**SEARCH_PAGE, "tag": S, "mood": S, "publishable_only": B},
            summary="List BGM media and publishability facts.",
        ),
        _command(
            "item",
            "list",
            "GET",
            "/ai-hook-items",
            {
                **PAGE,
                "status": enum(*ITEM_STATUSES),
                "hook_id": U,
                "actor_id": U,
                "persona_id": U,
            },
            version=1,
            summary="List generated Hook items with result media URLs and status; filter by reference Hook ID and paginate the matching results.",
        ),
        _command(
            "item",
            "get",
            "GET",
            "/ai-hook-items/{id}",
            {},
            version=1,
            workspace="resource",
            summary="Read one generated Hook item; resolve result_video_media_id with media +get --id.",
        ),
        _command(
            "batch",
            "list",
            "GET",
            "/ai-hook-batches",
            {**PAGE, "status": enum(*BATCH_STATUSES)},
            version=1,
            summary="List generation batches by status and counters; batches have IDs, not names.",
        ),
        _command(
            "batch",
            "get",
            "GET",
            "/ai-hook-batches/{id}",
            {},
            version=1,
            workspace="resource",
            summary="Read one generation batch status and counters by ID.",
        ),
        _command(
            "batch",
            "items",
            "GET",
            "/ai-hook-batches/{id}/items",
            {
                **PAGE,
                "status": enum(*ITEM_STATUSES),
                "hook_id": U,
                "actor_id": U,
                "persona_id": U,
            },
            version=1,
            workspace="resource",
            summary="List one batch's generated items; resolve each result_video_media_id with media +get --id.",
        ),
        _command(
            "clip",
            "list",
            "GET",
            "/content-clips",
            {
                **SEARCH_PAGE,
                "folder_id": U,
                "publishing_account_id": U,
                "reusable": B,
                "clip_status": enum(
                    "all", "available", "reserved", "used", "needs-account", "unused"
                ),
            },
            summary="Read Clip inventory and assignment state.",
        ),
        _command(
            "clip",
            "get",
            "GET",
            "/content-clips/{id}",
            {},
            workspace="resource",
            summary="Read one Clip including version, media and publishing account.",
        ),
        _command(
            "clip",
            "batch-create",
            "POST",
            "/content-clips/batch",
            {"items": arr(CLIP_ITEM, 1, 50)},
            required=("items",),
            workspace="body",
            write=True,
            summary="Register Clips with client_key/mapping_version identity; initial needs_account is not usable assigned stock.",
            readback="Read each Clip ID with hireaicreator clip +get, then assign-account and read again before claiming available inventory.",
        ),
        _command(
            "clip",
            "assign-account",
            "POST",
            "/content-clips/batch-assign-account",
            {"publishing_account_id": nullable(U), "items": arr(ASSIGN_ITEM, 1, 100)},
            required=("items",),
            workspace="resource",
            write=True,
            summary="Assign Clips with explicit expected versions and account IDs.",
            readback="hireaicreator clip +get each ID; verify publishing_account_id and the returned version; preserve conflicts.",
        ),
        _command(
            "video",
            "list",
            "GET",
            "/ai-hook-videos",
            {
                **PAGE,
                "plan_id": U,
                "status": enum(
                    "pending",
                    "planned",
                    "generating",
                    "pending-review",
                    "approved",
                    "scheduled",
                    "publishing",
                    "published",
                    "cancelled",
                    "missed",
                ),
                "include_preview": B,
                "publishing_account_id": S,
                "publishing_account_ids": arr(S),
                "device_kind": enum("cloud-phone", "real-device"),
                "persona_id": U,
                "reference_hook_id": U,
                "test_group_id": U,
                "scheduled_from": DT,
                "scheduled_to": DT,
            },
            summary="List videos and their version/state; paginate explicitly.",
        ),
        _command(
            "video",
            "get",
            "GET",
            "/ai-hook-videos/{id}",
            {"include_preview": B, "include_resource_snapshot": B},
            workspace="resource",
            summary="Read persisted video configuration, version, component/render/publish facts.",
        ),
        _command(
            "video",
            "readiness",
            "GET",
            "/ai-hook-videos/{id}/readiness",
            {},
            workspace="resource",
            summary="Read blockers and stage eligibility; readiness does not prove generation completion.",
        ),
        _command(
            "video",
            "update",
            "PATCH",
            "/ai-hook-videos/{id}",
            {
                "expected_version": POSITIVE_INT,
                "composition_bgm_id": nullable(U),
                "reference_hook_id": nullable(U),
                "ai_hook_item_id": nullable(U),
                "hook_resolution": nullable(enum("original", "480p")),
                "demo_id": nullable(U),
                "publishing_account_id": nullable(S),
                "scheduled_at": nullable(DT),
                "schedule_timezone": nullable(TZ),
                "pov_text": nullable(S),
                "caption": nullable(S),
            },
            required=("expected_version",),
            workspace="resource",
            write=True,
            summary="Patch only supplied video fields using the observed expected_version; do not auto-retry conflicts.",
            readback="hireaicreator video +get the same ID; compare desired fields/version. Export and verify video_version/render_revision for a new finished output.",
        ),
        _command(
            "video",
            "generate",
            "POST",
            "/ai-hook-videos/{id}/generate",
            {"expected_version": POSITIVE_INT, "generation_directions": DIRECTIONS},
            required=("expected_version",),
            workspace="resource",
            write=True,
            idempotent=True,
            summary="Request video generation with a stable idempotency key; response is acceptance only.",
            readback="hireaicreator video +get the ID; inspect component errors and statuses. Use delivery export for finished output facts.",
        ),
        _command(
            "video",
            "bulk-schedule",
            "POST",
            "/ai-hook-videos/bulk-schedule",
            {"items": arr(BULK_SLOT, 1)},
            required=("items",),
            workspace="resource",
            write=True,
            summary="Schedule explicit video/version/account/time tuples; retain succeeded/conflicted/failures.",
            readback="hireaicreator video +get each succeeded ID and compare account/scheduled_at; never treat top-level success as whole-batch completion.",
        ),
        _command(
            "plan",
            "preview",
            "POST",
            "/ai-hook-video-plans/preview",
            PLAN,
            required=PLAN_REQUIRED,
            workspace="body",
            summary="Read server allocation and blockers for a proposed plan; does not create the plan.",
        ),
        _command(
            "plan",
            "capacity",
            "POST",
            "/ai-hook-video-plans/capacity",
            {
                "publishing_account_ids": arr(S, 1),
                "date_from": D,
                "date_to": D,
                "timezone": TZ,
                "exclude_video_id": nullable(U),
            },
            required=("publishing_account_ids", "date_from", "date_to", "timezone"),
            workspace="body",
            summary="Read account capacity for a bounded date range.",
        ),
        _command(
            "plan",
            "create",
            "POST",
            "/ai-hook-video-plans",
            {
                **PLAN,
                "confirm_demo_reuse": B,
                "start_generation": B,
                "generation_directions": DIRECTIONS,
            },
            required=PLAN_REQUIRED,
            workspace="body",
            write=True,
            idempotent=True,
            summary="Create a plan with a stable idempotency key. Server defaults start_generation to false; creation is not a finished video.",
            readback="hireaicreator plan +get returned ID, then hireaicreator video +list --plan-id; verify generation separately.",
        ),
        _command(
            "plan",
            "get",
            "GET",
            "/ai-hook-video-plans/{id}",
            {},
            workspace="resource",
            summary="Read a persistent video plan and its state.",
        ),
        _command(
            "test-group",
            "list",
            "GET",
            "/ai-hook-test-groups",
            {**SEARCH_PAGE, "plan_id": U},
            summary="List workspace Test Groups without creating a plan; optional plan_id narrows to a known plan.",
        ),
        _command(
            "test-group",
            "get",
            "GET",
            "/ai-hook-test-groups/{id}",
            {},
            summary="Read current group members and schedule state; does not migrate accounts.",
        ),
        _command(
            "test-group",
            "preview",
            "POST",
            "/ai-hook-test-groups/preview",
            {"test_group_id": U, "campaign_id": nullable(U)},
            required=("test_group_id",),
            workspace="body",
            summary="Preview the persisted test group schedule and inventory gaps, without confirming a rollout.",
        ),
        _command(
            "warmup",
            "list",
            "GET",
            "/pool-account-warmup/strategies",
            {**SEARCH_PAGE, "status": enum("draft", "active", "paused")},
            summary="Read warmup strategies; does not change account stage.",
        ),
        _command(
            "warmup",
            "journeys",
            "GET",
            "/pool-account-warmup/journeys",
            {
                **PAGE,
                "strategy_id": U,
                "status": enum("warming", "onboarded", "terminated"),
                "current_only": B,
            },
            summary="Read warmup journey state and current participation.",
        ),
        _command(
            "dashboard",
            "get",
            "GET",
            "/ai-hook-dashboard",
            {
                "campaign_id": U,
                "date_from": D,
                "date_to": D,
                "timezone": TZ,
                "account_id": S,
                "test_group_id": U,
                "warmup_strategy_id": U,
                "section": enum(
                    "all",
                    "identity",
                    "analytics",
                    "analytics-overview",
                    "analytics-trends",
                    "analytics-tiers",
                    "analytics-rankings",
                    "accounts",
                    "posts",
                    "hooks",
                ),
                "account_page": POSITIVE_INT,
                "account_page_size": POSITIVE_INT,
                "post_page": POSITIVE_INT,
                "post_page_size": POSITIVE_INT,
                "hook_page": POSITIVE_INT,
                "hook_page_size": POSITIVE_INT,
            },
            required=("campaign_id", "date_from", "date_to"),
            summary="Read campaign performance with explicit dates; preserve freshness and missing-data distinctions.",
        ),
        _command(
            "delivery",
            "preview",
            "POST",
            "/ai-hook-public-video-collections/preview",
            {
                "collection_kind": enum("video-filter"),
                "video_filter": obj(
                    {
                        key: (DT if key in {"scheduled_from", "scheduled_to"} else value)
                        for key, value in FILTER["properties"].items()
                        if key != "video_ids"
                    },
                    ("scheduled_from", "scheduled_to"),
                ),
            },
            required=("collection_kind", "video_filter"),
            workspace="body",
            summary="Read share selection counts only; counts are not an exact video-ID manifest.",
        ),
        _command(
            "delivery",
            "share",
            "POST",
            "/ai-hook-public-video-collections/share",
            SHARE,
            required=("collection_kind",),
            workspace="body",
            write=True,
            summary="Create or rotate public collection access, possibly prewarming exports. No generic idempotency: do not blindly retry unknown outcomes.",
            readback="hireaicreator delivery +get --token returned public_token; enumerate total/items and compare explicit video IDs for snapshots. Dynamic filters may change.",
        ),
        _command(
            "delivery",
            "get",
            "GET",
            "/public/ai-hook-test-groups/{token}",
            PAGE,
            workspace="resource",
            path_key="token",
            summary="Read a public collection by its opaque token. Paginate with total/items; no has_more is promised.",
        ),
        _command(
            "delivery",
            "export",
            "POST",
            "/ai-hook-videos/{id}/exports",
            {"expected_version": POSITIVE_INT, "hook_resolution": enum("original", "480p")},
            required=("expected_version",),
            workspace="resource",
            write=True,
            idempotent=True,
            summary="Request an export bound to video version; preserve the idempotency key on retry.",
            readback="hireaicreator delivery +export-get returned export ID; require completed, matching video_id/video_version/render_revision and usable download_url.",
        ),
        _command(
            "delivery",
            "export-get",
            "GET",
            "/ai-hook-video-exports/{id}",
            {},
            workspace="resource",
            summary="Read actual export status, version/revision, error and download URL.",
        ),
    ]
