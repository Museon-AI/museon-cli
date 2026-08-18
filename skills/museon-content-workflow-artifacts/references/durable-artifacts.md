# Durable artifacts

Create an artifact when the user needs a deliverable they will keep, share, edit, download, schedule, or revisit: research reports, strategy directions, account diagnoses, performance reviews, schedules, or multi-result summaries. Answer directly for short Q&A, one caption, status updates, or missing required information.

Before authoring load:

```bash
museoncli skills +get --name artifact-authoring
```

Follow the returned structure/embed contract. Before upload run `museoncli artifacts +validate --file <report.md>` and fix errors. Upload is a write: explain what will be published and obtain separate approval before `museoncli artifacts +upload`.

When both links return, label both:

- `public_url`: shareable without Museon login.
- `url`: private workspace link for signed-in members.

Do not expose secrets or raw customer payloads. Paste ready-made `ref` values verbatim; never construct or edit them.

After review preserve only reusable value: evidence and decisions in reports; proven content elements as assets; repeatable work as routines; routine-specific learning in memory; performance as evidence for the next cycle.
