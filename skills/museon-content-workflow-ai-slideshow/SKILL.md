---
name: museon-content-workflow-ai-slideshow
description: "Manage reusable slideshow assets, create explicit-asset slideshows, and publish completed slideshow generations to a selected social account with Museon CLI."
metadata:
  requires:
    bins: ["museoncli"]
    skills: ["museon-content-workflow-base"]
  cliHelp: "museoncli schema ai-slideshow"
---

# AI slideshow

**CRITICAL — first read [`../museon-content-workflow-base/SKILL.md`](../museon-content-workflow-base/SKILL.md).**

## Mental model

Use `asset` to manage reusable inputs and `generation` to create or inspect a slideshow from explicit format, topic, persona, and optional product assets. Generation is independent of accounts and schedules. Use `publish` only after a generation is `done` and its result media is present; the publish target account and timing belong to that stage.

Read [slideshow-lifecycle.md](references/slideshow-lifecycle.md) for the supported lifecycle, write/readback rules, and publishing completion facts.

## Shortcuts

| Situation | Start with |
| --- | --- |
| Find or maintain inputs | `museoncli ai-slideshow asset +list` |
| Generate from explicit assets | `museoncli ai-slideshow generation +create` |
| Inspect or change account asset pools | `museoncli ai-slideshow publish +asset-pools-batch-preview` |
| Preview or apply schedule plans | `museoncli ai-slideshow publish +schedule-plan-preview` |
| Inspect account publish configuration | `museoncli ai-slideshow publish +config-get` |

## DON'T

- **DON'T** bind generation to an account or schedule.
- **DON'T** treat generation creation or a batch job receipt as terminal success.
- **DON'T** add evaluator or CTA inputs, or bind generation itself to an account or schedule.

## Relationships

Use `museon-content-workflow-base` for media, account, artifact, and routine command details. Use `museon-content-workflow-hireaicreator` only for HireAICreator plans and videos; its generation facts are separate.
