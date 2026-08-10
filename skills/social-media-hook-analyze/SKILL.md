---
name: social-media-hook-analyze
description: Research and compare Instagram video Hooks in asynchronous batches with Museon CLI. Use when an Agent needs to browse Instagram posts or profiles, filter non-video posts, decide whether each post is a UGC creator Hook, rank reusable Hooks, or identify UGC creator candidates. The host Agent owns every semantic classification and recommendation; Museon only returns structured observations.
---

# Social Media Hook Analyze

Use Museon as the evidence and job-state layer. You, the host Agent using this
Skill, own the semantic classification and recommendation policy.

The server does not decide whether a post is a UGC creator Hook or whether an
account is a UGC creator. Never treat `ugc_style.is_ugc_style` as either
decision: vertical, handheld, first-person, or ambient footage can describe a
brand/product video just as easily as creator content.

## Set up once per environment

This Skill requires the `ego-browser` Skill/runtime for authenticated Instagram
browsing and the `museon-cli` Skill/command for asynchronous analysis. On first
use in an environment, or after either command fails, run:

```bash
python3 scripts/check_setup.py --pretty
```

Continue when it returns `ready=true`. Otherwise read
[references/setup.md](references/setup.md) and repair only the reported
dependency. Do not perform unconditional authentication or workspace checks;
enter Museon recovery only when a real task command reports an auth/workspace
error.

## Choose the research mode

- **Hook discovery** asks whether each post's opening is a reusable UGC creator
  Hook. Judge the post first. Profile evidence may adjust confidence but cannot
  turn a non-qualifying post into a qualifying Hook.
- **Creator discovery** starts from qualifying posts, then asks whether the
  profile is a UGC creator and whether creator-led delivery is consistent across
  several posts. A good post alone does not prove the profile is a creator.

When the request includes both goals, finish Hook discovery before Creator
discovery.

## Collect and pre-filter inputs

Collect canonical Instagram post permalinks and optional profile URLs. Keep the
source link beside every later assessment.

Filter a post before submission only when its media type is reliable:

- keep `/reel/`, `/reels/`, and `/tv/` video links;
- exclude a post when browser DOM or extracted metadata explicitly identifies
  it as a static image/photo and shows no video media;
- keep an ambiguous `/p/` post because it may be a video or a mixed carousel;
- do not infer media type from a thumbnail, caption, or visual appearance alone.

Profile discovery already requests video content and filters discovered items
before analysis jobs are created. Direct ambiguous posts are resolved by the
server; a post without video becomes `ineligible` with `NOT_VIDEO` before video
download or model analysis. Treat this as an expected filtered result, not a
failed Hook.

## Start and poll asynchronous batches

Inspect the current command schema before first use. Start one or more batches,
reusing an idempotency key only for an exact retry:

```bash
museoncli schema research.social-media-hook-analyze
museoncli research +social-media-hook-analyze \
  --url https://www.instagram.com/reel/POST/ \
  --profile-url https://www.instagram.com/CREATOR/ \
  --limit-per-profile 12 \
  --max-items 20 \
  --idempotency-key <stable-key>
```

Collect every returned `run.id`, then poll up to 20 runs together. Do not start
the same analysis again merely to learn its status.

```bash
museoncli research +social-media-hook-analyze-poll \
  --id <analysis-id-1> --id <analysis-id-2>
```

If `all_terminal=false`, wait the returned `poll_after_seconds` and poll the same
group again. Split more than 20 IDs into stable groups. Stop polling terminal
groups. Fetch every result page for terminal or partially terminal batches:

```bash
museoncli research +social-media-hook-analyze-results \
  --id <analysis-id> --page 1 --page-size 100 > analysis.json
```

## Classify posts as the host Agent

Read [references/post-classification.md](references/post-classification.md),
then inspect each completed item's structured observations. Produce one
`post_assessments.json` entry per completed item. Use only returned observations
for the post verdict; do not fill evidence gaps with assumptions from the
caption, metrics, profile bio, or account category.

The required envelope is:

```json
{
  "assessment_schema_version": "ugc-creator-hook-assessment.v1",
  "items": [
    {
      "item_id": "<analysis item id>",
      "verdict": "qualifies",
      "confidence": "high",
      "post_type": "ugc_creator_hook",
      "creator_led": "yes",
      "creator_experience_carries_product": "yes",
      "ordinary_creator_reproducible": "yes",
      "evidence": [
        {"path": "opening.audio_and_speech", "observation": "Creator opens with a personal claim."}
      ],
      "exclusion_signals": []
    }
  ]
}
```

Use `verdict=uncertain` whenever the observations cannot support the distinction.
Uncertainty is a valid result and must never be auto-promoted.

## Gate and rank Hooks locally

Pass the Agent-authored assessment file to the deterministic ranker:

```bash
python3 scripts/rank_hooks.py analysis.json \
  --post-assessments post_assessments.json \
  --pretty > ranked_hooks.json
```

The ranker implements the fail-closed gate:

