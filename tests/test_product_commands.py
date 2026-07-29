from __future__ import annotations

import argparse
import asyncio
from typing import Any

import pytest

from museoncli import main as main_module
from museoncli.config import Config, WorkspaceState
from museoncli.domains import get_command_spec, product
from museoncli.execution import CommandContext
from museoncli.main import build_parser


def parse(argv: list[str]) -> argparse.Namespace:
    return build_parser().parse_args(argv)


class Capture:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, cfg, method, path, *, json_body=None, params=None, **kwargs):
        self.calls.append(
            {"method": method, "path": path, "json_body": json_body, "params": params}
        )
        return {}


def context(command: str, arguments: dict[str, Any], capture: Capture) -> CommandContext:
    return CommandContext(
        cfg=Config(),
        spec=get_command_spec(command),
        args=None,
        arguments=arguments,
        workspace_id="11111111-1111-4111-8111-111111111111",
        api_data=capture,
        api_data_v2=capture,
        upload_media_file=capture,
        upload_artifact_file=capture,
    )


def test_cta_target_list_maps_to_v1_get() -> None:
    product_id = "22222222-2222-4222-8222-222222222222"
    args = parse(["product", "+cta-target-list", "--product-id", product_id])
    arguments = product._build_list_arguments(args)
    capture = Capture()
    asyncio.run(product._execute_list(context("product.cta-target-list", arguments, capture)))
    assert capture.calls == [
        {
            "method": "GET",
            "path": f"/products/{product_id}/cta-targets",
            "json_body": None,
            "params": None,
        }
    ]
    assert get_command_spec("product.cta-target-list").supports_dry_run is False


def test_cta_target_create_builds_ordered_assets_and_maps_to_v1_post() -> None:
    product_id = "22222222-2222-4222-8222-222222222222"
    args = parse(
        [
            "product",
            "+cta-target-create",
            "--product-id",
            product_id,
            "--title",
            "Shop now",
            "--content-markdown",
            "See the collection.",
            "--asset-ids",
            "media-b,media-a",
            "--dry-run",
        ]
    )
    arguments = product._build_create_arguments(args)
    assert arguments["assets"] == [
        {"media_id": "media-b", "sort_order": 0},
        {"media_id": "media-a", "sort_order": 1},
    ]
    assert arguments["dry_run"] is True
    capture = Capture()
    asyncio.run(product._execute_create(context("product.cta-target-create", arguments, capture)))
    assert capture.calls[-1] == {
        "method": "POST",
        "path": f"/products/{product_id}/cta-targets",
        "json_body": {
            "title": "Shop now",
            "content_markdown": "See the collection.",
            "assets": [
                {"media_id": "media-b", "sort_order": 0},
                {"media_id": "media-a", "sort_order": 1},
            ],
        },
        "params": None,
    }
    assert get_command_spec("product.cta-target-create").supports_dry_run is True


def test_cta_target_create_defaults_to_empty_assets() -> None:
    args = parse(
        [
            "product",
            "+cta-target-create",
            "--product-id",
            "product-1",
            "--title",
            "Shop",
            "--content-markdown",
            "Now",
        ]
    )
    assert product._build_create_arguments(args)["assets"] == []


@pytest.mark.parametrize("shortcut", ["+cta-target-create", "+cta-target-update"])
def test_cta_target_write_dry_run_is_local(shortcut: str, monkeypatch: pytest.MonkeyPatch) -> None:
    async def fail_api(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("dry-run must not call the API")

    monkeypatch.setattr(main_module, "api_data", fail_api)
    argv = [
        "product",
        shortcut,
        "--product-id",
        "22222222-2222-4222-8222-222222222222",
        "--dry-run",
    ]
    if shortcut == "+cta-target-create":
        argv.extend(["--title", "Shop", "--content-markdown", "Now"])
    else:
        argv.extend(
            [
                "--cta-target-id",
                "33333333-3333-4333-8333-333333333333",
                "--title",
                "Shop",
            ]
        )
    cfg = Config(workspace=WorkspaceState(id="11111111-1111-4111-8111-111111111111"))
    result = asyncio.run(main_module.dispatch_domain_command(parse(argv), cfg))
    assert result["data"]["dry_run"] is True


@pytest.mark.parametrize(
    "missing",
    [
        ["--title", "Shop", "--content-markdown", "Now"],
        ["--product-id", "product-1", "--content-markdown", "Now"],
        ["--product-id", "product-1", "--title", "Shop"],
    ],
)
def test_cta_target_create_requires_fields(missing: list[str]) -> None:
    with pytest.raises(SystemExit):
        parse(["product", "+cta-target-create", *missing])


def test_cta_target_update_is_partial_and_empty_assets_clear_all() -> None:
    args = parse(
        [
            "product",
            "+cta-target-update",
            "--product-id",
            "product-1",
            "--cta-target-id",
            "cta-1",
            "--asset-ids",
            "",
        ]
    )
    arguments = product._build_update_arguments(args)
    assert arguments == {
        "product_id": "product-1",
        "cta_target_id": "cta-1",
        "assets": [],
        "dry_run": False,
    }
    capture = Capture()
    asyncio.run(product._execute_update(context("product.cta-target-update", arguments, capture)))
    assert capture.calls[-1] == {
        "method": "PATCH",
        "path": "/products/product-1/cta-targets/cta-1",
        "json_body": {"assets": []},
        "params": None,
    }


def test_cta_target_update_requires_mutable_field() -> None:
    args = parse(
        [
            "product",
            "+cta-target-update",
            "--product-id",
            "product-1",
            "--cta-target-id",
            "cta-1",
        ]
    )
    with pytest.raises(ValueError, match="at least one mutable flag"):
        product._build_update_arguments(args)


@pytest.mark.parametrize(
    "missing",
    [
        ["--cta-target-id", "cta-1", "--title", "Shop"],
        ["--product-id", "product-1", "--title", "Shop"],
    ],
)
def test_cta_target_update_requires_ids(missing: list[str]) -> None:
    with pytest.raises(SystemExit):
        parse(["product", "+cta-target-update", *missing])


def test_cta_target_list_requires_product_id() -> None:
    with pytest.raises(SystemExit):
        parse(["product", "+cta-target-list"])
