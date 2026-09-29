# museoncli surface conventions

The rules below are enforced by `tests/test_surface_conventions.py`. New commands
must pass without touching any allowlist.

## Command shape

```
museoncli <domain> +<action> [flags]              # flat domains (media, research, ...)
museoncli <domain> <resource> +<action> [flags]   # hireaicreator, ai-slideshow
```

- Domains come from the fixed `Domain` enum (`museoncli/domains/_model.py`).
  Built-in commands (`auth`, `workspace`, `schema`, `config`, ...) use plain verbs.
- Actions always carry the `+` sigil. No bare aliases.
- Target shape for new commands is `<domain> <resource> +<verb>`: nouns belong in
  the resource, the action is a verb. Do not fold a second noun into the action
  (`+creator-list`, `+asset-pools-batch-set`); existing ones migrate with aliases.
- Verbs: `list / get / create / update / delete / cancel`, `set` (full replacement),
  `add / remove` (child collections), plus domain verbs that the spec `summary`
  explains (e.g. `upload`, `import`, `preview`, `generate`). One word per meaning:
  `update`, not `patch`; `get`, not `status` / `poll`.
- `batch` names a batch entity (a generation batch). An operation over many
  records takes several IDs on the same verb, or `bulk-<verb>`.
- Each command has one capability key (`<domain>.<resource>-<action>`) and one
  CLI path; `museoncli schema` accepts either, and both are unique.

## Identifiers

- The id of the entity a command returns or acts on is always `--id`.
  (`routines +get --id`, `content-analysis +get --id`, `media +get --id`)
- Write commands scoped inside a parent entity use `--id` for the parent and
  qualified flags for children (`campaign-monitor +content-remove --id <campaign>
  --collection-content-id <content>`).
- Foreign references are always qualified: `--<entity>-id`.
- Positional IDs are forbidden. The only allowed positional is a mode selector
  (`routines +record output|memory`).
- ID values must be canonical UUIDs; the CLI rejects placeholders before any request.

## Pagination

- Offset-paged lists: `--page` (1-based) + `--page-size`. Never `--offset`, never
  `--limit` for paging.
- Cursor-paged lists: `--cursor` (pass back `pagination` tokens from responses).
- `--limit` exists only as a true "top N" cap where the server has no paging
  (research searches, performance series, content windows).

## Enum flag values

- All choice values are kebab-case on the CLI (`--intent keyword-search`,
  `--type content-analysis`).
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

- JSON on stdout, always, including usage errors: `{"ok": true, ...}` /
  `{"ok": false, "command", "reason", "detail", "error"}`.
- `error` is the stable failure shape: `code` (same category as `reason`),
  `message`, `server_code` (the service's own code, e.g. `version_conflict`,
  `UPLOADED_SCHEDULE_PAST`, when it sent one), `http_status`, `retryable`, and
  `hint` for usage errors. `reason` is a fixed category (`invalid_input`,
  `not_found`, `conflict`, `forbidden`, `unauthorized`, `missing_auth`,
  `rate_limited`, `server_error`, `service_unavailable`, `network_error`,
  `usage_error`, `confirmation_required`, `command_failed`, ...), never an
  exception class name.
- Exit codes: `0` success, `1` failure, `2` usage error, `3` not found,
  `4` authentication required, `5` conflict, `130` interrupted. The envelope
  remains the source of truth.
- Paged reads add `page_info` (`page`, `page_size`, `total`, `total_pages`,
  `has_more`, `next_cursor`) whatever shape the domain returns. Read commands
  with `--page` also take `--all`, which follows every page and reports
  `page_info.complete`; hitting its cap is a warning, not silent truncation.
- In the agent sandbox only, a successful JSON result above the configured size
  threshold becomes an `ok:true`, `status:large_json_offloaded` manifest. The
  complete unchanged JSON is written under a private six-hour-TTL result root
  inside the host operating system's temporary directory. The manifest provides
  narrow jq templates on POSIX hosts and PowerShell templates on Windows.
  Non-agent CLI output is unchanged.

## Help and examples

- Every flag prints help. Common flags and schema descriptions fill gaps
  automatically (`museoncli/domains/_discovery.py`); write a description on the
  input schema when the derived text is not specific enough.
- Every command shows at least one runnable example; when a spec only lists
  `museoncli schema <self>`, one is generated from its required inputs. Tests
  parse every example with the real parser.
- Summaries may only reference shortcuts that exist.

## Extending

Add a command by editing exactly one domain module in `museoncli/domains/`:
`CommandSpec` + `_add_*_arguments` + `_build_*_arguments` + executor +
`EXECUTORS` entry, plus focused tests. `tests/test_surface_conventions.py` and
the spec↔executor 1:1 test keep the surface honest.
