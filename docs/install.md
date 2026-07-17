<!-- Canonical source for https://www.museon.ai/cli/install.md. Keep the Web copy byte-for-byte identical. -->

# Set up Museon CLI

This is the canonical onboarding guide for an AI Agent that can run shell
commands. Carry out the steps below in the Agent's own environment. Do not
merely explain the commands unless an approval or missing prerequisite blocks
you.

During onboarding, do not create, change, schedule, publish, or delete any
social-media resource.

## Completion criteria

Onboarding is complete only when all of the following are true:

- `museoncli version` succeeds.
- The Museon CLI Skill is installed for the current Agent.
- If the host requires a restart to load the Skill, the user has been told and
  the Agent does not claim that the current session is ready.
- Browser authorization has completed.
- An active Museon workspace is selected.
- `museoncli whoami` and `museoncli schema` succeed.

`museon` is an equivalent alias for `museoncli`, but use `museoncli` in the
steps below for consistency.

## 1. Check the environment

First, check whether Museon CLI is already available:

```bash
museoncli version
```

If it succeeds, do not reinstall the CLI. Continue to the Skill setup.

If the command is unavailable:

1. Confirm that Python 3.11+ and `uv` are available, then install the exact
   reviewed wheel from the official GitHub release:

   ```bash
   uv tool install "https://github.com/Museon-AI/museon-cli/releases/download/v0.3.61/museoncli-0.3.61-py3-none-any.whl"
   ```

   Do not clone the repository, install from a mutable branch, or substitute a
   different package source.
2. If Python 3.11+ or `uv` is unavailable, report the missing prerequisite
   instead of replacing the host's runtime without approval.
3. Verify the installation with `museoncli version`. Do not claim success
   until it works.

## 2. Install the Museon CLI Skill

For Codex, Claude Code, or Cursor, install the Skill bundled with the CLI:

```bash
museoncli setup --agent auto
```

If automatic detection fails, choose the current host explicitly:

```bash
museoncli setup --agent codex
museoncli setup --agent claude-code
museoncli setup --agent cursor
```

Run only the command matching the current Agent. A successful result reports
the Skill status as `installed` or `current` and includes its destination path.

For another Agent that supports Skills, use that Agent's native Skill installer
to install this folder:

https://github.com/Museon-AI/museon-cli/tree/v0.3.61/skills/museon-cli

Do not invent a Skill directory for an unsupported host. If the Agent has no
native Skill installation mechanism, finish the CLI authorization steps and
tell the user that persistent Skill installation is the remaining limitation.

Some Agent hosts load newly installed Skills only after a restart. Complete the
remaining onboarding steps, then clearly report whether a restart is required.

## 3. Complete browser authorization

Check the current authorization state:

```bash
museoncli auth status
```

If it is already authenticated, continue to workspace selection. Otherwise,
start a browser authorization:

```bash
museoncli auth start
```

Give the user the returned `verification_uri_complete` exactly as returned.
Never expose the device code, access token, API key, or other credentials.

In the same turn, wait for completion:

```bash
museoncli auth finish --wait --timeout 60 --poll-interval 2
```

If the command times out while waiting for the user, keep the same verification
URL visible and run `museoncli auth finish` again after the user approves. Start
a new authorization only when the current one is expired, denied, or already
used.

The authorization must happen in the same environment where the Agent will run
Museon CLI. Do not ask the user to authenticate a different installation.

## 4. Confirm the active workspace

Read the authenticated identity and current workspace:

```bash
museoncli whoami
museoncli workspace current
```

If no workspace is selected, list the available workspaces:

```bash
museoncli workspace list
```

When exactly one valid workspace is available, select it. When several are
plausible, ask the user which one to use instead of guessing.

```bash
museoncli workspace select --id <workspace_id>
```

Use the exact workspace ID returned by the CLI.

## 5. Verify Museon is ready

Run the final checks:

```bash
museoncli version
museoncli auth status
museoncli whoami
museoncli schema
```

Do not paste large raw JSON responses into the conversation. Report a concise
summary containing:

- CLI version
- Skill status and whether a restart is required
- authenticated Museon identity
- active workspace
- whether the command schema is available

If any completion criterion is still missing, state the exact blocker and the
next action. If a restart is required, report setup as complete with restart
pending; do not say that the current Agent session is ready.

## After onboarding

Use the installed Museon CLI Skill for future tasks. Discover the live command
surface with `museoncli schema`; do not rely on remembered command names or
flags. Read-only work may run when it directly serves the user's request.
Creating, changing, scheduling, publishing, or deleting anything requires the
approval policy defined by the Skill and the command schema.

Repository: https://github.com/Museon-AI/museon-cli
