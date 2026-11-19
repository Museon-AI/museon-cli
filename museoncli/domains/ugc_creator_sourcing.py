"""Creator Sourcing reads: the internal 创作者寻源 page (/creator-sourcing).

The routes the page calls, addressed by the organization:
``/api/v2/ugc/agency/{organization}/creator-library`` and its per-person
``/applications`` and ``/works``. Everyone who joined the community or applied to
a project, with how they joined, what they declared, their projects and how their
posts did; per person, every form they filled in and their newest works with
views. MuseOn staff only, exactly as the page: the server checks that the key's
holder is staff and that the key's organization holds creator read, and answers
not found otherwise. The team's notes are edited in a signed-in browser only.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from museoncli.domains._model import CommandSpec, Domain
from museoncli.domains._org_reads import Route, choice, read, text, uuid
from museoncli.domains.hireaicreator import arr

EXECUTORS: dict[str, Any] = {}

LIBRARY = "/ugc/agency/{organization_id}/creator-library"
STAFF = " MuseOn staff only, as in the web."
#: Staff, with the organization's creator read: the page's own rule (museon D-133). The CLI
#: records it and does not enforce it; a caller who is not staff is the server's refusal.
STAFF_POLICY = "staff_with_organization_creator_read"


def _staff(spec: CommandSpec) -> CommandSpec:
    return replace(spec, required_roles=("staff",), resource_policy=STAFF_POLICY)


def _values(description: str) -> dict[str, Any]:
    """A repeatable flag sent as one query value per entry."""
    return {**arr(text(description, max_length=80), maximum=50), "description": description}


def _choices(description: str, *values: str) -> dict[str, Any]:
    return {**arr(choice(description, *values), maximum=len(values)), "description": description}


def _list_route(a: dict[str, Any]) -> Route:
    return Route(
        LIBRARY,
        {
            "q": a.get("search"),
            "sort": a.get("sort"),
            "countries": a.get("country"),
            "languages": a.get("language"),
            "categories": a.get("category"),
            "content_types": a.get("content_type"),
            "platforms": a.get("platform"),
            "sources": a.get("source"),
            "cooperation": a.get("cooperation"),
            "campaign_id": a.get("campaign_id"),
            "activity": a.get("activity"),
            "note": a.get("note"),
            "min_avg_views": a.get("min_avg_views"),
            "min_followers": a.get("min_followers"),
            "viral_only": a.get("viral_only"),
        },
    )


def specs() -> list[CommandSpec]:
    return [_staff(spec) for spec in _specs()]


def _specs() -> list[CommandSpec]:
    return [
        read(
            EXECUTORS,
            Domain.UGC,
            "sourcing",
            "list",
            summary=(
                "Find creators for a new project: everyone who joined the community or applied "
                "to a project, filtered and sorted, with how they joined, what they declared, "
                "their projects, performance (posts, average and best views, viral posts, last "
                "post), latest stills and the team's note. Total in `total`." + STAFF
            ),
            properties={
                "search": text("Name, handle or note contains this."),
                "sort": choice(
                    "Order (default newest).",
                    "newest",
                    "avg-views",
                    "viral",
                    "followers",
                    "last-post",
                    "posts",
                ),
                "country": _values("ISO country code they declared, e.g. US. Repeatable."),
                "language": _values("Language tag they speak, e.g. en. Repeatable."),
                "category": _values("Primary topic they declared, e.g. technology. Repeatable."),
                "content_type": _values("Content type they declared, e.g. tutorials. Repeatable."),
                "platform": _choices(
                    "Has an account on this platform. Repeatable.",
                    "instagram",
                    "tiktok",
                    "youtube",
                    "facebook",
                    "x",
                ),
                "source": _choices(
                    "How they joined. Repeatable.",
                    "community",
                    "community-referral",
                    "recruitment-link",
                    "creator-referral",
                    "apply-page",
                    "invitation",
                    "discord",
                    "import",
                    "unknown",
                ),
                "cooperation": choice(
                    "Worked with us before or not.",
                    "all",
                    "cooperated",
                    "working",
                    "never",
                    "pending",
                ),
                "campaign_id": uuid("Only people in this project (UGC Campaign id)."),
                "activity": choice(
                    "When they last posted in our projects.",
                    "all",
                    "within-7",
                    "within-30",
                    "within-90",
                    "inactive-30",
                    "inactive-90",
                    "never",
                ),
                "note": choice("Whether the team wrote a note.", "all", "with", "without"),
                "min_avg_views": {
                    "type": "integer",
                    "minimum": 0,
                    "description": "Average views of their confirmed posts at least this.",
                },
                "min_followers": {
                    "type": "integer",
                    "minimum": 0,
                    "description": "Largest follower count at least this.",
                },
                "viral_only": {
                    "type": "boolean",
                    "description": "Only people with a confirmed post past 10,000 views.",
                },
            },
            route=_list_route,
            paging="offset",
            example=(
                "museoncli ugc sourcing +list --country US --language en --platform tiktok "
                "--sort avg-views --page-size 20"
            ),
            output="A page of creators (items), total, offset, limit and notes_visible.",
        ),
        read(
            EXECUTORS,
            Domain.UGC,
            "sourcing",
            "forms",
            summary=(
                "Read every form one creator filled in, newest first: the community registration "
                "form (naming the project it was sent with, if any) and each project application "
                "with its answers, accounts and sample videos." + STAFF
            ),
            properties={"id": uuid("UGC creator id from sourcing +list.")},
            required=("id",),
            route=lambda a: Route(LIBRARY + "/{id}/applications"),
            example="museoncli ugc sourcing +forms --id <creator_id>",
            output="creator_id and the forms (items).",
        ),
        read(
            EXECUTORS,
            Domain.UGC,
            "sourcing",
            "works",
            summary=(
                "Read one creator's newest works in our projects (up to `limit`): each cut's "
                "still, media and original links, project, platform, publish date and views of "
                "its latest post." + STAFF
            ),
            properties={"id": uuid("UGC creator id from sourcing +list.")},
            required=("id",),
            route=lambda a: Route(LIBRARY + "/{id}/works"),
            example="museoncli ugc sourcing +works --id <creator_id>",
            output="creator_id, the works (items) and limit.",
        ),
    ]
