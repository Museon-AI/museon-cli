# Changelog

Museon CLI follows semantic versioning for its package and command contract.

## Unreleased

### Read what the web shows (coverage batch 1)

New read commands, each calling the route the web page already calls, addressed by the organization (`X-Organization-Id`); what a login may read is the server's decision, as in the browser. Agent Skill: `museon-content-workflow-campaign-monitor` → `references/organization-reads.md`.

| Command | Route | Who reads it |
| --- | --- | --- |
| `ugc task +list` | `GET /api/v2/ugc/agency/{org}/tasks` | owner/admin every Campaign's tasks, operator assigned Campaigns', member reads |
| `ugc task-summary +get` | `GET /api/v2/ugc/agency/{org}/tasks/summary` | same |
| `ugc task +get` | `GET /api/v2/ugc/tasks/{id}` and `.../events` | same |
| `ugc campaign-settings +get` | `GET /api/v2/ugc/campaigns/{id}` | anyone who sees the Campaign (payscales and contract for its team) |
| `ugc campaign-staff +list` | `GET .../campaigns/{id}/staff` | owner, admin, the Campaign's operators |
| `ugc delivery-target +list` | `GET .../campaigns/{id}/targets` | same |
| `ugc payscale +list` | `GET .../campaigns/{id}/payscales` | same |
| `ugc contract-template +get` | `GET .../campaigns/{id}/contract-template` | same |
| `ugc discord-server +get` | `GET .../campaigns/{id}/discord/guild-link` | same |
| `ugc dm-rule +list` / `ugc dm-automation +list` | `GET .../campaigns/{id}/dm-rules`, `/dm-automations` | same |
| `ugc campaign-setup +get` | all of the above at once; unreadable sections under `unavailable` | per section |
| `ugc message +list` | `GET /api/v2/ugc/enrollments/{id}/conversation` | owner, admin, the Campaign's operators |
| `ugc enrollment +get-contract` | `GET /api/v2/ugc/enrollments/{id}/contract` | same |
| `ugc creator +list` / `+get` | `GET /api/v2/ugc/agency/{org}/creators[/{id}]` | operating organization's owner, admin, operators |
| `ugc client-report +list` / `+get`, `ugc client-report-config +get` | `GET /api/v2/ugc/agency/campaigns/{id}/client-reports` | operating organization's owner, admin, the Campaign's operators |
| `analytics board +list` / `+get` | `GET /api/v1/analytics-dashboards[/{id}]` | every member |
| `analytics board +get-data` | the board's `/monitor-collection-sets/...` reads (trends, core metrics, content, creators) | every member |
| `organization member +list` | `GET /api/v1/organizations/{org}/members` | owner, admin, operator |
| `organization billing +get` | `GET /api/v1/billing/organizations/{org}/overview` | owner, admin |

- New domains `analytics` and `organization`.
- `campaign-monitor agency-campaign +list` and `agency-analytics +get` now read the organization the command acts in instead of always the operator organization: a brand organization lists its own Campaigns and those shared into it, as the web's Campaigns page does. Without a selected organization they still read the caller's operator organization; with neither they fail with `missing_organization` (was `forbidden`).
- The `campaign-monitor` settlement, payout, enrollment and creator-check commands work for a brand organization on a Campaign shared into it at the operator tier, as the web shows them (needs the server change of museon D-114). Their descriptions now name who reads them instead of "Agency team only".
- Not available to the CLI because the server serves them to a signed-in browser only: the team's work log, the creator directory's insights and a creator's history, partners, Campaign and account shares, and the organization's signature.

### Campaign lifecycle, setup, Formats and personas (`ugc`)

Agents can now create and run a Campaign end to end, through the routes the web's new-Campaign page, Campaign header, setup page and /formats page call. Every write reads the live state on `--dry-run` and writes nothing; writes that reach people outside, end or delete something also need `--yes`. Writes carry the route's compare-and-set token (`--expected-status`, `--expected-updated-at`, `--expected-version`), from the caller's earlier read or the read the command makes just before writing.

