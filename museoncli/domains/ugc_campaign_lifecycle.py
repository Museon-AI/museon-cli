"""UGC Campaign lifecycle: create, launch, pause, resume, complete, archive, restore, rename.

The routes are the ones the web's new-Campaign flow and Campaign header call
(`/api/v2/ugc/...`). Every status move carries `expected_status`: the status the
caller saw (``--expected-status``) or the one this command reads just before
writing. Who may move a Campaign is the server's decision: a UGC Campaign is
the operating team's (owner, admin, or an operator on the Campaign), a tracking
Campaign also its brand editors'.
"""

from __future__ import annotations

import argparse
from typing import Any

from museoncli.domains import _ugc_write as w
from museoncli.domains._model import CommandSpec
from museoncli.domains.ugc import _with_notes
from museoncli.execution import CommandContext

CAMPAIGN_STATUSES = ["draft", "active", "paused", "complete", "archived"]
CAMPAIGN_TYPES = ["ugc", "tracking"]
REQUIRED_UGC_PLATFORMS = ["tiktok", "instagram"]
"""A new UGC Campaign asks creators to connect these first (team default); Formats can change it."""

# action -> (statuses it starts from, status it ends in; None = the one it was archived from)
TRANSITIONS: dict[str, tuple[tuple[str, ...], str | None]] = {
    "launch": (("draft",), "active"),
    "pause": (("active",), "paused"),
    "resume": (("paused",), "active"),
    "complete": (("active", "paused"), "complete"),
    "archive": (("draft", "complete"), "archived"),
    "restore": (("archived",), None),
}
_TRANSITION_NOTES = {
    "launch": (
        "Launching opens the Campaign to creators: its apply link starts taking applications "
        "and it cannot go back to draft."
    ),
    "pause": "Pausing stops new work on the Campaign until it is resumed.",
    "resume": "Resuming puts the Campaign back to active.",
    "complete": (
        "Completing ends the Campaign for good: its posts stop syncing and the creators' "
        "accounts are released. It cannot be reopened, only archived."
    ),
    "archive": (
        "Archiving takes the Campaign out of every list and stops its sync; +restore brings "
        "it back."
    ),
    "restore": "Restoring moves the Campaign back to the status it was archived from.",
}


# -- organization fact the web's create flow uses ---------------------------


def _organization(ctx: CommandContext) -> str:
    if not ctx.organization_id:
        raise RuntimeError(
            "missing_organization: select one with `museoncli org select` or pass --organization-id"
        )
    return ctx.organization_id


async def _organization_kind(ctx: CommandContext) -> str | None:
    """`operator` or `brand`, as the web reads it from `/users/me/access`."""
    data = await ctx.api_data(
        ctx.cfg, "GET", "/users/me/access", params={"organization_id": ctx.organization_id}
    )
    organizations = data.get("organizations") if isinstance(data, dict) else None
    items = organizations.get("items") if isinstance(organizations, dict) else None
    row = next((item for item in w._dicts(items) if item.get("id") == ctx.organization_id), None)
    return row.get("kind") if row else None


async def _execute_create(ctx: CommandContext) -> Any:
    args = ctx.arguments
    campaign_type = args["campaign_type"]
    organization_id = _organization(ctx)
    if campaign_type == "ugc" and await _organization_kind(ctx) == "brand":
        raise ValueError(
            "A brand organization creates content tracking Campaigns only (--type tracking); "
            "UGC Campaigns are created by the operating team's organization, as in the web app."
        )
    body: dict[str, Any] = {
        "name": args["name"],
        "campaign_type": campaign_type,
        "product_id": args.get("product_id"),
        "allowed_platforms": list(w.PLATFORMS),
        "required_platforms": list(REQUIRED_UGC_PLATFORMS) if campaign_type == "ugc" else [],
    }
    data: dict[str, Any] = {
        "dry_run": args["dry_run"],
        "organization": {"id": organization_id},
        "campaign": {**body, "status": "draft"},
    }
    if args["dry_run"]:
        return data, [], w.ask("the Campaign that would be created")
    # The server picks where the Campaign lives: the product's home, else the organization's.
    created = await w.call(ctx, "POST", f"/organizations/{organization_id}/campaigns", body=body)
    data["campaign"] = w.campaign_line(created)
    steps = [
        "The Campaign is a draft. Set it up (ugc campaign-settings +update, ugc payscale, "
        "ugc contract-template +set, ugc brief +create) and launch it with ugc campaign +launch."
        if campaign_type == "ugc"
        else "The tracking Campaign is a draft; add creators or posts with campaign-monitor "
        "using data.campaign.monitor_collection_id, and launch it with ugc campaign +launch."
    ]
    return data, [], steps


