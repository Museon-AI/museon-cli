from __future__ import annotations

import asyncio
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

import pytest

from museoncli.artifact_validation import validate_artifact_markdown
from museoncli.config import Config
import museoncli.main as main_module
from museoncli.main import build_parser


def _artifact(body: str) -> str:
    return (
        "---\n"
        "template: research-report@v1\n"
        'title: "Artifact contract test"\n'
        "---\n\n"
        f"{body.strip()}\n"
    )


def test_validate_accepts_stats_free_direction_and_supported_embeds() -> None:
    markdown = _artifact(
        """
## Core decision

https://www.tiktok.com/@brand/photo/123456789

```report-directions
- number: '01'
  tag: "Product / Visual proof"
  headline: "Visible product evidence"
  description: "The packaging supports the recommendation."
  image: "https://cdn.example.com/product.webp"
  note:
    label: "Customer implication"
    value: "Use this packaging detail in the first test."
```
"""
    )

    result = validate_artifact_markdown(markdown)

    assert result["valid"] is True
    assert result["errors"] == []
    assert result["summary"] == {
        "report_direction_blocks": 1,
        "report_direction_items": 1,
        "standalone_social_embeds": 1,
        "main_sections": 1,
        "tables": 0,
    }


@pytest.mark.parametrize(
    ("payload", "expected_code"),
    [
        (
            """
- number: '01'
  tag: "Product"
  headline: "Bad image shape"
  description: "Top-level image cannot be a list."
  image:
    - "https://cdn.example.com/a.webp"
  note: {label: "Decision", value: "Fix it"}
""",
            "invalid_http_url",
        ),
        (
            """
- number: '01'
  tag: "Product"
  headline: "Unknown field"
  description: "Unknown fields leak the block as code."
  unsupported: true
  note: {label: "Decision", value: "Fix it"}
""",
            "unknown_fields",
        ),
        (
            """
- number: '01'
  tag: "Product"
  headline: "Missing note"
  description: "The note is required."
""",
            "missing_note",
        ),
        (
            """
- number: '01'
  tag: "Product"
  headline: "Ambiguous preview"
  description: "Only one preview mode is allowed."
  image: "https://cdn.example.com/a.webp"
  reference:
    images: ["https://cdn.example.com/b.webp"]
  note: {label: "Decision", value: "Fix it"}
""",
            "ambiguous_preview_mode",
        ),
    ],
)
def test_validate_rejects_invalid_direction_contract(payload: str, expected_code: str) -> None:
    markdown = _artifact(f"## Decision\n\n```report-directions\n{payload.strip()}\n```")

    result = validate_artifact_markdown(markdown)

    assert result["valid"] is False
    assert expected_code in {error["code"] for error in result["errors"]}


def test_validate_rejects_duplicate_embed_and_reference_placement() -> None:
    url = "https://www.instagram.com/p/ABC_123/"
    markdown = _artifact(
        f"""
## Evidence

{url}

```report-directions
- number: '01'
  tag: "Fallback"
  headline: "Fallback preview"
  description: "A failed Embed uses a persisted image card."
  reference:
    url: "{url}"
    images:
      - "https://cdn.example.com/fallback.webp"
  note:
    label: "Customer implication"
    value: "Keep one source placement."
```
"""
    )

    result = validate_artifact_markdown(markdown)

    assert result["valid"] is False
    assert "duplicate_social_placement" in {error["code"] for error in result["errors"]}


def test_validate_allows_failed_embed_fallback_without_standalone_url() -> None:
    markdown = _artifact(
        """
## Evidence

```report-directions
- number: '01'
  tag: "Instagram / Fallback"
  headline: "Persisted fallback preview"
  description: "Use this only after the native Embed was verified to fail."
  reference:
    url: "https://www.instagram.com/p/ABC_123/"
    label: "Original post"
    images:
      - "https://cdn.example.com/fallback.webp"
  note:
    label: "Customer implication"
    value: "The source remains clickable without a broken iframe."
```
"""
    )

    result = validate_artifact_markdown(markdown)

    assert result["valid"] is True


def test_artifacts_validate_command_reads_local_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = tmp_path / "report.md"
    report.write_text(_artifact("## Decision\n\nReady."), encoding="utf-8")
    monkeypatch.setattr(main_module, "load_config", Config)
    args = build_parser().parse_args(["artifacts", "+validate", "--file", str(report)])

    result = asyncio.run(main_module.dispatch(args))

    assert result["command"] == "artifacts.validate"
    assert result["workspace"] is None
    assert result["data"]["valid"] is True


def test_artifacts_validate_schema_is_local_and_read_only() -> None:
    schema = main_module.schema_payload("artifacts.validate")

    assert schema["risk_level"] == "read"
    assert schema["input_schema"]["required"] == ["file"]
    assert "no network calls" in schema["summary"]


def test_python_module_entrypoint_runs_positive_and_negative_validation(tmp_path: Path) -> None:
    valid_report = tmp_path / "valid.md"
    valid_report.write_text(_artifact("## Decision\n\nReady."), encoding="utf-8")
    invalid_report = tmp_path / "invalid.md"
    invalid_report.write_text(
        _artifact(
            """
## Decision

```report-directions
- number: '01'
  tag: Product
  headline: Invalid image
  description: Top-level image cannot be a list.
  image:
    - https://cdn.example.com/product.webp
  note: {label: Decision, value: Fix it}
```
"""
        ),
        encoding="utf-8",
    )

    def run(report: Path) -> dict[str, Any]:
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "museoncli.main",
                "artifacts",
                "+validate",
                "--file",
                str(report),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(completed.stdout)

    assert run(valid_report)["data"]["valid"] is True
    invalid = run(invalid_report)
    assert invalid["data"]["valid"] is False
    assert invalid["data"]["errors"][0]["code"] == "invalid_http_url"
