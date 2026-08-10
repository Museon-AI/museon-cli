#!/usr/bin/env python3
"""Check local dependencies for the social-media-hook-analyze Skill."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from typing import Any

REQUIRED_SCHEMAS = (
    "research.social-media-hook-analyze",
    "research.social-media-hook-analyze-poll",
    "research.social-media-hook-analyze-results",
)


def _run(
    command: list[str], *, stdin: str | None = None, keep_success_detail: bool = False
) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            input=stdin,
            text=True,
            capture_output=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ready": False, "detail": str(exc)}
    detail = (completed.stdout or completed.stderr).strip()
    ready = completed.returncode == 0
    result: dict[str, Any] = {"ready": ready}
    if detail and (not ready or keep_success_detail):
        result["detail"] = detail[-500:]
    return result


def check_setup() -> dict[str, Any]:
    ego_command = shutil.which("ego-browser")
    cli_command = shutil.which("museoncli") or shutil.which("museon")

    ego = (
        {
            "ready": False,
            "command": None,
            "detail": "ego-browser is not installed or is not on PATH",
        }
        if ego_command is None
        else {
            "command": ego_command,
            **_run([ego_command, "nodejs"], stdin="cliLog('ego-browser ready')\n"),
        }
    )

    if cli_command is None:
        museon = {
            "ready": False,
            "command": None,
            "detail": "museoncli is not installed or is not on PATH",
            "schemas": {},
        }
    else:
        version = _run([cli_command, "version"], keep_success_detail=True)
        schemas = {
            schema: _run([cli_command, "schema", schema]) for schema in REQUIRED_SCHEMAS
        }
        museon = {
            "ready": version["ready"] and all(item["ready"] for item in schemas.values()),
            "command": cli_command,
            "version": version,
            "schemas": schemas,
        }

    ready = bool(ego["ready"] and museon["ready"])
    return {
        "setup_schema_version": "social-hook-setup.v1",
        "ready": ready,
        "dependencies": {"ego_browser": ego, "museon_cli": museon},
        "next_step": (
            "Start browser collection and asynchronous analysis."
            if ready
            else "Read references/setup.md and repair only the missing dependency."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    result = check_setup()
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2 if args.pretty else None)
    sys.stdout.write("\n")
    return 0 if result["ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
