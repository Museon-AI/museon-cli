# Result contract

The current server payload is `analysis_schema_version = social-hook-analysis.v1`.

Each completed item includes:

- source: `id`, `permalink`, `source_kind`, optional `source_profile_url`, and
  creator/caption metadata;
- media: MIME type and duration only; signed download URLs are not persisted or
  returned;
- analysis: `hook_name`, `ugc_style`, `opening`, `mechanism`, `recreation`,
  `evidence_quality`, and timestamped `evidence`;
- lifecycle: `status`, `stage`, timestamps, and sanitized error fields.

These analysis fields are observations. In particular,
`ugc_style.is_ugc_style` does not mean `ugc_creator_hook` and says nothing about
whether the profile owner is a UGC creator.

The server deliberately does not return `post_assessment`, `creator_assessment`,
`decision`, `score`, `dimension_scores`, `strategy_version`, or recommendation
order. The host Agent and this Skill own those derived fields.

Run status is one of `queued`, `discovering`, `analyzing`, `completed`,
`partially_completed`, or `failed`. Item status is one of `queued`, `processing`,
`completed`, `ineligible`, or `failed`.

`ineligible / NOT_VIDEO` means the direct post was resolved and no video media
was found. This happens before video download and server model analysis.

For an analysis schema version unknown to the strategy script, fail closed and
update the Skill. Never guess field meanings across versions.
