"""Staff-only read adapters for operational diagnosis through Mel."""

from __future__ import annotations

import argparse
import json
from typing import Any

from museoncli.domains._model import CommandSpec, Domain
from museoncli.domains._shared import (
    _add_common_adapter_arguments,
    _direct_output_schema,
    _load_structured_args,
    _without_none,
)
from museoncli.execution import adapter_executor


def _json_object(value: str | None, *, flag: str) -> dict[str, Any]:
    if value is None:
        return {}
    try:
        parsed = json.loads(value)
    except ValueError as exc:
        raise ValueError(f"{flag} must be valid JSON.") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"{flag} must be a JSON object.")
    return dict(parsed)


def _json_list(value: str | None, *, flag: str) -> list[Any]:
    if value is None:
        return []
    try:
        parsed = json.loads(value)
    except ValueError as exc:
        raise ValueError(f"{flag} must be valid JSON.") from exc
    if not isinstance(parsed, list):
        raise ValueError(f"{flag} must be a JSON array.")
    return list(parsed)


def _add_code_read_arguments(parser: argparse.ArgumentParser) -> None:
    _add_common_adapter_arguments(parser)
    parser.add_argument("--path", required=True)
    parser.add_argument("--start-line", type=int, default=1)
    parser.add_argument("--end-line", type=int)


def _build_code_read_arguments(args: argparse.Namespace) -> dict[str, Any]:
    payload = _load_structured_args(args)
    payload.update(
        _without_none({"path": args.path, "start_line": args.start_line, "end_line": args.end_line})
    )
    return payload


def _add_code_search_arguments(parser: argparse.ArgumentParser) -> None:
    _add_common_adapter_arguments(parser)
    parser.add_argument("--query", required=True)
    parser.add_argument("--path-prefix", default="app")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--case-sensitive", action="store_true")


def _build_code_search_arguments(args: argparse.Namespace) -> dict[str, Any]:
    payload = _load_structured_args(args)
    payload.update(
        {
            "query": args.query,
            "path_prefix": args.path_prefix,
            "limit": args.limit,
            "case_sensitive": args.case_sensitive,
        }
    )
    return payload


def _add_supabase_read_arguments(parser: argparse.ArgumentParser) -> None:
    _add_common_adapter_arguments(parser)
    parser.add_argument("--table", required=True)
    parser.add_argument("--column", dest="columns", action="append", required=True)
    parser.add_argument("--filters-json")
    parser.add_argument("--order-by", required=True)
    parser.add_argument("--ascending", action="store_true")
    parser.add_argument("--limit", type=int, default=25)


def _build_supabase_read_arguments(args: argparse.Namespace) -> dict[str, Any]:
    payload = _load_structured_args(args)
    payload.update(
        {
            "table": args.table,
            "columns": args.columns,
            "filters": _json_list(args.filters_json, flag="--filters-json"),
            "order_by": args.order_by,
            "ascending": args.ascending,
            "limit": args.limit,
        }
    )
    return payload


def _add_log_search_arguments(parser: argparse.ArgumentParser) -> None:
    _add_common_adapter_arguments(parser)
    parser.add_argument(
        "--source", choices=["cloud-logging", "agents-timeline"], default="cloud-logging"
    )
    parser.add_argument("--start-time", required=True)
    parser.add_argument("--end-time", required=True)
    parser.add_argument("--service")
    parser.add_argument("--severity", default="INFO")
    parser.add_argument("--identifiers-json")
    parser.add_argument("--text-query")
    parser.add_argument("--limit", type=int, default=50)


def _build_log_search_arguments(args: argparse.Namespace) -> dict[str, Any]:
    payload = _load_structured_args(args)
    payload.update(
        _without_none(
            {
                "source": args.source.replace("-", "_"),
                "start_time": args.start_time,
                "end_time": args.end_time,
                "service": args.service,
                "severity": args.severity,
                "identifiers": _json_object(args.identifiers_json, flag="--identifiers-json"),
                "text_query": args.text_query,
                "limit": args.limit,
            }
        )
    )
    return payload


def _code_read_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "path": {"type": "string", "minLength": 1, "maxLength": 500},
            "start_line": {"type": "integer", "minimum": 1, "default": 1},
            "end_line": {"type": ["integer", "null"], "minimum": 1},
        },
        "required": ["path"],
    }


def _code_search_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "query": {"type": "string", "minLength": 2, "maxLength": 200},
            "path_prefix": {"type": "string", "default": "app"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 50},
            "case_sensitive": {"type": "boolean", "default": False},
        },
        "required": ["query"],
    }


