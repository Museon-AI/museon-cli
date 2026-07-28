"""Agentic Creative Campaign commands backed by the public v2 API."""

from __future__ import annotations

import argparse
from typing import Any

from museoncli.domains._model import CommandSpec, Domain
from museoncli.domains._shared import _direct_output_schema
from museoncli.execution import (
    CommandContext,
    compact_params,
    read_json_option,
    redacted_direct_enveloped,
)


def _csv(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in str(value).split(",") if item.strip()]


def _uuid_property(description: str) -> dict[str, Any]:
    return {
        "type": "string",
        "format": "uuid",
        "description": description,
        "examples": ["33333333-3333-4333-8333-333333333333"],
    }


def _add_list_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--search", default=None)
    parser.add_argument(
        "--status",
        choices=["setting-up", "setup-ready", "active", "paused", "archived"],
        default=None,
    )
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--page-size", type=int, default=20)


def _build_list_arguments(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "search": args.search,
        "status": args.status.replace("-", "_") if args.status else None,
        "page": args.page,
        "page_size": args.page_size,
    }


def _add_campaign_id_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--id", dest="campaign_id", required=True)


def _build_campaign_id_arguments(args: argparse.Namespace) -> dict[str, Any]:
    return {"campaign_id": args.campaign_id}


def _add_plan_id_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--plan-id", required=True)


def _build_plan_id_arguments(args: argparse.Namespace) -> dict[str, Any]:
    return {"plan_id": args.plan_id}


def _add_set_persona_arguments(parser: argparse.ArgumentParser) -> None:
    _add_plan_id_arguments(parser)
    parser.add_argument("--persona-id", required=True)
    parser.add_argument("--dry-run", action="store_true")


def _build_set_persona_arguments(args: argparse.Namespace) -> dict[str, Any]:
    return {"plan_id": args.plan_id, "persona_id": args.persona_id}


def _add_candidate_arguments(
    parser: argparse.ArgumentParser,
    *,
    submit: bool,
) -> None:
    _add_plan_id_arguments(parser)
    if not submit:
        parser.add_argument("--candidate-id", required=True)
    if submit:
        parser.add_argument("--name", required=True)
    parser.add_argument("--persona-payload-json", required=True)
    parser.add_argument("--elements-json", required=True)
    if not submit:
        parser.add_argument("--note", default=None)
    parser.add_argument("--dry-run", action="store_true")


def _candidate_json(value: str, *, field: str, expected_type: type) -> Any:
    parsed = read_json_option(value=value, file_path=None, field=field)
    if not isinstance(parsed, expected_type):
        expected_name = "object" if expected_type is dict else "array"
        raise ValueError(f"{field} must be a JSON {expected_name}")
    return parsed


def _build_candidate_arguments(args: argparse.Namespace, *, submit: bool) -> dict[str, Any]:
    payload = {
        "plan_id": args.plan_id,
        "persona_payload": _candidate_json(
            args.persona_payload_json,
            field="persona-payload",
            expected_type=dict,
        ),
        "elements": _candidate_json(
            args.elements_json,
            field="elements",
            expected_type=list,
        ),
        "dry_run": args.dry_run,
    }
    if submit:
        payload["name"] = args.name
    else:
        payload["candidate_id"] = args.candidate_id
        payload["note"] = args.note
    return payload


def _add_candidate_submit_arguments(parser: argparse.ArgumentParser) -> None:
    _add_candidate_arguments(parser, submit=True)


def _build_candidate_submit_arguments(args: argparse.Namespace) -> dict[str, Any]:
    return _build_candidate_arguments(args, submit=True)


def _add_candidate_revise_arguments(parser: argparse.ArgumentParser) -> None:
    _add_candidate_arguments(parser, submit=False)


def _build_candidate_revise_arguments(args: argparse.Namespace) -> dict[str, Any]:
    return _build_candidate_arguments(args, submit=False)


def _add_plan_revise_arguments(parser: argparse.ArgumentParser) -> None:
    _add_plan_id_arguments(parser)
    parser.add_argument("--add-elements-json")
    parser.add_argument("--retire-element-ids")
    parser.add_argument("--boost-elements-json")
    parser.add_argument("--note", default=None)


def _revision_json_list(value: str | None, *, field: str) -> list[Any]:
    if value is None:
        return []
    return _candidate_json(value, field=field, expected_type=list)


def _revision_changes(
    *,
    add_elements: Any,
    retire_element_ids: Any,
    boost_elements: Any,
) -> dict[str, list[Any]]:
    changes = {
        "add_elements": list(add_elements or []),
        "retire_element_ids": _csv(retire_element_ids),
        "boost_elements": list(boost_elements or []),
    }
    if not any(changes.values()):
        raise ValueError(
            "agentic-campaign +plan-revise requires at least one of "
            "--add-elements-json, --retire-element-ids, or --boost-elements-json."
        )
    return changes


