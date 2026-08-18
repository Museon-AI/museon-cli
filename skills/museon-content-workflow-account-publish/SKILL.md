---
name: museon-content-workflow-account-publish
description: "Preview and apply multi-account Museon asset-pool changes or schedule plans, including cancellation, BGM policy, idempotency, and per-account result review."
---

# Museon account publish workflow

Use for the `account-publish` domain and canonical multi-account publishing flows.

| Command family | Purpose |
| --- | --- |
| `+asset-pools-batch-get/+preview/+set/+status` | Read, preview, apply, and poll asset pools |
| `+schedule-plan-preview/+schedule-plan-batch/+schedule-plan-status` | Build, rebuild, or cancel schedules |
| `+schedule-plan-cancel` | Stop unfinished job work, not created schedule items |

## References

- [asset-pools.md](references/asset-pools.md): atomic pool configuration and retained snapshots.
- [schedule-plans.md](references/schedule-plans.md): preview tokens, cancellation, limits, BGM,
  idempotency, polling, and verification.
- Inspect `museoncli schema account-publish` and the exact shortcut before use.

## Cross-skill handoff

Resolve accounts with `museon-content-workflow-social-account`; create missing reusable inputs with
`museon-content-workflow-assets`; review published outcomes through social-account performance or
`museon-content-workflow-campaign-monitor` as appropriate.
