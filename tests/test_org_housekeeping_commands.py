"""Artifacts list/get, media collections, social account tags and product CTA targets.

Each command goes through the real dispatch and HTTP layer against a mock transport, so the
assertions see exactly what the server would: method, path, query, body and the
X-Organization-Id header, with no workspace anywhere.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
import pytest

import museoncli.main as cli
from museoncli.config import AuthState, Config, OrganizationState

ORG = "70000000-0000-4000-8000-000000000001"
OTHER_ORG = "70000000-0000-4000-8000-000000000002"
ARTIFACT = "11111111-1111-4111-8111-111111111111"
COLLECTION = "22222222-2222-4222-8222-222222222222"
MEDIA_A = "33333333-3333-4333-8333-333333333331"
MEDIA_B = "33333333-3333-4333-8333-333333333332"
ACCOUNT = "44444444-4444-4444-8444-444444444444"
PRODUCT = "55555555-5555-4555-8555-555555555555"
TARGET = "66666666-6666-4666-8666-666666666666"
HTTP_CLIENT = httpx.AsyncClient


class Server:
    """Answers each request from a route table and records what was sent."""

    def __init__(self, routes: dict[tuple[str, str], Any]) -> None:
        self.routes = routes
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        answer = self.routes.get((request.method, request.url.path))
        if answer is None:
            return httpx.Response(404, json={"detail": "Not found"})
        if isinstance(answer, httpx.Response):
            return answer
        if callable(answer):
            return answer(request)
        return httpx.Response(200, json=answer)

    def sent(self) -> list[tuple[str, str]]:
        return [(request.method, request.url.path) for request in self.requests]


def run(monkeypatch: pytest.MonkeyPatch, server: Server, argv: list[str]) -> dict[str, Any]:
    cfg = Config(
        api_base_url="https://api.example.test/api/v1",
        auth=AuthState(api_key="test-only"),
        organization=OrganizationState(id=ORG, name="MuseOn"),
    )
    monkeypatch.setattr(cli, "load_config", lambda: cfg)
    monkeypatch.setattr(
        cli.httpx,
        "AsyncClient",
        lambda **kwargs: HTTP_CLIENT(**kwargs, transport=httpx.MockTransport(server)),
    )
    return asyncio.run(cli.dispatch(cli.build_parser().parse_args(argv)))


def assert_organization_only(server: Server, organization: str = ORG) -> None:
    for request in server.requests:
        assert request.headers["X-Organization-Id"] == organization
        assert "workspace" not in request.url.query.decode()
        assert b"workspace" not in request.content


def body(request: httpx.Request) -> Any:
    return json.loads(request.content)


# -- artifacts ---------------------------------------------------------------


def test_artifact_list_reads_the_organization_route_and_reports_paging(monkeypatch):
    server = Server(
        {
            ("GET", f"/api/v1/agent-artifacts/organizations/{ORG}"): {
                "items": [{"id": ARTIFACT, "title": "Weekly report"}],
                "total": 41,
            }
        }
    )
    result = run(
        monkeypatch,
        server,
        ["artifacts", "+list", "--page", "2", "--page-size", "20", "--search", "weekly"],
    )

    (request,) = server.requests
    assert dict(request.url.params) == {"page": "2", "limit": "20", "search": "weekly"}
    assert result["data"]["items"][0]["id"] == ARTIFACT
    assert result["page_info"]["has_more"] is True
    assert result["organization"]["id"] == ORG
    assert_organization_only(server)


def test_artifact_list_addresses_another_organization_for_one_call(monkeypatch):
    server = Server(
        {("GET", f"/api/v1/agent-artifacts/organizations/{OTHER_ORG}"): {"items": [], "total": 0}}
    )
    run(monkeypatch, server, ["artifacts", "+list", "--organization-id", OTHER_ORG])

    assert server.sent() == [("GET", f"/api/v1/agent-artifacts/organizations/{OTHER_ORG}")]
    assert_organization_only(server, OTHER_ORG)


def test_artifact_get_reads_by_id_without_a_workspace(monkeypatch):
    server = Server(
        {("GET", f"/api/v1/agent-artifacts/{ARTIFACT}"): {"id": ARTIFACT, "markdown": "# Hi"}}
    )
    result = run(monkeypatch, server, ["artifacts", "+get", "--id", ARTIFACT])

    assert result["data"]["markdown"] == "# Hi"
    assert dict(server.requests[0].url.params) == {}
    assert_organization_only(server)


# -- media collections -------------------------------------------------------


def test_collection_list_pages_with_limit_on_the_organization_route(monkeypatch):
    server = Server(
        {
            ("GET", f"/api/v1/collections/organizations/{ORG}"): {
                "data": [{"id": COLLECTION, "name": "Launch"}],
                "pagination": {"page": 1, "limit": 50, "total": 1, "total_pages": 1},
            }
        }
    )
    result = run(monkeypatch, server, ["media", "collection", "+list", "--page-size", "50"])

    assert dict(server.requests[0].url.params) == {"page": "1", "limit": "50"}
    assert result["page_info"]["has_more"] is False
    assert_organization_only(server)


def test_collection_reads_go_to_the_collection(monkeypatch):
    server = Server(
        {
            ("GET", f"/api/v1/collections/{COLLECTION}"): {"id": COLLECTION, "media_count": 2},
            ("GET", f"/api/v1/collections/{COLLECTION}/media"): {
                "data": [],
                "pagination": {"page": 1, "limit": 20, "total": 0, "total_pages": 0},
            },
        }
    )
    run(monkeypatch, server, ["media", "collection", "+get", "--id", COLLECTION])
    run(monkeypatch, server, ["media", "collection", "+list-media", "--id", COLLECTION])

    assert server.sent() == [
        ("GET", f"/api/v1/collections/{COLLECTION}"),
        ("GET", f"/api/v1/collections/{COLLECTION}/media"),
    ]
    assert dict(server.requests[1].url.params) == {"page": "1", "limit": "20"}
    assert_organization_only(server)


def test_collection_rename_sends_only_the_name(monkeypatch):
    server = Server(
        {("PUT", f"/api/v1/collections/{COLLECTION}"): {"id": COLLECTION, "name": "Spring"}}
    )
    run(
        monkeypatch,
        server,
        ["media", "collection", "+update", "--id", COLLECTION, "--name", "  Spring "],
    )

    assert body(server.requests[0]) == {"name": "Spring"}
    assert_organization_only(server)


def test_collection_add_sends_distinct_media_ids_to_the_bulk_route(monkeypatch):
    server = Server(
        {
            ("POST", f"/api/v1/collections/{COLLECTION}/media/bulk"): {
                "added": 1,
                "skipped": 1,
                "message": "Added 1 media items",
            }
        }
    )
    result = run(
        monkeypatch,
        server,
        [
            "media",
            "collection",
            "+add",
            "--id",
            COLLECTION,
            "--media-id",
            MEDIA_A,
            "--media-id",
            MEDIA_B,
            "--media-id",
            MEDIA_A,
        ],
    )

    assert body(server.requests[0]) == {"media_ids": [MEDIA_A, MEDIA_B]}
    assert result["data"]["added"] == 1
    assert_organization_only(server)


def test_collection_add_dry_run_sends_nothing(monkeypatch):
    server = Server({})
    result = run(
        monkeypatch,
        server,
        ["media", "collection", "+add", "--id", COLLECTION, "--media-id", MEDIA_A, "--dry-run"],
    )

    assert server.requests == []
    assert result["data"]["dry_run"] is True


def test_collection_delete_needs_yes(monkeypatch):
    server = Server(
        {("GET", f"/api/v1/collections/{COLLECTION}"): {"id": COLLECTION, "media_count": 7}}
    )
    with pytest.raises(cli.ConfirmationRequired) as refused:
        run(monkeypatch, server, ["media", "collection", "+delete", "--id", COLLECTION])
    # Without --yes it answers with its dry run as the preview and deletes nothing.
    assert server.sent() == [("GET", f"/api/v1/collections/{COLLECTION}")]
    assert refused.value.preview["data"]["would_delete"]["media_count"] == 7


def test_collection_delete_dry_run_reads_the_collection_and_deletes_nothing(monkeypatch):
    server = Server(
        {("GET", f"/api/v1/collections/{COLLECTION}"): {"id": COLLECTION, "media_count": 7}}
    )
    result = run(
        monkeypatch, server, ["media", "collection", "+delete", "--id", COLLECTION, "--dry-run"]
    )

    assert server.sent() == [("GET", f"/api/v1/collections/{COLLECTION}")]
    assert result["data"] == {"dry_run": True, "would_delete": {"id": COLLECTION, "media_count": 7}}


def test_collection_delete_with_yes_deletes(monkeypatch):
    server = Server(
        {
            ("GET", f"/api/v1/collections/{COLLECTION}"): {"id": COLLECTION},
            ("DELETE", f"/api/v1/collections/{COLLECTION}"): httpx.Response(204),
        }
    )
    result = run(
        monkeypatch, server, ["media", "collection", "+delete", "--id", COLLECTION, "--yes"]
    )

    assert server.sent()[-1] == ("DELETE", f"/api/v1/collections/{COLLECTION}")
    assert result["data"]["deleted"] is True
    assert_organization_only(server)


def test_collection_remove_needs_yes_and_reports_each_media(monkeypatch):
    server = Server(
        {
            ("GET", f"/api/v1/collections/{COLLECTION}"): {"id": COLLECTION},
            ("DELETE", f"/api/v1/collections/{COLLECTION}/media/{MEDIA_A}"): httpx.Response(204),
            ("DELETE", f"/api/v1/collections/{COLLECTION}/media/{MEDIA_B}"): httpx.Response(
                404, json={"detail": "Media not found in collection"}
            ),
        }
    )
    argv = [
        "media",
        "collection",
        "+remove",
        "--id",
        COLLECTION,
        "--media-id",
        MEDIA_A,
        "--media-id",
        MEDIA_B,
    ]
    with pytest.raises(RuntimeError, match="confirmation_required"):
        run(monkeypatch, server, argv)
    assert [method for method, _ in server.sent()] == ["GET"]

    result = run(monkeypatch, server, [*argv, "--yes"])

    assert result["data"]["removed"] == [MEDIA_A]
    assert [item["media_id"] for item in result["data"]["failed"]] == [MEDIA_B]
    assert result["data"]["failed"][0]["http_status"] == 404
    assert any("not removed" in warning for warning in result["warnings"])
    assert_organization_only(server)


# -- social account tags -----------------------------------------------------


def _account(tags: list[str] | None) -> dict[str, Any]:
    result: dict[str, Any] = {"id": ACCOUNT}
    if tags is not None:
        result["tags"] = tags
    return {"success": True, "data": {"domain": "social-account", "result": result}}


def _tags_put(request: httpx.Request) -> httpx.Response:
    tags = body(request)["tags"]
    return httpx.Response(
        200,
        json={"success": True, "data": {"result": {"account_id": ACCOUNT, "tags": tags}}},
    )


def _tag_server(tags: list[str] | None) -> Server:
    return Server(
        {
            ("GET", f"/api/v1/agent-cli/social-accounts/{ACCOUNT}"): _account(tags),
            ("PUT", f"/api/v1/agent-cli/social-accounts/{ACCOUNT}/workspace-tags"): _tags_put,
        }
    )


def test_tag_add_keeps_existing_tags_and_writes_the_full_set(monkeypatch):
    server = _tag_server(["us", "beauty"])
    result = run(
        monkeypatch,
        server,
        ["social-account", "tag", "+add", "--id", ACCOUNT, "--tag", "warmup", "--tag", "us"],
    )

    assert body(server.requests[-1]) == {"tags": ["us", "beauty", "warmup"]}
    assert result["data"]["before"] == ["us", "beauty"]
    assert result["data"]["after"] == ["us", "beauty", "warmup"]
    assert_organization_only(server)


def test_tag_remove_drops_only_the_named_tags(monkeypatch):
    server = _tag_server(["us", "beauty", "warmup"])
    run(monkeypatch, server, ["social-account", "tag", "+remove", "--id", ACCOUNT, "--tag", "us"])

    assert body(server.requests[-1]) == {"tags": ["beauty", "warmup"]}


def test_tag_set_replaces_and_clear_empties(monkeypatch):
    server = _tag_server(["us"])
    run(
        monkeypatch,
        server,
        ["social-account", "tag", "+set", "--id", ACCOUNT, "--tag", "a", "--tag", "b"],
    )
    run(monkeypatch, server, ["social-account", "tag", "+set", "--id", ACCOUNT, "--clear"])

    puts = [body(request) for request in server.requests if request.method == "PUT"]
    assert puts == [{"tags": ["a", "b"]}, {"tags": []}]


def test_tag_dry_run_reads_and_shows_the_change_without_writing(monkeypatch):
    server = _tag_server(["us"])
    result = run(
        monkeypatch,
        server,
        ["social-account", "tag", "+add", "--id", ACCOUNT, "--tag", "eu", "--dry-run"],
    )

    assert server.sent() == [("GET", f"/api/v1/agent-cli/social-accounts/{ACCOUNT}")]
    assert result["data"]["dry_run"] is True
    assert result["data"]["after"] == ["us", "eu"]


def test_tag_change_that_changes_nothing_writes_nothing(monkeypatch):
    server = _tag_server(["us"])
    result = run(
        monkeypatch, server, ["social-account", "tag", "+add", "--id", ACCOUNT, "--tag", "us"]
    )

    assert [request.method for request in server.requests] == ["GET"]
    assert result["data"]["changed"] is False


def test_tag_add_refuses_when_the_read_carries_no_tags(monkeypatch):
    server = _tag_server(None)
    with pytest.raises(RuntimeError, match="no tags"):
        run(
            monkeypatch,
            server,
            ["social-account", "tag", "+add", "--id", ACCOUNT, "--tag", "x"],
        )
    assert [request.method for request in server.requests] == ["GET"]


def test_tag_set_needs_tags_or_clear():
    parser = cli.build_parser()
    from museoncli.domains import get_command_spec

    spec = get_command_spec("social-account.tag-set")
    with pytest.raises(ValueError, match="--clear"):
        spec.build_arguments(parser.parse_args(["social-account", "tag", "+set", "--id", ACCOUNT]))
    with pytest.raises(ValueError, match="not both"):
        spec.build_arguments(
            parser.parse_args(
                ["social-account", "tag", "+set", "--id", ACCOUNT, "--clear", "--tag", "a"]
            )
        )


# -- product CTA targets -----------------------------------------------------


def test_cta_target_list_and_create_follow_the_product_routes(monkeypatch):
    server = Server(
        {
            ("GET", f"/api/v1/products/{PRODUCT}/cta-targets"): [{"id": TARGET}],
            ("POST", f"/api/v1/products/{PRODUCT}/cta-targets"): {"id": TARGET},
        }
    )
    run(monkeypatch, server, ["ai-slideshow", "cta-target", "+list", "--product-id", PRODUCT])
    result = run(
        monkeypatch,
        server,
        [
            "ai-slideshow",
            "cta-target",
            "+create",
            "--product-id",
            PRODUCT,
            "--title",
            "Try it free",
            "--content-markdown",
            "Go to example.com",
            "--media-id",
            MEDIA_A,
            "--media-id",
            MEDIA_B,
        ],
    )

    assert body(server.requests[1]) == {
        "title": "Try it free",
        "content_markdown": "Go to example.com",
        "assets": [{"media_id": MEDIA_A, "sort_order": 0}, {"media_id": MEDIA_B, "sort_order": 1}],
    }
    assert any("idempotency" in warning for warning in result["warnings"])
    assert_organization_only(server)


def test_cta_target_update_patches_only_given_fields(monkeypatch):
    server = Server({("PATCH", f"/api/v1/products/{PRODUCT}/cta-targets/{TARGET}"): {"id": TARGET}})
    run(
        monkeypatch,
        server,
        [
            "ai-slideshow",
            "cta-target",
            "+update",
            "--product-id",
            PRODUCT,
            "--id",
            TARGET,
            "--status",
            "active",
            "--sort-order",
            "2",
        ],
    )

    assert body(server.requests[0]) == {"sort_order": 2, "status": "active"}
    assert_organization_only(server)


def test_cta_target_retire_needs_yes(monkeypatch):
    server = Server(
        {("POST", f"/api/v1/products/{PRODUCT}/cta-targets/{TARGET}:retire"): {"id": TARGET}}
    )
    argv = ["ai-slideshow", "cta-target", "+retire", "--product-id", PRODUCT, "--id", TARGET]
    with pytest.raises(RuntimeError, match="confirmation_required"):
        run(monkeypatch, server, argv)
    assert server.requests == []

    run(monkeypatch, server, [*argv, "--yes"])

    assert server.sent() == [("POST", f"/api/v1/products/{PRODUCT}/cta-targets/{TARGET}:retire")]
    assert_organization_only(server)


def test_structured_input_and_flags_cannot_both_name_one_field():
    from museoncli.domains import get_command_spec

    args = cli.build_parser().parse_args(
        [
            "media",
            "collection",
            "+update",
            "--id",
            COLLECTION,
            "--name",
            "A",
            "--args-json",
            json.dumps({"name": "B"}),
        ]
    )
    with pytest.raises(ValueError, match="both"):
        get_command_spec("media.collection-update").build_arguments(args)
