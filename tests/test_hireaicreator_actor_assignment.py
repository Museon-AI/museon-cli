"""Actor assignment must not bypass confirmation or silently retry conflicts."""

import json

import httpx
import pytest

from test_ai_hook_parameter_contract import attach_transport, dispatch

PAYLOAD = {
    "workspace_id": "11111111-1111-4111-8111-111111111111",
    "target_workspace_id": "33333333-3333-4333-8333-333333333333",
    "actor_ids": ["22222222-2222-4222-8222-222222222222"],
    "mode": "copy",
    "preview_token": "opaque-server-preview",
    "idempotency_key": "actor-assignment-test-001",
}


def argv(**overrides):
    return [
        "hireaicreator",
        "actor",
        "+assign",
        "--args-json",
        json.dumps({**PAYLOAD, **overrides}),
    ]


def test_assignment_needs_confirmation_and_dry_run_never_calls_api(monkeypatch):
    attach_transport(monkeypatch, lambda _: pytest.fail("unapproved assignment reached HTTP"))
    with pytest.raises(RuntimeError, match="confirmation_required"):
        dispatch(argv())
    dispatch([*argv(), "--dry-run"])


@pytest.mark.parametrize("mode", ["copy", "move"])
def test_stale_assignment_is_reported_without_refresh_or_retry(monkeypatch, mode):
    requests = []
    attach_transport(
        monkeypatch,
        lambda request: (
            requests.append(request)
            or httpx.Response(409, json={"detail": {"code": "actor_assignment_changed"}})
        ),
    )
    with pytest.raises(Exception, match="actor_assignment_changed"):
        dispatch([*argv(mode=mode), "--yes"])
    assert len(requests) == 1
    assert requests[0].headers["Idempotency-Key"] == PAYLOAD["idempotency_key"]


@pytest.mark.parametrize("actor_ids", [[], PAYLOAD["actor_ids"] * 101])
def test_invalid_batch_cannot_reach_server(monkeypatch, actor_ids):
    attach_transport(monkeypatch, lambda _: pytest.fail("invalid assignment reached HTTP"))
    with pytest.raises(ValueError, match="item count"):
        dispatch([*argv(actor_ids=actor_ids), "--yes"])
