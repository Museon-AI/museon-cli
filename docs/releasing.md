# Releasing Museon CLI

Public installation is npm-first. The Python wheel remains a verified GitHub
release asset for Museon's private runtime; it is not sent to a Python package
registry. Before the npm release exists, the public guide uses an immutable,
reviewed source snapshot as its `uv` fallback.

## Launch gates and one-time setup

Publication is intentionally fail-closed until every external registry and
signing prerequisite below is complete:

1. Keep the repository `LICENSE`, `pyproject.toml`, wheel metadata, and npm
   package metadata aligned on Apache-2.0.
2. Confirm that Museon controls the `@museon` npm scope. An npm scope owner
   must create the first version of all seven packages if trusted publishing
   cannot create a new scoped public package:
   - `@museon/cli`
   - `@museon/cli-darwin-arm64`
   - `@museon/cli-darwin-x64`
   - `@museon/cli-linux-arm64-gnu`
   - `@museon/cli-linux-x64-gnu`
   - `@museon/cli-win32-x64`
   - `@museon/cli-win32-arm64`
3. Configure an npm trusted publisher for every package: owner `Museon-AI`,
   repository `museon-cli`, workflow `release.yml`, environment `npm`. Create
   and protect that GitHub environment. The workflow uses Node 22.14 or newer,
   npm 11.5.1 or newer, and GitHub OIDC; no long-lived registry token remains
   after the one-time bootstrap.
   For the first publication only, create a granular npm token that can publish
   public packages under `@museon`, store it as the protected `npm` environment
   secret `MUSEON_NPM_BOOTSTRAP_TOKEN`, and approve that deployment. After all
   seven packages exist, configure their trusted publishers and delete the
   bootstrap secret before the next release.
4. Protect `main` and `v*` tags. Require CI before a release tag can be created.
5. Create a protected GitHub environment named `native-signing`. Configure
   Developer ID/notarization secrets `MUSEON_APPLE_CERTIFICATE_P12_BASE64`,
   `MUSEON_APPLE_CERTIFICATE_PASSWORD`, `MUSEON_APPLE_SIGNING_IDENTITY`,
   `MUSEON_APPLE_NOTARY_KEY_P8_BASE64`, `MUSEON_APPLE_NOTARY_KEY_ID`, and
   `MUSEON_APPLE_NOTARY_ISSUER_ID`. Configure Authenticode secrets
   `MUSEON_WINDOWS_CERTIFICATE_PFX_BASE64` and
   `MUSEON_WINDOWS_CERTIFICATE_PASSWORD`; optionally set
   `MUSEON_WINDOWS_TIMESTAMP_URL` as an environment variable.
6. Review the generated third-party notices for every native target. The native
   build records the notice hash and package count; npm verification requires
   those notices and the approved project license in every artifact.
7. Install a GitHub App on `Museon-AI/museon` with permission to dispatch
   repository events and only the `Contents: write` repository permission.
   Configure its numeric App ID as
   `MUSEON_RUNTIME_APP_ID` and its private key as
   `MUSEON_RUNTIME_APP_PRIVATE_KEY`. The workflow mints a short-lived token;
   do not use a long-lived personal access token.

`uv run python scripts/verify_release_prerequisites.py` enforces the repository
license and package-metadata gates before any release job can publish. Later
jobs fail closed unless notices are complete, macOS bundles have a Developer ID
signature and accepted notarization, and every Windows PE file has a valid,
timestamped Authenticode signature.

## Release sequence

1. Change only `[project].version` in `pyproject.toml`, update `uv.lock`, docs,
   the bundled Skill, and changelog, then regenerate the contract. The npm
   manifests are generated from `pyproject.toml`; do not commit copied versions.
2. Run the validation documented in `CONTRIBUTING.md`, including native smoke on
   the available local platform.
3. Merge to `main`, sync the command contract and install guide to the private
   runtime, and verify the live guide.
4. Create the protected tag `v<version>` on the reviewed `main` commit. The
   workflow verifies the tag/version and main ancestry, creates or reuses a
   draft GitHub release, and builds the exact wheel once.
5. Each supported runner builds its PyInstaller onedir bundle from that same
   reviewed wheel, records the wheel and notice hashes, and runs the native
   smoke. macOS runners then apply Developer ID signing and submit the exact
   bundle for notarization; Windows signs and timestamps every PE file. Only
   after signature verification does the runner generate its exact-version npm
   platform package and prepack native/npm assets. The root npm package is
   packed separately and verified with the six platform tarballs.
6. Upload the already-packed npm tarballs, native archives, wheel, sdist,
   contract, checksums, and SBOM to the draft release. Existing release assets
   are skipped only after byte-for-byte hash verification; a mismatch aborts.
7. Publish the six platform packages first. Publish `@museon/cli` only after
   all six succeed. If a version exists, compare its registry integrity with
   the prepacked tarball: identical packages are skipped and mismatches abort.
8. Publish the GitHub release only after assets and registries are complete,
   then dispatch the exact wheel URL/hash and contract URL/hash to the private
   runtime.

Never rebuild between verification, attachment, and publication. A rerun must
reuse the same prepacked artifacts or stop on an integrity mismatch.
