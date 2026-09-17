"""Test Group operations backed by the existing v2 API contracts.

Imported lazily from hireaicreator.specs; executors register in its shared registry.
Only group creation and run confirmation have server idempotency support.
"""

from museoncli.domains._model import CommandSpec
from museoncli.domains.hireaicreator import (
    B,
    D,
    DT,
    POSITIVE_INT,
    S,
    TZ,
    U,
    _command,
    enum,
    nullable,
    obj,
)


def arr(items, minimum=0, maximum=None):
    """Preserve endpoint lists with no server maximum."""
    schema = {"type": "array", "items": items, "minItems": minimum}
    if maximum is not None:
        schema["maxItems"] = maximum
    return schema


NAME = {"type": "string", "minLength": 1, "maxLength": 120}
ACCOUNT = {"type": "string", "minLength": 1, "maxLength": 200}
KIND = enum("hook", "recipe", "bgm", "pov")
SELECTION = obj({"key_id": U, "tag_ids": arr(U)}, ("key_id",))
TIMING = obj(
    {
        "mode": enum("speed", "trim"),
        "target_duration_ms": {
            "type": "integer",
            "minimum": 100,
            "maximum": 3600000,
            "multipleOf": 10,
        },
    },
    ("mode", "target_duration_ms"),
)
CONTENT = {"kind": KIND, "name": NAME, "resource_ids": arr(U, 1)}
COMBINATION = obj(
    {
        "hook_timing": nullable(TIMING),
        "composition_kind": enum("recipe", "hook-only", "format", "format-recipe"),
        "name": nullable({"type": "string", "maxLength": 120}),
        **{
            key: nullable(U)
            for key in ("hook_group_id", "recipe_group_id", "bgm_group_id", "pov_group_id")
        },
        "format_ids": arr(U, 1),
        "category_selections": arr(SELECTION),
    }
)
DATES = {"start_date": nullable(D), "end_date": nullable(D)}
PREVIEW = {
    "test_group_id": U,
    "campaign_id": nullable(U),
    "schedule_timezone": nullable(TZ),
    "publish_times": nullable(arr(S, maximum=100)),
}
READBACK = (
    "Read test-group +get and +publishing for the same workspace and group before dependent writes."
)


def page(maximum=100, search_length=120):
    return {
        "page": POSITIVE_INT,
        "page_size": {"type": "integer", "minimum": 1, "maximum": maximum},
        "search": {"type": "string", "maxLength": search_length},
    }


