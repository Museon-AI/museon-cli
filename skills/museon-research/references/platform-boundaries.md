# Platform boundaries

## Mental model

Social search uses a platform plus intent. Comment pagination belongs to the source platform: TikTok uses a numeric video identity and numeric cursors; Instagram accepts a Reel URL/shortcode and returns opaque pagination tokens; XHS accepts note IDs, note URLs, or share links and returns opaque cursors.

XHS `xhslink.cn` / `xhslink.com` links are first-class inputs for post, profile, creator-posts, and comments. A video-note post returns a directly downloadable `video_url`. Until URL analysis supports XHS, that video can become a local-file Content Analyzer input.

## Shortcuts

| Situation | Start with |
| --- | --- |
| TikTok comments by video ID | `museoncli research +social-media-search` |
| Instagram comments by Reel URL/shortcode | `museoncli research +social-media-search` |
| XHS post/comments by share link | `museoncli research +social-media-search` |

## DON'T

- **DON'T** pass a TikTok share URL where comments require the numeric video identity.
- **DON'T** normalize or reconstruct Instagram/XHS opaque pagination tokens.
- **DON'T** scrape an XHS page or resolve its redirect before calling social search.
- **DON'T** assume XHS URL analysis exists; use returned video media through the supported file path.
- **DON'T** feed an unpreparable TikTok/signed CDN URL to visual analysis repeatedly; import stable media first.

## Relationships

This reference selects research inputs only. Asset creation, generation, monitoring, and reporting move to their owning Skills after evidence is collected.
