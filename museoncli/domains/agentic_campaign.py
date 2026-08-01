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


def _add_plan_propose_arguments(parser: argparse.ArgumentParser) -> None:
    _add_plan_id_arguments(parser)
    parser.add_argument("--proposal-id")
    parser.add_argument("--note")
    parser.add_argument("--name")
    parser.add_argument("--title")
    parser.add_argument("--persona-payload", dest="persona_payload")
    parser.add_argument("--persona-json", dest="persona_payload", help=argparse.SUPPRESS)
    parser.add_argument("--patch-persona-payload")
    parser.add_argument(
        "--persona-id",
        help=(
            "Reference an existing persona instead of inline --persona-json. The server "
            "snapshots the referenced persona's name, description, and visual reference "
            "into this proposal at submission time (copied, not bound -- later edits to "
            "the source persona do not affect this proposal; tags and marketing_profile "
            "are not copied). Mutually exclusive with --persona-json. Creating a proposal "
            "requires exactly one persona option; revising may omit both to preserve the "
            "proposal's current persona."
        ),
    )
    parser.add_argument("--elements-json")
    parser.add_argument("--add-elements-json")
    parser.add_argument("--retire-element-ids")
    parser.add_argument("--boost-elements-json")
    parser.add_argument("--dry-run", action="store_true")


def _add_proposal_get_arguments(parser: argparse.ArgumentParser) -> None:
    _add_plan_id_arguments(parser)
    parser.add_argument("--proposal-id", required=True)


def _build_proposal_get_arguments(args: argparse.Namespace) -> dict[str, Any]:
    return {"plan_id": args.plan_id, "proposal_id": args.proposal_id}


def _candidate_json(value: str, *, field: str, expected_type: type) -> Any:
    parsed = read_json_option(value=value, file_path=None, field=field)
    if not isinstance(parsed, expected_type):
        expected_name = "object" if expected_type is dict else "array"
        raise ValueError(f"{field} must be a JSON {expected_name}")
    return parsed


def _revision_json_list(value: str | None, *, field: str) -> list[Any]:
    if value is None:
        return []
    return _candidate_json(value, field=field, expected_type=list)


