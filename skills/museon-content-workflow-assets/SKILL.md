---
name: museon-content-workflow-assets
description: "Create, list, inspect, and reuse Museon product, persona, format, topic, media, and other creative assets for social-media content workflows."
---

# Museon content workflow assets

Use for the `asset` and `product` domains and the reusable content model.

| Command family | Purpose |
| --- | --- |
| `museoncli asset ...` | Discover and manage reusable personas, formats, topics, media, and assets |
| `museoncli product ...` | Discover and manage promoted products and brand media |

## References

- [content-model-and-reuse.md](references/content-model-and-reuse.md): product/persona/format/topic
  semantics, deduplication, and evidence-to-asset workflow.
- Inspect `museoncli schema asset` or `museoncli schema product`, then the exact command schema,
  for every command's current inputs and examples.

## Cross-skill handoff

If source evidence is missing, use `museon-research`. When required assets are ready, hand off
to `museon-content-workflow-generation`; for account-bound pools, hand off to
`museon-content-workflow-social-account` or `museon-content-workflow-account-publish`.
