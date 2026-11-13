from __future__ import annotations

import pytest
from routes_stub import Server, assert_organization_only, body, query, run

CAMPAIGN = "11111111-1111-4111-8111-111111111111"
BROADCAST = "88888888-8888-4888-8888-888888888888"
PERSONA = "33333333-3333-4333-8333-333333333333"
BASE = f"/api/v2/ugc/campaigns/{CAMPAIGN}"
ONE = f"{BASE}/broadcasts/{BROADCAST}"
CHANNEL = "123456789012345678"
AUDIENCE = {
    "campaign_updated_at": "2026-11-10T00:00:00Z",
    "private_channels": 40,
    "direct_messages": 35,
    "direct_message_limit": 200,
    "channels": [{"channel_id": CHANNEL, "name": "announcements", "is_private": False}],
    "personas": [{"persona_id": PERSONA, "title": "Moms", "private_channels": 12, "direct_messages": 9}],
    "private_channel_options": [],
    "recruitment_blockers": [],
    "channels_unavailable": False,
}


def _broadcast(**extra) -> dict:
    return {
        "id": BROADCAST,
        "campaign_id": CAMPAIGN,
        "purpose": "notice",
        "status": "draft",
        "body": "Hello",
        "to_all_private_channels": True,
        "private_channel_ids": [],
        "to_all_direct_messages": False,
        "guild_channel_ids": [],
        "mention_creators": True,
        "persona_ids": [],
        "attachments": [{"upload_id": "44444444-4444-4444-8444-444444444444", "filename": "a.png"}],
        "allowed_actions": ["edit", "schedule", "send", "discard"],
        "updated_at": "2026-11-12T08:00:00Z",
        "progress": {"total": 0},
        **extra,
    }


def _detail(**extra) -> dict:
    return {"broadcast": _broadcast(**extra), "deliveries": [], "history": [], "attachment_previews": []}


def test_create_dry_run_counts_who_it_would_reach(monkeypatch: pytest.MonkeyPatch) -> None:
    server = Server({("GET", f"{BASE}/broadcast-audience"): AUDIENCE})

    result = run(
        monkeypatch,
        server,
        ["ugc", "broadcast", "+create", "--campaign-id", CAMPAIGN, "--body", "New brief",
         "--to-all-private-channels", "--to-all-direct-messages", "--persona-id", PERSONA,
         "--channel-id", CHANNEL, "--dry-run"],
    )

    assert server.writes() == []
    assert query(server.requests[0]) == {"purpose": "notice"}
    reach = result["data"]["would_reach_now"]
    # A persona narrows "all" to its own creators.
    assert reach["private_channels"] == 12
    assert reach["direct_messages"] == 9
    assert reach["public_channels"] == [{"channel_id": CHANNEL, "name": "announcements"}]
    assert_organization_only(server)


def test_create_saves_a_draft(monkeypatch: pytest.MonkeyPatch) -> None:
    server = Server({("POST", f"{BASE}/broadcasts"): _broadcast()})

    result = run(
        monkeypatch,
        server,
        ["ugc", "broadcast", "+create", "--campaign-id", CAMPAIGN, "--body", "New brief",
         "--to-all-private-channels", "--no-mention-creators"],
    )

    assert body(server.requests[0]) == {
        "purpose": "notice",
        "mention_creators": False,
        "body": "New brief",
        "to_all_private_channels": True,
        "attachments": [],
    }
    assert any("+send" in step for step in result["next_steps"])


def test_update_keeps_the_drafts_files_and_other_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    server = Server({("GET", ONE): _detail(), ("PUT", ONE): _broadcast(body="Changed")})

    run(monkeypatch, server, ["ugc", "broadcast", "+update", "--campaign-id", CAMPAIGN, "--id", BROADCAST,
                              "--body", "Changed"])

    sent = body(server.writes()[0])
    assert sent["body"] == "Changed"
    assert sent["to_all_private_channels"] is True
    assert sent["attachments"] == [{"upload_id": "44444444-4444-4444-8444-444444444444"}]


