# Operating contract and command discovery

## Operating contract

1. Translate the request into a concrete operating outcome. Clarify only when multiple materially different outcomes are plausible or a required target is missing.
2. Discover the current CLI surface before acting. Never rely on remembered flags or an old transcript.
3. For strategic work, follow the Business Skills step before gathering evidence or making recommendations.
4. Read the relevant state before proposing a change.
5. For a state-changing command, explain the exact change and obtain a separate explicit approval before execution.
6. Execute, verify with a read-back, and present customer-useful links and previews instead of dumping raw JSON.
7. Carry evidence, outcomes, and reusable assets into the next operating cycle.

## Discover commands

```bash
museoncli schema
museoncli schema research
museoncli schema research.social-media-search
```

- Run `museoncli schema` to see current domains and shortcuts.
- Run `museoncli schema <domain>` to choose within one capability area.
- Run `museoncli schema <domain>.<shortcut>` before first use to inspect exact inputs, risk level, execution mode, and examples.
- If the schema does not expose a command, do not call or invent it.
- Parse stdout as JSON. Success is `{"ok": true, ...}`; failure is `{"ok": false, "reason": "...", "detail": "..."}`.

## Business Skills

Before a strategy, research, audit, review, onboarding, or operating-plan task:

1. Run `museoncli skills +list`.
2. Read every directly relevant Skill with `museoncli skills +get --name <name>`.
3. Apply its methodology with current data and the relevant local reference.

Skip this only for a narrow factual lookup, schema inspection, or status read that needs no recommendation. Load a user-named Skill directly; otherwise do not guess names or use a stale list. `skills +create` belongs to this same business-Skill command domain and is a write governed by the risk policy.

## Safety and state changes

- Treat `risk=read` commands as safe when they directly serve the task.
- Treat `risk=write` and `risk=destructive` commands as proposals until separately approved; use `--dry-run` for bulk, novel, or uncertain writes and `--yes` only after destructive approval.
- A request to create, generate, schedule, or publish prepares the change; it is not separate execution confirmation.
- Use canonical UUIDs from responses. Never guess IDs or substitute handles/URLs where IDs are required.
- Never expose tokens, keys, callback codes, credentials, or raw customer payloads.
- Enter authentication recovery only after a task command reports an authentication or workspace problem.

## Async work and verification

- For `execution=async_run`, retain the handle and follow the matching status contract until settled.
- Honor `recommended_wakeup_delay_seconds`.
- After a write, use the relevant read command to verify intended state.
- Treat returned `ref` values as opaque primary identifiers; never reconstruct them.
- For completed visual generation, include its `ref` and available previews; for in-progress work, share the live `ref`.
- A `status:large_json_offloaded` manifest points to business data in a local file. Read bounded chunks or search it; do not paste the whole file.

## Skill boundaries

These bundled Skills teach the host Agent to operate the CLI. They differ from runtime Business Skills returned by `museoncli skills +list/+get`. Do not use business-Skill commands to load local integration Skills or assume runtime-only personas, subagents, output styles, or tools are present unless a loaded Business Skill requires them.
