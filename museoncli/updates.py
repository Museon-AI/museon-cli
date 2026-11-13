"""Keep the CLI current and tell its user when it is not.

The official uv tool installation upgrades itself before any user command.
Other installations only check the latest stable release (cached) so every
command can tell the Agent, and an interactive user, how to upgrade.
"""

from __future__ import annotations

from contextlib import contextmanager
from importlib.metadata import PackageNotFoundError, distribution, version
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
from typing import Any, Iterator

import httpx

from museoncli import __version__


REPOSITORY_URL = "https://github.com/Museon-AI/museon-cli"
RELEASE_URL = "https://api.github.com/repos/Museon-AI/museon-cli/releases/latest"
DOWNLOAD_ROOT = f"{REPOSITORY_URL}/releases/download"
CHECK_INTERVAL = 15 * 60
# The human stderr line about a newer release; the JSON notice is on every command.
NOTICE_INTERVAL = 24 * 60 * 60
_REEXEC_VERSION = "_MUSEONCLI_UPDATED_TO"
_REEXEC_FROM = "_MUSEONCLI_UPDATED_FROM"

# How this copy was installed decides who upgrades it.
UV_TOOL = "uv_tool"  # official `uv tool install`: upgrades itself
PIPX = "pipx"
UV_PIP = "uv_pip"
PIP = "pip"
OTHER = "other"  # another installer; pip can still replace the package
SOURCE = "source"  # a source checkout or editable install: git owns it
MANAGED = "managed"  # a host runtime (Mel's sandbox) imports and updates it
INSTALL_METHODS = (UV_TOOL, PIPX, UV_PIP, PIP, OTHER, SOURCE, MANAGED)
_NOTICE_ONLY = frozenset({PIPX, UV_PIP, PIP, OTHER})


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


def install_method() -> str:
    """Name who owns this installation (see INSTALL_METHODS). Reads local files only."""
    prefix = Path(sys.prefix).resolve()
    if _tool_bin(prefix) is not None:
        return UV_TOOL
    try:
        dist = distribution("museoncli")
        package = Path(str(dist.locate_file("museoncli/__init__.py"))).resolve()
        if package != Path(__file__).resolve().with_name("__init__.py"):
            return SOURCE  # This code is not the installed distribution's.
        direct_url = json.loads(dist.read_text("direct_url.json") or "{}")
        if (direct_url.get("dir_info") or {}).get("editable"):
            return SOURCE
        installer = (dist.read_text("INSTALLER") or "").strip().lower()
    except (PackageNotFoundError, OSError, ValueError, TypeError, AttributeError):
        return SOURCE
    if (prefix / "pipx_metadata.json").is_file():
        return PIPX
    return {"uv": UV_PIP, "pip": PIP}.get(installer, OTHER)


def wheel_url(release: str) -> str:
    return f"{DOWNLOAD_ROOT}/v{release}/museoncli-{release}-py3-none-any.whl"


def changelog_url(release: str | None = None) -> str:
    try:
        _stable_version(release or "")
    except ValueError:
        return f"{REPOSITORY_URL}/blob/main/CHANGELOG.md"
    # GitHub anchors "## 1.0.1" as #101; the tag keeps the link stable.
    return f"{REPOSITORY_URL}/blob/v{release}/CHANGELOG.md#{release.replace('.', '')}"


def _quote(path: str) -> str:
    if sys.platform == "win32":
        return f'"{path}"' if " " in path else path
    return shlex.quote(path)


def upgrade_command(method: str, latest: str | None) -> str | None:
    """The one command that upgrades this installation, or None when nobody should run one."""
    if method == UV_TOOL:
        return "museoncli upgrade"  # It verifies and installs the release itself.
    if method not in _NOTICE_ONLY or not latest:
        return None
    url = wheel_url(latest)
    if method == PIPX:
        return f'pipx install --force "{url}"'
    python = _quote(sys.executable)
    if method == UV_PIP:
        return f'uv pip install --python {python} "{url}"'
    return f'{python} -m pip install --upgrade "{url}"'


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_json(path: Path, data: dict[str, Any]) -> bool:
    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(handle, "w") as output:
                json.dump(data, output)
            os.replace(temporary, path)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise
    except OSError:
        return False  # Bookkeeping must never fail the user's command.
    return True


def _state_dir(method: str) -> Path:
    if method == UV_TOOL:
        # Next to the uv tool's own update cache and lock.
        return Path(sys.prefix).resolve().parent
    override = os.environ.get("MUSEONCLI_CONFIG")
    return Path(override).expanduser().parent if override else Path.home() / ".museoncli"


