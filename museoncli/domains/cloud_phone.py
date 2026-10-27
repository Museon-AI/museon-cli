"""Staff cloud-phone and IP management over the dashboard's shared operations."""

from __future__ import annotations

import asyncio
import csv
import io
import json
import os
import time
from uuid import uuid4
from dataclasses import replace
from pathlib import Path
from typing import Any

from museoncli.domains._model import CommandSpec, Domain
from museoncli.domains.hireaicreator import B, S, U, EXECUTORS, _command, arr, enum, obj
from museoncli.envelopes import direct_api_envelope
from museoncli.execution import CommandContext
from museoncli.paging import MAX_ALL_ITEMS

ROOT = "/agent-cli"
POOL = ROOT + "/proxy-pool"
FLEET = ROOT + "/cloud-phones"
RECOVERY = ROOT + "/device-recovery"
# These ids belong to the phone catalog; they are not Museon UUIDs or URL paths.
ID = {**S, "pattern": r"^[A-Za-z0-9_-]{1,100}$"}
IDS = {**arr(ID, 1, 5000), "uniqueItems": True}
PAGE = {
    "page": {"type": "integer", "minimum": 1},
    "page_size": {"type": "integer", "minimum": 1, "maximum": 5000},
}
READ = {"refresh": B}
FILTERS = {
    **READ,
    **PAGE,
    "search": S,
    "group_id": ID,
    "country": S,
    "health": enum("healthy", "suspect", "down", "unchecked", "held"),
    "sort": enum("name", "ip", "used", "last-moved", "accounts"),
    "descending": B,
}
WAIT = {"wait": B, "timeout": {"type": "number", "minimum": 1, "maximum": 1800}}
ENTRY = obj(
    {
        "server": S,
        "scheme": enum("socks5", "http", "https"),
        "port": {"type": "integer", "minimum": 1, "maximum": 65535},
        "username": {"type": "string"},
        "password": {"type": "string"},
    },
    ("server",),
)
SUPPLIER = {
    "name": S,
    "scheme": enum("socks5", "http", "https"),
    "port": {"type": "integer", "minimum": 1, "maximum": 65535},
    "username": {"type": "string"},
    "password_file": {**S, "description": "Local file containing the password; never printed."},
}


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[redacted]" if key == "password" else redact(child)
            for key, child in value.items()
        }
    if isinstance(value, list):
        return [redact(child) for child in value]
    return value


def _envelope(ctx: CommandContext, raw: Any) -> dict[str, Any]:
    return direct_api_envelope(
        ctx.spec.schema_name, ctx.workspace_id, raw, site_url=ctx.cfg.site_url
    )


async def _get(ctx: CommandContext, path: str, **params: Any) -> Any:
    return await ctx.api_data(ctx.cfg, "GET", path, params=params)


async def _views(ctx: CommandContext) -> tuple[dict, dict]:
    # Two complete shared reads, independent of the number of matching phones/IPs.
    return tuple(
        await asyncio.gather(
            _get(ctx, FLEET + "/fleet", refresh=ctx.arguments.get("refresh", False)),
            _get(ctx, POOL + "/snapshot", refresh=ctx.arguments.get("refresh", False)),
        )
    )


def _rows(fleet: dict, pool: dict) -> tuple[list[dict], list[dict]]:
    occupancy = {p["id"]: p for p in fleet["proxies"]}
    phones_by_proxy: dict[str, list[dict]] = {}
    for phone in fleet["phones"]:
        phones_by_proxy.setdefault(phone.get("proxy_id"), []).append(phone)
    proxies = []
    for proxy in pool["proxies"]:
        usage = occupancy.get(proxy["id"], {})
        used = usage.get("used", 0)
        proxies.append(
            {
                **proxy,
                "used": used,
                "available": max(0, fleet["phones_per_proxy"] - used),
                "phones": phones_by_proxy.get(proxy["id"], []),
            }
        )
    by_id = {p["id"]: p for p in proxies}
    phones = [
        {**p, "proxy": {k: v for k, v in by_id.get(p.get("proxy_id"), {}).items() if k != "phones"}}
        for p in fleet["phones"]
    ]
    return phones, proxies


