"""Canonical account-publish commands for durable batch schedule planning."""

from __future__ import annotations

import argparse
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from museoncli.domains._model import CommandSpec, Domain
from museoncli.domains._shared import (
    _async_output_schema,
    _direct_output_schema,
    _json_list,
    _uuid_id_schema,
    dekebab,
)
from museoncli.execution import CommandContext, compact_params, direct_enveloped


ACCOUNT_PUBLISH_MAX_ACCOUNTS = 200
ACCOUNT_PUBLISH_MAX_DAILY_SLOTS = 24
ACCOUNT_PUBLISH_MAX_DAYS = 180
ACCOUNT_PUBLISH_MAX_OCCURRENCES = 5_000
SCHEDULE_PLAN_OPERATION_CHOICES = ["plan", "cancel-only"]
FORMAT_STRATEGY_CHOICES = ["random", "rotate"]
TOPIC_STRATEGY_CHOICES = ["random", "rotate"]
PRODUCT_POLICY_CHOICES = ["required", "optional"]
BGM_POLICY_CHOICES = ["required", "optional", "disabled"]
BGM_STRATEGY_CHOICES = ["rotate", "random"]
CONFLICT_POLICY_CHOICES = [
    "create-only",
    "replace-non-published",
    "upsert-occurrences",
]
ASSET_POOL_SCALAR_OPERATION_CHOICES = ["set", "clear", "unchanged"]
ASSET_POOL_COLLECTION_OPERATION_CHOICES = [
    "replace",
    "add",
    "remove",
    "clear",
    "unchanged",
]
ASSET_POOL_SCALAR_FIELDS = ("persona", "product")
ASSET_POOL_COLLECTION_FIELDS = ("formats", "topics", "bgm")


def _add_asset_pool_account_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--workspace-id")
    parser.add_argument(
        "--account-id",
        dest="account_ids",
        action="append",
        required=True,
        help=f"Pool account UUID; repeat for each account (max {ACCOUNT_PUBLISH_MAX_ACCOUNTS}).",
    )


def _add_asset_pools_batch_get_arguments(parser: argparse.ArgumentParser) -> None:
    _add_asset_pool_account_arguments(parser)
    parser.add_argument(
        "--no-resource-details",
        action="store_false",
        dest="include_resource_details",
        help=(
            "Return ids and structural counts only. By default product/format/topic/BGM "
            "details are included so the batch can be audited without per-resource calls."
        ),
    )
    parser.set_defaults(include_resource_details=True)


def _add_asset_pool_patch_arguments(parser: argparse.ArgumentParser) -> None:
    for field in ASSET_POOL_SCALAR_FIELDS:
        parser.add_argument(
            f"--{field}-operation",
            choices=ASSET_POOL_SCALAR_OPERATION_CHOICES,
        )
        parser.add_argument(f"--{field}-id")
    for field, id_flag, id_dest in (
        ("formats", "--format-id", "format_ids"),
        ("topics", "--topic-id", "topic_ids"),
        ("bgm", "--bgm-asset-id", "bgm_ids"),
    ):
        parser.add_argument(
            f"--{field}-operation",
            choices=ASSET_POOL_COLLECTION_OPERATION_CHOICES,
        )
        parser.add_argument(id_flag, action="append", dest=id_dest)
    account_patches = parser.add_mutually_exclusive_group()
    account_patches.add_argument(
        "--account-patches-json",
        help=(
            "JSON array of per-account overrides: [{account_id, patch}]. Explicit fields "
            "override the uniform patch; omitted fields inherit it."
        ),
    )
    account_patches.add_argument(
        "--account-patches-file",
        help="Path to a JSON array accepted by --account-patches-json.",
    )


def _add_asset_pools_batch_preview_arguments(parser: argparse.ArgumentParser) -> None:
    _add_asset_pool_account_arguments(parser)
    _add_asset_pool_patch_arguments(parser)


