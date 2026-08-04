"""Agentic Creative Campaign commands backed by the public v2 API."""

from __future__ import annotations

import argparse
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

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


def _add_overview_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--page-size", type=int, default=20)


def _build_overview_arguments(args: argparse.Namespace) -> dict[str, Any]:
    if args.page < 1 or args.page_size < 1:
        raise ValueError("--page and --page-size must be positive")
    return {"page": args.page, "page_size": args.page_size}


def _add_recap_arguments(parser: argparse.ArgumentParser) -> None:
    _add_campaign_id_arguments(parser)
    parser.add_argument("--cells", action="store_true")


def _build_recap_arguments(args: argparse.Namespace) -> dict[str, Any]:
    return {"campaign_id": args.campaign_id, "include_cells": args.cells}


def _add_campaign_id_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--id", dest="campaign_id", required=True)


def _build_campaign_id_arguments(args: argparse.Namespace) -> dict[str, Any]:
    return {"campaign_id": args.campaign_id}


def _add_plan_id_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--plan-id", required=True)


def _build_plan_id_arguments(args: argparse.Namespace) -> dict[str, Any]:
    return {"plan_id": args.plan_id}


def _add_proposal_create_arguments(parser: argparse.ArgumentParser) -> None:
    """Primary and only Proposal creation command surface."""

    _add_plan_id_arguments(parser)
    parser.add_argument("--note")
    parser.add_argument("--name")
    parser.add_argument("--title")
    parser.add_argument("--persona-json")
    parser.add_argument("--persona-id")
    parser.add_argument("--elements-json")
    parser.add_argument("--add-elements-json")
    parser.add_argument("--retire-element-ids")
    parser.add_argument("--boost-elements-json")
    parser.add_argument("--replace-persona-json")
    parser.add_argument("--replace-persona-id")
    parser.add_argument("--persona-patch-json")
    parser.add_argument(
        "--rollout-coverage-mode",
        choices=["existing-future-all", "future-window"],
        default=None,
    )
    parser.add_argument("--rollout-days", type=int, default=None)
    parser.add_argument("--rationale", default=None)
    parser.add_argument("--dry-run", action="store_true")


def _add_proposal_revise_arguments(parser: argparse.ArgumentParser) -> None:
    _add_plan_id_arguments(parser)
    parser.add_argument("--proposal-id", required=True)
    parser.add_argument("--note")
    parser.add_argument("--elements-json")
    parser.add_argument("--add-elements-json")
    parser.add_argument("--retire-element-ids")
    parser.add_argument("--boost-elements-json")
    parser.add_argument("--replace-persona-json")
    parser.add_argument("--replace-persona-id")
    parser.add_argument("--persona-patch-json")
    parser.add_argument(
        "--rollout-coverage-mode",
        choices=["existing-future-all", "future-window"],
        default=None,
    )
    parser.add_argument("--rollout-days", type=int, default=None)
    parser.add_argument("--rationale", default=None)
    parser.add_argument("--dry-run", action="store_true")


