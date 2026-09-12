# Routine lifecycle

## Mental model

Define outcome, inputs, owner, trigger, report destination, approval boundary, and surviving memory. Draft → accepted/active; active ↔ paused; rebuild creates a replacement; cancel removes the active trigger. Memory should contain durable facts, decisions, successful patterns, failures worth avoiding, and next-state context.

## Shortcuts

| Transition | Start with |
| --- | --- |
| Draft to active | `museoncli routines +accept-draft` |
| Replace instruction/trigger | `museoncli routines +rebuild-ad-hoc` |
| Temporarily stop/restart | `museoncli routines +pause` |
| End trigger | `museoncli routines +cancel` |
| Persist learning | `museoncli routines +record` |

## DON'T

- **DON'T** hide the future writes or approval boundary implied by a trigger.
- **DON'T** take control of another owner's routine.
- **DON'T** rebuild when pause/resume expresses the intended lifecycle change.
- **DON'T** copy secrets or raw customer payloads into memory.

## Relationships

Routine lifecycle belongs here; content/account/campaign effects belong to their domain Skills and retain those approval rules.
