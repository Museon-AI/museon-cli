---
name: museon-content-workflow-generation
description: "Generate Museon images, carousels, and slideshows from approved product, persona, format, and topic assets, then track and present generation results."
---

# Museon content workflow generation

Use for the `generation` domain and concrete visual outputs.

| Command family | Purpose |
| --- | --- |
| `museoncli generation +create` | Prepare and start a generation from reusable assets |
| `museoncli generation ...` | Read and follow generation status/results exposed by current schema |

## References

- [visual-generation.md](references/visual-generation.md): approval, immutability, async polling,
  previews, and account-bound generation.
- Inspect `museoncli schema generation` and the exact shortcut before every operation.

## Cross-skill handoff

If creative inputs are missing, use `museon-content-workflow-assets`. If content is intended for
a managed schedule, use `museon-content-workflow-account-publish`; evaluate finished output with
`museon-content-workflow-evaluator` when requested.
