---
name: museon-content-workflow-routines
description: "Create, inspect, approve, pause, resume, rebuild, or cancel Museon recurring routines and preserve durable automation memory across social-media runs."
---

# Museon routines workflow

Use for the `routines` domain and recurring automation memory.

| Command family | Purpose |
| --- | --- |
| `museoncli routines ...` reads | Inspect routines, triggers, ownership, and memory |
| `museoncli routines ...` writes | Draft/create/accept or lifecycle changes exposed by schema |

## References

- [recurring-automation.md](references/recurring-automation.md): outcome definition, approvals,
  ownership, lifecycle, and durable memory.
- Inspect `museoncli schema routines` and the exact shortcut before use.

## Cross-skill handoff

Use the relevant domain skill for the work a routine performs. Send shareable run outputs to
`museon-content-workflow-artifacts` and review evidence to campaign-monitor, social-account, or
account-operation according to the object.
