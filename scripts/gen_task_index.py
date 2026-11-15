#!/usr/bin/env python3
"""Render the task guide from contracts/task-index.yaml and the live registry.

Usage (from the standalone museon-cli repository root):
    uv run python scripts/gen_task_index.py          # rewrite the generated files
    uv run python scripts/gen_task_index.py --check  # exit 2 when they drift or the index is unsound

Outputs:
    skills/museon-content-workflow-base/references/task-index.md  (Agent Skill reference)
    docs/guide.md                                                 (release asset guide.md)
    docs/llms.txt                                                 (release asset llms.txt)

`museoncli guide` reads the same index at run time. tests/test_task_index.py enforces
sync and coverage in CI.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from museoncli import guide  # noqa: E402

OUTPUTS = {
    ROOT / "skills" / "museon-content-workflow-base" / "references" / "task-index.md": (
        guide.render_skill_reference
    ),
    ROOT / "docs" / "guide.md": guide.render_guide_markdown,
    ROOT / "docs" / "llms.txt": guide.render_llms_txt,
}


def main() -> int:
    check = "--check" in sys.argv
    problems = guide.validate()
    if problems:
        print("task index is unsound (contracts/task-index.yaml):")
        for problem in problems:
            print(f"  - {problem}")
        return 2
    drifted: list[Path] = []
    for path, render in OUTPUTS.items():
        expected = render()
        current = path.read_text(encoding="utf-8") if path.is_file() else None
        if current != expected:
            drifted.append(path)
            if not check:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(expected, encoding="utf-8")
    if check and drifted:
        print("task guide drift detected; run: uv run python scripts/gen_task_index.py")
        for path in drifted:
            print(f"  - {path.relative_to(ROOT)}")
        return 2
    if not check:
        print("task guide regenerated" if drifted else "task guide already in sync")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
