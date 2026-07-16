#!/usr/bin/env python3
"""Generate the command tables in docs/ from the live registry.

Usage (from apps/museoncli):
    uv run python scripts/gen_command_docs.py          # rewrite docs in place
    uv run python scripts/gen_command_docs.py --check  # exit 2 when docs drift

The generated region sits between BEGIN/END markers; hand-written narrative
outside the markers is preserved. tests/test_docs_sync.py enforces sync in CI.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from museoncli.domains import command_specs, fixed_domain_values  # noqa: E402

MARKER_BEGIN = "<!-- BEGIN GENERATED COMMANDS (scripts/gen_command_docs.py) -->"
MARKER_END = "<!-- END GENERATED COMMANDS -->"
DOCS = [
    Path(__file__).resolve().parents[1] / "docs" / "domain-command-framework.md",
    Path(__file__).resolve().parents[1] / "docs" / "agent-discoverability.md",
]


def render_tables() -> str:
    lines: list[str] = [MARKER_BEGIN, ""]
    by_domain: dict[str, list] = {}
    for spec in command_specs():
        by_domain.setdefault(spec.domain.value, []).append(spec)
    total = sum(len(specs) for specs in by_domain.values())
    lines.append(
        f"{total} commands across {len(by_domain)} domains (source of truth: `museoncli schema`)."
    )
    lines.append("")
    for domain in fixed_domain_values():
        specs = by_domain.get(domain)
        if not specs:
            continue
        lines.append(f"### {domain}")
        lines.append("")
        lines.append("| command | risk | dry-run | confirm | execution | summary |")
        lines.append("|---|---|---|---|---|---|")
        for spec in specs:
            dry = "yes" if spec.supports_dry_run else "—"
            confirm = "`--yes`" if spec.requires_confirmation else "—"
            summary = spec.summary.replace("|", "\\|")
            lines.append(
                f"| `{domain} {spec.shortcut}` | {spec.risk_level} | {dry} "
                f"| {confirm} | {spec.execution} | {summary} |"
            )
        lines.append("")
    lines.append(MARKER_END)
    return "\n".join(lines)


def inject(path: Path, tables: str) -> str:
    text = path.read_text()
    begin = text.index(MARKER_BEGIN)
    end = text.index(MARKER_END) + len(MARKER_END)
    return text[:begin] + tables + text[end:]


def main() -> int:
    check = "--check" in sys.argv
    tables = render_tables()
    drifted: list[str] = []
    for path in DOCS:
        expected = inject(path, tables)
        if path.read_text() != expected:
            drifted.append(str(path))
            if not check:
                path.write_text(expected)
    if check and drifted:
        print("docs drift detected; run: uv run python scripts/gen_command_docs.py")
        for path in drifted:
            print(f"  - {path}")
        return 2
    if not check:
        print("docs regenerated" if drifted else "docs already in sync")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
