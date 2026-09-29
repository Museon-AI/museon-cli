"""Help text and runnable examples derived from each command's own schema.

Hand-written help and examples always win. This module only fills gaps, so
every flag says what it takes and every command shows one invocation that the
real parser accepts, instead of only ``museoncli schema <name>``.
"""

from __future__ import annotations

import argparse
from typing import Any

from museoncli.domains._model import CommandSpec

_COMMON_FLAG_HELP = {
    "--workspace-id": "Workspace ID; defaults to the selected workspace.",
    "--page": "Page number, starting at 1.",
    "--page-size": "Records per page.",
    "--cursor": "Opaque cursor returned by the previous page.",
    "--search": "Free-text search.",
    "--dry-run": "Validate the input locally and print it without calling the API.",
    "--yes": "Confirm this operation (required for commands that need confirmation).",
    "--idempotency-key": (
        "Stable key for this write; retry an unknown outcome with the same key and input."
    ),
    "--expected-version": (
        "Version from your latest read; the write fails instead of overwriting a newer change."
    ),
    "--expected-updated-at": (
        "updated_at from your latest read; the write fails if the resource changed since."
    ),
    "--args-json": "All inputs as one JSON object (see `museoncli schema <name>`).",
    "--args-file": "Path to a JSON file holding all inputs (see `museoncli schema <name>`).",
}
_FORMAT_HINTS = {
    "uuid": "UUID",
    "date": "date, YYYY-MM-DD",
    "date-time": "time with a timezone offset, e.g. 2026-10-01T09:00:00+08:00",
    "timezone": "IANA timezone, e.g. Asia/Shanghai",
}
_FORMAT_PLACEHOLDERS = {
    "date": "2026-10-01",
    "date-time": "2026-10-01T09:00:00+08:00",
    "timezone": "Asia/Shanghai",
}


def parser_for(spec: CommandSpec) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    spec.add_arguments(parser)
    return parser


def _property(spec: CommandSpec, dest: str) -> dict[str, Any]:
    value = spec.input_schema.get("properties", {}).get(dest)
    return value if isinstance(value, dict) else {}


def _item_schema(schema: dict[str, Any]) -> dict[str, Any]:
    items = schema.get("items")
    return items if isinstance(items, dict) else schema


def _humanize(name: str) -> str:
    return name.replace("_", " ").replace("-", " ").strip()


def flag_help(spec: CommandSpec, action: argparse.Action) -> str | None:
    """Return help for a flag that has none, or None when nothing useful is known."""
    if not action.option_strings:
        return None
    option = action.option_strings[0]
    if option in _COMMON_FLAG_HELP:
        return _COMMON_FLAG_HELP[option]
    if option == "--id":
        entity = _humanize(spec.resource or spec.domain.value)
        return f"ID of the {entity} this command acts on."
    schema = _property(spec, action.dest)
    repeated = isinstance(action, argparse._AppendAction)
    item = _item_schema(schema)
    description = schema.get("description")
    if isinstance(description, str) and description.strip():
        text = description.strip()
    elif action.dest.endswith("_ids") or (repeated and action.dest.endswith("_id")):
        text = f"{_humanize(action.dest.removesuffix('_ids').removesuffix('_id'))} ID"
    elif action.dest.endswith("_id"):
        text = f"{_humanize(action.dest.removesuffix('_id'))} ID"
    elif isinstance(action, argparse.BooleanOptionalAction):
        text = f"{_humanize(action.dest).capitalize()} (true with --{option[2:]}, false with --no-{option[2:]})"
    else:
        text = _humanize(action.dest).capitalize()
    hints: list[str] = []
    fmt = item.get("format")
    if isinstance(fmt, str) and fmt in _FORMAT_HINTS and _FORMAT_HINTS[fmt] not in text:
        hints.append(_FORMAT_HINTS[fmt])
    if action.choices and "one of" not in text.lower():
        hints.append("one of: " + ", ".join(str(choice) for choice in action.choices))
    if repeated:
        hints.append("repeat the flag for several values")
    if hints:
        text = f"{text.rstrip('.')} ({'; '.join(hints)})"
    text = text[:1].upper() + text[1:]
    return text if text.endswith((".", ")")) else f"{text}."


def fill_flag_help(spec: CommandSpec, parser: argparse.ArgumentParser) -> None:
    for action in parser._actions:
        if action.help is None and action.option_strings and "-h" not in action.option_strings:
            action.help = flag_help(spec, action)


def _placeholder(spec: CommandSpec, action: argparse.Action) -> str:
    if action.choices:
        return str(next(iter(action.choices)))
    schema = _item_schema(_property(spec, action.dest))
    fmt = schema.get("format")
    if isinstance(fmt, str) and fmt in _FORMAT_PLACEHOLDERS:
        return _FORMAT_PLACEHOLDERS[fmt]
    if action.type is int or schema.get("type") == "integer":
        return "1"
    if action.type is float or schema.get("type") == "number":
        return "1.0"
    if action.dest == "idempotency_key":
        return "<stable-key>"
    if action.dest in {"id", "token"}:
        return f"<{(spec.resource or spec.domain.value)}-{action.dest}>"
    name = action.dest.removesuffix("_ids").removesuffix("_id").replace("_", "-")
    return f"<{name}-id>" if action.dest.endswith(("_id", "_ids")) else f"<{name}>"


def generated_example(spec: CommandSpec) -> str:
    """One invocation with every required input, accepted by the real parser."""
    parser = parser_for(spec)
    by_dest = {action.dest: action for action in parser._actions if action.option_strings}
    required = [str(name) for name in spec.input_schema.get("required", [])]
    required += [
        action.dest
        for action in parser._actions
        if action.option_strings and action.required and action.dest not in required
    ]
    for group in parser._mutually_exclusive_groups:
        # "one of --id / --handle is required": show the first alternative.
        if group.required and not any(action.dest in required for action in group._group_actions):
            required.append(group._group_actions[0].dest)
    options = {option for action in parser._actions for option in action.option_strings}
    parts = [spec.cli_path]
    needs_file = False
    for name in required:
        action = by_dest.get(name)
        if action is None:
            needs_file = True
            continue
        option = action.option_strings[0]
        if isinstance(action, argparse.BooleanOptionalAction | argparse._StoreTrueAction):
            parts.append(option)
        else:
            parts.extend([option, _placeholder(spec, action)])
    if needs_file and "--args-file" in options:
        parts.extend(["--args-file", "input.json"])
    if spec.requires_confirmation and "--yes" in options:
        parts.append("--yes")
    return " ".join(parts)


def command_examples(spec: CommandSpec) -> list[str]:
    """Hand-written examples, led by a generated invocation when none is runnable."""
    if any(not example.startswith("museoncli schema") for example in spec.examples):
        return list(spec.examples)
    return [generated_example(spec), *spec.examples]
