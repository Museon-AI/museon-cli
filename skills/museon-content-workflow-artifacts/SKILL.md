---
name: museon-content-workflow-artifacts
description: "Validate, upload, share, and unshare durable Museon reports, strategies, reviews, schedules, and multi-result summaries."
metadata:
  requires:
    bins: ["museoncli"]
    skills: ["museon-content-workflow-base"]
  cliHelp: "museoncli schema artifacts"
---

# Museon artifacts workflow

**CRITICAL — first read [`../museon-content-workflow-base/SKILL.md`](../museon-content-workflow-base/SKILL.md).**

## Mental model

An Artifact is a durable file-backed deliverable with a private workspace link and optional public
share link. Validation is local and precedes upload. Resource `ref` values embed live Museon cards;
standalone social URLs embed players. See [artifact-lifecycle.md](references/artifact-lifecycle.md).

## Shortcuts

| Situation | Start with |
| --- | --- |
| Authoring contract | `museoncli skills +get` |
| Validate local Markdown | `museoncli artifacts +validate` |
| Publish/replace deliverable | `museoncli artifacts +upload` |
| Restore public access | `museoncli artifacts +share` |
| Revoke public access | `museoncli artifacts +unshare` |

## DON'T

- **DON'T** create an Artifact for short Q&A, one caption, status, or incomplete input.
- **DON'T** upload before local validation succeeds and separate approval is obtained.
- **DON'T** hand-write Museon resource URLs, file paths, or storage paths as embeds.
- **DON'T** omit either returned link when both public and private links exist.
- **DON'T** make a report private unless the user explicitly requests it.
- **DON'T** include secrets or raw customer payloads.

## Relationships

Other Skills produce evidence, generations, routines, and reviews. Artifacts packages those results
for retention and sharing without taking ownership of their source workflows.
