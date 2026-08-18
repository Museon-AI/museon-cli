# Member account operations

## Mental model

Submitting a pool account is the explicit account-publish → fully-managed transition under one active Persona Plan. Existing publish configuration is preserved; future scheduled items are adopted; in-flight generation/publishing finishes outside managed attribution. Research disposition decides whether the operation starts from an established seed or onboarding research.

One batch shares its Persona Plan and optional Product/CTA context. Per-account failures are isolated, while invalid Plan admission rejects atomically. Existing accounts may belong to another session/business/workspace/Product and remain unchanged. Operation stop is terminal cleanup of pending work, reservation, session, and campaign attachment.

## Shortcuts

| Situation | Start with |
| --- | --- |
| Enroll one account | `museoncli account-operation +submit` |
| Enroll several accounts | `museoncli account-operation +submit-batch` |
| One operation lifecycle/runs | `museoncli account-operation +get` |
| Known pool-account membership | `museoncli account-operation +ops-status-accounts` |
| Fleet capacity/intervention | `museoncli account-operation +ops-status` |
| Day-level schedule/publish gaps | `museoncli account-operation +daily-roster` |
| Remove from fully managed | `museoncli account-operation +stop` |

## DON'T

- **DON'T** use submit-batch as a read probe.
- **DON'T** report all accounts enrolled without inspecting failed and existing rows.
- **DON'T** silently move an operation from another session/business or switch its Product.
- **DON'T** mistake pending FIFO work for stuck work; use server-owned intervention/capacity signals.
- **DON'T** sample per-account runs to answer whole-fleet or whole-day questions.
- **DON'T** leave replaced originals running when the operator intended retirement.
- **DON'T** add research direction/benchmarks unless the operator supplied them.
- **DON'T** send one confirmation card per account for a batch; consolidate outcomes.

## Relationships

Persona Plan admission belongs to campaign state. Product/Persona truth comes from assets. Publish allocations transfer from account-publish; monitored public outcomes remain campaign-monitor data.
