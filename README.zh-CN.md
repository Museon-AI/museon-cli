<p align="center">
  <img src="./assets/readme/museon-icon.png" width="84" alt="Museon Logo">
</p>

<h1 align="center">Museon CLI</h1>

<p align="center">
  <strong>让你正在使用的 Agent 接手社媒运营。</strong><br>
  调研、创作、发布、复盘；重要操作仍由你决定。
</p>

<p align="center">
  <a href="https://www.museon.ai/zh/mel#cli">产品页面</a> ·
  <a href="./skills/museon-content-workflow-base/SKILL.md">Workflow Skills</a> ·
  <a href="./README.md">English</a>
</p>

Museon CLI 给你正在使用的 AI Agent 一套真正能执行的社媒工具：寻找内容机会、
了解内容为什么有效、生成新内容、经过你确认后发布，再根据真实表现调整下一轮。

你不需要换掉现在的 Agent。Museon 会给它完成社媒工作所需的能力，让一个想法
真正变成可以执行的运营工作。

随 CLI 分发的基础 Skill 内置了 **Mel——你的 AI 社媒运营** 的定位。
处理 Museon 任务时，Agent 会围绕你的目标推进调研、创作、已授权的执行和效果复盘，
通过 Museon CLI 执行并核实结果。这段定位会随 `museoncli setup` 一起安装。
产品介绍与 CLI 使用指引统一见 [MEL 页面](https://www.museon.ai/zh/mel#cli)。

## 把这段话交给 Agent

将下面这段话复制给 Codex、Claude Code、Cursor，或其他能够安装 Skill 并执行
Shell 命令的 Agent：

```text
请严格按照这份引导，为当前 Agent 配置 Museon CLI：
https://www.museon.ai/cli/install.md
```

这是推荐的安装方式。你不需要自己克隆仓库、研究 CLI 参数或手动配置凭证。

## 接下来会发生什么

1. **Agent 安装 Museon CLI。** 它会安装 GitHub Release 中固定版本的 Python wheel，
   并确认 CLI 命令真正可用。
2. **Museon CLI 安装 Skills。** CLI 会同时安装按任务结果拆分的工作流 Skills 和 Instagram Hook
   调研 Skill；需要登录态浏览时，再单独安装并初始化 ego lite。
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

当前工作树准备 CLI 2.0 命令面；下方固定安装链接仍指向最近已发布版本，发布另行执行。

保留 `research`、`campaign-monitor`、`content-analysis`、`routines`、`skills`，
新增 `hireaicreator` 领域，围绕既有 API 执行查询、规划、版本化编辑与交付回读。
新增 `media` 的本地文件上传、图片 URL 导入和媒体回读，并恢复 `artifacts` 的本地校验、
托管和分享；`social-account` 精确保留账号连接、读取、云手机、表现和资料编辑；
`ai-slideshow` 保留素材、独立生成与旧 slideshow 发布。五个集成 skill 分别承载基础原子能力、研究、HireAICreator、slideshow 与 campaign-monitor 流程。Agent 使用这些原子命令编排工作流。
写入后必须回读所属业务状态，不能把请求成功当成任务完成。

升级前请阅读[迁移说明](docs/cli-2-migration.md)。HireAICreator 业务域已包含在这个未发布候选中。
后端能力和数据没有随命令面退役而删除；权限仍由后端按用户、工作区和资源检查。

## 重要操作仍由你决定

- 调研和其他只读工作可以直接服务于当前任务。
- 创建、修改、排期、发布或删除内容时，Agent 必须遵守对应操作的确认要求。
- 重要操作执行前，Agent 会先说明具体要改变什么。
- 凭证保存在 Agent 所在的本地环境。Museon CLI 会优先使用系统凭据存储；只有
  无头环境无法使用系统凭据存储时，才会回退到权限为 `0600` 的本地文件。最终的
  权限判断始终由 Museon 服务端完成。

## 不通过 Agent 手动安装

如果你希望自己安装，请准备 Python 3.11+ 和 `uv`，然后安装 GitHub Release 中
固定版本的 wheel：

```bash
uv tool install "https://github.com/Museon-AI/museon-cli/releases/download/v0.7.2/museoncli-0.7.2-py3-none-any.whl"
```

安装成功后继续配置 Skills 和浏览器授权：

```bash
museoncli setup --agent codex
museoncli auth start
museoncli auth finish --wait
museoncli skills +list
museoncli whoami
```

Claude Code 和 Cursor 分别使用 `--agent claude-code`、`--agent cursor`；
`--agent auto` 会优先识别当前运行的 Agent；没有运行环境标记时，只会在唯一一个
已有的 Agent 目录中安装。如果检测到多个目录，请明确选择一个 Agent，或使用
`--agent all`。安装 Skills 后需要重启 Agent。完成授权后，`skills +list` 会列出当前工作区可用的业务 Skill。`auth finish --wait` 默认等待授权最多
五分钟，可以通过 `--timeout` 调整。CLI 可以使用 `museoncli`，也可以使用更短的
别名 `museon`。

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
uv build --wheel
uv run python scripts/verify_public_artifacts.py
```

命令定义位于 `museoncli/domains/`。修改命令后，需要重新生成文档和可移植的命令
契约：

```bash
uv run python scripts/gen_command_docs.py
uv run python scripts/gen_command_contract.py
```

</details>

参与贡献请阅读 [CONTRIBUTING.md](CONTRIBUTING.md) 和
[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)，版本变化记录在
[CHANGELOG.md](CHANGELOG.md)。安全问题请按照 [SECURITY.md](SECURITY.md) 私下报告。

## 开源协议

Museon CLI 使用 [Apache License 2.0](LICENSE) 开源。
