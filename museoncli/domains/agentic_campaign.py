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
    parser.add_argument("--candidate-id")
    parser.add_argument("--note")
    parser.add_argument("--name")
    parser.add_argument("--persona-json")
    parser.add_argument("--elements-json")
    parser.add_argument("--add-elements-json")
    parser.add_argument("--retire-element-ids")
    parser.add_argument("--boost-elements-json")
    parser.add_argument("--dry-run", action="store_true")


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
) -> dict[str, list[Any]]:
    changes = {
        "add_elements": list(add_elements or []),
        "retire_element_ids": _csv(retire_element_ids),
        "boost_elements": list(boost_elements or []),
    }
    if not any(changes.values()):
        raise ValueError(
            "agentic-campaign +plan-propose requires at least one of "
            "--add-elements-json, --retire-element-ids, or --boost-elements-json."
        )
    return changes


def _build_plan_propose_arguments(args: argparse.Namespace) -> dict[str, Any]:
    solution_supplied = any(
        value is not None for value in (args.name, args.persona_json, args.elements_json)
    )
    adjustment_supplied = any(
        value is not None
        for value in (
            args.add_elements_json,
            args.retire_element_ids,
            args.boost_elements_json,
        )
    )
    if solution_supplied and adjustment_supplied:
        raise ValueError("一次提案只能是一种:整套方案 或 调整")
    if not solution_supplied and not adjustment_supplied:
        raise ValueError(
            "agentic-campaign +plan-propose requires either a complete plan or an adjustment."
        )
    if solution_supplied and not all(
        value is not None for value in (args.persona_json, args.elements_json)
    ):
        raise ValueError(
            "complete plan proposal requires --persona-json and --elements-json; "
            "--name is also required when submitting a new candidate."
        )

    payload: dict[str, Any] = compact_params(
        {
            "plan_id": args.plan_id,
            "candidate_id": args.candidate_id,
            "note": args.note,
            "dry_run": args.dry_run,
        }
    )
    if solution_supplied:
        payload.update(
            {
                "name": args.name,
                "persona_payload": (
                    _candidate_json(
                        args.persona_json,
                        field="persona",
                        expected_type=dict,
                    )
                    if args.persona_json is not None
                    else None
                ),
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
        payload["changes"] = _revision_changes(
            add_elements=_revision_json_list(args.add_elements_json, field="add-elements"),
            retire_element_ids=args.retire_element_ids,
            boost_elements=_revision_json_list(args.boost_elements_json, field="boost-elements"),
        )
    return payload


def _add_campaign_rename_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--dry-run", action="store_true")


def _build_campaign_rename_arguments(args: argparse.Namespace) -> dict[str, Any]:
    return {"campaign_id": args.campaign_id, "name": args.name, "dry_run": args.dry_run}


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
            shortcut="+plan-propose",
            summary="Propose a complete draft plan or an active-plan adjustment for operator review.",
            risk_level="write",
            execution="direct",
            adapter_tool_name="agentic_campaign_plan_propose",
            input_schema={
                "type": "object",
                "description": (
                    "For a draft plan, submit a complete solution (name, persona_payload, and "
                    "elements), optionally revising a candidate with candidate_id. For an active "
                    "plan, submit at least one adjustment in changes; candidate_id is not allowed."
                ),
                "properties": {
                    "plan_id": _uuid_property("Agentic Persona Plan id"),
                    "candidate_id": {
                        "type": ["string", "null"],
                        "format": "uuid",
                        "description": "Draft-plan candidate id to revise",
                    },
                    "name": {"type": "string", "minLength": 1, "maxLength": 200},
                    "persona_payload": _persona_payload_schema(),
                    "elements": _candidate_elements_schema(),
                    "changes": {
                        "type": "object",
                        "additionalProperties": False,
                        "anyOf": [
                            {"properties": {"add_elements": {"minItems": 1}}},
                            {"properties": {"retire_element_ids": {"minItems": 1}}},
                            {"properties": {"boost_elements": {"minItems": 1}}},
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
                    "dry_run": {"type": "boolean", "default": False},
                },
                "required": ["plan_id"],
                "oneOf": [
                    {
                        "title": "Complete plan proposal",
                        "required": ["persona_payload", "elements"],
                        "anyOf": [
                            {"required": ["name"]},
                            {
                                "required": ["candidate_id"],
                                "properties": {
                                    "candidate_id": {"type": "string", "format": "uuid"}
                                },
                            },
                        ],
                        "not": {"required": ["changes"]},
                    },
                    {
                        "title": "Active plan adjustment",
                        "required": ["changes"],
                        "not": {
                            "anyOf": [
                                {"required": ["name"]},
                                {"required": ["persona_payload"]},
                                {"required": ["elements"]},
                            ]
                        },
                    },
                ],
            },
            output_schema=_direct_output_schema(
                "Candidate or adjustment proposal id, change summary, and operator review reminder."
            ),
            examples=[
                "museoncli agentic-campaign +plan-propose "
                "--plan-id 33333333-3333-4333-8333-333333333333 "
                "--name 'DIY problem solver' "
                """--persona-json '{"name":"Mia","description":"Practical maker","""
                """"visual_prompt":"Warm workshop portrait","reference_media_ids":[]}' """
                """--elements-json '[{"format_id":"44444444-4444-4444-8444-444444444444","""
                """"topic_id":"55555555-5555-4555-8555-555555555555"}]'"""
            ],
            add_arguments=_add_plan_propose_arguments,
            build_arguments=_build_plan_propose_arguments,
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
) -> tuple[str | None, dict[str, Any], list[Any]]:
    name = ctx.arguments.get("name")
    persona_payload = ctx.arguments.get("persona_payload")
    elements = ctx.arguments.get("elements")
    if not isinstance(persona_payload, dict) or not isinstance(elements, list):
        raise ValueError("draft plan proposal requires --persona-json and --elements-json.")
    if not elements:
        raise ValueError("draft plan proposal requires at least one element.")
    return str(name) if name else None, persona_payload, elements


def _proposal_output(response: Any, *, changes: dict[str, Any]) -> dict[str, Any]:
    payload = _payload_data(response)
    candidate = payload.get("candidate") if isinstance(payload, dict) else None
    candidate_id = candidate.get("id") if isinstance(candidate, dict) else None
    proposal = payload.get("proposal") if isinstance(payload, dict) else None
    proposal_id = proposal.get("id") if isinstance(proposal, dict) else None
    return {
        **({"candidate_id": candidate_id} if candidate is not None else {}),
        **({"proposal_id": proposal_id} if proposal is not None else {}),
        "change_summary": changes,
        "next_step": "Please review the proposal in Museon and confirm it there.",
    }


async def _execute_plan_propose(ctx: CommandContext) -> Any:
    campaign_id, plan, _ = await _locate_plan(ctx)
    status = plan.get("status")
    candidate_id = ctx.arguments.get("candidate_id")
    raw_changes = ctx.arguments.get("changes")
    has_solution = any(
        ctx.arguments.get(key) is not None for key in ("name", "persona_payload", "elements")
    )
    has_adjustment = raw_changes is not None
    if has_solution and has_adjustment:
        raise ValueError("一次提案只能是一种:整套方案 或 调整")

    if status == "draft":
        if has_adjustment:
            raise ValueError("draft plan only accepts a complete plan proposal.")
        name, persona_payload, elements = _complete_plan_arguments(ctx)
        if candidate_id:
            path = (
                f"/agentic-creative-campaigns/{campaign_id}/persona-plans/{plan['id']}/"
                f"candidates/{candidate_id}:revise"
            )
            body = {
                "workspace_id": ctx.workspace_id,
                "persona_payload": persona_payload,
                "elements": elements,
                "note": ctx.arguments.get("note"),
            }
        else:
            if not name:
                raise ValueError("new draft plan proposal requires --name.")
            path = (
                f"/agentic-creative-campaigns/{campaign_id}/persona-plans/"
                f"{plan['id']}/candidates:submit"
            )
            body = {
                "workspace_id": ctx.workspace_id,
                "name": name,
                "persona_payload": persona_payload,
                "elements": elements,
            }
        response = await ctx.api_data_v2(ctx.cfg, "POST", path, json_body=body)
        return _proposal_output(
            response,
            changes={
                "complete_plan": True,
                **({"name": name} if name else {}),
                "directions": len(elements),
            },
        )

    if status != "active":
        raise ValueError(
            f"plan status must be draft or active to accept a proposal; got {status!r}."
        )
    if candidate_id:
        raise ValueError("--candidate-id is only valid for a draft plan.")
    if has_solution:
        raise ValueError("active plan only accepts an adjustment proposal.")
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
    return _proposal_output(
        response,
        changes={
            "new_directions": len(changes["add_elements"]),
            "directions_to_stop": len(changes["retire_element_ids"]),
            "winner_boosts": len(changes["boost_elements"]),
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
    "agentic-campaign.get": redacted_direct_enveloped(_execute_get, redact_api_errors=True),
    "agentic-campaign.issues-pull": redacted_direct_enveloped(
        _execute_issues_pull, redact_api_errors=True
    ),
    "agentic-campaign.list": redacted_direct_enveloped(_execute_list, redact_api_errors=True),
    "agentic-campaign.plan-attribution": redacted_direct_enveloped(
        _execute_plan_attribution, redact_api_errors=True
    ),
    "agentic-campaign.plan-get": redacted_direct_enveloped(
        _execute_plan_get, redact_api_errors=True
    ),
    "agentic-campaign.plan-list": redacted_direct_enveloped(
        _execute_plan_list, redact_api_errors=True
    ),
    "agentic-campaign.plan-propose": redacted_direct_enveloped(
        _execute_plan_propose, redact_api_errors=True
    ),
    "agentic-campaign.plan-tags": redacted_direct_enveloped(
        _execute_plan_tags, redact_api_errors=True
    ),
}
