# Slideshow lifecycle

## Assets

Use `ai-slideshow asset +list/+get/+get-batch/+options/+create/+update/+delete`. Read the returned object after a write. If deletion is blocked by a relationship, resolve it in the owning workflow before retrying.

## Generation

Use `ai-slideshow generation +create` with explicit `format_id`, `content_topic_id`, and `persona_id`; `product_id` is optional. Use `+get` or `+list` to observe progress. A creation receipt is not a finished slideshow. Do not attach an account, pool account, or schedule item to generation.

## Publishing

The restored publish surface keeps the original account and schedule orchestration:

- `+asset-pools-batch-get/preview/set/status/cancel` reads and changes persona, product, format, topic, and BGM pools for up to 200 accounts. Preview first. `set` uses the matching `preview_token`, a stable `idempotency_key`, and required confirmation flags. Status is completion ground truth; cancel stops pending work and does not roll back completed changes.
- `+config-get/update/batch-update` manages account publish configuration.
- `+version-list/get/create/activate` manages versioned schedule rules.
- `+schedule-list/get/generate/create/update/delete` reads and changes concrete schedule items.
- `+schedule-plan-preview/batch/status/cancel` plans up to 200 accounts, 180 days, 24 daily slots, and 5,000 occurrences. Apply the matching preview token and stable idempotency key. Job cancellation does not delete schedule items already created; use a previewed `cancel-only` batch for schedule removal.

Do not treat preview or batch admission as completion. Preserve returned job ids and poll the matching status command. These commands use the established slideshow publishing backend; they do not restore evaluator or CTA commands.

## Content model

A slideshow generation combines reusable `format`, `topic`, and `persona` assets, with an optional `product`. The format is the evidence-backed structure and slide flow; the topic is the subject; the persona controls voice; the product supplies confirmed product facts when the work needs them. Reuse existing assets before creating near-duplicates. Register media first and pass its Media id where an asset expects media; do not substitute raw URLs, handles, or research prose for an id.

When reproducing a strong reference, collect and analyze the evidence first, distill only the reusable structure into a format, then create the topic and other missing inputs. Preserve the distinction between observed source facts and the new creative choices. Read the generation after creation until it reaches a terminal status and inspect returned result media before offering publication.