def specs() -> list[CommandSpec]:
    def cmd(resource, action, method, path, properties=None, **kwargs):
        write = kwargs.get("write", False)
        kwargs.setdefault("workspace", "query" if method in ("GET", "DELETE") else "body")
        if write:
            kwargs.setdefault("readback", READBACK)
        return _command(resource, action, method, path, properties or {}, **kwargs)

    group = "/ai-hook-test-groups"
    content = "/ai-hook-content-groups"
    plan = "/ai-hook-test-plans"
    return [
        cmd(
            "test-plan",
            "ensure",
            "GET",
            plan,
            write=True,
            summary="Get or create the workspace Test Plan.",
            readback="Read the returned plan ID and persisted settings.",
        ),
        cmd(
            "test-plan",
            "update",
            "PUT",
            plan,
            {
                "name": NAME,
                **DATES,
                "schedule_timezone": nullable(TZ),
                "publish_times": nullable(arr(S, 1, 24)),
            },
            required=("name",),
            write=True,
            summary="Update workspace Test Plan defaults.",
            readback="Read test-plan +ensure in the same workspace.",
        ),
        cmd(
            "content-group",
            "list",
            "GET",
            content,
            {**page(), "kind": KIND},
            summary="List reusable content groups; complete pagination.",
        ),
        cmd(
            "content-group",
            "create",
            "POST",
            content,
            CONTENT,
            required=("kind", "name", "resource_ids"),
            write=True,
            summary="Create a reusable Hook, Recipe, BGM or POV group.",
            readback="Read content-group +list for this workspace.",
        ),
        cmd(
            "content-group",
            "update",
            "PATCH",
            content + "/{id}",
            CONTENT,
            required=("kind", "name", "resource_ids"),
            write=True,
            summary="Replace reusable content group name and resource selection.",
            readback="Read content-group +list for this workspace.",
        ),
        cmd(
            "content-group",
            "delete",
            "DELETE",
            content + "/{id}",
            write=True,
            destructive=True,
            summary="Delete a reusable content group; review references before execution.",
            readback="Read content-group +list and confirm absence.",
        ),
        cmd(
            "test-group",
            "list",
            "GET",
            group,
            {
                **page(),
                "plan_id": U,
                "sort_by": enum("created-at", "name", "running-account-count"),
                "sort_direction": enum("asc", "desc"),
                "execution_states": arr(
                    enum(
                        "unscheduled",
                        "scheduled",
                        "running",
                        "completed",
                        "cancelled",
                        "healthy",
                        "attention",
                        "unknown",
                    )
                ),
            },
            summary="List Test Groups with execution filters and optional plan scope.",
        ),
        cmd(
            "test-group",
            "get",
            "GET",
            group + "/{id}",
            summary="Read group, content selection, account assignments and runs.",
        ),
        cmd(
            "test-group",
            "overview",
            "GET",
            group + "/operations-overview",
            {"plan_id": U, "timezone": TZ},
            required=("plan_id",),
            summary="Read operational totals for a Test Plan.",
        ),
        cmd(
            "test-group",
            "create",
            "POST",
            group,
            {
                "plan_id": U,
                "combinations": arr(COMBINATION, 1),
                **DATES,
                "schedule_timezone": nullable(TZ),
                "publish_times": nullable(arr(S, 1, 100)),
            },
            required=("plan_id", "combinations"),
            write=True,
            idempotent=True,
            summary="Create groups from explicit content combinations; retain the idempotency key on retries.",
        ),
        cmd(
            "test-group",
            "delete",
            "DELETE",
            group + "/{id}",
            {"force": B},
            query_fields=("force",),
            write=True,
            destructive=True,
            summary="Delete a group. Force also cancels unpublished work; requires explicit user intent.",
            readback="Read test-group +list and confirm absence.",
        ),
        cmd(
            "test-group",
            "rename",
            "PATCH",
            group + "/{id}",
            {"name": NAME},
            required=("name",),
            write=True,
            summary="Rename a Test Group.",
        ),
        cmd(
            "test-group",
            "category-requirements",
            "POST",
            group + "/category-requirements",
            {"recipe_group_ids": arr(U, 1)},
            required=("recipe_group_ids",),
            summary="Read required category keys for recipe groups.",
        ),
        cmd(
            "test-group",
            "category-options",
            "GET",
            group + "/category-tag-options",
            {**page(300), "key_id": U},
            required=("key_id",),
            summary="Read paginated category tag options.",
        ),
        cmd(
            "test-group",
            "category-set",
            "PUT",
            group + "/{id}/category-tags",
            {"selections": arr(SELECTION)},
            write=True,
            summary="Replace category selections; empty selections clear them.",
        ),
        cmd(
            "test-group",
            "hook-target",
            "GET",
            group + "/{id}/hook-launch-target",
            summary="Read Hook append target and constraints.",
        ),
        cmd(
            "test-group",
            "append-hooks",
            "POST",
            group + "/{id}/append-hooks",
            {"campaign_id": nullable(U), "hook_ids": arr(U, 1, 50)},
            required=("hook_ids",),
            write=True,
            summary="Append Hooks for the next run; existing runs retain their selection.",
        ),
        cmd(
            "test-group",
            "content-set",
            "PUT",
            group + "/{id}/content-source",
            {
                "expected_updated_at": DT,
                "source_kind": enum("format", "manual"),
                "hook_timing": nullable(TIMING),
                **{key: arr(U) for key in ("format_ids", "hook_ids", "pov_ids", "bgm_ids")},
            },
            required=("expected_updated_at", "source_kind"),
            write=True,
            summary="Replace content source using the last read updated_at; refresh after conflicts.",
        ),
        cmd(
            "test-group",
            "content-group-set",
            "PUT",
            group + "/{id}/content-group",
            CONTENT,
            required=("kind", "name", "resource_ids"),
            write=True,
            summary="Replace one content group used by a Test Group.",
        ),
        cmd(
            "test-group",
            "accounts",
            "GET",
            group + "/{id}/publishing-accounts",
            page(300, 200),
            summary="Read assigned publishing account identities.",
        ),
        cmd(
            "test-group",
            "accounts-set",
            "PUT",
            group + "/{id}/accounts",
            {"publishing_account_ids": arr(ACCOUNT), "mode": enum("replace", "append")},
            required=("publishing_account_ids",),
            write=True,
            requires_confirmation=True,
            summary="Replace or append assigned accounts; an empty replacement unassigns all.",
        ),
        cmd(
            "test-group",
            "accounts-transfer",
            "POST",
            group + "/{id}/accounts/transfer",
            {"publishing_account_ids": arr(ACCOUNT, 1, 200)},
            required=("publishing_account_ids",),
            write=True,
            requires_confirmation=True,
            summary="Transfer selected accounts into this group; read eligibility and affected groups first.",
        ),
        cmd(
            "test-group",
            "accounts-assign",
            "PUT",
            group + "/account-assignments",
            {"test_group_ids": arr(U, 1), "publishing_account_ids": arr(ACCOUNT)},
            required=("test_group_ids", "publishing_account_ids"),
            write=True,
            requires_confirmation=True,
            summary="Assign an explicit account set across selected Test Groups.",
        ),
        cmd(
            "test-group",
            "schedule-set",
            "PUT",
            group + "/{id}/schedule",
            {
                **DATES,
                "expected_updated_at": nullable(DT),
                "schedule_timezone": TZ,
                "publish_times": arr(S, 1, 100),
            },
            write=True,
            summary="Set group schedule; use read updated_at and explicit timezone, then preview before confirming.",
        ),
        cmd(
            "test-group",
            "preview",
            "POST",
            group + "/preview",
            PREVIEW,
            required=("test_group_id",),
            summary="Read schedule preview, blockers and match_fingerprint without publishing.",
        ),
        cmd(
            "test-run",
            "confirm",
            "POST",
            "/ai-hook-test-runs",
            {
                **PREVIEW,
                "match_fingerprint": nullable({"type": "string", "minLength": 64, "maxLength": 64}),
            },
            required=("test_group_id",),
            idempotent=True,
            write=True,
            requires_confirmation=True,
            summary="Confirm a preview into a scheduled run; use preview fingerprint and explicit publication authorization.",
        ),
        cmd(
            "test-run",
            "cancel",
            "POST",
            "/ai-hook-test-runs/{id}/cancel",
            workspace="query",
            write=True,
            requires_confirmation=True,
            summary="Cancel a run's remaining scheduled work; published posts are not undone.",
        ),
        cmd(
            "test-group",
            "cancel-schedule",
            "POST",
            group + "/{id}/cancel-schedule",
            workspace="query",
            write=True,
            requires_confirmation=True,
            summary="Cancel remaining group schedule; read publication state afterward.",
        ),
        cmd(
            "test-group",
            "publishing",
            "GET",
            group + "/{id}/publishing",
            {"run_id": U},
            summary="Read publication totals and failures, optionally for one run.",
        ),
        cmd(
            "test-group",
            "publishing-accounts",
            "GET",
            group + "/{id}/publishing/accounts",
            {
                "run_id": U,
                "page": POSITIVE_INT,
                "page_size": {"type": "integer", "minimum": 1, "maximum": 200},
                "sort": enum("failed-desc", "published-desc"),
            },
            summary="Read per-account publishing results and failures; complete pagination.",
        ),
    ]