def _add_asset_pools_batch_set_arguments(parser: argparse.ArgumentParser) -> None:
    _add_asset_pools_batch_preview_arguments(parser)
    parser.add_argument(
        "--preview-token",
        required=True,
        help="Opaque token returned by the matching live batch preview.",
    )
    parser.add_argument(
        "--idempotency-key",
        required=True,
        help="Stable key for safe retries; use a new key only for an intentional new job.",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--yes", action="store_true")


def _add_asset_pools_job_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--workspace-id")
    parser.add_argument("--id", dest="job_id", required=True)


def _add_asset_pools_batch_cancel_arguments(parser: argparse.ArgumentParser) -> None:
    _add_asset_pools_job_arguments(parser)
    parser.add_argument("--reason")
    parser.add_argument("--dry-run", action="store_true")


def _build_asset_pool_account_ids(args: argparse.Namespace) -> list[str]:
    account_ids = _ordered_unique(args.account_ids)
    if len(account_ids) > ACCOUNT_PUBLISH_MAX_ACCOUNTS:
        raise ValueError(
            "account-publish asset-pool batching accepts at most "
            f"{ACCOUNT_PUBLISH_MAX_ACCOUNTS} --account-id values."
        )
    return account_ids


def _build_asset_pools_batch_get_arguments(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "account_ids": _build_asset_pool_account_ids(args),
        "include_resource_details": bool(args.include_resource_details),
    }


def _asset_pool_uniform_patch_from_args(args: argparse.Namespace) -> dict[str, Any]:
    patch: dict[str, Any] = {}
    for field in ASSET_POOL_SCALAR_FIELDS:
        operation = getattr(args, f"{field}_operation")
        value_id = getattr(args, f"{field}_id")
        if operation is None and value_id is not None:
            operation = "set"
        if operation is not None:
            candidate = {"operation": operation}
            if value_id is not None:
                candidate["value_id"] = value_id
            patch[field] = candidate
    for field, id_dest in (
        ("formats", "format_ids"),
        ("topics", "topic_ids"),
        ("bgm", "bgm_ids"),
    ):
        operation = getattr(args, f"{field}_operation")
        values = getattr(args, id_dest)
        if operation is None and values is not None:
            operation = "replace"
        if operation is not None:
            candidate = {"operation": operation}
            if values is not None:
                candidate["ids"] = _ordered_unique(values)
            patch[field] = candidate
    return _normalize_asset_pool_patch(patch, context="uniform_patch")


def _load_asset_pool_account_patches(args: argparse.Namespace) -> list[dict[str, Any]]:
    raw: str | None = None
    flag = "--account-patches-json"
    if args.account_patches_file:
        flag = "--account-patches-file"
        raw = Path(args.account_patches_file).read_text(encoding="utf-8")
    elif args.account_patches_json:
        raw = args.account_patches_json
    if raw is None:
        return []
    parsed = _json_list(raw, flag=flag)
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(parsed):
        if not isinstance(item, dict):
            raise ValueError(f"{flag}[{index}] must be an object.")
        account_id = str(item.get("account_id") or "").strip()
        if not account_id:
            raise ValueError(f"{flag}[{index}].account_id is required.")
        if account_id in seen:
            raise ValueError(f"{flag} contains duplicate account_id {account_id}.")
        raw_patch = item.get("patch")
        if not isinstance(raw_patch, dict):
            raise ValueError(f"{flag}[{index}].patch must be an object.")
        patch = _normalize_asset_pool_patch(
            raw_patch,
            context=f"account_patches[{index}].patch",
        )
        if not patch:
            raise ValueError(f"{flag}[{index}].patch must not be empty.")
        output.append({"account_id": account_id, "patch": patch})
        seen.add(account_id)
    if len(output) > ACCOUNT_PUBLISH_MAX_ACCOUNTS:
        raise ValueError(f"{flag} accepts at most {ACCOUNT_PUBLISH_MAX_ACCOUNTS} account patches.")
    return output


def _normalize_asset_pool_patch(raw: dict[str, Any], *, context: str) -> dict[str, Any]:
    unknown = set(raw) - set(ASSET_POOL_SCALAR_FIELDS) - set(ASSET_POOL_COLLECTION_FIELDS)
    if unknown:
        raise ValueError(f"{context} has unsupported fields: {', '.join(sorted(unknown))}.")
    patch: dict[str, Any] = {}
    for field in ASSET_POOL_SCALAR_FIELDS:
        if field not in raw:
            continue
        candidate = raw[field]
        if not isinstance(candidate, dict):
            raise ValueError(f"{context}.{field} must be an object.")
        operation = str(candidate.get("operation") or "").strip().lower()
        if operation not in ASSET_POOL_SCALAR_OPERATION_CHOICES:
            raise ValueError(f"{context}.{field}.operation must be set, clear, or unchanged.")
        value_id = str(candidate.get("value_id") or "").strip()
        if operation == "set" and not value_id:
            raise ValueError(f"{context}.{field}.value_id is required for set.")
        if operation != "set" and value_id:
            raise ValueError(f"{context}.{field}.value_id is only allowed with operation set.")
        normalized = {"operation": operation}
        if value_id:
            normalized["value_id"] = value_id
        patch[field] = normalized
    for field in ASSET_POOL_COLLECTION_FIELDS:
        if field not in raw:
            continue
        candidate = raw[field]
        if not isinstance(candidate, dict):
            raise ValueError(f"{context}.{field} must be an object.")
        operation = str(candidate.get("operation") or "").strip().lower()
        if operation not in ASSET_POOL_COLLECTION_OPERATION_CHOICES:
            raise ValueError(
                f"{context}.{field}.operation must be replace, add, remove, clear, or unchanged."
            )
        raw_ids = candidate.get("ids")
        if raw_ids is not None and not isinstance(raw_ids, list):
            raise ValueError(f"{context}.{field}.ids must be an array.")
        ids = _ordered_unique(raw_ids or [])
        if operation in {"replace", "add", "remove"} and not ids:
            raise ValueError(f"{context}.{field}.ids is required for operation {operation}.")
        if operation in {"clear", "unchanged"} and ids:
            raise ValueError(f"{context}.{field}.ids is not allowed with operation {operation}.")
        normalized = {"operation": operation}
        if ids:
            normalized["ids"] = ids
        patch[field] = normalized
    return patch


def _build_asset_pools_mutation_arguments(args: argparse.Namespace) -> dict[str, Any]:
    account_ids = _build_asset_pool_account_ids(args)
    uniform_patch = _asset_pool_uniform_patch_from_args(args)
    account_patches = _load_asset_pool_account_patches(args)
    target_ids = set(account_ids)
    outside_targets = [
        item["account_id"] for item in account_patches if item["account_id"] not in target_ids
    ]
    if outside_targets:
        raise ValueError(
            "Every account_patches account_id must also be supplied with --account-id: "
            + ", ".join(outside_targets)
        )
    if not uniform_patch and not account_patches:
        raise ValueError(
            "asset-pool batch mutation requires a uniform patch or --account-patches-json/file."
        )
    payload: dict[str, Any] = {"account_ids": account_ids}
    if uniform_patch:
        payload["uniform_patch"] = uniform_patch
    if account_patches:
        payload["account_patches"] = account_patches
    return payload


def _build_asset_pools_batch_preview_arguments(args: argparse.Namespace) -> dict[str, Any]:
    return _build_asset_pools_mutation_arguments(args)


def _build_asset_pools_batch_set_arguments(args: argparse.Namespace) -> dict[str, Any]:
    payload = _build_asset_pools_mutation_arguments(args)
    preview_token = str(args.preview_token or "").strip()
    idempotency_key = str(args.idempotency_key or "").strip()
    if not preview_token:
        raise ValueError("--preview-token must not be blank.")
    if len(preview_token) > 200:
        raise ValueError("--preview-token must be at most 200 characters.")
    if not idempotency_key:
        raise ValueError("--idempotency-key must not be blank.")
    if len(idempotency_key) > 240:
        raise ValueError("--idempotency-key must be at most 240 characters.")
    payload.update(
        {
            "preview_token": preview_token,
            "idempotency_key": idempotency_key,
        }
    )
    return payload


def _build_asset_pools_job_arguments(args: argparse.Namespace) -> dict[str, Any]:
    return {"job_id": args.job_id}


def _build_asset_pools_batch_cancel_arguments(args: argparse.Namespace) -> dict[str, Any]:
    return compact_params({"job_id": args.job_id, "reason": args.reason})


def _add_schedule_plan_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--workspace-id")
    parser.add_argument(
        "--operation",
        choices=SCHEDULE_PLAN_OPERATION_CHOICES,
        default="plan",
        help="plan creates/rebuilds schedule items; cancel-only cancels current eligible items.",
    )
    parser.add_argument(
        "--account-id",
        dest="account_ids",
        action="append",
        required=True,
        help=f"Pool account UUID; repeat for each account (max {ACCOUNT_PUBLISH_MAX_ACCOUNTS}).",
    )
    parser.add_argument("--start-date")
    parser.add_argument("--days", type=int)
    parser.add_argument(
        "--daily-slot",
        dest="daily_slots",
        action="append",
        help="Local HH:MM posting time; repeat for each daily occurrence.",
    )
    parser.add_argument("--timezone", help="IANA timezone, e.g. Asia/Shanghai.")
    parser.add_argument("--format-strategy", choices=FORMAT_STRATEGY_CHOICES)
    parser.add_argument("--topic-strategy", choices=TOPIC_STRATEGY_CHOICES)
    parser.add_argument("--product-policy", choices=PRODUCT_POLICY_CHOICES)
    parser.add_argument("--bgm-policy", choices=BGM_POLICY_CHOICES)
    parser.add_argument("--bgm-strategy", choices=BGM_STRATEGY_CHOICES)
    parser.add_argument("--bgm-platform")
    parser.add_argument("--conflict-policy", choices=CONFLICT_POLICY_CHOICES)
    parser.add_argument(
        "--cancel-reason",
        help="Optional operator reason for cancel-only; forbidden for plan.",
    )


def _add_schedule_plan_preview_arguments(parser: argparse.ArgumentParser) -> None:
    _add_schedule_plan_arguments(parser)


def _add_schedule_plan_batch_arguments(parser: argparse.ArgumentParser) -> None:
    _add_schedule_plan_arguments(parser)
    parser.add_argument(
        "--preview-token",
        help="Opaque token returned by the live preview; required for replace-non-published.",
    )
    parser.add_argument(
        "--idempotency-key",
        required=True,
        help="Stable key for safe retries; use a new key only for an intentional new job.",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--yes", action="store_true")


def _add_schedule_plan_id_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--workspace-id")
    parser.add_argument("--id", dest="job_id", required=True)


def _add_schedule_plan_cancel_arguments(parser: argparse.ArgumentParser) -> None:
    _add_schedule_plan_id_arguments(parser)
    parser.add_argument("--reason")
    parser.add_argument("--dry-run", action="store_true")


def _build_schedule_plan_arguments(args: argparse.Namespace) -> dict[str, Any]:
    account_ids = _ordered_unique(args.account_ids)
    if len(account_ids) > ACCOUNT_PUBLISH_MAX_ACCOUNTS:
        raise ValueError(
            "account-publish schedule planning accepts at most "
            f"{ACCOUNT_PUBLISH_MAX_ACCOUNTS} --account-id values."
        )
    if args.operation == "cancel-only":
        plan_only_fields = (
            ("--start-date", args.start_date),
            ("--days", args.days),
            ("--daily-slot", args.daily_slots),
            ("--timezone", args.timezone),
            ("--format-strategy", args.format_strategy),
            ("--topic-strategy", args.topic_strategy),
            ("--product-policy", args.product_policy),
            ("--bgm-policy", args.bgm_policy),
            ("--bgm-strategy", args.bgm_strategy),
            ("--bgm-platform", args.bgm_platform),
            ("--conflict-policy", args.conflict_policy),
        )
        supplied_plan_fields = [flag for flag, value in plan_only_fields if value is not None]
        if supplied_plan_fields:
            raise ValueError(
                f"{', '.join(supplied_plan_fields)} are not allowed with --operation cancel-only."
            )
        cancel_reason = _normalize_cancel_reason(args.cancel_reason)
        return compact_params(
            {
                "operation": "cancel_only",
                "account_ids": account_ids,
                "cancel_reason": cancel_reason,
            }
        )

    if args.cancel_reason is not None:
        raise ValueError("--cancel-reason is only allowed with --operation cancel-only.")
    required_plan_fields = (
        ("--start-date", args.start_date),
        ("--days", args.days),
        ("--daily-slot", args.daily_slots),
        ("--timezone", args.timezone),
    )
    missing_plan_fields = [flag for flag, value in required_plan_fields if value is None]
    if missing_plan_fields:
        raise ValueError(f"{', '.join(missing_plan_fields)} are required with --operation plan.")

    daily_slots = _ordered_unique(args.daily_slots)
    if len(daily_slots) > ACCOUNT_PUBLISH_MAX_DAILY_SLOTS:
        raise ValueError(
            "account-publish schedule planning accepts at most "
            f"{ACCOUNT_PUBLISH_MAX_DAILY_SLOTS} --daily-slot values."
        )
    if not 1 <= args.days <= ACCOUNT_PUBLISH_MAX_DAYS:
        raise ValueError(f"--days must be between 1 and {ACCOUNT_PUBLISH_MAX_DAYS}.")
    occurrence_count = len(account_ids) * args.days * len(daily_slots)
    if occurrence_count > ACCOUNT_PUBLISH_MAX_OCCURRENCES:
        raise ValueError(
            "account-publish schedule planning accepts at most "
            f"{ACCOUNT_PUBLISH_MAX_OCCURRENCES} total occurrences "
            "(unique accounts x days x unique daily slots)."
        )
    _validate_start_date(args.start_date)
    for slot in daily_slots:
        _validate_daily_slot(slot)
    _validate_timezone(args.timezone)

    bgm_policy = {
        "mode": dekebab(args.bgm_policy or "required"),
        "strategy": dekebab(args.bgm_strategy or "rotate"),
        "platform": (args.bgm_platform or "tiktok").strip().lower(),
    }
    if bgm_policy["mode"] == "disabled":
        bgm_policy.pop("strategy")
        bgm_policy.pop("platform")

    return {
        "operation": "plan",
        "account_ids": account_ids,
        "start_date": args.start_date,
        "days": args.days,
        "daily_slots": daily_slots,
        "timezone": args.timezone,
        "format_strategy": dekebab(args.format_strategy or "rotate"),
        "topic_strategy": dekebab(args.topic_strategy or "rotate"),
        "product_policy": dekebab(args.product_policy or "required"),
        "bgm_policy": bgm_policy,
        "conflict_policy": dekebab(args.conflict_policy or "upsert-occurrences"),
    }


def _build_schedule_plan_preview_arguments(args: argparse.Namespace) -> dict[str, Any]:
    return _build_schedule_plan_arguments(args)


def _build_schedule_plan_batch_arguments(args: argparse.Namespace) -> dict[str, Any]:
    payload = _build_schedule_plan_arguments(args)
    preview_token = str(args.preview_token or "").strip()
    if payload["operation"] == "cancel_only" and not preview_token:
        raise ValueError(
            "--preview-token is required with --operation cancel-only; "
            "run +schedule-plan-preview first."
        )
    if (
        payload["operation"] == "plan"
        and payload["conflict_policy"] == "replace_non_published"
        and not preview_token
    ):
        raise ValueError(
            "--preview-token is required with --conflict-policy replace-non-published; "
            "run +schedule-plan-preview first."
        )
    if preview_token:
        if len(preview_token) > 200:
            raise ValueError("--preview-token must be at most 200 characters.")
        payload["preview_token"] = preview_token
    idempotency_key = str(args.idempotency_key or "").strip()
    if not idempotency_key:
        raise ValueError("--idempotency-key must not be blank.")
    if len(idempotency_key) > 240:
        raise ValueError("--idempotency-key must be at most 240 characters.")
    payload["idempotency_key"] = idempotency_key
    return payload


def _normalize_cancel_reason(value: Any) -> str | None:
    if value is None:
        return None
    reason = str(value).strip()
    if not reason:
        raise ValueError("--cancel-reason must not be blank.")
    if len(reason) > 500:
        raise ValueError("--cancel-reason must be at most 500 characters.")
    return reason


def _build_schedule_plan_id_arguments(args: argparse.Namespace) -> dict[str, Any]:
    return {"job_id": args.job_id}


def _build_schedule_plan_cancel_arguments(args: argparse.Namespace) -> dict[str, Any]:
    return compact_params({"job_id": args.job_id, "reason": args.reason})


def _ordered_unique(values: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = str(raw).strip()
        if value and value not in seen:
            output.append(value)
            seen.add(value)
    return output


def _validate_start_date(value: str) -> None:
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("--start-date must use YYYY-MM-DD.") from exc
    if parsed.isoformat() != value:
        raise ValueError("--start-date must use YYYY-MM-DD.")


def _validate_daily_slot(value: str) -> None:
    try:
        parsed = datetime.strptime(value, "%H:%M")
    except ValueError as exc:
        raise ValueError("--daily-slot must use 24-hour HH:MM.") from exc
    if parsed.strftime("%H:%M") != value:
        raise ValueError("--daily-slot must use 24-hour HH:MM.")


def _validate_timezone(value: str) -> None:
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError("--timezone must be a valid IANA timezone, e.g. Asia/Shanghai.") from exc


def _asset_pool_scalar_patch_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "operation": {"type": "string", "enum": ASSET_POOL_SCALAR_OPERATION_CHOICES},
            "value_id": _uuid_id_schema("Required for set; forbidden for clear/unchanged."),
        },
        "required": ["operation"],
        "allOf": [
            {
                "if": {"properties": {"operation": {"const": "set"}}},
                "then": {"required": ["value_id"]},
                "else": {"not": {"required": ["value_id"]}},
            }
        ],
    }


def _asset_pool_collection_patch_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "operation": {
                "type": "string",
                "enum": ASSET_POOL_COLLECTION_OPERATION_CHOICES,
            },
            "ids": {
                "type": "array",
                "items": _uuid_id_schema(),
                "minItems": 1,
                "uniqueItems": True,
            },
        },
        "required": ["operation"],
        "allOf": [
            {
                "if": {"properties": {"operation": {"enum": ["replace", "add", "remove"]}}},
                "then": {"required": ["ids"]},
                "else": {"not": {"required": ["ids"]}},
            }
        ],
    }


