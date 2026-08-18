---
name: museon-content-workflow-agentic-campaign
description: "Create, inspect, activate, pause, archive, and evolve Museon Agentic Creative Campaigns, Persona Plans, proposals, rollouts, issues, controls, and learnings."
---

# Museon Agentic Creative Campaign workflow

Use only for the `agentic-campaign` domain. Do not infer behavior beyond the current schema.

| Command family | Purpose |
| --- | --- |
| Campaign `+create/+update/+activate/+pause/+archive/+rename/+list/+get` | Campaign lifecycle |
| Plan `+plan-create/+plan-update/+plan-list/+plan-get/+members-reconcile` | Persona Plans and members |
| `proposal +create/+list/+get/+revise/+reallocate/+withdraw` | Operator-review proposals |
| `+schedule-rollout-preflight/+confirm-schedule-rollout/+schedule-rollout-get` | Rollout preview, apply, status |
| `+overview/+recap/+control-read`, issue and learning commands | Review and intervention |

## References

- [command-surface.md](references/command-surface.md): current CommandSpec summaries, risk levels,
  rollout order, proposal semantics, issues, and learning.
- Inspect `museoncli schema agentic-campaign` and exact shortcut before use.

## Cross-skill handoff

Use `museon-content-workflow-account-operation` for account-operation detail,
`museon-content-workflow-generation` for standalone generation, and
`museon-content-workflow-evaluator` for evaluator definitions/runs outside campaign commands.
