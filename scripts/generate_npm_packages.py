#!/usr/bin/env python3
"""Generate root and native npm package trees from pyproject.toml."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from distribution import (
    ROOT,
    ROOT_PACKAGE,
    TARGETS,
    TARGET_BY_NAME,
    npm_license,
    project_license_files,
    project_version,
)


TEMPLATES = ROOT / "npm" / "templates"


def _write_manifest(path: Path, value: dict[str, object]) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _render_template(source: Path, destination: Path, replacements: dict[str, str]) -> None:
    text = source.read_text(encoding="utf-8")
    for key, value in replacements.items():
        text = text.replace("{{" + key + "}}", value)
    destination.write_text(text, encoding="utf-8")


def _copy_project_licenses(output: Path) -> list[str]:
    copied: list[str] = []
    for source in project_license_files():
        shutil.copy2(source, output / source.name)
        copied.append(source.name)
    return copied


def generate_root(output_root: Path) -> Path:
    version = project_version()
    output = output_root / "cli"
    if output.exists():
        shutil.rmtree(output)
    shutil.copytree(TEMPLATES / "root", output)
    license_files = _copy_project_licenses(output)
    _render_template(
        TEMPLATES / "root" / "README.md",
        output / "README.md",
        {"VERSION": version},
    )
    manifest: dict[str, object] = {
        "name": ROOT_PACKAGE,
        "version": version,
        "description": "Native Museon CLI launcher for AI-agent social media operations",
        "license": npm_license(),
        "type": "commonjs",
        "bin": {"museoncli": "bin/museon.cjs", "museon": "bin/museon.cjs"},
        "files": [
            "bin/**",
            "lib/**",
            "README.md",
            "THIRD_PARTY_NOTICES.md",
            *license_files,
        ],
        "engines": {"node": ">=18"},
        "optionalDependencies": {target.package: version for target in TARGETS},
        "publishConfig": {"access": "public"},
        "repository": {
            "type": "git",
            "url": "git+https://github.com/Museon-AI/museon-cli.git",
        },
    }
    _write_manifest(output / "package.json", manifest)
    launcher = output / "bin" / "museon.cjs"
    launcher.chmod(launcher.stat().st_mode | 0o111)
    return output


def generate_platform(output_root: Path, native_root: Path, target_name: str) -> Path:
    target = TARGET_BY_NAME[target_name]
    bundle = native_root / target.target / "museoncli"
    executable = bundle / target.executable
    if not executable.is_file():
        raise RuntimeError(f"native bundle is missing {executable}")
    record = json.loads((bundle / "museon-build.json").read_text(encoding="utf-8"))
    if record.get("version") != project_version():
        raise RuntimeError(f"native bundle version mismatch for {target.target}: {record!r}")

    output = output_root / target.target
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    shutil.copytree(bundle, output / "bin" / "museoncli")
    license_files = _copy_project_licenses(output)
    _render_template(
        TEMPLATES / "platform" / "README.md",
        output / "README.md",
        {"PACKAGE": target.package, "TARGET": target.target, "VERSION": project_version()},
    )
    manifest: dict[str, object] = {
        "name": target.package,
        "version": project_version(),
        "description": f"Museon CLI native bundle for {target.target}",
        "license": npm_license(),
        "os": [target.os],
        "cpu": [target.cpu],
        "files": ["bin/**", "README.md", *license_files],
        "publishConfig": {"access": "public"},
        "repository": {
            "type": "git",
            "url": "git+https://github.com/Museon-AI/museon-cli.git",
        },
    }
    if target.libc:
        manifest["libc"] = [target.libc]
    _write_manifest(output / "package.json", manifest)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", action="append", choices=sorted(TARGET_BY_NAME))
    parser.add_argument("--root-only", action="store_true")
    parser.add_argument("--native-root", type=Path, default=ROOT / "build" / "native")
    parser.add_argument("--output-root", type=Path, default=ROOT / "build" / "npm")
    args = parser.parse_args()
    output = args.output_root.resolve()
    output.mkdir(parents=True, exist_ok=True)
    generated = [generate_root(output)]
    if not args.root_only:
        targets = args.target or [target.target for target in TARGETS]
        generated.extend(
            generate_platform(output, args.native_root.resolve(), target) for target in targets
        )
    for package in generated:
        print(f"generated {package}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
