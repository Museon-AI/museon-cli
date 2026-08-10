#!/usr/bin/env python3
"""Build a bounded Feishu Card 2.0 payload from ranked Hook results."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

CARD_SCHEMA_VERSION = "social-hook-lark-card.v1"
MEDIA_SCHEMA_VERSION = "social-hook-lark-media.v1"
RANKING_SCHEMA_VERSION = "hook-score.v2"
DEFAULT_MIN_SCORE = 75
DEFAULT_MAX_ITEMS = 4


def _object(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any, fallback: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return fallback


def _creator(item: dict[str, Any]) -> str:
    for key in ("creator_username", "username", "creator_name"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return f"@{value.strip().lstrip('@')}"
    source = _object(item.get("source"))
    for key in ("creator_username", "username", "creator_name"):
        value = source.get(key)
        if isinstance(value, str) and value.strip():
            return f"@{value.strip().lstrip('@')}"
    return "创作者待确认"


def _recommended_items(payload: Any, min_score: int, max_items: int) -> list[dict[str, Any]]:
    root = _object(payload)
    if root.get("strategy_version") != RANKING_SCHEMA_VERSION:
        raise ValueError(f"Unsupported ranking strategy version: {root.get('strategy_version')!r}")
    items = root.get("items")
    if not isinstance(items, list):
        raise ValueError("ranked Hook payload requires an items array")
    selected = [
        item
        for item in items
        if isinstance(item, dict)
        and item.get("decision") == "recommended"
        and isinstance(item.get("score"), int)
        and item["score"] >= min_score
        and isinstance(item.get("permalink"), str)
        and item["permalink"].startswith("https://www.instagram.com/")
    ]
    selected.sort(key=lambda item: -int(item["score"]))
    return selected[:max_items]


def _summary_block(batch_id: str, selected: list[dict[str, Any]], total: int) -> dict[str, Any]:
    best = max(int(item["score"]) for item in selected)
    return {
        "tag": "column_set",
        "flex_mode": "trisect",
        "horizontal_spacing": "8px",
        "margin": "0px 0px 12px 0px",
        "columns": [
            {
                "tag": "column",
                "background_style": "blue-50",
                "padding": "12px",
                "vertical_spacing": "2px",
                "elements": [
                    {"tag": "markdown", "content": f"## <font color='blue'>{len(selected)}</font>", "text_align": "center"},
                    {"tag": "markdown", "content": "<font color='grey'>高分 Hook</font>", "text_align": "center", "text_size": "notation"},
                ],
            },
            {
                "tag": "column",
                "background_style": "blue-50",
                "padding": "12px",
                "vertical_spacing": "2px",
                "elements": [
                    {"tag": "markdown", "content": f"## <font color='blue'>{best}</font>", "text_align": "center"},
                    {"tag": "markdown", "content": "<font color='grey'>最高分</font>", "text_align": "center", "text_size": "notation"},
                ],
            },
            {
                "tag": "column",
                "background_style": "blue-50",
                "padding": "12px",
                "vertical_spacing": "2px",
                "elements": [
                    {"tag": "markdown", "content": f"## <font color='blue'>{total}</font>", "text_align": "center"},
                    {"tag": "markdown", "content": "<font color='grey'>批次条目</font>", "text_align": "center", "text_size": "notation"},
                ],
            },
        ],
        "element_id": "batch_metrics",
    }


def _item_block(
    item: dict[str, Any],
    media: dict[str, Any],
    index: int,
) -> dict[str, Any]:
    analysis = _object(item.get("analysis_result"))
    opening = _object(analysis.get("opening"))
    recreation = _object(analysis.get("recreation"))
    title = _text(analysis.get("hook_name"), f"高分 Hook #{index}")
    opening_text = _text(
        recreation.get("three_second_description"),
        _text(opening.get("initial_frame"), "前三秒描述待补充"),
    )
    speech = _text(opening.get("audio_and_speech"), "无明确口播证据")
    url = str(item["permalink"])
    video: dict[str, Any] = {
        "tag": "video",
        "element_id": f"hook_video_{index}",
        "file_key": media["file_key"],
        "enable_download": False,
        "show_time": True,
        "hover_tips": {"tag": "plain_text", "content": "点击播放视频"},
        "fallback": {
            "tag": "fallback_text",
            "text": {
                "tag": "plain_text",
                "content": "当前客户端不支持卡内视频，请使用下方按钮打开原帖。",
            },
        },
    }
    cover_img_key = media.get("cover_img_key")
    if isinstance(cover_img_key, str) and cover_img_key.strip():
        video["cover"] = {"img_key": cover_img_key.strip()}
    return {
        "tag": "interactive_container",
        "width": "fill",
        "has_border": True,
        "border_color": "blue-100",
        "corner_radius": "8px",
        "background_style": "blue-50",
        "padding": "8px",
        "margin": "0px 0px 12px 0px",
        "behaviors": [{"type": "open_url", "default_url": url}],
        "elements": [
            {
                "tag": "column_set",
                "flex_mode": "none",
                "horizontal_spacing": "8px",
                "columns": [
                    {
                        "tag": "column",
                        "width": "weighted",
                        "weight": 2,
                        "elements": [video],
                    },
                    {
                        "tag": "column",
                        "width": "weighted",
                        "weight": 3,
                        "vertical_spacing": "4px",
                        "elements": [
                            {
                                "tag": "markdown",
                                "content": f"**[#{index} · {title}]({url})**  <text_tag color='blue'>{item['score']} 分</text_tag>\n<font color='grey'>{_creator(item)}</font>",
                            },
                            {
                                "tag": "markdown",
                                "content": f"**前三秒**：{opening_text}\n**声音/口播**：{speech}",
                                "text_size": "notation",
                            },
                        ],
                    },
                ],
                "element_id": f"hook_row_{index}",
            }
        ],
        "element_id": f"hook_item_{index}",
    }


def _analysis_url(admin_base_url: str, analysis_id: str) -> str:
    parts = urlsplit(admin_base_url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.update({"source": "social-hook-analysis", "analysis_id": analysis_id})
    query.pop("selected_item_ids", None)
    query.pop("auto_save", None)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _open_analysis_block(analysis_id: str, admin_base_url: str) -> dict[str, Any]:
    view_url = _analysis_url(admin_base_url, analysis_id)
    return {
        "tag": "column_set",
        "flex_mode": "none",
        "horizontal_spacing": "8px",
        "columns": [
            {
                "tag": "column",
                "width": "weighted",
                "weight": 3,
                "vertical_align": "center",
                "elements": [
                    {
                        "tag": "markdown",
                        "content": "**在 AI Hook 页面挑选**\n<font color='grey'>打开整批结果，预览后选择并保存</font>",
                        "text_size": "notation",
                    }
                ],
            },
            {
                "tag": "column",
                "width": "weighted",
                "weight": 1,
                "horizontal_align": "right",
                "vertical_align": "center",
                "elements": [
                    {
                        "tag": "button",
                        "text": {
                            "tag": "plain_text",
                            "content": "挑选并保存",
                        },
                        "type": "primary_filled",
                        "size": "small",
                        "width": "default",
                        "behaviors": [{"type": "open_url", "default_url": view_url}],
                        "element_id": "open_analysis_batch",
                    }
                ],
            },
        ],
        "element_id": "batch_open_area",
    }


def _media_map(payload: Any) -> dict[str, dict[str, Any]]:
    root = _object(payload)
    if root.get("media_schema_version") != MEDIA_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported Lark media schema version: {root.get('media_schema_version')!r}"
        )
    result: dict[str, dict[str, Any]] = {}
    for raw in root.get("items") if isinstance(root.get("items"), list) else []:
        item = _object(raw)
        item_id = item.get("item_id")
        file_key = item.get("file_key")
        if not isinstance(item_id, str) or not item_id.strip():
            raise ValueError("Every Lark media item requires item_id")
        if not isinstance(file_key, str) or not file_key.startswith("file_"):
            raise ValueError(f"Lark media item {item_id!r} requires a file_key")
        result[item_id] = item
    return result


def build_card(
    payload: Any,
    media_payload: Any,
    batch_id: str,
    admin_base_url: str,
    min_score: int,
    max_items: int,
) -> dict[str, Any]:
    selected = _recommended_items(payload, min_score, max_items)
    if not selected:
        raise ValueError("No recommended Instagram Hook meets the card threshold")
    media = _media_map(media_payload)
    missing_media = [str(item.get("id")) for item in selected if str(item.get("id")) not in media]
    if missing_media:
        raise ValueError(f"Missing uploaded Lark video for item(s): {', '.join(missing_media)}")
    elements = [
        _item_block(
            item,
            media[str(item.get("id"))],
            index,
        )
        for index, item in enumerate(selected, start=1)
    ]
    elements.append(_open_analysis_block(batch_id, admin_base_url))
    return {
        "schema": "2.0",
        "config": {
            "update_multi": True,
            "enable_forward": False,
            "width_mode": "default",
            "summary": {"content": f"Instagram Hook 分析 · {len(selected)} 条高分结果"},
        },
        "header": {
            "title": {"tag": "plain_text", "content": "Instagram Hook 分析"},
            "subtitle": {
                "tag": "plain_text",
                "content": f"批次 {batch_id} · {len(selected)} 条",
            },
            "template": "blue",
            "icon": {"tag": "standard_icon", "token": "chart_colorful"},
            "text_tag_list": [
                {"tag": "text_tag", "text": {"tag": "plain_text", "content": "已完成"}, "color": "blue"}
            ],
        },
        "body": {
            "direction": "vertical",
            "padding": "12px 12px 20px 12px",
            "vertical_spacing": "0px",
            "elements": elements,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", nargs="?", help="ranked_hooks.json; defaults to stdin")
    parser.add_argument(
        "--media-keys", required=True, help="social-hook-lark-media.v1 JSON from Lark uploads"
    )
    parser.add_argument("--analysis-id", required=True, help="analysis batch id shown in the card")
    parser.add_argument(
        "--admin-base-url",
        default="https://museon-ai-hook.vercel.app/hook-format",
        help="AI Hook app page used after a successful form submission",
    )
    parser.add_argument("--min-score", type=int, default=DEFAULT_MIN_SCORE)
    parser.add_argument("--max-items", type=int, choices=range(1, 5), default=DEFAULT_MAX_ITEMS)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    text = Path(args.input).read_text(encoding="utf-8") if args.input else sys.stdin.read()
    media_payload = json.loads(Path(args.media_keys).read_text(encoding="utf-8"))
    card = build_card(
        json.loads(text),
        media_payload,
        args.analysis_id,
        args.admin_base_url,
        args.min_score,
        args.max_items,
    )
    json.dump(card, sys.stdout, ensure_ascii=False, indent=2 if args.pretty else None)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
