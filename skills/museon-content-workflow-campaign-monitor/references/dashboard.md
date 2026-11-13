# Campaign Dashboard reads

Every command below takes `--id` as `campaign-monitor +list` returns it. The resource
commands (`campaign +get`, `video +list`, ...) work in any organization and Campaign the login can read;
the selected organization is only the default for `payment` reads. The flat commands (`+get-summary`,
`+get-period-performance`, `+list-content`, `+list-creators`) read only the selected
organization's campaigns: for another organization's campaign pass `--organization-id` with the
organization that owns it (from `museoncli org list`, `campaign +get` or `agency-campaign +list`).

## Everyone who can see the Campaign (members and shares included)

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
| The organization's Campaigns (its own and those shared in), delivery progress | `campaign-monitor agency-campaign +list [--with-progress]` |

## The Campaign's team: owner, admin, its operators, or a share's operator tier

A brand organization reads these on a Campaign shared into it at the operator tier exactly as
the web shows them; a `member` of the organization and a read-only share do not.

| Dashboard place | Command |
| --- | --- |
| Settlement tab | `campaign-monitor settlement +get --id <id> --date-from D --date-to D [--creator-id <ugc_creator_id>]` |
| Settled payouts | `campaign-monitor payout +list --id <id>` |
| Operations: enrollments, creator checks | `campaign-monitor enrollment +list`, `creator-check +get` / `+list --kind <kind>` |

## The owning organization's team only (a share does not open them, as on the web)

| Dashboard place | Command |
| --- | --- |
| Operations: brief assignments | `campaign-monitor assignment +list --id <id>` |
| Activity tab | `campaign-monitor activity +list --id <id>` |
| Audience map and profile over a period | `campaign-monitor audience +get --id <id> --by period --date-from D --date-to D` |
| Analytics over every UGC campaign (operating organization) | `campaign-monitor agency-analytics +get` |
| Creator payments (operating organization) | `campaign-monitor payment +list`, `campaign-monitor payment-summary +get` |

`agency-campaign`, `agency-analytics` and `payment` read the organization the command acts in
(`museoncli org select`, or `--organization-id`). A brand organization gets its own Campaigns
and those shared into it from `agency-campaign +list`; `agency-analytics` and `payment` answer
`not_found` outside the operating organization, as the web does.

## Scope and windows

- `--scope approved` reads confirmed posts only; the default reads every counted post. Say which one each number uses, as in the breakdown flow.
- Dates are publication dates in `--timezone` (UTC when omitted).
- `video +list` lists what the Content tab shows: each approved creative once, standing for its confirmed posts, and posts not yet stood for. `+list-content` lists every post with its attribution (brief, persona, review bucket); use it to drill into one post's numbers.
- `video +list` and `format-post +list` page with `--page` / `--page-size` (and `--all`); the other lists page with `--cursor` from `next_cursor`.
