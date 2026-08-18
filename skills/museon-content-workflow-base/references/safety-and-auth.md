# Safety, authentication, and recovery

## Availability

Use `museoncli version` when CLI availability or version is genuinely in question. Do not perform version, health, authentication, and workspace checks before every task.

If neither `museoncli` nor `museon` exists, return to the base Skill's installation flow. Verify the installed command before resuming.

## Authentication recovery

Enter this flow only after `missing_auth`, `unauthorized`, or a missing-workspace error:

1. Run `museoncli auth start`.
2. Give the user `verification_uri_complete` exactly as returned; never expose the device code.
3. In the same turn run `museoncli auth finish --wait` (up to five minutes by default).
4. On timeout, keep the same URL visible and retry `museoncli auth finish` after approval.
5. If no workspace is selected, run `museoncli workspace list`; ask when several are plausible, then run `museoncli workspace select --id <workspace_id>`.
6. Resume the original task immediately.

Never ask the user to authenticate in another terminal when the Agent's environment needs the credentials.

## Risk policy

- `risk=read`: run when it directly serves the task.
- `risk=write`: describe the exact write, use `--dry-run` when useful, and wait for separate approval.
- `risk=destructive`: do the same, then add `--yes` only after approval.
- `execution=async_run`: retain the handle and use the matching status command.

Confirm the target and effect, not a vague "continue?". After writing, verify with a read command.

## Failure handling

| Reason | Response |
| --- | --- |
| `missing_auth` | Start authentication recovery. |
| `unauthorized` | Start fresh browser authorization, then retry. |
| `forbidden` | Explain that the identity lacks permission. |
| `invalid_input` | Inspect schema and correct arguments. |
| `not_found` | Recheck workspace and IDs. |
| `cli_outdated` | Follow upgrade detail, then retry. |
| `confirmation_required` | Obtain approval before retrying with `--yes`. |
| `service_unavailable` | Report availability honestly and retry later. |

Use useful `detail` for diagnosis, but never dump raw payloads or secrets into replies, logs, reports, or memory.
