from __future__ import annotations

import json
import os
import stat
import base64
from pathlib import Path

import pytest

from museoncli.config import (
    AuthState,
    Config,
    PendingAuthState,
    load_config,
    normalize_api_base_url,
    save_config,
)
from museoncli.secret_provider import agent_secret_lease_path


def _capability(*, expires_at: int, version: str = "lease-1") -> str:
    def segment(payload: dict[str, object]) -> str:
        encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
        return encoded.rstrip("=")

    return f"mcap_{segment({'alg': 'RS256'})}.{segment({'exp': expires_at, 'jti': version})}.signature"


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
        verification_uri_complete="https://museon.ai/cli/authorize?device_code=device-1",
        expires_at=1600,
    )

    data = cfg.safe_dict()

    assert data["pending_auth"] == {
        "active": True,
        "expires_at": 1600,
        "user_code": "MUSEON-ABC123",
    }
    assert "device-1" not in str(data)


def test_safe_dict_reports_expired_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = Config(auth=AuthState(api_key="expired-key", expires_at=1000))
    monkeypatch.setattr("museoncli.config.time.time", lambda: 1000)

    assert cfg.safe_dict()["auth"] | {"credential_storage": "ignored"} == {
        "authenticated": False,
        "status": "expired",
        "reason": "credential_expired",
        "auth_method": "api_key",
        "credential_storage": "ignored",
        "expires_at": 1000,
        "managed_by": None,
        "version": None,
        "user": None,
    }


def test_safe_dict_does_not_report_expired_without_a_credential() -> None:
    cfg = Config(auth=AuthState(expires_at=1000))

    assert cfg.safe_dict()["auth"]["status"] == "unauthenticated"


def test_environment_api_key_does_not_inherit_stored_expiration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from museoncli.config import apply_env_overrides

    cfg = Config(auth=AuthState(api_key="stored-key", expires_at=1000))
    monkeypatch.setenv("MUSEON_API_KEY", "environment-key")

    apply_env_overrides(cfg)

    assert cfg.auth.api_key == "environment-key"
    assert cfg.auth.expires_at is None


def test_config_keeps_credentials_out_of_non_secret_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_file = tmp_path / "config.json"
    credential_file = tmp_path / "credentials.json"
    monkeypatch.setenv("MUSEONCLI_CONFIG", str(config_file))
    monkeypatch.setenv("MUSEONCLI_CREDENTIAL_BACKEND", "file")

    cfg = Config()
    cfg.auth = AuthState(
        api_key="museon-secret",
        user={"id": "user-1", "email": "user@example.com"},
    )
    save_config(cfg)

    public_payload = json.loads(config_file.read_text(encoding="utf-8"))
    credential_payload = json.loads(credential_file.read_text(encoding="utf-8"))
    assert "api_key" not in public_payload["auth"]
    assert credential_payload == {"api_key": "museon-secret"}

    loaded = load_config()
    assert loaded.auth.api_key == "museon-secret"
    assert loaded.safe_dict()["auth"]["credential_storage"] == "protected_file"


@pytest.mark.skipif(
    os.name == "nt",
    reason="Windows file access is enforced by ACLs rather than POSIX mode bits",
)
def test_file_backend_uses_owner_only_permissions_on_posix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_file = tmp_path / "config.json"
    credential_file = tmp_path / "credentials.json"
    monkeypatch.setenv("MUSEONCLI_CONFIG", str(config_file))
    monkeypatch.setenv("MUSEONCLI_CREDENTIAL_BACKEND", "file")

    save_config(Config(auth=AuthState(api_key="museon-secret")))

    assert stat.S_IMODE(credential_file.stat().st_mode) == 0o600
    assert stat.S_IMODE(config_file.stat().st_mode) == 0o600


