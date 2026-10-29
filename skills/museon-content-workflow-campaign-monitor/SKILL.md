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
| Know what a campaign can be broken down by | `museoncli campaign-monitor +list-dimensions` |
| Inspect creators or content | `museoncli campaign-monitor +list-creators` |
| Review performance | `museoncli campaign-monitor +get-summary` |
| Compare two periods | `museoncli campaign-monitor +get-period-performance` |
| Read synced posts | `museoncli campaign-monitor +list-posts` |

## Analysing a campaign

1. Run `+list-dimensions` first. `campaign_type` decides the menu.
2. A `ugc` campaign breaks down by brief, persona and tag. A post's persona is its brief's persona. Only approved posts carry a brief or tag; a post awaiting review has none yet.
3. Pick the post scope from `post_scopes`: `--link-status linked` reads approved posts only, omitting it reads every counted post. Say which one every number uses.
4. A `tracking` campaign has no review step and no briefs: break it down by `creator_tag` over all posts.
5. Report how many posts have no brief, persona or tag before any per-brief number. Tags overlap, so per-tag rows do not add up to the total.

## DON'T

- **DON'T** treat synchronized history as a live platform fetch.
- **DON'T** treat removing a monitor record as deleting the source account or post.
- **DON'T** report import acceptance as verified membership before list readback.

## Relationships

Use `museon-research` for live public evidence, base social-account references for connected-account performance, and base artifact references for retained reports.
