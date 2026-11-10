"""Update the official uv tool installation before executing any user command."""

from __future__ import annotations

from contextlib import contextmanager
from importlib.metadata import version
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
from typing import Any, Iterator

import httpx

from museoncli import __version__


RELEASE_URL = "https://api.github.com/repos/Museon-AI/museon-cli/releases/latest"
DOWNLOAD_ROOT = "https://github.com/Museon-AI/museon-cli/releases/download"
CHECK_INTERVAL = 15 * 60
_REEXEC_VERSION = "_MUSEONCLI_UPDATED_TO"


def _stable_version(value: str) -> tuple[int, ...]:
    if not re.fullmatch(r"\d+\.\d+\.\d+", value):
        raise ValueError("Not a stable CLI version")
    return tuple(int(part) for part in value.split("."))


def _tool_bin(prefix: Path) -> Path | None:
    # Source checkouts and host-managed runtime packages have their own owner.
    if not Path(__file__).resolve().is_relative_to(prefix):
        return None
    try:
        receipt = tomllib.loads((prefix / "uv-receipt.toml").read_text())
        entries = receipt["tool"]["entrypoints"]
        paths = {
            Path(entry["install-path"]).parent
            for entry in entries
            if entry.get("from") == "museoncli"
        }
        return paths.pop() if len(paths) == 1 else None
    except (OSError, ValueError, KeyError, TypeError):
        return None


@contextmanager
def _update_lock(path: Path) -> Iterator[None]:
    # The lock lives outside the environment uv replaces. OS locks release on crash.
    with path.open("a+b") as handle:
        if os.fstat(handle.fileno()).st_size == 0:
            handle.write(b"\0")
            handle.flush()
        deadline = time.monotonic() + 180
        while True:
            try:
                if sys.platform == "win32":
                    import msvcrt

                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise RuntimeError("cli_update_failed: another CLI upgrade is still running")
                time.sleep(0.1)
        try:
            yield
        finally:
            if sys.platform == "win32":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


def _cached_current(path: Path, current: str) -> bool:
    try:
        data = json.loads(path.read_text())
        return data["version"] == current and 0 <= time.time() - data["checked_at"] < CHECK_INTERVAL
    except (OSError, ValueError, KeyError, TypeError):
        return False


def _cache_current(path: Path, current: str) -> None:
    try:
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps({"version": current, "checked_at": time.time()}))
        temporary.replace(path)
    except OSError:
        pass  # A failed cache write must not undo a verified installation.


def _release() -> dict[str, Any]:
    with httpx.Client(timeout=2.0, follow_redirects=True) as client:
        response = client.get(RELEASE_URL, headers={"Accept": "application/vnd.github+json"})
        response.raise_for_status()
        release = response.json()
    if not isinstance(release, dict) or release.get("draft") or release.get("prerelease"):
        raise ValueError("No stable release")
    _stable_version(str(release.get("tag_name", "")).removeprefix("v"))
    return release


