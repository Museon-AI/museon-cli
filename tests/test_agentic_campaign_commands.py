from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

import pytest
import httpx

from museoncli import main as main_module
from museoncli.config import Config, WorkspaceState
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


def test_proposal_withdraw_dismisses_the_named_revision_proposal() -> None:
    plan_id = "33333333-3333-4333-8333-333333333333"
    proposal_id = "77777777-7777-4777-8777-777777777777"
    args = parse(
        [
            "agentic-campaign",
            "+proposal-withdraw",
            "--plan-id",
            plan_id,
            "--proposal-id",
            proposal_id,
        ]
    )
    arguments = agentic_campaign._build_proposal_withdraw_arguments(args)
    assert arguments == {
        "plan_id": plan_id,
        "proposal_id": proposal_id,
        "candidate_id": None,
        "dry_run": False,
    }
    capture = Capture(campaign_list(plan_id), campaign_detail(plan_id), {"id": proposal_id})
    asyncio.run(
        agentic_campaign._execute_proposal_withdraw(
            context("agentic-campaign.proposal-withdraw", arguments, capture)
        )
    )
    assert capture.calls[-1] == {
        "method": "POST",
        "path": (
            "/agentic-creative-campaigns/22222222-2222-4222-8222-222222222222/"
            f"persona-plans/{plan_id}/revision-proposals/{proposal_id}:dismiss"
        ),
        "json_body": {
            "workspace_id": "11111111-1111-4111-8111-111111111111",
        },
        "params": None,
    }
    spec = get_command_spec("agentic-campaign.proposal-withdraw")
    assert spec.risk_level == "write"
    assert spec.requires_confirmation is False
    assert spec.supports_dry_run is True
    assert spec.input_schema["required"] == ["plan_id", "proposal_id"]
    assert "candidate_id" not in spec.input_schema["properties"]


def test_proposal_withdraw_still_archives_a_candidate_for_the_deprecated_flag() -> None:
    """The published schema now teaches --proposal-id, but a sandbox running on a
    cached catalog can still be mid-flight with --candidate-id. Dropping the flag
    in the same release that renames it would break those callers."""
    plan_id = "33333333-3333-4333-8333-333333333333"
    candidate_id = "77777777-7777-4777-8777-777777777777"
    args = parse(
        [
            "agentic-campaign",
            "+proposal-withdraw",
            "--plan-id",
            plan_id,
            "--candidate-id",
            candidate_id,
        ]
    )
    arguments = agentic_campaign._build_proposal_withdraw_arguments(args)
    assert arguments["proposal_id"] is None
    capture = Capture(campaign_list(plan_id), campaign_detail(plan_id), {"id": candidate_id})
    asyncio.run(
        agentic_campaign._execute_proposal_withdraw(
            context("agentic-campaign.proposal-withdraw", arguments, capture)
        )
    )
    assert capture.calls[-1]["path"] == (
        "/agentic-creative-campaigns/22222222-2222-4222-8222-222222222222/"
        f"persona-plans/{plan_id}/candidates/{candidate_id}:archive"
    )


@pytest.mark.parametrize(
    "argv",
    [
        [
            "agentic-campaign",
            "+proposal-withdraw",
            "--proposal-id",
            "77777777-7777-4777-8777-777777777777",
        ],
        [
            "agentic-campaign",
            "+proposal-withdraw",
            "--plan-id",
            "33333333-3333-4333-8333-333333333333",
        ],
        [
            "agentic-campaign",
            "+proposal-withdraw",
            "--plan-id",
            "33333333-3333-4333-8333-333333333333",
            "--proposal-id",
            "77777777-7777-4777-8777-777777777777",
            "--candidate-id",
            "88888888-8888-4888-8888-888888888888",
        ],
    ],
)
def test_proposal_withdraw_requires_exactly_one_target_id(argv: list[str]) -> None:
    with pytest.raises(SystemExit):
        parse(argv)


