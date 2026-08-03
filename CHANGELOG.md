# Changelog

Museon CLI follows semantic versioning for its package and command contract.

## Unreleased

- Added `agentic-campaign proposal +reallocate` to move managed accounts into a
  Plan from another Plan in the same Campaign or from the recruitable pool, as a
  reviewable allocation Proposal.
- Added `agentic-campaign +overview` (workspace-wide Campaign summary) and
  `+recap` (per-Campaign decision history, signals, and learnings).
- Added `--rollout-coverage-mode`/`--rollout-days` (schedule-rollout intent
  carried on the Proposal) and `--rationale` to `proposal +create`/`+revise`.
- Added `--direction-brief`/`--success-hypothesis`/`--contract` to
  `+campaign-create`.
- Removed the private Issue pull session assertion requirement; Agentic
  Campaign Issue claims now require one campaign as the candidate boundary and
  use the runtime conversation identity only for lease and message context,
  together with the workspace-bound CLI credential.
- Required `--agentic-persona-plan-id` for `account-operation +submit` and
  `+submit-batch`, forwarding the plan-owned persona admission context to the
  API and retiring per-account persona assignment for linked operations.
- Added `--preferred-publish-time` (24h `HH:MM`) and `--publish-timezone` (IANA)
  to `account-operation +submit` / `+submit-batch`, forwarded to the API and
  stored on the operation so the daily routine schedules posts at that local
  time (batch value is shared across the accounts).
- Added `social-account +config-batch-update` to set publish settings (output
  language, required hashtags, approval-before-publish) on up to 200 accounts in
  one synchronous call, so multi-account config edits no longer loop
  `+config-update`.
- Added canonical product-category discovery, type-specific product schemas,
  server-validated product dry-runs, generated command help, and structured API
  validation details.
- Licensed Museon CLI under the Apache License 2.0.
- Standardized public installation and private runtime updates on the same
  reviewed GitHub Release wheel.
- Changed update discovery to explicit opt-in GitHub release metadata; local-only
  commands remain offline.
- Made large-result offloading portable across supported platforms, including
  system temporary directories and bounded PowerShell query templates on Windows.
- Prepared the standalone public CLI and Agent Skill.
- Added Museon browser authorization with revocable, expiring credentials.
- Added OS-keyring credential storage with a secure headless fallback.
- Added `museoncli setup --agent` for Codex, Claude Code, and Cursor.
- Added capability and authorization metadata to the portable command contract.
- Removed service-provider and model-selection controls from the public command surface.
- Added release checksums, dependency auditing, and private runtime dispatch.
