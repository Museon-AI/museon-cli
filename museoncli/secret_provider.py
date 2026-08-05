from __future__ import annotations

import base64
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol

from museoncli.credentials import credential_backend, load_credentials


AGENT_CAPABILITY_METHOD = "agent_capability"
API_KEY_METHOD = "api_key"
AGENT_SESSION_PROVIDER = "agent_session"
DEFAULT_AGENT_SECRET_REF = "museon-api"


@dataclass(frozen=True)
class CredentialLease:
    value: str | None
    auth_method: str
    provider: str
    managed_by: str
    expires_at: int | None = None
    version: str | None = None
    persistable: bool = False
    error: str | None = None

    def is_expired(self, *, now: int | None = None) -> bool:
        if self.expires_at is None:
            return False
        current_time = int(time.time()) if now is None else now
        return self.expires_at <= current_time


class SecretProvider(Protocol):
    def resolve(self) -> CredentialLease | None: ...


class AgentSessionSecretProvider:
    def __init__(self, config_file: Path, descriptor: dict[str, Any]) -> None:
        self._config_file = config_file
        self._descriptor = descriptor

    def resolve(self) -> CredentialLease:
        secret_ref = str(self._descriptor.get("secret_ref") or DEFAULT_AGENT_SECRET_REF)
        path = agent_secret_lease_path(self._config_file, secret_ref)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return self._failure("credential_missing")
        except (OSError, ValueError):
            return self._failure("credential_invalid")
        if not isinstance(payload, dict):
            return self._failure("credential_invalid")
        value = payload.get("value")
        method = str(payload.get("auth_method") or "")
        if not isinstance(value, str) or not value or method != AGENT_CAPABILITY_METHOD:
            return self._failure("credential_invalid")
        expires_at = _integer(payload.get("expires_at"))
        token_exp, token_version = capability_metadata(value)
        lease = CredentialLease(
            value=value,
            auth_method=AGENT_CAPABILITY_METHOD,
            provider=AGENT_SESSION_PROVIDER,
            managed_by="agents_host",
            expires_at=expires_at or token_exp,
            version=_optional_text(payload.get("version")) or token_version,
            persistable=False,
        )
        if lease.is_expired():
            return CredentialLease(**{**lease.__dict__, "value": None, "error": "credential_expired"})
        return lease

    def _failure(self, error: str) -> CredentialLease:
        return CredentialLease(
            value=None,
            auth_method=AGENT_CAPABILITY_METHOD,
            provider=AGENT_SESSION_PROVIDER,
            managed_by="agents_host",
            expires_at=_integer(self._descriptor.get("expires_at")),
            version=_optional_text(self._descriptor.get("version")),
            persistable=False,
            error=error,
        )


class EnvironmentAPIKeySecretProvider:
    def resolve(self) -> CredentialLease | None:
        value = os.environ.get("MUSEON_API_KEY")
        if not value:
            return None
        return CredentialLease(
            value=value,
            auth_method=API_KEY_METHOD,
            provider="environment",
            managed_by="environment",
            persistable=False,
        )


class PersistentAPIKeySecretProvider:
    def __init__(self, credentials: Mapping[str, str], provider: str) -> None:
        self._credentials = credentials
        self._provider = provider

    def resolve(self) -> CredentialLease | None:
        value = self._credentials.get("api_key")
        if not value:
            return None
        return CredentialLease(
            value=value,
            auth_method=API_KEY_METHOD,
            provider=self._provider,
            managed_by="user",
            persistable=True,
        )


class LegacyInlineSecretProvider:
    def __init__(self, auth: Mapping[str, Any]) -> None:
        self._auth = auth

    def resolve(self) -> CredentialLease | None:
        value = self._auth.get("api_key")
        if not isinstance(value, str) or not value:
            return None
        if value.startswith("mcap_"):
            expires_at, version = capability_metadata(value)
            lease = CredentialLease(
                value=value,
                auth_method=AGENT_CAPABILITY_METHOD,
                provider="legacy_inline",
                managed_by="agents_host",
                expires_at=_integer(self._auth.get("expires_at")) or expires_at,
                version=version,
                persistable=False,
            )
            if lease.is_expired():
                return CredentialLease(
                    **{**lease.__dict__, "value": None, "error": "credential_expired"}
                )
            return lease
        return CredentialLease(
            value=value,
            auth_method=API_KEY_METHOD,
            provider="legacy_inline",
            managed_by="user",
            expires_at=_integer(self._auth.get("expires_at")),
            persistable=True,
        )


def resolve_auth_credential(
    config_file: Path,
    raw: dict[str, Any],
    *,
    stored_credentials: Mapping[str, str] | None = None,
    stored_provider: str | None = None,
) -> CredentialLease | None:
    auth = raw.get("auth") if isinstance(raw.get("auth"), dict) else {}
    method = str(auth.get("method") or "")

    # A declared agent capability is an exclusive trust mode. It must never
    # degrade into a user API key from the environment, keyring, or file.
    if method == AGENT_CAPABILITY_METHOD:
        return AgentSessionSecretProvider(config_file, auth).resolve()

    inline_provider = LegacyInlineSecretProvider(auth)
    inline_lease = inline_provider.resolve()
    if inline_lease and inline_lease.auth_method == AGENT_CAPABILITY_METHOD:
        return inline_lease

    environment_lease = EnvironmentAPIKeySecretProvider().resolve()
    if environment_lease is not None:
        return environment_lease

    stored_lease = PersistentAPIKeySecretProvider(
        stored_credentials if stored_credentials is not None else load_credentials(config_file),
        stored_provider or credential_backend(config_file),
    ).resolve()
    if stored_lease is not None:
        return CredentialLease(
            **{
                **stored_lease.__dict__,
                "expires_at": _integer(auth.get("expires_at")),
            }
        )

    return inline_lease


def agent_secret_lease_path(config_file: Path, secret_ref: str = DEFAULT_AGENT_SECRET_REF) -> Path:
    safe_ref = "".join(char for char in secret_ref if char.isalnum() or char in {"-", "_"})
    if not safe_ref or safe_ref != secret_ref:
        safe_ref = DEFAULT_AGENT_SECRET_REF
    return config_file.with_name("secrets") / f"{safe_ref}.lease.json"


def capability_metadata(value: str) -> tuple[int | None, str | None]:
    if not value.startswith("mcap_"):
        return None, None
    segments = value.removeprefix("mcap_").split(".")
    if len(segments) != 3:
        return None, None
    try:
        segment = segments[1]
        padded = segment + "=" * (-len(segment) % 4)
        claims = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return None, None
    if not isinstance(claims, dict):
        return None, None
    return _integer(claims.get("exp")), _optional_text(claims.get("jti"))


def _integer(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None
