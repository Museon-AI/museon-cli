"""Version-bound video review, generation, rendering and delivery operations."""

from museoncli.domains._model import CommandSpec
from museoncli.domains.hireaicreator import (
    B,
    D,
    DT,
    PAGE,
    POSITIVE_INT,
    TZ,
    U,
    _command,
    enum,
    nullable,
    obj,
)
from museoncli.domains.hireaicreator_test_groups import arr

VERSION = {"expected_version": POSITIVE_INT}
DIRECTION = nullable({"type": "string", "maxLength": 1000})
DIRECTIONS = obj({"pov": DIRECTION, "text_overlay": DIRECTION, "caption": DIRECTION})
GENERATE = {**VERSION, "generation_directions": DIRECTIONS}
REVIEW = {
    **VERSION,
    "decision": enum("approved", "changes-requested"),
    "note": nullable({"type": "string", "minLength": 1, "maxLength": 2000}),
}
VERSION_ITEM = obj({"video_id": U, **VERSION}, ("video_id", "expected_version"))
BULK_REVIEW_ITEM = obj({"video_id": U, **REVIEW}, ("video_id", "expected_version", "decision"))
CALENDAR = {
    "campaign_id": U,
    "timezone": {**TZ, "maxLength": 64},
    "publishing_account_id": {"type": "string", "maxLength": 200},
    "account_operation_stage": enum("all", "promotable", "warmup"),
}
READBACK = "Read video +get and +readiness; accepted is not completed. Refresh versions before subsequent writes."


