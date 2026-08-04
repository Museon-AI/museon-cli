---
name: experiment-brain
description: "How Museon agentic campaign experiments work and how Mel operates inside them. Load before any managed-operation strategy work: persona-plan research, proposal drafting, holdings reading, or experiment reporting. Mental model and SOP only — command invocation details live in the Museon CLI's own help."
---

# Experiment Brain

## What a campaign is

- A campaign IS the experiment. Its dossier defines it: direction_brief (what we are betting on), success_hypothesis (the operator's judgment anchor), contract (client-facing constraints), strategy_signal (machine-judged targets: view ramps, miss windows, degradation guardrails), and policy (machine-enforced execution settings).
- Persona plans are the directions under test. Elements — persona / format / topic / CTA combinations — are the units of testing inside each plan. Accounts are capacity assigned to directions.

## How the system runs the loop daily (all of it is visible to you)

1. Account health is sensed and tagged every day. Tags are pure observation; they never change schedules by themselves.
2. Once a day an evaluation pass judges every active campaign against its strategy_signal: weekly view ramp factors, consecutive-miss windows, and degradation guardrails. Verdicts are recorded. When action is needed the system opens one issue per campaign — scope already complete — and dispatches it to you.
3. You research, draft, and submit proposals. The Gate applies them: element-level changes (add / retire / boost with rollout intent / account reallocation) are auto-class and apply automatically after a 1-hour operator veto window; persona-level changes go to operator review; strategy-level questions reach the operator as needs_human issues.
4. Confirmed proposals roll out schedule changes automatically, and a daily top-up keeps future publishing windows filled.
5. Outcomes flow back: confirmed proposals are re-checked later and conclusions accumulate in the campaign learning ledger. A vetoed proposal comes back to you with the operator's reason.

## Your role and boundaries

- Research, draft, and submit proposals directly. Do not ask for permission in conversation and do not wait for operator approval — the Gate is the control point, and the operator steps in only on exceptions (a veto, a review-class proposal, a needs_human issue).
- Never claim a change has taken effect until the system confirms it.
- Ground every direction choice in evidence: the campaign learning ledger first, then transferable winners from the same workspace, then external references. When there is no evidence, say so and ask the operator for direction — never invent elements.
- Explore in small, attributable batches; amplify only proven winners and always state the rollout intent; retire what has demonstrably failed; give every proposal an explicit rationale.

## Reporting

- In recaps and the daily workspace attribution report, narrate the experiment cycle in plain operator language: what is being tested, what won and is being amplified, what was retired, what conclusions were recorded, and what needs a human decision. Do not use internal mechanism jargon.

## Commands

- Command surfaces, flags, and invocation details are documented in the Museon CLI itself — always consult its help and catalog instead of this skill.
