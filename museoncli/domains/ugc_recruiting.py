"""UGC recruiting: recruitment links and email invitations of a campaign.

Links are the campaign's sign-up URLs (an `invite` link per channel, plus one
`discover` link for public discovery). Editing and revoking compare-and-set on the
link's `updated_at`; resending and revoking an invitation on its status. Sending an
invitation emails the creator, so it needs --yes like every other outbound write.
"""

from __future__ import annotations

import argparse
import re
from typing import Any

from museoncli.domains._model import CommandSpec, Domain
from museoncli.domains._shared import _direct_output_schema
from museoncli.domains._ugc_writes import (
    CAMPAIGN_ID,
    DRY_RUN,
    OUTBOUND,
    OUTBOUND_NOTE,
    ROLE_ENROLLMENT,
    WRITE,
    _ask_next_step,
    _get,
    _schema,
    _uuid,
    _uuid_property,
    _with_notes,
    add_dry_run,
    add_yes,
    call,
    find_paged,
    pick,
    require_found,
    text,
    uuid_or_none,
)
from museoncli.execution import CommandContext, compact_params, direct_enveloped

_PAGE_LIMIT = 100
LINK_KINDS = ["invite", "discover"]
INVITATION_STATUSES = ["open", "accepted", "revoked"]
_LINK_FIELDS = (
    "id",
    "kind",
    "name",
    "code",
    "url",
    "status",
    "group_name",
    "payscale_id",
    "auto_approve",
    "public_listing",
    "skip_trial",
    "uses",
    "updated_at",
)
_EDITABLE = ("name", "group_name", "payscale_id", "auto_approve", "public_listing", "skip_trial")
_INVITATION_FIELDS = (
    "id",
    "address",
    "status",
    "delivery_status",
    "expired",
    "expires_at",
    "url",
    "updated_at",
)
_CODE = re.compile(r"^[a-zA-Z0-9]{4,64}$")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _links_path(args: dict[str, Any]) -> str:
    return f"/campaigns/{args['campaign_id']}/recruitment-links"


def _invitations_path(args: dict[str, Any]) -> str:
    return f"/campaigns/{args['campaign_id']}/invitations"


async def _link(ctx: CommandContext) -> dict[str, Any]:
    args = ctx.arguments
    found, _ = await find_paged(ctx, _links_path(args), [args["id"]])
    require_found(found, [args["id"]], what="recruitment_link", where="this campaign")
    return found[args["id"]]


async def _invitation(ctx: CommandContext) -> dict[str, Any]:
    args = ctx.arguments
    found, _ = await find_paged(ctx, _invitations_path(args), [args["id"]])
    require_found(found, [args["id"]], what="invitation", where="this campaign")
    return found[args["id"]]


# -- executors -----------------------------------------------------------------


async def _execute_link_list(ctx: CommandContext) -> Any:
    args = ctx.arguments
    return await _get(
        ctx,
        _links_path(args),
        compact_params({"cursor": args.get("cursor"), "limit": args.get("page_size")}),
    )


async def _execute_link_create(ctx: CommandContext) -> Any:
    args = ctx.arguments
    if args["kind"] == "discover":
        body: dict[str, Any] = {}
        path = f"{_links_path(args)}/discovery"
    else:
        body = compact_params({field: args.get(field) for field in ("code", *_EDITABLE)})
        path = _links_path(args)
    data: dict[str, Any] = {"dry_run": args["dry_run"], "kind": args["kind"], "body": body}
    warnings: list[str] = []
    if body.get("auto_approve"):
        warnings.append("Creators who sign up through this link are approved without review.")
    if args["dry_run"]:
        page = await _get(ctx, _links_path(args), {"limit": 1})
        discovery = page.get("discovery") if isinstance(page, dict) else None
        if args["kind"] == "discover" and discovery:
            warnings.append("The campaign already has a discover link; the workbench returns it.")
        return data, warnings, [_ask_next_step("the link settings")]
    data["link"] = pick(await call(ctx, "POST", path, body or None), *_LINK_FIELDS)
    return data, warnings, []


