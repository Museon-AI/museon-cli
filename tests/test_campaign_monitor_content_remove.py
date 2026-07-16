from __future__ import annotations

import asyncio
from typing import Any

import pytest

from museoncli import main as main_module
from museoncli.config import Config, WorkspaceState
from museoncli.main import build_parser


CAMPAIGN_ID = "10000000-0000-4000-8000-000000000001"
CC_ID_1 = "20000000-0000-4000-8000-000000000001"
CC_ID_2 = "20000000-0000-4000-8000-000000000002"


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
            {
                "method": method,
                "path": path,
                "json_body": json_body,
                "params": params,
            }
        )
        return {
            "domain": "campaign-monitor",
            "operation": "content-batch-remove",
            "result": {"removed_count": len(json_body["payload"]["collection_content_ids"])},
        }


def parse(argv: list[str]) -> Any:
    return build_parser().parse_args(argv)


def _config_with_workspace() -> Config:
    cfg = Config()
    cfg.workspace = WorkspaceState(id="workspace-1", name="Workspace", organization_id="org-1")
    return cfg


@pytest.mark.parametrize(
    "argv,command",
    [
        (
            [
                "campaign-monitor",
                "+content-remove",
                "--id",
                CAMPAIGN_ID,
                "--collection-content-id",
                CC_ID_1,
                "--dry-run",
            ],
            "campaign-monitor.content-remove",
        ),
        (
            [
                "campaign-monitor",
                "+content-batch-remove",
                "--id",
                CAMPAIGN_ID,
                "--collection-content-ids",
                f"{CC_ID_1},{CC_ID_2}",
                "--dry-run",
            ],
            "campaign-monitor.content-batch-remove",
        ),
    ],
)
def test_campaign_monitor_content_remove_dry_run_does_not_call_api(
    monkeypatch: pytest.MonkeyPatch,
    argv: list[str],
    command: str,
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


def test_campaign_monitor_content_remove_without_yes_requires_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
                        "+content-remove",
                        "--id",
                        CAMPAIGN_ID,
                        "--collection-content-id",
                        CC_ID_1,
                    ]
                )
            )
        )


def test_campaign_monitor_content_remove_with_yes_posts_single_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = _config_with_workspace()
    capture = _Capture()
    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", capture)

    result = asyncio.run(
        main_module.dispatch(
            parse(
                [
                    "campaign-monitor",
                    "+content-remove",
                    "--id",
                    CAMPAIGN_ID,
                    "--collection-content-id",
                    CC_ID_1,
                    "--yes",
                ]
            )
        )
    )

    assert result["command"] == "campaign-monitor.content-remove"
    assert capture.calls == [
        {
            "method": "POST",
            "path": f"/agent-cli/campaign-monitors/{CAMPAIGN_ID}/content/batch-remove",
            "json_body": {
                "workspace_id": "workspace-1",
                "payload": {"collection_content_ids": [CC_ID_1]},
            },
            "params": None,
        }
    ]


def test_campaign_monitor_content_batch_remove_parses_and_dedupes_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = _config_with_workspace()
    capture = _Capture()
    monkeypatch.setattr(main_module, "load_config", lambda: cfg)
    monkeypatch.setattr(main_module, "api_data", capture)

    asyncio.run(
        main_module.dispatch(
            parse(
                [
                    "campaign-monitor",
                    "+content-batch-remove",
                    "--id",
                    CAMPAIGN_ID,
                    "--collection-content-ids",
                    f"{CC_ID_1}, {CC_ID_2},{CC_ID_1}",
                    "--yes",
                ]
            )
        )
    )

    assert capture.calls[0]["json_body"]["payload"]["collection_content_ids"] == [
        CC_ID_1,
        CC_ID_2,
    ]


def test_campaign_monitor_content_batch_remove_missing_workspace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config()
    monkeypatch.setattr(main_module, "load_config", lambda: cfg)

    with pytest.raises(RuntimeError, match="missing_workspace"):
        asyncio.run(
            main_module.dispatch(
                parse(
                    [
                        "campaign-monitor",
                        "+content-batch-remove",
                        "--id",
                        CAMPAIGN_ID,
                        "--collection-content-ids",
                        CC_ID_1,
                        "--yes",
                    ]
                )
            )
        )
