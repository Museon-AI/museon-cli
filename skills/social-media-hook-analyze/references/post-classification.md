# Post classification rubric

Use this rubric to write `ugc-creator-hook-assessment.v1`. This is an LLM task
performed by the host Agent. The server's model output is observation evidence,
not the verdict.

## Primary question

Decide whether the opening itself is a **UGC creator Hook**: a creator-led
expression mechanism that an ordinary creator could reuse. Judge the opening
and the way the content earns attention, not whether the profile looks like a
creator account.

A qualifying post normally has all of these properties:

- a human creator drives the opening through speech, action, expression,
  reaction, story, demonstration, or embodied POV;
- the content feels like native creator communication rather than an object,
  event, or brand asset being displayed;
- when a product is present, it enters through the creator's experience, claim,
  problem, test, or reaction;
- an ordinary creator could reproduce the expression structure without the
  original brand, venue, celebrity, production crew, or exclusive event.

A visible face is useful evidence but not mandatory. A first-person
demonstration with a real creator's voice or embodied experience can qualify.
Conversely, the presence of a person is not enough when the person merely
models, unveils, or decorates a product-focused ad.

## Exclusion patterns

Classify `does_not_qualify` when the evidence shows that the opening is mainly:

- a product or vehicle beauty montage;
- an event reveal, launch, booth tour, or event coverage;
- a cinematic brand advertisement;
- object-only demonstration without creator experience;
- text/motion graphics, scenery, or product footage without creator-led
  expression.

Do not use these as positive proof by themselves: vertical format, handheld
camera, selfie-like framing, first-person camera, environment audio, quick cuts,
or `ugc_style.is_ugc_style=true`.

## Evidence fields

Start with these server fields:

- `opening.initial_frame`
- `opening.visual_action`
- `opening.audio_and_speech`
- `opening.face_and_expression`
- `opening.body_language`
- `opening.camera_and_framing`
- `mechanism.hook_type`
- `mechanism.why_it_stops_scroll`
- `mechanism.why_viewers_continue`
- `recreation.must_preserve`
- `recreation.non_transferable_elements`
- `recreation.three_second_description`
- timestamped `evidence[]`
- `evidence_quality` limitations

Use `ugc_style.signals` only as supporting format evidence after creator-led
expression is established.

## Verdict rules

- `qualifies`: the evidence supports creator-led expression, creator experience
  (when a product is involved), and ordinary-creator reproducibility.
- `does_not_qualify`: the evidence supports an exclusion pattern or explicitly
  shows no creator-led expression.
- `uncertain`: visibility, speech, temporal evidence, or structured observations
  are insufficient or internally conflicting.

Confidence reflects evidence quality, not enthusiasm. Use low confidence when
the relevant opening cannot be observed clearly. The ranker sends every
low-confidence verdict to manual review.

Use these values for the three gate fields:

- `creator_led`: `yes`, `no`, or `uncertain`;
- `creator_experience_carries_product`: `yes`, `no`, `uncertain`, or
  `not_applicable` when the post contains no product at all;
- `ordinary_creator_reproducible`: `yes`, `no`, or `uncertain`.

A qualifying verdict requires `creator_led=yes`,
`ordinary_creator_reproducible=yes`, and product experience equal to `yes` or
`not_applicable`. Do not use `not_applicable` merely because a product is hard
to see; use it only when the observations show that no product is involved.

Allowed `post_type` values are:

- `ugc_creator_hook`
- `brand_product_showcase`
- `event_coverage`
- `cinematic_brand_ad`
- `object_demonstration`
- `other_non_creator`
- `uncertain`

Every evidence entry needs an exact server JSON path and a concise observation.
Do not cite profile-level facts in a post assessment.
