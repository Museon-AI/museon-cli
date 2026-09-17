# Format maintenance

Use `format +tags` to discover workspace tags and `format +warmup-readiness`
with explicit Format IDs to read the current readiness revisions and issues.
These commands do not start processing or publication.

For edits, first read `format +get --id ID`, then use `format +patch` with the
returned `expected_version`. The API permits omitting the version; doing so
loses the caller's stale-edit check. Name, BGM ID, POV ID and playbook override
are independently optional, but at least one non-null change is required.
An empty `viral_playbook_override` string clears the manual override. Null does
not clear BGM or POV links. Omitted fields remain omitted on the wire.

`format +retry --id ID --step STEP --yes` retries exactly one of `ingest`,
`hook`, `pov`, `bgm`, or `viral`. Inspect current detail/errors first and poll
that step afterward; a successful receipt does not mean analysis completed.
The server offers neither a version precondition nor an idempotency header for
retry. Reconcile an uncertain response before requesting another retry.

`format +delete --id ID --yes` deletes the Format. Read its current detail and
workspace first; this endpoint has no version parameter. A 204 receipt has no
JSON body. Verify not-found afterward. All three writes support `--dry-run`
without network requests; retry and deletion require explicit confirmation.
