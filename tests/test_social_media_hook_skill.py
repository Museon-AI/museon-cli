from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/social-media-hook-analyze/scripts/rank_hooks.py"
CARD_SCRIPT = ROOT / "skills/social-media-hook-analyze/scripts/prepare_lark_card.py"
SETUP_SCRIPT = ROOT / "skills/social-media-hook-analyze/scripts/check_setup.py"


def _analysis_payload() -> dict[str, Any]:
    return {
        "data": {
            "items": [
                {
                    "id": "item-1",
                    "permalink": "https://www.instagram.com/reel/example/",
                    "status": "completed",
                    "analysis_result": {
                        "analysis_schema_version": "social-hook-analysis.v1",
                        "opening": {
                            "initial_frame": "A person faces the camera with the product.",
                            "visual_action": "They point to a visible flaw.",
                            "face_and_expression": "Their frustration is clearly readable.",
                        },
                        "mechanism": {
                            "why_it_stops_scroll": "The gesture exposes a surprising flaw.",
                            "emotional_performance": "Frustration is immediate.",
                            "viewer_empathy": "The problem is familiar.",
                            "why_viewers_continue": "The fix has not been shown yet.",
                        },
                        "recreation": {
                            "three_second_description": "Show the flaw, react, promise a test.",
                            "must_preserve": ["personal reaction", "visible flaw"],
                            "adaptable_variables": ["product", "setting"],
                            "non_transferable_elements": [],
                        },
                        "evidence_quality": {"confidence": "high"},
                        "ugc_style": {"is_ugc_style": True},
                        "evidence": [
                            {
                                "supports": [
                                    "scroll_stop",
                                    "emotion",
                                    "curiosity",
                                ]
                            }
                        ],
                    },
                }
            ]
        }
    }


def _assessment(**overrides: Any) -> dict[str, Any]:
    item = {
        "item_id": "item-1",
        "verdict": "qualifies",
        "confidence": "high",
        "post_type": "ugc_creator_hook",
        "creator_led": "yes",
        "creator_experience_carries_product": "yes",
        "ordinary_creator_reproducible": "yes",
        "evidence": [
            {
                "path": "opening.audio_and_speech",
                "observation": "The creator makes a personal product claim.",
            }
        ],
        "exclusion_signals": [],
    }
    item.update(overrides)
    return {
        "assessment_schema_version": "ugc-creator-hook-assessment.v1",
        "items": [item],
    }


def _run(tmp_path: Path, assessment: dict[str, Any] | None) -> dict[str, Any]:
    analysis_path = tmp_path / "analysis.json"
    analysis_path.write_text(json.dumps(_analysis_payload()), encoding="utf-8")
    command = [sys.executable, str(SCRIPT), str(analysis_path)]
    if assessment is not None:
        assessment_path = tmp_path / "assessment.json"
        assessment_path.write_text(json.dumps(assessment), encoding="utf-8")
        command.extend(["--post-assessments", str(assessment_path)])
    completed = subprocess.run(command, text=True, capture_output=True, check=True)
    return json.loads(completed.stdout)


def test_ranker_recommends_only_agent_qualified_creator_hook(tmp_path: Path) -> None:
    result = _run(tmp_path, _assessment())

    item = result["items"][0]
    assert result["strategy_version"] == "hook-score.v2"
    assert item["decision"] == "recommended"
    assert item["gate_reason"] == "qualified_ugc_creator_hook"
    assert item["dimension_scores"]["creator_transferability"] == 100


def test_ranker_excludes_brand_showcase_even_with_strong_visual_evidence(
    tmp_path: Path,
) -> None:
    result = _run(
        tmp_path,
        _assessment(
            verdict="does_not_qualify",
            post_type="brand_product_showcase",
            creator_led="no",
            creator_experience_carries_product="no",
            ordinary_creator_reproducible="no",
            exclusion_signals=["Object-only product showcase"],
        ),
    )

    item = result["items"][0]
    assert item["decision"] == "excluded"
    assert item["gate_reason"] == "not_a_ugc_creator_hook"
    assert "score" not in item


def test_ranker_fails_closed_when_agent_assessment_is_missing(tmp_path: Path) -> None:
    result = _run(tmp_path, None)

    item = result["items"][0]
    assert item["decision"] == "post_hook_review_required"
    assert item["gate_reason"] == "missing_post_assessment"


def test_ranker_fails_closed_for_low_confidence_qualification(tmp_path: Path) -> None:
    result = _run(tmp_path, _assessment(confidence="low"))

    item = result["items"][0]
    assert item["decision"] == "post_hook_review_required"
    assert item["gate_reason"] == "low_assessment_confidence"


