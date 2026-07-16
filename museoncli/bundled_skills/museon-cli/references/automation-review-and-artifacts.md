# Automation, review, and artifacts

Read this reference for monitoring, performance review, recurring routines,
memory, reports, or reusable operating assets.

## Review outcomes

Use the appropriate source for the object being reviewed:

- `social-account` for connected or operated account performance.
- `campaign-monitor` for monitored creators, content, campaign summaries, and
  locally synced post histories.
- `account-operation` for managed-fleet lifecycle, runs, attribution, and
  intervention status.

Compare what was planned, generated, and published with what actually worked.
Distinguish performance facts from interpretation. Turn the review into a
specific next action: reuse a format, adjust a topic, pause a weak element,
change a schedule, collect more evidence, or run a new test.

## Recurring automation

Inspect `museoncli schema routines` before proposing automation.

1. Define the recurring outcome, inputs, owner, trigger, report destination,
   approval boundaries, and memory that should survive each run.
2. Read existing routines before creating a duplicate.
3. Prefer a draft when the routine still needs user review.
4. Explain the exact trigger and future writes, obtain explicit approval, then
   create or accept the routine.
5. Verify the active trigger and ownership after the write.
6. During later runs, read existing memory first and record only durable facts,
   decisions, successful patterns, failures worth avoiding, and next-state
   context.

Only change, pause, resume, rebuild, or cancel routines owned by the current
operator. If another owner is returned, surface that ownership rather than
silently taking control.

## Durable artifacts

Create an artifact when the user needs a deliverable they will keep, share,
edit, download, schedule, or revisit: research reports, strategy directions,
account diagnoses, performance reviews, schedules, or multi-result summaries.
Answer directly in chat for short Q&A, a single caption, status updates, or
when required information is still missing.

Before authoring, load the current Museon business contract with:

```bash
museoncli skills +get --name artifact-authoring
```

Follow that returned contract for structure and embeds. Before upload, run
`museoncli artifacts +validate --file <report.md>` and fix validation errors.
Artifact upload is a write: explain what will be published and obtain separate
approval before `museoncli artifacts +upload`.

When upload returns both links, label and provide both:

- `public_url`: shareable without Museon login.
- `url`: private workspace link for signed-in members.

Do not expose secrets or raw customer payloads in artifacts. Paste ready-made
resource `ref` values verbatim so Museon can render live cards; never construct
or edit a `ref` by hand.

## Compound the loop

After review or delivery, preserve only reusable value:

- evidence and decisions in a durable report;
- proven products, personas, topics, formats, and media as assets;
- repeatable work as a routine;
- routine-specific learning in routine memory;
- performance outcomes as the starting evidence for the next research cycle.

The objective is not merely to produce another post. It is to make the next
research, generation, and publishing decision better informed than the last.
