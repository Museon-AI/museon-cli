# Museon CLI

> 让任何能够执行 Shell 命令的 AI Agent，通过 Museon 完成社媒调研、创作、
> 发布和复盘。

[English](README.md)

[![CI](https://github.com/Museon-AI/museon-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/Museon-AI/museon-cli/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB)

Museon CLI 是 Museon 托管式社媒运营平台的开源客户端。它为 Agent 提供可发现的
命令 Schema、稳定的 JSON 输出、工作区鉴权，以及写操作所需的风险与确认信息。

## 为什么适合 Agent

- **可发现：** `museoncli schema` 是命令、参数、示例、风险等级和执行方式的
  唯一事实来源。
- **结构稳定：** stdout 始终返回 JSON，Agent 不需要解析终端文案。
- **工作区鉴权：** 通过浏览器登录，将本地 CLI 连接到用户有权访问的工作区。
- **操作克制：** 写入和破坏性操作会在 Schema 中声明 dry-run 与确认要求。
- **容易接入：** wheel 内置通用 Agent Skill，可交给不同的 Agent 使用。

## 安装

首个 PyPI 版本正在准备中。目前拥有私有仓库权限的协作者可以从源码安装：

```bash
git clone https://github.com/Museon-AI/museon-cli.git
cd museon-cli
uv tool install .
```

安装后可以使用 `museoncli`，也可以使用更短的别名 `museon`。

## 登录授权

先启动设备授权，在浏览器里选择并确认工作区，然后完成登录：

```bash
museoncli auth start
museoncli auth finish --wait
museoncli whoami
```

凭证只保存在本机。Museon API 会根据当前用户的组织、工作区成员关系、角色和
目标资源，对每一次操作进行鉴权。

## 先发现，再执行

```bash
# 查看所有能力域
museoncli schema

# 查看调研相关命令
museoncli schema research

# 执行前读取一个命令的完整契约
museoncli schema research.social-media-search
```

每个命令都会返回稳定的 JSON Envelope：

```json
{
  "ok": true,
  "data": {},
  "run": null,
  "warnings": [],
  "next_steps": []
}
```

## 能力范围

| 目标 | Domain |
| --- | --- |
| 查找市场、创作者、内容、社区与视觉证据 | `research`、`campaign-monitor` |
| 分析内容并沉淀可复用知识 | `content-analysis`、`asset`、`artifacts`、`skills` |
| 生成图片与轮播内容 | `generation` |
| 连接账号、安排内容、发布并查看效果 | `social-account`、`account-operation` |
| 执行一次性或周期性的运营循环 | `routines`、`evaluator` |

当前生成的契约包含 11 个 Domain、95 个命令。Agent 应读取实时 Schema，而不是
复用旧对话中的参数。

## 交给 Agent

可以把下面这段话直接交给 Agent：

```text
帮我安装 Museon CLI：https://github.com/Museon-AI/museon-cli。
通过浏览器完成授权，先运行 `museoncli schema`，每次执行前读取对应命令的完整
Schema。写入或破坏性操作需要单独向我确认。
```

仓库内置的 [Agent Skill](museoncli/bundled_skills/museon-cli/SKILL.md) 包含调研、
创作、发布、复盘、Artifact 与鉴权恢复等工作流说明。

## 仓库边界

这个仓库只包含可安装的 CLI、命令注册表、生成的契约、文档、测试和通用 Agent
Skill。鉴权、权限判断、业务执行、平台集成与客户数据由 Museon 托管服务负责。

CLI 不区分所谓 public/internal 命令。登录后的用户与 Agent 看到同一份命令契约，
服务端根据当前身份判断是否允许执行具体操作。

## 本地开发

```bash
uv sync --frozen --all-groups
uv run ruff check .
uv run pytest -q
uv run python scripts/gen_command_docs.py --check
uv run python scripts/gen_command_contract.py --check
uv build
```

修改命令时，需要同时重新生成文档和 JSON 契约：

```bash
uv run python scripts/gen_command_docs.py
uv run python scripts/gen_command_contract.py
```

完整检查清单见 [CONTRIBUTING.md](CONTRIBUTING.md)，安全问题请阅读
[SECURITY.md](SECURITY.md)。