def test_ranker_rejects_inconsistent_qualification(tmp_path: Path) -> None:
    result = _run(tmp_path, _assessment(creator_led="no"))

    item = result["items"][0]
    assert item["decision"] == "post_hook_review_required"
    assert item["gate_reason"] == "qualifying_verdict_requires_creator_led"


def test_lark_card_groups_only_recommended_hooks_with_clickable_video(tmp_path: Path) -> None:
    ranked = _run(tmp_path, _assessment())
    ranked["items"][0]["creator_username"] = "creator"
    ranked_path = tmp_path / "ranked.json"
    ranked_path.write_text(json.dumps(ranked), encoding="utf-8")
    media_path = tmp_path / "media.json"
    media_path.write_text(
        json.dumps(
            {
                "media_schema_version": "social-hook-lark-media.v1",
                "items": [
                    {
                        "item_id": "item-1",
                        "file_key": "file_v3_demo",
                        "cover_img_key": "img_v3_demo",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(CARD_SCRIPT),
            str(ranked_path),
            "--analysis-id",
            "batch-1",
            "--media-keys",
            str(media_path),
        ],
        text=True,
        capture_output=True,
        check=True,
    )
    card = json.loads(completed.stdout)

    assert card["schema"] == "2.0"
    assert card["header"]["subtitle"]["content"] == "批次 batch-1 · 1 条"
    assert len(card["body"]["elements"]) == 2
    item_block = card["body"]["elements"][0]
    open_area = card["body"]["elements"][1]
    assert card["config"]["enable_forward"] is False
    row = item_block["elements"][0]
    assert row["tag"] == "column_set"
    assert row["columns"][0]["weight"] == 2
    assert row["columns"][1]["weight"] == 3
    assert row["columns"][0]["elements"][0] == {
        "tag": "video",
        "element_id": "hook_video_1",
        "file_key": "file_v3_demo",
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
        "cover": {"img_key": "img_v3_demo"},
    }
    assert item_block["behaviors"] == [
        {
            "type": "open_url",
            "default_url": "https://www.instagram.com/reel/example/",
        }
    ]
    title = row["columns"][1]["elements"][0]
    assert title["tag"] == "markdown"
    assert "@creator" in title["content"]
    assert "https://www.instagram.com/reel/example/" in title["content"]
    assert "checker" not in json.dumps(card)
    assert "form_action_type" not in json.dumps(card)
    open_button = open_area["columns"][1]["elements"][0]
    assert open_button["text"]["content"] == "挑选并保存"
    assert open_button["type"] == "primary_filled"
    assert open_button["size"] == "small"
    assert open_button["behaviors"] == [
        {
            "type": "open_url",
            "default_url": "https://museon-ai-hook.vercel.app/hook-format?source=social-hook-analysis&analysis_id=batch-1",
        }
    ]
    assert open_area["element_id"] == "batch_open_area"


def test_lark_card_fails_closed_without_recommended_hooks(tmp_path: Path) -> None:
    ranked = _run(
        tmp_path,
        _assessment(
            verdict="does_not_qualify",
            post_type="brand_product_showcase",
            creator_led="no",
            creator_experience_carries_product="no",
            ordinary_creator_reproducible="no",
            exclusion_signals=["Object-only product showcase"],
        ),
    )
    ranked_path = tmp_path / "ranked.json"
    ranked_path.write_text(json.dumps(ranked), encoding="utf-8")
    media_path = tmp_path / "media.json"
    media_path.write_text(
        json.dumps({"media_schema_version": "social-hook-lark-media.v1", "items": []}),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(CARD_SCRIPT),
            str(ranked_path),
            "--analysis-id",
            "batch-1",
            "--media-keys",
            str(media_path),
        ],
        text=True,
        capture_output=True,
    )

    assert completed.returncode != 0
    assert "No recommended Instagram Hook" in completed.stderr


def test_skill_setup_checks_ego_and_required_museon_schemas(
    tmp_path: Path, monkeypatch: Any
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    ego = bin_dir / "ego-browser"
    ego.write_text("#!/bin/sh\necho 'ego-browser ready'\n", encoding="utf-8")
    museon = bin_dir / "museoncli"
    museon.write_text("#!/bin/sh\necho '{\"ok\": true}'\n", encoding="utf-8")
    ego.chmod(0o755)
    museon.chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir))

    completed = subprocess.run(
        [sys.executable, str(SETUP_SCRIPT)],
        text=True,
        capture_output=True,
        check=True,
    )
    result = json.loads(completed.stdout)

    assert result["ready"] is True
    assert set(result["dependencies"]["museon_cli"]["schemas"]) == {
        "research.social-media-hook-analyze",
        "research.social-media-hook-analyze-poll",
        "research.social-media-hook-analyze-results",
    }
