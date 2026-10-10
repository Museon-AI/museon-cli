---
name: museon-content-workflow-ai-slideshow
description: "Manage reusable slideshow assets, create explicit-asset slideshows, and publish completed slideshow generations to a selected social account with Museon CLI."
metadata:
  requires:
    bins: ["museoncli"]
    skills: ["museon-content-workflow-base"]
  cliHelp: "museoncli schema ai-slideshow"
---

# AI slideshow

**CRITICAL — first read [`../museon-content-workflow-base/SKILL.md`](../museon-content-workflow-base/SKILL.md).**

## Mental model

Use `asset` to manage reusable inputs and `generation` to create or inspect a slideshow from explicit format, topic, persona, and optional product assets. Generation is independent of accounts and schedules. Use `publish` only after a generation is `done` and its result media is present; the publish target account and timing belong to that stage.

Read [slideshow-lifecycle.md](references/slideshow-lifecycle.md) for the supported lifecycle, write/readback rules, and publishing completion facts.

## Persistent Museon managed publishing

When the operator wants daily image posts to continue after Codex closes, use
`museoncli schema agentic-campaign`. This is Museon, separate from HireAICreator.
The server performs recurring generation, publishing and metrics collection.
Do not schedule a local Codex loop or use the manual generation path for this intent.

1. Resolve workspace, existing Campaign/Plan, persona and the explicit account
   roster. Do not enroll every account that happens to reference the persona.
2. Analyze each supplied link/image page by page. Preserve its topic, facts,
   order and page count; mark unreadable text instead of inventing it. Create or
   reuse the existing Format and Topic assets, keeping source provenance.
3. Keep each reference as an explicit `{format_id, topic_id}` pair. Twenty
   references mean twenty reviewed pairs, never a Cartesian product. Read back
   resource IDs before retrying imports; do not blindly recreate successful assets.
4. Create a Campaign only when the selected scope needs one. New CLI campaigns
   require manual strategy review and disable automatic recruitment. Existing
   campaigns must have that policy before `plan +supply-update`; changing it with
   `+campaign-review-only` affects the whole Campaign, so do not silently change
   other Plans' operating policy.
5. Create a draft with `+plan-create --persona-id ...`. Use `plan +supply-update`
   with the complete desired paired supply and its latest Plan version. Keep
   existing pairs when adding references. Read the returned proposal and inspect
   generated previews. Saving supply does not mean publishing has started.
6. Run `+schedule-rollout-preflight` before `+confirm-schedule-rollout`, with a
   caller-owned idempotency key for confirmation. A new Plan with no accounts may
   have zero slots: confirm its reviewed reference supply first; never describe
   that receipt as an active publishing schedule.
7. Use `plan +members-reconcile` to admit only the specified accounts after the
   reference version is confirmed. This applies their finalized supply and tops
   up the existing seven-day window. Inspect the calendar and `+plan-get` before
   `plan +account-control --action enable` for each selected account, using its
   returned version. Current cadence is one post per account per local day,
   starting with the next local day; do not promise arbitrary daily frequency.
8. Return the Plan ID, `web_url`, exact accounts, reference count, schedule,
   timezone and execution state. Use `plan +posts` and the account/calendar views
   for readback. Generation done, channel acceptance, public post and metrics
   availability are different facts. Missing metrics are not zero results.

Maintenance uses the same Plan and resource IDs. Retire references through a
reviewed supply update; do not erase their history. Reconcile the full desired
account list to add/remove members. Pause/resume/stop selected accounts through
`plan +account-control`; resume skips expired slots, and stop releases ownership.
Submitted external posts continue reconciliation and cannot be promised withdrawn.
For another persona, prepare a new Plan, release the explicitly selected old
members, then admit them to the new Plan; preserve the old Plan's history and
stop on a handover conflict. Never overwrite the old Plan's persona identity.

## Shortcuts

| Situation | Start with |
| --- | --- |
| Find or maintain inputs | `museoncli ai-slideshow asset +list` |
| Generate from explicit assets | `museoncli ai-slideshow generation +create` |
| Inspect or change account asset pools | `museoncli ai-slideshow publish +bulk-preview-asset-pools` |
| Preview or apply schedule plans | `museoncli ai-slideshow publish +preview-schedule-plan` |
| Inspect account publish configuration | `museoncli ai-slideshow publish +get-config` |

## DON'T

- **DON'T** bind generation to an account or schedule.
- **DON'T** treat generation creation or a batch job receipt as terminal success.
- **DON'T** add evaluator or CTA inputs, or bind generation itself to an account or schedule.

## Relationships

Use `museon-content-workflow-base` for media, account, artifact, and routine command details. Use `museon-content-workflow-hireaicreator` only for HireAICreator plans and videos; its generation facts are separate.
