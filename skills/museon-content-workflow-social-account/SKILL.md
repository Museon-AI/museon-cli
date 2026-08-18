---
name: museon-content-workflow-social-account
description: "Connect and inspect Museon social accounts, manage one-account configuration and schedule state, edit profiles, and read performance provenance."
metadata:
  requires:
    bins: ["museoncli"]
    skills: ["museon-content-workflow-base"]
  cliHelp: "museoncli schema social-account"
---

# Museon social account workflow

**CRITICAL — first read [`../museon-content-workflow-base/SKILL.md`](../museon-content-workflow-base/SKILL.md).**

## Mental model

A social account has connection state, publish configuration, asset bindings, versioned config,
schedule items, profile state, and performance. This Skill owns precise one-account work; batch
pool/schedule plans belong to account-publish. Performance can come from authorized analytics or
public fallback and must retain provenance. See [account-state.md](references/account-state.md).

## Shortcuts

| Situation | Start with |
| --- | --- |
| Resolve known accounts | `museoncli social-account +list` |
| Connect user-owned account | `museoncli social-account +connect-link-create` |
| Read one account's bindings | `museoncli social-account +assets-get` |
| Read publish configuration | `museoncli social-account +config-get` |
| Read schedule item | `museoncli social-account +schedule-get` |
| Read performance | `museoncli social-account +performance-get` |
| Draft profile changes | `museoncli social-account +profile-edit-draft` |

## DON'T

- **DON'T** concatenate handles or page-scan account lists when resolving several known handles.
- **DON'T** expect `+list` to contain publish asset bindings; read the owning asset surface.
- **DON'T** loop one-account asset/config writes for a multi-account change.
- **DON'T** alter a fully-managed account's assets without relaying impact and obtaining approval.
- **DON'T** describe public-data fallback as official analytics or an API delay.
- **DON'T** ask users for social-platform passwords; return the authorization link.

## Relationships

Account-publish owns multi-account pools and schedule plans. Agentic Campaign owns fully-managed
membership and operations. Assets owns reusable objects; campaign-monitor owns synced history.
