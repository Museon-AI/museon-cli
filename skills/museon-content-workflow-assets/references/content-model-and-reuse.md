# Content model and asset reuse

- **Product**: what is promoted, including category, description, and brand media.
- **Persona**: who is speaking and the voice used in copy.
- **Format**: the repeatable hook, slide flow, proof pattern, caption style, and visual structure extracted from evidence.
- **Topic**: the subject or angle run through a format.
- **Generation**: one concrete output from format x topic x persona and, when relevant, product. The current primary shape is slideshow.

Use `museoncli asset +list` before creating near-duplicates. Use canonical IDs from CLI responses when a command expects an asset reference.

## Replicate what works

1. Research the account or posts and identify outliers against the account's own baseline.
2. Extract a reusable format from winning evidence. Inspect `museoncli schema asset.create`, then use supported URL or media inputs.
3. Review the extracted format and correct poor extraction before generation.
4. Select or create topic, persona, and optional product assets.

If the workspace lacks required assets, do not ask for opaque IDs. Explain the missing creative input in customer language, ask for a product or reference posts, then prepare asset changes for approval.
