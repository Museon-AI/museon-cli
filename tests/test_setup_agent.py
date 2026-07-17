from __future__ import annotations

from pathlib import Path

import pytest

from museoncli.setup_agent import _resolve_agents, install_agent_skill


def test_setup_agent_installs_and_verifies_codex_skill(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    codex_home = tmp_path / "codex"
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    first = install_agent_skill("codex")
    second = install_agent_skill("codex")

    destination = codex_home / "skills" / "museon-cli"
    assert first["agents"][0]["status"] == "installed"
    assert second["agents"][0]["status"] == "current"
    assert destination.joinpath("SKILL.md").is_file()
    assert destination.joinpath("agents", "openai.yaml").is_file()
    assert first["agents"][0]["digest"] == second["agents"][0]["digest"]


def test_setup_agent_auto_uses_detected_host(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    codex_home = tmp_path / "codex"
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setenv("CODEX_THREAD_ID", "thread-1")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    monkeypatch.delenv("CLAUDECODE", raising=False)
    monkeypatch.delenv("CURSOR_HOME", raising=False)
    monkeypatch.delenv("CURSOR_TRACE_ID", raising=False)

    result = install_agent_skill("auto")

    assert [item["agent"] for item in result["agents"]] == ["codex"]


def test_setup_agent_auto_active_marker_wins_over_other_existing_homes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    codex_home = tmp_path / "codex"
    claude_home = tmp_path / "claude"
    cursor_home = tmp_path / "cursor"
    claude_home.mkdir()
    cursor_home.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(claude_home))
    monkeypatch.setenv("CURSOR_HOME", str(cursor_home))
    monkeypatch.setenv("CODEX_THREAD_ID", "thread-1")
    monkeypatch.delenv("CLAUDECODE", raising=False)
    monkeypatch.delenv("CURSOR_TRACE_ID", raising=False)

    assert _resolve_agents("auto") == ["codex"]


def test_setup_agent_auto_uses_only_existing_home_when_no_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    codex_home = tmp_path / "codex"
    codex_home.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "missing-claude"))
    monkeypatch.setenv("CURSOR_HOME", str(tmp_path / "missing-cursor"))
    monkeypatch.delenv("CODEX_THREAD_ID", raising=False)
    monkeypatch.delenv("CLAUDECODE", raising=False)
    monkeypatch.delenv("CURSOR_TRACE_ID", raising=False)

    assert _resolve_agents("auto") == ["codex"]


def test_setup_agent_auto_requires_choice_for_multiple_existing_homes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    codex_home = tmp_path / "codex"
    claude_home = tmp_path / "claude"
    codex_home.mkdir()
    claude_home.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(claude_home))
    monkeypatch.setenv("CURSOR_HOME", str(tmp_path / "missing-cursor"))
    monkeypatch.delenv("CODEX_THREAD_ID", raising=False)
    monkeypatch.delenv("CLAUDECODE", raising=False)
    monkeypatch.delenv("CURSOR_TRACE_ID", raising=False)

    with pytest.raises(RuntimeError, match="Multiple Agent homes"):
        _resolve_agents("auto")


def test_setup_agent_all_keeps_all_supported_targets() -> None:
    assert _resolve_agents("all") == ["codex", "claude-code", "cursor"]


def test_setup_agent_refuses_unmanaged_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    codex_home = tmp_path / "codex"
    destination = codex_home / "skills" / "museon-cli"
    destination.mkdir(parents=True)
    destination.joinpath("SKILL.md").write_text("name: something-else\n", encoding="utf-8")
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    with pytest.raises(RuntimeError, match="unmanaged"):
        install_agent_skill("codex")
