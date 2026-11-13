# Boards, client reports, broadcasts and reminders

These commands write what the web's 分析看板, 客户报告, 广播 and 提醒 pages write, through
the same routes. The server decides who may: board edits need edit rights on the board
(owner, admin, or an operator holding its Campaigns); everything under `ugc` here is the
Campaign's operations team's (owner, admin, or an operator on it), and `reminder +test`,
`reminder +subscribe` and `reminder-delegation` are MuseOn staff only. A refusal is
`not_found` or `forbidden`: report it, never retry under another identity.

`--campaign-id` is the UGC campaign id (`museoncli ugc campaign +list`). Board Campaign ids
are the same marketing campaign ids.

## Preview, ask, then write

Every write takes `--dry-run`: it reads the live state, returns what would change
(`changes` with `before`/`after`, who a broadcast reaches, where a report goes, anything
blocking it) and writes nothing. Commands that send something or cannot be undone also take
`--yes`; without it they fail (`ok: false`, `reason: confirmation_required`) and carry that
same dry run as `preview`. Show the user the preview, ask, and only then run with `--yes`. Never add `--yes` on your own.

| Needs `--yes` | Why |
| --- | --- |
| `ugc client-report +send` (and `--test`), `+request-review` | posts to the client's or the internal Feishu group (test: your own Mel chat) |
| `ugc broadcast +send`, `+schedule`, `+retry` | messages creators on Discord |
| `ugc broadcast +withdraw`, `+discard` | deletes sent messages / ends a draft |
| `ugc auto-nudge +update` | changes what creators are sent automatically |
| `ugc reminder +test`, `ugc reminder-delegation +cancel`, `analytics board +delete` | sends / removes |

Writes carry the server's guards: a report's `revision` and the settings `version`, a
broadcast's `updated_at`, a reminder policy's or auto nudge's `updated_at`. A `conflict`
means someone changed it since the read: read again and show the user before retrying.
Report actions use an idempotency key per report revision, so running the same `+send`
again after a lost answer does not send twice.

## Analytics boards

```bash
museoncli analytics board +create --name "Q4 UGC" --campaign-type ugc \
  --campaign-id <id> --campaign-id <id> --post-scope approved --dry-run
museoncli analytics board +update --id <board> --date-from 2026-11-01 --metric views \
  --metric engagement-rate --threshold views-min=1000
museoncli analytics board +set-source --id <board> --campaign-type mixed --campaign-id <ugc> --campaign-id <tracking>
museoncli analytics board +delete --id <board>          # preview; then --yes
```

`--campaign-type mixed` is UGC and content tracking Campaigns together; otherwise the
Campaigns' one type. Filters not passed keep their value; `none` clears a date, accounts,
metrics or thresholds, `--platform all` clears the platform. The public share link cannot
be managed from the CLI (the server allows it for a signed-in browser session only): tell
the user to open the board's 分享 in the web.

## Client reports

```bash
museoncli ugc client-report +create --campaign-id <id> --type daily --date 2026-11-12
museoncli ugc client-report +refresh --campaign-id <id> --id <report> --dry-run
museoncli ugc client-report +update --campaign-id <id> --id <report> --markdown-file report.md --expected-revision 4
museoncli ugc client-report +approve --campaign-id <id> --id <report>
museoncli ugc client-report +send --campaign-id <id> --id <report>      # preview; then --yes
museoncli ugc client-report-config +update --campaign-id <id> --enable daily \
  --daily-generate-time 09:00 --daily-due-time 12:00 --customer-group-id <group id> --dry-run
```

A report goes draft → `+request-review` → `+approve` → `+send`, or `+skip --reason`.
Editing an approved report needs approving again. The `--customer-group-id` /
`--internal-group-id` must be one of the groups the Campaign can use (the config
`--dry-run` lists the error with the choices).

## Broadcasts

```bash
museoncli ugc broadcast +audience --campaign-id <id>                 # who can be reached, channels, personas
museoncli ugc broadcast +create --campaign-id <id> --body "New brief is up" \
  --to-all-private-channels --persona-id <persona> --dry-run          # who it would reach
museoncli ugc broadcast +send --campaign-id <id> --id <broadcast>    # preview; then --yes
museoncli ugc broadcast +get --campaign-id <id> --id <broadcast>     # each delivery's outcome
```

Targets: `--to-all-private-channels` or `--private-channel-id`, `--to-all-direct-messages`
(at most 200), `--channel-id` (public channels), narrowed by `--persona-id`. Only a draft
can be edited (`+unschedule` a scheduled one first). Files are attached in the web.

## Reminders and automatic nudges

```bash
museoncli ugc reminder +get --campaign-id <id>
museoncli ugc reminder +update --campaign-id <id> --feishu on --digest-time 09:30 --task-kind review-creative --dry-run
museoncli ugc auto-nudge +update --campaign-id <id> --check not-set-up --check quiet --day mon --day thu --send-at 10:00
```

`inherit` falls a reminder setting back to the organization's; `none` empties a list
(`--digest-time none` stops digests). `ugc auto-nudge +update --off` stops automatic nudges.
