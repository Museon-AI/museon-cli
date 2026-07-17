# Safety, authentication, and recovery

Read this reference when the CLI is unavailable, a command fails, the workspace
is missing, or a state-changing operation is planned.

## Availability

Use `museoncli version` when CLI availability or version is genuinely in
question. Do not perform version, health, authentication, and workspace checks
as unconditional preflight before every task.

If neither `museoncli` nor its `museon` alias exists, return to the Skill's
**Install the CLI when needed** section and follow that bootstrap flow. Verify
the installed command before resuming the original task.

## Authentication recovery

Enter this flow only after a task command returns `missing_auth`,
`unauthorized`, or a missing-workspace error:

1. Run `museoncli auth start`.
2. Give the user the returned `verification_uri_complete` exactly as returned.
   Never expose the device code or other credentials.
3. In the same turn, run:

   ```bash
   museoncli auth finish --wait
   ```

   This waits for up to five minutes by default. Use `--timeout <seconds>` only
   when the task needs a different limit.
4. If it times out, keep the same verification URL visible and retry
   `museoncli auth finish` after the user approves.
5. If no workspace is selected, run `museoncli workspace list`, ask the user
   when several plausible workspaces exist, then run
   `museoncli workspace select --id <workspace_id>`.
6. Resume the original task immediately after recovery.

Never ask the user to run the authentication command in a different terminal
when the Agent's environment is the environment that needs credentials.

## Risk policy

Inspect `museoncli schema <domain>.<shortcut>` and apply its metadata:

- `risk=read`: run when it directly serves the task.
- `risk=write`: describe the exact write, use `--dry-run` when useful, and wait
  for a separate explicit approval before the real call.
- `risk=destructive`: do the same, then add `--yes` only after approval.
- `execution=async_run`: retain the handle and use the matching status command.

Confirm the specific target and effect, not a vague "continue?". After the
write, verify using a read command and state whether the read-back matched.

## Failure handling

Use the JSON `reason` to choose the next step:

| Reason | Response |
| --- | --- |
| `missing_auth` | Start the authentication recovery flow. |
| `unauthorized` | Start a fresh browser authorization, then retry the original task. |
| `forbidden` | Explain that the current identity lacks permission. |
| `invalid_input` | Inspect the command schema and correct the arguments. |
| `not_found` | Recheck the selected workspace and IDs. |
| `cli_outdated` | Follow the returned upgrade detail, then retry. |
| `confirmation_required` | Obtain approval before retrying with `--yes`. |
| `service_unavailable` | Report availability honestly and retry later. |

Use the useful part of `detail` for diagnosis, but do not dump raw payloads or
secrets into the reply, logs, reports, or memory.
