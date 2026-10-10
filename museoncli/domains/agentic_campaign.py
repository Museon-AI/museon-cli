"""Museon managed campaigns, restored from the original CLI and adapted to v2."""

from __future__ import annotations


import argparse


from typing import Any
from uuid import UUID
from urllib.parse import quote, urlencode


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
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--plan-id", required=True)


def _build_plan_id_arguments(args: argparse.Namespace) -> dict[str, Any]:
    return {"campaign_id": args.campaign_id, "plan_id": args.plan_id}


def _add_proposal_list_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--plan-id")
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--page-size", type=int, default=20)
    parser.add_argument("--include-draft-stage", action="store_true")
    parser.add_argument(
        "--status",
        action="append",
        choices=["awaiting-review", "confirmed", "dismissed", "superseded"],
    )
    parser.add_argument("--awaiting-review", action="store_true")


def _add_proposal_get_arguments(parser: argparse.ArgumentParser) -> None:
    _add_plan_id_arguments(parser)
    parser.add_argument("--proposal-id", required=True)


def _build_proposal_get_arguments(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "campaign_id": args.campaign_id,
        "plan_id": args.plan_id,
        "proposal_id": args.proposal_id,
    }


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
        "campaign_id": args.campaign_id,
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
        "campaign_id": args.campaign_id,
        "plan_id": args.plan_id,
        "rollout_id": args.rollout_id,
        "proposal_id": args.proposal_id,
    }


def _candidate_json(value: str, *, field: str, expected_type: type) -> Any:
    parsed = read_json_option(
        value=None if value.startswith("@") else value,
        file_path=value[1:] if value.startswith("@") else None,
        field=field,
    )
    if not isinstance(parsed, expected_type):
        expected_name = "object" if expected_type is dict else "array"
        raise ValueError(f"{field} must be a JSON {expected_name}")
    return parsed


