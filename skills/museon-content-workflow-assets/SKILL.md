---
name: museon-content-workflow-assets
description: "Create, inspect, and reuse Museon products, personas, formats, topics, media, and Product CTA targets for social-media content workflows."
metadata:
  requires:
    bins: ["museoncli"]
    skills: ["museon-content-workflow-base"]
  cliHelp: "museoncli schema asset"
---

# Museon content workflow assets

**CRITICAL — first read [`../museon-content-workflow-base/SKILL.md`](../museon-content-workflow-base/SKILL.md).**

## Mental model

Product is what is promoted; Persona is the speaker; Format is reusable creative structure;
Topic is the angle; Media is reusable source material. Generation combines format × topic ×
persona × optional product without changing those reusable objects. Product CTA targets reference
media already owned by the asset domain. See [content-model.md](references/content-model.md).

## Shortcuts

| Situation | Start with |
| --- | --- |
| Find reusable objects | `museoncli asset +list` |
| Read several known formats | `museoncli asset +get-batch` |
| Discover canonical values | `museoncli asset +options` |
| Create reusable object | `museoncli asset +create` |
| Product CTA targets | `museoncli product +cta-target-list` |

## DON'T

- **DON'T** create near-duplicates before searching existing assets.
- **DON'T** loop `asset +get` for two or more known Format IDs; use the batch read.
- **DON'T** join multiple search concepts into one comma-separated search value.
- **DON'T** delete a Persona held by a live Persona Plan; replace/retire the plan relationship first.
- **DON'T** treat Product CTA target commands as media upload; create media assets upstream.
- **DON'T** ask customers for opaque asset IDs when creative input can be gathered in plain language.

## Relationships

Research supplies evidence for Formats/Topics; generation consumes assets; social-account and
account-publish bind them to publishing; Agentic Campaign Persona Plans hold Personas.
