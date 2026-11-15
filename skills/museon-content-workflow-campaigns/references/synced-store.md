# A Campaign's tracked creators and posts

## Mental model

Campaign → tracked creator (social account) / post → synced post → local performance history. A tracking Campaign takes creators and posts by hand; a UGC Campaign's come through its enrollments. Creator/post imports by URL run in the background: `+add --wait` reports what became of each URL, or `campaign import +get --id <task_id>` reads it later. Later list reads verify membership. A schedule item can resolve to the published post stored in this graph.

Review compares planned, generated, and published work with observed outcomes, separating performance facts from interpretation and ending in a specific next action.

## Shortcuts

| Object | Start with |
| --- | --- |
| Creator membership | `museoncli campaign creator +list --campaign-id <id>` (`data.items`, `data.source_kind` ugc or tracking: one shape for both kinds) |
| Post membership | `museoncli campaign content +list --campaign-id <id>` (`data.items`; a UGC Campaign's Content tab is `campaign video +list`) |
| Track more (tracking Campaigns only) | `museoncli campaign creator +add` / `campaign content +add --campaign-id <id> --url <url> --wait` |
| What became of an add | `museoncli campaign import +get --id <task_id>` (`data.url_import_task.task.id` from the add): status, counts, each failed URL with its reason |
| One creator's profile and history | `museoncli campaign creator +get --creator-id <creator_social_account_id>`, `campaign creator +get-performance --creator-id <creator_social_account_id> --date-from D --date-to D` (both dates required, at most 180 days; `--creator-id` is the creator's social account id, not a Campaign id) |
| One creator's synced posts | `museoncli campaign post +list --creator-id <creator_social_account_id>` |
| Post history | `museoncli campaign post +get-performance --content-id <content_id>` |

## DON'T

- **DON'T** confuse creator social-account IDs with collection-content IDs (`content +remove` takes the latter, from `content +list`).
- **DON'T** report an import as done from `+add`'s `ok`: the add is queued. Read its outcome (`--wait` or `campaign import +get`) and report each failed URL.
- **DON'T** conflate local synchronized history with authorized live analytics.
- **DON'T** stop at interpretation; identify the next content, schedule, evidence, or test action.

## Relationships

Use research for live discovery and local files for retained reviews. Preserve the returned data provenance; do not present public tracking as connected-account analytics.