def specs() -> list[CommandSpec]:
    def cmd(resource, action, method, path, properties=None, **kwargs):
        kwargs.setdefault("workspace", "resource")
        if kwargs.get("write"):
            kwargs.setdefault("readback", READBACK)
        return _command(resource, action, method, path, properties or {}, **kwargs)

    video = "/ai-hook-videos"
    plan = "/ai-hook-video-plans"
    result = [
        cmd(
            "plan",
            "list",
            "GET",
            plan,
            PAGE,
            workspace="query",
            summary="List workspace video plans; complete pagination.",
        ),
        cmd(
            "plan",
            "generate",
            "POST",
            plan + "/{id}/generate",
            {"generation_directions": DIRECTIONS},
            write=True,
            idempotent=True,
            summary="Start generation for a plan with a stable retry key.",
            readback="Read plan +get and the plan's video list; inspect accepted and failed counts.",
        ),
        cmd(
            "plan",
            "cancel",
            "POST",
            plan + "/{id}/cancel",
            VERSION,
            required=("expected_version",),
            write=True,
            requires_confirmation=True,
            summary="Cancel remaining plan work at the expected version; inspect skipped items.",
            readback="Read plan +get and inspect skipped items; published work cannot be undone.",
        ),
        cmd(
            "video",
            "review",
            "POST",
            video + "/{id}/review",
            REVIEW,
            required=("expected_version", "decision"),
            write=True,
            requires_confirmation=True,
            summary="Approve or request changes at the reviewed version; approval can enable scheduled publication.",
        ),
        cmd(
            "video",
            "bulk-review",
            "POST",
            video + "/bulk-review",
            {"items": arr(BULK_REVIEW_ITEM, 1)},
            required=("items",),
            write=True,
            requires_confirmation=True,
            summary="Review explicit video versions; inspect succeeded, conflicted and failures independently.",
        ),
        cmd(
            "video",
            "delete",
            "DELETE",
            video + "/{id}",
            VERSION,
            required=("expected_version",),
            query_fields=("expected_version",),
            write=True,
            destructive=True,
            summary="Delete a video at its expected version; requires explicit destructive intent.",
            readback="Read video +list in the original workspace and confirm absence.",
        ),
        cmd(
            "video",
            "bulk-delete",
            "POST",
            video + "/bulk-delete",
            {"items": arr(VERSION_ITEM, 1)},
            required=("items",),
            write=True,
            destructive=True,
            summary="Delete explicit video versions; inspect per-item failures before retrying.",
            readback="Read video +list in the original workspace and verify each result.",
        ),
        cmd(
            "video",
            "cancel",
            "POST",
            video + "/{id}/cancel",
            VERSION,
            required=("expected_version",),
            write=True,
            requires_confirmation=True,
            summary="Cancel one video at its current version.",
        ),
        cmd(
            "video",
            "cancel-generation",
            "POST",
            video + "/{id}/cancel-generation",
            {
                **VERSION,
                "components": nullable(arr(enum("ai-hook", "pov", "text-overlay", "caption"))),
            },
            required=("expected_version",),
            write=True,
            requires_confirmation=True,
            summary="Cancel selected generation components; omitted or null selects server defaults.",
        ),
        cmd(
            "video",
            "retry-render",
            "POST",
            video + "/{id}/retry-render",
            GENERATE,
            required=("expected_version",),
            write=True,
            summary="Retry failed rendering at the expected version; generation directions are accepted but not used by this endpoint.",
        ),
        cmd(
            "video",
            "render",
            "POST",
            video + "/{id}/render",
            GENERATE,
            required=("expected_version",),
            write=True,
            summary="Request rendering for a video version; generation directions are accepted but not used by this endpoint.",
            readback="Poll video +render-get until succeeded or failed; verify video_version and render_revision.",
        ),
        cmd(
            "video",
            "render-get",
            "GET",
            video + "/{id}/render",
            summary="Read actual rendering status, version, revision, URL and error.",
        ),
        cmd(
            "video",
            "candidates-commit",
            "POST",
            video + "/{id}/candidates/commit",
            VERSION,
            required=("expected_version",),
            write=True,
            summary="Commit generated candidates only after inspecting them at the current version.",
        ),
        cmd(
            "video",
            "bulk-regenerate",
            "POST",
            video + "/bulk-regenerate",
            {
                "items": arr(VERSION_ITEM, 1),
                "components": {
                    **arr(enum("pov", "text-overlay", "caption"), 1, 3),
                    "uniqueItems": True,
                },
                "generation_directions": DIRECTIONS,
            },
            required=("items", "components"),
            write=True,
            idempotent=True,
            summary="Regenerate selected text components across explicit versions; inspect accepted, conflicted and failures.",
        ),
        cmd(
            "delivery",
            "export-batch",
            "POST",
            "/ai-hook-video-exports/batches",
            {"items": arr(VERSION_ITEM, 1, 50), "hook_resolution": enum("original", "480p")},
            required=("items",),
            write=True,
            idempotent=True,
            summary="Export up to 50 unique video versions under a stable idempotency key.",
            readback="Poll each delivery +export-get; require completed and matching video/version/revision before delivery.",
        ),
        cmd(
            "calendar",
            "month",
            "GET",
            video + "/calendar/month",
            {**CALENDAR, "scheduled_from": DT, "scheduled_to": DT},
            workspace="query",
            required=("campaign_id", "timezone", "scheduled_from", "scheduled_to"),
            summary="Read campaign calendar day totals for an explicit timezone and interval.",
        ),
        cmd(
            "calendar",
            "day",
            "GET",
            video + "/calendar/day",
            {**CALENDAR, "day": D, "include_preview": B},
            workspace="query",
            required=("campaign_id", "timezone", "day"),
            summary="Read a campaign day; inspect truncated before treating the result as complete.",
        ),
    ]
    for component in ("ai-hook", "pov", "text-overlay", "caption"):
        properties = (
            GENERATE if component == "ai-hook" else {**VERSION, "creative_direction": DIRECTION}
        )
        result.append(
            cmd(
                "video",
                component + "-regenerate",
                "POST",
                video + "/{id}/" + component + "/regenerate",
                properties,
                required=("expected_version",),
                write=True,
                idempotent=True,
                summary=f"Regenerate {component} at an explicit video version with a stable retry key.",
            )
        )
    for component in ("ai-hook", "pov"):
        result.append(
            cmd(
                "video",
                component + "-candidate",
                "POST",
                video + "/{id}/" + component + "/candidate",
                GENERATE,
                required=("expected_version",),
                write=True,
                idempotent=True,
                summary=f"Generate a {component} candidate; inspect it before candidates-commit.",
            )
        )
    return result
