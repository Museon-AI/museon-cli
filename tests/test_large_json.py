from __future__ import annotations

import hashlib
import json
import os
import stat
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import pytest

from museoncli import large_json
import museoncli.main as main_module


def test_default_offload_root_uses_the_host_temporary_directory() -> None:
    assert large_json.OFFLOAD_BASE == Path(tempfile.gettempdir()) / "museon-agent"
    assert large_json.OFFLOAD_ROOT == large_json.OFFLOAD_BASE / "tool-results"


def _configure_offload(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    enabled: str = "1",
) -> Path:
    base = tmp_path / "museon-agent"
    root = base / "tool-results"
    monkeypatch.setattr(large_json, "OFFLOAD_BASE", base)
    monkeypatch.setattr(large_json, "OFFLOAD_ROOT", root)
    monkeypatch.setenv("MUSEON_JSON_OFFLOAD_ENABLED", enabled)
    monkeypatch.setenv("MUSEON_JSON_OFFLOAD_THRESHOLD_BYTES", "4096")
    monkeypatch.setenv("MUSEON_CONVERSATION_ID", "conversation-private-id")
    monkeypatch.setenv("MUSEON_SANDBOX_ID", "sandbox-private-id")
    return root


def _large_payload(*, ok: bool = True) -> dict[str, Any]:
    items = []
    for index in range(4):
        items.append(
            {
                "id": f"asset-{index}",
                "title": f"Scenic format {index}",
                "status": "ready",
                "type": "format",
                "raw": {
                    "content_form": "slideshow",
                    "format_json": {"md": "SENSITIVE-MARKER-MUST-NOT-LEAK-" + ("x" * 8_000)},
                },
            }
        )
    return {
        "ok": ok,
        "command": "asset.list",
        "data": {
            "type": "format",
            "items": items,
            "pagination": {
                "page": 1,
                "page_size": 20,
                "total": 4,
                "total_pages": 1,
                "has_more": False,
            },
        },
    }