def test_proposal_withdraw_dry_run_is_local(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fail_api(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("dry-run must not call the API")

    monkeypatch.setattr(main_module, "api_data_v2", fail_api)
    args = parse(
        [
            "agentic-campaign",
            "+proposal-withdraw",
            "--plan-id",
            "33333333-3333-4333-8333-333333333333",
            "--candidate-id",
            "77777777-7777-4777-8777-777777777777",
            "--dry-run",
        ]
    )
    cfg = Config(workspace=WorkspaceState(id="11111111-1111-4111-8111-111111111111"))
    result = asyncio.run(main_module.dispatch_domain_command(args, cfg))
    assert result["data"]["dry_run"] is True


def test_campaign_create_builds_extended_fields_and_field_config() -> None:
    args = parse(
        [
            "agentic-campaign",
            "+campaign-create",
            "--name",
            "Summer",
            "--cta-definition",
            "Shop the launch",
            "--required-hashtags",
            "#summer,#maker",
            "--required-mentions",
            "@museon",
            "--preferred-publish-windows-json",
            '[{"start":"09:00","end":"12:00"}]',
            "--bind-notification-conversation",
        ]
    )
    arguments = agentic_campaign._build_campaign_create_arguments(args)
    assert arguments == {
        "name": "Summer",
        "total_account_budget": 0,
        "cta_definition": "Shop the launch",
        "bind_notification_conversation": True,
        "config": {
            "required_hashtags": ["#summer", "#maker"],
            "required_mentions": ["@museon"],
            "preferred_publish_windows": [{"start": "09:00", "end": "12:00"}],
        },
        "dry_run": False,
    }
    capture = Capture({})
    asyncio.run(
        agentic_campaign._execute_campaign_create(
            context("agentic-campaign.campaign-create", arguments, capture)
        )
    )
    assert capture.calls == [
        {
            "method": "POST",
            "path": "/agentic-creative-campaigns",
            "json_body": {
                "workspace_id": "11111111-1111-4111-8111-111111111111",
                "name": "Summer",
                "total_account_budget": 0,
                "cta_definition": "Shop the launch",
                "bind_notification_conversation": True,
                "config": {
                    "required_hashtags": ["#summer", "#maker"],
                    "required_mentions": ["@museon"],
                    "preferred_publish_windows": [{"start": "09:00", "end": "12:00"}],
                },
            },
            "params": None,
        }
    ]


def test_campaign_create_rejects_config_json_with_field_config() -> None:
    args = parse(
        [
            "agentic-campaign",
            "+campaign-create",
            "--name",
            "Summer",
            "--config-json",
            "{}",
            "--required-hashtags",
            "#summer",
        ]
    )
    with pytest.raises(ValueError, match="mutually exclusive"):
        agentic_campaign._build_campaign_create_arguments(args)


def test_campaign_create_requires_name() -> None:
    with pytest.raises(SystemExit):
        parse(["agentic-campaign", "+campaign-create"])


def test_campaign_update_builds_field_level_config_patch_and_current_version() -> None:
    campaign_id = "22222222-2222-4222-8222-222222222222"
    args = parse(
        [
            "agentic-campaign",
            "+campaign-update",
            "--campaign-id",
            campaign_id,
            "--required-hashtags",
            "",
            "--required-mentions",
            "@museon",
            "--preferred-publish-windows-json",
            "[]",
        ]
    )
    arguments = agentic_campaign._build_campaign_update_arguments(args)
    assert arguments == {
        "campaign_id": campaign_id,
        "required_hashtags": [],
        "required_mentions": ["@museon"],
        "preferred_publish_windows": [],
        "dry_run": False,
    }
    assert "config" not in arguments
    capture = Capture({"campaign": {"id": campaign_id, "version": 9}}, {"id": campaign_id})
    asyncio.run(
        agentic_campaign._execute_campaign_update(
            context("agentic-campaign.campaign-update", arguments, capture)
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
                "required_hashtags": [],
                "required_mentions": ["@museon"],
                "preferred_publish_windows": [],
            },
            "params": None,
        },
    ]
    assert "config" not in capture.calls[-1]["json_body"]


def test_campaign_update_config_json_replaces_full_config() -> None:
    campaign_id = "22222222-2222-4222-8222-222222222222"
    args = parse(
        [
            "agentic-campaign",
            "+campaign-update",
            "--campaign-id",
            campaign_id,
            "--config-json",
            '{"required_hashtags":["#only"]}',
        ]
    )
    arguments = agentic_campaign._build_campaign_update_arguments(args)
    assert arguments == {
        "campaign_id": campaign_id,
        "config": {"required_hashtags": ["#only"]},
        "dry_run": False,
    }
    capture = Capture({"campaign": {"id": campaign_id, "version": 9}}, {})
    asyncio.run(
        agentic_campaign._execute_campaign_update(
            context("agentic-campaign.campaign-update", arguments, capture)
        )
    )
    assert capture.calls[-1]["json_body"] == {
        "workspace_id": "11111111-1111-4111-8111-111111111111",
        "expected_version": 9,
        "config": {"required_hashtags": ["#only"]},
    }


def test_campaign_update_builds_notification_binding_without_conversation_id() -> None:
    args = parse(
        [
            "agentic-campaign",
            "+campaign-update",
            "--campaign-id",
            "22222222-2222-4222-8222-222222222222",
            "--bind-notification-conversation",
        ]
    )
    arguments = agentic_campaign._build_campaign_update_arguments(args)
    assert arguments["bind_notification_conversation"] is True
    assert "conversation_id" not in arguments


@pytest.mark.parametrize(
    "extra,match",
    [
        ([], "at least one mutable flag"),
        (["--name", "New", "--total-account-budget", "107"], "mutually exclusive"),
        (
            ["--config-json", "{}", "--required-mentions", "@museon"],
            "mutually exclusive",
        ),
    ],
)
def test_campaign_update_rejects_invalid_field_combinations(extra: list[str], match: str) -> None:
    args = parse(
        [
            "agentic-campaign",
            "+campaign-update",
            "--campaign-id",
            "22222222-2222-4222-8222-222222222222",
            *extra,
        ]
    )
    with pytest.raises(ValueError, match=match):
        agentic_campaign._build_campaign_update_arguments(args)


def test_campaign_update_requires_campaign_id() -> None:
    with pytest.raises(SystemExit):
        parse(["agentic-campaign", "+campaign-update", "--name", "New"])


def test_campaign_update_requires_confirmation_and_accepts_yes() -> None:
    spec = get_command_spec("agentic-campaign.campaign-update")
    args = parse(
        [
            "agentic-campaign",
            "+campaign-update",
            "--campaign-id",
            "22222222-2222-4222-8222-222222222222",
            "--total-account-budget",
            "107",
            "--yes",
        ]
    )
    assert spec.risk_level == "write"
    assert spec.requires_confirmation is True
    assert spec.supports_dry_run is True
    assert args.yes is True


def test_plan_update_locates_version_and_patches_tokens() -> None:
    plan_id = "33333333-3333-4333-8333-333333333333"
    args = parse(
        [
            "agentic-campaign",
            "+plan-update",
            "--plan-id",
            plan_id,
            "--required-hashtags",
            "#maker,#diy",
            "--required-mentions",
            "",
        ]
    )
    arguments = agentic_campaign._build_plan_update_arguments(args)
    capture = Capture(campaign_list(plan_id), campaign_detail(plan_id), {"id": plan_id})
    asyncio.run(
        agentic_campaign._execute_plan_update(
            context("agentic-campaign.plan-update", arguments, capture)
        )
    )
    assert capture.calls[-1] == {
        "method": "PATCH",
        "path": (
            "/agentic-creative-campaigns/22222222-2222-4222-8222-222222222222/"
            f"agentic-persona-plans/{plan_id}"
        ),
        "json_body": {
            "workspace_id": "11111111-1111-4111-8111-111111111111",
            "expected_version": 7,
            "required_hashtags": ["#maker", "#diy"],
            "required_mentions": [],
        },
        "params": None,
    }


@pytest.mark.parametrize(
    "extra,match",
    [
        ([], "at least one mutable flag"),
        (
            ["--name", "New", "--required-hashtags", "#maker"],
            "mutually exclusive",
        ),
    ],
)
def test_plan_update_rejects_invalid_field_combinations(extra: list[str], match: str) -> None:
    args = parse(
        [
            "agentic-campaign",
            "+plan-update",
            "--plan-id",
            "33333333-3333-4333-8333-333333333333",
            *extra,
        ]
    )
    with pytest.raises(ValueError, match=match):
        agentic_campaign._build_plan_update_arguments(args)


def test_plan_update_requires_plan_id() -> None:
    with pytest.raises(SystemExit):
        parse(["agentic-campaign", "+plan-update", "--name", "New"])


def test_plan_propose_dispatches_draft_submit() -> None:
    plan_id = "33333333-3333-4333-8333-333333333333"
    capture = Capture(
        campaign_list(plan_id),
        campaign_detail(plan_id),
        {"candidate": {"id": "candidate-1"}},
    )
    argv = ["agentic-campaign", "+plan-propose", "--plan-id", plan_id]
    complete_args = _complete_plan_cli_args()
    args = parse([*argv, *complete_args])
    arguments = agentic_campaign._build_plan_propose_arguments(args)
    result = asyncio.run(
        agentic_campaign._execute_plan_propose(
            context("agentic-campaign.plan-propose", arguments, capture)
        )
    )
    call = capture.calls[-1]
    assert call["path"].endswith("/candidates:submit")
    assert call["json_body"]["persona_payload"]["name"] == "Mia"
    assert call["json_body"]["elements"][0]["format_id"].startswith("4444")
    assert "name" in call["json_body"]
    assert result == {
        "candidate_id": "candidate-1",
        "change_summary": {
            "complete_plan": True,
            "name": "DIY problem solver",
            "directions": 1,
        },
        "next_step": "Please review the proposal in Museon and confirm it there.",
    }


def test_plan_propose_dispatches_draft_submit_with_persona_id() -> None:
    plan_id = "33333333-3333-4333-8333-333333333333"
    persona_id = "99999999-9999-4999-8999-999999999999"
    capture = Capture(
        campaign_list(plan_id),
        campaign_detail(plan_id),
        {"candidate": {"id": "candidate-1"}},
    )
    argv = [
        "agentic-campaign",
        "+plan-propose",
        "--plan-id",
        plan_id,
        "--persona-id",
        persona_id,
        "--elements-json",
        json.dumps(
            [
                {
                    "format_id": "44444444-4444-4444-8444-444444444444",
                    "topic_id": "55555555-5555-4555-8555-555555555555",
                }
            ]
        ),
        "--name",
        "DIY problem solver",
    ]
    args = parse(argv)
    arguments = agentic_campaign._build_plan_propose_arguments(args)
    assert arguments["persona_id"] == persona_id
    assert "persona_payload" not in arguments
    result = asyncio.run(
        agentic_campaign._execute_plan_propose(
            context("agentic-campaign.plan-propose", arguments, capture)
        )
    )
    call = capture.calls[-1]
    assert call["path"].endswith("/candidates:submit")
    assert call["json_body"]["persona_id"] == persona_id
    assert "persona_payload" not in call["json_body"]
    assert result["candidate_id"] == "candidate-1"


def test_plan_propose_rejects_persona_json_and_persona_id_together() -> None:
    args = parse(
        [
            "agentic-campaign",
            "+plan-propose",
            "--plan-id",
            "33333333-3333-4333-8333-333333333333",
            "--name",
            "DIY problem solver",
            "--persona-json",
            json.dumps(
                {
                    "name": "Mia",
                    "description": "Practical maker",
                    "visual_prompt": "Portrait",
                }
            ),
            "--persona-id",
            "99999999-9999-4999-8999-999999999999",
            "--elements-json",
            json.dumps(
                [
                    {
                        "format_id": "44444444-4444-4444-8444-444444444444",
                        "topic_id": "55555555-5555-4555-8555-555555555555",
                    }
                ]
            ),
        ]
    )
    with pytest.raises(ValueError, match="mutually exclusive"):
        agentic_campaign._build_plan_propose_arguments(args)


def test_plan_propose_rejects_neither_persona_json_nor_persona_id() -> None:
    args = parse(
        [
            "agentic-campaign",
            "+plan-propose",
            "--plan-id",
            "33333333-3333-4333-8333-333333333333",
            "--name",
            "DIY problem solver",
            "--elements-json",
            json.dumps(
                [
                    {
                        "format_id": "44444444-4444-4444-8444-444444444444",
                        "topic_id": "55555555-5555-4555-8555-555555555555",
                    }
                ]
            ),
        ]
    )
    with pytest.raises(ValueError, match="exactly one of"):
        agentic_campaign._build_plan_propose_arguments(args)


_REVISION_ELEMENTS = [
    {
        "format_id": "44444444-4444-4444-8444-444444444444",
        "topic_id": "55555555-5555-4555-8555-555555555555",
    }
]


def test_plan_propose_revision_builds_arguments_with_persona_id() -> None:
    args = parse(
        [
            "agentic-campaign",
            "+plan-propose",
            "--plan-id",
            "33333333-3333-4333-8333-333333333333",
            "--proposal-id",
            "77777777-7777-4777-8777-777777777777",
            "--persona-id",
            "99999999-9999-4999-8999-999999999999",
            "--elements-json",
            json.dumps(_REVISION_ELEMENTS),
        ]
    )
    arguments = agentic_campaign._build_plan_propose_arguments(args)
    assert arguments == {
        "plan_id": "33333333-3333-4333-8333-333333333333",
        "proposal_id": "77777777-7777-4777-8777-777777777777",
        "elements": _REVISION_ELEMENTS,
        "persona_id": "99999999-9999-4999-8999-999999999999",
        "dry_run": False,
    }


def test_plan_propose_revision_builds_arguments_with_persona_payload() -> None:
    persona_payload = {"name": "Mia", "description": "Practical maker", "visual_prompt": "Portrait"}
    args = parse(
        [
            "agentic-campaign",
            "+plan-propose",
            "--plan-id",
            "33333333-3333-4333-8333-333333333333",
            "--proposal-id",
            "77777777-7777-4777-8777-777777777777",
            "--persona-json",
            json.dumps(persona_payload),
            "--elements-json",
            json.dumps(_REVISION_ELEMENTS),
        ]
    )
    arguments = agentic_campaign._build_plan_propose_arguments(args)
    assert arguments == {
        "plan_id": "33333333-3333-4333-8333-333333333333",
        "proposal_id": "77777777-7777-4777-8777-777777777777",
        "elements": _REVISION_ELEMENTS,
        "persona_payload": persona_payload,
        "dry_run": False,
    }


def test_plan_propose_revision_builds_arguments_without_persona() -> None:
    args = parse(
        [
            "agentic-campaign",
            "+plan-propose",
            "--plan-id",
            "33333333-3333-4333-8333-333333333333",
            "--proposal-id",
            "77777777-7777-4777-8777-777777777777",
            "--elements-json",
            json.dumps(_REVISION_ELEMENTS),
        ]
    )
    arguments = agentic_campaign._build_plan_propose_arguments(args)
    assert "persona_id" not in arguments
    assert "persona_payload" not in arguments


def test_plan_propose_revision_rejects_persona_payload_and_persona_id_together() -> None:
    args = parse(
        [
            "agentic-campaign",
            "+plan-propose",
            "--plan-id",
            "33333333-3333-4333-8333-333333333333",
            "--proposal-id",
            "77777777-7777-4777-8777-777777777777",
            "--persona-id",
            "99999999-9999-4999-8999-999999999999",
            "--persona-json",
            json.dumps({"name": "Mia", "description": "d", "visual_prompt": "v"}),
            "--elements-json",
            json.dumps(_REVISION_ELEMENTS),
        ]
    )
    with pytest.raises(ValueError, match="mutually exclusive"):
        agentic_campaign._build_plan_propose_arguments(args)


def test_plan_propose_revision_rejects_patch_persona_payload() -> None:
    args = parse(
        [
            "agentic-campaign",
            "+plan-propose",
            "--plan-id",
            "33333333-3333-4333-8333-333333333333",
            "--proposal-id",
            "77777777-7777-4777-8777-777777777777",
            "--patch-persona-payload",
            json.dumps({"name": "New name"}),
            "--elements-json",
            json.dumps(_REVISION_ELEMENTS),
        ]
    )
    with pytest.raises(ValueError, match="--patch-persona-payload is not valid"):
        agentic_campaign._build_plan_propose_arguments(args)


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
            "title": None,
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


def test_plan_propose_dispatches_persona_and_retirement_in_one_adjustment() -> None:
    plan_id = "33333333-3333-4333-8333-333333333333"
    persona_id = "99999999-9999-4999-8999-999999999999"
    retired_id = "88888888-8888-4888-8888-888888888888"
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
            "--persona-id",
            persona_id,
            "--retire-element-ids",
            retired_id,
            "--title",
            "Persona and retirement update",
        ]
    )
    arguments = agentic_campaign._build_plan_propose_arguments(args)
    assert arguments["changes"] == {
        "add_elements": [],
        "retire_element_ids": [retired_id],
        "boost_elements": [],
        "persona": {"persona_id": persona_id},
    }
    result = asyncio.run(
        agentic_campaign._execute_plan_propose(
            context("agentic-campaign.plan-propose", arguments, capture)
        )
    )
    assert capture.calls[-1]["json_body"]["changes"] == arguments["changes"]
    assert result["change_summary"] == {
        "new_directions": 0,
        "directions_to_stop": 1,
        "winner_boosts": 0,
        "persona_change": True,
    }