def _supabase_read_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "table": {"type": "string", "pattern": "^[A-Za-z_][A-Za-z0-9_]*$"},
            "columns": {
                "type": "array",
                "minItems": 1,
                "maxItems": 30,
                "items": {"type": "string", "pattern": "^[A-Za-z_][A-Za-z0-9_]*$"},
            },
            "filters": {
                "type": "array",
                "maxItems": 12,
                "items": {
                    "type": "object",
                    "properties": {
                        "field": {"type": "string"},
                        "op": {
                            "type": "string",
                            "enum": [
                                "eq",
                                "neq",
                                "gt",
                                "gte",
                                "lt",
                                "lte",
                                "like",
                                "ilike",
                                "in",
                                "is",
                            ],
                        },
                        "value": {},
                    },
                    "required": ["field", "op", "value"],
                },
            },
            "order_by": {"type": "string"},
            "ascending": {"type": "boolean", "default": False},
            "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 25},
        },
        "required": ["table", "columns", "order_by"],
    }


def _log_search_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "source": {
                "type": "string",
                "enum": ["cloud-logging", "agents-timeline"],
                "default": "cloud-logging",
            },
            "start_time": {"type": "string", "format": "date-time"},
            "end_time": {"type": "string", "format": "date-time"},
            "service": {"type": ["string", "null"]},
            "severity": {"type": "string", "default": "INFO"},
            "identifiers": {"type": "object", "maxProperties": 6},
            "text_query": {"type": ["string", "null"], "maxLength": 160},
            "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 50},
        },
        "required": ["start_time", "end_time"],
    }


def specs() -> list[CommandSpec]:
    common = {
        "risk_level": "read",
        "execution": "direct",
        "output_schema": _direct_output_schema("Bounded, redacted staff operations result."),
        "required_roles": ("staff",),
        "stability": "preview",
    }
    return [
        CommandSpec(
            domain=Domain.STAFF_OPS,
            shortcut="+code-read",
            summary="Read a bounded line range from code packaged in the deployed API image.",
            adapter_tool_name="staff_code_read",
            input_schema=_code_read_schema(),
            examples=[
                "museoncli staff-ops +code-read --path app/main.py --start-line 1 --end-line 120"
            ],
            add_arguments=_add_code_read_arguments,
            build_arguments=_build_code_read_arguments,
            **common,  # type: ignore[arg-type]
        ),
        CommandSpec(
            domain=Domain.STAFF_OPS,
            shortcut="+code-search",
            summary="Search deployed API source code with bounded results.",
            adapter_tool_name="staff_code_search",
            input_schema=_code_search_schema(),
            examples=["museoncli staff-ops +code-search --query trace_id --path-prefix app"],
            add_arguments=_add_code_search_arguments,
            build_arguments=_build_code_search_arguments,
            **common,  # type: ignore[arg-type]
        ),
        CommandSpec(
            domain=Domain.STAFF_OPS,
            shortcut="+supabase-read",
            summary="Run a structured, bounded, read-only Supabase table query.",
            adapter_tool_name="staff_supabase_read",
            input_schema=_supabase_read_schema(),
            examples=[
                'museoncli staff-ops +supabase-read --table agent_jobs --column id --column status --order-by created_at --filters-json \'[{"field":"status","op":"eq","value":"failed"}]\''
            ],
            add_arguments=_add_supabase_read_arguments,
            build_arguments=_build_supabase_read_arguments,
            **common,  # type: ignore[arg-type]
        ),
        CommandSpec(
            domain=Domain.STAFF_OPS,
            shortcut="+log-search",
            summary="Search Cloud Logging or the Agents per-turn timeline in a bounded window.",
            adapter_tool_name="staff_log_search",
            input_schema=_log_search_schema(),
            examples=[
                'museoncli staff-ops +log-search --start-time 2026-09-20T00:00:00Z --end-time 2026-09-20T01:00:00Z --service museon-api-prod --identifiers-json \'{"trace_id":"TRACE_ID"}\''
            ],
            add_arguments=_add_log_search_arguments,
            build_arguments=_build_log_search_arguments,
            **common,  # type: ignore[arg-type]
        ),
    ]


EXECUTORS = {
    "staff-ops.code-read": adapter_executor(),
    "staff-ops.code-search": adapter_executor(),
    "staff-ops.supabase-read": adapter_executor(),
    "staff-ops.log-search": adapter_executor(),
}
