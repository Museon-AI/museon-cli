"""Tests for staff-only `social-account credentials` 3rd-level commands."""

from __future__ import annotations

import pytest

from museoncli.domains import get_command_spec
from tests.routes_stub import Server, assert_organization_only, body, run

ACCOUNT_ID = "10000000-0000-4000-8000-000000000042"


def test_social_account_credential_commands_are_staff_only_under_credentials_resource() -> None:
    expected_read = (
        "social-account.credentials-totp-code",
        "social-account.credentials-get",
        "social-account.credentials-bulk-status",
        "social-account.credentials-bulk-totp-codes",
        "social-account.credentials-bulk-get",
    )
    for name in expected_read:
        spec = get_command_spec(name)
        assert spec.resource == "credentials"
        assert spec.required_roles == ("staff",)
        assert spec.risk_level == "read"

    upsert = get_command_spec("social-account.credentials-bulk-upsert")
    assert upsert.resource == "credentials"
    assert upsert.required_roles == ("staff",)
    assert upsert.risk_level == "write"
    assert upsert.supports_dry_run is True
    assert upsert.dry_run_reads_server is True


def test_get_totp_code_posts_reason_and_returns_live_code(monkeypatch: pytest.MonkeyPatch) -> None:
    server = Server(
        {
            ("POST", f"/api/v1/agent-cli/pool-accounts/{ACCOUNT_ID}/totp-code"): {
                "success": True,
                "data": {
                    "domain": "pool-account",
                    "action": "totp-code",
                    "resource_id": ACCOUNT_ID,
                    "result": {
                        "pool_account_id": ACCOUNT_ID,
                        "platform": "tiktok",
                        "login_method": "password",
                        "effective_login_type": "platform_password",
                        "email": "demo@tk1860.com",
                        "code": "123456",
                        "expires_in_seconds": 19,
                        "period": 30,
                        "totp_source": "account",
                        "second_factor_kind": "totp",
                        "verification_urls": [],
                        "inherited_from_account_id": None,
                    },
                },
            }
        }
    )

    out = run(
        monkeypatch,
        server,
        [
            "social-account",
            "credentials",
            "+totp-code",
            "--id",
            ACCOUNT_ID,
            "--reason",
            "cloud-phone login",
        ],
    )

    assert out["command"] == "social-account.credentials-totp-code"
    assert out["data"]["code"] == "123456"
    assert out["data"]["expires_in_seconds"] == 19
    assert server.calls() == [("POST", f"/api/v1/agent-cli/pool-accounts/{ACCOUNT_ID}/totp-code")]
    assert body(server.requests[0]) == {"reason": "cloud-phone login"}
    assert_organization_only(server)


def test_get_credentials_omits_seed_by_default_and_honors_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _handler(request):
        req_body = body(request)
        return {
            "success": True,
            "data": {
                "domain": "pool-account",
                "action": "credentials-reveal",
                "resource_id": ACCOUNT_ID,
                "result": {
                    "pool_account_id": ACCOUNT_ID,
                    "platform": "youtube",
                    "username": "yt_demo",
                    "effective_login_type": "google_sso",
                    "email": "shared@gmail.com",
                    "password": "resolved-password",
                    "totp_code": "654321",
                    "totp_expires_in_seconds": 22,
                    "totp_secret": (
                        "JBSWY3DPEHPK3PXP" if req_body.get("include_totp_secret") else None
                    ),
                    "identity_shared_account_count": 4,
                },
            },
        }

    server = Server(
        {("POST", f"/api/v1/agent-cli/pool-accounts/{ACCOUNT_ID}/credentials"): _handler}
    )

    default_out = run(
        monkeypatch,
        server,
        ["social-account", "credentials", "+get", "--id", ACCOUNT_ID],
    )
    assert default_out["command"] == "social-account.credentials-get"
    assert default_out["data"]["effective_login_type"] == "google_sso"
    assert default_out["data"]["totp_code"] == "654321"
    assert default_out["data"]["totp_secret"] is None
    assert body(server.requests[0]) == {"include_totp_secret": False}

    seed_out = run(
        monkeypatch,
        server,
        [
            "social-account",
            "credentials",
            "+get",
            "--id",
            ACCOUNT_ID,
            "--reason",
            "rebind authenticator",
            "--include-totp-secret",
        ],
    )
    assert seed_out["command"] == "social-account.credentials-get"
    assert seed_out["data"]["totp_secret"] == "JBSWY3DPEHPK3PXP"
    assert body(server.requests[1]) == {
        "reason": "rebind authenticator",
        "include_totp_secret": True,
    }
    assert_organization_only(server)


