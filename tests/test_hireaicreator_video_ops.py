"""Versioned video lifecycle regression tests, through the real CLI dispatcher."""

import json
from pathlib import Path

import httpx
import pytest

from test_ai_hook_parameter_contract import attach_transport, dispatch
from museoncli.domains.hireaicreator_video_ops import specs

CASES = json.loads((Path(__file__).parent / "fixtures/video_ops_requests.json").read_text())


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
    "name", ["video-review", "video-bulk-review", "video-delete", "video-bulk-delete"]
)
def test_review_and_deletion_require_explicit_confirmation(monkeypatch, name):
    attach_transport(monkeypatch, lambda _: pytest.fail("unconfirmed write reached HTTP"))
    with pytest.raises(RuntimeError, match="confirmation_required"):
        dispatch(argv(name))


def test_delete_passes_version_in_query_and_accepts_empty_204(monkeypatch):
    requests = []
    attach_transport(monkeypatch, lambda r: requests.append(r) or httpx.Response(204))
    dispatch([*argv("video-delete"), "--yes"])
    assert dict(requests[0].url.params) == {"expected_version": "7"}
    assert requests[0].content == b""


def test_bulk_partial_failure_remains_visible_and_does_not_retry(monkeypatch):
    requests = []
    receipt = {
        "succeeded": [],
        "conflicted": ["22222222-2222-4222-8222-222222222222"],
        "failures": [
            {"code": "version_conflict", "message": "refresh first", "current_version": 8}
        ],
    }
    attach_transport(monkeypatch, lambda r: requests.append(r) or httpx.Response(200, json=receipt))
    result = dispatch([*argv("video-bulk-review"), "--yes"])
    assert result["data"] == receipt
    assert len(requests) == 1


def test_export_batch_rejects_over_50_before_network(monkeypatch):
    attach_transport(monkeypatch, lambda _: pytest.fail("invalid batch reached HTTP"))
    original = next(c for c in CASES if c["name"] == "delivery-export-batch")
    with pytest.raises(ValueError, match="item count"):
        dispatch(argv("delivery-export-batch", items=original["input"]["items"] * 51))


@pytest.mark.parametrize("name", ["video-render", "video-caption-regenerate", "video-review"])
def test_stale_or_missing_version_cannot_be_silently_defaulted(monkeypatch, name):
    attach_transport(monkeypatch, lambda _: pytest.fail("invalid version reached HTTP"))
    with pytest.raises(ValueError, match="range"):
        dispatch([*argv(name, expected_version=0), "--dry-run"])


def test_cancel_plan_does_not_advertise_ignored_optional_idempotency_header():
    spec = next(s for s in specs() if s.schema_name == "hireaicreator.plan-cancel")
    assert "idempotency_key" not in spec.input_schema["properties"]
