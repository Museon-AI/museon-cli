"""Part of the museoncli domains/executors architecture (see docs/museoncli-optimization-plan.md)."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from museoncli.config import Config
from museoncli.domains._model import CommandSpec
from museoncli.envelopes import add_routine_refs, direct_api_envelope, domain_command_envelope

_ROUTINE_TARGET_DELIVERY_MODES = {
    "session_reply",
    "deferred_session_result",
    "deferred_root_result",
    "root_reply",
}
_ROUTINE_RESULT_DELIVERY_MODES = {
    "deferred_session_result",
    "deferred_root_result",
}


@dataclass
class CommandContext:
    cfg: Config
    spec: CommandSpec
    args: argparse.Namespace | None
    arguments: dict[str, Any]
    workspace_id: str | None
    api_data: Callable[..., Awaitable[Any]]
    api_data_v2: Callable[..., Awaitable[Any]]
    upload_media_file: Callable[..., Awaitable[Any]]
    upload_artifact_file: Callable[..., Awaitable[Any]]


Executor = Callable[[CommandContext], Awaitable[dict[str, Any]]]
RawCommand = Callable[[CommandContext], Awaitable[Any]]


def direct_enveloped(fn: RawCommand, *, with_workspace: bool = True) -> Executor:
    async def run(ctx: CommandContext) -> dict[str, Any]:
        raw = await fn(ctx)
        workspace_id = ctx.workspace_id if with_workspace else None
        return direct_api_envelope(
            ctx.spec.schema_name,
            workspace_id,
            raw,
            site_url=ctx.cfg.site_url,
        )

    return run


def routines_enveloped(fn: RawCommand) -> Executor:
    async def run(ctx: CommandContext) -> dict[str, Any]:
        raw = await fn(ctx)
        if ctx.spec.schema_name in {"routines.list", "routines.get"}:
            raw = add_routine_refs(raw, site_url=ctx.cfg.site_url)
        return direct_api_envelope(
            ctx.spec.schema_name,
            ctx.workspace_id,
            raw,
            site_url=ctx.cfg.site_url,
        )

    return run


async def adapter_call(ctx: CommandContext) -> Any:
    payload = {
        "arguments": ctx.arguments,
        "workspace_id": ctx.workspace_id,
        "runtime_context": None,
        "wait": False,
        "wait_timeout_seconds": 0,
        "poll_interval_seconds": 2.0,
    }
    return await ctx.api_data(
        ctx.cfg,
        "POST",
        f"/agent-cli/tools/{ctx.spec.adapter_tool_name}/call",
        json_body=payload,
    )


def adapter_executor(ctx_unused: None = None) -> Executor:
    async def run(ctx: CommandContext) -> dict[str, Any]:
        data = await adapter_call(ctx)
        return domain_command_envelope(ctx.spec.schema_name, data, site_url=ctx.cfg.site_url)

    return run


def agent_domain_result(response: Any) -> Any:
    if isinstance(response, dict) and "domain" in response and "result" in response:
        return response.get("result")
    return response


def compact_params(params: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in params.items() if value is not None}


def read_json_option(
    *,
    value: str | None,
    file_path: str | None,
    field: str,
    default: Any | None = None,
) -> Any:
    if value is None and file_path is None and default is not None:
        return default
    text = read_text_option(value=value, file_path=file_path, field=field)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid_{field}_json: {exc}") from exc


def read_text_option(*, value: str | None, file_path: str | None, field: str) -> str:
    if value is not None and file_path is not None:
        raise RuntimeError(f"{field}: provide either inline value or file, not both")
    if file_path is not None:
        return Path(file_path).read_text(encoding="utf-8")
    if value is not None:
        return value
    raise RuntimeError(f"missing_{field}")


def routine_turn_context(
    cfg: Config,
    *,
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    runtime = runtime_context_with_env(cfg)
    source_channel_message_id = (
        runtime.get("source_channel_message_id")
        or runtime.get("source_runtime_message_id")
        or runtime.get("trigger_message_id")
    )
    return compact_params(
        {
            "conversation_id": runtime.get("conversation_id"),
            "source_conversation_id": runtime.get("source_conversation_id"),
            "source_channel_message_id": source_channel_message_id,
            "source_external_message_id": runtime.get("source_external_message_id"),
            "origin_turn_id": runtime.get("origin_turn_id"),
            **routine_target_context(arguments, runtime=runtime),
        }
    )


def routine_target_context(
    arguments: dict[str, Any] | None,
    *,
    runtime: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not isinstance(arguments, dict):
        return {}
    runtime = runtime if isinstance(runtime, dict) else {}
    other_scope_conversation_id = clean_optional_argument(
        arguments.get("other_scope_conversation_id")
    )
    requested_result_delivery_mode = clean_optional_argument(
        arguments.get("result_delivery_mode")
    )
    target_conversation_id = clean_optional_argument(arguments.get("target_conversation_id"))
    target_channel_chat_id = clean_optional_argument(arguments.get("target_channel_chat_id"))
    requested_target_delivery_mode = clean_optional_argument(arguments.get("target_delivery_mode"))
    legacy_target_requested = bool(
        target_conversation_id or target_channel_chat_id or requested_target_delivery_mode
    )
    canonical_requested = bool(other_scope_conversation_id or requested_result_delivery_mode)
    if canonical_requested and legacy_target_requested:
        raise RuntimeError(
            "routine delivery accepts either other_scope_conversation_id/result_delivery_mode "
            "or legacy target_* arguments, not both"
        )
    if not legacy_target_requested:
        result_delivery_mode = _routine_result_delivery_mode(
            requested_result_delivery_mode,
            other_scope_conversation_id=other_scope_conversation_id,
        )
        return compact_params(
            {
                "other_scope_conversation_id": other_scope_conversation_id,
                "result_delivery_mode": result_delivery_mode,
            }
        )
    target_channel_id = (
        clean_optional_argument(runtime.get("channel_id"))
        if target_channel_chat_id and not target_conversation_id
        else None
    )
    target_delivery_mode = _routine_target_delivery_mode(
        requested_target_delivery_mode,
        target_conversation_id=target_conversation_id,
        target_channel_chat_id=target_channel_chat_id,
    )
    return compact_params(
        {
            "target_conversation_id": target_conversation_id,
            "target_channel_id": target_channel_id,
            "target_channel_chat_id": target_channel_chat_id,
            "target_delivery_mode": target_delivery_mode,
        }
    )


def runtime_context_with_env(cfg: Config) -> dict[str, Any]:
    runtime = dict(cfg.runtime_context) if isinstance(cfg.runtime_context, dict) else {}
    env_defaults = {
        "conversation_id": os.environ.get("MUSEON_CONVERSATION_ID")
        or os.environ.get("MUSEON_SESSION_CONVERSATION_ID"),
        "source_conversation_id": os.environ.get("MUSEON_SCOPE_CONVERSATION_ID")
        or os.environ.get("MUSEON_CONVERSATION_ID")
        or os.environ.get("MUSEON_SESSION_CONVERSATION_ID"),
        "sandbox_id": os.environ.get("MUSEON_SANDBOX_ID"),
    }
    for key, value in env_defaults.items():
        if runtime.get(key) is None and value:
            runtime[key] = value
    return runtime


def clean_optional_argument(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _routine_target_delivery_mode(
    value: Any,
    *,
    target_conversation_id: str | None,
    target_channel_chat_id: str | None,
) -> str | None:
    explicit = clean_optional_argument(value)
    if explicit:
        normalized = explicit.replace("-", "_")
        if normalized in _ROUTINE_TARGET_DELIVERY_MODES:
            return normalized
        return explicit
    if target_conversation_id:
        return "deferred_session_result"
    if target_channel_chat_id:
        return "deferred_root_result"
    return None


def _routine_result_delivery_mode(
    value: Any,
    *,
    other_scope_conversation_id: str | None,
) -> str | None:
    explicit = clean_optional_argument(value)
    if explicit:
        normalized = explicit.replace("-", "_")
        if normalized in _ROUTINE_RESULT_DELIVERY_MODES:
            return normalized
        return explicit
    if other_scope_conversation_id:
        return "deferred_root_result"
    return None


def _dict_argument(arguments: dict[str, Any], key: str) -> dict[str, Any]:
    value = arguments.get(key)
    if not isinstance(value, dict):
        raise RuntimeError(f"{key} must be an object")
    return value


async def api_data(*args: Any, **kwargs: Any) -> Any:
    """Late-bound proxy to main.api_data — keeps the monkeypatch seam intact."""
    from museoncli import main as _main

    return await _main.api_data(*args, **kwargs)


async def api_data_v2(*args: Any, **kwargs: Any) -> Any:
    """Late-bound proxy to main.api_data_v2 — keeps the monkeypatch seam intact."""
    from museoncli import main as _main

    return await _main.api_data_v2(*args, **kwargs)
