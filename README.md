<p align="center">
  <img src="./assets/readme/museon-icon.png" width="84" alt="Museon logo">
</p>

<h1 align="center">Museon CLI</h1>

<p align="center">
  <strong>Turn the AI agent you already use into a social media operator.</strong><br>
  Research, create, publish, and learn — with your approval where it matters.
</p>

<p align="center">
  <a href="https://www.museon.ai/cli">Website</a> ·
  <a href="./skills/museon-cli/SKILL.md">Agent Skill</a> ·
  <a href="./README.zh-CN.md">简体中文</a>
</p>

Museon CLI gives the AI agent you already use the tools to research social
content, understand what works, create new material, publish with your
approval, and learn from real performance.

You keep working with your Agent. Museon gives it the social-media capabilities
needed to move from an idea to real work.

## Give this to your Agent

Copy the instruction below into Codex, Claude Code, Cursor, or another Agent
that can install Skills and run shell commands:

```text
Set up Museon CLI for this agent by following this onboarding guide exactly:
https://www.museon.ai/cli/install.md
Complete the CLI and Skill installation, guide me through browser authorization,
verify the active workspace, and tell me when Museon is ready. Do not perform
any social-media changes during setup.
```

That is the recommended installation path. You do not need to clone the
repository, choose CLI flags, or configure credentials by hand.

## What happens next

1. **Your Agent installs Museon CLI.** It installs the exact Python wheel from
   the official GitHub release and verifies that the command is available.
2. **Museon CLI installs the Skill.** The bundled, same-version Skill teaches
   the Agent how to use Museon, when to ask for approval, and how to recover
   from authentication problems.
3. **You approve access in the browser.** Sign in to Museon and choose the
   workspace the Agent may use.
4. **You describe the work, not the commands.** The Agent discovers the right
   Museon actions and keeps the task moving.

Once connected, try a request like this:

```text
Research the AI note-taking content gaining momentum on TikTok and Instagram.
Explain the repeated hooks and audience questions, then propose three carousel
ideas for our product. Do not publish anything until I approve it.
```

## What your Agent can do

- **Find real content signals** across social platforms, creators, posts,
  comments, communities, and the public web.
- **Understand why content works** by comparing creative structure with account
  and post performance.
- **Turn findings into content** such as image posts and multi-page slideshows.
- **Connect accounts and keep a schedule moving** while leaving approval gates
  in place for publishing and other important changes.
- **Review results and reuse what worked** in the next brief, routine, report,
  or creative direction.

Museon is designed for the full loop: **research → decide → create → approve →
publish → review → reuse**.

## Skill, CLI, and Museon

These three parts work together:

- **Museon Skill** teaches your Agent how to approach social-media work and how
  to use the available tools safely.
- **Museon CLI** is the connection the Agent uses to take action from its own
  environment.
- **Museon** runs the hosted research, generation, account, scheduling,
  publishing, and performance workflows behind that connection.

The CLI never grants access by itself. Museon checks the signed-in user,
workspace membership, role, and target resource for every operation.

| Outcome | Domains |
| --- | --- |
| Find market, creator, post, community, and visual evidence | `research`, `campaign-monitor` |
| Analyze content and preserve reusable knowledge | `content-analysis`, `asset`, `artifacts`, `skills` |
| Create images and slideshows | `generation` |
| Connect accounts, configure publish pools, schedule work, publish, and review results | `social-account`, `account-publish`, `account-operation` |
| Run recurring or one-off operating loops | `routines`, `evaluator` |

The generated contract snapshot is the reviewed source of truth for the public
command set. Use the live schema rather than copying flags from an old transcript.

## You stay in control

- Research and other read-only work can run as part of the task.
- Creating, changing, scheduling, publishing, or deleting something requires
  the approval rules described by the command.
- The Agent must explain the intended change before a sensitive operation.
- Credentials stay in the Agent's local environment. Museon CLI uses the
  operating-system credential store when available and a mode-0600 file only
  in headless environments; authorization decisions remain on Museon's servers.

## Install without an Agent

If you prefer to install the CLI yourself, use Python 3.11+, `uv`, and the exact
wheel from the official GitHub release:

```bash
uv tool install "https://github.com/Museon-AI/museon-cli/releases/download/v0.3.72/museoncli-0.3.72-py3-none-any.whl"
```

Then continue with setup and browser authorization:

```bash
museoncli setup --agent codex
museoncli auth start
museoncli auth finish --wait
museoncli whoami
```

Use `--agent claude-code` or `--agent cursor` for those hosts; `--agent auto`
uses the active host marker, or a single existing supported Agent home. If
several Agent homes exist, choose one explicitly or use `--agent all`. Restart
the Agent after installing the Skill. `auth finish --wait` waits for approval
for up to five minutes by default; use `--timeout` to change that limit. The
shorter `museon` command is an alias for `museoncli`.

<details>
<summary><strong>Develop Museon CLI</strong></summary>

[![CI](https://github.com/Museon-AI/museon-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/Museon-AI/museon-cli/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.11%2B-7C65C1)

```bash
uv sync --frozen --all-groups
uv run ruff check .
uv run pytest -q
uv run python scripts/gen_command_docs.py --check
uv run python scripts/gen_command_contract.py --check
uv build --wheel
uv run python scripts/verify_public_artifacts.py
```

Command definitions live in `museoncli/domains/`. When a command changes,
regenerate the documentation and portable command contract:

```bash
uv run python scripts/gen_command_docs.py
uv run python scripts/gen_command_contract.py
```

</details>

See [CONTRIBUTING.md](CONTRIBUTING.md) and the
[Code of Conduct](CODE_OF_CONDUCT.md) to contribute. Release notes live in
[CHANGELOG.md](CHANGELOG.md). Please report security issues privately by
following [SECURITY.md](SECURITY.md).

## License

Museon CLI is licensed under the [Apache License 2.0](LICENSE).
