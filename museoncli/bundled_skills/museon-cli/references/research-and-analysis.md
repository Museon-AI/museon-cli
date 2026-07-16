# Research and analysis

Read this reference for market, trend, competitor, creator, account, post,
community, visual, or creative-intelligence work.

## Choose evidence by shape

Inspect `museoncli schema research` and the exact command schema before use.

| Evidence needed | Command family |
| --- | --- |
| TikTok, Instagram, YouTube, or XHS creators, profiles, posts, hashtags, comments, and trends | `museoncli research +social-media-search` |
| X, Reddit, or LinkedIn discussions, profiles, and sentiment | `museoncli research +community-search` |
| Official sites, public pages, market facts, and official visual assets | `museoncli research +web-research` |
| Images, screenshots, ads, product visuals, or video frames | `museoncli research +visual-analyze` |
| A connected or Museon-operated account's current performance | `museoncli social-account +performance-get` |
| Already monitored campaign content and creators | `museoncli campaign-monitor +content-list` and `museoncli campaign-monitor +creator-list` |

Do not substitute generic web search for social-native evidence when the object
is a creator, post, comment, hashtag, or platform trend. Do not use the campaign
monitor store as if it were a live public-platform search.

## Research workflow

1. Resolve the business question, target platforms, and time horizon. Ask only
   for missing information that would materially change the research.
2. Search for evidence using the correct source family.
3. Open or analyze the strongest sources instead of collecting a long list of
   weak mentions.
4. For creative claims, inspect the visual material rather than relying only on
   captions or transcripts.
5. Separate observed facts, model interpretation, business inference, and
   confidence.
6. Keep a link next to every load-bearing claim. Every named creator or post
   must have its source URL.
7. Convert findings into an operating decision: content direction, reusable
   format, account action, generation brief, monitoring plan, or next test.

## Content Analyzer boundary

Use `museoncli content-analysis +run` for video platform URLs, Museon video
media, or local video files. It is a write/async command, so inspect its schema,
state the analysis job that will be created, and obtain separate approval.

Static images, carousels, and slideshows do not use the video-only Content
Analyzer path. Analyze their visuals with research tools or extract a reusable
format through the asset workflow described in
[content-and-visuals.md](content-and-visuals.md).

When a completed analysis returns a `share_url`, include it so the user can
inspect the full result.
