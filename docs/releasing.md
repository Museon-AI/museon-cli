# Releasing Museon CLI

Museon CLI is distributed as one Python wheel attached to an official GitHub
Release. Users and Museon's private Agent runtime install the same reviewed
wheel; the private runtime adds its own overlay afterward.

## Release sequence

1. Update `[project].version` in `pyproject.toml`, refresh `uv.lock`, and update
   the versioned wheel URL in the README, install guide, and bundled Skill.
2. Regenerate the command docs and contract, then run the checks in
   `CONTRIBUTING.md`.
3. Merge the CLI changes to `main`, then create tag `v<version>` on that reviewed
   commit.
4. The release workflow verifies the tag and `main` ancestry, runs the Python
   test suite, builds the wheel once, checks its public boundary,
   and performs a clean wheel install.
5. The workflow publishes the wheel, command contract, install guide,
   and SHA-256 checksums in a GitHub Release.
6. After publication, the workflow sends the exact wheel URL/hash and command
   contract URL/hash to the private Agent runtime release workflow.
7. Verify the public wheel URL, then sync the command contract and install guide
   to the Museon monorepo. The live guide must never point at an unpublished
   wheel.

Do not rebuild or replace assets for an existing tag. If a published version is
wrong, fix it on `main` and release a new patch version.