async def _execute_transition(ctx: CommandContext, action: str) -> Any:
    args = ctx.arguments
    view = await w.read_campaign(ctx, args["id"])
    campaign = view["campaign"]
    status = campaign.get("status")
    w.check_token("status", status, args.get("expected_status"))
    sources, target = TRANSITIONS[action]
    if status not in sources:
        raise RuntimeError(
            f"conflict: invalid_transition: the Campaign is {status}; {action} starts from "
            f"{' or '.join(sources)}."
        )
    data: dict[str, Any] = {
        "dry_run": args["dry_run"],
        "campaign": w.campaign_line(campaign),
        "before": status,
        "after": target,
    }
    warnings = [_TRANSITION_NOTES[action]]
    if action == "launch":
        launchability = view.get("launchability") if isinstance(view.get("launchability"), dict) else {}
        data["launchability"] = launchability
        if launchability and not launchability.get("ok", True):
            warnings.append(
                "The Campaign is not ready to launch: the workbench refuses it until the "
                "launchability reasons are fixed."
            )
    if args["dry_run"]:
        return data, warnings, w.ask(f"the Campaign and the move from {status}")
    written = await w.call(
        ctx, "POST", f"/campaigns/{args['id']}/{action}", body={"expected_status": status}
    )
    data["campaign"] = w.campaign_line(written)
    data["after"] = data["campaign"].get("status")
    return data, [], []


async def _execute_rename(ctx: CommandContext) -> Any:
    args = ctx.arguments
    view = await w.read_campaign(ctx, args["id"])
    campaign = view["campaign"]
    data: dict[str, Any] = {
        "dry_run": args["dry_run"],
        "campaign": w.campaign_line(campaign),
        "before": campaign.get("name"),
        "after": args["name"],
    }
    if campaign.get("name") == args["name"]:
        return data, [w.nothing_to_write("the current name")], []
    if args["dry_run"]:
        return data, [], w.ask("the old and new name")
    written = await w.call(ctx, "POST", f"/campaigns/{args['id']}/rename", body={"name": args["name"]})
    data["campaign"] = w.campaign_line(written)
    return data, [], []


def _transition_executor(action: str):
    async def run(ctx: CommandContext) -> Any:
        return await _execute_transition(ctx, action)

    return _with_notes(run)


# -- arguments ---------------------------------------------------------------


def _name(value: str) -> str:
    name = value.strip()
    if not name:
        raise ValueError("--name must not be blank.")
    if len(name) > 200:
        raise ValueError("--name must be at most 200 characters.")
    return name


def _add_create_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--name", required=True)
    parser.add_argument("--type", dest="campaign_type", choices=CAMPAIGN_TYPES, default="ugc")
    parser.add_argument("--product-id")
    w.add_dry_run(parser)


def _build_create_arguments(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "name": _name(args.name),
        "campaign_type": args.campaign_type,
        "product_id": w._uuid(args.product_id, flag="--product-id") if args.product_id else None,
        "dry_run": bool(args.dry_run),
    }


