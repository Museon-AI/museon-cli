# Slideshow lifecycle

## Assets

Use `ai-slideshow asset +list/+get/+get-batch/+list-options/+create/+update/+delete`. Read the returned object after a write. If deletion is blocked by a relationship, resolve it in the owning workflow before retrying.

## Generation

Use `ai-slideshow generation +create` with explicit `format_id`, `content_topic_id`, and `persona_id`; `product_id` is optional. Use `+get` or `+list` to observe progress. A creation receipt is not a finished slideshow. Do not attach an account, pool account, or schedule item to generation.

## Publishing

The restored publish surface keeps the original account and schedule orchestration:

- `+bulk-get-asset-pools/preview/set/status/cancel` reads and changes persona, product, format, topic, and BGM pools for up to 200 accounts. Preview first. `set` uses the matching `preview_token`, a stable `idempotency_key`, and required confirmation flags. Status is completion ground truth; cancel stops pending work and does not roll back completed changes.
- `+get-config/update/batch-update` manages account publish configuration.
- `+list-versions/get/create/activate` manages versioned schedule rules.
- `+list-schedules/get/generate/create/update/delete` reads and changes concrete schedule items.
- `+preview-schedule-plan/batch/status/cancel` plans up to 200 accounts, 180 days, 24 daily slots, and 5,000 occurrences. Apply the matching preview token and stable idempotency key. Job cancellation does not delete schedule items already created; use a previewed `cancel-only` batch for schedule removal.

- `+schedule-approve --account-id <pool_account_id> --schedule-item-id <id>` approves one schedule item (staff only).
- `+retry-failed --task-id <parent_task_id>` redrives a batch publish's failed jobs. Only when the failures produced no post: without `--yes` it returns `confirmation_required` with a preview; `--yes` is the server's duplicate-post confirmation. Check `publish job +list --task-id` before and after; never repeat it blindly.

Do not treat preview or batch admission as completion. Preserve returned job ids and poll the matching status command. These commands use the established slideshow publishing backend; they do not restore evaluator or CTA commands.

## Content model

A slideshow generation combines reusable `format`, `topic`, and `persona` assets, with an optional `product`. The format is the evidence-backed structure and slide flow; the topic is the subject; the persona controls voice; the product supplies confirmed product facts when the work needs them. Reuse existing assets before creating near-duplicates. Register media first and pass its Media id where an asset expects media; do not substitute raw URLs, handles, or research prose for an id.

When reproducing a strong reference, collect and analyze the evidence first, distill only the reusable structure into a format, then create the topic and other missing inputs. Preserve the distinction between observed source facts and the new creative choices. Read the generation after creation until it reaches a terminal status and inspect returned result media before offering publication.

## Reviewing AI image posts

The web's /content-review actions, by generation id (`ai-slideshow generation +list`); owner, admin or operator. No workspace is sent, and the routes carry no version or idempotency key, so read the generation (`generation +get`) before repeating one.

```bash
museoncli ai-slideshow review +approve --generation-id <id>      # mark reviewed
museoncli ai-slideshow review +unreview --generation-id <id>     # take the approval back
museoncli ai-slideshow review +reject --generation-id <id>
museoncli ai-slideshow review +adjust --generation-id <id> --instruction 'Shorter title' \
  --annotations-json '[{"slide_media_id":"<media>","slide_index":2,"x":100,"y":200,"comment":"Too small"}]'
museoncli ai-slideshow review +retry --generation-id <replacement_id>   # rerun a failed adjustment
```

`+adjust` regenerates the post as a new generation (`replacement_generation_id`): review that one next. Annotations are points (`x`, `y`) or regions (plus `width`, `height`) on a 0-1000 grid, up to 20, each with a comment.
