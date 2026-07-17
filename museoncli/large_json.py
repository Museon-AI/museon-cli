from __future__ import annotations

import errno
import hashlib
import json
import os
import re
import shlex
import stat
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_THRESHOLD_BYTES = 20_000
MIN_THRESHOLD_BYTES = 4_096
MAX_THRESHOLD_BYTES = 1_000_000
OFFLOAD_BASE = Path(tempfile.gettempdir()) / "museon-agent"
OFFLOAD_ROOT = OFFLOAD_BASE / "tool-results"
OFFLOAD_TTL_SECONDS = 6 * 60 * 60
PROFILE_MAX_DEPTH = 9
PROFILE_MAX_NODES = 10_000
PROFILE_MAX_ANALYSIS_BYTES = 2_000_000
PROFILE_TOP_K = 8
CLEANUP_MAX_ENTRIES = 1_000
_PAGINATION_KEYS = (
    "page",
    "page_size",
    "total",
    "total_pages",
    "has_more",
    "next_page",
    "next_cursor",
    "cursor",
    "next_page_token",
)
_TRUE_VALUES = {"1", "true", "yes", "on", "enabled"}
_FALSE_VALUES = {"0", "false", "no", "off", "disabled"}


@dataclass(frozen=True)
class RenderedJson:
    text: str
    offload_failed: bool = False


def render_json(payload: dict[str, Any], *, command_hint: str | None = None) -> RenderedJson:
    """Render one CLI envelope, offloading large agent-only success results."""
    raw = json.dumps(payload, ensure_ascii=False, default=str)
    if not _offload_enabled() or payload.get("ok") is not True:
        return RenderedJson(raw)
    threshold = _threshold_bytes()
    raw_bytes = raw.encode("utf-8", errors="replace")
    if len(raw_bytes) <= threshold:
        return RenderedJson(raw)

    command_family = _command_family(payload.get("command"), command_hint)
    try:
        cleanup = _cleanup_expired(OFFLOAD_ROOT)
        offload = _write_offload(raw_bytes, cleanup=cleanup)
        profile = _profile_large_json(payload, len(raw_bytes))
        manifest = _manifest(
            payload,
            command_hint=command_hint,
            command_family=command_family,
            threshold=threshold,
            raw_result=offload,
            profile=profile,
        )
        return RenderedJson(_compact_json(manifest))
    except Exception as exc:
        failure = {
            "ok": False,
            "status": "large_json_offload_failed",
            "command": command_family,
            "command_family": command_family,
            "raw_bytes": len(raw_bytes),
            "threshold": threshold,
            "failure_class": _failure_class(exc),
            "next_step": (
                "The large result was withheld. Retry with narrower CLI filters or "
                "pagination; do not use a whole-output shell reader."
            ),
        }
        return RenderedJson(_compact_json(failure), offload_failed=True)


def _offload_enabled() -> bool:
    override = os.environ.get("MUSEON_JSON_OFFLOAD_ENABLED", "").strip().lower()
    if override in _TRUE_VALUES:
        return True
    if override in _FALSE_VALUES:
        return False
    return bool(
        os.environ.get("MUSEON_CONVERSATION_ID", "").strip()
        and os.environ.get("MUSEON_SANDBOX_ID", "").strip()
    )


def _threshold_bytes() -> int:
    try:
        value = int(os.environ.get("MUSEON_JSON_OFFLOAD_THRESHOLD_BYTES", DEFAULT_THRESHOLD_BYTES))
    except (TypeError, ValueError):
        return DEFAULT_THRESHOLD_BYTES
    return max(MIN_THRESHOLD_BYTES, min(MAX_THRESHOLD_BYTES, value))


def _command_family(payload_command: Any, command_hint: str | None) -> str:
    for candidate in (payload_command, command_hint):
        if isinstance(candidate, str) and re.fullmatch(
            r"[a-z][a-z0-9_-]{0,31}\.[a-z][a-z0-9_-]{0,31}", candidate
        ):
            return candidate
    return "museon.unknown"


