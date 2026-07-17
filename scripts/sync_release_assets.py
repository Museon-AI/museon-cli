#!/usr/bin/env python3
"""Upload missing release assets and reject non-identical existing assets."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _gh(*args: str, capture: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["gh", *args],
        check=True,
        text=True,
        capture_output=capture,
    )


def sync(tag: str, repository: str, assets: list[Path]) -> None:
    release = json.loads(
        _gh(
            "release",
            "view",
            tag,
            "--repo",
            repository,
            "--json",
            "assets",
            capture=True,
        ).stdout
    )
    existing = {asset["name"] for asset in release.get("assets", [])}
    names: set[str] = set()
    for asset in assets:
        if asset.name in names:
            raise RuntimeError(f"duplicate release asset name: {asset.name}")
        names.add(asset.name)
        if asset.name not in existing:
            _gh("release", "upload", tag, str(asset), "--repo", repository)
            print(f"uploaded release asset: {asset.name}")
            continue
        with tempfile.TemporaryDirectory(prefix="museoncli-release-asset-") as temporary:
            _gh(
                "release",
                "download",
                tag,
                "--repo",
                repository,
                "--pattern",
                asset.name,
                "--dir",
                temporary,
            )
            downloaded = Path(temporary) / asset.name
            if _sha256(downloaded) != _sha256(asset):
                raise RuntimeError(
                    f"release asset integrity mismatch for {asset.name}; refusing to overwrite"
                )
        print(f"identical release asset already exists: {asset.name}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("assets", nargs="+", type=Path)
    args = parser.parse_args()
    assets = [path.resolve() for path in args.assets]
    missing = [str(path) for path in assets if not path.is_file()]
    if missing:
        raise RuntimeError(f"release assets are missing: {missing}")
    sync(args.tag, args.repository, assets)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
