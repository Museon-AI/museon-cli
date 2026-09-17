# HireAICreator Test Group workflow

Use `museoncli schema hireaicreator.<resource>-<action>` before a command and pass
`--workspace-id` on every invocation, including follow-up turns in Codex or Mel.
The command catalog describes CLI support; the server still checks the caller's
capability and workspace/resource membership. A 403 is an authorization denial;
404 can indicate missing/inaccessible resources and 422 indicates invalid input.
Do not switch identity or interpret 404/422 as proof of missing capability.
For large responses, read the JSON file at `raw_result.path` and complete all
pages before selecting accounts or content.

## Prepare content and accounts

1. `test-plan +ensure` gets or creates the workspace plan (a write, with dry-run).
   `test-plan +update` edits its defaults. Retain the actual returned plan ID.
2. `content-group +list/+create/+update/+delete` manages named Hook, Recipe, BGM
   and POV collections. Use exact resource IDs, with no duplicate selections.
3. `test-group +list/+get/+overview` reads current groups and operational state.
   `+create` accepts `combinations` through `--args-file` or `--args-json`:
   `recipe` needs Hook/BGM/POV/Recipe groups; `hook-only` needs Hook/BGM/POV;
   `format` needs `format_ids`; `format-recipe` needs formats and a Recipe group.
   Formats cannot be combined with manual Hook/BGM/POV groups or hook timing.
   `category_selections` apply to recipe compositions. Read `+category-requirements`
   and `+category-options` before `+category-set`.
4. Read `account +eligibility` for the explicit account set and `test-group +accounts`
   for current assignments. `+accounts-set` replaces or appends, `+accounts-transfer`
   transfers accounts into the target group, and `+accounts-assign` applies the
   explicit set across selected groups. These writes require `--yes`; an empty
   replacement clears assignments. Read both affected groups after transfer.

## Schedule, preview and confirm

`test-group +schedule-set` sets persisted group dates, timezone and local HH:MM
publish times. Dates must be supplied together. Pass the freshly read
`updated_at` as `expected_updated_at`; after a 409, refresh and review changes.
The schedule endpoint permits omitting this concurrency guard, but automation
should supply it. `+content-set` requires the guard and chooses either nonempty
format IDs or all three manual Hook/POV/BGM lists. `+content-group-set` replaces
one group selection, `+hook-target` reads append constraints, and `+append-hooks`
changes the next run's inputs without rewriting existing runs.

Run `test-group +preview --test-group-id <uuid>` and inspect blockers, content
gaps, accounts and exact schedule. Preview's legacy timezone/time fields are
accepted by the API for compatibility; the persisted group schedule is the source
of truth. Supply the returned `match_fingerprint` to `test-run +confirm`, together
with `--idempotency-key` and `--yes`, only after the user's publishing intent is
established. Confirmation creates real scheduled work, not a draft. If inputs
changed, preview again; never invent a fingerprint.

Only `test-group +create` and `test-run +confirm` support server idempotency keys.
Reuse the same key only for retries of the same request. Other writes have no
server idempotency guarantee: read back before retrying after a timeout.
All writes support local `--dry-run`, which validates/prints the request without
contacting the server; it does not establish server authorization or readiness.

## Read results and stop work

Read `test-group +get` for runs, `+publishing` for totals/failures and
`+publishing-accounts` for paginated account results. A confirmation receipt does
not mean a post has published. Preserve missing metrics separately from zero.
`test-run +cancel` stops remaining work for one run; `test-group +cancel-schedule`
stops the group's remaining schedule. Both require `--yes` and cannot undo
published posts. `test-group +delete --yes` deletes a group; additionally using
`--force` cancels unpublished work. Review that destructive effect explicitly.
`content-group +delete --yes` removes a reusable group. Verify persisted state
after each mutation before dependent writes.
