# museoncli domain command framework

Museon CLI exposes business capabilities through domain shortcuts:

```bash
museoncli <domain> +<shortcut> [flags]
museoncli schema [<domain>[.<shortcut>]]
```

The fixed top-level domain enum lives in `museoncli/domains/_model.py`
(`Domain`). The enum is the source of truth for deciding whether a new
capability belongs under an existing domain or needs a new top-level domain
discussion. Surface rules (identifiers, pagination, enum values, safety) are
defined in [cli-surface-conventions.md](cli-surface-conventions.md) and
enforced by `tests/test_surface_conventions.py`.

## Layers

| Layer | Purpose |
|-|-|
| Command surface | `museoncli <domain> +<shortcut>` |
| Command schema registry | Input/output/risk/examples per shortcut (`museoncli/domains/`) |
| HTTP executor | Converts validated arguments into authenticated Museon API calls |
| Envelope | Shapes stable `{"ok", "data", "run", "next_steps"}` JSON output |

There is no separate public/internal command tier in the CLI. Every user or
Agent discovers the same command contract through `museoncli schema`. After
login, the hosted Museon API authorizes each call from the user's organization,
workspace membership, role, and the requested resource.

## Current commands

The tables below are generated — edit code, then run
`uv run python scripts/gen_command_docs.py`. CI fails when they drift
(`tests/test_docs_sync.py`).

<!-- BEGIN GENERATED COMMANDS (scripts/gen_command_docs.py) -->

154 commands across 10 domains (source of truth: `museoncli schema`).

### research

| command | risk | dry-run | confirm | execution | summary |
|---|---|---|---|---|---|
| `research +web-research` | read | — | — | direct | Research public web evidence from a query or URL, including page text and official-site visual assets. |
| `research +social-media-search` | read | — | — | direct | Search social-native evidence across TikTok, Instagram, YouTube, and XHS using a stable platform and intent contract. |
| `research +social-media-hook-analyze` | write | yes | — | async_run | Start a durable Instagram Hook analysis batch from post and/or profile URLs. Returns immediately; poll batches together and read structured results by page. |
| `research +social-media-hook-source` | write | yes | — | async_run | Submit Agent-prefiltered Instagram Hook candidates, recheck workspace-scoped duplicates, and start the existing durable analysis batch. |
| `research +social-media-hook-analyze-seen` | read | — | — | direct | Check up to 40 Instagram post URLs against prior workspace-scoped Social Media Hook analyses. |
| `research +social-media-hook-analyze-get` | read | — | — | direct | Read one Social Media Hook analysis batch and its aggregate progress. |
| `research +social-media-hook-analyze-poll` | read | — | — | direct | Poll up to 20 Social Media Hook analysis batches in one request. |
| `research +social-media-hook-analyze-results` | read | — | — | direct | List versioned, structured Hook evidence for one analysis batch. Apply scoring and recommendation policy in the consuming Skill. |
| `research +social-media-hook-analyze-media-get` | read | — | — | direct | Download one workspace-scoped temporary source video from a Social Media Hook analysis item without exposing a signed URL. |
| `research +community-search` | read | — | — | direct | Search community evidence across X, Reddit, and LinkedIn using a stable platform and intent contract. |
| `research +creative-search-ads` | write | yes | — | async_run | Start a durable Creative Search Ads task across Meta and TikTok ad libraries. Requires a stable idempotency key for safe retries. This is Ads-only and never falls back to organic social search. |
| `research +creative-search-ads-get` | read | — | — | direct | Read one Creative Search Ads task, including terminal aggregate statistics and sanitized partial-failure details. |
| `research +creative-search-ads-results` | read | — | — | direct | List deduplicated Creative Search Ads evidence for one task. Defaults to analysis-eligible matches and returns relevance, evidence quality, metric extrema, and limitations. Treat results as one snapshot: cite item IDs for numeric claims and do not infer causality, conversion effectiveness, market growth, competition intensity, or geographic activity without additional evidence. |
| `research +visual-analyze` | read | — | — | direct | Analyze one or more image/video URLs with a business prompt. If a TikTok or signed CDN URL cannot be prepared, import it as Museon media first and retry with the returned stable media URL. |

### content-analysis

