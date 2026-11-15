"""Commands Museon CLI 2.0 removed, and the command that replaced each.

2.0 put both kinds of Campaign (UGC and tracking) in one `campaign` command group: the
Campaign itself (list, create, lifecycle, settings, staff, setup) and its figures.
`campaign-monitor` and the Campaign commands of `ugc` are gone, with no aliases. A
removed name answers `invalid_command` naming its replacement, so an Agent holding an
old Skill learns the new command from the error instead of guessing. The command
contract lists the removed names under each replacement (`removed_aliases`), so the
Museon API still finds a schema by the name a 1.x CLI knew it by.
"""

from __future__ import annotations

from typing import Any

REMOVED_IN = "2.0.0"

#: Removed CLI path (without `museoncli`) -> its replacement. Released 1.x spellings,
#: including the older aliases 1.x still accepted, each map to the command they became.
REMOVED_COMMANDS: dict[str, str] = {
    # campaign-monitor: the Campaign, its figures, and a tracking Campaign's members
    "campaign-monitor +list": "campaign +list",
    "campaign-monitor +get": "campaign +get",
    "campaign-monitor campaign +get": "campaign +get",
    "campaign-monitor agency-campaign +list": "campaign +list",
    "campaign-monitor +list-dimensions": "campaign +list-dimensions",
    "campaign-monitor +get-breakdown": "campaign +get-breakdown",
    "campaign-monitor +get-summary": "campaign +get-summary",
    "campaign-monitor +summary": "campaign +get-summary",
    "campaign-monitor +get-period-performance": "campaign +get-period-performance",
    "campaign-monitor +period-performance": "campaign +get-period-performance",
    "campaign-monitor +list-creators": "campaign creator +list",
    "campaign-monitor +creator-list": "campaign creator +list",
    "campaign-monitor +add-creators": "campaign creator +add",
    "campaign-monitor +creator-add": "campaign creator +add",
    "campaign-monitor +remove-creators": "campaign creator +remove",
    "campaign-monitor +creator-remove": "campaign creator +remove",
    "campaign-monitor +list-content": "campaign content +list",
    "campaign-monitor +content-list": "campaign content +list",
    "campaign-monitor +add-content": "campaign content +add",
    "campaign-monitor +content-add": "campaign content +add",
    "campaign-monitor +remove-content": "campaign content +remove",
    "campaign-monitor +content-remove": "campaign content +remove",
    "campaign-monitor +bulk-remove-content": "campaign content +bulk-remove",
    "campaign-monitor +content-batch-remove": "campaign content +bulk-remove",
    "campaign-monitor +get-creator": "campaign creator +get",
    "campaign-monitor +creator-get": "campaign creator +get",
    "campaign-monitor +get-creator-performance": "campaign creator +get-performance",
    "campaign-monitor +creator-performance-get": "campaign creator +get-performance",
    "campaign-monitor +list-posts": "campaign post +list",
    "campaign-monitor +post-list": "campaign post +list",
    "campaign-monitor +get-post": "campaign post +get",
    "campaign-monitor +post-get": "campaign post +get",
    "campaign-monitor +get-post-performance": "campaign post +get-performance",
    "campaign-monitor +post-performance-get": "campaign post +get-performance",
    "campaign-monitor +resolve-post": "campaign post +resolve",
    "campaign-monitor +post-resolve": "campaign post +resolve",
    # campaign-monitor: the Dashboard tabs
    "campaign-monitor video +list": "campaign video +list",
    "campaign-monitor video +get": "campaign video +get",
    "campaign-monitor roster +list": "campaign roster +list",
    "campaign-monitor format +list": "campaign format +list",
    "campaign-monitor format-post +list": "campaign format-post +list",
    "campaign-monitor report +get": "campaign report +get",
    "campaign-monitor creator-tag +list": "campaign creator-tag +list",
    "campaign-monitor audience +get": "campaign audience +get",
    "campaign-monitor payment +list": "campaign payment +list",
    "campaign-monitor payment-summary +get": "campaign payment-summary +get",
    "campaign-monitor settlement +get": "campaign settlement +get",
    "campaign-monitor payout +list": "campaign payout +list",
    "campaign-monitor activity +list": "campaign activity +list",
    "campaign-monitor agency-analytics +get": "campaign analytics +get",
    # campaign-monitor: UGC creator operations, now beside their ugc writes
    "campaign-monitor enrollment +list": "ugc enrollment +list",
    "campaign-monitor assignment +list": "ugc assignment +list",
    "campaign-monitor creator-check +get": "ugc creator-check +get",
    "campaign-monitor creator-check +list": "ugc creator-check +list",
    # ugc: the Campaign entity
    "ugc campaign +list": "campaign +list",
    "ugc campaign +create": "campaign +create",
    "ugc campaign +launch": "campaign +launch",
    "ugc campaign +pause": "campaign +pause",
    "ugc campaign +resume": "campaign +resume",
    "ugc campaign +complete": "campaign +complete",
    "ugc campaign +archive": "campaign +archive",
    "ugc campaign +restore": "campaign +restore",
    "ugc campaign +rename": "campaign +rename",
    "ugc campaign-settings +get": "campaign settings +get",
    "ugc campaign-settings +update": "campaign settings +update",
    "ugc campaign-staff +list": "campaign staff +list",
    "ugc campaign-staff +set": "campaign staff +set",
    "ugc campaign-setup +get": "campaign setup +get",
}