def _build_proposal_list_arguments(args: argparse.Namespace) -> dict[str, Any]:
    if args.page < 1 or args.page_size < 1:
        raise ValueError("--page and --page-size must be positive")
    statuses = list(args.status or [])
    if args.awaiting_review and "awaiting-review" not in statuses:
        statuses.append("awaiting-review")
    return {
        "campaign_id": args.campaign_id,
        "plan_id": args.plan_id,
        "page": args.page,
        "page_size": args.page_size,
        "include_draft_stage": args.include_draft_stage,
        "status": [value.replace("-", "_") for value in statuses] or None,
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
    return {
        "campaign_id": args.campaign_id,
        "plan_id": args.plan_id,
        **mutable,
        "dry_run": args.dry_run,
    }


def _add_plan_create_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--persona-id")
    parser.add_argument("--account-budget", type=int, required=True)
    parser.add_argument("--dry-run", action="store_true")


def _build_plan_create_arguments(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "campaign_id": args.campaign_id,
        "name": args.name,
        "persona_id": args.persona_id,
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
        {
            "campaign_id": _uuid_property("Owning Museon campaign id"),
            "plan_id": _uuid_property("Agentic Persona Plan id"),
            **(extra or {}),
        },
        required=["campaign_id", "plan_id", *(required or [])],
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
    schema["required"] = ["campaign_id"]
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
        _supply_spec(),
        _account_control_spec(),
        *_managed_read_specs(),
        CommandSpec(
            domain=domain,
            shortcut="+members-reconcile",
            required_roles=("workspace_admin_or_staff",),
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
                'museoncli agentic-campaign plan +members-reconcile --plan-id 33333333-3333-4333-8333-333333333333 --account-ids \'["44444444-4444-4444-8444-444444444444","55555555-5555-4555-8555-555555555555"]\' --campaign-id 11111111-1111-4111-8111-111111111111'
            ],
            add_arguments=_add_plan_members_reconcile_arguments,
            build_arguments=_build_plan_members_reconcile_arguments,
            supports_dry_run=True,
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
                "in place with plan +supply-update --proposal-id. Never resend the rejected payload "
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
                "museoncli agentic-campaign proposal +withdraw --plan-id 33333333-3333-4333-8333-333333333333 --proposal-id 77777777-7777-4777-8777-777777777777 --campaign-id 11111111-1111-4111-8111-111111111111"
            ],
            add_arguments=_add_proposal_withdraw_arguments,
            build_arguments=_build_proposal_withdraw_arguments,
            supports_dry_run=True,
        ),
        CommandSpec(
            domain=domain,
            shortcut="+schedule-rollout-preflight",
            summary="Always run this read-only command before first confirming one specified awaiting-review proposal, and rerun it whenever coverage or testing overrides change. It returns the exact schedule-rollout matrix the operator must review before applying. The proposal does not need to be the Plan's newest: independent active-Plan proposals can be confirmed in any order. Includes winner boost placements. A boost reserves visible target-account slots; if the response is coverage_days_required because existing future slots cannot fulfil its days, rerun with --coverage future-window --days 1..30. Future slots follow the campaign preferred publish windows. A confirmed proposal can only be inspected or retried; use +schedule-rollout-get for its persisted rollout. Dismissed or superseded proposals are rejected.",
            risk_level="read",
            execution="direct",
            adapter_tool_name="agentic_campaign_schedule_rollout_preflight",
            input_schema=_plan_schema(
                {
                    "proposal_id": _uuid_property(
                        "Exact revision proposal id. First confirmation requires awaiting_review; it need not be the newest proposal on the Plan. A confirmed proposal may be inspected, but +schedule-rollout-get reads its persisted rollout."
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
                "Read-only rollout preview: target slots, seed bindings, regular generation count, failed elements, and coverage_days_required when future slots must be created."
            ),
            examples=[
                "museoncli agentic-campaign +schedule-rollout-preflight --plan-id 33333333-3333-4333-8333-333333333333 --proposal-id 77777777-7777-4777-8777-777777777777 --timezone Asia/Shanghai --campaign-id 11111111-1111-4111-8111-111111111111",
                "museoncli agentic-campaign +schedule-rollout-preflight --plan-id 33333333-3333-4333-8333-333333333333 --proposal-id 77777777-7777-4777-8777-777777777777 --coverage future-window --days 7 --timezone Asia/Shanghai --campaign-id 11111111-1111-4111-8111-111111111111",
            ],
            add_arguments=_add_schedule_rollout_preflight_arguments,
            build_arguments=_build_schedule_rollout_preflight_arguments,
        ),
        CommandSpec(
            domain=domain,
            shortcut="+confirm-schedule-rollout",
            summary="After a ready +schedule-rollout-preflight for the same proposal, coverage, and testing plan, atomically apply one specified awaiting-review proposal (there is no separate approval command), persist its immutable schedule-rollout intent including visible winner boost placements, and dispatch asynchronous execution. The proposal need not be newest: independent active-Plan proposals can be confirmed in any order; confirming a competitive whole-plan alternative dismisses the other awaiting-review alternatives. Reuse the same idempotency key to retry a confirmed proposal's existing rollout; dismissed or superseded proposals are rejected. Poll +schedule-rollout-get after the 202 response.",
            risk_level="write",
            execution="direct",
            adapter_tool_name="agentic_campaign_confirm_schedule_rollout",
            input_schema=_plan_schema(
                {
                    "proposal_id": _uuid_property(
                        "Exact awaiting-review revision proposal id to apply. It need not be the newest Plan proposal. A confirmed id only retries its existing durable rollout; dismissed and superseded ids are rejected."
                    ),
                    "coverage": {"type": "object"},
                    "testing_plan": {"type": "object"},
                    "idempotency_key": {"type": "string", "minLength": 8, "maxLength": 240},
                    "dry_run": {"type": "boolean", "default": False},
                },
                required=["proposal_id", "coverage", "testing_plan", "idempotency_key"],
            ),
            output_schema=_direct_output_schema(
                "202-accepted durable rollout id and current state; use +schedule-rollout-get until terminal."
            ),
            examples=[
                "museoncli agentic-campaign +confirm-schedule-rollout --plan-id 33333333-3333-4333-8333-333333333333 --proposal-id 77777777-7777-4777-8777-777777777777 --timezone Asia/Shanghai --idempotency-key rollout-20260801-001 --campaign-id 11111111-1111-4111-8111-111111111111"
            ],
            add_arguments=_add_confirm_schedule_rollout_arguments,
            build_arguments=_build_confirm_schedule_rollout_arguments,
            supports_dry_run=True,
        ),
        CommandSpec(
            domain=domain,
            shortcut="+schedule-rollout-get",
            summary="Read durable schedule-rollout status by rollout id or confirmed proposal id. Use this after +confirm-schedule-rollout's 202 response to inspect immutable assignments, seed bindings, and asynchronous progress.",
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
                "Durable rollout state, immutable coverage/testing assignments, seed bindings, and execution progress."
            ),
            examples=[
                "museoncli agentic-campaign +schedule-rollout-get --plan-id 33333333-3333-4333-8333-333333333333 --rollout-id 88888888-8888-4888-8888-888888888888 --campaign-id 11111111-1111-4111-8111-111111111111"
            ],
            add_arguments=_add_schedule_rollout_get_arguments,
            build_arguments=_build_schedule_rollout_get_arguments,
        ),
        CommandSpec(
            domain=domain,
            shortcut="+list",
            resource="proposal",
            summary="List Proposals for exactly one Plan or all Plans in one Campaign. Campaign scope returns each Proposal's Plan and Persona summary.",
            risk_level="read",
            execution="direct",
            adapter_tool_name="agentic_campaign_proposal_list",
            input_schema=_proposal_list_input_schema(),
            output_schema=_direct_output_schema(
                "Paginated Proposal list for one Plan or Campaign. Every item includes its canonical proposal_url; forward it exactly as returned."
            ),
            examples=[
                "museoncli agentic-campaign proposal +list --plan-id 33333333-3333-4333-8333-333333333333 --campaign-id 11111111-1111-4111-8111-111111111111",
                "museoncli agentic-campaign proposal +list --campaign-id 22222222-2222-4222-8222-222222222222 --awaiting-review",
            ],
            add_arguments=_add_proposal_list_arguments,
            build_arguments=_build_proposal_list_arguments,
        ),
        CommandSpec(
            domain=domain,
            shortcut="+get",
            resource="proposal",
            legacy_shortcuts=("+proposal-get",),
            summary="Read an adjustment proposal, its latest revision guidance, and the full round-by-round annotation history (annotations).",
            risk_level="read",
            execution="direct",
            adapter_tool_name="agentic_campaign_proposal_get",
            input_schema=_plan_schema(
                {"proposal_id": _uuid_property("Adjustment proposal id")}, required=["proposal_id"]
            ),
            output_schema=_direct_output_schema(
                'Proposal number, canonical proposal_url, status, revision round, changes, current elements, latest feedback summary, the annotations section (per-round compiled_summary/round/resolved, newest round first, or the string "暂无标注意见" when there is no feedback yet), and a review reminder. Forward proposal_url exactly as returned; never construct a link.'
            ),
            examples=[
                "museoncli agentic-campaign proposal +get --plan-id 33333333-3333-4333-8333-333333333333 --proposal-id 77777777-7777-4777-8777-777777777777 --campaign-id 11111111-1111-4111-8111-111111111111"
            ],
            add_arguments=_add_proposal_get_arguments,
            build_arguments=_build_proposal_get_arguments,
        ),
        CommandSpec(
            domain=domain,
            shortcut="+campaign-create",
            summary="Create an Agentic Creative Campaign in the selected workspace. Confirm the intent (name, total budget, planned persona count) with the operator before creating, and report the campaign link back afterward.",
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
                    "bind_notification_conversation": {"type": "boolean", "default": False},
                    "config": _campaign_config_schema(),
                    "dry_run": {"type": "boolean", "default": False},
                },
                required=["name"],
            ),
            output_schema=_direct_output_schema("Created campaign detail."),
            examples=[
                "museoncli agentic-campaign +campaign-create --name 'Summer maker campaign' --total-account-budget 20 --planned-persona-count 3"
            ],
            add_arguments=_add_campaign_create_arguments,
            build_arguments=_build_campaign_create_arguments,
            supports_dry_run=True,
        ),
        CommandSpec(
            domain=domain,
            shortcut="+campaign-update",
            summary="Patch only supplied campaign fields. Budget and config fields are setup-only; name must be changed by itself. Field-level hashtag, mention, and publish-window options merge into existing config, while --config-json replaces the full config.",
            risk_level="write",
            requires_confirmation=True,
            execution="direct",
            adapter_tool_name="agentic_campaign_campaign_update",
            input_schema=_schema(
                {
                    "campaign_id": _uuid_property("Agentic Creative Campaign id"),
                    "name": {"type": "string", "minLength": 1, "maxLength": 160},
                    "total_account_budget": {"type": "integer", "minimum": 0},
                    "planned_persona_count": {"type": "integer", "minimum": 1, "maximum": 10},
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
                "museoncli agentic-campaign +campaign-update --campaign-id 22222222-2222-4222-8222-222222222222 --total-account-budget 107 --yes",
                "museoncli agentic-campaign +campaign-update --campaign-id 22222222-2222-4222-8222-222222222222 --bind-notification-conversation --yes",
            ],
            add_arguments=_add_campaign_update_arguments,
            build_arguments=_build_campaign_update_arguments,
            supports_dry_run=True,
        ),
        CommandSpec(
            domain=domain,
            shortcut="+plan-update",
            summary="Update plan tokens for the next generation while a campaign is active or paused, or update name/budget only during setup.",
            risk_level="write",
            execution="direct",
            adapter_tool_name="agentic_campaign_plan_update",
            input_schema=_plan_schema(
                {
                    "name": {"type": "string", "minLength": 1, "maxLength": 160},
                    "account_budget": {"type": "integer", "minimum": 0},
                    "required_hashtags": {"type": "array", "items": {"type": "string"}},
                    "required_mentions": {"type": "array", "items": {"type": "string"}},
                    "dry_run": {"type": "boolean", "default": False},
                }
            ),
            output_schema=_direct_output_schema("Updated Persona Plan detail."),
            examples=[
                "museoncli agentic-campaign +plan-update --plan-id 33333333-3333-4333-8333-333333333333 --required-hashtags '#maker,#diy' --campaign-id 11111111-1111-4111-8111-111111111111"
            ],
            add_arguments=_add_plan_update_arguments,
            build_arguments=_build_plan_update_arguments,
            supports_dry_run=True,
        ),
        CommandSpec(
            domain=domain,
            shortcut="+plan-create",
            summary="Create a Persona Plan under a campaign. Only allowed while the campaign is in setup (setting_up or setup_ready); the server rejects the request otherwise and the error is passed through unchanged.",
            risk_level="write",
            execution="direct",
            adapter_tool_name="agentic_campaign_plan_create",
            input_schema=_schema(
                {
                    "campaign_id": _uuid_property("Agentic Creative Campaign id"),
                    "persona_id": {
                        "type": ["string", "null"],
                        "format": "uuid",
                        "description": "Existing workspace persona to bind",
                    },
                    "name": {"type": "string", "minLength": 1, "maxLength": 160},
                    "account_budget": {"type": "integer", "minimum": 0},
                    "dry_run": {"type": "boolean", "default": False},
                },
                required=["campaign_id", "name", "account_budget"],
            ),
            output_schema=_direct_output_schema("Campaign detail including the new plan."),
            examples=[
                "museoncli agentic-campaign +plan-create --campaign-id 22222222-2222-4222-8222-222222222222 --name 'DIY makers' --account-budget 5"
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
                "museoncli agentic-campaign +campaign-activate --campaign-id 22222222-2222-4222-8222-222222222222"
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
                "museoncli agentic-campaign +campaign-pause --campaign-id 22222222-2222-4222-8222-222222222222"
            ],
            add_arguments=_add_campaign_lifecycle_arguments,
            build_arguments=_build_campaign_lifecycle_arguments,
            supports_dry_run=True,
        ),
        CommandSpec(
            domain=domain,
            shortcut="+campaign-archive",
            summary="Archive an Agentic Creative Campaign. This cascades to stop account operations for every member of every plan in the campaign; the operator must explicitly confirm before running with --yes.",
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
                "Transitioned campaign detail and the operation batch result (succeeded/skipped/failed counts for the stopped member operations)."
            ),
            examples=[
                "museoncli agentic-campaign +campaign-archive --campaign-id 22222222-2222-4222-8222-222222222222 --yes"
            ],
            add_arguments=_add_campaign_archive_arguments,
            build_arguments=_build_campaign_archive_arguments,
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
            summary="List Persona Plans for one campaign with member pool account ids and handles; account operation ids are omitted.",
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
            summary="Get a Persona Plan by plan id with member pool account ids and handles; account operation ids are omitted.",
            risk_level="read",
            execution="direct",
            adapter_tool_name="agentic_campaign_plan_get",
            input_schema=_plan_schema(),
            output_schema=_direct_output_schema("Persona Plan and display-safe member accounts."),
            examples=[
                "museoncli agentic-campaign +plan-get --plan-id 33333333-3333-4333-8333-333333333333 --campaign-id 11111111-1111-4111-8111-111111111111"
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
                "museoncli agentic-campaign +plan-tags --plan-id 33333333-3333-4333-8333-333333333333 --campaign-id 11111111-1111-4111-8111-111111111111"
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
                "museoncli agentic-campaign +plan-attribution --plan-id 33333333-3333-4333-8333-333333333333 --campaign-id 11111111-1111-4111-8111-111111111111"
            ],
            add_arguments=_add_plan_id_arguments,
            build_arguments=_build_plan_id_arguments,
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
                "version": unit.get("version"),
                "lifecycle_status": unit.get("lifecycle_status"),
                "native_schedule_execution_enabled": unit.get("native_schedule_execution_enabled"),
                "effective_persona_id": unit.get("effective_persona_id"),
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
    """Read one explicitly scoped Campaign; never scan every Campaign over HTTP."""
    campaign_id = str(ctx.arguments.get("campaign_id") or "")
    plan_id = str(ctx.arguments.get("plan_id") or "")
    if not campaign_id:
        raise ValueError("--campaign-id is required; select the owning Museon Campaign first")
    detail = _payload_data(await _detail(ctx, campaign_id))
    if isinstance(detail, dict):
        for plan in detail.get("agentic_persona_plans") or []:
            if isinstance(plan, dict) and str(plan.get("id") or "") == plan_id:
                return campaign_id, plan, detail
    raise ValueError("Plan is not a member of the selected Campaign and workspace")


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
    campaign_id, plan, detail = await _locate_plan(ctx)
    response = await ctx.api_data_v2(
        ctx.cfg,
        "GET",
        f"/agentic-creative-campaigns/{campaign_id}/persona-plans/{plan['id']}",
        params={"workspace_id": ctx.workspace_id},
    )
    return {**_payload_data(response), "accounts": _plan_members(detail, str(plan["id"]))}


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
            **(
                {"reallocate_accounts": changes["reallocate_accounts"]}
                if isinstance(changes.get("reallocate_accounts"), dict)
                else {}
            ),
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
    if campaign_id and not ctx.arguments.get("plan_id"):
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
        int(item.get("account_budget") or 0) for item in plans if isinstance(item, dict)
    )
    current_plan_budget = int(plan.get("account_budget") or 0)
    required_total_budget = max(
        int(campaign.get("total_account_budget") or 0),
        allocated_budget - current_plan_budget + len(account_ids),
    )
    return await ctx.api_data_v2(
        ctx.cfg,
        "POST",
        (f"/agentic-creative-campaigns/{campaign_id}/persona-plans/{plan['id']}:reconcile-members"),
        json_body={
            "workspace_id": ctx.workspace_id,
            "expected_campaign_version": campaign["version"],
            "expected_plan_version": plan["version"],
            "account_budget": len(account_ids),
            "target_account_ids": account_ids,
            "target_campaign_total_budget": required_total_budget,
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
                "policy": {
                    "version": 1,
                    "veto_window_minutes": 0,
                    "max_auto_element_ops": 0,
                    "auto_recruit": {"enabled": False},
                },
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
            "persona_id": ctx.arguments.get("persona_id"),
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


def _add_plan_members_reconcile_arguments(parser: argparse.ArgumentParser) -> None:
    _add_plan_id_arguments(parser)
    parser.add_argument("--account-ids", required=True)
    parser.add_argument("--dry-run", action="store_true")


def _build_plan_members_reconcile_arguments(args: argparse.Namespace) -> dict[str, Any]:
    account_ids = _candidate_json(args.account_ids, field="account-ids", expected_type=list)
    if not all(isinstance(item, str) and item.strip() for item in account_ids):
        raise ValueError("account-ids must be a JSON array of account ids")
    return {
        "campaign_id": args.campaign_id,
        "plan_id": args.plan_id,
        "target_account_ids": list(dict.fromkeys(item.strip() for item in account_ids)),
        "dry_run": args.dry_run,
    }


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
        "campaign_id": args.campaign_id,
        "plan_id": args.plan_id,
        "proposal_id": args.proposal_id,
        "dry_run": args.dry_run,
    }


def _add_supply_arguments(parser: argparse.ArgumentParser) -> None:
    _add_plan_id_arguments(parser)
    parser.add_argument("--persona-id", required=True)
    parser.add_argument("--expected-version", type=int, required=True)
    parser.add_argument(
        "--pairs-json",
        required=True,
        help="JSON array or @file of explicit format_id/topic_id pairs; replaces the target supply",
    )
    parser.add_argument("--proposal-id", help="Current open draft proposal, when replacing it")
    parser.add_argument("--dry-run", action="store_true")


def _build_supply_arguments(args: argparse.Namespace) -> dict[str, Any]:
    pairs = _candidate_json(args.pairs_json, field="pairs", expected_type=list)
    if not 1 <= len(pairs) <= 100:
        raise ValueError("Provide 1..100 explicit reference pairs")
    normalized = []
    seen = set()
    for pair in pairs:
        if not isinstance(pair, dict) or set(pair) - {"format_id", "topic_id", "cta_target_id"}:
            raise ValueError(
                "Each pair requires format_id and topic_id, with optional cta_target_id"
            )
        try:
            item = {
                "format_id": str(UUID(pair["format_id"])),
                "topic_id": str(UUID(pair["topic_id"])),
            }
            if pair.get("cta_target_id"):
                item["cta_target_id"] = str(UUID(pair["cta_target_id"]))
        except (KeyError, ValueError, TypeError, AttributeError) as exc:
            raise ValueError("Reference pairs require valid resource UUIDs") from exc
        key = tuple(sorted(item.items()))
        if key not in seen:
            seen.add(key)
            normalized.append(item)
    if args.expected_version < 1:
        raise ValueError("expected-version must be positive")
    return {
        **_build_plan_id_arguments(args),
        "persona_id": args.persona_id,
        "expected_version": args.expected_version,
        "combinations": normalized,
        "proposal_id": args.proposal_id,
        "dry_run": args.dry_run,
    }


async def _execute_supply(ctx: CommandContext) -> Any:
    campaign_id, plan, _ = await _locate_plan(ctx)
    policy = _payload_data(
        await ctx.api_data_v2(
            ctx.cfg,
            "GET",
            f"/agentic-creative-campaigns/{campaign_id}/policy",
            params={"workspace_id": ctx.workspace_id},
        )
    )
    if policy.get("max_auto_element_ops") != 0:
        raise ValueError(
            "This Campaign allows automatic strategy changes. Set its policy to manual review before importing paired references."
        )
    body = {
        "workspace_id": ctx.workspace_id,
        "expected_version": ctx.arguments["expected_version"],
        "persona_id": ctx.arguments["persona_id"],
        "combinations": ctx.arguments["combinations"],
    }
    if ctx.arguments.get("proposal_id"):
        body.update(
            proposal_id=ctx.arguments["proposal_id"],
            expected_head_version_id=ctx.arguments["proposal_id"],
        )
    return await ctx.api_data_v2(
        ctx.cfg,
        "POST",
        f"/agentic-creative-campaigns/{campaign_id}/persona-plans/{plan['id']}:update-supply",
        json_body=body,
    )


def _supply_spec() -> CommandSpec:
    return CommandSpec(
        domain=Domain.AGENTIC_CAMPAIGN,
        resource="plan",
        shortcut="+supply-update",
        summary="Set reviewed reference pairs for a Museon persona Plan. This opens a proposal; it does not start publishing. Keep existing pairs when appending. Never creates a Format × Topic cross product.",
        risk_level="write",
        execution="direct",
        adapter_tool_name="agentic_campaign_plan_supply_update",
        input_schema=_plan_schema(
            {
                "persona_id": _uuid_property("Selected persona"),
                "expected_version": {"type": "integer", "minimum": 1},
                "combinations": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 100,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "format_id": _uuid_property("Reference format"),
                            "topic_id": _uuid_property("Reference topic"),
                            "cta_target_id": _uuid_property("Optional CTA"),
                        },
                        "required": ["format_id", "topic_id"],
                    },
                },
                "proposal_id": {"type": ["string", "null"]},
                "dry_run": {"type": "boolean"},
            },
            required=["persona_id", "expected_version", "combinations"],
        ),
        output_schema=_direct_output_schema(
            "Proposal receipt, pair count and preview generation count; read proposal before confirming rollout"
        ),
        examples=[],
        supports_dry_run=True,
        required_roles=("workspace_admin_or_staff",),
        add_arguments=_add_supply_arguments,
        build_arguments=_build_supply_arguments,
    )


