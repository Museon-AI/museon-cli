# Releasing Museon CLI

Releases are built from a published GitHub Release and published to PyPI with
Trusted Publishing. No long-lived PyPI token belongs in GitHub secrets.

## One-time setup

1. Choose and add the repository's open-source license.
2. Create the `museoncli` project on PyPI.
3. Configure a PyPI Trusted Publisher for:
   - owner: `Museon-AI`
   - repository: `museon-cli`
   - workflow: `release.yml`
   - environment: `pypi`
4. Create a protected GitHub environment named `pypi`.
5. Configure a `main` ruleset/branch protection policy that requires CI and
   protects release tags.
6. Enable private vulnerability reporting, Dependabot alerts, secret scanning,
   and code scanning before announcing the public repository.
7. Add a fine-grained `MUSEON_RUNTIME_DISPATCH_TOKEN` Actions secret with
   permission to send repository-dispatch events to the private
   `Museon-AI/museon` repository. This token does not publish packages and must
   not be available to pull-request workflows.
8. Restrict the repository Actions policy to the Actions used by this project
   and require full-length commit SHA pins. The checked-in workflows are already
   pinned; Dependabot keeps those references current.

## Release checklist

1. Update the version in `pyproject.toml`, refresh `uv.lock`, update the
   immutable GitHub fallback tag in `docs/install.md`, both READMEs, and the
   bundled Skill, then regenerate the command contract. Tests enforce that all
   fallback tags match the package version. Package metadata is the single
   runtime version source; runtime code reads it through `importlib.metadata`.
2. Run the complete local validation from `CONTRIBUTING.md`.
   This includes the wheel/sdist public-boundary scanner and a clean-venv smoke
   install. CI repeats the install and Agent Skill checks on Linux, macOS, and
   Windows.
3. Merge the release change to `main`.
4. Sync `contracts/command-catalog.json` and `docs/install.md` into the private
   monorepo, deploy its API/Web/Agent changes, and verify the live onboarding
   guide before publishing the release.
5. Create a GitHub Release whose tag is exactly `v<package-version>` and points
   to a commit reachable from `main`. The workflow fetches `origin/main` and
   refuses releases from side branches even when the version and tag match.
6. The release workflow verifies the tag and commit ancestry, rebuilds from source, audits and
   tests the package, publishes to PyPI, and attaches the wheel, sdist, command
   contract, checksums, and SPDX SBOM to the release. Public releases also get
   GitHub provenance and SBOM attestations.
7. After PyPI publishing and asset upload succeed, the workflow dispatches the
   immutable wheel and command-contract URLs and hashes to the private Agent
   runtime. If the dispatch secret is intentionally absent, run the monorepo
   runtime release workflow manually with those four values.

The private Museon Agent runtime consumes only a hash-verified release wheel.
It also rejects the release when its public command contract differs from the
API's reviewed snapshot. Runtime dispatch accepts only the canonical wheel and
contract URLs from the same `Museon-AI/museon-cli` GitHub Release; it never
builds from either repository checkout.
