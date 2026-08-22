---
name: museon-content-workflow-social-account
description: "Connect and inspect Museon social accounts, prepare an account-bound Android cloud-phone session, manage one-account configuration and schedule state, edit profiles, and read performance provenance."
metadata:
  requires:
    bins: ["museoncli"]
    skills: ["museon-content-workflow-base"]
  cliHelp: "museoncli schema social-account"
---

# Museon social account workflow

**CRITICAL — first read [`../museon-content-workflow-base/SKILL.md`](../museon-content-workflow-base/SKILL.md).**

## Mental model

A social account has connection state, publish configuration, bindings, schedule, profile, and performance.
This Skill owns precise one-account work; batch plans belong to account-publish. Preserve performance provenance. See [account-state.md](references/account-state.md).

## Shortcuts

| Situation | Start with |
| --- | --- |
| Resolve known accounts | `museoncli social-account +list` |
| Operate the account-bound Android session in Mel | `museoncli social-account +adb-connect --id <account_uuid>` |
| Connect user-owned account | `museoncli social-account +connect-link-create` |
| Read one account's bindings | `museoncli social-account +assets-get` |
| Read publish configuration | `museoncli social-account +config-get` |
| Read schedule item | `museoncli social-account +schedule-get` |
| Read performance | `museoncli social-account +performance-get` |
| Draft profile changes | `museoncli social-account +profile-edit-draft` |

## Account-bound Android session

- Resolve the canonical account UUID with `+list`; never substitute a device id, idle phone, or platform handle.
- In Mel, run `museoncli social-account +adb-connect` only for requested device work; `--dry-run` contacts neither cloud phone nor local ADB.
- The command resolves the account-bound phone, prepares and authenticates local ADB, checks state, and returns only a serial; never handle provider credentials.
- Keep that serial for the sandbox session: native `adb -s <serial> ...` and `u2cli -s <serial> ...` reuse it. Do not reconnect before every tap or dump.
- If `adb -s <serial> get-state` is not `device`, reconnect once; do not invent a keepalive or stop the phone.
- For UI work, use `uiautomator2`: screenshot after navigation, compressed `dump-hierarchy` first, and verified semantic selectors before coordinates.

## DON'T

- **DON'T** concatenate handles or page-scan account lists when resolving several known handles.
- **DON'T** expect `+list` to contain publish asset bindings; read the owning asset surface.
- **DON'T** loop one-account asset/config writes for a multi-account change.
- **DON'T** alter a fully-managed account's assets without relaying impact and obtaining approval.
- **DON'T** describe public-data fallback as official analytics or an API delay.
- **DON'T** ask users for social-platform passwords; return the authorization link.
- **DON'T** persist connection endpoints or temporary authentication material, or manufacture human-like behavior to bypass a platform.

## Relationships

Account-publish owns multi-account pools/plans; Agentic Campaign owns fully-managed operations; Assets owns reusable objects; campaign-monitor owns synced history.