def _health(proxy: dict) -> str:
    check = proxy.get("check") or {}
    return "held" if check.get("recovery_held") else check.get("health_state", "unchecked")


def _select(rows: list[dict], args: dict, *, phones: bool = False) -> list[dict]:
    selected = []
    for row in rows:
        proxy = row.get("proxy", {}) if phones else row
        check = proxy.get("check") or {}
        if args.get("search", "").casefold() not in json.dumps(row, ensure_ascii=False).casefold():
            continue
        if "group_id" in args and proxy.get("group_id") != args["group_id"]:
            continue
        if (
            "country" in args
            and (check.get("country_code") or "").upper() != args["country"].upper()
        ):
            continue
        if "health" in args and _health(proxy) != args["health"]:
            continue
        if "supplier_id" in args and proxy.get("supplier_id") != args["supplier_id"]:
            continue
        kind = args.get("filter")
        if phones and kind:
            matches = {
                "all": True,
                "no-proxy": not row["has_proxy"],
                "unmatched": row["has_proxy"] and not row.get("proxy_id"),
                "no-accounts": not row["accounts"],
                "recently-moved": row["moved_recently"],
                "down": _health(proxy) in {"down", "held"},
            }
            if not matches[kind]:
                continue
        selected.append(row)
    key = args.get("sort", "name")

    def order(row: dict) -> Any:
        proxy = row.get("proxy", {}) if phones else row
        return {
            "name": str(row.get("name") or row.get("serial_no") or row.get("id", "")),
            "ip": proxy.get("server", ""),
            "used": proxy.get("used", 0),
            "last-moved": row.get("last_moved_at") or "",
            "accounts": len(row.get("accounts", [])),
        }[key]

    return sorted(selected, key=order, reverse=args.get("descending", False))


def _page(ctx: CommandContext, rows: list, **metadata: Any) -> dict:
    page, size = ctx.arguments.get("page", 1), ctx.arguments.get("page_size", 100)
    if ctx.args is not None and getattr(ctx.args, "all", False):
        page, size = 1, MAX_ALL_ITEMS
    return _envelope(
        ctx,
        {
            "items": rows[(page - 1) * size : page * size],
            "page": page,
            "page_size": size,
            "total": len(rows),
            **metadata,
        },
    )


async def _read(ctx: CommandContext) -> dict:
    fleet, pool = await _views(ctx)
    phones, proxies = _rows(fleet, pool)
    metadata = {
        k: fleet[k]
        for k in (
            "generated_at",
            "phones_fetched_at",
            "stale",
            "writes_enabled",
            "phones_per_proxy",
        )
    }
    resource = ctx.spec.resource
    if resource == "summary":
        countries: dict[str, dict] = {}
        for proxy in proxies:
            country = (proxy.get("check") or {}).get("country_code") or "unknown"
            stats = countries.setdefault(
                country, {"proxies": 0, "healthy": 0, "down": 0, "available": 0, "phones": 0}
            )
            stats["proxies"] += 1
            stats["phones"] += proxy["used"]
            state = _health(proxy)
            stats["healthy"] += state == "healthy"
            stats["down"] += state in {"down", "held"}
            if state == "healthy":
                stats["available"] += proxy["available"]
        return _envelope(
            ctx,
            {
                **metadata,
                "phone_count": len(phones),
                "proxy_count": len(proxies),
                "countries": countries,
            },
        )
    if resource == "attention":
        rows = fleet["attention"]
        if "kind" in ctx.arguments:
            rows = [row for row in rows if row["kind"].replace("_", "-") == ctx.arguments["kind"]]
        return _page(ctx, rows, **metadata)
    rows = phones if resource == "phone" else proxies
    if ctx.spec.shortcut == "+get":
        key = "provider_device_id" if resource == "phone" else "id"
        found = next((r for r in rows if r[key] == ctx.arguments["id"]), None)
        if found is None:
            raise RuntimeError("not_found")
        return _envelope(ctx, {**metadata, "item": found})
    return _page(ctx, _select(rows, ctx.arguments, phones=resource == "phone"), **metadata)