- Lifecycle: `ugc campaign +create` (UGC in operating-team organizations, or tracking; a draft on TikTok, Instagram, YouTube and Facebook, as the web creates it), `+launch` (`--yes`; the dry run shows `launchability`), `+pause`, `+resume`, `+complete` (`--yes`), `+archive` (`--yes`), `+restore`, `+rename`.
- Setup: `ugc campaign-settings +update` (approval and join mode, budget cap, post grouping, Format mode, platforms, Discord onboarding, `--settings-json` for languages, countries, stay/warmup/trial rules, content intake and the apply form, `--platform-pay-rules-json`; the whole settings object is written back with only those fields changed), `ugc campaign-staff +set` (PMs and OPs), `ugc delivery-target +create/+update/+delete`, `ugc contract-template +set` (default or custom; the dry run returns the filled preview), `ugc payscale +create/+update/+delete`, `ugc pay-rate +create/+update/+delete` (the dry run prices a video under the rate), `ugc discord-server +set/+initialize/+remove`, `ugc dm-rule +create/+update`.
- Formats (脚本, `brief`): `ugc brief-library +list/+get/+create/+update/+archive/+copy` for the organization library, and `ugc brief +create/+link/+unlink/+copy` inside a Campaign. Creates send an idempotency key and return it.
- UGC personas: `ugc persona +list/+create/+update/+delete` (not the `ai-slideshow` personas).
- The campaign-monitor Skill gains `references/ugc-campaign-setup.md`.

### Settings and account housekeeping (coverage batch 6)

New commands over the routes the web app already calls. Each addresses the organization only (`X-Organization-Id`); the server decides who may run it.

- `artifacts +list` / `artifacts +get`: list the organization's artifacts (page, search, `--all`) and read one (Markdown or download URL). Any organization role.
- `media collection +list` / `+get` / `+list-media`: the organization's media collections and the media in one. Any organization role.
- `media collection +update` (rename) and `+add` (up to 100 media; already-present media are skipped): owner, admin or operator.
- `media collection +delete` and `+remove` (media out of a collection) are destructive: `--dry-run` reads the collection and writes nothing, `--yes` runs. `+remove` reports `data.removed` and `data.failed` per media.
- `social-account tag +set` / `+add` / `+remove`: change an account's organization tags; `--dry-run` shows before and after. `+add` / `+remove` read and write back the full set (no server version check). Owner, admin or operator.
- `ai-slideshow cta-target +list` / `+create` / `+update` (staff only on the server) and `+retire` (owner, admin or operator; needs `--yes`): a product's CTA targets.

Not added, because the API refuses an API key or needs a workspace the CLI never sends: organization members (invite, role, Campaign scope, removal), partner organizations, Campaign and account shares, the organization signature (all signed-in session only); social account sync and unbinding, scheduled-item approval, failed-publish retry, AI image post review, and creating a media collection (workspace required). The API has no artifact delete.

### Boards, client reports, broadcasts and reminders (coverage batch 5)

The writes the web makes, through the same routes.

- New `analytics` domain. `analytics board +create` makes a multi-Campaign board in the selected organization (1 to 10 Campaigns of one type, `mixed` for UGC and tracking together, optional opening filters); `+update` renames it or changes its filters (dates, platform, post scope, accounts, thresholds, metrics, chart mode; only the ones passed); `+set-source` replaces its Campaigns; `+delete` deletes it (`--yes`). The public share link stays in the browser: the server opens and closes it for a signed-in person only.
- `ugc client-report`: `+create` (generate the daily, weekly, monthly or wrap-up report of a date's period), `+update` (title or Markdown, guarded by the report revision), `+regenerate`, `+refresh` (`--dry-run` returns the server's proposed figure changes; `--keep-change` keeps one), `+approve`, `+skip --reason`, and `+request-review` / `+send` (`--test` to your own chat with Mel), which post to Feishu and take `--yes`. Actions carry the report revision, the settings version and an idempotency key per revision, so a rerun never sends twice. `ugc client-report-config +update` changes which reports run, their times, weekly day, timezone, data scope, language, client and internal groups, owner and reviewer (guarded by the settings version). These routes name the operator organization `agency_workspace_id`; the CLI sends the organization id there.
- `ugc broadcast`: `+audience`, `+list`, `+get`; `+create` and `+update` write a draft (all or some private channels, direct messages, public channels, personas); `+send`, `+schedule`, `+retry`, `+withdraw` and `+discard` take `--yes`; `+unschedule`. Files are attached in the browser.
- `ugc reminder`: `+get`, `+update` (the Campaign's own reminder policy; `inherit` falls back to the organization's; guarded by `expected_updated_at`), and for MuseOn staff `+test` (`--yes`) and `+subscribe`. `ugc reminder-delegation +create` / `+cancel` (`--yes`, staff). `ugc auto-nudge +get` / `+update` (`--yes`): which creator checks trigger an automatic Discord nudge, on which days and at what time; `--off` stops it.
- Commands that send something or cannot be undone take `--yes`; without it they return the same preview as `--dry-run` (what would be sent, to whom, and anything blocking it) instead of failing, so the Agent can show the user before asking.

