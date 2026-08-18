---
name: museon-content-workflow-account-operation
description: "Inspect and manage Museon fully managed account-fleet operations, runs, attribution, lifecycle interventions, batch submissions, and stop operations."
---

# Museon account operation workflow

Use for the `account-operation` domain.

| Command family | Purpose |
| --- | --- |
| `museoncli account-operation ...` reads | Fleet lifecycle, runs, attribution, and intervention state |
| `museoncli account-operation ...` writes | Schema-exposed single or batch managed operations |

## References

- [managed-operations.md](references/managed-operations.md): preflight state, batch behavior,
  per-row reporting, and stop approval.
- Inspect `museoncli schema account-operation` and the exact shortcut before use.

## Cross-skill handoff

Use `museon-content-workflow-social-account` to resolve account state,
`museon-content-workflow-campaign-monitor` for monitored content, and
`museon-content-workflow-agentic-campaign` when operations belong to a Persona Plan.
