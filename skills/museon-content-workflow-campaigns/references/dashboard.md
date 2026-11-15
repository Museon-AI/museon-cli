# Campaign Dashboard reads

Every command below takes the Campaign as `--campaign-id`, the id `campaign +list` returns, for
either kind. The resource commands (`video +list`, `roster +list`, ...) work in any organization
and Campaign the login can read; the selected organization is only the default for the
organization-wide reads (`campaign +list`, `analytics`, `payment`). The flat figures
(`+get-summary`, `+get-period-performance`) and `creator +list` / `content +list` read only the
selected organization's Campaigns: for another organization's Campaign pass `--organization-id`
with the organization that owns it (from `museoncli org list` or `campaign +get`).

## Everyone who can see the Campaign (members and shares included)

| Dashboard place | Command |
| --- | --- |
| Header: type, status, start date; tracking record | `campaign +get --campaign-id <id>` |
| KPI tiles and trend | `campaign +get-summary --campaign-id <id>` |
| Analytics: current vs previous period | `campaign +get-period-performance --campaign-id <id>` |
| Analytics: cumulative views, content tiers, creator countries | `campaign report +get --campaign-id <id> --widget <widget> --date-from D --date-to D` |
| Content tab, UGC (videos, review status) | `campaign video +list --campaign-id <id> [--status confirmation\|review\|not-counted]` |
| One video: detail, summary, daily, insights | `campaign video +get --campaign-id <id> --content-id <content_id> --section <section>` |
| Content tab, tracking (posts) | `campaign content +list --campaign-id <id>` |
| Creators tab, UGC (By Creator) | `campaign roster +list --campaign-id <id>` |
| Creators tab, by account | `campaign creator +list --campaign-id <id>` |
| Creator tags | `campaign creator-tag +list --campaign-id <id>` |
| Performance by Format | `campaign format +list --campaign-id <id>`, then `format-post +list --brief-id <brief_id>` |
| Daily audience (trend tooltip) | `campaign audience +get --campaign-id <id> --date-from D --date-to D` |
| The organization's Campaigns (its own and those shared in), delivery progress | `campaign +list [--with-progress]` |

## The Campaign's team: owner, admin, its operators, or a share's operator tier

A brand organization reads these on a Campaign shared into it at the operator tier exactly as
the web shows them; a `member` of the organization and a read-only share do not.

| Dashboard place | Command |
| --- | --- |
| Settlement tab | `campaign settlement +get --campaign-id <id> --date-from D --date-to D [--creator-id <ugc_creator_id>]` |
| Settled payouts | `campaign payout +list --campaign-id <id>` |
| Operations: enrollments, creator checks | `ugc enrollment +list --campaign-id <id> --detail`, `ugc creator-check +get` / `+list --kind <kind>` |

## The owning organization's team only (a share does not open them, as on the web)

| Dashboard place | Command |
| --- | --- |
| Operations: brief assignments | `ugc assignment +list --campaign-id <id>` |
| Activity tab | `campaign activity +list --campaign-id <id>` |
| Audience map and profile over a period | `campaign audience +get --campaign-id <id> --by period --date-from D --date-to D` |
| Analytics over every UGC campaign (operating organization) | `campaign analytics +get` |
| Creator payments (operating organization) | `campaign payment +list`, `campaign payment-summary +get` |

`campaign +list`, `analytics` and `payment` read the organization the command acts in
(`museoncli org select`, or `--organization-id`). A brand organization gets its own Campaigns
and those shared into it from `campaign +list`; `analytics` and `payment` answer `not_found`
outside the operating organization, as the web does.

## Scope and windows

- `--scope approved` reads confirmed posts only; the default reads every counted post. Say which one each number uses, as in the breakdown flow.
- Dates are publication dates in `--timezone` (UTC when omitted).
- `video +list` lists what the Content tab shows: each approved creative once, standing for its confirmed posts, and posts not yet stood for. `content +list` lists every post with its attribution (brief, persona, review bucket); use it to drill into one post's numbers.
- `video +list` and `format-post +list` page with `--page` / `--page-size` (and `--all`); the other lists page with `--cursor` from `next_cursor`.
