# Social account state

## Mental model

Connection authorizes a platform account into a workspace. Publish configuration controls account-wide output behavior; asset bindings select effective creative pools; a config version can materialize schedule items. Schedule items progress independently into generation and publication. Profile edits and avatar generation are separate asynchronous tasks.

One-account asset changes may create an explicit effective-Persona override while leaving a fully-managed account's Persona Plan binding unchanged. That distinction must be visible before approval.

## Shortcuts

| State | Start with |
| --- | --- |
| Account identity | `museoncli social-account +get` |
| Connection completion | `museoncli social-account +connect-link-status` |
| Effective bindings | `museoncli social-account +assets-get` |
| Planned content | `museoncli social-account +schedule-list` |
| Profile task progress | `museoncli social-account +profile-edit-status` |

## DON'T

- **DON'T** guess an account or schedule item from a handle when a canonical ID is required.
- **DON'T** treat omitted configuration fields as a request to clear them.
- **DON'T** use one-account asset reads for a complete multi-account audit.
- **DON'T** hide `source` when reporting performance.
- **DON'T** bypass Persona Plan semantics with an account-level Persona override.

## Relationships

Use account-publish for atomic pools/plans, Agentic Campaign for fully-managed operations, and generation for standalone outputs not bound to a schedule.
