#!/usr/bin/env python3
"""Generate the portable Museon CLI command contract.

The CLI registry remains the source of truth. Other repositories consume the
generated JSON instead of importing ``museoncli`` at runtime.

Usage (from apps/museoncli):
    uv run python scripts/gen_command_contract.py
    uv run python scripts/gen_command_contract.py --check
    uv run python scripts/gen_command_contract.py --output ../api/app/contracts/agent_cli_command_catalog.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "contracts" / "command-catalog.json"

sys.path.insert(0, str(ROOT))

from museoncli import __version__  # noqa: E402
from museoncli.domains import command_specs, schema_payload  # noqa: E402


def build_contract() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "package": "museoncli",
        "contract_revision": __version__,
        "catalog": schema_payload(),
        "schemas": {spec.schema_name: schema_payload(spec.schema_name) for spec in command_specs()},
    }


def render_contract() -> str:
    return (
        json.dumps(
            build_contract(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Fail when the output has drifted.")
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Contract path. Defaults to contracts/command-catalog.json.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = args.output.resolve()
    expected = render_contract()

    if args.check:
        if not output.is_file() or output.read_text(encoding="utf-8") != expected:
            print(f"command contract drift detected: {output}")
            print(f"run: {Path(sys.executable).name} {Path(__file__).name} --output {output}")
            return 2
        print(f"command contract is in sync: {output}")
        return 0

    output.parent.mkdir(parents=True, exist_ok=True)
    if output.is_file() and output.read_text(encoding="utf-8") == expected:
        print(f"command contract already in sync: {output}")
        return 0
    output.write_text(expected, encoding="utf-8")
    print(f"command contract generated: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
