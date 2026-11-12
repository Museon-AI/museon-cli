"""Workspace addressing kept for agentic-campaign and hireaicreator only.

MuseOn addresses organizations; a workspace is internal storage and museoncli
1.0 has no workspace concept. These two command groups have not moved yet and
keep their 0.25 behaviour: hireaicreator commands take a deprecated optional
``workspace_id`` input, and both groups' envelopes keep a ``workspace`` key.
Everything workspace-shaped for them lives here, so the rest of the CLI never
sees a workspace.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from museoncli.domains._model import CommandSpec, Domain

LEGACY_WORKSPACE_DOMAINS = frozenset({Domain.AGENTIC_CAMPAIGN, Domain.HIRE_AI_CREATOR})

_ORGANIZATION_ID_PROPERTY = {
    "type": "string",
    "format": "uuid",
    "description": (
        "Organization to act in, sent as the X-Organization-Id header (never in the body). "
        "Defaults to the selected organization."
    ),
}
_WORKSPACE_ID_DEPRECATION = (
    "DEPRECATED: a workspace inside the organization. Optional; the server resolves the "
    "workspace from the organization and refuses one from another organization "
    "(409 organization_workspace_mismatch)."
)
_WORKSPACE_OUTPUT_PROPERTY = {
    "type": ["object", "null"],
    "deprecated": True,
    "description": "Deprecated: the --workspace-id this command was given, if any.",
}
ORGANIZATION_WORKSPACE_MISMATCH_MESSAGE = (
    "The workspace given with --workspace-id is not in the organization this request "
    "addresses (--organization-id, or the organization selected with `museoncli org "
    "select`). Drop --workspace-id, or address the organization it belongs to."
)
WORKSPACE_FLAG_HELP = (
    "DEPRECATED: a workspace in the organization; the server resolves the workspace "
    "from the organization."
)


def keeps_workspace(domain: Domain) -> bool:
    return domain in LEGACY_WORKSPACE_DOMAINS


def legacy_workspace_spec(spec: CommandSpec) -> CommandSpec:
    """The 0.25 schemas of the two groups: deprecated workspace_id and the envelope key."""
    if not keeps_workspace(spec.domain):
        return spec
    changes: dict[str, Any] = {}
    output_properties = spec.output_schema.get("properties")
    if isinstance(output_properties, dict) and "organization" in output_properties:
        changes["output_schema"] = {
            **spec.output_schema,
            "properties": {**output_properties, "workspace": dict(_WORKSPACE_OUTPUT_PROPERTY)},
        }
    properties = spec.input_schema.get("properties")
    if spec.organization_bound and isinstance(properties, dict) and "workspace_id" in properties:
        workspace_property = properties["workspace_id"]
        changes["input_schema"] = {
            **spec.input_schema,
            "properties": {
                **properties,
                "workspace_id": {
                    **(workspace_property if isinstance(workspace_property, dict) else {}),
                    "deprecated": True,
                    "description": _WORKSPACE_ID_DEPRECATION,
                },
                "organization_id": dict(_ORGANIZATION_ID_PROPERTY),
            },
        }
    return dataclasses.replace(spec, **changes) if changes else spec


def with_workspace_key(spec: CommandSpec, result: Any, arguments: dict[str, Any]) -> Any:
    """Put the 0.25 ``workspace`` key back into the two groups' envelopes, after ``command``."""
    if (
        not keeps_workspace(spec.domain)
        or not isinstance(result, dict)
        or "command" not in result
        or "workspace" in result
    ):
        return result
    workspace_id = arguments.get("workspace_id")
    output: dict[str, Any] = {}
    for key, value in result.items():
        output[key] = value
        if key == "command":
            output["workspace"] = {"id": workspace_id} if workspace_id else None
    return output


def workspace_flag_notice(spec: CommandSpec, workspace_flag: Any) -> str | None:
    """The 0.25 stderr notice for --workspace-id, still printed by the two groups."""
    if keeps_workspace(spec.domain) and workspace_flag:
        return (
            "--workspace-id is deprecated; commands act in the selected organization "
            "(`museoncli org select`) or --organization-id."
        )
    return None
