"""Task queue reads: the 任务 page (/tasks) of the new interface.

The same routes the web's task page calls, addressed by the organization the
command acts in: ``/api/v2/ugc/agency/{organization}/tasks`` (one queue, a page at
a time), ``.../tasks/summary`` (each queue's count) and ``/api/v2/ugc/tasks/{id}``
with its events (comments, claims, actions). The server decides which tasks a
login sees: owners and admins every Campaign's, an operator the Campaigns assigned
to them, a member reads only. Writes (claim, comment, due date, actions) are their
own commands.
"""

from __future__ import annotations

from typing import Any

from museoncli.domains._model import CommandSpec, Domain
from museoncli.domains._org_reads import (
    B,
    D,
    TZ,
    Route,
    choice,
    get,
    read,
    text,
    uuid,
)
from museoncli.execution import CommandContext

EXECUTORS: dict[str, Any] = {}

INBOX = "/ugc/agency/{organization_id}/tasks"
QUEUES = ("media", "onboarding", "creators", "posts", "viral", "invites", "client-reports", "all")
SCOPE = choice(
    "my-campaigns: only the Campaigns you are staff of or tasks assigned to you; all: every "
    "Campaign you may see (the default for owners and admins).",
    "my-campaigns",
    "all",
)
CAMPAIGN = uuid("Only this Campaign's tasks (id from ugc campaign +list or agency-campaign +list).")


async def _task_with_events(ctx: CommandContext, arguments: dict[str, Any]) -> Any:
    task_id = arguments["id"]
    task = await get(ctx, Route("/ugc/tasks/{id}"), {"id": task_id})
    if arguments.get("with_events") is False:
        return {"task": task}
    events = await get(ctx, Route("/ugc/tasks/{id}/events"), {"id": task_id})
    return {"task": task, "events": events}


def specs() -> list[CommandSpec]:
    ugc = Domain.UGC
    task_id = "11111111-1111-4111-8111-111111111111"
    return [
        read(
            EXECUTORS,
            ugc,
            "task",
            "list",
            summary=(
                "List one queue of the organization's tasks, as the Tasks page shows it: media "
                "review, onboarding, creators, posts, viral, invites, client reports, or all. Each "
                "row carries its kind, status, Campaign, subject, due time and the actions the "
                "caller may take. Owner/admin see every Campaign's tasks, an operator their "
                "assigned Campaigns', a member reads only."
            ),
            properties={
                "queue": {**choice("Which queue (default media).", *QUEUES)},
                "campaign_id": CAMPAIGN,
                "creator_id": uuid("Only tasks about this UGC creator."),
                "creative_id": uuid("Only tasks about this creative."),
                "search": text("Creator, Campaign or task title contains this."),
                "platform": choice(
                    "Only post tasks on this platform.",
                    "tiktok",
                    "instagram",
                    "youtube",
                    "facebook",
                    "x",
                ),
                "sort": choice("oldest (default) or newest first.", "oldest", "newest"),
                "min_followers": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Only post tasks whose account has at least this many followers.",
                },
                "country": {
                    "type": "array",
                    "items": {"type": "string", "pattern": "^[A-Z]{2}$"},
                    "maxItems": 256,
                    "description": "Only creators in these ISO countries (repeat the flag).",
                },
                "posted_from": {**D, "description": "Post tasks published on or after this day."},
                "posted_to": {**D, "description": "Post tasks published on or before this day."},
                "timezone": {**TZ, "description": "IANA timezone of --posted-from/--posted-to."},
                "actor": choice(
                    "operator: tasks whose next step is yours; others: waiting on a creator or "
                    "the system.",
                    "operator",
                    "others",
                ),
                "scope": SCOPE,
            },
            route=lambda a: Route(
                INBOX,
                {
                    "queue": a.get("queue"),
                    "campaign": a.get("campaign_id"),
                    "creator": a.get("creator_id"),
                    "creative": a.get("creative_id"),
                    "search": a.get("search"),
                    "platform": a.get("platform"),
                    "sort": a.get("sort"),
                    "min_followers": a.get("min_followers"),
                    "country": a.get("country"),
                    "posted_from": a.get("posted_from"),
                    "posted_to": a.get("posted_to"),
                    "timezone": a.get("timezone"),
                    "actor": a.get("actor"),
                    "scope": a.get("scope"),
                },
            ),
            paging="cursor",
            example="museoncli ugc task +list --queue media --actor operator",
            output="A page of task rows (items) and next_cursor.",
        ),
        read(
            EXECUTORS,
            ugc,
            "task-summary",
            "get",
            summary=(
                "Count the organization's open tasks per queue, as the Tasks page's tabs show "
                "them, with what waits on you versus a creator or the system. Same visibility "
                "as task +list."
            ),
            properties={"campaign_id": CAMPAIGN, "scope": SCOPE},
            route=lambda a: Route(
                INBOX + "/summary", {"campaign": a.get("campaign_id"), "scope": a.get("scope")}
            ),
            example="museoncli ugc task-summary +get --scope my-campaigns",
            output="Per-queue counts.",
        ),
        read(
            EXECUTORS,
            ugc,
            "task",
            "get",
            summary=(
                "Read one task as its drawer shows it: subject, status, assignee, due time, "
                "available actions, and its events (comments, claims, actions taken), oldest "
                "first. --no-with-events skips the events."
            ),
            properties={
                "id": uuid("Task id from task +list."),
                "with_events": {**B, "description": "Also read its events (default true)."},
            },
            required=("id",),
            execute=_task_with_events,
            example=f"museoncli ugc task +get --id {task_id}",
            output="data.task (the task) and data.events (its history, comments included).",
        ),
    ]
