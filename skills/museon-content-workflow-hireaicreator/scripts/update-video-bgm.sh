#!/usr/bin/env bash
# Run only for an authorized BGM-only edit with an already selected BGM ID.
# Usage: bash update-video-bgm.sh WORKSPACE_ID VIDEO_ID BGM_ID NEW_TASK_DIRECTORY
set -euo pipefail

if [[ $# -ne 4 ]]; then
  echo "usage: $0 WORKSPACE_ID VIDEO_ID BGM_ID NEW_TASK_DIRECTORY" >&2
  exit 2
fi
workspace_id=$1
video_id=$2
bgm_id=$3
task_dir=$4
command -v museoncli >/dev/null
command -v jq >/dev/null
umask 077
mkdir -- "$task_dir"

# Preserve only the fields needed to prove this narrowly scoped modification.
projection='if .ok == true then
  {ok, data: (.data | {id, workspace_id, version, composition_bgm_id,
                      ai_hook_item_id, render_revision, status})}
  else {ok, reason, detail} end'
museoncli hireaicreator video +get --id "$video_id" |
  jq -e "$projection" > "$task_dir/before.json"
jq -e --arg wid "$workspace_id" --arg vid "$video_id" '
  .ok == true and .data.id == $vid and .data.workspace_id == $wid
  and (.data.version | type == "number") and .data.version >= 1
' "$task_dir/before.json" >/dev/null

if jq -e --arg bgm "$bgm_id" '.data.composition_bgm_id == $bgm' \
  "$task_dir/before.json" >/dev/null; then
  jq -n --arg id "$video_id" \
    '{status:"already_satisfied", video_id:$id, new_output_verified:false}'
  exit 0
fi

jq --arg bgm "$bgm_id" \
  '{expected_version:.data.version, composition_bgm_id:$bgm}' \
  "$task_dir/before.json" > "$task_dir/desired.json"

# A write failure exits here. Do not reset a version or replay an unknown write.
museoncli hireaicreator video +update --id "$video_id" \
  --args-file "$task_dir/desired.json" |
  jq -e "$projection" > "$task_dir/receipt.json"
jq -e --arg vid "$video_id" '
  .ok == true and .data.id == $vid and (.data.version | type == "number")
' "$task_dir/receipt.json" >/dev/null

museoncli hireaicreator video +get --id "$video_id" |
  jq -e "$projection" > "$task_dir/after.json"
jq -e -s --arg wid "$workspace_id" --arg vid "$video_id" --arg bgm "$bgm_id" '
  .[0] as $before | .[1] as $receipt | .[2] as $after |
  $after.ok == true and $after.data.id == $vid
  and $after.data.workspace_id == $wid
  and $after.data.composition_bgm_id == $bgm
  and $after.data.ai_hook_item_id == $before.data.ai_hook_item_id
  and $after.data.version == $receipt.data.version
  and $after.data.version > $before.data.version
' "$task_dir/before.json" "$task_dir/receipt.json" "$task_dir/after.json" >/dev/null

jq -n --arg id "$video_id" \
  '{status:"configuration_verified", video_id:$id, new_output_verified:false}'