def _add_account_control_arguments(parser: argparse.ArgumentParser) -> None:
    _add_plan_id_arguments(parser)
    parser.add_argument("--account-id", required=True)
    parser.add_argument(
        "--action", choices=["enable", "disable", "pause", "resume", "stop"], required=True
    )
    parser.add_argument("--expected-version", type=int)
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--dry-run", action="store_true")


def _build_account_control_arguments(args: argparse.Namespace) -> dict[str, Any]:
    if args.action in {"enable", "disable"} and not args.expected_version:
        raise ValueError("enable/disable requires --expected-version from +plan-get")
    if not args.yes and not args.dry_run:
        raise ValueError("Review the account and action, then pass --yes")
    return {
        **_build_plan_id_arguments(args),
        "account_id": args.account_id,
        "action": args.action,
        "expected_version": args.expected_version,
        "destructive_confirmation": args.yes,
        "dry_run": args.dry_run,
    }


async def _execute_account_control(ctx: CommandContext) -> Any:
    _, plan, detail = await _locate_plan(ctx)
    member = next(
        (
            unit
            for unit in detail.get("op_units") or []
            if unit.get("agentic_persona_plan_id") == plan["id"]
            and unit.get("pool_account_id") == ctx.arguments["account_id"]
        ),
        None,
    )
    if member is None:
        raise ValueError("Account is not a member of the selected Plan")
    action = ctx.arguments["action"]
    if action in {"enable", "disable"}:
        return await ctx.api_data_v2(
            ctx.cfg,
            "PUT",
            f"/account-operations/{member['id']}/native-schedule-execution",
            json_body={
                "workspace_id": ctx.workspace_id,
                "expected_version": ctx.arguments["expected_version"],
                "enabled": action == "enable",
            },
        )
    return await ctx.api_data_v2(
        ctx.cfg,
        "POST",
        f"/account-operations/{member['id']}/{action}",
        params={"workspace_id": ctx.workspace_id},
    )


