---
name: museon-content-workflow-evaluator
description: "List, inspect, create, update, and run Museon prompt-based evaluators against text, media, research, or generation output, then inspect evaluator runs."
---

# Museon evaluator workflow

Use only for the `evaluator` domain. Do not infer behavior beyond current CommandSpecs.

| Command family | Purpose |
| --- | --- |
| `+kind-list/+list/+get` | Discover evaluator kinds and definitions |
| `+create/+update` | Manage prompt-based evaluator definitions |
| `+run` | Evaluate text, media, research, or generation output |
| `+run-list/+run-get` | Inspect evaluator run history and detail |

## References

- [command-surface.md](references/command-surface.md): summaries, risk, inputs, role boundary,
  and dry-run semantics extracted from `evaluator.py`.
- Inspect `museoncli schema evaluator` and exact shortcut before use.

## Cross-skill handoff

Collect inputs through `museon-research` or `museon-content-workflow-generation`; return durable
evaluation reports through `museon-content-workflow-artifacts`.
