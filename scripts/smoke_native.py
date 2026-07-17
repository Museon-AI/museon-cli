#!/usr/bin/env python3
"""Exercise a PyInstaller onedir bundle and its bundled Agent Skill."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

from distribution import ROOT, TARGET_BY_NAME, project_version, reviewed_command_names


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run(command: list[str], *, env: dict[str, str]) -> str:
    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )
    if result.returncode:
        raise RuntimeError(
            f"native command failed ({result.returncode}): {command!r}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result.stdout.strip()


def _envelope(raw: str) -> dict[str, object]:
    payload = json.loads(raw.splitlines()[-1])
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        raise RuntimeError(f"unexpected native response: {payload!r}")
    return payload


def smoke(bundle: Path, executable_name: str) -> None:
    executable = bundle / executable_name
    if not executable.is_file():
        raise RuntimeError(f"native executable is missing: {executable}")
    record = json.loads((bundle / "museon-build.json").read_text(encoding="utf-8"))
    if record.get("version") != project_version():
        raise RuntimeError(f"native build record has the wrong version: {record!r}")
    notices = bundle / "THIRD_PARTY_NOTICES.md"
    notice_record = record.get("third_party_notices", {})
    if not notices.is_file() or notice_record.get("sha256") != _sha256(notices):
        raise RuntimeError("native third-party notices are missing or do not match the build record")
    if int(notice_record.get("package_count") or 0) < 1:
        raise RuntimeError("native third-party notices contain no package records")

    with tempfile.TemporaryDirectory(prefix="museoncli-native-smoke-") as temporary:
        home = Path(temporary)
        env = dict(os.environ)
        env.update(
            {
                "HOME": str(home),
                "USERPROFILE": str(home),
                "CODEX_HOME": str(home / ".codex"),
                "MUSEONCLI_CREDENTIAL_BACKEND": "file",
            }
        )
        version = _envelope(_run([str(executable), "version"], env=env))
        schema = _envelope(_run([str(executable), "schema"], env=env))
        _run([str(executable), "--help"], env=env)
        installed = _envelope(
            _run([str(executable), "setup", "--agent", "codex"], env=env)
        )
        current = _envelope(
            _run([str(executable), "setup", "--agent", "codex"], env=env)
        )

        commands = schema.get("data", {}).get("commands", {})  # type: ignore[union-attr]
        actual_name_list = [entry["name"] for items in commands.values() for entry in items]
        actual_names = frozenset(actual_name_list)
        if len(actual_names) != len(actual_name_list):
            raise RuntimeError("native command schema contains duplicate command names")
        expected_names = reviewed_command_names()
        if actual_names != expected_names:
            missing = sorted(expected_names - actual_names)
            unexpected = sorted(actual_names - expected_names)
            raise RuntimeError(
                "native command schema differs from the reviewed contract: "
                f"missing={missing!r} unexpected={unexpected!r}"
            )
        installed_agents = installed.get("data", {}).get("agents", [])  # type: ignore[union-attr]
        current_agents = current.get("data", {}).get("agents", [])  # type: ignore[union-attr]
        if not installed_agents or installed_agents[0].get("status") != "installed":
            raise RuntimeError(f"bundled Skill did not install: {installed!r}")
        if not current_agents or current_agents[0].get("status") != "current":
            raise RuntimeError(f"bundled Skill was not idempotent: {current!r}")
        version_data = version.get("data", {})
        if version_data.get("cli_version") != project_version():  # type: ignore[union-attr]
            raise RuntimeError(f"native version mismatch: {version!r}")
        print(f"native smoke passed: version={project_version()} commands={len(actual_names)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--target", default="auto")
    args = parser.parse_args()
    if args.target == "auto":
        from build_native import detect_target

        target = detect_target()
    else:
        target = TARGET_BY_NAME[args.target]
    bundle = args.bundle or ROOT / "build" / "native" / target.target / "museoncli"
    smoke(bundle.resolve(), target.executable)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
