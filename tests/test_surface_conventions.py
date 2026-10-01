"""CLI surface conventions gate — see docs/cli-surface-conventions.md.

Every rule here is a convention, not a suggestion: new commands must pass
with no allowlist edits.
"""

from __future__ import annotations

import argparse
import json
import re
import shlex

from museoncli.domains import command_specs

# commands where --limit is a true "top N" cap (server has no offset paging)
LIMIT_CAP_COMMANDS = {
    "research.create-ads-search",
    "research.search-web",
    "research.search-social-media",
    "research.search-community",
    "campaign-monitor.get-creator-performance",
    "campaign-monitor.get-post-performance",
    "staff-ops.search-code",
    "staff-ops.read-supabase",
    "staff-ops.search-logs",
}
ADMIN_OR_STAFF_COMMANDS = set()
STAFF_COMMANDS = {
    "staff-ops.read-code",
    "staff-ops.search-code",
    "staff-ops.read-supabase",
    "staff-ops.search-logs",
}
# positional mode selectors (never IDs)
ALLOWED_POSITIONALS = {"routines.record": ["kind"]}
# skills.get windows file content by offset/limit chars — not list pagination
CONTENT_WINDOW_COMMANDS = {"skills.get"}


def _parser_for(spec):
    parser = argparse.ArgumentParser(add_help=False)
    spec.add_arguments(parser)
    return parser


def test_no_positional_ids() -> None:
    for spec in command_specs():
        positionals = [a.dest for a in _parser_for(spec)._actions if not a.option_strings]
        assert positionals == ALLOWED_POSITIONALS.get(spec.schema_name, []), (
            spec.schema_name,
            positionals,
        )


def test_pagination_conventions() -> None:
    for spec in command_specs():
        flags = {a.option_strings[0] for a in _parser_for(spec)._actions if a.option_strings}
        if spec.schema_name in CONTENT_WINDOW_COMMANDS:
            continue
        if "--page" in flags:
            assert "--page-size" in flags, spec.schema_name
            assert "--limit" not in flags, spec.schema_name
        assert "--offset" not in flags, spec.schema_name
        if "--limit" in flags:
            assert spec.schema_name in LIMIT_CAP_COMMANDS, spec.schema_name


def test_enum_flag_values_are_kebab_case() -> None:
    for spec in command_specs():
        for action in _parser_for(spec)._actions:
            if not action.option_strings or not action.choices:
                continue
            for choice in action.choices:
                assert "_" not in str(choice), (
                    spec.schema_name,
                    action.option_strings[0],
                    choice,
                )


def _choice_actions(spec):
    return {
        option: action
        for action in _parser_for(spec)._actions
        if action.option_strings and action.choices
        for option in action.option_strings
    }


def _schema_descriptions(value):
    if isinstance(value, dict):
        description = value.get("description")
        if isinstance(description, str):
            yield description
        for child in value.values():
            yield from _schema_descriptions(child)
    elif isinstance(value, list):
        for child in value:
            yield from _schema_descriptions(child)


def test_input_schema_enum_values_match_cli_choices() -> None:
    for spec in command_specs():
        properties = spec.input_schema.get("properties", {})
        for option, action in _choice_actions(spec).items():
            property_name = option.removeprefix("--").replace("-", "_")
            property_schema = properties.get(property_name)
            if not isinstance(property_schema, dict) or "enum" not in property_schema:
                continue
            schema_choices = {str(value) for value in property_schema["enum"] if value is not None}
            assert schema_choices == {str(value) for value in action.choices}, (
                spec.schema_name,
                option,
                schema_choices,
                action.choices,
            )


def test_input_schema_descriptions_do_not_expose_snake_case_enum_values() -> None:
    for spec in command_specs():
        descriptions = "\n".join(_schema_descriptions(spec.input_schema))
        for action in _choice_actions(spec).values():
            for choice in action.choices:
                internal_value = str(choice).replace("-", "_")
                if internal_value == choice:
                    continue
                assert not re.search(
                    rf"(?<![A-Za-z0-9_]){re.escape(internal_value)}(?![A-Za-z0-9_])",
                    descriptions,
                ), (spec.schema_name, internal_value)


