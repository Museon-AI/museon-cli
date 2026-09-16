"""Known regression: a public option is accepted but disappears before HTTP.

Expected requests are independently reviewed API examples in fixtures, never
computed from the production route map/builder. Every declared input must have
an example, and every exposed flag must survive the real parser/dispatch path.
"""

from __future__ import annotations

import argparse
import asyncio
from copy import deepcopy
import json
from pathlib import Path

import httpx
import pytest

from museoncli.config import AuthState, Config, WorkspaceState
from museoncli.domains import command_specs, get_command_spec
import museoncli.main as cli

CASES = json.loads((Path(__file__).parent / "fixtures/ai_hook_requests.json").read_text())
HTTP_CLIENT = httpx.AsyncClient
BASE_WORKSPACE = "40000000-0000-4000-8000-000000000004"


def command(case):
    spec = get_command_spec("hireaicreator." + case["name"])
    return ["hireaicreator", spec.resource, spec.shortcut]


def dispatch(argv):
    return asyncio.run(cli.dispatch(cli.build_parser().parse_args(argv)))


def attach_transport(monkeypatch, handler):
    cfg = Config(
        api_base_url="https://api.example.test/api/v1",
        workspace=WorkspaceState(id=BASE_WORKSPACE),
        auth=AuthState(api_key="test-only"),
    )
    monkeypatch.setattr(cli, "load_config", lambda: cfg)
    real = HTTP_CLIENT
    monkeypatch.setattr(
        cli.httpx,
        "AsyncClient",
        lambda **kwargs: real(**kwargs, transport=httpx.MockTransport(handler)),
    )


def flag_argv(case):
    # This encoding follows the public convention, not the production parser.
    flags, structured = [], {}
    for key, value in case["input"].items():
        option = "--search-term" if key == "search_terms" else "--" + key.replace("_", "-")
        if (
            value is None
            or isinstance(value, dict)
            or (isinstance(value, list) and (not value or isinstance(value[0], dict)))
        ):
            structured[key] = value
        elif type(value) is bool:
            flags += [option if value else "--no-" + option[2:]]
        elif isinstance(value, list):
            for item in value:
                flags += [option, str(item)]
        else:
            flags += [option, str(value)]
    return [*command(case), *flags, "--args-json", json.dumps(structured)]


def request_matches(request, case):
    assert request.method == case["method"]
    assert request.url.path == case["path"]
    assert request.headers["X-Museon-CLI-Command"] == "hireaicreator." + case["name"]
    if "query" in case:
        expected = []
        for key, value in case["query"].items():
            for item in value if isinstance(value, list) else [value]:
                expected.append((key, str(item).lower() if type(item) is bool else str(item)))
        assert sorted(request.url.params.multi_items()) == sorted(expected)
        assert request.content == b""
    else:
        assert not request.url.query
        assert json.loads(request.content) == case["body"]
    for key, value in case.get("header", {}).items():
        assert request.headers[key] == value
    if "header" not in case:
        assert "Idempotency-Key" not in request.headers


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["name"])
@pytest.mark.parametrize("source", ["json", "file", "flags"])
def test_real_argv_reaches_final_http_without_dropping_parameters(
    monkeypatch, tmp_path, case, source
):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"items": [], "sentinel": "actual-api-data"})

    attach_transport(monkeypatch, handler)
    if source == "flags":
        argv = flag_argv(case)
    elif source == "file":
        path = tmp_path / "args.json"
        path.write_text(json.dumps(case["input"]))
        argv = [*command(case), "--args-file", str(path)]
    else:
        argv = [*command(case), "--args-json", json.dumps(case["input"])]
    result = dispatch(argv)
    assert len(requests) == 1
    request_matches(requests[0], case)
    assert result["data"]["sentinel"] == "actual-api-data"
    # Resource-bound APIs must not claim the unrelated selected workspace.
    assert result["workspace"] == (
        {"id": case["input"]["workspace_id"]} if "workspace_id" in case["input"] else None
    )


