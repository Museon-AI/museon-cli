# HireAICreator warmup

Inspect each command with `museoncli schema hireaicreator.warmup-COMMAND`.
Use `--args-file` for nested configuration, and `--workspace-id` to select the
workspace explicitly. Omitted fields are not expanded into client defaults.

1. Run `warmup +readiness` for the intended account IDs and action type.
2. Run `warmup +create --args-file strategy.json --dry-run`, inspect the payload,
   then submit the same command without `--dry-run`. Creation produces a draft.
3. Read `warmup +get --id ID`, and use `+preview` to inspect blockers, candidates
   and format revisions. `+configure` requires the full configuration, while
   `+replace` additionally replaces the account assignments.
4. Use `+check-and-start --id ID --expected-version VERSION --args-file revisions.json
   --yes` only after authorizing automated generation/publication. Supply the
   preview's `expected_format_revisions` map to detect stale format snapshots.
   Read `started` and `preview.blocker_codes`; HTTP success need not mean started.
5. Page through `+accounts`, inspect `+account-stats`, and use existing `+journeys`
   plus `+journey-get` for per-cycle receipts and evidence. Missing metrics remain
   missing. Account pages expose reset blockers.
6. `+add-accounts` and `+remove-accounts` require the latest strategy version.
   `+activate`, `+pause`, and `+resume` also require the latest version and `--yes`.
   Pausing does not imply that already dispatched work was cancelled.
7. Use `+reset` only for explicitly selected account IDs after inspecting reset
   blockers. Before `+delete`, inspect `+deletion-preview`, then pass its version
   and `--yes`. Read back not-found and account participation after deletion.

All mutations support `--dry-run`, which makes no API call. Removal, lifecycle
transitions, check-and-start, reset and deletion require `--yes`. Preview and
readiness use POST but are read operations. The server exposes no idempotency
header for warmup. Do not invent one: after an uncertain create or reset,
reconcile list/detail/journey state before retrying. Never auto-refresh a stale
version and repeat a rejected write without reviewing the changed state.

The API uses workspace query parameters for reads, preview, check-and-start,
transitions and deletion; create/configuration/account mutations and reset place
workspace in the JSON body. Deletion's expected version is a query parameter.
These distinctions are covered by transport-level contract tests.
