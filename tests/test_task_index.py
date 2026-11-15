"""The task guide stays true to the command registry and in sync with its renderings."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from museoncli import guide
from museoncli.domains import Domain, discoverable_command_specs
from museoncli.domains._discovery import DOMAIN_HELP

ROOT = Path(__file__).resolve().parents[1]


def _run(*argv: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ, MUSEON_JSON_OFFLOAD_ENABLED="false", MUSEONCLI_UPDATE_CHECK="0")
    return subprocess.run(
        [sys.executable, "-c", "from museoncli.main import main; main()", *argv],
        capture_output=True,
        encoding="utf-8",
        env=env,
        check=False,
    )


def test_index_names_only_registered_commands_and_places_every_command() -> None:
    """A renamed or removed command breaks its task; a new command must be placed."""
    assert guide.validate() == []


def test_gotchas_do_not_restate_what_the_registry_owns() -> None:
    """Whether a command needs --yes comes from its spec; a note saying so would drift."""
    for _chapter, task in guide.tasks():
        for command, note in guide._steps(task):
            assert "--yes" not in note, (task["id"], command)


def test_generated_guide_files_are_in_sync() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "gen_task_index.py"), "--check"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_every_task_renders_with_usage_risk_and_summary() -> None:
    specs = {spec.schema_name: spec for spec in discoverable_command_specs()}
    for _chapter, task in guide.tasks():
        detail = guide.lookup(task["id"])
        assert detail["kind"] == "task"
        for step in detail["steps"]:
            assert step["usage"].startswith("museoncli ")
            assert step["risk"] in {"read", "write", "destructive"}
            assert step["summary"]
            spec = specs.get(step["command"])
            if spec is not None:
                assert step["needs_yes"] is spec.requires_confirmation
                assert " --yes" not in step["usage"]


def test_guide_cli_overview_task_and_search_are_stable() -> None:
    overview = _run("guide")
    assert overview.returncode == 0, overview.stderr
    payload = json.loads(overview.stdout)
    assert payload["ok"] is True
    chapter_ids = [chapter["id"] for chapter in payload["data"]["chapters"]]
    assert chapter_ids[:2] == ["start", "ugc"]
    assert _run("guide").stdout == overview.stdout

    task = json.loads(_run("guide", "ugc-approve-applications").stdout)
    commands = [step["command"] for step in task["data"]["steps"]]
    assert "ugc.enrollment-approve" in commands

    english = json.loads(_run("guide", "--search", "approve", "application").stdout)
    assert english["data"]["tasks"][0]["id"] == "ugc-approve-applications"
    chinese = json.loads(_run("guide", "--search", "审核视频").stdout)
    assert chinese["data"]["tasks"][0]["id"] == "ugc-review-content"
    renamed = json.loads(_run("guide", "--search", "creator-performance-get").stdout)
    assert renamed["data"]["commands"][0]["name"] == "campaign-monitor.get-creator-performance"


def test_unknown_guide_id_is_not_found() -> None:
    result = _run("guide", "approve-everything")
    assert result.returncode == 3
    payload = json.loads(result.stdout)
    assert payload["reason"] == "not_found"
    assert "museoncli guide --search" in payload["error"]["message"]


def test_schema_compact_drops_contracts_and_search_ranks_commands() -> None:
    compact = json.loads(_run("schema", "ugc", "--compact").stdout)["data"]
    entry = compact["commands"][0]
    assert set(entry) == {"name", "usage", "risk_level", "requires_confirmation", "summary"}
    found = json.loads(_run("schema", "--search", "approve", "application").stdout)["data"]
    assert found["commands"][0]["name"] == "ugc.enrollment-approve"


def test_every_domain_says_what_it_is_for_in_help() -> None:
    assert [domain.value for domain in Domain if not DOMAIN_HELP.get(domain.value)] == []
