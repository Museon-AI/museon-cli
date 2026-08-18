# Evaluation model

## Mental model

Kinds are workspace configuration; definitions are prompt-based evaluators visible to the agent runtime; runs are immutable applications of a definition to a supported source. Definition administration and evaluation execution have different authority boundaries.

## Shortcuts

| Object | Start with |
| --- | --- |
| Definition catalog | `museoncli evaluator +list` |
| Definition administration | `museoncli evaluator +get` |
| New evaluation | `museoncli evaluator +run` |
| One prior run | `museoncli evaluator +run-get` |

## DON'T

- **DON'T** treat list visibility as authority to administer a definition.
- **DON'T** infer unsupported media/research/generation inputs from prior runs.
- **DON'T** overwrite definition history to change an evaluation outcome.
- **DON'T** detach a reported verdict from its source and evaluator definition.

## Relationships

The source Skill establishes evidence/output semantics. Evaluator adds a structured verdict; artifacts adds durable presentation.
