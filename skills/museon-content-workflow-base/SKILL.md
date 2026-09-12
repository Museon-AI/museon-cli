---
name: museon-content-workflow-base
description: "Install and operate Museon CLI, discover command schemas and Business Skills, authenticate, recover failures, and route social-media workflow tasks to the correct Museon skill."
metadata:
  requires:
    bins: ["museoncli"]
  cliHelp: "museoncli --help"
---

# Museon content workflow base

## Mental model

Museon CLI is the execution layer; bundled workflow Skills provide durable operating judgment;
runtime Business Skills provide workspace methodology. The live schema is the sole source for
commands and inputs. Install the CLI when needed: if it is absent, install the reviewed wheel,
verify `museoncli version`,
then resume the original task:

```bash
uv tool install "https://github.com/Museon-AI/museon-cli/releases/download/v0.6.0/museoncli-0.6.0-py3-none-any.whl"
```

Read [operating-model.md](references/operating-model.md) for risk, async work, authentication,
and Business Skill boundaries. Read only the reference needed for the current capability:

- [media.md](references/media.md) for media upload, prompt generation, and durable task status.
- [artifacts.md](references/artifacts.md) for artifact validation, upload, and sharing.
- [social-accounts.md](references/social-accounts.md) and [social-account-batch-edits.md](references/social-account-batch-edits.md) for retained account reads, connection helpers, profile edits, avatars, and performance.
- [routines.md](references/routines.md) for recurring work and memory.
- [content-analysis.md](references/content-analysis.md) for durable video analysis.

## Shortcuts

| Situation | Start with |
| --- | --- |
| Discover a domain or command | `museoncli schema` |
| Strategic/research/audit work | `museoncli skills +list` |
| Known Business Skill | `museoncli skills +get` |
| Authentication failure | `museoncli auth start` |
| Missing workspace | `museoncli workspace list` |

## DON'T

- **DON'T** invent a command, flag, ID, or risk rule; inspect `museoncli schema <domain.shortcut>`.
- Treat the user's request and existing authorization as sufficient within their stated scope. Ask only when a necessary target or authorization is missing; never supply a server-required confirmation on the user's behalf.
- **DON'T** expose credentials, callback codes, raw customer payloads, or reconstructed `ref` values.
- **DON'T** preflight auth/version/workspace before every task; enter recovery after a real failure.
- **DON'T** load bundled integration Skills through the runtime `skills` domain.

## Relationships

| Desired result | Skill |
| --- | --- |
| External evidence and research synthesis | `museon-research` |
| Monitored creator/content history | `museon-content-workflow-campaign-monitor` |
| Reusable slideshow assets, generation and publish | `museon-content-workflow-ai-slideshow` |
| HireAICreator content planning, editing and delivery | `museon-content-workflow-hireaicreator` |
