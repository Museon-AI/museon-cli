#!/usr/bin/env python3
"""Build a PyInstaller onedir bundle from the exact reviewed Museon wheel."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import zipfile
from email.parser import BytesParser
from pathlib import Path

from distribution import (
    ROOT,
    TARGET_BY_NAME,
    NativeTarget,
    project_license_files,
    project_version,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalized_arch() -> str:
    value = platform.machine().lower()
    if value in {"amd64", "x86_64"}:
        return "x64"
    if value in {"aarch64", "arm64"}:
        return "arm64"
    return value


def _normalized_os() -> str:
    if sys.platform.startswith("linux"):
        return "linux"
    if sys.platform == "darwin":
        return "darwin"
    if sys.platform in {"win32", "cygwin"}:
        return "win32"
    return sys.platform


def detect_target() -> NativeTarget:
    os_name = _normalized_os()
    arch = _normalized_arch()
    suffix = "-gnu" if os_name == "linux" else ""
    name = f"{os_name}-{arch}{suffix}"
    target = TARGET_BY_NAME.get(name)
    if target is None:
        raise RuntimeError(f"unsupported native build host: {os_name}/{arch}")
    if os_name == "linux" and platform.libc_ver()[0].lower() != "glibc":
        raise RuntimeError("Linux native builds require glibc; musl artifacts are not supported")
    return target


def _validate_requested_target(requested: str) -> NativeTarget:
    detected = detect_target()
    if requested == "auto":
        return detected
    target = TARGET_BY_NAME.get(requested)
    if target is None:
        raise RuntimeError(f"unknown target {requested!r}; choose from {sorted(TARGET_BY_NAME)}")
    if target != detected:
        raise RuntimeError(
            f"requested target {target.target} does not match this host ({detected.target}); "
            "cross-compilation is intentionally disabled"
        )
    return target


def _wheel_metadata(wheel: Path) -> tuple[str, str]:
    with zipfile.ZipFile(wheel) as archive:
        metadata_names = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
        if len(metadata_names) != 1:
            raise RuntimeError(f"expected one METADATA file in {wheel.name}")
        message = BytesParser().parsebytes(archive.read(metadata_names[0]))
        bundled_skill = "museoncli/bundled_skills/museon-cli/SKILL.md"
        if bundled_skill not in archive.namelist():
            raise RuntimeError(f"reviewed wheel is missing {bundled_skill}")
    return str(message["Name"] or ""), str(message["Version"] or "")


def verify_wheel(wheel: Path) -> dict[str, str]:
    if not wheel.is_file() or wheel.suffix != ".whl":
        raise RuntimeError(f"reviewed wheel not found: {wheel}")
    name, version = _wheel_metadata(wheel)
    expected = project_version()
    if name.lower() != "museoncli" or version != expected:
        raise RuntimeError(
            f"reviewed wheel metadata mismatch: name={name!r} version={version!r}; "
            f"expected museoncli {expected}"
        )
    return {"filename": wheel.name, "sha256": _sha256(wheel), "version": version}


def _run(command: list[str], *, cwd: Path | None = None) -> None:
    rendered = " ".join(command)
    print(f"+ {rendered}")
    subprocess.run(command, cwd=cwd, check=True)


def build_native(wheel: Path, output_root: Path, target: NativeTarget) -> Path:
    wheel_record = verify_wheel(wheel)
    uv = shutil.which("uv")
    if not uv:
        raise RuntimeError("uv is required to stage the reviewed wheel")

    output = output_root / target.target / "museoncli"
    if output.exists():
        shutil.rmtree(output)
    output.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="museoncli-native-") as temporary:
        workspace = Path(temporary)
        build_environment = workspace / "build-environment"
        requirements = workspace / "locked-requirements.txt"
        notices = workspace / "THIRD_PARTY_NOTICES.md"
        notices_manifest = workspace / "third-party-notices.json"
        entrypoint = workspace / "museoncli_entry.py"
        entrypoint.write_text("from museoncli.main import main\n\nmain()\n", encoding="utf-8")
        _run(
            [
                uv,
                "export",
                "--frozen",
                "--no-dev",
                "--group",
                "distribution",
                "--no-emit-project",
                "--format",
                "requirements.txt",
                "--output-file",
                str(requirements),
            ],
            cwd=ROOT,
        )
        _run([uv, "venv", "--python", sys.executable, str(build_environment)], cwd=workspace)
        build_python = build_environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        pyinstaller = build_environment / (
            "Scripts/pyinstaller.exe" if os.name == "nt" else "bin/pyinstaller"
        )
        _run(
            [
                uv,
                "pip",
                "install",
                "--python",
                str(build_python),
                "--requirement",
                str(requirements),
                str(wheel),
            ],
            cwd=workspace,
        )
        _run(
            [
                str(build_python),
                str(ROOT / "scripts" / "generate_third_party_notices.py"),
                "--output",
                str(notices),
                "--manifest",
                str(notices_manifest),
            ],
            cwd=workspace,
        )

        command = [
            str(pyinstaller),
            "--noconfirm",
            "--clean",
            "--onedir",
            "--name",
            "museoncli",
            "--distpath",
            str(workspace / "dist"),
            "--workpath",
            str(workspace / "work"),
            "--specpath",
            str(workspace / "spec"),
            "--collect-data",
            "museoncli",
            "--copy-metadata",
            "museoncli",
            "--collect-all",
            "keyring",
            "--copy-metadata",
            "keyring",
            "--collect-all",
            "certifi",
            "--collect-all",
            "yaml",
        ]
        if target.os == "win32":
            command.extend(["--collect-all", "tzdata"])
        command.append(str(entrypoint))

        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        print(f"+ {' '.join(command)}")
        subprocess.run(command, cwd=workspace, check=True, env=env)
        built = workspace / "dist" / "museoncli"
        executable = built / target.executable
        if not executable.is_file():
            raise RuntimeError(f"PyInstaller did not produce {target.executable}")
        shutil.copytree(built, output)
        shutil.copy2(notices, output / notices.name)
        for license_file in project_license_files():
            shutil.copy2(license_file, output / license_file.name)
        notices_summary = json.loads(notices_manifest.read_text(encoding="utf-8"))
        pyinstaller_version = subprocess.run(
            [str(pyinstaller), "--version"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    lock = ROOT / "uv.lock"
    build_record = {
        "format": 1,
        "package": "museoncli",
        "target": target.target,
        "version": project_version(),
        "wheel": wheel_record,
        "uv_lock_sha256": _sha256(lock),
        "pyinstaller": pyinstaller_version,
        "third_party_notices": {
            "filename": "THIRD_PARTY_NOTICES.md",
            "sha256": _sha256(output / "THIRD_PARTY_NOTICES.md"),
            "package_count": len(notices_summary["packages"]),
        },
    }
    (output / "museon-build.json").write_text(
        json.dumps(build_record, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    executable = output / target.executable
    if target.os != "win32":
        executable.chmod(executable.stat().st_mode | 0o111)
    print(
        f"built {target.target} from {wheel_record['filename']} "
        f"sha256={wheel_record['sha256']}: {output}"
    )
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--target", default="auto")
    parser.add_argument("--output-root", type=Path, default=ROOT / "build" / "native")
    args = parser.parse_args()
    target = _validate_requested_target(args.target)
    build_native(args.wheel.resolve(), args.output_root.resolve(), target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
