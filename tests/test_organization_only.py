"""museoncli 1.0 addresses organizations only.

Outside agentic-campaign and hireaicreator (which keep their 0.25 workspace
handling, see museoncli/domains/_legacy_workspace.py) no command declares a
workspace input, accepts --workspace-id, or sends a workspace to the server.
The request sweep drives every such executor through the real HTTP layer, so a
new command or a refactor that starts sending workspace_id fails here.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl

import httpx
import pytest

import museoncli.main as cli
from museoncli.config import AuthState, Config, OrganizationState
from museoncli.domains import command_executor, command_specs
from museoncli.domains._legacy_workspace import keeps_workspace
from museoncli.execution import CommandContext

ORG = "70000000-0000-4000-8000-000000000001"
OTHER_ORG = "70000000-0000-4000-8000-000000000002"
WORKSPACE = "70000000-0000-4000-8000-000000000009"
UUID = "11111111-1111-4111-8111-111111111111"
API_HOST = "api.example.test"

ORGANIZATION_ONLY = [spec for spec in command_specs() if not keeps_workspace(spec.domain)]

# Inputs the schema alone cannot express (internal asset types, JSON strings, a
# built upload session); everything else is synthesized from the input schema.
_TRIGGER = '{"schema_version":1,"kind":"recurring","timezone":"UTC","cron":"0 9 * * *"}'
_OVERRIDES: dict[str, dict[str, Any]] = {
    **{
        f"ai-slideshow.asset-{action}": {"type": "persona"}
        for action in ("list", "get", "create", "update", "delete")
    },
    **{
        f"routines.{name}": {"trigger_config_json": _TRIGGER}
        for name in ("create-ad-hoc", "create-draft", "rebuild-ad-hoc")
    },
    "ugc.brief-upload-media": {
        "content_type": "video/mp4",
        "size_bytes": 1,
        "filename": "clip.mp4",
    },
}


def _property_names(schema: Any) -> set[str]:
    names: set[str] = set()
    if isinstance(schema, dict):
        properties = schema.get("properties")
        if isinstance(properties, dict):
            names.update(properties)
        for value in schema.values():
            names |= _property_names(value)
    elif isinstance(schema, list):
        for value in schema:
            names |= _property_names(value)
    return names


def _flags(spec: Any) -> set[str]:
    parser = argparse.ArgumentParser(add_help=False)
    spec.add_arguments(parser)
    return {option for action in parser._actions for option in action.option_strings}


@pytest.mark.parametrize("spec", ORGANIZATION_ONLY, ids=lambda spec: spec.schema_name)
def test_no_command_outside_the_two_groups_declares_a_workspace(spec: Any) -> None:
    assert "--workspace-id" not in _flags(spec)
    assert "workspace_id" not in _property_names(spec.input_schema)
    assert "workspace" not in (spec.output_schema.get("properties") or {})


def _synthesize(schema: Any, key: str, files: Path) -> Any:
    if not isinstance(schema, dict):
        return "x"
    if "enum" in schema:
        return next(value for value in schema["enum"] if value is not None)
    kind = schema.get("type")
    if isinstance(kind, list):
        kind = next((value for value in kind if value != "null"), None)
    if kind is None and schema.get("oneOf"):
        return _synthesize(schema["oneOf"][0], key, files)
    if kind == "string":
        fmt = schema.get("format")
        if fmt == "uuid":
            return UUID
        if fmt == "date":
            return "2026-10-01"
        if fmt == "date-time":
            return "2026-10-01T09:00:00+00:00"
        if key == "file" or key.endswith("_file"):
            return str(files / "clip.mp4")
        if key == "output":
            return str(files / f"output-{len(list(files.iterdir()))}")
        if key == "timezone":
            return "UTC"
        return "x" * max(schema.get("minLength", 1), 1)
    if kind == "integer":
        return max(schema.get("minimum", 1), 1)
    if kind == "number":
        return float(max(schema.get("minimum", 1), 1))
    if kind == "boolean":
        return False
    if kind == "array":
        count = max(schema.get("minItems", 1), 1)
        return [_synthesize(schema.get("items", {}), key, files) for _ in range(count)]
    if kind == "object":
        required = set(schema.get("required") or [])
        return {
            name: _synthesize(value, name, files)
            for name, value in (schema.get("properties") or {}).items()
            if name in required
        }
    return "x"


def _arguments(spec: Any, files: Path, *, every_input: bool) -> dict[str, Any]:
    schema = spec.input_schema
    properties = schema.get("properties") or {}
    required = set(schema.get("required") or [])
    if schema.get("oneOf"):
        required |= set(schema["oneOf"][0].get("required") or [])
    arguments = {
        name: _synthesize(value, name, files)
        for name, value in properties.items()
        if name != "organization_id" and (every_input or name in required)
    }
    return {**arguments, **_OVERRIDES.get(spec.schema_name, {})}


def _workspace_fields(request: httpx.Request) -> list[str]:
    found = [
        f"query {key}" for key, _ in parse_qsl(request.url.query.decode()) if "workspace" in key
    ]
    found += [f"header {name}" for name in request.headers if "workspace" in name.lower()]
    if b"workspace_id" in request.content:
        found.append("body workspace_id")
    return found


def test_no_request_outside_the_two_groups_carries_a_workspace(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "clip.mp4").write_bytes(b"x")
    # Publishing commands keep idempotency receipts in the cache; keep them out of $HOME.
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"success": True, "data": {}})

    client = httpx.AsyncClient
    monkeypatch.setattr(
        cli.httpx, "AsyncClient", lambda **kw: client(**kw, transport=httpx.MockTransport(handle))
    )
    cfg = Config(
        api_base_url=f"https://{API_HOST}/api/v1",
        auth=AuthState(api_key="test-only"),
        organization=OrganizationState(id=ORG, name="MuseOn"),
    )
    silent: list[str] = []
    leaks: dict[str, list[str]] = {}
    for spec in ORGANIZATION_ONLY:
        if spec.transport != "agent_cli_api":
            continue
        sent = len(requests)
        for every_input in (True, False):
            ctx = CommandContext(
                cfg=cfg,
                spec=spec,
                args=None,
                arguments=_arguments(spec, tmp_path, every_input=every_input),
                organization_id=ORG,
                api_data=cli.api_data,
                api_data_v2=cli.api_data_v2,
                upload_media_file=cli.upload_media_file,
                upload_artifact_file=cli.upload_artifact_file,
                download_api_file=cli.download_api_file,
            )
            try:
                asyncio.run(asyncio.wait_for(command_executor(spec.schema_name)(ctx), 5))
            except Exception:  # noqa: BLE001 - the canned answer fails many readers; only requests matter
                pass
            if len(requests) > sent:
                break
        else:
            silent.append(spec.schema_name)
        for request in requests[sent:]:
            if request.url.host != API_HOST:
                continue
            assert request.headers.get("X-Organization-Id") == ORG, spec.schema_name
            if fields := _workspace_fields(request):
                leaks[spec.schema_name] = fields

    assert leaks == {}
    # A command the sweep cannot reach is a command this guard does not check.
    assert silent == []


def _main(monkeypatch: pytest.MonkeyPatch, argv: list[str]) -> int:
    cfg = Config(auth=AuthState(api_key="test-only"), organization=OrganizationState(id=ORG))
    monkeypatch.setattr(cli, "load_config", lambda: cfg)
    monkeypatch.setattr(sys, "argv", ["museoncli", *argv])
    with pytest.raises(SystemExit) as exited:
        cli.main()
    return int(exited.value.code)


@pytest.mark.parametrize(
    "argv",
    [
        ["routines", "+list", "--workspace-id", WORKSPACE],
        ["ugc", "campaign", "+list", "--workspace-id", WORKSPACE],
        ["campaign-monitor", "payment", "+list", "--workspace-id", WORKSPACE],
        ["media", "+get", "--id", UUID, "--workspace-id", WORKSPACE],
    ],
)
def test_workspace_id_flag_is_an_unknown_argument(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], argv: list[str]
) -> None:
    code = _main(monkeypatch, argv)

    payload = json.loads(capsys.readouterr().out)
    assert code == cli.EXIT_USAGE
    assert payload["reason"] == "usage_error"
    assert "--workspace-id" in payload["error"]["message"]


def test_workspace_id_in_structured_input_is_refused(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    code = _main(
        monkeypatch,
        [
            "social-account",
            "+connect-adb",
            "--handle",
            "creator",
            "--platform",
            "tiktok",
            "--args-json",
            json.dumps({"workspace_id": WORKSPACE}),
            "--dry-run",
        ],
    )

    payload = json.loads(capsys.readouterr().out)
    assert code == cli.EXIT_FAILURE
    assert payload["reason"] == "invalid_input"
    assert "workspace_id is not an input" in payload["error"]["message"]


def _recording_api(calls: list[dict[str, Any]]) -> Any:
    async def api(cfg: Config, method: str, path: str, **kwargs: Any) -> Any:
        calls.append({"method": method, "path": path, **kwargs})
        return {"items": [], "total": 0}

    return api


def test_hireaicreator_keeps_its_workspace_flag_and_envelope_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(cli, "load_config", lambda: Config(organization=OrganizationState(id=ORG)))
    monkeypatch.setattr(cli, "api_data_v2", _recording_api(calls))
    args = cli.build_parser().parse_args(
        ["hireaicreator", "account", "+list", "--workspace-id", WORKSPACE]
    )

    result = asyncio.run(cli.dispatch(args))

    assert calls[0]["params"]["workspace_id"] == WORKSPACE
    assert list(result)[:3] == ["command", "workspace", "organization"]
    assert result["workspace"] == {"id": WORKSPACE}
    assert cli.deprecation_notices(args) == [
        "--workspace-id is deprecated; commands act in the selected organization "
        "(`museoncli org select`) or --organization-id."
    ]


def test_hireaicreator_without_a_workspace_sends_none(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(cli, "load_config", lambda: Config(organization=OrganizationState(id=ORG)))
    monkeypatch.setattr(cli, "api_data_v2", _recording_api(calls))

    result = asyncio.run(
        cli.dispatch(cli.build_parser().parse_args(["hireaicreator", "account", "+list"]))
    )

    assert "workspace_id" not in calls[0]["params"]
    assert result["workspace"] is None
    assert result["organization"] == {"id": ORG, "name": None}


def test_organization_id_addresses_another_organization_for_one_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"success": True, "data": {"items": []}})

    client = httpx.AsyncClient
    monkeypatch.setattr(
        cli.httpx, "AsyncClient", lambda **kw: client(**kw, transport=httpx.MockTransport(handle))
    )
    monkeypatch.setattr(
        cli,
        "load_config",
        lambda: Config(
            api_base_url=f"https://{API_HOST}/api/v1",
            auth=AuthState(api_key="test-only"),
            organization=OrganizationState(id=ORG, name="MuseOn"),
        ),
    )

    result = asyncio.run(
        cli.dispatch(
            cli.build_parser().parse_args(["routines", "+list", "--organization-id", OTHER_ORG])
        )
    )

    (request,) = requests
    assert request.headers["X-Organization-Id"] == OTHER_ORG
    assert _workspace_fields(request) == []
    assert result["organization"] == {"id": OTHER_ORG, "name": None}
    assert "workspace" not in result