def _private_file(path: str, content: bytes) -> str:
    destination = Path(path).expanduser().absolute()
    # Never follow a symlink or silently replace an existing credential/export file.
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(content)
    return str(destination)


async def _export_credentials(ctx: CommandContext) -> dict:
    resource = "proxies" if ctx.spec.resource == "proxy" else "suppliers"
    raw = await _get(ctx, POOL + f"/{resource}/{ctx.arguments['id']}/credentials")
    path = _private_file(ctx.arguments["output"], json.dumps(raw).encode())
    return _envelope(ctx, {"id": ctx.arguments["id"], "file": path})


async def _save_supplier(ctx: CommandContext) -> dict:
    arguments = dict(ctx.arguments)
    target = arguments.pop("id", None)
    if "password_file" in arguments:
        arguments["password"] = (
            Path(arguments.pop("password_file")).expanduser().read_text().rstrip("\r\n")
        )
    path = POOL + "/suppliers" + (f"/{target}" if target else "")
    return _envelope(
        ctx, await ctx.api_data(ctx.cfg, "PUT" if target else "POST", path, json_body=arguments)
    )


def _entries(path: str, supplier: bool) -> list[dict]:
    content = Path(path).expanduser().read_text(encoding="utf-8-sig")
    if path.lower().endswith(".json"):
        entries = json.loads(content)
    elif path.lower().endswith(".csv"):
        entries = [
            {k: int(v) if k == "port" and v else v for k, v in row.items() if v != ""}
            for row in csv.DictReader(io.StringIO(content))
        ]
    elif supplier:
        entries = [{"server": line.strip()} for line in content.splitlines() if line.strip()]
    else:
        raise ValueError(
            "Use a JSON array or CSV (server,scheme,port,username,password); with a supplier, a text file of IPs also works"
        )
    from museoncli.domains.hireaicreator import _validate

    _validate(entries, arr(ENTRY, 1, 5000), "entries")
    return entries


async def _add(ctx: CommandContext) -> dict:
    arguments = dict(ctx.arguments)
    if "entries_file" in arguments:
        arguments["entries"] = _entries(
            arguments.pop("entries_file"), bool(arguments.get("supplier_id"))
        )
    raw = await ctx.api_data(ctx.cfg, "POST", POOL + "/proxies", json_body=arguments)
    return _envelope(ctx, raw)


async def _assign(ctx: CommandContext) -> dict:
    items = [
        {
            "provider_device_id": item["phone_id"],
            "proxy_id": item["proxy_id"],
            "reason": item.get("reason", "manual"),
        }
        for item in ctx.arguments["items"]
    ]
    return _envelope(
        ctx,
        await ctx.api_data(ctx.cfg, "POST", FLEET + "/proxy-changes", json_body={"items": items}),
    )


