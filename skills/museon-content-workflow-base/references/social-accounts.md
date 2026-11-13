# Retained account state

`+list` resolves canonical account IDs; `+get` verifies one account. A connection link is only an
authorization request until `+get-connect-link` reports its terminal result. `+connect-adb` and
`+get-stream-url` address the phone already bound to that account and do not change its business ownership.

`+connect-adb` waits up to about two minutes for a cold phone by itself. If it still ends with
`server_code: CLOUD_PHONE_BOOTING`, the phone is booting and stays on: run the same command again once
before reporting it as a blocker. A repeat does not start the phone twice.

Performance responses carry provenance. Relay whether data came from official/managed analytics or
public fallback, and do not turn a missing page into a claim that the account has no history.

HireAICreator account assignment, plan capacity, generation, scheduling, and delivery are owned by `hireaicreator`.

## Tags

Tags are the organization's own labels on an account; `social-account +list --tag <tag>` filters by
one. Owner, admin or operator can change them:

```bash
museoncli social-account tag +add --id <account_id> --tag warmup --dry-run   # before/after, no write
museoncli social-account tag +add --id <account_id> --tag warmup
museoncli social-account tag +remove --id <account_id> --tag warmup
museoncli social-account tag +set --id <account_id> --tag us --tag beauty     # exact set; --clear empties
```

`+add` and `+remove` read the current tags and write the whole set back; there is no version check,
so a change someone makes in between is overwritten. Staff pool allocation stays in the web app.

## Sync and unbind

Owner, admin or operator. Both work with the selected organization alone:

```bash
museoncli social-account +sync --profile-id <late_profile_id>   # one profile's accounts, safe to repeat
museoncli social-account +sync-all                               # your landing workspace in this organization only
museoncli social-account +unbind --account-id <id> --dry-run     # show the user, then --yes
museoncli social-account +unbind --account-id <id> --yes
```

`--profile-id` is the Late profile id of a bound account, not a MuseOn UUID. `+sync-all` syncs only your
landing workspace in the organization; use `+sync` for a profile held elsewhere. `+unbind --account-id`
is the bound-account row's id (`late_social_accounts`), not a pool account id; it disconnects the account
from the platform and cannot be undone from the CLI (connect it again with `+create-connect-link`).
Without `--yes` it returns `confirmation_required` with a preview.
