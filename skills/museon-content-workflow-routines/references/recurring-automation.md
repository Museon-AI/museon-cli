# Recurring automation

Inspect `museoncli schema routines` before proposing automation.

1. Define recurring outcome, inputs, owner, trigger, report destination, approval boundaries, and surviving memory.
2. Read existing routines before creating a duplicate.
3. Prefer a draft while user review is needed.
4. Explain exact trigger and future writes, obtain explicit approval, then create or accept.
5. Verify active trigger and ownership after writing.
6. On later runs, read memory first and record only durable facts, decisions, successful patterns, failures worth avoiding, and next-state context.

Only change, pause, resume, rebuild, or cancel routines owned by the current operator. If another owner is returned, surface ownership rather than taking control.
