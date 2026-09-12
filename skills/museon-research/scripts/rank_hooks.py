#!/usr/bin/env python3
"""Gate and rank Hook evidence using host-Agent post assessments."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

STRATEGY_VERSION = "hook-score.v2"
ANALYSIS_SCHEMA_VERSION = "social-hook-analysis.v1"
ASSESSMENT_SCHEMA_VERSION = "ugc-creator-hook-assessment.v1"
VERDICTS = {"qualifies", "does_not_qualify", "uncertain"}
CONFIDENCES = {"high", "medium", "low"}
POST_TYPES = {
    "ugc_creator_hook",
    "brand_product_showcase",
    "event_coverage",
    "cinematic_brand_ad",
    "object_demonstration",
    "other_non_creator",
    "uncertain",
}
TRISTATE = {"yes", "no", "uncertain"}
PRODUCT_STATES = {*TRISTATE, "not_applicable"}
DEFAULT_CONFIG: dict[str, Any] = {
    "weights": {
        "scroll_stop": 30,
        "emotion": 20,
        "curiosity": 20,
        "reproducibility": 20,
        "creator_transferability": 10,
    },
    "recommend_threshold": 75,
    "review_threshold": 60,
}


def _nonempty(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    return bool(value)


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _object(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _support_count(analysis: dict[str, Any], dimension: str) -> int:
    return sum(
        dimension in _list(_object(item).get("supports"))
        for item in _list(analysis.get("evidence"))
    )


def _assessment_error(assessment: dict[str, Any]) -> str | None:
    if assessment.get("verdict") not in VERDICTS:
        return "invalid_verdict"
    if assessment.get("confidence") not in CONFIDENCES:
        return "invalid_confidence"
    if assessment.get("post_type") not in POST_TYPES:
        return "invalid_post_type"
    if assessment.get("creator_led") not in TRISTATE:
        return "invalid_creator_led"
    if assessment.get("creator_experience_carries_product") not in PRODUCT_STATES:
        return "invalid_product_experience"
    if assessment.get("ordinary_creator_reproducible") not in TRISTATE:
        return "invalid_reproducibility"
    evidence = assessment.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        return "missing_evidence"
    for entry in evidence:
        if not isinstance(entry, dict) or not _nonempty(entry.get("path")) or not _nonempty(
            entry.get("observation")
        ):
            return "invalid_evidence"
    if not isinstance(assessment.get("exclusion_signals"), list):
        return "invalid_exclusion_signals"
    return None


def _qualified_assessment_error(assessment: dict[str, Any]) -> str | None:
    if assessment.get("post_type") != "ugc_creator_hook":
        return "qualifying_verdict_requires_ugc_creator_hook_type"
    if assessment.get("creator_led") != "yes":
        return "qualifying_verdict_requires_creator_led"
    if assessment.get("creator_experience_carries_product") not in {
        "yes",
        "not_applicable",
    }:
        return "qualifying_verdict_requires_creator_experience"
    if assessment.get("ordinary_creator_reproducible") != "yes":
        return "qualifying_verdict_requires_reproducibility"
    return None


def _dimension_scores(
    analysis: dict[str, Any], assessment: dict[str, Any]
) -> dict[str, int]:
    opening = _object(analysis.get("opening"))
    mechanism = _object(analysis.get("mechanism"))
    recreation = _object(analysis.get("recreation"))

    scores = {
        "scroll_stop": min(
            100,
            30
            + 20 * _nonempty(opening.get("initial_frame"))
            + 20 * _nonempty(opening.get("visual_action"))
            + 15 * _nonempty(mechanism.get("why_it_stops_scroll"))
            + 15 * min(_support_count(analysis, "scroll_stop"), 1),
        ),
        "emotion": min(
            100,
            25
            + 25 * _nonempty(opening.get("face_and_expression"))
            + 20 * _nonempty(mechanism.get("emotional_performance"))
            + 15 * _nonempty(mechanism.get("viewer_empathy"))
            + 15 * min(_support_count(analysis, "emotion"), 1),
        ),
        "curiosity": min(
            100,
            30
            + 35 * _nonempty(mechanism.get("why_viewers_continue"))
            + 20 * min(_support_count(analysis, "curiosity"), 1)
            + 15 * _nonempty(recreation.get("three_second_description")),
        ),
        "reproducibility": max(
            0,
            min(
                100,
                25
                + 30 * _nonempty(recreation.get("three_second_description"))
                + 20 * min(len(_list(recreation.get("must_preserve"))), 2) / 2
                + 25 * min(len(_list(recreation.get("adaptable_variables"))), 2) / 2
                - 10 * min(len(_list(recreation.get("non_transferable_elements"))), 3),
            ),
        ),
        "creator_transferability": min(
            100,
            30
            + 25 * (assessment.get("creator_led") == "yes")
            + 20
            * (assessment.get("creator_experience_carries_product") in {"yes", "not_applicable"})
            + 25 * (assessment.get("ordinary_creator_reproducible") == "yes"),
        ),
    }
    return {key: round(value) for key, value in scores.items()}


def score_item(
    item: dict[str, Any], config: dict[str, Any], assessment: dict[str, Any] | None
) -> dict[str, Any]:
    base = {**item, "strategy_version": STRATEGY_VERSION}
    analysis = _object(item.get("analysis_result"))
    if item.get("status") != "completed" or not analysis:
        return {**base, "decision": "unscored", "gate_reason": "analysis_not_completed"}
    schema_version = analysis.get("analysis_schema_version")
    if schema_version != ANALYSIS_SCHEMA_VERSION:
        raise ValueError(f"Unsupported analysis schema version: {schema_version!r}")

    if assessment is None:
        return {
            **base,
            "decision": "post_hook_review_required",
            "gate_reason": "missing_post_assessment",
        }
    error = _assessment_error(assessment)
    if error:
        return {
            **base,
            "post_assessment": assessment,
            "decision": "post_hook_review_required",
            "gate_reason": error,
        }
    verdict = assessment["verdict"]
    if verdict == "does_not_qualify":
        return {
            **base,
            "post_assessment": assessment,
            "decision": "excluded",
            "gate_reason": "not_a_ugc_creator_hook",
        }
    if verdict == "uncertain" or assessment["confidence"] == "low":
        return {
            **base,
            "post_assessment": assessment,
            "decision": "post_hook_review_required",
            "gate_reason": (
                "uncertain_post_verdict" if verdict == "uncertain" else "low_assessment_confidence"
            ),
        }
    qualified_error = _qualified_assessment_error(assessment)
    if qualified_error:
        return {
            **base,
            "post_assessment": assessment,
            "decision": "post_hook_review_required",
            "gate_reason": qualified_error,
        }

    scores = _dimension_scores(analysis, assessment)
    weights = _object(config.get("weights"))
    weight_total = sum(float(weights.get(key, 0)) for key in scores)
    if weight_total <= 0:
        raise ValueError("Strategy weights must sum to a positive value")
    total = round(
        sum(scores[key] * float(weights.get(key, 0)) for key in scores) / weight_total
    )
    evidence_confidence = _object(analysis.get("evidence_quality")).get("confidence")
    if total >= int(config["recommend_threshold"]) and evidence_confidence != "low":
        decision = "recommended"
    elif total >= int(config["review_threshold"]):
        decision = "review"
    else:
        decision = "skip"
    return {
        **base,
        "post_assessment": assessment,
        "gate_reason": "qualified_ugc_creator_hook",
        "dimension_scores": scores,
        "score": total,
        "decision": decision,
    }


def _items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    root = _object(payload)
    data = _object(root.get("data"))
    result = (
        data
        if isinstance(data.get("items"), list)
        else _object(data.get("result")) or _object(root.get("result")) or root
    )
    return [item for item in _list(result.get("items")) if isinstance(item, dict)]


def _assessment_map(payload: Any) -> dict[str, dict[str, Any]]:
    root = _object(payload)
    version = root.get("assessment_schema_version")
    if version != ASSESSMENT_SCHEMA_VERSION:
        raise ValueError(f"Unsupported assessment schema version: {version!r}")
    result: dict[str, dict[str, Any]] = {}
    for raw in _list(root.get("items")):
        assessment = _object(raw)
        item_id = assessment.get("item_id")
        if not isinstance(item_id, str) or not item_id.strip():
            raise ValueError("Every post assessment requires a non-empty item_id")
        if item_id in result:
            raise ValueError(f"Duplicate post assessment item_id: {item_id}")
        result[item_id] = assessment
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", nargs="?", help="museoncli result JSON; defaults to stdin")
    parser.add_argument(
        "--post-assessments",
        help="host-Agent ugc-creator-hook-assessment.v1 JSON; missing entries fail closed",
    )
    parser.add_argument("--config", help="JSON file overriding default weights/thresholds")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    text = Path(args.input).read_text(encoding="utf-8") if args.input else sys.stdin.read()
    payload = json.loads(text)
    assessments: dict[str, dict[str, Any]] = {}
    if args.post_assessments:
        assessment_payload = json.loads(
            Path(args.post_assessments).read_text(encoding="utf-8")
        )
        assessments = _assessment_map(assessment_payload)
    config = json.loads(json.dumps(DEFAULT_CONFIG))
    if args.config:
        custom = json.loads(Path(args.config).read_text(encoding="utf-8"))
        config.update({key: value for key, value in custom.items() if key != "weights"})
        config["weights"].update(_object(custom.get("weights")))
    ranked = [
        score_item(item, config, assessments.get(str(item.get("id"))))
        for item in _items(payload)
    ]
    decision_order = {
        "recommended": 0,
        "review": 1,
        "skip": 2,
        "post_hook_review_required": 3,
        "excluded": 4,
        "unscored": 5,
    }
    ranked.sort(
        key=lambda item: (
            decision_order.get(str(item.get("decision")), 99),
            -int(item.get("score", -1)),
        )
    )
    json.dump(
        {"strategy_version": STRATEGY_VERSION, "items": ranked},
        sys.stdout,
        ensure_ascii=False,
        indent=2 if args.pretty else None,
    )
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
