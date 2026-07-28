from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

import pytest
import httpx

from museoncli import main as main_module
from museoncli.config import Config
from museoncli.domains import agentic_campaign, command_executor, get_command_spec
from museoncli.execution import CommandContext
from museoncli.main import ApiRequestError, build_parser


def parse(argv: list[str]) -> argparse.Namespace:
    return build_parser().parse_args(argv)


class Capture:
    def __init__(self, *responses: Any) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, cfg, method, path, *, json_body=None, params=None, **kwargs):
        self.calls.append(
            {"method": method, "path": path, "json_body": json_body, "params": params}
        )
        response = self.responses.pop(0) if self.responses else {}
        if isinstance(response, Exception):
            raise response
        return response


def context(
    command: str,
    arguments: dict[str, Any],
    capture: Capture,
    *,
    runtime: dict[str, Any] | None = None,
) -> CommandContext:
    cfg = Config()
    cfg.runtime_context = runtime or {}
    return CommandContext(
        cfg=cfg,
        spec=get_command_spec(command),
        args=None,
        arguments=arguments,
        workspace_id="11111111-1111-4111-8111-111111111111",
        api_data=capture,
        api_data_v2=capture,
        upload_media_file=capture,
        upload_artifact_file=capture,
    )


def campaign_list(plan_id: str) -> dict[str, Any]:
    return {
        "items": [{"id": "22222222-2222-4222-8222-222222222222"}],
        "meta": {"page": 1, "page_size": 100, "total": 1},
    }


def empty_campaign_page(*, page: int, total: int) -> dict[str, Any]:
    return {
        "items": [],
        "meta": {"page": page, "page_size": 100, "total": total},
    }


def campaign_detail(plan_id: str, *, status: str = "draft") -> dict[str, Any]:
    return {
        "campaign": {"id": "22222222-2222-4222-8222-222222222222"},
        "agentic_persona_plans": [
            {
                "id": plan_id,
                "name": "DIY",
                "version": 7,
                "persona_id": None,
                "status": status,
            }
        ],
        "op_units": [
            {
                "id": "secret-op-id",
                "pool_account_id": "pool-1",
                "agentic_persona_plan_id": plan_id,
                "account": {"username": "maker_one"},
            }
        ],
    }


def _complete_plan_cli_args() -> list[str]:
    return [
        "--name",
        "DIY problem solver",
        "--persona-json",
        json.dumps(
            {
                "name": "Mia",
                "description": "Practical maker",
                "visual_prompt": "Warm workshop portrait",
                "reference_media_ids": ["88888888-8888-4888-8888-888888888888"],
            }
        ),
        "--elements-json",
        json.dumps(
            [
                {
                    "format_id": "44444444-4444-4444-8444-444444444444",
                    "topic_id": "55555555-5555-4555-8555-555555555555",
                    "cta_target_id": "66666666-6666-4666-8666-666666666666",
                }
            ]
        ),
    ]


@pytest.mark.parametrize("candidate_id", [None, "77777777-7777-4777-8777-777777777777"])
def test_plan_propose_dispatches_draft_submit_or_revise(candidate_id: str | None) -> None:
    plan_id = "33333333-3333-4333-8333-333333333333"
    capture = Capture(
        campaign_list(plan_id),
        campaign_detail(plan_id),
        {"candidate": {"id": "candidate-1"}},
    )
    argv = ["agentic-campaign", "+plan-propose", "--plan-id", plan_id]
    complete_args = _complete_plan_cli_args()
    if candidate_id:
        argv.extend(["--candidate-id", candidate_id, "--note", "Brighter visual direction"])
        complete_args = complete_args[2:]
    args = parse([*argv, *complete_args])
    arguments = agentic_campaign._build_plan_propose_arguments(args)
    result = asyncio.run(
        agentic_campaign._execute_plan_propose(
            context("agentic-campaign.plan-propose", arguments, capture)
        )
    )
    call = capture.calls[-1]
    expected_suffix = f"/candidates/{candidate_id}:revise" if candidate_id else "/candidates:submit"
    assert call["path"].endswith(expected_suffix)
    assert call["json_body"]["persona_payload"]["name"] == "Mia"
    assert call["json_body"]["elements"][0]["format_id"].startswith("4444")
    assert ("name" in call["json_body"]) is (candidate_id is None)
    assert result == {
        "candidate_id": "candidate-1",
        "change_summary": {
            "complete_plan": True,
            **({"name": "DIY problem solver"} if candidate_id is None else {}),
            "directions": 1,
        },
        "next_step": "Please review the proposal in Museon and confirm it there.",
    }