def schema_paths(schema, prefix=""):
    if "properties" in schema:
        for key, child in schema["properties"].items():
            name = prefix + "/" + key
            yield name
            yield from schema_paths(child, name)
    if "items" in schema:
        yield from schema_paths(schema["items"], prefix + "[]")


def value_paths(value, prefix=""):
    if isinstance(value, dict):
        for key, child in value.items():
            name = prefix + "/" + key
            yield name
            yield from value_paths(child, name)
    if isinstance(value, list):
        for child in value:
            yield from value_paths(child, prefix + "[]")


def test_every_declared_field_and_flag_has_an_independent_request_case():
    specs = {
        spec.schema_name.removeprefix("hireaicreator."): spec
        for spec in command_specs()
        if spec.domain.value == "hireaicreator"
    }
    assert set(specs) == {case["name"] for case in CASES}
    for case in CASES:
        spec = specs[case["name"]]
        assert set(schema_paths(spec.input_schema)) <= set(value_paths(case["input"])), case["name"]
        parser = argparse.ArgumentParser(add_help=False)
        spec.add_arguments(parser)
        declared = {a.dest for a in parser._actions}
        tested = set(vars(parser.parse_args(flag_argv(case)[3:])))
        # Explicit request cases below cover nullable collection IDs via flags.
        if case["name"] == "delivery-share":
            tested.add("collection_id")
        # local consumers have their own tests: mutually exclusive files and dry-run.
        assert declared - {"args_file", "dry_run"} <= tested, (
            case["name"],
            declared - tested,
        )


def test_test_group_list_needs_no_plan_id_or_write(monkeypatch):
    requests = []
    attach_transport(
        monkeypatch,
        lambda request: (
            requests.append(request)
            or httpx.Response(200, json={"items": [], "total": 0, "has_more": False})
        ),
    )

    dispatch(["hireaicreator", "test-group", "+list", "--search", "pilot"])

    assert len(requests) == 1
    assert requests[0].method == "GET"
    assert requests[0].url.path == "/api/v2/ai-hook-test-groups"
    assert dict(requests[0].url.params) == {
        "workspace_id": BASE_WORKSPACE,
        "search": "pilot",
    }


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["name"])
def test_unknown_json_fields_and_source_conflicts_fail_before_http(monkeypatch, tmp_path, case):
    attach_transport(monkeypatch, lambda _: pytest.fail("invalid input reached network"))
    bad = {**case["input"], "invented_parameter": 123}
    with pytest.raises(ValueError, match="unknown"):
        dispatch([*command(case), "--args-json", json.dumps(bad)])
    path = tmp_path / "args.json"
    path.write_text(json.dumps(case["input"]))
    with pytest.raises(ValueError, match="exactly one"):
        dispatch([*command(case), "--args-file", str(path), "--args-json", "{}"])
    candidate = next((key for key, value in case["input"].items() if isinstance(value, str)), None)
    if candidate:
        option = "--" + candidate.replace("_", "-")
        with pytest.raises(ValueError, match="both"):
            dispatch(
                [
                    *command(case),
                    "--args-json",
                    json.dumps(case["input"]),
                    option,
                    case["input"][candidate],
                ]
            )


@pytest.mark.parametrize(
    "case",
    [c for c in CASES if get_command_spec("hireaicreator." + c["name"]).supports_dry_run],
    ids=lambda c: c["name"],
)
def test_write_dry_run_is_local_and_validates_nested_fields(monkeypatch, case):
    attach_transport(monkeypatch, lambda _: pytest.fail("dry run reached network"))
    dispatch([*command(case), "--args-json", json.dumps(case["input"]), "--dry-run"])
    if isinstance(case["input"].get("items"), list):
        bad = deepcopy(case["input"])
        bad["items"][0]["typo_version"] = 4
        with pytest.raises(ValueError, match="unknown"):
            dispatch([*command(case), "--args-json", json.dumps(bad), "--dry-run"])


