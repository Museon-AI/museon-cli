---
name: museon-content-workflow-account-publish
description: "Preview and apply Museon multi-account asset-pool changes and durable schedule plans, including replacement, cancellation, BGM, and result review."
metadata:
  requires:
    bins: ["museoncli"]
    skills: ["museon-content-workflow-base", "museon-content-workflow-assets"]
  cliHelp: "museoncli schema account-publish"
---

# Museon account publish workflow

**CRITICAL — first read [`../museon-content-workflow-base/SKILL.md`](../museon-content-workflow-base/SKILL.md).**

## Mental model

Asset pools define which Persona/Product/Format/Topic/BGM resources accounts may publish from.
A schedule plan is a separate durable operation that previews then creates/replaces/cancels
schedule items. Preview tokens bind server-observed state to a write; status is the authoritative
post-submit state. See [publish-plans.md](references/publish-plans.md).

## Shortcuts

| Situation | Start with |
| --- | --- |
| Audit effective pools | `museoncli account-publish +asset-pools-batch-get` |
| Change pools | `museoncli account-publish +asset-pools-batch-preview` |
| Build/replace schedule | `museoncli account-publish +schedule-plan-preview` |
| Remove eligible schedule items | `museoncli account-publish +schedule-plan-preview` |
| Follow pool job | `museoncli account-publish +asset-pools-batch-status` |
| Follow schedule job | `museoncli account-publish +schedule-plan-status` |

## DON'T

- **DON'T** loop social-account reads/writes or use Python/shell for batch pool/schedule work.
- **DON'T** submit without a fresh matching preview or alter its normalized request/token.
- **DON'T** rescan accounts after submission; the matching status command is the state source.
- **DON'T** treat schedule-job cancellation as deletion of schedule items already created.
- **DON'T** silently create no-BGM occurrences when BGM is required.
- **DON'T** reuse an idempotency key for an intentional new operation.
- **DON'T** skip failed, skipped, protected, or already-completed per-account rows.

## Relationships

Social-account resolves account identity; assets owns pool resources. Submitting an account into
Agentic Campaign fully-managed operation transfers its publish allocation without requiring
schedule cancellation.
