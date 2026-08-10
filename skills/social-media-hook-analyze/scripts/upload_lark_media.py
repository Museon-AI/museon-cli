#!/usr/bin/env python3
"""Probe, cover, and upload Hook MP4s with complete Lark media metadata."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

SOURCE_SCHEMA_VERSION = "social-hook-lark-media-source.v1"
MEDIA_SCHEMA_VERSION = "social-hook-lark-media.v2"
MAX_VIDEO_BYTES = 30 * 1024 * 1024
_BLACK_SEGMENT = re.compile(r"black_start:(?P<start>[0-9.]+).*black_end:(?P<end>[0-9.]+)")


def _run(command: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> str:
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()[-1200:]
        raise RuntimeError(f"Command failed ({command[0]}): {detail}")
    return completed.stdout


def _duration_ms(video_path: Path, *, cwd: Path) -> int:
    output = _run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ],
        cwd=cwd,
    ).strip()
    try:
        duration_ms = round(float(output) * 1000)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Could not read MP4 duration for {video_path.name}") from exc
    if duration_ms <= 0:
        raise ValueError(f"MP4 duration must be positive for {video_path.name}")
    return duration_ms


def _cover_timestamp(video_path: Path, duration_ms: int, *, cwd: Path) -> float:
    scan_seconds = min(1.0, duration_ms / 1000)
    completed = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "info",
            "-i",
            str(video_path),
            "-t",
            f"{scan_seconds:.3f}",
            "-vf",
            "blackdetect=d=0.02:pix_th=0.10",
            "-an",
            "-f",
            "null",
            "-",
        ],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        return 0.0
    for match in _BLACK_SEGMENT.finditer(completed.stderr):
        if float(match.group("start")) <= 0.02:
            return min(float(match.group("end")) + 0.02, max(0.0, duration_ms / 1000 - 0.02))
    return 0.0


def _extract_cover(video_path: Path, cover_path: Path, duration_ms: int, *, cwd: Path) -> None:
    timestamp = _cover_timestamp(video_path, duration_ms, cwd=cwd)
    _run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(video_path),
            "-ss",
            f"{timestamp:.3f}",
            "-frames:v",
            "1",
            "-vf",
            "scale='min(1080,iw)':-2",
            "-q:v",
            "2",
            "-y",
            str(cover_path),
        ],
        cwd=cwd,
    )
    if not cover_path.is_file() or cover_path.stat().st_size == 0:
        raise ValueError(f"Could not extract a cover for {video_path.name}")


def _response_key(payload: Any, key: str, prefix: str) -> str:
    if isinstance(payload, dict):
        value = payload.get(key)
        if isinstance(value, str) and value.startswith(prefix):
            return value
        for nested in payload.values():
            try:
                return _response_key(nested, key, prefix)
            except ValueError:
                continue
    elif isinstance(payload, list):
        for nested in payload:
            try:
                return _response_key(nested, key, prefix)
            except ValueError:
                continue
    raise ValueError(f"Lark upload response did not contain {key}")


def _lark_json(command: list[str], *, cwd: Path) -> dict[str, Any]:
    env = dict(os.environ)
    env["LARKSUITE_CLI_NO_UPDATE_NOTIFIER"] = "1"
    env["LARKSUITE_CLI_NO_SKILLS_NOTIFIER"] = "1"
    output = _run(command, cwd=cwd, env=env)
    try:
        payload = json.loads(output)
    except json.JSONDecodeError as exc:
        raise ValueError("lark-cli returned a non-JSON upload response") from exc
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        raise ValueError("lark-cli upload did not return ok=true")
    return payload


def _source_items(payload: Any, source_dir: Path) -> list[tuple[str, Path]]:
    if (
        not isinstance(payload, dict)
        or payload.get("media_source_schema_version") != SOURCE_SCHEMA_VERSION
    ):
        raise ValueError(f"Media source manifest must use {SOURCE_SCHEMA_VERSION}")
    raw_items = payload.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        raise ValueError("Media source manifest requires at least one item")
    items: list[tuple[str, Path]] = []
    seen: set[str] = set()
    for raw in raw_items:
        if not isinstance(raw, dict):
            raise ValueError("Every media source item must be an object")
        item_id = raw.get("item_id")
        video_path = raw.get("video_path")
        if not isinstance(item_id, str) or not item_id.strip() or item_id in seen:
            raise ValueError("Every media source item requires a unique item_id")
        if not isinstance(video_path, str) or not video_path.strip():
            raise ValueError(f"Media source item {item_id!r} requires video_path")
        resolved = Path(video_path)
        if not resolved.is_absolute():
            resolved = source_dir / resolved
        resolved = resolved.resolve()
        if not resolved.is_file():
            raise ValueError(f"Video for media source item {item_id!r} does not exist")
        if resolved.stat().st_size <= 0 or resolved.stat().st_size > MAX_VIDEO_BYTES:
            raise ValueError(f"Video for media source item {item_id!r} must be 1 byte to 30 MiB")
        seen.add(item_id)
        items.append((item_id, resolved))
    return items


def upload_manifest(payload: Any, *, source_dir: Path, cwd: Path) -> dict[str, Any]:
    uploaded: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix=".social-hook-lark-", dir=cwd) as temp_name:
        temp_dir = Path(temp_name)
        for index, (item_id, source_path) in enumerate(_source_items(payload, source_dir), start=1):
            video_path = temp_dir / f"video-{index}.mp4"
            cover_path = temp_dir / f"cover-{index}.jpg"
            shutil.copyfile(source_path, video_path)
            duration_ms = _duration_ms(video_path, cwd=cwd)
            _extract_cover(video_path, cover_path, duration_ms, cwd=cwd)
            relative_video = video_path.relative_to(cwd)
            relative_cover = cover_path.relative_to(cwd)
            video_response = _lark_json(
                [
                    "lark-cli",
                    "api",
                    "POST",
                    "/open-apis/im/v1/files",
                    "--as",
                    "bot",
                    "--data",
                    json.dumps(
                        {
                            "file_type": "mp4",
                            "file_name": f"social-hook-{index}.mp4",
                            "duration": duration_ms,
                        },
                        separators=(",", ":"),
                    ),
                    "--file",
                    f"file={relative_video}",
                ],
                cwd=cwd,
            )
            cover_response = _lark_json(
                [
                    "lark-cli",
                    "im",
                    "images",
                    "create",
                    "--as",
                    "bot",
                    "--data",
                    '{"image_type":"message"}',
                    "--file",
                    f"image={relative_cover}",
                ],
                cwd=cwd,
            )
            uploaded.append(
                {
                    "item_id": item_id,
                    "file_key": _response_key(video_response, "file_key", "file_"),
                    "cover_img_key": _response_key(cover_response, "image_key", "img_"),
                    "duration_ms": duration_ms,
                }
            )
    return {"media_schema_version": MEDIA_SCHEMA_VERSION, "items": uploaded}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("sources", help=f"{SOURCE_SCHEMA_VERSION} JSON manifest")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    source_path = Path(args.sources).resolve()
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    result = upload_manifest(payload, source_dir=source_path.parent, cwd=Path.cwd().resolve())
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2 if args.pretty else None)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
