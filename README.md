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
  <a href="./skills/museon-content-workflow-base/SKILL.md">Workflow Skills</a> ·
  <a href="./skills/museon-research/SKILL.md">Research Skill</a> ·
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
```

That is the recommended installation path. You do not need to clone the
repository, choose CLI flags, or configure credentials by hand.

## What happens next

1. **Your Agent installs Museon CLI.** It installs the exact Python wheel from
   the official GitHub release and verifies that the command is available.
2. **Museon CLI installs the Skills.** The bundled, same-version workflow Skills teach
   the Agent how to route and use Museon safely and add the Instagram Hook research
   workflow. ego lite is installed separately when authenticated browsing is
   needed.
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

## Agent capabilities

This working tree prepares the CLI 2.0 surface; the pinned installation below remains
at the last published release until a separate release is approved.

| Outcome | Domains |
| --- | --- |
| Research public content and Hooks | `research` |
| Plan, inspect, edit and verify HireAICreator content | `hireaicreator` |
| Track creators, posts and performance | `campaign-monitor` |
| Analyze video content | `content-analysis` |
| Upload files, import image URLs and read media records | `media` |
| Validate, host and share durable reports | `artifacts` |
| Connect and inspect accounts, use bound phones, read performance and edit profiles | `social-account` |
| Schedule Agent work and retain run memory | `routines` |
| Discover workspace methodology | `skills` |

Eight bundled Skills teach discovery, research, durable artifacts, account access, Hook analysis, monitoring and routines.
The CLI executes atomic operations; the Agent composes workflows. Museon checks user,
workspace membership, role and resource access for every request. Verify writes with
readback from the owning domain, not with a request receipt alone.

See [the migration guide](docs/cli-2-migration.md) before replacing an older CLI.
The HireAICreator domain is included in this unpublished candidate.

## You stay in control

- Research and other read-only work can run as part of the task.
- Creating, changing, scheduling, publishing, or deleting something requires
  the approval rules described by the command.
- The Agent must explain the intended change before a sensitive operation.
- Credentials stay in the Agent's local environment. Museon CLI uses the
  operating-system credential store when available and a mode-0600 file only
  in headless environments; an Agents-hosted session instead uses an exclusive,
  short-lived private lease that cannot fall back to a user API key. Authorization
  decisions remain on Museon's servers. See
  [Authentication credential providers](docs/auth-credential-providers.md).

## Install without an Agent

If you prefer to install the CLI yourself, use Python 3.11+, `uv`, and the exact
wheel from the official GitHub release:

```bash
uv tool install "https://github.com/Museon-AI/museon-cli/releases/download/v0.6.0/museoncli-0.6.0-py3-none-any.whl"
```

Then continue with Skill setup and browser authorization:

```bash
museoncli setup --agent codex
museoncli auth start
museoncli auth finish --wait
museoncli skills +list
museoncli whoami
```

Use `--agent claude-code` or `--agent cursor` for those hosts; `--agent auto`
uses the active host marker, or a single existing supported Agent home. If
several Agent homes exist, choose one explicitly or use `--agent all`. Restart
the Agent after installing the Skill. After authentication, `skills +list`
shows the Business Skills available in the current workspace. `auth finish --wait` waits for approval
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