def test_plan_propose_dispatches_active_adjustment() -> None:
    plan_id = "33333333-3333-4333-8333-333333333333"
    add_elements = [
        {
            "format_id": "44444444-4444-4444-8444-444444444444",
            "topic_id": "55555555-5555-4555-8555-555555555555",
            "cta_target_id": "66666666-6666-4666-8666-666666666666",
        }
    ]
    boost_elements = [
        {
            "element_id": "77777777-7777-4777-8777-777777777777",
            "account_count": 3,
            "days": 7,
        }
    ]
    retire_element_ids = ["88888888-8888-4888-8888-888888888888"]
    capture = Capture(
        campaign_list(plan_id),
        campaign_detail(plan_id, status="active"),
        {"proposal": {"id": "proposal-1"}},
    )
    args = parse(
        [
            "agentic-campaign",
            "+plan-propose",
            "--plan-id",
            plan_id,
            "--add-elements-json",
            json.dumps(add_elements),
            "--retire-element-ids",
            ",".join(retire_element_ids),
            "--boost-elements-json",
            json.dumps(boost_elements),
            "--note",
            "Expand the winner",
        ]
    )
    arguments = agentic_campaign._build_plan_propose_arguments(args)

    result = asyncio.run(
        agentic_campaign._execute_plan_propose(
            context("agentic-campaign.plan-propose", arguments, capture)
        )
    )

    assert capture.calls[-1] == {
        "method": "POST",
        "path": (
            "/agentic-creative-campaigns/22222222-2222-4222-8222-222222222222/"
            f"persona-plans/{plan_id}/revision-proposals"
        ),
        "json_body": {
            "workspace_id": "11111111-1111-4111-8111-111111111111",
            "note": "Expand the winner",
            "changes": {
                "add_elements": add_elements,
                "retire_element_ids": retire_element_ids,
                "boost_elements": boost_elements,
            },
        },
        "params": None,
    }
    assert result == {
        "proposal_id": "proposal-1",
        "change_summary": {
            "new_directions": 1,
            "directions_to_stop": 1,
            "winner_boosts": 1,
        },
        "next_step": "Please review the proposal in Museon and confirm it there.",
    }


def test_plan_propose_schema_has_two_content_shapes_and_dry_run() -> None:
    spec = get_command_spec("agentic-campaign.plan-propose")
    args = parse(
        [
            "agentic-campaign",
            "+plan-propose",
            "--plan-id",
            "33333333-3333-4333-8333-333333333333",
            *_complete_plan_cli_args(),
            "--dry-run",
        ]
    )
    assert len(spec.input_schema["oneOf"]) == 2
    assert spec.supports_dry_run is True
    assert args.dry_run is True


def test_plan_propose_requires_one_complete_content_shape() -> None:
    args = parse(
        [
            "agentic-campaign",
            "+plan-propose",
            "--plan-id",
            "33333333-3333-4333-8333-333333333333",
        ]
    )
    with pytest.raises(ValueError, match="requires either a complete plan or an adjustment"):
        agentic_campaign._build_plan_propose_arguments(args)


def test_plan_propose_rejects_mixed_content() -> None:
    args = parse(
        [
            "agentic-campaign",
            "+plan-propose",
            "--plan-id",
            "33333333-3333-4333-8333-333333333333",
            *_complete_plan_cli_args(),
            "--retire-element-ids",
            "77777777-7777-4777-8777-777777777777",
        ]
    )
    with pytest.raises(ValueError, match="一次提案只能是一种:整套方案 或 调整"):
        agentic_campaign._build_plan_propose_arguments(args)


