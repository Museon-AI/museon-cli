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

from museoncli.config import AuthState, Config, OrganizationState
from museoncli.domains import command_specs, get_command_spec
import museoncli.main as cli

CASES = [
    case
    for filename in (
        "ai_hook_requests.json",
        "hireaicreator_test_group_requests.json",
        "hireaicreator_warmup_requests.json",
        "video_ops_requests.json",
        "hireaicreator_format_requests.json",
        "hireaicreator_actor_assignment_requests.json",
    )
    for case in json.loads((Path(__file__).parent / "fixtures" / filename).read_text())
]
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
        organization=OrganizationState(id="org-1", name="MuseOn"),
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
    else:
        assert not request.url.query
    if "body" in case:
        assert json.loads(request.content) == case["body"]
    else:
        assert request.content in (b"", b"{}")
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
    if get_command_spec("hireaicreator." + case["name"]).requires_confirmation:
        argv.append("--yes")
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
        and spec.schema_name != "hireaicreator.video-publish-local"
    }
    # Local upload has a multi-request, resumable workflow, covered separately.
    assert set(specs) == {case["name"] for case in CASES}
    for case in CASES:
        spec = specs[case["name"]]
        covered = set().union(
            *(set(value_paths(other["input"])) for other in CASES if other["name"] == case["name"])
        )
        # organization_id is the X-Organization-Id header, never a request field.
        assert set(schema_paths(spec.input_schema)) - {"/organization_id"} <= covered, case["name"]
        parser = argparse.ArgumentParser(add_help=False)
        spec.add_arguments(parser)
        declared = {a.dest for a in parser._actions}
        tested = set().union(
            *(
                set(vars(parser.parse_args(flag_argv(other)[3:])))
                for other in CASES
                if other["name"] == case["name"]
            )
        )
        # Explicit request cases below cover nullable collection IDs via flags.
        if case["name"] == "delivery-share":
            tested.add("collection_id")
        # local consumers have their own tests: mutually exclusive files and dry-run.
        assert declared - {"args_file", "dry_run", "organization_id"} <= tested, (
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
    assert dict(requests[0].url.params) == {"search": "pilot"}
    assert requests[0].headers["X-Organization-Id"] == "org-1"


@pytest.mark.parametrize("source", ["csv", "repeated", "mixed", "json"])
def test_video_list_multiple_accounts_returns_single_account_union(monkeypatch, source):
    accounts = [f"10000000-0000-4000-8000-{i:012d}" for i in range(1, 4)]
    rows = [
        {
            "id": f"{account}-{i}",
            "publishing_account_id": account,
            "status": "cancelled" if i < 8 else "scheduled",
            "scheduled_at": "2026-11-10T10:30:00+08:00",
        }
        for account in [*accounts, "unselected-account"]
        for i in range(10)
    ]
    requests = []

    def handler(request):
        assert request.method == "GET"
        assert request.url.path == "/api/v2/ai-hook-videos"
        params = request.url.params
        assert "workspace_id" not in params
        assert params["scheduled_from"] == "2026-11-09T10:30:00+08:00"
        # Match the API's repeated-query list contract, without splitting CSV here.
        ids = params.get_list("publishing_account_ids") or [params["publishing_account_id"]]
        selected = [row for row in rows if row["publishing_account_id"] in ids]
        page, size = int(params.get("page", "1")), int(params["page_size"])
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "items": selected[(page - 1) * size : page * size],
                "total": len(selected),
                "page": page,
                "page_size": size,
                "has_more": page * size < len(selected),
            },
        )

    attach_transport(monkeypatch, handler)
    argv = [
        "hireaicreator",
        "video",
        "+list",
        "--scheduled-from",
        "2026-11-09T10:30:00+08:00",
        "--page-size",
        "7",
        "--all",
    ]
    singles = [
        dispatch([*argv, "--publishing-account-id", account])["data"]["items"]
        for account in accounts
    ]
    assert [len(items) for items in singles] == [10, 10, 10]
    expected = {row["id"] for items in singles for row in items}
    if source == "csv":
        flags = ["--publishing-account-ids", ", ".join(accounts)]
    elif source == "repeated":
        flags = [part for account in accounts for part in ("--publishing-account-ids", account)]
    elif source == "mixed":
        flags = [
            "--publishing-account-ids",
            ",".join(accounts[:2]),
            "--publishing-account-ids",
            accounts[2],
        ]
    else:
        flags = ["--args-json", json.dumps({"publishing_account_ids": accounts})]
    requests.clear()
    result = dispatch([*argv, *flags])
    assert {row["id"] for row in result["data"]["items"]} == expected
    assert len(result["data"]["items"]) == 30
    assert result["page_info"]["complete"] is True
    assert len(requests) == 5


def test_video_list_csv_account_limit_is_checked_after_splitting(monkeypatch):
    requests = []
    attach_transport(
        monkeypatch,
        lambda request: requests.append(request) or httpx.Response(200, json={"items": []}),
    )
    accounts = [f"10000000-0000-4000-8000-{i:012d}" for i in range(301)]
    argv = ["hireaicreator", "video", "+list", "--publishing-account-ids"]
    dispatch([*argv, ",".join(accounts[:300])])
    assert len(requests[0].url.params.get_list("publishing_account_ids")) == 300
    with pytest.raises(ValueError, match="publishing_account_ids has an invalid item count"):
        dispatch([*argv, ",".join(accounts)])
    assert len(requests) == 1


