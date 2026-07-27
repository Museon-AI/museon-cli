from __future__ import annotations

import argparse
import asyncio
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


def campaign_detail(plan_id: str) -> dict[str, Any]:
    return {
        "campaign": {"id": "22222222-2222-4222-8222-222222222222"},
        "agentic_persona_plans": [{"id": plan_id, "name": "DIY", "version": 7, "persona_id": None}],
        "op_units": [
            {
                "id": "secret-op-id",
                "pool_account_id": "pool-1",
                "agentic_persona_plan_id": plan_id,
                "account": {"username": "maker_one"},
            }
        ],
    }


def test_parser_registers_domain_and_server_dry_run_defaults() -> None:
    args = parse(
        [
            "agentic-campaign",
            "+plan-submit",
            "--plan-id",
            "33333333-3333-4333-8333-333333333333",
            "--format-ids",
            "f1,f2",
        ]
    )
    assert args.domain_command == "agentic-campaign.plan-submit"
    assert args.dry_run is True
    assert agentic_campaign._build_plan_submit_arguments(args)["format_ids"] == ["f1", "f2"]

    apply_args = parse(
        [
            "agentic-campaign",
            "+plan-elements-replace",
            "--plan-id",
            "33333333-3333-4333-8333-333333333333",
            "--pause-format-ids",
            "f1",
            "--pause-topic-ids",
            "t1",
            "--no-dry-run",
        ]
    )
    built = agentic_campaign._build_elements_replace_arguments(apply_args)
    assert built["pause_format_ids"] == ["f1"]
    assert built["pause_topic_ids"] == ["t1"]
    assert built["dry_run"] is False


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


def test_plan_set_persona_uses_current_plan_version() -> None:
    plan_id = "33333333-3333-4333-8333-333333333333"
    capture = Capture(campaign_list(plan_id), campaign_detail(plan_id), {"campaign": {}})
    asyncio.run(
        agentic_campaign._execute_plan_set_persona(
            context(
                "agentic-campaign.plan-set-persona",
                {
                    "plan_id": plan_id,
                    "persona_id": "44444444-4444-4444-8444-444444444444",
                },
                capture,
            )
        )
    )
    call = capture.calls[-1]
    assert call["path"].endswith(f"/persona-plans/{plan_id}:set-persona")
    assert call["json_body"] == {
        "workspace_id": "11111111-1111-4111-8111-111111111111",
        "expected_version": 7,
        "persona_id": "44444444-4444-4444-8444-444444444444",
    }


def test_plan_submit_sends_server_dry_run_and_hashtags() -> None:
    plan_id = "33333333-3333-4333-8333-333333333333"
    capture = Capture(campaign_list(plan_id), campaign_detail(plan_id), {"results": []})
    asyncio.run(
        agentic_campaign._execute_plan_submit(
            context(
                "agentic-campaign.plan-submit",
                {
                    "plan_id": plan_id,
                    "format_ids": ["f1"],
                    "topic_ids": ["t1"],
                    "required_hashtags": ["#DIY"],
                    "dry_run": True,
                },
                capture,
            )
        )
    )
    assert capture.calls[-1]["json_body"] == {
        "workspace_id": "11111111-1111-4111-8111-111111111111",
        "dry_run": True,
        "format_ids": ["f1"],
        "topic_ids": ["t1"],
        "note": None,
        "required_hashtags": ["#DIY"],
    }


@pytest.mark.parametrize(
    ("shortcut", "extra_args", "expected_suffix"),
    [
        (
            "+plan-submit",
            [
                "--format-ids",
                "44444444-4444-4444-8444-444444444444",
            ],
            ":plan-submit",
        ),
        (
            "+plan-elements-replace",
            [
                "--pause-topic-ids",
                "55555555-5555-4555-8555-555555555555",
            ],
            ":elements-replace",
        ),
        (
            "+plan-strategy-decide",
            [],
            ":strategy-decide",
        ),
    ],
)
def test_fan_out_no_dry_run_reaches_server_payload(
    monkeypatch,
    shortcut: str,
    extra_args: list[str],
    expected_suffix: str,
) -> None:
    plan_id = "33333333-3333-4333-8333-333333333333"
    capture = Capture(campaign_list(plan_id), campaign_detail(plan_id), {"results": []})
    monkeypatch.setattr(main_module, "api_data_v2", capture)
    cfg = Config()
    cfg.workspace.id = "11111111-1111-4111-8111-111111111111"
    args = parse(
        [
            "agentic-campaign",
            shortcut,
            "--plan-id",
            plan_id,
            *extra_args,
            "--no-dry-run",
        ]
    )
    asyncio.run(main_module.dispatch_domain_command(args, cfg))
    assert capture.calls[-1]["path"].endswith(expected_suffix)
    assert capture.calls[-1]["json_body"]["dry_run"] is False


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
        "account_operation_issue_pull_assertion": "v1." + ("a" * 64),
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
        "session_assertion": "v1." + ("a" * 64),
        "scope_conversation_id": "66666666-6666-4666-8666-666666666666",
        "campaign_id": campaign_id,
        "limit": 17,
    }
    assert "secret-op-id" not in repr(result)


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
        (
            "agentic-campaign.plan-set-persona",
            {
                "plan_id": "33333333-3333-4333-8333-333333333333",
                "persona_id": "44444444-4444-4444-8444-444444444444",
            },
            [
                campaign_list("33333333-3333-4333-8333-333333333333"),
                campaign_detail("33333333-3333-4333-8333-333333333333"),
                {"op_units": [{"id": "secret-operation-id"}]},
            ],
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


def test_issues_pull_requires_server_attested_runtime_context() -> None:
    with pytest.raises(RuntimeError, match="session assertion"):
        asyncio.run(
            agentic_campaign._execute_issues_pull(
                context(
                    "agentic-campaign.issues-pull",
                    {"limit": 20},
                    Capture(),
                    runtime={"conversation_id": "session-1"},
                )
            )
        )
