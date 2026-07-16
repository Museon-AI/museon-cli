"""End-to-end dispatch tests for campaign-monitor tracking write commands.

Covers +creator-add / +creator-remove / +content-add — the creator/post
tracking write surface added on top of the read + content-remove commands.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from museoncli import main as main_module
from museoncli.config import Config, WorkspaceState
from museoncli.domains import get_command_spec
from museoncli.main import build_parser

CAMPAIGN_ID = "10000000-0000-4000-8000-000000000001"
CREATOR_ID = "20000000-0000-4000-8000-000000000001"
CONTENT_ID = "30000000-0000-4000-8000-000000000001"


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
        return {"domain": "campaign-monitor", "result": {"campaign_id": CAMPAIGN_ID}}


def parse(argv: list[str]) -> Any:
    return build_parser().parse_args(argv)


def _config_with_workspace() -> Config:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="Workspace", organization_id="org-1")
    return cfg


def test_parser_registers_tracking_write_commands() -> None:
    add = parse(
        [
            "campaign-monitor",
            "+creator-add",
            "--id",
            CAMPAIGN_ID,
            "--url",
            "https://www.tiktok.com/@a",
            "--creator-id",
            CREATOR_ID,
        ]
    )
    assert add.domain_command == "campaign-monitor.creator-add"
    assert add.creator_urls == ["https://www.tiktok.com/@a"]
    assert add.creator_ids == [CREATOR_ID]

    remove = parse(
        ["campaign-monitor", "+creator-remove", "--id", CAMPAIGN_ID, "--creator-id", CREATOR_ID]
    )
    assert remove.domain_command == "campaign-monitor.creator-remove"
    assert remove.creator_social_account_id == CREATOR_ID

    content = parse(
        ["campaign-monitor", "+content-add", "--id", CAMPAIGN_ID, "--content-id", CONTENT_ID]
    )
    assert content.domain_command == "campaign-monitor.content-add"
    assert content.content_ids == [CONTENT_ID]


def test_creator_add_requires_url_or_creator_id() -> None:
    args = parse(["campaign-monitor", "+creator-add", "--id", CAMPAIGN_ID])
    spec = get_command_spec("campaign-monitor.creator-add")
    with pytest.raises(ValueError):
        spec.build_arguments(args)


def test_content_add_requires_url_or_content_id() -> None:
    args = parse(["campaign-monitor", "+content-add", "--id", CAMPAIGN_ID])
    spec = get_command_spec("campaign-monitor.content-add")
    with pytest.raises(ValueError):
        spec.build_arguments(args)


def test_creator_add_posts_urls_ids_and_sync_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = _config_with_workspace()
    capture = _Capture()
    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", capture)

    asyncio.run(
        main_module.dispatch(
            parse(
                [
                    "campaign-monitor",
                    "+creator-add",
                    "--id",
                    CAMPAIGN_ID,
                    "--url",
                    "https://www.tiktok.com/@a",
                    "--creator-id",
                    CREATOR_ID,
                    "--hashtag",
                    "ad",
                    "--no-sync",
                ]
            )
        )
    )

    assert capture.calls == [
        {
            "method": "POST",
            "path": f"/agent-cli/campaign-monitors/{CAMPAIGN_ID}/creators",
            "json_body": {
                "workspace_id": "workspace-1",
                "payload": {
                    "creator_urls": ["https://www.tiktok.com/@a"],
                    "creator_ids": [CREATOR_ID],
                    "hashtags": ["ad"],
                    "sync": False,
                },
            },
            "params": None,
        }
    ]


def test_content_add_posts_content_id(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = _config_with_workspace()
    capture = _Capture()
    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", capture)

    asyncio.run(
        main_module.dispatch(
            parse(
                [
                    "campaign-monitor",
                    "+content-add",
                    "--id",
                    CAMPAIGN_ID,
                    "--content-id",
                    CONTENT_ID,
                ]
            )
        )
    )

    call = capture.calls[0]
    assert call["method"] == "POST"
    assert call["path"] == f"/agent-cli/campaign-monitors/{CAMPAIGN_ID}/content"
    assert call["json_body"] == {
        "workspace_id": "workspace-1",
        "payload": {"content_ids": [CONTENT_ID]},
    }


def test_creator_remove_without_yes_requires_confirmation(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = _config_with_workspace()

    async def explode(*args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        raise AssertionError("confirmation gate must block the API call")

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", explode)

    with pytest.raises(RuntimeError, match="confirmation_required"):
        asyncio.run(
            main_module.dispatch(
                parse(
                    [
                        "campaign-monitor",
                        "+creator-remove",
                        "--id",
                        CAMPAIGN_ID,
                        "--creator-id",
                        CREATOR_ID,
                    ]
                )
            )
        )


def test_creator_remove_with_yes_posts_remove_path(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = _config_with_workspace()
    capture = _Capture()
    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", capture)

    result = asyncio.run(
        main_module.dispatch(
            parse(
                [
                    "campaign-monitor",
                    "+creator-remove",
                    "--id",
                    CAMPAIGN_ID,
                    "--creator-id",
                    CREATOR_ID,
                    "--yes",
                ]
            )
        )
    )

    assert result["command"] == "campaign-monitor.creator-remove"
    assert capture.calls == [
        {
            "method": "POST",
            "path": (f"/agent-cli/campaign-monitors/{CAMPAIGN_ID}/creators/{CREATOR_ID}/remove"),
            "json_body": {"workspace_id": "workspace-1", "payload": {}},
            "params": None,
        }
    ]


@pytest.mark.parametrize(
    "argv,command",
    [
        (
            [
                "campaign-monitor",
                "+creator-add",
                "--id",
                CAMPAIGN_ID,
                "--creator-id",
                CREATOR_ID,
                "--dry-run",
            ],
            "campaign-monitor.creator-add",
        ),
        (
            [
                "campaign-monitor",
                "+creator-remove",
                "--id",
                CAMPAIGN_ID,
                "--creator-id",
                CREATOR_ID,
                "--dry-run",
            ],
            "campaign-monitor.creator-remove",
        ),
        (
            [
                "campaign-monitor",
                "+content-add",
                "--id",
                CAMPAIGN_ID,
                "--content-id",
                CONTENT_ID,
                "--dry-run",
            ],
            "campaign-monitor.content-add",
        ),
    ],
)
def test_tracking_write_commands_dry_run_do_not_call_api(
    monkeypatch: pytest.MonkeyPatch, argv: list[str], command: str
) -> None:
    cfg = _config_with_workspace()

    async def explode(*args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        raise AssertionError("dry run should not call API")

    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", explode)

    result = asyncio.run(main_module.dispatch(parse(argv)))
    assert result["command"] == command
    assert result["data"]["dry_run"] is True
