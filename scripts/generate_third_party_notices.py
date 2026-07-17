#!/usr/bin/env python3
"""Generate deterministic license notices from the native build environment."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import re
import sys
from pathlib import Path


LICENSE_PREFIXES = ("LICENSE", "LICENCE", "COPYING", "NOTICE")


def _distribution_name(distribution: importlib.metadata.Distribution) -> str:
    return str(distribution.metadata.get("Name") or "unknown").strip()


def _license_files(distribution: importlib.metadata.Distribution) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    seen: set[str] = set()
    declared = {
        str(value).replace("\\", "/")
        for value in (distribution.metadata.get_all("License-File") or [])
    }
    for entry in distribution.files or []:
        relative = str(entry).replace("\\", "/")
        basename = Path(relative).name.upper()
        if relative not in declared and not basename.startswith(LICENSE_PREFIXES):
            continue
        source = Path(distribution.locate_file(entry))
        if not source.is_file() or relative in seen:
            continue
        seen.add(relative)
        text = source.read_text(encoding="utf-8", errors="replace").strip()
        if text:
            result.append((relative, text))
    return sorted(result)


def _python_license() -> tuple[str, str]:
    version_dir = f"python{sys.version_info.major}.{sys.version_info.minor}"
    candidates = (
        Path(sys.base_prefix) / "LICENSE.txt",
        Path(sys.base_prefix) / "LICENSE",
        Path(sys.base_prefix) / "lib" / version_dir / "LICENSE.txt",
        Path(sys.base_prefix) / "Lib" / "LICENSE.txt",
        Path(sys.prefix) / "LICENSE.txt",
        Path(sys.prefix) / "LICENSE",
    )
    for path in candidates:
        if path.is_file():
            return path.name, path.read_text(encoding="utf-8", errors="replace").strip()
    raise RuntimeError("the CPython runtime license file is missing")


def generate(output: Path, manifest: Path) -> dict[str, object]:
    python_license_name, python_license = _python_license()
    distributions = sorted(
        (
            distribution
            for distribution in importlib.metadata.distributions()
            if re.sub(r"[-_.]+", "-", _distribution_name(distribution).lower()) != "museoncli"
        ),
        key=lambda distribution: _distribution_name(distribution).lower(),
    )
    sections = [
        "# Museon CLI Third-Party Notices",
        "",
        "This file is generated from the locked native build environment. It covers",
        "the CPython runtime, the PyInstaller bootloader, and bundled Python packages.",
        "",
        f"## CPython {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "",
        f"Source license file: `{python_license_name}`",
        "",
        "```text",
        python_license,
        "```",
    ]
    package_records: list[dict[str, object]] = []
    for distribution in distributions:
        name = _distribution_name(distribution)
        version = str(distribution.version or "unknown")
        declared_license = str(
            distribution.metadata.get("License-Expression")
            or distribution.metadata.get("License")
            or "not declared in package metadata"
        ).strip()
        license_files = _license_files(distribution)
        if not license_files and declared_license == "not declared in package metadata":
            raise RuntimeError(f"{name} {version} has no discoverable license metadata or file")
        sections.extend(
            [
                "",
                f"## {name} {version}",
                "",
                f"Declared license: `{declared_license}`",
            ]
        )
        for relative, text in license_files:
            sections.extend(["", f"### `{relative}`", "", "```text", text, "```"])
        package_records.append(
            {
                "name": name,
                "version": version,
                "declared_license": declared_license,
                "license_files": [relative for relative, _ in license_files],
            }
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(sections).rstrip() + "\n", encoding="utf-8")
    summary: dict[str, object] = {
        "format": 1,
        "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "packages": package_records,
    }
    manifest.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    summary = generate(args.output.resolve(), args.manifest.resolve())
    print(
        f"generated third-party notices for {len(summary['packages'])} packages: "
        f"{args.output.resolve()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
