from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tarfile
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
    skill = ROOT / "skills" / "museon-content-workflow-base" / "SKILL.md"
    assert skill.is_file()
    assert "Install the CLI when needed" in skill.read_text(encoding="utf-8")


def test_public_auth_surface_only_persists_scoped_api_keys() -> None:
    assert set(AuthState.__dataclass_fields__) == {
        "expires_at",
        "user",
        "api_key",
        "method",
        "provider",
        "managed_by",
        "secret_ref",
        "version",
        "persistable",
        "resolution_error",
    }
    assert stored_auth_fields() == ("api_key",)
    config_source = (ROOT / "museoncli" / "config.py").read_text(encoding="utf-8")
    assert "MUSEON_AUTH_TOKEN" not in config_source


def test_release_workflow_rejects_commits_outside_main() -> None:
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")

    assert "fetch-depth: 0" in workflow
    assert "refs/heads/main:refs/remotes/origin/main" in workflow
    assert 'git merge-base --is-ancestor "${GITHUB_SHA}" origin/main' in workflow
    assert "docs/install.md" in workflow


def test_release_workflow_uses_short_lived_credentials() -> None:
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )

    assert "actions/create-github-app-token@" in workflow
    assert "MUSEON_RUNTIME_APP_ID" in workflow
    assert "MUSEON_RUNTIME_APP_PRIVATE_KEY" in workflow
    assert "permission-contents: write" in workflow
    assert "MUSEON_RUNTIME_DISPATCH_TOKEN" not in workflow


def test_release_workflow_builds_one_wheel_before_privileged_publication() -> None:
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )
    build, publish = workflow.split("\n  publish:\n", 1)

    assert "uv build --wheel" in build
    assert "contents: write" not in build
    assert "contents: write" in publish
    assert "scripts/sync_release_assets.py" in publish
    assert "npm" not in workflow.lower()
    assert "native-signing" not in workflow
    assert "pyinstaller" not in workflow.lower()


def test_release_workflow_publishes_deterministic_skills_asset(tmp_path: Path) -> None:
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )
    first = tmp_path / "first.tar.gz"
    second = tmp_path / "second.tar.gz"
    command = [sys.executable, str(ROOT / "scripts" / "build_skills_archive.py")]

    subprocess.run([*command, "--output", str(first)], check=True)
    subprocess.run([*command, "--output", str(second)], check=True)

    assert hashlib.sha256(first.read_bytes()).digest() == hashlib.sha256(
        second.read_bytes()
    ).digest()
    with tarfile.open(first, "r:gz") as archive:
        members = archive.getmembers()
    top_level_skills = {
        member.name.split("/")[1]
        for member in members
        if member.name.startswith("skills/") and member.name.count("/") >= 1
    }
    assert len(top_level_skills) == 14
    assert "skills/museon-content-workflow-base/SKILL.md" in {
        member.name for member in members
    }
    assert "skills/museon-research/SKILL.md" in {member.name for member in members}
    assert "skills/experiment-brain/SKILL.md" in {member.name for member in members}
    assert "skills/social-media-hook-analyze/SKILL.md" in {
        member.name for member in members
    }
    assert "skills/social-media-hook-analyze/scripts/rank_hooks.py" in {
        member.name for member in members
    }
    assert not any(
        "__pycache__" in member.name or member.name.endswith((".pyc", ".pyo"))
        for member in members
    )
    assert all(
        member.mtime == 0
        and member.uid == 0
        and member.gid == 0
        and member.uname == "root"
        and member.gname == "root"
        for member in members
    )

    assert "uv run python scripts/build_skills_archive.py" in workflow
    assert "(cd release && sha256sum -- * > checksums.txt)" in workflow
    assert "skills_url: $skills_url" in workflow
    assert "skills_sha256: $skills_sha256" in workflow