def test_plan_propose_dispatches_patch_persona_payload() -> None:
    plan_id = "33333333-3333-4333-8333-333333333333"
    patch_payload = {"description": "New description", "reference_media_ids": None}
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
            "--patch-persona-payload",
            json.dumps(patch_payload),
        ]
    )
    arguments = agentic_campaign._build_plan_propose_arguments(args)
    assert arguments["changes"]["patch_persona_payload"] == patch_payload
    asyncio.run(
        agentic_campaign._execute_plan_propose(
            context("agentic-campaign.plan-propose", arguments, capture)
        )
    )
    assert capture.calls[-1]["json_body"]["changes"]["patch_persona_payload"] == patch_payload


def test_plan_propose_active_adjustment_threads_title() -> None:
    plan_id = "33333333-3333-4333-8333-333333333333"
    add_elements = [
        {
            "format_id": "44444444-4444-4444-8444-444444444444",
            "topic_id": "55555555-5555-4555-8555-555555555555",
        }
    ]
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
            "--title",
            "暗黑向第二批开测",
        ]
    )
    arguments = agentic_campaign._build_plan_propose_arguments(args)

    asyncio.run(
        agentic_campaign._execute_plan_propose(
            context("agentic-campaign.plan-propose", arguments, capture)
        )
    )

    assert capture.calls[-1]["json_body"]["title"] == "暗黑向第二批开测"


