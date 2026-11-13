"""Campaign setup reads: everything the Campaign setup page (/campaigns/{id}/setup) reads.

``--campaign-id`` is the UGC campaign id (``ugc campaign +list``, or the ``id`` of
``campaign-monitor agency-campaign +list``), not a campaign-monitor collection id.

- ``campaign-settings +get``: the page's Campaign view -- type, status, settings
  (approval mode, platforms, budget cap, language), product and promotion context,
  readiness and confirmed steps, the briefs, and for the Campaign's team also the
  payscales, pay defaults and contract template.
- One command per section the page reads beside it: staff (PM/OP), delivery targets,
  payscales and rates, the contract template, the Discord server link, DM rules and
  automations.
- ``campaign-setup +get`` reads all of those at once (a fixed handful of requests) and
  reports a section the caller may not read under ``unavailable`` instead of failing.

Who reads what is the server's: the Campaign view is open to everyone who may see the
Campaign (members and shares included); the operations sections to its owner/admin
and its operators, not members.
"""

from __future__ import annotations

import asyncio
from typing import Any

from museoncli.domains._model import CommandSpec, Domain
from museoncli.domains._org_reads import Route, choice, get, read, uuid
from museoncli.execution import CommandContext

EXECUTORS: dict[str, Any] = {}

CAMPAIGN = "/ugc/campaigns/{campaign_id}"
CAMPAIGN_ID = uuid(
    "UGC campaign id (ugc campaign +list, or agency-campaign +list's id), not a "
    "campaign-monitor collection id."
)
TEAM = (
    " Owner/admin and the Campaign's operators of the organization that owns it; members "
    "cannot read it."
)

#: Section -> (route suffix, what it is). The order is the setup page's.
SECTIONS: dict[str, tuple[str, str]] = {
    "settings": ("", "the Campaign view: type, settings, product, readiness, briefs"),
    "staff": ("/staff", "PM / OP"),
    "targets": ("/targets", "delivery targets"),
    "payscales": ("/payscales", "payscales and their rates"),
    "contract-template": ("/contract-template", "the contract template"),
    "discord": ("/discord/guild-link", "the Discord server link"),
    "dm-rules": ("/dm-rules", "DM auto-reply rules"),
    "dm-automations": ("/dm-automations", "DM automations"),
}


async def _section(ctx: CommandContext, campaign_id: str, suffix: str) -> tuple[bool, Any]:
    try:
        return True, await get(ctx, Route(CAMPAIGN + suffix), {"campaign_id": campaign_id})
    except Exception as error:  # noqa: BLE001 - one unreadable section never hides the rest
        status = getattr(error, "status_code", None)
        detail = getattr(error, "detail", None)
        code = detail.get("code") if isinstance(detail, dict) else None
        return False, {"http_status": status, "code": code, "message": str(error)[:300]}


async def _setup(ctx: CommandContext, arguments: dict[str, Any]) -> Any:
    wanted = [name.replace("_", "-") for name in (arguments.get("section") or [])] or list(SECTIONS)
    campaign_id = arguments["campaign_id"]
    results = await asyncio.gather(
        *(_section(ctx, campaign_id, SECTIONS[name][0]) for name in wanted)
    )
    sections: dict[str, Any] = {}
    unavailable: dict[str, Any] = {}
    for name, (ok, value) in zip(wanted, results, strict=True):
        (sections if ok else unavailable)[name] = value
    if not sections:
        first = next(iter(unavailable.values()))
        raise RuntimeError(
            f"HTTP {first.get('http_status') or 404}: no section of this Campaign is readable"
        )
    return {"campaign_id": campaign_id, "sections": sections, "unavailable": unavailable}


def _one(resource: str, action: str, suffix: str, summary: str, example_tail: str = "") -> Any:
    return read(
        EXECUTORS,
        Domain.UGC,
        resource,
        action,
        summary=summary,
        properties={"campaign_id": CAMPAIGN_ID},
        required=("campaign_id",),
        route=lambda a: Route(CAMPAIGN + suffix),
        example=f"museoncli ugc {resource} +{action} --campaign-id <campaign_id>{example_tail}",
    )


def specs() -> list[CommandSpec]:
    return [
        _one(
            "campaign-settings",
            "get",
            "",
            "Read a Campaign's setup as its setup page does: type, status, settings (approval "
            "mode, platforms, budget cap, language), product and promotion context, readiness, "
            "confirmed steps and briefs; for the Campaign's team also payscales, pay defaults "
            "and the contract template. Anyone who may see the Campaign reads it.",
        ),
        _one(
            "campaign-staff",
            "list",
            "/staff",
            "List a Campaign's staff (PM / OP) with their roles." + TEAM,
        ),
        _one(
            "delivery-target",
            "list",
            "/targets",
            "List a Campaign's delivery targets (posts, videos or views per period) and their "
            "progress." + TEAM,
        ),
        _one(
            "payscale",
            "list",
            "/payscales",
            "List a Campaign's payscales with their rates (base fee, view tiers, bonuses), in "
            "the order the setup page shows them." + TEAM,
        ),
        _one(
            "contract-template",
            "get",
            "/contract-template",
            "Read a Campaign's contract template: its text, variables and signing parties." + TEAM,
        ),
        _one(
            "discord-server",
            "get",
            "/discord/guild-link",
            "Read the Discord server a Campaign is linked to and the link's state." + TEAM,
        ),
        _one(
            "dm-rule",
            "list",
            "/dm-rules",
            "List a Campaign's DM auto-reply rules (keyword, reply, link)." + TEAM,
        ),
        _one(
            "dm-automation",
            "list",
            "/dm-automations",
            "List a Campaign's DM automations and whether each is on." + TEAM,
        ),
        read(
            EXECUTORS,
            Domain.UGC,
            "campaign-setup",
            "get",
            summary=(
                "Read everything a Campaign's setup page reads in one call: settings, staff, "
                "delivery targets, payscales, contract template, Discord server and DM rules / "
                "automations (--section narrows it). A section the caller may not read is listed "
                "under data.unavailable with its HTTP status instead of failing the command: "
                "members read settings only."
            ),
            properties={
                "campaign_id": CAMPAIGN_ID,
                "section": {
                    "type": "array",
                    "items": choice("A section to read.", *SECTIONS),
                    "maxItems": len(SECTIONS),
                    "description": "Only these sections (repeat the flag); default all.",
                },
            },
            required=("campaign_id",),
            execute=_setup,
            example=(
                "museoncli ugc campaign-setup +get --campaign-id <campaign_id> "
                "--section settings --section payscales"
            ),
            output="data.sections (by name), data.unavailable (name -> http_status, code).",
        ),
    ]
