# Publishing and accounts

Read this reference for account connection, configuration, scheduling,
publishing, profile changes, or fully managed account operation.

## Start with current state

Inspect the relevant command schemas, then read the account before proposing a
change:

- Use `museoncli social-account +list` or `museoncli social-account +get` to
  resolve the target account.
- Use `museoncli social-account +assets-get` for bound persona, product, format,
  and topic assets.
- Use `museoncli social-account +config-get` for publishing configuration.
- Use `museoncli social-account +schedule-list` and
  `museoncli social-account +schedule-get` for planned posts and generation
  status.

Never guess an account, schedule item, or workspace from a handle alone when a
write requires a canonical ID.

## Connect a user-owned account

1. Inspect `museoncli schema social-account.connect-link-create`.
2. State the platform and workspace that will receive a connection link, then
   obtain explicit approval for the write.
3. Run `museoncli social-account +connect-link-create` with the approved input.
4. Give the returned authorization URL to the user exactly as returned.
5. Use `museoncli social-account +connect-link-status` to verify completion.

Do not ask for passwords or platform credentials in chat.

## Configure, schedule, and publish

1. Read current bindings, configuration, versions, and schedule as needed.
2. Prepare the smallest patch. Omit fields that should not change.
3. Dry-run bulk or uncertain changes.
4. Explain the accounts, content, timing, platforms, and approval behavior that
   will change.
5. Wait for separate explicit approval, apply, then read the state back.

Anything that can lead to a live post requires an approved content/schedule
plan, unless the account is already explicitly delegated for autonomous
publishing under an approved configuration. Never silently disable an approval
requirement.

Generate scheduled content with the schedule command exposed by the current
schema so account assets bind automatically. After publishing, resolve the
schedule item to the live post and return the post link when available.

## Performance provenance

`museoncli social-account +performance-get` prefers authorized channel data and
may fall back to public data. Read the returned `source` and label the
difference in customer-visible language. Do not describe an API limitation as a
sync delay or promise that unavailable historical data will appear later.

## Managed account operations

Use the `account-operation` domain only after reading the target accounts and
the exact command schemas. Batch operations should use the batch shortcut
exposed by the schema instead of repeating single-account writes.

Before submission, resolve niche, reference accounts, research direction, and
account conflicts. After submission, inspect created, failed, and existing
rows; never report a batch as fully successful without checking each category.
Stopping an operation is a separate terminal change and requires its own
explicit approval.
