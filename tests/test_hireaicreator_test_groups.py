"""Operational boundaries not captured by the independent HTTP request fixtures."""

import json
from pathlib import Path

import httpx
import pytest

from test_ai_hook_parameter_contract import attach_transport, dispatch
from museoncli.domains.hireaicreator_test_groups import specs
import museoncli.main as cli

CASES = json.loads(
    (Path(__file__).parent / "fixtures/hireaicreator_test_group_requests.json").read_text()
)


def argv(name, **overrides):
    case = next(c for c in CASES if c["name"] == name)
    spec = next(s for s in specs() if s.schema_name == "hireaicreator." + name)
    return [
        "hireaicreator",
        spec.resource,
        spec.shortcut,
        "--args-json",
        json.dumps({**case["input"], **overrides}),
    ]


@pytest.mark.parametrize(
    "name", ["test-run-confirm", "test-group-accounts-transfer", "test-group-delete"]
)
def test_publication_transfer_and_deletion_require_confirmation_before_http(monkeypatch, name):
    attach_transport(monkeypatch, lambda _: pytest.fail("unconfirmed write reached HTTP"))
    with pytest.raises((ValueError, RuntimeError), match="(?i)(confirm|yes)"):
        dispatch(argv(name))


@pytest.mark.parametrize("status", [404, 409, 422])
def test_server_denial_or_validation_is_preserved_without_retry_or_fallback(monkeypatch, status):
    requests = []
    detail = {"code": "reviewed_server_reason", "message": "No alternate identity or retry"}
    attach_transport(
        monkeypatch, lambda r: requests.append(r) or httpx.Response(status, json={"detail": detail})
    )
    with pytest.raises(cli.ApiRequestError) as exc:
        dispatch([*argv("test-run-confirm"), "--yes"])
    assert exc.value.status_code == status
    assert len(requests) == 1
    assert "reviewed_server_reason" in str(exc.value.detail)


def test_clear_accounts_preserves_empty_array_and_no_fake_idempotency(monkeypatch):
    requests = []
    attach_transport(
        monkeypatch, lambda r: requests.append(r) or httpx.Response(200, json={"id": "receipt"})
    )
    dispatch([*argv("test-group-accounts-set", publishing_account_ids=[], mode="replace"), "--yes"])
    assert json.loads(requests[0].content)["publishing_account_ids"] == []
    assert "Idempotency-Key" not in requests[0].headers


def test_delete_handles_204_and_keeps_workspace_and_force_in_query(monkeypatch):
    requests = []
    attach_transport(monkeypatch, lambda r: requests.append(r) or httpx.Response(204))
    dispatch([*argv("test-group-delete"), "--yes"])
    assert requests[0].content == b""
    assert requests[0].url.params["force"] == "true"
    assert requests[0].url.params["workspace_id"] == CASES[0]["input"]["workspace_id"]


def test_only_true_server_idempotency_operations_expose_key():
    assert {
        s.schema_name for s in specs() if "idempotency_key" in s.input_schema["properties"]
    } == {
        "hireaicreator.test-group-create",
        "hireaicreator.test-run-confirm",
    }
    for spec in specs():
        if spec.risk_level != "read":
            assert spec.supports_dry_run


def test_forbidden_is_not_retried_with_another_identity(monkeypatch):
    requests = []
    attach_transport(
        monkeypatch,
        lambda r: (
            requests.append(r) or httpx.Response(403, json={"detail": "agent capability denied"})
        ),
    )
    with pytest.raises(RuntimeError):
        dispatch([*argv("test-run-confirm"), "--yes"])
    assert len(requests) == 1
