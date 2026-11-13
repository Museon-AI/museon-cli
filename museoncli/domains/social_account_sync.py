"""Social account sync and unbinding: refresh bound accounts from the platform, or disconnect one.

The routes are the ones the Social Accounts page calls (``/api/v1/social-accounts``). They work
with the organization alone (``X-Organization-Id``): a profile or account id is looked up where
it is held, inside that organization. Syncing and unbinding take owner, admin or operator
(social account edit), which the server decides.

``+sync-all`` syncs the caller's own landing workspace in the organization, not every
workspace in it; sync a profile that lives elsewhere with ``+sync --profile-id``.
"""

from __future__ import annotations

import argparse
from typing import Any

from museoncli.domains._model import CommandSpec, Domain
from museoncli.domains._org_commands import (
    DRY_RUN_PROPERTY,
    add_structured_arguments,
    merged_input,
    output_schema,
    reject_unknown,
    require,
    schema,
    string_property,
    uuid_property,
    with_notes,
)
from museoncli.domains._writes import uuid_arg
from museoncli.execution import CommandContext

_ROLE = " Needs owner, admin or operator."
_PROFILE_ID = string_property(
    "Late profile ID: the late_profile_id of a bound account (social-account +get), not a "
    "MuseOn UUID."
)
_ACCOUNT_ID = uuid_property(
    "ID of the bound-account row (the late_social_accounts id), not a pool account ID."
)
_SYNC = {"profile_id": _PROFILE_ID, "dry_run": DRY_RUN_PROPERTY}
_SYNC_ALL = {"dry_run": DRY_RUN_PROPERTY}
_UNBIND = {"account_id": _ACCOUNT_ID, "dry_run": DRY_RUN_PROPERTY}


# -- executors ---------------------------------------------------------------


async def _execute_sync(ctx: CommandContext) -> Any:
    profile_id = ctx.arguments["profile_id"]
    data = await ctx.api_data(ctx.cfg, "POST", f"/social-accounts/profiles/{profile_id}/sync")
    return (
        data,
        [
            "Syncing re-reads the profile's accounts from the platform and relinks them; it "
            "is safe to repeat."
        ],
        ["museoncli social-account +list"],
    )


async def _execute_sync_all(ctx: CommandContext) -> Any:
    data = await ctx.api_data(ctx.cfg, "POST", "/social-accounts/sync-all-accounts")
    return (
        data,
        [
            "Only the caller's landing workspace in this organization was synced; profiles "
            "held elsewhere need social-account +sync --profile-id."
        ],
        ["museoncli social-account +list"],
    )


async def _execute_unbind(ctx: CommandContext) -> Any:
    account_id = ctx.arguments["account_id"]
    if ctx.arguments.get("dry_run"):
        return (
            {"dry_run": True, "would_unbind": {"account_id": account_id}},
            [
                "Unbinding disconnects the account from its platform authorization and removes "
                "its binding; it cannot be undone from the CLI. The account has to be "
                "connected again (social-account +create-connect-link) to publish."
            ],
            ["Show the user which account goes, ask them, then run again with --yes."],
        )
    await ctx.api_data(ctx.cfg, "DELETE", f"/social-accounts/accounts/{account_id}")
    return {"unbound": True, "account_id": account_id}, [], []


# -- arguments ---------------------------------------------------------------


def _dry_run(args: argparse.Namespace, payload: dict[str, Any]) -> None:
    payload["dry_run"] = bool(getattr(args, "dry_run", False) or payload.get("dry_run"))


def _add_sync_arguments(parser: argparse.ArgumentParser) -> None:
    add_structured_arguments(parser)
    parser.add_argument("--profile-id")
    parser.add_argument("--dry-run", action="store_true")


def _build_sync_arguments(args: argparse.Namespace) -> dict[str, Any]:
    payload = merged_input(args, ("profile_id",))
    reject_unknown(payload, _SYNC)
    require(payload, "profile_id")
    payload["profile_id"] = str(payload["profile_id"]).strip()
    _dry_run(args, payload)
    return payload


