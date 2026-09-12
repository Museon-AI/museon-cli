#!/usr/bin/env bash
# Prerequisites: bash, jq, configured museoncli. No polling or automatic new-key retry.
set -euo pipefail
[[ $# -eq 5 ]] || { echo 'usage: generate-media-once.sh WORKSPACE TYPE PROMPT KEY NEW_DIRECTORY' >&2; exit 2; }
workspace=$1
kind=$2
prompt=$3
key=$4
out=$5
umask 077
mkdir -- "$out"
jq -n --arg workspace "$workspace" --arg type "$kind" --arg prompt "$prompt" --arg key "$key" \
  '{workspace_id:$workspace,type:$type,prompt:$prompt,idempotency_key:$key}' > "$out/request.json"
museoncli media +generate --workspace-id "$workspace" --type "$kind" --prompt "$prompt" \
  --idempotency-key "$key" > "$out/receipt.json"
jq -e --arg w "$workspace" '.ok == true and .data.workspace_id == $w and (.data.task_id | type == "string")' "$out/receipt.json" >/dev/null
task=$(jq -r '.data.task_id' "$out/receipt.json")
media=$(jq -r '.data.media_id' "$out/receipt.json")
museoncli media +status --workspace-id "$workspace" --task-id "$task" > "$out/status.json"
jq -e --arg w "$workspace" --arg task "$task" --arg media "$media" \
  '.ok == true and .data.workspace_id == $w and .data.task_id == $task and .data.media_id == $media' "$out/status.json" >/dev/null
if jq -e '.data.status == "failed" or .data.status == "cancelled" or .data.phase == "unknown"' "$out/status.json" >/dev/null; then
  echo 'Generation has failed or is unknown; preserve this key and evidence. Do not resubmit with a new key.' >&2
  exit 3
fi
if ! jq -e '.data.status == "completed" and .data.phase == "completed" and .data.media_ready == true' "$out/status.json" >/dev/null; then
  jq -n --arg task "$task" '{status:"pending",task_id:$task,new_output_verified:false}'
  exit 0
fi
museoncli media +get --workspace-id "$workspace" --id "$media" > "$out/media.json"
jq -e --arg id "$media" --arg kind "$kind" \
  '.ok == true and .data.asset.id == $id and .data.asset.media_type == $kind and .data.asset.status == "completed" and (.data.asset.media_url | type == "string" and length > 0)' "$out/media.json" >/dev/null
jq -n --arg task "$task" --arg media "$media" '{status:"verified",task_id:$task,media_id:$media,new_output_verified:true}'