| command | risk | dry-run | confirm | execution | summary |
|---|---|---|---|---|---|
| `content-analysis +run` | write | yes | — | async_run | Run Content Analyzer for supported platform content (including Xiaohongshu image notes), uploaded video media, or local video files, optionally using a workspace Business Skill. |
| `content-analysis +get` | read | — | — | direct | Read one Content Analyzer run by ID. |
| `content-analysis +list` | read | — | — | direct | List Content Analyzer runs in the selected workspace. |

### artifacts

| command | risk | dry-run | confirm | execution | summary |
|---|---|---|---|---|---|
| `artifacts +validate` | read | — | — | direct | Validate one local Artifact Markdown file before upload. Checks frontmatter, report-directions YAML and field schema, preview URLs, optional stats, and duplicate social Embed placements. This command performs no network calls. |
| `artifacts +upload` | write | yes | — | direct | Upload or replace one local agent file artifact through multipart form-data. Markdown uploads are public by default. After upload, give BOTH links when both exist: data.public_url (public share link, anyone with the link) and data.url (workspace/private link, logged-in workspace members). Use --no-public only when the user explicitly wants a private artifact (then only data.url). To embed resources inside markdown, paste ready-made refs returned by retained domains such as routines verbatim. Do not hand-write resource links, file names, local paths, or storage paths as links. You can also paste a raw TikTok, Instagram, or YouTube URL on its own line to embed a player. |
| `artifacts +share` | write | yes | — | direct | Re-enable public internet access for one markdown artifact (for example after +unshare). Prefer +upload defaults for new reports. |
| `artifacts +unshare` | write | yes | — | direct | Revoke the public internet link for one artifact. Use only when the user explicitly wants to revoke public access. |

### media

| command | risk | dry-run | confirm | execution | summary |
|---|---|---|---|---|---|
| `media +generate` | write | yes | — | direct | Submit prompt image (GPT Image 2.5) or text video (Kling 3); requires configured model credits. Receipt is not completion: read media +status then +get. |
| `media +status` | read | — | — | direct | Read durable generation phase, effective model parameters, errors and media readiness. |
| `media +upload` | write | yes | — | direct | Upload local image/video/audio or a private general file. General files return artifact_id, with expiring download URL; read with --kind file. Read the returned media ID with media +get; upload success does not prove business generation or delivery completion. |
| `media +import` | write | yes | — | direct | Import an image from a direct HTTP(S) URL. This API supports images only; upload local video/audio files with media +upload. |
| `media +get` | read | — | — | direct | Read one media record in the selected workspace. Business output completion must be verified through its owning domain. |

### social-account

| command | risk | dry-run | confirm | execution | summary |
|---|---|---|---|---|---|
| `social-account +list` | read | — | — | direct | List social accounts available to the current workspace. For multiple known handles, repeat --search-term (max 100) in one request; do not concatenate handles into --search or page-scan the account list. |
| `social-account +get` | read | — | — | direct | Read one workspace social account. |
| `social-account +adb-connect` | write | yes | — | direct | Connect the current sandbox to this account's cloud phone over ADB. After success, use native adb or u2cli with the returned serial; the temporary connection password is never printed. |
| `social-account +stream-url` | read | — | — | direct | Return this account's cloud-phone live-stream URL. The sandbox stream sidecar renders it to capture fast motion the u2cli clip command needs; the URL views the same phone adb-connect controls. |
| `social-account +connect-link-create` | write | yes | — | direct | Create a workspace self-authorization link to connect a user-owned social account. Supports TikTok, Instagram, Facebook, LinkedIn, and X. |
| `social-account +connect-link-status` | read | — | — | direct | Read or wait for the authorization result of a social account connect link. |
| `social-account +performance-get` | read | — | — | direct | Live-read performance for one social account: authorized channels first, with automatic public-data fallback when authorization is missing/expired or the platform exposes no history. Payload `source` marks provenance (official/managed analytics vs public_data) — relay that difference to customers and never show internal retrieval details. First page includes the profile block; posts paginate via --cursor. |
| `social-account +profile-edit-draft` | read | — | — | direct | Generate proposed TikTok display name, bio, or avatar drafts for one account. |
| `social-account +profile-edit-submit` | write | yes | — | async_run | Submit a TikTok profile edit task for one account. Use +profile-edit-status to confirm completion. |
| `social-account +profile-edit-batch-submit` | write | yes | — | async_run | Submit a TikTok profile edit task for multiple accounts in one batch. Use +profile-edit-status to poll the single task for all account statuses. |
| `social-account +profile-edit-status` | read | — | — | direct | Read execution status for a profile edit task. |
| `social-account +avatar-generate-batch` | read | — | — | async_run | Generate TikTok profile avatar drafts for multiple accounts as one async task. Poll +avatar-generate-status for per-account avatar URLs, then feed the succeeded ones into +profile-edit-batch-submit. |
| `social-account +avatar-generate-status` | read | — | — | direct | Read per-account status and avatar URLs for an avatar-generation task. |

