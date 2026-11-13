# Running a UGC campaign day to day (`ugc`)

These commands do what the web's task center, roster, content review and recruiting
screens do, through the same routes. `--campaign-id` is the UGC campaign id from
`museoncli ugc campaign +list`. The server decides who may write: owner and admin
everywhere, an operator on Campaigns they are assigned to (PM/OP), Brand editors
only review and counting on a shared Campaign, members never. A refusal is
`not_found` or `forbidden`; report it, never retry as someone else.

## The confirmation rule

Every write reads the live state first. `--dry-run` returns that read and what the
write would send, and writes nothing.

- Plain writes (claim, comment, due date, pause, persona, counting...) run without
  `--yes`. Still dry-run first when the user has not already decided.
- Anything that reaches the creator or cannot be undone from the CLI needs `--yes`:
  task actions, approve, reject, remove, verdicts, feedback threads and replies,
  messages, nudges, card resends, invitations, revoking a link, splitting, merging,
  taking posts out of the count. Without `--yes` the command answers
  `ok: false, reason: confirmation_required` with `preview` (the same dry run).
  Show the user `preview.data` and `preview.warnings`, ask, then rerun with `--yes`.
- Compare-and-set: the CLI sends the status or `updated_at` it just read. Pass
  `--expected-status` / `--expected-updated-at` from your own earlier read to make
  the write fail if things moved since the user decided. A `conflict` means read
  again and ask again; never retry blindly.
- Messages, feedback threads and replies carry an idempotency key (the CLI makes
  one and returns it as `idempotency_key`). After a timeout, retry with
  `--idempotency-key <that key>` and the same text; a new key sends a second message.

## Tasks

| Do | Command |
| --- | --- |
| Take a task / give it back | `ugc task +claim --id <task>` / `ugc task +release --id <task>` |
| Leave a note for the team (the creator does not see it) | `ugc task +comment --id <task> --body "..."` |
| Set or clear the due time | `ugc task +set-due --id <task> --due-at 2026-11-20T18:00:00+08:00` (`none` clears) |
| Assign people | `ugc task +set-assignees --id <task> --assignee-user-id <user>` (`--unassign` clears) |
| Snooze its reminder | `ugc task +defer-reminder --id <task>` |
| Press one of its buttons | `ugc task +run-action --id <task> --action <action> ...` |

`+run-action` takes one of the task's own `actions` (kebab or snake case):
review tasks `approve` / `reject` (`--comments` go to the creator), attribution
`attach` / `attach-unpaid` / `detach` / `skip`, invitations `resend` / `revoke`,
contracts `send` / `mark-signed` / `terminate`, warmup `approve-warmup` /
`reject-warmup`, Discord `retry` / `resend-card` / `abandon`. Inputs other than
`--comments` go in `--fields-json` (for example `{"creative_id": "..."}` to attach a
post to a video, `{"payscale_id": "..."}` when approving an application on another
payment structure, or the warmup account and proof versions from the task's
`context`). The CLI adds the attribution card version and the application revision
the way the web does.

```bash
museoncli ugc task +run-action --id <task> --action reject --comments "Show the product in the first 3 seconds" --dry-run
museoncli ugc task +run-action --id <task> --action reject --comments "Show the product in the first 3 seconds" --yes
```

## Enrollments (the roster)

| Do | Command |
| --- | --- |
| Approve an application (tells the creator, sends the contract) | `ugc enrollment +approve --campaign-id <c> --id <enrollment> --yes` |
| Reject one (`--note` is written to the creator; `--ban` also bans from Discord) | `ugc enrollment +reject --campaign-id <c> --id <enrollment> --note "..." --yes` |
| Admit an onboarding creator by hand | `ugc enrollment +admit --campaign-id <c> --id <enrollment> --note "why"` (`--warmup-not-ready` to admit before warmup) |
| Pause / resume a creator | `ugc enrollment +pause ...` / `ugc enrollment +resume ...` |
| Remove creators (up to 1000) | `ugc enrollment +remove --campaign-id <c> --id <e1> --id <e2> --yes` |
| Give enrollments a persona | `ugc enrollment +set-persona --campaign-id <c> --id <e> --persona-id <persona>` (`none` clears) |
| Change one creator's payment structure | `ugc enrollment +set-payscale --campaign-id <c> --id <e> --payscale-id <payscale>` |
| End a trial | `ugc enrollment +graduate-trial --campaign-id <c> --id <e>` |

