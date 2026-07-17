#!/usr/bin/env python3
"""Prepack generated npm package trees without running lifecycle scripts."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

from distribution import ROOT


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-root", type=Path, default=ROOT / "build" / "npm")
    parser.add_argument("--output", type=Path, default=ROOT / "npm-dist")
    parser.add_argument("--package", action="append")
    args = parser.parse_args()
    npm = shutil.which("npm")
    if not npm:
        raise RuntimeError("npm is required")
    package_root = args.package_root.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    packages = [package_root / item for item in args.package] if args.package else sorted(
        path for path in package_root.iterdir() if (path / "package.json").is_file()
    )
    for package in packages:
        result = subprocess.run(
            [
                npm,
                "pack",
                "--ignore-scripts",
                "--json",
                "--pack-destination",
                str(output),
            ],
            cwd=package,
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(result.stdout)
        if not payload or not payload[0].get("filename"):
            raise RuntimeError(f"npm pack returned an unexpected result for {package}: {payload!r}")
        print(output / payload[0]["filename"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
