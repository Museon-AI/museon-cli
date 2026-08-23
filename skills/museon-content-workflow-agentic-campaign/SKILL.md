---
name: museon-content-workflow-agentic-campaign
description: "Operate Museon Agentic Creative Campaigns from Persona Plans through member accounts and runs, including proposals, rollouts, issues, and fleet health."
metadata:
  requires:
    bins: ["museoncli"]
    skills: ["museon-content-workflow-base"]
  cliHelp: "museoncli schema agentic-campaign"
---

# Museon Agentic Creative Campaign workflow

**CRITICAL — first read [`../museon-content-workflow-base/SKILL.md`](../museon-content-workflow-base/SKILL.md).**

## Mental model

Campaign → Persona Plan → member account operation → daily runs. A Persona Plan owns one Persona
and shared creative direction; account-operation submits pool accounts into that active Plan and
is the managed execution layer, not a parallel top-level workflow. Proposals evolve plans;
confirmed rollouts bind changes to schedules. See [campaign-lifecycle.md](references/campaign-lifecycle.md),
[member-account-operations.md](references/member-account-operations.md), and
[fulfillment-issue-recovery.md](references/fulfillment-issue-recovery.md).

## Shortcuts

| Situation | Start with |
| --- | --- |
| Choose campaign needing attention | `museoncli agentic-campaign +overview` |
| Inspect one campaign context | `museoncli agentic-campaign +recap` |
| Inspect Persona Plans | `museoncli agentic-campaign +plan-list` |
| Propose plan evolution | `museoncli agentic-campaign proposal +create` |
| Preview proposal rollout | `museoncli agentic-campaign +schedule-rollout-preflight` |
| Enroll member accounts | `museoncli account-operation +submit-batch` |
| Read whole-fleet health | `museoncli account-operation +ops-status` |
| Check exact account membership | `museoncli account-operation +ops-status-accounts` |
| Read one-day publish roster | `museoncli account-operation +daily-roster` |
| Resolve one account's exact managed state | `museoncli account-operation +resolve` |
| Recover daily-fulfillment Issues | `museoncli agentic-campaign +issues-pull` |

## DON'T

- **DON'T** submit an account without a valid active Persona Plan with a Persona.
- **DON'T** use per-account Persona/Product overrides inside one batch; split by Plan/context.
- **DON'T** cancel live schedules to enroll an account; transfer/adoption handles them.
- **DON'T** infer unmanaged status from absence on one paginated operation-list page.
- **DON'T** confuse `operation_id` with `pool_account_id`.
- **DON'T** treat normal draining backlog as an incident or sample a few runs as fleet health.
- **DON'T** assume replacement enrollment retires originals; stopping is a separate terminal action.
- **DON'T** resend a conflicted proposal unchanged; revise or withdraw the named blocker.
- **DON'T** confirm a rollout without a matching current preflight.
- **DON'T** pull a second Issue batch in one pass, or let a claimed Issue expire unreported.

## Relationships

Account-publish hands an allocation into fully-managed operation; assets supply Persona/Product/
Format/Topic; campaign-monitor stores monitored external history; evaluator is separate from
campaign learning and decision memory.