@pytest.mark.parametrize("action", ["assets-get", "actor-set", "persona-set"])
@pytest.mark.parametrize("override", [None, "50000000-0000-4000-8000-000000000005"])
def test_account_bindings_resolve_workspace_and_preserve_approval_omission(
    monkeypatch, action, override
):
    requests = []
    attach_transport(monkeypatch, lambda r: requests.append(r) or httpx.Response(200, json={}))
    argv = [
        "hireaicreator",
        "account",
        "+" + action,
        "--id",
        "10000000-0000-4000-8000-000000000001",
    ]
    if action != "assets-get":
        argv += ["--" + action.removesuffix("-set") + "-id", "30000000-0000-4000-8000-000000000003"]
    if override:
        argv += ["--workspace-id", override]
    result = dispatch(argv)
    assert len(requests) == 1
    sent = (
        dict(requests[0].url.params) if action == "assets-get" else json.loads(requests[0].content)
    )
    assert sent.get("workspace_id") == override
    assert "managed_operation_approved" not in sent
    assert "approval_note" not in sent
    assert result["workspace"] == ({"id": override} if override else None)
    assert result["organization"] == {"id": "org-1", "name": "MuseOn"}


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
    case = deepcopy(next(c for c in CASES if c["name"] == "clip-bulk-create"))
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
        *(
            [
                "hireaicreator",
                "video",
                action,
                "--args-json",
                json.dumps({"idempotency_key": "upload-without-campaign", "items": [item]}),
            ]
            for action, item in [
                (
                    "+create-from-upload",
                    {
                        "media_id": BASE_WORKSPACE,
                        "publishing_account_ids": ["account"],
                        "caption": "Finished",
                    },
                ),
                (
                    "+publish-local",
                    {
                        "file": "finished.mp4",
                        "account_ids": [BASE_WORKSPACE],
                        "caption": "Finished",
                    },
                ),
            ]
        ),
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


@pytest.mark.parametrize(
    "field,value",
    [
        ("publishing_account_id", BASE_WORKSPACE),
        ("scheduled_at", "2030-01-01T00:00:00Z"),
        ("composition_source", "clips"),
    ],
)
def test_manual_video_create_rejects_account_and_schedule_before_http(monkeypatch, field, value):
    case = next(c for c in CASES if c["name"] == "video-create")
    payload = {**case["input"], field: value}
    attach_transport(monkeypatch, lambda request: pytest.fail("invalid write reached HTTP"))
    with pytest.raises(ValueError):
        dispatch([*command(case), "--args-json", json.dumps(payload)])


def test_manual_video_create_requires_source_and_dry_run_never_writes(monkeypatch):
    case = next(c for c in CASES if c["name"] == "video-create")
    payload = dict(case["input"])
    attach_transport(monkeypatch, lambda request: pytest.fail("dry run reached HTTP"))
    result = dispatch([*command(case), "--args-json", json.dumps(payload), "--dry-run"])
    assert result["data"]["dry_run"] is True
    payload.pop("format_id")
    payload.pop("reference_hook_id")
    with pytest.raises(ValueError, match="requires format_id or reference_hook_id"):
        dispatch([*command(case), "--args-json", json.dumps(payload)])


@pytest.mark.parametrize(
    "video_model",
    ["auto", "compshare-h3", "kling-3-standard", "minimax-h3-max", "minimax-h3-max-turbo"],
)
def test_plan_generation_model_ids_retain_provider_spelling(monkeypatch, tmp_path, video_model):
    case = deepcopy(next(case for case in CASES if case["name"] == "plan-create"))
    for direction in ("input", "body"):
        case[direction]["generation_options"]["video_model"] = video_model
        case[direction]["generation_options"]["image_model"] = "gpt-image-2.5-sunburst"
    requests = []
    attach_transport(
        monkeypatch,
        lambda request: requests.append(request) or httpx.Response(200, json={"ok": True}),
    )
    path = tmp_path / "generation.json"
    path.write_text(json.dumps(case["input"]))
    dispatch([*command(case), "--args-file", str(path)])
    assert len(requests) == 1
    request_matches(requests[0], case)


def test_create_from_upload_warns_when_videos_stay_unscheduled(monkeypatch):
    # A null scheduled_at is "not scheduled", not "publish now"; callers must be told.
    def handler(request):
        return httpx.Response(
            201,
            json={
                "items": [
                    {"id": "video-later", "status": "approved", "scheduled_at": None},
                    {
                        "id": "video-timed",
                        "status": "scheduled",
                        "scheduled_at": "2026-10-29T01:00:00Z",
                    },
                ]
            },
        )

    attach_transport(monkeypatch, handler)
    item = {"media_id": BASE_WORKSPACE, "publishing_account_ids": ["account"], "caption": "Done"}
    result = dispatch(
        [
            "hireaicreator",
            "video",
            "+create-from-upload",
            "--args-json",
            json.dumps(
                {
                    "campaign_id": BASE_WORKSPACE,
                    "idempotency_key": "upload-unscheduled",
                    "items": [item],
                }
            ),
        ]
    )
    assert any("will not publish: video-later" in warning for warning in result["warnings"])
    assert any("+bulk-schedule" in step for step in result["next_steps"])
