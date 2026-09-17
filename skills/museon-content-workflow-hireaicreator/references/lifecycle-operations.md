# Lifecycle operations

Read the live command schema before constructing JSON. CLI enum values use kebab
case. Resolve the intended workspace and exact account/resource IDs once, then
pass `--workspace-id` on commands that accept it. Resource-scoped video/plan
commands authorize the resource itself; verify the returned workspace. A shared
conversation's execution identity belongs to that target conversation, not to an
unrelated sender or source chat. Do not change credentials or tenant identity to
bypass a managed-auth rejection.

Continue within the user's existing authorization. Generation, account changes,
automated publishing and deletion are distinct operations. A request for download
links alone does not authorize scheduling. When the scope already authorizes the
operation, supply the command's `--yes`; do not create a redundant approval loop.
Use `--dry-run` to validate local payloads, and the named server preview to inspect
live blockers. A successful preview does not reserve state indefinitely.

## Test Groups and Runs

1. Discover existing groups with `test-group +list`, then `+get` / `+overview`.
   `test-plan +ensure` may create a plan, so use it only when creating/configuring
   a plan is within scope. `test-plan +update` edits its configuration.
2. Manage selected content with `content-group +list/+create/+update/+delete`
   and Test Group creation/content commands from the current schema. Preserve
   exact resource IDs and requested composition; do not send an entire GET object
   back as an update.
3. Read account eligibility and `test-group +accounts`. Use `+accounts-set`
   (append or replace), `+accounts-transfer`, or `+accounts-assign` according to
   the requested membership change. An empty replacement removes all members.
   Inspect source and destination membership and blockers after a transfer.
4. Set the schedule with `+schedule-set`, the observed `expected_updated_at`,
   explicit timezone and intended times. Then run `+preview`. Address its blockers
   and retain the preview inputs and `match_fingerprint`.
5. `test-run +confirm` creates a scheduled Run and requires publication authority,
   `--yes`, and a stable idempotency key. Supply the preview fingerprint to detect
   changed allocations. Read group overview, publishing state and child videos;
   confirmation is not proof of completed generation or publication.
6. For authorized cancellation, use `test-run +cancel` or
   `test-group +cancel-schedule` and read back remaining work. Published posts are
   not undone. Group deletion requires `--yes`; `force` can also cancel unpublished
   work and needs that scope in the user's instruction.

Do not promise uninterrupted migration when the service reports active-work
blockers. A transfer command's existence is not a guarantee that a particular
account is eligible. Keep partial successes and unchanged memberships explicit.

## Warmup

Read `warmup +list`, `+get`, `+accounts`, `+journeys`, `+journey-get` and
`+account-stats` for current configuration, participation, evidence and blockers.
Complete pagination. Historical journey outcomes differ from current membership.

For a new plan, run `+readiness` on exact accounts, then `+create` with account
IDs/timezones, content, onboarding/termination rules and publish time. Read the
draft and its version. `+configure` replaces required configuration fields;
`+replace` also replaces account assignments. `+add-accounts` and
`+remove-accounts` use the observed strategy version.

Run `+preview` and retain Format revisions. Use `+check-and-start` with the current
version and `expected_format_revisions` only when automated generation/publication
is authorized. Inspect both `started` and preview blockers: success can mean the
check completed without starting. `+activate`, `+pause` and `+resume` require the
current version and `--yes`. A paused strategy can still have dispatched work.

`+reset` applies only to selected account IDs; inspect account reset blockers first.
Before `+delete`, use `+deletion-preview` and its version. Neither reset nor creation
has an idempotency-header contract; reconcile uncertain outcomes before retrying.
Verify journey/version/status changes, not merely the command receipt.

## Formats

Use `format +tags`, `+list`, `+get` and `+warmup-readiness` for discovery and readiness.
`+patch` supports name, BGM, POV and viral playbook. Supply the observed
`expected_version`; the API permits omission but then cannot detect a caller's
stale view. Empty `viral_playbook_override` explicitly clears the manual override;
null and omission do not clear BGM/POV links.

`+retry` accepts one processing step: ingest, hook, pov, bgm or viral. It requires
`--yes` and may incur processing work; inspect the step's status/error before
retrying and poll the same Format afterward. Retry/delete expose no version or
idempotency header. `+delete` requires `--yes`; its 204 receipt has no JSON data.
Verify not-found without recreating the deleted Format.

## Videos, generation and delivery

`video +create` supports standalone Actor/Persona and account-derived identity,
and Hook-only, Demo, Clips or Demo-only compositions. Actor mode is unscheduled;
account mode can be unscheduled for manual delivery or explicitly scheduled.
Clips require the selected account, campaign and clip rules. Format inputs provide
linked creative context; use actual schema and readiness for BGM requirements.
Creation does not start generation automatically.

Use current versions and stable keys for `video +generate`, component
`+ai-hook-regenerate`, `+pov-regenerate`, `+text-overlay-regenerate`,
`+caption-regenerate`, or `+bulk-regenerate`. Use candidate commands followed by
inspection and `+candidates-commit` when comparing alternatives. Do not regenerate
unaffected content for a BGM-only or caption-only correction. Cancel generation
only when requested; cancellation is not a successful generation result.

`+review` / `+bulk-review` record review decisions with confirmation. `+render`
and `+retry-render` request rendering; `+render-get` verifies render progress.
`delivery +export` / `+export-batch` require current versions; retain every export
ID and use `+export-get` until completed or failed. Batch success is per item.
Download and inspect dimensions, playback, text, identity and audio when delivering
finished media; an export receipt alone cannot establish creative quality.

For scheduling use authorized video updates/bulk scheduling, then read the same
IDs and scheduled instants. `calendar +month/+day` help verify the intended scope;
respect truncation and missing data. `video +cancel`, `+delete` and `+bulk-delete`
affect existing work and require their declared confirmations/versions. Read back
results and account for conflicts without refreshing versions and overwriting.

Create a share only for the intended audience and selection. Re-read collection
membership, confirm matching exports and check the actual download page/QR.
Shares have no general idempotency guarantee; reconcile a timeout rather than
blindly rotating or creating another public capability. Generation, exported
files, delivered links and externally published posts are separate completion facts.