def test_plan_propose_rejects_title_when_revising_proposal() -> None:
    args = parse(
        [
            "agentic-campaign",
            "+plan-propose",
            "--plan-id",
            "33333333-3333-4333-8333-333333333333",
            "--proposal-id",
            "77777777-7777-4777-8777-777777777777",
            "--title",
            "not allowed here",
            "--elements-json",
            json.dumps(
                [
                    {
                        "format_id": "44444444-4444-4444-8444-444444444444",
                        "topic_id": "55555555-5555-4555-8555-555555555555",
                    }
                ]
            ),
        ]
    )
    with pytest.raises(ValueError, match="--title is not valid when revising"):
        agentic_campaign._build_plan_propose_arguments(args)


def test_plan_propose_rejects_title_for_draft_plan() -> None:
    args = parse(
        [
            "agentic-campaign",
            "+plan-propose",
            "--plan-id",
            "33333333-3333-4333-8333-333333333333",
            "--title",
            "not allowed here",
            *_complete_plan_cli_args(),
        ]
    )
    with pytest.raises(ValueError, match="--title is only valid for an active-plan adjustment"):
        agentic_campaign._build_plan_propose_arguments(args)


def test_proposal_get_returns_operator_revision_context() -> None:
    plan_id = "33333333-3333-4333-8333-333333333333"
    proposal_id = "77777777-7777-4777-8777-777777777777"
    feedback_summary = (
        "提案修订意见（坐标以预览左上角为原点）：\n\n"
        "整体意见：\n让视觉更明亮\n\n逐项标注：\n- 保留完整意见"
    )
    capture = Capture(
        campaign_list(plan_id),
        campaign_detail(plan_id, status="active"),
        {
            "id": proposal_id,
            "status": "awaiting_review",
            "revision_round": 2,
            "changes": {
                "add_elements": [{"format_id": "format-1"}],
                "retire_element_ids": ["element-old"],
                "boost_elements": [{"element_id": "element-winner"}],
            },
            "elements": [
                {
                    "id": "internal-element-id",
                    "format_id": "44444444-4444-4444-8444-444444444444",
                    "topic_id": "55555555-5555-4555-8555-555555555555",
                    "cta_target_id": "66666666-6666-4666-8666-666666666666",
                }
            ],
            "feedback_summary": feedback_summary,
        },
        {
            "items": [
                {
                    "id": "feedback-1",
                    "round": 1,
                    "compiled_summary": "方向A · 帖子1 · 第1页",
                    "resolved_at": "2026-07-20T00:00:00Z",
                },
                {
                    "id": "feedback-2",
                    "round": 2,
                    "compiled_summary": None,
                    "resolved_at": None,
                },
            ]
        },
    )
    result = asyncio.run(
        agentic_campaign._execute_proposal_get(
            context(
                "agentic-campaign.proposal-get",
                {"plan_id": plan_id, "proposal_id": proposal_id},
                capture,
            )
        )
    )

    assert capture.calls[-2] == {
        "method": "GET",
        "path": (
            "/agentic-creative-campaigns/22222222-2222-4222-8222-222222222222/"
            f"persona-plans/{plan_id}/revision-proposals/{proposal_id}"
        ),
        "json_body": None,
        "params": {"workspace_id": "11111111-1111-4111-8111-111111111111"},
    }
    assert capture.calls[-1] == {
        "method": "GET",
        "path": (
            "/agentic-creative-campaigns/22222222-2222-4222-8222-222222222222/"
            f"persona-plans/{plan_id}/revision-proposals/{proposal_id}/feedback"
        ),
        "json_body": None,
        "params": {"workspace_id": "11111111-1111-4111-8111-111111111111"},
    }
    assert result == {
        "status": "awaiting_review",
        "revision_round": 2,
        "change_summary": {
            "new_directions": 1,
            "directions_to_stop": 1,
            "winner_boosts": 1,
        },
        "elements": [
            {
                "format_id": "44444444-4444-4444-8444-444444444444",
                "topic_id": "55555555-5555-4555-8555-555555555555",
                "cta_target_id": "66666666-6666-4666-8666-666666666666",
            }
        ],
        "feedback_summary": feedback_summary,
        "annotations": [
            {"round": 2, "resolved": False, "compiled_summary": "该轮无可渲染文本"},
            {"round": 1, "resolved": True, "compiled_summary": "方向A · 帖子1 · 第1页"},
        ],
        "next_step": "请在 Museon 审阅台查看这一稿；运营可继续标注意见或确认。",
    }
    assert "internal-element-id" not in repr(result)
    assert "feedback-1" not in repr(result)


