from __future__ import annotations

import argparse

import pytest

from museoncli.domains import command_executors, command_payload, get_command_spec, schema_payload
from museoncli.main import build_parser


EXPECTED = {
    "asset-list",
    "asset-get",
    "asset-get-batch",
    "asset-options",
    "asset-create",
    "asset-update",
    "asset-delete",
    "generation-create",
    "generation-get",
    "generation-list",
    "publish-asset-pools-batch-get",
    "publish-asset-pools-batch-preview",
    "publish-asset-pools-batch-set",
    "publish-asset-pools-batch-status",
    "publish-asset-pools-batch-cancel",
    "publish-schedule-plan-preview",
    "publish-schedule-plan-batch",
    "publish-schedule-plan-status",
    "publish-schedule-plan-cancel",
    "publish-config-get",
    "publish-config-update",
    "publish-config-batch-update",
    "publish-version-list",
    "publish-version-get",
    "publish-version-create",
    "publish-version-activate",
    "publish-schedule-list",
    "publish-schedule-get",
    "publish-schedule-generate",
    "publish-schedule-create",
    "publish-schedule-update",
    "publish-schedule-delete",
}


def parse(argv: list[str]) -> argparse.Namespace:
    return build_parser().parse_args(argv)


def test_ai_slideshow_public_surface_is_exact() -> None:
    names = {
        item["name"].removeprefix("ai-slideshow.")
        for item in schema_payload("ai-slideshow")["commands"]
    }
    executors = {
        name.removeprefix("ai-slideshow.")
        for name in command_executors()
        if name.startswith("ai-slideshow.")
    }
    assert names == EXPECTED
    assert executors == EXPECTED


def test_generation_exposes_explicit_assets_without_account_or_schedule_flags() -> None:
    schema = get_command_spec("ai-slideshow.generation-create").input_schema
    forbidden = {"account_id", "pool_account_id", "schedule_item_id"}
    assert not forbidden.intersection(schema["properties"])
    args = parse(
        [
            "ai-slideshow",
            "generation",
            "+create",
            "--format-id",
            "f",
            "--topic-id",
            "t",
            "--persona-id",
            "p",
        ]
    )
    assert not forbidden.intersection(command_payload(args))
    with pytest.raises(SystemExit):
        parse(["ai-slideshow", "generation", "+create", "--account-id", "a"])


def test_publish_config_batch_preserves_bulk_and_json_inputs() -> None:
    ids = ",".join(f"10000000-0000-4000-8000-{n:012d}" for n in range(200))
    args = parse(
        [
            "ai-slideshow",
            "publish",
            "+config-batch-update",
            "--ids",
            ids,
            "--output-language",
            "zh-CN",
            "--required-hashtags",
            "#one,#two",
        ]
    )
    payload = command_payload(args)
    assert len(payload["account_updates"]) == 200
    assert payload["account_updates"][0]["output_language"] == "zh-CN"
    assert payload["account_updates"][-1]["required_hashtags"] == ["#one", "#two"]

    json_args = parse(
        [
            "ai-slideshow",
            "publish",
            "+config-batch-update",
            "--account-updates",
            '[{"account_id":"10000000-0000-4000-8000-000000000001","require_approval_before_publish":true}]',
        ]
    )
    assert (
        command_payload(json_args)["account_updates"][0]["require_approval_before_publish"] is True
    )


def test_publish_version_rules_and_activation_parameters_are_preserved() -> None:
    create = parse(
        [
            "ai-slideshow",
            "publish",
            "+version-create",
            "--id",
            "10000000-0000-4000-8000-000000000001",
            "--rules-json",
            '[{"weekday":1,"times":["09:00"]}]',
            "--change-note",
            "weekly",
        ]
    )
    assert command_payload(create)["schedule_rules"] == [{"weekday": 1, "times": ["09:00"]}]
    activate = parse(
        [
            "ai-slideshow",
            "publish",
            "+version-activate",
            "--id",
            "10000000-0000-4000-8000-000000000001",
            "--version-id",
            "20000000-0000-4000-8000-000000000001",
            "--days",
            "30",
            "--seed",
            "7",
            "--no-preserve-manual-overrides",
        ]
    )
    assert command_payload(activate) == {
        "account_id": "10000000-0000-4000-8000-000000000001",
        "version_id": "20000000-0000-4000-8000-000000000001",
        "seed": 7,
        "days": 30,
        "preserve_manual_overrides": False,
    }


def test_publish_schedule_create_update_generate_delete_parameters_are_preserved() -> None:
    account = "10000000-0000-4000-8000-000000000001"
    item = "20000000-0000-4000-8000-000000000001"
    create = command_payload(
        parse(
            [
                "ai-slideshow",
                "publish",
                "+schedule-create",
                "--id",
                account,
                "--scheduled-at",
                "2026-10-01T00:00:00Z",
                "--format-id",
                "30000000-0000-4000-8000-000000000001",
                "--content-topic-id",
                "40000000-0000-4000-8000-000000000001",
                "--generation-id",
                "50000000-0000-4000-8000-000000000001",
            ]
        )
    )
    assert create["schedule_item"]["generation_id"] == "50000000-0000-4000-8000-000000000001"
    update = command_payload(
        parse(
            [
                "ai-slideshow",
                "publish",
                "+schedule-update",
                "--id",
                account,
                "--schedule-item-id",
                item,
                "--status",
                "cancelled",
            ]
        )
    )
    assert update["schedule_item"] == {"status": "cancelled"}
    generate = command_payload(
        parse(
            [
                "ai-slideshow",
                "publish",
                "+schedule-generate",
                "--id",
                account,
                "--schedule-item-id",
                item,
                "--notes",
                "use approved assets",
                "--metadata-json",
                '{"source":"schedule"}',
            ]
        )
    )
    assert generate["generation"] == {
        "custom_prompt": "use approved assets",
        "metadata": {"source": "schedule"},
    }
    delete = command_payload(
        parse(
            [
                "ai-slideshow",
                "publish",
                "+schedule-delete",
                "--id",
                account,
                "--schedule-item-id",
                item,
                "--reason",
                "operator request",
            ]
        )
    )
    assert delete["schedule_item"] == {"status": "cancelled", "override_reason": "operator request"}