def _add_proposal_reallocate_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--plan-id", required=True)
    parser.add_argument("--count", type=int, required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--from-plan")
    source.add_argument("--from-pool", action="store_true")
    parser.add_argument("--rationale")
    parser.add_argument("--dry-run", action="store_true")


def _add_proposal_list_arguments(parser: argparse.ArgumentParser) -> None:
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--plan-id")
    scope.add_argument("--campaign-id")
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--page-size", type=int, default=20)
    parser.add_argument("--include-draft-stage", action="store_true")
    parser.add_argument(
        "--status",
        action="append",
        choices=["awaiting-review", "confirmed", "dismissed", "superseded"],
    )
    parser.add_argument("--awaiting-review", action="store_true")


def _add_plan_members_reconcile_arguments(parser: argparse.ArgumentParser) -> None:
    _add_plan_id_arguments(parser)
    parser.add_argument("--account-ids", required=True)
    parser.add_argument("--dry-run", action="store_true")


def _add_proposal_get_arguments(parser: argparse.ArgumentParser) -> None:
    _add_plan_id_arguments(parser)
    parser.add_argument("--proposal-id", required=True)


def _build_proposal_get_arguments(args: argparse.Namespace) -> dict[str, Any]:
    return {"plan_id": args.plan_id, "proposal_id": args.proposal_id}


def _schedule_rollout_testing_plan(value: str | None) -> dict[str, Any]:
    if value is None:
        return {"strategy": "balanced_exploration", "overrides": []}
    parsed = _candidate_json(value, field="testing-plan", expected_type=dict)
    if set(parsed) - {"strategy", "overrides"}:
        raise ValueError("testing-plan only accepts strategy and overrides.")
    if parsed.get("strategy") != "balanced_exploration":
        raise ValueError("testing-plan strategy must be balanced_exploration.")
    overrides = parsed.get("overrides")
    if not isinstance(overrides, list):
        raise ValueError("testing-plan overrides must be a JSON array.")
    return {"strategy": "balanced_exploration", "overrides": overrides}


def _schedule_rollout_coverage(args: argparse.Namespace) -> dict[str, Any]:
    mode = str(args.coverage).replace("-", "_")
    days = args.days
    if mode == "future_window" and days is None:
        raise ValueError("--coverage future-window requires --days 1..30.")
    if mode == "existing_future_all" and days is not None:
        raise ValueError("--days is only valid with --coverage future-window.")
    if days is not None and not 1 <= days <= 30:
        raise ValueError("--days must be between 1 and 30.")
    return {"mode": mode, "timezone": args.timezone, "days": days}


def _proposal_rollout_intent(args: argparse.Namespace) -> dict[str, Any] | None:
    mode_raw = getattr(args, "rollout_coverage_mode", None)
    days = getattr(args, "rollout_days", None)
    if mode_raw is None:
        if days is not None:
            raise ValueError(
                "--rollout-days requires --rollout-coverage-mode future-window."
            )
        return None
    mode = mode_raw.replace("-", "_")
    if mode == "future_window" and days is None:
        raise ValueError(
            "--rollout-coverage-mode future-window requires --rollout-days 1..30."
        )
    if mode == "existing_future_all" and days is not None:
        raise ValueError(
            "--rollout-days is only valid with --rollout-coverage-mode future-window."
        )
    if days is not None and not 1 <= days <= 30:
        raise ValueError("--rollout-days must be between 1 and 30.")
    return {"coverage": {"mode": mode, "days": days}, "version": 1}


def _add_schedule_rollout_preflight_arguments(parser: argparse.ArgumentParser) -> None:
    _add_plan_id_arguments(parser)
    parser.add_argument("--proposal-id", required=True)
    parser.add_argument(
        "--coverage",
        choices=["existing-future-all", "future-window"],
        default="existing-future-all",
    )
    parser.add_argument("--days", type=int)
    parser.add_argument("--timezone", default="Asia/Shanghai")
    parser.add_argument("--testing-plan-json", default=None)


def _build_schedule_rollout_preflight_arguments(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "plan_id": args.plan_id,
        "proposal_id": args.proposal_id,
        "coverage": _schedule_rollout_coverage(args),
        "testing_plan": _schedule_rollout_testing_plan(args.testing_plan_json),
    }


def _add_confirm_schedule_rollout_arguments(parser: argparse.ArgumentParser) -> None:
    _add_schedule_rollout_preflight_arguments(parser)
    parser.add_argument("--idempotency-key", required=True)
    parser.add_argument("--dry-run", action="store_true")


def _build_confirm_schedule_rollout_arguments(args: argparse.Namespace) -> dict[str, Any]:
    payload = _build_schedule_rollout_preflight_arguments(args)
    payload["idempotency_key"] = args.idempotency_key
    payload["dry_run"] = args.dry_run
    return payload


def _add_schedule_rollout_get_arguments(parser: argparse.ArgumentParser) -> None:
    _add_plan_id_arguments(parser)
    selector = parser.add_mutually_exclusive_group(required=True)
    selector.add_argument("--rollout-id")
    selector.add_argument("--proposal-id")


def _build_schedule_rollout_get_arguments(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "plan_id": args.plan_id,
        "rollout_id": args.rollout_id,
        "proposal_id": args.proposal_id,
    }


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


def _retire_element_ids(value: str | None) -> list[str] | None:
    if value is None:
        return None
    stripped = value.strip()
    if stripped.startswith("["):
        parsed = _candidate_json(stripped, field="retire-element-ids", expected_type=list)
        if not all(isinstance(item, str) and item.strip() for item in parsed):
            raise ValueError("retire-element-ids must be a JSON array of ids")
        return [item.strip() for item in parsed]
    return _csv(value)


def _proposal_persona_operation(args: argparse.Namespace) -> dict[str, Any]:
    sources = [
        ("replace-persona-id", args.replace_persona_id),
        ("replace-persona-json", args.replace_persona_json),
        ("persona-patch-json", args.persona_patch_json),
    ]
    supplied = [(name, value) for name, value in sources if value is not None]
    if len(supplied) > 1:
        raise ValueError(
            "--replace-persona-id, --replace-persona-json, and --persona-patch-json "
            "are mutually exclusive."
        )
    if not supplied:
        return {}
    name, value = supplied[0]
    if name == "replace-persona-id":
        return {"persona": {"persona_id": value}}
    if name == "replace-persona-json":
        return {
            "persona": {
                "persona_payload": _candidate_json(value, field="replace-persona", expected_type=dict)
            }
        }
    return {
        "patch_persona_payload": _candidate_json(
            value, field="persona-patch", expected_type=dict
        )
    }


def _build_proposal_create_arguments(args: argparse.Namespace) -> dict[str, Any]:
    complete_persona_sources = [
        value for value in (args.persona_id, args.persona_json) if value is not None
    ]
    if len(complete_persona_sources) > 1:
        raise ValueError("--persona-id and --persona-json are mutually exclusive.")
    persona_operation = _proposal_persona_operation(args)
    complete_supplied = args.name is not None or args.elements_json is not None
    atomic_supplied = any(
        value is not None
        for value in (
            args.add_elements_json,
            args.retire_element_ids,
            args.boost_elements_json,
        )
    ) or bool(persona_operation)
    if complete_supplied and atomic_supplied:
        raise ValueError("a Proposal is either a complete draft solution or atomic active changes")
    if complete_supplied:
        if args.name is None or args.elements_json is None or not complete_persona_sources:
            raise ValueError(
                "a complete draft Proposal requires --name, --elements-json, and exactly one "
                "of --persona-id or --persona-json"
            )
        if args.title is not None:
            raise ValueError("--title is only valid for an active-plan Proposal")
        persona = (
            {"persona_id": args.persona_id}
            if args.persona_id is not None
            else {"persona_payload": _candidate_json(args.persona_json, field="persona", expected_type=dict)}
        )
        return {
            "plan_id": args.plan_id,
            "name": args.name,
            **persona,
            "elements": _candidate_json(args.elements_json, field="elements", expected_type=list),
            "note": args.note,
            "rationale": args.rationale,
            "rollout_intent": _proposal_rollout_intent(args),
            "dry_run": args.dry_run,
        }
    if not atomic_supplied:
        raise ValueError("an active-plan Proposal requires at least one atomic change")
    changes = compact_params(
        {
            "add_elements": (
                _revision_json_list(args.add_elements_json, field="add-elements")
                if args.add_elements_json is not None
                else None
            ),
            "retire_element_ids": _retire_element_ids(args.retire_element_ids),
            "boost_elements": (
                _revision_json_list(args.boost_elements_json, field="boost-elements")
                if args.boost_elements_json is not None
                else None
            ),
            **persona_operation,
        }
    )
    return compact_params(
        {
            "plan_id": args.plan_id,
            "title": args.title,
            "changes": changes,
            "note": args.note,
            "rationale": args.rationale,
            "rollout_intent": _proposal_rollout_intent(args),
            "dry_run": args.dry_run,
        }
    )


def _build_proposal_revise_arguments(args: argparse.Namespace) -> dict[str, Any]:
    if args.elements_json is not None and args.add_elements_json is not None:
        raise ValueError("--elements-json and --add-elements-json are mutually exclusive.")
    persona_operation = _proposal_persona_operation(args)
    changes = compact_params(
        {
            "add_elements": (
                _revision_json_list(
                    args.elements_json if args.elements_json is not None else args.add_elements_json,
                    field="elements" if args.elements_json is not None else "add-elements",
                )
                if args.elements_json is not None or args.add_elements_json is not None
                else None
            ),
            "retire_element_ids": _retire_element_ids(args.retire_element_ids),
            "boost_elements": (
                _revision_json_list(args.boost_elements_json, field="boost-elements")
                if args.boost_elements_json is not None
                else None
            ),
            **persona_operation,
        }
    )
    if not changes:
        raise ValueError("a Proposal revision requires at least one named change")
    return {
        "plan_id": args.plan_id,
        "proposal_id": args.proposal_id,
        "changes": changes,
        "note": args.note,
        "rationale": args.rationale,
        "rollout_intent": _proposal_rollout_intent(args),
        "dry_run": args.dry_run,
    }


def _build_proposal_reallocate_arguments(args: argparse.Namespace) -> dict[str, Any]:
    if args.count < 1:
        raise ValueError("--count must be at least 1.")
    source: dict[str, Any] = (
        {"plan_id": args.from_plan} if args.from_plan else {"pool": True}
    )
    return compact_params(
        {
            "campaign_id": args.campaign_id,
            "plan_id": args.plan_id,
            "changes": {
                "reallocate_accounts": {
                    "count": args.count,
                    "from": source,
                }
            },
            "rationale": args.rationale,
            "dry_run": args.dry_run,
        }
    )


def _build_proposal_list_arguments(args: argparse.Namespace) -> dict[str, Any]:
    if args.page < 1 or args.page_size < 1:
        raise ValueError("--page and --page-size must be positive")
    statuses = list(args.status or [])
    if args.awaiting_review and "awaiting-review" not in statuses:
        statuses.append("awaiting-review")
    return {
        "plan_id": args.plan_id,
        "campaign_id": args.campaign_id,
        "page": args.page,
        "page_size": args.page_size,
        "include_draft_stage": args.include_draft_stage,
        "status": [value.replace("-", "_") for value in statuses] or None,
    }


def _build_plan_members_reconcile_arguments(args: argparse.Namespace) -> dict[str, Any]:
    account_ids = _candidate_json(args.account_ids, field="account-ids", expected_type=list)
    if not all(isinstance(item, str) and item.strip() for item in account_ids):
        raise ValueError("account-ids must be a JSON array of account ids")
    return {
        "plan_id": args.plan_id,
        "target_account_ids": list(dict.fromkeys(item.strip() for item in account_ids)),
        "dry_run": args.dry_run,
    }


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
            "an active-plan Proposal adjustment requires at least one of "
            "persona, patch_persona_payload, add_elements, retire_element_ids, "
            "or boost_elements."
        )
    return changes


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
    parser.add_argument("--direction-brief", default=None)
    parser.add_argument("--success-hypothesis", default=None)
    parser.add_argument("--contract", default=None)
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
            "direction_brief": args.direction_brief,
            "success_hypothesis": args.success_hypothesis,
            "contract": args.contract,
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