def _manifest(
    payload: dict[str, Any],
    *,
    command_hint: str | None,
    command_family: str,
    threshold: int,
    raw_result: dict[str, Any],
    profile: dict[str, Any],
) -> dict[str, Any]:
    data = payload.get("data")
    item_count = _item_count(data)
    requested_command = payload.get("command") or command_hint
    command = (
        requested_command
        if isinstance(requested_command, str) and len(requested_command) <= 80
        else command_family
    )
    manifest: dict[str, Any] = {
        "ok": True,
        "status": "large_json_offloaded",
        "command": command,
        "command_family": command_family,
        "threshold": threshold,
        "shape": _json_shape(payload),
        "item_count": item_count,
        "pagination": _pagination(payload),
        "raw_result": raw_result,
        "heavy_fields": profile,
        "query_manifest": _query_manifest(
            raw_result["path"], command_family=command_family, profile=profile
        ),
    }
    if command_family == "asset.list" and isinstance(data, dict):
        asset_type = data.get("type")
        if isinstance(asset_type, str) and len(asset_type) <= 64:
            manifest["asset_type"] = asset_type
    return manifest


def _write_offload(raw: bytes, *, cleanup: dict[str, Any]) -> dict[str, Any]:
    conversation_id = os.environ.get("MUSEON_CONVERSATION_ID", "test")
    session_key = hashlib.sha256(conversation_id.encode("utf-8", errors="replace")).hexdigest()[:16]
    session_dir = OFFLOAD_ROOT / session_key
    _ensure_private_dir(OFFLOAD_BASE)
    _ensure_private_dir(OFFLOAD_ROOT)
    _ensure_private_dir(session_dir)

    final_path = session_dir / f"result_{uuid.uuid4().hex}.json"
    temporary_path = session_dir / f".{final_path.name}.{uuid.uuid4().hex[:12]}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(temporary_path, flags, 0o600)
    try:
        with os.fdopen(fd, "wb") as handle:
            fd = -1
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_path, 0o600)
        os.replace(temporary_path, final_path)
        os.chmod(final_path, 0o600)
    finally:
        if fd >= 0:
            os.close(fd)
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            pass
    return {
        "path": str(final_path),
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "cleanup": cleanup,
    }


def _ensure_private_dir(path: Path) -> None:
    try:
        os.mkdir(path, 0o700)
    except FileExistsError:
        # Parallel agent CLI calls may create the shared parent/session path
        # between our existence check and mkdir. Re-validate the winner's path.
        pass
    path_stat = os.lstat(path)
    if stat.S_ISLNK(path_stat.st_mode) or not stat.S_ISDIR(path_stat.st_mode):
        raise RuntimeError("unsafe_offload_path")
    os.chmod(path, 0o700)


def _cleanup_expired(root: Path) -> dict[str, Any]:
    stats: dict[str, Any] = {
        "reason": "none",
        "deleted_files": 0,
        "deleted_bytes": 0,
        "failure_count": 0,
        "scanned_entries": 0,
        "scan_truncated": False,
    }
    if not os.path.lexists(root):
        return stats
    if root.is_symlink() or not root.is_dir():
        stats["failure_count"] = 1
        return stats

    cutoff = time.time() - OFFLOAD_TTL_SECONDS
    try:
        with os.scandir(root) as directory_entries:
            for directory_entry in directory_entries:
                if stats["scanned_entries"] >= CLEANUP_MAX_ENTRIES:
                    stats["scan_truncated"] = True
                    break
                stats["scanned_entries"] += 1
                if directory_entry.is_symlink() or not directory_entry.is_dir(
                    follow_symlinks=False
                ):
                    continue
                directory = Path(directory_entry.path)
                try:
                    with os.scandir(directory) as file_entries:
                        for file_entry in file_entries:
                            if stats["scanned_entries"] >= CLEANUP_MAX_ENTRIES:
                                stats["scan_truncated"] = True
                                break
                            stats["scanned_entries"] += 1
                            path = Path(file_entry.path)
                            try:
                                stat_result = file_entry.stat(follow_symlinks=False)
                                if (
                                    file_entry.is_symlink()
                                    or not file_entry.is_file(follow_symlinks=False)
                                    or stat_result.st_mtime > cutoff
                                ):
                                    continue
                                path.unlink()
                                stats["deleted_files"] += 1
                                stats["deleted_bytes"] += max(0, int(stat_result.st_size))
                            except OSError:
                                stats["failure_count"] += 1
                except OSError:
                    stats["failure_count"] += 1
                    continue
                try:
                    directory.rmdir()
                except OSError:
                    pass
                if stats["scan_truncated"]:
                    break
    except OSError:
        stats["failure_count"] += 1
        return stats
    if stats["deleted_files"]:
        stats["reason"] = "ttl"
    return stats


