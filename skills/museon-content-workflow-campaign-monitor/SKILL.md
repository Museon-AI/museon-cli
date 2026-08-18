---
name: museon-content-workflow-campaign-monitor
description: "Monitor Museon campaigns, creators, content, summaries, social-media sync jobs, and locally synced post histories for performance review and next actions."
---

# Museon campaign monitor workflow

Use for the `campaign-monitor` domain, including commands implemented in `social_media.py`.

| Command family | Purpose |
| --- | --- |
| `museoncli campaign-monitor +content-list/+creator-list` | Read monitored content and creators |
| `museoncli campaign-monitor ...` | Campaign summaries, sync commands, and post history exposed by schema |

## References

- [monitoring-and-review.md](references/monitoring-and-review.md): source boundaries, review
  discipline, and next-action loop.
- Inspect `museoncli schema campaign-monitor` and the exact shortcut before use.

## Cross-skill handoff

Use `museon-research` for live public-platform evidence, not the monitor store. Send durable
reviews to `museon-content-workflow-artifacts` and recurring monitoring to
`museon-content-workflow-routines`.
