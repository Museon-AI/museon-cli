#!/usr/bin/env python3
"""Create the exact native archive attached to a GitHub release."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from distribution import ROOT, TARGET_BY_NAME, project_version


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True, choices=sorted(TARGET_BY_NAME))
    parser.add_argument("--native-root", type=Path, default=ROOT / "build" / "native")
    parser.add_argument("--output", type=Path, default=ROOT / "native-dist")
    args = parser.parse_args()
    source = args.native_root.resolve() / args.target / "museoncli"
    if not source.is_dir():
        raise RuntimeError(f"native bundle is missing: {source}")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    base = output / f"museoncli-v{project_version()}-{args.target}"
    format_name = "zip" if TARGET_BY_NAME[args.target].os == "win32" else "gztar"
    archive = Path(
        shutil.make_archive(
            str(base),
            format_name,
            root_dir=source.parent,
            base_dir=source.name,
        )
    )
    print(archive)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
