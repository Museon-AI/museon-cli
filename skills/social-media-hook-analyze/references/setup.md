# Setup and dependency recovery

Use this reference only when `scripts/check_setup.py` reports a missing or
broken dependency. Do not repeat setup checks before every batch.

## ego-browser

Instagram browsing requires the `ego-browser` command provided by ego lite.
On macOS, install ego lite from <https://lite.ego.app/>, open it, and complete
the first-run browser-data onboarding. That onboarding registers
`ego-browser`, normally under `~/.local/bin`.

If ego lite is already installed but the command is missing, add
`~/.local/bin` to the current shell `PATH` and rerun the setup check. When the
host Agent provides an `ego-browser` Skill, prefer its installation flow and
return here after onboarding. Never replace ego-browser with a generic HTTP
scraper: the workflow intentionally reuses the user's authenticated Instagram
session in an isolated task space.

## Museon CLI and Agent Skills

Follow the canonical onboarding guide at <https://www.museon.ai/cli/install.md>
when `museoncli` is missing. It installs a reviewed release wheel, then runs:

```bash
museoncli setup --agent auto
```

The setup command installs both the base `museon-cli` Skill and this
`social-media-hook-analyze` Skill for Codex, Claude Code, or Cursor. Select the
host explicitly when auto-detection is ambiguous.

Do not check authentication during ordinary setup. Start authentication
recovery only after a real Museon command returns `missing_auth`,
`unauthorized`, or a missing-workspace error. Preserve the returned browser URL
and finish with `museoncli auth finish --wait`, then retry the original command.

## Ready condition

Setup is ready only when the dependency checker confirms:

- the ego-browser Node runtime can execute;
- `museoncli version` succeeds;
- the start, batch-poll, and results command schemas are present.

The checker performs no Instagram navigation, authentication, analysis, card
send, or other external write.