def _notice_state_path(method: str) -> Path:
    name = ".museoncli-notices.json" if method == UV_TOOL else "update-notices.json"
    return _state_dir(method) / name


@contextmanager
def _update_lock(path: Path) -> Iterator[bool]:
    # A read-only tool directory must not turn optional maintenance into a
    # failure of the user's command. Yield False only before acquiring the lock.
    try:
        handle = path.open("a+b")
    except OSError:
        yield False
        return
    with handle:
        try:
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
                except OSError as exc:
                    if exc.errno not in {errno.EACCES, errno.EAGAIN}:
                        raise
                    if time.monotonic() >= deadline:
                        raise RuntimeError(
                            "cli_update_failed: another CLI upgrade is still running"
                        )
                    time.sleep(0.1)
        except OSError:
            yield False
            return
        try:
            yield True
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
    # A failed cache write must not undo a verified installation.
    _write_json(path, {"version": current, "checked_at": time.time()})


def _release() -> dict[str, Any]:
    with httpx.Client(timeout=2.0, follow_redirects=True) as client:
        response = client.get(RELEASE_URL, headers={"Accept": "application/vnd.github+json"})
        response.raise_for_status()
        release = response.json()
    if not isinstance(release, dict) or release.get("draft") or release.get("prerelease"):
        raise ValueError("No stable release")
    _stable_version(str(release.get("tag_name", "")).removeprefix("v"))
    return release


def _highlights(release: dict[str, Any]) -> list[str]:
    """Up to three change titles from the release notes GitHub generated."""
    body = release.get("body")
    titles = []
    for line in body.splitlines() if isinstance(body, str) else []:
        line = line.strip()
        if not line.startswith(("* ", "- ")) or "made their first contribution" in line:
            continue
        title = re.sub(r"\s+by @\S+ in https://\S+$", "", line[2:]).strip()
        if title:
            titles.append(title[:200])
        if len(titles) == 3:
            break
    return titles


def _record_upgrade(method: str, previous: str, latest: str, highlights: list[str]) -> None:
    path = _notice_state_path(method)
    state = _read_json(path)
    state["upgrade"] = {"from": previous, "to": latest, "highlights": highlights}
    _write_json(path, state)


