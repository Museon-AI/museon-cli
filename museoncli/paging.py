"""One pagination contract over the page shapes different domains return.

Domains return pages as ``data.{items,total,page,page_size,has_more}``,
``data.{items,pagination}`` or ``data.data`` with a top-level ``pagination``.
``page_info`` normalizes all of them, and ``collect_all_pages`` follows them for
``--all`` without a domain-specific loop.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from copy import deepcopy
from typing import Any

MAX_ALL_PAGES = 100
MAX_ALL_ITEMS = 10_000
_LIST_KEYS = ("items", "data")


def page_info(result: dict[str, Any]) -> dict[str, Any] | None:
    """Return ``{page, page_size, total, total_pages, has_more, next_cursor}`` or None."""
    data = result.get("data")
    sources: list[dict[str, Any]] = []
    if isinstance(data, dict) and isinstance(data.get("pagination"), dict):
        sources.append(data["pagination"])
    if isinstance(result.get("pagination"), dict):
        sources.append(result["pagination"])
    if isinstance(data, dict) and any(key in data for key in ("has_more", "total", "total_pages")):
        sources.append(data)
    if not sources:
        return None
    raw: dict[str, Any] = {}
    for source in reversed(sources):  # earlier sources win
        raw.update({key: value for key, value in source.items() if value is not None})
    info: dict[str, Any] = {}
    for key, aliases in (
        ("page", ("page",)),
        ("page_size", ("page_size", "limit")),
        ("total", ("total", "total_count")),
        ("total_pages", ("total_pages",)),
        ("has_more", ("has_more",)),
        ("next_cursor", ("next_cursor", "cursor", "next_page_token")),
    ):
        for alias in aliases:
            value = raw.get(alias)
            if isinstance(value, bool) or isinstance(value, int | str):
                info[key] = value
                break
    if "has_more" not in info:
        page, size, total = info.get("page"), info.get("page_size"), info.get("total")
        if isinstance(page, int) and isinstance(info.get("total_pages"), int):
            info["has_more"] = page < info["total_pages"]
        elif isinstance(page, int) and isinstance(size, int) and isinstance(total, int):
            info["has_more"] = page * size < total
    return info or None


def _records_location(data: Any) -> tuple[dict[str, Any], str] | None:
    """Find the dict and key holding a page's records.

    Records sit at ``data.items``, ``data.data``, or one level deeper as the only
    list under ``data.data`` (campaign-monitor: ``data.data.creators``).
    """
    if not isinstance(data, dict):
        return None
    for key in _LIST_KEYS:
        if isinstance(data.get(key), list):
            return data, key
    nested = data.get("data")
    if isinstance(nested, dict):
        lists = [key for key, value in nested.items() if isinstance(value, list)]
        if len(lists) == 1:
            return nested, lists[0]
    return None


def page_items(result: dict[str, Any]) -> list[Any] | None:
    """Return the list of records on one page, wherever the domain put it."""
    data = result.get("data")
    if isinstance(data, list):
        return data
    location = _records_location(data)
    return location[0][location[1]] if location else None


def _with_page(arguments: dict[str, Any], page: int) -> dict[str, Any]:
    updated = deepcopy(arguments)
    if isinstance(updated.get("page"), dict):
        updated["page"]["page"] = page
    else:
        updated["page"] = page
    return updated


def _replace_items(result: dict[str, Any], items: list[Any]) -> dict[str, Any]:
    merged = deepcopy(result)
    data = merged.get("data")
    if isinstance(data, list):
        merged["data"] = items
        return merged
    location = _records_location(data)
    if location:
        location[0][location[1]] = items
    return merged


async def collect_all_pages(
    run_page: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]],
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Fetch every page from the requested one on and merge their records.

    Stops when the service reports no more pages, when a page comes back short or
    empty, or at the safety caps; hitting a cap is reported, never silent.
    """
    start = arguments.get("page")
    if isinstance(start, dict):
        start = start.get("page")
    page = start if isinstance(start, int) and start > 0 else 1
    first: dict[str, Any] | None = None
    items: list[Any] = []
    pages = 0
    complete = False
    while pages < MAX_ALL_PAGES and len(items) < MAX_ALL_ITEMS:
        result = await run_page(_with_page(arguments, page))
        pages += 1
        if first is None:
            first = result
        records = page_items(result)
        if records is None:
            raise RuntimeError("--all is not supported: the response has no record list")
        items.extend(records)
        info = page_info(result) or {}
        requested_size = arguments.get("page_size")
        if isinstance(arguments.get("page"), dict):
            requested_size = arguments["page"].get("page_size", requested_size)
        size = info.get("page_size") or requested_size
        if not records:
            complete = True
        elif info.get("has_more") is False:
            complete = True
        elif "has_more" not in info and isinstance(size, int) and len(records) < size:
            complete = True
        if complete:
            break
        page += 1
    assert first is not None
    merged = _replace_items(first, items[:MAX_ALL_ITEMS])
    total = (page_info(first) or {}).get("total")
    merged["page_info"] = {
        "all_pages": True,
        "pages_fetched": pages,
        "items": min(len(items), MAX_ALL_ITEMS),
        "complete": complete,
        **({"total": total} if isinstance(total, int) else {}),
    }
    if not complete:
        merged.setdefault("warnings", []).append(
            f"--all stopped at {pages} pages / {min(len(items), MAX_ALL_ITEMS)} records; "
            "narrow the filters or continue with --page."
        )
    return merged