def test_patch_null_and_omission_remain_distinct(monkeypatch):
    case = next(c for c in CASES if c["name"] == "video-update")
    requests = []
    attach_transport(
        monkeypatch, lambda r: requests.append(r) or httpx.Response(200, json={"id": "result"})
    )
    dispatch(
        [
            *command(case),
            "--id",
            case["input"]["id"],
            "--args-json",
            '{"expected_version":17,"composition_bgm_id":null,"scheduled_at":null}',
        ]
    )
    assert json.loads(requests[0].content) == {
        "expected_version": 17,
        "composition_bgm_id": None,
        "scheduled_at": None,
    }
    assert "caption" not in json.loads(requests[0].content)


def test_partial_failure_and_version_conflict_are_not_hidden_or_retried(monkeypatch):
    case = next(c for c in CASES if c["name"] == "video-bulk-schedule")
    calls = []
    partial = {
        "succeeded": [],
        "conflicted": [case["input"]["items"][0]["video_id"]],
        "failures": [{"code": "blocked"}],
    }
    attach_transport(monkeypatch, lambda r: calls.append(r) or httpx.Response(200, json=partial))
    assert dispatch([*command(case), "--args-json", json.dumps(case["input"])])["data"] == partial
    assert len(calls) == 1
    calls.clear()
    attach_transport(
        monkeypatch,
        lambda r: (
            calls.append(r) or httpx.Response(409, json={"detail": {"code": "version_conflict"}})
        ),
    )
    with pytest.raises(cli.ApiRequestError) as error:
        dispatch([*command(case), "--args-json", json.dumps(case["input"])])
    assert error.value.status_code == 409
    assert len(calls) == 1


@pytest.mark.parametrize("action", ["share"])
def test_nullable_collection_id_explicit_flag_reaches_http(monkeypatch, action):
    requests = []
    attach_transport(monkeypatch, lambda r: requests.append(r) or httpx.Response(200, json={}))
    dispatch(
        [
            "hireaicreator",
            "delivery",
            "+" + action,
            "--collection-kind",
            "test-group",
            "--collection-id",
            BASE_WORKSPACE,
            "--workspace-id",
            BASE_WORKSPACE,
        ]
    )
    assert json.loads(requests[0].content) == {
        "collection_kind": "test_group",
        "collection_id": BASE_WORKSPACE,
        "workspace_id": BASE_WORKSPACE,
    }


def test_integer_zero_is_forwarded_for_server_business_validation(monkeypatch):
    case = deepcopy(next(c for c in CASES if c["name"] == "clip-batch-create"))
    case["input"]["items"][0]["usage_limit"] = 0
    requests = []
    attach_transport(
        monkeypatch,
        lambda r: requests.append(r) or httpx.Response(422, json={"detail": "invalid usage limit"}),
    )
    with pytest.raises(cli.ApiRequestError):
        dispatch([*command(case), "--args-json", json.dumps(case["input"])])
    assert json.loads(requests[0].content)["items"][0]["usage_limit"] == 0


@pytest.mark.parametrize(
    "argv",
    [
        ["hireaicreator", "format", "+list", "--status", "processing"],
        ["hireaicreator", "actor", "+list", "--page-size", "101"],
        [
            "hireaicreator",
            "video",
            "+generate",
            "--args-json",
            json.dumps(
                {"id": BASE_WORKSPACE, "expected_version": 1, "idempotency_key": "bad\nkey"}
            ),
            "--dry-run",
        ],
    ],
)
def test_invalid_contract_values_never_reach_http(monkeypatch, argv):
    attach_transport(monkeypatch, lambda _: pytest.fail("invalid input reached network"))
    with pytest.raises((ValueError, SystemExit)):
        dispatch(argv)


def test_delivery_preview_cannot_claim_explicit_id_snapshot(monkeypatch):
    attach_transport(monkeypatch, lambda _: pytest.fail("unsupported preview reached network"))
    for payload in [
        {"collection_kind": "test-group", "collection_id": BASE_WORKSPACE},
        {"collection_kind": "video-filter", "video_filter": {"video_ids": [BASE_WORKSPACE]}},
    ]:
        with pytest.raises(ValueError):
            dispatch(["hireaicreator", "delivery", "+preview", "--args-json", json.dumps(payload)])