def _build_plan_revise_arguments(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "plan_id": args.plan_id,
        "changes": _revision_changes(
            add_elements=_revision_json_list(
                args.add_elements_json,
                field="add-elements",
            ),
            retire_element_ids=args.retire_element_ids,
            boost_elements=_revision_json_list(
                args.boost_elements_json,
                field="boost-elements",
            ),
        ),
        "note": args.note,
    }


def _add_campaign_rename_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--name", required=True)


def _build_campaign_rename_arguments(args: argparse.Namespace) -> dict[str, Any]:
    return {"campaign_id": args.campaign_id, "name": args.name}


def _add_plan_submit_arguments(parser: argparse.ArgumentParser) -> None:
    _add_plan_id_arguments(parser)
    parser.add_argument("--format-ids", required=True, help="Comma-separated format ids.")
    parser.add_argument("--topic-ids", default=None, help="Comma-separated topic ids.")
    parser.add_argument("--required-hashtags", default=None, help="Comma-separated hashtags.")
    parser.add_argument("--note", default=None)
    parser.add_argument(
        "--dry-run",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Preview by default; pass --no-dry-run to apply.",
    )


def _build_plan_submit_arguments(args: argparse.Namespace) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "plan_id": args.plan_id,
        "format_ids": _csv(args.format_ids),
        "topic_ids": _csv(args.topic_ids),
        "note": args.note,
        "dry_run": args.dry_run,
    }
    if args.required_hashtags is not None:
        payload["required_hashtags"] = _csv(args.required_hashtags)
    return payload


def _add_elements_replace_arguments(parser: argparse.ArgumentParser) -> None:
    _add_plan_id_arguments(parser)
    for action in ("add", "resume", "pause"):
        parser.add_argument(f"--{action}-format-ids", default=None)
        parser.add_argument(f"--{action}-topic-ids", default=None)
    parser.add_argument("--note", default=None)
    parser.add_argument(
        "--dry-run",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Preview by default; pass --no-dry-run to apply.",
    )


def _build_elements_replace_arguments(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "plan_id": args.plan_id,
        **{
            f"{action}_{kind}_ids": _csv(getattr(args, f"{action}_{kind}_ids"))
            for action in ("add", "resume", "pause")
            for kind in ("format", "topic")
        },
        "note": args.note,
        "dry_run": args.dry_run,
    }


def _add_strategy_decide_arguments(parser: argparse.ArgumentParser) -> None:
    _add_plan_id_arguments(parser)
    parser.add_argument(
        "--run-scope",
        choices=["latest-awaiting-review"],
        default="latest-awaiting-review",
    )
    parser.add_argument("--decided-by", choices=["human", "auto-timeout"], default="human")
    parser.add_argument("--decision", default=None, help="Optional JSON object.")
    parser.add_argument(
        "--dry-run",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Preview by default; pass --no-dry-run to apply.",
    )


def _build_strategy_decide_arguments(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "plan_id": args.plan_id,
        "run_scope": args.run_scope.replace("-", "_"),
        "decided_by": args.decided_by.replace("-", "_"),
        "decision": args.decision,
        "dry_run": args.dry_run,
    }


def _add_issues_pull_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--limit", type=int, required=True)
    parser.add_argument("--dry-run", action="store_true")


def _build_issues_pull_arguments(args: argparse.Namespace) -> dict[str, Any]:
    return {"campaign_id": args.campaign_id, "limit": args.limit}


def _schema(
    properties: dict[str, Any],
    *,
    required: list[str] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        result["required"] = required
    return result


def _plan_schema(extra: dict[str, Any] | None = None, required: list[str] | None = None):
    return _schema(
        {"plan_id": _uuid_property("Agentic Persona Plan id"), **(extra or {})},
        required=["plan_id", *(required or [])],
    )


def _persona_payload_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "name": {"type": "string", "minLength": 1, "maxLength": 200},
            "description": {"type": "string", "minLength": 1, "maxLength": 4000},
            "visual_prompt": {"type": "string", "minLength": 1, "maxLength": 10000},
            "reference_media_ids": {
                "type": "array",
                "items": _uuid_property("Reference media id"),
                "default": [],
            },
            "avatar_style": {"type": ["string", "null"], "maxLength": 2000},
            "bio_template": {"type": ["string", "null"], "maxLength": 2000},
            "required_hashtags": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 100,
                "default": [],
            },
            "required_mentions": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 100,
                "default": [],
            },
        },
        "required": ["name", "description", "visual_prompt"],
    }


def _candidate_elements_schema() -> dict[str, Any]:
    return {
        "type": "array",
        "minItems": 1,
        "maxItems": 100,
        "items": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "format_id": _uuid_property("Format id"),
                "topic_id": _uuid_property("Content topic id"),
                "cta_target_id": {
                    "type": ["string", "null"],
                    "format": "uuid",
                    "description": "Optional CTA target id",
                    "examples": ["66666666-6666-4666-8666-666666666666"],
                },
            },
            "required": ["format_id", "topic_id"],
        },
    }


