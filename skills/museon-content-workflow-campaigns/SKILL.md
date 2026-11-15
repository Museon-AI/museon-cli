---
name: museon-content-workflow-campaigns
description: "Run MuseOn Campaigns with Museon CLI. Use for both kinds of Campaign (UGC and content tracking): listing, creating, launching and setting them up, Dashboard figures and breakdowns, a tracking Campaign's creators and posts, UGC daily operations (recruiting, approvals, contracts, tasks, creator messages, content review, counting, client reports), analytics boards and organization members."
metadata:
  requires:
    bins: ["museoncli"]
    skills: ["museon-content-workflow-base"]
  cliHelp: "museoncli schema campaign"
---

# Campaigns

**CRITICAL — first read [`../museon-content-workflow-base/SKILL.md`](../museon-content-workflow-base/SKILL.md).**

Find the commands for a job with `museoncli guide --search <words>`; chapters 1 (UGC Campaign operations, in working order), 2 (tracking) and 3 (analytics) of `museoncli guide` cover this Skill. The references below explain the judgment behind them.

## Mental model

A Campaign is one thing with one id, whichever kind it is:

- **UGC Campaign**: creators apply, sign a contract, post against Formats (脚本, `brief` in commands) and are paid by payscales. Its creators and posts come through enrollments and review.
- **Content tracking Campaign**: no applications or review; you add the creators and posts it follows, and Museon syncs their performance.

`museoncli campaign` is the Campaign itself and its figures, for both kinds: `+list`, `+get`, `+create`, the lifecycle, `settings`, `staff`, `setup`, the Dashboard reads, and a tracking Campaign's `creator` / `content` membership. `museoncli ugc` is the work with a UGC Campaign's creators: recruiting, the roster, tasks, messages, review, payscales, client reports. Every command that addresses a Campaign takes its id as `--campaign-id`, from `museoncli campaign +list`.

Adding URLs to a tracking Campaign may start import or sync work: an import is accepted, not done, until a list read shows it. Removing a post from a Campaign changes the Campaign, not the platform post. Read [synced-store.md](references/synced-store.md).

## Shortcuts

| Situation | Start with |
| --- | --- |
| Find a Campaign (both kinds) | `museoncli campaign +list [--type ugc\|tracking] [--status active] [--search <name>]` |
| One Campaign's header and tracking record | `museoncli campaign +get --campaign-id <id>` |
| Know what a Campaign can be broken down by | `museoncli campaign +list-dimensions --campaign-id <id>` |
| Inspect its creators or posts | `museoncli campaign creator +list` / `campaign content +list --campaign-id <id>` |
| Review performance | `museoncli campaign +get-summary --campaign-id <id>` |
| Compare two periods | `museoncli campaign +get-period-performance --campaign-id <id>` |
| Read one creator's synced posts | `museoncli campaign post +list --creator-id <creator_social_account_id>` |

## Analysing a campaign

1. Run `campaign +list-dimensions` first. `campaign_type` decides the menu.
2. A `ugc` campaign breaks down by brief, persona and tag. A post's persona is its brief's persona. Only approved posts carry a brief or tag; a post awaiting review has none yet.
3. Pick the post scope from `post_scopes`: `--link-status linked` reads approved posts only, omitting it reads every counted post. Say which one every number uses.
4. A `tracking` campaign has no review step and no briefs: break it down by `--by creator-tag` or `--by source-video` (the video each post was made from) over all posts.
5. Run `campaign +get-breakdown --by <dimension>`. Rows come in three buckets: `value`, `unassigned` (approved, without one) and `awaiting_review`. Report the `unassigned` and `awaiting_review` share before any per-brief number; never fold one into the other.
6. Compare on `median_views` with the post count beside it; one viral post moves the sum and the average. Tags overlap, so per-tag rows do not add up to `totals`.
7. Drill into a row's posts with `campaign content +list --link-status linked` and the same window.

| Situation | Start with |
| --- | --- |
| What can this campaign be broken down by | `museoncli campaign +list-dimensions --campaign-id <id>` |
| Which brief performs best, approved posts | `museoncli campaign +get-breakdown --campaign-id <id> --by brief --link-status linked` |
| Persona or tag comparison | `museoncli campaign +get-breakdown --campaign-id <id> --by persona` |
| A tracking campaign by creator tag | `museoncli campaign +get-breakdown --campaign-id <id> --by creator-tag` |
| A tracking campaign by source video | `museoncli campaign +get-breakdown --campaign-id <id> --by source-video` |

## Daily reports and post drilldown

Pass the same `--timezone` to `+get-summary`, `content +list`, `+get-breakdown`
and `+get-period-performance`. Calendar dates are inclusive publication dates in
that timezone. A latest content counter and a period-end snapshot are different
cutoffs; do not mix them as daily growth.

`campaign content +list --brief-id <id>` and `--persona-id <id>` read approved attribution.
`--review-status approved|awaiting-review` drills into the review buckets.
Each UGC post carries `ugc_creator_id`, `enrollment_id`, `link_status`,
`creative_id`, `brief_id` and `persona_id`. Use `--ugc-creator-id` for a person;
`--creator-id` is the social account. Do not infer the person from handles or the
social account's unrelated `creator_info.creator_id`.

The summary's `daily_report.timezone` describes publication counts;
`observation_timezone` describes its observation bucket (UTC).
`observed_views_delta` sums recorded snapshot deltas over the authorized campaign
cohort, with `observed_views_content_count` / `observation_eligible_content_count`
showing coverage. It is not actual platform plays within a local calendar day.
The old-post leader uses that same observation bucket, among posts published
before the report's local day. Missing observations remain null.

