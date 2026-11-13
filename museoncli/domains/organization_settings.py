"""Organization settings reads: Settings -> members and billing, for the organization acted in.

The routes the web's settings pages call: ``/api/v1/organizations/{id}/members``
(each member's role and Campaign scope) and
``/api/v1/billing/organizations/{id}/overview`` (plan, AI credits and usage). The
organization is the one the command acts in (``museoncli org select`` or
``--organization-id``). Members are readable by owner, admin and operator;
billing by owner and admin; the server refuses everyone else.

Partners, Campaign and account shares in and out and the organization's signature
are read in a signed-in browser only, so they have no command here.
"""

from __future__ import annotations

from typing import Any

from museoncli.domains._model import CommandSpec, Domain
from museoncli.domains._org_reads import Route, read

EXECUTORS: dict[str, Any] = {}


def specs() -> list[CommandSpec]:
    organization = Domain.ORGANIZATION
    return [
        read(
            EXECUTORS,
            organization,
            "member",
            "list",
            summary=(
                "List the organization's members with their role (owner, admin, operator, "
                "member) and Campaign scope (all or chosen Campaigns). Owner, admin and "
                "operator read it."
            ),
            properties={},
            route=lambda a: Route("/organizations/{organization_id}/members", version=1),
            example="museoncli organization member +list",
            output="The members.",
        ),
        read(
            EXECUTORS,
            organization,
            "billing",
            "get",
            summary=(
                "Read the organization's billing overview: plan and subscription, AI credit "
                "balance and usage. Owner and admin only."
            ),
            properties={},
            route=lambda a: Route("/billing/organizations/{organization_id}/overview", version=1),
            example="museoncli organization billing +get",
        ),
    ]
