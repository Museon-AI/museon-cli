#!/usr/bin/env python3
"""Verify that built Museon CLI artifacts are complete and public-safe."""

from __future__ import annotations

import argparse
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
PRIVATE_REFERENCES = (
    b"apps/museoncli",
    b"apps/api",
    b"apps/agents",
    b"/admin/cli",
    b"MUSEON_CLI_DOWNLOAD_TOKEN",
    b"museon-ai.feishu.cn",
    b"movora-469510",
    b"DOPPLER_TOKEN",
)
FORBIDDEN_SUFFIXES = (".env", ".key", ".pem", ".p12", ".pfx")
FORBIDDEN_FILES = {
    "museoncli/prompt.py",
    "museoncli/system.md",
}
SECRET_PATTERNS = (
    ("private key", re.compile(rb"-----BEGIN (?:RSA |OPENSSH |EC |DSA )?PRIVATE KEY-----")),
    ("GitHub token", re.compile(rb"\b(?:github_pat_[A-Za-z0-9_]{20,}|gh[pousr]_[A-Za-z0-9]{20,})\b")),
    ("model provider key", re.compile(rb"\bsk-(?:live|proj)-[A-Za-z0-9_-]{16,}\b")),
    ("Slack token", re.compile(rb"\bxox[baprs]-[A-Za-z0-9-]{16,}\b")),
    ("AWS access key", re.compile(rb"\bAKIA[0-9A-Z]{16}\b")),
)
@dataclass(frozen=True, slots=True)
class ArchiveEntry:
    name: str
    payload: bytes


def _wheel_entries(path: Path) -> list[ArchiveEntry]:
    with zipfile.ZipFile(path) as archive:
        result: list[ArchiveEntry] = []
        for item in archive.infolist():
            if item.is_dir():
                continue
            unix_mode = (item.external_attr >> 16) & 0o170000
            if unix_mode == 0o120000:
                raise RuntimeError(f"wheel contains a symbolic link: {item.filename}")
            result.append(ArchiveEntry(item.filename, archive.read(item)))
        return result


def _assert_no_forbidden_paths(entries: list[ArchiveEntry], *, artifact: Path) -> None:
    for entry in entries:
        normalized = entry.name.lower()
        path = PurePosixPath(normalized)
        if entry.name in FORBIDDEN_FILES or "museon_runtime" in path.parts:
            raise RuntimeError(f"{artifact.name} contains private runtime file: {entry.name}")
        if any(normalized.endswith(suffix) for suffix in FORBIDDEN_SUFFIXES):
            raise RuntimeError(f"{artifact.name} contains sensitive file type: {entry.name}")


def _assert_complete_skill(entries: list[ArchiveEntry], *, prefix: str, artifact: Path) -> None:
    names = {entry.name for entry in entries}
    source_files = {
        path.relative_to(ROOT / "skills" / "museon-cli").as_posix()
        for path in (ROOT / "skills" / "museon-cli").rglob("*")
        if path.is_file()
    }
    expected = {f"{prefix}/{relative}" for relative in source_files}
    missing = sorted(expected - names)
    if missing:
        raise RuntimeError(f"{artifact.name} is missing Agent Skill files: {missing}")


def _assert_no_private_content(
    entries: list[ArchiveEntry],
    *,
    artifact: Path,
) -> None:
    for entry in entries:
        for private_reference in PRIVATE_REFERENCES:
            if private_reference in entry.payload:
                label = private_reference.decode("utf-8", errors="replace")
                raise RuntimeError(
                    f"{artifact.name} contains private reference {label!r} in {entry.name}"
                )
        for label, pattern in SECRET_PATTERNS:
            if pattern.search(entry.payload):
                raise RuntimeError(f"{artifact.name} contains a possible {label} in {entry.name}")


def _assert_public_wheel_content(entries: list[ArchiveEntry], *, artifact: Path) -> None:
    _assert_no_private_content(entries, artifact=artifact)
    entry_points = next(
        (entry.payload.decode("utf-8") for entry in entries if entry.name.endswith(".dist-info/entry_points.txt")),
        "",
    )
    for command in ("museon", "museoncli"):
        if f"{command} = museoncli.main:main" not in entry_points:
            raise RuntimeError(f"{artifact.name} is missing the {command!r} console entry point")


def _repository_license_files() -> list[str]:
    return sorted(
        path.name
        for path in ROOT.iterdir()
        if path.is_file() and path.name.upper().startswith(("LICENSE", "COPYING"))
    )


def _assert_license_files_packaged(
    *,
    source_license_files: list[str],
    wheel_entries: list[ArchiveEntry],
    wheel: Path,
) -> None:
    if not source_license_files:
        raise RuntimeError("repository is missing a license file")

    wheel_names = {entry.name for entry in wheel_entries}
    missing_wheel = [
        name
        for name in source_license_files
        if not any(
            entry_name.endswith(f".dist-info/licenses/{name}")
            for entry_name in wheel_names
        )
    ]
    if missing_wheel:
        raise RuntimeError(
            f"{wheel.name} is missing packaged license metadata files: {missing_wheel}"
        )


def verify_dist(dist_dir: Path) -> None:
    wheels = sorted(dist_dir.glob("*.whl"))
    if len(wheels) != 1:
        raise RuntimeError(f"expected exactly one wheel in {dist_dir}; found {len(wheels)}")

    wheel = wheels[0]
    wheel_entries = _wheel_entries(wheel)
    _assert_no_forbidden_paths(wheel_entries, artifact=wheel)
    _assert_complete_skill(
        wheel_entries,
        prefix="museoncli/bundled_skills/museon-cli",
        artifact=wheel,
    )
    _assert_public_wheel_content(wheel_entries, artifact=wheel)

    _assert_license_files_packaged(
        source_license_files=_repository_license_files(),
        wheel_entries=wheel_entries,
        wheel=wheel,
    )

    print(f"verified public artifact: {wheel.name}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist-dir", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    verify_dist(args.dist_dir.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
