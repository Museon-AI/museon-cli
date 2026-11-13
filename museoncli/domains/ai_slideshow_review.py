"""AI image post review: approve, take back, reject, retry and adjust a generated post.

The routes are the ones the web's /content-review page calls
(``/api/v2/content-reviews/{generation_id}/...``). They work with the organization alone
(``X-Organization-Id``): the generation is looked up where it is held, inside that
organization, and the body carries no workspace. ``generation_id`` is the slideshow generation
(``ai-slideshow generation +list`` / ``+get``); for ``+retry`` it is the replacement generation
an adjustment produced. Reviewing takes a workspace editor: owner, admin or operator. The
server decides.

The routes take no version or idempotency key, so a rerun after an unknown outcome acts on
whatever state the post is in then: read it first (``ai-slideshow generation +get``).
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
    uuid_property,
    with_notes,
)
from museoncli.domains._shared import _json_list
from museoncli.domains._writes import uuid_arg
from museoncli.execution import CommandContext

MAX_ANNOTATIONS = 20
MAX_INSTRUCTION = 2000
_ROLE = " Needs owner, admin or operator."
_GENERATION_ID = uuid_property(
    "Slideshow generation ID (ai-slideshow generation +list / +get). For +retry, the "
    "replacement generation that the adjustment created."
)
_ANNOTATION = {
    "type": "object",
    "properties": {
        "slide_media_id": {"type": "string", "minLength": 1, "maxLength": 100},
        "slide_index": {"type": "integer", "minimum": 1, "maximum": 100},
        "annotation_type": {"type": "string", "enum": ["point", "region"], "default": "point"},
        "x": {"type": "integer", "minimum": 0, "maximum": 1000},
        "y": {"type": "integer", "minimum": 0, "maximum": 1000},
        "width": {"type": "integer", "minimum": 1, "maximum": 1000},
        "height": {"type": "integer", "minimum": 1, "maximum": 1000},
        "comment": {"type": "string", "minLength": 1, "maxLength": 500},
    },
    "required": ["slide_media_id", "slide_index", "x", "y", "comment"],
    "additionalProperties": False,
}
_DECIDE = {"generation_id": _GENERATION_ID, "dry_run": DRY_RUN_PROPERTY}
_ADJUST = {
    "generation_id": _GENERATION_ID,
    "instruction": {
        "type": "string",
        "minLength": 1,
        "maxLength": MAX_INSTRUCTION,
        "description": "What to change in the post, in words.",
    },
    "annotations": {
        "type": "array",
        "items": _ANNOTATION,
        "maxItems": MAX_ANNOTATIONS,
        "description": (
            "Marks on slides: a point (x, y) or a region (x, y, width, height) on a 0-1000 "
            "grid of the slide, each with a comment. --annotations-json takes the array."
        ),
    },
    "dry_run": DRY_RUN_PROPERTY,
}

# action -> (route suffix, what it does, what the server answers)
_ACTIONS: dict[str, tuple[str, str, str]] = {
    "approve": (
        "review",
        "Mark an AI image post reviewed (approved): it can go on to publish.",
        "data: the review decision (decision reviewed, generation_id, reviewed_at).",
    ),
    "unreview": (
        "unreview",
        "Take back an approval: the post returns to the review queue. Answers data.undone.",
        "data.undone: whether the approval was taken back.",
    ),
    "reject": (
        "reject",
        "Reject an AI image post's publication.",
        "data: the review decision (decision rejected, generation_id, reviewed_at).",
    ),
    "retry": (
        "retry",
        "Run an adjustment again: retry the replacement generation after the one the last "
        "+adjust asked for failed. --generation-id is that replacement generation.",
        "data: the review decision (generation_id, replacement_generation_id).",
    ),
}


def _path(generation_id: str, suffix: str) -> str:
    return f"/content-reviews/{generation_id}/{suffix}"


# -- executors ---------------------------------------------------------------


def _decide(action: str):
    suffix = _ACTIONS[action][0]

    async def run(ctx: CommandContext) -> Any:
        generation_id = ctx.arguments["generation_id"]
        data = await ctx.api_data_v2(
            ctx.cfg, "POST", _path(generation_id, suffix), json_body={}
        )
        return data, [], [f"museoncli ai-slideshow generation +get --id {generation_id}"]

    return with_notes(run)


async def _execute_adjust(ctx: CommandContext) -> Any:
    args = ctx.arguments
    body: dict[str, Any] = {}
    if args.get("instruction"):
        body["instruction"] = args["instruction"]
    if args.get("annotations"):
        body["annotations"] = args["annotations"]
    data = await ctx.api_data_v2(
        ctx.cfg, "POST", _path(args["generation_id"], "adjust"), json_body=body
    )
    return (
        data,
        ["The adjustment starts a new generation; data.replacement_generation_id is the post to review next."],
        [],
    )


# -- arguments ---------------------------------------------------------------


def _dry_run(args: argparse.Namespace, payload: dict[str, Any]) -> None:
    payload["dry_run"] = bool(getattr(args, "dry_run", False) or payload.get("dry_run"))


def _add_decide_arguments(parser: argparse.ArgumentParser) -> None:
    add_structured_arguments(parser)
    parser.add_argument("--generation-id")
    parser.add_argument("--dry-run", action="store_true")


def _build_decide_arguments(args: argparse.Namespace) -> dict[str, Any]:
    payload = merged_input(args, ("generation_id",))
    reject_unknown(payload, _DECIDE)
    require(payload, "generation_id")
    payload["generation_id"] = uuid_arg(payload["generation_id"], flag="--generation-id")
    _dry_run(args, payload)
    return payload


def _add_adjust_arguments(parser: argparse.ArgumentParser) -> None:
    add_structured_arguments(parser)
    parser.add_argument("--generation-id")
    parser.add_argument("--instruction")
    parser.add_argument("--annotations-json")
    parser.add_argument("--dry-run", action="store_true")


def _build_adjust_arguments(args: argparse.Namespace) -> dict[str, Any]:
    payload = merged_input(args, ("generation_id", "instruction"))
    annotations_json = getattr(args, "annotations_json", None)
    if annotations_json:
        if "annotations" in payload:
            raise ValueError(
                "annotations is given both as --annotations-json and in --args-json/--args-file."
            )
        payload["annotations"] = _json_list(annotations_json, flag="--annotations-json")
    reject_unknown(payload, _ADJUST)
    require(payload, "generation_id")
    payload["generation_id"] = uuid_arg(payload["generation_id"], flag="--generation-id")
    instruction = payload.get("instruction")
    if instruction is not None:
        if not isinstance(instruction, str) or len(instruction) > MAX_INSTRUCTION:
            raise ValueError(f"--instruction must be text of at most {MAX_INSTRUCTION} characters.")
        payload["instruction"] = instruction.strip()
    annotations = payload.get("annotations")
    if annotations is not None:
        if not isinstance(annotations, list) or not all(isinstance(a, dict) for a in annotations):
            raise ValueError("annotations must be a list of objects.")
        if len(annotations) > MAX_ANNOTATIONS:
            raise ValueError(f"annotations takes at most {MAX_ANNOTATIONS} marks.")
    if not payload.get("instruction") and not annotations:
        raise ValueError("Adjustment feedback must not be empty: give --instruction or annotations.")
    _dry_run(args, payload)
    return payload


# -- specs -------------------------------------------------------------------

_EXAMPLE_ID = "72defd40-39ad-40d3-8105-8f23a9a016da"


def specs() -> list[CommandSpec]:
    base: dict[str, Any] = {
        "domain": Domain.AI_SLIDESHOW,
        "resource": "review",
        "execution": "direct",
        "risk_level": "write",
        "supports_dry_run": True,
    }
    built = [
        CommandSpec(
            **base,
            shortcut=f"+{action}",
            summary=summary + _ROLE,
            adapter_tool_name=f"ai_slideshow_review_{action}",
            input_schema=schema(_DECIDE, ["generation_id"]),
            output_schema=output_schema(output),
            examples=[f"museoncli ai-slideshow review +{action} --generation-id {_EXAMPLE_ID}"],
            add_arguments=_add_decide_arguments,
            build_arguments=_build_decide_arguments,
        )
        for action, (_, summary, output) in _ACTIONS.items()
    ]
    built.append(
        CommandSpec(
            **base,
            shortcut="+adjust",
            summary=(
                "Ask for changes to an AI image post: --instruction in words and/or "
                "--annotations-json marks on slides (up to 20). The post is regenerated as a "
                "new generation to review next." + _ROLE
            ),
            adapter_tool_name="ai_slideshow_review_adjust",
            input_schema=schema(_ADJUST, ["generation_id"]),
            output_schema=output_schema(
                "data: the review decision (decision adjustment_requested, instruction, "
                "replacement_generation_id)."
            ),
            examples=[
                f"museoncli ai-slideshow review +adjust --generation-id {_EXAMPLE_ID} "
                "--instruction 'Make the first slide title shorter'"
            ],
            add_arguments=_add_adjust_arguments,
            build_arguments=_build_adjust_arguments,
        )
    )
    return built


EXECUTORS = {
    **{f"ai-slideshow.review-{action}": _decide(action) for action in _ACTIONS},
    "ai-slideshow.review-adjust": with_notes(_execute_adjust),
}
