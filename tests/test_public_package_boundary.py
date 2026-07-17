from __future__ import annotations

import json
from pathlib import Path

from museoncli.config import AuthState, stored_auth_fields

ROOT = Path(__file__).resolve().parents[1]


def test_private_host_prompt_is_not_part_of_the_public_package() -> None:
    assert not (ROOT / "museoncli" / "prompt.py").exists()
    assert not (ROOT / "museoncli" / "system.md").exists()


def test_runtime_does_not_link_to_private_distribution_surfaces() -> None:
    runtime = (ROOT / "museoncli" / "main.py").read_text(encoding="utf-8")
    for private_reference in (
        "museon-ai" + ".feishu.cn",
        "/admin" + "/cli",
        "Museon-AI/" + "museon/main/apps/web/public/cli",
    ):
        assert private_reference not in runtime


def test_generated_contract_hides_monorepo_implementation_paths() -> None:
    contract_path = ROOT / "contracts" / "command-catalog.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    serialized = json.dumps(contract, ensure_ascii=False)
    for private_reference in (
        "apps/" + "api",
        "apps/" + "agents",
        "gcs_path",
        "/admin" + "/",
    ):
        assert private_reference not in serialized


def test_agent_skill_is_available_before_cli_installation() -> None:
    skill = ROOT / "skills" / "museon-cli" / "SKILL.md"
    assert skill.is_file()
    assert "Install the CLI when needed" in skill.read_text(encoding="utf-8")


def test_public_auth_surface_only_persists_scoped_api_keys() -> None:
    assert set(AuthState.__dataclass_fields__) == {"expires_at", "user", "api_key"}
    assert stored_auth_fields() == ("api_key",)
    config_source = (ROOT / "museoncli" / "config.py").read_text(encoding="utf-8")
    assert "MUSEON_AUTH_TOKEN" not in config_source


def test_release_workflow_rejects_commits_outside_main() -> None:
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")

    assert "fetch-depth: 0" in workflow
    assert "refs/heads/main:refs/remotes/origin/main" in workflow
    assert 'git merge-base --is-ancestor "${GITHUB_SHA}" origin/main' in workflow
    assert "docs/install.md" in workflow
