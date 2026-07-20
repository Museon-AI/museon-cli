# museoncli public surface

Museon CLI exposes a small, domain-oriented command surface. Agents must
discover capabilities from `museoncli schema` and call domain commands only —
never rely on memory or older transcripts for the command list.

## Infrastructure commands

- `version` / `health` / `whoami`
- `setup --agent [auto|codex|claude-code|cursor|all]`
- `config get` / `config set`
- `auth start` / `auth finish` / `auth login` / `auth status` / `auth logout`
- `workspace list` / `workspace current` / `workspace select`
- `schema [<domain>[.<shortcut>]]`

## Business commands

Generated from the registry — run `uv run python scripts/gen_command_docs.py`
after changing specs; `tests/test_docs_sync.py` fails CI on drift.

<!-- BEGIN GENERATED COMMANDS (scripts/gen_command_docs.py) -->

106 commands across 12 domains (source of truth: `museoncli schema`).

### research

| command | risk | dry-run | confirm | execution | summary |
|---|---|---|---|---|---|
| `research +web-research` | read | — | — | direct | Research public web evidence from a query or URL, including page text and official-site visual assets. |
| `research +social-media-search` | read | — | — | direct | Search social-native evidence across TikTok, Instagram, YouTube, and XHS using a stable platform and intent contract. |
| `research +community-search` | read | — | — | direct | Search community evidence across X, Reddit, and LinkedIn using a stable platform and intent contract. |
| `research +visual-analyze` | read | — | — | direct | Analyze one or more image/video URLs with a business prompt. If a TikTok or signed CDN URL cannot be prepared, import it as Museon media first and retry with the returned stable media URL. |

### content-analysis

| command | risk | dry-run | confirm | execution | summary |
|---|---|---|---|---|---|
| `content-analysis +run` | write | yes | — | async_run | Run video-only Content Analyzer for a platform URL, uploaded Museon media ID, or local video file upload. |
| `content-analysis +get` | read | — | — | direct | Read one Content Analyzer run by ID. |
| `content-analysis +list` | read | — | — | direct | List Content Analyzer runs in the selected workspace. |

### asset

| command | risk | dry-run | confirm | execution | summary |
|---|---|---|---|---|---|
| `asset +list` | read | — | — | direct | List reusable product, persona, topic, format, or media assets. For multiple search concepts, repeat --search-term (max 20); do not join terms with commas in --search. Each resource includes a ref — paste it into report/pitchdeck markdown to embed a live card. Inline in a sentence renders a chip; alone on its own line renders a full card. |
| `asset +get` | read | — | — | direct | Read one reusable product, persona, topic, format, or media asset. Each resource includes a ref — paste it into report/pitchdeck markdown to embed a live card. Inline in a sentence renders a chip; alone on its own line renders a full card. |
| `asset +get-batch` | read | — | — | direct | Read 1-100 Formats by exact IDs in one request. When two or more known Format IDs must be queried, MUST use this command instead of looping asset +get. Items preserve request order; missing or inaccessible IDs are returned in missing_ids. |
| `asset +options` | read | — | — | direct | List canonical values and labels for an asset field. Product category supports optional intent search, so a term such as education, edtech, or 教育 returns the relevant learning categories without trial writes. |
| `asset +create` | write | yes | — | direct | Create one reusable product, persona, topic, format, or media asset. Product requires name, category, and description; discover canonical categories with asset +options and use --dry-run for authoritative server validation without writing. |
| `asset +update` | write | yes | — | direct | Update one reusable product, persona, topic, format, or media asset. |
| `asset +delete` | destructive | yes | `--yes` | direct | Delete one reusable product, persona, topic, format, or media asset. |

### artifacts