def test_config_file_backend_supports_platforms_without_fchmod(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_file = tmp_path / "config.json"
    monkeypatch.setenv("MUSEONCLI_CONFIG", str(config_file))
    monkeypatch.setenv("MUSEONCLI_CREDENTIAL_BACKEND", "file")
    monkeypatch.delattr("museoncli.credentials.os.fchmod", raising=False)

    cfg = Config(auth=AuthState(api_key="museon-secret"))
    save_config(cfg)

    assert json.loads(tmp_path.joinpath("credentials.json").read_text()) == {
        "api_key": "museon-secret"
    }


def test_environment_credentials_are_not_persisted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_file = tmp_path / "config.json"
    credential_file = tmp_path / "credentials.json"
    monkeypatch.setenv("MUSEONCLI_CONFIG", str(config_file))
    monkeypatch.setenv("MUSEONCLI_CREDENTIAL_BACKEND", "file")
    monkeypatch.setenv("MUSEON_API_KEY", "injected-secret")

    cfg = Config(auth=AuthState(api_key="injected-secret"))
    save_config(cfg)

    assert config_file.is_file()
    assert not credential_file.exists()
    assert "injected-secret" not in config_file.read_text(encoding="utf-8")


def test_environment_key_is_not_persisted_while_migrating_legacy_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_file = tmp_path / "config.json"
    monkeypatch.setenv("MUSEONCLI_CONFIG", str(config_file))
    monkeypatch.setenv("MUSEONCLI_CREDENTIAL_BACKEND", "file")
    monkeypatch.setenv("MUSEON_API_KEY", "environment-key")
    config_file.write_text(
        json.dumps({"auth": {"api_key": "legacy-user-key"}}), encoding="utf-8"
    )

    cfg = load_config()

    assert cfg.auth.api_key == "environment-key"
    assert json.loads(tmp_path.joinpath("credentials.json").read_text()) == {
        "api_key": "legacy-user-key"
    }


def test_legacy_inline_credentials_are_migrated_on_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_file = tmp_path / "config.json"
    monkeypatch.setenv("MUSEONCLI_CONFIG", str(config_file))
    monkeypatch.setenv("MUSEONCLI_CREDENTIAL_BACKEND", "file")
    config_file.write_text(
        json.dumps({"auth": {"api_key": "legacy-secret"}}),
        encoding="utf-8",
    )

    cfg = load_config()

    assert cfg.auth.api_key == "legacy-secret"
    assert "legacy-secret" not in config_file.read_text(encoding="utf-8")
    assert json.loads(tmp_path.joinpath("credentials.json").read_text())["api_key"] == (
        "legacy-secret"
    )


def test_fresh_legacy_inline_capability_overrides_stale_stored_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_file = tmp_path / "config.json"
    credential_file = tmp_path / "credentials.json"
    capability = _capability(expires_at=4_000_000_000)
    monkeypatch.setenv("MUSEONCLI_CONFIG", str(config_file))
    monkeypatch.setenv("MUSEONCLI_CREDENTIAL_BACKEND", "file")
    config_file.write_text(json.dumps({"auth": {"api_key": capability}}), encoding="utf-8")
    credential_file.write_text(json.dumps({"api_key": "stale-key"}), encoding="utf-8")

    cfg = load_config()

    assert cfg.auth.api_key == capability
    assert cfg.auth.method == "agent_capability"
    assert cfg.auth.provider == "legacy_inline"
    assert json.loads(credential_file.read_text()) == {"api_key": "stale-key"}


def test_saving_public_state_preserves_legacy_inline_capability(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_file = tmp_path / "config.json"
    capability = _capability(expires_at=4_000_000_000)
    monkeypatch.setenv("MUSEONCLI_CONFIG", str(config_file))
    config_file.write_text(
        json.dumps({"auth": {"api_key": capability}, "workspace": {}}), encoding="utf-8"
    )
    cfg = load_config()
    cfg.workspace.id = "workspace-2"

    save_config(cfg)

    payload = json.loads(config_file.read_text())
    assert payload["auth"] == {"api_key": capability}
    assert payload["workspace"]["id"] == "workspace-2"
    assert load_config().auth.api_key == capability


def test_agent_session_lease_is_exclusive_over_environment_and_stored_api_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_file = tmp_path / "config.json"
    capability = _capability(expires_at=4_000_000_000, version="lease-current")
    monkeypatch.setenv("MUSEONCLI_CONFIG", str(config_file))
    monkeypatch.setenv("MUSEONCLI_CREDENTIAL_BACKEND", "file")
    monkeypatch.setenv("MUSEON_API_KEY", "environment-key")
    config_file.write_text(
        json.dumps(
            {
                "auth": {
                    "method": "agent_capability",
                    "provider": "agent_session",
                    "secret_ref": "museon-api",
                    "managed_by": "agents_host",
                    "persistable": False,
                }
            }
        ),
        encoding="utf-8",
    )
    tmp_path.joinpath("credentials.json").write_text(
        json.dumps({"api_key": "stored-key"}), encoding="utf-8"
    )
    lease_path = agent_secret_lease_path(config_file)
    lease_path.parent.mkdir()
    lease_path.write_text(
        json.dumps(
            {
                "value": capability,
                "auth_method": "agent_capability",
                "managed_by": "agents_host",
                "expires_at": 4_000_000_000,
                "version": "lease-current",
                "persistable": False,
            }
        ),
        encoding="utf-8",
    )

    cfg = load_config()

    assert cfg.auth.api_key == capability
    assert cfg.auth.method == "agent_capability"
    assert cfg.auth.provider == "agent_session"
    assert cfg.auth.version == "lease-current"


def test_missing_agent_session_lease_fails_closed_without_api_key_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_file = tmp_path / "config.json"
    monkeypatch.setenv("MUSEONCLI_CONFIG", str(config_file))
    monkeypatch.setenv("MUSEONCLI_CREDENTIAL_BACKEND", "file")
    monkeypatch.setenv("MUSEON_API_KEY", "environment-key")
    config_file.write_text(
        json.dumps(
            {
                "auth": {
                    "method": "agent_capability",
                    "provider": "agent_session",
                    "secret_ref": "museon-api",
                    "managed_by": "agents_host",
                }
            }
        ),
        encoding="utf-8",
    )
    tmp_path.joinpath("credentials.json").write_text(
        json.dumps({"api_key": "stored-key"}), encoding="utf-8"
    )

    cfg = load_config()

    assert cfg.auth.api_key is None
    assert cfg.auth.method == "agent_capability"
    assert cfg.auth.resolution_error == "credential_missing"


def test_agent_session_mode_does_not_touch_persistent_credential_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_file = tmp_path / "config.json"
    monkeypatch.setenv("MUSEONCLI_CONFIG", str(config_file))
    monkeypatch.setattr(
        "museoncli.config.load_credentials_with_backend",
        lambda _path: (_ for _ in ()).throw(AssertionError("must not load stored credentials")),
    )
    config_file.write_text(
        json.dumps(
            {
                "auth": {
                    "method": "agent_capability",
                    "provider": "agent_session",
                    "secret_ref": "museon-api",
                    "managed_by": "agents_host",
                }
            }
        ),
        encoding="utf-8",
    )

    cfg = load_config()

    assert cfg.auth.method == "agent_capability"
    assert cfg.auth.resolution_error == "credential_missing"


def test_host_managed_config_save_does_not_persist_capability(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_file = tmp_path / "config.json"
    monkeypatch.setenv("MUSEONCLI_CONFIG", str(config_file))
    monkeypatch.setenv("MUSEONCLI_CREDENTIAL_BACKEND", "file")
    cfg = Config(
        auth=AuthState(
            api_key=_capability(expires_at=4_000_000_000),
            method="agent_capability",
            provider="agent_session",
            managed_by="agents_host",
            secret_ref="museon-api",
            persistable=False,
        )
    )

    save_config(cfg)

    assert not tmp_path.joinpath("credentials.json").exists()
    assert "mcap_" not in config_file.read_text(encoding="utf-8")


def test_legacy_bearer_credentials_are_removed_on_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_file = tmp_path / "config.json"
    credential_file = tmp_path / "credentials.json"
    monkeypatch.setenv("MUSEONCLI_CONFIG", str(config_file))
    monkeypatch.setenv("MUSEONCLI_CREDENTIAL_BACKEND", "file")
    config_file.write_text(
        json.dumps(
            {
                "auth": {
                    "access_token": "old-access-token",
                    "refresh_token": "old-refresh-token",
                }
            }
        ),
        encoding="utf-8",
    )
    credential_file.write_text(
        json.dumps(
            {
                "api_key": "current-api-key",
                "access_token": "old-access-token",
                "refresh_token": "old-refresh-token",
            }
        ),
        encoding="utf-8",
    )

    cfg = load_config()

    assert cfg.auth.api_key == "current-api-key"
    assert json.loads(credential_file.read_text()) == {"api_key": "current-api-key"}
    serialized_config = config_file.read_text(encoding="utf-8")
    assert "old-access-token" not in serialized_config
    assert "old-refresh-token" not in serialized_config
