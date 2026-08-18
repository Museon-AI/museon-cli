---
name: museon-content-workflow-routines
description: "Create and manage Museon recurring routines, triggers, ownership, lifecycle, and durable memory across social-media operating runs."
metadata:
  requires:
    bins: ["museoncli"]
    skills: ["museon-content-workflow-base"]
  cliHelp: "museoncli schema routines"
---

# Museon routines workflow

**CRITICAL — first read [`../museon-content-workflow-base/SKILL.md`](../museon-content-workflow-base/SKILL.md).**

## Mental model

A Routine combines instruction, owner, trigger, active lifecycle, and durable memory. Drafts have
no registered trigger until accepted. Rebuild replaces instruction/trigger and may carry memory;
pause/resume/cancel affect the trigger. Platform output capture is automatic. See
[routine-lifecycle.md](references/routine-lifecycle.md).

## Shortcuts

| Situation | Start with |
| --- | --- |
| Find existing routine | `museoncli routines +list` |
| Review before scheduling | `museoncli routines +create-draft` |
| Create approved recurring work | `museoncli routines +create-ad-hoc` |
| Inspect trigger/owner | `museoncli routines +get` |
| Read durable memory | `museoncli routines +memory-get` |

## DON'T

- **DON'T** create a duplicate before reading existing routines.
- **DON'T** mutate lifecycle for a routine owned by someone else; surface the owner.
- **DON'T** activate an under-specified routine instead of creating a draft.
- **DON'T** record transient chatter or entire outputs as durable memory.
- **DON'T** manually record ordinary output already captured by the platform.

## Relationships

Each routine delegates its work to the owning domain Skill. Artifacts retains shareable outputs;
campaign-monitor/social-account/Agentic Campaign provide the state reviewed on later runs.