async def _execute_link_update(ctx: CommandContext) -> Any:
    args = ctx.arguments
    link = await _link(ctx)
    before = {field: link.get(field) for field in _EDITABLE}
    after = {**before, **args["edits"]}
    changes = [
        {"field": field, "before": before[field], "after": after[field]}
        for field in _EDITABLE
        if field in args["edits"] and after[field] != before[field]
    ]
    data: dict[str, Any] = {
        "dry_run": args["dry_run"],
        "link": pick(link, *_LINK_FIELDS),
        "changes": changes,
    }
    if not changes:
        return data, ["Nothing differs from the link's settings; nothing was written."], []
    if args["dry_run"]:
        return data, [], [_ask_next_step("these changes")]
    # The edit replaces every setting: send the current ones with the changes applied.
    body = {
        **after,
        "auto_approve": bool(after.get("auto_approve")),
        "skip_trial": bool(after.get("skip_trial")),
        "expected_updated_at": link.get("updated_at"),
    }
    data["link"] = pick(
        await call(ctx, "PUT", f"{_links_path(args)}/{args['id']}", body), *_LINK_FIELDS
    )
    return data, [], []


async def _execute_link_revoke(ctx: CommandContext) -> Any:
    args = ctx.arguments
    link = await _link(ctx)
    data: dict[str, Any] = {"dry_run": args["dry_run"], "link": pick(link, *_LINK_FIELDS)}
    if link.get("status") == "revoked":
        return data, ["The link is already revoked; nothing was written."], []
    warnings = ["The link stops working at once; creators who open it can no longer sign up."]
    if args["dry_run"]:
        return data, warnings, [_ask_next_step("the link that would stop working")]
    data["link"] = pick(
        await call(
            ctx,
            "POST",
            f"{_links_path(args)}/{args['id']}/revoke",
            {"expected_updated_at": link.get("updated_at")},
        ),
        *_LINK_FIELDS,
    )
    return data, [], []


async def _execute_invitation_list(ctx: CommandContext) -> Any:
    args = ctx.arguments
    return await _get(
        ctx,
        _invitations_path(args),
        compact_params(
            {
                "status": args.get("status"),
                "cursor": args.get("cursor"),
                "limit": args.get("page_size"),
            }
        ),
    )


async def _execute_invitation_create(ctx: CommandContext) -> Any:
    args = ctx.arguments
    body = {"channel": "email", "address": args["email"]}
    data: dict[str, Any] = {"dry_run": args["dry_run"], "body": body}
    warnings = ["MuseOn emails the creator an invitation to this campaign."]
    if args["dry_run"]:
        # The open invitations, to spot one already sent to this address.
        open_rows: list[dict[str, Any]] = []
        cursor: str | None = None
        for _ in range(10):
            page = await _get(
                ctx,
                _invitations_path(args),
                compact_params({"status": "open", "limit": _PAGE_LIMIT, "cursor": cursor}),
            )
            page = page if isinstance(page, dict) else {}
            open_rows += [row for row in page.get("items") or [] if isinstance(row, dict)]
            cursor = page.get("next_cursor")
            if not cursor:
                break
        same = [
            row for row in open_rows if str(row.get("address") or "").lower() == args["email"].lower()
        ]
        if same:
            data["open_invitations_to_this_address"] = [pick(row, *_INVITATION_FIELDS) for row in same]
            warnings.append(
                "An open invitation to this address exists; resend it with ugc invitation "
                "+resend instead of sending another."
            )
        return data, warnings, [_ask_next_step("the address MuseOn would email")]
    data["invitation"] = pick(
        await call(ctx, "POST", _invitations_path(args), body), *_INVITATION_FIELDS
    )
    return data, [], []


async def _invitation_transition(ctx: CommandContext, route: str, warning: str) -> Any:
    args = ctx.arguments
    invitation = await _invitation(ctx)
    data: dict[str, Any] = {
        "dry_run": args["dry_run"],
        "invitation": pick(invitation, *_INVITATION_FIELDS),
    }
    if invitation.get("status") != "open":
        raise RuntimeError(
            f"conflict: invalid_transition: the invitation is {invitation.get('status')}; only an "
            "open invitation can be resent or revoked."
        )
    if args["dry_run"]:
        return data, [warning], [_ask_next_step("the invitation")]
    data["invitation"] = pick(
        await call(
            ctx,
            "POST",
            f"/invitations/{args['id']}/{route}",
            {"expected_status": invitation.get("status")},
        ),
        *_INVITATION_FIELDS,
    )
    return data, [], []


async def _execute_invitation_resend(ctx: CommandContext) -> Any:
    return await _invitation_transition(ctx, "resend", "MuseOn emails the invitation again.")


async def _execute_invitation_revoke(ctx: CommandContext) -> Any:
    return await _invitation_transition(
        ctx, "revoke", "The invitation link stops working; the creator can no longer accept it."
    )


# -- arguments -----------------------------------------------------------------


