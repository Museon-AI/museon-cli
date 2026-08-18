# Generation lifecycle

## Mental model

The reusable asset combination is stable input; per-generation guidance belongs to the new Generation, not back into shared assets. A live `ref` is both identifier and customer progress surface. Completion adds grid/slide media and preview images.

## Shortcuts

| State question | Start with |
| --- | --- |
| Missing creative input | `museoncli asset +list` |
| Start immutable attempt | `museoncli generation +create` |
| Returned async handle | `museoncli generation +get` |

## DON'T

- **DON'T** mutate reusable assets for a one-off note.
- **DON'T** use placeholder IDs.
- **DON'T** reconstruct or edit a returned `ref`.
- **DON'T** omit available previews from completed-result delivery.

## Relationships

Standalone generation uses asset inputs directly. Managed publishing should start from its schedule item so account, pool, and schedule context remain bound.
