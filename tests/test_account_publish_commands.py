"""Focused coverage for canonical account-publish batch schedule commands."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from museoncli import main as main_module
from museoncli.config import Config, WorkspaceState
from museoncli.domains import get_command_spec
from museoncli.main import build_parser


ACCOUNT_1 = "10000000-0000-4000-8000-000000000001"
ACCOUNT_2 = "10000000-0000-4000-8000-000000000002"
JOB_ID = "20000000-0000-4000-8000-000000000001"
PRODUCT_ID = "40000000-0000-4000-8000-000000000001"
FORMAT_ID = "50000000-0000-4000-8000-000000000001"
TOPIC_ID = "60000000-0000-4000-8000-000000000001"
PERSONA_ID = "70000000-0000-4000-8000-000000000001"
BGM_ID = "80000000-0000-4000-8000-000000000001"
WORKSPACE_1 = "30000000-0000-4000-8000-000000000001"
WORKSPACE_2 = "30000000-0000-4000-8000-000000000002"


class _Capture:
    def __init__(self, result: dict[str, Any] | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self.result = result or {"status": "previewed"}

    async def __call__(
        self,
        cfg: Config,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        del cfg
        self.calls.append(
            {"method": method, "path": path, "json_body": json_body, "params": params}
        )
        return self.result


def _parse(argv: list[str]) -> Any:
    return build_parser().parse_args(argv)


def _config_with_workspace() -> Config:
    cfg = Config()
    cfg.workspace = WorkspaceState(id=WORKSPACE_1, name="Workspace", organization_id="org-1")
    return cfg


def _plan_args(shortcut: str, *, execute: bool = False) -> list[str]:
    argv = [
        "account-publish",
        shortcut,
        "--account-id",
        ACCOUNT_1,
        "--account-id",
        ACCOUNT_2,
        "--start-date",
        "2026-07-17",
        "--days",
        "5",
        "--daily-slot",
        "17:00",
        "--daily-slot",
        "22:00",
        "--timezone",
        "Asia/Shanghai",
        "--format-strategy",
        "random",
        "--topic-strategy",
        "rotate",
        "--product-policy",
        "required",
        "--bgm-policy",
        "required",
        "--bgm-strategy",
        "random",
        "--bgm-platform",
        "TikTok",
        "--conflict-policy",
        "replace-non-published",
    ]
    if shortcut == "+schedule-plan-batch":
        argv.extend(
            [
                "--preview-token",
                "preview-token-1",
                "--idempotency-key",
                "schedule-plan-2026-07-17-v1",
            ]
        )
    if execute:
        argv.append("--yes")
    return argv


def _cancel_only_args(shortcut: str, *, execute: bool = False) -> list[str]:
    argv = [
        "account-publish",
        shortcut,
        "--operation",
        "cancel-only",
        "--account-id",
        ACCOUNT_1,
        "--account-id",
        ACCOUNT_2,
        "--cancel-reason",
        "operator requested schedule removal",
    ]
    if shortcut == "+schedule-plan-batch":
        argv.extend(
            [
                "--preview-token",
                "cancel-preview-token-1",
                "--idempotency-key",
                "cancel-only-2026-07-17-v1",
            ]
        )
    if execute:
        argv.append("--yes")
    return argv


def _asset_pool_args(shortcut: str, *, execute: bool = False) -> list[str]:
    argv = [
        "account-publish",
        shortcut,
        "--account-id",
        ACCOUNT_1,
        "--account-id",
        ACCOUNT_2,
        "--product-operation",
        "set",
        "--product-id",
        PRODUCT_ID,
        "--formats-operation",
        "add",
        "--format-id",
        FORMAT_ID,
    ]
    if shortcut == "+asset-pools-batch-set":
        argv.extend(
            [
                "--preview-token",
                "asset-preview-token-1",
                "--idempotency-key",
                "asset-pools-2026-07-17-v1",
            ]
        )
    if execute:
        argv.append("--yes")
    return argv


def test_asset_pool_uniform_patch_parser_and_builder() -> None:
    args = _parse(_asset_pool_args("+asset-pools-batch-preview"))
    spec = get_command_spec("account-publish.asset-pools-batch-preview")

    assert args.domain_command == "account-publish.asset-pools-batch-preview"
    assert spec.build_arguments(args) == {
        "account_ids": [ACCOUNT_1, ACCOUNT_2],
        "uniform_patch": {
            "product": {"operation": "set", "value_id": PRODUCT_ID},
            "formats": {"operation": "add", "ids": [FORMAT_ID]},
        },
    }


def test_one_account_parser_builds_complete_five_pool_patch() -> None:
    argv = [
        "account-publish",
        "+asset-pools-batch-preview",
        "--account-id",
        ACCOUNT_1,
        "--persona-operation",
        "set",
        "--persona-id",
        PERSONA_ID,
        "--product-operation",
        "set",
        "--product-id",
        PRODUCT_ID,
        "--formats-operation",
        "replace",
        "--format-id",
        FORMAT_ID,
        "--topics-operation",
        "replace",
        "--topic-id",
        TOPIC_ID,
        "--bgm-operation",
        "replace",
        "--bgm-asset-id",
        BGM_ID,
    ]

    payload = get_command_spec("account-publish.asset-pools-batch-preview").build_arguments(
        _parse(argv)
    )

    assert payload == {
        "account_ids": [ACCOUNT_1],
        "uniform_patch": {
            "persona": {"operation": "set", "value_id": PERSONA_ID},
            "product": {"operation": "set", "value_id": PRODUCT_ID},
            "formats": {"operation": "replace", "ids": [FORMAT_ID]},
            "topics": {"operation": "replace", "ids": [TOPIC_ID]},
            "bgm": {"operation": "replace", "ids": [BGM_ID]},
        },
    }


def test_asset_pool_per_account_patch_overrides_and_explicit_unchanged() -> None:
    patches = (
        '[{"account_id":"'
        + ACCOUNT_2
        + '","patch":{"product":{"operation":"unchanged"},'
        + '"topics":{"operation":"replace","ids":["'
        + TOPIC_ID
        + '"]}}}]'
    )
    argv = _asset_pool_args("+asset-pools-batch-preview") + [
        "--account-patches-json",
        patches,
    ]

    payload = get_command_spec("account-publish.asset-pools-batch-preview").build_arguments(
        _parse(argv)
    )

    assert payload["account_patches"] == [
        {
            "account_id": ACCOUNT_2,
            "patch": {
                "product": {"operation": "unchanged"},
                "topics": {"operation": "replace", "ids": [TOPIC_ID]},
            },
        }
    ]


def test_asset_pool_schema_exposes_batch_and_patch_contract() -> None:
    get = get_command_spec("account-publish.asset-pools-batch-get")
    preview = get_command_spec("account-publish.asset-pools-batch-preview")
    batch = get_command_spec("account-publish.asset-pools-batch-set")

    assert get.input_schema["properties"]["account_ids"]["maxItems"] == 200
    assert get.input_schema["properties"]["include_resource_details"]["default"] is True
    patch_schema = preview.input_schema["properties"]["uniform_patch"]
    assert patch_schema["properties"]["product"]["properties"]["operation"]["enum"] == [
        "set",
        "clear",
        "unchanged",
    ]
    assert "unchanged" in patch_schema["properties"]["formats"]["properties"]["operation"]["enum"]
    assert batch.input_schema["properties"]["preview_token"]["maxLength"] == 200
    assert batch.input_schema["properties"]["idempotency_key"]["maxLength"] == 240
    assert "managed_operation_approved" not in batch.input_schema["properties"]
    assert batch.risk_level == "destructive"
    assert batch.execution == "async_run"
    assert batch.requires_confirmation is True
    assert batch.supports_dry_run is True


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        (["--formats-operation", "clear", "--format-id", FORMAT_ID], "not allowed"),
        (["--formats-operation", "add"], "ids is required"),
        (["--product-operation", "set"], "value_id is required"),
        (["--product-operation", "clear", "--product-id", PRODUCT_ID], "only allowed"),
    ],
)
def test_asset_pool_builder_rejects_invalid_operations(extra: list[str], message: str) -> None:
    argv = [
        "account-publish",
        "+asset-pools-batch-preview",
        "--account-id",
        ACCOUNT_1,
        *extra,
    ]

    with pytest.raises(ValueError, match=message):
        get_command_spec("account-publish.asset-pools-batch-preview").build_arguments(_parse(argv))


def test_asset_pool_account_override_must_target_selected_account() -> None:
    patches = '[{"account_id":"' + ACCOUNT_2 + '","patch":{"product":{"operation":"clear"}}}]'
    argv = [
        "account-publish",
        "+asset-pools-batch-preview",
        "--account-id",
        ACCOUNT_1,
        "--account-patches-json",
        patches,
    ]

    with pytest.raises(ValueError, match="must also be supplied"):
        get_command_spec("account-publish.asset-pools-batch-preview").build_arguments(_parse(argv))


def test_parser_and_builder_normalize_schedule_plan() -> None:
    args = _parse(_plan_args("+schedule-plan-preview"))
    spec = get_command_spec("account-publish.schedule-plan-preview")

    assert args.domain_command == "account-publish.schedule-plan-preview"
    assert spec.build_arguments(args) == {
        "operation": "plan",
        "account_ids": [ACCOUNT_1, ACCOUNT_2],
        "start_date": "2026-07-17",
        "days": 5,
        "daily_slots": ["17:00", "22:00"],
        "timezone": "Asia/Shanghai",
        "format_strategy": "random",
        "topic_strategy": "rotate",
        "product_policy": "required",
        "bgm_policy": {"mode": "required", "strategy": "random", "platform": "tiktok"},
        "conflict_policy": "replace_non_published",
    }


def test_cancel_only_parser_and_builder_map_to_api_operation() -> None:
    args = _parse(_cancel_only_args("+schedule-plan-preview"))
    spec = get_command_spec("account-publish.schedule-plan-preview")

    assert args.operation == "cancel-only"
    assert spec.build_arguments(args) == {
        "operation": "cancel_only",
        "account_ids": [ACCOUNT_1, ACCOUNT_2],
        "cancel_reason": "operator requested schedule removal",
    }


def test_plan_defaults_are_preserved_after_conditional_argument_parsing() -> None:
    argv = [
        "account-publish",
        "+schedule-plan-preview",
        "--account-id",
        ACCOUNT_1,
        "--start-date",
        "2026-07-17",
        "--days",
        "1",
        "--daily-slot",
        "17:00",
        "--timezone",
        "UTC",
    ]

    payload = get_command_spec("account-publish.schedule-plan-preview").build_arguments(
        _parse(argv)
    )

    assert payload == {
        "operation": "plan",
        "account_ids": [ACCOUNT_1],
        "start_date": "2026-07-17",
        "days": 1,
        "daily_slots": ["17:00"],
        "timezone": "UTC",
        "format_strategy": "rotate",
        "topic_strategy": "rotate",
        "product_policy": "required",
        "bgm_policy": {
            "mode": "required",
            "strategy": "rotate",
            "platform": "tiktok",
        },
        "conflict_policy": "upsert_occurrences",
    }


def test_cancel_only_reason_is_optional_but_explicit_blank_is_rejected() -> None:
    argv = _cancel_only_args("+schedule-plan-preview")
    reason_index = argv.index("--cancel-reason")
    del argv[reason_index : reason_index + 2]
    spec = get_command_spec("account-publish.schedule-plan-preview")

    assert spec.build_arguments(_parse(argv)) == {
        "operation": "cancel_only",
        "account_ids": [ACCOUNT_1, ACCOUNT_2],
    }

    with pytest.raises(ValueError, match="must not be blank"):
        spec.build_arguments(_parse([*argv, "--cancel-reason", ""]))


def test_schema_advertises_cli_kebab_choices_and_batch_contract() -> None:
    preview = get_command_spec("account-publish.schedule-plan-preview")
    batch = get_command_spec("account-publish.schedule-plan-batch")

    assert preview.input_schema["properties"]["conflict_policy"]["enum"] == [
        "create-only",
        "replace-non-published",
        "upsert-occurrences",
    ]
    assert preview.input_schema["properties"]["days"]["maximum"] == 180
    assert preview.input_schema["properties"]["daily_slots"]["maxItems"] == 24
    assert preview.input_schema["properties"]["account_ids"]["maxItems"] == 200
    assert preview.input_schema["properties"]["operation"] == {
        "type": "string",
        "enum": ["plan", "cancel-only"],
        "default": "plan",
        "description": (
            "plan creates/rebuilds schedule items; cancel-only cancels the account's "
            "current eligible schedule items."
        ),
    }
    assert preview.input_schema["properties"]["cancel_reason"]["maxLength"] == 500
    for spec in (preview, batch):
        assert spec.input_schema["properties"]["bgm_policy"] == {
            "type": "string",
            "enum": ["required", "optional", "disabled"],
            "default": "required",
            "description": "CLI --bgm-policy mode.",
        }
        assert spec.input_schema["properties"]["bgm_strategy"]["enum"] == [
            "rotate",
            "random",
        ]
        assert spec.input_schema["properties"]["bgm_strategy"]["default"] == "rotate"
        assert spec.input_schema["properties"]["bgm_platform"]["type"] == "string"
        assert spec.input_schema["properties"]["bgm_platform"]["default"] == "tiktok"
    assert batch.input_schema["properties"]["preview_token"]["maxLength"] == 200
    assert batch.input_schema["properties"]["idempotency_key"]["maxLength"] == 240
    assert batch.input_schema["properties"]["idempotency_key"]["type"] == "string"
    assert "idempotency_key" in batch.input_schema["required"]
    replace_condition = batch.input_schema["allOf"][1]
    assert replace_condition["if"] == {
        "properties": {"conflict_policy": {"const": "replace-non-published"}},
        "required": ["conflict_policy"],
    }
    assert replace_condition["then"] == {"required": ["preview_token"]}
    assert "5000 total occurrences" in batch.input_schema["description"]
    assert batch.risk_level == "destructive"
    assert batch.execution == "async_run"
    assert batch.requires_confirmation is True
    assert batch.supports_dry_run is True
    assert "only state source is +schedule-plan-status" in batch.summary
    assert "bgm_bound_count/summary.bgm_bound" in batch.summary
    assert "never call schedule-list, bgm-asset-list, or routines" in batch.summary
    assert "--operation cancel-only is the primary batch deletion path" in batch.summary
    assert any("--operation cancel-only" in example for example in preview.examples)
    assert any("--operation cancel-only" in example for example in batch.examples)

    status = get_command_spec("account-publish.schedule-plan-status")
    assert "only state source after submission" in status.summary
    assert "bgm_bound_count/summary.bgm_bound" in status.summary
    assert "never call schedule-list, bgm-asset-list, or routines" in status.summary

    cancel = get_command_spec("account-publish.schedule-plan-cancel")
    assert "job control only" in cancel.summary
    assert "never deletes schedule items already created" in cancel.summary


@pytest.mark.parametrize(
    "plan_only_args",
    [
        ["--start-date", "2026-07-17"],
        ["--days", "5"],
        ["--daily-slot", "17:00"],
        ["--timezone", "Asia/Shanghai"],
        ["--bgm-policy", "required"],
        ["--conflict-policy", "upsert-occurrences"],
    ],
)
def test_cancel_only_rejects_plan_only_fields(plan_only_args: list[str]) -> None:
    argv = _cancel_only_args("+schedule-plan-preview") + plan_only_args

    with pytest.raises(ValueError, match="not allowed with --operation cancel-only"):
        get_command_spec("account-publish.schedule-plan-preview").build_arguments(_parse(argv))


def test_plan_rejects_cancel_reason() -> None:
    argv = _plan_args("+schedule-plan-preview") + [
        "--cancel-reason",
        "not a plan field",
    ]

    with pytest.raises(ValueError, match="only allowed with --operation cancel-only"):
        get_command_spec("account-publish.schedule-plan-preview").build_arguments(_parse(argv))


def test_cancel_only_batch_requires_preview_token() -> None:
    argv = _cancel_only_args("+schedule-plan-batch")
    token_index = argv.index("--preview-token")
    del argv[token_index : token_index + 2]

    with pytest.raises(ValueError, match="preview-token is required"):
        get_command_spec("account-publish.schedule-plan-batch").build_arguments(_parse(argv))


def test_replace_batch_requires_preview_token() -> None:
    argv = _plan_args("+schedule-plan-batch")
    token_index = argv.index("--preview-token")
    del argv[token_index : token_index + 2]
    args = _parse(argv)

    with pytest.raises(ValueError, match="preview-token is required"):
        get_command_spec("account-publish.schedule-plan-batch").build_arguments(args)


def test_batch_parser_requires_idempotency_key() -> None:
    argv = _plan_args("+schedule-plan-batch")
    key_index = argv.index("--idempotency-key")
    del argv[key_index : key_index + 2]

    with pytest.raises(SystemExit):
        _parse(argv)


def test_plan_builder_rejects_total_occurrence_budget() -> None:
    argv = _plan_args("+schedule-plan-preview")
    account_flag_index = argv.index("--account-id")
    del argv[account_flag_index : account_flag_index + 4]
    for number in range(29):
        argv[2:2] = ["--account-id", f"10000000-0000-4000-8000-{number:012d}"]
    days_index = argv.index("--days")
    argv[days_index + 1] = "180"

    with pytest.raises(ValueError, match="5000 total occurrences"):
        get_command_spec("account-publish.schedule-plan-preview").build_arguments(_parse(argv))


@pytest.mark.parametrize(
    ("replacement", "message"),
    [
        (["--start-date", "2026/07/17"], "YYYY-MM-DD"),
        (["--daily-slot", "7:00"], "HH:MM"),
        (["--timezone", "Mars/Olympus"], "IANA timezone"),
        (["--days", "0"], "between 1"),
    ],
)
def test_plan_builder_rejects_invalid_time_inputs(replacement: list[str], message: str) -> None:
    argv = _plan_args("+schedule-plan-preview")
    flag = replacement[0]
    first_index = argv.index(flag)
    argv[first_index : first_index + 2] = replacement
    if flag == "--daily-slot":
        second_index = argv.index(flag, first_index + 2)
        del argv[second_index : second_index + 2]
    args = _parse(argv)

    with pytest.raises(ValueError, match=message):
        get_command_spec("account-publish.schedule-plan-preview").build_arguments(args)


def test_preview_is_a_real_server_request_with_workspace_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture = _Capture({"would_create": 20, "would_cancel": 4})
    monkeypatch.setattr(main_module, "load_config", _config_with_workspace)
    monkeypatch.setattr(main_module, "api_data_v2", capture)
    argv = _plan_args("+schedule-plan-preview") + ["--workspace-id", WORKSPACE_2]

    result = asyncio.run(main_module.dispatch(_parse(argv)))

    assert result["data"] == {"would_create": 20, "would_cancel": 4}
    assert capture.calls[0]["method"] == "POST"
    assert capture.calls[0]["path"] == "/account-publish/schedule-plans:preview"
    assert capture.calls[0]["json_body"]["workspace_id"] == WORKSPACE_2
    assert capture.calls[0]["json_body"]["operation"] == "plan"
    assert capture.calls[0]["json_body"]["account_ids"] == [ACCOUNT_1, ACCOUNT_2]


def test_cancel_only_preview_and_batch_send_api_operation_and_workspace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture = _Capture(
        {
            "job": {
                "id": JOB_ID,
                "status": "queued",
                "recommended_wakeup_delay_seconds": 10,
            }
        }
    )
    monkeypatch.setattr(main_module, "load_config", _config_with_workspace)
    monkeypatch.setattr(main_module, "api_data_v2", capture)

    asyncio.run(
        main_module.dispatch(
            _parse(_cancel_only_args("+schedule-plan-preview") + ["--workspace-id", WORKSPACE_2])
        )
    )
    batch_result = asyncio.run(
        main_module.dispatch(_parse(_cancel_only_args("+schedule-plan-batch", execute=True)))
    )

    assert capture.calls[0] == {
        "method": "POST",
        "path": "/account-publish/schedule-plans:preview",
        "json_body": {
            "workspace_id": WORKSPACE_2,
            "operation": "cancel_only",
            "account_ids": [ACCOUNT_1, ACCOUNT_2],
            "cancel_reason": "operator requested schedule removal",
        },
        "params": None,
    }
    assert capture.calls[1]["path"] == "/account-publish/schedule-plans:batch"
    assert capture.calls[1]["json_body"] == {
        "workspace_id": WORKSPACE_1,
        "operation": "cancel_only",
        "account_ids": [ACCOUNT_1, ACCOUNT_2],
        "cancel_reason": "operator requested schedule removal",
        "preview_token": "cancel-preview-token-1",
        "idempotency_key": "cancel-only-2026-07-17-v1",
    }
    assert batch_result["run"]["id"] == JOB_ID


def test_batch_requires_yes_before_server_call(monkeypatch: pytest.MonkeyPatch) -> None:
    capture = _Capture()
    monkeypatch.setattr(main_module, "load_config", _config_with_workspace)
    monkeypatch.setattr(main_module, "api_data_v2", capture)

    with pytest.raises(RuntimeError, match="confirmation_required"):
        asyncio.run(main_module.dispatch(_parse(_plan_args("+schedule-plan-batch"))))

    assert capture.calls == []


def test_batch_dry_run_is_local_and_does_not_call_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture = _Capture()
    monkeypatch.setattr(main_module, "load_config", _config_with_workspace)
    monkeypatch.setattr(main_module, "api_data_v2", capture)
    argv = _plan_args("+schedule-plan-batch") + ["--dry-run"]

    result = asyncio.run(main_module.dispatch(_parse(argv)))

    assert result["data"]["dry_run"] is True
    assert capture.calls == []


def test_batch_returns_async_run_and_status_next_step(monkeypatch: pytest.MonkeyPatch) -> None:
    capture = _Capture(
        {
            "job": {
                "id": JOB_ID,
                "status": "queued",
                "recommended_wakeup_delay_seconds": 12,
            }
        }
    )
    monkeypatch.setattr(main_module, "load_config", _config_with_workspace)
    monkeypatch.setattr(main_module, "api_data_v2", capture)

    result = asyncio.run(
        main_module.dispatch(_parse(_plan_args("+schedule-plan-batch", execute=True)))
    )

    assert capture.calls[0]["path"] == "/account-publish/schedule-plans:batch"
    assert capture.calls[0]["json_body"]["operation"] == "plan"
    assert capture.calls[0]["json_body"]["preview_token"] == "preview-token-1"
    assert capture.calls[0]["json_body"]["idempotency_key"] == "schedule-plan-2026-07-17-v1"
    assert result["run"] == {
        "id": JOB_ID,
        "type": "account_publish_schedule_plan",
        "status": "queued",
        "watch_command": f"museoncli account-publish +schedule-plan-status --id {JOB_ID}",
        "recommended_wakeup_delay_seconds": 12,
    }
    assert "poll only with" in result["next_steps"][0].lower()


def test_status_and_cancel_use_job_resource_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    capture = _Capture({"id": JOB_ID, "status": "running"})
    monkeypatch.setattr(main_module, "load_config", _config_with_workspace)
    monkeypatch.setattr(main_module, "api_data_v2", capture)

    status = asyncio.run(
        main_module.dispatch(_parse(["account-publish", "+schedule-plan-status", "--id", JOB_ID]))
    )
    cancelled = asyncio.run(
        main_module.dispatch(
            _parse(
                [
                    "account-publish",
                    "+schedule-plan-cancel",
                    "--id",
                    JOB_ID,
                    "--reason",
                    "operator request",
                ]
            )
        )
    )

    assert status["data"]["status"] == "running"
    assert cancelled["data"]["id"] == JOB_ID
    assert capture.calls == [
        {
            "method": "GET",
            "path": f"/account-publish/schedule-plans/{JOB_ID}",
            "json_body": None,
            "params": {"workspace_id": WORKSPACE_1},
        },
        {
            "method": "POST",
            "path": f"/account-publish/schedule-plans/{JOB_ID}:cancel",
            "json_body": {"workspace_id": WORKSPACE_1, "reason": "operator request"},
            "params": None,
        },
    ]


def test_existing_social_account_single_schedule_commands_remain_registered() -> None:
    for name in (
        "social-account.schedule-list",
        "social-account.schedule-create",
        "social-account.schedule-delete",
    ):
        assert get_command_spec(name).schema_name == name


def test_asset_pool_batch_get_and_preview_use_workspace_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture = _Capture({"summary": {"requested": 2}})
    monkeypatch.setattr(main_module, "load_config", _config_with_workspace)
    monkeypatch.setattr(main_module, "api_data_v2", capture)

    get_result = asyncio.run(
        main_module.dispatch(
            _parse(
                [
                    "account-publish",
                    "+asset-pools-batch-get",
                    "--account-id",
                    ACCOUNT_1,
                    "--account-id",
                    ACCOUNT_2,
                    "--workspace-id",
                    WORKSPACE_2,
                ]
            )
        )
    )
    preview_result = asyncio.run(
        main_module.dispatch(
            _parse(_asset_pool_args("+asset-pools-batch-preview") + ["--workspace-id", WORKSPACE_2])
        )
    )

    assert get_result["data"]["summary"]["requested"] == 2
    assert preview_result["data"]["summary"]["requested"] == 2
    assert capture.calls[0] == {
        "method": "POST",
        "path": "/account-publish/asset-pools:batch-get",
        "json_body": {
            "workspace_id": WORKSPACE_2,
            "account_ids": [ACCOUNT_1, ACCOUNT_2],
            "include_resource_details": True,
        },
        "params": None,
    }
    assert capture.calls[1]["path"] == "/account-publish/asset-pools:batch-preview"
    assert capture.calls[1]["json_body"]["workspace_id"] == WORKSPACE_2


def test_asset_pool_batch_set_requires_confirmation_and_supports_local_dry_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture = _Capture()
    monkeypatch.setattr(main_module, "load_config", _config_with_workspace)
    monkeypatch.setattr(main_module, "api_data_v2", capture)

    with pytest.raises(RuntimeError, match="confirmation_required"):
        asyncio.run(main_module.dispatch(_parse(_asset_pool_args("+asset-pools-batch-set"))))
    dry_run = asyncio.run(
        main_module.dispatch(_parse(_asset_pool_args("+asset-pools-batch-set") + ["--dry-run"]))
    )

    assert capture.calls == []
    assert dry_run["data"]["dry_run"] is True


def test_asset_pool_batch_set_returns_async_run_and_status_next_step(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture = _Capture(
        {
            "job": {
                "id": JOB_ID,
                "status": "queued",
                "recommended_wakeup_delay_seconds": 9,
            }
        }
    )
    monkeypatch.setattr(main_module, "load_config", _config_with_workspace)
    monkeypatch.setattr(main_module, "api_data_v2", capture)

    result = asyncio.run(
        main_module.dispatch(_parse(_asset_pool_args("+asset-pools-batch-set", execute=True)))
    )

    assert capture.calls[0]["path"] == "/account-publish/asset-pools:batch-set"
    assert capture.calls[0]["json_body"]["preview_token"] == "asset-preview-token-1"
    assert capture.calls[0]["json_body"]["idempotency_key"] == "asset-pools-2026-07-17-v1"
    assert result["run"] == {
        "id": JOB_ID,
        "type": "account_publish_asset_pools_batch",
        "status": "queued",
        "watch_command": f"museoncli account-publish +asset-pools-batch-status --id {JOB_ID}",
        "recommended_wakeup_delay_seconds": 9,
    }
    assert "poll only with" in result["next_steps"][0].lower()


def test_asset_pool_status_and_cancel_use_job_resource_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture = _Capture({"id": JOB_ID, "status": "running"})
    monkeypatch.setattr(main_module, "load_config", _config_with_workspace)
    monkeypatch.setattr(main_module, "api_data_v2", capture)

    asyncio.run(
        main_module.dispatch(
            _parse(["account-publish", "+asset-pools-batch-status", "--id", JOB_ID])
        )
    )
    asyncio.run(
        main_module.dispatch(
            _parse(
                [
                    "account-publish",
                    "+asset-pools-batch-cancel",
                    "--id",
                    JOB_ID,
                    "--reason",
                    "operator request",
                ]
            )
        )
    )

    assert capture.calls == [
        {
            "method": "GET",
            "path": f"/account-publish/asset-pools/jobs/{JOB_ID}",
            "json_body": None,
            "params": {"workspace_id": WORKSPACE_1},
        },
        {
            "method": "POST",
            "path": f"/account-publish/asset-pools/jobs/{JOB_ID}:cancel",
            "json_body": {"workspace_id": WORKSPACE_1, "reason": "operator request"},
            "params": None,
        },
    ]


def test_single_account_asset_commands_remain_but_are_not_batch_fallbacks() -> None:
    get = get_command_spec("social-account.assets-get")
    set_assets = get_command_spec("social-account.assets-set")

    assert "exactly ONE" in get.summary
    assert "asset-pools-batch-get" in get.summary
    assert "exactly ONE" in set_assets.summary
    assert "asset-pools-batch-preview" in set_assets.summary


_BULK_REQ = "account-publish.schedule-requirements-bulk-update"


def _bulk_req_build(argv_tail: list[str]) -> dict[str, Any]:
    argv = ["account-publish", "+schedule-requirements-bulk-update", *argv_tail]
    return get_command_spec(_BULK_REQ).build_arguments(_parse(argv))


def test_bulk_requirements_account_selector_and_preview() -> None:
    payload = _bulk_req_build(
        [
            "--account-id",
            ACCOUNT_1,
            "--account-id",
            ACCOUNT_2,
            "--required-hashtag",
            "#PlantSenso",
            "--required-hashtag",
            "#planttips",
            "--preview",
        ]
    )
    assert payload == {
        "dry_run": True,
        "account_ids": [ACCOUNT_1, ACCOUNT_2],
        "required_hashtags": ["#PlantSenso", "#planttips"],
    }


def test_bulk_requirements_item_selector_json_and_clear_music() -> None:
    payload = _bulk_req_build(
        [
            "--item-id",
            ACCOUNT_1,
            "--required-hashtags-json",
            '["#a","#b"]',
            "--clear-music",
        ]
    )
    assert payload == {
        "dry_run": False,
        "item_ids": [ACCOUNT_1],
        "required_hashtags": ["#a", "#b"],
        "bgm_by_platform": {},
    }


def test_bulk_requirements_scheduled_after_dropped_for_item_selector() -> None:
    payload = _bulk_req_build(
        [
            "--item-id",
            ACCOUNT_1,
            "--scheduled-after",
            "2026-07-23T00:00:00Z",
            "--required-mention",
            "@brand",
        ]
    )
    assert "scheduled_after" not in payload
    assert payload["item_ids"] == [ACCOUNT_1]
    assert payload["required_mentions"] == ["@brand"]


def test_bulk_requirements_scheduled_after_kept_for_account_selector() -> None:
    payload = _bulk_req_build(
        [
            "--account-id",
            ACCOUNT_1,
            "--scheduled-after",
            "2026-07-23T00:00:00Z",
            "--required-hashtag",
            "#x",
        ]
    )
    assert payload["scheduled_after"] == "2026-07-23T00:00:00Z"


def test_bulk_requirements_requires_exactly_one_selector() -> None:
    with pytest.raises(ValueError, match="exactly one selector"):
        _bulk_req_build(["--required-hashtag", "#x"])
    with pytest.raises(ValueError, match="exactly one selector"):
        _bulk_req_build(
            ["--account-id", ACCOUNT_1, "--item-id", ACCOUNT_2, "--required-hashtag", "#x"]
        )


def test_bulk_requirements_requires_at_least_one_field() -> None:
    with pytest.raises(ValueError, match="at least one field"):
        _bulk_req_build(["--account-id", ACCOUNT_1])


def test_bulk_requirements_dispatches_to_v2_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    capture = _Capture({"matched": 2, "eligible": 2, "updated": 2})
    monkeypatch.setattr(main_module, "load_config", _config_with_workspace)
    monkeypatch.setattr(main_module, "api_data_v2", capture)

    argv = [
        "account-publish",
        "+schedule-requirements-bulk-update",
        "--account-id",
        ACCOUNT_1,
        "--required-hashtag",
        "#x",
        "--preview",
    ]
    asyncio.run(main_module.dispatch(_parse(argv)))

    assert capture.calls[0]["method"] == "POST"
    assert capture.calls[0]["path"] == "/account-publish/schedule-items:bulk-requirements"
    assert capture.calls[0]["json_body"] == {
        "workspace_id": WORKSPACE_1,
        "dry_run": True,
        "account_ids": [ACCOUNT_1],
        "required_hashtags": ["#x"],
    }
