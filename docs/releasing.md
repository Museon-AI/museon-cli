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
5. Enable private vulnerability reporting before making the repository public.

## Release checklist

1. Update `museoncli/__init__.py`, `pyproject.toml`, `uv.lock`, and the generated
   command contract to the same version.
2. Run the complete local validation from `CONTRIBUTING.md`.
3. Merge the release change to `main`.
4. Create a GitHub Release whose tag is exactly `v<package-version>`.
5. The release workflow verifies the tag, rebuilds from source, publishes to
   PyPI, and attaches the wheel, sdist, and command contract to the release.

The private Museon Agent runtime should consume an explicitly pinned release;
it must not build from a checkout of this repository at runtime.
