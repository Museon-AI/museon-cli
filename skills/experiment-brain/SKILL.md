---
name: experiment-brain
description: "Design and revise evidence-driven social persona experiments for Museon Agentic Campaigns. Use when Mel needs to propose persona directions, format-topic-CTA combinations, interpret experiment holdings, or communicate experiment recommendations to an operator."
---

# Experiment Brain

Use this Skill to produce experiment proposals for Agentic Campaign Persona
Plans. Mel proposes; the operator decides and applies.

## 1. Core model

- **Persona is the supreme creative authority — it outranks every other
  content rule in this skill.** Operator-submitted formats and topics
  frequently contradict the plan persona (casing, tone, styling, content
  boundaries — e.g. a persona mandating uppercase in specific contexts while a
  format demands all-lowercase copy). Before any proposal draft, revision, or
  generation, audit the involved formats and topics against the persona; on
  conflict the persona wins: fix the asset itself — proposal-dedicated assets
  in place, shared assets as a corrected variant with the element rebound to
  it. Never generate content that violates the persona, and never split the
  difference.
- Treat platform distribution as a feedback system: early audience response
  changes later reach, so judge a direction from repeated observations rather
  than one post.
- Require enough comparable observations before claiming a meaningful
  difference. Separate signal from ordinary variance; do not call a Winner
  from a lucky outlier.
- Expect platforms to reduce distribution for repetitive, homogeneous supply.
  Preserve a recognizable persona while varying creative execution.
- Keep policy, brand-safety, and account-risk checks as hard fallback
  constraints. Performance never overrides them.
- Treat cold start as a supply problem: begin with several coherent directions
  so the system can learn, then narrow the portfolio from evidence.

## 2. Experiment method

1. Start from current feedback and state what evidence supports each proposal.
2. Do not make an unrepeatable news spike or transient trend a priority
   direction. It may be used tactically, but it is not stable experiment
   memory.
3. Optimize for repeatable combinations of persona content direction and CTA,
   not for one viral post.
4. Compare like with like, record uncertainty, and ask for another round when
   evidence is weak or confounded.
5. Put additional budget behind the directions most worth repeating: stable
   response, clear attribution, sufficient supply, and acceptable risk.
6. Preserve alternatives until the evidence supports stopping them; avoid
   letting an early Winner consume all learning budget.

## 3. Platform differences

Build a separate hypothesis for each platform. Account for its audience,
content grammar, interaction signals, moderation risks, creative shelf life,
and distribution cadence. Evidence from one platform may inspire a proposal
for another, but never copy the strategy or declare it validated across
platforms without a new test.

## 4. Content layers and experiment elements

Reason from stable identity to concrete execution:

`persona -> format -> topic -> content -> CTA`

- **Persona** defines the recognizable voice, worldview, visual identity, and
  audience promise.
- **Format** defines the repeatable presentation structure.
- **Topic** defines what the content discusses.
- **Content** is the individual produced post. It is an observation, not an
  experiment element.
- **CTA** defines the intended next action and target.

An experiment element is exactly one `format × topic × CTA` combination. The
Persona Plan owns the shared element vocabulary. Compare and manage elements
as combinations; do not attribute a result to one dimension when the observed
content changed several dimensions at once.

## 5. Mechanism operating guide

Read holdings as the operator-facing experiment state:

| Holding | Meaning | Mel action |
| --- | --- | --- |
| `待测` | Proposed and not yet receiving test supply | Explain the hypothesis and required test |
| `测试中` | Receiving supply and gathering evidence | Monitor comparable feedback; avoid premature judgment |
| `Winner` | Worth repeating and eligible for more budget | Recommend `Winner加推` with evidence |
| `已停投` | No longer receiving new test budget | Preserve the learning and explain why it stopped |

## 6. Proposals — the only way you change a plan

Mel always proposes; the operator reviews the visuals and confirms on the
review page. Never select, merge, finalize, enable, boost, or stop a direction
on the operator's behalf.

### Action 1: create a complete proposal during preparation

Submit complete `人设方案` alternatives while the plan is in preparation. A
failed proposal must not block another, so multiple coherent alternatives may
coexist. A new proposal requires `--name`, `--elements-json`, and exactly one
of `--persona-json` or `--persona-id`.

To revise an existing open proposal as its next `第N稿`, use `--proposal-id`
with the complete replacement `--elements-json` and, only when changing its
persona, either `--persona-json` or `--persona-id`:

```bash
museoncli agentic-campaign +plan-propose \
  --plan-id 33333333-3333-4333-8333-333333333333 \
  --proposal-id 77777777-7777-4777-8777-777777777777 \
  --persona-json '{"name":"Mia","description":"Practical maker","visual_prompt":"Bright workshop portrait","reference_media_ids":[]}' \
  --elements-json '[{"format_id":"44444444-4444-4444-8444-444444444444","topic_id":"55555555-5555-4555-8555-555555555555","cta_target_id":"66666666-6666-4666-8666-666666666666"}]' \
  --note "Tighten the visual direction"
```

Omit `--proposal-id` to create a new proposal, and include its required
`--name`. When revising with `--proposal-id`, omitting both persona options
preserves that proposal's current persona; it does not clear the persona.

When the persona already exists as a workspace persona asset, pass
`--persona-id <id>` instead of `--persona-json` (mutually exclusive). The
server snapshots the asset's name, description, and look-reference media at
submit time — a copy, not a live link; tags and marketing profile do not
carry over.

### Action 2: adjust a running plan from evidence

Use the experiment scoreboard before proposing an operating-plan adjustment,
and use `--note` to state the evidence:

- Add a new direction when the current holdings leave a meaningful hypothesis
  untested. Define it as one format × topic × optional CTA combination.
- Retire a direction only after enough comparable observations and consistently
  weak performance across repeated posts. Never stop a direction because of
  one poor result or an undersized sample.
- Boost only a `Winner` supported by sufficient, repeatable evidence. State the
  proposed allocation explicitly as `account count × days` so the operator can
  judge the added commitment.

Require enough comparable observations before retiring a direction; never stop
one because of a single poor result or an undersized sample. Boost only a
`Winner` with sufficient, repeatable evidence. Create one adjustment proposal
containing any combination of additions, retirements, and Winner boosts. Always
set `--title` to a short name the operator can recognize at a glance in the
proposal list (for example `「暗黑向第二批开测」`) — without it every proposal
renders with the generic label and the operator cannot tell them apart:

```bash
museoncli agentic-campaign +plan-propose \
  --plan-id 33333333-3333-4333-8333-333333333333 \
  --title "暗黑向第二批开测" \
  --add-elements-json '[{"format_id":"44444444-4444-4444-8444-444444444444","topic_id":"55555555-5555-4555-8555-555555555555","cta_target_id":"66666666-6666-4666-8666-666666666666"}]' \
  --retire-element-ids 77777777-7777-4777-8777-777777777777 \
  --boost-elements-json '[{"element_id":"88888888-8888-4888-8888-888888888888","account_count":3,"days":7}]' \
  --note "Add one distinct direction, stop the repeatedly weak direction, and boost the Winner across 3 accounts for 7 days"
```

The command creates an `调整记录` for review; it never confirms it. Tell the
operator what will be added, stopped, and boosted, then direct them to review
the visuals and confirm on the page.

### Action 3: revise an open proposal

When a revision task arrives, read the latest unresolved operator feedback
before changing the proposal:

```bash
museoncli agentic-campaign +proposal-get \
  --plan-id 33333333-3333-4333-8333-333333333333 \
  --proposal-id 77777777-7777-4777-8777-777777777777
```

To read the operator's page annotations on a proposal at any time, call
`+proposal-get`: its `annotations` section lists each round's compiled
feedback text and resolution state. Annotations live on the proposal — never
look for them on persona or asset fields.

Apply the compiled `feedback_summary` consistently across the proposed supply
assets. Only dedicated assets created for this proposal may be modified in
place. If feedback applies to a shared asset, copy it into a new variant and
point the revised element list to that new variant; never mutate the shared
asset.

**Persona is a plan-shared asset — never edit it directly.** `asset +update`
against a plan-held persona is rejected by the server (409) no matter who
asks: operator-instructed rewrites, "replace with persona X" requests, and
annotation feedback all go through the same draft flow. Whenever ANY change
to a plan's persona identity or appearance (name, description, visual
reference) is needed, first call `+proposal-persona-draft` to create or reuse
this proposal's own draft persona:

```bash
museoncli agentic-campaign +proposal-persona-draft \
  --plan-id 33333333-3333-4333-8333-333333333333 \
  --proposal-id 77777777-7777-4777-8777-777777777777
```

When the operator names an existing persona to source from (for example
"replace with persona X"), pass `--from-persona-id <id>` to seed the draft
directly instead of hand-copying fields: it copies the source persona's
description and look references into the draft — a copy, not a live link —
and re-running with this flag overwrites the draft's current content.

Edit only the returned draft persona, then regenerate this proposal's
previews. It is idempotent across a proposal: calling it again returns the
same draft instead of creating a duplicate.

**Verify before retiring or shrinking a direction.** Before proposing to
retire or reduce an element, confirm its current state and performance with a
tool call and cite the evidence in `--note`: the asset id and the exact
queried text or numbers it came from. Never retire, shrink, or otherwise touch
an element the operator did not name.

**Summarize as a diff against the previous draft.** When reporting a revision
back to the operator, list what this `第N稿` adds and removes compared with
the previous `第N稿` — the delta, not just the new state.

Submit the complete replacement element list as the next `第N稿`:

```bash
museoncli agentic-campaign +plan-propose \
  --plan-id 33333333-3333-4333-8333-333333333333 \
  --proposal-id 77777777-7777-4777-8777-777777777777 \
  --elements-json '[{"format_id":"44444444-4444-4444-8444-444444444444","topic_id":"55555555-5555-4555-8555-555555555555","cta_target_id":"66666666-6666-4666-8666-666666666666"}]' \
  --note "Applied the latest compiled review feedback across the replacement supply"
```

This form intentionally omits persona options, so the proposal keeps its
current persona. Add exactly one of `--persona-json` or `--persona-id` only
when the next `第N稿` replaces that persona.

The operator may continue annotating or confirm from the review desk. Never
pressure or prompt the operator to confirm.

When speaking to operators, use only this interface vocabulary:
`人设方案`, `第N稿`, `调整记录`, `定稿启用`, `新方向开测`, `Winner加推`,
`停投`, and `内容组成`. Do not expose engineering terms such as candidate,
branch, commit, head, merge, payload, element row, or version table.

## 7. Campaign creation and archiving

Creating and archiving a campaign are workspace-level actions with lasting
consequences. Never take either unprompted.

- **Before creating**, state the full intent to the operator and get their
  confirmation: project name, total account budget, planned persona (plan)
  count, and each plan's name and budget. Only call `+campaign-create` (and
  `+plan-create` for each plan) after the operator confirms.
- **After creating**, report the project link back to the operator so they
  can open it directly.
- **Before archiving**, get the operator's explicit confirmation.
  `+campaign-archive` cascades to stop account operations for every member of
  every plan in the campaign; make sure the operator understands this before
  they confirm.
