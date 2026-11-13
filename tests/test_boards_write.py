from __future__ import annotations

import pytest
from routes_stub import ORG, Server, assert_organization_only, body, run

BOARD = "66666666-6666-4666-8666-666666666666"
CAMPAIGN = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"
PATH = f"/api/v1/analytics-dashboards/{BOARD}"


def _board(**filters) -> dict:
    return {
        "id": BOARD,
        "workspace_id": None,
        "agency": False,
        "name": "Q4",
        "campaign_type": "ugc",
        "campaigns": [{"id": CAMPAIGN, "name": "A", "campaign_type": "ugc", "available": True}],
        "filters": {
            "date_from": "2026-10-01",
            "date_to": None,
            "platform": "tiktok",
            "post_scope": "approved",
            "accounts": [],
            "thresholds": {"views_min": 500.0},
            "metrics": ["views"],
            "chart_mode": "daily",
            **filters,
        },
        "is_public": True,
        "updated_at": "2026-11-12T00:00:00Z",
    }


def test_create_makes_the_board_in_the_selected_organization(monkeypatch: pytest.MonkeyPatch) -> None:
    server = Server({("POST", "/api/v1/analytics-dashboards"): {"id": BOARD, "name": "Q4"}})

    result = run(
        monkeypatch,
        server,
        [
            "analytics", "board", "+create", "--name", " Q4 ", "--campaign-type", "product-seeding",
            "--campaign-id", CAMPAIGN, "--campaign-id", OTHER, "--campaign-id", CAMPAIGN,
            "--metric", "engagement-rate", "--threshold", "views-min=1000",
        ],
    )

    assert server.calls() == [("POST", "/api/v1/analytics-dashboards")]
    sent = body(server.requests[0])
    assert sent["organization_id"] == ORG
    assert sent["name"] == "Q4"
    assert sent["campaign_type"] == "product_seeding"
    assert sent["campaign_ids"] == [CAMPAIGN, OTHER]
    # A filter passed at creation fills in the rest with the board defaults.
    assert sent["filters"]["metrics"] == ["engagement_rate"]
    assert sent["filters"]["thresholds"] == {"views_min": 1000.0}
    assert sent["filters"]["post_scope"] == "all"
    assert result["command"] == "analytics.board-create"
    assert result["data"] == {"id": BOARD, "name": "Q4"}
    assert_organization_only(server)


def test_create_dry_run_sends_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    server = Server({})

    result = run(
        monkeypatch,
        server,
        ["analytics", "board", "+create", "--name", "Q4", "--campaign-type", "ugc",
         "--campaign-id", CAMPAIGN, "--dry-run"],
    )

    assert server.requests == []
    assert result["data"]["dry_run"] is True
    assert "filters" not in result["data"]["board"]


def test_update_changes_only_the_passed_filters(monkeypatch: pytest.MonkeyPatch) -> None:
    server = Server({("GET", PATH): _board(), ("PATCH", PATH): _board(platform=None)})

    preview = run(
        monkeypatch, server, ["analytics", "board", "+update", "--id", BOARD, "--platform", "all", "--dry-run"]
    )
    assert server.writes() == []
    assert preview["data"]["changes"] == [{"field": "platform", "before": "tiktok", "after": None}]

    run(monkeypatch, server, ["analytics", "board", "+update", "--id", BOARD, "--platform", "all"])

    patch = body(server.writes()[0])
    assert "name" not in patch
    # The whole saved filter set travels back with only the platform cleared.
    assert patch["filters"] == {**_board()["filters"], "platform": None}
    assert_organization_only(server)


def test_update_with_nothing_different_writes_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    server = Server({("GET", PATH): _board()})

    result = run(monkeypatch, server, ["analytics", "board", "+update", "--id", BOARD, "--name", "Q4"])

    assert server.writes() == []
    assert result["data"]["changes"] == []


def test_update_rejects_an_unknown_metric(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValueError, match="not a board metric"):
        run(monkeypatch, Server({}), ["analytics", "board", "+update", "--id", BOARD, "--metric", "reach"])


def test_set_source_replaces_the_campaigns(monkeypatch: pytest.MonkeyPatch) -> None:
    server = Server({("GET", PATH): _board(), ("PUT", f"{PATH}/data-source"): _board()})

    result = run(
        monkeypatch,
        server,
        ["analytics", "board", "+set-source", "--id", BOARD, "--campaign-type", "mixed",
         "--campaign-id", OTHER],
    )

    assert body(server.writes()[0]) == {"campaign_type": "mixed", "campaign_ids": [OTHER]}
    assert result["data"]["campaigns_added"] == [OTHER]
    assert result["data"]["campaigns_removed"] == [CAMPAIGN]


def test_delete_without_yes_only_previews(monkeypatch: pytest.MonkeyPatch) -> None:
    server = Server({("GET", PATH): _board(), ("DELETE", PATH): None})

    preview = run(monkeypatch, server, ["analytics", "board", "+delete", "--id", BOARD])

    assert server.writes() == []
    assert preview["data"]["dry_run"] is True
    assert preview["data"]["board"]["name"] == "Q4"
    assert any("share link" in warning for warning in preview["warnings"])
    assert any("--yes" in step for step in preview["next_steps"])

    done = run(monkeypatch, server, ["analytics", "board", "+delete", "--id", BOARD, "--yes"])

    assert [(r.method, r.url.path) for r in server.writes()] == [("DELETE", PATH)]
    assert done["data"]["deleted"] is True
    assert_organization_only(server)
