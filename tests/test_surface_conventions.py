"""CLI surface conventions gate — see docs/cli-surface-conventions.md.

Every rule here is a convention, not a suggestion: new commands must pass
with no allowlist edits.
"""

from __future__ import annotations

import argparse
import json

from museoncli.domains import command_specs

# commands where --limit is a true "top N" cap (server has no offset paging)
LIMIT_CAP_COMMANDS = {
    "research.web-research",
    "research.social-media-search",
    "research.community-search",
    "campaign-monitor.creator-performance-get",
    "campaign-monitor.post-performance-get",
    "evaluator.kind-list",
    "evaluator.list",
    "evaluator.run-list",
    "account-operation.runs",
    "account-operation.attribution",
}
# positional mode selectors (never IDs)
ALLOWED_POSITIONALS = {"routines.record": ["kind"]}
# skills.get windows file content by offset/limit chars — not list pagination
CONTENT_WINDOW_COMMANDS = {"skills.get"}
ADMIN_OR_STAFF_COMMANDS = {"evaluator.create", "evaluator.update"}


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
            if spec.schema_name in ADMIN_OR_STAFF_COMMANDS:
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
        assert forbidden.isdisjoint(properties), spec.schema_name
        for value in properties.values():
            if isinstance(value, dict):
                nested = value.get("properties", {})
                assert forbidden.isdisjoint(nested), spec.schema_name


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
        assert forbidden.isdisjoint(flags), spec.schema_name
