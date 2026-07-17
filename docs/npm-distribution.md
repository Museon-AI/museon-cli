# npm distribution contract

Museon CLI's public installer is the dependency-free CommonJS package
`@museon/cli`. Version `0.3.60` installs with:

```bash
npm install --global @museon/cli@0.3.60
```

The root package exposes both `museoncli` and `museon`. At runtime it chooses
one exact-version optional dependency:

| Host | npm package | GitHub runner |
| --- | --- | --- |
| macOS arm64 | `@museon/cli-darwin-arm64` | `macos-15` |
| macOS x64 | `@museon/cli-darwin-x64` | `macos-15-intel` |
| Linux arm64, glibc | `@museon/cli-linux-arm64-gnu` | `ubuntu-22.04-arm` |
| Linux x64, glibc | `@museon/cli-linux-x64-gnu` | `ubuntu-22.04` |
| Windows x64 | `@museon/cli-win32-x64` | `windows-2025` |
| Windows arm64 | `@museon/cli-win32-arm64` | `windows-11-arm` |

Linux musl is not supported. The launcher verifies that the native package has
the root package's exact version, then spawns its executable with inherited
arguments and stdio. It preserves the native exit code or signal and adds only
`MUSEONCLI_DISTRIBUTION_CHANNEL=npm` to the child environment. Missing optional
dependencies, version skew, musl, and unsupported hosts produce actionable
errors. There are no `preinstall`, `install`, or `postinstall` scripts and no
install-time or runtime download.

## Native payload

Each platform package contains a PyInstaller onedir bundle built from the same
reviewed `museoncli-<version>-py3-none-any.whl` used as the Python release asset.
The build stages that wheel outside the source checkout and records its filename
and SHA-256 plus the lock hash in `museon-build.json`. The bundle preserves:

- Museon distribution metadata and version;
- all importlib resources for the bundled `museon-cli` Skill;
- keyring backends and distribution metadata;
- certifi's CA bundle and PyYAML's native extension;
- `tzdata` on Windows so IANA time zones work without a system zone database.

The native smoke covers `version`, `schema`, `--help`, first and idempotent
Skill setup, and exact agreement with the reviewed public command contract.

## Local generation and verification

Generated trees stay under ignored `build/`; prepacked artifacts stay under
ignored `npm-dist/` and `native-dist/`. On a supported host:

```bash
uv sync --frozen --all-groups
uv build
uv run python scripts/verify_public_artifacts.py
uv run python scripts/build_native.py --wheel dist/museoncli-0.3.60-py3-none-any.whl
uv run python scripts/smoke_native.py
uv run python scripts/generate_npm_packages.py --target darwin-arm64
uv run python scripts/verify_npm_packages.py --package-root build/npm --allow-partial
uv run python scripts/pack_npm_packages.py --package cli --package darwin-arm64
uv run python scripts/verify_npm_packages.py --tarball-dir npm-dist --allow-partial
```

Use the target matching the current host. Cross-compilation is deliberately
disabled. CI performs the same flow on all six frozen runners and installs the
root plus matching platform tarball using `npm install --global --ignore-scripts`.

## Python fallback and update discovery

For a host without npm, the immutable fallback is the wheel attached to GitHub
release `v0.3.60`:

```bash
uv tool install "https://github.com/Museon-AI/museon-cli/releases/download/v0.3.60/museoncli-0.3.60-py3-none-any.whl"
```

Update discovery is off by default. Setting `MUSEONCLI_UPDATE_CHECK=true`
allows network-backed commands to read GitHub's latest-release metadata. Local
commands still never perform an update request. npm-launched processes receive
npm-specific upgrade guidance.

## Publication gates

Museon CLI is licensed under Apache-2.0. Release verification requires the
repository `LICENSE` and matching project/package metadata. Native builds
generate full third-party notices from the locked environment; package
verification requires their recorded hash and copies the project license into
every npm package. A protected release also requires Developer ID
signing plus accepted Apple notarization, and timestamped Authenticode signatures
on every Windows PE file, before npm packing. npm scope ownership, one-time
package creation, signing credentials, and trusted-publisher setup for all seven
packages remain external launch gates; see [releasing.md](releasing.md).
