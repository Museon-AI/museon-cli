from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolated_agent_homes(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    # Skills installed on the developer's machine must not leak `_notice` into envelopes.
    home = tmp_path_factory.mktemp("agent-homes")
    for variable in ("CODEX_HOME", "CLAUDE_CONFIG_DIR", "CURSOR_HOME"):
        monkeypatch.setenv(variable, str(home / variable.lower()))