def _add_learning_add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--claim", required=True)
    parser.add_argument("--confidence", choices=["low", "medium", "high"], default=None)
    parser.add_argument(
        "--scope-json",
        default=None,
        help="Optional JSON object narrowing what this learning applies to.",
    )
    parser.add_argument(
        "--evidence-json",
        default=None,
        help="Optional JSON object citing the evidence behind this learning.",
    )
    parser.add_argument("--dry-run", action="store_true")


def _build_learning_add_arguments(args: argparse.Namespace) -> dict[str, Any]:
    claim = args.claim.strip() if args.claim else ""
    if not claim:
        raise ValueError("--claim must not be empty.")
    return compact_params(
        {
            "campaign_id": args.campaign_id,
            "claim": claim,
            "confidence": args.confidence,
            "scope": (
                _candidate_json(args.scope_json, field="scope", expected_type=dict)
                if args.scope_json is not None
                else None
            ),
            "evidence": (
                _candidate_json(args.evidence_json, field="evidence", expected_type=dict)
                if args.evidence_json is not None
                else None
            ),
            "dry_run": args.dry_run,
        }
    )


def _add_issue_open_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--kind", choices=["reset", "evolution", "strategy"], required=True)
    parser.add_argument("--note", default=None)
    parser.add_argument(
        "--scope-json",
        default=None,
        help=(
            "Optional JSON object narrowing the issue's scope, "
            '{"plan_ids": [...], "account_ids": [...]}.'
        ),
    )
    parser.add_argument("--dry-run", action="store_true")


def _build_issue_open_arguments(args: argparse.Namespace) -> dict[str, Any]:
    scope: dict[str, Any] | None = None
    if args.scope_json is not None:
        scope = _candidate_json(args.scope_json, field="scope", expected_type=dict)
        unknown = set(scope) - {"plan_ids", "account_ids"}
        if unknown:
            raise ValueError(
                f"--scope-json only accepts plan_ids and account_ids, got: {sorted(unknown)}"
            )
    return compact_params(
        {
            "campaign_id": args.campaign_id,
            "kind": args.kind,
            "note": args.note,
            "scope": scope,
            "dry_run": args.dry_run,
        }
    )


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


def _proposal_list_input_schema() -> dict[str, Any]:
    schema = _schema(
        {
            "plan_id": _uuid_property("Agentic Persona Plan id"),
            "campaign_id": _uuid_property("Agentic Creative Campaign id"),
            "page": {"type": "integer", "minimum": 1, "default": 1},
            "page_size": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
            "include_draft_stage": {"type": "boolean", "default": False},
            "status": {
                "type": "array",
                "items": {
                    "enum": ["awaiting-review", "confirmed", "dismissed", "superseded"],
                    "type": "string",
                },
            },
            "awaiting_review": {"type": "boolean", "default": False},
        }
    )
    schema["oneOf"] = [
        {"required": ["plan_id"], "not": {"required": ["campaign_id"]}},
        {"required": ["campaign_id"], "not": {"required": ["plan_id"]}},
    ]
    return schema


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


