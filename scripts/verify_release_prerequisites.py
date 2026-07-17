#!/usr/bin/env python3
"""Fail closed until legal and npm launch prerequisites are explicitly completed."""

from __future__ import annotations

import argparse
from pathlib import Path

from distribution import ROOT, npm_license


def verify(root: Path = ROOT) -> None:
    licenses = [
        path
        for path in root.iterdir()
        if path.is_file() and path.name.upper().startswith(("LICENSE", "COPYING"))
    ]
    if not licenses:
        raise RuntimeError(
            "release blocked: the repository license is an unresolved external decision; "
            "add the approved LICENSE before publishing"
        )
    license_value = npm_license()
    if not license_value or license_value.upper() == "UNLICENSED":
        raise RuntimeError(
            "release blocked: pyproject.toml must contain the approved non-UNLICENSED "
            "license metadata before npm packages are generated"
        )


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    verify()
    print(f"release prerequisites verified: license={npm_license()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