async def _check(ctx: CommandContext) -> dict:
    ids = ctx.arguments["proxy_ids"]
    baseline = None
    if ctx.arguments.get("wait"):
        baseline = {
            p["id"]: (p.get("check") or {}).get("checked_at")
            for p in (await _get(ctx, POOL + "/snapshot"))["proxies"]
        }
    receipt = await ctx.api_data(ctx.cfg, "POST", POOL + "/checks", json_body={"proxy_ids": ids})
    if baseline is None:
        return _envelope(ctx, {**receipt, "status": "accepted"})
    deadline = time.monotonic() + ctx.arguments.get("timeout", 300)
    while True:
        snapshot = await _get(ctx, POOL + "/snapshot")
        rows = [p for p in snapshot["proxies"] if p["id"] in ids]
        pending = [
            pid
            for pid in ids
            if not any(
                p["id"] == pid
                and (p.get("check") or {}).get("checked_at")
                and p["check"]["checked_at"] != baseline.get(pid)
                for p in rows
            )
        ]
        if not pending or time.monotonic() >= deadline:
            result = _envelope(
                ctx,
                {
                    **receipt,
                    "status": "completed" if not pending else "pending",
                    "pending_ids": pending,
                    "items": rows,
                },
            )
            if pending:
                result["warnings"].append(
                    "Wait timed out; accepted checks continue. Query these IPs again; do not resubmit just to wait."
                )
            return result
        await asyncio.sleep(min(3, max(0, deadline - time.monotonic())))


async def _recover(ctx: CommandContext) -> dict:
    body = dict(ctx.arguments)
    job_id = body.pop("id", None)
    path = RECOVERY + (f"/jobs/{job_id}/retry" if job_id else "/jobs")
    if not job_id:
        body["workspace_id"] = body.get("workspace_id") or ctx.workspace_id
        if not body["workspace_id"]:
            raise RuntimeError("missing_workspace")
    # Recovery owns body-level idempotency. Do not move this key to the generic
    # HTTP header: an uncertain response must replay the same job, not create another.
    return _envelope(ctx, await ctx.api_data(ctx.cfg, "POST", path, json_body=body))


async def _recovery_list(ctx: CommandContext) -> dict:
    page, size = ctx.arguments.get("page", 1), ctx.arguments.get("page_size", 20)
    rows = await _get(ctx, RECOVERY + "/jobs", limit=size, offset=(page - 1) * size)
    return _envelope(
        ctx, {"items": rows, "page": page, "page_size": size, "has_more": len(rows) == size}
    )


