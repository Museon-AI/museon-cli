"""Credential persistence for Museon CLI.

The operating-system credential store is preferred. Headless environments that
do not provide one fall back to a mode-0600 file beside the non-secret config.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import warnings
from pathlib import Path
from typing import Mapping

import keyring
from keyring.errors import KeyringError, PasswordDeleteError


SERVICE_NAME = "museoncli"
SECRET_FIELDS = ("api_key",)
LEGACY_SECRET_FIELDS = ("access_token", "refresh_token")
MANAGED_SECRET_FIELDS = SECRET_FIELDS + LEGACY_SECRET_FIELDS


def load_credentials(config_file: Path) -> dict[str, str]:
    credentials = _load_file_credentials(config_file)
    if _file_has_legacy_credentials(config_file):
        _save_file_credentials(config_file, credentials)
    if _force_file_backend():
        return credentials
    try:
        for field in SECRET_FIELDS:
            value = keyring.get_password(SERVICE_NAME, _account(config_file, field))
            if value:
                credentials[field] = value
    except KeyringError:
        return credentials
    return credentials


def save_credentials(config_file: Path, values: Mapping[str, str | None]) -> str:
    normalized = {
        field: str(values.get(field) or "").strip()
        for field in SECRET_FIELDS
        if str(values.get(field) or "").strip()
    }
    if _force_file_backend():
        _save_file_credentials(config_file, normalized)
        return "protected_file"
    try:
        for field in MANAGED_SECRET_FIELDS:
            account = _account(config_file, field)
            value = normalized.get(field)
            if value:
                keyring.set_password(SERVICE_NAME, account, value)
            else:
                try:
                    keyring.delete_password(SERVICE_NAME, account)
                except PasswordDeleteError:
                    pass
        _delete_file_credentials(config_file)
        return "system_keyring"
    except KeyringError:
        warnings.warn(
            "No usable system credential store was found; Museon CLI credentials "
            "were saved in a mode-0600 local file.",
            RuntimeWarning,
            stacklevel=2,
        )
        _save_file_credentials(config_file, normalized)
        return "protected_file"


def clear_credentials(config_file: Path) -> None:
    if not _force_file_backend():
        try:
            for field in MANAGED_SECRET_FIELDS:
                try:
                    keyring.delete_password(SERVICE_NAME, _account(config_file, field))
                except PasswordDeleteError:
                    pass
        except KeyringError:
            pass
    _delete_file_credentials(config_file)


def credential_backend(config_file: Path) -> str:
    if _force_file_backend() or _credential_file(config_file).is_file():
        return "protected_file"
    try:
        backend = keyring.get_keyring()
        if float(getattr(backend, "priority", 0)) > 0:
            return "system_keyring"
    except (KeyringError, TypeError, ValueError):
        pass
    return "unavailable"


def _force_file_backend() -> bool:
    return os.environ.get("MUSEONCLI_CREDENTIAL_BACKEND", "").strip().lower() == "file"


def _account(config_file: Path, field: str) -> str:
    profile = hashlib.sha256(str(config_file.expanduser().resolve()).encode()).hexdigest()[:16]
    return f"{profile}:{field}"


def _credential_file(config_file: Path) -> Path:
    override = os.environ.get("MUSEONCLI_CREDENTIAL_FILE")
    if override:
        return Path(override).expanduser()
    return config_file.with_name("credentials.json")


def _load_file_credentials(config_file: Path) -> dict[str, str]:
    path = _credential_file(config_file)
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return {
        field: str(payload[field])
        for field in SECRET_FIELDS
        if isinstance(payload.get(field), str) and payload[field]
    }


def _file_has_legacy_credentials(config_file: Path) -> bool:
    path = _credential_file(config_file)
    if not path.is_file():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(payload, dict) and any(payload.get(field) for field in LEGACY_SECRET_FIELDS)


def _save_file_credentials(config_file: Path, values: Mapping[str, str]) -> None:
    path = _credential_file(config_file)
    if not values:
        _delete_file_credentials(config_file)
        return
    write_private_json(path, dict(values))


def write_private_json(path: Path, payload: Mapping[str, object]) -> None:
    """Atomically write a mode-0600 JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        dir=path.parent,
    )
    temporary_path = Path(temporary_name)
    try:
        try:
            os.fchmod(descriptor, 0o600)
        except OSError:
            pass
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(dict(payload), indent=2, ensure_ascii=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary_path.replace(path)
        try:
            path.chmod(0o600)
        except OSError:
            pass
    except Exception:
        try:
            os.close(descriptor)
        except OSError:
            pass
        temporary_path.unlink(missing_ok=True)
        raise


def _delete_file_credentials(config_file: Path) -> None:
    try:
        _credential_file(config_file).unlink()
    except FileNotFoundError:
        pass
