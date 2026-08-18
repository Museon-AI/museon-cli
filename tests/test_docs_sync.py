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
    "museon-research", "museon-content-workflow-base", "museon-content-workflow-assets",
    "museon-content-workflow-generation", "museon-content-workflow-social-account",
    "museon-content-workflow-account-publish", "museon-content-workflow-campaign-monitor",
    "museon-content-workflow-routines",
    "museon-content-workflow-artifacts", "museon-content-workflow-agentic-campaign",
    "museon-content-workflow-evaluator",
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


def test_agent_skill_is_complete_and_portable() -> None:
    for name, skill_root in zip(SKILL_NAMES, SKILL_ROOTS, strict=True):
        skill = (skill_root / "SKILL.md").read_text(encoding="utf-8")
        assert skill.startswith(f"---\nname: {name}\n")
        assert len(skill.splitlines()) <= 60
        assert 'bins: ["museoncli"]' in skill
        assert "cliHelp:" in skill
        assert "TODO" not in skill
        assert "AskUserQuestion" not in skill
        if name != "museon-content-workflow-base":
            assert 'skills: ["museon-content-workflow-base"' in skill
            assert "**CRITICAL" in skill
        for heading in ("## Mental model", "## Shortcuts", "## DON'T", "## Relationships"):
            assert heading in skill
        linked_references = set(re.findall(r"\(references/([a-z0-9-]+\.md)\)", skill))
        actual_references = {path.name for path in (skill_root / "references").glob("*.md")}
        assert linked_references == actual_references
        for reference in (skill_root / "references").glob("*.md"):
            reference_text = reference.read_text(encoding="utf-8")
            for heading in ("## Mental model", "## Shortcuts", "## DON'T", "## Relationships"):
                assert heading in reference_text, reference

    base = ROOT / "skills" / "museon-content-workflow-base"
    base_skill = (base / "SKILL.md").read_text(encoding="utf-8")
    assert (base / "agents" / "openai.yaml").is_file()
    assert "uv tool install" in base_skill
    assert "museoncli version" in base_skill


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
