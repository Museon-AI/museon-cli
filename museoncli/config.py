from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


DEFAULT_SITE_URL = "https://www.museon.ai"
DEFAULT_API_BASE_URL = "https://api.museon.ai/api/v1"
DEFAULT_WORKSPACE_NAME = "MuseOn Official"
API_V1_SUFFIX = "/api/v1"


@dataclass
class AuthState:
    access_token: str | None = None
    refresh_token: str | None = None
    expires_at: int | None = None
    user: dict[str, Any] | None = None
    api_key: str | None = None


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
    supabase_url: str | None = None
    supabase_anon_key: str | None = None
    default_workspace_name: str = DEFAULT_WORKSPACE_NAME
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
            "supabase_url",
            "supabase_anon_key",
            "default_workspace_name",
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
        apply_env_overrides(cfg)
        return cfg

    def safe_dict(self) -> dict[str, Any]:
        data = asdict(self)
        auth = data.get("auth") or {}
        auth_method = "none"
        if auth.get("api_key"):
            auth_method = "api_key"
        elif auth.get("access_token"):
            auth_method = "bearer"
        data["auth"] = {
            "authenticated": bool(auth.get("access_token") or auth.get("api_key")),
            "auth_method": auth_method,
            "expires_at": auth.get("expires_at"),
            "user": auth.get("user"),
        }
        if data.get("supabase_anon_key"):
            data["supabase_anon_key"] = "***"
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
    return Config.from_dict(json.loads(path.read_text(encoding="utf-8")))


def save_config(config: Config) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(config), indent=2, ensure_ascii=False), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def apply_env_overrides(config: Config) -> None:
    if os.environ.get("MUSEON_API_BASE_URL"):
        try:
            config.api_base_url = normalize_api_base_url(os.environ["MUSEON_API_BASE_URL"])
        except ValueError as exc:
            raise ValueError(f"MUSEON_API_BASE_URL is invalid: {exc}") from exc
    if os.environ.get("MUSEON_SITE_URL"):
        config.site_url = os.environ["MUSEON_SITE_URL"].rstrip("/")
    if os.environ.get("MUSEON_SUPABASE_URL") or os.environ.get("NEXT_PUBLIC_SUPABASE_URL"):
        config.supabase_url = os.environ.get("MUSEON_SUPABASE_URL") or os.environ.get(
            "NEXT_PUBLIC_SUPABASE_URL"
        )
    if os.environ.get("MUSEON_SUPABASE_ANON_KEY") or os.environ.get(
        "NEXT_PUBLIC_SUPABASE_ANON_KEY"
    ):
        config.supabase_anon_key = os.environ.get("MUSEON_SUPABASE_ANON_KEY") or os.environ.get(
            "NEXT_PUBLIC_SUPABASE_ANON_KEY"
        )
    if os.environ.get("MUSEON_AUTH_TOKEN"):
        config.auth.access_token = os.environ["MUSEON_AUTH_TOKEN"]
    if os.environ.get("MUSEON_API_KEY"):
        config.auth.api_key = os.environ["MUSEON_API_KEY"]


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
