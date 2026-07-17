"""Drift guards for generated docs, prompts, and the installable Agent Skill."""

from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from pathlib import Path

from museoncli.domains import command_specs

ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "skills" / "museon-cli"
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
    skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")

    assert skill.startswith("---\nname: museon-cli\n")
    assert "TODO" not in skill
    assert "museon-research-task" not in skill
    assert "museon-social-media-workflow" not in skill
    assert "AskUserQuestion" not in skill
    assert (SKILL_ROOT / "agents" / "openai.yaml").is_file()
    assert "uv tool install" in skill
    assert "museoncli version" in skill

    linked_references = set(re.findall(r"\(references/([a-z0-9-]+\.md)\)", skill))
    actual_references = {path.name for path in (SKILL_ROOT / "references").glob("*.md")}
    assert linked_references == actual_references


def test_agent_skill_mentions_only_registered_commands() -> None:
    registered = {spec.schema_name for spec in command_specs()}
    for doc in SKILL_ROOT.rglob("*.md"):
        unknown = sorted(_mentioned_commands(doc.read_text(encoding="utf-8")) - registered)
        assert unknown == [], f"{doc.relative_to(ROOT)} references unknown commands: {unknown}"


def test_install_docs_offer_versioned_official_source_fallback() -> None:
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    version = metadata["project"]["version"]
    source = f"git+https://github.com/Museon-AI/museon-cli.git@v{version}"
    docs = (
        ROOT / "docs" / "install.md",
        ROOT / "README.md",
        ROOT / "README.zh-CN.md",
        SKILL_ROOT / "SKILL.md",
    )

    for path in docs:
        text = path.read_text(encoding="utf-8")
        assert "uv tool install museoncli" in text, path
        assert source in text, path
        assert "museon-cli.git@main" not in text, path

    assert INSTALL_GUIDE_URL in (ROOT / "README.md").read_text(encoding="utf-8")
    assert INSTALL_GUIDE_URL in (ROOT / "README.zh-CN.md").read_text(encoding="utf-8")
