"""Social account tags: the organization's private labels on an account (filter and group by).

Tags live on the Agent CLI account resource (``/agent-cli/social-accounts/{id}/workspace-tags``),
which replaces the whole tag set; the organization is the addressed one. ``+add`` and
``+remove`` read the account's tags (``social-account +get``), change them and write the full
set back. The route has no version check: a tag change someone makes between that read and
the write is overwritten. ``--dry-run`` reads and shows before and after without writing.

Changing tags takes owner, admin or operator (social account edit), decided by the server.
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
    string_list,
    uuid_property,
    with_notes,
)
from museoncli.execution import CommandContext, agent_domain_result

MAX_TAGS = 50

_ACCOUNT_ID = uuid_property("Social account ID (social-account +list / +get).")
_TAGS = {
    "type": "array",
    "items": {"type": "string", "minLength": 1, "maxLength": 100},
    "maxItems": MAX_TAGS,
    "description": "Tags; repeat --tag for several (an account holds at most 50).",
}
_SET = {
    "id": _ACCOUNT_ID,
    "tags": {**_TAGS, "description": "The full tag set; [] (or --clear) removes every tag."},
    "dry_run": DRY_RUN_PROPERTY,
}
_CHANGE = {"id": _ACCOUNT_ID, "tags": {**_TAGS, "minItems": 1}, "dry_run": DRY_RUN_PROPERTY}
_ROLE = " Needs owner, admin or operator."
_RACE = " No version check: a tag change made between the read and the write is overwritten."


async def _current_tags(ctx: CommandContext, account_id: str) -> list[str]:
    account = agent_domain_result(
        await ctx.api_data(ctx.cfg, "GET", f"/agent-cli/social-accounts/{account_id}")
    )
    tags = account.get("tags") if isinstance(account, dict) else None
    if not isinstance(tags, list):
        raise RuntimeError(
            "The account read returned no tags, so the change cannot be computed; nothing was "
            "written. Use social-account tag +set with the full tag set instead."
        )
    return [str(tag) for tag in tags]


async def _write(
    ctx: CommandContext, before: list[str], after: list[str]
) -> tuple[dict[str, Any], list[str], list[str]]:
    args = ctx.arguments
    data: dict[str, Any] = {
        "account_id": args["id"],
        "dry_run": bool(args.get("dry_run")),
        "before": before,
        "after": after,
        "changed": before != after,
    }
    if len(after) > MAX_TAGS:
        raise ValueError(f"An account holds at most {MAX_TAGS} tags; the result has {len(after)}.")
    if args.get("dry_run"):
        return data, [], ["Run again without --dry-run to write data.after."]
    if before == after:
        return data, ["The account already has exactly these tags; nothing was written."], []
    result = agent_domain_result(
        await ctx.api_data(
            ctx.cfg,
            "PUT",
            f"/agent-cli/social-accounts/{args['id']}/workspace-tags",
            json_body={"tags": after},
        )
    )
    if isinstance(result, dict) and isinstance(result.get("tags"), list):
        data["after"] = result["tags"]
    return data, [], []


async def _execute_set(ctx: CommandContext) -> Any:
    before = await _current_tags(ctx, ctx.arguments["id"])
    return await _write(ctx, before, list(ctx.arguments["tags"]))


async def _execute_add(ctx: CommandContext) -> Any:
    before = await _current_tags(ctx, ctx.arguments["id"])
    after = [*before, *(tag for tag in ctx.arguments["tags"] if tag not in before)]
    return await _write(ctx, before, after)


async def _execute_remove(ctx: CommandContext) -> Any:
    before = await _current_tags(ctx, ctx.arguments["id"])
    drop = set(ctx.arguments["tags"])
    return await _write(ctx, before, [tag for tag in before if tag not in drop])


# -- arguments ---------------------------------------------------------------


def _add_change_arguments(parser: argparse.ArgumentParser) -> None:
    add_structured_arguments(parser)
    parser.add_argument("--id", help="ID of the social account whose tags change.")
    parser.add_argument("--tag", dest="tags", action="append")
    parser.add_argument("--dry-run", action="store_true")


def _add_set_arguments(parser: argparse.ArgumentParser) -> None:
    _add_change_arguments(parser)
    parser.add_argument(
        "--clear", action="store_true", help="Remove every tag (the same as an empty tag set)."
    )


def _payload(args: argparse.Namespace, properties: dict[str, Any]) -> dict[str, Any]:
    payload = merged_input(args, ("id", "tags"))
    reject_unknown(payload, properties)
    require(payload, "id")
    payload["dry_run"] = bool(getattr(args, "dry_run", False) or payload.get("dry_run"))
    return payload


def _build_set_arguments(args: argparse.Namespace) -> dict[str, Any]:
    payload = _payload(args, _SET)
    clear = bool(getattr(args, "clear", False))
    if clear and payload.get("tags"):
        raise ValueError("Use --clear or --tag, not both.")
    if not clear and "tags" not in payload:
        raise ValueError("Give the full tag set with --tag (repeat it), or --clear to remove all.")
    payload["tags"] = [] if clear else string_list(payload["tags"], field="tags", maximum=MAX_TAGS)
    return payload


def _build_change_arguments(args: argparse.Namespace) -> dict[str, Any]:
    payload = _payload(args, _CHANGE)
    payload["tags"] = string_list(payload.get("tags"), field="tags", maximum=MAX_TAGS)
    if not payload["tags"]:
        raise ValueError("Missing required input: --tag.")
    return payload


# -- specs -------------------------------------------------------------------

_EXAMPLE_ACCOUNT = "72defd40-39ad-40d3-8105-8f23a9a016da"


def specs() -> list[CommandSpec]:
    base: dict[str, Any] = {
        "domain": Domain.SOCIAL_ACCOUNT,
        "resource": "tag",
        "risk_level": "write",
        "execution": "direct",
        "supports_dry_run": True,
        "dry_run_reads_server": True,
    }
    return [
        CommandSpec(
            **base,
            shortcut="+set",
            summary=(
                "Replace a social account's tags with exactly the given set (--clear removes "
                "all). Tags are the organization's own labels for filtering "
                "(social-account +list --tag). --dry-run shows before and after." + _ROLE
            ),
            adapter_tool_name="social_account_tag_set",
            input_schema=schema(_SET, ["id", "tags"]),
            output_schema=output_schema("data: account_id, before, after, changed, dry_run."),
            examples=[
                f"museoncli social-account tag +set --id {_EXAMPLE_ACCOUNT} --tag us --tag beauty",
                f"museoncli social-account tag +set --id {_EXAMPLE_ACCOUNT} --clear --dry-run",
            ],
            add_arguments=_add_set_arguments,
            build_arguments=_build_set_arguments,
        ),
        CommandSpec(
            **base,
            shortcut="+add",
            summary=(
                "Add tags to a social account, keeping its other tags. --dry-run shows before "
                "and after." + _RACE + _ROLE
            ),
            adapter_tool_name="social_account_tag_add",
            input_schema=schema(_CHANGE, ["id", "tags"]),
            output_schema=output_schema("data: account_id, before, after, changed, dry_run."),
            examples=[f"museoncli social-account tag +add --id {_EXAMPLE_ACCOUNT} --tag warmup"],
            add_arguments=_add_change_arguments,
            build_arguments=_build_change_arguments,
        ),
        CommandSpec(
            **base,
            shortcut="+remove",
            summary=(
                "Remove tags from a social account, keeping its other tags. --dry-run shows "
                "before and after." + _RACE + _ROLE
            ),
            adapter_tool_name="social_account_tag_remove",
            input_schema=schema(_CHANGE, ["id", "tags"]),
            output_schema=output_schema("data: account_id, before, after, changed, dry_run."),
            examples=[f"museoncli social-account tag +remove --id {_EXAMPLE_ACCOUNT} --tag warmup"],
            add_arguments=_add_change_arguments,
            build_arguments=_build_change_arguments,
        ),
    ]


EXECUTORS = {
    "social-account.tag-set": with_notes(_execute_set),
    "social-account.tag-add": with_notes(_execute_add),
    "social-account.tag-remove": with_notes(_execute_remove),
}
