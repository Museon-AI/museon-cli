# Visual generation

1. Select reviewed format, topic, persona, and optional product assets.
2. Inspect `museoncli schema generation.create`, prepare a dry run, explain the exact generation, and obtain explicit approval.
3. Start generation and follow its returned run/status contract.
4. Deliver the ready-made `ref` plus grid or slide previews when complete.

- Use `--notes` only for one-generation guidance; do not mutate reusable assets for a one-off adjustment.
- Never pass placeholder IDs. Look up or create required assets through an approved workflow.
- Treat each generation as immutable history. Diagnose a failed/unusable result and create a new approved generation rather than rewriting the old record.
- For in-progress generation, share the live `ref` immediately and honor `recommended_wakeup_delay_seconds`.
- For a completed slideshow, present the `ref` and available grid image or first one to two slide previews; do not reduce it to a UUID.

For a Museon-operated account, prefer generation from its schedule item so account, persona, product, format, and topic context remain bound.
