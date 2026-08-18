# Social search platforms

Inspect `museoncli schema research` and the exact command schema before use. Use `museoncli research +social-media-search` for TikTok, Instagram, YouTube, or XHS creators, profiles, posts, hashtags, comments, and trends.

Do not substitute generic web search when the object is a creator, post, comment, hashtag, or platform trend. Do not use the campaign monitor store as live public-platform search.

For comment pagination, reuse the cursor returned in `evidence.pagination`:

- TikTok: `museoncli research +social-media-search --platform tiktok --intent comments --query '7551234567890123456' --cursor 0`; `query` is the numeric video `aweme_id`, not a share URL, and later cursors are numeric.
- Instagram: `museoncli research +social-media-search --platform instagram --intent comments --query 'https://www.instagram.com/reel/SHORTCODE/'`; `query` may also be the post shortcode, and later `pagination_token` values are passed unchanged with `--cursor`.

## XHS links and video notes

Pass `xhslink.cn` / `xhslink.com` share links directly as `--query` for `post`, `profile`, or `creator-posts`; do not resolve redirects or scrape the page in the shell.

For a video note, `museoncli research +social-media-search --platform xhs --intent post --query 'https://xhslink.cn/o/<share_id>'` returns `video_url`, a directly downloadable MP4 URL that does not require login.

For comments, `museoncli research +social-media-search --platform xhs --intent comments --query 'https://xhslink.cn/o/<share_id>'`; `query` accepts a note ID, note URL, or xhslink share link, and later opaque cursors from `evidence.pagination` are passed unchanged with `--cursor`.

`content-analysis +run --url` currently supports TikTok videos, Instagram Reels, and YouTube Shorts. XHS video-note URL support will follow the backend rollout; until then, use XHS `post` to get `video_url`, download it, and pass it with `content-analysis +run --file`.