def _add_sync_all_arguments(parser: argparse.ArgumentParser) -> None:
    add_structured_arguments(parser)
    parser.add_argument("--dry-run", action="store_true")


def _build_sync_all_arguments(args: argparse.Namespace) -> dict[str, Any]:
    payload = merged_input(args, ())
    reject_unknown(payload, _SYNC_ALL)
    _dry_run(args, payload)
    return payload


def _add_unbind_arguments(parser: argparse.ArgumentParser) -> None:
    add_structured_arguments(parser)
    parser.add_argument("--account-id")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--yes", action="store_true")


def _build_unbind_arguments(args: argparse.Namespace) -> dict[str, Any]:
    payload = merged_input(args, ("account_id",))
    reject_unknown(payload, _UNBIND)
    require(payload, "account_id")
    payload["account_id"] = uuid_arg(payload["account_id"], flag="--account-id")
    _dry_run(args, payload)
    return payload


# -- specs -------------------------------------------------------------------

_EXAMPLE_ACCOUNT = "72defd40-39ad-40d3-8105-8f23a9a016da"


def specs() -> list[CommandSpec]:
    base: dict[str, Any] = {"domain": Domain.SOCIAL_ACCOUNT, "execution": "direct"}
    return [
        CommandSpec(
            **base,
            shortcut="+sync",
            summary=(
                "Sync one Late profile's accounts from the platform: refresh each account's "
                "name, avatar and status and relink it to its creator account. Repeating it is "
                "safe." + _ROLE
            ),
            risk_level="write",
            adapter_tool_name="social_account_sync",
            input_schema=schema(_SYNC, ["profile_id"]),
            output_schema=output_schema("data: the sync result the server returns."),
            examples=["museoncli social-account +sync --profile-id 66b2f0c1a9d3e4f5a6b7c8d9"],
            add_arguments=_add_sync_arguments,
            build_arguments=_build_sync_arguments,
            supports_dry_run=True,
        ),
        CommandSpec(
            **base,
            shortcut="+sync-all",
            summary=(
                "Sync every bound profile in the caller's own landing workspace of the "
                "selected organization (not every workspace in it). Repeating it is safe."
                + _ROLE
            ),
            risk_level="write",
            adapter_tool_name="social_account_sync_all",
            input_schema=schema(_SYNC_ALL),
            output_schema=output_schema("data: the sync result the server returns."),
            examples=["museoncli social-account +sync-all"],
            add_arguments=_add_sync_all_arguments,
            build_arguments=_build_sync_all_arguments,
            supports_dry_run=True,
        ),
        CommandSpec(
            **base,
            shortcut="+unbind",
            summary=(
                "Unbind (disconnect) one social account: its platform authorization is "
                "revoked and the binding removed; it cannot be undone from the CLI. --account-id "
                "is the bound-account row's id, not a pool account ID. --dry-run shows what "
                "would go and writes nothing; show it to the user, then run with --yes."
                + _ROLE
            ),
            risk_level="destructive",
            adapter_tool_name="social_account_unbind",
            input_schema=schema(_UNBIND, ["account_id"]),
            output_schema=output_schema("data.would_unbind (dry run) or data.unbound."),
            examples=[
                f"museoncli social-account +unbind --account-id {_EXAMPLE_ACCOUNT} --dry-run",
                f"museoncli social-account +unbind --account-id {_EXAMPLE_ACCOUNT} --yes",
            ],
            add_arguments=_add_unbind_arguments,
            build_arguments=_build_unbind_arguments,
            supports_dry_run=True,
            dry_run_reads_server=True,
            requires_confirmation=True,
        ),
    ]


EXECUTORS = {
    "social-account.sync": with_notes(_execute_sync),
    "social-account.sync-all": with_notes(_execute_sync_all),
    "social-account.unbind": with_notes(_execute_unbind),
}
