"""Commands over the routes that work with the organization alone (monorepo #7366).

Each test drives the real CLI entry point over a mocked HTTP transport, so the method, path,
query, body and headers asserted are the ones that would go out: always `X-Organization-Id`,
never a workspace, and `{}` where the body used to hold only the workspace.
"""

from __future__ import annotations

import json
import sys
from typing import Any

import httpx
import pytest
from routes_stub import API, ORG, Server, body, query

import museoncli.main as cli
from museoncli.config import AuthState, Config, OrganizationState

_REAL_CLIENT = httpx.AsyncClient
ID = "11111111-1111-4111-8111-111111111111"
ITEM = "22222222-2222-4222-8222-222222222222"
PROFILE = "66b2f0c1a9d3e4f5a6b7c8d9"


@pytest.fixture
def cli_run(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    def go(server: Server, *argv: str) -> tuple[int, dict[str, Any]]:
        monkeypatch.setenv("MUSEONCLI_UPDATE_CHECK", "0")
        cfg = Config(
            api_base_url=f"{API}/api/v1",
            auth=AuthState(api_key="test-only"),
            organization=OrganizationState(id=ORG, name="MuseOn"),
        )
        monkeypatch.setattr(cli, "load_config", lambda: cfg)
        monkeypatch.setattr(
            cli.httpx,
            "AsyncClient",
            lambda **kw: _REAL_CLIENT(**kw, transport=httpx.MockTransport(server)),
        )
        monkeypatch.setattr(sys, "argv", ["museoncli", *argv])
        code = 0
        try:
            cli.main()
        except SystemExit as exited:
            code = int(exited.code or 0)
        payload = json.loads(capsys.readouterr().out)
        for request in server.requests:
            assert request.headers.get("X-Organization-Id") == ORG
            assert "workspace" not in request.url.query.decode()
            assert not any("workspace" in name.lower() for name in request.headers)
            assert b"workspace" not in request.content
        return code, payload

    return go


# -- social account sync and unbind -----------------------------------------


def test_sync_posts_the_profile_route_with_no_body_and_no_workspace(cli_run) -> None:
    path = f"/api/v1/social-accounts/profiles/{PROFILE}/sync"
    server = Server({("POST", path): {"success": True, "data": {"synced": 2}}})

    code, result = cli_run(server, "social-account", "+sync", "--profile-id", PROFILE)

    assert code == 0, result
    (sent,) = server.requests
    assert sent.url.path == path
    assert query(sent) == {}
    assert result["data"] == {"synced": 2}


def test_sync_all_posts_the_organization_wide_route(cli_run) -> None:
    path = "/api/v1/social-accounts/sync-all-accounts"
    server = Server({("POST", path): {"success": True, "data": {"synced": 5}}})

    code, result = cli_run(server, "social-account", "+sync-all")

    assert code == 0, result
    (sent,) = server.requests
    assert (sent.method, sent.url.path, query(sent)) == ("POST", path, {})
    assert any("landing workspace" in warning for warning in result["warnings"])


def test_sync_dry_run_sends_nothing(cli_run) -> None:
    server = Server({})

    code, _ = cli_run(server, "social-account", "+sync", "--profile-id", PROFILE, "--dry-run")

    assert code == 0
    assert server.requests == []


def test_unbind_without_yes_is_refused_with_its_preview_and_sends_nothing(cli_run) -> None:
    server = Server({})

    code, result = cli_run(server, "social-account", "+unbind", "--account-id", ID)

    assert code == cli.EXIT_FAILURE
    assert result["reason"] == "confirmation_required"
    assert result["preview"]["data"]["would_unbind"] == {"account_id": ID}
    assert server.requests == []


def test_unbind_with_yes_deletes_the_bound_account_row(cli_run) -> None:
    path = f"/api/v1/social-accounts/accounts/{ID}"
    server = Server({("DELETE", path): None})

    code, result = cli_run(server, "social-account", "+unbind", "--account-id", ID, "--yes")

    assert code == 0, result
    (sent,) = server.requests
    assert (sent.method, sent.url.path, query(sent)) == ("DELETE", path, {})
    assert result["data"] == {"unbound": True, "account_id": ID}


def test_unbind_refuses_a_non_uuid_before_any_request(cli_run) -> None:
    server = Server({})

    code, result = cli_run(server, "social-account", "+unbind", "--account-id", "x", "--yes")

    assert code == cli.EXIT_FAILURE
    assert result["reason"] == "invalid_input"
    assert server.requests == []


# -- schedule approval and failed-publish retry -----------------------------


def test_schedule_approve_posts_an_empty_object(cli_run) -> None:
    path = f"/api/v2/pool-accounts/{ID}/publish-config/schedule-items/{ITEM}/approve"
    server = Server({("POST", path): {"id": ITEM, "status": "scheduled"}})

    code, result = cli_run(
        server,
        "ai-slideshow",
        "publish",
        "+schedule-approve",
        "--account-id",
        ID,
        "--schedule-item-id",
        ITEM,
    )

    assert code == 0, result
    (sent,) = server.requests
    assert sent.url.path == path
    assert sent.content == b"{}"
    assert result["data"]["id"] == ITEM


def test_schedule_approve_keeps_the_sibling_commands_id_flag(cli_run) -> None:
    path = f"/api/v2/pool-accounts/{ID}/publish-config/schedule-items/{ITEM}/approve"
    server = Server({("POST", path): {"id": ITEM}})

    code, _ = cli_run(
        server, "ai-slideshow", "publish", "+schedule-approve", "--id", ID, "--schedule-item-id", ITEM
    )

    assert code == 0
    assert server.requests[0].url.path == path


def test_retry_failed_without_yes_previews_and_sends_nothing(cli_run) -> None:
    server = Server({})

    code, result = cli_run(server, "ai-slideshow", "publish", "+retry-failed", "--task-id", ID)

    assert code == cli.EXIT_FAILURE
    assert result["reason"] == "confirmation_required"
    assert result["preview"]["data"]["would_retry_failed_jobs_of"] == ID
    assert server.requests == []


def test_retry_failed_with_yes_sends_the_duplicate_confirmation_only(cli_run) -> None:
    path = f"/api/v1/pool-accounts/publish/{ID}/retry-failed"
    server = Server({("POST", path): {"redriven": 3}})

    code, result = cli_run(
        server, "ai-slideshow", "publish", "+retry-failed", "--task-id", ID, "--yes"
    )

    assert code == 0, result
    (sent,) = server.requests
    assert sent.url.path == path
    assert body(sent) == {"confirm_no_duplicate": True}
    assert result["data"] == {"redriven": 3}


# -- AI image post review ---------------------------------------------------


@pytest.mark.parametrize(
    ("command", "suffix"),
    [("+approve", "review"), ("+unreview", "unreview"), ("+reject", "reject"), ("+retry", "retry")],
)
def test_review_decisions_post_an_empty_object_to_their_route(
    cli_run, command: str, suffix: str
) -> None:
    path = f"/api/v2/content-reviews/{ID}/{suffix}"
    server = Server({("POST", path): {"generation_id": ID}})

    code, result = cli_run(
        server, "ai-slideshow", "review", command, "--generation-id", ID
    )

    assert code == 0, result
    (sent,) = server.requests
    assert (sent.method, sent.url.path) == ("POST", path)
    assert sent.content == b"{}"


def test_review_adjust_sends_instruction_and_annotations(cli_run) -> None:
    path = f"/api/v2/content-reviews/{ID}/adjust"
    server = Server({("POST", path): {"replacement_generation_id": ITEM}})
    mark = {"slide_media_id": "m1", "slide_index": 2, "x": 10, "y": 20, "comment": "Too small"}

    code, result = cli_run(
        server,
        "ai-slideshow",
        "review",
        "+adjust",
        "--generation-id",
        ID,
        "--instruction",
        " Shorter title ",
        "--annotations-json",
        json.dumps([mark]),
    )

    assert code == 0, result
    assert body(server.requests[0]) == {"instruction": "Shorter title", "annotations": [mark]}


def test_review_adjust_without_feedback_is_refused_before_any_request(cli_run) -> None:
    server = Server({})

    code, result = cli_run(server, "ai-slideshow", "review", "+adjust", "--generation-id", ID)

    assert code == cli.EXIT_FAILURE
    assert result["reason"] == "invalid_input"
    assert server.requests == []


def test_review_decision_dry_run_sends_nothing(cli_run) -> None:
    server = Server({})

    code, _ = cli_run(
        server, "ai-slideshow", "review", "+approve", "--generation-id", ID, "--dry-run"
    )

    assert code == 0
    assert server.requests == []


# -- media collection create ------------------------------------------------


def test_collection_create_posts_only_the_name(cli_run) -> None:
    server = Server({("POST", "/api/v1/collections"): {"id": ID, "name": "Spring"}})

    code, result = cli_run(server, "media", "collection", "+create", "--name", " Spring ")

    assert code == 0, result
    (sent,) = server.requests
    assert body(sent) == {"name": "Spring"}
    assert result["data"]["id"] == ID
