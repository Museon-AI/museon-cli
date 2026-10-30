# Campaign Dashboard reads

Every command below takes `--id` as `campaign-monitor +list` returns it. The resource
commands (`campaign +get`, `video +list`, ...) work in any workspace the login can read; the
selected workspace only scopes `payment` reads. The flat commands (`+get-summary`,
`+get-period-performance`, `+list-content`, `+list-creators`) read only the selected
workspace's campaigns: pass `--workspace-id` with the campaign's `workspace_id`
(from `campaign +get` or `agency-campaign +list`).

## Both views (Brand View and Agency workbench)

| Dashboard place | Command |
| --- | --- |
| Header: type, status, start date | `campaign-monitor campaign +get --id <id>` |
| KPI tiles and trend | `campaign-monitor +get-summary --id <id>` |
| Analytics: current vs previous period | `campaign-monitor +get-period-performance --id <id>` |
| Analytics: cumulative views, content tiers, creator countries | `campaign-monitor report +get --id <id> --widget <widget> --date-from D --date-to D` |
| Content tab, UGC (videos, review status) | `campaign-monitor video +list --id <id> [--status confirmation\|review\|not-counted]` |
| One video: detail, summary, daily, insights | `campaign-monitor video +get --id <id> --content-id <content_id> --section <section>` |
| Content tab, tracking (posts) | `campaign-monitor +list-content --id <id>` |
| Creators tab, UGC (By Creator) | `campaign-monitor roster +list --id <id>` |
| Creators tab, by account | `campaign-monitor +list-creators --id <id>` |
| Creator tags | `campaign-monitor creator-tag +list --id <id>` |
| Performance by Format | `campaign-monitor format +list --id <id>`, then `format-post +list --brief-id <brief_id>` |
| Daily audience (trend tooltip) | `campaign-monitor audience +get --id <id> --date-from D --date-to D` |
| Payments page (selected workspace) | `campaign-monitor payment +list`, `campaign-monitor payment-summary +get` |

## Agency team only

| Dashboard place | Command |
| --- | --- |
| All campaigns across Brands, delivery progress | `campaign-monitor agency-campaign +list [--with-progress]` |
| Agency analytics over every UGC campaign | `campaign-monitor agency-analytics +get` |
| Audience map and profile over a period | `campaign-monitor audience +get --id <id> --by period --date-from D --date-to D` |
| Settlement tab | `campaign-monitor settlement +get --id <id> --date-from D --date-to D [--creator-id <ugc_creator_id>]` |
| Settled payouts | `campaign-monitor payout +list --id <id>` |
| Operations: enrollments, assignments, creator checks | `campaign-monitor enrollment +list`, `assignment +list`, `creator-check +get` / `+list --kind <kind>` |
| Activity tab | `campaign-monitor activity +list --id <id>` |

## Scope and windows

- `--scope approved` reads confirmed posts only; the default reads every counted post. Say which one each number uses, as in the breakdown flow.
- Dates are publication dates in `--timezone` (UTC when omitted).
- `video +list` lists what the Content tab shows: each approved creative once, standing for its confirmed posts, and posts not yet stood for. `+list-content` lists every post with its attribution (brief, persona, review bucket); use it to drill into one post's numbers.
- `video +list` and `format-post +list` page with `--page` / `--page-size` (and `--all`); the other lists page with `--cursor` from `next_cursor`.