## 1.0.1

Know which version runs and how to upgrade it.

- Every command's JSON carries `_notice.update` while a newer stable release exists that this installation did not install: `{current, latest, install_method, upgrade_command, changelog_url, message}`. `message` is one sentence for the Agent to pass on, e.g. "Museon CLI 1.0.1 is outdated (latest 1.1.0). Tell the user to run: …". An interactive terminal also gets one stderr line, at most once a day: `Museon CLI 1.0.1 → 1.1.0 available. Upgrade: <command>  Changes: <url>`. Pipes, CI and `MUSEONCLI_UPDATE_CHECK=0` get no line; the JSON notice stays unless checks are disabled.
- After the CLI upgrades itself, the next output carries `_notice.updated {from, to, changelog_url, highlights}` once, and a terminal gets `Museon CLI upgraded 1.0.0 → 1.0.1. Changes: <url>` once.
- The CLI names how it was installed (`install_method`): `uv_tool` (official; upgrades itself), `pipx`, `uv_pip`, `pip` or `other` (notice with the matching upgrade command), `source` and `managed` (a source checkout or a host runtime such as Mel's sandbox: no notices, their owner updates them).
- Installs that cannot upgrade themselves now learn the latest release too, without ever making a command wait: commands read a cache, and when it is older than 15 minutes a detached background process refreshes it, so the notice appears from the next command on. `version` and `upgrade` ask GitHub directly. A failed check never fails a command. The uv tool check is unchanged.
- pip, pipx and other non-uv installs used to count as host-managed. They no longer do, so Agent Skills that `museoncli setup` installed for them are now kept in sync like the uv tool's (`_notice.skills`).
- `museoncli version` adds `current`, `latest`, `install_method`, `upgrade_command`, `changelog_url` and `update_status` (`data.update` is unchanged).
- New `museoncli upgrade`: an official uv tool install verifies and installs the latest release (also when `MUSEONCLI_UPDATE_CHECK=0`) and reports `status: upgraded`; other installs get `status: manual` with the command to run; `current` and `managed_externally` say so. A release check that cannot reach GitHub is `network_error` (retryable).
- Command contract 1.0.1: `catalog.cli` lists `version` and `upgrade`, and `schemas` has their entries (`museoncli schema version`), including the `_notice` shape. Domain commands are unchanged.
- The base Skill tells Agents to relay `_notice.update` once after the task and offer `museoncli upgrade`. The `cli_outdated` (HTTP 426) fallback hint points at `museoncli upgrade`.

## 1.0.0

Organizations only. MuseOn addresses organizations; workspaces are internal storage and are gone from the CLI. This release removes the workspace aliases that 0.25 kept and makes every request outside `agentic-campaign` and `hireaicreator` address the organization alone. It has no backward compatibility with the workspace surface.

### Breaking changes

| Before (0.25 and earlier) | Now (1.0.0) |
| --- | --- |
| `museoncli workspace list` | `museoncli org list` |
| `museoncli workspace current` | `museoncli org current` |
| `museoncli workspace select --id <workspace-id>` | `museoncli org select --id <organization-id>` (or `--name <exact name>`) |
| `--workspace-id <workspace-id>` on a command | drop it; `--organization-id <organization-id>` addresses another organization for one call |
| `workspace_id` in `--args-json` / `--args-file` | drop it |
| envelope `.workspace` | envelope `.organization` (`{id, name}` or `null`) |
| `auth status` / `auth login` / `auth finish` `.workspace` | `.organization` |
| `whoami` `.workspaces`, `.default_workspace_id`, `.default_workspace_name` | `.organizations`, `.default_organization_id`, `.default_organization_name` |
| `ai-slideshow asset +list --scope workspace` | `--scope organization` |
| `cloud-phone recovery +preview` / `recovery-job +create` `--scope workspace` | `--scope organization` |
| contract `authorization.workspace_bound` | `authorization.organization_bound` |
| contract `schema_version: 2` | `schema_version: 3` |

- `museoncli workspace ...` and `--workspace-id` are unknown: a usage error (exit 2). A `workspace_id` key in structured input is refused before any request (`invalid_input`).
- No request from these commands carries `workspace_id` (query, JSON body or upload form) or a workspace header; each carries `X-Organization-Id` for the selected organization or `--organization-id`. This covers every domain except the two below: `ai-slideshow`, `artifacts`, `campaign-monitor` (including the payments reads), `cloud-phone`, `content-analysis`, `media`, `publish`, `research`, `routines`, `skills`, `social-account`, `staff-ops` and `ugc`.
- `ugc campaign +list` always reads the organization's UGC campaigns; the `/ugc/workspaces/{id}/campaigns` route is no longer used.
- `media +upload --media-type file` and `media +generate` no longer require a `workspace_id` in the server's receipt; a receipt is proven by its artifact, task and media ids.
- `social-account +connect-adb`: the ADB relay renews the phone lease in the organization the command addressed (`--organization-id` when given), not in a workspace.
- Config: a pre-0.25 `workspace` block still migrates to its organization when it names one, and is then dropped from `~/.museoncli/config.json`; the CLI no longer writes it. A 0.22-era block without an organization selects nothing: run `museoncli org select`.
- Command contract: no input schema outside the two groups declares `workspace_id`, no output schema declares `workspace`, and `workspace_bound` is gone from their `authorization`.

### Unchanged: agentic-campaign and hireaicreator

These two groups keep their 0.25 behaviour until they move to organizations. hireaicreator commands still take the deprecated `--workspace-id` (and `workspace_id` input), send it when given and print the stderr notice; both groups' envelopes keep the `workspace` key; their contract entries are byte-for-byte the 0.25 ones. `org list` rows keep the server's `default_workspace_id`, which `hireaicreator actor +preview-assign --target-workspace-id` reads. All of it lives in `museoncli/domains/_legacy_workspace.py`.

### Server compatibility

- Requires the Museon API whose Agent CLI routes are organization-only and ignore `workspace_id` (Museon-AI/museon). Commands that still need a workspace on the server side are listed in the release PR.
- Once that API is live it rejects CLIs older than 1.0.0 with HTTP 426 `cli_outdated` and the upgrade command; upgrade with `uv tool upgrade museoncli`.

## 0.25.0

MuseOn has organizations only: your organization role and Campaign scope decide what you can see and change. The CLI now addresses an organization instead of a workspace.

- New `museoncli org list | current | select --id <organization-id> | --name <name>`. `org list` returns each organization with your `role` (owner/admin/operator/member), `campaign_scope` (all/chosen) and `is_default`. The selection is stored in `~/.museoncli/config.json` as `organization {id, name}`.
- Every API request (`/api/v1` and `/api/v2`, uploads and downloads included) carries `X-Organization-Id` for the selected organization. Any domain command takes `--organization-id` to address another organization for one call. The CLI no longer picks a workspace: the server resolves it from the organization. `X-Museon-Workspace-Id` is no longer sent; `X-Museon-Organization-Id` (usage attribution) is unchanged.
- `whoami` adds `organizations[]`, `default_organization_id` and `default_organization_name`; against an older server the CLI derives them from `workspaces[]`. `auth login` / `auth start` request the selected organization (`requested_organization_id`) and store the approved one.
- `ugc campaign +list` reads the organization's UGC campaigns across all its workspaces (`/ugc/organizations/{id}/campaigns?campaign_type=ugc`; `--status archived` lists archived ones instead of live ones); `--workspace-id` keeps the workspace route. `campaign-monitor payment +list` and `payment-summary +get` address the organization through the header alone.
- Output envelopes gain an `organization` key next to `workspace`. `workspace` stays until 1.0 but is only set when `--workspace-id` was given.
- HTTP 426 `cli_outdated` reads the same on every route (agent-cli, `/api/v2`, uploads): `reason: cli_outdated`, a message with the minimum version, and `error.hint` with the upgrade command. HTTP 409 `organization_workspace_mismatch` is explained in `error.message`.
- Command contract: `authorization.organization_bound` (with a deprecated `workspace_bound` mirror), roles `organization_member` / `organization_admin_or_staff`, resource policy `server_evaluated_organization_and_resource_access`. Every input schema that has `workspace_id` marks it deprecated and adds an optional `organization_id`.

### Migration

| Before (0.24 and earlier) | Now |
| --- | --- |
| `museoncli workspace list` | `museoncli org list` |
| `museoncli workspace current` | `museoncli org current` |
| `museoncli workspace select --id <workspace-id>` | `museoncli org select --id <organization-id>` |
| `--workspace-id <workspace-id>` on a command | drop it, or `--organization-id <organization-id>` |
| envelope `.workspace` | envelope `.organization` |

- `workspace list | current | select` and `--workspace-id` keep working as deprecated aliases until 1.0. Each use prints a one-line notice on stderr and adds it to `warnings`. `workspace select` selects that workspace's organization.
- The selected workspace is no longer a default. A script that relied on it now acts in the selected organization; pass `--workspace-id` only to keep the old addressing during the transition. A workspace from another organization than the addressed one is refused with 409 `organization_workspace_mismatch` (exit 5).
- Existing configs migrate on read: a 0.23/0.24 `workspace` block selects its organization. The block itself is left untouched so an older CLI can still read the file, but it is never used to address requests. A config written by 0.25 stays readable by 0.22–0.24, which ignore `organization`.
- Requires the Museon API that accepts `X-Organization-Id` and resolves workspaces from organizations (Museon-AI/museon, organization phase 1). Against an older API, `/agent-cli` commands fall back to the key's default workspace as before; `/api/v2` commands (agentic-campaign, hireaicreator, ugc) need the new API or an explicit `--workspace-id`.

## 0.24.0

- 自动升级同样覆盖 `setup` 装过的 Agent Skills：发现本机为 Codex / Claude Code / Cursor 安装的 Museon Skills 与当前 CLI 自带版本不一致（含 CLI 自动升级后）时自动同步，并在该次命令的 JSON（成功、失败和大结果清单）里带 `_notice.skills.updated`，提醒 Agent 重读 Skill。同步失败或 `MUSEONCLI_UPDATE_CHECK=0` 时不写入，改为每条命令带 `_notice.skills.command` 提示手动运行 `museoncli setup`。没跑过 setup 的 Agent 不处理；托管 runtime 和源码环境不检查。

## 0.23.0

- 官方 `uv tool` 安装默认在执行命令前检查稳定版并自动升级，校验官方 wheel 的 SHA-256，再用新版继续原命令。普通检查缓存 15 分钟，`version` 强制检查并报告状态；并行命令共享升级锁。源码和托管 runtime 由各自发布流程更新。
- `MUSEONCLI_UPDATE_CHECK=0` 保留固定版本/离线用法；检查不可用时明确提示，已发现新版但升级失败时停止业务命令。升级不修改登录或 workspace，不会重复执行写操作。
- 修复 `hireaicreator video +list --publishing-account-ids a,b,c` 静默返回空的问题。共用解析器的 ID 数组 flag 支持 CSV、重复和混合输入，拆分后仍执行原数量/元素校验；JSON 数组保持原语义。

## 0.22.3

- `social-account +create-connect-link --platform youtube` creates a YouTube self-authorization link. The Museon API already accepts `youtube`; the CLI's platform list did not.
- `publish post +schedule` help no longer cites a 2-per-day, 120-minute limit; the Museon API applies neither to manually scheduled media.

## 0.22.2

- `social-account +connect-adb` (alias `+adb-connect`) waits for a cold cloud phone: when the Museon API answers `CLOUD_PHONE_BOOTING`, it backs off and asks again for up to 110 seconds in total, without starting the phone twice. After that it returns the same error, still `retryable`. Requires the Museon API change that introduces the code (Museon-AI/museon#6973); against an older API it behaves as before.

## 0.22.1

- `campaign-monitor payment +list` and `payment-summary +get` accept `--workspace-id`, like every other workspace command; they read the selected workspace only before.
- Payments are the Agency team's: the Brand View has no Payments page, and these two commands now answer the team only (with the Museon API change that removes Brand access).

## 0.22.0

- New `ugc` domain lets an operator's agent read and edit UGC briefs through the UGC workbench (`/api/v2/ugc`), with the operator's own API key and the same workspace role as the web app:
  - Reads: `ugc campaign +list`, `ugc enrollment +list`, `ugc brief +list/+get/+progress`, `ugc creative +list` (`--brief-id none` lists creatives with no brief).
  - Writes: `ugc creative +set-brief/+apply-default-briefs`, `ugc brief +update/+upload-media`, `ugc assignment +create/+update-terms/+withdraw`.
- Human in the loop: the workbench never asks for confirmation, so the agent does. A new `CommandSpec.dry_run_reads_server` field makes `--dry-run` run the executor, which reads live state (what changes, how many creators are working on the brief, whether the caption rule changes), writes nothing, and returns `warnings` and `next_steps` telling the agent what to ask the user. `brief +update --notify` asks the server to send each creator on a live assignment a "Your brief was updated" card.
- The campaign-monitor skill and the base skill's routing table gain the `ugc` command map.
- Requires the Museon API with Museon-AI/museon#6687 (the `notify` field and `POST /campaigns/{id}/creatives/default-briefs`) deployed.

## 0.21.0

- New Campaign Dashboard reads under `campaign-monitor`, each calling the route the web Dashboard calls for the same figures, so a login reads exactly what it sees in the browser:
  - Both views: `campaign +get`, `video +list` / `+get` (UGC videos with their review status; detail, summary, daily and insights), `roster +list` (By Creator), `format +list`, `format-post +list`, `report +get --widget cumulative-views|content-tiers|creator-countries`, `creator-tag +list`, `audience +get` (by day), `payment +list`, `payment-summary +get`.
  - Agency team only: `agency-campaign +list [--with-progress]`, `agency-analytics +get`, `audience +get --by period`, `settlement +get`, `payout +list`, `activity +list`, `enrollment +list`, `assignment +list`, `creator-check +get` / `+list`.
- `--id` is the campaign as `campaign-monitor +list` returns it; UGC routes resolve the UGC campaign with one read, Agency-wide reads take the caller's Agency from `/ugc/agency/me`. These commands are not bound to the selected workspace.
- The campaign-monitor skill gains the Dashboard command map (`references/dashboard.md`).
- No API change is required to call them. The Museon API change that holds Brand members, read grants and share links out of the Agency-only routes, and holds CLI keys to their approved workspaces, ships separately.

## 0.20.0

- Campaign summaries and post lists now accept `--timezone`, so daily reports use one publication calendar across summaries, breakdowns and post drilldown.
- Post lists now expose `--brief-id`, `--persona-id`, `--ugc-creator-id` and `--review-status approved|awaiting-review` for UGC fulfillment drilldown.
- The Campaign workflow explains fulfillment identity, approval buckets, observation coverage and the distinction between local publication dates and UTC observed snapshot deltas.

## 0.19.0

- New `campaign-monitor +get-breakdown --id --by brief|persona|tag|creator-tag [--link-status linked] [--date-from] [--date-to] [--platform] [--timezone]`: groups a campaign's counted posts by one dimension, from `GET /agent-cli/campaign-monitors/{id}/breakdown`. The campaign type decides the menu and the default (`ugc`: brief; others: creator-tag). Rows are value / unassigned / awaiting_review with posts, creators, measured_posts, metric sums and median_views; tags overlap.
- The flag is kebab-case (`creator-tag`); the API takes the dimension as `+list-dimensions` names it (`creator_tag`).
- The campaign-monitor skill's analysis order gains the breakdown step: report unassigned and awaiting_review before per-brief numbers, compare on median.
- Requires the Museon API with `GET /agent-cli/campaign-monitors/{id}/breakdown` deployed.

## 0.18.0

- New `campaign-monitor +list-dimensions`: the campaign's type, its post scopes, and its dimensions (`ugc`: brief with its persona, persona, tag; other types: `creator_tag`), from `GET /agent-cli/campaign-monitors/{id}/dimensions`.
- New `--link-status linked` on `campaign-monitor +list-content` and `+list-creators`, matching the Campaign page's Approved scope.
- The campaign-monitor skill gains the analysis order: dimensions first, then the scope, coverage before per-brief numbers, tags overlap.
- Requires the Museon API with `GET /agent-cli/campaign-monitors/{id}/dimensions` deployed.

## 0.17.1

- `hireaicreator video +create-from-upload` documents `scheduled_at`: omit it or pass null and the video stays `approved` and never publishes until `video +bulk-schedule` gives it a time. There is no publish-now value; pass a time a few minutes ahead to publish soon. The command now warns and lists the video IDs it left unscheduled.
- No API change is required.

## 0.17.0

- New staff commands for social app versions on cloud phones:
  - `cloud-phone app +list` reads installed and team-pinned versions of YouTube, Facebook, Instagram and TikTok live from up to 50 phones (`--phone-id`) or accounts (`--account-id`). Each app reports `current`, `outdated`, `ahead`, `installing`, `missing` or `unpinned`.
  - `cloud-phone app-upgrade +preview` shows which phones an upgrade would move up to the team's pinned version and why others are skipped; nothing changes.
  - `cloud-phone app-upgrade +create` upgrades outdated apps to the pinned version in the background (never downgrades or installs a missing app). It needs `--yes` and an idempotency key; a retry with the same key never upgrades a phone twice. Follow progress by rerunning `cloud-phone app +list`.
- `publish job +list` and `+get` return each job's `delivery`: `stage` (`verifying` means the publishing service already reported and Museon is confirming the post on the platform until `verification.deadline_at`), the service's own report as `upstream`, and `verification`. It is null for older jobs.
- Requires the Museon API with `GET /agent-cli/cloud-phones/apps`, `POST /agent-cli/cloud-phones/app-upgrades/preview`, `POST /agent-cli/cloud-phones/app-upgrades`, and `delivery` on publish jobs.

## 0.16.0

- `social-account +connect-adb` routes ADB through a local relay. Museon now shuts down a cloud phone whose lease nobody renews; the relay renews it at most once a minute while ADB traffic flows and exits after 15 minutes without ADB traffic, so a phone stays on while a script or agent operates it and shuts down about 15 minutes after the last ADB command. An open but idle ADB connection sends no traffic and does not keep the phone on. The returned serial is the relay's local address (`127.0.0.1:<port>`); a later `+connect-adb` for the same account reuses it.
- New `social-account +renew-phone-lease`: keeps an account's cloud phone on for 15 more minutes. The relay runs it; scripts that hold ADB some other way can run it themselves.
- Requires the Museon API with `POST /agent-cli/social-accounts/{account_id}/phone-lease`.

## 0.15.0

- 新增员工云机与 IP 管理：查询、批量添加、检测、分组、供应商、换 IP、待处理事项及资源回收。
- 连接凭据仅导出至受保护的本地文件；批量操作保留逐项失败，查询显示数据更新时间。

## 0.14.0

- `publish post +schedule` takes an optional `music_url` per item: a TikTok post link (`/video/<id>` or `/photo/<id>`) whose sound the cloud phone reuses as the post's background music, like "use this sound". Sound pages (`/music/...`), short links and bare IDs are rejected before any upload. Accounts not on a cloud phone publish without it; an item without it keeps the cloud phone's random sound.
- Uses the existing `bgm_config.ref_video_id` of `POST /api/v2/pool-accounts/publish`; no new API is required.

## 0.13.0

- `publish post +schedule` publishes TikTok photo sets: an item takes `image_files` (local images, uploaded in order) or `image_media_ids` (1-30 images; the first is the cover) instead of a video `file` / `media_id`. Photo sets publish to TikTok accounts on a GeeLark cloud phone; `product_id` stays video-only. Retries reuse each uploaded image under the same idempotency key.
- Requires the Museon API that accepts `image_media_ids` on `POST /api/v2/pool-accounts/publish`.

## 0.12.0

- New `publish` domain: publish finished videos to the social accounts bound to a workspace, without HireAICreator campaigns.
  - `publish account +list` lists the workspace's bound accounts (filter by platform and device kind).
  - `publish post +schedule` uploads local videos (or reuses media IDs) and schedules each on the chosen accounts with a caption, at a scheduled time or `now=true`. It sends an idempotency key: a retry reuses uploads and the server returns the batch it already accepted instead of posting twice. Resend the same input unchanged when retrying.
  - `publish job +list`, `+get` and `+cancel` read and cancel the resulting publish jobs.

## 0.11.0

- Breaking: `hireaicreator video +publish-local` and `hireaicreator video +create-from-upload` require `campaign_id`. Uploaded videos without a campaign published but never reached the Campaign dashboard or Campaign sync, and a campaign cannot be assigned after creation. Requests without one are rejected before any network call; look the id up with `workspace select --id <workspace>` followed by `agentic-campaign +list --all`.
- `video +publish-local` binds the campaign to the idempotency key. Receipts written by earlier versions stay readable, and a batch submitted before this change whose outcome is unknown is replayed with its original request first.

## 0.9.1

- `hireaicreator plan +create` accepts optional `generation_options` in structured JSON, including `compshare-h3`, video duration, audio, image settings, and Actor reference image media IDs.
- Provider model IDs retain their original spelling when sent to the API.

## 0.8.2

- `hireaicreator account +list` takes a repeatable `--tags` to filter by workspace account tags (any match); tags must not contain commas.

## 0.8.1

- Fix: `--all` now works on commands whose records sit one level deeper (`data.data.<records>`), e.g. `campaign-monitor +list-creators`.
- Fix: a usage error for a missing required flag now names its `command` and points at that command's `--help`.

## 0.8.0

- Errors: every failure carries `command` and an `error` object (`code`, `message`, `server_code`, `http_status`, `retryable`, `hint`); `reason` is always a category. Usage errors are JSON on stdout. New exit codes: 3 not found, 4 authentication required, 5 conflict.
- Paged reads add a normalized `page_info`; read commands with `--page` take `--all`.
- Every flag has help and every command shows a runnable example; `schema` accepts CLI paths.
- HireAICreator actions are now a verb or a verb with its object (51 renames, e.g. `video +from-upload` → `+create-from-upload`, `test-group +accounts-set` → `+set-accounts`, `warmup +journeys` → `+list-journeys`). Old names keep working, hidden from help, and return a deprecation warning; `schema` lists them under `deprecated_aliases`.
- The same rule now covers every other domain (70 renames, e.g. `research +web-research` → `+search-web`, `social-account +connect-link-create` → `+create-connect-link`, `campaign-monitor +creator-list` → `+list-creators`, `ai-slideshow publish +schedule-plan-batch` → `+submit-schedule-plan`, `routines +memory-get` → `+get-memory`). Old names keep working the same way.
- Fix: `ai-slideshow generation +create` returns its run and frontend links again.

## 0.7.3

- 新增 `hireaicreator actor +resolve`：一次最多读取 200 个 Actor 及其参考图 URL。
- 新增 `hireaicreator product +list`：一次读取工作区产品的描述、卖点、目标人群和全部图片素材。
- 新增 `hireaicreator video +from-upload`：把 `media +upload` 上传的外部成片登记为发布任务，带文案和排期，支持幂等重试。
- 新增外部生成视频上传与排期发布的 best practice（HireAICreator skill 参考文档），要求每条视频只发给同一个 Actor 名下的账号。

## 0.7.2

- Add `campaign-monitor +period-performance` for frontend-aligned period-end snapshot comparisons.
- Clarify that `campaign-monitor +summary` reports daily content-trend totals rather than Period Performance snapshots.

## 0.7.1

- 新增 Actor 批量权限与锁诊断、跨工作区复制和移动，以及实时操作预览。
- 执行需要明确确认、匹配的预览与幂等键；保留服务端冲突，防止自动覆盖变化或重复复制。
- 更新 Mel 工作流，说明共享编辑锁的复制解决方式与目标工作区回读。

## 0.7.0

- Add staff-only, read-only operational commands for deployed API code, bounded
  Supabase queries, Cloud Logging, and the Agents per-turn timeline.

## 0.6.3

- Add complete HireAICreator Test Group, warmup, video review and scheduling, Format, and Clip operations for Codex and Mel.
- Preserve workspace authorization, optimistic concurrency, explicit confirmations, and endpoint-supported idempotency.
- Treat successful HTTP 204 deletion responses as success.
- Include manual Actor video creation and publish matching workflow skills and command discovery.

## 0.6.2

- Added HireAICreator account Actor and Persona binding commands with publish asset readback, workspace selection, and dry-run validation.

## 0.6.1

- Removed the low-level `hireaicreator test-plan +ensure` command and made Test Group listing work without a Plan ID.
- Added Persona-based Actor creation and generation batch commands, including candidate selection.

## 0.6.0

- Replaced the former AI Hook public domain with `hireaicreator`, exposing 45 commands including read-only item and batch history queries.
- Added `media` upload, import, read, generation, and status commands with explicit idempotency and billing boundaries.
- Added `ai-slideshow` with 32 asset, generation, publish configuration, version, scheduling, and batch publishing commands.
- Kept 13 selected `social-account` commands and retired the former account-operation, account-publish, asset, generation, product, evaluator, and agentic-campaign top-level domains.
- Consolidated the public Agent Skills into five packages: base, research, HireAICreator, AI Slideshow, and campaign monitor.
- Kept artifacts, routines, content analysis, media, and social-account atomic guidance under the base Skill, while preserving research and campaign monitoring as separate workflows.
