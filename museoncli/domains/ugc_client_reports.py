"""Client report reads: a Campaign's daily and weekly client reports and their settings.

The route the web's report editor reads, ``/api/v2/ugc/agency/campaigns/{campaign_id}
/client-reports``: one read answers the Campaign's report settings (where and when
reports go), its generated reports and what the caller may do with each. Client
reports are the operating organization's: its owner, admin and the Campaign's
operators read them, and a Campaign shared to another organization does not open
them. Every request names the organization the command acts in in the
``organization_id`` query, as the write commands do. Generating, editing and sending
are their own commands.
"""

from __future__ import annotations

from typing import Any

from museoncli.domains._model import CommandSpec, Domain
from museoncli.domains._org_reads import Route, get, read, require_organization, uuid
from museoncli.execution import CommandContext

EXECUTORS: dict[str, Any] = {}

CAMPAIGN_ID = uuid("Campaign id (ugc campaign +list, or agency-campaign +list's id).")
REPORT_FIELDS = (
    "id",
    "type",
    "title",
    "status",
    "period_start",
    "period_end",
    "timezone",
    "revision",
    "due_at",
    "public_link",
    "message_url",
    "skipped_reason",
    "created_at",
    "updated_at",
)


async def _workspace(
    ctx: CommandContext, campaign_id: str, report_id: str | None = None
) -> dict[str, Any]:
    route = Route(
        "/ugc/agency/campaigns/{campaign_id}/client-reports",
        {"organization_id": require_organization(ctx), "report_id": report_id},
    )
    found = await get(ctx, route, {"campaign_id": campaign_id})
    return found if isinstance(found, dict) else {}


def _reports(workspace: dict[str, Any]) -> list[dict[str, Any]]:
    reports = workspace.get("reports")
    return [item for item in reports if isinstance(item, dict)] if isinstance(reports, list) else []


async def _list(ctx: CommandContext, arguments: dict[str, Any]) -> Any:
    reports = _reports(await _workspace(ctx, arguments["campaign_id"]))
    status = arguments.get("status")
    return {
        "items": [
            {key: report.get(key) for key in REPORT_FIELDS}
            for report in reports
            if status is None or report.get("status") == status
        ]
    }


async def _get(ctx: CommandContext, arguments: dict[str, Any]) -> Any:
    report_id = arguments["report_id"]
    workspace = await _workspace(ctx, arguments["campaign_id"], report_id)
    report = next((item for item in _reports(workspace) if item.get("id") == report_id), None)
    if report is None:
        raise RuntimeError("not_found: client_report_not_found: the Campaign has no such report")
    return report


async def _config(ctx: CommandContext, arguments: dict[str, Any]) -> Any:
    workspace = await _workspace(ctx, arguments["campaign_id"])
    return {
        key: workspace.get(key)
        for key in ("communication", "capabilities", "internal_group_access", "candidates")
    }


def specs() -> list[CommandSpec]:
    return [
        read(
            EXECUTORS,
            Domain.UGC,
            "client-report",
            "list",
            summary=(
                "List a Campaign's generated client reports (daily and weekly), newest first: "
                "type, title, status (draft, in review, ready, sent, skipped), period, revision "
                "and due time. The operating organization's owner, admin and the Campaign's "
                "operators; a shared Campaign's partner cannot read them."
            ),
            properties={
                "campaign_id": CAMPAIGN_ID,
                "status": {
                    "type": "string",
                    "enum": ["draft", "in-review", "ready", "sent", "skipped"],
                    "description": "Only reports in this status.",
                },
            },
            required=("campaign_id",),
            execute=_list,
            example="museoncli ugc client-report +list --campaign-id <campaign_id> --status ready",
            output="Report summaries (items).",
        ),
        read(
            EXECUTORS,
            Domain.UGC,
            "client-report",
            "get",
            summary=(
                "Read one client report in full: its Markdown, language variants, data scope, "
                "history and the actions the caller may take. Same visibility as "
                "client-report +list."
            ),
            properties={
                "campaign_id": CAMPAIGN_ID,
                "report_id": uuid("Report id from client-report +list."),
            },
            required=("campaign_id", "report_id"),
            execute=_get,
            # Sibling +get commands take the entity as --id; both spellings work here.
            flags={"report_id": ("--report-id", "--id")},
            example=(
                "museoncli ugc client-report +get --campaign-id <campaign_id> "
                "--report-id <report_id>"
            ),
        ),
        read(
            EXECUTORS,
            Domain.UGC,
            "client-report-config",
            "get",
            summary=(
                "Read a Campaign's client report settings: which reports are on, the client and "
                "internal groups they go to, schedule and language, with the settings' version "
                "that a settings write needs. Same visibility as client-report +list."
            ),
            properties={"campaign_id": CAMPAIGN_ID},
            required=("campaign_id",),
            execute=_config,
            example="museoncli ugc client-report-config +get --campaign-id <campaign_id>",
            output="data.communication (the settings and their version) and data.capabilities.",
        ),
    ]