def _proposal_create_input_schema() -> dict[str, Any]:
    schema = _plan_schema(
        {
            "name": {"type": "string", "minLength": 1, "maxLength": 80},
            "title": {"type": "string", "minLength": 1, "maxLength": 80},
            "persona_id": _uuid_property("Persona for a complete draft Proposal"),
            "persona_payload": _persona_payload_schema(),
            "elements": _candidate_elements_schema(),
            "changes": {
                "type": "object",
                "minProperties": 1,
                "additionalProperties": False,
                "properties": {
                    "add_elements": _revision_add_elements_schema(),
                    "retire_element_ids": {
                        "type": "array",
                        "items": _uuid_property("Active Plan element id"),
                    },
                    "boost_elements": _revision_boosts_schema(),
                    "persona": {"type": "object"},
                    "patch_persona_payload": {"type": "object"},
                },
            },
            "note": {"type": ["string", "null"], "maxLength": 2000},
            "rationale": {"type": ["string", "null"]},
            "rollout_intent": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "coverage": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "mode": {"enum": ["existing_future_all", "future_window"]},
                            "days": {
                                "type": ["integer", "null"],
                                "minimum": 1,
                                "maximum": 30,
                            },
                        },
                        "required": ["mode"],
                    },
                    "version": {"const": 1},
                },
                "required": ["coverage", "version"],
            },
            "dry_run": {"type": "boolean", "default": False},
        }
    )
    schema["oneOf"] = [
        {
            "title": "Complete Draft Plan Proposal",
            "required": ["name", "elements"],
            "oneOf": [
                {"required": ["persona_id"], "not": {"required": ["persona_payload"]}},
                {"required": ["persona_payload"], "not": {"required": ["persona_id"]}},
            ],
            "not": {"anyOf": [{"required": ["title"]}, {"required": ["changes"]}]},
        },
        {
            "title": "Atomic Active Plan Proposal",
            "required": ["changes"],
            "not": {
                "anyOf": [
                    {"required": ["name"]},
                    {"required": ["persona_id"]},
                    {"required": ["persona_payload"]},
                    {"required": ["elements"]},
                ]
            },
        },
    ]
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
            shortcut="+schedule-rollout-preflight",
            summary=(
                "Always run this read-only command before first confirming one specified "
                "awaiting-review proposal, and rerun it whenever coverage or testing overrides "
                "change. It returns the exact schedule-rollout matrix the operator must review "
                "before applying. The proposal does not need to be the Plan's newest: independent "
                "active-Plan proposals can be confirmed in any order. Includes winner boost "
                "placements. A boost reserves visible target-account slots; if the response is "
                "coverage_days_required because existing future slots cannot fulfil its days, rerun "
                "with --coverage future-window --days 1..30. Future slots follow the campaign "
                "preferred publish windows. A confirmed proposal can only be inspected or retried; "
                "use +schedule-rollout-get for its persisted rollout. Dismissed or superseded "
                "proposals are rejected."
            ),
            risk_level="read",
            execution="direct",
            adapter_tool_name="agentic_campaign_schedule_rollout_preflight",
            input_schema=_plan_schema(
                {
                    "proposal_id": _uuid_property(
                        "Exact revision proposal id. First confirmation requires awaiting_review; "
                        "it need not be the newest proposal on the Plan. A confirmed proposal may "
                        "be inspected, but +schedule-rollout-get reads its persisted rollout."
                    ),
                    "coverage": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "mode": {"enum": ["existing_future_all", "future_window"]},
                            "timezone": {"type": "string", "minLength": 1, "maxLength": 100},
                            "days": {"type": ["integer", "null"], "minimum": 1, "maximum": 30},
                        },
                        "required": ["mode", "timezone"],
                    },
                    "testing_plan": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "strategy": {"const": "balanced_exploration"},
                            "overrides": {"type": "array", "maxItems": 500},
                        },
                        "required": ["strategy", "overrides"],
                    },
                },
                required=["proposal_id", "coverage", "testing_plan"],
            ),
            output_schema=_direct_output_schema(
                "Read-only rollout preview: target slots, seed bindings, regular generation "
                "count, failed elements, and coverage_days_required when future slots must be "
                "created."
            ),
            examples=[
                "museoncli agentic-campaign +schedule-rollout-preflight "
                "--plan-id 33333333-3333-4333-8333-333333333333 "
                "--proposal-id 77777777-7777-4777-8777-777777777777 --timezone Asia/Shanghai",
                "museoncli agentic-campaign +schedule-rollout-preflight "
                "--plan-id 33333333-3333-4333-8333-333333333333 "
                "--proposal-id 77777777-7777-4777-8777-777777777777 "
                "--coverage future-window --days 7 --timezone Asia/Shanghai",
            ],
            add_arguments=_add_schedule_rollout_preflight_arguments,
            build_arguments=_build_schedule_rollout_preflight_arguments,
        ),
        CommandSpec(
            domain=domain,
            shortcut="+confirm-schedule-rollout",
            summary=(
                "After a ready +schedule-rollout-preflight for the same proposal, coverage, and "
                "testing plan, atomically apply one specified awaiting-review proposal (there is "
                "no separate approval command), persist its immutable schedule-rollout intent "
                "including visible winner boost placements, and dispatch asynchronous execution. "
                "The proposal need not be newest: independent active-Plan proposals can be "
                "confirmed in any order; confirming a competitive whole-plan alternative dismisses "
                "the other awaiting-review alternatives. Reuse the same idempotency key to retry a "
                "confirmed proposal's existing rollout; dismissed or superseded proposals are "
                "rejected. Poll +schedule-rollout-get after the 202 response."
            ),
            risk_level="write",
            execution="direct",
            adapter_tool_name="agentic_campaign_confirm_schedule_rollout",
            input_schema=_plan_schema(
                {
                    "proposal_id": _uuid_property(
                        "Exact awaiting-review revision proposal id to apply. It need not be the "
                        "newest Plan proposal. A confirmed id only retries its existing durable rollout; "
                        "dismissed and superseded ids are rejected."
                    ),
                    "coverage": {"type": "object"},
                    "testing_plan": {"type": "object"},
                    "idempotency_key": {"type": "string", "minLength": 8, "maxLength": 240},
                    "dry_run": {"type": "boolean", "default": False},
                },
                required=["proposal_id", "coverage", "testing_plan", "idempotency_key"],
            ),
            output_schema=_direct_output_schema(
                "202-accepted durable rollout id and current state; use +schedule-rollout-get "
                "until terminal."
            ),
            examples=[
                "museoncli agentic-campaign +confirm-schedule-rollout "
                "--plan-id 33333333-3333-4333-8333-333333333333 "
                "--proposal-id 77777777-7777-4777-8777-777777777777 "
                "--timezone Asia/Shanghai --idempotency-key rollout-20260801-001"
            ],
            add_arguments=_add_confirm_schedule_rollout_arguments,
            build_arguments=_build_confirm_schedule_rollout_arguments,
            supports_dry_run=True,
        ),
        CommandSpec(
            domain=domain,
            shortcut="+schedule-rollout-get",
            summary=(
                "Read durable schedule-rollout status by rollout id or confirmed proposal id. "
                "Use this after +confirm-schedule-rollout's 202 response to inspect immutable "
                "assignments, seed bindings, and asynchronous progress."
            ),
            risk_level="read",
            execution="direct",
            adapter_tool_name="agentic_campaign_schedule_rollout_get",
            input_schema=_plan_schema(
                {
                    "rollout_id": {"type": "string", "format": "uuid"},
                    "proposal_id": {"type": "string", "format": "uuid"},
                }
            ),
            output_schema=_direct_output_schema(
                "Durable rollout state, immutable coverage/testing assignments, seed bindings, "
                "and execution progress."
            ),
            examples=[
                "museoncli agentic-campaign +schedule-rollout-get "
                "--plan-id 33333333-3333-4333-8333-333333333333 "
                "--rollout-id 88888888-8888-4888-8888-888888888888"
            ],
            add_arguments=_add_schedule_rollout_get_arguments,
            build_arguments=_build_schedule_rollout_get_arguments,
        ),
        CommandSpec(
            domain=domain,
            shortcut="+members-reconcile",
            resource="plan",
            summary=(
                "Atomically reconcile a Plan's managed accounts and matching Plan budget. "
                "The CLI reads current versions, raises Campaign total budget only when required, "
                "and submits the member/budget change as one compare-and-swap operation."
            ),
            risk_level="write",
            execution="direct",
            adapter_tool_name="agentic_campaign_plan_members_reconcile",
            input_schema=_plan_schema(
                {
                    "target_account_ids": {
                        "type": "array",
                        "maxItems": 500,
                        "items": _uuid_property("Managed social account id"),
                    },
                    "dry_run": {"type": "boolean", "default": False},
                },
                required=["target_account_ids"],
            ),
            output_schema=_direct_output_schema(
                "Reconciled member list, Plan budget, Campaign total budget, and new versions."
            ),
            examples=[
                "museoncli agentic-campaign plan +members-reconcile "
                "--plan-id 33333333-3333-4333-8333-333333333333 "
                "--account-ids '[\"44444444-4444-4444-8444-444444444444\","
                "\"55555555-5555-4555-8555-555555555555\"]'",
            ],
            add_arguments=_add_plan_members_reconcile_arguments,
            build_arguments=_build_plan_members_reconcile_arguments,
            supports_dry_run=True,
        ),
        CommandSpec(
            domain=domain,
            shortcut="+create",
            resource="proposal",
            summary=(
                "Create one operator-review Proposal. Draft Plans require a complete Persona "
                "and element selection; active Plans accept named atomic changes."
            ),
            risk_level="write",
            execution="direct",
            adapter_tool_name="agentic_campaign_proposal_create",
            input_schema=_proposal_create_input_schema(),
            output_schema=_direct_output_schema(
                "Proposal id, change summary, and operator review reminder."
            ),
            examples=[
                "museoncli agentic-campaign proposal +create "
                "--plan-id 33333333-3333-4333-8333-333333333333 "
                "--name 'DIY problem solver' --persona-id 99999999-9999-4999-8999-999999999999 "
                "--elements-json '[{\"format_id\":\"44444444-4444-4444-8444-444444444444\","
                "\"topic_id\":\"55555555-5555-4555-8555-555555555555\"}]'",
                "museoncli agentic-campaign proposal +create "
                "--plan-id 33333333-3333-4333-8333-333333333333 "
                "--title 'Dark-tone second test batch' "
                "--add-elements-json '[{\"format_id\":\"44444444-4444-4444-8444-444444444444\","
                "\"topic_id\":\"55555555-5555-4555-8555-555555555555\"}]'",
            ],
            add_arguments=_add_proposal_create_arguments,
            build_arguments=_build_proposal_create_arguments,
            supports_dry_run=True,
        ),
        CommandSpec(
            domain=domain,
            shortcut="+list",
            resource="proposal",
            summary=(
                "List Proposals for exactly one Plan or all Plans in one Campaign. "
                "Campaign scope returns each Proposal's Plan and Persona summary."
            ),
            risk_level="read",
            execution="direct",
            adapter_tool_name="agentic_campaign_proposal_list",
            input_schema=_proposal_list_input_schema(),
            output_schema=_direct_output_schema(
                "Paginated Proposal list for one Plan or Campaign. Every item includes its "
                "canonical proposal_url; forward it exactly as returned."
            ),
            examples=[
                "museoncli agentic-campaign proposal +list "
                "--plan-id 33333333-3333-4333-8333-333333333333",
                "museoncli agentic-campaign proposal +list "
                "--campaign-id 22222222-2222-4222-8222-222222222222 --awaiting-review",
            ],
            add_arguments=_add_proposal_list_arguments,
            build_arguments=_build_proposal_list_arguments,
        ),
        CommandSpec(
            domain=domain,
            shortcut="+reallocate",
            resource="proposal",
            summary=(
                "Create an allocation Proposal that moves managed accounts into this Plan, "
                "either from another Plan in the same Campaign or from the recruitable "
                "account pool. The server validates eligibility (pool sourcing requires "
                "policy.auto_recruit, the target Plan must be active, and this cannot be "
                "mixed with content changes) and returns a normal awaiting-review Proposal."
            ),
            risk_level="write",
            execution="direct",
            adapter_tool_name="agentic_campaign_proposal_reallocate",
            input_schema=_schema(
                {
                    "campaign_id": _uuid_property("Agentic Creative Campaign id"),
                    "plan_id": _uuid_property("Target Persona Plan id, the Proposal's anchor"),
                    "changes": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "reallocate_accounts": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "count": {"type": "integer", "minimum": 1},
                                    "from": {
                                        "type": "object",
                                        "description": "Exactly one of plan_id or pool.",
                                        "additionalProperties": False,
                                        "properties": {
                                            "plan_id": _uuid_property(
                                                "Source Persona Plan id in the same Campaign"
                                            ),
                                            "pool": {"const": True},
                                        },
                                    },
                                },
                                "required": ["count", "from"],
                            },
                        },
                        "required": ["reallocate_accounts"],
                    },
                    "rationale": {"type": ["string", "null"]},
                    "dry_run": {"type": "boolean", "default": False},
                },
                required=["campaign_id", "plan_id", "changes"],
            ),
            output_schema=_direct_output_schema(
                "Created allocation Proposal id, number, canonical proposal_url, and change summary."
            ),
            examples=[
                "museoncli agentic-campaign proposal +reallocate "
                "--campaign-id 22222222-2222-4222-8222-222222222222 "
                "--plan-id 33333333-3333-4333-8333-333333333333 "
                "--count 2 --from-plan 44444444-4444-4444-8444-444444444444",
                "museoncli agentic-campaign proposal +reallocate "
                "--campaign-id 22222222-2222-4222-8222-222222222222 "
                "--plan-id 33333333-3333-4333-8333-333333333333 "
                "--count 3 --from-pool --rationale ramp-up-winner-plan",
            ],
            add_arguments=_add_proposal_reallocate_arguments,
            build_arguments=_build_proposal_reallocate_arguments,
            supports_dry_run=True,
        ),
        CommandSpec(
            domain=domain,
            shortcut="+revise",
            resource="proposal",
            summary=(
                "Revise an open Proposal after operator feedback. Each supplied atomic field "
                "replaces that field's current proposed value; omit fields to preserve them."
            ),
            risk_level="write",
            execution="direct",
            adapter_tool_name="agentic_campaign_proposal_revise",
            input_schema=_plan_schema(
                {
                    "proposal_id": _uuid_property("Open Proposal id"),
                    "changes": {
                        "type": "object",
                        "minProperties": 1,
                        "additionalProperties": False,
                        "properties": {
                            "add_elements": _revision_add_elements_schema(),
                            "retire_element_ids": {
                                "type": "array",
                                "items": _uuid_property("Active Plan element id"),
                            },
                            "boost_elements": _revision_boosts_schema(),
                            "persona": {"type": "object"},
                            "patch_persona_payload": {"type": "object"},
                        },
                    },
                    "note": {"type": ["string", "null"], "maxLength": 2000},
                    "rationale": {"type": ["string", "null"]},
                    "rollout_intent": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "coverage": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "mode": {
                                        "enum": ["existing_future_all", "future_window"]
                                    },
                                    "days": {
                                        "type": ["integer", "null"],
                                        "minimum": 1,
                                        "maximum": 30,
                                    },
                                },
                                "required": ["mode"],
                            },
                            "version": {"const": 1},
                        },
                        "required": ["coverage", "version"],
                    },
                    "dry_run": {"type": "boolean", "default": False},
                },
                required=["proposal_id", "changes"],
            ),
            output_schema=_direct_output_schema(
                "Next Proposal revision round and canonical proposal_url. Forward proposal_url exactly "
                "as returned; never construct a link."
            ),
            examples=[
                "museoncli agentic-campaign proposal +revise "
                "--plan-id 33333333-3333-4333-8333-333333333333 "
                "--proposal-id 77777777-7777-4777-8777-777777777777 "
                "--retire-element-ids '[\"88888888-8888-4888-8888-888888888888\"]' "
                "--boost-elements-json '[{\"element_id\":\"99999999-9999-4999-8999-999999999999\","
                "\"account_count\":2,\"days\":7}]'",
            ],
            add_arguments=_add_proposal_revise_arguments,
            build_arguments=_build_proposal_revise_arguments,
            supports_dry_run=True,
        ),
        CommandSpec(
            domain=domain,
            shortcut="+get",
            resource="proposal",
            legacy_shortcuts=("+proposal-get",),
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
                "Proposal number, canonical proposal_url, status, revision round, changes, current "
                "elements, latest feedback summary, the annotations section (per-round "
                "compiled_summary/round/resolved, newest round first, or the string "
                '"暂无标注意见" when there is no feedback yet), and a review reminder. '
                "Forward proposal_url exactly as returned; never construct a link."
            ),
            examples=[
                "museoncli agentic-campaign proposal +get "
                "--plan-id 33333333-3333-4333-8333-333333333333 "
                "--proposal-id 77777777-7777-4777-8777-777777777777"
            ],
            add_arguments=_add_proposal_get_arguments,
            build_arguments=_build_proposal_get_arguments,
        ),
        CommandSpec(
            domain=domain,
            shortcut="+withdraw",
            resource="proposal",
            legacy_shortcuts=("+proposal-withdraw",),
            summary=(
                "Withdraw one open adjustment proposal on this plan, permanently releasing "
                "the plan elements and the persona change it holds. Withdrawal cannot be "
                "undone, and a proposal the operator already confirmed cannot be withdrawn. "
                "This is one of the two ways out of a rejected Proposal: when the server "
                "answers 409 proposal_element_conflict, proposal_persona_conflict or "
                "proposal_open_limit_reached it names the blocking_proposal_id, so either "
                "withdraw that proposal here and submit again, or revise the named proposal "
                "in place with proposal +revise --proposal-id. Never resend the rejected payload "
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
                "museoncli agentic-campaign proposal +withdraw "
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
                    "direction_brief": {"type": ["string", "null"]},
                    "success_hypothesis": {"type": ["string", "null"]},
                    "contract": {"type": ["string", "null"]},
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
            shortcut="+overview",
            summary=(
                "Read a workspace-wide overview across every Agentic Creative Campaign: "
                "direction, latest strategy signal, latest verdict, recent signal series, "
                "and open issue/proposal counts. Use this before +recap to decide which "
                "Campaign needs closer attention."
            ),
            risk_level="read",
            execution="direct",
            adapter_tool_name="agentic_campaign_overview",
            input_schema=_schema(
                {
                    "page": {"type": "integer", "minimum": 1, "default": 1},
                    "page_size": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 100,
                        "default": 20,
                    },
                }
            ),
            output_schema=_direct_output_schema(
                "Paginated Campaign overview rows (id, name, status, direction_brief, "
                "success_hypothesis, contract, strategy_signal, latest_verdict, signals, "
                "open_issue_counts, open_proposal_count) and pagination metadata."
            ),
            examples=["museoncli agentic-campaign +overview --page 1 --page-size 20"],
            add_arguments=_add_overview_arguments,
            build_arguments=_build_overview_arguments,
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
            shortcut="+recap",
            summary=(
                "Read one Campaign's full recap: the archive fields (direction_brief, "
                "success_hypothesis, contract, strategy_signal, policy), its decision "
                "history with rationale, the last weeks of strategy signals, learnings, "
                "and open issues/proposals. This is the same payload the AgentClock issue "
                "dispatch injects into Mel's prompt."
            ),
            risk_level="read",
            execution="direct",
            adapter_tool_name="agentic_campaign_recap",
            input_schema=_schema(
                {
                    "campaign_id": _uuid_property("Agentic Creative Campaign id"),
                    "include_cells": {
                        "type": "boolean",
                        "default": False,
                        "description": "Include testing ledger details.",
                    },
                },
                required=["campaign_id"],
            ),
            output_schema=_direct_output_schema(
                "Campaign recap: campaign archive fields, decision_history, signals, "
                "learnings, open_issues, and open_proposals."
            ),
            examples=[
                "museoncli agentic-campaign +recap "
                "--id 22222222-2222-4222-8222-222222222222",
                "museoncli agentic-campaign +recap "
                "--id 22222222-2222-4222-8222-222222222222 --cells",
            ],
            add_arguments=_add_recap_arguments,
            build_arguments=_build_recap_arguments,
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
        CommandSpec(
            domain=domain,
            shortcut="+learning-add",
            summary=(
                "Add a rule-type Learning Entry to a Campaign's evaluation memory. Distinct "
                "from the 'outcome' entries evaluation runs produce automatically, this is a "
                "human- or Mel-authored rule that future evaluation runs weigh alongside them."
            ),
            risk_level="write",
            execution="direct",
            adapter_tool_name="agentic_campaign_learning_add",
            input_schema=_schema(
                {
                    "campaign_id": _uuid_property("Agentic Creative Campaign id"),
                    "claim": {
                        "type": "string",
                        "minLength": 1,
                        "description": "The learning statement being recorded.",
                    },
                    "confidence": {
                        "enum": ["low", "medium", "high"],
                        "description": "Optional confidence level for this claim.",
                    },
                    "scope": {
                        "type": ["object", "null"],
                        "description": "Optional free-form object narrowing what this learning applies to.",
                    },
                    "evidence": {
                        "type": ["object", "null"],
                        "description": "Optional free-form object citing the evidence behind this claim.",
                    },
                    "dry_run": {"type": "boolean", "default": False},
                },
                required=["campaign_id", "claim"],
            ),
            output_schema=_direct_output_schema(
                "Created Learning Entry: id, entry_type (rule), claim, confidence, scope, "
                "evidence, status (active), and timestamps."
            ),
            examples=[
                "museoncli agentic-campaign +learning-add "
                "--campaign-id 22222222-2222-4222-8222-222222222222 "
                "--claim 'Warm workshop portraits outperform studio shots' "
                "--confidence medium",
                "museoncli agentic-campaign +learning-add "
                "--campaign-id 22222222-2222-4222-8222-222222222222 "
                "--claim 'CTA overlays reduce completion rate on short-form video' "
                "--confidence high "
                """--evidence-json '{"proposal_ids":["77777777-7777-4777-8777-777777777777"]}'""",
            ],
            add_arguments=_add_learning_add_arguments,
            build_arguments=_build_learning_add_arguments,
            supports_dry_run=True,
        ),
        CommandSpec(
            domain=domain,
            shortcut="+issue-open",
            summary=(
                "Manually open a Campaign Issue (reset, evolution, or strategy) outside the "
                "automated evaluation pipeline, e.g. for an operator- or Mel-initiated "
                "intervention. The issue starts in status open, source manual."
            ),
            risk_level="write",
            execution="direct",
            adapter_tool_name="agentic_campaign_issue_open",
            input_schema=_schema(
                {
                    "campaign_id": _uuid_property("Agentic Creative Campaign id"),
                    "kind": {"enum": ["reset", "evolution", "strategy"]},
                    "note": {"type": ["string", "null"]},
                    "scope": {
                        "type": ["object", "null"],
                        "additionalProperties": False,
                        "properties": {
                            "plan_ids": {
                                "type": "array",
                                "items": _uuid_property("Agentic Persona Plan id"),
                            },
                            "account_ids": {
                                "type": "array",
                                "items": _uuid_property("Managed social account id"),
                            },
                        },
                    },
                    "dry_run": {"type": "boolean", "default": False},
                },
                required=["campaign_id", "kind"],
            ),
            output_schema=_direct_output_schema(
                "Created Campaign Issue: id, kind, status (open), scope, source (manual), "
                "and timestamps."
            ),
            examples=[
                "museoncli agentic-campaign +issue-open "
                "--campaign-id 22222222-2222-4222-8222-222222222222 "
                "--kind strategy --note 'Persona drift observed across all plans'",
                "museoncli agentic-campaign +issue-open "
                "--campaign-id 22222222-2222-4222-8222-222222222222 "
                "--kind reset "
                """--scope-json '{"plan_ids":["33333333-3333-4333-8333-333333333333"]}'""",
            ],
            add_arguments=_add_issue_open_arguments,
            build_arguments=_build_issue_open_arguments,
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
    if name is not None and len(str(name)) > 80:
        raise ValueError("draft plan proposal --name must be 80 characters or fewer.")
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
    proposal_number = proposal.get("proposal_number") if isinstance(proposal, dict) else None
    proposal_url = payload.get("proposal_url") if isinstance(payload, dict) else None
    return {
        **({"proposal_id": proposal_id} if proposal is not None else {}),
        **({"proposal_number": proposal_number} if isinstance(proposal_number, int) else {}),
        # This is the server-owned canonical route. Never derive it from ids.
        **({"proposal_url": proposal_url} if isinstance(proposal_url, str) else {}),
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
        **(
            {"proposal_number": proposal["proposal_number"]}
            if isinstance(proposal.get("proposal_number"), int)
            else {}
        ),
        **(
            {"proposal_url": proposal["proposal_url"]}
            if isinstance(proposal.get("proposal_url"), str)
            else {}
        ),
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


async def _execute_proposal_list(ctx: CommandContext) -> Any:
    campaign_id = ctx.arguments.get("campaign_id")
    if campaign_id:
        path = f"/agentic-creative-campaigns/{campaign_id}/revision-proposals"
    else:
        located_campaign_id, plan, _ = await _locate_plan(ctx)
        path = (
            f"/agentic-creative-campaigns/{located_campaign_id}/persona-plans/{plan['id']}/"
            "revision-proposals"
        )
    return await ctx.api_data_v2(
        ctx.cfg,
        "GET",
        path,
        params={
            "workspace_id": ctx.workspace_id,
            "page": ctx.arguments["page"],
            "page_size": ctx.arguments["page_size"],
            "include_draft_stage": ctx.arguments["include_draft_stage"],
            "status": ctx.arguments["status"],
        },
    )


async def _execute_schedule_rollout_preflight(ctx: CommandContext) -> Any:
    campaign_id, plan, _ = await _locate_plan(ctx)
    proposal_id = ctx.arguments.get("proposal_id")
    return await ctx.api_data_v2(
        ctx.cfg,
        "POST",
        (
            f"/agentic-creative-campaigns/{campaign_id}/persona-plans/{plan['id']}/"
            f"revision-proposals/{proposal_id}:schedule-rollout-preflight"
        ),
        json_body={
            "workspace_id": ctx.workspace_id,
            "coverage": ctx.arguments.get("coverage"),
            "testing_plan": ctx.arguments.get("testing_plan"),
        },
    )


async def _execute_confirm_schedule_rollout(ctx: CommandContext) -> Any:
    campaign_id, plan, _ = await _locate_plan(ctx)
    proposal_id = ctx.arguments.get("proposal_id")
    return await ctx.api_data_v2(
        ctx.cfg,
        "POST",
        (
            f"/agentic-creative-campaigns/{campaign_id}/persona-plans/{plan['id']}/"
            f"revision-proposals/{proposal_id}:confirm-schedule-rollout"
        ),
        json_body={
            "workspace_id": ctx.workspace_id,
            "coverage": ctx.arguments.get("coverage"),
            "testing_plan": ctx.arguments.get("testing_plan"),
            "idempotency_key": ctx.arguments.get("idempotency_key"),
        },
    )


async def _execute_schedule_rollout_get(ctx: CommandContext) -> Any:
    campaign_id, plan, _ = await _locate_plan(ctx)
    rollout_id = ctx.arguments.get("rollout_id")
    proposal_id = ctx.arguments.get("proposal_id")
    if rollout_id:
        path = f"schedule-rollouts/{rollout_id}"
    elif proposal_id:
        path = f"revision-proposals/{proposal_id}/schedule-rollout"
    else:
        raise ValueError("one of rollout_id or proposal_id is required.")
    return await ctx.api_data_v2(
        ctx.cfg,
        "GET",
        f"/agentic-creative-campaigns/{campaign_id}/persona-plans/{plan['id']}/{path}",
        params={"workspace_id": ctx.workspace_id},
    )


async def _execute_plan_propose(ctx: CommandContext) -> Any:
    """Shared submission engine backing the canonical ``proposal +create`` command:
    a complete draft-plan solution (status == "draft") or an atomic active-plan
    adjustment (status == "active", via ``changes``). Revising an already-open
    proposal is a separate, independent code path -- see ``_execute_proposal_revise``.
    """
    campaign_id, plan, _ = await _locate_plan(ctx)
    status = plan.get("status")
    raw_changes = ctx.arguments.get("changes")
    has_solution = any(
        ctx.arguments.get(key) is not None
        for key in ("name", "persona_payload", "persona_id", "elements")
    )
    has_adjustment = raw_changes is not None
    if has_solution and has_adjustment:
        raise ValueError("一次提案只能是一种:整套方案 或 调整")

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
            "rationale": ctx.arguments.get("rationale"),
            "rollout_intent": ctx.arguments.get("rollout_intent"),
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
            "rationale": ctx.arguments.get("rationale"),
            "rollout_intent": ctx.arguments.get("rollout_intent"),
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


async def _execute_proposal_create(ctx: CommandContext) -> Any:
    return await _execute_plan_propose(ctx)


async def _execute_proposal_reallocate(ctx: CommandContext) -> Any:
    campaign_id = str(ctx.arguments["campaign_id"])
    plan_id = str(ctx.arguments["plan_id"])
    changes = ctx.arguments["changes"]
    response = await ctx.api_data_v2(
        ctx.cfg,
        "POST",
        f"/agentic-creative-campaigns/{campaign_id}/persona-plans/{plan_id}/revision-proposals",
        json_body=compact_params(
            {
                "workspace_id": ctx.workspace_id,
                "changes": changes,
                "rationale": ctx.arguments.get("rationale"),
            }
        ),
    )
    return _proposal_output(
        response, changes={"reallocate_accounts": changes["reallocate_accounts"]}
    )


async def _execute_proposal_revise(ctx: CommandContext) -> Any:
    campaign_id, plan, _ = await _locate_plan(ctx)
    proposal_id = str(ctx.arguments["proposal_id"])
    response = await ctx.api_data_v2(
        ctx.cfg,
        "POST",
        (
            f"/agentic-creative-campaigns/{campaign_id}/persona-plans/{plan['id']}/"
            f"revision-proposals/{proposal_id}:submit-revision"
        ),
        json_body={
            "workspace_id": ctx.workspace_id,
            "changes": ctx.arguments["changes"],
            "note": ctx.arguments.get("note"),
            "rationale": ctx.arguments.get("rationale"),
            "rollout_intent": ctx.arguments.get("rollout_intent"),
        },
    )
    payload = _payload_data(response)
    if not isinstance(payload, dict):
        raise RuntimeError("revision submission response was not an object")
    revision_round = payload.get("round")
    return {
        "revision_round": revision_round,
        "new_element_count": len(payload.get("elements") or []),
        "preview_task_count": payload.get("dispatched_task_count"),
        **(
            {"proposal_url": payload["proposal_url"]}
            if isinstance(payload.get("proposal_url"), str)
            else {}
        ),
        "next_step": f"第 {revision_round} 稿已提交；运营将在审阅台看到新一稿。",
    }


async def _execute_plan_members_reconcile(ctx: CommandContext) -> Any:
    campaign_id, plan, detail = await _locate_plan(ctx)
    campaign = detail.get("campaign") if isinstance(detail, dict) else None
    plans = detail.get("agentic_persona_plans") if isinstance(detail, dict) else None
    if not isinstance(campaign, dict) or campaign.get("version") is None:
        raise RuntimeError("campaign detail did not include its current version")
    if plan.get("version") is None:
        raise RuntimeError("plan detail did not include its current version")
    if not isinstance(plans, list):
        raise RuntimeError("campaign detail did not include Persona Plans")
    account_ids = list(ctx.arguments["target_account_ids"])
    allocated_budget = sum(
        int(item.get("account_budget") or 0)
        for item in plans
        if isinstance(item, dict)
    )
    current_plan_budget = int(plan.get("account_budget") or 0)
    required_total_budget = max(
        int(campaign.get("total_account_budget") or 0),
        allocated_budget - current_plan_budget + len(account_ids),
    )
    return await ctx.api_data_v2(
        ctx.cfg,
        "POST",
        (
            f"/agentic-creative-campaigns/{campaign_id}/persona-plans/{plan['id']}:"
            "reconcile-members"
        ),
        json_body={
            "workspace_id": ctx.workspace_id,
            "expected_campaign_version": campaign["version"],
            "expected_plan_version": plan["version"],
            "account_budget": len(account_ids),
            "target_account_ids": account_ids,
            "target_campaign_total_budget": required_total_budget,
        },
    )


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
                "direction_brief": ctx.arguments.get("direction_brief"),
                "success_hypothesis": ctx.arguments.get("success_hypothesis"),
                "contract": ctx.arguments.get("contract"),
                "bind_notification_conversation": ctx.arguments.get(
                    "bind_notification_conversation"
                ),
                "config": ctx.arguments.get("config"),
            }
        ),
    )


