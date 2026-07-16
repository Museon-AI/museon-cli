<p align="center">
  <img src="./assets/readme/museon-icon.png" width="84" alt="Museon Logo">
</p>

<h1 align="center">Museon CLI</h1>

<p align="center">
  <strong>让你正在使用的 Agent 接手社媒运营。</strong><br>
  调研、创作、发布、复盘；重要操作仍由你决定。
</p>

<p align="center">
  <a href="https://www.museon.ai/zh/cli">产品页面</a> ·
  <a href="./skills/museon-cli/SKILL.md">Agent Skill</a> ·
  <a href="./README.md">English</a>
</p>

Museon CLI 给你正在使用的 AI Agent 一套真正能执行的社媒工具：寻找内容机会、
了解内容为什么有效、生成新内容、经过你确认后发布，再根据真实表现调整下一轮。

你不需要换掉现在的 Agent。Museon 会给它完成社媒工作所需的能力，让一个想法
真正变成可以执行的运营工作。

## 把这段话交给 Agent

将下面这段话复制给 Codex、Claude Code、Cursor，或其他能够安装 Skill 并执行
Shell 命令的 Agent：

```text
请从下面的地址安装 Museon CLI Skill：
https://github.com/Museon-AI/museon-cli/tree/main/skills/museon-cli
然后使用这个 Skill 安装 Museon CLI，带我完成登录授权，并在可以开始社媒运营时
告诉我。
```

这是推荐的安装方式。你不需要自己克隆仓库、研究 CLI 参数或手动配置凭证。

## 接下来会发生什么

1. **Agent 安装 Museon Skill。** Skill 会告诉 Agent 如何完成社媒工作、什么时候
   需要向你确认，以及遇到登录问题时如何恢复。
2. **Skill 安装 Museon CLI。** 它会检查 Agent 所在的环境，安装 CLI，并确认安装
   成功。
3. **你在浏览器里完成授权。** 登录 Museon，然后选择允许 Agent 使用的工作区。
4. **你只需要描述工作。** Agent 会自己找到合适的 Museon 能力并继续完成任务，
   不需要你提供命令。

连接完成后，可以先试试这样的需求：

```text
调研最近在 TikTok 和 Instagram 上增长较快的 AI 笔记产品内容，告诉我反复出现的
开场方式和用户问题，再为我们的产品提出 3 个多页图文方向。没有经过我确认，先
不要发布。
```

## Agent 可以做什么

- **找到真实的内容机会：** 调研不同平台、创作者、帖子、评论、社区和公开网页。
- **了解内容为什么有效：** 把内容结构与账号、帖子的真实表现放在一起分析。
- **把发现变成内容：** 生成图片内容和多页图文，而不是停留在一份文字建议里。
- **连接账号并推进排期：** 安排内容、准备发布，同时保留必要的人工确认。
- **复盘并积累有效经验：** 把结果带回下一份 Brief、定期任务、报告或创作方向。

Museon 关注的是完整循环：**调研 → 判断 → 创作 → 确认 → 发布 → 复盘 → 复用**。

## Skill、CLI 和 Museon 分别做什么

它们共同组成 Agent 的社媒工作能力：

- **Museon Skill** 告诉 Agent 应该怎样完成社媒任务，以及怎样安全地使用工具。
- **Museon CLI** 是 Agent 在自己环境里调用 Museon 能力的连接方式。
- **Museon** 在服务端完成调研、生成、账号、排期、发布和表现分析等工作。

CLI 本身不会绕过权限。Museon 会在每次操作时检查当前登录用户、工作区成员关系、
角色和目标资源。

## 重要操作仍由你决定

- 调研和其他只读工作可以直接服务于当前任务。
- 创建、修改、排期、发布或删除内容时，Agent 必须遵守对应操作的确认要求。
- 重要操作执行前，Agent 会先说明具体要改变什么。
- 凭证保存在 Agent 所在的本地环境，最终的权限判断始终由 Museon 服务端完成。

## 不通过 Agent 手动安装

如果你希望自己安装，请准备 Python 3.11+ 和
[uv](https://docs.astral.sh/uv/)：

```bash
uv tool install "git+https://github.com/Museon-AI/museon-cli.git"
museoncli auth start
museoncli auth finish --wait
museoncli whoami
```

安装后可以使用 `museoncli`，也可以使用更短的别名 `museon`。

> 首个公开版本仍在准备中，目前仓库是私有的，安装时需要拥有仓库访问权限。

<details>
<summary><strong>参与 Museon CLI 开发</strong></summary>

[![CI](https://github.com/Museon-AI/museon-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/Museon-AI/museon-cli/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.11%2B-7C65C1)

```bash
uv sync --frozen --all-groups
uv run ruff check .
uv run pytest -q
uv run python scripts/gen_command_docs.py --check
uv run python scripts/gen_command_contract.py --check
uv build
```

命令定义位于 `museoncli/domains/`。修改命令后，需要重新生成文档和可移植的命令
契约：

```bash
uv run python scripts/gen_command_docs.py
uv run python scripts/gen_command_contract.py
```

</details>

参与贡献请阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。安全问题请按照
[SECURITY.md](SECURITY.md) 私下报告。
