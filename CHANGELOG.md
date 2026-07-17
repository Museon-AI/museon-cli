# Changelog

Museon CLI follows semantic versioning for its package and command contract.

## Unreleased

- Added an immutable official GitHub release fallback so Agent onboarding can
  recover when `museoncli` is not yet available from the configured registry.
- Prepared the standalone public CLI and Agent Skill.
- Added Museon browser authorization with revocable, expiring credentials.
- Added OS-keyring credential storage with a secure headless fallback.
- Added `museoncli setup --agent` for Codex, Claude Code, and Cursor.
- Added capability and authorization metadata to the portable command contract.
- Removed service-provider and model-selection controls from the public command surface.
- Added release checksums, SPDX SBOM, attestations, dependency auditing, and private runtime dispatch.
