# Changelog

Museon CLI follows semantic versioning for its package and command contract.

## 0.18.0

- New `campaign-monitor +list-dimensions`: the campaign's type, its post scopes, and its dimensions (`ugc`: brief with its persona, persona, tag; other types: `creator_tag`), from `GET /agent-cli/campaign-monitors/{id}/dimensions`.
- New `--link-status linked` on `campaign-monitor +list-content` and `+list-creators`, matching the Campaign page's Approved scope.
- The campaign-monitor skill gains the analysis order: dimensions first, then the scope, coverage before per-brief numbers, tags overlap.
- Requires the Museon API with `GET /agent-cli/campaign-monitors/{id}/dimensions` deployed.

## 0.17.1

- `hireaicreator video +create-from-upload` documents `scheduled_at`: omit it or pass null and the video stays `approved` and never publishes until `video +bulk-schedule` gives it a time. There is no publish-now value; pass a time a few minutes ahead to publish soon. The command now warns and lists the video IDs it left unscheduled.
- No API change is required.

## 0.17.0

- New staff commands for social app versions on cloud phones:
  - `cloud-phone app +list` reads installed and team-pinned versions of YouTube, Facebook, Instagram and TikTok live from up to 50 phones (`--phone-id`) or accounts (`--account-id`). Each app reports `current`, `outdated`, `ahead`, `installing`, `missing` or `unpinned`.
  - `cloud-phone app-upgrade +preview` shows which phones an upgrade would move up to the team's pinned version and why others are skipped; nothing changes.
  - `cloud-phone app-upgrade +create` upgrades outdated apps to the pinned version in the background (never downgrades or installs a missing app). It needs `--yes` and an idempotency key; a retry with the same key never upgrades a phone twice. Follow progress by rerunning `cloud-phone app +list`.
- `publish job +list` and `+get` return each job's `delivery`: `stage` (`verifying` means the publishing service already reported and Museon is confirming the post on the platform until `verification.deadline_at`), the service's own report as `upstream`, and `verification`. It is null for older jobs.
- Requires the Museon API with `GET /agent-cli/cloud-phones/apps`, `POST /agent-cli/cloud-phones/app-upgrades/preview`, `POST /agent-cli/cloud-phones/app-upgrades`, and `delivery` on publish jobs.

## 0.16.0

- `social-account +connect-adb` routes ADB through a local relay. Museon now shuts down a cloud phone whose lease nobody renews; the relay renews it at most once a minute while ADB traffic flows and exits after 15 minutes without ADB traffic, so a phone stays on while a script or agent operates it and shuts down about 15 minutes after the last ADB command. An open but idle ADB connection sends no traffic and does not keep the phone on. The returned serial is the relay's local address (`127.0.0.1:<port>`); a later `+connect-adb` for the same account reuses it.
- New `social-account +renew-phone-lease`: keeps an account's cloud phone on for 15 more minutes. The relay runs it; scripts that hold ADB some other way can run it themselves.
- Requires the Museon API with `POST /agent-cli/social-accounts/{account_id}/phone-lease`.

## 0.15.0

- 新增员工云机与 IP 管理：查询、批量添加、检测、分组、供应商、换 IP、待处理事项及资源回收。
- 连接凭据仅导出至受保护的本地文件；批量操作保留逐项失败，查询显示数据更新时间。

## 0.14.0

- `publish post +schedule` takes an optional `music_url` per item: a TikTok post link (`/video/<id>` or `/photo/<id>`) whose sound the cloud phone reuses as the post's background music, like "use this sound". Sound pages (`/music/...`), short links and bare IDs are rejected before any upload. Accounts not on a cloud phone publish without it; an item without it keeps the cloud phone's random sound.
- Uses the existing `bgm_config.ref_video_id` of `POST /api/v2/pool-accounts/publish`; no new API is required.

## 0.13.0

- `publish post +schedule` publishes TikTok photo sets: an item takes `image_files` (local images, uploaded in order) or `image_media_ids` (1-30 images; the first is the cover) instead of a video `file` / `media_id`. Photo sets publish to TikTok accounts on a GeeLark cloud phone; `product_id` stays video-only. Retries reuse each uploaded image under the same idempotency key.
- Requires the Museon API that accepts `image_media_ids` on `POST /api/v2/pool-accounts/publish`.

## 0.12.0

- New `publish` domain: publish finished videos to the social accounts bound to a workspace, without HireAICreator campaigns.
  - `publish account +list` lists the workspace's bound accounts (filter by platform and device kind).
  - `publish post +schedule` uploads local videos (or reuses media IDs) and schedules each on the chosen accounts with a caption, at a scheduled time or `now=true`. It sends an idempotency key: a retry reuses uploads and the server returns the batch it already accepted instead of posting twice. Resend the same input unchanged when retrying.
  - `publish job +list`, `+get` and `+cancel` read and cancel the resulting publish jobs.

## 0.11.0

