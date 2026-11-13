"""Contract entries for the commands about the CLI installation itself.

Domain commands describe Museon capabilities; these two describe the CLI: which
version runs, whether a newer release exists, and how to upgrade it. They make
no Museon API call and need no login.
"""

from __future__ import annotations

from typing import Any

from museoncli.updates import INSTALL_METHODS


_NULLABLE_STRING = {"type": ["string", "null"]}

UPDATE_STATUSES = [
    "current",
    "cached",
    "outdated",
    "updated",
    "check_failed",
    "disabled",
    "not_checked",
    "managed_externally",
]

_RELEASE_FACTS: dict[str, Any] = {
    "current": {"type": "string", "description": "The running CLI version."},
    "latest": {
        **_NULLABLE_STRING,
        "description": "Latest stable release; null when it could not be checked.",
    },
    "install_method": {
        "enum": list(INSTALL_METHODS),
        "description": (
            "uv_tool upgrades itself; pipx, uv_pip, pip and other need upgrade_command; "
            "source (a checkout) and managed (a host runtime) are updated by their owner."
        ),
    },
    "upgrade_command": {
        **_NULLABLE_STRING,
        "description": "The command that upgrades this installation; null when none applies.",
    },
    "changelog_url": {"type": "string"},
    "update_status": {"enum": UPDATE_STATUSES},
}

NOTICE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "description": (
        "Present only when there is something to tell. Finish the user's request, then "
        "relay `message`; never paste the raw notice."
    ),
    "properties": {
        "update": {
            "type": "object",
            "description": (
                "A newer stable release exists and was not installed. Tell the user and "
                "offer `museoncli upgrade`."
            ),
            "properties": {
                "current": {"type": "string"},
                "latest": {"type": "string"},
                "install_method": {"enum": list(INSTALL_METHODS)},
                "upgrade_command": _NULLABLE_STRING,
                "changelog_url": {"type": "string"},
                "message": {"type": "string"},
            },
            "required": [
                "current",
                "latest",
                "install_method",
                "upgrade_command",
                "changelog_url",
                "message",
            ],
        },
        "updated": {
            "type": "object",
            "description": "The CLI upgraded itself; reported once.",
            "properties": {
                "from": {"type": "string"},
                "to": {"type": "string"},
                "changelog_url": {"type": "string"},
                "highlights": {"type": "array", "items": {"type": "string"}},
                "message": {"type": "string"},
            },
            "required": ["from", "to", "changelog_url", "highlights", "message"],
        },
        "skills": {
            "type": "object",
            "description": "Installed Museon Agent Skills were synced or are out of date.",
        },
    },
}


def _envelope(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {"ok": {"type": "boolean"}, "data": data, "_notice": NOTICE_SCHEMA},
        "required": ["ok", "data"],
    }


_COMMON = {
    "authorization": {"authentication_required": False, "enforcement": "local"},
    "execution": "direct",
    "input_schema": {"type": "object", "properties": {}, "required": []},
    "requires_confirmation": False,
    "stability": "stable",
    "supports_dry_run": False,
    "transport": "local",
}

CLI_COMMANDS: list[dict[str, Any]] = [
    {
        **_COMMON,
        "name": "version",
        "cli": "museoncli version",
        "examples": ["museoncli version"],
        "risk_level": "read",
        "summary": (
            "Report this CLI's version, the latest stable release, how it was installed "
            "and the command that upgrades it. Checks the latest release on every call."
        ),
        "output_schema": _envelope(
            {
                "type": "object",
                "properties": {
                    "cli_version": {"type": "string"},
                    "api_base_url": {"type": "string"},
                    **_RELEASE_FACTS,
                    "update": {
                        "type": "object",
                        "description": "The raw release check (status and its details).",
                    },
                },
                "required": ["cli_version", *_RELEASE_FACTS, "update"],
            }
        ),
    },
    {
        **_COMMON,
        "name": "upgrade",
        "cli": "museoncli upgrade",
        "examples": ["museoncli upgrade"],
        "risk_level": "write",
        "summary": (
            "Upgrade to the latest stable release. An official uv tool install verifies and "
            "installs it (even with MUSEONCLI_UPDATE_CHECK=0); other installs get "
            "status manual and the command to run. Changes only the local CLI."
        ),
        "output_schema": _envelope(
            {
                "type": "object",
                "properties": {
                    "status": {
                        "enum": ["upgraded", "current", "manual", "managed_externally"],
                    },
                    "message": {"type": "string"},
                    "previous_version": _NULLABLE_STRING,
                    **_RELEASE_FACTS,
                },
                "required": ["status", "message", *_RELEASE_FACTS],
            }
        ),
    },
]


def cli_command_summary(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        key: entry[key]
        for key in ("name", "cli", "summary", "risk_level", "requires_confirmation")
    }


def cli_command(name: str) -> dict[str, Any] | None:
    normalized = name.removeprefix("museoncli ").strip()
    return next((entry for entry in CLI_COMMANDS if entry["name"] == normalized), None)
