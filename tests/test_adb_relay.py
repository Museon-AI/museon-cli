"""The ADB relay keeps a cloud phone on only while ADB is actually used.

Regressions prevented: an open but idle ADB connection keeping a billed cloud
phone on forever (Museon stops phones whose lease nobody renews), and the
opposite, a phone stopped mid-task because ADB traffic did not renew its lease.
"""

from __future__ import annotations

import asyncio

from museoncli import adb_relay


async def _echo_server() -> tuple[asyncio.AbstractServer, int]:
    async def echo(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        while data := await reader.read(1024):
            writer.write(data)
            await writer.drain()
        writer.close()

    server = await asyncio.start_server(echo, "127.0.0.1", 0)
    return server, server.sockets[0].getsockname()[1]


def test_relay_forwards_adb_and_renews_only_while_traffic_flows() -> None:
    asyncio.run(_relay_forwards_adb_and_renews_only_while_traffic_flows())


async def _relay_forwards_adb_and_renews_only_while_traffic_flows() -> None:
    upstream, upstream_port = await _echo_server()
    renewals: list[float] = []
    ready: asyncio.Future[int] = asyncio.get_running_loop().create_future()

    async def renew() -> None:
        renewals.append(asyncio.get_running_loop().time())

    relay = asyncio.create_task(
        adb_relay.serve(
            target=f"127.0.0.1:{upstream_port}",
            renew=renew,
            on_ready=ready.set_result,
            renew_interval=0.05,
            idle_exit=0.4,
        )
    )
    port = await ready
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    for _ in range(3):  # ADB in use: traffic in every renewal interval
        writer.write(b"CNXN")
        await writer.drain()
        assert await reader.readexactly(4) == b"CNXN"
        await asyncio.sleep(0.06)
    in_use_renewals = len(renewals)

    await asyncio.sleep(0.2)  # connection still open, no ADB commands
    assert len(renewals) == in_use_renewals

    await asyncio.wait_for(relay, timeout=2)  # silence for a whole lease ends the relay
    assert in_use_renewals >= 2
    writer.close()
    upstream.close()


def test_a_connection_whose_phone_is_off_counts_as_no_traffic() -> None:
    asyncio.run(_a_connection_whose_phone_is_off_counts_as_no_traffic())


async def _a_connection_whose_phone_is_off_counts_as_no_traffic() -> None:
    renewals: list[str] = []
    ready: asyncio.Future[int] = asyncio.get_running_loop().create_future()

    async def renew() -> None:
        renewals.append("renewed")

    unused = await asyncio.start_server(lambda r, w: None, "127.0.0.1", 0)
    dead_port = unused.sockets[0].getsockname()[1]
    unused.close()
    await unused.wait_closed()

    relay = asyncio.create_task(
        adb_relay.serve(
            target=f"127.0.0.1:{dead_port}",
            renew=renew,
            on_ready=ready.set_result,
            renew_interval=0.05,
            idle_exit=0.3,
        )
    )
    port = await ready
    for _ in range(3):  # the ADB server keeps reconnecting to a stopped phone
        _, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(b"CNXN")
        writer.close()
        await asyncio.sleep(0.05)

    await asyncio.wait_for(relay, timeout=2)
    assert renewals == []