def _revision_boosts_schema() -> dict[str, Any]:
    return {
        "type": "array",
        "maxItems": 100,
        "items": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "element_id": _uuid_property("Experiment direction id"),
                "account_count": {"type": "integer", "minimum": 1},
                "days": {"type": "integer", "minimum": 1, "maximum": 14},
            },
            "required": ["element_id", "account_count", "days"],
        },
    }


def _revision_add_elements_schema() -> dict[str, Any]:
    schema = _candidate_elements_schema()
    schema.pop("minItems")
    return schema


def specs() -> list[CommandSpec]:
    domain = Domain.AGENTIC_CAMPAIGN
    return [
        CommandSpec(
            domain=domain,
            shortcut="+candidate-submit",
            summary="Submit one Persona Plan candidate and its first version.",
            risk_level="write",
            execution="direct",
            adapter_tool_name="agentic_campaign_candidate_submit",
            input_schema=_plan_schema(
                {
                    "name": {"type": "string", "minLength": 1, "maxLength": 200},
                    "persona_payload": _persona_payload_schema(),
                    "elements": _candidate_elements_schema(),
                    "dry_run": {"type": "boolean", "default": False},
                },
                required=["name", "persona_payload", "elements"],
            ),
            output_schema=_direct_output_schema(
                "Created candidate, first version, elements, and generation task ids."
            ),
            examples=[
                "museoncli agentic-campaign +candidate-submit "
                "--plan-id 33333333-3333-4333-8333-333333333333 "
                "--name 'DIY problem solver' "
                """--persona-payload-json '{"name":"Mia","description":"Practical maker","""
                """"visual_prompt":"Warm workshop portrait","reference_media_ids":[]}' """
                """--elements-json '[{"format_id":"44444444-4444-4444-8444-444444444444","""
                """"topic_id":"55555555-5555-4555-8555-555555555555"}]'"""
            ],
            add_arguments=_add_candidate_submit_arguments,
            build_arguments=_build_candidate_submit_arguments,
            supports_dry_run=True,
        ),
        CommandSpec(
            domain=domain,
            shortcut="+candidate-revise",
            summary="Submit a new version to a Persona Plan candidate's current head.",
            risk_level="write",
            execution="direct",
            adapter_tool_name="agentic_campaign_candidate_revise",
            input_schema=_plan_schema(
                {
                    "candidate_id": _uuid_property("Persona Plan candidate id"),
                    "persona_payload": _persona_payload_schema(),
                    "elements": _candidate_elements_schema(),
                    "note": {"type": ["string", "null"], "maxLength": 2000},
                    "dry_run": {"type": "boolean", "default": False},
                },
                required=["candidate_id", "persona_payload", "elements"],
            ),
            output_schema=_direct_output_schema(
                "Candidate, new head version, elements, and generation task ids."
            ),
            examples=[
                "museoncli agentic-campaign +candidate-revise "
                "--plan-id 33333333-3333-4333-8333-333333333333 "
                "--candidate-id 77777777-7777-4777-8777-777777777777 "
                """--persona-payload-json '{"name":"Mia","description":"Practical maker","""
                """"visual_prompt":"Bright workshop portrait","reference_media_ids":[]}' """
                """--elements-json '[{"format_id":"44444444-4444-4444-8444-444444444444","""
                """"topic_id":"55555555-5555-4555-8555-555555555555","""
                """"cta_target_id":"66666666-6666-4666-8666-666666666666"}]' """
                "--note 'Tighten the visual direction'"
            ],
            add_arguments=_add_candidate_revise_arguments,
            build_arguments=_build_candidate_revise_arguments,
            supports_dry_run=True,
        ),
        CommandSpec(
            domain=domain,
            shortcut="+plan-revise",
            summary="Create an adjustment proposal for operator review.",
            risk_level="write",
            execution="direct",
            adapter_tool_name="agentic_campaign_plan_revise",
            input_schema=_plan_schema(
                {
                    "changes": {
                        "type": "object",
                        "additionalProperties": False,
                        "anyOf": [
                            {
                                "properties": {
                                    "add_elements": {"minItems": 1},
                                }
                            },
                            {
                                "properties": {
                                    "retire_element_ids": {"minItems": 1},
                                }
                            },
                            {
                                "properties": {
                                    "boost_elements": {"minItems": 1},
                                }
                            },
                        ],
                        "properties": {
                            "add_elements": _revision_add_elements_schema(),
                            "retire_element_ids": {
                                "type": "array",
                                "maxItems": 100,
                                "items": _uuid_property("Experiment direction id"),
                            },
                            "boost_elements": _revision_boosts_schema(),
                        },
                        "required": [
                            "add_elements",
                            "retire_element_ids",
                            "boost_elements",
                        ],
                    },
                    "note": {"type": ["string", "null"], "maxLength": 2000},
                },
                required=["changes"],
            ),
            output_schema=_direct_output_schema(
                "Adjustment proposal id, change summary, and operator review reminder."
            ),
            examples=[
                "museoncli agentic-campaign +plan-revise "
                "--plan-id 33333333-3333-4333-8333-333333333333 "
                """--add-elements-json '[{"format_id":"44444444-4444-4444-8444-444444444444","""
                """"topic_id":"55555555-5555-4555-8555-555555555555"}]' """
                """--boost-elements-json '[{"element_id":"66666666-6666-4666-8666-666666666666","""
                """"account_count":3,"days":7}]' --note 'Expand the proven direction'"""
            ],
            add_arguments=_add_plan_revise_arguments,
            build_arguments=_build_plan_revise_arguments,
        ),
        CommandSpec(
            domain=domain,
            shortcut="+campaign-rename",
            summary="Rename an Agentic Creative Campaign.",
            risk_level="write",
            execution="direct",
            adapter_tool_name="agentic_campaign_campaign_rename",
            input_schema=_schema(
                {
                    "campaign_id": _uuid_property("Agentic Creative Campaign id"),
                    "name": {"type": "string", "minLength": 1, "maxLength": 160},
                },
                required=["campaign_id", "name"],
            ),
            output_schema=_direct_output_schema("Renamed campaign detail."),
            examples=[
                "museoncli agentic-campaign +campaign-rename "
                "--campaign-id 22222222-2222-4222-8222-222222222222 "
                "--name 'Summer maker campaign'"
            ],
            add_arguments=_add_campaign_rename_arguments,
            build_arguments=_build_campaign_rename_arguments,
        ),
        CommandSpec(
            domain=domain,
            shortcut="+list",
            summary="List Agentic Creative Campaign summaries in the selected workspace.",
            risk_level="read",
            execution="direct",
            adapter_tool_name="agentic_campaign_list",
            input_schema=_schema(
                {
                    "search": {"type": ["string", "null"]},
                    "status": {"type": ["string", "null"]},
                    "page": {"type": "integer", "minimum": 1},
                    "page_size": {"type": "integer", "minimum": 1, "maximum": 100},
                }
            ),
            output_schema=_direct_output_schema("Campaign summaries and pagination metadata."),
            examples=["museoncli agentic-campaign +list --page 1 --page-size 20"],
            add_arguments=_add_list_arguments,
            build_arguments=_build_list_arguments,
        ),
        CommandSpec(
            domain=domain,
            shortcut="+get",
            summary="Get an Agentic Creative Campaign detail by campaign id.",
            risk_level="read",
            execution="direct",
            adapter_tool_name="agentic_campaign_get",
            input_schema=_schema(
                {"campaign_id": _uuid_property("Agentic Creative Campaign id")},
                required=["campaign_id"],
            ),
            output_schema=_direct_output_schema("Campaign detail."),
            examples=["museoncli agentic-campaign +get --id 22222222-2222-4222-8222-222222222222"],
            add_arguments=_add_campaign_id_arguments,
            build_arguments=_build_campaign_id_arguments,
        ),
        CommandSpec(
            domain=domain,
            shortcut="+plan-list",
            summary=(
                "List Persona Plans for one campaign with member pool account ids and handles; "
                "account operation ids are omitted."
            ),
            risk_level="read",
            execution="direct",
            adapter_tool_name="agentic_campaign_plan_list",
            input_schema=_schema(
                {"campaign_id": _uuid_property("Agentic Creative Campaign id")},
                required=["campaign_id"],
            ),
            output_schema=_direct_output_schema("Persona Plans with display-safe member accounts."),
            examples=[
                "museoncli agentic-campaign +plan-list --id 22222222-2222-4222-8222-222222222222"
            ],
            add_arguments=_add_campaign_id_arguments,
            build_arguments=_build_campaign_id_arguments,
        ),
        CommandSpec(
            domain=domain,
            shortcut="+plan-get",
            summary=(
                "Get a Persona Plan by plan id with member pool account ids and handles; "
                "account operation ids are omitted."
            ),
            risk_level="read",
            execution="direct",
            adapter_tool_name="agentic_campaign_plan_get",
            input_schema=_plan_schema(),
            output_schema=_direct_output_schema("Persona Plan and display-safe member accounts."),
            examples=[
                "museoncli agentic-campaign +plan-get "
                "--plan-id 33333333-3333-4333-8333-333333333333"
            ],
            add_arguments=_add_plan_id_arguments,
            build_arguments=_build_plan_id_arguments,
        ),
        CommandSpec(
            domain=domain,
            shortcut="+plan-set-persona",
            summary="Set a Persona Plan's persona, using its current version for concurrency control.",
            risk_level="write",
            execution="direct",
            adapter_tool_name="agentic_campaign_plan_set_persona",
            input_schema=_plan_schema(
                {"persona_id": _uuid_property("Persona id")}, required=["persona_id"]
            ),
            output_schema=_direct_output_schema("Updated campaign detail."),
            examples=[
                "museoncli agentic-campaign +plan-set-persona "
                "--plan-id 33333333-3333-4333-8333-333333333333 "
                "--persona-id 44444444-4444-4444-8444-444444444444"
            ],
            add_arguments=_add_set_persona_arguments,
            build_arguments=_build_set_persona_arguments,
            supports_dry_run=True,
        ),
        CommandSpec(
            domain=domain,
            shortcut="+plan-submit",
            summary="Fan out an onboarding/reset plan to every account in a Persona Plan.",
            risk_level="write",
            execution="direct",
            adapter_tool_name="agentic_campaign_plan_submit",
            input_schema=_plan_schema(
                {
                    "format_ids": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                    "topic_ids": {"type": "array", "items": {"type": "string"}},
                    "required_hashtags": {
                        "type": ["array", "null"],
                        "items": {"type": "string"},
                        "maxItems": 50,
                    },
                    "note": {"type": ["string", "null"]},
                    "dry_run": {"type": "boolean", "default": True},
                },
                required=["format_ids"],
            ),
            output_schema=_direct_output_schema(
                "Per-account result with pool_account_id and handle; operation ids are omitted."
            ),
            examples=[
                "museoncli agentic-campaign +plan-submit "
                "--plan-id 33333333-3333-4333-8333-333333333333 "
                "--format-ids 44444444-4444-4444-8444-444444444444,"
                "55555555-5555-4555-8555-555555555555 --no-dry-run"
            ],
            add_arguments=_add_plan_submit_arguments,
            build_arguments=_build_plan_submit_arguments,
            supports_dry_run=True,
        ),
        CommandSpec(
            domain=domain,
            shortcut="+plan-elements-replace",
            summary=(
                "Fan out add/resume/pause format and topic changes to a Persona Plan's accounts."
            ),
            risk_level="write",
            execution="direct",
            adapter_tool_name="agentic_campaign_plan_elements_replace",
            input_schema=_plan_schema(
                {
                    **{
                        f"{action}_{kind}_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                        }
                        for action in ("add", "resume", "pause")
                        for kind in ("format", "topic")
                    },
                    "note": {"type": ["string", "null"]},
                    "dry_run": {"type": "boolean", "default": True},
                }
            ),
            output_schema=_direct_output_schema(
                "Per-account result with pool_account_id and handle; operation ids are omitted."
            ),
            examples=[
                "museoncli agentic-campaign +plan-elements-replace "
                "--plan-id 33333333-3333-4333-8333-333333333333 "
                "--add-format-ids 44444444-4444-4444-8444-444444444444 "
                "--pause-topic-ids 55555555-5555-4555-8555-555555555555 --no-dry-run"
            ],
            add_arguments=_add_elements_replace_arguments,
            build_arguments=_build_elements_replace_arguments,
            supports_dry_run=True,
        ),
        CommandSpec(
            domain=domain,
            shortcut="+plan-strategy-decide",
            summary="Fan out a strategy decision to the latest awaiting-review run in a Persona Plan.",
            risk_level="write",
            execution="direct",
            adapter_tool_name="agentic_campaign_plan_strategy_decide",
            input_schema=_plan_schema(
                {
                    "run_scope": {
                        "type": "string",
                        "enum": ["latest-awaiting-review"],
                        "default": "latest-awaiting-review",
                    },
                    "decided_by": {
                        "type": "string",
                        "enum": ["human", "auto-timeout"],
                        "default": "human",
                    },
                    "decision": {"type": ["object", "null"]},
                    "dry_run": {"type": "boolean", "default": True},
                }
            ),
            output_schema=_direct_output_schema(
                "Per-account result with pool_account_id and handle; operation ids are omitted."
            ),
            examples=[
                "museoncli agentic-campaign +plan-strategy-decide "
                "--plan-id 33333333-3333-4333-8333-333333333333 "
                "--run-scope latest-awaiting-review --no-dry-run"
            ],
            add_arguments=_add_strategy_decide_arguments,
            build_arguments=_build_strategy_decide_arguments,
            supports_dry_run=True,
        ),
        CommandSpec(
            domain=domain,
            shortcut="+plan-tags",
            summary="Aggregate element tags across a Persona Plan, omitting account operation ids.",
            risk_level="read",
            execution="direct",
            adapter_tool_name="agentic_campaign_plan_tags",
            input_schema=_plan_schema(),
            output_schema=_direct_output_schema("Plan tag rows with pool_account_id and handle."),
            examples=[
                "museoncli agentic-campaign +plan-tags "
                "--plan-id 33333333-3333-4333-8333-333333333333"
            ],
            add_arguments=_add_plan_id_arguments,
            build_arguments=_build_plan_id_arguments,
        ),
        CommandSpec(
            domain=domain,
            shortcut="+plan-attribution",
            summary="Aggregate attribution across a Persona Plan, omitting account operation ids.",
            risk_level="read",
            execution="direct",
            adapter_tool_name="agentic_campaign_plan_attribution",
            input_schema=_plan_schema(),
            output_schema=_direct_output_schema(
                "Plan attribution rows with pool_account_id and handle."
            ),
            examples=[
                "museoncli agentic-campaign +plan-attribution "
                "--plan-id 33333333-3333-4333-8333-333333333333"
            ],
            add_arguments=_add_plan_id_arguments,
            build_arguments=_build_plan_id_arguments,
        ),
        CommandSpec(
            domain=domain,
            shortcut="+issues-pull",
            summary=(
                "Pull and lease Account Operation Issues from one required Agentic Creative "
                "Campaign. The campaign selects candidates; the runtime conversation identity is "
                "used only for lease and message context. Claims omit account_operation_id."
            ),
            risk_level="write",
            execution="direct",
            adapter_tool_name="agentic_campaign_issues_pull",
            input_schema=_schema(
                {
                    "campaign_id": {
                        "type": "string",
                        "format": "uuid",
                    },
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                },
                required=["campaign_id", "limit"],
            ),
            output_schema=_direct_output_schema(
                "Leased Issue claims with pool_account_id and handle; operation ids are omitted."
            ),
            examples=[
                "museoncli agentic-campaign +issues-pull "
                "--campaign-id 22222222-2222-4222-8222-222222222222 --limit 20"
            ],
            add_arguments=_add_issues_pull_arguments,
            build_arguments=_build_issues_pull_arguments,
            supports_dry_run=True,
        ),
    ]


