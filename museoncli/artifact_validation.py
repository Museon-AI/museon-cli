"""Local validation for customer-facing Artifact Markdown."""

from __future__ import annotations

import math
import re
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import yaml


_REPORT_DIRECTIONS_OPEN_RE = re.compile(r"^\s*```report-directions\s*$", re.IGNORECASE)
_FENCE_CLOSE_RE = re.compile(r"^\s*```\s*$")
_STANDALONE_MARKDOWN_LINK_RE = re.compile(r"^\s*\[[^\]]+\]\((https?://[^)\s]+)\)\s*$")
_DIRECTION_FIELDS = {
    "number",
    "tag",
    "headline",
    "description",
    "image",
    "reference",
    "generated",
    "stats",
    "note",
}
_STAT_FIELDS = {"label", "value"}
_NOTE_FIELDS = {"label", "value"}
_REFERENCE_FIELDS = {"url", "label", "images"}
_GENERATED_FIELDS = {"label", "images"}


def validate_artifact_file(file_path: str) -> dict[str, Any]:
    path = Path(file_path).expanduser()
    if not path.is_file():
        raise ValueError(f"artifact file not found: {file_path}")
    try:
        markdown = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"artifact file must be UTF-8: {file_path}") from exc
    return validate_artifact_markdown(markdown, file_path=str(path))


def validate_artifact_markdown(
    markdown: str,
    *,
    file_path: str | None = None,
) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    lines = markdown.splitlines()

    _validate_frontmatter(lines, errors)
    blocks = _report_direction_blocks(lines, errors)
    item_count = 0
    reference_social_urls: list[str] = []
    for block_index, start_line, raw in blocks:
        document = _parse_yaml(raw, start_line=start_line, errors=errors)
        if document is None:
            continue
        if not isinstance(document, list) or not document:
            _error(
                errors,
                "directions_not_list",
                "report-directions must contain a non-empty YAML list.",
                line=start_line,
                block=block_index,
            )
            continue
        for item_index, item in enumerate(document, start=1):
            item_count += 1
            reference_url = _validate_direction_item(
                item,
                errors=errors,
                block_index=block_index,
                item_index=item_index,
                line=start_line,
            )
            social_url = _canonical_social_url(reference_url) if reference_url else None
            if social_url:
                reference_social_urls.append(social_url)

    standalone_social_urls = _validate_social_embed_lines(lines, errors)
    standalone_counts = Counter(standalone_social_urls)
    for url, count in standalone_counts.items():
        if count > 1:
            _error(
                errors,
                "duplicate_social_embed",
                f"Social URL has {count} standalone Embed placements; keep exactly one: {url}",
            )
    for url in sorted(set(standalone_social_urls) & set(reference_social_urls)):
        _error(
            errors,
            "duplicate_social_placement",
            (
                "Social URL appears as both a standalone Embed and reference.url. "
                f"Choose one placement: {url}"
            ),
        )

    main_sections = sum(1 for line in lines if re.match(r"^##\s+\S", line))
    table_count = sum(1 for line in lines if re.match(r"^\s*\|(?:\s*:?-{3,}:?\s*\|)+\s*$", line))
    if main_sections > 4:
        _warning(
            warnings,
            "section_budget_exceeded",
            f"Artifact has {main_sections} main sections; the default budget is 4.",
        )
    if table_count > 2:
        _warning(
            warnings,
            "table_budget_exceeded",
            f"Artifact has {table_count} tables; the default budget is 2.",
        )

    return {
        "valid": not errors,
        "file": file_path,
        "errors": errors,
        "warnings": warnings,
        "summary": {
            "report_direction_blocks": len(blocks),
            "report_direction_items": item_count,
            "standalone_social_embeds": len(standalone_social_urls),
            "main_sections": main_sections,
            "tables": table_count,
        },
    }


