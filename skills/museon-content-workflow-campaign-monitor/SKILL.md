---
name: museon-content-workflow-campaign-monitor
description: "Track campaign collections, creators, content, synced posts, and local performance history with Museon CLI; edit UGC briefs, brief assignments and creative brief links."
metadata:
  requires:
    bins: ["museoncli"]
    skills: ["museon-content-workflow-base"]
  cliHelp: "museoncli schema campaign-monitor"
---

# Campaign monitor

**CRITICAL — first read [`../museon-content-workflow-base/SKILL.md`](../museon-content-workflow-base/SKILL.md).**

## Mental model

A campaign monitor stores tracked creators and content with synchronized post and performance history. Adding URLs may start import or sync work. Removing a monitor record changes the collection, not the source platform object. Read [monitor-store.md](references/monitor-store.md).

## Shortcuts

| Situation | Start with |
| --- | --- |
| Find a collection | `museoncli campaign-monitor +list` |
| Know what a campaign can be broken down by | `museoncli campaign-monitor +list-dimensions` |
| Inspect creators or content | `museoncli campaign-monitor +list-creators` |
| Review performance | `museoncli campaign-monitor +get-summary` |
| Compare two periods | `museoncli campaign-monitor +get-period-performance` |
| Read synced posts | `museoncli campaign-monitor +list-posts` |

## Analysing a campaign

1. Run `+list-dimensions` first. `campaign_type` decides the menu.
2. A `ugc` campaign breaks down by brief, persona and tag. A post's persona is its brief's persona. Only approved posts carry a brief or tag; a post awaiting review has none yet.
3. Pick the post scope from `post_scopes`: `--link-status linked` reads approved posts only, omitting it reads every counted post. Say which one every number uses.
4. A `tracking` campaign has no review step and no briefs: break it down by `--by creator-tag` over all posts.
5. Run `+get-breakdown --by <dimension>`. Rows come in three buckets: `value`, `unassigned` (approved, without one) and `awaiting_review`. Report the `unassigned` and `awaiting_review` share before any per-brief number; never fold one into the other.
6. Compare on `median_views` with the post count beside it; one viral post moves the sum and the average. Tags overlap, so per-tag rows do not add up to `totals`.
7. Drill into a row's posts with `+list-content --link-status linked` and the same window.

| Situation | Start with |
| --- | --- |
| What can this campaign be broken down by | `museoncli campaign-monitor +list-dimensions --id <campaign_id>` |
| Which brief performs best, approved posts | `museoncli campaign-monitor +get-breakdown --id <campaign_id> --by brief --link-status linked` |
| Persona or tag comparison | `museoncli campaign-monitor +get-breakdown --id <campaign_id> --by persona` |
| A tracking campaign by creator tag | `museoncli campaign-monitor +get-breakdown --id <campaign_id> --by creator-tag` |

## Daily reports and post drilldown

Pass the same `--timezone` to `+get-summary`, `+list-content`, `+get-breakdown`
and `+get-period-performance`. Calendar dates are inclusive publication dates in
that timezone. A latest content counter and a period-end snapshot are different
cutoffs; do not mix them as daily growth.

`+list-content --brief-id <id>` and `--persona-id <id>` read approved attribution.
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

The resource commands (`campaign`, `video`, `roster`, `format`, `report`, `audience`, `settlement`, `enrollment`, `agency-campaign` and the rest) read the same figures as the web Campaign Dashboard, through the same routes, so the login sees exactly what it sees in the browser. A Brand member reads the Brand View; the Agency team also reads settlement, operations, activity and audience. A refusal answers `not_found` (or `forbidden` for Agency-wide reads): report that the login cannot see it, never retry under another identity. Read [dashboard.md](references/dashboard.md) for the command per tab.

## Editing UGC briefs and assignments (`ugc`)

The `ugc` domain writes the UGC workbench: briefs, brief assignments, and which brief a creative cites. Its `--campaign-id` is the UGC campaign id from `museoncli ugc campaign +list`, not a campaign-monitor collection id.

| Situation | Start with |
| --- | --- |
| Which briefs a campaign has | `museoncli ugc brief +list --campaign-id <id>` |
| How far each brief has got | `museoncli ugc brief +progress --campaign-id <id>` |
| Creatives that cite no brief | `museoncli ugc creative +list --campaign-id <id> --brief-id none` |
| Who can be assigned | `museoncli ugc enrollment +list --campaign-id <id> --status participating` |

The workbench never asks for confirmation, so the Agent does. Every write runs with `--dry-run` first. Its result reads the live state and changes nothing. Show the user what it returned (`changes`, `before`/`after`, who gets an assignment), ask them, and run it without `--dry-run` only after they say yes. Before `ugc brief +update`, also ask whether to `--notify` the `live_assignments` creators working on the brief. `+progress` returns raw counts: report them, and do not decide who owes a video.

## DON'T

- **DON'T** treat synchronized history as a live platform fetch.
- **DON'T** treat removing a monitor record as deleting the source account or post.
- **DON'T** report import acceptance as verified membership before list readback.

## Relationships

Use `museon-research` for live public evidence, base social-account references for connected-account performance, and base artifact references for retained reports.