def _account_control_spec() -> CommandSpec:
    return CommandSpec(
        domain=Domain.AGENTIC_CAMPAIGN,
        resource="plan",
        shortcut="+account-control",
        summary="Control one explicitly selected Museon managed member. Enable after reviewed rollout; pause/resume preserve membership; stop retires and releases it. Already-submitted posts keep reconciling.",
        risk_level="destructive",
        execution="direct",
        adapter_tool_name="agentic_campaign_plan_account_control",
        input_schema=_plan_schema(
            {
                "account_id": _uuid_property("Member account"),
                "action": {"enum": ["enable", "disable", "pause", "resume", "stop"]},
                "expected_version": {"type": ["integer", "null"], "minimum": 1},
                "destructive_confirmation": {"type": "boolean"},
                "dry_run": {"type": "boolean"},
            },
            required=["account_id", "action"],
        ),
        output_schema=_direct_output_schema("Authoritative account execution state"),
        examples=[],
        supports_dry_run=True,
        requires_confirmation=True,
        required_roles=("workspace_admin_or_staff",),
        add_arguments=_add_account_control_arguments,
        build_arguments=_build_account_control_arguments,
    )


def _add_posts_arguments(parser: argparse.ArgumentParser) -> None:
    _add_plan_id_arguments(parser)
    parser.add_argument("--account-id")
    parser.add_argument("--element-id")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--sort", choices=["recent", "views"], default="recent")
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--page-size", type=int, default=50)


