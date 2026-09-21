# Changelog

Museon CLI follows semantic versioning for its package and command contract.

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
