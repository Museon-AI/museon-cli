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

## DON'T

Keep partial failures, missing pages and unknown outcomes visible. Do not refresh a conflicting version and silently overwrite, choose a new idempotency key for an ambiguous write, or cancel/recreate a group to simulate unsupported migration.

## Relationships

Use `media` for file ingestion, standalone prompt-based image/video generation, and media-record verification. Its generation receipt does not prove that an HireAICreator plan or video was generated. Use `research` for optional external references and `content-analysis` for video analysis; the HireAICreator service owns its plan, generation and publication facts.