async def _list(ctx: CommandContext, *, page: int, page_size: int) -> Any:
    return await ctx.api_data_v2(
        ctx.cfg,
        "GET",
        "/agentic-creative-campaigns",
        params=compact_params(
            {
                "workspace_id": ctx.workspace_id,
                "search": ctx.arguments.get("search"),
                "status": ctx.arguments.get("status"),
                "page": page,
                "page_size": page_size,
            }
        ),
    )


async def _detail(ctx: CommandContext, campaign_id: str) -> Any:
    return await ctx.api_data_v2(
        ctx.cfg,
        "GET",
        f"/agentic-creative-campaigns/{campaign_id}",
        params={"workspace_id": ctx.workspace_id},
    )


def _payload_data(response: Any) -> Any:
    if isinstance(response, dict) and set(response) >= {"data"}:
        return response["data"]
    return response


def _plan_members(detail: dict[str, Any], plan_id: str) -> list[dict[str, Any]]:
    members: list[dict[str, Any]] = []
    for unit in detail.get("op_units") or []:
        if not isinstance(unit, dict) or unit.get("agentic_persona_plan_id") != plan_id:
            continue
        account = unit.get("account") if isinstance(unit.get("account"), dict) else {}
        members.append(
            {
                "pool_account_id": unit.get("pool_account_id"),
                "handle": account.get("username"),
            }
        )
    return members


