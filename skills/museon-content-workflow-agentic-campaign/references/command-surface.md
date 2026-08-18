# Agentic campaign command surface

This is a concise extraction of `museoncli/domains/agentic_campaign.py` CommandSpecs. Inspect exact schema before use.

## Rollouts and proposals

| Commands | Risk | Key semantics |
| --- | --- | --- |
| `+schedule-rollout-preflight`, `+schedule-rollout-get` | read | Preflight is required before first confirmation and whenever coverage/testing overrides change; get reads durable immutable rollout assignments and progress. |
| `+confirm-schedule-rollout` | write | Apply the same ready proposal/coverage/testing plan atomically; persist immutable intent; reuse its idempotency key only for retry; poll rollout get after 202. |
| `plan +members-reconcile` | write | Atomically reconcile plan members and matching budget with compare-and-swap. |
| `proposal +create/+revise/+reallocate` | write | Create/revise operator-review proposals; reallocation may mix with content but not persona change. |
| `proposal +list/+get` | read | List by plan/campaign or read revision guidance and annotation history. |
| `proposal +withdraw` | write | Permanently withdraw an unconfirmed open proposal; use named blocking proposal rather than resending a conflicted payload. |

## Campaign and plan lifecycle

| Commands | Risk | Key semantics |
| --- | --- | --- |
| `+campaign-create`, `+campaign-update`, `+campaign-rename` | write | Create or patch supported campaign setup/config/name fields. |
| `+plan-create`, `+plan-update` | write | Create plans only during setup; update allowed fields according to campaign state. |
| `+campaign-activate`, `+campaign-pause` | write | Resume or stop member account operations. |
| `+campaign-archive` | destructive | Cascades to stop all member operations; requires explicit confirmation and `--yes`. |
| `+list`, `+get`, `+plan-list`, `+plan-get`, `+plan-tags`, `+plan-attribution` | read | Campaign/plan detail, members, tags, and attribution with display-safe account identifiers. |

## Review and intervention

| Commands | Risk | Key semantics |
| --- | --- | --- |
| `+overview`, `+recap`, `+control-read` | read | Workspace overview, full campaign recap, and normalized controls/etags/version. |
| `+issue-decision`, `+issue-resolve`, `+issue-open` | write | Execute explicit human decisions, resolve ordinary issues with evidence, or manually open issues. |
| `+issues-pull` | write | Pull and lease issues for one required campaign using runtime conversation identity for lease/message context. |
| `+learning-add` | write | Add a human/Mel-authored rule learning distinct from automatic outcome entries. |
