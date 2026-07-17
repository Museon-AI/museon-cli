#!/usr/bin/env python3
"""Install the built wheel into a clean venv and exercise its public entry points."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def reviewed_command_names() -> frozenset[str]:
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    document = json.loads(
        (ROOT / "contracts" / "command-catalog.json").read_text(encoding="utf-8")
    )
    version = metadata["project"]["version"]
    if document.get("contract_revision") != version:
        raise RuntimeError("reviewed command contract version does not match the package")
    commands = document.get("catalog", {}).get("commands")
    if not isinstance(commands, dict):
        raise RuntimeError("reviewed command contract has no command catalog")
    names = [
        entry["name"]
        for entries in commands.values()
        for entry in entries
        if isinstance(entry, dict) and isinstance(entry.get("name"), str)
    ]
    if len(names) != sum(len(entries) for entries in commands.values()):
        raise RuntimeError("reviewed command contract contains an invalid command")
    if len(names) != len(set(names)):
        raise RuntimeError("reviewed command contract contains duplicate command names")
    return frozenset(names)


def _run(command: list[str], *, env: dict[str, str] | None = None) -> str:
    try:
        result = subprocess.run(
            command,
            check=True,
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"command failed: {command!r}\nstdout:\n{exc.stdout}\nstderr:\n{exc.stderr}"
        ) from exc
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
        actual_name_list = [entry["name"] for items in commands.values() for entry in items]
        actual_names = frozenset(actual_name_list)
        if len(actual_names) != len(actual_name_list):
            raise RuntimeError("installed command schema contains duplicate command names")
        expected_names = reviewed_command_names()
        if actual_names != expected_names:
            missing = sorted(expected_names - actual_names)
            unexpected = sorted(actual_names - expected_names)
            raise RuntimeError(
                "installed command schema differs from the reviewed contract: "
                f"missing={missing!r} unexpected={unexpected!r}"
            )
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
            f"version={version_data.get('cli_version')} commands={len(actual_names)}"
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
