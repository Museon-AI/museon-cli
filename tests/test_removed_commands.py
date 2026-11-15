"""A 1.x command name answers with its 2.0 replacement instead of an argparse choice list.

2.0 removed `campaign-monitor` and the Campaign commands of `ugc` with no aliases. An Agent
holding a 1.x Skill must learn the new command from the failure, and the Museon API must
still find a schema by the name a 1.x CLI knew it by (`removed_aliases` in the contract).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from museoncli.domains import command_specs
from museoncli.domains._removed import REMOVED_COMMANDS, REMOVED_GROUPS, REMOVED_KEYS
from museoncli.domains._shared import _spec_summary_payload

CAMPAIGN = "11111111-1111-4111-8111-111111111111"


def _cli(*argv: str) -> tuple[int, dict]:
    env = {**os.environ, "MUSEONCLI_UPDATE_CHECK": "0", "MUSEON_JSON_OFFLOAD_ENABLED": "false"}
    result = subprocess.run(
        [sys.executable, "-c", "from museoncli.main import main; main()", *argv],
        env=env,
        capture_output=True,
        encoding="utf-8",
        check=False,
    )
    return result.returncode, json.loads(result.stdout)


def test_every_replacement_exists_and_no_removed_name_still_runs() -> None:
    paths = {spec.cli_path.removeprefix("museoncli ") for spec in command_specs()}
    assert set(REMOVED_COMMANDS.values()) <= paths
    assert not set(REMOVED_COMMANDS) & paths
    assert {key.split(".")[0] for key in REMOVED_KEYS} == {"campaign-monitor", "ugc"}
    assert set(REMOVED_GROUPS.values()) <= {" ".join(path.split()[:-1]) for path in paths}


@pytest.mark.parametrize(
    ("argv", "replacement"),
    [
        (
            ["campaign-monitor", "+get-summary", "--id", CAMPAIGN],
            "museoncli campaign +get-summary",
        ),
        (["campaign-monitor", "+content-list", "--id", CAMPAIGN], "museoncli campaign content +list"),
        (["campaign-monitor", "agency-campaign", "+list"], "museoncli campaign +list"),
        (["ugc", "campaign", "+launch", "--id", CAMPAIGN, "--yes"], "museoncli campaign +launch"),
        (["ugc", "campaign-settings", "+get", "--campaign-id", CAMPAIGN], "museoncli campaign settings +get"),
        (["campaign-monitor"], "museoncli campaign"),
        (["ugc", "campaign-setup", "--help"], "museoncli campaign setup"),
    ],
)
def test_a_removed_command_names_its_replacement(argv: list[str], replacement: str) -> None:
    code, payload = _cli(*argv)

    assert code == 2
    assert payload["ok"] is False and payload["reason"] == "invalid_command"
    assert payload["error"]["replacement"] == replacement
    assert replacement in payload["error"]["message"]


def test_schema_of_a_removed_name_names_its_replacement() -> None:
    code, payload = _cli("schema", "campaign-monitor.get-creator-performance")

    assert code == 2
    assert payload["reason"] == "invalid_command"
    assert payload["error"]["replacement"] == "museoncli campaign creator +get-performance"


def test_a_command_that_stayed_is_untouched() -> None:
    code, payload = _cli("ugc", "enrollment", "+list", "--campaign-id", "not-a-uuid")

    assert payload["reason"] != "invalid_command", payload
    assert code != 0


def test_the_contract_lists_the_names_each_command_replaced() -> None:
    by_key = {spec.schema_name: _spec_summary_payload(spec) for spec in command_specs()}

    listed = {
        alias["capability_key"]: key
        for key, payload in by_key.items()
        for alias in payload.get("removed_aliases", [])
    }
    assert listed == REMOVED_KEYS
    assert {"campaign-monitor.agency-campaign-list", "ugc.campaign-list", "campaign-monitor.list"} <= {
        alias["capability_key"] for alias in by_key["campaign.list"]["removed_aliases"]
    }
