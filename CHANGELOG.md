# Changelog

Museon CLI follows semantic versioning for its package and command contract.

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
