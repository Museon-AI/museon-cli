---
name: museon-content-workflow-generation
description: "Generate Museon image posts and slideshows from reusable creative assets, then track immutable generation progress and present result previews."
metadata:
  requires:
    bins: ["museoncli"]
    skills: ["museon-content-workflow-base", "museon-content-workflow-assets"]
  cliHelp: "museoncli schema generation"
---

# Museon content workflow generation

**CRITICAL — first read [`../museon-content-workflow-base/SKILL.md`](../museon-content-workflow-base/SKILL.md).**

## Mental model

A Generation is immutable history produced from Format, Topic, Persona, and optional Product.
Creation starts asynchronous work; get/list expose live state, a ready-made `ref`, and completed
grid/slide previews. See [generation-lifecycle.md](references/generation-lifecycle.md).

## Shortcuts

| Situation | Start with |
| --- | --- |
| Create image-post/slideshow | `museoncli generation +create` |
| Follow one generation | `museoncli generation +get` |
| Find prior generations | `museoncli generation +list` |

## DON'T

- **DON'T** refuse generation or request asset IDs when inputs are missing; prepare assets first.
- **DON'T** rewrite a failed/unusable Generation; diagnose and create a new approved one.
- **DON'T** hide an in-progress result until completion; return its live `ref` immediately.
- **DON'T** invent polling cadence; honor the returned wakeup delay.
- **DON'T** reduce completed work to a UUID when grid/slide previews exist.

## Relationships

Assets are mandatory upstream judgment; account-publish owns schedule-bound generation context;
evaluator scores finished output; artifacts embeds returned `ref` values verbatim.
