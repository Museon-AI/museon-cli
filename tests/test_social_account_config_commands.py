"""Focused parser and dispatch coverage for social-account publish settings."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from museoncli import main as main_module
from museoncli.config import Config, WorkspaceState
from museoncli.domains import get_command_spec, social_account
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


def test_adb_connect_uses_native_adb_without_printing_the_temporary_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _AdbCapture(_Capture):
        async def __call__(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
            await super().__call__(*args, **kwargs)
            return {
                "domain": "social-account",
                "result": {
                    "serial": "203.0.113.9:12345",
                    "password": "temporary-password",
                },
            }

    capture = _AdbCapture()
    adb_commands: list[tuple[str, ...]] = []

    class _Process:
        def __init__(self, stdout: bytes) -> None:
            self.returncode = 0
            self._stdout = stdout

        async def communicate(self) -> tuple[bytes, bytes]:
            return self._stdout, b""

    async def fake_create_subprocess_exec(*argv: str, **_kwargs: Any) -> _Process:
        adb_commands.append(argv)
        stdout = b"device\n" if argv[-1] == "get-state" else b""
        return _Process(stdout)

    monkeypatch.setattr(main_module, "load_config", _config_with_workspace)
    monkeypatch.setattr(main_module, "api_data", capture)
    monkeypatch.setattr(
        social_account.asyncio, "create_subprocess_exec", fake_create_subprocess_exec
    )

    result = asyncio.run(
        main_module.dispatch(_parse(["social-account", "+adb-connect", "--id", ACCOUNT_ID]))
    )

    assert capture.calls == [
        {
            "method": "POST",
            "path": f"/agent-cli/social-accounts/{ACCOUNT_ID}/adb-credentials",
            "json_body": None,
            "params": {"workspace_id": "workspace-1"},
        }
    ]
    assert adb_commands == [
        ("adb", "connect", "203.0.113.9:12345"),
        ("adb", "-s", "203.0.113.9:12345", "shell", "glogin", "temporary-password"),
        ("adb", "-s", "203.0.113.9:12345", "get-state"),
    ]
    assert result is not None
    assert result["data"]["serial"] == "203.0.113.9:12345"
    assert "temporary-password" not in repr(result)


def test_adb_connect_dry_run_avoids_provider_and_local_adb(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fail_api(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("dry-run must not call the API")

    monkeypatch.setattr(main_module, "load_config", _config_with_workspace)
    monkeypatch.setattr(main_module, "api_data", fail_api)

    result = asyncio.run(
        main_module.dispatch(
            _parse(["social-account", "+adb-connect", "--id", ACCOUNT_ID, "--dry-run"])
        )
    )

    assert result is not None
    assert result["data"]["dry_run"] is True
    assert result["data"]["would_execute"] == "social-account.adb-connect"


def test_adb_connect_kills_a_timed_out_native_subprocess(monkeypatch: pytest.MonkeyPatch) -> None:
    class _HangingProcess:
        def __init__(self) -> None:
            self.calls = 0
            self.killed = False
            self.returncode = 0

        async def communicate(self) -> tuple[bytes, bytes]:
            self.calls += 1
            if self.calls == 1:
                await asyncio.Event().wait()
            return b"", b""

        def kill(self) -> None:
            self.killed = True

    process = _HangingProcess()

    async def fake_create_subprocess_exec(*_args: Any, **_kwargs: Any) -> _HangingProcess:
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    monkeypatch.setattr(social_account, "ADB_COMMAND_TIMEOUT_SECONDS", 0.001)

    with pytest.raises(RuntimeError, match="adb_connect_timed_out"):
        asyncio.run(social_account._run_adb("connect", "203.0.113.9:12345"))

    assert process.killed is True


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

    assert built["account_updates"] == [{"account_id": ACCOUNT_ID, "output_language": "zh-CN"}]


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
    assert capture.calls[0]["path"] == ("/agent-cli/social-accounts/publish-config/settings:batch")
    assert capture.calls[0]["json_body"] == {
        "workspace_id": "workspace-1",
        "payload": {
            "account_updates": [
                {"account_id": ACCOUNT_ID, "required_hashtags": ["#Soliya"]},
                {"account_id": ACCOUNT_ID_2, "required_hashtags": ["#Soliya"]},
            ]
        },
    }
