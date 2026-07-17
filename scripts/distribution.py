"""Shared, version-free distribution matrix for native and npm tooling."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ROOT_PACKAGE = "@museon/cli"


@dataclass(frozen=True, slots=True)
class NativeTarget:
    target: str
    package: str
    os: str
    cpu: str
    runner: str
    executable: str
    libc: str | None = None


TARGETS = (
    NativeTarget(
        "darwin-arm64",
        "@museon/cli-darwin-arm64",
        "darwin",
        "arm64",
        "macos-15",
        "museoncli",
    ),
    NativeTarget(
        "darwin-x64",
        "@museon/cli-darwin-x64",
        "darwin",
        "x64",
        "macos-15-intel",
        "museoncli",
    ),
    NativeTarget(
        "linux-arm64-gnu",
        "@museon/cli-linux-arm64-gnu",
        "linux",
        "arm64",
        "ubuntu-22.04-arm",
        "museoncli",
        "glibc",
    ),
    NativeTarget(
        "linux-x64-gnu",
        "@museon/cli-linux-x64-gnu",
        "linux",
        "x64",
        "ubuntu-22.04",
        "museoncli",
        "glibc",
    ),
    NativeTarget(
        "win32-x64",
        "@museon/cli-win32-x64",
        "win32",
        "x64",
        "windows-2025",
        "museoncli.exe",
    ),
    NativeTarget(
        "win32-arm64",
        "@museon/cli-win32-arm64",
        "win32",
        "arm64",
        "windows-11-arm",
        "museoncli.exe",
    ),
)
TARGET_BY_NAME = {target.target: target for target in TARGETS}
TARGET_BY_PACKAGE = {target.package: target for target in TARGETS}


def project_metadata() -> dict[str, object]:
    document = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return document["project"]


def project_version() -> str:
    return str(project_metadata()["version"])


def npm_license() -> str:
    value = project_metadata().get("license")
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, dict) and isinstance(value.get("text"), str):
        return str(value["text"]).strip() or "UNLICENSED"
    return "UNLICENSED"


def project_license_files() -> tuple[Path, ...]:
    return tuple(
        sorted(
            (
                path
                for path in ROOT.iterdir()
                if path.is_file() and path.name.upper().startswith(("LICENSE", "COPYING"))
            ),
            key=lambda path: path.name,
        )
    )
