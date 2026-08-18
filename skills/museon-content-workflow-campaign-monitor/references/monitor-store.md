# Campaign monitor store

## Mental model

Collection → tracked creator/content → synced post → local performance history. Creator/content imports can be asynchronous; later list reads verify collection membership. A schedule item can resolve to the published post stored in this graph.

Review compares planned, generated, and published work with observed outcomes, separating performance facts from interpretation and ending in a specific next action.

## Shortcuts

| Object | Start with |
| --- | --- |
| Creator membership | `museoncli campaign-monitor +creator-list` |
| Content membership | `museoncli campaign-monitor +content-list` |
| Creator history | `museoncli campaign-monitor +creator-performance-get` |
| Post history | `museoncli campaign-monitor +post-performance-get` |

## DON'T

- **DON'T** confuse creator social-account IDs with collection-content IDs.
- **DON'T** report an import as verified membership before a list read confirms it.
- **DON'T** conflate local synchronized history with authorized live analytics.
- **DON'T** stop at interpretation; identify the next content, schedule, evidence, or test action.

## Relationships

Use research for live discovery and artifacts for a retained review. Use social-account when provenance must come from the connected account itself.
