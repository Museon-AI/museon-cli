# Schedule plans

For cancellation use `+schedule-plan-preview --operation cancel-only`, present cancellable/protected counts, then after approval submit identical account IDs, cancel reason, token, idempotency key, and `--yes`. Do not supply build fields. `+schedule-plan-cancel` stops unfinished job work and never deletes already-created items.

For multi-account build/rebuild or more than one manual occurrence, inspect `museoncli schema account-publish.schedule-plan-preview`, run live preview, and present create/cancel/skip and per-account errors. After approval submit the same normalized request and opaque token, then poll only `+schedule-plan-status`. On preview drift, create a fresh preview. Copy full UUIDs, token, and normalized fields verbatim. Pass `--bgm-policy required`, not JSON. Reuse an idempotency key only for the same submission.

One plan permits at most 200 accounts and 5,000 total occurrences (unique accounts x days x unique daily slots). Reduce days or slots if exceeded.

Resolve handles once with bulk `social-account +list`, then preview directly. Do not preflight with per-account asset, BGM, schedule, or version loops. Generic `--dry-run` does not replace live preview. Do not use `/tmp` as job state or rescan accounts after submission.

With required BGM, an account lacking valid BGM must fail explicitly. On success, report per-account `bgm_bound_count` and `summary.bgm_bound` from status; never call other domains as post-write verification.

Anything leading to a live post requires an approved content/schedule plan unless the account is already explicitly delegated under approved autonomous configuration.
