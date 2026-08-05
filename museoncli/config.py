from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from museoncli.credentials import (
    clear_credentials,
    credential_backend,
    load_credentials,
    load_credentials_with_backend,
    save_credentials,
    write_private_json,
)
from museoncli.secret_provider import (
    AGENT_CAPABILITY_METHOD,
    API_KEY_METHOD,
    CredentialLease,
    resolve_auth_credential,
)


DEFAULT_SITE_URL = "https://www.museon.ai"
DEFAULT_API_BASE_URL = "https://api.museon.ai/api/v1"
API_V1_SUFFIX = "/api/v1"


@dataclass
class AuthState:
    expires_at: int | None = None
    user: dict[str, Any] | None = None
    api_key: str | None = None
    method: str | None = None
    provider: str | None = None
    managed_by: str | None = None
    secret_ref: str | None = None
    version: str | None = None
    persistable: bool = True
    resolution_error: str | None = None

    def is_expired(self, *, now: int | None = None) -> bool:
        if self.expires_at is None or (
            not self.api_key and self.resolution_error != "credential_expired"
        ):
            return False
        current_time = int(time.time()) if now is None else now
        return self.expires_at <= current_time

    def is_host_managed(self) -> bool:
        return self.method == AGENT_CAPABILITY_METHOD and self.managed_by == "agents_host"


@dataclass
class WorkspaceState:
    id: str | None = None
    name: str | None = None
    organization_id: str | None = None
    organization_name: str | None = None


@dataclass
class PendingAuthState:
    device_code: str | None = None
    user_code: str | None = None
    verification_uri: str | None = None
    verification_uri_complete: str | None = None
    expires_at: int | None = None
    interval: float | None = None


@dataclass
class Config:
    api_base_url: str = DEFAULT_API_BASE_URL
    site_url: str = DEFAULT_SITE_URL
    runtime_context: dict[str, Any] = field(default_factory=dict)
    auth: AuthState = field(default_factory=AuthState)
    workspace: WorkspaceState = field(default_factory=WorkspaceState)
    pending_auth: PendingAuthState = field(default_factory=PendingAuthState)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Config":
        cfg = cls()
        for key in (
            "api_base_url",
            "site_url",
        ):
            if value.get(key):
                parsed_value = (
                    normalize_api_base_url(value[key]) if key == "api_base_url" else value[key]
                )
                setattr(cfg, key, parsed_value)
        if isinstance(value.get("auth"), dict):
            cfg.auth = AuthState(
                **{k: value["auth"].get(k) for k in AuthState.__dataclass_fields__}
            )
        if isinstance(value.get("workspace"), dict):
            cfg.workspace = WorkspaceState(
                **{k: value["workspace"].get(k) for k in WorkspaceState.__dataclass_fields__}
            )
        if isinstance(value.get("pending_auth"), dict):
            cfg.pending_auth = PendingAuthState(
                **{k: value["pending_auth"].get(k) for k in PendingAuthState.__dataclass_fields__}
            )
        if isinstance(value.get("runtime_context"), dict):
            cfg.runtime_context = dict(value["runtime_context"])
        return cfg

    def safe_dict(self) -> dict[str, Any]:
        data = asdict(self)
        auth = data.get("auth") or {}
        auth_expired = self.auth.is_expired()
        authenticated = bool(auth.get("api_key")) and not auth_expired
        data["auth"] = {
            "authenticated": authenticated,
            "status": (
                "expired"
                if auth_expired
                else "authenticated"
                if authenticated
                else "unauthenticated"
            ),
            "reason": self.auth.resolution_error or ("credential_expired" if auth_expired else None),
            "auth_method": self.auth.method or ("api_key" if auth.get("api_key") else "none"),
            "credential_storage": self.auth.provider or credential_backend(config_path()),
            "expires_at": auth.get("expires_at"),
            "managed_by": auth.get("managed_by"),
            "version": auth.get("version"),
            "user": auth.get("user"),
        }
        pending_auth = data.get("pending_auth") or {}
        data["pending_auth"] = {
            "active": bool(pending_auth.get("device_code")),
            "expires_at": pending_auth.get("expires_at"),
            "user_code": pending_auth.get("user_code"),
        }
        return data


def config_path() -> Path:
    override = os.environ.get("MUSEONCLI_CONFIG")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".museoncli" / "config.json"


def skill_state_path() -> Path:
    return config_path().with_name("skills_seen.json")


