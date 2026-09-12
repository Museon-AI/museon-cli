# VMOS natural Reels collection

Use this runbook only when discovery must come from an Instagram home or Reels
recommendation feed on a VMOS cloud phone. It records fragile operational facts;
keep semantic Hook classification in the main Skill.

## Source and safety contract

- Launch the authenticated Instagram app on the specified VMOS device and enter
  Home or Reels. Do not query a Museon Campaign, saved collection, search result,
  profile, browser scrape, or stale URL list as a replacement for the natural feed.
- Browsing, swiping, opening Share, and copying a permalink are collection
  actions. Do not like, follow, comment, save, send, publish, or change profiles.
- Keep at most the requested number of candidates. Prefer creator-led speech,
  action, expression, experience, story, embodied POV, or real scenes. Reject
  brand/product showcases, object-only demos, cinematic ads, and event montages
  before submission when the opening clearly shows an exclusion pattern.

## Reliable candidate loop

For each visible Reel, save a fresh screenshot and use visual judgment only for
the cheap candidate gate. If it qualifies, capture and canonicalize its permalink
while it is still visible, then immediately run:

```bash
museoncli research +social-media-hook-analyze-seen \
  --workspace-id <workspace-id> \
  --url <canonical-permalink>
```

- `seen=false`: append the returned canonical URL and safe
  `platform_content_id`, reset the consecutive-seen streak, then advance. It
  consumes one collection-budget slot.
- `seen=true`: record `reused_from_item_id`, advance to the next Reel, and do
  not consume a candidate slot.
- After four consecutive `seen=true` responses, refresh Instagram or leave and
  re-enter Reels, wait for settling, take a fresh screenshot, increment
  `refresh_count`, and reset the streak.

Open Share, choose **Copy link**, and require visible copy confirmation before
trusting the clipboard. Paste into a blank Chrome address field with Android key
code `279`, use the newest complete `/reel/<shortcode>/` suggestion, and reject
stale or mismatched links. VMOS screenshots and touch coordinates can use
different resolutions; measure in the current screenshot and convert explicitly.
Wait at least 2.3 seconds between gestures and verify each swipe changed Reel
identity. Stop on a login challenge, CAPTCHA, security warning, app mismatch, or
repeated navigation failure.

## Final batch guard

Inspect at most 40 Reels or stop at the task's time budget. Before analysis, run
one final seen command with every collected URL as repeated `--url` flags. Remove
anything now returning `seen=true`; those entries do not consume the candidate
quota. Submit only final `seen=false` URLs together in one new analysis batch.

Do not download media or invoke content analysis during collection. After the
analysis finishes, obtain recommended media only through
`+social-media-hook-analyze-media-get`.