def test_proposal_get_annotations_placeholder_when_no_feedback() -> None:
    plan_id = "33333333-3333-4333-8333-333333333333"
    proposal_id = "77777777-7777-4777-8777-777777777777"
    capture = Capture(
        campaign_list(plan_id),
        campaign_detail(plan_id, status="active"),
        {
            "id": proposal_id,
            "status": "awaiting_review",
            "revision_round": 1,
            "changes": {},
            "elements": [],
        },
        {"items": []},
    )
    result = asyncio.run(
        agentic_campaign._execute_proposal_get(
            context(
                "agentic-campaign.proposal-get",
                {"plan_id": plan_id, "proposal_id": proposal_id},
                capture,
            )
        )
    )
    assert result["annotations"] == "暂无标注意见"


def test_plan_propose_submits_active_proposal_revision() -> None:
    plan_id = "33333333-3333-4333-8333-333333333333"
    proposal_id = "77777777-7777-4777-8777-777777777777"
    elements = [
        {
            "format_id": "44444444-4444-4444-8444-444444444444",
            "topic_id": "55555555-5555-4555-8555-555555555555",
            "cta_target_id": "66666666-6666-4666-8666-666666666666",
        }
    ]
    capture = Capture(
        campaign_list(plan_id),
        campaign_detail(plan_id, status="active"),
        {"elements": [{"id": "new-element"}], "round": 3, "dispatched_task_count": 1},
    )
    args = parse(
        [
            "agentic-campaign",
            "+plan-propose",
            "--plan-id",
            plan_id,
            "--proposal-id",
            proposal_id,
            "--elements-json",
            json.dumps(elements),
            "--note",
            "Apply the compiled feedback",
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
            f"persona-plans/{plan_id}/revision-proposals/{proposal_id}:submit-revision"
        ),
        "json_body": {
            "workspace_id": "11111111-1111-4111-8111-111111111111",
            "elements": elements,
            "note": "Apply the compiled feedback",
        },
        "params": None,
    }
    assert result == {
        "revision_round": 3,
        "new_element_count": 1,
        "preview_task_count": 1,
        "next_step": "第 3 稿已提交；运营将在审阅台看到新一稿。",
    }