def _asset_pool_patch_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "description": (
            "Patch-style asset-pool mutation. Omitted uniform fields are unchanged. In an "
            "account-specific override, omitted fields inherit the uniform patch; explicit "
            "operation=unchanged opts that account out of the uniform field change."
        ),
        "properties": {
            "persona": _asset_pool_scalar_patch_schema(),
            "product": _asset_pool_scalar_patch_schema(),
            "formats": _asset_pool_collection_patch_schema(),
            "topics": _asset_pool_collection_patch_schema(),
            "bgm": _asset_pool_collection_patch_schema(),
        },
        "minProperties": 1,
    }


def _asset_pool_account_ids_schema() -> dict[str, Any]:
    return {
        "type": "array",
        "items": _uuid_id_schema("Pool account UUID."),
        "minItems": 1,
        "maxItems": ACCOUNT_PUBLISH_MAX_ACCOUNTS,
        "uniqueItems": True,
    }


def _asset_pools_batch_get_input_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "account_ids": _asset_pool_account_ids_schema(),
            "include_resource_details": {
                "type": "boolean",
                "default": True,
                "description": (
                    "Include hydrated product/format/topic/BGM details for semantic and "
                    "structural auditing without per-account or per-resource calls."
                ),
            },
        },
        "required": ["account_ids"],
    }