def _install(release: dict[str, Any], latest: str, prefix: Path) -> None:
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
        # The uv-owned launchers and Python executable stay in place. Replacing
        # those running executables is forbidden on Windows; only update the
        # package inside this already-identified tool environment.
        subprocess.run(
            [
                uv,
                "pip",
                "install",
                str(verified),
                "--upgrade-package",
                "museoncli",
                "--python",
                sys.executable,
            ],
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
                "-I",
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


def _checks_disabled() -> bool:
    value = os.environ.get("MUSEONCLI_UPDATE_CHECK", "1").strip().lower()
    return value in {"0", "false", "no", "off"}


def _release_cache_path(method: str) -> Path:
    return _state_dir(method) / "update-check.json"


def _latest_release() -> str | None:
    try:
        return str(_release()["tag_name"]).removeprefix("v")
    except (httpx.HTTPError, OSError, ValueError, TypeError, KeyError):
        return None


def refresh_release_cache(method: str) -> None:
    """Run in a detached child process: record the latest stable release."""
    latest = _latest_release()
    if latest is not None:  # On failure the parent already moved the next try out.
        _write_json(
            _release_cache_path(method),
            {"version": __version__, "latest": latest, "checked_at": time.time()},
        )


def _refresh_in_background(method: str) -> None:
    # -E -P: no PYTHON* variables, no cwd on sys.path; user site-packages stay
    # importable for `pip install --user`.
    command = [
        sys.executable,
        "-E",
        "-P",
        "-c",
        "import sys; from museoncli.updates import refresh_release_cache; "
        "refresh_release_cache(sys.argv[1])",
        method,
    ]
    options: dict[str, Any] = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }
    if sys.platform == "win32":
        options["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        options["start_new_session"] = True
    try:
        subprocess.Popen(command, **options)
    except (OSError, ValueError):
        pass  # The next interval tries again.


def _check_release(method: str, *, force: bool) -> dict[str, Any]:
    """Learn the latest stable release for an installation that cannot upgrade itself.

    Ordinary commands never wait on the network: they read the cache, and when it
    is older than CHECK_INTERVAL a detached process refreshes it for later commands.
    `version` and `upgrade` ask GitHub directly.
    """
    current = __version__
    path = _release_cache_path(method)
    cached = _read_json(path)
    latest = cached.get("latest") if isinstance(cached.get("latest"), str) else None
    try:
        fresh = 0 <= time.time() - float(cached["checked_at"]) < CHECK_INTERVAL
    except (KeyError, TypeError, ValueError):
        fresh = False
    if force:
        checked = _latest_release()
        _write_json(
            path,
            {"version": current, "latest": checked or latest, "checked_at": time.time()},
        )
        if checked is None:
            return {"status": "check_failed", "install_method": method}
        latest = checked
    elif not fresh:
        # Claim this interval first so concurrent commands start one refresh, not many.
        _write_json(path, {"version": current, "latest": latest, "checked_at": time.time()})
        _refresh_in_background(method)
    try:
        newer = _stable_version(str(latest)) > _stable_version(current)
    except ValueError:
        return {"status": "not_checked", "install_method": method}
    status = "outdated" if newer else "current"
    return {"status": status, "install_method": method, "latest_version": latest}


def ensure_latest(argv: list[str]) -> dict[str, Any]:
    """Check/update once, then re-exec with untouched argv before business effects."""
    resumed = os.environ.pop(_REEXEC_VERSION, None)
    previous = os.environ.pop(_REEXEC_FROM, None)
    if resumed == __version__:
        return {
            "status": "updated",
            "install_method": UV_TOOL,
            "latest_version": resumed,
            "previous_version": previous,
        }
    command = next((item for item in argv if not item.startswith("-")), None)
    # `upgrade` is the user asking for it, so it overrides MUSEONCLI_UPDATE_CHECK=0.
    explicit = command == "upgrade"
    forced = command in {"version", "upgrade"}
    method = install_method()
    if _checks_disabled() and not explicit:
        return {"status": "disabled", "install_method": method}
    if not argv or "--help" in argv or "-h" in argv:
        return {"status": "not_checked", "install_method": method}
    if method in {SOURCE, MANAGED}:
        return {"status": "managed_externally", "install_method": method}
    if method != UV_TOOL:
        return _check_release(method, force=forced)
    prefix = Path(sys.prefix).resolve()
    cache = prefix.parent / ".museoncli-update.json"
    restart = None
    with _update_lock(prefix.parent / ".museoncli-update.lock") as locked:
        if not locked:
            print(
                "Museon CLI: update lock unavailable; using the installed version.",
                file=sys.stderr,
            )
            return {
                "status": "check_failed",
                "install_method": method,
                "reason": "update_lock_unavailable",
            }
        current = version("museoncli")
        if current != __version__:
            # Another process upgraded while this process was waiting for the lock.
            restart = current
        elif not forced and _cached_current(cache, current):
            return {"status": "cached", "install_method": method, "latest_version": current}
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
                return {"status": "check_failed", "install_method": method}
            if not newer:
                _cache_current(cache, current)
                return {"status": "current", "install_method": method, "latest_version": latest}
            _install(release, latest, prefix)
            _cache_current(cache, latest)
            _record_upgrade(UV_TOOL, current, latest, _highlights(release))
            restart = latest
    # Release the lock before starting the new interpreter; never replay a command
    # that has already run. Neither dispatch nor credential loading has happened.
    os.environ[_REEXEC_VERSION] = restart
    os.environ[_REEXEC_FROM] = __version__
    command = [sys.executable, "-I", "-c", "from museoncli.bootstrap import main; main()", *argv]
    if sys.platform == "win32":
        # Windows exec creates another process; explicitly wait and preserve its
        # exit status so agents never mistake a failed business command for success.
        raise SystemExit(subprocess.call(command))
    os.execv(sys.executable, command)
    raise RuntimeError("cli_update_failed: could not restart the upgraded CLI")


def _interactive() -> bool:
    """Human lines go to a person at a terminal, never to CI logs or an Agent's pipe."""
    if os.environ.get("CI", "").strip().lower() not in {"", "0", "false", "no"}:
        return False
    try:
        return sys.stderr.isatty()
    except (AttributeError, ValueError, OSError):
        return False


def _human_line(text: str) -> None:
    try:
        print(text, file=sys.stderr, flush=True)
    except UnicodeEncodeError:
        print(text.replace("\u2192", "->"), file=sys.stderr, flush=True)
    except (OSError, ValueError):
        pass


def release_notices(update: dict[str, Any] | None) -> dict[str, Any]:
    """This command's `_notice.update` / `_notice.updated`; prints the matching human line.

    `update` says a newer stable release exists that was not installed, on every
    command while that is true; its stderr line appears at most once a day.
    `updated` announces a completed self-upgrade once.
    """
    method = (update or {}).get("install_method")
    if method != UV_TOOL and method not in _NOTICE_ONLY:
        return {}  # Source checkouts and host runtimes are updated by their owner.
    notices: dict[str, Any] = {}
    interactive = _interactive()
    path = _notice_state_path(method)
    state = _read_json(path)
    upgrade = state.get("upgrade")
    if (
        isinstance(upgrade, dict)
        and upgrade.get("to") == __version__
        and not upgrade.get("announced")
    ):
        upgrade["announced"] = True
        if _write_json(path, state):
            previous = str(upgrade.get("from") or "")
            url = changelog_url(__version__)
            highlights = [str(item) for item in upgrade.get("highlights") or []][:3]
            notices["updated"] = {
                "from": previous,
                "to": __version__,
                "changelog_url": url,
                "highlights": highlights,
                "message": (
                    f"Museon CLI was upgraded from {previous} to {__version__}. "
                    f"Mention it to the user when relevant; changes: {url}"
                ),
            }
            if interactive:
                _human_line(f"Museon CLI upgraded {previous} \u2192 {__version__}. Changes: {url}")
    if (update or {}).get("status") == "outdated":
        latest = str(update["latest_version"])  # type: ignore[index]
        command = upgrade_command(method, latest)
        url = changelog_url(latest)
        notices["update"] = {
            "current": __version__,
            "latest": latest,
            "install_method": method,
            "upgrade_command": command,
            "changelog_url": url,
            "message": (
                f"Museon CLI {__version__} is outdated (latest {latest}). "
                f"Tell the user to run: {command}"
            ),
        }
        try:
            shown = float(state.get("update_line_at", 0))
        except (TypeError, ValueError):
            shown = 0.0
        if interactive and not 0 <= time.time() - shown < NOTICE_INTERVAL:
            state["update_line_at"] = time.time()
            if _write_json(path, state):
                _human_line(
                    f"Museon CLI {__version__} \u2192 {latest} available. "
                    f"Upgrade: {command}  Changes: {url}"
                )
    return notices


def describe(update: dict[str, Any] | None) -> dict[str, Any]:
    """The version facts `museoncli version` and `museoncli upgrade` report."""
    # A host that imports the CLI directly (no bootstrap) owns its updates.
    update = update or {"status": "managed_externally", "install_method": MANAGED}
    method = str(update.get("install_method") or MANAGED)
    status = str(update.get("status") or "managed_externally")
    latest = update.get("latest_version")
    outdated = status == "outdated"
    return {
        "current": __version__,
        "latest": latest,
        "install_method": method,
        "upgrade_command": (
            upgrade_command(method, latest) if method == UV_TOOL or outdated else None
        ),
        "changelog_url": changelog_url(latest or __version__),
        "update_status": status,
    }


_INSTALLER_NAMES = {PIPX: "pipx", UV_PIP: "uv pip", PIP: "pip", OTHER: "another installer"}


def upgrade_result(update: dict[str, Any] | None) -> dict[str, Any]:
    """Report what `museoncli upgrade` did; bootstrap already installed a uv tool release."""
    info = describe(update)
    status = info["update_status"]
    current = info["current"]
    if status == "updated":
        previous = (update or {}).get("previous_version")
        return {
            **info,
            "status": "upgraded",
            "previous_version": previous,
            "message": f"Museon CLI upgraded {previous or 'the installed version'} to {current}.",
        }
    if status == "outdated":
        installer = _INSTALLER_NAMES[info["install_method"]]
        return {
            **info,
            "status": "manual",
            "message": (
                f"This Museon CLI was installed with {installer}, so it does not replace "
                f"itself. Tell the user to run: {info['upgrade_command']}"
            ),
        }
    if status in {"current", "cached"}:
        return {
            **info,
            "status": "current",
            "message": f"Museon CLI {current} is the latest stable release.",
        }
    if status == "managed_externally":
        owner = (
            "This is a source checkout; update it with git."
            if info["install_method"] == SOURCE
            else "The host runtime installs and updates this Museon CLI."
        )
        return {**info, "status": "managed_externally", "message": owner}
    if (update or {}).get("reason") == "update_lock_unavailable":
        raise RuntimeError(
            "cli_update_failed: the uv tool directory is not writable, so Museon CLI "
            "cannot upgrade itself."
        )
    raise RuntimeError(
        "network_error: could not reach GitHub to find the latest Museon CLI release; "
        "retry later."
    )
