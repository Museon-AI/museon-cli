"""Warmup lifecycle commands backed by the workspace-scoped v2 operator API."""

from __future__ import annotations

from museoncli.domains._model import CommandSpec
from museoncli.domains.hireaicreator import (
    B,
    PAGE,
    POSITIVE_INT,
    TZ,
    U,
    _command,
    arr,
    enum,
    nullable,
    obj,
)

PREFIX = "/pool-account-warmup"
STRATEGY = PREFIX + "/strategies/{id}"
ACCOUNTS = arr(
    obj(
        {"pool_account_id": U, "timezone": {**TZ, "minLength": 1, "maxLength": 64}},
        ("pool_account_id", "timezone"),
    ),
    1,
)
CONTENT = obj(
    {
        key: arr(U)
        for key in (
            "format_ids",
            "hook_ids",
            "pov_ids",
            "bgm_ids",
            "demo_ids",
            "recipe_ids",
        )
    }
)
ONBOARD = obj(
    {
        "qualified_post_count": {"type": "integer", "minimum": 1, "maximum": 100},
        "views_strictly_greater_than": {"type": "integer", "minimum": 0},
    },
    ("qualified_post_count", "views_strictly_greater_than"),
)
TERMINATE = obj(
    {
        "consecutive_low_view_days": {"type": "integer", "minimum": 1, "maximum": 30},
        "views_strictly_less_than": POSITIVE_INT,
        "max_action_days": {"type": "integer", "minimum": 1, "maximum": 365},
        "evidence_maturity_hours": {"type": "integer", "minimum": 0, "maximum": 168},
        "evidence_grace_hours": {"type": "integer", "minimum": 1, "maximum": 336},
    },
    ("consecutive_low_view_days", "views_strictly_less_than", "max_action_days"),
)
CONFIG = {
    "campaign_id": nullable(U),
    "name": {"type": "string", "minLength": 1, "maxLength": 120},
    "content": CONTENT,
    "onboard_rule": ONBOARD,
    "terminate_rule": TERMINATE,
    "publish_time": {"type": "string", "pattern": r"^([01]\d|2[0-3]):[0-5]\d$"},
    "confirm_demo_reuse_for_automation": B,
}
CONFIG_REQUIRED = ("name", "content", "onboard_rule", "terminate_rule", "publish_time")
CREATE = {**CONFIG, "accounts": ACCOUNTS, "action_type": enum("ai-hook", "nurture")}
TRANSITION = {"expected_version": POSITIVE_INT, "campaign_id": nullable(U)}
REVISIONS = nullable(
    {
        "type": "object",
        "additionalProperties": {"type": "string"},
        "propertyNames": {"type": "string", "format": "uuid"},
        "maxProperties": 300,
    }
)


def _operation(action: str, method: str, path: str, properties: dict, **kwargs) -> CommandSpec:
    confirmation = kwargs.pop("confirmation", False)
    return _command(
        "warmup",
        action,
        method,
        path,
        properties,
        requires_confirmation=confirmation,
        destructive=action == "delete",
        **kwargs,
    )


