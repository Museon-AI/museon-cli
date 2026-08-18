# Evaluator command surface

Extracted from `museoncli/domains/evaluator.py`; inspect exact schema before use.

| Command | Risk/execution | Summary and key inputs |
| --- | --- | --- |
| `museoncli evaluator +kind-list` | read/direct | List configured evaluator kind keys; schema supports visibility filtering. |
| `museoncli evaluator +list` | read/direct | List definitions available to the current agent runtime; may filter by kind. |
| `museoncli evaluator +get` | read/direct | Read one definition by evaluator UUID. |
| `museoncli evaluator +create` | write/direct | Create one prompt-based definition from kind, name, and prompt content/file; supports dry run and requires workspace admin or staff. |
| `museoncli evaluator +update` | write/direct | Update prompt, metadata, or visibility by UUID; supports dry run and requires workspace admin or staff. |
| `museoncli evaluator +run` | write/direct | Run against schema-supported text, media, research, or generation input; supports dry run. |
| `museoncli evaluator +run-list` | read/direct | List workspace evaluator runs, including schema-supported filters. |
| `museoncli evaluator +run-get` | read/direct | Read one evaluator run by returned run UUID. |

All writes follow the base skill's separate-approval policy. Never invent an input type or evaluator kind absent from the current schema.
