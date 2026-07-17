#!/usr/bin/env python3
"""Publish prepacked npm packages platform-first with safe rerun integrity checks."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import subprocess
import tarfile
from pathlib import Path

from distribution import ROOT, ROOT_PACKAGE, TARGETS, project_version


def _manifest(tarball: Path) -> dict[str, object]:
    with tarfile.open(tarball, "r:gz") as archive:
        handle = archive.extractfile("package/package.json")
        if handle is None:
            raise RuntimeError(f"npm tarball is missing package.json: {tarball}")
        value = json.load(handle)
    if not isinstance(value, dict):
        raise RuntimeError(f"npm package manifest is invalid: {tarball}")
    return value


def _integrity(path: Path) -> str:
    digest = hashlib.sha512(path.read_bytes()).digest()
    return "sha512-" + base64.b64encode(digest).decode("ascii")


def _npm_version() -> tuple[int, ...]:
    result = subprocess.run(["npm", "--version"], check=True, capture_output=True, text=True)
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)", result.stdout.strip())
    if not match:
        raise RuntimeError(f"could not parse npm version: {result.stdout!r}")
    return tuple(int(part) for part in match.groups())


def publish(tarballs: list[Path]) -> None:
    if _npm_version() < (11, 5, 1):
        raise RuntimeError("npm 11.5.1 or newer is required for trusted publishing")
    by_name = {str(_manifest(path)["name"]): path for path in tarballs}
    expected = [*(target.package for target in TARGETS), ROOT_PACKAGE]
    if set(by_name) != set(expected):
        raise RuntimeError(
            f"npm publication matrix mismatch: missing={sorted(set(expected) - set(by_name))} "
            f"extra={sorted(set(by_name) - set(expected))}"
        )
    for name in expected:
        tarball = by_name[name]
        manifest = _manifest(tarball)
        version = str(manifest.get("version") or "")
        if version != project_version():
            raise RuntimeError(f"refusing to publish {name}@{version}; expected {project_version()}")
        spec = f"{name}@{version}"
        query = subprocess.run(
            ["npm", "view", spec, "dist.integrity", "--json"],
            check=False,
            capture_output=True,
            text=True,
        )
        existing = ""
        if query.returncode == 0 and query.stdout.strip():
            value = json.loads(query.stdout)
            if isinstance(value, str):
                existing = value
        local = _integrity(tarball)
        if existing:
            if existing != local:
                raise RuntimeError(
                    f"registry integrity mismatch for {spec}: registry={existing} local={local}"
                )
            print(f"identical npm package already exists: {spec}")
            continue
        subprocess.run(
            ["npm", "publish", str(tarball), "--access", "public", "--provenance"],
            check=True,
        )
        print(f"published npm package: {spec}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tarball-dir", type=Path, default=ROOT / "npm-dist")
    args = parser.parse_args()
    publish(sorted(args.tarball_dir.resolve().glob("*.tgz")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
