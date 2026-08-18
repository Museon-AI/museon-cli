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

## Shortcuts

| Situation | Start with |
| --- | --- |
| Creator/post/comment/trend | `museoncli research +social-media-search` |
| X/Reddit/LinkedIn discussion | `museoncli research +community-search` |
| Public page or official asset | `museoncli research +web-research` |
| Meta/TikTok ad evidence | `museoncli research +creative-search-ads` |
| Image/video visual question | `museoncli research +visual-analyze` |
| Durable video analysis | `museoncli content-analysis +run` |

## DON'T

- **DON'T** replace social-native search with generic web search for creators, posts, or comments.
- **DON'T** treat campaign-monitor data as a live public-platform search.
- **DON'T** resolve or scrape XHS short links in the shell; pass them directly.
- **DON'T** infer causality, conversion, growth, competition, or geography from one ads snapshot.
- **DON'T** run video-only Content Analyzer on static images, carousels, or slideshows.
- **DON'T** lose returned pagination cursors or rewrite opaque cursor values.

## Relationships

Convert evidence into assets with `museon-content-workflow-assets`, evaluate an output with
`museon-content-workflow-evaluator`, inspect stored campaign history with campaign-monitor, and
publish a durable synthesis with artifacts.