def _revision_changes(
    *,
    add_elements: Any,
    retire_element_ids: Any,
    boost_elements: Any,
    persona: dict[str, Any] | None = None,
    patch_persona_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    changes = {
        "add_elements": list(add_elements or []),
        "retire_element_ids": _csv(retire_element_ids),
        "boost_elements": list(boost_elements or []),
    }
    if persona is not None:
        changes["persona"] = persona
    if patch_persona_payload is not None:
        changes["patch_persona_payload"] = patch_persona_payload
    if not any(changes.values()):
        raise ValueError(
            "agentic-campaign +plan-propose requires at least one of "
            "--persona-payload, --patch-persona-payload, --add-elements-json, "
            "--retire-element-ids, or --boost-elements-json."
        )
    return changes


def _build_plan_propose_arguments(args: argparse.Namespace) -> dict[str, Any]:
    if args.proposal_id is not None:
        if args.name is not None:
            raise ValueError("--name is not valid when revising an adjustment proposal.")
        if args.title is not None:
            raise ValueError("--title is not valid when revising an adjustment proposal.")
        if args.patch_persona_payload is not None:
            raise ValueError(
                "--patch-persona-payload is not valid when revising an adjustment proposal; "
                "the server only accepts a full persona replacement here (--persona-json or "
                "--persona-id), never a partial patch."
            )
        if args.persona_payload is not None and args.persona_id is not None:
            raise ValueError(
                "--persona-json and --persona-id are mutually exclusive; provide exactly one."
            )
        if any(
            value is not None
            for value in (
                args.add_elements_json,
                args.retire_element_ids,
                args.boost_elements_json,
            )
        ):
            raise ValueError(
                "adjustment change options are not valid when revising an adjustment proposal."
            )
        if args.elements_json is None:
            raise ValueError("adjustment proposal revision requires --elements-json.")
        elements = _candidate_json(
            args.elements_json,
            field="elements",
            expected_type=list,
        )
        if not elements:
            raise ValueError("adjustment proposal revision requires at least one element.")
        persona_field: dict[str, Any] = {}
        if args.persona_id is not None:
            persona_field = {"persona_id": args.persona_id}
        elif args.persona_payload is not None:
            persona_field = {
                "persona_payload": _candidate_json(
                    args.persona_payload,
                    field="persona",
                    expected_type=dict,
                )
            }
        return compact_params(
            {
                "plan_id": args.plan_id,
                "proposal_id": args.proposal_id,
                "elements": elements,
                **persona_field,
                "note": args.note,
                "dry_run": args.dry_run,
            }
        )

    if args.persona_payload is not None and args.persona_id is not None:
        raise ValueError(
            "--persona-json and --persona-id are mutually exclusive; provide exactly one."
        )
    if args.persona_payload is not None and args.patch_persona_payload is not None:
        raise ValueError("--persona-payload and --patch-persona-payload are mutually exclusive.")
    complete_plan_supplied = args.name is not None or args.elements_json is not None
    element_adjustment_supplied = any(
        value is not None
        for value in (
            args.add_elements_json,
            args.retire_element_ids,
            args.boost_elements_json,
        )
    )
    persona_adjustment_supplied = (
        (
            args.persona_payload is not None
            or args.persona_id is not None
            or args.patch_persona_payload is not None
        )
        and args.name is None
        and args.elements_json is None
    )
    adjustment_supplied = element_adjustment_supplied or persona_adjustment_supplied
    if complete_plan_supplied and element_adjustment_supplied:
        raise ValueError("一次提案只能是一种:整套方案 或 调整")
    if not complete_plan_supplied and not adjustment_supplied:
        raise ValueError(
            "agentic-campaign +plan-propose requires either a complete plan or an adjustment."
        )
    if args.title is not None and not adjustment_supplied:
        raise ValueError(
            "--title is only valid for an active-plan adjustment proposal; "
            "a draft plan proposal already uses --name."
        )
    if complete_plan_supplied:
        persona_supplied = args.persona_payload is not None or args.persona_id is not None
        if not persona_supplied or args.elements_json is None:
            raise ValueError(
                "complete plan proposal requires --elements-json and exactly one of "
                "--persona-payload or --persona-id; --name is also required when submitting "
                "a new candidate."
            )

    payload: dict[str, Any] = compact_params(
        {
            "plan_id": args.plan_id,
            "proposal_id": args.proposal_id,
            "note": args.note,
            "dry_run": args.dry_run,
        }
    )
    if complete_plan_supplied:
        persona_field: dict[str, Any] = (
            {"persona_id": args.persona_id}
            if args.persona_id is not None
            else {
                "persona_payload": _candidate_json(
                    args.persona_payload,
                    field="persona",
                    expected_type=dict,
                )
            }
        )
        payload.update(
            {
                "name": args.name,
                **persona_field,
                "elements": (
                    _candidate_json(
                        args.elements_json,
                        field="elements",
                        expected_type=list,
                    )
                    if args.elements_json is not None
                    else None
                ),
            }
        )
    elif adjustment_supplied:
        persona: dict[str, Any] | None = None
        if args.persona_id is not None:
            persona = {"persona_id": args.persona_id}
        elif args.persona_payload is not None:
            persona = {
                "persona_payload": _candidate_json(
                    args.persona_payload,
                    field="persona",
                    expected_type=dict,
                )
            }
        payload["changes"] = _revision_changes(
            add_elements=_revision_json_list(args.add_elements_json, field="add-elements"),
            retire_element_ids=args.retire_element_ids,
            boost_elements=_revision_json_list(args.boost_elements_json, field="boost-elements"),
            persona=persona,
            patch_persona_payload=(
                _candidate_json(
                    args.patch_persona_payload,
                    field="patch-persona-payload",
                    expected_type=dict,
                )
                if args.patch_persona_payload is not None
                else None
            ),
        )
        if args.title is not None:
            payload["title"] = args.title
    return payload


def _add_campaign_rename_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--dry-run", action="store_true")


def _build_campaign_rename_arguments(args: argparse.Namespace) -> dict[str, Any]:
    return {"campaign_id": args.campaign_id, "name": args.name, "dry_run": args.dry_run}


def _add_proposal_withdraw_arguments(parser: argparse.ArgumentParser) -> None:
    _add_plan_id_arguments(parser)
    parser.add_argument(
        "--proposal-id",
        required=True,
        help="Open revision proposal to withdraw on an active plan.",
    )
    parser.add_argument("--dry-run", action="store_true")


def _build_proposal_withdraw_arguments(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "plan_id": args.plan_id,
        "proposal_id": args.proposal_id,
        "dry_run": args.dry_run,
    }


def _add_campaign_create_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--name", required=True)
    parser.add_argument("--total-account-budget", type=int, default=0)
    parser.add_argument("--planned-persona-count", type=int, default=None)
    parser.add_argument("--product-id", default=None)
    parser.add_argument("--cta-definition", default=None)
    parser.add_argument("--config-json", default=None)
    parser.add_argument("--required-hashtags", default=None)
    parser.add_argument("--required-mentions", default=None)
    parser.add_argument("--preferred-publish-windows-json", default=None)
    parser.add_argument("--bind-notification-conversation", action="store_true")
    parser.add_argument("--dry-run", action="store_true")


def _field_config(args: argparse.Namespace) -> dict[str, Any] | None:
    values = (
        args.required_hashtags,
        args.required_mentions,
        args.preferred_publish_windows_json,
    )
    if args.config_json is not None and any(value is not None for value in values):
        raise ValueError(
            "--config-json is mutually exclusive with --required-hashtags, "
            "--required-mentions, and --preferred-publish-windows-json."
        )
    if args.config_json is not None:
        return _candidate_json(args.config_json, field="config", expected_type=dict)
    config: dict[str, Any] = {}
    if args.required_hashtags is not None:
        config["required_hashtags"] = _csv(args.required_hashtags)
    if args.required_mentions is not None:
        config["required_mentions"] = _csv(args.required_mentions)
    if args.preferred_publish_windows_json is not None:
        config["preferred_publish_windows"] = _candidate_json(
            args.preferred_publish_windows_json,
            field="preferred-publish-windows",
            expected_type=list,
        )
    return config or None


def _build_campaign_create_arguments(args: argparse.Namespace) -> dict[str, Any]:
    config = _field_config(args)
    return compact_params(
        {
            "name": args.name,
            "total_account_budget": args.total_account_budget,
            "planned_persona_count": args.planned_persona_count,
            "product_id": args.product_id,
            "cta_definition": args.cta_definition,
            "bind_notification_conversation": args.bind_notification_conversation,
            "config": config,
            "dry_run": args.dry_run,
        }
    )


def _add_campaign_update_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--name")
    parser.add_argument("--total-account-budget", type=int)
    parser.add_argument("--planned-persona-count", type=int)
    parser.add_argument("--cta-definition")
    parser.add_argument("--product-id")
    parser.add_argument("--config-json")
    parser.add_argument("--required-hashtags")
    parser.add_argument("--required-mentions")
    parser.add_argument("--preferred-publish-windows-json")
    parser.add_argument("--bind-notification-conversation", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--yes", action="store_true")


def _build_campaign_update_arguments(args: argparse.Namespace) -> dict[str, Any]:
    field_config_values = (
        args.required_hashtags,
        args.required_mentions,
        args.preferred_publish_windows_json,
    )
    if args.config_json is not None and any(value is not None for value in field_config_values):
        raise ValueError(
            "--config-json is mutually exclusive with --required-hashtags, "
            "--required-mentions, and --preferred-publish-windows-json."
        )
    mutable = compact_params(
        {
            "name": args.name,
            "total_account_budget": args.total_account_budget,
            "planned_persona_count": args.planned_persona_count,
            "cta_definition": args.cta_definition,
            "product_id": args.product_id,
            "config": (
                _candidate_json(args.config_json, field="config", expected_type=dict)
                if args.config_json is not None
                else None
            ),
            "required_hashtags": (
                _csv(args.required_hashtags) if args.required_hashtags is not None else None
            ),
            "required_mentions": (
                _csv(args.required_mentions) if args.required_mentions is not None else None
            ),
            "preferred_publish_windows": (
                _candidate_json(
                    args.preferred_publish_windows_json,
                    field="preferred-publish-windows",
                    expected_type=list,
                )
                if args.preferred_publish_windows_json is not None
                else None
            ),
            "bind_notification_conversation": (
                True if args.bind_notification_conversation else None
            ),
        }
    )
    if not mutable:
        raise ValueError("agentic-campaign +campaign-update requires at least one mutable flag.")
    if "name" in mutable and len(mutable) != 1:
        raise ValueError("--name is mutually exclusive with all other mutable flags.")
    return {
        "campaign_id": args.campaign_id,
        **mutable,
        "dry_run": args.dry_run,
    }


def _add_plan_update_arguments(parser: argparse.ArgumentParser) -> None:
    _add_plan_id_arguments(parser)
    parser.add_argument("--name")
    parser.add_argument("--account-budget", type=int)
    parser.add_argument("--required-hashtags")
    parser.add_argument("--required-mentions")
    parser.add_argument("--dry-run", action="store_true")


def _build_plan_update_arguments(args: argparse.Namespace) -> dict[str, Any]:
    mutable = compact_params(
        {
            "name": args.name,
            "account_budget": args.account_budget,
            "required_hashtags": (
                _csv(args.required_hashtags) if args.required_hashtags is not None else None
            ),
            "required_mentions": (
                _csv(args.required_mentions) if args.required_mentions is not None else None
            ),
        }
    )
    if not mutable:
        raise ValueError("agentic-campaign +plan-update requires at least one mutable flag.")
    token_fields = {"required_hashtags", "required_mentions"} & mutable.keys()
    setup_fields = {"name", "account_budget"} & mutable.keys()
    if token_fields and setup_fields:
        raise ValueError(
            "--required-hashtags and --required-mentions are mutually exclusive "
            "with --name and --account-budget."
        )
    return {"plan_id": args.plan_id, **mutable, "dry_run": args.dry_run}


def _add_plan_create_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--account-budget", type=int, required=True)
    parser.add_argument("--dry-run", action="store_true")


def _build_plan_create_arguments(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "campaign_id": args.campaign_id,
        "name": args.name,
        "account_budget": args.account_budget,
        "dry_run": args.dry_run,
    }


def _add_campaign_lifecycle_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--dry-run", action="store_true")


def _build_campaign_lifecycle_arguments(args: argparse.Namespace) -> dict[str, Any]:
    return {"campaign_id": args.campaign_id, "dry_run": args.dry_run}


def _add_campaign_archive_arguments(parser: argparse.ArgumentParser) -> None:
    _add_campaign_lifecycle_arguments(parser)
    parser.add_argument("--yes", action="store_true")


def _build_campaign_archive_arguments(args: argparse.Namespace) -> dict[str, Any]:
    return {"campaign_id": args.campaign_id, "dry_run": args.dry_run}


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


def _campaign_config_schema() -> dict[str, Any]:
    return {
        "type": ["object", "null"],
        "additionalProperties": False,
        "properties": {
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
            "preferred_publish_windows": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "start": {"type": "string", "pattern": "^\\d{2}:\\d{2}$"},
                        "end": {"type": "string", "pattern": "^\\d{2}:\\d{2}$"},
                    },
                    "required": ["start", "end"],
                },
                "default": [],
            },
        },
    }


