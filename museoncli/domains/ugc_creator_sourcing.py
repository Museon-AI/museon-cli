"""Creator Sourcing reads: the internal 创作者寻源 page (/creator-sourcing).

The routes the page calls, addressed by the organization:
``/api/v2/ugc/agency/{organization}/creator-library``, its ``/form-questions``, and its
per-person ``/applications`` and ``/works``. Everyone who joined the community or applied to
a project, with how they joined, what they declared, their projects and how their
posts did; per person, every form they filled in and their newest works with
views. MuseOn staff only, exactly as the page: the server checks that the key's
holder is staff and that the key's organization holds creator read, and answers
not found otherwise. The team's notes are edited in a signed-in browser only.
"""

from __future__ import annotations

import re
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


def _choices(description: str, *values: str) -> dict[str, Any]:
    return {**arr(choice(description, *values), maximum=len(values)), "description": description}


#: What the profile stores: `US`, and a language tag whose first part is lower case (`en`,
#: `zh-Hant`). Other spellings are refused here rather than matching nobody.
COUNTRY = "^[A-Za-z]{2}$"
LANGUAGE = "^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*$"
ANSWER = "^.*\\S.*::.+$"
#: The topics and content types the creator form offers (museon `CreatorDetails`).
CATEGORIES = (
    "beauty",
    "fashion",
    "food",
    "pets",
    "technology",
    "gaming",
    "home",
    "fitness",
    "travel",
    "parenting",
    "lifestyle",
    "other",
    "exploring",
)
CONTENT_TYPES = (
    "tutorial",
    "review",
    "unboxing",
    "vlog",
    "comedy",
    "testimonial",
    "screen-recording",
    "other",
    "exploring",
)


def _coded(description: str) -> dict[str, Any]:
    return {**arr(text(description, max_length=40), maximum=50), "description": description}


#: Each coded flag, its form, and the refusal that says what to type instead.
_CODED = (
    ("country", COUNTRY, "--country takes two-letter ISO codes such as US or BR, got {!r}"),
    (
        "language",
        LANGUAGE,
        "--language takes language codes such as en, es or zh-Hant, not names, got {!r}",
    ),
    (
        "answer",
        ANSWER,
        "--answer is QUESTION::VALUE, e.g. 'Which of these have you done before?::3D design' "
        "(questions and values from `museoncli ugc sourcing +questions`), got {!r}",
    ),
)


def _check_list(a: dict[str, Any]) -> None:
    """A value in the wrong form would match nobody and answer an empty page; refuse it."""
    for key, pattern, message in _CODED:
        for value in a.get(key) or ():
            if re.search(pattern, value) is None:
                raise ValueError(message.format(value))


def _language(tag: str) -> str:
    first, _, rest = tag.partition("-")
    return first.lower() + ("-" + rest if rest else "")


def _list_route(a: dict[str, Any]) -> Route:
    countries, languages = a.get("country"), a.get("language")
    return Route(
        LIBRARY,
        {
            "q": a.get("search"),
            "sort": a.get("sort"),
            "countries": [code.upper() for code in countries] if countries else None,
            "languages": [_language(tag) for tag in languages] if languages else None,
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
            "answer": a.get("answer"),
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
                "their latest form answers (`form_answers`), sample videos and work link, their "
                "projects, performance (posts, average and best views, viral posts, last post), "
                "latest stills and the team's note. Total in `total`. Narrow by form answers "
                "with --answer; `sourcing +questions` lists the questions and choices." + STAFF
            ),
            properties={
                "search": text("Name, handle, note or any form answer contains this."),
                "sort": choice(
                    "Order (default newest).",
                    "newest",
                    "avg-views",
                    "viral",
                    "followers",
                    "last-post",
                    "posts",
                ),
                "country": _coded(
                    "Two-letter ISO country code they declared, e.g. US. Repeatable."
                ),
                "language": _coded(
                    "Language code they speak, e.g. en, es, zh-Hant (not a language name). "
                    "Repeatable."
                ),
                "category": _choices("Primary topic they declared. Repeatable.", *CATEGORIES),
                "content_type": _choices("Content type they declared. Repeatable.", *CONTENT_TYPES),
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
                    "description": (
                        "Largest follower count at least this, among the accounts they post "
                        "with in our projects (the accounts on their forms are not measured)."
                    ),
                },
                "viral_only": {
                    "type": "boolean",
                    "description": "Only people with a confirmed post past 10,000 views.",
                },
                "answer": {
                    **arr(text("Form answer filter.", max_length=300), maximum=50),
                    "description": (
                        "Their latest answer to a form question holds this value, written "
                        "QUESTION::VALUE with the question and value exactly as "
                        "`sourcing +questions` lists them (question in any case). Repeatable: "
                        "values of one question match any, different questions must all match."
                    ),
                },
            },
            route=_list_route,
            check=_check_list,
            paging="offset",
            example=(
                "museoncli ugc sourcing +list --country US --language en "
                "--answer 'Which of these have you done before?::3D design' "
                "--sort avg-views --page-size 20"
            ),
            output="A page of creators (items), total, offset, limit and notes_visible.",
        ),
        read(
            EXECUTORS,
            Domain.UGC,
            "sourcing",
            "questions",
            summary=(
                "List the form questions creators in scope answered, most answered first: each "
                "question's label and type, how many people answered it, and for a choice "
                "question how many chose each value. Use a label and value with "
                "`sourcing +list --answer 'QUESTION::VALUE'`." + STAFF
            ),
            properties={},
            route=lambda a: Route(LIBRARY + "/form-questions"),
            example="museoncli ugc sourcing +questions",
            output="The questions (items), each with label, type, people and options.",
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