#: Removed command groups (a domain, or a domain's resource) -> where they went.
REMOVED_GROUPS: dict[str, str] = {
    "campaign-monitor": "campaign",
    "ugc campaign": "campaign",
    "ugc campaign-settings": "campaign settings",
    "ugc campaign-staff": "campaign staff",
    "ugc campaign-setup": "campaign setup",
}


class RemovedCommandError(ValueError):
    """A command name 2.0 removed: the error names the command that replaced it."""

    def __init__(self, removed: str, replacement: str, *, exact: bool) -> None:
        self.removed = f"museoncli {removed}"
        self.replacement = f"museoncli {replacement}"
        self.exact = exact
        if exact:
            message = (
                f"`{self.removed}` was removed in Museon CLI {REMOVED_IN}; use "
                f"`{self.replacement}`. Read its flags first (`{self.replacement} --help`): "
                "a Campaign is always --campaign-id now."
            )
        else:
            message = (
                f"`{self.removed}` was removed in Museon CLI {REMOVED_IN}; its commands are now "
                f"under `{self.replacement}`. Run `{self.replacement} --help`, or "
                "`museoncli guide --search <words>`, to find the one you need."
            )
        super().__init__(message)

    def detail(self) -> dict[str, Any]:
        return {
            "message": str(self),
            "removed": self.removed,
            "replacement": self.replacement,
            "removed_in": REMOVED_IN,
        }


def _key(path: str) -> str:
    """`campaign-monitor video +list` -> `campaign-monitor.video-list` (a capability key)."""
    domain, *resource, action = path.split()
    action = action.removeprefix("+")
    return f"{domain}.{resource[0]}-{action}" if resource else f"{domain}.{action}"


#: Removed capability key -> the capability key that replaced it.
REMOVED_KEYS: dict[str, str] = {_key(old): _key(new) for old, new in REMOVED_COMMANDS.items()}


def removed_invocation(tokens: list[str]) -> RemovedCommandError | None:
    """The error for an argv that names a removed command or group, else None."""
    words = [token for token in tokens if not token.startswith("-")]
    if not words:
        return None
    action = next((word for word in words[1:3] if word.startswith("+")), None)
    for size in (2, 1):
        group = " ".join(words[:size])
        if group not in REMOVED_GROUPS:
            continue
        if action is not None:
            resource = words[1:words.index(action)]
            path = " ".join([words[0], *resource, action])
            if path in REMOVED_COMMANDS:
                return RemovedCommandError(path, REMOVED_COMMANDS[path], exact=True)
        if size == 1 and len(words) > 1 and not words[1].startswith("+"):
            sub = f"{group} {words[1]}"
            if sub in REMOVED_GROUPS:
                return RemovedCommandError(sub, REMOVED_GROUPS[sub], exact=False)
        return RemovedCommandError(group, REMOVED_GROUPS[group], exact=False)
    return None


def removed_schema_name(name: str) -> RemovedCommandError | None:
    """The error for a removed capability key or CLI path given to `schema`, else None."""
    text = name.strip().removeprefix("museoncli ").strip()
    if " " in text:
        return removed_invocation(text.split())
    normalized = text.replace(".+", ".")
    if normalized in REMOVED_KEYS:
        old = next(path for path in REMOVED_COMMANDS if _key(path) == normalized)
        return RemovedCommandError(old, REMOVED_COMMANDS[old], exact=True)
    if normalized in REMOVED_GROUPS:
        return RemovedCommandError(normalized, REMOVED_GROUPS[normalized], exact=False)
    return None


def removed_aliases(replacement_path: str) -> list[dict[str, str]]:
    """The removed names a command replaced, for its contract entry."""
    return [
        {"cli": f"museoncli {old}", "capability_key": _key(old), "removed_in": REMOVED_IN}
        for old, new in REMOVED_COMMANDS.items()
        if new == replacement_path
    ]
