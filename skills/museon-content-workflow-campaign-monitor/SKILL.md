---
name: museon-content-workflow-campaign-monitor
description: "Track campaign collections, creators, content, synced posts, and local performance history with Museon CLI."
metadata:
  requires:
    bins: ["museoncli"]
    skills: ["museon-content-workflow-base"]
  cliHelp: "museoncli schema campaign-monitor"
---

# Campaign monitor

**CRITICAL — first read [`../museon-content-workflow-base/SKILL.md`](../museon-content-workflow-base/SKILL.md).**

## Mental model

A campaign monitor stores tracked creators and content with synchronized post and performance history. Adding URLs may start import or sync work. Removing a monitor record changes the collection, not the source platform object. Read [monitor-store.md](references/monitor-store.md).

## Shortcuts

| Situation | Start with |
| --- | --- |
| Find a collection | `museoncli campaign-monitor +list` |
| Inspect creators or content | `museoncli campaign-monitor +creator-list` |
| Review performance | `museoncli campaign-monitor +summary` |
| Read synced posts | `museoncli campaign-monitor +post-list` |

## DON'T

- **DON'T** treat synchronized history as a live platform fetch.
- **DON'T** treat removing a monitor record as deleting the source account or post.
- **DON'T** report import acceptance as verified membership before list readback.

## Relationships

Use `museon-research` for live public evidence, base social-account references for connected-account performance, and base artifact references for retained reports.