def _asset_pools_mutation_input_schema(*, include_submission: bool) -> dict[str, Any]:
    properties: dict[str, Any] = {
        "account_ids": _asset_pool_account_ids_schema(),
        "uniform_patch": _asset_pool_patch_schema(),
        "account_patches": {
            "type": "array",
            "maxItems": ACCOUNT_PUBLISH_MAX_ACCOUNTS,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "account_id": _uuid_id_schema(
                        "Must also appear in account_ids; one override per account."
                    ),
                    "patch": _asset_pool_patch_schema(),
                },
                "required": ["account_id", "patch"],
            },
            "description": (
                "Per-account precise overrides supplied with --account-patches-json/file. "
                "Explicit fields override uniform_patch; omitted fields inherit it."
            ),
        },
    }
    required = ["account_ids"]
    if include_submission:
        properties.update(
            {
                "preview_token": {"type": "string", "minLength": 1, "maxLength": 200},
                "idempotency_key": {"type": "string", "minLength": 1, "maxLength": 240},
                "dry_run": {"type": "boolean", "default": False},
            }
        )
        required.extend(["preview_token", "idempotency_key"])
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "anyOf": [{"required": ["uniform_patch"]}, {"required": ["account_patches"]}],
    }


def _asset_pools_job_input_schema(*, include_reason: bool) -> dict[str, Any]:
    properties: dict[str, Any] = {
        "job_id": _uuid_id_schema("Asset-pool batch job UUID returned by +asset-pools-batch-set.")
    }
    if include_reason:
        properties["reason"] = {"type": ["string", "null"], "maxLength": 500}
        properties["dry_run"] = {"type": "boolean", "default": False}
    return {"type": "object", "properties": properties, "required": ["job_id"]}