def test_examples_use_cli_enum_values() -> None:
    for spec in command_specs():
        choice_actions = _choice_actions(spec)
        for example in spec.examples:
            for segment in example.split("&&"):
                tokens = shlex.split(segment.strip())
                for index, token in enumerate(tokens[:-1]):
                    option, separator, value = token.partition("=")
                    action = choice_actions.get(option)
                    if action is None:
                        continue
                    if not separator:
                        value = tokens[index + 1]
                    assert value in action.choices, (spec.schema_name, example, option, value)


def test_write_commands_support_dry_run_and_destructive_gate() -> None:
    for spec in command_specs():
        if spec.risk_level in {"write", "destructive"}:
            assert spec.supports_dry_run, spec.schema_name
        if spec.risk_level == "destructive":
            assert spec.requires_confirmation, spec.schema_name


def test_dry_run_spec_and_parser_agree() -> None:
    """supports_dry_run on the spec must match an actual --dry-run parser flag.

    Regression guard: content-analysis.run / skills.create / skills.update once
    claimed dry-run support in schema while the parser rejected the flag.
    """
    for spec in command_specs():
        flags = {
            action.option_strings[0]
            for action in _parser_for(spec)._actions
            if action.option_strings
        }
        assert spec.supports_dry_run == ("--dry-run" in flags), spec.schema_name


def test_command_specs_publish_auth_and_capability_metadata() -> None:
    for spec in command_specs():
        assert spec.capability_key == spec.schema_name
        assert spec.stability in {"stable", "preview"}
        if spec.schema_name == "artifacts.validate":
            assert spec.authentication_required is False
            assert spec.required_scopes == ()
            assert spec.required_roles == ()
            assert spec.workspace_bound is False
            assert spec.transport == "local_process"
        else:
            assert spec.authentication_required is True
            assert spec.required_scopes == ("agent_cli.access",)
            if spec.schema_name in STAFF_COMMANDS:
                assert spec.required_roles == ("staff",)
            elif spec.schema_name in ADMIN_OR_STAFF_COMMANDS:
                assert spec.required_roles == ("workspace_admin_or_staff",)
            else:
                assert spec.required_roles == ("workspace_member",)
            assert spec.workspace_bound is True
            assert spec.transport == "agent_cli_api"


def test_public_schema_does_not_expose_provider_identity() -> None:
    schema_text = json.dumps(
        [
            {
                "name": spec.schema_name,
                "summary": spec.summary,
                "input_schema": spec.input_schema,
                "output_schema": spec.output_schema,
            }
            for spec in command_specs()
        ]
    ).lower()

    for internal_name in ("provider", "tikhub", "rapidapi", "gemini", "geelark", "phyllo"):
        assert internal_name not in schema_text


def test_public_schema_does_not_expose_server_model_controls() -> None:
    forbidden = {"model", "text_model", "image_model", "slice_model", "analysis_model"}
    for spec in command_specs():
        properties = spec.input_schema.get("properties", {})
        # Prompt-media generation explicitly exposes its three supported product models;
        # unrelated business workflows continue to hide server routing controls.
        blocked = forbidden - {"model"} if spec.schema_name == "media.generate" else forbidden
        assert blocked.isdisjoint(properties), spec.schema_name
        for name, value in properties.items():
            if isinstance(value, dict):
                nested = value.get("properties", {})
                # Plan generation exposes a reviewed finite image model selection.
                nested_blocked = (
                    forbidden - {"image_model"}
                    if spec.schema_name == "hireaicreator.plan-create"
                    and name == "generation_options"
                    else forbidden
                )
                assert nested_blocked.isdisjoint(nested), spec.schema_name


def test_public_parser_does_not_expose_server_model_controls() -> None:
    forbidden = {
        "--model",
        "--text-model",
        "--image-model",
        "--slice-model",
        "--analysis-model",
        "--temperature",
        "--max-output-tokens",
    }
    for spec in command_specs():
        flags = {
            option for action in _parser_for(spec)._actions for option in action.option_strings
        }
        blocked = forbidden - {"--model"} if spec.schema_name == "media.generate" else forbidden
        assert blocked.isdisjoint(flags), spec.schema_name


