"""Red tests for the `account-operation` command group.

The agent-facing linkage to /api/v2/account-operations: submit / get / list /
plan-submit / strategy-decide / elements-replace, all via api_data_v2 with the
sandbox credential system. session_conversation_id defaults from the per-turn runtime_context (current topic/thread).
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from museoncli import main as main_module
from museoncli.config import Config
from museoncli.main import build_parser
from museoncli.domains import account_operation, get_command_spec
from museoncli.execution import CommandContext


def parse(argv: list[str]):
    return build_parser().parse_args(argv)


class _Capture:
    def __init__(self, response: Any = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self._response = response or {"data": {"id": "op-1", "lifecycle_status": "draft"}}

    async def __call__(self, cfg, method, path, *, json_body=None, params=None, **kw):
        self.calls.append(
            {"method": method, "path": path, "json_body": json_body, "params": params}
        )
        return self._response


def _direct(command_name: str, arguments: dict[str, Any], *, runtime: dict | None = None):
    cfg = Config()
    cfg.runtime_context = runtime or {}
    executor = {
        "account-operation.submit": account_operation._execute_submit,
        "account-operation.submit-batch": account_operation._execute_submit_batch,
        "account-operation.stop": account_operation._execute_stop,
        "account-operation.get": account_operation._execute_get,
        "account-operation.list": account_operation._execute_list,
        "account-operation.ops-status": account_operation._execute_ops_status,
        "account-operation.daily-roster": account_operation._execute_daily_roster,
        "account-operation.plan-submit": account_operation._execute_plan_submit,
        "account-operation.strategy-decide": account_operation._execute_strategy_decide,
        "account-operation.elements-replace": account_operation._execute_elements_replace,
    }[command_name]
    ctx = CommandContext(
        cfg=cfg,
        spec=get_command_spec(command_name),
        args=None,
        arguments=arguments,
        workspace_id="ws-1",
        api_data=main_module.api_data,
        api_data_v2=main_module.api_data_v2,
        upload_media_file=main_module.upload_media_file,
        upload_artifact_file=main_module.upload_artifact_file,
    )
    return asyncio.run(executor(ctx))


def test_parser_registers_account_operation_commands() -> None:
    args = parse(
        [
            "account-operation",
            "+submit",
            "--pool-account-id",
            "11111111-1111-1111-1111-111111111111",
            "--organization-id",
            "22222222-2222-2222-2222-222222222222",
            "--product-id",
            "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            "--niche",
            "leather_care",
        ]
    )
    assert args.domain_command == "account-operation.submit"
    assert args.product_id == "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"

    decide = parse(
        [
            "account-operation",
            "+strategy-decide",
            "--id",
            "33333333-3333-3333-3333-333333333333",
            "--run-id",
            "44444444-4444-4444-4444-444444444444",
            "--decided-by",
            "auto-timeout",
        ]
    )
    assert decide.domain_command == "account-operation.strategy-decide"

    stop = parse(
        [
            "account-operation",
            "+stop",
            "--id",
            "33333333-3333-3333-3333-333333333333",
            "--reason",
            "历史冲突换一批账号",
        ]
    )
    assert stop.domain_command == "account-operation.stop"
    built = account_operation._build_account_operation_stop_arguments(stop)
    assert built == {
        "operation_id": "33333333-3333-3333-3333-333333333333",
        "reason": "历史冲突换一批账号",
    }


def test_submit_posts_with_conversation_from_runtime_context(monkeypatch) -> None:
    capture = _Capture()
    monkeypatch.setattr(main_module, "api_data_v2", capture)
    _direct(
        "account-operation.submit",
        {
            "pool_account_id": "pool-1",
            "organization_id": "org-1",
            "product_id": "product-1",
            "niche": "leather",
        },
        runtime={"conversation_id": "conv-9"},
    )
    call = capture.calls[0]
    assert call["method"] == "POST" and call["path"] == "/account-operations"
    body = call["json_body"]
    assert body["workspace_id"] == "ws-1"
    assert body["pool_account_id"] == "pool-1"
    assert body["product_id"] == "product-1"
    assert body["session_conversation_id"] == "conv-9"  # defaulted from per-turn runtime context


def test_submit_allows_omitted_optional_product(monkeypatch) -> None:
    args = parse(
        [
            "account-operation",
            "+submit",
            "--pool-account-id",
            "pool-1",
            "--organization-id",
            "org-1",
        ]
    )
    assert args.product_id is None

    capture = _Capture()
    monkeypatch.setattr(main_module, "api_data_v2", capture)
    _direct(
        "account-operation.submit",
        {
            "pool_account_id": "pool-1",
            "organization_id": "org-1",
            "product_id": None,
        },
    )
    assert "product_id" not in capture.calls[0]["json_body"]


def test_submit_batch_sends_one_shared_product_not_per_account(monkeypatch) -> None:
    args = parse(
        [
            "account-operation",
            "+submit-batch",
            "--pool-account-ids",
            "pool-1,pool-2",
            "--organization-id",
            "org-1",
            "--product-id",
            "product-1",
        ]
    )
    built = account_operation._build_account_operation_submit_batch_arguments(args)
    assert built["product_id"] == "product-1"

    capture = _Capture(response={"data": [], "meta": {}})
    monkeypatch.setattr(main_module, "api_data_v2", capture)
    _direct(
        "account-operation.submit-batch",
        {
            "pool_account_ids": "pool-1,pool-2",
            "organization_id": "org-1",
            "product_id": "product-1",
        },
        runtime={"conversation_id": "conv-9"},
    )

    body = capture.calls[0]["json_body"]
    assert body["product_id"] == "product-1"
    assert body["accounts"] == [
        {"pool_account_id": "pool-1"},
        {"pool_account_id": "pool-2"},
    ]
    assert all("product_id" not in account for account in body["accounts"])


def test_submit_contract_describes_account_publish_managed_takeover() -> None:
    submit = get_command_spec("account-operation.submit")
    batch = get_command_spec("account-operation.submit-batch")

    assert "explicit Account Publish -> fully-managed mode switch" in submit.summary
    assert "atomically transferred" in submit.summary
    assert "existing publish configuration is preserved" in submit.summary
    assert "Live schedule work never blocks the switch" in submit.summary
    assert "future scheduled items are adopted by the operation" in submit.summary
    assert "account_publish_schedule_conflict" not in submit.summary
    assert "blocking_schedule_counts" not in submit.summary
    assert "account_publish holder is transferred automatically" in batch.summary
    assert "never cancel schedules to unblock enrollment" in batch.summary
    assert "blocking_schedule_counts" not in batch.output_schema["description"]


def test_get_and_list(monkeypatch) -> None:
    capture = _Capture()
    monkeypatch.setattr(main_module, "api_data_v2", capture)
    _direct("account-operation.get", {"operation_id": "op-1"})
    _direct("account-operation.list", {"limit": 10})
    assert capture.calls[0]["method"] == "GET"
    assert capture.calls[0]["path"] == "/account-operations/op-1"
    assert capture.calls[1]["path"] == "/account-operations"
    assert capture.calls[1]["params"]["workspace_id"] == "ws-1"


def test_ops_status_gets_aggregate_scoped_to_workspace(monkeypatch) -> None:
    capture = _Capture(response={"data": {"accounts_needing_intervention": 0}})
    monkeypatch.setattr(main_module, "api_data_v2", capture)
    _direct("account-operation.ops-status", {})
    call = capture.calls[0]
    assert call["method"] == "GET"
    assert call["path"] == "/account-operations/ops-status"
    assert call["params"]["workspace_id"] == "ws-1"
    # No --window -> omitted so the API default (24h) applies.
    assert "window" not in call["params"]


def test_ops_status_forwards_failed_reasons_window(monkeypatch) -> None:
    capture = _Capture(response={"data": {"failed_reasons_window": "7d"}})
    monkeypatch.setattr(main_module, "api_data_v2", capture)
    _direct("account-operation.ops-status", {"window": "7d"})
    call = capture.calls[0]
    assert call["params"]["window"] == "7d"

    # Parser accepts only 24h|7d and defaults to omitted (API default 24h).
    args = parse(["account-operation", "+ops-status", "--window", "7d"])
    assert args.domain_command == "account-operation.ops-status"
    built = account_operation._build_account_operation_ops_status_arguments(args)
    assert built == {"window": "7d"}


def test_daily_roster_posts_to_health_roster_endpoint(monkeypatch) -> None:
    capture = _Capture(response={"data": {"summary": {}, "accounts": [], "pagination": {}}})
    monkeypatch.setattr(main_module, "api_data_v2", capture)
    _direct(
        "account-operation.daily-roster",
        {
            "date": "2026-07-21",
            "timezone": "Asia/Shanghai",
            "result_filter": "no_publish",
            "page": 1,
            "page_size": 200,
        },
    )
    call = capture.calls[0]
    assert call["method"] == "POST"
    assert call["path"] == "/account-ops-health/roster/query"
    body = call["json_body"]
    assert body["workspace_id"] == "ws-1"
    assert body["date"] == "2026-07-21"
    assert body["timezone"] == "Asia/Shanghai"
    assert body["filter"] == "no_publish"
    # Omitted optionals are dropped so the API defaults apply.
    assert "managed" not in body
    assert "success" not in body


def test_daily_roster_parser_dekebabs_filter_and_keeps_workspace_from_context() -> None:
    args = parse(
        ["account-operation", "+daily-roster", "--filter", "no-publish", "--managed", "semi"]
    )
    assert args.domain_command == "account-operation.daily-roster"
    built = account_operation._build_account_operation_daily_roster_arguments(args)
    # Enum stays kebab on the CLI surface, dekebabbed onto the wire value.
    assert built["result_filter"] == "no_publish"
    assert built["managed"] == "semi"


def test_daily_roster_forwards_as_of_cutoff_and_behind_filter(monkeypatch) -> None:
    args = parse(
        [
            "account-operation",
            "+daily-roster",
            "--tz",
            "Asia/Shanghai",
            "--as-of",
            "18:00",
            "--filter",
            "behind",
        ]
    )
    built = account_operation._build_account_operation_daily_roster_arguments(args)
    assert built["as_of"] == "18:00"
    assert built["result_filter"] == "behind"

    capture = _Capture(response={"data": {"summary": {}, "accounts": [], "pagination": {}}})
    monkeypatch.setattr(main_module, "api_data_v2", capture)
    _direct(
        "account-operation.daily-roster",
        {"timezone": "Asia/Shanghai", "as_of": "18:00", "result_filter": "behind"},
    )
    body = capture.calls[0]["json_body"]
    assert body["as_of"] == "18:00"
    assert body["filter"] == "behind"


def test_worker_callbacks(monkeypatch) -> None:
    capture = _Capture()
    monkeypatch.setattr(main_module, "api_data_v2", capture)
    _direct(
        "account-operation.plan-submit",
        {
            "operation_id": "op-1",
            "format_ids": "f1,f2",
            "topic_ids": "t1",
            "required_hashtags": "#PlantSenso,#PlantCare",
            "note": "n",
        },
    )
    _direct(
        "account-operation.strategy-decide",
        {
            "operation_id": "op-1",
            "run_id": "run-1",
            "decided_by": "human",
            "decision_json": '{"action": "override"}',
        },
    )
    _direct(
        "account-operation.elements-replace",
        {"operation_id": "op-1", "add_format_ids": "f9", "pause_topic_ids": "t0"},
    )
    plan, decide, elements = capture.calls
    assert plan["path"] == "/account-operations/op-1/plan:submit"
    assert plan["json_body"]["format_ids"] == ["f1", "f2"]
    assert plan["json_body"]["topic_ids"] == ["t1"]
    assert plan["json_body"]["required_hashtags"] == ["#PlantSenso", "#PlantCare"]
    assert decide["path"] == "/account-operations/op-1/daily-runs/run-1/strategy:decide"
    assert decide["json_body"]["decided_by"] == "human"
    assert decide["json_body"]["decision"] == {"action": "override"}
    assert elements["path"] == "/account-operations/op-1/elements:replace"
    assert elements["json_body"]["add_format_ids"] == ["f9"]
    assert elements["json_body"]["pause_topic_ids"] == ["t0"]


def test_stop_posts_reason_to_stop_endpoint(monkeypatch) -> None:
    # Conflict-swap retirement: +stop is the ONLY agent-facing way to retire an
    # op (swapping in replacement accounts does not GC the originals).
    capture = _Capture(response={"data": {"id": "op-1", "lifecycle_status": "stopped"}})
    monkeypatch.setattr(main_module, "api_data_v2", capture)
    _direct("account-operation.stop", {"operation_id": "op-1", "reason": "历史冲突换号"})
    call = capture.calls[0]
    assert call["method"] == "POST"
    assert call["path"] == "/account-operations/op-1/stop"
    assert call["json_body"] == {"reason": "历史冲突换号"}

    # No --reason -> empty body (endpoint treats the body as optional).
    _direct("account-operation.stop", {"operation_id": "op-2"})
    assert capture.calls[1]["json_body"] == {}


def test_write_commands_dry_run_do_not_call_api(monkeypatch) -> None:
    cfg = Config()
    cfg.runtime_context = {"conversation_id": "conv-9"}

    async def explode(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("dry run should not call API")

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data_v2", explode)

    pool_id = "11111111-1111-1111-1111-111111111111"
    org_id = "22222222-2222-2222-2222-222222222222"
    op_id = "33333333-3333-3333-3333-333333333333"
    run_id = "44444444-4444-4444-4444-444444444444"
    format_a = "55555555-5555-4555-8555-555555555555"
    format_b = "66666666-6666-4666-8666-666666666666"
    argvs = [
        [
            "account-operation",
            "+submit",
            "--pool-account-id",
            pool_id,
            "--organization-id",
            org_id,
            "--dry-run",
        ],
        [
            "account-operation",
            "+plan-submit",
            "--id",
            op_id,
            "--format-ids",
            f"{format_a},{format_b}",
            "--dry-run",
        ],
        [
            "account-operation",
            "+strategy-decide",
            "--id",
            op_id,
            "--run-id",
            run_id,
            "--decided-by",
            "human",
            "--dry-run",
        ],
        [
            "account-operation",
            "+elements-replace",
            "--id",
            op_id,
            "--add-format-ids",
            format_a,
            "--dry-run",
        ],
        [
            "account-operation",
            "+stop",
            "--id",
            op_id,
            "--reason",
            "conflict swap",
            "--dry-run",
        ],
    ]
    for argv in argvs:
        result = asyncio.run(main_module.dispatch(parse(argv)))
        assert result["data"]["dry_run"] is True, argv


def test_plan_submit_csv_ids_pass_uuid_validation_and_reach_api(monkeypatch) -> None:
    """Regression: CSV *_ids used to stay strings and fail UUID list validation."""
    cfg = Config()
    capture = _Capture()
    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data_v2", capture)

    op_id = "33333333-3333-3333-3333-333333333333"
    format_a = "55555555-5555-4555-8555-555555555555"
    topic_a = "77777777-7777-4777-8777-777777777777"
    result = asyncio.run(
        main_module.dispatch(
            parse(
                [
                    "account-operation",
                    "+plan-submit",
                    "--id",
                    op_id,
                    "--format-ids",
                    format_a,
                    "--topic-ids",
                    topic_a,
                ]
            )
        )
    )
    assert result["command"] == "account-operation.plan-submit"
    call = capture.calls[0]
    assert call["path"] == f"/account-operations/{op_id}/plan:submit"
    assert call["json_body"]["format_ids"] == [format_a]
    assert call["json_body"]["topic_ids"] == [topic_a]


@pytest.mark.parametrize(
    ("cli_args", "expected_presence", "expected_value"),
    [
        ([], False, None),
        (["--required-hashtags", "#PlantSenso, #PlantCare"], True, ["#PlantSenso", "#PlantCare"]),
        (["--required-hashtags", ""], True, []),
    ],
)
def test_plan_submit_required_hashtags_preserve_override_and_clear(
    monkeypatch,
    cli_args,
    expected_presence,
    expected_value,
) -> None:
    cfg = Config()
    capture = _Capture()
    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data_v2", capture)

    op_id = "33333333-3333-3333-3333-333333333333"
    result = asyncio.run(
        main_module.dispatch(
            parse(
                [
                    "account-operation",
                    "+plan-submit",
                    "--id",
                    op_id,
                    *cli_args,
                ]
            )
        )
    )

    assert result["command"] == "account-operation.plan-submit"
    payload = capture.calls[0]["json_body"]
    assert ("required_hashtags" in payload) is expected_presence
    if expected_presence:
        assert payload["required_hashtags"] == expected_value


def test_plan_submit_schema_exposes_required_hashtags_array() -> None:
    schema = get_command_spec("account-operation.plan-submit").input_schema

    assert schema["properties"]["required_hashtags"] == {
        "type": "array",
        "items": {"type": "string"},
        "maxItems": 50,
        "description": (
            "Account-wide required hashtags. Omit to preserve the current setting; "
            "pass an empty array to clear it."
        ),
    }


def test_all_write_command_specs_support_dry_run() -> None:
    from museoncli.domains import command_specs

    missing = [
        spec.schema_name
        for spec in command_specs()
        if spec.risk_level == "write" and not spec.supports_dry_run
    ]
    assert missing == []


def test_every_spec_has_exactly_one_executor() -> None:
    from museoncli.domains import command_executors, command_specs

    spec_names = {spec.schema_name for spec in command_specs()}
    executor_names = set(command_executors())
    assert spec_names == executor_names