def test_plan_propose_submits_draft_stage_proposal_revision_with_persona_payload() -> None:
    """Restores what --candidate-id used to do (deleted in error by museoncli v0.3.96,
    then renamed by mistake in the same release): revise a proposal on a still-draft
    plan with a full persona replacement inline. The backend's persona field on
    :submit-revision is the same nested shape plan-propose already uses elsewhere --
    exactly one of persona_id or persona_payload."""
    plan_id = "33333333-3333-4333-8333-333333333333"
    proposal_id = "77777777-7777-4777-8777-777777777777"
    persona_payload = {
        "name": "Mia",
        "description": "Practical maker",
        "visual_prompt": "Warm workshop portrait",
    }
    capture = Capture(
        campaign_list(plan_id),
        campaign_detail(plan_id, status="draft"),
        {"elements": [{"id": "new-element"}], "round": 2, "dispatched_task_count": 1},
    )
    args = parse(
        [
            "agentic-campaign",
            "+plan-propose",
            "--plan-id",
            plan_id,
            "--proposal-id",
            proposal_id,
            "--persona-json",
            json.dumps(persona_payload),
            "--elements-json",
            json.dumps(_REVISION_ELEMENTS),
            "--note",
            "Brighter visual direction",
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
            f"persona-plans/{plan_id}/revision-proposals/{proposal_id}:submit-revision"
        ),
        "json_body": {
            "workspace_id": "11111111-1111-4111-8111-111111111111",
            "elements": _REVISION_ELEMENTS,
            "note": "Brighter visual direction",
            "persona": {"persona_payload": persona_payload},
        },
        "params": None,
    }
    assert result["revision_round"] == 2