| command | risk | dry-run | confirm | execution | summary |
|---|---|---|---|---|---|
| `artifacts +validate` | read | — | — | direct | Validate one local Artifact Markdown file before upload. Checks frontmatter, report-directions YAML and field schema, preview URLs, optional stats, and duplicate social Embed placements. This command performs no network calls. |
| `artifacts +upload` | write | yes | — | direct | Upload or replace one local agent file artifact through multipart form-data. Markdown uploads are public by default. After upload, give BOTH links when both exist: data.public_url (public share link, anyone with the link) and data.url (workspace/private link, logged-in workspace members). Use --no-public only when the user explicitly wants a private artifact (then only data.url). To embed resources inside markdown, paste their ready-made ref ([name](https://www.museon.ai/section/id)) from asset +get/+list, generation +get/+list/+create, or routines +get/+list verbatim. For generation batch/summary artifacts, paste each generation ref alone on its own line so it renders as a card; do not hand-write generation links, file names, local paths, or storage paths as links. You can also paste a raw TikTok, Instagram, or YouTube URL on its own line to embed a player. |
| `artifacts +share` | write | yes | — | direct | Re-enable public internet access for one markdown artifact (for example after +unshare). Prefer +upload defaults for new reports. |
| `artifacts +unshare` | write | yes | — | direct | Revoke the public internet link for one artifact. Use only when the user explicitly wants to revoke public access. |

### generation

| command | risk | dry-run | confirm | execution | summary |
|---|---|---|---|---|---|
| `generation +create` | write | yes | — | async_run | Create and start one media generation — Museon's image-post (生图/图文) generation capability. Current type: slideshow, driven by format, topic, persona, and optional product assets. When the user asks to generate images or image posts but the workspace lacks these assets, do not refuse and do not ask the customer for asset IDs — follow the Content Replication flow to guide asset preparation first. Responses include a ready-made generation ref and a recommended wakeup delay. Present the ref in the current final response, tell the customer generation is in progress and the link shows live progress, then use the returned delay for the next status check instead of choosing one yourself. |
| `generation +get` | read | — | — | direct | Read one media generation by id. Current type: slideshow. The response includes a ready-made generation ref; completed generations include grid_media, slide_media, and result_preview_image_urls when result media is available. |
| `generation +list` | read | — | — | direct | List media generations in the current workspace. Current type: slideshow. Each item includes a ready-made generation ref; completed generations include grid_media, slide_media, and result_preview_image_urls when result media is available. |

### social-account

| command | risk | dry-run | confirm | execution | summary |
|---|---|---|---|---|---|
| `social-account +list` | read | — | — | direct | List managed social accounts with account-operation filters. For multiple known handles, repeat --search-term (max 100) in one request; do not concatenate handles into --search or page-scan the account list. The list payload does not include publish asset refs; use +assets-get for persona/product/format/topic bindings. |
| `social-account +get` | read | — | — | direct | Read one workspace social account. |
| `social-account +connect-link-create` | write | yes | — | direct | Create a workspace self-authorization link to connect a user-owned social account. Supports TikTok, Instagram, Facebook, LinkedIn, and X. |
| `social-account +connect-link-status` | read | — | — | direct | Read or wait for the authorization result of a social account connect link. |
| `social-account +performance-get` | read | — | — | direct | Live-read performance for one social account: authorized channels first, with automatic public-data fallback when authorization is missing/expired or the platform exposes no history. Payload `source` marks provenance (official/managed analytics vs public_data) — relay that difference to customers and never show internal retrieval details. First page includes the profile block; posts paginate via --cursor. |
| `social-account +assets-get` | read | — | — | direct | Read publish asset refs for exactly ONE social account. For two or more accounts, MUST use account-publish +asset-pools-batch-get instead of looping. |
| `social-account +assets-set` | write | yes | — | direct | Update publish asset refs for exactly ONE account and/or its workspace tags. For multi-account publish assets, MUST use account-publish +asset-pools-batch-preview then +asset-pools-batch-set instead of looping. For a fully-managed account, first relay the returned impact to the user; retry with --managed-operation-approved only after explicit confirmation. |
| `social-account +bgm-asset-list` | read | — | — | direct | List workspace BGM assets (same-style reference videos). |
| `social-account +bgm-asset-create` | write | yes | — | direct | Create a workspace BGM asset from a TikTok post URL. |
| `social-account +config-get` | read | — | — | direct | Read account publish configuration, including the account-wide output language used for overlays, captions, and hashtags. |
| `social-account +config-update` | write | yes | — | direct | Update account publish settings such as output language, required hashtags, and approval-before-publish. |
| `social-account +version-list` | read | — | — | direct | List account publish config versions. |
| `social-account +version-get` | read | — | — | direct | Read one account publish config version. |
| `social-account +version-create` | write | yes | — | direct | Create a draft account publish config version. |
| `social-account +version-activate` | write | yes | — | direct | Activate a publish config version and materialize schedule items. |
| `social-account +schedule-list` | read | — | — | direct | List account publish schedule items. |
| `social-account +schedule-get` | read | — | — | direct | Read one account publish schedule item. |
| `social-account +schedule-generate` | write | yes | — | async_run | Start content generation for one account publish schedule item. |
| `social-account +schedule-create` | write | yes | — | direct | Create one manual account publish schedule item. |
| `social-account +schedule-update` | write | yes | — | direct | Update one account publish schedule item. |
| `social-account +schedule-delete` | write | yes | — | direct | Cancel one account publish schedule item. |
| `social-account +profile-edit-draft` | read | — | — | direct | Generate proposed TikTok display name, bio, or avatar drafts for one account. |
| `social-account +profile-edit-submit` | write | yes | — | async_run | Submit a TikTok profile edit task for one account. Use +profile-edit-status to confirm completion. |
| `social-account +profile-edit-status` | read | — | — | direct | Read execution status for a profile edit task. |

### account-publish

| command | risk | dry-run | confirm | execution | summary |
|---|---|---|---|---|---|
| `account-publish +asset-pools-batch-get` | read | — | — | direct | Read effective persona, product, format, topic, and BGM pools for MULTIPLE accounts in one request, with per-account issues and hydrated resource details by default. MUST use this for multi-account audits instead of looping social-account +assets-get; keep that single command for small, precise one-account reads. This batch command is also valid for a complete five-pool inspection of one account. |
| `account-publish +asset-pools-batch-preview` | read | — | — | direct | Live-preview one multi-account asset-pool change without writing. Supports a uniform patch plus per-account precise overrides for persona, product, formats, topics, and BGM. Always run this before +asset-pools-batch-set, present every changed/skipped/failed account and existing-schedule impact, then obtain explicit approval. Fully-managed accounts fail per-account in v1 and cannot be bypassed. |
| `account-publish +asset-pools-batch-set` | destructive | yes | `--yes` | async_run | Submit one durable Cloud Task job to change publish asset pools for MULTIPLE accounts. MUST use this instead of looping social-account +assets-set or writing Python/shell scripts; keep the single command for small, precise one-account edits. This batch command is preferred when atomically configuring all five pools for one account. Requires the opaque token and identical normalized patches from a fresh live preview, plus a stable idempotency key and --yes. After submission, poll only +asset-pools-batch-status and inspect every failed/skipped account. Fully-managed accounts fail per-account in v1 and cannot be bypassed. |
| `account-publish +asset-pools-batch-status` | read | — | — | direct | Read durable asset-pool batch progress and per-account results. This is the only state source after +asset-pools-batch-set; do not rescan accounts or loop social-account +assets-get for verification. |
| `account-publish +asset-pools-batch-cancel` | write | yes | — | direct | Request cancellation of a durable asset-pool batch job. Stops account work not yet started but does not roll back accounts already completed. |
| `account-publish +schedule-plan-preview` | read | — | — | direct | Live-preview a durable schedule-plan operation without writing. --operation cancel-only is the primary way to inspect deletion of current eligible schedule items: it returns cancellable/protected counts by status and an opaque token for the matching batch. For --operation plan, use this before replace-non-published; unlike generic --dry-run, it asks the server to inspect current conflicts, account assets, product bindings, and BGM availability. After resolving account IDs in one bulk social-account +list call, invoke this preview directly; do not preflight with per-account asset, BGM, schedule, or publish-version calls. The response preview_token must be passed unchanged to the matching replace submission. |
| `account-publish +schedule-plan-batch` | destructive | yes | `--yes` | async_run | Submit one durable asynchronous schedule-plan operation. --operation cancel-only is the primary batch deletion path for current eligible schedule items; it requires the matching preview token and reports cancelled, already cancelled, and protected results by prior status. For --operation plan, create MULTIPLE accounts or MULTIPLE occurrences. MUST use this command instead of looping social-account +schedule-list/+schedule-create/+schedule-delete or Python/shell scripts. One plan accepts up to 200 accounts and 5,000 total occurrences. BGM mode required makes an account fail when its pool has no valid BGM; it never silently creates a no-BGM occurrence. After submission, the only state source is +schedule-plan-status. When --bgm-policy required finishes with status succeeded, the server guarantees every created occurrence has a concrete BGM; use bgm_bound_count/summary.bgm_bound and never call schedule-list, bgm-asset-list, or routines to verify it. Inspect every failed/skipped account. replace-non-published requires the opaque preview token from a matching live preview and fails closed when the preview has drifted. --idempotency-key is required: reuse it only for retries of the same submission, and use a new key for an intentional new job. Copy full canonical account UUIDs and the preview token verbatim from the successful preview; never reconstruct them. |
| `account-publish +schedule-plan-status` | read | — | — | direct | Read durable schedule-plan operation progress and per-account results. This is the only state source after submission. cancel-only results include cancelled and protected counts by prior status. For plan with --bgm-policy required and status succeeded, bgm_bound_count/summary.bgm_bound is the server-owned proof that every created occurrence has concrete BGM; never call schedule-list, bgm-asset-list, or routines for post-write verification, rescan accounts, or rely on /tmp state. |
| `account-publish +schedule-plan-cancel` | write | yes | — | direct | Abort unfinished work in a durable schedule-plan job. This is job control only: it never deletes schedule items already created. Use +schedule-plan-preview/+schedule-plan-batch --operation cancel-only when the operator wants schedule items removed. |

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

### evaluator

| command | risk | dry-run | confirm | execution | summary |
|---|---|---|---|---|---|
| `evaluator +kind-list` | read | — | — | direct | List evaluator kind keys configured in the current workspace. |
| `evaluator +list` | read | — | — | direct | List evaluator definitions available to the current agent runtime. |
| `evaluator +get` | read | — | — | direct | Read one evaluator definition by ID. |
| `evaluator +create` | write | yes | — | direct | Create one prompt-based evaluator definition. |
| `evaluator +update` | write | yes | — | direct | Update an evaluator definition's prompt, metadata, or visibility. |
| `evaluator +run` | write | yes | — | direct | Run an evaluator against text, media, research, or generation output. |
| `evaluator +run-list` | read | — | — | direct | List evaluator runs for the current workspace. |
| `evaluator +run-get` | read | — | — | direct | Read one evaluator run by ID. |

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

### account-operation

| command | risk | dry-run | confirm | execution | summary |
|---|---|---|---|---|---|
| `account-operation +submit` | write | yes | — | direct | Submit a pool account into automated operation (registers + binds the agent conversation). Response data.research_disposition tells the outcome: established_seeded=直接 active(继承既有排期元素,无需调研); research_directed/inductive/full=进入 onboarding 调研. When a Product is resolved, pass optional --product-id once to bind product truth, description/media, and promotion guidance to the operation; an explicit audience action is optional. Same-Product retries are idempotent and a different Product is rejected. Submitting is the explicit Account Publish -> fully-managed mode switch: an account_publish allocation is atomically transferred when no scheduled, generating, generated, or publishing work remains, while existing publish configuration is preserved. Otherwise the API returns account_publish_schedule_conflict with blocking_schedule_counts. Pass --research-prompt/--reference-url ONLY when the operator explicitly mentioned research direction or benchmark accounts. When submitting MULTIPLE accounts in one turn, reply ONE consolidated confirmation card (per-account row: username/op_id/disposition) instead of N cards. NOTE: an account already operating under a DIFFERENT session is NOT moved here — you get the existing op back unchanged (no rebind); prefer +submit-batch which reports this explicitly in meta.existing[] with a conflict link. |
| `account-operation +submit-batch` | write | yes | — | direct | Batch-submit MULTIPLE pool accounts into automated operation in ONE call — PREFERRED over N single +submit calls when the operator hands over a batch. All accounts bind to the current session; account-operation submission does NOT create a campaign monitor. One optional --product-id identifies the shared Product/CTA context for the ENTIRE batch; one batch has at most one Product and per-account overrides are forbidden. Shared --niche/--research-prompt/--reference-url apply to every account. Reply ONE consolidated confirmation card from the response rows (username/op_id/research_disposition). IMPORTANT: per-account failures are isolated — ALWAYS check meta.failed[] (each {pool_account_id, error}); if non-empty, call out the dropped accounts in the confirmation and re-submit them, do NOT assume all landed. ALSO check meta.existing[]: these accounts were ALREADY in operation (not new). outcome='existing_other_session' means the account is already running under a DIFFERENT session and was NOT added here — pick a fresh 账号库 account instead, and surface conflict_session_url so the operator can open that session to check. outcome='occupied_other_business' means the account is already used by another business (for example campaign) and was NOT taken into 全托管运营 — pick a different 账号库 (unoccupied) account. An idle account_publish holder is transferred automatically during submit; outcome='account_publish_schedule_conflict' means scheduled, generating, generated, or publishing work still blocks that transfer. Report blocking_schedule_counts; cancel eligible work or wait for publishing to finish, then retry after confirmation. outcome='not_in_workspace' means the account does not belong to this workspace's account pool and was NOT taken into 全托管运营 — pick an account from this workspace. outcome='existing_product_conflict' means that account is already managed for another Product and was NOT changed; report current_product_id and requested_product_id instead of silently switching it. meta.created_count = how many were genuinely new. |
| `account-operation +get` | read | — | — | direct | Get one operated account (lifecycle, health, baseline). |
| `account-operation +list` | read | — | — | direct | List operated accounts in the workspace. |
| `account-operation +ops-status` | read | — | — | direct | Whole-fleet operation/publish status for the workspace in ONE aggregate query — USE THIS instead of sampling a few accounts with +get/+runs before concluding anything about publishing. IMPORTANT: a scheduled backlog draining over hours is the DESIGNED steady state (finite generation throughput), so backlog/lag alone is NEVER a problem — report red ONLY on capacity.due_demand_exceeds_capacity, delivery stage overdue_items, pipeline.stuck > 0, or accounts_needing_intervention > 0. Returns: capacity {backlog_items (legacy all-scheduled), due_backlog_items (headline), scheduled_future_items, drain_rate_24h_per_hour, eta_hours_to_clear_due, demand_per_day, capacity_24h_per_day, due_demand_exceeds_capacity, publish_success_rate_24h (null = no outcomes)}; accounts_needing_intervention (THE number: stalled accounts in the cold_start/active/recovering cohort); delivery_stages (managed lane) + manual_delivery_stages (one_off outside the managed cohort), each split into future_reservations, due_unclaimed, awaiting_publish_approval, generation_done_awaiting_handoff, delivery_executing, and delivery_succeeded_awaiting_visibility with oldest_age_seconds / overdue_items; pipeline in 条 {published_24h, in_flight, pending (waiting its turn = normal), stuck (FIFO pipeline PASSED IT OVER = real), failed_24h, total = their sum}; account_health[] per cohort lifecycle {accounts = producing + stalled + not_ready}; lifecycle_funnel[] (all lifecycles, plain counts); failed_reasons[] {code, label, items, distinct_accounts} over failed_reasons_window (--window 24h\|7d, default 24h). Item stats cover source='one_off' items of accounts under active operation. Read-only. |
| `account-operation +runs` | read | — | — | direct | List an operated account's daily runs (steps, attribution flag, schedule result). |
| `account-operation +tags` | read | — | — | direct | List an operated account's element tags (format/topic/combo lifecycle). |
| `account-operation +attribution` | read | — | — | direct | List an operated account's attribution reports (comment classes, recommendation, decision). |
| `account-operation +plan-submit` | write | yes | — | direct | Write back the onboarding/reset research plan (seed formats/topics) -> cold_start. |
| `account-operation +set-persona` | write | yes | — | direct | Author & attach the account's persona (REQUIRED first step of onboarding research, BEFORE +plan-submit). 全托管 accounts have no persona ref, so the publish pipeline generates from the persona set here; without it, generation fails. Define {name, description, tags} from research: for a 对标账号 (reference_url) capture that creator's voice/audience/style; for established_seeded use the account's OWN seed content; otherwise from open research. Creates a workspace persona and sets account_operations.persona_id. Idempotent-safe to re-call to replace the persona. |
| `account-operation +strategy-decide` | write | yes | — | direct | Decide the attribution review (human override or auto timeout) and resume the daily run. |
| `account-operation +stop` | write | yes | — | direct | Retire an account from automated operation (TERMINAL). USE WHEN the operator removes an account from 全托管 — e.g. conflict accounts being replaced by a new batch (历史冲突，换一批账号), or the operator says an account should no longer be operated. IMPORTANT: submitting replacement accounts does NOT retire the originals — without +stop they stay live and the system keeps dispatching research/persona/daily-run tasks for them forever. Full GC: cancels the op's pending schedule items, releases the account reservation, unbinds the work session, detaches the campaign, and frees the account so it can be +submit-ed afresh later. Pass --reason quoting the operator's instruction (audit trail). |
| `account-operation +elements-replace` | write | yes | — | direct | Weak recovery write-back: add new formats/topics and pause failing ones. |

<!-- END GENERATED COMMANDS -->

## Contract notes

- Output is always JSON: `{"ok": true, ...}` / `{"ok": false, "reason", "detail"}`.
- Agent-sandbox results above the size threshold use the generic
  `status:large_json_offloaded` success manifest; this is an output transport
  policy, not a per-domain command contract or API response change.
- Every request carries `X-CLI-Version`; servers below the minimum reply
  `cli_outdated` with upgrade instructions.
- Remote commands require browser authorization and the `agent_cli.access`
  scope. Workspace membership, roles, and target-resource access are evaluated
  by Museon on every request; there is no public/internal command split.
- Surface rules (ids, pagination, enum casing, `--dry-run` / `--yes`) live in
  [cli-surface-conventions.md](cli-surface-conventions.md).