def _build_posts_arguments(args: argparse.Namespace) -> dict[str, Any]:
    if not 1 <= args.days <= 365 or args.page < 1 or not 1 <= args.page_size <= 200:
        raise ValueError("days must be 1..365, page positive and page-size 1..200")
    return {
        **_build_plan_id_arguments(args),
        "account_id": args.account_id,
        "element_id": args.element_id,
        "days": args.days,
        "sort": args.sort,
        "page": args.page,
        "page_size": args.page_size,
    }


async def _execute_posts(ctx: CommandContext) -> Any:
    return await ctx.api_data_v2(
        ctx.cfg,
        "GET",
        f"/agentic-creative-campaigns/{ctx.arguments['campaign_id']}/persona-plans/{ctx.arguments['plan_id']}/posts",
        params=compact_params(
            {
                "workspace_id": ctx.workspace_id,
                **{
                    key: value
                    for key, value in ctx.arguments.items()
                    if key in {"account_id", "element_id", "days", "sort", "page", "page_size"}
                },
            }
        ),
    )


async def _execute_review_only(ctx: CommandContext) -> Any:
    return await ctx.api_data_v2(
        ctx.cfg,
        "PUT",
        f"/agentic-creative-campaigns/{ctx.arguments['campaign_id']}/policy",
        json_body={
            "workspace_id": ctx.workspace_id,
            "version": 1,
            "veto_window_minutes": 0,
            "max_auto_element_ops": 0,
            "auto_recruit": {"enabled": False},
        },
    )


