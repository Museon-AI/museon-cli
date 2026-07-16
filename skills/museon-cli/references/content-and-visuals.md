# Content and visuals

Read this reference for content replication, content analysis, image posts,
creative assets, or slideshow generation.

## Museon content model

- **Product**: what is promoted, including category, description, and brand
  media.
- **Persona**: who is speaking and the voice used in copy.
- **Format**: the repeatable hook, slide flow, proof pattern, caption style, and
  visual structure extracted from evidence.
- **Topic**: the subject or angle run through a format.
- **Generation**: one concrete output produced from format x topic x persona
  and, when relevant, product. The current primary shape is slideshow.

Use `museoncli asset +list` before creating near-duplicates. Use canonical IDs
from CLI responses when a command expects an asset reference.

## Replicate what works

1. Research the account or posts and identify outliers against the account's
   own baseline.
2. Extract a reusable format from the winning evidence. Inspect
   `museoncli schema asset.create`, then use the supported URL or media inputs.
3. Review the extracted format. Correct a poor extraction before generation.
4. Select or create the topic, persona, and optional product assets.
5. Inspect `museoncli schema generation.create`, prepare a dry run, explain the
   exact generation that will be created, and obtain explicit approval.
6. Start the generation and follow its returned run/status contract.
7. Deliver the ready-made `ref` plus grid or slide previews when complete.

If the user asks to generate an image post or slideshow but the workspace lacks
the required assets, do not simply refuse and do not ask for opaque asset IDs.
Explain the missing creative input in customer language, ask for a product or a
few reference posts, then prepare the asset changes for approval.

## Generation discipline

- Use `--notes` only for guidance specific to one generation; do not mutate
  reusable assets when the request is a one-off adjustment.
- Never pass placeholder IDs. Look up or create the required asset through an
  approved workflow.
- Treat each generation as immutable history. If the result fails or is
  unusable, diagnose it and create a new approved generation instead of
  rewriting the old record.
- For an in-progress generation, share the returned live `ref` immediately and
  honor `recommended_wakeup_delay_seconds` for the next check.
- For a completed slideshow, present the generation `ref` and available grid
  image or first one to two slide previews. Do not reduce the result to a UUID.

When the content is intended for a Museon-operated account, prefer generating
from that account's schedule item so its account, persona, product, format, and
topic context remain bound. Read
[publishing-and-accounts.md](publishing-and-accounts.md) before doing so.