def test_large_agent_json_is_offloaded_with_hook_compatible_manifest(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = _configure_offload(monkeypatch, tmp_path)
    payload = _large_payload()
    expected_raw = json.dumps(payload, ensure_ascii=False, default=str)

    rendered = large_json.render_json(payload)

    assert rendered.offload_failed is False
    manifest = json.loads(rendered.text)
    assert manifest["ok"] is True
    assert manifest["status"] == "large_json_offloaded"
    assert manifest["command"] == "asset.list"
    assert manifest["command_family"] == "asset.list"
    assert manifest["asset_type"] == "format"
    assert manifest["item_count"] == 4
    assert manifest["pagination"] == {
        "page": 1,
        "page_size": 20,
        "total": 4,
        "total_pages": 1,
        "has_more": False,
    }
    assert manifest["shape"]["data"]["items_count"] == 4
    assert manifest["query_manifest"]["preferred_tool"] == "jq"
    assert "parallel jq Bash tool calls" in " ".join(manifest["query_manifest"]["guidance"])
    assert (
        ".content_form // .raw.content_form"
        in manifest["query_manifest"]["templates"]["project_sample"]
    )

    raw_path = Path(manifest["raw_result"]["path"])
    conversation_hash = hashlib.sha256(b"conversation-private-id").hexdigest()[:16]
    assert raw_path.parent == root / conversation_hash
    assert raw_path.read_text(encoding="utf-8") == expected_raw
    assert manifest["raw_result"]["bytes"] == len(expected_raw.encode())
    assert manifest["raw_result"]["sha256"] == hashlib.sha256(expected_raw.encode()).hexdigest()
    assert stat.S_IMODE(root.stat().st_mode) == 0o700
    assert stat.S_IMODE(raw_path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(raw_path.stat().st_mode) == 0o600
    assert not list(raw_path.parent.glob("*.tmp"))

    heavy = manifest["heavy_fields"]
    assert len(heavy["heavy_containers"]) <= large_json.PROFILE_TOP_K
    assert len(heavy["heavy_leaves"]) <= large_json.PROFILE_TOP_K
    assert any(row["path"] == ".data.items[].raw.format_json.md" for row in heavy["heavy_leaves"])
    assert heavy["raw_share_ratio"] > 0.9
    assert "SENSITIVE-MARKER-MUST-NOT-LEAK" not in rendered.text
    assert len(rendered.text.encode()) < 10_000


def test_windows_query_manifest_uses_literal_powershell_paths() -> None:
    manifest = large_json._query_manifest(
        "C:\\Users\\O'Brien\\result.json",
        command_family="asset.list",
        profile={},
        platform_name="nt",
    )

    assert manifest["preferred_tool"] == "powershell"
    templates = manifest["templates"]
    assert "-LiteralPath 'C:\\Users\\O''Brien\\result.json'" in templates["project_sample"]
    assert "Select-Object -First 10" in templates["project_sample"]
    assert all("jq" not in value for value in manifest["guidance"])


def test_large_json_offload_requires_agent_context_unless_explicitly_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _large_payload()
    expected = json.dumps(payload, ensure_ascii=False, default=str)
    monkeypatch.delenv("MUSEON_JSON_OFFLOAD_ENABLED", raising=False)
    monkeypatch.delenv("MUSEON_CONVERSATION_ID", raising=False)
    monkeypatch.delenv("MUSEON_SANDBOX_ID", raising=False)

    rendered = large_json.render_json(payload)

    assert rendered.text == expected
    assert rendered.offload_failed is False


def test_explicit_disable_wins_over_agent_context(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _large_payload()
    expected = json.dumps(payload, ensure_ascii=False, default=str)
    monkeypatch.setenv("MUSEON_CONVERSATION_ID", "conversation-1")
    monkeypatch.setenv("MUSEON_SANDBOX_ID", "sandbox-1")
    monkeypatch.setenv("MUSEON_JSON_OFFLOAD_ENABLED", "0")

    assert large_json.render_json(payload).text == expected


@pytest.mark.parametrize(
    "payload",
    [
        {"ok": True, "data": {"message": "small"}},
        {"ok": False, "reason": "upstream_error", "detail": "x" * 30_000},
    ],
)
def test_small_and_error_json_remain_unchanged(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    payload: dict[str, Any],
) -> None:
    _configure_offload(monkeypatch, tmp_path)

    rendered = large_json.render_json(payload)

    assert rendered.text == json.dumps(payload, ensure_ascii=False, default=str)
    assert rendered.offload_failed is False


def test_offload_opportunistically_removes_expired_results(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = _configure_offload(monkeypatch, tmp_path)
    stale_dir = root / "old-conversation"
    stale_dir.mkdir(parents=True, mode=0o700)
    stale = stale_dir / "result_stale.json"
    stale.write_text("old-result", encoding="utf-8")
    stale_at = time.time() - large_json.OFFLOAD_TTL_SECONDS - 1
    os.utime(stale, (stale_at, stale_at))

    rendered = large_json.render_json(_large_payload())

    manifest = json.loads(rendered.text)
    assert manifest["raw_result"]["cleanup"] == {
        "reason": "ttl",
        "deleted_files": 1,
        "deleted_bytes": len("old-result"),
        "failure_count": 0,
        "scanned_entries": 2,
        "scan_truncated": False,
    }
    assert not stale.exists()
    assert not stale_dir.exists()


def test_cleanup_scan_is_bounded_and_reports_truncation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "tool-results"
    root.mkdir()
    monkeypatch.setattr(large_json, "CLEANUP_MAX_ENTRIES", 3)
    for index in range(5):
        (root / f"entry-{index}").write_text("still here", encoding="utf-8")

    stats = large_json._cleanup_expired(root)

    assert stats["scanned_entries"] == 3
    assert stats["scan_truncated"] is True


def test_private_directory_creation_tolerates_parallel_creator(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    target = tmp_path / "shared-session"
    real_mkdir = os.mkdir

    def racing_mkdir(path: os.PathLike[str] | str, mode: int = 0o777) -> None:
        assert Path(path) == target
        real_mkdir(path, mode)
        raise FileExistsError(path)

    monkeypatch.setattr(os, "mkdir", racing_mkdir)

    large_json._ensure_private_dir(target)

    assert target.is_dir()
    assert stat.S_IMODE(target.stat().st_mode) == 0o700


def test_offload_failure_is_small_and_main_exits_one(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    bad_base = tmp_path / "occupied"
    bad_base.write_text("not a directory", encoding="utf-8")
    monkeypatch.setattr(large_json, "OFFLOAD_BASE", bad_base)
    monkeypatch.setattr(large_json, "OFFLOAD_ROOT", bad_base / "tool-results")
    monkeypatch.setenv("MUSEON_JSON_OFFLOAD_ENABLED", "1")
    monkeypatch.setenv("MUSEON_JSON_OFFLOAD_THRESHOLD_BYTES", "4096")
    monkeypatch.setenv("MUSEON_CONVERSATION_ID", "conversation-1")
    monkeypatch.setenv("MUSEON_SANDBOX_ID", "sandbox-1")

    async def fake_dispatch(_args: Any) -> dict[str, Any]:
        payload = _large_payload()
        payload.pop("ok")
        return payload

    monkeypatch.setattr(main_module, "dispatch_with_notices", fake_dispatch)
    monkeypatch.setattr(sys, "argv", ["museoncli", "version"])

    with pytest.raises(SystemExit) as exc_info:
        main_module.main()

    assert exc_info.value.code == 1
    output = capsys.readouterr().out
    failure = json.loads(output)
    assert failure["ok"] is False
    assert failure["status"] == "large_json_offload_failed"
    assert failure["failure_class"] == "unsafe_path"
    assert "SENSITIVE-MARKER-MUST-NOT-LEAK" not in output
    assert len(output.encode()) < 1_000
