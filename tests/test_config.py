from __future__ import annotations

import pytest

from museoncli.config import Config, PendingAuthState, normalize_api_base_url


def test_normalize_api_base_url_accepts_v1_base() -> None:
    assert normalize_api_base_url("https://api.museon.ai/api/v1") == (
        "https://api.museon.ai/api/v1"
    )


def test_normalize_api_base_url_appends_v1_to_origin() -> None:
    assert normalize_api_base_url("https://api.museon.ai") == "https://api.museon.ai/api/v1"
    assert normalize_api_base_url("http://127.0.0.1:8000/") == "http://127.0.0.1:8000/api/v1"


def test_normalize_api_base_url_rejects_versionless_paths() -> None:
    with pytest.raises(ValueError, match="/api/v1"):
        normalize_api_base_url("https://api.museon.ai/agent-cli")


def test_config_from_dict_normalizes_existing_versionless_config() -> None:
    cfg = Config.from_dict({"api_base_url": "https://api.museon.ai"})

    assert cfg.api_base_url == "https://api.museon.ai/api/v1"


def test_config_from_dict_preserves_workspace_organization_name() -> None:
    cfg = Config.from_dict(
        {
            "workspace": {
                "id": "workspace-1",
                "name": "MuseOn Official",
                "organization_id": "org-1",
                "organization_name": "MuseOn",
            }
        }
    )

    assert cfg.workspace.id == "workspace-1"
    assert cfg.workspace.organization_id == "org-1"
    assert cfg.workspace.organization_name == "MuseOn"


def test_safe_dict_redacts_pending_auth_device_code_and_url() -> None:
    cfg = Config()
    cfg.pending_auth = PendingAuthState(
        device_code="device-1",
        user_code="MUSEON-ABC123",
        verification_uri_complete="https://museon.ai/admin/cli/approve?device_code=device-1",
        expires_at=1600,
    )

    data = cfg.safe_dict()

    assert data["pending_auth"] == {
        "active": True,
        "expires_at": 1600,
        "user_code": "MUSEON-ABC123",
    }
    assert "device-1" not in str(data)
