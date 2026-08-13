from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/social-media-hook-analyze/scripts/rank_hooks.py"
CARD_SCRIPT = ROOT / "skills/social-media-hook-analyze/scripts/prepare_lark_card.py"
UPLOAD_SCRIPT = ROOT / "skills/social-media-hook-analyze/scripts/upload_lark_media.py"
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
                "media_schema_version": "social-hook-lark-media.v2",
                "items": [
                    {
                        "item_id": "item-1",
                        "file_key": "file_v3_demo",
                        "cover_img_key": "img_v3_demo",
                        "duration_ms": 47000,
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
    assert len(card["body"]["elements"]) == 3
    item_block = card["body"]["elements"][0]
    open_area = card["body"]["elements"][2]
    assert card["config"]["enable_forward"] is False
    assert item_block["tag"] == "column_set"
    assert item_block["columns"][0]["weight"] == 1
    assert item_block["columns"][0]["elements"][0] == {
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
    assert "behaviors" not in item_block
    title = item_block["columns"][0]["elements"][1]
    assert title["tag"] == "markdown"
    assert "@creator" in title["content"]
    assert "https://www.instagram.com/reel/example/" in title["content"]
    assert "checker" not in json.dumps(card)
    assert "form_action_type" not in json.dumps(card)
    open_button = open_area["columns"][0]["elements"][0]
    assert open_button["text"]["content"] == "挑选并保存"
    assert open_button["type"] == "default"
    assert open_button["size"] == "medium"
    assert open_button["width"] == "fill"
    assert open_button["behaviors"] == [
        {
            "type": "open_url",
            "default_url": "https://museon-ai-hook.vercel.app/hook-format/social-analysis?source=social-hook-analysis&analysis_id=batch-1&recommended_item_ids=item-1",
        }
    ]
    save_all_button = open_area["columns"][1]["elements"][0]
    assert save_all_button["text"]["content"] == "全部保存"
    assert save_all_button["type"] == "primary_filled"
    assert save_all_button["size"] == "medium"
    assert save_all_button["width"] == "fill"
    assert save_all_button["behaviors"] == [
        {
            "type": "open_url",
            "default_url": "https://museon-ai-hook.vercel.app/hook-format/social-analysis?source=social-hook-analysis&analysis_id=batch-1&recommended_item_ids=item-1&auto_save=1",
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
        json.dumps({"media_schema_version": "social-hook-lark-media.v2", "items": []}),
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


def test_lark_card_fails_closed_without_duration_and_cover(tmp_path: Path) -> None:
    ranked = _run(tmp_path, _assessment())
    ranked_path = tmp_path / "ranked.json"
    ranked_path.write_text(json.dumps(ranked), encoding="utf-8")

    for media_item, expected_error in [
        (
            {"item_id": "item-1", "file_key": "file_v3_demo", "cover_img_key": "img_v3_demo"},
            "duration_ms > 0",
        ),
        (
            {"item_id": "item-1", "file_key": "file_v3_demo", "duration_ms": 47000},
            "cover_img_key",
        ),
    ]:
        media_path = tmp_path / "media-invalid.json"
        media_path.write_text(
            json.dumps(
                {
                    "media_schema_version": "social-hook-lark-media.v2",
                    "items": [media_item],
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
        )

        assert completed.returncode != 0
        assert expected_error in completed.stderr


def test_lark_media_uploader_passes_real_duration_and_uploads_cover(
    tmp_path: Path, monkeypatch: Any
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    upload_log = tmp_path / "upload.log"
    ffprobe = bin_dir / "ffprobe"
    ffprobe.write_text("#!/bin/sh\nprintf '47.125\\n'\n", encoding="utf-8")
    ffmpeg = bin_dir / "ffmpeg"
    ffmpeg.write_text(
        "#!/bin/sh\n"
        'case "$*" in\n'
        "  *blackdetect*) echo 'black_start:0 black_end:0.08' >&2 ;;\n"
        "  *) for last do :; done; printf 'jpeg' > \"$last\" ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    lark = bin_dir / "lark-cli"
    lark.write_text(
        "#!/bin/sh\n"
        'printf \'%s\\n\' "$*" >> "$UPLOAD_LOG"\n'
        'case "$*" in\n'
        '  */open-apis/im/v1/files*) echo \'{"ok":true,"data":{"file_key":"file_v3_demo"}}\' ;;\n'
        '  *) echo \'{"ok":true,"data":{"image_key":"img_v3_demo"}}\' ;;\n'
        "esac\n",
        encoding="utf-8",
    )
    for executable in (ffprobe, ffmpeg, lark):
        executable.chmod(0o755)
    video_path = tmp_path / "hook.mp4"
    video_path.write_bytes(b"fake-mp4")
    sources_path = tmp_path / "sources.json"
    sources_path.write_text(
        json.dumps(
            {
                "media_source_schema_version": "social-hook-lark-media-source.v1",
                "items": [{"item_id": "item-1", "video_path": "hook.mp4"}],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")
    monkeypatch.setenv("UPLOAD_LOG", str(upload_log))

    completed = subprocess.run(
        [sys.executable, str(UPLOAD_SCRIPT), str(sources_path)],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=True,
    )
    result = json.loads(completed.stdout)

    assert result == {
        "media_schema_version": "social-hook-lark-media.v2",
        "items": [
            {
                "item_id": "item-1",
                "file_key": "file_v3_demo",
                "cover_img_key": "img_v3_demo",
                "duration_ms": 47125,
            }
        ],
    }
    upload_calls = upload_log.read_text(encoding="utf-8")
    assert '"duration":47125' in upload_calls
    assert "/open-apis/im/v1/files --as bot" in upload_calls
    assert "im images create --as bot" in upload_calls


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
        "research.social-media-hook-analyze-media-get",
    }


def test_skill_setup_vmos_mode_does_not_require_ego(tmp_path: Path, monkeypatch: Any) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    museon = bin_dir / "museoncli"
    museon.write_text("#!/bin/sh\necho '{\"ok\": true}'\n", encoding="utf-8")
    museon.chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir))

    completed = subprocess.run(
        [sys.executable, str(SETUP_SCRIPT), "--collector", "vmos"],
        text=True,
        capture_output=True,
        check=True,
    )
    result = json.loads(completed.stdout)

    assert result["ready"] is True
    assert result["collector"] == "vmos"
    assert result["dependencies"]["ego_browser"]["required"] is False