- `qualifies` with medium/high confidence may be scored and recommended;
- `does_not_qualify` becomes `excluded` regardless of visual score;
- missing, uncertain, malformed, or low-confidence assessment becomes
  `post_hook_review_required` and cannot be recommended;
- non-completed analysis items remain `unscored`.

Scoring is versioned `hook-score.v2` and remains intentionally simple:
scroll-stop 30%, emotion 20%, curiosity 20%, reproducibility 20%, and creator
transferability 10%. Change weights or thresholds in `scripts/rank_hooks.py` or
with `--config`; never move them into API inputs or server storage.

Inspect timestamped evidence for leading candidates before reporting or
promoting them. Return links, verdicts, confidence, exclusion reasons, scores,
and evidence rather than only an ordered list.

## Publish one Lark card per batch

When the user asks to publish high-scoring results, read the installed
`lark-shared` and `lark-im` Skills before using `lark-cli`. For every selected
Hook, obtain a temporary local MP4 of at most 30 MB. Put the item IDs and local
paths in a source manifest, then use the bundled uploader rather than assembling
the multipart requests by hand:

```json
{
  "media_source_schema_version": "social-hook-lark-media-source.v1",
  "items": [
    {"item_id": "<analysis-item-id>", "video_path": "./hook-1.mp4"}
  ]
}
```

```bash
python3 scripts/upload_lark_media.py lark_media_sources.json --pretty > lark_media_keys.json
```

The uploader probes the real duration with `ffprobe`, passes that positive
millisecond value to `/open-apis/im/v1/files`, extracts a visible opening cover,
uploads it through `im images create`, and deletes its temporary copies. It uses
the Lark bot identity for both uploads; send the card with the same bot
application. The resulting manifest is deliberately fail-closed:

```json
{
  "media_schema_version": "social-hook-lark-media.v2",
  "items": [
    {
      "item_id": "<analysis-item-id>",
      "file_key": "file_v3_xxx",
      "cover_img_key": "img_v3_xxx",
      "duration_ms": 47000
    }
  ]
}
```

Never save the Instagram CDN URL. Prepare a bounded Card 2.0 payload from the
ranked result and uploaded media keys:

```bash
python3 scripts/prepare_lark_card.py ranked_hooks.json \
  --analysis-id <analysis-id> \
  --media-keys lark_media_keys.json \
  --admin-base-url https://museon-ai-hook.vercel.app/hook-format/social-analysis \
  --min-score 75 \
  --max-items 4 \
  --pretty > lark_card.json
```

The card contains up to four `recommended` Instagram Hooks in one batch. Each
item uses a full-width native `video` component with its required cover; title,
score, creator, and opening evidence sit below it. Do not wrap the player in an
`open_url` container because that competes with video taps on mobile. The
Instagram link lives in the title instead. There are no card-side selectors,
forms, submit actions, or callbacks.

The bottom area has two static `open_url` actions. **挑选并保存** opens the
curated batch for review:

```text
https://museon-ai-hook.vercel.app/hook-format/social-analysis?source=social-hook-analysis&analysis_id=<analysis-id>&recommended_item_ids=<codex-filtered-item-ids>
```

The AI Hook page loads the batch, lets the authenticated user preview and choose
items, then calls the explicit idempotent import endpoint. **全部保存** uses the
same URL plus `auto_save=1`; after authentication the frontend imports exactly
the `recommended_item_ids` already selected by the host Agent. It never imports
all analyzed posts. Do not put `selected_item_ids` in either link. Override the
frontend origin with `--admin-base-url` when required. Because the card has no
interactive form state, the sending Lark application does not need
`card.action.trigger` or a callback webhook for this workflow.

Video cards require Feishu 7.56+, MP4 files no larger than 30 MB, and
`config.enable_forward=false`; the script enforces the card-side contract.

Before the visible send, explicitly confirm the recipient, card content, and
sending identity as required by `lark-im`. Then send the generated payload with
an idempotency key derived from the analysis id:

```bash
lark-cli im +messages-send \
  --chat-id <confirmed-chat-id> \
  --as bot \
  --msg-type interactive \
  --content "$(tr -d '\n' < lark_card.json)" \
  --idempotency-key "hook-card-<analysis-id-prefix>"
```

## Add Creator discovery only after Hook discovery

For each profile, group its post assessments and then inspect profile-level
evidence in the browser. Report a creator candidate only when all three are
supported:

1. at least one post has a qualifying UGC creator Hook;
2. the profile itself is operated as a UGC creator account;
3. creator-led expression is a repeated content pattern, not a one-off post.

Keep the profile assessment separate from `post_assessments.json`. Profile
evidence can increase or reduce creator-candidate confidence, but it cannot
rewrite a post verdict. If profile evidence is missing or mixed, return
`creator_review_required`.

## Evidence and safety boundaries

- Do not infer causal performance from likes, comments, or views.
- Do not replace failed strict analysis with free text or another analyzer.
- Do not supply browser cookies or persist signed media URLs.
- Treat failed and ineligible items as evidence gaps, not low-scoring Hooks.
- Read [references/result-contract.md](references/result-contract.md) before
  adapting to a new server analysis schema.