The team usually approves and rejects applications from the review task
(`ugc task +run-action --action approve|reject`); the enrollment commands are the
direct route. There is no command to reopen a rejected application: the creator
reapplies.

## Reminding and messaging creators

| Do | Command |
| --- | --- |
| Remind one creator about a check (Discord, once a day) | `ugc enrollment +nudge --id <enrollment> --check not-signed --yes` |
| Remind everyone a check holds for | `ugc enrollment +bulk-nudge --campaign-id <c> --check quiet --yes` (no `--check`: every check) |
| Write in the creator's project conversation (their MuseOn project page) | `ugc message +send --enrollment-id <e> --body "..." --yes` |
| Write about one video (pushed to their Discord) | `ugc message +send --campaign-id <c> --creative-id <video> --body "..." --yes` |
| Send the contract or onboarding card again | `ugc message +resend-card --enrollment-id <e> --kind contract-card --yes` |
| Retry a failed delivery | `ugc message +retry --enrollment-id <e> --id <intent_id> --yes` |

Checks: `cant-track`, `not-signed`, `not-set-up`, `quiet`, `not-healthy`. The nudge
preview says whether the check holds and whether the creator was already nudged
today; the bulk preview counts creators per check.

## Content review and counting

| Do | Command |
| --- | --- |
| Approve / reject a video directly (Brand editors too) | `ugc creative +review --campaign-id <c> --id <video> --decision reject --note "..." --yes` |
| Start a feedback thread at a moment of the video | `ugc feedback-thread +create --campaign-id <c> --creative-id <video> --body "..." --time-ms 2500 --yes` |
| Reply in a thread | `ugc feedback-thread +reply --campaign-id <c> --creative-id <video> --id <thread> --body "..." --yes` |
| Resolve or reopen a thread | `ugc feedback-thread +set-status ... --id <thread> --status resolved` |
| Count a video again / stop counting it (creator not told) | `ugc creative +set-counting --campaign-id <c> --id <video> --counted` / `--no-counted` |
| Take posts out of the count | `ugc post +stop-counting --campaign-id <c> --id <content> [--id ...] --yes` |
| Make one post its own video | `ugc post +split --campaign-id <c> --id <content> --yes` |
| Merge a creator's videos into one | `ugc creative +merge --campaign-id <c> --id <into> --merged-creative-id <other> --yes` |

A post or video a payout already pays for refuses counting changes, splits and
merges (`post_in_payout`): tell the user, do not work around it. Attribution
decisions (which video a post belongs to) go through the attribution task:
`ugc task +run-action --action attach|detach|skip`.

## Recruiting

| Do | Command |
| --- | --- |
| See the campaign's sign-up links | `ugc recruit-link +list --campaign-id <c>` |
| Make a link (own code, roster group, payscale, auto-approve) | `ugc recruit-link +create --campaign-id <c> --name "TikTok ads" --group-name Wave2` |
| The public discover link | `ugc recruit-link +create --campaign-id <c> --kind discover` |
| Change a link's settings (others kept) | `ugc recruit-link +update --campaign-id <c> --id <link> --no-auto-approve` |
| Stop a link working | `ugc recruit-link +revoke --campaign-id <c> --id <link> --yes` |
| Invite a creator by email | `ugc invitation +create --campaign-id <c> --email creator@example.com --yes` |
| See invitations / resend / revoke one | `ugc invitation +list --campaign-id <c> --status open`, `+resend`, `+revoke` (`--id <invitation> --yes`) |

The invitation preview flags an open invitation already sent to that address:
resend that one instead of sending another.
