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
uv tool install "https://github.com/Museon-AI/museon-cli/releases/download/v0.5.20/museoncli-0.5.20-py3-none-any.whl"
```

Read [operating-model.md](references/operating-model.md) for risk, async work, authentication,
and Business Skill boundaries.

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
- **DON'T** treat a request to create/publish as separate approval to execute the write.
- **DON'T** expose credentials, callback codes, raw customer payloads, or reconstructed `ref` values.
- **DON'T** preflight auth/version/workspace before every task; enter recovery after a real failure.
- **DON'T** load bundled integration Skills through the runtime `skills` domain.

## Relationships

| Desired result | Skill |
| --- | --- |
| Evidence or video analysis | `museon-research` |
| Reusable creative objects | `museon-content-workflow-assets` |
| Images or slideshows | `museon-content-workflow-generation` |
| One-account state/config/performance | `museon-content-workflow-social-account` |
| Asset pools or schedule plans | `museon-content-workflow-account-publish` |
| Campaigns, Persona Plans, members, operations, runs | `museon-content-workflow-agentic-campaign` |
| Monitored creators/content/history | `museon-content-workflow-campaign-monitor` |
| Recurring work and memory | `museon-content-workflow-routines` |
| Durable reports | `museon-content-workflow-artifacts` |
| Evaluator definitions/runs | `museon-content-workflow-evaluator` |