### hireaicreator

| command | risk | dry-run | confirm | execution | summary |
|---|---|---|---|---|---|
| `hireaicreator account +list` | read | — | — | direct | Find exact account identities and current stage/assignment state; complete pagination before fixing a selection. |
| `hireaicreator account +assets-get` | read | — | — | direct | Read an account's Actor, Persona and other publish asset bindings. |
| `hireaicreator account +actor-set` | write | yes | — | direct | Bind an existing Actor to an account; use its exact ID to resolve duplicate names. |
| `hireaicreator account +persona-set` | write | yes | — | direct | Bind an existing Persona to an account. Managed-operation approval must be explicit. |
| `hireaicreator account +eligibility` | read | — | — | direct | Read eligibility and blockers for an explicit account set. |
| `hireaicreator actor +list` | read | — | — | direct | List Actors (independent identities), optionally by source Persona. |
| `hireaicreator actor +get` | read | — | — | direct | Read one Actor; its ID is not a Persona ID. |
| `hireaicreator actor +from-persona` | write | yes | — | direct | Create one Actor from an existing Persona and one workspace image. |
| `hireaicreator actor +batch-create` | write | yes | — | direct | Start Persona-based Actor generation. Generated images remain candidates until selected. |
| `hireaicreator actor +batch-get` | read | — | — | direct | Read the status and counts of one Actor generation batch. |
| `hireaicreator actor +batch-items` | read | — | — | direct | Page through generated Actor candidates and their image/status details. |
| `hireaicreator actor +batch-select` | write | yes | — | direct | Turn explicitly chosen successful candidates into Actors. |
| `hireaicreator persona +list` | read | — | — | direct | List Personas and their actual identities. |
| `hireaicreator persona +get` | read | — | — | direct | Read a Persona through resource access control; no workspace override. |
| `hireaicreator format +list` | read | — | — | direct | List HireAICreator Formats, distinct from slideshow Formats. |
| `hireaicreator format +get` | read | — | — | direct | Read Format processing state and source resources. |
| `hireaicreator format +import-urls` | write | yes | — | direct | Import Format source URLs asynchronously; acceptance is not ready content. |
| `hireaicreator hook +list` | read | — | — | direct | List reference Hooks; distinguish Hook IDs from generated item IDs. |
| `hireaicreator recipe +list` | read | — | — | direct | List reusable Clip recipes. |
| `hireaicreator recipe +get` | read | — | — | direct | Read one Recipe and its steps. |
| `hireaicreator pov +list` | read | — | — | direct | List reusable POV text. |
| `hireaicreator bgm +list` | read | — | — | direct | List BGM media and publishability facts. |
| `hireaicreator item +list` | read | — | — | direct | List generated Hook items with result media URLs and status; filter by reference Hook ID and paginate the matching results. |
| `hireaicreator item +get` | read | — | — | direct | Read one generated Hook item; resolve result_video_media_id with media +get --id. |
| `hireaicreator batch +list` | read | — | — | direct | List generation batches by status and counters; batches have IDs, not names. |
| `hireaicreator batch +get` | read | — | — | direct | Read one generation batch status and counters by ID. |
| `hireaicreator batch +items` | read | — | — | direct | List one batch's generated items; resolve each result_video_media_id with media +get --id. |
| `hireaicreator clip +list` | read | — | — | direct | Read Clip inventory and assignment state. |
| `hireaicreator clip +get` | read | — | — | direct | Read one Clip including version, media and publishing account. |
| `hireaicreator clip +batch-create` | write | yes | — | direct | Register Clips with client_key/mapping_version identity; initial needs_account is not usable assigned stock. |
| `hireaicreator clip +assign-account` | write | yes | — | direct | Assign Clips with explicit expected versions and account IDs. |
| `hireaicreator video +list` | read | — | — | direct | List videos and their version/state; paginate explicitly. |
| `hireaicreator video +get` | read | — | — | direct | Read persisted video configuration, version, component/render/publish facts. |
| `hireaicreator video +readiness` | read | — | — | direct | Read blockers and stage eligibility; readiness does not prove generation completion. |
| `hireaicreator video +update` | write | yes | — | direct | Patch only supplied video fields using the observed expected_version; do not auto-retry conflicts. |
| `hireaicreator video +generate` | write | yes | — | direct | Request video generation with a stable idempotency key; response is acceptance only. |
| `hireaicreator video +bulk-schedule` | write | yes | — | direct | Schedule explicit video/version/account/time tuples; retain succeeded/conflicted/failures. |
| `hireaicreator plan +preview` | read | — | — | direct | Read server allocation and blockers for a proposed plan; does not create the plan. |
| `hireaicreator plan +capacity` | read | — | — | direct | Read account capacity for a bounded date range. |
| `hireaicreator plan +create` | write | yes | — | direct | Create a plan with a stable idempotency key. Server defaults start_generation to false; creation is not a finished video. |
| `hireaicreator plan +get` | read | — | — | direct | Read a persistent video plan and its state. |
| `hireaicreator test-group +list` | read | — | — | direct | List workspace Test Groups without creating a plan; optional plan_id narrows to a known plan. |
| `hireaicreator test-group +get` | read | — | — | direct | Read current group members and schedule state; does not migrate accounts. |
| `hireaicreator test-group +preview` | read | — | — | direct | Preview the persisted test group schedule and inventory gaps, without confirming a rollout. |
| `hireaicreator warmup +list` | read | — | — | direct | Read warmup strategies; does not change account stage. |
| `hireaicreator warmup +journeys` | read | — | — | direct | Read warmup journey state and current participation. |
| `hireaicreator dashboard +get` | read | — | — | direct | Read campaign performance with explicit dates; preserve freshness and missing-data distinctions. |
| `hireaicreator delivery +preview` | read | — | — | direct | Read share selection counts only; counts are not an exact video-ID manifest. |
| `hireaicreator delivery +share` | write | yes | — | direct | Create or rotate public collection access, possibly prewarming exports. No generic idempotency: do not blindly retry unknown outcomes. |
| `hireaicreator delivery +get` | read | — | — | direct | Read a public collection by its opaque token. Paginate with total/items; no has_more is promised. |
| `hireaicreator delivery +export` | write | yes | — | direct | Request an export bound to video version; preserve the idempotency key on retry. |
| `hireaicreator delivery +export-get` | read | — | — | direct | Read actual export status, version/revision, error and download URL. |

