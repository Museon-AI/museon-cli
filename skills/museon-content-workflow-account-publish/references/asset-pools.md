# Multi-account asset pools

1. Resolve all handles in one bulk `social-account +list` call.
2. Read effective persona/product/format/topic/BGM pools with one `account-publish +asset-pools-batch-get`; do not loop per-account reads.
3. Run `+asset-pools-batch-preview` with uniform patch and precise overrides. Omission preserves a field; explicit `unchanged` opts an account out.
4. Present changed/skipped/failed accounts and existing-schedule impact. Fully managed accounts fail per-account in v1; do not seek a bypass. Wait for separate approval.
5. Submit identical normalized patches and opaque token with `+asset-pools-batch-set --idempotency-key <stable_key> --yes`; reuse the key only for retrying the same submission.
6. Poll only `+asset-pools-batch-status` using the returned delay and report every failed/skipped row.

Never loop `social-account +assets-get/+assets-set` or use shell/Python as a fallback. If batch commands are absent/outdated, report the runtime update requirement. Batch applies to publish pools; workspace tags remain separate.

New schedule previews read latest pools. Existing schedule items retain prior snapshots; rebuild only when asked.
