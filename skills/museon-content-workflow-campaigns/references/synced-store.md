# A Campaign's tracked creators and posts

## Mental model

Campaign → tracked creator (social account) / post → synced post → local performance history. A tracking Campaign takes creators and posts by hand; a UGC Campaign's come through its enrollments. Creator/post imports can be asynchronous; later list reads verify membership. A schedule item can resolve to the published post stored in this graph.

Review compares planned, generated, and published work with observed outcomes, separating performance facts from interpretation and ending in a specific next action.

## Shortcuts

| Object | Start with |
| --- | --- |
| Creator membership | `museoncli campaign creator +list --campaign-id <id>` |
| Post membership | `museoncli campaign content +list --campaign-id <id>` |
| Track more (tracking Campaigns only) | `museoncli campaign creator +add` / `campaign content +add --campaign-id <id> --url <url>` |
| One creator's profile and history | `museoncli campaign creator +get --id <creator_social_account_id>`, `campaign creator +get-performance --id <creator_social_account_id> --date-from D --date-to D` (both dates required, at most 180 days; `--id` is the creator's social account id, not a Campaign id) |
| One creator's synced posts | `museoncli campaign post +list --creator-id <creator_social_account_id>` |
| Post history | `museoncli campaign post +get-performance --id <content_id>` |

## DON'T

- **DON'T** confuse creator social-account IDs with collection-content IDs (`content +remove` takes the latter, from `content +list`).
- **DON'T** report an import as verified membership before a list read confirms it.
- **DON'T** conflate local synchronized history with authorized live analytics.
- **DON'T** stop at interpretation; identify the next content, schedule, evidence, or test action.

## Relationships

Use research for live discovery and local files for retained reviews. Preserve the returned data provenance; do not present public tracking as connected-account analytics.