def _validate_frontmatter(lines: list[str], errors: list[dict[str, Any]]) -> None:
    if not lines or lines[0].strip() != "---":
        _error(errors, "missing_frontmatter", "Artifact must start with YAML frontmatter.", line=1)
        return
    closing_index = next(
        (index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---"),
        None,
    )
    if closing_index is None:
        _error(errors, "unclosed_frontmatter", "Artifact frontmatter is missing its closing ---.")
        return
    document = _parse_yaml("\n".join(lines[1:closing_index]), start_line=2, errors=errors)
    if document is None:
        return
    if not isinstance(document, dict):
        _error(errors, "frontmatter_not_mapping", "Artifact frontmatter must be a YAML mapping.")
        return
    if document.get("template") != "research-report@v1":
        _error(
            errors,
            "invalid_template",
            "Frontmatter template must be research-report@v1.",
            field="template",
        )
    if not _required_scalar(document.get("title")):
        _error(errors, "missing_title", "Frontmatter title is required.", field="title")


def _report_direction_blocks(
    lines: list[str],
    errors: list[dict[str, Any]],
) -> list[tuple[int, int, str]]:
    blocks: list[tuple[int, int, str]] = []
    index = 0
    while index < len(lines):
        if not _REPORT_DIRECTIONS_OPEN_RE.match(lines[index]):
            index += 1
            continue
        opening_line = index + 1
        content: list[str] = []
        index += 1
        while index < len(lines) and not _FENCE_CLOSE_RE.match(lines[index]):
            content.append(lines[index])
            index += 1
        if index >= len(lines):
            _error(
                errors,
                "unclosed_directions_fence",
                "report-directions fence is missing its closing ```.",
                line=opening_line,
            )
            break
        blocks.append((len(blocks) + 1, opening_line + 1, "\n".join(content)))
        index += 1
    return blocks


def _parse_yaml(
    raw: str,
    *,
    start_line: int,
    errors: list[dict[str, Any]],
) -> Any | None:
    try:
        for token in yaml.scan(raw):
            if isinstance(token, (yaml.tokens.AliasToken, yaml.tokens.AnchorToken)):
                _error(
                    errors,
                    "yaml_alias_forbidden",
                    "YAML anchors and aliases are not supported.",
                    line=start_line + token.start_mark.line,
                )
                return None
        return yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        line = start_line + mark.line if mark is not None else start_line
        _error(errors, "invalid_yaml", f"Invalid YAML: {exc}", line=line)
        return None


def _validate_direction_item(
    item: Any,
    *,
    errors: list[dict[str, Any]],
    block_index: int,
    item_index: int,
    line: int,
) -> str | None:
    location = {"line": line, "block": block_index, "item": item_index}
    if not isinstance(item, dict):
        _error(errors, "direction_not_mapping", "Direction item must be a mapping.", **location)
        return None
    _reject_unknown_fields(item, _DIRECTION_FIELDS, errors, location=location)
    for field in ("number", "tag", "headline", "description"):
        if not _required_scalar(item.get(field)):
            _error(
                errors,
                "missing_required_field",
                f"Direction field '{field}' is required and must be scalar.",
                field=field,
                **location,
            )

    image = item.get("image")
    if image is not None:
        _validate_url_scalar(image, "image", errors, location)

    reference = item.get("reference")
    reference_url, reference_has_images = _validate_preview(
        reference,
        allowed_fields=_REFERENCE_FIELDS,
        allow_url=True,
        field="reference",
        errors=errors,
        location=location,
    )
    _, generated_has_images = _validate_preview(
        item.get("generated"),
        allowed_fields=_GENERATED_FIELDS,
        allow_url=False,
        field="generated",
        errors=errors,
        location=location,
    )
    if image is not None and (reference_has_images or generated_has_images):
        _error(
            errors,
            "ambiguous_preview_mode",
            "Use top-level image or reference/generated images, not both.",
            field="image",
            **location,
        )

    stats = item.get("stats")
    if stats is not None:
        if not isinstance(stats, list):
            _error(errors, "invalid_stats", "stats must be a list when present.", **location)
        elif len(stats) > 3:
            _error(errors, "too_many_stats", "stats supports at most 3 items.", **location)
        else:
            for stat_index, stat in enumerate(stats, start=1):
                stat_location = {**location, "field": f"stats[{stat_index}]"}
                if not isinstance(stat, dict):
                    _error(errors, "invalid_stat", "Each stat must be a mapping.", **stat_location)
                    continue
                _reject_unknown_fields(stat, _STAT_FIELDS, errors, location=stat_location)
                if not _required_scalar(stat.get("label")) or not _required_scalar(
                    stat.get("value")
                ):
                    _error(
                        errors,
                        "invalid_stat",
                        "Each stat requires non-empty label and value scalars.",
                        **stat_location,
                    )

    note = item.get("note")
    if not isinstance(note, dict):
        _error(errors, "missing_note", "note is required and must be a mapping.", **location)
    else:
        _reject_unknown_fields(note, _NOTE_FIELDS, errors, location={**location, "field": "note"})
        if not _required_scalar(note.get("label")) or not _required_scalar(note.get("value")):
            _error(
                errors,
                "invalid_note",
                "note requires non-empty label and value scalars.",
                field="note",
                **location,
            )
    return reference_url


def _validate_preview(
    value: Any,
    *,
    allowed_fields: set[str],
    allow_url: bool,
    field: str,
    errors: list[dict[str, Any]],
    location: dict[str, Any],
) -> tuple[str | None, bool]:
    if value is None:
        return None, False
    field_location = {**location, "field": field}
    if not isinstance(value, dict):
        _error(errors, "invalid_preview", f"{field} must be a mapping.", **field_location)
        return None, False
    _reject_unknown_fields(value, allowed_fields, errors, location=field_location)
    label = value.get("label")
    if label is not None and not _scalar(label):
        _error(errors, "invalid_preview_label", f"{field}.label must be scalar.", **field_location)
    images = value.get("images")
    has_images = isinstance(images, list) and len(images) > 0
    if not has_images:
        _error(
            errors,
            "preview_images_required",
            f"{field}.images must contain at least one image URL.",
            **field_location,
        )
    else:
        for image_index, image in enumerate(images, start=1):
            _validate_url_scalar(
                image,
                f"{field}.images[{image_index}]",
                errors,
                location,
            )
    url = value.get("url") if allow_url else None
    if allow_url and url is not None:
        _validate_url_scalar(url, f"{field}.url", errors, location)
    return str(url).strip() if _scalar(url) else None, has_images


def _validate_url_scalar(
    value: Any,
    field: str,
    errors: list[dict[str, Any]],
    location: dict[str, Any],
) -> None:
    if not isinstance(value, str) or not _http_url(value):
        _error(
            errors,
            "invalid_http_url",
            f"{field} must be one raw public http(s) URL string.",
            field=field,
            **location,
        )


def _reject_unknown_fields(
    value: dict[Any, Any],
    allowed: set[str],
    errors: list[dict[str, Any]],
    *,
    location: dict[str, Any],
) -> None:
    unknown = sorted(str(key) for key in value if key not in allowed)
    if unknown:
        _error(
            errors,
            "unknown_fields",
            f"Unsupported fields: {', '.join(unknown)}.",
            **location,
        )


def _validate_social_embed_lines(
    lines: list[str],
    errors: list[dict[str, Any]],
) -> list[str]:
    standalone: list[str] = []
    for line_number, line in enumerate(lines, start=1):
        stripped = line.strip()
        social_url = _canonical_social_url(stripped)
        if social_url:
            standalone.append(social_url)
            continue
        anchor_match = _STANDALONE_MARKDOWN_LINK_RE.match(line)
        if anchor_match and _canonical_social_url(anchor_match.group(1)):
            _error(
                errors,
                "social_embed_must_be_raw_url",
                "A standalone social Embed must use the raw canonical URL, not a Markdown anchor.",
                line=line_number,
            )
    return standalone


def _canonical_social_url(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = urlsplit(value.strip())
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"}:
        return None
    host = parsed.hostname.lower() if parsed.hostname else ""
    path = parsed.path.rstrip("/")
    if host in {"tiktok.com", "www.tiktok.com", "m.tiktok.com"} and re.fullmatch(
        r"/@[^/]+/(?:video|photo)/\d+", path, re.IGNORECASE
    ):
        return f"https://www.tiktok.com{path}"
    if host in {"instagram.com", "www.instagram.com", "m.instagram.com"} and re.fullmatch(
        r"/(?:p|reel)/[A-Za-z0-9_-]+", path
    ):
        return f"https://www.instagram.com{path}/"
    if host in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
        if path == "/watch":
            video_id = (parse_qs(parsed.query).get("v") or [""])[0]
            if re.fullmatch(r"[A-Za-z0-9_-]+", video_id):
                return f"https://www.youtube.com/watch?v={video_id}"
        shorts_match = re.fullmatch(r"/shorts/([A-Za-z0-9_-]+)", path)
        if shorts_match:
            return f"https://www.youtube.com/shorts/{shorts_match.group(1)}"
    return None


def _required_scalar(value: Any) -> bool:
    return _scalar(value) and bool(str(value).strip())


def _scalar(value: Any) -> bool:
    return isinstance(value, (str, bool)) or (
        isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    )


def _http_url(value: str) -> bool:
    try:
        parsed = urlsplit(value.strip())
    except ValueError:
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.hostname)


def _error(errors: list[dict[str, Any]], code: str, message: str, **location: Any) -> None:
    errors.append({"code": code, "message": message, **location})


def _warning(warnings: list[dict[str, Any]], code: str, message: str, **location: Any) -> None:
    warnings.append({"code": code, "message": message, **location})
