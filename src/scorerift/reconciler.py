"""Reconciliation logic — weekly score merging and ratchet enforcement."""

from __future__ import annotations

import logging
from typing import Any

from scorerift.claims import (
    Claim,
    Divergence,
    classify_divergence,
)
from scorerift.grades import grade_to_score, is_failing

log = logging.getLogger("scorerift")


def merge_weekly_score(
    daily_score: float,
    weekly_score: float | None,
    weekly_age_days: int = 0,
) -> float:
    """Merge daily and weekly scores with decay-weighted blending.

    Weekly weight starts at 0.4 (fresh) and decays to 0.1 over 6 days.
    """
    if weekly_score is None:
        return daily_score
    weekly_weight = max(0.1, 0.4 - (weekly_age_days * 0.05))
    return daily_score * (1 - weekly_weight) + weekly_score * weekly_weight


def check_ratchet(
    dimension: str,
    auto_score: float,
    ratchet_grade: str | None,
) -> dict[str, Any] | None:
    """Check if a score violates its ratchet floor.

    Returns a violation dict if the score dropped below the ratchet, else None.
    """
    if ratchet_grade is None:
        return None
    ratchet_score = grade_to_score(ratchet_grade)
    if auto_score < ratchet_score:
        return {
            "dimension": dimension,
            "auto_score": auto_score,
            "ratchet_grade": ratchet_grade,
            "ratchet_score": ratchet_score,
            "gap": round(ratchet_score - auto_score, 3),
        }
    return None


def classify_status(
    auto_score: float,
    manual_score: float | None,
    confidence: float,
    divergence_threshold: float = 0.15,
    confidence_floor: float = 0.5,
) -> str:
    """Classify a dimension's reconciliation status.

    Returns one of: "ok", "warn", "review_suggested", "fail".
    """
    if is_failing(auto_score):
        # Below the confidence floor the score is not evidence of failure
        # (e.g. a neutral placeholder from a tool crash) — ask for review.
        if confidence >= confidence_floor:
            return "fail"
        return "review_suggested"
    if manual_score is None:
        return "ok"
    gap = abs(auto_score - manual_score)
    if gap > divergence_threshold:
        if confidence >= confidence_floor:
            return "warn"
        return "review_suggested"
    return "ok"


def classify_status_rich(
    auto_score: float,
    manual_score: float | None,
    confidence: float,
    dimension_name: str,
    *,
    auto_evidence: str = "",
    manual_evidence: str = "",
    file_path: str | None = None,
    last_review_timestamp: str | None = None,
    last_commit_timestamp: str | None = None,
    divergence_threshold: float = 0.15,
    confidence_floor: float = 0.5,
) -> tuple[str, Divergence | None]:
    """Enhanced classify_status that also returns a typed Divergence.

    Returns (status_string, divergence_or_none) where status_string is
    the same "ok"/"warn"/"review_suggested"/"fail" as classify_status().
    The Divergence provides gap_type, severity, and explanation.
    """
    status = classify_status(
        auto_score, manual_score, confidence,
        divergence_threshold, confidence_floor,
    )

    if manual_score is None:
        return status, None

    auto_claim = Claim(
        source="auto",
        dimension=dimension_name,
        statement=f"Auto score: {auto_score:.2f}",
        confidence=auto_score,
        evidence=auto_evidence,
        file_path=file_path,
    )
    manual_claim = Claim(
        source="manual",
        dimension=dimension_name,
        statement=f"Manual score: {manual_score:.2f}",
        confidence=manual_score,
        evidence=manual_evidence,
        file_path=file_path,
    )

    try:
        divergence = classify_divergence(
            auto_claim,
            manual_claim,
            last_review_timestamp=last_review_timestamp,
            last_commit_timestamp=last_commit_timestamp,
        )
    except Exception:
        log.warning("Failed to classify divergence for %s", dimension_name, exc_info=True)
        divergence = None

    return status, divergence
