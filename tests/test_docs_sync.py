"""Drift guards for generated docs, prompts, and the installable Agent Skill."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from museoncli import __version__
from museoncli.domains import command_specs

ROOT = Path(__file__).resolve().parents[1]
SKILL_NAMES = (
    "museon-research",
    "museon-content-workflow-base",
    "museon-content-workflow-hireaicreator",
    "museon-content-workflow-ai-slideshow",
    "museon-content-workflow-campaign-monitor",
)
SKILL_ROOTS = tuple(ROOT / "skills" / name for name in SKILL_NAMES)
INSTALL_GUIDE_URL = "https://www.museon.ai/cli/install.md"


def _mentioned_commands(text: str) -> set[str]:
    return {
        f"{domain}.{shortcut}"
        for domain, shortcut in re.findall(r"museoncli ([a-z][a-z-]*) \+([a-z][a-z-]*)", text)
    }


def test_generated_command_docs_are_in_sync() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "gen_command_docs.py"), "--check"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_generated_command_contract_is_in_sync() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "gen_command_contract.py"), "--check"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_docs_mention_only_registered_commands() -> None:
    registered = {spec.schema_name for spec in command_specs()}
    for doc in (ROOT / "docs").glob("*.md"):
        text = doc.read_text(encoding="utf-8")
        mentioned = _mentioned_commands(text)
        unknown = sorted(mentioned - registered)
        assert unknown == [], f"{doc.name} references unregistered commands: {unknown}"


def test_agent_skill_mentions_only_registered_commands() -> None:
    registered = {spec.schema_name for spec in command_specs()}
    for skill_root in SKILL_ROOTS:
        for doc in skill_root.rglob("*.md"):
            unknown = sorted(_mentioned_commands(doc.read_text(encoding="utf-8")) - registered)
            assert unknown == [], f"{doc.relative_to(ROOT)} references unknown commands: {unknown}"


def test_install_docs_use_one_versioned_official_wheel() -> None:
    version = __version__
    wheel = (
        "https://github.com/Museon-AI/museon-cli/releases/download/"
        f"v{version}/museoncli-{version}-py3-none-any.whl"
    )
    docs = (
        ROOT / "docs" / "install.md",
        ROOT / "README.md",
        ROOT / "README.zh-CN.md",
        ROOT / "skills" / "museon-content-workflow-base" / "SKILL.md",
    )

    for path in docs:
        text = path.read_text(encoding="utf-8")
        assert text.count(wheel) == 1, path
        assert "npm install" not in text, path
        assert "archive/" not in text, path
        assert "museon-cli.git@main" not in text, path
        assert "/tree/main/" not in text, path
        assert "pypi" not in text.lower(), path

    assert INSTALL_GUIDE_URL in (ROOT / "README.md").read_text(encoding="utf-8")
    assert INSTALL_GUIDE_URL in (ROOT / "README.zh-CN.md").read_text(encoding="utf-8")
