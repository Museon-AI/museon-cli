# Changelog

Museon CLI follows semantic versioning for its package and command contract.

## Unreleased

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
