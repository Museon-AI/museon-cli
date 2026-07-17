#!/usr/bin/env python3
"""Install the built wheel into a clean venv and exercise its public entry points."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _run(command: list[str], *, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        command,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    return result.stdout.strip()


def _parse_envelope(raw: str) -> dict[str, object]:
    payload = json.loads(raw.splitlines()[-1])
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        raise RuntimeError(f"unexpected CLI envelope: {payload!r}")
    return payload


def smoke_install(wheel: Path) -> None:
    if not wheel.is_file() or wheel.suffix != ".whl":
        raise RuntimeError(f"wheel not found: {wheel}")
    uv = shutil.which("uv")
    if not uv:
        raise RuntimeError("uv is required for the clean-install smoke test")

    with tempfile.TemporaryDirectory(prefix="museoncli-smoke-") as temporary:
        root = Path(temporary)
        venv = root / "venv"
        home = root / "home"
        _run([uv, "venv", "--seed", str(venv)])
        python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        command = venv / ("Scripts/museoncli.exe" if os.name == "nt" else "bin/museoncli")
        _run([uv, "pip", "install", "--python", str(python), str(wheel)])

        env = dict(os.environ)
        env.update(
            {
                "HOME": str(home),
                "USERPROFILE": str(home),
                "CODEX_HOME": str(home / ".codex"),
                "MUSEONCLI_CREDENTIAL_BACKEND": "file",
            }
        )
        version = _parse_envelope(_run([str(command), "version"], env=env))
        schema = _parse_envelope(_run([str(command), "schema"], env=env))
        _run([str(command), "--help"], env=env)
        installed = _parse_envelope(
            _run([str(command), "setup", "--agent", "codex"], env=env)
        )
        current = _parse_envelope(
            _run([str(command), "setup", "--agent", "codex"], env=env)
        )

        commands = schema.get("data", {}).get("commands", {})  # type: ignore[union-attr]
        command_count = sum(len(items) for items in commands.values())
        if command_count != 95:
            raise RuntimeError(f"expected 95 public commands, got {command_count}")
        installed_agents = installed.get("data", {}).get("agents", [])  # type: ignore[union-attr]
        current_agents = current.get("data", {}).get("agents", [])  # type: ignore[union-attr]
        if not installed_agents or installed_agents[0].get("status") != "installed":
            raise RuntimeError(f"Skill was not installed: {installed!r}")
        if not current_agents or current_agents[0].get("status") != "current":
            raise RuntimeError(f"Skill installation was not idempotent: {current!r}")
        skill = home / ".codex" / "skills" / "museon-cli" / "SKILL.md"
        if not skill.is_file():
            raise RuntimeError(f"installed Skill is missing: {skill}")

        version_data = version.get("data", {})
        print(
            "clean install smoke passed: "
            f"version={version_data.get('cli_version')} commands={command_count}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path)
    parser.add_argument("--dist-dir", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    wheel = args.wheel
    if wheel is None:
        wheels = sorted(args.dist_dir.resolve().glob("*.whl"))
        if len(wheels) != 1:
            raise RuntimeError(f"expected one wheel in {args.dist_dir}, found {len(wheels)}")
        wheel = wheels[0]
    smoke_install(wheel.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
