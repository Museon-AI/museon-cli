"""UGC enrollment writes: approve, reject, admit, pause, resume, remove, persona, payscale.

Each command first reads the enrollment's roster row (`GET /campaigns/{id}/enrollments`,
paged until found) for its status and `updated_at`, which the routes compare-and-set
on, and for the blockers the web checks before it offers the button.
"""

from __future__ import annotations

import argparse
from typing import Any

from museoncli.domains._model import CommandSpec, Domain
from museoncli.domains._shared import _direct_output_schema, dekebab, kebab_choices
from museoncli.domains._ugc_writes import (
    CAMPAIGN_ID,
    DRY_RUN,
    OUTBOUND,
    OUTBOUND_NOTE,
    ROLE_ENROLLMENT,
    WRITE,
    _ask_next_step,
    _plural,
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
    uuids,
)
from museoncli.execution import CommandContext, compact_params

STATUSES = ["pending", "rejected", "onboarding", "active", "paused", "removed"]
_ROW_FIELDS = ("id", "status", "updated_at", "persona_id", "payscale_id", "contract_status")


def _row(item: dict[str, Any]) -> dict[str, Any]:
    creator = item.get("creator") if isinstance(item.get("creator"), dict) else {}
    line = pick(item, *_ROW_FIELDS)
    line["display_name"] = creator.get("display_name")
    return line


async def _rows(
    ctx: CommandContext, ids: list[str], *, status: str | None = None
) -> dict[str, dict[str, Any]]:
    campaign_id = ctx.arguments["campaign_id"]
    found, _ = await find_paged(
        ctx,
        f"/campaigns/{campaign_id}/enrollments",
        ids,
        params={"status": status},
    )
    require_found(found, ids, what="enrollment", where="this campaign")
    return found


async def _one(ctx: CommandContext) -> dict[str, Any]:
    """The roster row; with --expected-status only that status's rows are read."""
    args = ctx.arguments
    expected = args.get("expected_status")
    try:
        return (await _rows(ctx, [args["id"]], status=expected))[args["id"]]
    except RuntimeError as exc:
        if expected and str(exc).startswith("not_found:"):
            raise RuntimeError(
                f"conflict: invalid_transition: the campaign has no {expected} enrollment "
                f"{args['id']}; it may have moved on. Read the roster again."
            ) from None
        raise


def _moved(row: dict[str, Any], expected: str, action: str) -> None:
    if row.get("status") != expected:
        raise RuntimeError(
            f"conflict: invalid_transition: the enrollment is {row.get('status')}, not "
            f"{expected}; only a {expected} enrollment can be {action}."
        )


async def _transition(
    ctx: CommandContext,
    *,
    route: str,
    allowed: str,
    done: str,
    body: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
    ask: str,
) -> Any:
    args = ctx.arguments
    row = await _one(ctx)
    expected = args.get("expected_status") or row.get("status")
    _moved(row, allowed, done)
    payload = {"expected_status": expected, **(body or {})}
    data: dict[str, Any] = {"dry_run": args["dry_run"], "enrollment": _row(row), "body": payload}
    if args["dry_run"]:
        return data, warnings or [], [_ask_next_step(ask)]
    written = await call(ctx, "POST", f"/enrollments/{args['id']}/{route}", payload)
    data["enrollment"] = _row(written) if isinstance(written, dict) else written
    return data, warnings or [], []


async def _execute_approve(ctx: CommandContext) -> Any:
    return await _transition(
        ctx,
        route="approve",
        allowed="pending",
        done="approved",
        warnings=[
            "Approving tells the creator and sends them the contract to sign (the Campaign's "
            "auto message on accept goes with it)."
        ],
        ask="whom this approves",
    )


async def _execute_reject(ctx: CommandContext) -> Any:
    args = ctx.arguments
    body = compact_params({"note": args.get("note"), "ban": True if args.get("ban") else None})
    warnings = []
    if args.get("note"):
        warnings.append(
            "The note is written to the creator: they read it on their project page and in the "
            "rejection email."
        )
    if args.get("ban"):
        warnings.append("--ban also bans the applicant from the Campaign's Discord server.")
    return await _transition(
        ctx,
        route="reject",
        allowed="pending",
        done="rejected",
        body=body,
        warnings=warnings,
        ask="whom this rejects and the note they will read",
    )