def _managed_read_specs() -> list[CommandSpec]:
    return [
        CommandSpec(
            domain=Domain.AGENTIC_CAMPAIGN,
            resource="plan",
            shortcut="+posts",
            summary="Read this Plan's posts and metrics by account or reference. Missing metrics are not zero results; platform acceptance is not public-post confirmation.",
            risk_level="read",
            execution="direct",
            adapter_tool_name="agentic_campaign_plan_posts",
            input_schema=_plan_schema(
                {
                    "account_id": {"type": ["string", "null"]},
                    "element_id": {"type": ["string", "null"]},
                    "days": {"type": "integer", "minimum": 1, "maximum": 365},
                    "sort": {"enum": ["recent", "views"]},
                    "page": {"type": "integer", "minimum": 1},
                    "page_size": {"type": "integer", "minimum": 1, "maximum": 200},
                }
            ),
            output_schema=_direct_output_schema(
                "Posts, generation and publication state, attribution and metrics"
            ),
            examples=[],
            add_arguments=_add_posts_arguments,
            build_arguments=_build_posts_arguments,
        ),
        CommandSpec(
            domain=Domain.AGENTIC_CAMPAIGN,
            shortcut="+campaign-review-only",
            summary="Require manual review for future reference/persona/strategy changes in this Museon Campaign, and disable automatic recruitment. Existing confirmed publishing continues. New CLI campaigns use this policy by default.",
            risk_level="write",
            execution="direct",
            adapter_tool_name="agentic_campaign_review_only",
            input_schema=_schema(
                {"campaign_id": _uuid_property("Campaign id"), "dry_run": {"type": "boolean"}},
                required=["campaign_id"],
            ),
            output_schema=_direct_output_schema("Persisted review-only policy"),
            examples=[],
            supports_dry_run=True,
            add_arguments=_add_campaign_lifecycle_arguments,
            build_arguments=_build_campaign_lifecycle_arguments,
        ),
    ]


