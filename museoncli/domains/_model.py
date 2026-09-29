"""Command specification shared by every domain module."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any, Literal


RiskLevel = Literal["read", "write", "destructive"]


ExecutionMode = Literal["direct", "async_run"]


AdapterType = Literal[
    "internal_tool",
    "run_status",
]


Stability = Literal["stable", "preview"]


Transport = Literal["agent_cli_api", "local_process"]


ROUTINES_DOMAIN = "routines"


class Domain(str, Enum):
    RESEARCH = "research"
    CONTENT_ANALYSIS = "content-analysis"
    ARTIFACTS = "artifacts"
    MEDIA = "media"
    SOCIAL_ACCOUNT = "social-account"
    HIRE_AI_CREATOR = "hireaicreator"
    AI_SLIDESHOW = "ai-slideshow"
    CAMPAIGN_MONITOR = "campaign-monitor"
    SKILLS = "skills"
    STAFF_OPS = "staff-ops"
    ROUTINES = ROUTINES_DOMAIN


@dataclass(frozen=True, slots=True)
class CommandSpec:
    domain: Domain
    shortcut: str
    summary: str
    risk_level: RiskLevel
    execution: ExecutionMode
    adapter_tool_name: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    examples: list[str]
    add_arguments: Callable[[argparse.ArgumentParser], None]
    build_arguments: Callable[[argparse.Namespace], dict[str, Any]]
    resource: str | None = None
    legacy_shortcuts: tuple[str, ...] = ()
    discoverable: bool = True
    adapter_type: AdapterType = "internal_tool"
    supports_dry_run: bool = False
    requires_confirmation: bool = False
    authentication_required: bool = True
    required_scopes: tuple[str, ...] = ("agent_cli.access",)
    required_roles: tuple[str, ...] = ("workspace_member",)
    workspace_bound: bool = True
    resource_policy: str = "server_evaluated_workspace_and_resource_access"
    stability: Stability = "stable"
    transport: Transport = "agent_cli_api"

    @property
    def schema_name(self) -> str:
        action = self.shortcut.removeprefix("+")
        if self.resource:
            return f"{self.domain.value}.{self.resource}-{action}"
        return f"{self.domain.value}.{action}"

    @property
    def cli_path(self) -> str:
        """The exact argv that invokes this command, without flags."""

        parts = ["museoncli", self.domain.value]
        if self.resource:
            parts.append(self.resource)
        parts.append(self.shortcut)
        return " ".join(parts)

    @property
    def legacy_schema_names(self) -> tuple[str, ...]:
        """Capability keys this command answered to before a rename."""

        return tuple(
            f"{self.domain.value}.{self.resource}-{legacy.removeprefix('+')}"
            if self.resource
            else f"{self.domain.value}.{legacy.removeprefix('+')}"
            for legacy in self.legacy_shortcuts
        )

    def legacy_cli_path(self, legacy_shortcut: str) -> str:
        parts = ["museoncli", self.domain.value]
        if self.resource:
            parts.append(self.resource)
        parts.append(legacy_shortcut)
        return " ".join(parts)

    @property
    def capability_key(self) -> str:
        """Stable capability identifier shared by discovery and API contracts."""

        return self.schema_name
