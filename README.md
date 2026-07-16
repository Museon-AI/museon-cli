# Museon CLI

> Give any shell-capable AI agent a structured way to research, create,
> publish, and review social content with Museon.

[简体中文](README.zh-CN.md)

[![CI](https://github.com/Museon-AI/museon-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/Museon-AI/museon-cli/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB)

Museon CLI is the open client for Museon's hosted social-media operating
platform. It gives Agents a discoverable command schema, predictable JSON
output, workspace-aware authentication, and explicit safety metadata for
state-changing operations.

## Why it works well with Agents

- **Discoverable:** `museoncli schema` is the source of truth for commands,
  inputs, examples, risk levels, and execution modes.
- **Structured:** stdout is always a JSON envelope; Agents do not need to
  scrape terminal prose.
- **Workspace-aware:** browser authorization connects the CLI to a Museon user
  and one accessible workspace.
- **Guarded:** write and destructive commands declare dry-run and confirmation
  requirements in their schemas.
- **Portable:** the wheel includes a reusable Agent Skill under
  `museoncli/bundled_skills/museon-cli/`.

## Install

The first PyPI release is being prepared. Until then, authorized repository
collaborators can install from a checkout:

```bash
git clone https://github.com/Museon-AI/museon-cli.git
cd museon-cli
uv tool install .
```

The installed commands are `museoncli` and the shorter alias `museon`.

## Authenticate

Start the device flow, approve the requested workspace in the browser, then
finish the login:

```bash
museoncli auth start
museoncli auth finish --wait
museoncli whoami
```

Credentials remain local to the machine. The hosted Museon API validates the
credential and authorizes every operation against the user's organization,
workspace membership, role, and requested resource.

## Discover before executing

```bash
# See every capability area.
museoncli schema

# Narrow to research commands.
museoncli schema research

# Inspect one exact contract before using it.
museoncli schema research.social-media-search
```

Every command returns a stable envelope:

```json
{
  "ok": true,
  "data": {},
  "run": null,
  "warnings": [],
  "next_steps": []
}
```

## Capability map

| Outcome | Domains |
| --- | --- |
| Find market, creator, post, community, and visual evidence | `research`, `campaign-monitor` |
| Analyze content and preserve reusable knowledge | `content-analysis`, `asset`, `artifacts`, `skills` |
| Create images and slideshows | `generation` |
| Connect accounts, schedule work, publish, and review results | `social-account`, `account-operation` |
| Run recurring or one-off operating loops | `routines`, `evaluator` |

The current generated catalog contains 95 commands across 11 domains. Use the
live schema rather than copying flags from an old transcript.

## Give it to an Agent

An Agent can start with this instruction:

```text
Install Museon CLI from https://github.com/Museon-AI/museon-cli.
Authenticate me with the browser flow, run `museoncli schema`, and inspect the
exact command schema before executing any operation. Ask for separate approval
before writes or destructive actions.
```

The bundled [Agent Skill](museoncli/bundled_skills/museon-cli/SKILL.md) adds
workflow guidance for research, creation, publishing, review, artifacts, and
authentication recovery.

## Repository boundary

This repository contains the installable CLI, its command registry, generated
contract, documentation, tests, and reusable Agent Skill. Museon's hosted API
contains authentication, authorization, business execution, integrations, and
customer data.

There is no separate public/internal command flag in the CLI. Authenticated
users and Agents discover the same command contract; the server decides whether
the current identity may execute a requested operation.

## Development

```bash
uv sync --frozen --all-groups
uv run ruff check .
uv run pytest -q
uv run python scripts/gen_command_docs.py --check
uv run python scripts/gen_command_contract.py --check
uv build
```

When a command changes, edit its definition in `museoncli/domains/`, then
regenerate the human-readable tables and portable JSON contract:

```bash
uv run python scripts/gen_command_docs.py
uv run python scripts/gen_command_contract.py
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the complete change checklist and
[SECURITY.md](SECURITY.md) for private vulnerability reporting.