def test_send_without_yes_only_previews(monkeypatch: pytest.MonkeyPatch) -> None:
    server = Server({("GET", ONE): _detail(), ("GET", f"{BASE}/broadcast-audience"): AUDIENCE})

    result = run(monkeypatch, server, ["ugc", "broadcast", "+send", "--campaign-id", CAMPAIGN, "--id", BROADCAST])

    assert server.writes() == []
    assert result["data"]["dry_run"] is True
    assert result["data"]["would_reach_now"]["private_channels"] == 40
    assert any("--yes" in step for step in result["next_steps"])


def test_send_with_yes_guards_on_the_version_read(monkeypatch: pytest.MonkeyPatch) -> None:
    server = Server(
        {
            ("GET", ONE): _detail(purpose="recruitment"),
            ("GET", f"{BASE}/broadcast-audience"): AUDIENCE,
            ("POST", f"{ONE}/send"): _broadcast(status="dispatched"),
        }
    )

    result = run(
        monkeypatch, server, ["ugc", "broadcast", "+send", "--campaign-id", CAMPAIGN, "--id", BROADCAST, "--yes"]
    )

    assert body(server.writes()[0]) == {
        "expected_updated_at": "2026-11-12T08:00:00Z",
        "expected_campaign_updated_at": "2026-11-10T00:00:00Z",
    }
    assert result["data"]["broadcast"]["status"] == "dispatched"
    assert_organization_only(server)


def test_schedule_needs_a_timezone(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValueError, match="timezone offset"):
        run(monkeypatch, Server({}), ["ugc", "broadcast", "+schedule", "--campaign-id", CAMPAIGN,
                                      "--id", BROADCAST, "--at", "2026-11-14T10:00:00", "--yes"])


def test_schedule_posts_the_time(monkeypatch: pytest.MonkeyPatch) -> None:
    server = Server(
        {
            ("GET", ONE): _detail(),
            ("GET", f"{BASE}/broadcast-audience"): AUDIENCE,
            ("POST", f"{ONE}/schedule"): _broadcast(status="scheduled"),
        }
    )

    run(monkeypatch, server, ["ugc", "broadcast", "+schedule", "--campaign-id", CAMPAIGN, "--id", BROADCAST,
                              "--at", "2026-11-14T10:00:00+08:00", "--yes"])

    assert body(server.writes()[0]) == {"scheduled_at": "2026-11-14T10:00:00+08:00"}


def test_withdraw_and_discard_need_yes(monkeypatch: pytest.MonkeyPatch) -> None:
    server = Server(
        {
            ("GET", ONE): _detail(status="dispatched", allowed_actions=["withdraw"]),
            ("POST", f"{ONE}/withdraw"): _broadcast(status="withdrawn"),
            ("DELETE", ONE): _broadcast(status="discarded"),
        }
    )

    preview = run(monkeypatch, server, ["ugc", "broadcast", "+withdraw", "--campaign-id", CAMPAIGN, "--id", BROADCAST])
    assert server.writes() == []
    assert preview["data"]["dry_run"] is True

    run(monkeypatch, server, ["ugc", "broadcast", "+withdraw", "--campaign-id", CAMPAIGN, "--id", BROADCAST, "--yes"])
    run(monkeypatch, server, ["ugc", "broadcast", "+discard", "--campaign-id", CAMPAIGN, "--id", BROADCAST, "--yes"])

    assert [(r.method, r.url.path) for r in server.writes()] == [("POST", f"{ONE}/withdraw"), ("DELETE", ONE)]


def test_list_passes_filters_and_paging(monkeypatch: pytest.MonkeyPatch) -> None:
    server = Server({("GET", f"{BASE}/broadcasts"): {"items": [], "next_cursor": None}})

    run(monkeypatch, server, ["ugc", "broadcast", "+list", "--campaign-id", CAMPAIGN, "--status", "draft",
                              "--status", "scheduled", "--page-size", "50"])

    request = server.requests[0]
    assert request.url.params.get_list("status") == ["draft", "scheduled"]
    assert request.url.params["limit"] == "50"
    assert_organization_only(server)