def _add_transition_arguments(*, confirm: bool):
    def add(parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--id", required=True)
        parser.add_argument("--expected-status", choices=CAMPAIGN_STATUSES)
        w.add_dry_run(parser)
        if confirm:
            w.add_yes(parser)

    return add


def _build_transition_arguments(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "id": w._uuid(args.id, flag="--id"),
        **({"expected_status": args.expected_status} if args.expected_status else {}),
        "dry_run": bool(args.dry_run),
    }


def _add_rename_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--id", required=True)
    parser.add_argument("--name", required=True)
    w.add_dry_run(parser)


def _build_rename_arguments(args: argparse.Namespace) -> dict[str, Any]:
    return {"id": w._uuid(args.id, flag="--id"), "name": _name(args.name), "dry_run": bool(args.dry_run)}


# -- specs -------------------------------------------------------------------

_ID = w.uuid_property("UGC campaign ID (from ugc campaign +list).")
_EXPECTED_STATUS = {
    "type": "string",
    "enum": CAMPAIGN_STATUSES,
    "description": (
        "The status you last read; the move fails instead of acting on a Campaign that moved "
        "on. Left out, the status this command reads first is used."
    ),
}
_ROLE = (
    " Role: owner, admin, or an operator on the Campaign (a content tracking Campaign also its "
    "brand editors); the server decides."
)
_TRANSITION_SUMMARIES = {
    "launch": (
        "Launch a draft Campaign: it goes active (a UGC one opens its apply link to creators). "
        "--dry-run returns the status move and launchability (ok, reasons) without writing."
    ),
    "pause": "Pause an active Campaign. --dry-run returns the status move without writing.",
    "resume": "Resume a paused Campaign. --dry-run returns the status move without writing.",
    "complete": (
        "Complete (end) an active or paused Campaign: sync stops and creators' accounts are "
        "released; it cannot reopen. --dry-run returns the status move without writing."
    ),
    "archive": (
        "Archive a draft or completed Campaign: it leaves every list and stops syncing; "
        "+restore brings it back. --dry-run returns the status move without writing."
    ),
    "restore": (
        "Restore an archived Campaign to the status it was archived from. --dry-run returns "
        "the status move without writing."
    ),
}
_TRANSITION_KIND = {
    "launch": w.CONFIRMED_WRITE,
    "pause": w.WRITE,
    "resume": w.WRITE,
    "complete": w.DESTRUCTIVE,
    "archive": w.DESTRUCTIVE,
    "restore": w.WRITE,
}


def specs() -> list[CommandSpec]:
    campaign = w.CAMPAIGN
    built = [
        w.spec(
            resource="campaign",
            shortcut="+create",
            summary=(
                "Create a Campaign in the selected organization, as the web's new-Campaign page "
                "does: a draft named --name, on TikTok, Instagram, YouTube and Facebook, with "
                "its default payscale. --type ugc (operating-team organizations only; creators "
                "must connect TikTok and Instagram) or tracking (content tracking). --dry-run "
                "returns what would be created without writing." + w.CONFIRM_FIRST + _ROLE
            ),
            adapter="ugc_campaign_create",
            properties={
                "name": {"type": "string", "maxLength": 200, "description": "Campaign name."},
                "campaign_type": {
                    "type": "string",
                    "enum": CAMPAIGN_TYPES,
                    "default": "ugc",
                    "description": "ugc (creators make content) or tracking (follow posts).",
                },
                "product_id": w.uuid_property("The organization's product the Campaign promotes."),
                "dry_run": w.DRY_RUN,
            },
            required=["name"],
            output_description="dry_run, organization and campaign (id, name, type, status, ...).",
            examples=[
                "museoncli ugc campaign +create --name 'Spring launch' --type ugc --dry-run",
                "museoncli ugc campaign +create --name 'Brand mentions' --type tracking",
            ],
            add_arguments=_add_create_arguments,
            build_arguments=_build_create_arguments,
            kind=w.WRITE,
        ),
    ]
    for action, summary in _TRANSITION_SUMMARIES.items():
        kind = _TRANSITION_KIND[action]
        confirm = bool(kind.get("requires_confirmation"))
        tail = w.CONFIRM_YES if confirm else w.CONFIRM_FIRST
        built.append(
            w.spec(
                resource="campaign",
                shortcut=f"+{action}",
                summary=summary + tail + _ROLE,
                adapter=f"ugc_campaign_{action}",
                properties={"id": _ID, "expected_status": _EXPECTED_STATUS, "dry_run": w.DRY_RUN},
                required=["id"],
                output_description="dry_run, campaign, before and after status"
                + (", launchability." if action == "launch" else "."),
                examples=[f"museoncli ugc campaign +{action} --id {campaign} --dry-run"],
                add_arguments=_add_transition_arguments(confirm=confirm),
                build_arguments=_build_transition_arguments,
                kind=kind,
            )
        )
    built.append(
        w.spec(
            resource="campaign",
            shortcut="+rename",
            summary=(
                "Rename a Campaign in any status; its tracking pages' title follows. --dry-run "
                "returns the old and new name without writing." + w.CONFIRM_FIRST
                + " Role: owner, admin, or an operator or editor on the Campaign."
            ),
            adapter="ugc_campaign_rename",
            properties={
                "id": _ID,
                "name": {"type": "string", "maxLength": 200, "description": "The new name."},
                "dry_run": w.DRY_RUN,
            },
            required=["id", "name"],
            output_description="dry_run, campaign, before and after name.",
            examples=[f"museoncli ugc campaign +rename --id {campaign} --name 'Spring launch EU' --dry-run"],
            add_arguments=_add_rename_arguments,
            build_arguments=_build_rename_arguments,
            kind=w.WRITE,
        )
    )
    return built


EXECUTORS = {
    "ugc.campaign-create": _with_notes(_execute_create),
    **{f"ugc.campaign-{action}": _transition_executor(action) for action in TRANSITIONS},
    "ugc.campaign-rename": _with_notes(_execute_rename),
}
