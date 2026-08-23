# Batch account edits (config, profile, avatar)

## Mental model

Editing the same thing across two or more accounts is one server-side batch call, not a loop.
The batch returns a per-account `results` array plus a `summary`; judge success from those, not
from the exit code. A `skipped: account_not_accessible` row means that id is not in this
workspace.

Asynchronous batches split by size: a large batch is submitted without waiting, and its task id
is handed back so the caller can schedule the follow-up status read. Blocking inside an agent
turn is not an option — the sandbox pauses between turns, so a wait that outlives the turn is
lost.

Avatar image generation is a separate asynchronous step that runs BEFORE a profile submit.
Generate avatars in their own batch, collect the completed `avatar_url` values, then feed those
into the profile submit.

## Required-hashtag scope and precedence

The account-level value is only the DEFAULT that a schedule item copies in at creation time.
Once an item exists, the item's own required hashtags are authoritative all the way to publish:
the account level is never re-read at generation or publish, and the two levels are never merged.
An account-level write therefore affects only FUTURE items. Changing hashtags on items that are
already scheduled needs a schedule rebuild.

An empty required-hashtags value clears the account's hashtags; omitting the flag preserves them.

## Shortcuts

| Situation | Start with |
| --- | --- |
| One account's publish config | `museoncli social-account +config-update` |
| Two or more accounts' publish config | `museoncli social-account +config-batch-update` |
| One account's profile | `museoncli social-account +profile-edit-submit` |
| Two or more accounts' profiles | `museoncli social-account +profile-edit-batch-submit` |
| Follow a profile batch | `museoncli social-account +profile-edit-status` |
| Draft new avatars | `museoncli social-account +avatar-generate-batch` |
| Collect generated avatars | `museoncli social-account +avatar-generate-status` |

## Sizes

- Config batch: at most 200 accounts per call; split larger sets.
- Avatar batch: one shared base prompt, at most 20 accounts; group accounts sharing a prompt.
- Large batch (5 or more accounts): submit without waiting and return the task id for a later
  status read. Small batch (4 or fewer): waiting inline is acceptable.

## DON'T

- **DON'T** loop the single-account command to emulate a batch.
- **DON'T** fan out one OS process or one sub-agent per account; a large per-account fan-out
  exhausts sandbox memory and fails the whole task.
- **DON'T** block or poll inside the turn for a large asynchronous batch.
- **DON'T** judge a batch from its submission response or exit code instead of the per-account
  results and summary.
- **DON'T** generate avatars through the synchronous profile draft path; a single slow generation
  exceeds the edge timeout and then retries forever. That draft path is for nickname/bio text only.
- **DON'T** re-run a whole avatar batch to repair a few failures; re-run only the failed accounts.
- **DON'T** claim an account-level hashtag write changed already-scheduled items.

## Relationships

Multi-account pools and schedule plans belong to account-publish; fully-managed accounts are
governed by Agentic Campaign.