def test_plan_propose_submits_draft_stage_proposal_revision_with_persona_id() -> None:
    plan_id = "33333333-3333-4333-8333-333333333333"
    proposal_id = "77777777-7777-4777-8777-777777777777"
    persona_id = "99999999-9999-4999-8999-999999999999"
    capture = Capture(
        campaign_list(plan_id),
        campaign_detail(plan_id, status="draft"),
        {"elements": [{"id": "new-element"}], "round": 2, "dispatched_task_count": 1},
    )
    args = parse(
        [
            "agentic-campaign",
            "+plan-propose",
            "--plan-id",
            plan_id,
            "--proposal-id",
            proposal_id,
            "--persona-id",
            persona_id,
            "--elements-json",
            json.dumps(_REVISION_ELEMENTS),
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
            f"persona-plans/{plan_id}/revision-proposals/{proposal_id}:submit-revision"
        ),
        "json_body": {
            "workspace_id": "11111111-1111-4111-8111-111111111111",
            "elements": _REVISION_ELEMENTS,
            "note": None,
            "persona": {"persona_id": persona_id},
        },
        "params": None,
    }
    assert result["revision_round"] == 2


def test_plan_propose_submits_draft_stage_proposal_revision_without_persona() -> None:
    """A revision with no persona flag at all must produce a body with no persona
    field -- the omission means "keep the persona the proposal already carries", and
    existing elements-only callers (draft or active) must be unchanged by this fix."""
    plan_id = "33333333-3333-4333-8333-333333333333"
    proposal_id = "77777777-7777-4777-8777-777777777777"
    capture = Capture(
        campaign_list(plan_id),
        campaign_detail(plan_id, status="draft"),
        {"elements": [{"id": "new-element"}], "round": 2, "dispatched_task_count": 1},
    )
    args = parse(
        [
            "agentic-campaign",
            "+plan-propose",
            "--plan-id",
            plan_id,
            "--proposal-id",
            proposal_id,
            "--elements-json",
            json.dumps(_REVISION_ELEMENTS),
        ]
    )
    arguments = agentic_campaign._build_plan_propose_arguments(args)
    asyncio.run(
        agentic_campaign._execute_plan_propose(
            context("agentic-campaign.plan-propose", arguments, capture)
        )
    )
    body = capture.calls[-1]["json_body"]
    assert "persona" not in body
    assert body["elements"] == _REVISION_ELEMENTS


