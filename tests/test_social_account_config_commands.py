"""Focused parser and dispatch coverage for social-account publish settings."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from museoncli import main as main_module
from museoncli.config import Config, WorkspaceState
from museoncli.domains import get_command_spec
from museoncli.main import build_parser


ACCOUNT_ID = "10000000-0000-4000-8000-000000000001"


class _Capture:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

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
        return {"domain": "social-account", "result": {"output_language": "zh-CN"}}


def _parse(argv: list[str]) -> Any:
    return build_parser().parse_args(argv)


def _config_with_workspace() -> Config:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="Workspace", organization_id="org-1")
    return cfg


def test_config_update_parser_accepts_language_alias() -> None:
    args = _parse(
        [
            "social-account",
            "+config-update",
            "--id",
            ACCOUNT_ID,
            "--language",
            "zh-CN",
        ]
    )

    assert args.domain_command == "social-account.config-update"
    assert args.output_language == "zh-CN"


def test_config_update_requires_at_least_one_change() -> None:
    args = _parse(["social-account", "+config-update", "--id", ACCOUNT_ID])
    spec = get_command_spec("social-account.config-update")

    with pytest.raises(ValueError, match="--output-language"):
        spec.build_arguments(args)


def test_config_update_schema_allows_language_without_approval() -> None:
    schema = get_command_spec("social-account.config-update").input_schema

    assert schema["properties"]["output_language"]["maxLength"] == 32
    assert {"required": ["output_language"]} in schema["anyOf"]


def test_config_update_schema_allows_required_hashtags_only() -> None:
    schema = get_command_spec("social-account.config-update").input_schema

    assert schema["properties"]["required_hashtags"]["maxItems"] == 50
    assert {"required": ["required_hashtags"]} in schema["anyOf"]


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        ("#PlantSenso, #PlantCare", ["#PlantSenso", "#PlantCare"]),
        ("", []),
    ],
)
def test_config_update_builds_required_hashtags_patch(
    raw_value: str,
    expected: list[str],
) -> None:
    args = _parse(
        [
            "social-account",
            "+config-update",
            "--id",
            ACCOUNT_ID,
            "--required-hashtags",
            raw_value,
        ]
    )

    built = get_command_spec("social-account.config-update").build_arguments(args)

    assert built["required_hashtags"] == expected
    assert "output_language" not in built
    assert "require_approval_before_publish" not in built


def test_config_update_dispatches_language_only(monkeypatch: pytest.MonkeyPatch) -> None:
    capture = _Capture()
    monkeypatch.setattr(main_module, "load_config", _config_with_workspace)
    monkeypatch.setattr(main_module, "api_data", capture)

    result = asyncio.run(
        main_module.dispatch(
            _parse(
                [
                    "social-account",
                    "+config-update",
                    "--id",
                    ACCOUNT_ID,
                    "--output-language",
                    "zh",
                ]
            )
        )
    )

    assert result["data"] == {"output_language": "zh-CN"}
    assert capture.calls == [
        {
            "method": "PATCH",
            "path": (f"/agent-cli/social-accounts/{ACCOUNT_ID}/publish-config/settings"),
            "json_body": {
                "workspace_id": "workspace-1",
                "payload": {"output_language": "zh"},
            },
            "params": None,
        }
    ]


def test_config_update_dispatches_language_and_approval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture = _Capture()
    monkeypatch.setattr(main_module, "load_config", _config_with_workspace)
    monkeypatch.setattr(main_module, "api_data", capture)

    asyncio.run(
        main_module.dispatch(
            _parse(
                [
                    "social-account",
                    "+config-update",
                    "--id",
                    ACCOUNT_ID,
                    "--output-language",
                    "ja",
                    "--no-require-approval-before-publish",
                ]
            )
        )
    )

    assert capture.calls[0]["json_body"] == {
        "workspace_id": "workspace-1",
        "payload": {
            "require_approval_before_publish": False,
            "output_language": "ja",
        },
    }


def test_config_update_dispatches_explicit_empty_required_hashtags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture = _Capture()
    monkeypatch.setattr(main_module, "load_config", _config_with_workspace)
    monkeypatch.setattr(main_module, "api_data", capture)

    asyncio.run(
        main_module.dispatch(
            _parse(
                [
                    "social-account",
                    "+config-update",
                    "--id",
                    ACCOUNT_ID,
                    "--required-hashtags",
                    "",
                ]
            )
        )
    )

    assert capture.calls[0]["json_body"] == {
        "workspace_id": "workspace-1",
        "payload": {"required_hashtags": []},
    }


ACCOUNT_ID_2 = "10000000-0000-4000-8000-000000000002"


def test_config_batch_update_builds_account_updates_from_ids() -> None:
    args = _parse(
        [
            "social-account",
            "+config-batch-update",
            "--ids",
            f"{ACCOUNT_ID}, {ACCOUNT_ID_2}",
            "--required-hashtags",
            "#PlantSenso, #PlantCare",
        ]
    )

    built = get_command_spec("social-account.config-batch-update").build_arguments(args)

    assert built["account_updates"] == [
        {"account_id": ACCOUNT_ID, "required_hashtags": ["#PlantSenso", "#PlantCare"]},
        {"account_id": ACCOUNT_ID_2, "required_hashtags": ["#PlantSenso", "#PlantCare"]},
    ]


def test_config_batch_update_passes_through_account_updates_json() -> None:
    args = _parse(
        [
            "social-account",
            "+config-batch-update",
            "--account-updates",
            f'[{{"account_id":"{ACCOUNT_ID}","output_language":"zh-CN"}}]',
        ]
    )

    built = get_command_spec("social-account.config-batch-update").build_arguments(args)

    assert built["account_updates"] == [
        {"account_id": ACCOUNT_ID, "output_language": "zh-CN"}
    ]


def test_config_batch_update_requires_ids_or_account_updates() -> None:
    args = _parse(["social-account", "+config-batch-update"])
    spec = get_command_spec("social-account.config-batch-update")

    with pytest.raises(ValueError, match="--account-updates or --ids"):
        spec.build_arguments(args)


def test_config_batch_update_ids_requires_at_least_one_field() -> None:
    args = _parse(["social-account", "+config-batch-update", "--ids", ACCOUNT_ID])
    spec = get_command_spec("social-account.config-batch-update")

    with pytest.raises(ValueError, match="at least one of"):
        spec.build_arguments(args)


def test_config_batch_update_schema_caps_accounts_and_hashtags() -> None:
    schema = get_command_spec("social-account.config-batch-update").input_schema
    account_updates = schema["properties"]["account_updates"]

    assert account_updates["maxItems"] == 200
    item = account_updates["items"]
    assert item["required"] == ["account_id"]
    assert item["properties"]["required_hashtags"]["maxItems"] == 50


def test_config_batch_update_dispatches_to_batch_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture = _Capture()
    monkeypatch.setattr(main_module, "load_config", _config_with_workspace)
    monkeypatch.setattr(main_module, "api_data", capture)

    asyncio.run(
        main_module.dispatch(
            _parse(
                [
                    "social-account",
                    "+config-batch-update",
                    "--ids",
                    f"{ACCOUNT_ID},{ACCOUNT_ID_2}",
                    "--required-hashtags",
                    "#Soliya",
                ]
            )
        )
    )

    assert capture.calls[0]["method"] == "POST"
    assert capture.calls[0]["path"] == (
        "/agent-cli/social-accounts/publish-config/settings:batch"
    )
    assert capture.calls[0]["json_body"] == {
        "workspace_id": "workspace-1",
        "payload": {
            "account_updates": [
                {"account_id": ACCOUNT_ID, "required_hashtags": ["#Soliya"]},
                {"account_id": ACCOUNT_ID_2, "required_hashtags": ["#Soliya"]},
            ]
        },
    }
