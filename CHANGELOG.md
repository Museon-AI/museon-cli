# Changelog

Museon CLI follows semantic versioning for its package and command contract.

## Unreleased

- Added canonical product-category discovery, type-specific product schemas,
  server-validated product dry-runs, generated command help, and structured API
  validation details.
- Made exact-version npm installation the primary public distribution path,
  backed by six optional native platform packages and a dependency-free CJS
  launcher with no lifecycle scripts or runtime downloads.
- Added a native Windows ARM64 package built and tested on GitHub's Windows 11
  ARM runner.
- Licensed Museon CLI under the Apache License 2.0.
- Added reviewed-wheel PyInstaller onedir builds, native/npm smoke tests,
  package-boundary verification, and an immutable GitHub/uv wheel fallback.
- Added locked-environment third-party notices plus fail-closed Developer ID,
  Apple notarization, and timestamped Authenticode release verification.
- Changed update discovery to explicit opt-in GitHub release metadata and
  npm-specific upgrade guidance; local-only commands remain offline.
- Made large-result offloading portable across supported platforms, including
  system temporary directories and bounded PowerShell query templates on Windows.
- Prepared the standalone public CLI and Agent Skill.
- Added Museon browser authorization with revocable, expiring credentials.
- Added OS-keyring credential storage with a secure headless fallback.
- Added `museoncli setup --agent` for Codex, Claude Code, and Cursor.
- Added capability and authorization metadata to the portable command contract.
- Removed service-provider and model-selection controls from the public command surface.
- Added release checksums, SPDX SBOM, attestations, dependency auditing, and private runtime dispatch.