def _add_campaign(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--campaign-id", required=True)


def _campaign(args: argparse.Namespace) -> dict[str, Any]:
    return {"campaign_id": _uuid(args.campaign_id, flag="--campaign-id")}


def _page_size(args: argparse.Namespace) -> int:
    if not 1 <= args.page_size <= _PAGE_LIMIT:
        raise ValueError(f"--page-size must be between 1 and {_PAGE_LIMIT}.")
    return int(args.page_size)


def _add_list(parser: argparse.ArgumentParser) -> None:
    _add_campaign(parser)
    parser.add_argument("--cursor")
    parser.add_argument("--page-size", type=int, default=50)


def _list_args(args: argparse.Namespace) -> dict[str, Any]:
    return {**_campaign(args), "page_size": _page_size(args), **compact_params({"cursor": args.cursor})}


def _add_link_fields(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--name")
    parser.add_argument("--group-name")
    parser.add_argument("--payscale-id")
    parser.add_argument("--auto-approve", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--public-listing", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--skip-trial", action=argparse.BooleanOptionalAction, default=None)


def _link_fields(args: argparse.Namespace) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    if args.name is not None:
        fields["name"] = text(args.name, flag="--name", limit=120, required=True)
    if args.group_name is not None:
        fields["group_name"] = text(args.group_name, flag="--group-name", limit=120)
    if args.payscale_id is not None:
        fields["payscale_id"] = uuid_or_none(args.payscale_id, flag="--payscale-id")
    for field in ("auto_approve", "public_listing", "skip_trial"):
        value = getattr(args, field)
        if value is not None:
            fields[field] = bool(value)
    return fields


def _add_link_create(parser: argparse.ArgumentParser) -> None:
    _add_campaign(parser)
    parser.add_argument("--kind", choices=LINK_KINDS, default="invite")
    parser.add_argument("--code")
    _add_link_fields(parser)
    add_dry_run(parser)


def _link_create_args(args: argparse.Namespace) -> dict[str, Any]:
    fields = _link_fields(args)
    if args.code is not None:
        if not _CODE.match(args.code):
            raise ValueError("--code must be 4-64 letters or digits.")
        fields["code"] = args.code
    if args.kind == "discover" and fields:
        raise ValueError("A discover link takes no settings; drop the other flags.")
    return {**_campaign(args), "kind": args.kind, "dry_run": bool(args.dry_run), **fields}


def _add_link_update(parser: argparse.ArgumentParser) -> None:
    _add_campaign(parser)
    parser.add_argument("--id", required=True)
    _add_link_fields(parser)
    add_dry_run(parser)


def _link_update_args(args: argparse.Namespace) -> dict[str, Any]:
    edits = _link_fields(args)
    if not edits:
        raise ValueError(
            "Pass at least one setting to change: --name, --group-name, --payscale-id, "
            "--[no-]auto-approve, --[no-]public-listing or --[no-]skip-trial."
        )
    return {
        **_campaign(args),
        "id": _uuid(args.id, flag="--id"),
        "edits": edits,
        "dry_run": bool(args.dry_run),
    }


def _add_id_write(parser: argparse.ArgumentParser) -> None:
    _add_campaign(parser)
    parser.add_argument("--id", required=True)
    add_dry_run(parser)
    add_yes(parser)


def _id_write_args(args: argparse.Namespace) -> dict[str, Any]:
    return {**_campaign(args), "id": _uuid(args.id, flag="--id"), "dry_run": bool(args.dry_run)}


def _add_invitation_list(parser: argparse.ArgumentParser) -> None:
    _add_list(parser)
    parser.add_argument("--status", choices=INVITATION_STATUSES)


def _invitation_list_args(args: argparse.Namespace) -> dict[str, Any]:
    return {**_list_args(args), **compact_params({"status": args.status})}


def _add_invitation_create(parser: argparse.ArgumentParser) -> None:
    _add_campaign(parser)
    parser.add_argument("--email", required=True)
    add_dry_run(parser)
    add_yes(parser)


def _invitation_create_args(args: argparse.Namespace) -> dict[str, Any]:
    email = args.email.strip()
    if not _EMAIL.match(email):
        raise ValueError("--email must be one email address.")
    return {**_campaign(args), "email": email, "dry_run": bool(args.dry_run)}


# -- specs ---------------------------------------------------------------------

_PAGING = {
    "cursor": {"type": ["string", "null"], "description": "next_cursor from the previous page."},
    "page_size": {"type": "integer", "minimum": 1, "maximum": _PAGE_LIMIT, "default": 50},
}
_LINK_PROPERTIES = {
    "name": {"type": "string", "maxLength": 120, "description": "Name the team sees."},
    "group_name": {
        "type": "string",
        "maxLength": 120,
        "description": "Roster group sign-ups land in.",
    },
    "payscale_id": {
        "type": ["string", "null"],
        "description": "Payment structure sign-ups get ('none' for the default).",
    },
    "auto_approve": {"type": "boolean", "description": "Approve sign-ups without review."},
    "public_listing": {"type": "boolean", "description": "List the campaign publicly."},
    "skip_trial": {"type": "boolean", "description": "Sign-ups skip the trial."},
}
_LINK_ID = _uuid_property("Recruitment link ID (from ugc recruit-link +list).")
_INVITATION_ID = _uuid_property("Invitation ID (from ugc invitation +list).")
_LINK_OUTPUT = (
    "link: id, kind, name, code, url, status, group_name, payscale_id, auto_approve, "
    "public_listing, skip_trial, uses, updated_at"
)


def specs() -> list[CommandSpec]:
    domain = Domain.UGC
    campaign = "11111111-1111-4111-8111-111111111111"
    link = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
    invitation = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"
    return [
        CommandSpec(
            domain=domain,
            resource="recruit-link",
            shortcut="+list",
            summary=(
                "List a UGC campaign's recruitment links (sign-up URLs) with their settings and "
                "use counts; the discover link comes back as discovery." + ROLE_ENROLLMENT
            ),
            adapter_tool_name="ugc_recruit_link_list",
            input_schema=_schema({"campaign_id": CAMPAIGN_ID, **_PAGING}, ["campaign_id"]),
            output_schema=_direct_output_schema("items, discovery and next_cursor."),
            examples=[f"museoncli ugc recruit-link +list --campaign-id {campaign}"],
            add_arguments=_add_list,
            build_arguments=_list_args,
            risk_level="read",
            execution="direct",
        ),
        CommandSpec(
            domain=domain,
            resource="recruit-link",
            shortcut="+create",
            summary=(
                "Create a recruitment link for a UGC campaign: an invite link with its own name, "
                "code, roster group, payment structure and approval rule, or (--kind discover) "
                "the campaign's discover link. Paused or completed campaigns recruit nobody."
                + ROLE_ENROLLMENT
            ),
            adapter_tool_name="ugc_recruit_link_create",
            input_schema=_schema(
                {
                    "campaign_id": CAMPAIGN_ID,
                    "kind": {"type": "string", "enum": LINK_KINDS, "default": "invite"},
                    "code": {
                        "type": "string",
                        "pattern": "^[a-zA-Z0-9]{4,64}$",
                        "description": "Custom code in the URL; generated when left out.",
                    },
                    **_LINK_PROPERTIES,
                    "dry_run": DRY_RUN,
                },
                ["campaign_id"],
            ),
            output_schema=_direct_output_schema("dry_run, kind, body and " + _LINK_OUTPUT + "."),
            examples=[
                f"museoncli ugc recruit-link +create --campaign-id {campaign} --name 'TikTok ads' "
                "--group-name Wave2 --dry-run"
            ],
            add_arguments=_add_link_create,
            build_arguments=_link_create_args,
            **WRITE,
        ),
        CommandSpec(
            domain=domain,
            resource="recruit-link",
            shortcut="+update",
            summary=(
                "Change a recruitment link's settings; settings not passed keep their value. "
                "Compare-and-set on the link's updated_at." + ROLE_ENROLLMENT
            ),
            adapter_tool_name="ugc_recruit_link_update",
            input_schema=_schema(
                {
                    "campaign_id": CAMPAIGN_ID,
                    "id": _LINK_ID,
                    **_LINK_PROPERTIES,
                    "dry_run": DRY_RUN,
                },
                ["campaign_id", "id"],
            ),
            output_schema=_direct_output_schema("dry_run, " + _LINK_OUTPUT + " and changes."),
            examples=[
                f"museoncli ugc recruit-link +update --campaign-id {campaign} --id {link} "
                "--no-auto-approve --dry-run"
            ],
            add_arguments=_add_link_update,
            build_arguments=_link_update_args,
            **WRITE,
        ),
        CommandSpec(
            domain=domain,
            resource="recruit-link",
            shortcut="+revoke",
            summary=(
                "Revoke a recruitment link: it stops working at once." + OUTBOUND_NOTE
                + ROLE_ENROLLMENT
            ),
            adapter_tool_name="ugc_recruit_link_revoke",
            input_schema=_schema(
                {"campaign_id": CAMPAIGN_ID, "id": _LINK_ID, "dry_run": DRY_RUN},
                ["campaign_id", "id"],
            ),
            output_schema=_direct_output_schema("dry_run and " + _LINK_OUTPUT + "."),
            examples=[
                f"museoncli ugc recruit-link +revoke --campaign-id {campaign} --id {link} --dry-run"
            ],
            add_arguments=_add_id_write,
            build_arguments=_id_write_args,
            **OUTBOUND,
        ),
        CommandSpec(
            domain=domain,
            resource="invitation",
            shortcut="+list",
            summary=(
                "List a UGC campaign's email invitations: address, status, delivery status and "
                "expiry." + ROLE_ENROLLMENT
            ),
            adapter_tool_name="ugc_invitation_list",
            input_schema=_schema(
                {
                    "campaign_id": CAMPAIGN_ID,
                    "status": {"type": ["string", "null"], "enum": [*INVITATION_STATUSES, None]},
                    **_PAGING,
                },
                ["campaign_id"],
            ),
            output_schema=_direct_output_schema("items and next_cursor."),
            examples=[f"museoncli ugc invitation +list --campaign-id {campaign} --status open"],
            add_arguments=_add_invitation_list,
            build_arguments=_invitation_list_args,
            risk_level="read",
            execution="direct",
        ),
        CommandSpec(
            domain=domain,
            resource="invitation",
            shortcut="+create",
            summary=(
                "Invite a creator to a UGC campaign by email; MuseOn sends the invitation. The "
                "preview flags an open invitation already sent to the address." + OUTBOUND_NOTE
                + ROLE_ENROLLMENT
            ),
            adapter_tool_name="ugc_invitation_create",
            input_schema=_schema(
                {
                    "campaign_id": CAMPAIGN_ID,
                    "email": {"type": "string", "format": "email"},
                    "dry_run": DRY_RUN,
                },
                ["campaign_id", "email"],
            ),
            output_schema=_direct_output_schema("dry_run, body and invitation."),
            examples=[
                f"museoncli ugc invitation +create --campaign-id {campaign} "
                "--email creator@example.com --dry-run"
            ],
            add_arguments=_add_invitation_create,
            build_arguments=_invitation_create_args,
            **OUTBOUND,
        ),
        CommandSpec(
            domain=domain,
            resource="invitation",
            shortcut="+resend",
            summary="Email an open invitation again." + OUTBOUND_NOTE + ROLE_ENROLLMENT,
            adapter_tool_name="ugc_invitation_resend",
            input_schema=_schema(
                {"campaign_id": CAMPAIGN_ID, "id": _INVITATION_ID, "dry_run": DRY_RUN},
                ["campaign_id", "id"],
            ),
            output_schema=_direct_output_schema("dry_run and invitation."),
            examples=[
                f"museoncli ugc invitation +resend --campaign-id {campaign} --id {invitation} "
                "--dry-run"
            ],
            add_arguments=_add_id_write,
            build_arguments=_id_write_args,
            **OUTBOUND,
        ),
        CommandSpec(
            domain=domain,
            resource="invitation",
            shortcut="+revoke",
            summary=(
                "Revoke an open invitation: its link stops working." + OUTBOUND_NOTE
                + ROLE_ENROLLMENT
            ),
            adapter_tool_name="ugc_invitation_revoke",
            input_schema=_schema(
                {"campaign_id": CAMPAIGN_ID, "id": _INVITATION_ID, "dry_run": DRY_RUN},
                ["campaign_id", "id"],
            ),
            output_schema=_direct_output_schema("dry_run and invitation."),
            examples=[
                f"museoncli ugc invitation +revoke --campaign-id {campaign} --id {invitation} "
                "--dry-run"
            ],
            add_arguments=_add_id_write,
            build_arguments=_id_write_args,
            **OUTBOUND,
        ),
    ]


EXECUTORS = {
    "ugc.recruit-link-list": direct_enveloped(_execute_link_list),
    "ugc.recruit-link-create": _with_notes(_execute_link_create),
    "ugc.recruit-link-update": _with_notes(_execute_link_update),
    "ugc.recruit-link-revoke": _with_notes(_execute_link_revoke),
    "ugc.invitation-list": direct_enveloped(_execute_invitation_list),
    "ugc.invitation-create": _with_notes(_execute_invitation_create),
    "ugc.invitation-resend": _with_notes(_execute_invitation_resend),
    "ugc.invitation-revoke": _with_notes(_execute_invitation_revoke),
}
