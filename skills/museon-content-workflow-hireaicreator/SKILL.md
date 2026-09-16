---
name: museon-content-workflow-hireaicreator
description: "Operate HireAICreator with Museon CLI: find accounts and creative resources, inspect capacity and execution, register Clips, generate or edit videos, and prepare delivery. Use for HireAICreator business objects, not generic media analysis or external social research."
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

## Manual video delivery

For downloadable videos or a manual publishing link, use `video +create` with an observed Actor and Persona, `--composition-source hook-only`, and `--format-id` or `--reference-hook-id`. If the user names an account, read its `account +assets-get` bindings first; preserve those Actor and Persona IDs without binding or scheduling the new video. Create one video per chosen Format with a stable idempotency key per item. Read back each video, then `video +generate` with the observed version, poll `video +get`, and finish with verified `delivery +export` / `+export-get` and an authorized share. Record partial results and resume existing IDs; do not create duplicates after an ambiguous response. `plan +create` is not required for manual delivery.

Pass explicit `--workspace-id` on every workspace-scoped command after resolving the user's workspace; resource-scoped commands do not accept that flag. Do not rely on a workspace selection surviving a new agent turn. If a result is offloaded, read `raw_result.path` (or the local path supplied in the large-result manifest) before interpreting `data: null` as empty data.

A 422 validation error or a 404 response does not prove write permission or end-to-end success. Do not probe unrelated write routes to infer a permissions map. Report the actual command and response; for host-managed authentication, do not promise an `auth start` / login switch that the host prohibits. Read schema again when a command is unavailable, and report a release mismatch rather than inventing a command.

## Mental model

- Actor is an on-camera identity; Persona is a separate content/personality resource. They have separate IDs. An account binding is evidence of their relationship, not permission to interchange them.
- Format, reference Hook, generated Hook item, Recipe, POV, BGM and Clip are different resources. Preserve the actual selected IDs across steps. A Test Group, its historical Run and an individual Video are also different scopes.
- For writes, fix the authorized IDs and desired change, read current versions, submit, then read the same objects again. An acknowledgement, preview, or `readiness.ready` is not a completed output.

## Account Actor and Persona bindings

Find accounts with `account +list` using exact handles and inspect all matching pages. Resolve Actors with `actor +list` / `actor +get`; use the Actor's `source_persona_id` to identify its Persona and disambiguate duplicate Actor names by ID and reference image. If `source_persona_id` is null (including reference Actors), ask the user to select the Persona explicitly; do not infer or invent a mapping from names or appearance. Read current bindings with `account +assets-get --id <pool-account-id>`. Apply `account +actor-set --id <pool-account-id> --actor-id <actor-id>` and `account +persona-set --id <pool-account-id> --persona-id <persona-id>` in the selected or explicit workspace, then read `account +assets-get` again to verify both IDs. The two writes are separate receipts; report any partial success. Only pass `--managed-operation-approved` when that additional change is explicitly authorized.

## DON'T

Keep partial failures, missing pages and unknown outcomes visible. Do not refresh a conflicting version and silently overwrite, choose a new idempotency key for an ambiguous write, or cancel/recreate a group to simulate unsupported migration.

## Relationships

Use `media` for file ingestion, standalone prompt-based image/video generation, and media-record verification. Its generation receipt does not prove that an HireAICreator plan or video was generated. Use `research` for optional external references and `content-analysis` for video analysis; the HireAICreator service owns its plan, generation and publication facts.
