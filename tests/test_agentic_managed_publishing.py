import asyncio
import json
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from museoncli.config import Config
from museoncli.domains import command_executor, command_payload, get_command_spec
from museoncli.execution import CommandContext
from museoncli.main import build_parser

CAMPAIGN = str(UUID(int=1))
PLAN = str(UUID(int=2))
PERSONA = str(UUID(int=3))


def supply_args(pairs):
    return build_parser().parse_args(
        [
            "agentic-campaign",
            "plan",
            "+supply-update",
            "--campaign-id",
            CAMPAIGN,
            "--plan-id",
            PLAN,
            "--persona-id",
            PERSONA,
            "--expected-version",
            "1",
            "--pairs-json",
            json.dumps(pairs),
            "--dry-run",
        ]
    )


def test_twenty_references_stay_twenty_pairs_and_duplicate_imports_do_not_expand():
    pairs = [
        {"format_id": str(UUID(int=100 + i)), "topic_id": str(UUID(int=200 + i))} for i in range(20)
    ]
    payload = command_payload(supply_args(pairs + pairs))
    assert payload["combinations"] == pairs
    assert "format_ids" not in payload and "topic_ids" not in payload


@pytest.mark.parametrize(
    "pairs", [[], [{"format_id": PLAN}], [{"format_id": PLAN, "topic_id": "unreadable"}]]
)
def test_incomplete_reference_cannot_enter_supply(pairs):
    with pytest.raises(ValueError):
        command_payload(supply_args(pairs))


def test_wrong_plan_membership_never_reaches_account_mutation():
    async def run():
        api = AsyncMock(
            return_value={
                "campaign": {"id": CAMPAIGN},
                "agentic_persona_plans": [{"id": PLAN}],
                "op_units": [],
            }
        )
        ctx = CommandContext(
            cfg=Config(),
            spec=get_command_spec("agentic-campaign.plan-account-control"),
            args=None,
            arguments={
                "campaign_id": CAMPAIGN,
                "plan_id": PLAN,
                "account_id": PERSONA,
                "action": "enable",
                "expected_version": 1,
            },
            workspace_id=str(UUID(int=4)),
            api_data=api,
            api_data_v2=api,
            upload_media_file=AsyncMock(),
            upload_artifact_file=AsyncMock(),
        )
        with pytest.raises(ValueError, match="not a member"):
            await command_executor(ctx.spec.schema_name)(ctx)
        assert all(call.args[1] == "GET" for call in api.await_args_list)
        assert api.await_count == 1

    asyncio.run(run())
