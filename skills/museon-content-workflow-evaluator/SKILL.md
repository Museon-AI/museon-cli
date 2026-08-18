---
name: museon-content-workflow-evaluator
description: "Discover, manage, and run Museon prompt-based evaluators against text, media, research, or generation output, then inspect run history."
metadata:
  requires:
    bins: ["museoncli"]
    skills: ["museon-content-workflow-base"]
  cliHelp: "museoncli schema evaluator"
---

# Museon evaluator workflow

**CRITICAL — first read [`../museon-content-workflow-base/SKILL.md`](../museon-content-workflow-base/SKILL.md).**

## Mental model

An evaluator kind classifies purpose; an evaluator definition stores prompt/metadata/visibility;
an evaluator run binds one definition to supported text, media, research, or generation output.
Definitions and run history are separate object sets. See [evaluation-model.md](references/evaluation-model.md).

## Shortcuts

| Situation | Start with |
| --- | --- |
| Discover configured kinds | `museoncli evaluator +kind-list` |
| Find available definition | `museoncli evaluator +list` |
| Inspect definition | `museoncli evaluator +get` |
| Evaluate an output | `museoncli evaluator +run` |
| Review run history | `museoncli evaluator +run-list` |

## DON'T

- **DON'T** invent an evaluator kind or input shape absent from live schema.
- **DON'T** confuse a definition ID with a run ID.
- **DON'T** create/update definitions without the required elevated workspace role.
- **DON'T** mutate a definition merely to preserve one run's result.
- **DON'T** report an evaluation without retaining the evaluated source object's identity.

## Relationships

Research and generation supply common inputs; Agentic Campaign has its own campaign evaluation
memory; artifacts can retain a user-facing evaluation report.