- Breaking: `hireaicreator video +publish-local` and `hireaicreator video +create-from-upload` require `campaign_id`. Uploaded videos without a campaign published but never reached the Campaign dashboard or Campaign sync, and a campaign cannot be assigned after creation. Requests without one are rejected before any network call; look the id up with `workspace select --id <workspace>` followed by `agentic-campaign +list --all`.
- `video +publish-local` binds the campaign to the idempotency key. Receipts written by earlier versions stay readable, and a batch submitted before this change whose outcome is unknown is replayed with its original request first.

## 0.9.1

- `hireaicreator plan +create` accepts optional `generation_options` in structured JSON, including `compshare-h3`, video duration, audio, image settings, and Actor reference image media IDs.
- Provider model IDs retain their original spelling when sent to the API.

## 0.8.2

- `hireaicreator account +list` takes a repeatable `--tags` to filter by workspace account tags (any match); tags must not contain commas.

## 0.8.1

- Fix: `--all` now works on commands whose records sit one level deeper (`data.data.<records>`), e.g. `campaign-monitor +list-creators`.
- Fix: a usage error for a missing required flag now names its `command` and points at that command's `--help`.

## 0.8.0

- Errors: every failure carries `command` and an `error` object (`code`, `message`, `server_code`, `http_status`, `retryable`, `hint`); `reason` is always a category. Usage errors are JSON on stdout. New exit codes: 3 not found, 4 authentication required, 5 conflict.
- Paged reads add a normalized `page_info`; read commands with `--page` take `--all`.
- Every flag has help and every command shows a runnable example; `schema` accepts CLI paths.
- HireAICreator actions are now a verb or a verb with its object (51 renames, e.g. `video +from-upload` → `+create-from-upload`, `test-group +accounts-set` → `+set-accounts`, `warmup +journeys` → `+list-journeys`). Old names keep working, hidden from help, and return a deprecation warning; `schema` lists them under `deprecated_aliases`.
- The same rule now covers every other domain (70 renames, e.g. `research +web-research` → `+search-web`, `social-account +connect-link-create` → `+create-connect-link`, `campaign-monitor +creator-list` → `+list-creators`, `ai-slideshow publish +schedule-plan-batch` → `+submit-schedule-plan`, `routines +memory-get` → `+get-memory`). Old names keep working the same way.
- Fix: `ai-slideshow generation +create` returns its run and frontend links again.

## 0.7.3

- 新增 `hireaicreator actor +resolve`：一次最多读取 200 个 Actor 及其参考图 URL。
- 新增 `hireaicreator product +list`：一次读取工作区产品的描述、卖点、目标人群和全部图片素材。
- 新增 `hireaicreator video +from-upload`：把 `media +upload` 上传的外部成片登记为发布任务，带文案和排期，支持幂等重试。
- 新增外部生成视频上传与排期发布的 best practice（HireAICreator skill 参考文档），要求每条视频只发给同一个 Actor 名下的账号。

## 0.7.2

- Add `campaign-monitor +period-performance` for frontend-aligned period-end snapshot comparisons.
- Clarify that `campaign-monitor +summary` reports daily content-trend totals rather than Period Performance snapshots.

## 0.7.1

- 新增 Actor 批量权限与锁诊断、跨工作区复制和移动，以及实时操作预览。
- 执行需要明确确认、匹配的预览与幂等键；保留服务端冲突，防止自动覆盖变化或重复复制。
- 更新 Mel 工作流，说明共享编辑锁的复制解决方式与目标工作区回读。

## 0.7.0

- Add staff-only, read-only operational commands for deployed API code, bounded
  Supabase queries, Cloud Logging, and the Agents per-turn timeline.

## 0.6.3

- Add complete HireAICreator Test Group, warmup, video review and scheduling, Format, and Clip operations for Codex and Mel.
- Preserve workspace authorization, optimistic concurrency, explicit confirmations, and endpoint-supported idempotency.
- Treat successful HTTP 204 deletion responses as success.
- Include manual Actor video creation and publish matching workflow skills and command discovery.

## 0.6.2

- Added HireAICreator account Actor and Persona binding commands with publish asset readback, workspace selection, and dry-run validation.

## 0.6.1

- Removed the low-level `hireaicreator test-plan +ensure` command and made Test Group listing work without a Plan ID.
- Added Persona-based Actor creation and generation batch commands, including candidate selection.

## 0.6.0

- Replaced the former AI Hook public domain with `hireaicreator`, exposing 45 commands including read-only item and batch history queries.
- Added `media` upload, import, read, generation, and status commands with explicit idempotency and billing boundaries.
- Added `ai-slideshow` with 32 asset, generation, publish configuration, version, scheduling, and batch publishing commands.
- Kept 13 selected `social-account` commands and retired the former account-operation, account-publish, asset, generation, product, evaluator, and agentic-campaign top-level domains.
- Consolidated the public Agent Skills into five packages: base, research, HireAICreator, AI Slideshow, and campaign monitor.
- Kept artifacts, routines, content analysis, media, and social-account atomic guidance under the base Skill, while preserving research and campaign monitoring as separate workflows.