@pytest.mark.parametrize("status", [None, "archived"])
def test_plan_propose_rejects_missing_or_unknown_status(status: str | None) -> None:
    plan_id = "33333333-3333-4333-8333-333333333333"
    detail = campaign_detail(plan_id)
    plan = detail["agentic_persona_plans"][0]
    if status is None:
        plan.pop("status")
    else:
        plan["status"] = status
    capture = Capture(campaign_list(plan_id), detail)
    args = parse(
        [
            "agentic-campaign",
            "+plan-propose",
            "--plan-id",
            plan_id,
            *_complete_plan_cli_args(),
        ]
    )
    with pytest.raises(ValueError, match="plan status must be draft or active"):
        asyncio.run(
            agentic_campaign._execute_plan_propose(
                context(
                    "agentic-campaign.plan-propose",
                    agentic_campaign._build_plan_propose_arguments(args),
                    capture,
                )
            )
        )


def test_campaign_rename_gets_version_and_only_patches_name() -> None:
    campaign_id = "22222222-2222-4222-8222-222222222222"
    capture = Capture(
        {"campaign": {"id": campaign_id, "version": 9, "name": "Old name"}},
        {"campaign": {"id": campaign_id, "version": 10, "name": "New name"}},
    )

    asyncio.run(
        agentic_campaign._execute_campaign_rename(
            context(
                "agentic-campaign.campaign-rename",
                {"campaign_id": campaign_id, "name": "New name"},
                capture,
            )
        )
    )

    assert capture.calls == [
        {
            "method": "GET",
            "path": f"/agentic-creative-campaigns/{campaign_id}",
            "json_body": None,
            "params": {"workspace_id": "11111111-1111-4111-8111-111111111111"},
        },
        {
            "method": "PATCH",
            "path": f"/agentic-creative-campaigns/{campaign_id}",
            "json_body": {
                "workspace_id": "11111111-1111-4111-8111-111111111111",
                "expected_version": 9,
                "name": "New name",
            },
            "params": None,
        },
    ]
    business_patch = capture.calls[-1]["json_body"]
    assert set(business_patch) - {"workspace_id", "expected_version"} == {"name"}


def test_plan_get_resolves_campaign_and_only_returns_display_account_identity() -> None:
    plan_id = "33333333-3333-4333-8333-333333333333"
    capture = Capture(campaign_list(plan_id), campaign_detail(plan_id))
    result = asyncio.run(
        agentic_campaign._execute_plan_get(
            context("agentic-campaign.plan-get", {"plan_id": plan_id}, capture)
        )
    )
    assert result["accounts"] == [{"pool_account_id": "pool-1", "handle": "maker_one"}]
    assert "secret-op-id" not in repr(result)
    assert capture.calls[0]["path"] == "/agentic-creative-campaigns"


def test_plan_locator_finds_plan_on_second_page() -> None:
    plan_id = "33333333-3333-4333-8333-333333333333"
    first_campaign = "22222222-2222-4222-8222-222222222221"
    second_campaign = "22222222-2222-4222-8222-222222222222"
    capture = Capture(
        {
            "items": [{"id": first_campaign}],
            "meta": {"page": 1, "page_size": 100, "total": 101},
        },
        {"agentic_persona_plans": [], "op_units": []},
        {
            "items": [{"id": second_campaign}],
            "meta": {"page": 2, "page_size": 100, "total": 101},
        },
        campaign_detail(plan_id),
    )
    campaign_id, plan, _ = asyncio.run(
        agentic_campaign._locate_plan(
            context("agentic-campaign.plan-get", {"plan_id": plan_id}, capture)
        )
    )
    assert campaign_id == second_campaign
    assert plan["id"] == plan_id
    assert [
        call["params"]["page"] for call in capture.calls if call["path"].endswith("campaigns")
    ] == [
        1,
        2,
    ]


def test_plan_locator_not_found_reports_scanned_pages() -> None:
    plan_id = "33333333-3333-4333-8333-333333333333"
    capture = Capture(
        {
            "items": [{"id": "22222222-2222-4222-8222-222222222221"}],
            "meta": {"page": 1, "page_size": 100, "total": 101},
        },
        {"agentic_persona_plans": []},
        empty_campaign_page(page=2, total=101),
    )
    with pytest.raises(RuntimeError, match=r"scanned 2 pages"):
        asyncio.run(
            agentic_campaign._locate_plan(
                context("agentic-campaign.plan-get", {"plan_id": plan_id}, capture)
            )
        )


def test_plan_locator_total_boundary_does_not_fetch_extra_page() -> None:
    plan_id = "33333333-3333-4333-8333-333333333333"
    capture = Capture(empty_campaign_page(page=1, total=100))
    with pytest.raises(RuntimeError, match=r"scanned 1 pages"):
        asyncio.run(
            agentic_campaign._locate_plan(
                context("agentic-campaign.plan-get", {"plan_id": plan_id}, capture)
            )
        )
    assert len(capture.calls) == 1


