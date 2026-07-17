#!/usr/bin/env python3
"""Verify generated or prepacked npm artifacts against the frozen package matrix."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import tarfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from distribution import (
    ROOT_PACKAGE,
    TARGETS,
    TARGET_BY_PACKAGE,
    project_license_files,
    project_version,
)


LIFECYCLE_SCRIPTS = {"preinstall", "install", "postinstall"}
SECRET_PATTERNS = (
    re.compile(rb"-----BEGIN (?:RSA |OPENSSH |EC |DSA )?PRIVATE KEY-----"),
    re.compile(rb"\b(?:github_pat_[A-Za-z0-9_]{20,}|gh[pousr]_[A-Za-z0-9]{20,})\b"),
)


@dataclass(frozen=True, slots=True)
class PackageArchive:
    name: str
    files: dict[str, bytes]
    modes: dict[str, int]


def _assert_safe_name(name: str) -> None:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or "" in path.parts:
        raise RuntimeError(f"npm artifact contains an unsafe path: {name}")


def _directory_archive(path: Path) -> PackageArchive:
    files: dict[str, bytes] = {}
    modes: dict[str, int] = {}
    for item in path.rglob("*"):
        if item.is_symlink():
            raise RuntimeError(f"npm package contains a symlink: {item}")
        if not item.is_file():
            continue
        name = item.relative_to(path).as_posix()
        _assert_safe_name(name)
        files[name] = item.read_bytes()
        modes[name] = item.stat().st_mode
    manifest = json.loads(files["package.json"])
    return PackageArchive(str(manifest["name"]), files, modes)


def _tarball_archive(path: Path) -> PackageArchive:
    files: dict[str, bytes] = {}
    modes: dict[str, int] = {}
    with tarfile.open(path, "r:gz") as archive:
        for member in archive.getmembers():
            if member.issym() or member.islnk():
                raise RuntimeError(f"npm tarball contains a link: {member.name}")
            if not member.isfile():
                continue
            name = PurePosixPath(member.name)
            if not name.parts or name.parts[0] != "package":
                raise RuntimeError(f"npm tarball member is outside package/: {member.name}")
            relative = PurePosixPath(*name.parts[1:]).as_posix()
            _assert_safe_name(relative)
            handle = archive.extractfile(member)
            if handle is None:
                raise RuntimeError(f"could not read npm tarball member: {member.name}")
            files[relative] = handle.read()
            modes[relative] = member.mode
    manifest = json.loads(files["package.json"])
    return PackageArchive(str(manifest["name"]), files, modes)


def _manifest(package: PackageArchive) -> dict[str, object]:
    value = json.loads(package.files["package.json"])
    if not isinstance(value, dict):
        raise RuntimeError(f"{package.name} package.json is not an object")
    return value


def _verify_common(package: PackageArchive) -> dict[str, object]:
    manifest = _manifest(package)
    if manifest.get("name") != package.name:
        raise RuntimeError(f"package name mismatch for {package.name}")
    if manifest.get("version") != project_version():
        raise RuntimeError(f"{package.name} is not version {project_version()}")
    scripts = manifest.get("scripts") or {}
    if not isinstance(scripts, dict):
        raise RuntimeError(f"{package.name} scripts must be an object")
    forbidden = sorted(LIFECYCLE_SCRIPTS.intersection(scripts))
    if forbidden:
        raise RuntimeError(f"{package.name} contains forbidden lifecycle scripts: {forbidden}")
    for name, payload in package.files.items():
        _assert_safe_name(name)
        for pattern in SECRET_PATTERNS:
            if pattern.search(payload):
                raise RuntimeError(f"{package.name} contains a possible secret in {name}")
    for license_file in project_license_files():
        if package.files.get(license_file.name) != license_file.read_bytes():
            raise RuntimeError(
                f"{package.name} is missing the approved project license {license_file.name}"
            )
    return manifest


def _verify_root(package: PackageArchive) -> None:
    manifest = _verify_common(package)
    if manifest.get("dependencies"):
        raise RuntimeError("root npm launcher must be dependency-free")
    optional = manifest.get("optionalDependencies")
    expected = {target.package: project_version() for target in TARGETS}
    if optional != expected:
        raise RuntimeError(f"root optional dependency matrix mismatch: {optional!r}")
    if manifest.get("bin") != {
        "museon": "bin/museon.cjs",
        "museoncli": "bin/museon.cjs",
    }:
        raise RuntimeError("root package must expose both museoncli and museon")
    notices = package.files.get("THIRD_PARTY_NOTICES.md", b"")
    if b"dependency-free CommonJS launcher" not in notices:
        raise RuntimeError("root npm package is missing its third-party notice statement")
    allowed_roots = {
        "package.json",
        "README.md",
        "THIRD_PARTY_NOTICES.md",
        "bin",
        "lib",
        *(path.name for path in project_license_files()),
    }
    unexpected = sorted(
        name for name in package.files if PurePosixPath(name).parts[0] not in allowed_roots
    )
    if unexpected:
        raise RuntimeError(f"root package contains files outside its public boundary: {unexpected}")
    launcher = package.files.get("lib/launcher.cjs", b"")
    if b"MUSEONCLI_DISTRIBUTION_CHANNEL" not in launcher or b"runtime download" in launcher.lower():
        raise RuntimeError("root launcher does not declare the npm distribution channel safely")


def _verify_platform(package: PackageArchive) -> None:
    manifest = _verify_common(package)
    target = TARGET_BY_PACKAGE[package.name]
    if manifest.get("dependencies") or manifest.get("optionalDependencies"):
        raise RuntimeError(f"{package.name} must not have runtime dependencies")
    if manifest.get("os") != [target.os] or manifest.get("cpu") != [target.cpu]:
        raise RuntimeError(f"{package.name} os/cpu metadata mismatch")
    expected_libc = [target.libc] if target.libc else None
    if manifest.get("libc") != expected_libc:
        raise RuntimeError(f"{package.name} libc metadata mismatch")
    allowed_roots = {
        "package.json",
        "README.md",
        "bin",
        *(path.name for path in project_license_files()),
    }
    unexpected = sorted(
        name for name in package.files if PurePosixPath(name).parts[0] not in allowed_roots
    )
    if unexpected:
        raise RuntimeError(f"{package.name} contains files outside its public boundary: {unexpected}")
    executable = f"bin/museoncli/{target.executable}"
    if not package.files.get(executable):
        raise RuntimeError(f"{package.name} is missing its native executable: {executable}")
    if target.os != "win32" and package.modes.get(executable, 0) & 0o111 == 0:
        raise RuntimeError(f"{package.name} native executable is not executable")
    build_record = json.loads(package.files.get("bin/museoncli/museon-build.json", b"{}"))
    notices = package.files.get("bin/museoncli/THIRD_PARTY_NOTICES.md", b"")
    notice_record = build_record.get("third_party_notices", {})
    if (
        build_record.get("target") != target.target
        or build_record.get("version") != project_version()
        or not re.fullmatch(r"[0-9a-f]{64}", str(build_record.get("wheel", {}).get("sha256", "")))
        or not notices
        or hashlib.sha256(notices).hexdigest() != notice_record.get("sha256")
        or int(notice_record.get("package_count") or 0) < 1
    ):
        raise RuntimeError(f"{package.name} has an invalid native build record")


def verify(packages: list[PackageArchive], *, require_all: bool) -> None:
    by_name: dict[str, PackageArchive] = {}
    for package in packages:
        if package.name in by_name:
            raise RuntimeError(f"duplicate npm package: {package.name}")
        by_name[package.name] = package
    expected = {ROOT_PACKAGE, *(target.package for target in TARGETS)}
    unknown = sorted(set(by_name) - expected)
    if unknown:
        raise RuntimeError(f"unexpected npm packages: {unknown}")
    if ROOT_PACKAGE not in by_name:
        raise RuntimeError(f"missing root npm package: {ROOT_PACKAGE}")
    if require_all and set(by_name) != expected:
        raise RuntimeError(f"npm package matrix is incomplete: missing {sorted(expected - set(by_name))}")
    _verify_root(by_name[ROOT_PACKAGE])
    for name in sorted(set(by_name) - {ROOT_PACKAGE}):
        _verify_platform(by_name[name])
    print(f"verified npm packages: {', '.join(sorted(by_name))}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-root", type=Path)
    parser.add_argument("--tarball-dir", type=Path)
    parser.add_argument("--allow-partial", action="store_true")
    args = parser.parse_args()
    if bool(args.package_root) == bool(args.tarball_dir):
        parser.error("provide exactly one of --package-root or --tarball-dir")
    if args.package_root:
        packages = [
            _directory_archive(path)
            for path in sorted(args.package_root.resolve().iterdir())
            if (path / "package.json").is_file()
        ]
    else:
        packages = [_tarball_archive(path) for path in sorted(args.tarball_dir.resolve().glob("*.tgz"))]
    verify(packages, require_all=not args.allow_partial)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
