# Daily-fulfillment Issue recovery

## Mental model

A fully-managed account that misses its daily promise raises an Issue. Recovery is a bounded,
claim-based SOP: pull a batch of claims, take exactly one safe action per claim, and report the
result before the claim's lease expires. The claim's own checkpoint/backfill evidence is the
source of truth about what already exists — recovery repairs delivery, it never re-decides
campaign strategy.

A reported SOP success means the bounded recovery action completed. It never means the daily
promise is fulfilled or a post was published; the fulfillment evaluator verifies and resolves
the Issue later.

One pull per wake. `has_more` belongs to the next sweep, not to a second pull in the same pass.

## Claim → action mapping

| Claim | Action | Repair rule |
| --- | --- | --- |
| `unscheduled` | `ensure-schedule` | If the claim's evidence already proves a covering schedule exists, report success on that evidence instead of creating a duplicate. |
| `generation_failed` | `recover-generation` | Retry only when the claim identifies exactly one current covering item and the failure is retryable. Never start a second run while one is pending. |
| `publish_failed` | `recover-publish` | Never substitute a replacement schedule or a fresh generation for publishing the claimed item. |

## Shortcuts

| Situation | Start with |
| --- | --- |
| Claim a bounded batch of Issues | `museoncli agentic-campaign +issues-pull --campaign-id <id> --limit 20` |
| Report one claim's outcome | `museoncli account-operation +issue-result` |
| Repair a specific account/item generation | `museoncli social-account +schedule-generate` |

## DON'T

- **DON'T** pull without the delegated `campaign_id`, or infer/replace/discover one.
- **DON'T** pull a second batch in the same pass, even when `has_more` is true.
- **DON'T** let a claimed Issue expire unreported; every claim gets exactly one result,
  including when no safe mutation exists.
- **DON'T** alter `issue_id` or `dispatch_key`, or surface internal operation ids.
- **DON'T** hand-write a schedule item for a fully-managed account.
- **DON'T** blind-retry validation, missing-asset, Persona, authorization, identity, permission,
  device, or terminal provider failures; report the blocker and request human help.
- **DON'T** invent assets or change campaign direction to unblock a backfill.
- **DON'T** paraphrase the enums: `ensure-schedule` / `recover-generation` / `recover-publish`
  and `succeeded` / `failed` / `no-change`. `--request-human` requires a concrete `--reason`.

## Relationships

Issues arise from campaign daily runs; the repair itself touches social-account schedule items.
Whole-fleet gaps are a roster question, not an Issue question.