def test_issues_pull_uses_full_v2_url_and_complete_payload(monkeypatch) -> None:
    sent: dict[str, Any] = {}

    async def fake_send(cfg, method, url, *, json_body, params):
        sent.update(method=method, url=url, json_body=json_body, params=params)
        return httpx.Response(
            200,
            json={
                "data": {
                    "issues": [
                        {
                            "issue_id": "issue-1",
                            "account_operation_id": "secret-op-id",
                            "pool_account_id": "pool-1",
                            "handle": "maker_one",
                        }
                    ]
                }
            },
        )

    monkeypatch.setattr(main_module, "_api_send", fake_send)
    campaign_id = "22222222-2222-4222-8222-222222222222"
    cfg = Config()
    cfg.auth.api_key = "test-key"
    cfg.workspace.id = "11111111-1111-4111-8111-111111111111"
    cfg.runtime_context = {
        "conversation_id": "55555555-5555-4555-8555-555555555555",
        "scope_conversation_id": "66666666-6666-4666-8666-666666666666",
    }
    args = parse(
        [
            "agentic-campaign",
            "+issues-pull",
            "--campaign-id",
            campaign_id,
            "--limit",
            "17",
        ]
    )
    result = asyncio.run(main_module.dispatch_domain_command(args, cfg))
    assert sent["url"] == (
        "https://api.museon.ai/api/v2/account-operation-issues:pull-triage-batch"
    )
    assert sent["json_body"] == {
        "workspace_id": "11111111-1111-4111-8111-111111111111",
        "session_conversation_id": "55555555-5555-4555-8555-555555555555",
        "scope_conversation_id": "66666666-6666-4666-8666-666666666666",
        "campaign_id": campaign_id,
        "limit": 17,
    }
    assert "secret-op-id" not in repr(result)


def test_issues_pull_requires_campaign_id_in_cli_and_contract() -> None:
    with pytest.raises(SystemExit):
        parse(["agentic-campaign", "+issues-pull", "--limit", "20"])

    spec = get_command_spec("agentic-campaign.issues-pull")
    assert spec.input_schema["required"] == ["campaign_id", "limit"]
    assert spec.input_schema["properties"]["campaign_id"]["type"] == "string"


@pytest.mark.parametrize(
    ("command", "arguments", "responses"),
    [
        (
            "agentic-campaign.list",
            {"page": 1, "page_size": 20},
            [
                {
                    "items": [
                        {
                            "operation_transition": {
                                "failures": [{"operation_id": "secret-operation-id"}]
                            }
                        }
                    ]
                }
            ],
        ),
        (
            "agentic-campaign.get",
            {"campaign_id": "22222222-2222-4222-8222-222222222222"},
            [{"op_units": [{"id": "secret-operation-id", "pool_account_id": "pool-1"}]}],
        ),
    ],
)
def test_agentic_success_boundary_redacts_confirmed_leaks(
    command: str,
    arguments: dict[str, Any],
    responses: list[Any],
) -> None:
    capture = Capture(*responses)
    result = asyncio.run(command_executor(command)(context(command, arguments, capture)))
    assert "secret-operation-id" not in repr(result)


def test_agentic_error_boundary_redacts_api_detail() -> None:
    capture = Capture(
        ApiRequestError(
            422,
            {
                "operation_id": "secret-operation-id",
                "nested": {"account_operation_id": "also-secret"},
            },
        )
    )
    ctx = context("agentic-campaign.list", {"page": 1, "page_size": 20}, capture)
    with pytest.raises(ApiRequestError) as raised:
        asyncio.run(command_executor("agentic-campaign.list")(ctx))
    assert raised.value.status_code == 422
    assert raised.value.detail == {"nested": {}}
    assert "secret-operation-id" not in str(raised.value)


def test_issues_pull_requires_runtime_conversation_identity() -> None:
    with pytest.raises(RuntimeError, match="conversation identity"):
        asyncio.run(
            agentic_campaign._execute_issues_pull(
                context(
                    "agentic-campaign.issues-pull",
                    {"limit": 20},
                    Capture(),
                )
            )
        )