def test_execute_plan_propose_rejects_patch_persona_payload_defensively() -> None:
    """The executor re-checks patch_persona_payload independently of the argument
    builder, matching this codebase's existing dual-validation convention (see the
    same pattern for name/changes above it in _execute_plan_propose): a caller that
    builds ctx.arguments directly, bypassing the CLI's own flag parsing, must not be
    able to sneak a patch payload past the builder's rejection and have it silently
    sent as a full persona replacement."""
    plan_id = "33333333-3333-4333-8333-333333333333"
    proposal_id = "77777777-7777-4777-8777-777777777777"
    capture = Capture(campaign_list(plan_id), campaign_detail(plan_id, status="draft"))
    arguments = {
        "plan_id": plan_id,
        "proposal_id": proposal_id,
        "elements": _REVISION_ELEMENTS,
        "patch_persona_payload": {"name": "New name"},
    }
    with pytest.raises(ValueError, match="patch_persona_payload is not valid"):
        asyncio.run(
            agentic_campaign._execute_plan_propose(
                context("agentic-campaign.plan-propose", arguments, capture)
            )
        )


def test_plan_propose_revision_rejects_name() -> None:
    """--name still names a *new* proposal, so it stays rejected on a revision -- unlike
    --persona-json/--persona-id, which the backend's persona field on :submit-revision now
    accepts (see test_plan_propose_revision_builds_arguments_with_persona_*)."""
    args = parse(
        [
            "agentic-campaign",
            "+plan-propose",
            "--plan-id",
            "33333333-3333-4333-8333-333333333333",
            "--proposal-id",
            "77777777-7777-4777-8777-777777777777",
            "--elements-json",
            json.dumps(
                [
                    {
                        "format_id": "44444444-4444-4444-8444-444444444444",
                        "topic_id": "55555555-5555-4555-8555-555555555555",
                    }
                ]
            ),
            "--name",
            "not applicable",
        ]
    )
    with pytest.raises(ValueError, match="--name is not valid"):
        agentic_campaign._build_plan_propose_arguments(args)


def _branch_requirement_satisfied(rule: dict[str, Any], payload: dict[str, Any]) -> bool:
    """Minimal evaluator for the required/oneOf/anyOf/not combinators plan-propose's
    oneOf branches are built from. Enough to check which branch(es) a call shape
    satisfies without pulling in a jsonschema dependency for this one narrow check --
    the branches never nest anything richer than these four keywords."""
    if "required" in rule and not all(key in payload for key in rule["required"]):
        return False
    if "oneOf" in rule:
        matches = sum(1 for sub in rule["oneOf"] if _branch_requirement_satisfied(sub, payload))
        if matches != 1:
            return False
    if "anyOf" in rule:
        if not any(_branch_requirement_satisfied(sub, payload) for sub in rule["anyOf"]):
            return False
    if "not" in rule:
        if _branch_requirement_satisfied(rule["not"], payload):
            return False
    return True


@pytest.mark.parametrize(
    "shape",
    [
        pytest.param(
            {"name": "n", "elements": [1], "persona_payload": {}}, id="new-persona-payload"
        ),
        pytest.param({"name": "n", "elements": [1], "persona_id": "p"}, id="new-persona-id"),
        pytest.param(
            {"proposal_id": "p", "elements": [1], "persona_payload": {}},
            id="revise-with-persona-payload",
        ),
        pytest.param(
            {"proposal_id": "p", "elements": [1], "persona_id": "p"},
            id="revise-with-persona-id",
        ),
        pytest.param({"changes": {}}, id="active-plan-adjustment"),
        pytest.param(
            {"proposal_id": "p", "elements": [1]}, id="proposal-revision-elements-only"
        ),
    ],
)
def test_plan_propose_oneof_call_shapes_match_exactly_one_branch(shape: dict[str, Any]) -> None:
    """Each legal plan-propose call shape must satisfy exactly one oneOf branch.

    Regression coverage for the fold that renamed candidate_id to proposal_id: the
    revise-with-persona shapes are reachable only through branch 0's `anyOf`
    (name or proposal_id), and without excluding persona_id from branch 2's `not`,
    the revise-with-persona-id shape quietly satisfied both branch 0 and branch 2,
    which `oneOf` rejects. A test asserting only "this shape validates" would not
    have caught that -- it has to count matching branches.
    """
    spec = get_command_spec("agentic-campaign.plan-propose")
    branches = spec.input_schema["oneOf"]
    matches = [
        branch["title"] for branch in branches if _branch_requirement_satisfied(branch, shape)
    ]
    assert len(matches) == 1, f"{shape} matched {matches}, want exactly one branch"


def test_plan_propose_schema_has_three_content_shapes_and_dry_run() -> None:
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
    assert len(spec.input_schema["oneOf"]) == 3
    assert spec.supports_dry_run is True
    changes_schema = spec.input_schema["properties"]["changes"]
    assert "patch_persona_payload" in changes_schema["properties"]
    assert args.dry_run is True

    proposal_get = get_command_spec("agentic-campaign.proposal-get")
    assert proposal_get.risk_level == "read"
    assert proposal_get.input_schema["required"] == ["plan_id", "proposal_id"]


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
