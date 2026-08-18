# Campaign lifecycle

## Mental model

A Campaign owns budget, policy, direction, multiple Persona Plans, decisions, signals, learnings, issues, and proposals. Plans can be created during setup; active/paused campaigns allow constrained plan evolution. Proposals remain operator-review objects. A rollout preflight freezes the observed proposal/coverage/testing matrix; confirmation persists immutable rollout intent and starts execution.

Issues represent intervention. Control reads supply effective controls plus concurrency tokens before needs-human decisions. Rule Learnings are authored memory distinct from automatic evaluation outcomes.

## Shortcuts

| Situation | Start with |
| --- | --- |
| Workspace triage | `museoncli agentic-campaign +overview` |
| Campaign detail | `museoncli agentic-campaign +get` |
| Decision context | `museoncli agentic-campaign +control-read` |
| Open proposals | `museoncli agentic-campaign proposal +list` |
| Rollout progress | `museoncli agentic-campaign +schedule-rollout-get` |
| Account-operation issues | `museoncli agentic-campaign +issues-pull` |

## DON'T

- **DON'T** create a Persona Plan after the campaign leaves setup.
- **DON'T** mix account reallocation with a Persona change in one proposal.
- **DON'T** assume only the newest independent proposal may be confirmed.
- **DON'T** reuse an idempotency/decision identity for a different intent.
- **DON'T** archive without explaining that all member account operations stop.
- **DON'T** confuse plan-list member IDs with account-operation IDs; those reads omit operation IDs.

## Relationships

Member execution is detailed in `member-account-operations.md`. Asset Persona ownership can block deletion; schedule rollout ultimately feeds the publishing system.