async def _execute_overview(ctx: CommandContext) -> Any:
    response = await ctx.api_data_v2(
        ctx.cfg,
        "GET",
        "/agentic-creative-campaigns/overview",
        params={
            "workspace_id": ctx.workspace_id,
            "page": ctx.arguments.get("page", 1),
            "page_size": ctx.arguments.get("page_size", 20),
        },
    )
    if not isinstance(response, dict) or not isinstance(response.get("items"), list):
        return response
    for item in response["items"]:
        if isinstance(item, dict):
            _render_overview_ledger(item)
    return response


_LEDGER_STATUS = {
    "testing": "在测",
    "proposed": "待入",
    "winner": "赢家",
    "retired": "已淘汰",
}


def _ledger_summary(summary: Any, *, compact: bool = False) -> str | None:
    if not isinstance(summary, dict):
        return None
    parts = [
        f"在测组合 {summary.get('testing_cells', 0)}",
        f"容量 {summary.get('capacity_cells', 0)}",
    ]
    overload_ratio = summary.get("overload_ratio")
    if overload_ratio is not None:
        parts.append(f"超载 {overload_ratio:g}×")
    if not compact:
        parts.extend(
            [
                f"零样本 {summary.get('testing_cells_zero_sample', 0)}",
                f"赢家 {summary.get('winner_cells', 0)}",
            ]
        )
    return " · ".join(parts)


