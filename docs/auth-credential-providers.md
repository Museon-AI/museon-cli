# Authentication credential providers

Museon CLI resolves authentication through an explicit authentication mode. It
does not merge agent capabilities and user API keys into one fallback chain.

## Agent-managed sessions

An Agents sandbox writes a non-secret descriptor to the configured
`config.json` and a short-lived credential lease beside it:

```text
<config directory>/
├── config.json
└── secrets/museon-api.lease.json
```

The descriptor selects `method=agent_capability`, `provider=agent_session`, and
`secret_ref=museon-api`. The mode-0600 lease contains the current `mcap_` value,
expiry, and version. Museon CLI reads the lease for every invocation and never
copies it into the system keyring or `credentials.json`.

This mode is exclusive. A missing, invalid, or expired lease fails closed; the
CLI does not fall back to `MUSEON_API_KEY`, a keyring entry, a protected file,
or browser authorization. `auth status` reports the provider and lease state,
while `auth login`, `auth start`, `auth finish`, and `auth logout` return
`managed_auth` because the Agents host owns renewal and revocation.

## User API keys

Outside an agent-managed session, API-key resolution keeps the existing
precedence:

1. `MUSEON_API_KEY`
2. operating-system keyring
3. mode-0600 `credentials.json`
4. legacy inline config value

The resolver changes only where the credential is obtained. Museon's server
still owns API-key scopes, workspace authorization, revocation, and usage
accounting.

## Legacy capability compatibility

An inline `mcap_` value from an older Agents runtime takes precedence over any
stale persisted credential. Museon CLI does not migrate that capability into a
persistent credential provider. This compatibility rule prevents an expired
bootstrap credential from shadowing a fresh turn credential while sandboxes
move to the lease contract.
