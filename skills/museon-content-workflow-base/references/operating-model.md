# Operating model

## Mental model

Read state before proposing change. Read commands may directly serve the task; writes and destructive actions remain proposals until separately approved. Async work has a returned handle, a matching status command, and server-owned wakeup guidance. A returned `ref` is an opaque presentation object, not a URL template.

Runtime Business Skills are workspace-visible strategy/methodology. List them before strategic, research, audit, review, onboarding, or operating-plan work; load every directly relevant one. Bundled workflow Skills instead teach the host Agent how to operate the CLI.

Authentication recovery begins only after `missing_auth`, `unauthorized`, or missing-workspace failure: start browser authorization, show `verification_uri_complete`, wait with `auth finish`, select a workspace when needed, then resume the original task.

## Shortcuts

| Situation | Start with |
| --- | --- |
| Exact command contract | `museoncli schema <domain.shortcut>` |
| Relevant runtime methodology | `museoncli skills +list` |
| Async progress | Matching domain status/get shortcut |
| Large offloaded JSON | Read/search the manifest path in bounded chunks |
| Failed authentication | `museoncli auth start` |

## DON'T

- **DON'T** guess Business Skill names from memory; list them or load a user-named one.
- **DON'T** poll on an invented interval when the response supplies a wakeup delay.
- **DON'T** paste large offloaded JSON back into conversation or treat its manifest as missing data.
- **DON'T** ask users to authenticate in another terminal when this Agent environment needs access.
- **DON'T** claim a write succeeded until the owning domain's read/status surface confirms it.

## Relationships

All domain Skills depend on this contract. They own object-specific state machines and anti-patterns; this reference owns cross-domain discovery, approval, recovery, async, and presentation rules.
