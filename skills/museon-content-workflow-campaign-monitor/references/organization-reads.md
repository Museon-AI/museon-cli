# Reading the organization's work

Each command reads the route the web page reads, in the organization the command acts in
(`museoncli org select`, or `--organization-id` for one call). The server decides what the
login may see, exactly as in the browser; on a Campaign shared into the organization the CLI
reads only its figures, and at the operator tier also its settlement, payouts, enrollments and
creator checks (`campaign-monitor`); a refusal is `not_found` (or `forbidden`): say the
login cannot see it, never retry under another identity. `--campaign-id` is the UGC campaign
id (`ugc campaign +list`, or `agency-campaign +list`'s `id`), not a campaign-monitor
collection id. All of these are reads: nothing changes.

## Tasks (任务)

| Need | Command | Who |
| --- | --- | --- |
| Each queue's open count, mine vs waiting on others | `ugc task-summary +get [--scope my-campaigns]` | owner/admin: every Campaign; operator: assigned Campaigns; member: reads |
| One queue's tasks | `ugc task +list --queue media\|onboarding\|creators\|posts\|viral\|invites\|client-reports\|all [--actor operator] [--campaign-id <id>]` | same |
| One task with its comments and history | `ugc task +get --id <task_id>` | same |

Start with `task-summary +get`, then list the queue with the most `--actor operator` work.
Pages follow `next_cursor` with `--cursor`.

## A Campaign's setup (设置)

| Need | Command | Who |
| --- | --- | --- |
| Everything the setup page shows, at once | `ugc campaign-setup +get --campaign-id <id> [--section <name> ...]` | per section, below |
| Type, approval mode, platforms, budget cap, product, readiness, briefs (payscales and contract for the team) | `ugc campaign-settings +get --campaign-id <id>` | anyone who sees the Campaign |
| PM / OP | `ugc campaign-staff +list --campaign-id <id>` | owner, admin, the Campaign's operators |
| Delivery targets | `ugc delivery-target +list --campaign-id <id>` | same |
| Payscales and rates | `ugc payscale +list --campaign-id <id>` | same |
| Contract template | `ugc contract-template +get --campaign-id <id>` | owner, admin, the Campaign's operators |
| Discord server | `ugc discord-server +get --campaign-id <id>` | same |
| DM rules, DM automations | `ugc dm-rule +list`, `ugc dm-automation +list` `--campaign-id <id>` | same |

`campaign-setup +get` lists a section the login may not read under `data.unavailable` with its
HTTP status (a member reads `settings` only). Report what is unavailable; don't guess it.

## Creators and conversations

| Need | Command | Who |
| --- | --- | --- |
| The organization's creators across Campaigns | `ugc creator +list [--search <text>]`, `ugc creator +get --id <id>` | operating organization's owner/admin/operators |
| The conversation with one enrolled creator | `ugc message +list --enrollment-id <id>` | owner, admin, the Campaign's operators |
| One enrollment's contract | `ugc enrollment +get-contract --enrollment-id <id>` | same |

Find enrollment ids with `ugc enrollment +list --campaign-id <id>`.

## Client reports

| Need | Command | Who |
| --- | --- | --- |
| A Campaign's reports | `ugc client-report +list --campaign-id <id> [--status ready]` | operating organization's owner/admin/the Campaign's operators; never a share |
| One report in full | `ugc client-report +get --campaign-id <id> --report-id <id>` | same |
| Report settings and their version | `ugc client-report-config +get --campaign-id <id>` | same |

## Analytics boards (分析)

| Need | Command | Who |
| --- | --- | --- |
| The organization's boards and those shared into it | `analytics board +list` | every member |
| One board: Campaigns and saved filters | `analytics board +get --id <id>` | every member |
| A board's figures | `analytics board +get-data --id <id> [--widget trends\|core-metrics\|content\|creators] [--date-from D --date-to D]` | every member; each Campaign as the board page shows it |

`+get-data` uses the board's saved dates, platform and post scope unless flags override them;
`core-metrics` needs a period. Say which window and scope every number uses.

## Organization settings

| Need | Command | Who |
| --- | --- | --- |
| Members, their role and Campaign scope | `organization member +list` | owner, admin, operator |
| Plan, AI credits and usage | `organization billing +get` | owner, admin |

Not available to the CLI (the web reads them in a signed-in browser only): partners, Campaign
and account shares in and out, the organization's signature, the team's work log, the creator
directory's insights and a creator's cooperation history.