async def _export_history(ctx: CommandContext) -> dict:
    if ctx.download_api_file is None:
        raise RuntimeError("File downloads are unavailable")
    destination = Path(ctx.arguments["output"]).expanduser().absolute()
    temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.part")
    if destination.exists():
        raise FileExistsError("output already exists")
    try:
        await ctx.download_api_file(
            ctx.cfg,
            RECOVERY + "/jobs/export",
            params={},
            destination=temporary,
            max_bytes=50 * 1024 * 1024,
            allowed_content_types={"text/csv"},
        )
        # Linking is exclusive and atomic even if another process creates the target.
        os.link(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return _envelope(ctx, {"file": str(destination)})


def _spec(
    resource: str,
    action: str,
    method: str,
    path: str,
    properties: dict,
    *,
    executor=None,
    workspace=False,
    **kwargs,
) -> CommandSpec:
    base = _command(
        resource,
        action,
        method,
        path,
        properties,
        version=1,
        workspace="body" if workspace else "resource",
        domain=Domain.CLOUD_PHONE,
        **kwargs,
    )
    if workspace:
        original_build = base.build_arguments

        def build(args):
            payload = original_build(args)
            payload.setdefault("scope", "global")
            return payload

        base = replace(base, build_arguments=build)
    original = executor or EXECUTORS[base.schema_name]

    async def execute(ctx):
        result = await original(ctx)
        data = result.get("data")
        if isinstance(data, dict):
            outcomes = data.get("results", data.get("outcomes", []))
            failed = [
                row
                for row in outcomes
                if row.get("ok") is False
                or row.get("status") in {"invalid", "failed"}
                or row.get("result") in {"failed", "skipped"}
            ]
            if failed:
                data["status"] = "partial" if len(failed) < len(outcomes) else "failed"
                result["warnings"].append(
                    f"{len(failed)} of {len(outcomes)} items did not succeed; inspect each outcome before continuing."
                )
        return result

    EXECUTORS[base.schema_name] = execute
    return replace(
        base,
        required_roles=("staff",),
        workspace_bound=workspace,
        resource_policy="staff_global_cloud_phone_management",
    )


def specs() -> list[CommandSpec]:
    specs = [
        _spec(
            "fleet",
            "get",
            "GET",
            FLEET + "/fleet",
            {**READ, "last_known": B},
            summary="Read the complete phone fleet, IP occupancy and attention queue; timestamps and stale indicate freshness.",
        ),
        _spec(
            "summary",
            "get",
            "GET",
            FLEET + "/fleet",
            READ,
            executor=_read,
            summary="Summarize cloud phones, IP health and available slots by country.",
        ),
        _spec(
            "phone",
            "list",
            "GET",
            FLEET + "/fleet",
            {
                **FILTERS,
                "filter": enum(
                    "all", "down", "no-proxy", "unmatched", "no-accounts", "recently-moved"
                ),
            },
            executor=_read,
            summary="Find phones by name, account or IP, including current connection, exit IP, health, occupancy and last change.",
        ),
        _spec(
            "phone",
            "get",
            "GET",
            FLEET + "/fleet",
            {**READ, "id": ID},
            required=("id",),
            executor=_read,
            summary="Get one phone and its current IP details by its catalog ID.",
        ),
        _spec(
            "phone",
            "set-proxy",
            "POST",
            FLEET + "/proxy-changes",
            {
                "items": arr(
                    obj(
                        {
                            "phone_id": ID,
                            "proxy_id": ID,
                            "reason": enum("manual", "down", "overloaded"),
                        },
                        ("phone_id", "proxy_id"),
                    ),
                    1,
                    10,
                ),
                "id": ID,
                "proxy_id": ID,
                "reason": enum("manual", "down", "overloaded"),
            },
            executor=_assign,
            write=True,
            requires_confirmation=True,
            summary="Assign explicit target IPs to up to 10 phones; each IP holds at most 5 phones. Read-back verifies each change. No automatic target selection or country restriction.",
            readback="Read phone +get for each changed phone; inspect every failed or skipped outcome.",
        ),
        _spec(
            "proxy",
            "list",
            "GET",
            POOL + "/snapshot",
            {**FILTERS, "supplier_id": U},
            executor=_read,
            summary="List IPs with groups, suppliers, health, exit IP, bound phones and available slots.",
        ),
        _spec(
            "proxy",
            "get",
            "GET",
            POOL + "/snapshot",
            {**READ, "id": ID},
            required=("id",),
            executor=_read,
            summary="Get one IP and all its bound phones without per-phone lookups.",
        ),
        _spec(
            "proxy",
            "add",
            "POST",
            POOL + "/proxies",
            {
                "entries": arr(ENTRY, 1, 5000),
                "entries_file": S,
                "group_id": ID,
                "supplier_id": U,
                "query_channel": {**enum("IP2Location", "IP-API"), "x-preserve-wire-value": True},
            },
            executor=_add,
            write=True,
            summary="Add up to 5000 IPs from entries or a JSON/CSV file; a supplier preset also accepts a text file of IPs. New IPs are checked in the background. Each row reports added, exists, invalid or failed.",
            readback="Read proxy +get or +list to verify new IPs and their checks.",
        ),
        _spec(
            "proxy",
            "check",
            "POST",
            POOL + "/checks",
            {"proxy_ids": IDS, **WAIT},
            required=("proxy_ids",),
            flags={"proxy_ids": "--id"},
            executor=_check,
            write=True,
            summary="Check selected IPs; --wait waits for a newer check for every selected IP. Accepted does not mean healthy; inspect each result.",
            readback="Read proxy +get for health and detection time.",
        ),
        _spec(
            "proxy",
            "move",
            "POST",
            POOL + "/proxies/move",
            {"proxy_ids": IDS, "group_id": ID},
            required=("proxy_ids", "group_id"),
            flags={"proxy_ids": "--id"},
            write=True,
            summary="Move selected IPs into one group; returns a result per IP.",
            readback="Read proxy +list --group-id to verify membership.",
        ),
        _spec(
            "proxy",
            "delete",
            "POST",
            POOL + "/proxies/delete",
            {"proxy_ids": IDS},
            required=("proxy_ids",),
            flags={"proxy_ids": "--id"},
            write=True,
            destructive=True,
            summary="Delete selected unused IPs; IPs used by phones are refused. Inspect every result.",
            readback="Read proxy +list and verify successful deletions are absent.",
        ),
        _spec(
            "group",
            "list",
            "GET",
            POOL + "/snapshot",
            READ,
            summary="List all IP groups, including empty groups.",
        ),
        _spec(
            "group",
            "create",
            "POST",
            POOL + "/groups",
            {"name": S},
            required=("name",),
            write=True,
            summary="Create an IP group.",
            readback="Read group +list.",
        ),
        _spec(
            "group",
            "delete",
            "POST",
            POOL + "/groups/delete",
            {"group_ids": arr(ID, 1, 100)},
            required=("group_ids",),
            flags={"group_ids": "--id"},
            write=True,
            destructive=True,
            summary="Delete empty IP groups; occupied groups and the ungrouped category are refused.",
            readback="Read group +list.",
        ),
        _spec(
            "supplier",
            "list",
            "GET",
            POOL + "/suppliers",
            {},
            summary="List saved IP supplier connection presets without passwords.",
        ),
        _spec(
            "supplier",
            "create",
            "POST",
            POOL + "/suppliers",
            SUPPLIER,
            required=("name",),
            write=True,
            executor=_save_supplier,
            summary="Create an IP supplier preset; read its password from --password-file.",
            readback="Read supplier +list.",
        ),
        _spec(
            "supplier",
            "update",
            "PUT",
            POOL + "/suppliers/{id}",
            {**SUPPLIER, "id": U},
            required=("name",),
            write=True,
            executor=_save_supplier,
            summary="Update an IP supplier preset; omitted password keeps its existing value.",
            readback="Read supplier +list.",
        ),
        _spec(
            "supplier",
            "delete",
            "DELETE",
            POOL + "/suppliers/{id}",
            {"id": U},
            write=True,
            destructive=True,
            summary="Delete a saved IP supplier preset.",
            readback="Read supplier +list.",
        ),
        _spec(
            "attention",
            "list",
            "GET",
            FLEET + "/fleet",
            {
                **PAGE,
                **READ,
                "kind": enum(
                    "down", "held", "overloaded", "change-failed", "reclaimable", "returnable"
                ),
            },
            executor=_read,
            summary="List down, repeatedly failing or overloaded IPs, failed changes, reclaimable phones and unused IPs.",
        ),
        _spec(
            "recovery",
            "preview",
            "POST",
            RECOVERY + "/inspect",
            {
                "account_ids": arr(U, 1, 100),
                "scope": {**enum("workspace", "global"), "default": "global"},
            },
            required=("account_ids",),
            workspace=True,
            summary="Live inspection before reclaiming disabled accounts' devices. Defaults to the global staff cloud-phone queue; --scope workspace narrows it. Returns blockers and Museon device IDs; no resources are released.",
        ),
        _spec(
            "recovery-job",
            "create",
            "POST",
            RECOVERY + "/jobs",
            {
                "account_ids": arr(U, 1, 100),
                "device_ids": arr(U, 1, 100),
                "scope": {**enum("workspace", "global"), "default": "global"},
                "idempotency_key": {**S, "maxLength": 128},
            },
            required=("account_ids", "device_ids", "idempotency_key"),
            workspace=True,
            executor=_recover,
            write=True,
            destructive=True,
            summary="Reclaim explicitly selected devices from a fresh recovery preview. Retry uncertain submission with the same key; accepted is not completed.",
            readback="Read recovery-job +get until terminal and inspect each item.",
        ),
        _spec(
            "recovery-job",
            "list",
            "GET",
            RECOVERY + "/jobs",
            {"page": PAGE["page"], "page_size": {"type": "integer", "minimum": 1, "maximum": 50}},
            executor=_recovery_list,
            summary="List resource-recovery jobs, including failed and partial outcomes.",
        ),
        _spec(
            "recovery-job",
            "get",
            "GET",
            RECOVERY + "/jobs/{id}",
            {"id": U},
            summary="Get a recovery job and every device's outcome and blockers.",
        ),
        _spec(
            "recovery-job",
            "retry",
            "POST",
            RECOVERY + "/jobs/{id}/retry",
            {"id": U, "idempotency_key": {**S, "maxLength": 128}},
            required=("idempotency_key",),
            executor=_recover,
            write=True,
            destructive=True,
            summary="Retry eligible unfinished recovery items using a stable dispatch key.",
            readback="Read recovery-job +get and inspect every result.",
        ),
        _spec(
            "recovery-job",
            "export",
            "GET",
            RECOVERY + "/jobs/export",
            {"output": S},
            required=("output",),
            executor=_export_history,
            summary="Export recovery history to a new local CSV file; refuses to overwrite an existing file.",
        ),
    ]
    for resource in ("proxy", "supplier"):
        specs.append(
            _spec(
                resource,
                "export-credentials",
                "GET",
                POOL + "/snapshot",
                {"id": ID if resource == "proxy" else U, "output": S},
                required=("id", "output"),
                executor=_export_credentials,
                requires_confirmation=True,
                summary="Save one connection's credentials to a new mode-0600 local JSON file; never print the password or overwrite an existing file.",
            )
        )
    change_spec = next(s for s in specs if s.schema_name == "cloud-phone.phone-set-proxy")
    build_change = change_spec.build_arguments

    def change_input(args):
        payload = build_change(args)
        if "items" in payload:
            if set(payload) != {"items"}:
                raise ValueError("Use items or single --id and --proxy-id, not both")
        elif "id" in payload and "proxy_id" in payload:
            payload = {
                "items": [
                    {
                        "phone_id": payload["id"],
                        "proxy_id": payload["proxy_id"],
                        "reason": payload.get("reason", "manual"),
                    }
                ]
            }
        else:
            raise ValueError("Supply items or both --id and --proxy-id")
        return payload

    specs[specs.index(change_spec)] = replace(
        change_spec,
        build_arguments=change_input,
        examples=[
            "museoncli cloud-phone phone +set-proxy --id 123456789 --proxy-id 987654321 --dry-run"
        ],
    )
    # A group list needs only the catalog, not the entire fleet or credentials.
    group_spec = next(s for s in specs if s.schema_name == "cloud-phone.group-list")

    async def groups(ctx):
        snapshot = await _get(ctx, POOL + "/snapshot", refresh=ctx.arguments.get("refresh", False))
        return _envelope(
            ctx,
            {
                "items": snapshot["groups"],
                "generated_at": snapshot["generated_at"],
                "writes_enabled": snapshot["writes_enabled"],
            },
        )

    EXECUTORS[group_spec.schema_name] = groups
    add_spec = next(s for s in specs if s.schema_name == "cloud-phone.proxy-add")
    build_add = add_spec.build_arguments

    def build(args):
        payload = build_add(args)
        if ("entries" in payload) == ("entries_file" in payload):
            raise ValueError("Supply exactly one of entries or --entries-file")
        if "entries_file" in payload:
            payload["entries"] = _entries(
                payload.pop("entries_file"), bool(payload.get("supplier_id"))
            )
        return payload

    specs[specs.index(add_spec)] = replace(
        add_spec,
        build_arguments=build,
        examples=["museoncli cloud-phone proxy +add --entries-file ips.csv --group-id 0 --dry-run"],
    )
    return specs
