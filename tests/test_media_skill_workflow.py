"""Execute the packaged Bash example; unresolved ground truth cannot advance."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = "10000000-0000-4000-8000-000000000001"
TASK = "20000000-0000-4000-8000-000000000002"
MEDIA = "30000000-0000-4000-8000-000000000003"


@pytest.mark.parametrize(
    "scenario,count,success,verified",
    [
        ("pending", 2, True, False),
        ("unknown", 2, False, False),
        ("wrong_media", 3, False, False),
        ("complete", 3, True, True),
        ("write_failed", 1, False, False),
    ],
)
def test_bash_generation_requires_task_and_media_ground_truth(
    tmp_path, scenario, count, success, verified
):
    bash = shutil.which("bash")
    jq = shutil.which("jq") or (
        "/opt/homebrew/bin/jq" if Path("/opt/homebrew/bin/jq").exists() else None
    )
    if not bash or not jq:
        pytest.skip("Bash example requires bash and jq")
    record = {
        "task_id": TASK,
        "media_id": MEDIA,
        "workspace_id": WORKSPACE,
        "phase": "completed",
        "status": "completed",
        "media_ready": True,
    }
    responses = [
        {
            "ok": True,
            "data": {**record, "status": "pending", "phase": "queued", "media_ready": False},
        },
        {"ok": True, "data": dict(record)},
        {
            "ok": True,
            "data": {
                "asset": {
                    "id": MEDIA,
                    "media_type": "image",
                    "status": "completed",
                    "media_url": "gs://fixture/image",
                }
            },
        },
    ]
    if scenario == "pending":
        responses[1]["data"].update(status="pending", phase="polling", media_ready=False)
    if scenario == "unknown":
        responses[1]["data"].update(status="failed", phase="unknown", media_ready=False)
    if scenario == "wrong_media":
        responses[2]["data"]["asset"]["id"] = TASK
    if scenario == "write_failed":
        responses[0] = {"ok": False, "error": "pricing_unavailable"}
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"responses": responses, "calls": []}))
    fake = tmp_path / "museoncli"
    fake.write_text(f"""#!{sys.executable}
import json,os,sys
from pathlib import Path
sys.path.insert(0,{str(ROOT)!r})
from museoncli.main import build_parser,command_payload
args=build_parser().parse_args(sys.argv[1:])
payload=command_payload(args)
p=Path(os.environ["MEDIA_WORKFLOW_STATE"])
s=json.loads(p.read_text()); index=len(s["calls"])
s["calls"].append({{"command":args.domain_command,"arguments":payload}})
p.write_text(json.dumps(s)); response=s["responses"][index]
print(json.dumps(response)); sys.exit(0 if response["ok"] else 1)
""")
    fake.chmod(0o700)
    env = {
        **os.environ,
        "MEDIA_WORKFLOW_STATE": str(state),
        "PATH": os.pathsep.join([str(tmp_path), str(Path(jq).parent), os.environ.get("PATH", "")]),
    }
    result = subprocess.run(
        [
            bash,
            str(ROOT / "skills/museon-content-workflow-base/scripts/generate-media-once.sh"),
            WORKSPACE,
            "image",
            "A blue cup",
            "stable-key",
            str(tmp_path / "evidence"),
        ],
        env=env,
        text=True,
        capture_output=True,
    )
    assert (result.returncode == 0) == success, result.stderr
    calls = json.loads(state.read_text())["calls"]
    assert len(calls) == count
    assert calls[0]["arguments"] == {
        "type": "image",
        "prompt": "A blue cup",
        "model": "gpt-image-2.5-flare",
        "idempotency_key": "stable-key",
    }
    if success:
        assert json.loads(result.stdout)["new_output_verified"] is verified
