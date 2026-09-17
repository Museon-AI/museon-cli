# HireAICreator video lifecycle in Codex and Mel

Run `museoncli schema hireaicreator.<resource>-<action>` before constructing an
operation. For workspace-scoped list/calendar commands pass `--workspace-id`
every turn. Video/plan ID operations are resource-scoped; their APIs authorize
membership from the resource itself and accept no workspace argument. Resolve
the resource in the intended workspace before operating on its exact ID.
Read full `raw_result.path` JSON when output is large and complete pagination.

## Generate and refine

`plan +list/+get` reads plans. `plan +generate` starts plan generation with a
required idempotency key; an accepted receipt is not completion. `plan +cancel`
requires the latest `expected_version` and `--yes`; inspect skipped videos.
Although its API accepts an optional idempotency header, that handler ignores
it, so this CLI command does not advertise idempotency.

Use `video +get/+readiness` before mutations and carry the returned version as
`expected_version`. `video +ai-hook-regenerate`, `+pov-regenerate`,
`+text-overlay-regenerate` and `+caption-regenerate` replace selected components.
Hook regeneration accepts `generation_directions`; the other three accept
`creative_direction`. `+bulk-regenerate` supports only POV, text overlay and
caption, with per-video versions. Inspect accepted, conflicted and failures.

`video +ai-hook-candidate/+pov-candidate` creates a candidate. Inspect returned
video state/media before `+candidates-commit`; commit takes the current version
and has no idempotency key. `+cancel-generation` can target specific components;
omitting components or supplying null preserves server defaults. Cancel actions
require `--yes`. Refresh after conflicts instead of guessing a version.

## Review, render and deliver

`video +review/+bulk-review` sends `approved` or `changes-requested` with the
reviewed version and optional note. Both require `--yes`: approving a scheduled
video may allow its publication, so review is not merely a cosmetic label.
Verify the content and user intent before approval. A bulk HTTP 200 can contain
conflicted/failed items; inspect each result before dependent operations.

`video +render` requests the version-bound render; `+render-get` reports its
actual status, version and revision. `+retry-render` retries a failed render.
These endpoints accept generation directions in their request schema but do not
use them: use component regeneration to change creative direction. None of these
render requests has server idempotency support.

`delivery +export-batch` exports 1–50 unique videos with explicit versions and
a required idempotency key. Poll every returned export through `+export-get`
and require completed status, correct video/version/revision and usable URL.
Do not equate accepted/rendered/exported with published. Use the existing
share/manual-delivery workflow only when that delivery mode was requested.

## Calendar, cancellation and deletion

`calendar +month` needs campaign, timezone and interval; `+day` needs campaign,
timezone and day. Inspect `truncated` on a day response; a truncated result is
not the full set. Calendar queries do not schedule anything.

`video +cancel` stops one video's remaining work. `+delete/+bulk-delete` are
destructive, require `--yes`, and use explicit versions. Single deletion sends
expected_version in the query and accepts the API's empty 204 response.
Read persisted state after all mutations. Cancellation does not undo posts.

Every write supports local `--dry-run`; it does not test server authorization,
resource eligibility, or generate media. Generation/candidate/export operations
that advertise `--idempotency-key` require the same key for the same retried
request. Other operations must be read back after ambiguous failures before
retrying. Preserve server 403/404/409/422 reasons: do not bypass denial, retry
with another identity, or diagnose 404/422 as proof of missing capability.