def _failure_class(exc: Exception) -> str:
    if isinstance(exc, PermissionError):
        return "permission_denied"
    if isinstance(exc, OSError) and exc.errno == errno.ENOSPC:
        return "no_space"
    if isinstance(exc, (FileNotFoundError, NotADirectoryError)):
        return "path_unavailable"
    if str(exc) == "unsafe_offload_path":
        return "unsafe_path"
    return "io_error"


def _json_kind(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    if isinstance(value, str):
        return "string"
    if isinstance(value, (int, float)):
        return "number"
    return "other"


def _path_key(path: str, key: Any) -> str:
    text = str(key)
    suffix = text if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]{0,63}", text) else "*"
    return ("" if path == "." else path) + "." + suffix


def _profile_add(stats: dict[str, dict[str, Any]], path: str, kind: str, size: int) -> None:
    if path == ".":
        return
    row = stats.setdefault(
        path,
        {"path": path, "json_type": kind, "occurrences": 0, "bytes": 0, "max_item_bytes": 0},
    )
    row["occurrences"] += 1
    row["bytes"] += max(0, size)
    row["max_item_bytes"] = max(row["max_item_bytes"], max(0, size))


def _profile_large_json(payload: dict[str, Any], raw_bytes: int) -> dict[str, Any]:
    containers: dict[str, dict[str, Any]] = {}
    leaves: dict[str, dict[str, Any]] = {}
    budget = {"nodes": 0, "analysis_bytes": 0, "truncated": False}

    def walk(value: Any, path: str, depth: int) -> int:
        if budget["nodes"] >= PROFILE_MAX_NODES or depth > PROFILE_MAX_DEPTH:
            budget["truncated"] = True
            return 0
        budget["nodes"] += 1
        if isinstance(value, dict):
            size = 2
            for index, (key, child) in enumerate(value.items()):
                if budget["nodes"] >= PROFILE_MAX_NODES:
                    budget["truncated"] = True
                    break
                if index:
                    size += 1
                encoded_key = json.dumps(str(key), ensure_ascii=False, separators=(",", ":"))
                size += len(encoded_key.encode("utf-8", errors="replace")) + 1
                size += walk(child, _path_key(path, key), depth + 1)
            _profile_add(containers, path, "object", size)
            return size
        if isinstance(value, list):
            size = 2
            child_path = ("" if path == "." else path) + "[]"
            for index, child in enumerate(value):
                if budget["nodes"] >= PROFILE_MAX_NODES:
                    budget["truncated"] = True
                    break
                if index:
                    size += 1
                size += walk(child, child_path, depth + 1)
            _profile_add(containers, path, "array", size)
            return size
        size = _scalar_size(value, budget)
        _profile_add(leaves, path, _json_kind(value), size)
        return size

    walk(payload, ".", 0)
    denominator = max(1, raw_bytes)

    def top_rows(stats: dict[str, dict[str, Any]], byte_key: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for row in sorted(stats.values(), key=lambda item: (-item["bytes"], item["path"]))[
            :PROFILE_TOP_K
        ]:
            rows.append(
                {
                    "path": row["path"],
                    "json_type": row["json_type"],
                    "occurrences": row["occurrences"],
                    byte_key: row["bytes"],
                    "ratio": round(min(1.0, row["bytes"] / denominator), 4),
                    "max_item_bytes": row["max_item_bytes"],
                }
            )
        return rows

    raw_share_ratio = 0.0
    raw_row = containers.get(".data.items[].raw")
    if raw_row:
        raw_share_ratio = min(1.0, raw_row["bytes"] / denominator)
    return {
        "heavy_containers": top_rows(containers, "inclusive_bytes"),
        "heavy_leaves": top_rows(leaves, "estimated_bytes"),
        "approximate": True,
        "truncated": bool(budget["truncated"]),
        "profiled_nodes": budget["nodes"],
        "analysis_bytes": budget["analysis_bytes"],
        "limits": {
            "max_depth": PROFILE_MAX_DEPTH,
            "max_nodes": PROFILE_MAX_NODES,
            "max_analysis_bytes": PROFILE_MAX_ANALYSIS_BYTES,
            "top_k": PROFILE_TOP_K,
        },
        "note": "inclusive container sizes overlap and must not be added together",
        "raw_share_ratio": round(raw_share_ratio, 4),
    }


def _scalar_size(value: Any, budget: dict[str, Any]) -> int:
    if isinstance(value, str):
        remaining = max(0, PROFILE_MAX_ANALYSIS_BYTES - budget["analysis_bytes"])
        if remaining <= 0:
            budget["truncated"] = True
            return len(value) + 2
        sample = value[: max(1, remaining // 4)]
        encoded = len(sample.encode("utf-8", errors="replace"))
        budget["analysis_bytes"] += encoded
        if len(sample) < len(value):
            budget["truncated"] = True
            ratio = encoded / len(sample) if sample else 1.0
            return max(2, int(round(len(value) * ratio)) + 2)
        escapes = sum(1 for char in sample if char in ('"', "\\") or ord(char) < 32)
        return encoded + 2 + escapes
    scalar_bytes = _compact_json(value).encode("utf-8", errors="replace")
    budget["analysis_bytes"] += min(
        len(scalar_bytes), max(0, PROFILE_MAX_ANALYSIS_BYTES - budget["analysis_bytes"])
    )
    return len(scalar_bytes)


def _json_shape(payload: dict[str, Any]) -> dict[str, Any]:
    shape: dict[str, Any] = {
        "top_level_kind": "object",
        "top_level_keys": _shape_keys(payload),
    }
    data = payload.get("data")
    data_shape: dict[str, Any] = {"kind": _json_kind(data)}
    if isinstance(data, list):
        data_shape["count"] = len(data)
    elif isinstance(data, dict):
        data_shape["keys"] = _shape_keys(data)
        items = data.get("items")
        if isinstance(items, list):
            data_shape["items_count"] = len(items)
            if items and isinstance(items[0], dict):
                data_shape["item_keys"] = _shape_keys(items[0])
    shape["data"] = data_shape
    return shape


def _shape_keys(value: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    for key in value:
        text = str(key)
        normalized = text if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]{0,63}", text) else "*"
        if normalized not in keys:
            keys.append(normalized)
        if len(keys) >= 32:
            break
    return sorted(keys)


def _item_count(data: Any) -> int | None:
    if isinstance(data, dict) and isinstance(data.get("items"), list):
        return len(data["items"])
    if isinstance(data, list):
        return len(data)
    return None


def _pagination(payload: dict[str, Any]) -> dict[str, Any] | None:
    data = payload.get("data")
    pagination = data.get("pagination") if isinstance(data, dict) else None
    if not isinstance(pagination, dict):
        pagination = payload.get("pagination")
    if not isinstance(pagination, dict):
        return None
    result: dict[str, Any] = {}
    for key in _PAGINATION_KEYS:
        if key not in pagination:
            continue
        value = pagination[key]
        if value is None or isinstance(value, (str, int, float, bool)):
            if isinstance(value, str) and len(value.encode("utf-8")) > 512:
                result[key] = {"omitted": True, "reason": "value_exceeds_512_bytes"}
            else:
                result[key] = value
    return result


def _query_manifest(
    path: str,
    *,
    command_family: str,
    profile: dict[str, Any],
    platform_name: str | None = None,
) -> dict[str, Any]:
    if (platform_name or os.name) == "nt":
        return _powershell_query_manifest(path)

    quoted = shlex.quote(path)
    if command_family == "asset.list":
        projection = (
            "jq '.data.items[:10] | map({id,title,status,type,"
            "content_form:(.content_form // .raw.content_form),"
            "tags:(.tags // .raw.tags // []),ref})' " + quoted
        )
    else:
        projection = "jq '.data.items[:10] | map({id,title,status,type,ref})' " + quoted
    heavy_leaves = profile.get("heavy_leaves") or []
    heavy_path = str(heavy_leaves[0].get("path") or "") if heavy_leaves else ""
    heavy_query = None
    if heavy_path.startswith(".") and ".*" not in heavy_path:
        heavy_query = "jq '" + heavy_path.replace("[]", "[0]") + "' " + quoted
    return {
        "preferred_tool": "jq",
        "guidance": [
            "Use jq as the primary interface to the complete offloaded result.",
            "Combine related keys/count/filter/projection questions into one jq query when practical.",
            "Independent questions may be issued as parallel jq Bash tool calls.",
            "Project small decision fields first; avoid heavy paths and never query the whole document.",
            "Heavy containers may still hold small decision scalars: lift required scalars, then omit large leaves.",
        ],
        "templates": {
            "keys_and_types": "jq '{top_level_keys: keys, data_type: (.data | type)}' " + quoted,
            "count_and_fields": (
                "jq '{item_count: ((.data.items? // []) | length), "
                "item_fields: ((.data.items?[0]? // {}) | keys)}' " + quoted
            ),
            "project_sample": projection,
            "select_sample": (
                'jq \'.data.items[] | select(.status == "ready") | '
                "{id,title,status,type,ref}' " + quoted
            ),
            "heavy_leaf_only_if_required": heavy_query,
        },
    }


def _powershell_query_manifest(path: str) -> dict[str, Any]:
    quoted = "'" + path.replace("'", "''") + "'"
    load = f"$result = Get-Content -Raw -LiteralPath {quoted} | ConvertFrom-Json; "
    return {
        "preferred_tool": "powershell",
        "guidance": [
            "Use PowerShell to read the complete offloaded result from the literal file path.",
            "Project only the fields needed for the current decision; do not print the whole document.",
            "Use Select-Object -First to keep samples bounded.",
        ],
        "templates": {
            "keys_and_types": (
                load
                + "$result.PSObject.Properties.Name | ConvertTo-Json -Compress"
            ),
            "count_and_fields": (
                load
                + "@{item_count=@($result.data.items).Count; "
                + "item_fields=@($result.data.items)[0].PSObject.Properties.Name} "
                + "| ConvertTo-Json -Compress"
            ),
            "project_sample": (
                load
                + "@($result.data.items) | Select-Object -First 10 "
                + "-Property id,title,status,type,ref | ConvertTo-Json -Depth 6 -Compress"
            ),
            "select_sample": (
                load
                + "@($result.data.items) | Where-Object status -eq 'ready' "
                + "| Select-Object -First 10 -Property id,title,status,type,ref "
                + "| ConvertTo-Json -Depth 6 -Compress"
            ),
            "heavy_leaf_only_if_required": None,
        },
    }


def _compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))