def _asset_pools_async_output_schema() -> dict[str, Any]:
    schema = _async_output_schema("Durable account publish asset-pool batch job.")
    run = schema["properties"]["run"]
    run["properties"]["recommended_wakeup_delay_seconds"] = {
        "type": "integer",
        "minimum": 1,
        "description": "Server-recommended delay before the next job status check.",
    }
    return schema


def _schedule_plan_input_schema(*, include_idempotency_key: bool) -> dict[str, Any]:
    properties: dict[str, Any] = {
        "operation": {
            "type": "string",
            "enum": SCHEDULE_PLAN_OPERATION_CHOICES,
            "default": "plan",
            "description": (
                "plan creates/rebuilds schedule items; cancel-only cancels the account's "
                "current eligible schedule items."
            ),
        },
        "account_ids": {
            "type": "array",
            "items": _uuid_id_schema("Pool account UUID."),
            "minItems": 1,
            "maxItems": ACCOUNT_PUBLISH_MAX_ACCOUNTS,
            "uniqueItems": True,
        },
        "start_date": {"type": "string", "format": "date"},
        "days": {"type": "integer", "minimum": 1, "maximum": ACCOUNT_PUBLISH_MAX_DAYS},
        "daily_slots": {
            "type": "array",
            "items": {"type": "string", "pattern": "^(?:[01]\\d|2[0-3]):[0-5]\\d$"},
            "minItems": 1,
            "maxItems": ACCOUNT_PUBLISH_MAX_DAILY_SLOTS,
            "uniqueItems": True,
        },
        "timezone": {"type": "string", "description": "IANA timezone."},
        "format_strategy": {"type": "string", "enum": FORMAT_STRATEGY_CHOICES},
        "topic_strategy": {"type": "string", "enum": TOPIC_STRATEGY_CHOICES},
        "product_policy": {"type": "string", "enum": PRODUCT_POLICY_CHOICES},
        "bgm_policy": {
            "type": "string",
            "enum": BGM_POLICY_CHOICES,
            "default": "required",
            "description": "CLI --bgm-policy mode.",
        },
        "bgm_strategy": {
            "type": "string",
            "enum": BGM_STRATEGY_CHOICES,
            "default": "rotate",
            "description": "CLI --bgm-strategy; ignored when bgm_policy is disabled.",
        },
        "bgm_platform": {
            "type": "string",
            "default": "tiktok",
            "description": "CLI --bgm-platform; ignored when bgm_policy is disabled.",
        },
        "conflict_policy": {
            "type": "string",
            "enum": CONFLICT_POLICY_CHOICES,
            "default": "upsert-occurrences",
        },
        "cancel_reason": {"type": "string", "minLength": 1, "maxLength": 500},
    }
    if include_idempotency_key:
        properties["preview_token"] = {"type": "string", "minLength": 1, "maxLength": 200}
        properties["idempotency_key"] = {"type": "string", "minLength": 1, "maxLength": 240}
        properties["dry_run"] = {"type": "boolean", "default": False}
    plan_only_fields = [
        "start_date",
        "days",
        "daily_slots",
        "timezone",
        "format_strategy",
        "topic_strategy",
        "product_policy",
        "bgm_policy",
        "bgm_strategy",
        "bgm_platform",
        "conflict_policy",
    ]
    cancel_only_then: dict[str, Any] = {
        "not": {"anyOf": [{"required": [field]} for field in plan_only_fields]}
    }
    if include_idempotency_key:
        cancel_only_then["required"] = ["preview_token"]
    schema: dict[str, Any] = {
        "type": "object",
        "description": (
            "operation=plan requires the plan fields and caps unique account_ids x days x "
            f"unique daily_slots at {ACCOUNT_PUBLISH_MAX_OCCURRENCES} total occurrences. "
            "operation=cancel-only forbids every plan-only field."
        ),
        "properties": properties,
        "required": ["account_ids"],
        "allOf": [
            {
                "if": {
                    "properties": {"operation": {"const": "cancel-only"}},
                    "required": ["operation"],
                },
                "then": cancel_only_then,
                "else": {
                    "required": ["start_date", "days", "daily_slots", "timezone"],
                    "not": {"required": ["cancel_reason"]},
                },
            }
        ],
    }
    if include_idempotency_key:
        schema["required"].append("idempotency_key")
        schema["allOf"].append(
            {
                "if": {
                    "properties": {"conflict_policy": {"const": "replace-non-published"}},
                    "required": ["conflict_policy"],
                },
                "then": {"required": ["preview_token"]},
            }
        )
    return schema