### ai-slideshow

| command | risk | dry-run | confirm | execution | summary |
|---|---|---|---|---|---|
| `ai-slideshow asset +list` | read | — | — | direct | List reusable product, persona, topic, format, or media assets. For multiple search concepts, repeat --search-term (max 20); do not join terms with commas in --search. Each resource includes a ref — paste it into report/pitchdeck markdown to embed a live card. Inline in a sentence renders a chip; alone on its own line renders a full card. |
| `ai-slideshow asset +get` | read | — | — | direct | Read one reusable product, persona, topic, format, or media asset. Each resource includes a ref — paste it into report/pitchdeck markdown to embed a live card. Inline in a sentence renders a chip; alone on its own line renders a full card. |
| `ai-slideshow asset +get-batch` | read | — | — | direct | Read 1-100 Formats by exact IDs in one request. When two or more known Format IDs must be queried, MUST use this command instead of looping ai-slideshow asset +get. Items preserve request order; missing or inaccessible IDs are returned in missing_ids. |
| `ai-slideshow asset +options` | read | — | — | direct | List canonical values and labels for an asset field. Product category supports optional intent search, so a term such as education, edtech, or 教育 returns the relevant learning categories without trial writes. |
| `ai-slideshow asset +create` | write | yes | — | direct | Create one reusable product, persona, topic, format, or media asset. Product requires name, category, and description; discover canonical categories with ai-slideshow asset +options and use --dry-run for authoritative server validation without writing. |
| `ai-slideshow asset +update` | write | yes | — | direct | Update one reusable product, persona, topic, format, or media asset. |
| `ai-slideshow asset +delete` | destructive | yes | `--yes` | direct | Delete one reusable product, persona, topic, format, or media asset. If another resource still references the asset, the server returns the blocking relationship; resolve it through its owning workflow before retrying. |
| `ai-slideshow generation +create` | write | yes | — | async_run | Create and start one media generation — Museon's image-post (生图/图文) generation capability. Current type: slideshow, driven by format, topic, persona, and optional product assets. When the user asks to generate images or image posts but the workspace lacks these assets, do not refuse and do not ask the customer for asset IDs — follow the Content Replication flow to guide asset preparation first. Responses include a ready-made generation ref and a recommended wakeup delay. Present the ref in the current final response, tell the customer generation is in progress and the link shows live progress, then use the returned delay for the next status check instead of choosing one yourself. |
| `ai-slideshow generation +get` | read | — | — | direct | Read one media generation by id. Current type: slideshow. The response includes a ready-made generation ref; completed generations include grid_media, slide_media, and result_preview_image_urls when result media is available. |
| `ai-slideshow generation +list` | read | — | — | direct | List media generations in the current workspace. Current type: slideshow. Each item includes a ready-made generation ref; completed generations include grid_media, slide_media, and result_preview_image_urls when result media is available. |
| `ai-slideshow publish +asset-pools-batch-get` | read | — | — | direct | Read effective persona, product, format, topic, and BGM pools for MULTIPLE accounts in one request, with per-account issues and hydrated resource details by default. MUST use this for multi-account audits instead rather than issuing one request per account. This batch command is also valid for a complete five-pool inspection of one account. |
| `ai-slideshow publish +asset-pools-batch-preview` | read | — | — | direct | Live-preview one multi-account asset-pool change without writing. Supports a uniform patch plus per-account precise overrides for persona, product, formats, topics, and BGM. Always run this before +asset-pools-batch-set, present every changed/skipped/failed account and existing-schedule impact, then obtain explicit approval. Fully-managed accounts are previewed normally and marked requires_managed_operation_approved=true; after explicit approval, submit with --managed-operation-approved. |
| `ai-slideshow publish +asset-pools-batch-set` | destructive | yes | `--yes` | async_run | Submit one durable Cloud Task job to change publish asset pools for MULTIPLE accounts. Use this instead of issuing one write per account or writing Python/shell scripts; keep the single command for small, precise one-account edits. This batch command is preferred when atomically configuring all five pools for one account. Requires the opaque token and identical normalized patches from a fresh live preview, plus a stable idempotency key and --yes. After submission, poll only +asset-pools-batch-status and inspect every failed/skipped account. If preview marks any fully-managed account requires_managed_operation_approved=true, relay its impact and add --managed-operation-approved only after explicit approval; without it those accounts fail per-account. |
| `ai-slideshow publish +asset-pools-batch-status` | read | — | — | direct | Read durable asset-pool batch progress and per-account results. This is the only state source after +asset-pools-batch-set; do not rescan accounts or loop +asset-pools-batch-get for verification. |
| `ai-slideshow publish +asset-pools-batch-cancel` | write | yes | — | direct | Request cancellation of a durable asset-pool batch job. Stops account work not yet started but does not roll back accounts already completed. |
| `ai-slideshow publish +schedule-plan-preview` | read | — | — | direct | Live-preview a durable schedule-plan operation without writing. --operation cancel-only is the primary way to inspect deletion of current eligible schedule items: it returns cancellable/protected counts by status and an opaque token for the matching batch. For --operation plan, use this before replace-non-published; unlike generic --dry-run, it asks the server to inspect current conflicts, account assets, product bindings, and BGM availability. After resolving account IDs in one bulk social-account +list call, invoke this preview directly; do not preflight with per-account asset, BGM, schedule, or publish-version calls. The response preview_token must be passed unchanged to the matching replace submission. |
| `ai-slideshow publish +schedule-plan-batch` | destructive | yes | `--yes` | async_run | Submit one durable asynchronous schedule-plan operation. --operation cancel-only is the primary batch deletion path for current eligible schedule items; it requires the matching preview token and reports cancelled, already cancelled, and protected results by prior status. For --operation plan, create MULTIPLE accounts or MULTIPLE occurrences. MUST use this command instead of looping social-account +schedule-list/+schedule-create/+schedule-delete or Python/shell scripts. One plan accepts up to 200 accounts and 5,000 total occurrences. BGM mode required makes an account fail when its pool has no valid BGM; it never silently creates a no-BGM occurrence. After submission, the only state source is +schedule-plan-status. When --bgm-policy required finishes with status succeeded, the server guarantees every created occurrence has a concrete BGM; use bgm_bound_count/summary.bgm_bound and never call schedule-list, bgm-asset-list, or routines to verify it. Inspect every failed/skipped account. replace-non-published requires the opaque preview token from a matching live preview and fails closed when the preview has drifted. --idempotency-key is required: reuse it only for retries of the same submission, and use a new key for an intentional new job. Copy full canonical account UUIDs and the preview token verbatim from the successful preview; never reconstruct them. |
| `ai-slideshow publish +schedule-plan-status` | read | — | — | direct | Read durable schedule-plan operation progress and per-account results. This is the only state source after submission. cancel-only results include cancelled and protected counts by prior status. For plan with --bgm-policy required and status succeeded, bgm_bound_count/summary.bgm_bound is the server-owned proof that every created occurrence has concrete BGM; never call schedule-list, bgm-asset-list, or routines for post-write verification, rescan accounts, or rely on /tmp state. |
| `ai-slideshow publish +schedule-plan-cancel` | write | yes | — | direct | Abort unfinished work in a durable schedule-plan job. This is job control only: it never deletes schedule items already created. Use +schedule-plan-preview/+schedule-plan-batch --operation cancel-only when the operator wants schedule items removed. |
| `ai-slideshow publish +config-get` | read | — | — | direct | Read account publish configuration, including the account-wide output language used for overlays, captions, and hashtags. |
| `ai-slideshow publish +config-update` | write | yes | — | direct | Update account publish settings such as output language, required hashtags, and approval-before-publish. |
| `ai-slideshow publish +config-batch-update` | write | yes | — | direct | Batch-update publish settings (output language, required hashtags, approval-before-publish) for up to 200 accounts in one call. Use instead of looping +config-update; returns a per-account summary. |
| `ai-slideshow publish +version-list` | read | — | — | direct | List account publish config versions. |
| `ai-slideshow publish +version-get` | read | — | — | direct | Read one account publish config version. |
| `ai-slideshow publish +version-create` | write | yes | — | direct | Create a draft account publish config version. |
| `ai-slideshow publish +version-activate` | write | yes | — | direct | Activate a publish config version and materialize schedule items. |
| `ai-slideshow publish +schedule-list` | read | — | — | direct | List account publish schedule items. |
| `ai-slideshow publish +schedule-get` | read | — | — | direct | Read one account publish schedule item. |
| `ai-slideshow publish +schedule-generate` | write | yes | — | async_run | Start content generation for one account publish schedule item. |
| `ai-slideshow publish +schedule-create` | write | yes | — | direct | Create one manual account publish schedule item. |
| `ai-slideshow publish +schedule-update` | write | yes | — | direct | Update one account publish schedule item. |
| `ai-slideshow publish +schedule-delete` | write | yes | — | direct | Cancel one account publish schedule item. |

