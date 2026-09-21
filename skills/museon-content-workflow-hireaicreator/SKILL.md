---
name: museon-content-workflow-hireaicreator
description: "Operate HireAICreator with Museon CLI: find accounts and creative resources, operate Test Groups and warmup, inspect capacity, register Clips, generate or edit videos, schedule authorized work, and verify delivery. Use for HireAICreator business objects, not generic media analysis or external social research."
metadata:
  requires:
    bins: ["museoncli"]
    skills: ["museon-content-workflow-base"]
  cliHelp: "museoncli schema hireaicreator"
---

# HireAICreator workflows

**CRITICAL — first read [the base skill](../museon-content-workflow-base/SKILL.md).**

## Shortcuts

Use the `hireaicreator` domain directly. Inspect the live command schema before constructing a request; resource IDs, versions, allowed fields and response facts come from the service. Ordinary API-key access is supported; a sandbox capability rejected by these routes is an authentication boundary, not a reason to substitute another business domain.

Read the relevant section of [the ten scenarios](references/top-10-scenarios.md). It defines inputs, stage facts, completion conditions and recovery boundaries. Compose existing commands with Bash and deterministic JSON checks; the skill does not introduce a workflow engine.

For historical generated footage or generation batch progress, read [history and batches](references/history-and-batches.md).

## Choose the requested workflow

For downloadable videos, choose between an unbound Actor/Persona video and an account-bound unscheduled video using `video +create`. If an account is named, read `account +assets-get` first; account mode derives Actor/Persona from that binding. Actor mode takes explicit Actor and Persona IDs. Preserve the user's requested composition (`hook-only`, `demo`, `clips`, or `demo-only`) instead of reducing every request to Hook-only. Manual delivery omits `scheduled_at`; selecting an account does not itself authorize publishing. Multiple account-bound videos can also use a `fixed-count` plan without schedule slots. Neither creating a video nor creating a plan without `start_generation` proves generation started.

Read back created IDs and versions, then generate, inspect actual media, export, and verify each export before sharing. Use a stable idempotency key wherever the command declares one. Resume existing IDs after interruption. For configured automated publication, use the Test Group or warmup workflow below rather than claiming the CLI is limited to manual delivery.

Read [lifecycle operations](references/lifecycle-operations.md) for the full Test Group, warmup, Format and video paths, including preview/confirmation and version checks. Supply a command's `--yes` when the user's existing authorization already covers that exact operation; the flag records authorization and does not grant permission to expand the task. `--dry-run` validates local input without making an API call, while a service preview reads live blockers and allocations.

Pass explicit `--workspace-id` on every workspace-scoped command after resolving the user's workspace; resource-scoped commands do not accept that flag. Do not rely on a workspace selection surviving a new agent turn. If a result is offloaded, read `raw_result.path` (or the local path supplied in the large-result manifest) before interpreting `data: null` as empty data.

A 422 validation error or a 404 response does not prove write permission or end-to-end success. Do not probe unrelated write routes to infer a permissions map. Report the actual command and response; for host-managed authentication, do not promise an `auth start` / login switch that the host prohibits. Read schema again when a command is unavailable, and report a release mismatch rather than inventing a command.

## Mental model

- Actor is an on-camera identity; Persona is a separate content/personality resource. They have separate IDs. An account binding is evidence of their relationship, not permission to interchange them.
- Format, reference Hook, generated Hook item, Recipe, POV, BGM and Clip are different resources. Preserve the actual selected IDs across steps. A Test Group, its historical Run and an individual Video are also different scopes.
- For writes, fix the authorized IDs and desired change, read current versions, submit, then read the same objects again. An acknowledgement, preview, or `readiness.ready` is not a completed output.

## Account Actor and Persona bindings

Find accounts with `account +list` using exact handles and inspect all matching pages. Resolve Actors with `actor +list` / `actor +get`; use the Actor's `source_persona_id` to identify its Persona and disambiguate duplicate Actor names by ID and reference image. If `source_persona_id` is null (including reference Actors), inspect the named account’s current Persona or an explicit previously authorized binding. If the mapping remains ambiguous, ask the user; do not infer it from names or appearance. Read current bindings with `account +assets-get --id <pool-account-id>`. Apply `account +actor-set --id <pool-account-id> --actor-id <actor-id>` and `account +persona-set --id <pool-account-id> --persona-id <persona-id>` in the selected or explicit workspace, then read `account +assets-get` again to verify both IDs. The two writes are separate receipts; report any partial success. Only pass `--managed-operation-approved` when that additional change is explicitly authorized.

## Actor 工作区分配与锁处理

用 `actor +access --workspace-id <source> --actor-ids <id>` 批量读取权限、绑定锁和解决方式；多个 Actor 重复传 `--actor-ids`。复制或移动前调用 `actor +assign-preview`，明确源 `--workspace-id`、`--target-workspace-id` 与 `--mode copy|move`，检查所有 blockers。复制保留原人脸并创建独立 Actor；移动保留 Actor ID，有账号绑定或生成中的 Actor 不能直接移动。共享编辑锁通过复制后使用新 Actor 解决，不支持强制解锁。

只对已授权且 `can_execute` 的预览执行 `actor +assign`，原样传回同一组参数和 `--preview-token`、稳定的 `--idempotency-key`，并用 `--yes` 记录确认。整批原子执行，状态漂移或幂等冲突应停止并说明，不能自动刷新预览覆盖变化，未知结果不能换新 key 重试。`--dry-run` 不读取服务端状态。执行后使用返回的 Actor IDs 在目标工作区调用 `actor +access` 验证；账号绑定另走 `account +actor-set`，复制不会自动迁移 Persona、成片或发布任务。

## DON'T

Keep partial failures, missing pages and unknown outcomes visible. Do not refresh a conflicting version and silently overwrite, choose a new idempotency key for an ambiguous write, or cancel/recreate a group to simulate unsupported migration.

## Relationships

Use `media` for file ingestion, standalone prompt-based image/video generation, and media-record verification. Its generation receipt does not prove that an HireAICreator plan or video was generated. Use `research` for optional external references and `content-analysis` for video analysis; the HireAICreator service owns its plan, generation and publication facts.