def _schedule_plan_job_input_schema(*, include_reason: bool) -> dict[str, Any]:
    properties: dict[str, Any] = {
        "job_id": _uuid_id_schema("Schedule-plan job UUID returned by +schedule-plan-batch.")
    }
    if include_reason:
        properties["reason"] = {"type": ["string", "null"], "maxLength": 500}
        properties["dry_run"] = {"type": "boolean", "default": False}
    return {"type": "object", "properties": properties, "required": ["job_id"]}


def _schedule_plan_async_output_schema() -> dict[str, Any]:
    schema = _async_output_schema("Durable schedule-plan job returned by Museon API.")
    run = schema["properties"]["run"]
    run["properties"]["recommended_wakeup_delay_seconds"] = {
        "type": "integer",
        "minimum": 1,
        "description": "Server-recommended delay before the next job status check.",
    }
    return schema


def specs() -> list[CommandSpec]:
    return [
        CommandSpec(
            domain=Domain.ACCOUNT_PUBLISH,
            shortcut="+asset-pools-batch-get",
            summary=(
                "Read effective persona, product, format, topic, and BGM pools for MULTIPLE "
                "accounts in one request, with per-account issues and hydrated resource details "
                "by default. MUST use this for multi-account audits instead "
                "of looping social-account +assets-get; keep that single command for small, "
                "precise one-account reads. This batch command is also valid for a complete "
                "five-pool inspection of one account."
            ),
            risk_level="read",
            execution="direct",
            adapter_tool_name="account_publish_asset_pools_batch_get",
            input_schema=_asset_pools_batch_get_input_schema(),
            output_schema=_direct_output_schema(
                "Batch effective publish asset pools and audit summary returned by Museon API."
            ),
            examples=[
                (
                    "museoncli account-publish +asset-pools-batch-get "
                    "--account-id <uuid1> --account-id <uuid2>"
                )
            ],
            add_arguments=_add_asset_pools_batch_get_arguments,
            build_arguments=_build_asset_pools_batch_get_arguments,
        ),
        CommandSpec(
            domain=Domain.ACCOUNT_PUBLISH,
            shortcut="+asset-pools-batch-preview",
            summary=(
                "Live-preview one multi-account asset-pool change without writing. Supports a "
                "uniform patch plus per-account precise overrides for persona, product, formats, "
                "topics, and BGM. Always run this before +asset-pools-batch-set, present every "
                "changed/skipped/failed account and existing-schedule impact, then obtain explicit "
                "approval. Fully-managed accounts fail per-account in v1 and cannot be bypassed."
            ),
            risk_level="read",
            execution="direct",
            adapter_tool_name="account_publish_asset_pools_batch_preview",
            input_schema=_asset_pools_mutation_input_schema(include_submission=False),
            output_schema=_direct_output_schema(
                "Live account publish asset-pool batch preview returned by Museon API."
            ),
            examples=[
                (
                    "museoncli account-publish +asset-pools-batch-preview "
                    "--account-id <uuid1> --account-id <uuid2> "
                    "--product-operation set --product-id <product_id> "
                    "--formats-operation add --format-id <format_id>"
                ),
                (
                    "museoncli account-publish +asset-pools-batch-preview "
                    "--account-id <uuid1> --account-id <uuid2> "
                    "--account-patches-file ./account-patches.json"
                ),
            ],
            add_arguments=_add_asset_pools_batch_preview_arguments,
            build_arguments=_build_asset_pools_batch_preview_arguments,
        ),
        CommandSpec(
            domain=Domain.ACCOUNT_PUBLISH,
            shortcut="+asset-pools-batch-set",
            summary=(
                "Submit one durable Cloud Task job to change publish asset pools for MULTIPLE "
                "accounts. MUST use this instead of looping social-account +assets-set or writing "
                "Python/shell scripts; keep the single command for small, precise one-account "
                "edits. This batch command is preferred when atomically configuring all five "
                "pools for one account. "
                "Requires the opaque token and identical normalized patches from a fresh live "
                "preview, plus a stable idempotency key and --yes. After submission, poll only "
                "+asset-pools-batch-status and inspect every failed/skipped account. Fully-managed "
                "accounts fail per-account in v1 and cannot be bypassed."
            ),
            risk_level="destructive",
            execution="async_run",
            adapter_tool_name="account_publish_asset_pools_batch_set",
            input_schema=_asset_pools_mutation_input_schema(include_submission=True),
            output_schema=_asset_pools_async_output_schema(),
            examples=[
                (
                    "museoncli account-publish +asset-pools-batch-set "
                    "--account-id <uuid1> --account-id <uuid2> "
                    "--product-operation set --product-id <product_id> "
                    "--formats-operation add --format-id <format_id> "
                    "--preview-token <preview_token> --idempotency-key <stable_key> --yes"
                )
            ],
            add_arguments=_add_asset_pools_batch_set_arguments,
            build_arguments=_build_asset_pools_batch_set_arguments,
            supports_dry_run=True,
            requires_confirmation=True,
        ),
        CommandSpec(
            domain=Domain.ACCOUNT_PUBLISH,
            shortcut="+asset-pools-batch-status",
            summary=(
                "Read durable asset-pool batch progress and per-account results. This is the only "
                "state source after +asset-pools-batch-set; do not rescan accounts or loop "
                "social-account +assets-get for verification."
            ),
            risk_level="read",
            execution="direct",
            adapter_tool_name="account_publish_asset_pools_batch_status",
            input_schema=_asset_pools_job_input_schema(include_reason=False),
            output_schema=_direct_output_schema(
                "Account publish asset-pool batch job status returned by Museon API."
            ),
            examples=["museoncli account-publish +asset-pools-batch-status --id <job_id>"],
            add_arguments=_add_asset_pools_job_arguments,
            build_arguments=_build_asset_pools_job_arguments,
        ),
        CommandSpec(
            domain=Domain.ACCOUNT_PUBLISH,
            shortcut="+asset-pools-batch-cancel",
            summary=(
                "Request cancellation of a durable asset-pool batch job. Stops account work not "
                "yet started but does not roll back accounts already completed."
            ),
            risk_level="write",
            execution="direct",
            adapter_tool_name="account_publish_asset_pools_batch_cancel",
            input_schema=_asset_pools_job_input_schema(include_reason=True),
            output_schema=_direct_output_schema(
                "Account publish asset-pool batch cancellation result returned by API."
            ),
            examples=[
                (
                    "museoncli account-publish +asset-pools-batch-cancel --id <job_id> "
                    "--reason 'operator request'"
                )
            ],
            add_arguments=_add_asset_pools_batch_cancel_arguments,
            build_arguments=_build_asset_pools_batch_cancel_arguments,
            supports_dry_run=True,
        ),
        CommandSpec(
            domain=Domain.ACCOUNT_PUBLISH,
            shortcut="+schedule-plan-preview",
            summary=(
                "Live-preview a durable schedule-plan operation without writing. "
                "--operation cancel-only is the primary way to inspect deletion of current "
                "eligible schedule items: it returns cancellable/protected counts by status "
                "and an opaque token for the matching batch. For --operation plan, use this "
                "before replace-non-published; unlike generic --dry-run, it asks the server to "
                "inspect current conflicts, account assets, product bindings, and BGM "
                "availability. "
                "After resolving account IDs in one bulk social-account +list call, invoke this "
                "preview directly; do not preflight with per-account asset, BGM, schedule, or "
                "publish-version calls. "
                "The response preview_token must be passed unchanged to the matching replace "
                "submission."
            ),
            risk_level="read",
            execution="direct",
            adapter_tool_name="account_publish_schedule_plan_preview",
            input_schema=_schedule_plan_input_schema(include_idempotency_key=False),
            output_schema=_direct_output_schema(
                "Live schedule-plan preview returned by Museon API."
            ),
            examples=[
                (
                    "museoncli account-publish +schedule-plan-preview "
                    "--account-id <uuid1> --account-id <uuid2> --start-date 2026-07-17 "
                    "--days 5 --daily-slot 17:00 --daily-slot 22:00 "
                    "--timezone Asia/Shanghai --conflict-policy replace-non-published "
                    "--bgm-policy required"
                ),
                (
                    "museoncli account-publish +schedule-plan-preview "
                    "--operation cancel-only --account-id <uuid1> --account-id <uuid2> "
                    "--cancel-reason 'operator requested schedule removal'"
                ),
            ],
            add_arguments=_add_schedule_plan_preview_arguments,
            build_arguments=_build_schedule_plan_preview_arguments,
        ),
        CommandSpec(
            domain=Domain.ACCOUNT_PUBLISH,
            shortcut="+schedule-plan-batch",
            summary=(
                "Submit one durable asynchronous schedule-plan operation. --operation "
                "cancel-only is the primary batch deletion path for current eligible schedule "
                "items; it requires the matching preview token and reports cancelled, already "
                "cancelled, and protected results by prior status. For --operation plan, create "
                "MULTIPLE accounts or MULTIPLE occurrences. MUST use this command instead of "
                "looping social-account "
                "+schedule-list/+schedule-create/+schedule-delete or Python/shell scripts. "
                "One plan accepts up to 200 accounts and 5,000 total occurrences. "
                "BGM mode required makes an account fail when its pool has no valid BGM; it "
                "never silently creates a no-BGM occurrence. After submission, the only state "
                "source is +schedule-plan-status. When --bgm-policy required finishes with "
                "status succeeded, the server guarantees every created occurrence has a "
                "concrete BGM; use bgm_bound_count/summary.bgm_bound and never call "
                "schedule-list, bgm-asset-list, or routines to verify it. Inspect every "
                "failed/skipped account. "
                "replace-non-published requires the opaque preview token from a matching live "
                "preview and fails closed when the preview has drifted. --idempotency-key is "
                "required: reuse it only for retries of the same submission, and use a new key "
                "for an intentional new job. Copy full canonical account UUIDs and the preview "
                "token verbatim from the successful preview; never reconstruct them."
            ),
            risk_level="destructive",
            execution="async_run",
            adapter_tool_name="account_publish_schedule_plan_batch",
            input_schema=_schedule_plan_input_schema(include_idempotency_key=True),
            output_schema=_schedule_plan_async_output_schema(),
            examples=[
                (
                    "museoncli account-publish +schedule-plan-batch "
                    "--account-id <uuid1> --account-id <uuid2> --start-date 2026-07-17 "
                    "--days 5 --daily-slot 17:00 --daily-slot 22:00 "
                    "--timezone Asia/Shanghai --conflict-policy replace-non-published "
                    "--preview-token <preview_token> --bgm-policy required "
                    "--idempotency-key <stable_key> --yes"
                ),
                (
                    "museoncli account-publish +schedule-plan-batch "
                    "--operation cancel-only --account-id <uuid1> --account-id <uuid2> "
                    "--preview-token <preview_token> --cancel-reason "
                    "'operator requested schedule removal' "
                    "--idempotency-key <stable_key> --yes"
                ),
            ],
            add_arguments=_add_schedule_plan_batch_arguments,
            build_arguments=_build_schedule_plan_batch_arguments,
            supports_dry_run=True,
            requires_confirmation=True,
        ),
        CommandSpec(
            domain=Domain.ACCOUNT_PUBLISH,
            shortcut="+schedule-plan-status",
            summary=(
                "Read durable schedule-plan operation progress and per-account results. This is "
                "the only state source after submission. cancel-only results include cancelled "
                "and protected counts by prior status. For plan with --bgm-policy required and "
                "status "
                "succeeded, bgm_bound_count/summary.bgm_bound is the server-owned proof that "
                "every created occurrence has concrete BGM; never call schedule-list, "
                "bgm-asset-list, or routines for post-write verification, rescan accounts, or "
                "rely on /tmp state."
            ),
            risk_level="read",
            execution="direct",
            adapter_tool_name="account_publish_schedule_plan_status",
            input_schema=_schedule_plan_job_input_schema(include_reason=False),
            output_schema=_direct_output_schema("Schedule-plan job status returned by Museon API."),
            examples=["museoncli account-publish +schedule-plan-status --id <job_id>"],
            add_arguments=_add_schedule_plan_id_arguments,
            build_arguments=_build_schedule_plan_id_arguments,
        ),
        CommandSpec(
            domain=Domain.ACCOUNT_PUBLISH,
            shortcut="+schedule-plan-cancel",
            summary=(
                "Abort unfinished work in a durable schedule-plan job. This is job control only: "
                "it never deletes schedule items already created. Use "
                "+schedule-plan-preview/+schedule-plan-batch --operation cancel-only when the "
                "operator wants schedule items removed."
            ),
            risk_level="write",
            execution="direct",
            adapter_tool_name="account_publish_schedule_plan_cancel",
            input_schema=_schedule_plan_job_input_schema(include_reason=True),
            output_schema=_direct_output_schema(
                "Schedule-plan cancellation result returned by API."
            ),
            examples=[
                "museoncli account-publish +schedule-plan-cancel --id <job_id> --reason 'operator request'"
            ],
            add_arguments=_add_schedule_plan_cancel_arguments,
            build_arguments=_build_schedule_plan_cancel_arguments,
            supports_dry_run=True,
        ),
    ]


