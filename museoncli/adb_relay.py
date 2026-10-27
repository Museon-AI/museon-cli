"""Local ADB relay that keeps a Museon cloud phone on only while ADB is in use.

Museon stops a started cloud phone once nobody renews its lease. ``+connect-adb``
therefore routes ADB through this relay instead of connecting to the phone
directly: the relay forwards bytes unchanged, renews the lease at most once a
minute while ADB traffic flows, and exits after a lease's worth of silence. An
idle ADB connection sends no traffic, so an open terminal that no longer runs
commands does not keep the phone on.

One relay serves one account. A later ``+connect-adb`` for the same account and
phone reuses it; a relay whose phone moved is replaced.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os
import selectors
import shutil
import signal
import socket
import subprocess
import sys
import time
from collections.abc import Awaitable, Callable
from pathlib import Path

#: Renew at most this often, and only after ADB traffic since the last renewal.
RENEW_INTERVAL_SECONDS = 60
#: One renewal keeps the phone on this long; the relay exits after as much silence.
IDLE_EXIT_SECONDS = 15 * 60
RENEW_TIMEOUT_SECONDS = 60
_READY_TIMEOUT_SECONDS = 10
_LOCALHOST = "127.0.0.1"


def registry_dir() -> Path:
    return Path.home() / ".museoncli" / "adb-relays"


def _registry_path(account_id: str) -> Path:
    return registry_dir() / f"{account_id}.json"


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _accepting(port: int) -> bool:
    with contextlib.suppress(OSError), socket.create_connection((_LOCALHOST, port), timeout=1):
        return True
    return False


def _cli_command() -> list[str]:
    for name in ("museoncli", "museon"):
        if path := shutil.which(name):
            return [path]
    return [sys.executable, "-m", "museoncli.main"]


def ensure_relay(
    *, target: str, account_id: str, workspace_id: str | None
) -> tuple[str, str | None]:
    """Return the local ADB serial for ``target`` and a stale local serial to drop.

    The stale serial belongs to a previous relay for this account that is gone
    or points at another phone; the caller disconnects it so the ADB server
    stops reconnecting to a port another relay may reuse.
    """
    path = _registry_path(account_id)
    stale: str | None = None
    with contextlib.suppress(OSError, ValueError, TypeError, KeyError):
        entry = json.loads(path.read_text(encoding="utf-8"))
        pid, port = int(entry["pid"]), int(entry["port"])
        if entry.get("target") == target and _alive(pid) and _accepting(port):
            return f"{_LOCALHOST}:{port}", None
        stale = f"{_LOCALHOST}:{port}"
        if _alive(pid):
            with contextlib.suppress(OSError):
                os.kill(pid, signal.SIGTERM)

    command = [
        sys.executable,
        "-m",
        "museoncli.adb_relay",
        "--target",
        target,
        "--account-id",
        account_id,
        *(["--workspace-id", workspace_id] if workspace_id else []),
        "--cli",
        json.dumps(_cli_command()),
    ]
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(p for p in sys.path if p)}
    process = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        env=env,
        start_new_session=True,
        close_fds=True,
    )
    port = _read_ready_port(process)
    if port is None:
        with contextlib.suppress(OSError):
            process.kill()
        raise RuntimeError("adb_relay_failed")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"pid": process.pid, "port": port, "target": target}), encoding="utf-8"
    )
    return f"{_LOCALHOST}:{port}", stale


def _read_ready_port(process: subprocess.Popen[bytes]) -> int | None:
    assert process.stdout is not None
    with selectors.DefaultSelector() as selector:
        selector.register(process.stdout, selectors.EVENT_READ)
        if not selector.select(timeout=_READY_TIMEOUT_SECONDS):
            return None
        line = process.stdout.readline().decode("utf-8", errors="replace").strip()
    process.stdout.close()
    return int(line) if line.isdigit() else None


async def serve(
    *,
    target: str,
    renew: Callable[[], Awaitable[None]],
    on_ready: Callable[[int], None],
    renew_interval: float = RENEW_INTERVAL_SECONDS,
    idle_exit: float = IDLE_EXIT_SECONDS,
) -> None:
    """Forward 127.0.0.1:<port> to ``target`` until ADB has been silent for ``idle_exit``."""
    host, _, raw_port = target.rpartition(":")
    upstream_port = int(raw_port)
    last_traffic = time.monotonic()
    connections: set[asyncio.StreamWriter] = set()

    async def pump(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        nonlocal last_traffic
        try:
            while data := await reader.read(65536):
                last_traffic = time.monotonic()
                writer.write(data)
                await writer.drain()
        except (OSError, asyncio.IncompleteReadError):
            pass
        finally:
            writer.close()

    async def handle(client_reader: asyncio.StreamReader, client_writer: asyncio.StreamWriter):
        try:
            upstream_reader, upstream_writer = await asyncio.open_connection(host, upstream_port)
        except OSError:
            client_writer.close()
            return
        connections.update((client_writer, upstream_writer))
        try:
            await asyncio.gather(
                pump(client_reader, upstream_writer), pump(upstream_reader, client_writer)
            )
        finally:
            connections.difference_update((client_writer, upstream_writer))

    server = await asyncio.start_server(handle, _LOCALHOST, 0)
    on_ready(server.sockets[0].getsockname()[1])
    # The hand-out that started this relay already gave the phone a lease.
    renewed_at = time.monotonic()
    try:
        while True:
            await asyncio.sleep(renew_interval)
            if time.monotonic() - last_traffic >= idle_exit:
                return
            if last_traffic > renewed_at:
                renewed_at = time.monotonic()
                # A failed renewal is left to the next interval; the lease outlasts many.
                with contextlib.suppress(Exception):
                    await renew()
    finally:
        server.close()
        for writer in list(connections):
            writer.close()


def _renewer(cli: list[str], account_id: str, workspace_id: str | None):
    command = [
        *cli,
        "social-account",
        "+renew-phone-lease",
        "--id",
        account_id,
        *(["--workspace-id", workspace_id] if workspace_id else []),
    ]

    async def renew() -> None:
        # A fresh CLI process picks up rotated credentials the relay never holds.
        process = await asyncio.create_subprocess_exec(
            *command, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL
        )
        try:
            await asyncio.wait_for(process.wait(), timeout=RENEW_TIMEOUT_SECONDS)
        except TimeoutError:
            process.kill()
            await process.wait()

    return renew


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="museoncli.adb_relay")
    parser.add_argument("--target", required=True)
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--workspace-id")
    parser.add_argument("--cli", required=True, help="JSON argv that runs museoncli.")
    args = parser.parse_args(argv)

    def ready(port: int) -> None:
        sys.stdout.write(f"{port}\n")
        sys.stdout.flush()
        # The parent reads one line and closes its end; nothing else is written.
        with contextlib.suppress(OSError):
            os.close(sys.stdout.fileno())

    asyncio.run(
        serve(
            target=args.target,
            renew=_renewer(json.loads(args.cli), args.account_id, args.workspace_id),
            on_ready=ready,
        )
    )
    with contextlib.suppress(OSError):
        path = _registry_path(args.account_id)
        if json.loads(path.read_text(encoding="utf-8")).get("pid") == os.getpid():
            path.unlink()


if __name__ == "__main__":
    main()
