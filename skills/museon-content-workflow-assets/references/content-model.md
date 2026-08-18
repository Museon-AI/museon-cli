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