def _render_overview_ledger(item: dict[str, Any]) -> None:
    if "matrix" not in item:
        return
    matrix = item.pop("matrix")
    if not isinstance(matrix, dict):
        return
    rendered = _ledger_summary(matrix.get("summary"), compact=True)
    if rendered is not None:
        item["台账"] = rendered


def _short_shanghai_datetime(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        return "—"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return "—"
        return parsed.astimezone(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return "—"


def _ledger_detail(cells: Any) -> list[dict[str, Any]]:
    if not isinstance(cells, list):
        return []
    return [
        {
            "plan": cell.get("plan_name") or cell.get("plan_id") or "—",
            "状态": _LEDGER_STATUS.get(cell.get("element_status"), "—"),
            "format": cell.get("format_name") or cell.get("format_id") or "—",
            "topic": cell.get("topic_title") or cell.get("topic_id") or "—",
            "样本": cell.get("samples_total", 0),
            "近7天": cell.get("samples_in_window", 0),
            "中位播放": cell.get("median_views") if cell.get("median_views") is not None else "—",
            "最高播放": cell.get("max_views") if cell.get("max_views") is not None else "—",
            "最近发布": _short_shanghai_datetime(cell.get("last_published_at")),
        }
        for cell in cells
        if isinstance(cell, dict)
    ]


def _render_recap_ledger(response: Any) -> Any:
    if not isinstance(response, dict) or "matrix" not in response:
        return response
    matrix = response.pop("matrix")
    if not isinstance(matrix, dict):
        return response
    rendered = _ledger_summary(matrix.get("summary"))
    if rendered is not None:
        response["测试台账"] = rendered
    if "cells" in matrix:
        response["组合明细"] = _ledger_detail(matrix.get("cells"))
    return response


async def _execute_recap(ctx: CommandContext) -> Any:
    campaign_id = str(ctx.arguments.get("campaign_id") or "")
    response = await ctx.api_data_v2(
        ctx.cfg,
        "GET",
        f"/agentic-creative-campaigns/{campaign_id}/recap",
        params={
            "workspace_id": ctx.workspace_id,
            "include_cells": bool(ctx.arguments.get("include_cells", False)),
        },
    )
    return _render_recap_ledger(response)


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


async def _execute_learning_add(ctx: CommandContext) -> Any:
    campaign_id = str(ctx.arguments.get("campaign_id") or "")
    return await ctx.api_data_v2(
        ctx.cfg,
        "POST",
        f"/agentic-creative-campaigns/{campaign_id}/learning-entries",
        json_body=compact_params(
            {
                "workspace_id": ctx.workspace_id,
                "claim": ctx.arguments.get("claim"),
                "scope": ctx.arguments.get("scope"),
                "confidence": ctx.arguments.get("confidence"),
                "evidence": ctx.arguments.get("evidence"),
            }
        ),
    )


async def _execute_issue_open(ctx: CommandContext) -> Any:
    campaign_id = str(ctx.arguments.get("campaign_id") or "")
    return await ctx.api_data_v2(
        ctx.cfg,
        "POST",
        f"/agentic-creative-campaigns/{campaign_id}/issues",
        json_body=compact_params(
            {
                "workspace_id": ctx.workspace_id,
                "kind": ctx.arguments.get("kind"),
                "note": ctx.arguments.get("note"),
                "scope": ctx.arguments.get("scope"),
            }
        ),
    )


EXECUTORS = {
    "agentic-campaign.confirm-schedule-rollout": redacted_direct_enveloped(
        _execute_confirm_schedule_rollout, redact_api_errors=True
    ),
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
    "agentic-campaign.issue-open": redacted_direct_enveloped(
        _execute_issue_open, redact_api_errors=True
    ),
    "agentic-campaign.issues-pull": redacted_direct_enveloped(
        _execute_issues_pull, redact_api_errors=True
    ),
    "agentic-campaign.learning-add": redacted_direct_enveloped(
        _execute_learning_add, redact_api_errors=True
    ),
    "agentic-campaign.list": redacted_direct_enveloped(_execute_list, redact_api_errors=True),
    "agentic-campaign.overview": redacted_direct_enveloped(
        _execute_overview, redact_api_errors=True
    ),
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
    "agentic-campaign.plan-members-reconcile": redacted_direct_enveloped(
        _execute_plan_members_reconcile, redact_api_errors=True
    ),
    "agentic-campaign.proposal-create": redacted_direct_enveloped(
        _execute_proposal_create, redact_api_errors=True
    ),
    "agentic-campaign.proposal-reallocate": redacted_direct_enveloped(
        _execute_proposal_reallocate, redact_api_errors=True
    ),
    "agentic-campaign.proposal-list": redacted_direct_enveloped(
        _execute_proposal_list, redact_api_errors=True
    ),
    "agentic-campaign.proposal-revise": redacted_direct_enveloped(
        _execute_proposal_revise, redact_api_errors=True
    ),
    "agentic-campaign.proposal-get": redacted_direct_enveloped(
        _execute_proposal_get, redact_api_errors=True
    ),
    "agentic-campaign.proposal-withdraw": redacted_direct_enveloped(
        _execute_proposal_withdraw, redact_api_errors=True
    ),
    "agentic-campaign.recap": redacted_direct_enveloped(_execute_recap, redact_api_errors=True),
    "agentic-campaign.schedule-rollout-get": redacted_direct_enveloped(
        _execute_schedule_rollout_get, redact_api_errors=True
    ),
    "agentic-campaign.schedule-rollout-preflight": redacted_direct_enveloped(
        _execute_schedule_rollout_preflight, redact_api_errors=True
    ),
    "agentic-campaign.plan-tags": redacted_direct_enveloped(
        _execute_plan_tags, redact_api_errors=True
    ),
}
