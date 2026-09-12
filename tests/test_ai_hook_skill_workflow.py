"""A real Bash workflow must stop at failed/contradictory stage evidence."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/museon-content-workflow-hireaicreator/scripts/update-video-bgm.sh"
WORKSPACE = "10000000-0000-4000-8000-000000000001"
VIDEO = "20000000-0000-4000-8000-000000000002"
BGM = "30000000-0000-4000-8000-000000000003"


@pytest.mark.parametrize(
    "scenario,count,success",
    [
        ("verified", 3, True),
        ("already", 1, True),
        ("old_readback", 3, False),
        ("version_drift", 3, False),
        ("write_conflict", 2, False),
    ],
)
def test_actual_bash_stops_on_unproven_write(monkeypatch, tmp_path, scenario, count, success):
    bash = shutil.which("bash")
    jq = shutil.which("jq") or (
        "/opt/homebrew/bin/jq" if Path("/opt/homebrew/bin/jq").exists() else None
    )
    if not bash or not jq:
        pytest.skip("Bash workflow example requires bash and jq on this platform")
    before = {
        "id": VIDEO,
        "workspace_id": WORKSPACE,
        "version": 4,
        "composition_bgm_id": BGM if scenario == "already" else None,
        "ai_hook_item_id": "40000000-0000-4000-8000-000000000004",
        "status": "planned",
    }
    after = {**before, "composition_bgm_id": BGM, "version": 5}
    responses = [
        {"ok": True, "data": before},
        {"ok": True, "data": after},
        {"ok": True, "data": {**after}},
    ]
    if scenario == "old_readback":
        responses[-1]["data"]["composition_bgm_id"] = None
    if scenario == "version_drift":
        responses[-1]["data"]["version"] = 6
    if scenario == "write_conflict":
        responses[1] = {"ok": False, "reason": "version_conflict"}
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"responses": responses, "calls": []}))
    fake = tmp_path / "museoncli"
    fake.write_text(f"""#!{sys.executable}
import json, os, sys
from pathlib import Path
sys.path.insert(0, {str(ROOT)!r})
from museoncli.main import build_parser, command_payload
args = build_parser().parse_args(sys.argv[1:])
arguments = command_payload(args)
p = Path(os.environ['WORKFLOW_TEST_STATE'])
s = json.loads(p.read_text())
i = len(s['calls'])
s['calls'].append({{'command':args.domain_command,'arguments':arguments}})
p.write_text(json.dumps(s))
response = s['responses'][i]
print(json.dumps(response))
sys.exit(0 if response['ok'] else 1)
""")
    fake.chmod(0o700)
    env = {
        **os.environ,
        "WORKFLOW_TEST_STATE": str(state),
        "PATH": os.pathsep.join([str(tmp_path), str(Path(jq).parent), os.environ.get("PATH", "")]),
    }
    result = subprocess.run(
        [bash, str(SCRIPT), WORKSPACE, VIDEO, BGM, str(tmp_path / "task")],
        env=env,
        text=True,
        capture_output=True,
    )
    assert (result.returncode == 0) == success, result.stderr
    calls = json.loads(state.read_text())["calls"]
    assert len(calls) == count
    assert calls[0] == {"command": "hireaicreator.video-get", "arguments": {"id": VIDEO}}
    if count > 1:
        assert calls[1] == {
            "command": "hireaicreator.video-update",
            "arguments": {"id": VIDEO, "expected_version": 4, "composition_bgm_id": BGM},
        }
    if success:
        output = json.loads(result.stdout)
        assert output["new_output_verified"] is False
        assert output["status"] == (
            "already_satisfied" if scenario == "already" else "configuration_verified"
        )