def specs() -> list[CommandSpec]:
    domain = Domain.AGENTIC_CAMPAIGN
    return [
        CommandSpec(
            domain=domain,
            shortcut="+plan-propose",
            summary=(
                "Create a complete plan proposal, adjust a running plan, or revise an open "
                "proposal for operator review. For a running-plan adjustment, set --title to "
                "a short name the "
                "operator can recognize at a glance in the proposal list. Several adjustment "
                "proposals may stay open on one plan at the same time and each is confirmed "
                "on its own, but a submission that collides with an open proposal, or that "
                "exceeds the open-proposal limit, is rejected and names the blocking proposal."
            ),
            risk_level="write",
            execution="direct",
            adapter_tool_name="agentic_campaign_plan_propose",
            input_schema={
                "type": "object",
                "description": (
                    "Choose exactly one action. To create a proposal, submit a complete solution "
                    "(name, elements, and exactly "
                    "one of persona_payload or persona_id). persona_id references an existing "
                    "persona; the server "
                    "snapshots its name, description, and visual reference into the proposal at "
                    "submission time (copied, not bound -- later edits to the source persona do "
                    "not affect this proposal; tags and marketing_profile are not copied). For "
                    "a running plan, submit one unified adjustment in changes; changes may include "
                    "persona, add_elements, retire_element_ids, and boost_elements in any "
                    "combination, optionally with a title. To revise an open proposal after "
                    "operator feedback, provide proposal_id and replacement elements, with an "
                    "optional full persona replacement via persona_payload or persona_id. When "
                    "persona_payload and persona_id are both omitted during revision, the "
                    "proposal's current persona is preserved; it is not cleared. "
                    "Several adjustment proposals may stay open on the same plan at once, and "
                    "confirming one never invalidates the others, so an open proposal stays "
                    "confirmable however old its base is. In exchange, open proposals must not "
                    "overlap: submission is rejected with 409 proposal_element_conflict "
                    "(blocking_proposal_id, element_ids) when the new proposal touches a plan "
                    "element another open proposal already claims, 409 proposal_persona_conflict "
                    "(blocking_proposal_id) when it carries a persona change while another open "
                    "proposal already does, and 409 proposal_open_limit_reached (limit, "
                    "open_proposal_ids) when the plan already has the maximum number of open "
                    "proposals. Retrying the same payload always fails again: withdraw the "
                    "blocking proposal with +proposal-withdraw --proposal-id "
                    "<blocking_proposal_id> and submit again, or revise the named proposal in "
                    "place with +plan-propose --proposal-id. +plan-get reports what is already "
                    "claimed in open_proposal_claims and how many slots are left in "
                    "proposal_capacity."
                ),
                "properties": {
                    "plan_id": _uuid_property("Agentic Persona Plan id"),
                    "proposal_id": {
                        "type": ["string", "null"],
                        "format": "uuid",
                        "description": "Open proposal id to revise",
                    },
                    "name": {"type": "string", "minLength": 1, "maxLength": 200},
                    "title": {
                        "type": ["string", "null"],
                        "maxLength": 80,
                        "description": (
                            "Short operator-facing name for an active-plan adjustment proposal"
                        ),
                    },
                    "persona_payload": _persona_payload_schema(),
                    "persona_id": {
                        "type": ["string", "null"],
                        "format": "uuid",
                        "description": (
                            "Existing persona id to snapshot into this proposal at submission "
                            "(name, description, and visual reference are copied, not bound -- "
                            "later edits to the source persona do not affect this proposal; "
                            "tags and marketing_profile are not copied). Mutually exclusive "
                            "with persona_payload. Creating a proposal requires exactly one; "
                            "revising may omit both to preserve the proposal's current persona."
                        ),
                    },
                    "elements": _candidate_elements_schema(),
                    "changes": {
                        "type": "object",
                        "additionalProperties": False,
                        "anyOf": [
                            {
                                "required": ["add_elements"],
                                "properties": {"add_elements": {"minItems": 1}},
                            },
                            {
                                "required": ["retire_element_ids"],
                                "properties": {"retire_element_ids": {"minItems": 1}},
                            },
                            {
                                "required": ["boost_elements"],
                                "properties": {"boost_elements": {"minItems": 1}},
                            },
                            {"required": ["persona"]},
                            {"required": ["patch_persona_payload"]},
                        ],
                        "properties": {
                            "add_elements": _revision_add_elements_schema(),
                            "retire_element_ids": {
                                "type": "array",
                                "maxItems": 100,
                                "items": _uuid_property("Experiment direction id"),
                            },
                            "boost_elements": _revision_boosts_schema(),
                            "persona": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "persona_id": {
                                        "type": ["string", "null"],
                                        "format": "uuid",
                                        "description": "Workspace Persona to snapshot into the proposal.",
                                    },
                                    "persona_payload": {
                                        "type": ["object", "null"],
                                        "description": "Persona content to snapshot into the proposal.",
                                    },
                                },
                            },
                            "patch_persona_payload": {
                                "type": "object",
                                "additionalProperties": False,
                                "description": (
                                    "Partial Persona update: omitted keys are preserved; "
                                    "explicit null clears a nullable field."
                                ),
                                "properties": {
                                    "name": {"type": ["string", "null"], "maxLength": 200},
                                    "description": {"type": ["string", "null"], "maxLength": 4000},
                                    "tags": {
                                        "type": ["array", "null"],
                                        "items": {"type": "string"},
                                    },
                                    "marketing_profile": {"type": ["object", "null"]},
                                    "reference_media_ids": {
                                        "type": ["array", "null"],
                                        "items": {"type": "string", "format": "uuid"},
                                    },
                                },
                            },
                        },
                        "required": [],
                    },
                    "note": {"type": ["string", "null"], "maxLength": 2000},
                    "dry_run": {"type": "boolean", "default": False},
                },
                "required": ["plan_id"],
                "oneOf": [
                    {
                        "title": "Create a proposal",
                        "required": ["name", "elements"],
                        "oneOf": [
                            {"required": ["persona_payload"], "not": {"required": ["persona_id"]}},
                            {"required": ["persona_id"], "not": {"required": ["persona_payload"]}},
                        ],
                        "not": {
                            "anyOf": [
                                {"required": ["proposal_id"]},
                                {"required": ["changes"]},
                                {"required": ["title"]},
                            ]
                        },
                    },
                    {
                        "title": "Adjust a running plan",
                        "required": ["changes"],
                        "not": {
                            "anyOf": [
                                {"required": ["name"]},
                                {"required": ["persona_payload"]},
                                {"required": ["persona_id"]},
                                {"required": ["elements"]},
                                {"required": ["proposal_id"]},
                            ]
                        },
                    },
                    {
                        "title": "Revise an open proposal",
                        "required": ["proposal_id", "elements"],
                        "properties": {"proposal_id": {"type": "string", "format": "uuid"}},
                        "not": {
                            "anyOf": [
                                {"required": ["name"]},
                                {"required": ["changes"]},
                                {"required": ["title"]},
                                {
                                    "required": ["persona_payload", "persona_id"],
                                },
                            ]
                        },
                    },
                ],
            },
            output_schema=_direct_output_schema(
                "Proposal id, change summary, and operator review reminder."
            ),
            examples=[
                "museoncli agentic-campaign +plan-propose "
                "--plan-id 33333333-3333-4333-8333-333333333333 "
                "--name 'DIY problem solver' "
                """--persona-json '{"name":"Mia","description":"Practical maker","""
                """"visual_prompt":"Warm workshop portrait","reference_media_ids":[]}' """
                """--elements-json '[{"format_id":"44444444-4444-4444-8444-444444444444","""
                """"topic_id":"55555555-5555-4555-8555-555555555555"}]'""",
                "museoncli agentic-campaign +plan-propose "
                "--plan-id 33333333-3333-4333-8333-333333333333 "
                "--name 'Reuse the workshop persona' "
                "--persona-id 99999999-9999-4999-8999-999999999999 "
                """--elements-json '[{"format_id":"44444444-4444-4444-8444-444444444444","""
                """"topic_id":"55555555-5555-4555-8555-555555555555"}]'""",
                "museoncli agentic-campaign +plan-propose "
                "--plan-id 33333333-3333-4333-8333-333333333333 "
                "--title 'Dark-tone second test batch' "
                """--add-elements-json '[{"format_id":"44444444-4444-4444-8444-444444444444","""
                """"topic_id":"55555555-5555-4555-8555-555555555555"}]' """
                "--note 'Untested hypothesis on the dark visual direction'",
                "museoncli agentic-campaign +plan-propose "
                "--plan-id 33333333-3333-4333-8333-333333333333 "
                "--proposal-id 77777777-7777-4777-8777-777777777777 "
                """--elements-json '[{"format_id":"44444444-4444-4444-8444-444444444444","""
                """"topic_id":"55555555-5555-4555-8555-555555555555"}]' """
                "--note 'Applied the latest review feedback; omitted persona is preserved'",
            ],
            add_arguments=_add_plan_propose_arguments,
            build_arguments=_build_plan_propose_arguments,
            supports_dry_run=True,
        ),
        CommandSpec(
            domain=domain,
            shortcut="+proposal-get",
            summary=(
                "Read an adjustment proposal, its latest revision guidance, and the "
                "full round-by-round annotation history (annotations)."
            ),
            risk_level="read",
            execution="direct",
            adapter_tool_name="agentic_campaign_proposal_get",
            input_schema=_plan_schema(
                {"proposal_id": _uuid_property("Adjustment proposal id")},
                required=["proposal_id"],
            ),
            output_schema=_direct_output_schema(
                "Proposal status, revision round, changes, current elements, latest feedback "
                "summary, the annotations section (per-round compiled_summary/round/resolved, "
                'newest round first, or the string "暂无标注意见" when there is no feedback '
                "yet), and a review reminder."
            ),
            examples=[
                "museoncli agentic-campaign +proposal-get "
                "--plan-id 33333333-3333-4333-8333-333333333333 "
                "--proposal-id 77777777-7777-4777-8777-777777777777"
            ],
            add_arguments=_add_proposal_get_arguments,
            build_arguments=_build_proposal_get_arguments,
        ),
        CommandSpec(
            domain=domain,
            shortcut="+proposal-withdraw",
            summary=(
                "Withdraw one open adjustment proposal on this plan, permanently releasing "
                "the plan elements and the persona change it holds. Withdrawal cannot be "
                "undone, and a proposal the operator already confirmed cannot be withdrawn. "
                "This is one of the two ways out of a rejected +plan-propose: when the server "
                "answers 409 proposal_element_conflict, proposal_persona_conflict or "
                "proposal_open_limit_reached it names the blocking_proposal_id, so either "
                "withdraw that proposal here and submit again, or revise the named proposal "
                "in place with +plan-propose --proposal-id. Never resend the rejected payload "
                "unchanged."
            ),
            risk_level="write",
            execution="direct",
            adapter_tool_name="agentic_campaign_proposal_withdraw",
            input_schema=_plan_schema(
                {
                    "proposal_id": _uuid_property("Open adjustment proposal id"),
                    "dry_run": {"type": "boolean", "default": False},
                },
                required=["proposal_id"],
            ),
            output_schema=_direct_output_schema("Withdrawn adjustment proposal."),
            examples=[
                "museoncli agentic-campaign +proposal-withdraw "
                "--plan-id 33333333-3333-4333-8333-333333333333 "
                "--proposal-id 77777777-7777-4777-8777-777777777777"
            ],
            add_arguments=_add_proposal_withdraw_arguments,
            build_arguments=_build_proposal_withdraw_arguments,
            supports_dry_run=True,
        ),
        CommandSpec(
            domain=domain,
            shortcut="+campaign-create",
            summary=(
                "Create an Agentic Creative Campaign in the selected workspace. Confirm the "
                "intent (name, total budget, planned persona count) with the operator before "
                "creating, and report the campaign link back afterward."
            ),
            risk_level="write",
            execution="direct",
            adapter_tool_name="agentic_campaign_campaign_create",
            input_schema=_schema(
                {
                    "name": {"type": "string", "minLength": 1, "maxLength": 160},
                    "total_account_budget": {"type": "integer", "minimum": 0, "default": 0},
                    "planned_persona_count": {
                        "type": ["integer", "null"],
                        "minimum": 1,
                        "maximum": 10,
                    },
                    "product_id": {
                        "type": ["string", "null"],
                        "format": "uuid",
                        "description": "Optional product id",
                    },
                    "cta_definition": {"type": ["string", "null"]},
                    "bind_notification_conversation": {
                        "type": "boolean",
                        "default": False,
                    },
                    "config": _campaign_config_schema(),
                    "dry_run": {"type": "boolean", "default": False},
                },
                required=["name"],
            ),
            output_schema=_direct_output_schema("Created campaign detail."),
            examples=[
                "museoncli agentic-campaign +campaign-create "
                "--name 'Summer maker campaign' --total-account-budget 20 "
                "--planned-persona-count 3"
            ],
            add_arguments=_add_campaign_create_arguments,
            build_arguments=_build_campaign_create_arguments,
            supports_dry_run=True,
        ),
        CommandSpec(
            domain=domain,
            shortcut="+campaign-update",
            summary=(
                "Patch only supplied campaign fields. Budget and config fields are setup-only; "
                "name must be changed by itself. Field-level hashtag, mention, and publish-window "
                "options merge into existing config, while --config-json replaces the full config."
            ),
            risk_level="write",
            requires_confirmation=True,
            execution="direct",
            adapter_tool_name="agentic_campaign_campaign_update",
            input_schema=_schema(
                {
                    "campaign_id": _uuid_property("Agentic Creative Campaign id"),
                    "name": {"type": "string", "minLength": 1, "maxLength": 160},
                    "total_account_budget": {"type": "integer", "minimum": 0},
                    "planned_persona_count": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 10,
                    },
                    "cta_definition": {"type": "string"},
                    "product_id": _uuid_property("Product id"),
                    "config": _campaign_config_schema(),
                    "required_hashtags": _campaign_config_schema()["properties"][
                        "required_hashtags"
                    ],
                    "required_mentions": _campaign_config_schema()["properties"][
                        "required_mentions"
                    ],
                    "preferred_publish_windows": _campaign_config_schema()["properties"][
                        "preferred_publish_windows"
                    ],
                    "bind_notification_conversation": {"type": "boolean"},
                    "dry_run": {"type": "boolean", "default": False},
                },
                required=["campaign_id"],
            ),
            output_schema=_direct_output_schema("Updated campaign detail."),
            examples=[
                "museoncli agentic-campaign +campaign-update "
                "--campaign-id 22222222-2222-4222-8222-222222222222 "
                "--total-account-budget 107 --yes",
                "museoncli agentic-campaign +campaign-update "
                "--campaign-id 22222222-2222-4222-8222-222222222222 "
                "--bind-notification-conversation --yes",
            ],
            add_arguments=_add_campaign_update_arguments,
            build_arguments=_build_campaign_update_arguments,
            supports_dry_run=True,
        ),
        CommandSpec(
            domain=domain,
            shortcut="+plan-update",
            summary=(
                "Update plan tokens for the next generation while a campaign is active or "
                "paused, or update name/budget only during setup."
            ),
            risk_level="write",
            execution="direct",
            adapter_tool_name="agentic_campaign_plan_update",
            input_schema=_plan_schema(
                {
                    "name": {"type": "string", "minLength": 1, "maxLength": 160},
                    "account_budget": {"type": "integer", "minimum": 0},
                    "required_hashtags": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "required_mentions": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "dry_run": {"type": "boolean", "default": False},
                }
            ),
            output_schema=_direct_output_schema("Updated Persona Plan detail."),
            examples=[
                "museoncli agentic-campaign +plan-update "
                "--plan-id 33333333-3333-4333-8333-333333333333 "
                "--required-hashtags '#maker,#diy'"
            ],
            add_arguments=_add_plan_update_arguments,
            build_arguments=_build_plan_update_arguments,
            supports_dry_run=True,
        ),
        CommandSpec(
            domain=domain,
            shortcut="+plan-create",
            summary=(
                "Create a Persona Plan under a campaign. Only allowed while the campaign is "
                "in setup (setting_up or setup_ready); the server rejects the request "
                "otherwise and the error is passed through unchanged."
            ),
            risk_level="write",
            execution="direct",
            adapter_tool_name="agentic_campaign_plan_create",
            input_schema=_schema(
                {
                    "campaign_id": _uuid_property("Agentic Creative Campaign id"),
                    "name": {"type": "string", "minLength": 1, "maxLength": 160},
                    "account_budget": {"type": "integer", "minimum": 0},
                    "dry_run": {"type": "boolean", "default": False},
                },
                required=["campaign_id", "name", "account_budget"],
            ),
            output_schema=_direct_output_schema("Campaign detail including the new plan."),
            examples=[
                "museoncli agentic-campaign +plan-create "
                "--campaign-id 22222222-2222-4222-8222-222222222222 "
                "--name 'DIY makers' --account-budget 5"
            ],
            add_arguments=_add_plan_create_arguments,
            build_arguments=_build_plan_create_arguments,
            supports_dry_run=True,
        ),
        CommandSpec(
            domain=domain,
            shortcut="+campaign-activate",
            summary="Activate an Agentic Creative Campaign, resuming member account operations.",
            risk_level="write",
            execution="direct",
            adapter_tool_name="agentic_campaign_campaign_activate",
            input_schema=_schema(
                {
                    "campaign_id": _uuid_property("Agentic Creative Campaign id"),
                    "dry_run": {"type": "boolean", "default": False},
                },
                required=["campaign_id"],
            ),
            output_schema=_direct_output_schema(
                "Transitioned campaign detail and the operation batch result."
            ),
            examples=[
                "museoncli agentic-campaign +campaign-activate "
                "--campaign-id 22222222-2222-4222-8222-222222222222"
            ],
            add_arguments=_add_campaign_lifecycle_arguments,
            build_arguments=_build_campaign_lifecycle_arguments,
            supports_dry_run=True,
        ),
        CommandSpec(
            domain=domain,
            shortcut="+campaign-pause",
            summary="Pause an Agentic Creative Campaign, stopping member account operations.",
            risk_level="write",
            execution="direct",
            adapter_tool_name="agentic_campaign_campaign_pause",
            input_schema=_schema(
                {
                    "campaign_id": _uuid_property("Agentic Creative Campaign id"),
                    "dry_run": {"type": "boolean", "default": False},
                },
                required=["campaign_id"],
            ),
            output_schema=_direct_output_schema(
                "Transitioned campaign detail and the operation batch result."
            ),
            examples=[
                "museoncli agentic-campaign +campaign-pause "
                "--campaign-id 22222222-2222-4222-8222-222222222222"
            ],
            add_arguments=_add_campaign_lifecycle_arguments,
            build_arguments=_build_campaign_lifecycle_arguments,
            supports_dry_run=True,
        ),
        CommandSpec(
            domain=domain,
            shortcut="+campaign-archive",
            summary=(
                "Archive an Agentic Creative Campaign. This cascades to stop account "
                "operations for every member of every plan in the campaign; the operator "
                "must explicitly confirm before running with --yes."
            ),
            risk_level="destructive",
            requires_confirmation=True,
            execution="direct",
            adapter_tool_name="agentic_campaign_campaign_archive",
            input_schema=_schema(
                {
                    "campaign_id": _uuid_property("Agentic Creative Campaign id"),
                    "dry_run": {"type": "boolean", "default": False},
                },
                required=["campaign_id"],
            ),
            output_schema=_direct_output_schema(
                "Transitioned campaign detail and the operation batch result "
                "(succeeded/skipped/failed counts for the stopped member operations)."
            ),
            examples=[
                "museoncli agentic-campaign +campaign-archive "
                "--campaign-id 22222222-2222-4222-8222-222222222222 --yes"
            ],
            add_arguments=_add_campaign_archive_arguments,
            build_arguments=_build_campaign_archive_arguments,
            supports_dry_run=True,
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
                    "dry_run": {"type": "boolean", "default": False},
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
            supports_dry_run=True,
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


def _complete_plan_arguments(
    ctx: CommandContext,
) -> tuple[str | None, dict[str, Any] | None, str | None, list[Any]]:
    name = ctx.arguments.get("name")
    persona_payload = ctx.arguments.get("persona_payload")
    persona_id = ctx.arguments.get("persona_id")
    elements = ctx.arguments.get("elements")
    if (persona_payload is None) == (persona_id is None):
        raise ValueError(
            "draft plan proposal requires exactly one of --persona-json or --persona-id."
        )
    if persona_payload is not None and not isinstance(persona_payload, dict):
        raise ValueError("draft plan proposal requires --persona-json to be a JSON object.")
    if not isinstance(elements, list) or not elements:
        raise ValueError("draft plan proposal requires --elements-json with at least one element.")
    return (
        str(name) if name else None,
        persona_payload if isinstance(persona_payload, dict) else None,
        str(persona_id) if persona_id is not None else None,
        elements,
    )


def _proposal_output(response: Any, *, changes: dict[str, Any]) -> dict[str, Any]:
    payload = _payload_data(response)
    proposal = payload.get("proposal") if isinstance(payload, dict) else None
    proposal_id = proposal.get("id") if isinstance(proposal, dict) else None
    return {
        **({"proposal_id": proposal_id} if proposal is not None else {}),
        "change_summary": changes,
        "next_step": "Please review the proposal in Museon and confirm it there.",
    }


def _proposal_elements(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [
        {
            "format_id": item.get("format_id"),
            "topic_id": item.get("topic_id"),
            "cta_target_id": item.get("cta_target_id"),
        }
        for item in value
        if isinstance(item, dict)
    ]


def _annotations(items: Any) -> Any:
    """Render the "标注意见" section: newest round first, or a placeholder string."""

    rounds = [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []
    if not rounds:
        return "暂无标注意见"
    rounds.sort(key=lambda item: item.get("round") or 0, reverse=True)
    rendered = []
    for item in rounds:
        summary = item.get("compiled_summary")
        rendered.append(
            {
                "round": item.get("round"),
                "resolved": item.get("resolved_at") is not None,
                "compiled_summary": (
                    summary if isinstance(summary, str) and summary else "该轮无可渲染文本"
                ),
            }
        )
    return rendered


async def _execute_proposal_get(ctx: CommandContext) -> Any:
    campaign_id, plan, _ = await _locate_plan(ctx)
    proposal_id = ctx.arguments.get("proposal_id")
    response = await ctx.api_data_v2(
        ctx.cfg,
        "GET",
        (
            f"/agentic-creative-campaigns/{campaign_id}/persona-plans/{plan['id']}/"
            f"revision-proposals/{proposal_id}"
        ),
        params={"workspace_id": ctx.workspace_id},
    )
    proposal = _payload_data(response)
    if not isinstance(proposal, dict):
        raise RuntimeError("revision proposal response was not an object")
    changes = proposal.get("changes")
    if not isinstance(changes, dict):
        changes = {}
    feedback_summary = proposal.get("feedback_summary")
    feedback_response = await ctx.api_data_v2(
        ctx.cfg,
        "GET",
        (
            f"/agentic-creative-campaigns/{campaign_id}/persona-plans/{plan['id']}/"
            f"revision-proposals/{proposal_id}/feedback"
        ),
        params={"workspace_id": ctx.workspace_id},
    )
    feedback_payload = _payload_data(feedback_response)
    feedback_items = feedback_payload.get("items") if isinstance(feedback_payload, dict) else None
    return {
        "status": proposal.get("status"),
        "revision_round": proposal.get("revision_round"),
        "change_summary": {
            "new_directions": len(changes.get("add_elements") or []),
            "directions_to_stop": len(changes.get("retire_element_ids") or []),
            "winner_boosts": len(changes.get("boost_elements") or []),
        },
        "elements": _proposal_elements(proposal.get("elements")),
        **(
            {"feedback_summary": feedback_summary}
            if isinstance(feedback_summary, str) and feedback_summary
            else {}
        ),
        "annotations": _annotations(feedback_items),
        "next_step": "请在 Museon 审阅台查看这一稿；运营可继续标注意见或确认。",
    }


async def _execute_plan_propose(ctx: CommandContext) -> Any:
    campaign_id, plan, _ = await _locate_plan(ctx)
    status = plan.get("status")
    proposal_id = ctx.arguments.get("proposal_id")
    raw_changes = ctx.arguments.get("changes")
    has_solution = any(
        ctx.arguments.get(key) is not None
        for key in ("name", "persona_payload", "persona_id", "elements")
    )
    has_adjustment = raw_changes is not None
    if has_solution and has_adjustment:
        raise ValueError("一次提案只能是一种:整套方案 或 调整")

    if proposal_id:
        # Revise an existing proposal -- draft-stage or active-plan, the same operation
        # either way. persona is optional: omitting it keeps the persona the proposal
        # already carries; patch semantics are out of scope here (the server only takes
        # a full persona replacement on this endpoint), so a patch payload is rejected
        # rather than silently sent as a full replacement.
        if ctx.arguments.get("name") is not None:
            raise ValueError("name is not valid when revising an adjustment proposal.")
        if raw_changes is not None:
            raise ValueError(
                "adjustment changes are not valid when revising an adjustment proposal."
            )
        if ctx.arguments.get("patch_persona_payload") is not None:
            raise ValueError(
                "patch_persona_payload is not valid when revising an adjustment proposal; "
                "the server only accepts a full persona replacement here."
            )
        elements = ctx.arguments.get("elements")
        if not isinstance(elements, list) or not elements:
            raise ValueError("adjustment proposal revision requires at least one element.")
        persona_id = ctx.arguments.get("persona_id")
        persona_payload = ctx.arguments.get("persona_payload")
        body: dict[str, Any] = {
            "workspace_id": ctx.workspace_id,
            "elements": elements,
            "note": ctx.arguments.get("note"),
        }
        if persona_id is not None:
            body["persona"] = {"persona_id": persona_id}
        elif persona_payload is not None:
            body["persona"] = {"persona_payload": persona_payload}
        response = await ctx.api_data_v2(
            ctx.cfg,
            "POST",
            (
                f"/agentic-creative-campaigns/{campaign_id}/persona-plans/{plan['id']}/"
                f"revision-proposals/{proposal_id}:submit-revision"
            ),
            json_body=body,
        )
        payload = _payload_data(response)
        if not isinstance(payload, dict):
            raise RuntimeError("revision submission response was not an object")
        revision_round = payload.get("round")
        return {
            "revision_round": revision_round,
            "new_element_count": len(payload.get("elements") or []),
            "preview_task_count": payload.get("dispatched_task_count"),
            "next_step": f"第 {revision_round} 稿已提交；运营将在审阅台看到新一稿。",
        }

    if status == "draft":
        if has_adjustment:
            raise ValueError("draft plan only accepts a complete plan proposal.")
        name, persona_payload, persona_id, elements = _complete_plan_arguments(ctx)
        if not name:
            raise ValueError("new draft plan proposal requires --name.")
        persona_field: dict[str, Any] = (
            {"persona_id": persona_id}
            if persona_id is not None
            else {"persona_payload": persona_payload}
        )
        body = {
            "workspace_id": ctx.workspace_id,
            "title": name,
            "note": ctx.arguments.get("note"),
            "changes": {
                "add_elements": elements,
                "persona": persona_field,
            },
        }
        response = await ctx.api_data_v2(
            ctx.cfg,
            "POST",
            (
                f"/agentic-creative-campaigns/{campaign_id}/persona-plans/"
                f"{plan['id']}/revision-proposals"
            ),
            json_body=body,
        )
        return _proposal_output(
            response,
            changes={
                "complete_plan": True,
                "name": name,
                "directions": len(elements),
            },
        )

    if status != "active":
        raise ValueError(
            f"plan status must be draft or active to accept a proposal; got {status!r}."
        )
    if has_solution:
        raise ValueError("active plan only accepts an adjustment proposal.")
    raw_changes = ctx.arguments.get("changes")
    if not isinstance(raw_changes, dict):
        raw_changes = {}
    changes = _revision_changes(
        add_elements=raw_changes.get("add_elements"),
        retire_element_ids=raw_changes.get("retire_element_ids"),
        boost_elements=raw_changes.get("boost_elements"),
        persona=raw_changes.get("persona"),
        patch_persona_payload=raw_changes.get("patch_persona_payload"),
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
            "title": ctx.arguments.get("title"),
            "note": ctx.arguments.get("note"),
            "changes": changes,
        },
    )
    change_summary = {
        "new_directions": len(changes["add_elements"]),
        "directions_to_stop": len(changes["retire_element_ids"]),
        "winner_boosts": len(changes["boost_elements"]),
    }
    if changes.get("persona") or changes.get("patch_persona_payload"):
        change_summary["persona_change"] = True
    return _proposal_output(response, changes=change_summary)


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


async def _execute_proposal_withdraw(ctx: CommandContext) -> Any:
    campaign_id, plan, _ = await _locate_plan(ctx)
    proposal_id = ctx.arguments.get("proposal_id")
    if not proposal_id:
        raise ValueError("--proposal-id is required.")
    path = (
        f"/agentic-creative-campaigns/{campaign_id}/persona-plans/{plan['id']}/"
        f"revision-proposals/{proposal_id}:dismiss"
    )
    return await ctx.api_data_v2(
        ctx.cfg,
        "POST",
        path,
        json_body={"workspace_id": ctx.workspace_id},
    )


async def _execute_campaign_create(ctx: CommandContext) -> Any:
    return await ctx.api_data_v2(
        ctx.cfg,
        "POST",
        "/agentic-creative-campaigns",
        json_body=compact_params(
            {
                "workspace_id": ctx.workspace_id,
                "name": ctx.arguments.get("name"),
                "total_account_budget": ctx.arguments.get("total_account_budget"),
                "planned_persona_count": ctx.arguments.get("planned_persona_count"),
                "product_id": ctx.arguments.get("product_id"),
                "cta_definition": ctx.arguments.get("cta_definition"),
                "bind_notification_conversation": ctx.arguments.get(
                    "bind_notification_conversation"
                ),
                "config": ctx.arguments.get("config"),
            }
        ),
    )


async def _execute_campaign_update(ctx: CommandContext) -> Any:
    campaign_id = str(ctx.arguments.get("campaign_id") or "")
    expected_version = await _current_campaign_version(ctx, campaign_id)
    body = {
        "workspace_id": ctx.workspace_id,
        "expected_version": expected_version,
    }
    body.update(
        {
            key: value
            for key, value in ctx.arguments.items()
            if key
            in {
                "name",
                "total_account_budget",
                "planned_persona_count",
                "cta_definition",
                "product_id",
                "config",
                "required_hashtags",
                "required_mentions",
                "preferred_publish_windows",
                "bind_notification_conversation",
            }
        }
    )
    return await ctx.api_data_v2(
        ctx.cfg,
        "PATCH",
        f"/agentic-creative-campaigns/{campaign_id}",
        json_body=body,
    )


async def _execute_plan_update(ctx: CommandContext) -> Any:
    campaign_id, plan, _ = await _locate_plan(ctx)
    if plan.get("version") is None:
        raise RuntimeError("agentic persona plan did not include its current version")
    body = {
        "workspace_id": ctx.workspace_id,
        "expected_version": plan["version"],
    }
    body.update(
        {
            key: value
            for key, value in ctx.arguments.items()
            if key
            in {
                "name",
                "account_budget",
                "required_hashtags",
                "required_mentions",
            }
        }
    )
    return await ctx.api_data_v2(
        ctx.cfg,
        "PATCH",
        (f"/agentic-creative-campaigns/{campaign_id}/agentic-persona-plans/{plan['id']}"),
        json_body=body,
    )


async def _execute_plan_create(ctx: CommandContext) -> Any:
    campaign_id = str(ctx.arguments.get("campaign_id") or "")
    return await ctx.api_data_v2(
        ctx.cfg,
        "POST",
        f"/agentic-creative-campaigns/{campaign_id}/agentic-persona-plans",
        json_body={
            "workspace_id": ctx.workspace_id,
            "name": ctx.arguments.get("name"),
            "account_budget": ctx.arguments.get("account_budget"),
        },
    )


async def _current_campaign_version(ctx: CommandContext, campaign_id: str) -> int:
    detail = _payload_data(await _detail(ctx, campaign_id))
    campaign = detail.get("campaign") if isinstance(detail, dict) else None
    if not isinstance(campaign, dict) or campaign.get("version") is None:
        raise RuntimeError("campaign detail did not include its current version")
    return campaign["version"]


async def _execute_campaign_lifecycle(ctx: CommandContext, *, action: str) -> Any:
    campaign_id = str(ctx.arguments.get("campaign_id") or "")
    expected_version = await _current_campaign_version(ctx, campaign_id)
    return await ctx.api_data_v2(
        ctx.cfg,
        "POST",
        f"/agentic-creative-campaigns/{campaign_id}/{action}",
        json_body={
            "workspace_id": ctx.workspace_id,
            "expected_version": expected_version,
        },
    )


async def _execute_campaign_activate(ctx: CommandContext) -> Any:
    return await _execute_campaign_lifecycle(ctx, action="activate")


async def _execute_campaign_pause(ctx: CommandContext) -> Any:
    return await _execute_campaign_lifecycle(ctx, action="pause")


async def _execute_campaign_archive(ctx: CommandContext) -> Any:
    return await _execute_campaign_lifecycle(ctx, action="archive")


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
    "agentic-campaign.campaign-activate": redacted_direct_enveloped(
        _execute_campaign_activate, redact_api_errors=True
    ),
    "agentic-campaign.campaign-archive": redacted_direct_enveloped(
        _execute_campaign_archive, redact_api_errors=True
    ),
    "agentic-campaign.campaign-create": redacted_direct_enveloped(
        _execute_campaign_create, redact_api_errors=True
    ),
    "agentic-campaign.campaign-update": redacted_direct_enveloped(
        _execute_campaign_update, redact_api_errors=True
    ),
    "agentic-campaign.campaign-pause": redacted_direct_enveloped(
        _execute_campaign_pause, redact_api_errors=True
    ),
    "agentic-campaign.campaign-rename": redacted_direct_enveloped(
        _execute_campaign_rename, redact_api_errors=True
    ),
    "agentic-campaign.get": redacted_direct_enveloped(_execute_get, redact_api_errors=True),
    "agentic-campaign.issues-pull": redacted_direct_enveloped(
        _execute_issues_pull, redact_api_errors=True
    ),
    "agentic-campaign.list": redacted_direct_enveloped(_execute_list, redact_api_errors=True),
    "agentic-campaign.plan-attribution": redacted_direct_enveloped(
        _execute_plan_attribution, redact_api_errors=True
    ),
    "agentic-campaign.plan-create": redacted_direct_enveloped(
        _execute_plan_create, redact_api_errors=True
    ),
    "agentic-campaign.plan-get": redacted_direct_enveloped(
        _execute_plan_get, redact_api_errors=True
    ),
    "agentic-campaign.plan-list": redacted_direct_enveloped(
        _execute_plan_list, redact_api_errors=True
    ),
    "agentic-campaign.plan-update": redacted_direct_enveloped(
        _execute_plan_update, redact_api_errors=True
    ),
    "agentic-campaign.plan-propose": redacted_direct_enveloped(
        _execute_plan_propose, redact_api_errors=True
    ),
    "agentic-campaign.proposal-get": redacted_direct_enveloped(
        _execute_proposal_get, redact_api_errors=True
    ),
    "agentic-campaign.proposal-withdraw": redacted_direct_enveloped(
        _execute_proposal_withdraw, redact_api_errors=True
    ),
    "agentic-campaign.plan-tags": redacted_direct_enveloped(
        _execute_plan_tags, redact_api_errors=True
    ),
}