### campaign-monitor

| command | risk | dry-run | confirm | execution | summary |
|---|---|---|---|---|---|
| `campaign-monitor +list` | read | — | — | direct | List campaign monitor collections available to the active workspace. |
| `campaign-monitor +get` | read | — | — | direct | Read one campaign monitor collection. |
| `campaign-monitor +creator-list` | read | — | — | direct | List creators covered by a campaign monitor. |
| `campaign-monitor +creator-add` | write | yes | — | direct | Track creators in a campaign so their matching posts sync in going forward. --url imports new creators by public profile URL via a background task (response data.url_import_task); --creator-id attaches creators already known to Museon. Verify with +creator-list later. |
| `campaign-monitor +creator-remove` | destructive | yes | `--yes` | direct | Stop tracking a creator in a campaign: removes the creator monitor and its derived content monitors from this campaign and resyncs. This does NOT delete the creator's social-platform account; explicit operator confirmation is required before running with --yes. Tracking is workspace-wide, so the monitor is only fully deleted when no other campaign references it. --creator-id is the creator_social_account_id from +creator-list. |
| `campaign-monitor +content-list` | read | — | — | direct | List posts/content covered by a campaign monitor. |
| `campaign-monitor +content-add` | write | yes | — | direct | Track individual posts in a campaign. --url imports new posts by public URL via a background task (response data.url_import_task); --content-id attaches posts already known to Museon. Verify with +content-list later. |
| `campaign-monitor +content-remove` | destructive | yes | `--yes` | direct | Remove one content record from a campaign monitor. This only removes the collection record from the campaign monitor (soft delete), it does NOT delete the original social-platform post; explicit operator confirmation is required before running with --yes. The collection_content_id comes from the +content-list response, and the response includes removed / missing detail. |
| `campaign-monitor +content-batch-remove` | destructive | yes | `--yes` | direct | Remove content records from a campaign monitor in batch. This only removes the collection record from the campaign monitor (soft delete), it does NOT delete the original social-platform post; explicit operator confirmation is required before running with --yes. Batch size <=100, split into multiple batches if exceeded; response includes removed / missing detail; collection_content_id comes from the +content-list response. |
| `campaign-monitor +summary` | read | — | — | direct | Read campaign monitor level performance summary. |
| `campaign-monitor +creator-get` | read | — | — | direct | Read one workspace-visible social account profile from Museon's store. |
| `campaign-monitor +post-list` | read | — | — | direct | List Museon-synced posts for one workspace-visible social account; not a live platform-history fetch. |
| `campaign-monitor +creator-performance-get` | read | — | — | direct | Read local synced performance history for one workspace-visible social account. |
| `campaign-monitor +post-get` | read | — | — | direct | Read one Museon-synced social post/content record. |
| `campaign-monitor +post-performance-get` | read | — | — | direct | Read local synced performance history for one social post/content record. |
| `campaign-monitor +post-resolve` | read | — | — | direct | Resolve an account publish schedule item to its published social post. |