def _managed_enveloped(fn, *, redact_api_errors: bool = True):
    wrapped = redacted_direct_enveloped(fn, redact_api_errors=redact_api_errors)

    async def execute(ctx: CommandContext) -> dict[str, Any]:
        response = await wrapped(ctx)
        data = response.get("data")
        returned_campaign = data.get("campaign") if isinstance(data, dict) else None
        campaign_id = ctx.arguments.get("campaign_id") or (
            returned_campaign.get("id") if isinstance(returned_campaign, dict) else None
        )
        plan_id = ctx.arguments.get("plan_id")
        if campaign_id and plan_id:
            path = f"/admin/account-ops-lab/experiment-brain/{quote(str(campaign_id), safe='')}/plans/{quote(str(plan_id), safe='')}/review"
            response["web_url"] = (
                ctx.cfg.site_url.rstrip("/")
                + path
                + "?"
                + urlencode({"workspace_id": ctx.workspace_id or ""})
            )
        elif campaign_id:
            response["web_url"] = (
                ctx.cfg.site_url.rstrip("/")
                + "/admin/account-ops-lab?"
                + urlencode(
                    {
                        "surface": "session-operations",
                        "campaign": campaign_id,
                        "workspace_id": ctx.workspace_id or "",
                    }
                )
            )
        return response

    return execute


