# Publishing and accounts

Read this reference for account connection, configuration, scheduling,
publishing, profile changes, or fully managed account operation.

## Start with current state

Inspect the relevant command schemas, then read the account before proposing a
change:

- Use `museoncli social-account +list` or `museoncli social-account +get` to
  resolve the target account.
- For a small, precise read of exactly one account, use
  `museoncli social-account +assets-get`. For two or more accounts, or when one
  account needs a complete persona/product/format/topic/BGM pool inspection,
  use one `account-publish +asset-pools-batch-get` call; never loop the
  single-account command.
- Use `museoncli social-account +config-get` for publishing configuration.
- Use `museoncli social-account +schedule-list` and
  `museoncli social-account +schedule-get` for planned posts and generation
  status.

Never guess an account, schedule item, or workspace from a handle alone when a
write requires a canonical ID.

## Connect a user-owned account

1. Inspect `museoncli schema social-account.connect-link-create`.
2. State the platform and workspace that will receive a connection link, then
   obtain explicit approval for the write.
3. Run `museoncli social-account +connect-link-create` with the approved input.
4. Give the returned authorization URL to the user exactly as returned.
5. Use `museoncli social-account +connect-link-status` to verify completion.

Do not ask for passwords or platform credentials in chat.

## Configure, schedule, and publish

For a small, precise one-account binding edit, read with
`social-account +assets-get`, prepare the smallest patch, and write with
`social-account +assets-set`. When one account needs its complete
persona/product/format/topic/BGM pool configured atomically, the batch flow
below is valid and preferred even though the batch contains one account. The
single-account commands are not a multi-account fallback.

For multi-account asset-pool inspection or configuration:

1. Resolve every requested handle in one bulk `social-account +list` call.
2. Read all effective persona/product/format/topic/BGM pools with one
   `account-publish +asset-pools-batch-get` call. Its hydrated resource details
   are sufficient for structural and semantic audits; do not make per-account
   `+assets-get` calls or per-resource lookup loops.
3. Run `account-publish +asset-pools-batch-preview` with the uniform patch and,
   when needed, per-account precise overrides. Omit a field to leave it alone;
   use explicit `unchanged` in an account override to opt that account out of a
   uniform field change.
4. Present every changed/skipped/failed account and the existing-schedule
   impact. Fully-managed accounts fail per-account in v1; do not claim or seek
   an approval bypass. Wait for separate explicit user approval.
5. Submit the identical normalized patches and opaque preview token with
   `account-publish +asset-pools-batch-set --idempotency-key <stable_key> --yes`.
   Reuse the key only for a retry of the same submission.
6. Poll only `account-publish +asset-pools-batch-status` using the returned
   wakeup delay. Do not rescan accounts to verify the write. Inspect and report
   every failed and skipped row.

Never implement multi-account asset configuration by looping
`social-account +assets-get/+assets-set`, or through Python/shell scripts. If
the batch command is absent or outdated, report the runtime update requirement
instead of falling back. The batch applies to publish pools only; workspace
tags remain separate metadata.

After an asset-pool job succeeds, new schedule-plan previews automatically read
the latest pools. Existing schedule items retain their prior asset snapshot and
do not change silently; only run the separate schedule-plan rebuild flow when
the user asks to update existing schedules.

For multi-account build/rebuild or manually creating more than one schedule
occurrence, use the canonical `account-publish` batch flow. Activating one
existing publish-config version for one account with
`social-account +version-activate` remains valid because the server materializes
that version's schedule; it is not a manual single-occurrence loop. Inspect
`museoncli schema account-publish.schedule-plan-preview`, run the live preview,
and for replacements present its create/cancel/skip and per-account error
summary before approval. After approval, submit the same normalized request
with the preview's opaque `--preview-token` and
`account-publish +schedule-plan-batch --idempotency-key <stable_key> --yes`, then poll only
`account-publish +schedule-plan-status` using the returned wakeup delay. If the
server reports preview drift, fail closed and run a fresh preview; never reuse
or invent a token. Copy every full canonical account UUID, preview token, and
normalized plan field verbatim from the successful preview into the batch
submission; never abbreviate, reconstruct, or manually regenerate UUIDs or
tokens while delegating the write. Pass the CLI enum as
`--bgm-policy required`, not as a JSON object. Reuse an idempotency key only to retry the same submission;
use a new key for an intentional new job. One plan accepts at most 200 accounts
and 5,000 total occurrences (unique accounts x days x unique daily slots);
reduce days or slots when the total budget is exceeded.

Resolve all requested handles in one bulk `social-account +list` call and then
run the live schedule-plan preview directly. The preview already inspects each
account's current conflicts, bound formats/topics/products, and BGM
availability. Do not preflight a batch plan with per-account `+assets-get`,
`+bgm-asset-list`, `+schedule-list`, or publish-version calls, and do not
delegate instructions that perform those loops.

Never implement batch scheduling by looping `social-account +schedule-list`,
`+schedule-create`, or `+schedule-delete` in Python, shell, or repeated CLI
calls. Generic `--dry-run` only validates the local command shape; it does not
replace the live schedule-plan preview. Do not use `/tmp` as batch progress
state or rescan all accounts after submission. If the batch command is absent
or outdated, report the required runtime update instead of falling back to
single-item loops.

When the user requires music from each account's BGM pool, pass
`--bgm-policy required`. An account with no valid BGM must fail explicitly;
never silently create no-BGM occurrences. Final reporting must inspect all
failed and skipped accounts, not only an aggregate created count. After batch
submission, `account-publish +schedule-plan-status` is the only state source.
When a required-BGM job reaches `status: succeeded`, the server guarantees that
every created occurrence has a concrete BGM binding. Report the status payload's
per-account `bgm_bound_count` and `summary.bgm_bound` directly; never call
`social-account +schedule-list`, `social-account +bgm-asset-list`, `routines`,
or any other read as post-write verification.

Anything that can lead to a live post requires an approved content/schedule
plan, unless the account is already explicitly delegated for autonomous
publishing under an approved configuration. Never silently disable an approval
requirement.

Generate scheduled content with the schedule command exposed by the current
schema so account assets bind automatically. After publishing, resolve the
schedule item to the live post and return the post link when available.

## Performance provenance

`museoncli social-account +performance-get` prefers authorized channel data and
may fall back to public data. Read the returned `source` and label the
difference in customer-visible language. Do not describe an API limitation as a
sync delay or promise that unavailable historical data will appear later.

## Managed account operations

Use the `account-operation` domain only after reading the target accounts and
the exact command schemas. Batch operations should use the batch shortcut
exposed by the schema instead of repeating single-account writes.

Before submission, resolve niche, reference accounts, research direction, and
account conflicts. After submission, inspect created, failed, and existing
rows; never report a batch as fully successful without checking each category.
Stopping an operation is a separate terminal change and requires its own
explicit approval.