### skills

| command | risk | dry-run | confirm | execution | summary |
|---|---|---|---|---|---|
| `skills +list` | read | — | — | direct | List business skills available to the current agent runtime. |
| `skills +get` | read | — | — | direct | Read one business skill by name. |
| `skills +create` | write | yes | — | direct | Create one workspace-private Museon skill from Markdown content; --is-public requires organization admin permission. |
| `skills +update` | write | yes | — | direct | Update a workspace-private Museon skill's Markdown content, description, reference, or active status; changing --is-public requires organization admin permission. |

### routines

| command | risk | dry-run | confirm | execution | summary |
|---|---|---|---|---|---|
| `routines +list` | read | — | — | direct | List routines visible to the current workspace. Each routine includes a ref — paste it into report markdown to embed a live schedule card. Lifecycle writes are only allowed on routines you own; when a routine belongs to someone else, surface the owner to the user instead of operating on it. |
| `routines +get` | read | — | — | direct | Read one routine, including its active trigger if present. Each routine includes a ref — paste it into report markdown to embed a live schedule card. Lifecycle writes are only allowed on routines you own; when a routine belongs to someone else, surface the owner to the user instead of operating on it. |
| `routines +create-ad-hoc` | write | yes | — | direct | Create an agent-owned ad-hoc routine and immediately register its trigger with Museon's scheduler. |
| `routines +create-draft` | write | yes | — | direct | Create a draft ad-hoc routine for user review without registering a trigger. |
| `routines +accept-draft` | write | yes | — | direct | Accept a draft ad-hoc routine and register its trigger with Museon's scheduler. |
| `routines +rebuild-ad-hoc` | write | yes | — | direct | Replace an existing ad-hoc routine with a new instruction and trigger, copying memory by default. |
| `routines +cancel` | write | yes | — | direct | Cancel the active trigger for a routine. |
| `routines +pause` | write | yes | — | direct | Pause the recurring trigger for a routine. |
| `routines +resume` | write | yes | — | direct | Resume the paused recurring trigger for a routine. |
| `routines +memory-get` | read | — | — | direct | Read the current effective memory snapshot for one routine. |
| `routines +record` | write | yes | — | direct | Record routine memory back to Museon. Routine output is captured automatically by the platform at turn end; kind=output remains only for backward compatibility. |

<!-- END GENERATED COMMANDS -->

## Adding a capability

1. Pick a domain from the `Domain` enum (new domains are a design discussion).
2. In `museoncli/domains/<domain>.py`: add the `CommandSpec`, the
   `_add_*_arguments` / `_build_*_arguments` pair, the executor, and the
   `EXECUTORS` entry.
3. Follow [cli-surface-conventions.md](cli-surface-conventions.md) — the
   conventions test will reject positional ids, `--offset`, snake_case enum
   values, or a write command without `--dry-run`.
4. Add parser/schema/payload/executor tests.
5. Run `uv run python scripts/gen_command_docs.py` to refresh this file.

Do not add flat self-discovery commands. Public business behavior belongs in a
domain command spec.
