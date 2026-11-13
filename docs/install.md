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
- An active Museon organization is selected.
- `museoncli whoami` and `museoncli schema` succeed.

`museon` is an equivalent alias for `museoncli`, but use `museoncli` in the
steps below for consistency.

## 1. Check the environment

First, check whether Museon CLI is already available:

```bash
museoncli version
```

从 0.23.0 起，官方 `uv tool` 安装会在命令执行前自动检查稳定版并升级。
`version` 每次强制检查。从 1.0.1 起它直接报告 `current`、`latest`、
`install_method`（`uv_tool`、`pipx`、`uv_pip`、`pip`、`other`、`source`、`managed`）、
`upgrade_command`、`changelog_url` 和 `update_status`（`current`、`outdated`、`updated`、
`check_failed`、`disabled` 或 `managed_externally`）；`data.update` 保留原始检查结果。
普通命令使用 15 分钟检查缓存。

用 pip、pipx 等无法自动升级的方式安装时，发现新版后每条命令的 JSON 都带
`_notice.update`（含 `upgrade_command` 和 `message`），Agent 应在完成当前任务后告诉用户，
并提出运行 `museoncli upgrade`：官方 `uv tool` 安装会校验并安装新版，其他安装方式返回
`status: manual` 和要运行的命令。CLI 自动升级后，下一次输出带一次 `_notice.updated`
（`from`、`to`、`changelog_url`、`highlights`）。交互式终端另在 stderr 打印一行提示
（新版提示每天最多一次）；管道、CI 和 `MUSEONCLI_UPDATE_CHECK=0` 不打印。这类安装的普通命令
不等待网络：缓存超过 15 分钟时由后台进程刷新，提示从下一条命令开始出现。

如果已有 CLI 的输出没有 `data.update`，说明它尚未包含自动升级能力：先用下面的
官方 wheel 安装命令加 `--force` 升级一次，再运行 `museoncli version` 验证。
不要把“命令能执行”当作“已经是最新版”。

网络不可用时会明确提示检查未完成并继续使用已安装版本；发现新版但安装失败时，
原业务命令不会执行。升级完成后保留登录和所选组织，并用新版继续原命令，
不会重放已经执行过的写操作。升级日志写入 stderr，stdout 保持 JSON。

从 0.24.0 起，`museoncli setup` 装过的 Agent Skills 也随 CLI 自动同步；同步后该次命令的 JSON
带 `_notice.skills.updated`，Agent 应重读正在使用的 Skill。固定版本时（`MUSEONCLI_UPDATE_CHECK=0`）
不写入，改为每条命令带 `_notice.skills.command` 提示手动运行。

`MUSEONCLI_UPDATE_CHECK=0` 可用于需要固定版本或完全离线的环境。源码开发环境、
非 `uv tool` 安装及托管 Agent runtime 由其安装/发布流程更新；自动升级不会修改它们。
自动安装只接受官方 GitHub 稳定版 wheel 及其 SHA-256，不使用自定义 manifest 源。

If the command is unavailable:

1. Confirm that Python 3.11+ and `uv` are available, then install the exact
   reviewed wheel from the official GitHub release:

   ```bash
   uv tool install "https://github.com/Museon-AI/museon-cli/releases/download/v1.1.0/museoncli-1.1.0-py3-none-any.whl"
   ```

   Do not clone the repository, install from a mutable branch, or substitute a
   different package source.
2. If Python 3.11+ or `uv` is unavailable, report the missing prerequisite
   instead of replacing the host's runtime without approval.
3. Verify the installation with `museoncli version`. Do not claim success
   until it works.

## 2. Install the Museon Agent Skills

For Codex, Claude Code, or Cursor, install the Skills bundled with the CLI:

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
all five bundled workflow Skills as `installed`
or `current` and includes their destination paths.

For another Agent that supports Skills, use that Agent's native Skill installer
to install the workflow Skill folders and Hook Analysis Skill:

https://github.com/Museon-AI/museon-cli/tree/v1.1.0/skills/museon-content-workflow-base
https://github.com/Museon-AI/museon-cli/tree/v1.1.0/skills/museon-research
https://github.com/Museon-AI/museon-cli/tree/v1.1.0/skills/museon-content-workflow-hireaicreator
https://github.com/Museon-AI/museon-cli/tree/v1.1.0/skills/museon-content-workflow-ai-slideshow
https://github.com/Museon-AI/museon-cli/tree/v1.1.0/skills/museon-content-workflow-campaign-monitor

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

If it is already authenticated, continue to organization selection. Otherwise,
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

## 4. Discover Business Skills

After authentication, list the strategy and operations playbooks available in
the current organization:

```bash
museoncli skills +list
```

Read directly relevant entries with `museoncli skills +get --name <name>` before
strategy, research, audit, review, onboarding, or operating-plan work.

## 5. Confirm the active organization

Read the authenticated identity and current organization:

```bash
museoncli whoami
museoncli org current
```

If no organization is selected, list the organizations this login can act in
(each entry has `role`, `campaign_scope` and `is_default`):

```bash
museoncli org list
```

When exactly one valid organization is available, select it. When several are
plausible, ask the user which one to use instead of guessing.

```bash
museoncli org select --id <organization-id>
```

Use the exact organization ID returned by the CLI (`--name <exact name>` also works).
To address another organization for a single call, pass `--organization-id <uuid>` to that
domain command.

### 只有组织（1.0.0）

MuseOn 只有组织，访问权限由组织角色加 Campaign 范围决定。

- `workspace list` -> `org list`；`workspace current` -> `org current`；
  `workspace select --id <ws>` -> `org select --id <organization-id>`。1.0.0 起 `workspace` 命令组已删除。
- 业务命令不再接受 `--workspace-id`，结构化输入里的 `workspace_id` 也会被拒绝；需要单次指定其他组织时用 `--organization-id <org>`。
- 输出信封读 `.organization`（`{id, name}` 或 `null`），没有 `.workspace`。
- `agentic-campaign` 与 `hireaicreator` 暂时保持 0.25 的行为（弃用的 `--workspace-id` 与 `workspace` 键）。

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
- active organization
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