def load_config() -> Config:
    path = config_path()
    if not path.exists():
        cfg = Config()
        apply_env_overrides(cfg)
        return cfg
    raw = json.loads(path.read_text(encoding="utf-8"))
    cfg = Config.from_dict(raw)
    legacy_auth = raw.get("auth") if isinstance(raw.get("auth"), dict) else {}
    inline_credential = legacy_auth.get("api_key")
    capability_mode = legacy_auth.get("method") == AGENT_CAPABILITY_METHOD or (
        isinstance(inline_credential, str) and inline_credential.startswith("mcap_")
    )
    stored_auth, stored_provider = (
        ({}, "unavailable") if capability_mode else load_credentials_with_backend(path)
    )
    lease = resolve_auth_credential(
        path,
        raw,
        stored_credentials=stored_auth,
        stored_provider=stored_provider,
    )
    if lease is not None:
        _apply_credential_lease(cfg.auth, lease)
    if any(
        legacy_auth.get(field_name) for field_name in ("api_key", "access_token", "refresh_token")
    ) and not (lease and lease.auth_method == AGENT_CAPABILITY_METHOD):
        legacy_api_key = legacy_auth.get("api_key")
        migration_api_key = stored_auth.get("api_key") or (
            legacy_api_key if isinstance(legacy_api_key, str) else None
        )
        save_credentials(path, {"api_key": migration_api_key})
        _write_non_secret_config(path, cfg)
    if not (lease and lease.auth_method == AGENT_CAPABILITY_METHOD):
        apply_env_overrides(cfg)
    return cfg


def save_config(config: Config) -> None:
    path = config_path()
    if config.auth.is_host_managed():
        if config.auth.provider == "legacy_inline":
            _write_legacy_inline_config(path, config)
        else:
            _write_non_secret_config(path, config)
        return
    previous = load_credentials(path)
    values: dict[str, str | None] = {}
    for field_name in stored_auth_fields():
        if _auth_field_is_from_environment(config, field_name):
            values[field_name] = previous.get(field_name)
        else:
            values[field_name] = getattr(config.auth, field_name)
    save_credentials(path, values)
    _write_non_secret_config(path, config)


def delete_auth_credentials() -> None:
    clear_credentials(config_path())


def stored_auth_fields() -> tuple[str, ...]:
    return ("api_key",)


def _write_non_secret_config(path: Path, config: Config) -> None:
    data = asdict(config)
    for field_name in stored_auth_fields():
        data["auth"].pop(field_name, None)
    write_private_json(path, data)


def _write_legacy_inline_config(path: Path, config: Config) -> None:
    """Update public state without converting an old host config to lease mode."""
    try:
        current = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, ValueError):
        return
    current_auth = current.get("auth") if isinstance(current, dict) else None
    inline = current_auth.get("api_key") if isinstance(current_auth, dict) else None
    if not isinstance(inline, str) or not inline.startswith("mcap_"):
        return
    data = asdict(config)
    data["auth"] = dict(current_auth)
    write_private_json(path, data)


def _auth_field_is_from_environment(config: Config, field_name: str) -> bool:
    return (
        field_name == "api_key"
        and bool(os.environ.get("MUSEON_API_KEY"))
        and (config.auth.api_key == os.environ.get("MUSEON_API_KEY"))
    )


def apply_env_overrides(config: Config) -> None:
    if os.environ.get("MUSEON_API_BASE_URL"):
        try:
            config.api_base_url = normalize_api_base_url(os.environ["MUSEON_API_BASE_URL"])
        except ValueError as exc:
            raise ValueError(f"MUSEON_API_BASE_URL is invalid: {exc}") from exc
    if os.environ.get("MUSEON_SITE_URL"):
        config.site_url = os.environ["MUSEON_SITE_URL"].rstrip("/")
    if os.environ.get("MUSEON_API_KEY"):
        config.auth.api_key = os.environ["MUSEON_API_KEY"]
        config.auth.method = API_KEY_METHOD
        config.auth.provider = "environment"
        config.auth.managed_by = "environment"
        config.auth.persistable = False
        # Environment credentials are independent from any previously stored
        # device-flow credential and therefore do not inherit its expiry.
        config.auth.expires_at = None


def _apply_credential_lease(auth: AuthState, lease: CredentialLease) -> None:
    auth.api_key = lease.value
    auth.method = lease.auth_method
    auth.provider = lease.provider
    auth.managed_by = lease.managed_by
    auth.expires_at = lease.expires_at
    auth.version = lease.version
    auth.persistable = lease.persistable
    auth.resolution_error = lease.error


def update_config(**values: str | None) -> Config:
    cfg = load_config()
    for key, value in values.items():
        if value is not None:
            normalized = normalize_api_base_url(value) if key == "api_base_url" else value
            setattr(cfg, key, normalized.rstrip("/") if key.endswith("_url") else normalized)
    save_config(cfg)
    return cfg


def normalize_api_base_url(value: str) -> str:
    base = value.rstrip("/")
    if base.endswith(API_V1_SUFFIX):
        return base
    parsed = urlsplit(base)
    if parsed.path in {"", "/"}:
        return f"{base}{API_V1_SUFFIX}"
    raise ValueError(
        f"api_base_url must point at the Museon v1 API and end with /api/v1. Got: {base}"
    )
