---
name: experiment-brain
description: "Design and revise evidence-driven social persona experiments for Museon Agentic Campaigns. Use when Mel needs to propose persona directions, format-topic-CTA combinations, interpret experiment holdings, or communicate experiment recommendations to an operator."
---

# Experiment Brain

Use this Skill to produce experiment proposals for Agentic Campaign Persona
Plans. Mel proposes; the operator decides and applies.

## 1. Core model

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

Submit one new `人设方案` at a time. A failed proposal must not block another:

```bash
museoncli agentic-campaign +candidate-submit \
  --plan-id 33333333-3333-4333-8333-333333333333 \
  --name "DIY problem solver" \
  --persona-payload-json '{"name":"Mia","description":"Practical maker","visual_prompt":"Warm workshop portrait","reference_media_ids":[]}' \
  --elements-json '[{"format_id":"44444444-4444-4444-8444-444444444444","topic_id":"55555555-5555-4555-8555-555555555555","cta_target_id":"66666666-6666-4666-8666-666666666666"}]'
```

Submit a new `第N稿` for an existing proposal. The server automatically uses
its current head as the parent:

```bash
museoncli agentic-campaign +candidate-revise \
  --plan-id 33333333-3333-4333-8333-333333333333 \
  --candidate-id 77777777-7777-4777-8777-777777777777 \
  --persona-payload-json '{"name":"Mia","description":"Practical maker","visual_prompt":"Bright workshop portrait","reference_media_ids":[]}' \
  --elements-json '[{"format_id":"44444444-4444-4444-8444-444444444444","topic_id":"55555555-5555-4555-8555-555555555555"}]' \
  --note "Tighten the visual direction"
```

## 6. Adjustment proposals

Use the experiment scoreboard before proposing a live-plan adjustment:

- Add a new direction when the current holdings leave a meaningful hypothesis
  untested. Define it as one format × topic × optional CTA combination.
- Retire a direction only after enough comparable observations and consistently
  weak performance across repeated posts. Never stop a direction because of
  one poor result or an undersized sample.
- Boost only a `Winner` supported by sufficient, repeatable evidence. State the
  proposed allocation explicitly as `account count × days` so the operator can
  judge the added commitment.

Create one adjustment proposal containing any combination of additions,
retirements, and Winner boosts:

```bash
museoncli agentic-campaign +plan-revise \
  --plan-id 33333333-3333-4333-8333-333333333333 \
  --add-elements-json '[{"format_id":"44444444-4444-4444-8444-444444444444","topic_id":"55555555-5555-4555-8555-555555555555","cta_target_id":"66666666-6666-4666-8666-666666666666"}]' \
  --retire-element-ids 77777777-7777-4777-8777-777777777777 \
  --boost-elements-json '[{"element_id":"88888888-8888-4888-8888-888888888888","account_count":3,"days":7}]' \
  --note "Add one distinct direction, stop the repeatedly weak direction, and boost the Winner across 3 accounts for 7 days"
```

The command creates an `调整记录` for review; it never confirms it. Tell the
operator what will be added, stopped, and boosted, then direct them to review
the visuals and confirm on the page.

Mel always produces proposals only. Applying a proposal requires the operator
to review its visuals and confirm it on the page. Never select, merge, finalize,
enable, boost, or stop a direction on the operator's behalf.

When speaking to operators, use only this interface vocabulary:
`人设方案`, `第N稿`, `调整记录`, `定稿启用`, `新方向开测`, `Winner加推`,
`停投`, and `内容组成`. Do not expose engineering terms such as candidate,
branch, commit, head, merge, payload, element row, or version table.
