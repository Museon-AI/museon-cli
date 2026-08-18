# Account connection and current state

Inspect exact schemas, then read the account before proposing a change:

- Resolve with `museoncli social-account +list` or `+get`.
- For a small one-account read use `+assets-get`; for complete pools or two or more accounts use the `account-publish` batch skill.
- Read publishing configuration with `+config-get`.
- Read planned posts and generation status with `+schedule-list` and `+schedule-get`.

Never guess an account, schedule item, or workspace from a handle when a write requires a canonical ID.

Required hashtags belong to publish settings. `social-account +config-update --required-hashtags '#Brand,#Campaign'` replaces them; `--required-hashtags ""` clears them; omission preserves current settings.

## Connect a user-owned account

1. Inspect `museoncli schema social-account.connect-link-create`.
2. State platform and workspace, then obtain explicit approval.
3. Run `museoncli social-account +connect-link-create`.
4. Give the authorization URL exactly as returned.
5. Verify with `museoncli social-account +connect-link-status`.

Never ask for passwords or platform credentials in chat.

For a small binding edit, read with `+assets-get`, prepare the smallest patch, and write with `+assets-set`. Generate scheduled content with the schedule command exposed by the current schema so account assets bind automatically. After publishing, resolve the schedule item to the live post and return its link when available.

## Performance provenance

`museoncli social-account +performance-get` prefers authorized channel data and may fall back to public data. Read `source` and label the difference. Do not call an API limitation a sync delay or promise unavailable history will later appear.
