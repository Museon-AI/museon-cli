"""A stub Museon API behind the real HTTP layer: answers by (method, path), records every request."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any
from urllib.parse import parse_qsl

import httpx
import pytest

import museoncli.main as cli
from museoncli.config import AuthState, Config, OrganizationState

ORG = "70000000-0000-4000-8000-000000000001"
API = "https://api.example.test"
_CLIENT = httpx.AsyncClient


class Server:
    def __init__(self, routes: dict[tuple[str, str], Any]) -> None:
        self.routes = routes
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        key = (request.method, request.url.path)
        if key not in self.routes:
            return httpx.Response(404, json={"detail": f"no stub for {request.method} {request.url.path}"})
        answer = self.routes[key]
        if callable(answer):
            answer = answer(request)
        if answer is None:
            return httpx.Response(204)
        return httpx.Response(200, json=answer)

    def calls(self) -> list[tuple[str, str]]:
        return [(request.method, request.url.path) for request in self.requests]

    def writes(self) -> list[httpx.Request]:
        return [request for request in self.requests if request.method != "GET"]


def body(request: httpx.Request) -> Any:
    return json.loads(request.content) if request.content else None


def query(request: httpx.Request) -> dict[str, str]:
    return dict(parse_qsl(request.url.query.decode()))


def run(monkeypatch: pytest.MonkeyPatch, server: Callable[[httpx.Request], httpx.Response], argv: list[str]) -> dict:
    cfg = Config(
        api_base_url=f"{API}/api/v1",
        auth=AuthState(api_key="test-only"),
        organization=OrganizationState(id=ORG, name="MuseOn"),
    )
    monkeypatch.setattr(cli, "load_config", lambda: cfg)
    monkeypatch.setattr(
        cli.httpx,
        "AsyncClient",
        lambda **kwargs: _CLIENT(**kwargs, transport=httpx.MockTransport(server)),
    )
    return asyncio.run(cli.dispatch(cli.build_parser().parse_args(argv)))


def refused(
    monkeypatch: pytest.MonkeyPatch, server: Callable[[httpx.Request], httpx.Response], argv: list[str]
) -> dict:
    """Run a command that needs --yes without it: it fails and returns its dry run as preview."""
    with pytest.raises(cli.ConfirmationRequired) as refusal:
        run(monkeypatch, server, argv)
    payload, code = cli.error_envelope(refusal.value, command=None)
    assert code == cli.EXIT_FAILURE
    assert payload["ok"] is False and payload["reason"] == "confirmation_required"
    return payload["preview"]


def assert_organization_only(server: Server) -> None:
    """Every request addresses the selected organization and names no workspace."""
    for request in server.requests:
        assert request.headers.get("X-Organization-Id") == ORG
        assert not any("workspace" in name.lower() for name in request.headers)
        assert b"workspace" not in (request.content or b"")