def _install(release: dict[str, Any], latest: str, prefix: Path, bin_dir: Path) -> None:
    wheel = f"museoncli-{latest}-py3-none-any.whl"
    url = f"{DOWNLOAD_ROOT}/v{latest}/{wheel}"
    asset: dict[str, Any] = next(
        (a for a in release.get("assets", []) if a.get("name") == wheel), {}
    )
    digest = asset.get("digest", "")
    if asset.get("browser_download_url") != url or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise RuntimeError("cli_update_failed: official release wheel or SHA-256 is missing")
    uv = shutil.which("uv")
    if not uv:
        raise RuntimeError("cli_update_failed: uv is required to upgrade this installation")
    env = {**os.environ, "UV_TOOL_DIR": str(prefix.parent), "UV_TOOL_BIN_DIR": str(bin_dir)}
    print(f"Museon CLI: upgrading {__version__} -> {latest}...", file=sys.stderr)
    try:
        # uv tool install does not enforce URL hash fragments. Verify the exact
        # bytes ourselves, then install that file (not a second network fetch).
        cache_dir = prefix.parent / ".museoncli-wheels"
        cache_dir.mkdir(mode=0o700, exist_ok=True)
        verified = cache_dir / wheel
        with tempfile.TemporaryDirectory(prefix=".museoncli-download-", dir=prefix.parent) as tmp:
            downloaded = Path(tmp) / wheel
            checksum = hashlib.sha256()
            size = 0
            with httpx.Client(timeout=30, follow_redirects=True) as client:
                with client.stream("GET", url) as response, downloaded.open("wb") as output:
                    response.raise_for_status()
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > 50 * 1024 * 1024:
                            raise RuntimeError(
                                "cli_update_failed: release wheel exceeds size limit"
                            )
                        checksum.update(chunk)
                        output.write(chunk)
            if checksum.hexdigest() != digest[7:]:
                raise RuntimeError("cli_update_failed: release wheel SHA-256 did not match")
            downloaded.replace(verified)
        subprocess.run(
            [
                uv,
                "tool",
                "install",
                str(verified),
                "--force",
                "--python",
                str(Path(getattr(sys, "_base_executable", None) or sys.executable).resolve()),
            ],
            env=env,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
        installed = subprocess.run(
            [
                sys.executable,
                "-c",
                "from importlib.metadata import version; print(version('museoncli'))",
            ],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        ).stdout.strip()
        if installed != latest:
            raise RuntimeError("cli_update_failed: installed version did not match the release")
        for previous in cache_dir.glob("museoncli-*-py3-none-any.whl"):
            if previous != verified:
                try:
                    previous.unlink()
                except OSError:
                    pass
    except (OSError, subprocess.SubprocessError, httpx.HTTPError) as exc:
        # Installer diagnostics may include proxy credentials; do not echo them.
        raise RuntimeError(
            "cli_update_failed: upgrade failed; the requested command was not executed. "
            f'Retry, or run uv tool install "{url}" --force.'
        ) from exc


def ensure_latest(argv: list[str]) -> dict[str, Any]:
    """Check/update once, then re-exec with untouched argv before business effects."""
    resumed = os.environ.pop(_REEXEC_VERSION, None)
    if resumed == __version__:
        return {"status": "updated", "latest_version": resumed}
    if os.environ.get("MUSEONCLI_UPDATE_CHECK", "1").strip().lower() in {"0", "false", "no", "off"}:
        return {"status": "disabled"}
    if not argv or "--help" in argv or "-h" in argv:
        return {"status": "not_checked"}
    prefix = Path(sys.prefix).resolve()
    bin_dir = _tool_bin(prefix)
    if bin_dir is None:
        return {"status": "managed_externally"}
    cache = prefix.parent / ".museoncli-update.json"
    restart = None
    with _update_lock(prefix.parent / ".museoncli-update.lock"):
        current = version("museoncli")
        if current != __version__:
            # Another process upgraded while this process was waiting for the lock.
            restart = current
        elif "version" not in argv and _cached_current(cache, current):
            return {"status": "cached", "latest_version": current}
        else:
            try:
                release = _release()
                latest = str(release["tag_name"]).removeprefix("v")
                newer = _stable_version(latest) > _stable_version(current)
            except (httpx.HTTPError, ValueError, TypeError, KeyError):
                print(
                    "Museon CLI: could not check for updates; using the installed version.",
                    file=sys.stderr,
                )
                return {"status": "check_failed"}
            if not newer:
                _cache_current(cache, current)
                return {"status": "current", "latest_version": latest}
            _install(release, latest, prefix, bin_dir)
            _cache_current(cache, latest)
            restart = latest
    # Release the lock before starting the new interpreter; never replay a command
    # that has already run. Neither dispatch nor credential loading has happened.
    os.environ[_REEXEC_VERSION] = restart
    os.execv(
        sys.executable, [sys.executable, "-c", "from museoncli.main import main; main()", *argv]
    )
    raise RuntimeError("cli_update_failed: could not restart the upgraded CLI")
