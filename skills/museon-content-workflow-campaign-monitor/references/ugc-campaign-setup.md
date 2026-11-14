# Setting up and running a Campaign (`ugc`)

These commands write what the web's new-Campaign page, Campaign header, Campaign setup page and
/formats page write, through the same routes. `--campaign-id` / campaign `--id` is the UGC
campaign id (`ugc campaign +list`, or `data.campaign.id` of `+create`), not a campaign-monitor
collection id. The server decides who may write; each command's summary names the role.

**Every write: `--dry-run` first, show the user what it returned, ask, then run it for real.**
The dry run reads the live state and writes nothing. Commands marked *yes* also need `--yes`
(they reach people outside, end something or delete something). Pass back the token the dry run
returned (`--expected-status`, `--expected-updated-at`, `--expected-version`) so the write fails
with `conflict` instead of overwriting a change made in between; on `conflict`, read again.

## Create and move through the lifecycle

| Do | Command |
| --- | --- |
| Create a draft (UGC: operating team's organization only) | `ugc campaign +create --name N [--type ugc\|tracking] [--product-id P]` |
| Launch a draft (*yes*; dry run shows `launchability.reasons`) | `ugc campaign +launch --id C` |
| Pause / resume | `ugc campaign +pause --id C`, `+resume` |
| End it for good (*yes*) | `ugc campaign +complete --id C` |
| Put a draft or completed one away (*yes*) / bring it back | `ugc campaign +archive --id C`, `+restore` (`--campaign-id` works as well as `--id`; a restore dry run reports `after: "draft or complete"`, the status it was archived from) |
| Rename | `ugc campaign +rename --id C --name N` |

Statuses: draft → active ⇄ paused → complete → archived; a draft can also be archived;
restore returns to the status it was archived from.

```bash
museoncli ugc campaign +create --name "Spring launch" --type ugc --dry-run
museoncli ugc campaign +launch --id C --dry-run          # check launchability.ok
museoncli ugc campaign +launch --id C --expected-status draft --yes
```

## Setup

| Setup step | Command |
| --- | --- |
| Approval/join mode, budget cap, post grouping, platforms, Discord onboarding | `ugc campaign-settings +update --campaign-id C [--approval-mode auto\|manual] [--join-mode open\|invite-only] [--budget-cap-cents N\|none] ...` |
| Languages, countries, stay/warmup/trial rules, content intake, apply form | `... +update --settings-json '{"stay_rules": {"inactivity_days": 7}}'` (nested rules change only the keys given) |
| Pay by number of platforms | `... +update --platform-pay-rules-json '{"single_bps":10000,"rules":[{"count":2,"multiplier_bps":12000}]}'` |
| PMs and OPs | `ugc campaign-staff +set --campaign-id C --manager-user-id U --operator-user-id U` |
| Delivery targets | `ugc delivery-target +create/+update/+delete --campaign-id C [--target-views N] [--target-posts N] [--target-creators N] [--start-date D] [--due-date D]` (*yes* on delete). A target's dates are its own window; they never move the Campaign's start day, which is set separately |
| Contract | `ugc contract-template +set --campaign-id C --source default\|custom [--body-file F] [--terms-json ...]` (dry run returns the filled preview) |
| Payscales and rates | `ugc payscale +create/+update/+delete`, `ugc pay-rate +create/+update/+delete` (dry run of a rate prices a video under it and refuses a rate the server would 422: a `video-content` rate needs a `description` (the sentence a post is judged against), `lifetime-views` needs `min_creator_views`, `base_fee_cents` goes with `base_rate_mode: per_video`; *yes* on delete) |
| Discord server | `ugc discord-server +initialize --guild-id G` (*yes*; builds channels and roles), `+set` (existing layout), `+remove` (*yes*) |
| Comment-to-DM | `ugc dm-rule +create` / `+update` (*yes*: an active rule DMs commenters) |

`campaign-settings +update` writes the whole settings object back with only your fields changed,
the way the page saves; brand editors may not change the team's settings (approval, join, rules,
budget cap, Discord onboarding).

## Formats (脚本 = `brief`) and personas

The UGC Format is `brief` in commands; `ai-slideshow asset format/persona` are slideshow assets,
not these.

| Do | Command |
| --- | --- |
| Browse the organization library | `ugc brief-library +list [--search S] [--status archived]`, `+get --id B` |
| New library Format / edit (new version) / duplicate | `ugc brief-library +create`, `+update --id B --expected-version V`, `+copy --id B` |
| Archive a library Format (*yes*; no restore exists) | `ugc brief-library +archive --id B --expected-version V` |
| Write a Format inside a Campaign | `ugc brief +create --campaign-id C --title T --content-file F [--persona-id P]` |
| Use / stop using a library Format in a Campaign | `ugc brief +link --campaign-id C --id B [--replaces B0]`, `+unlink` (*yes*) |
| Copy a Format into a Campaign for another persona | `ugc brief +copy --campaign-id C --id B --persona-id P [--keep-source]` |
| Personas | `ugc persona +list`, `+create --title T`, `+update --id P`, `+delete --id P` (*yes*) |

Creates return an `idempotency_key`; if a create's outcome is unknown, rerun it with
`--idempotency-key <key>` instead of creating twice. Editing a library Format reaches every
Campaign in `linked_campaign_ids`: tell the user before they confirm.