def _runnable_examples(spec):
    from museoncli.domains._discovery import command_examples

    for example in command_examples(spec):
        if example.startswith("museoncli schema") or not example.startswith("museoncli "):
            continue
        if any(token in example for token in ("&&", "|", "$(")):
            continue
        yield example


def test_every_command_shows_a_runnable_example() -> None:
    """Known regression: 132 commands only showed `museoncli schema <self>`."""
    from museoncli.main import build_parser

    parser = build_parser()
    for spec in command_specs():
        examples = list(_runnable_examples(spec))
        assert examples, spec.schema_name
        for example in examples:
            args = parser.parse_args(shlex.split(example)[1:])
            assert args.domain_command == spec.schema_name, (spec.schema_name, example)


def test_every_flag_has_help() -> None:
    """Known regression: about 95% of flags printed no help at all."""
    from museoncli.domains._discovery import fill_flag_help

    for spec in command_specs():
        parser = _parser_for(spec)
        fill_flag_help(spec, parser)
        for action in parser._actions:
            if action.option_strings:
                assert action.help, (spec.schema_name, action.option_strings[0])


def test_capability_keys_and_cli_paths_are_unique_and_reversible() -> None:
    from museoncli.domains import get_command_spec

    specs = command_specs()
    assert len({spec.schema_name for spec in specs}) == len(specs)
    assert len({spec.cli_path for spec in specs}) == len(specs)
    for spec in specs:
        assert get_command_spec(spec.cli_path).schema_name == spec.schema_name
        assert get_command_spec(spec.schema_name).cli_path == spec.cli_path


def test_summaries_only_reference_existing_shortcuts() -> None:
    shortcuts = {spec.shortcut for spec in command_specs()}
    for spec in command_specs():
        for reference in re.findall(r"(?<![\w-])\+[a-z][a-z0-9-]+", spec.summary):
            assert reference in shortcuts, (spec.schema_name, reference)


# Existing commands that accept both a singular and a plural spelling of one
# input. New commands must pick one (a singular flag repeated for several values).
SINGULAR_PLURAL_FLAG_EXCEPTIONS = {("hireaicreator.video-list", "--publishing-account-id")}


def test_no_command_accepts_singular_and_plural_spellings_of_one_input() -> None:
    for spec in command_specs():
        flags = {
            option for action in _parser_for(spec)._actions for option in action.option_strings
        }
        for flag in flags:
            if f"{flag}s" in flags:
                assert (spec.schema_name, flag) in SINGULAR_PLURAL_FLAG_EXCEPTIONS, (
                    spec.schema_name,
                    flag,
                )


def test_renamed_commands_keep_answering_to_their_old_names() -> None:
    """A rename must not break a released invocation: old paths and keys resolve."""
    from museoncli.domains import get_command_spec
    from museoncli.main import build_parser

    parser = build_parser()
    canonical = {spec.cli_path for spec in command_specs()}
    for spec in command_specs():
        for legacy, key in zip(spec.legacy_shortcuts, spec.legacy_schema_names):
            path = spec.legacy_cli_path(legacy)
            assert path not in canonical, path
            assert get_command_spec(key).schema_name == spec.schema_name
            assert get_command_spec(path).schema_name == spec.schema_name
            from museoncli.domains._discovery import generated_example

            required = shlex.split(generated_example(spec))[len(shlex.split(spec.cli_path)) :]
            args = parser.parse_args(shlex.split(path)[1:] + required)
            assert args.domain_command == spec.schema_name
            assert args.legacy_invocation == path


def test_old_names_are_hidden_from_help() -> None:
    import contextlib
    import io

    from museoncli.main import build_parser

    parser = build_parser()
    for spec in command_specs():
        if not spec.legacy_shortcuts:
            continue
        prefix = ["hireaicreator", spec.resource] if spec.resource else [spec.domain.value]
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer), contextlib.suppress(SystemExit):
            parser.parse_args([*prefix, "--help"])
        for legacy in spec.legacy_shortcuts:
            assert re.search(rf"(?<![\w-]){re.escape(legacy)}(?![\w-])", buffer.getvalue()) is None, (
                spec.schema_name,
                legacy,
            )
