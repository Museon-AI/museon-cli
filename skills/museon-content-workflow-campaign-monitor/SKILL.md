---
name: museon-content-workflow-campaign-monitor
description: "Track Museon campaign collections, creators, content, synced posts, and local performance history for monitoring and review."
metadata:
  requires:
    bins: ["museoncli"]
    skills: ["museon-content-workflow-base"]
  cliHelp: "museoncli schema campaign-monitor"
---

# Museon campaign monitor workflow

**CRITICAL — first read [`../museon-content-workflow-base/SKILL.md`](../museon-content-workflow-base/SKILL.md).**

## Mental model

A campaign monitor is a collection of tracked creators and content with locally synced post and
performance history. Adding URLs may start import/sync work. Removing a monitor record changes the
collection, not the source platform object. See [monitor-store.md](references/monitor-store.md).

## Shortcuts

| Situation | Start with |
| --- | --- |
| Find monitor collection | `museoncli campaign-monitor +list` |
| Inspect tracked creators | `museoncli campaign-monitor +creator-list` |
| Inspect tracked content | `museoncli campaign-monitor +content-list` |
| Review collection performance | `museoncli campaign-monitor +summary` |
| Resolve schedule to live post | `museoncli campaign-monitor +post-resolve` |
| Read synced post history | `museoncli campaign-monitor +post-list` |

## DON'T

- **DON'T** treat synced post history as a live platform-history fetch.
- **DON'T** treat removing a creator monitor as deleting the creator's platform account.
- **DON'T** treat removing content as deleting the original platform post.
- **DON'T** assume a workspace-wide monitor disappears while another campaign references it.
- **DON'T** use public research when the question concerns already monitored local history.

## Relationships

Research owns live public evidence; social-account owns connected-account performance; Agentic
Campaign owns strategy and managed operations; artifacts owns durable review reports.
