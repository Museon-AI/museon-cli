---
name: museon-cli
description: "Install and use Museon CLI for end-to-end social-media operations: research markets, competitors, creators, and posts; analyze content; generate images and slideshows; connect accounts; automate routines; schedule or publish content; review performance; and preserve reusable reports and assets. Trigger when the user asks to install Museon, mentions Museon, or asks an Agent to run social media, including 调研、内容分析、做图、slideshow、自动化、发布、复盘或沉淀。"
---

# Museon CLI

Use Museon CLI as the operating layer between the Agent and real social-media
work. The executable is `museoncli`; `museon` is an equivalent alias.

## Install the CLI when needed

Check whether `museoncli` or `museon` is already available. If neither command
exists and the user asked to install Museon or complete a Museon task:

1. If Python 3.11+ and `uv` are available, install the exact reviewed wheel from
   the official GitHub release:

   ```bash
   uv tool install "https://github.com/Museon-AI/museon-cli/releases/download/v0.3.63/museoncli-0.3.63-py3-none-any.whl"
   ```

2. Do not install or replace Python or `uv` without the user's approval. Do not
   clone the repository, install from a mutable branch, or substitute another
   package source.
3. Verify the result with `museoncli version`. Do not claim installation
   succeeded until that command works.
4. Continue the original task. If the user asked to sign in, start the browser
   authorization flow described in
   [safety-and-auth.md](references/safety-and-auth.md).

## Operating contract

1. Translate the request into a concrete operating outcome. Clarify only when
   multiple materially different outcomes are plausible or a required target is
   missing.
2. Discover the current CLI surface before acting. Never rely on remembered
   flags or an old transcript.
3. Read the relevant state before proposing a change.
4. For a state-changing command, explain the exact change and obtain a separate
   explicit approval before execution.
5. Execute, verify with a read-back, and present customer-useful links and
   previews instead of dumping raw JSON.
6. Carry evidence, outcomes, and reusable assets into the next operating cycle.

## Discover commands

The generated schema is the source of truth:

```bash
museoncli schema
museoncli schema research
museoncli schema research.social-media-search
```

- Run `museoncli schema` to see current domains and shortcuts.
- Run `museoncli schema <domain>` to choose within one capability area.
- Run `museoncli schema <domain>.<shortcut>` before first use of a command to
  inspect its exact inputs, risk level, execution mode, and examples.
- If the schema does not expose a command, do not call or invent it.
- Parse stdout as JSON. Success is `{"ok": true, ...}`; failure is
  `{"ok": false, "reason": "...", "detail": "..."}`.

## Route the request

Read only the reference needed for the current task before substantive work:

| User outcome | Required reference |
| --- | --- |
| Market, competitor, creator, post, trend, community, or visual research | [research-and-analysis.md](references/research-and-analysis.md) |
| Content analysis, reusable creative structure, images, or slideshows | [content-and-visuals.md](references/content-and-visuals.md) |
| Account connection, configuration, scheduling, publishing, or managed operation | [publishing-and-accounts.md](references/publishing-and-accounts.md) |
| Monitoring, review, recurring automation, memory, or durable reports | [automation-review-and-artifacts.md](references/automation-review-and-artifacts.md) |
| Authentication, workspace recovery, safety, errors, or CLI availability | [safety-and-auth.md](references/safety-and-auth.md) |

For a request spanning several areas, read the references in workflow order and
keep one visible plan. Prefer a complete operating loop over isolated outputs:
research -> decide -> create -> approve -> publish -> review -> reuse.

## Safety and state changes

- Treat `risk=read` commands as safe to run when they directly serve the task.
- Treat `risk=write` commands as proposals until the user separately approves
  the stated change. Use `--dry-run` first for bulk, novel, or uncertain writes.
- Treat `risk=destructive` commands the same way and pass `--yes` only after
  explicit approval.
- A request such as "create", "generate", "schedule", or "publish" is the
  request to prepare the change, not the separate confirmation to execute it.
- Use canonical UUIDs copied from command responses. Never pass placeholders,
  guessed IDs, social handles, or raw URLs where an ID is required.
- Do not expose access tokens, API keys, callback codes, service credentials,
  or raw customer payloads.
- Do not run authentication checks before every task. Enter recovery only after
  the task command reports an authentication or workspace problem.

## Async work and verification

- When `execution=async_run`, retain the returned handle and follow the matching
  status contract until the run settles.
- Honor a returned `recommended_wakeup_delay_seconds`; do not invent a polling
  delay when the CLI provides one.
- After a write, run the relevant read command and verify that the intended
  state is present.
- When results include a ready-made `ref`, treat it as opaque and present it as
  the primary identifier. Do not reconstruct or edit it.
- For completed visual generations, include the result `ref` and available grid
  or slide previews. For an in-progress generation, share its live `ref` now
  and explain that progress is visible there.
- Large successful JSON results may be replaced by a
  `status:large_json_offloaded` manifest containing a local file path, byte
  count, and a small preview. Read the referenced file in bounded chunks or use
  targeted search; do not treat the manifest as missing business data and do
  not paste the full file back into the conversation.

## Skill boundaries

This bundled `museon-cli` Skill is a local Agent integration: it teaches the
host Agent how to operate the CLI. It is different from Museon business skills
returned by `museoncli skills +list` and `museoncli skills +get`, which contain
workspace-visible strategy, methodology, and content frameworks.

Do not use the business-skill commands to load this local integration Skill.
Do not assume Mel-specific personas, internal subagents, output styles, or
runtime-only tools are available. Use the host Agent's native planning,
clarification, browser, scheduling, and file capabilities when needed.