def test_bulk_status_and_bulk_totp_and_bulk_reveal_commands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    account_b = "10000000-0000-4000-8000-000000000043"
    server = Server(
        {
            ("POST", "/api/v1/agent-cli/pool-accounts/credentials/status"): {
                "success": True,
                "data": {
                    "domain": "pool-account",
                    "action": "credentials-bulk-status",
                    "result": {
                        "items": [{"pool_account_id": ACCOUNT_ID, "found": True, "has_totp": True}],
                        "summary": {"requested": 2, "found": 2},
                    },
                },
            },
            ("POST", "/api/v1/agent-cli/pool-accounts/totp-codes/bulk"): {
                "success": True,
                "data": {
                    "domain": "pool-account",
                    "action": "totp-codes-bulk",
                    "result": {
                        "items": [{"pool_account_id": ACCOUNT_ID, "status": "ok", "code": "111222"}],
                        "summary": {"requested": 2, "generated": 2},
                    },
                },
            },
            ("POST", "/api/v1/agent-cli/pool-accounts/credentials/bulk-reveal"): {
                "success": True,
                "data": {
                    "domain": "pool-account",
                    "action": "credentials-bulk-reveal",
                    "result": {
                        "items": [{"pool_account_id": ACCOUNT_ID, "status": "ok"}],
                        "summary": {"requested": 2, "revealed": 2},
                    },
                },
            },
        }
    )

    st = run(
        monkeypatch,
        server,
        [
            "social-account",
            "credentials",
            "+bulk-status",
            "--id",
            ACCOUNT_ID,
            "--id",
            account_b,
        ],
    )
    assert st["command"] == "social-account.credentials-bulk-status"
    assert body(server.requests[0]) == {"account_ids": [ACCOUNT_ID, account_b]}

    totps = run(
        monkeypatch,
        server,
        [
            "social-account",
            "credentials",
            "+bulk-totp-codes",
            "--id",
            ACCOUNT_ID,
            "--id",
            account_b,
            "--reason",
            "batch login",
        ],
    )
    assert totps["command"] == "social-account.credentials-bulk-totp-codes"
    assert body(server.requests[1]) == {
        "account_ids": [ACCOUNT_ID, account_b],
        "reason": "batch login",
    }

    with pytest.raises(ValueError, match="--reason"):
        run(
            monkeypatch,
            server,
            ["social-account", "credentials", "+bulk-get", "--id", ACCOUNT_ID],
        )

    rev = run(
        monkeypatch,
        server,
        [
            "social-account",
            "credentials",
            "+bulk-get",
            "--id",
            ACCOUNT_ID,
            "--id",
            account_b,
            "--reason",
            "cloud phone batch",
        ],
    )
    assert rev["command"] == "social-account.credentials-bulk-get"
    assert body(server.requests[2]) == {
        "account_ids": [ACCOUNT_ID, account_b],
        "reason": "cloud phone batch",
        "include_totp_secret": False,
    }
    assert_organization_only(server)


