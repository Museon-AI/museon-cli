from __future__ import annotations

import pytest

from museoncli.domains import command_executors, get_command_spec, schema_payload


RETAINED = {
    "list",
    "get",
    "adb-connect",
    "stream-url",
    "connect-link-create",
    "connect-link-status",
    "performance-get",
    "profile-edit-draft",
    "profile-edit-submit",
    "profile-edit-batch-submit",
    "profile-edit-status",
    "avatar-generate-batch",
    "avatar-generate-status",
}

REMOVED = {
    "assets-get",
    "assets-set",
    "bgm-asset-list",
    "bgm-asset-create",
    "config-get",
    "config-update",
    "config-batch-update",
    "version-list",
    "version-get",
    "version-create",
    "version-activate",
    "schedule-list",
    "schedule-get",
    "schedule-generate",
    "schedule-create",
    "schedule-update",
    "schedule-delete",
}


def test_social_account_exposes_only_the_retained_product_surface() -> None:
    schema = schema_payload("social-account")
    shortcuts = {item["shortcut"].removeprefix("+") for item in schema["commands"]}
    executors = {
        name.removeprefix("social-account.")
        for name in command_executors()
        if name.startswith("social-account.")
    }

    assert shortcuts == RETAINED
    assert executors == RETAINED


@pytest.mark.parametrize("action", sorted(REMOVED))
def test_removed_social_account_actions_are_not_discoverable(action: str) -> None:
    with pytest.raises(ValueError, match="Unknown"):
        get_command_spec(f"social-account.{action}")
