"""Creator conversation and contract reads: what the Operations tab opens for one enrollment.

``--enrollment-id`` comes from ``ugc enrollment +list``. The same routes the web
calls: ``/api/v2/ugc/enrollments/{id}/conversation`` (the thread with the creator:
messages both ways, cards, delivery state) and ``.../contract`` (the contract's
state, its rendered terms and signatures). Both are the Campaign team's: owner/admin
and the Campaign's operators; members read neither, and a Campaign shared into the
organization does not open them to the CLI.
Sending, resending and nudging are their own commands.
"""

from __future__ import annotations

from typing import Any

from museoncli.domains._model import CommandSpec, Domain
from museoncli.domains._org_reads import Route, read, uuid

EXECUTORS: dict[str, Any] = {}

ENROLLMENT_ID = uuid("Enrollment id from ugc enrollment +list.")


def specs() -> list[CommandSpec]:
    return [
        read(
            EXECUTORS,
            Domain.UGC,
            "message",
            "list",
            summary=(
                "Read the conversation with one enrolled creator, newest first, as the "
                "Operations tab's thread shows it: messages both ways, cards and their delivery "
                "state. Owner/admin and the Campaign's operators; members cannot read it."
            ),
            properties={"enrollment_id": ENROLLMENT_ID},
            required=("enrollment_id",),
            route=lambda a: Route("/ugc/enrollments/{enrollment_id}/conversation"),
            paging="cursor",
            example="museoncli ugc message +list --enrollment-id <enrollment_id>",
            output="A page of the conversation (items) and next_cursor.",
        ),
        read(
            EXECUTORS,
            Domain.UGC,
            "enrollment",
            "get-contract",
            summary=(
                "Read one enrollment's contract: its state (draft, sent, signed, terminated), "
                "rendered terms and signatures. Owner/admin and the Campaign's operators; "
                "members cannot read it."
            ),
            properties={"enrollment_id": ENROLLMENT_ID},
            required=("enrollment_id",),
            route=lambda a: Route("/ugc/enrollments/{enrollment_id}/contract"),
            example="museoncli ugc enrollment +get-contract --enrollment-id <enrollment_id>",
        ),
    ]
