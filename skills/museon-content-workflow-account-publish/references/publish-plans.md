# Publish pools and plans

## Mental model

Pool preview/set is one durable transaction family; schedule preview/batch is another. A pool change affects future plan previews, while existing schedule items retain their prior asset snapshot until explicitly rebuilt. Fully-managed accounts can be previewed but require explicit managed-operation impact approval.

Schedule cancellation has two distinct meanings: cancel-only plan operations remove eligible schedule items; job cancellation merely stops unfinished job work and does not roll back completed rows.

## Cancellation shape

Cancellation is the default reading of "delete / stop / cancel schedules". Preserve every
requested handle character-for-character: resolve the whole set once in one bulk account lookup,
which is the only source of missing or ambiguous handles, and report those rather than
autocorrecting, fuzzy-matching, or silently dropping one. Then run one cancel-only preview for
the resolved ids; it returns per-account schedule-state counts, not handle-resolution results.
That is exactly two bulk calls before approval, with no per-account reads. The confirmation
summary combines the unresolved handles with the preview's per-account counts.

## Sizes

One plan accepts at most 200 accounts and 5,000 total occurrences (unique accounts x days x
unique daily slots). Reduce days or slots when the budget is exceeded.

## Shortcuts

| Desired result | Start with |
| --- | --- |
| Complete five-pool audit, even one account | `museoncli account-publish +asset-pools-batch-get` |
| Atomic pool change | `museoncli account-publish +asset-pools-batch-preview` |
| Server-aware schedule conflict check | `museoncli account-publish +schedule-plan-preview` |
| Delete eligible schedule items | `museoncli account-publish +schedule-plan-preview` |

## DON'T

- **DON'T** use generic dry-run as a substitute for the live server preview.
- **DON'T** preflight a schedule plan with per-account asset, BGM, schedule, or version calls.
- **DON'T** assume a successful aggregate means every account succeeded.
- **DON'T** verify required BGM through other domains; status-owned binding counts are proof.
- **DON'T** use `/tmp` or a local rescan as durable job state.
- **DON'T** assume pool changes rewrite existing schedule snapshots.
- **DON'T** simulate cancellation with an empty schedule plan or a loop of single-item deletes.
- **DON'T** abbreviate, reconstruct, or regenerate account UUIDs or a preview token when handing
  the write on; copy them verbatim from the successful preview.

## Relationships

Pool resources come from assets; account identity comes from social-account; fully-managed transfer and account lifecycle belong to Agentic Campaign.