async def _execute_admit(ctx: CommandContext) -> Any:
    args = ctx.arguments
    row = await _one(ctx)
    _moved(row, "onboarding", "admitted")
    blockers = list(row.get("warmup_admit_blockers") or [])
    body = compact_params(
        {
            "expected_status": "onboarding",
            "note": args["note"],
            "expected_missing": ["warmup_not_ready"] if args.get("warmup_not_ready") else None,
        }
    )
    data: dict[str, Any] = {"dry_run": args["dry_run"], "enrollment": _row(row), "body": body}
    if args.get("warmup_not_ready") and blockers:
        raise RuntimeError(
            "conflict: admission_blocked: this creator cannot be admitted before warmup: "
            + ", ".join(str(item) for item in blockers)
        )
    warnings = [
        "Only a signed contract is required; whatever else is missing is recorded with your note."
    ]
    if args["dry_run"]:
        return data, warnings, [_ask_next_step("whom this admits and the note")]
    written = await call(ctx, "POST", f"/enrollments/{args['id']}/admit", body)
    data["enrollment"] = _row(written) if isinstance(written, dict) else written
    return data, [], []


async def _execute_pause(ctx: CommandContext) -> Any:
    return await _transition(
        ctx,
        route="pause",
        allowed="active",
        done="paused",
        warnings=[
            "A paused creator's posts are not collected or settled until they are resumed."
        ],
        ask="whom this pauses",
    )


async def _execute_resume(ctx: CommandContext) -> Any:
    return await _transition(
        ctx,
        route="resume",
        allowed="paused",
        done="resumed",
        warnings=["Resuming makes the creator active again; their stay window counts from now."],
        ask="whom this resumes",
    )


async def _execute_remove(ctx: CommandContext) -> Any:
    args = ctx.arguments
    ids: list[str] = args["ids"]
    rows = await _rows(ctx, ids)
    blocked = {
        key: list(row.get("remove_blockers") or [])
        for key, row in rows.items()
        if row.get("remove_blockers")
    }
    if blocked:
        raise RuntimeError(
            "conflict: removal_blocked: these enrollments cannot be removed now: "
            + "; ".join(f"{key} ({', '.join(map(str, value))})" for key, value in blocked.items())
        )
    items = [
        {
            "enrollment_id": key,
            "expected_status": rows[key].get("status"),
            "expected_updated_at": rows[key].get("updated_at"),
        }
        for key in ids
    ]
    data: dict[str, Any] = {
        "dry_run": args["dry_run"],
        "enrollments": [_row(rows[key]) for key in ids],
    }
    warnings = [
        f"Removing takes {_plural(len(ids), 'creator', 'creators')} out of the Campaign; "
        "the CLI cannot undo it."
    ]
    if args["dry_run"]:
        return data, warnings, [_ask_next_step("who would be removed")]
    data["result"] = await call(
        ctx, "POST", f"/campaigns/{args['campaign_id']}/enrollments/remove", {"items": items}
    )
    return data, [], []


async def _execute_set_persona(ctx: CommandContext) -> Any:
    args = ctx.arguments
    ids: list[str] = args["ids"]
    persona = args.get("persona_id")
    data: dict[str, Any] = {"dry_run": args["dry_run"], "persona_id": persona}
    if args["dry_run"]:
        rows = await _rows(ctx, ids)
        data["enrollments"] = [
            {**_row(rows[key]), "after": persona} for key in ids
        ]
        changing = sum(1 for key in ids if rows[key].get("persona_id") != persona)
        warnings = [] if changing else ["Every enrollment already has this persona."]
        return data, warnings, [_ask_next_step("the persona before and after")]
    data["result"] = await call(
        ctx,
        "PUT",
        f"/campaigns/{args['campaign_id']}/enrollments/persona",
        {"enrollment_ids": ids, "persona_id": persona},
    )
    return data, [], []


async def _execute_set_payscale(ctx: CommandContext) -> Any:
    args = ctx.arguments
    row = await _one(ctx)
    body = {"payscale_id": args.get("payscale_id"), "expected_updated_at": row.get("updated_at")}
    data: dict[str, Any] = {
        "dry_run": args["dry_run"],
        "enrollment": _row(row),
        "before": row.get("payscale_id"),
        "after": args.get("payscale_id"),
    }
    if row.get("payscale_id") == args.get("payscale_id"):
        return data, ["The enrollment already has this payment structure; nothing was written."], []
    if args["dry_run"]:
        return data, [], [_ask_next_step("the payment structure before and after")]
    written = await call(ctx, "PATCH", f"/enrollments/{args['id']}", body)
    data["enrollment"] = _row(written) if isinstance(written, dict) else written
    return data, [], []