def specs() -> list[CommandSpec]:
    """Add to HireAICreator specs; existing +list and +journeys remain there."""
    readback = "hireaicreator warmup +get --id STRATEGY_ID; inspect version, status and blockers before the next operation."
    result = [
        _operation(
            "get", "GET", STRATEGY, {}, summary="Read a warmup strategy and its current version."
        ),
        _operation(
            "create",
            "POST",
            PREFIX + "/strategies",
            CREATE,
            required=(*CONFIG_REQUIRED, "accounts"),
            workspace="body",
            write=True,
            summary="Create a draft warmup strategy. No server idempotency key is supported; reconcile before retrying.",
            readback=readback,
        ),
        _operation(
            "replace",
            "PUT",
            STRATEGY,
            {**CREATE, "expected_version": POSITIVE_INT},
            required=(*CONFIG_REQUIRED, "accounts", "expected_version"),
            workspace="body",
            write=True,
            summary="Replace a strategy using its current version; sends the full configuration and account set.",
            readback=readback,
        ),
        _operation(
            "configure",
            "PATCH",
            STRATEGY + "/configuration",
            {**CONFIG, "expected_version": POSITIVE_INT},
            required=(*CONFIG_REQUIRED, "expected_version"),
            workspace="body",
            write=True,
            summary="Replace warmup configuration without replacing account membership; provide all required configuration fields.",
            readback=readback,
        ),
        _operation(
            "accounts",
            "GET",
            STRATEGY + "/accounts",
            {
                **PAGE,
                "search": {"type": "string", "maxLength": 200},
                "status": arr(enum("warming", "onboarded", "terminated")),
                "device_kind": enum("cloud-phone", "real-device"),
            },
            summary="Page through warmup accounts, journey states and reset blockers. Compare total with collected items.",
        ),
        _operation(
            "add-accounts",
            "POST",
            STRATEGY + "/accounts",
            {
                "accounts": ACCOUNTS,
                "expected_version": POSITIVE_INT,
            },
            required=("accounts", "expected_version"),
            workspace="body",
            write=True,
            summary="Add account/timezone assignments with optimistic version control.",
            readback=readback,
        ),
        _operation(
            "remove-accounts",
            "POST",
            STRATEGY + "/accounts/remove",
            {
                "pool_account_ids": arr(U, 1),
                "expected_version": POSITIVE_INT,
            },
            required=("pool_account_ids", "expected_version"),
            workspace="body",
            write=True,
            confirmation=True,
            summary="Remove selected account memberships from warmup; requires --yes.",
            readback=readback,
        ),
        _operation(
            "account-stats",
            "GET",
            STRATEGY + "/account-stats",
            {
                "pool_account_ids": arr(U, 1, 100),
            },
            required=("pool_account_ids",),
            summary="Read selected accounts' published counts and measured performance; preserve missing values.",
        ),
        _operation(
            "readiness",
            "POST",
            PREFIX + "/accounts/readiness",
            {
                "pool_account_ids": arr(U, 1),
                "action_type": enum("ai-hook", "nurture"),
            },
            required=("pool_account_ids",),
            workspace="body",
            summary="Check Actor/Persona and account readiness without creating or starting a strategy.",
        ),
        _operation(
            "preview",
            "POST",
            STRATEGY + "/preview",
            {},
            summary="Inspect candidates, current format revisions and activation blockers without starting warmup.",
        ),
        _operation(
            "check-and-start",
            "POST",
            STRATEGY + "/check-and-start",
            {
                **TRANSITION,
                "expected_format_revisions": REVISIONS,
            },
            required=("expected_version",),
            write=True,
            confirmation=True,
            summary="Check readiness and activate when ready; may start automated generation/publication. Requires --yes. Read started and blockers.",
            readback=readback,
        ),
        _operation(
            "reset",
            "POST",
            STRATEGY + "/journeys/reset",
            {"pool_account_ids": arr(U, 1)},
            required=("pool_account_ids",),
            workspace="body",
            write=True,
            confirmation=True,
            summary="Reset selected journeys after checking reset blockers. No server version/idempotency key is supported; reconcile before retrying. Requires --yes.",
            readback="hireaicreator warmup +accounts --id STRATEGY_ID; inspect current journeys and reset blockers.",
        ),
        _operation(
            "journey-get",
            "GET",
            PREFIX + "/journeys/{id}",
            {},
            summary="Read a journey and its cycles, receipts, evidence and blocker codes.",
        ),
        _operation(
            "deletion-preview",
            "GET",
            STRATEGY + "/deletion",
            {},
            summary="Read deletion blockers and the current strategy version before deleting.",
        ),
        _operation(
            "delete",
            "DELETE",
            STRATEGY,
            {"expected_version": POSITIVE_INT},
            required=("expected_version",),
            query_fields=("expected_version",),
            write=True,
            confirmation=True,
            summary="Delete a warmup strategy after deletion-preview; requires matching version and --yes.",
            readback="hireaicreator warmup +get --id STRATEGY_ID; verify not_found and inspect account participation.",
        ),
    ]
    for action in ("activate", "pause", "resume"):
        result.append(
            _operation(
                action,
                "POST",
                STRATEGY + "/" + action,
                TRANSITION,
                required=("expected_version",),
                write=True,
                confirmation=True,
                summary=(
                    f"{action.capitalize()} warmup with optimistic version control; requires --yes. "
                    + (
                        "May start automated generation/publication."
                        if action != "pause"
                        else "Read back paused state; already dispatched work may still complete."
                    )
                ),
                readback=readback,
            )
        )
    return result