def test_bulk_upsert_reads_csv_file_and_routes_dry_run_to_server(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    csv_file = tmp_path / "creds.csv"
    csv_file.write_text(
        "platform,username,email,password,2FA\n"
        "tiktok,demo_user,demo@tk1860.com,secret-pass,JBSWY3DPEHPK3PXP\n",
        encoding="utf-8",
    )
    server = Server(
        {
            ("POST", "/api/v1/agent-cli/pool-accounts/credentials/bulk-upsert"): lambda req: {
                "success": True,
                "data": {
                    "domain": "pool-account",
                    "action": "credentials-bulk-upsert",
                    "result": {
                        "dry_run": body(req)["dry_run"],
                        "overwrite": body(req)["overwrite"],
                        "items": [{"index": 0, "status": "would_upsert"}],
                        "summary": {"requested": 1, "would_upsert": 1},
                    },
                },
            }
        }
    )

    out = run(
        monkeypatch,
        server,
        [
            "social-account",
            "credentials",
            "+bulk-upsert",
            "--file",
            str(csv_file),
            "--overwrite",
            "--reason",
            "vendor batch",
            "--dry-run",
        ],
    )
    assert out["command"] == "social-account.credentials-bulk-upsert"
    assert out["data"]["dry_run"] is True
    assert "secret-pass" not in str(out)
    req_payload = body(server.requests[0])
    assert req_payload["dry_run"] is True
    assert req_payload["overwrite"] is True
    assert req_payload["reason"] == "vendor batch"
    assert req_payload["items"] == [
        {
            "platform": "tiktok",
            "username": "demo_user",
            "email": "demo@tk1860.com",
            "password": "secret-pass",
            "2fa": "JBSWY3DPEHPK3PXP",
        }
    ]
    assert_organization_only(server)


def test_single_totp_and_get_support_platform_and_handle_full_pool_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = Server(
        {
            ("POST", "/api/v1/agent-cli/pool-accounts/totp-code"): {
                "success": True,
                "data": {
                    "domain": "pool-account",
                    "action": "totp-code",
                    "resource_id": ACCOUNT_ID,
                    "result": {
                        "pool_account_id": ACCOUNT_ID,
                        "platform": "tiktok",
                        "code": "987654",
                        "expires_in_seconds": 17,
                    },
                },
            },
            ("POST", "/api/v1/agent-cli/pool-accounts/credentials"): {
                "success": True,
                "data": {
                    "domain": "pool-account",
                    "action": "credentials-reveal",
                    "resource_id": ACCOUNT_ID,
                    "result": {
                        "pool_account_id": ACCOUNT_ID,
                        "platform": "tiktok",
                        "username": "demo_user",
                        "password": "resolved-password",
                        "totp_code": "987654",
                        "totp_secret": None,
                    },
                },
            },
        }
    )

    totp_out = run(
        monkeypatch,
        server,
        [
            "social-account",
            "credentials",
            "+totp-code",
            "--platform",
            "tiktok",
            "--handle",
            "@demo_user",
            "--reason",
            "staff check",
        ],
    )
    assert totp_out["data"]["code"] == "987654"
    assert body(server.requests[0]) == {
        "platform": "tiktok",
        "handle": "@demo_user",
        "reason": "staff check",
    }

    cred_out = run(
        monkeypatch,
        server,
        [
            "social-account",
            "credentials",
            "+get",
            "--platform",
            "tk",
            "--handle",
            "demo_user",
        ],
    )
    assert cred_out["data"]["password"] == "resolved-password"
    assert body(server.requests[1]) == {
        "platform": "tk",
        "handle": "demo_user",
        "include_totp_secret": False,
    }

    with pytest.raises(ValueError, match="not both"):
        run(
            monkeypatch,
            server,
            [
                "social-account",
                "credentials",
                "+totp-code",
                "--id",
                ACCOUNT_ID,
                "--platform",
                "tiktok",
                "--handle",
                "demo_user",
            ],
        )

    with pytest.raises(ValueError, match="requires --id or both --platform and --handle"):
        run(
            monkeypatch,
            server,
            ["social-account", "credentials", "+get", "--handle", "demo_user"],
        )


def test_bulk_commands_support_platform_handles_and_mixed_account_refs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = Server(
        {
            ("POST", "/api/v1/agent-cli/pool-accounts/credentials/status"): {
                "success": True,
                "data": {
                    "domain": "pool-account",
                    "action": "credentials-bulk-status",
                    "result": {"items": [], "summary": {"requested": 2, "found": 2}},
                },
            },
            ("POST", "/api/v1/agent-cli/pool-accounts/totp-codes/bulk"): {
                "success": True,
                "data": {
                    "domain": "pool-account",
                    "action": "totp-codes-bulk",
                    "result": {"items": [], "summary": {"requested": 2, "generated": 2}},
                },
            },
            ("POST", "/api/v1/agent-cli/pool-accounts/credentials/bulk-reveal"): {
                "success": True,
                "data": {
                    "domain": "pool-account",
                    "action": "credentials-bulk-reveal",
                    "result": {"items": [], "summary": {"requested": 2, "revealed": 2}},
                },
            },
        }
    )

    run(
        monkeypatch,
        server,
        [
            "social-account",
            "credentials",
            "+bulk-status",
            "--platform",
            "tiktok",
            "--handle",
            "@a",
            "--handle",
            "@b",
        ],
    )
    assert body(server.requests[0]) == {
        "accounts": [
            {"platform": "tiktok", "handle": "@a"},
            {"platform": "tiktok", "handle": "@b"},
        ]
    }

    run(
        monkeypatch,
        server,
        [
            "social-account",
            "credentials",
            "+bulk-totp-codes",
            "--account",
            "tiktok:@a",
            "--account",
            "instagram:b",
            "--reason",
            "batch login",
        ],
    )
    assert body(server.requests[1]) == {
        "accounts": [
            {"platform": "tiktok", "handle": "@a"},
            {"platform": "instagram", "handle": "b"},
        ],
        "reason": "batch login",
    }

    run(
        monkeypatch,
        server,
        [
            "social-account",
            "credentials",
            "+bulk-get",
            "--id",
            ACCOUNT_ID,
            "--account",
            "youtube:yt_demo",
            "--reason",
            "mixed batch",
        ],
    )
    assert body(server.requests[2]) == {
        "account_ids": [ACCOUNT_ID],
        "accounts": [{"platform": "youtube", "handle": "yt_demo"}],
        "reason": "mixed batch",
        "include_totp_secret": False,
    }

    with pytest.raises(ValueError, match="requires --platform"):
        run(
            monkeypatch,
            server,
            ["social-account", "credentials", "+bulk-status", "--handle", "@a"],
        )

    with pytest.raises(ValueError, match="Invalid --account"):
        run(
            monkeypatch,
            server,
            ["social-account", "credentials", "+bulk-status", "--account", "no_colon_here"],
        )