async def _execute_graduate_trial(ctx: CommandContext) -> Any:
    args = ctx.arguments
    row = await _one(ctx)
    trial = row.get("trial") if isinstance(row.get("trial"), dict) else {}
    blockers = list(trial.get("graduate_blockers") or [])
    if row and not trial.get("on_trial"):
        blockers = blockers or ["not_on_trial"]
    if blockers:
        raise RuntimeError(
            "conflict: graduation_blocked: " + ", ".join(str(item) for item in blockers)
        )
    body = {
        "expected_updated_at": row.get("updated_at"),
        "expected_payscale_id": row.get("payscale_id"),
    }
    data: dict[str, Any] = {
        "dry_run": args["dry_run"],
        "enrollment": _row(row),
        "trial": pick(trial, "on_trial", "outcome", "measure_by", "views_observed", "target_views"),
    }
    if args["dry_run"]:
        return data, [
            "Graduating moves the creator off the trial payment structure onto the Campaign's "
            "regular one."
        ], [_ask_next_step("who graduates")]
    written = await call(ctx, "POST", f"/enrollments/{args['id']}/graduate-trial", body)
    data["enrollment"] = _row(written) if isinstance(written, dict) else written
    return data, [], []


# -- arguments -----------------------------------------------------------------


def _add_campaign(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--campaign-id", required=True)


def _add_one(parser: argparse.ArgumentParser) -> None:
    _add_campaign(parser)
    parser.add_argument("--id", required=True)
    add_dry_run(parser)


def _one_args(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "campaign_id": _uuid(args.campaign_id, flag="--campaign-id"),
        "id": _uuid(args.id, flag="--id"),
        "dry_run": bool(args.dry_run),
    }


def _add_transition(parser: argparse.ArgumentParser) -> None:
    _add_one(parser)
    parser.add_argument("--expected-status", choices=kebab_choices(STATUSES))


def _transition_args(args: argparse.Namespace) -> dict[str, Any]:
    return {
        **_one_args(args),
        **compact_params({"expected_status": dekebab(args.expected_status)}),
    }


def _add_outbound_transition(parser: argparse.ArgumentParser) -> None:
    _add_transition(parser)
    add_yes(parser)


def _add_reject(parser: argparse.ArgumentParser) -> None:
    _add_outbound_transition(parser)
    parser.add_argument("--note")
    parser.add_argument("--ban", action="store_true")


def _reject_args(args: argparse.Namespace) -> dict[str, Any]:
    return {
        **_transition_args(args),
        **compact_params(
            {
                "note": text(args.note, flag="--note", limit=1000),
                "ban": True if args.ban else None,
            }
        ),
    }


def _add_admit(parser: argparse.ArgumentParser) -> None:
    _add_one(parser)
    parser.add_argument("--note", required=True)
    parser.add_argument("--warmup-not-ready", action="store_true")


def _admit_args(args: argparse.Namespace) -> dict[str, Any]:
    return {
        **_one_args(args),
        "note": text(args.note, flag="--note", limit=1000, required=True),
        **compact_params({"warmup_not_ready": True if args.warmup_not_ready else None}),
    }


def _add_many(parser: argparse.ArgumentParser) -> None:
    _add_campaign(parser)
    parser.add_argument("--id", action="append", dest="ids", required=True)
    add_dry_run(parser)


def _many_args(args: argparse.Namespace, *, limit: int) -> dict[str, Any]:
    return {
        "campaign_id": _uuid(args.campaign_id, flag="--campaign-id"),
        "ids": uuids(args.ids, flag="--id", limit=limit),
        "dry_run": bool(args.dry_run),
    }


def _add_remove(parser: argparse.ArgumentParser) -> None:
    _add_many(parser)
    add_yes(parser)


def _remove_args(args: argparse.Namespace) -> dict[str, Any]:
    return _many_args(args, limit=1000)


def _add_set_persona(parser: argparse.ArgumentParser) -> None:
    _add_many(parser)
    parser.add_argument("--persona-id", required=True)


def _set_persona_args(args: argparse.Namespace) -> dict[str, Any]:
    return {
        **_many_args(args, limit=200),
        "persona_id": uuid_or_none(args.persona_id, flag="--persona-id"),
    }


def _add_set_payscale(parser: argparse.ArgumentParser) -> None:
    _add_one(parser)
    parser.add_argument("--payscale-id", required=True)


def _set_payscale_args(args: argparse.Namespace) -> dict[str, Any]:
    return {**_one_args(args), "payscale_id": _uuid(args.payscale_id, flag="--payscale-id")}


# -- specs ---------------------------------------------------------------------

_ENROLLMENT_ID = _uuid_property("Enrollment ID (from ugc enrollment +list).")
_ENROLLMENT_IDS = {
    "type": "array",
    "items": {"type": "string", "format": "uuid"},
    "minItems": 1,
    "description": "Enrollment IDs (repeat --id).",
}
_EXPECTED_STATUS = {
    "type": "string",
    "enum": kebab_choices(STATUSES),
    "description": (
        "Status you saw on your latest read; the write fails if it moved. Read from the "
        "roster when left out."
    ),
}
_ROW_OUTPUT = (
    "dry_run and enrollment (id, status, updated_at, persona_id, payscale_id, contract_status, "
    "display_name)"
)


def _one_schema(extra: dict[str, Any] | None = None, required: list[str] | None = None) -> dict:
    return _schema(
        {
            "campaign_id": CAMPAIGN_ID,
            "id": _ENROLLMENT_ID,
            **(extra or {}),
            "dry_run": DRY_RUN,
        },
        ["campaign_id", "id", *(required or [])],
    )


def specs() -> list[CommandSpec]:
    domain = Domain.UGC
    campaign = "11111111-1111-4111-8111-111111111111"
    enrollment = "44444444-4444-4444-8444-444444444444"
    persona = "88888888-8888-4888-8888-888888888888"
    payscale = "99999999-9999-4999-8999-999999999999"
    base = f"--campaign-id {campaign} --id {enrollment}"

    def spec(shortcut: str, summary: str, **kwargs: Any) -> CommandSpec:
        return CommandSpec(
            domain=domain,
            resource="enrollment",
            shortcut=shortcut,
            summary=summary + ROLE_ENROLLMENT,
            adapter_tool_name=f"ugc_enrollment_{shortcut[1:].replace('-', '_')}",
            **kwargs,
        )

    return [
        spec(
            "+approve",
            "Approve a pending application. The creator is told and gets the contract to sign."
            + OUTBOUND_NOTE,
            input_schema=_one_schema({"expected_status": _EXPECTED_STATUS}),
            output_schema=_direct_output_schema(_ROW_OUTPUT + " and body."),
            examples=[f"museoncli ugc enrollment +approve {base} --dry-run"],
            add_arguments=_add_outbound_transition,
            build_arguments=_transition_args,
            **OUTBOUND,
        ),
        spec(
            "+reject",
            "Turn a pending application down. --note is written to the creator (project page "
            "and rejection email); --ban also bans them from the Campaign's Discord."
            + OUTBOUND_NOTE,
            input_schema=_one_schema(
                {
                    "expected_status": _EXPECTED_STATUS,
                    "note": {
                        "type": "string",
                        "maxLength": 1000,
                        "description": "Message to the creator explaining the decision.",
                    },
                    "ban": {"type": "boolean", "default": False},
                }
            ),
            output_schema=_direct_output_schema(_ROW_OUTPUT + " and body."),
            examples=[
                f"museoncli ugc enrollment +reject {base} --note 'We are full this month' --dry-run"
            ],
            add_arguments=_add_reject,
            build_arguments=_reject_args,
            **OUTBOUND,
        ),
        spec(
            "+admit",
            "Admit an onboarding creator by hand (the web's release). Only a signed contract "
            "is required; --note records why. --warmup-not-ready admits before warmup is ready, "
            "as the web's warmup admission does.",
            input_schema=_one_schema(
                {
                    "note": {"type": "string", "minLength": 1, "maxLength": 1000},
                    "warmup_not_ready": {"type": "boolean", "default": False},
                },
                ["note"],
            ),
            output_schema=_direct_output_schema(_ROW_OUTPUT + " and body."),
            examples=[
                f"museoncli ugc enrollment +admit {base} --note 'Signed in person' --dry-run"
            ],
            add_arguments=_add_admit,
            build_arguments=_admit_args,
            **WRITE,
        ),
        spec(
            "+pause",
            "Pause an active creator: their posts are not collected or settled until resumed.",
            input_schema=_one_schema({"expected_status": _EXPECTED_STATUS}),
            output_schema=_direct_output_schema(_ROW_OUTPUT + " and body."),
            examples=[f"museoncli ugc enrollment +pause {base} --dry-run"],
            add_arguments=_add_transition,
            build_arguments=_transition_args,
            **WRITE,
        ),
        spec(
            "+resume",
            "Resume a paused creator straight back to active.",
            input_schema=_one_schema({"expected_status": _EXPECTED_STATUS}),
            output_schema=_direct_output_schema(_ROW_OUTPUT + " and body."),
            examples=[f"museoncli ugc enrollment +resume {base} --dry-run"],
            add_arguments=_add_transition,
            build_arguments=_transition_args,
            **WRITE,
        ),
        spec(
            "+remove",
            "Remove up to 1000 creators from a UGC campaign (repeat --id), each compare-and-set "
            "on the status and updated_at the CLI reads first. Enrollments with remove blockers "
            "are refused before anything is written." + OUTBOUND_NOTE,
            input_schema=_schema(
                {
                    "campaign_id": CAMPAIGN_ID,
                    "ids": {**_ENROLLMENT_IDS, "maxItems": 1000},
                    "dry_run": DRY_RUN,
                },
                ["campaign_id", "ids"],
            ),
            output_schema=_direct_output_schema(
                "dry_run, enrollments and result (campaign_id, enrollment_ids)."
            ),
            examples=[
                f"museoncli ugc enrollment +remove --campaign-id {campaign} --id {enrollment} "
                "--dry-run"
            ],
            add_arguments=_add_remove,
            build_arguments=_remove_args,
            **OUTBOUND,
        ),
        spec(
            "+set-persona",
            "Give up to 200 enrollments of a UGC campaign one persona (repeat --id), or none "
            "with --persona-id none; all or nothing.",
            input_schema=_schema(
                {
                    "campaign_id": CAMPAIGN_ID,
                    "ids": {**_ENROLLMENT_IDS, "maxItems": 200},
                    "persona_id": {
                        "type": ["string", "null"],
                        "description": "A persona the Campaign links, or 'none'.",
                    },
                    "dry_run": DRY_RUN,
                },
                ["campaign_id", "ids", "persona_id"],
            ),
            output_schema=_direct_output_schema("dry_run, persona_id, enrollments or result."),
            examples=[
                f"museoncli ugc enrollment +set-persona --campaign-id {campaign} "
                f"--id {enrollment} --persona-id {persona} --dry-run"
            ],
            add_arguments=_add_set_persona,
            build_arguments=_set_persona_args,
            **WRITE,
        ),
        spec(
            "+set-payscale",
            "Set the payment structure (payscale) one creator is paid on, compare-and-set on "
            "the enrollment's updated_at.",
            input_schema=_one_schema(
                {"payscale_id": _uuid_property("One of the Campaign's payment structures.")},
                ["payscale_id"],
            ),
            output_schema=_direct_output_schema(_ROW_OUTPUT + ", before and after."),
            examples=[
                f"museoncli ugc enrollment +set-payscale {base} --payscale-id {payscale} --dry-run"
            ],
            add_arguments=_add_set_payscale,
            build_arguments=_set_payscale_args,
            **WRITE,
        ),
        spec(
            "+graduate-trial",
            "Graduate a creator from the trial onto the Campaign's regular payment structure "
            "(refused while the trial lists graduate blockers).",
            input_schema=_one_schema(),
            output_schema=_direct_output_schema(_ROW_OUTPUT + " and trial."),
            examples=[f"museoncli ugc enrollment +graduate-trial {base} --dry-run"],
            add_arguments=_add_one,
            build_arguments=_one_args,
            **WRITE,
        ),
    ]


EXECUTORS = {
    "ugc.enrollment-approve": _with_notes(_execute_approve),
    "ugc.enrollment-reject": _with_notes(_execute_reject),
    "ugc.enrollment-admit": _with_notes(_execute_admit),
    "ugc.enrollment-pause": _with_notes(_execute_pause),
    "ugc.enrollment-resume": _with_notes(_execute_resume),
    "ugc.enrollment-remove": _with_notes(_execute_remove),
    "ugc.enrollment-set-persona": _with_notes(_execute_set_persona),
    "ugc.enrollment-set-payscale": _with_notes(_execute_set_payscale),
    "ugc.enrollment-graduate-trial": _with_notes(_execute_graduate_trial),
}
