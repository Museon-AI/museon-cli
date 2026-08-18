---
name: museon-content-workflow-social-account
description: "Connect, inspect, configure, schedule, publish, and review one Museon social account, including account assets, hashtags, BGM, and performance provenance."
---

# Museon social account workflow

Use for the `social-account` domain and precise one-account work.

| Command family | Purpose |
| --- | --- |
| `museoncli social-account +list/+get` | Resolve accounts and inspect state |
| `+connect-link-create/+connect-link-status` | Connect a user-owned platform account |
| `+assets-get/+assets-set`, `+config-get/+config-update` | One-account assets and publish config |
| `+schedule-list/+schedule-get` | Planned posts and generation state |
| `+performance-get` | Performance with source provenance |

## References

- [account-connection-and-state.md](references/account-connection-and-state.md): canonical IDs,
  authorization links, precise edits, publishing, and performance provenance.
- Inspect `museoncli schema social-account` and the exact shortcut before use.

## Cross-skill handoff

For multi-account asset pools or schedule plans, use `museon-content-workflow-account-publish`.
For fully managed fleet lifecycle, use `museon-content-workflow-account-operation`; for missing
creative assets, use `museon-content-workflow-assets`.