async def _execute_asset_pools_batch_get(ctx: CommandContext) -> Any:
    if not ctx.workspace_id:
        raise RuntimeError("missing_workspace")
    return await ctx.api_data_v2(
        ctx.cfg,
        "POST",
        "/account-publish/asset-pools:batch-get",
        json_body={"workspace_id": ctx.workspace_id, **ctx.arguments},
    )


async def _execute_asset_pools_batch_preview(ctx: CommandContext) -> Any:
    if not ctx.workspace_id:
        raise RuntimeError("missing_workspace")
    return await ctx.api_data_v2(
        ctx.cfg,
        "POST",
        "/account-publish/asset-pools:batch-preview",
        json_body={"workspace_id": ctx.workspace_id, **ctx.arguments},
    )


async def _execute_asset_pools_batch_set(ctx: CommandContext) -> Any:
    if not ctx.workspace_id:
        raise RuntimeError("missing_workspace")
    return await ctx.api_data_v2(
        ctx.cfg,
        "POST",
        "/account-publish/asset-pools:batch-set",
        json_body={"workspace_id": ctx.workspace_id, **ctx.arguments},
    )


async def _execute_asset_pools_batch_status(ctx: CommandContext) -> Any:
    if not ctx.workspace_id:
        raise RuntimeError("missing_workspace")
    job_id = str(ctx.arguments.get("job_id") or "")
    return await ctx.api_data_v2(
        ctx.cfg,
        "GET",
        f"/account-publish/asset-pools/jobs/{job_id}",
        params={"workspace_id": ctx.workspace_id},
    )