def _plans_with_members(detail: dict[str, Any]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for plan in detail.get("agentic_persona_plans") or []:
        if isinstance(plan, dict):
            results.append({**plan, "accounts": _plan_members(detail, str(plan.get("id") or ""))})
    return results


async def _locate_plan(ctx: CommandContext) -> tuple[str, dict[str, Any], dict[str, Any]]:
    plan_id = str(ctx.arguments.get("plan_id") or "")
    page = 1
    total_pages: int | None = None
    scanned_pages = 0
    while total_pages is None or page <= total_pages:
        response = await _list(ctx, page=page, page_size=100)
        scanned_pages += 1
        payload = _payload_data(response)
        if not isinstance(payload, dict):
            break
        items = payload.get("items") or []
        meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
        if total_pages is None:
            total = max(0, int(meta.get("total") or 0))
            total_pages = max(1, (total + 99) // 100)
        for campaign in items:
            if not isinstance(campaign, dict):
                continue
            campaign_id = str(campaign.get("id") or "")
            detail_response = await _detail(ctx, campaign_id)
            detail = _payload_data(detail_response)
            if not isinstance(detail, dict):
                continue
            for plan in detail.get("agentic_persona_plans") or []:
                if isinstance(plan, dict) and str(plan.get("id") or "") == plan_id:
                    return campaign_id, plan, detail
        page += 1
    raise RuntimeError(
        "agentic persona plan not found in selected workspace: "
        f"{plan_id} (scanned {scanned_pages} pages)"
    )


async def _execute_list(ctx: CommandContext) -> Any:
    return await _list(
        ctx,
        page=int(ctx.arguments.get("page") or 1),
        page_size=int(ctx.arguments.get("page_size") or 20),
    )


async def _execute_get(ctx: CommandContext) -> Any:
    return await _detail(ctx, str(ctx.arguments.get("campaign_id") or ""))


async def _execute_plan_list(ctx: CommandContext) -> Any:
    detail = _payload_data(await _detail(ctx, str(ctx.arguments.get("campaign_id") or "")))
    if not isinstance(detail, dict):
        return detail
    return {"plans": _plans_with_members(detail)}


async def _execute_plan_get(ctx: CommandContext) -> Any:
    _, plan, detail = await _locate_plan(ctx)
    return {**plan, "accounts": _plan_members(detail, str(plan.get("id") or ""))}


async def _execute_plan_set_persona(ctx: CommandContext) -> Any:
    campaign_id, plan, _ = await _locate_plan(ctx)
    return await ctx.api_data_v2(
        ctx.cfg,
        "POST",
        f"/agentic-creative-campaigns/{campaign_id}/persona-plans/{plan['id']}:set-persona",
        json_body={
            "workspace_id": ctx.workspace_id,
            "expected_version": plan.get("version"),
            "persona_id": ctx.arguments.get("persona_id"),
        },
    )


async def _execute_candidate_submit(ctx: CommandContext) -> Any:
    campaign_id, plan, _ = await _locate_plan(ctx)
    return await ctx.api_data_v2(
        ctx.cfg,
        "POST",
        (f"/agentic-creative-campaigns/{campaign_id}/persona-plans/{plan['id']}/candidates:submit"),
        json_body={
            "workspace_id": ctx.workspace_id,
            "name": ctx.arguments.get("name"),
            "persona_payload": ctx.arguments.get("persona_payload"),
            "elements": ctx.arguments.get("elements"),
        },
    )


async def _execute_candidate_revise(ctx: CommandContext) -> Any:
    campaign_id, plan, _ = await _locate_plan(ctx)
    candidate_id = ctx.arguments.get("candidate_id")
    return await ctx.api_data_v2(
        ctx.cfg,
        "POST",
        (
            f"/agentic-creative-campaigns/{campaign_id}/persona-plans/{plan['id']}/"
            f"candidates/{candidate_id}:revise"
        ),
        json_body={
            "workspace_id": ctx.workspace_id,
            "persona_payload": ctx.arguments.get("persona_payload"),
            "elements": ctx.arguments.get("elements"),
            "note": ctx.arguments.get("note"),
        },
    )


async def _execute_plan_revise(ctx: CommandContext) -> Any:
    campaign_id, plan, _ = await _locate_plan(ctx)
    raw_changes = ctx.arguments.get("changes")
    if not isinstance(raw_changes, dict):
        raw_changes = {}
    changes = _revision_changes(
        add_elements=raw_changes.get("add_elements"),
        retire_element_ids=raw_changes.get("retire_element_ids"),
        boost_elements=raw_changes.get("boost_elements"),
    )
    response = await ctx.api_data_v2(
        ctx.cfg,
        "POST",
        (
            f"/agentic-creative-campaigns/{campaign_id}/persona-plans/"
            f"{plan['id']}/revision-proposals"
        ),
        json_body={
            "workspace_id": ctx.workspace_id,
            "note": ctx.arguments.get("note"),
            "changes": changes,
        },
    )
    payload = _payload_data(response)
    proposal = payload.get("proposal") if isinstance(payload, dict) else {}
    proposal_id = proposal.get("id") if isinstance(proposal, dict) else None
    return {
        "proposal_id": proposal_id,
        "change_summary": {
            "new_directions": len(changes["add_elements"]),
            "directions_to_stop": len(changes["retire_element_ids"]),
            "winner_boosts": len(changes["boost_elements"]),
        },
        "next_step": "Please review the adjustment in Museon and confirm it there.",
    }


async def _execute_campaign_rename(ctx: CommandContext) -> Any:
    campaign_id = str(ctx.arguments.get("campaign_id") or "")
    detail = _payload_data(await _detail(ctx, campaign_id))
    campaign = detail.get("campaign") if isinstance(detail, dict) else None
    if not isinstance(campaign, dict) or campaign.get("version") is None:
        raise RuntimeError("campaign detail did not include its current version")
    return await ctx.api_data_v2(
        ctx.cfg,
        "PATCH",
        f"/agentic-creative-campaigns/{campaign_id}",
        json_body={
            "workspace_id": ctx.workspace_id,
            "expected_version": campaign["version"],
            "name": ctx.arguments.get("name"),
        },
    )


async def _plan_post(ctx: CommandContext, action: str, payload: dict[str, Any]) -> Any:
    campaign_id, plan, _ = await _locate_plan(ctx)
    return await ctx.api_data_v2(
        ctx.cfg,
        "POST",
        f"/agentic-creative-campaigns/{campaign_id}/persona-plans/{plan['id']}:{action}",
        json_body={"workspace_id": ctx.workspace_id, **payload},
    )


async def _execute_plan_submit(ctx: CommandContext) -> Any:
    payload = {
        "dry_run": bool(ctx.arguments.get("dry_run", True)),
        "format_ids": _csv(ctx.arguments.get("format_ids")),
        "topic_ids": _csv(ctx.arguments.get("topic_ids")),
        "note": ctx.arguments.get("note"),
    }
    if "required_hashtags" in ctx.arguments:
        payload["required_hashtags"] = _csv(ctx.arguments.get("required_hashtags"))
    return await _plan_post(ctx, "plan-submit", payload)


async def _execute_elements_replace(ctx: CommandContext) -> Any:
    payload = {
        "dry_run": bool(ctx.arguments.get("dry_run", True)),
        **{
            f"{action}_{kind}_ids": _csv(ctx.arguments.get(f"{action}_{kind}_ids"))
            for action in ("add", "resume", "pause")
            for kind in ("format", "topic")
        },
        "note": ctx.arguments.get("note"),
    }
    return await _plan_post(ctx, "elements-replace", payload)


async def _execute_strategy_decide(ctx: CommandContext) -> Any:
    decision = (
        read_json_option(
            value=ctx.arguments.get("decision"),
            file_path=None,
            field="decision",
        )
        if ctx.arguments.get("decision")
        else None
    )
    if decision is not None and not isinstance(decision, dict):
        raise RuntimeError("decision must be a JSON object")
    return await _plan_post(
        ctx,
        "strategy-decide",
        compact_params(
            {
                "dry_run": bool(ctx.arguments.get("dry_run", True)),
                "run_scope": ctx.arguments.get("run_scope", "latest_awaiting_review"),
                "decided_by": ctx.arguments.get("decided_by", "human"),
                "decision": decision,
            }
        ),
    )


async def _plan_get_route(ctx: CommandContext, suffix: str, params: dict[str, Any]) -> Any:
    campaign_id, plan, _ = await _locate_plan(ctx)
    return await ctx.api_data_v2(
        ctx.cfg,
        "GET",
        f"/agentic-creative-campaigns/{campaign_id}/persona-plans/{plan['id']}/{suffix}",
        params={"workspace_id": ctx.workspace_id, **params},
    )


async def _execute_plan_tags(ctx: CommandContext) -> Any:
    return await _plan_get_route(ctx, "tags", {})


async def _execute_plan_attribution(ctx: CommandContext) -> Any:
    return await _plan_get_route(
        ctx,
        "attribution",
        {"limit_per_account": 20},
    )


async def _execute_issues_pull(ctx: CommandContext) -> Any:
    runtime = ctx.cfg.runtime_context if isinstance(ctx.cfg.runtime_context, dict) else {}
    session_id = runtime.get("conversation_id")
    if not session_id:
        raise RuntimeError("runtime context has no conversation identity")
    return await ctx.api_data_v2(
        ctx.cfg,
        "POST",
        "/account-operation-issues:pull-triage-batch",
        json_body=compact_params(
            {
                "workspace_id": ctx.workspace_id,
                "session_conversation_id": session_id,
                "scope_conversation_id": runtime.get("scope_conversation_id"),
                "campaign_id": ctx.arguments.get("campaign_id"),
                "limit": ctx.arguments.get("limit"),
            }
        ),
    )


EXECUTORS = {
    "agentic-campaign.campaign-rename": redacted_direct_enveloped(
        _execute_campaign_rename, redact_api_errors=True
    ),
    "agentic-campaign.candidate-revise": redacted_direct_enveloped(
        _execute_candidate_revise, redact_api_errors=True
    ),
    "agentic-campaign.candidate-submit": redacted_direct_enveloped(
        _execute_candidate_submit, redact_api_errors=True
    ),
    "agentic-campaign.get": redacted_direct_enveloped(_execute_get, redact_api_errors=True),
    "agentic-campaign.issues-pull": redacted_direct_enveloped(
        _execute_issues_pull, redact_api_errors=True
    ),
    "agentic-campaign.list": redacted_direct_enveloped(_execute_list, redact_api_errors=True),
    "agentic-campaign.plan-attribution": redacted_direct_enveloped(
        _execute_plan_attribution, redact_api_errors=True
    ),
    "agentic-campaign.plan-elements-replace": redacted_direct_enveloped(
        _execute_elements_replace, redact_api_errors=True
    ),
    "agentic-campaign.plan-get": redacted_direct_enveloped(
        _execute_plan_get, redact_api_errors=True
    ),
    "agentic-campaign.plan-list": redacted_direct_enveloped(
        _execute_plan_list, redact_api_errors=True
    ),
    "agentic-campaign.plan-revise": redacted_direct_enveloped(
        _execute_plan_revise, redact_api_errors=True
    ),
    "agentic-campaign.plan-set-persona": redacted_direct_enveloped(
        _execute_plan_set_persona, redact_api_errors=True
    ),
    "agentic-campaign.plan-strategy-decide": redacted_direct_enveloped(
        _execute_strategy_decide, redact_api_errors=True
    ),
    "agentic-campaign.plan-submit": redacted_direct_enveloped(
        _execute_plan_submit, redact_api_errors=True
    ),
    "agentic-campaign.plan-tags": redacted_direct_enveloped(
        _execute_plan_tags, redact_api_errors=True
    ),
}