## Reading what the Dashboard shows

The `campaign` resource commands (`video`, `roster`, `format`, `report`, `audience`, `settlement`, `payout`, `activity` and the rest) read the same figures as the web Campaign Dashboard, through the same routes, so the login sees exactly what it sees in the browser, in the organization it acts in. Everyone who can see a Campaign reads its figures; the Campaign's team (owner, admin, its operators, or a share's operator tier) also reads settlement, payouts, enrollments and creator checks; the owning organization's team alone reads assignments, the activity log, the period audience, organization analytics and payments. A refusal answers `not_found`: report that the login cannot see it, never retry under another identity. Read [dashboard.md](references/dashboard.md) for the command per tab.

## Reading the rest of the organization's work (`ugc`, `analytics`, `organization`)

Tasks, a Campaign's setup, creator conversations, the creator directory, client reports, analytics boards and the organization's members and billing each have read commands that call the web page's own route. Read [organization-reads.md](references/organization-reads.md) for the command per page and who may read it.

| Situation | Start with |
| --- | --- |
| What needs doing today | `museoncli ugc task-summary +get`, then `museoncli ugc task +list --queue <queue> --actor operator` |
| How a Campaign is configured (budget, pricing, approval, contract, staff, Discord, DM rules, targets) | `museoncli campaign setup +get --campaign-id <id>` |
| The conversation with one creator | `museoncli ugc message +list --enrollment-id <id>` |
| Analytics boards and their figures | `museoncli analytics board +list`, `analytics board +get-data --id <id>` |
| Who is in the organization, with which role | `museoncli organization member +list` |

## Editing UGC briefs and assignments (`ugc`)

The `ugc` domain writes the UGC workbench: briefs, brief assignments, and which brief a creative cites. Its `--campaign-id` is the same Campaign id `museoncli campaign +list` returns.

| Situation | Start with |
| --- | --- |
| Which briefs a campaign has | `museoncli ugc brief +list --campaign-id <id>` |
| How far each brief has got | `museoncli ugc brief +progress --campaign-id <id>` |
| Creatives that cite no brief | `museoncli ugc creative +list --campaign-id <id> --brief-id none` |
| Who can be assigned | `museoncli ugc enrollment +list --campaign-id <id> --status participating` |

The workbench never asks for confirmation, so the Agent does. Every write runs with `--dry-run` first. Its result reads the live state and changes nothing. Show the user what it returned (`changes`, `before`/`after`, who gets an assignment), ask them, and run it without `--dry-run` only after they say yes. Before `ugc brief +update`, also ask whether to `--notify` the `live_assignments` creators working on the brief. `+progress` returns raw counts: report them, and do not decide who owes a video.

To create a Campaign, move it through its lifecycle (launch, pause, complete, archive), change its setup (settings, team, targets, contract, payscales, Discord, Comment-to-DM), or manage the Format (脚本) library and UGC personas, read [ugc-campaign-setup.md](references/ugc-campaign-setup.md). Commands marked *yes* there also need `--yes` after the user confirms.

## Boards, client reports, broadcasts and reminders

| Situation | Start with |
| --- | --- |
| Build or change a multi-Campaign board | `museoncli analytics board +create` / `+update` / `+set-source` |
| Generate, review and send a client report | `museoncli ugc client-report +create` → `+approve` → `+send` |
| Change which reports run and when | `museoncli ugc client-report-config +update` |
| Message many creators on Discord | `museoncli ugc broadcast +audience`, then `+create`, `+send` |
| Team reminders, automatic creator nudges | `museoncli ugc reminder +update`, `museoncli ugc auto-nudge +update` |

Run every write with `--dry-run` first and show the user the result. Anything that sends (a report, a broadcast, a nudge setting) or cannot be undone also takes `--yes`: without it the command fails with `confirmation_required` and carries that preview as `preview`. Ask before adding `--yes`. Read [boards-reports-broadcasts.md](references/boards-reports-broadcasts.md).

## Running a UGC campaign day to day (`ugc`)

Tasks (claim, comment, due date, the task's own buttons), the roster (approve, reject, admit, pause, resume, remove, persona, payscale, trial), creator messages and nudges, content review and counting, recruitment links and invitations: read [ugc-operations.md](references/ugc-operations.md). Anything that reaches the creator or cannot be undone needs `--yes`; without it the command answers `confirmation_required` with a `preview`. Show the user that preview, ask, then rerun with `--yes`.

## Commands from Museon CLI 1.x

2.0 removed `campaign-monitor` and the Campaign commands of `ugc` (`ugc campaign`, `campaign-settings`, `campaign-staff`, `campaign-setup`). An old name answers `invalid_command` with `error.replacement`, the 2.0 command to run instead: read its `--help` (a Campaign is always `--campaign-id` now) and retry with it. `museoncli guide --search <old name>` finds the replacement too.

## DON'T

- **DON'T** treat synchronized history as a live platform fetch.
- **DON'T** treat removing a post from a Campaign as deleting the source account or post.
- **DON'T** report import acceptance as verified membership before list readback.
- **DON'T** add creators or posts to a UGC Campaign: they come through enrollments, and `campaign creator +add` / `content +add` refuse one.
- **DON'T** pass `--yes` to a send, broadcast or delete the user has not confirmed after seeing its preview.

## Relationships

Use `museon-research` for live public evidence, base social-account references for connected-account performance, and base artifact references for retained reports.