EXECUTORS = {
    "agentic-campaign.plan-posts": _managed_enveloped(_execute_posts, redact_api_errors=True),
    "agentic-campaign.campaign-review-only": _managed_enveloped(
        _execute_review_only, redact_api_errors=True
    ),
    "agentic-campaign.plan-account-control": _managed_enveloped(
        _execute_account_control, redact_api_errors=True
    ),
    "agentic-campaign.plan-supply-update": _managed_enveloped(
        _execute_supply, redact_api_errors=True
    ),
    "agentic-campaign.confirm-schedule-rollout": _managed_enveloped(
        _execute_confirm_schedule_rollout, redact_api_errors=True
    ),
    "agentic-campaign.campaign-activate": _managed_enveloped(
        _execute_campaign_activate, redact_api_errors=True
    ),
    "agentic-campaign.campaign-archive": _managed_enveloped(
        _execute_campaign_archive, redact_api_errors=True
    ),
    "agentic-campaign.campaign-create": _managed_enveloped(
        _execute_campaign_create, redact_api_errors=True
    ),
    "agentic-campaign.campaign-update": _managed_enveloped(
        _execute_campaign_update, redact_api_errors=True
    ),
    "agentic-campaign.campaign-pause": _managed_enveloped(
        _execute_campaign_pause, redact_api_errors=True
    ),
    "agentic-campaign.get": _managed_enveloped(_execute_get, redact_api_errors=True),
    "agentic-campaign.list": _managed_enveloped(_execute_list, redact_api_errors=True),
    "agentic-campaign.plan-attribution": _managed_enveloped(
        _execute_plan_attribution, redact_api_errors=True
    ),
    "agentic-campaign.plan-create": _managed_enveloped(
        _execute_plan_create, redact_api_errors=True
    ),
    "agentic-campaign.plan-get": _managed_enveloped(_execute_plan_get, redact_api_errors=True),
    "agentic-campaign.plan-list": _managed_enveloped(_execute_plan_list, redact_api_errors=True),
    "agentic-campaign.plan-update": _managed_enveloped(
        _execute_plan_update, redact_api_errors=True
    ),
    "agentic-campaign.plan-members-reconcile": _managed_enveloped(
        _execute_plan_members_reconcile, redact_api_errors=True
    ),
    "agentic-campaign.proposal-list": _managed_enveloped(
        _execute_proposal_list, redact_api_errors=True
    ),
    "agentic-campaign.proposal-get": _managed_enveloped(
        _execute_proposal_get, redact_api_errors=True
    ),
    "agentic-campaign.proposal-withdraw": _managed_enveloped(
        _execute_proposal_withdraw, redact_api_errors=True
    ),
    "agentic-campaign.schedule-rollout-get": _managed_enveloped(
        _execute_schedule_rollout_get, redact_api_errors=True
    ),
    "agentic-campaign.schedule-rollout-preflight": _managed_enveloped(
        _execute_schedule_rollout_preflight, redact_api_errors=True
    ),
    "agentic-campaign.plan-tags": _managed_enveloped(_execute_plan_tags, redact_api_errors=True),
}
