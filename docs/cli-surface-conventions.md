# museoncli surface conventions

The rules below are enforced by `tests/test_surface_conventions.py`. New commands
must pass without touching any allowlist.

## Command shape

```
museoncli <domain> +<shortcut> [flags]
```

- Domains come from the fixed `Domain` enum (`museoncli/domains/_model.py`).
- Shortcuts always carry the `+` sigil. No bare aliases.
- Verbs: `list / get / create / update / delete / cancel` plus domain verbs that
  the spec `summary` explains (e.g. `schedule-generate`, `version-activate`).

## Identifiers

- The id of the entity a command returns or acts on is always `--id`.
  (`routines +get --id`, `content-analysis +get --id`,
  `social-account +connect-link-status --id`)
- Write commands scoped inside a parent entity use `--id` for the parent and
  qualified flags for children (`social-account +schedule-update --id <account>
  --schedule-item-id <item>`, `account-operation +strategy-decide --id <op> --run-id <run>`).
- Foreign references are always qualified: `--<entity>-id`.
- Positional IDs are forbidden. The only allowed positional is a mode selector
  (`routines +record output|memory`).
- ID values must be canonical UUIDs; the CLI rejects placeholders before any request.

## Pagination

- Offset-paged lists: `--page` (1-based) + `--page-size`. Never `--offset`, never
  `--limit` for paging.
- Cursor-paged lists: `--cursor` (pass back `pagination` tokens from responses).
- `--limit` exists only as a true "top N" cap where the server has no paging
  (research searches, performance series, evaluator lists).

## Enum flag values

- All choice values are kebab-case on the CLI (`--intent keyword-search`,
  `--decided-by auto-timeout`, `--type topic-direction`).
- Builders convert to server contract values with `dekebab`; payloads stay
  snake_case. Schemas (`museoncli schema`) advertise the kebab forms.

## Safety

- `risk_level`: `read` / `write` / `destructive`.
- Every `write` and `destructive` command supports `--dry-run` (generic
  short-circuit in dispatch; no API call is made).
- `destructive` commands set `requires_confirmation` and demand `--yes`;
  without it the CLI returns `{"ok": false, "reason": "confirmation_required"}`.
  Agents must confirm with the user, then retry with `--yes`.
- Provider identity, model selection, credentials, storage buckets, queue names,
  and other service implementation controls are server-owned. They must not
  appear as public flags or schema fields, and structured arguments that try to
  inject them are rejected.

## Output contract

- JSON on stdout, always: `{"ok": true, ...}` / `{"ok": false, "reason", "detail"}`.
- In the agent sandbox only, a successful JSON result above the configured size
  threshold becomes an `ok:true`, `status:large_json_offloaded` manifest. The
  complete unchanged JSON is written under a private six-hour-TTL result root
  inside the host operating system's temporary directory. The manifest provides
  narrow jq templates on POSIX hosts and PowerShell templates on Windows.
  Non-agent CLI output is unchanged.
- Exit codes: `0` success, `1` failure (reason in envelope), `2` usage error,
  `130` interrupted. The envelope, not the exit code, is the source of truth.

## Extending

Add a command by editing exactly one domain module in `museoncli/domains/`:
`CommandSpec` + `_add_*_arguments` + `_build_*_arguments` + executor +
`EXECUTORS` entry, plus focused tests. `tests/test_surface_conventions.py` and
the spec↔executor 1:1 test keep the surface honest.
