---
name: museon-research
description: "Research markets, competitors, creators, posts, trends, comments, communities, web pages, ads, and visuals, or run Museon video content analysis."
metadata:
  requires:
    bins: ["museoncli"]
    skills: ["museon-content-workflow-base"]
  cliHelp: "museoncli schema research"
---

# Museon research

**CRITICAL — first read [`../museon-content-workflow-base/SKILL.md`](../museon-content-workflow-base/SKILL.md).**

## Mental model

Research produces evidence, not platform state. Choose the evidence store by object: live social
objects, community discussion, public web, ad-library snapshot, visual interpretation, or a durable
video Content Analyzer run. Facts, model interpretation, business inference, and confidence remain
separate. See [evidence-model.md](references/evidence-model.md) and
[platform-boundaries.md](references/platform-boundaries.md).
Read [research-reporting.md](references/research-reporting.md) for evidence claims, ads comparisons, and durable report delivery.

For the Instagram Hook comparison workflow, begin with [setup.md](references/setup.md), then read
[post-classification.md](references/post-classification.md), [vmos-natural-reels.md](references/vmos-natural-reels.md), or [result-contract.md](references/result-contract.md) only when that phase applies. Reuse the scripts in this skill's `scripts/` directory.

## Shortcuts

| Situation | Start with |
| --- | --- |
| Creator/post/comment/trend | `museoncli research +social-media-search` |
| X/Reddit/LinkedIn discussion | `museoncli research +community-search` |
| Public page or official asset | `museoncli research +web-research` |
| Meta/TikTok ad evidence | `museoncli research +creative-search-ads` |
| Image/video visual question | `museoncli research +visual-analyze` |

## DON'T

- **DON'T** replace social-native search with generic web search for creators, posts, or comments.
- **DON'T** treat campaign-monitor data as a live public-platform search.
- **DON'T** resolve or scrape XHS short links in the shell; pass them directly.
- **DON'T** infer causality, conversion, growth, competition, or geography from one ads snapshot.
- **DON'T** lose returned pagination cursors or rewrite opaque cursor values.

## Relationships

Use base media and content-analysis references for inputs and durable video analysis; use the campaign-monitor skill for stored creator/post history.
Preserve a synthesis as a local report; business creation and delivery require their owning API.
