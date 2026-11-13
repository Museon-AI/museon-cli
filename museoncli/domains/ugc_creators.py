"""Creator directory reads: the 创作者 page (/creators) across the organization's Campaigns.

The routes the web's creator list calls, addressed by the organization:
``/api/v2/ugc/agency/{organization}/creators`` and ``.../creators/{id}``. One row per
creator the organization has worked with, with their accounts and Campaigns; an
operator limited to chosen Campaigns sees those Campaigns' creators. The page is the
operating organization's team's (owner, admin, operator); elsewhere the server
answers not found. A creator's cooperation history and the directory's insights are
read in a signed-in browser only, so they have no command.
"""

from __future__ import annotations

from typing import Any

from museoncli.domains._model import CommandSpec, Domain
from museoncli.domains._org_reads import Route, read, text, uuid

EXECUTORS: dict[str, Any] = {}

CREATORS = "/ugc/agency/{organization_id}/creators"


def specs() -> list[CommandSpec]:
    return [
        read(
            EXECUTORS,
            Domain.UGC,
            "creator",
            "list",
            summary=(
                "List the creators the organization works with across its Campaigns, newest "
                "first: name, accounts and Campaigns. Operating organization's owner, admin and "
                "operators (an operator sees their assigned Campaigns' creators)."
            ),
            properties={"search": text("Name or listed handle contains this.")},
            route=lambda a: Route(CREATORS, {"q": a.get("search")}),
            paging="cursor",
            example="museoncli ugc creator +list --search maya",
            output="A page of creators (items) and next_cursor.",
        ),
        read(
            EXECUTORS,
            Domain.UGC,
            "creator",
            "get",
            summary=(
                "Read one creator of the organization: profile, accounts and the Campaigns they "
                "are in. Same visibility as creator +list."
            ),
            properties={"id": uuid("UGC creator id from creator +list.")},
            required=("id",),
            route=lambda a: Route(CREATORS + "/{id}"),
            example="museoncli ugc creator +get --id <creator_id>",
        ),
    ]
