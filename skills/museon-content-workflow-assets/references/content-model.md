# Content model

## Mental model

A Format captures hook, sequence, proof pattern, caption style, and visual structure independent of one Topic. A Persona owns voice and identity. A Product owns category, description, brand media, promotion truth, and CTA targets. A Generation is immutable output assembled from those reusable objects.

Persona Plan ownership is stronger than an ordinary reference: a live plan can block Persona deletion. Product CTA targets point to media assets rather than uploading files themselves.

## Shortcuts

| Situation | Start with |
| --- | --- |
| Evidence-to-Format extraction | `museoncli asset +create` |
| Canonical Product category | `museoncli asset +options` |
| Existing object review | `museoncli asset +get` |
| CTA media preparation | `museoncli asset +create` |

## DON'T

- **DON'T** encode a one-off generation adjustment into a reusable asset without intent.
- **DON'T** confuse a Topic with a Format or a Persona with per-post copy.
- **DON'T** retry a Persona deletion unchanged after the server names a blocking Persona Plan.
- **DON'T** manufacture IDs; carry canonical IDs from reads.

## Relationships

Move to generation after inputs are reviewed, account-publish for pool binding, or Agentic Campaign to change a Persona held by a live plan.

## Batch Topic creation

Creating several Topics is one create call carrying one top-level `topics` array. Each Topic uses
the canonical write contract: `title` for the name, `narrative` for its content direction, `tags`
for the tag strings — never `name` or `description` in their place.

User-authored Topic text routinely contains quotes and other shell-sensitive characters, so the
payload is never hand-built or interpolated into a shell string. Serialize a native structure to
JSON (`ensure_ascii=False`) and pass the serialized string as a single argv element. That
serializer wrapper is the only scripting allowed here; item-by-item shell or Python loops are not,
and a temporary payload file is never written, inspected, or repaired.

When the response returns one result per requested Topic with canonical ids or refs, those are the
verification — no per-Topic read-back. Other asset types stay separately managed and must not be
folded into this batch.