async def _execute_asset_pools_batch_cancel(ctx: CommandContext) -> Any:
    if not ctx.workspace_id:
        raise RuntimeError("missing_workspace")
    job_id = str(ctx.arguments.get("job_id") or "")
    return await ctx.api_data_v2(
        ctx.cfg,
        "POST",
        f"/account-publish/asset-pools/jobs/{job_id}:cancel",
        json_body=compact_params(
            {"workspace_id": ctx.workspace_id, "reason": ctx.arguments.get("reason")}
        ),
    )


async def _execute_schedule_plan_preview(ctx: CommandContext) -> Any:
    if not ctx.workspace_id:
        raise RuntimeError("missing_workspace")
    return await ctx.api_data_v2(
        ctx.cfg,
        "POST",
        "/account-publish/schedule-plans:preview",
        json_body={"workspace_id": ctx.workspace_id, **ctx.arguments},
    )


async def _execute_schedule_plan_batch(ctx: CommandContext) -> Any:
    if not ctx.workspace_id:
        raise RuntimeError("missing_workspace")
    return await ctx.api_data_v2(
        ctx.cfg,
        "POST",
        "/account-publish/schedule-plans:batch",
        json_body={"workspace_id": ctx.workspace_id, **ctx.arguments},
    )


async def _execute_schedule_plan_status(ctx: CommandContext) -> Any:
    if not ctx.workspace_id:
        raise RuntimeError("missing_workspace")
    job_id = str(ctx.arguments.get("job_id") or "")
    return await ctx.api_data_v2(
        ctx.cfg,
        "GET",
        f"/account-publish/schedule-plans/{job_id}",
        params={"workspace_id": ctx.workspace_id},
    )


async def _execute_schedule_plan_cancel(ctx: CommandContext) -> Any:
    if not ctx.workspace_id:
        raise RuntimeError("missing_workspace")
    job_id = str(ctx.arguments.get("job_id") or "")
    return await ctx.api_data_v2(
        ctx.cfg,
        "POST",
        f"/account-publish/schedule-plans/{job_id}:cancel",
        json_body=compact_params(
            {"workspace_id": ctx.workspace_id, "reason": ctx.arguments.get("reason")}
        ),
    )


EXECUTORS = {
    "account-publish.asset-pools-batch-get": direct_enveloped(_execute_asset_pools_batch_get),
    "account-publish.asset-pools-batch-preview": direct_enveloped(
        _execute_asset_pools_batch_preview
    ),
    "account-publish.asset-pools-batch-set": direct_enveloped(_execute_asset_pools_batch_set),
    "account-publish.asset-pools-batch-status": direct_enveloped(_execute_asset_pools_batch_status),
    "account-publish.asset-pools-batch-cancel": direct_enveloped(_execute_asset_pools_batch_cancel),
    "account-publish.schedule-plan-preview": direct_enveloped(_execute_schedule_plan_preview),
    "account-publish.schedule-plan-batch": direct_enveloped(_execute_schedule_plan_batch),
    "account-publish.schedule-plan-status": direct_enveloped(_execute_schedule_plan_status),
    "account-publish.schedule-plan-cancel": direct_enveloped(_execute_schedule_plan_cancel),
}
