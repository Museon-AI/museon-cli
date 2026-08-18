---
name: museon-content-workflow-base
description: "Install and operate Museon CLI, discover command schemas and Business Skills, authenticate, recover failures, and route social-media workflow tasks to the correct Museon skill."
---

# Museon content workflow base

Use Museon CLI as the operating layer between the Agent and real social-media work.
The executable is `museoncli`; `museon` is an equivalent alias.

## Install the CLI when needed

If neither command exists and the user asked to install Museon or complete a Museon task,
install the reviewed wheel with Python 3.11+ and `uv`:

```bash
uv tool install "https://github.com/Museon-AI/museon-cli/releases/download/v0.5.17/museoncli-0.5.17-py3-none-any.whl"
```

Do not install Python or `uv` without approval. Verify with `museoncli version`, authenticate
when required, run `museoncli skills +list`, then continue the original task.

## Core operating contract

Discover the exact schema before use, load relevant Business Skills for strategic work, read
current state, obtain separate approval for writes, verify with a read-back, and carry reusable
evidence and assets into the next cycle. Never invent a command absent from the schema.

| Command family | Purpose |
| --- | --- |
| `museoncli schema [domain[.shortcut]]` | Discover current commands and exact contracts |
| `museoncli skills +list/+get/+create` | List, read, or create runtime Business Skills |
| `museoncli auth`, `workspace`, `version` | Availability, authentication, and workspace recovery |

## Route by task result

| Desired result | Skill |
| --- | --- |
| Evidence or video content analysis | `museon-research` |
| Reusable product/persona/format/topic assets | `museon-content-workflow-assets` |
| Generated images, carousels, or slideshows | `museon-content-workflow-generation` |
| Account reads, connection, config, or performance | `museon-content-workflow-social-account` |
| Asset-pool or schedule-plan publishing workflows | `museon-content-workflow-account-publish` |
| Managed-fleet operations | `museon-content-workflow-account-operation` |
| Campaign monitoring and synced post history | `museon-content-workflow-campaign-monitor` |
| Recurring automation and memory | `museon-content-workflow-routines` |
| Durable reports and uploads | `museon-content-workflow-artifacts` |
| Agentic Creative Campaign lifecycle | `museon-content-workflow-agentic-campaign` |
| Evaluator definitions and runs | `museon-content-workflow-evaluator` |

## References

- [operating-contract.md](references/operating-contract.md): discovery, Business Skills, safety,
  asynchronous work, and integration boundaries.
- [safety-and-auth.md](references/safety-and-auth.md): availability, authentication, risk, and errors.

## Cross-skill handoff
For multi-area work, load skills in workflow order and keep one visible plan: research -> decide
-> create -> approve -> publish -> review -> reuse. Return here when authentication, command
discovery, workspace selection, or general risk handling blocks another skill.
