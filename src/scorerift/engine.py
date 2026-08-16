"""Core audit engine — dimension registry, scoring, reconciliation."""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from scorerift.db import AuditDB
from scorerift.grades import grade_to_score, is_failing, score_to_grade
from scorerift.reconciler import check_ratchet, classify_status, classify_status_rich
from scorerift.sidecar import Sidecar
from scorerift.tiers import DEFAULT_SCHEDULES, Tier

if TYPE_CHECKING:
    from collections.abc import Callable

    from scorerift.claims import Divergence

# Lock to prevent concurrent os.chdir races in run_tier/run_dimension
_chdir_lock = threading.Lock()

log = logging.getLogger("scorerift")

# Default divergence threshold: flag when auto and manual disagree by > 0.15
# AND auto-confidence is high enough to trust the automated score.
DIVERGENCE_THRESHOLD = 0.15
CONFIDENCE_FLOOR = 0.5


@dataclass
class Dimension:
    """A single auditable dimension.

    Args:
        name: Unique identifier (e.g. "test_coverage", "security").
        check: Callable that returns (score: float 0.0-1.0, detail: dict).
        confidence: How much to trust the auto score (0.0-1.0).
        tier: Minimum tier required to run this check.
        description: Human-readable description.
    """

    name: str
    check: Callable[[], tuple[float, dict[str, Any]]]
    confidence: float = 0.75
    tier: Tier = Tier.LIGHT
    description: str = ""


@dataclass
class DimensionResult:
    """Result of scoring a single dimension."""

    name: str
    auto_score: float
    auto_detail: dict[str, Any]
    auto_confidence: float
    manual_grade: str | None
    manual_score: float | None
    divergent: bool
    acknowledged: bool
    tier: str
    timestamp: str = ""
    ratchet_violation: dict[str, Any] | None = None
    divergence_detail: Divergence | None = None
    # Ray tracing fields (WS-1: populated by AuditEngine.ray_trace())
    interaction_delta: float | None = None
    combined_score: float | None = None
    ci_95: tuple[float, float] | None = None


@dataclass
class AuditEngine:
    """Main entry point — register dimensions, run tiers, reconcile.

    Args:
        db_path: Path to SQLite database file.
        baseline_path: Path to audit_baseline.json sidecar.
        divergence_threshold: Max allowed gap before flagging divergence.
        confidence_floor: Minimum auto-confidence to trigger divergence.
    """

    db_path: str = "audit.db"
    baseline_path: str = "audit_baseline.json"
    divergence_threshold: float = DIVERGENCE_THRESHOLD
    confidence_floor: float = CONFIDENCE_FLOOR
    target_path: str = "."
    _dimensions: dict[str, Dimension] = field(default_factory=dict, init=False, repr=False)
    _db: AuditDB | None = field(default=None, init=False, repr=False)
    _sidecar: Sidecar | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self.target_path = str(Path(self.target_path).resolve())
        # Resolve DB/sidecar paths now: run_tier/run_dimension chdir into
        # target_path, and the lazily-opened DB would otherwise resolve a
        # relative path against the target instead of the invoking CWD.
        self.db_path = str(Path(self.db_path).resolve())
        self.baseline_path = str(Path(self.baseline_path).resolve())

    @property
    def db(self) -> AuditDB:
        if self._db is None:
            self._db = AuditDB(self.db_path)
        return self._db

    @property
    def sidecar(self) -> Sidecar:
        if self._sidecar is None:
            self._sidecar = Sidecar(self.baseline_path)
        return self._sidecar

    # ── Registration ─────────────────────────────────────────────────

    def register(self, dim: Dimension) -> None:
        """Register a dimension for auditing."""
        self._dimensions[dim.name] = dim

    def register_many(self, dims: list[Dimension]) -> None:
        """Register multiple dimensions at once."""
        for d in dims:
            self.register(d)

    def unregister(self, name: str) -> None:
        """Remove a dimension from the registry."""
        self._dimensions.pop(name, None)

    @property
    def dimensions(self) -> dict[str, Dimension]:
        """All registered dimensions."""
        return dict(self._dimensions)

    # ── Scoring ──────────────────────────────────────────────────────

    def run_tier(self, tier: Tier | str) -> list[DimensionResult]:
        """Run all dimensions at or below the given tier.

        Returns a list of DimensionResult with reconciliation status.
        """
        if isinstance(tier, str):
            tier = Tier(tier)

        baseline = self.sidecar.load()
        results: list[DimensionResult] = []
        ts = time.strftime("%Y-%m-%dT%H:%M:%S")

        with _chdir_lock:
            old_cwd = os.getcwd()
            try:
                os.chdir(self.target_path)
                for name, dim in self._dimensions.items():
                    if not tier.includes(dim.tier):
                        continue

                    try:
                        auto_score, auto_detail = dim.check()
                        auto_score = max(0.0, min(1.0, auto_score))
                    except Exception as exc:
                        log.warning("Dimension %s check failed: %s", name, exc)
                        auto_score = 0.5
                        auto_detail = {"error": str(exc)}

                    # Reconciliation via classify_status
                    manual_entry = baseline.get("dimensions", {}).get(name, {})
                    manual_grade = manual_entry.get("grade")
                    manual_score = grade_to_score(manual_grade) if manual_grade else None
                    status = classify_status(
                        auto_score, manual_score, dim.confidence,
                        self.divergence_threshold, self.confidence_floor,
                    )
                    divergent = status in ("warn", "fail")
                    acknowledged = self.db.is_acknowledged(name)
                    ratchet_grade = self.sidecar.get_ratchet(name)
                    ratchet_violation = check_ratchet(name, auto_score, ratchet_grade)

                    # Rich divergence detail
                    manual_evidence = manual_entry.get("notes", "")
                    _status_rich, divergence_detail = classify_status_rich(
                        auto_score, manual_score, dim.confidence, name,
                        auto_evidence=str(auto_detail),
                        manual_evidence=manual_evidence,
                        divergence_threshold=self.divergence_threshold,
                        confidence_floor=self.confidence_floor,
                    )

                    result = DimensionResult(
                        name=name,
                        auto_score=auto_score,
                        auto_detail=auto_detail,
                        auto_confidence=dim.confidence,
                        manual_grade=manual_grade,
                        manual_score=manual_score,
                        divergent=divergent,
                        acknowledged=acknowledged,
                        tier=tier.value,
                        timestamp=ts,
                        ratchet_violation=ratchet_violation,
                        divergence_detail=divergence_detail,
                    )
                    results.append(result)
                    self.db.write_score(result)
            finally:
                os.chdir(old_cwd)

        return results

    def run_dimension(self, name: str) -> DimensionResult | None:
        """Run a single dimension regardless of tier. Returns None if not found."""
        dim = self._dimensions.get(name)
        if dim is None:
            return None
        baseline = self.sidecar.load()
        ts = time.strftime("%Y-%m-%dT%H:%M:%S")

        with _chdir_lock:
            old_cwd = os.getcwd()
            try:
                os.chdir(self.target_path)
                auto_score, auto_detail = dim.check()
                auto_score = max(0.0, min(1.0, auto_score))
            except Exception as exc:
                log.warning("Dimension %s check failed: %s", name, exc)
                auto_score = 0.5
                auto_detail = {"error": str(exc)}
            finally:
                os.chdir(old_cwd)

        manual_entry = baseline.get("dimensions", {}).get(name, {})
        manual_grade = manual_entry.get("grade")
        manual_score = grade_to_score(manual_grade) if manual_grade else None
        status = classify_status(
            auto_score, manual_score, dim.confidence,
            self.divergence_threshold, self.confidence_floor,
        )
        divergent = status in ("warn", "fail")

        # Rich divergence detail
        manual_evidence = manual_entry.get("notes", "")
        _status_rich, divergence_detail = classify_status_rich(
            auto_score, manual_score, dim.confidence, name,
            auto_evidence=str(auto_detail),
            manual_evidence=manual_evidence,
            divergence_threshold=self.divergence_threshold,
            confidence_floor=self.confidence_floor,
        )

        result = DimensionResult(
            name=name,
            auto_score=auto_score,
            auto_detail=auto_detail,
            auto_confidence=dim.confidence,
            manual_grade=manual_grade,
            manual_score=manual_score,
            divergent=divergent,
            acknowledged=self.db.is_acknowledged(name),
            tier="single",
            timestamp=ts,
            divergence_detail=divergence_detail,
        )
        self.db.write_score(result)
        return result

    # ── Reconciliation ───────────────────────────────────────────────

    def get_divergences(self, *, include_acknowledged: bool = False) -> list[DimensionResult]:
        """Return all dimensions with active divergences."""
        return self.db.get_divergences(include_acknowledged=include_acknowledged)

    def acknowledge(self, dimension: str) -> None:
        """Acknowledge a divergence (dismiss without changing grade)."""
        self.db.acknowledge(dimension)

    # ── LLM Review ────────────────────────────────────────────────────

    def review_dimension(
        self,
        dimension: str,
        context: str,
        mode: str = "consensus",
    ) -> dict[str, Any]:
        """Trigger an LLM review and update the manual grade in the sidecar.

        Modes:
            "single" — one provider, one pass
            "swarm" — one provider, 4 specialized lenses + cross-validation
            "consensus" — all available providers, compare scores

        Returns the review result dict. Also writes to sidecar with
        source="llm_review".
        """
        from scorerift.reviewers.cache import ReviewCache
        from scorerift.reviewers.consensus import consensus_review
        from scorerift.reviewers.oss_review import oss_review, swarm_review

        cache = ReviewCache(db_path=self.db_path)

        if mode == "swarm":
            result = swarm_review(dimension, context)
        elif mode == "consensus":
            result = consensus_review(dimension, context, cache=cache)
        else:
            r = oss_review(dimension, context)
            result = {
                "grade": r.grade, "score": r.score, "confidence": r.confidence,
                "findings": r.findings, "recommendations": r.recommendations,
                "cost_usd": r.cost_usd, "model": r.model, "provider": r.provider,
            }

        # Normalize keys (consensus uses different names)
        grade = result.get("grade") or result.get("consensus_grade", "C")
        confidence = result.get("confidence") or result.get("agreement", 0.5)
        findings = result.get("findings") or result.get("merged_findings", [])
        cost = result.get("cost_usd") or result.get("total_cost_usd", 0)

        # Write to sidecar
        self.sidecar.set_grade(
            dimension=dimension,
            grade=grade,
            source="llm_review",
            notes=f"Mode: {mode}, findings: {len(findings)}, cost: ${cost:.4f}",
            confidence=confidence,
            findings=findings[:10],  # keep top 10 in sidecar
        )

        return result

    # ── Feedback ─────────────────────────────────────────────────────

    def record_feedback(
        self,
        score: float,
        scope: str = "overall",
        text: str | None = None,
        session_id: str | None = None,
        actor: str | None = None,
    ) -> int:
        """Record user feedback. Returns the feedback row ID."""
        return self.db.write_feedback(
            score=max(0.0, min(1.0, score)),
            scope=scope,
            text=text,
            session_id=session_id,
            actor=actor,
        )

    def feedback_summary(self) -> dict[str, Any]:
        """Aggregated feedback statistics."""
        return self.db.feedback_summary()

    # ── Status ───────────────────────────────────────────────────────

    def latest_scores(self) -> list[DimensionResult]:
        """Get the most recent score for each dimension."""
        return self.db.latest_scores()

    def overall_score(self) -> float:
        """Weighted average of latest auto scores (equal weight)."""
        scores = self.latest_scores()
        if not scores:
            return 0.0
        return sum(r.auto_score for r in scores) / len(scores)

    def overall_grade(self) -> str:
        """Letter grade for the overall score."""
        return score_to_grade(self.overall_score())

    def health_check(self) -> dict[str, Any]:
        """Quick health summary for CI/smoke test integration.

        Returns:
            {ok, grade, score, divergences, failing, ratchet_violations}
        """
        scores = self.latest_scores()
        divergences = self.get_divergences()
        failing = [r.name for r in scores if is_failing(r.auto_score)]
        ratchet_violations = [r.name for r in scores if r.ratchet_violation]
        overall = self.overall_score()

        return {
            "ok": len(failing) == 0 and len(divergences) == 0,
            "grade": score_to_grade(overall),
            "score": round(overall, 3),
            "divergences": len(divergences),
            "failing": failing,
            "ratchet_violations": ratchet_violations,
        }

    # ── Scheduling ───────────────────────────────────────────────────

    def run_scheduled(self, *, hour: int, minute: int, weekday: int) -> list[DimensionResult] | None:
        """Run the tier matching the current schedule, if any.

        Called by external schedulers (cron, Task Scheduler, or Studio).
        Returns results if a tier matched, None otherwise.
        """
        for sched in DEFAULT_SCHEDULES:
            if sched.matches(hour=hour, minute=minute, weekday=weekday):
                log.info("Scheduled %s tier triggered", sched.tier.value)
                return self.run_tier(sched.tier)
        return None

    # ── Ray Tracing (WS-1: cross-dimension interaction scoring) ────

    def ray_trace(
        self,
        graph: "InteractionGraph",
        seed: int = 0,
    ) -> "RayTraceReport":
        """Run evidence ray tracing on the latest scores.

        Produces interaction_delta modifiers for each dimension and
        enriches the latest DimensionResults with combined_score + CI.

        Args:
            graph: InteractionGraph built via build_graph()
            seed: Fixed seed for reproducibility (default 0)

        Returns:
            RayTraceReport with per-dimension results.
        """
        from scorerift.ray_trace import ray_trace as _ray_trace, RayTraceReport, InteractionGraph

        scores_dict = {
            r.name: r.auto_score
            for r in self.latest_scores()
        }
        if not scores_dict:
            # No scores to trace — return empty report
            return _ray_trace({}, graph, seed=seed)

        report = _ray_trace(scores_dict, graph, seed=seed)

        # Enrich the cached latest scores with ray trace results
        for result in self.latest_scores():
            if result.name in report.results:
                rt = report.results[result.name]
                result.interaction_delta = rt.interaction_delta
                result.combined_score = rt.combined_score
                result.ci_95 = rt.ci_95

        return report

    def connection_score(self, graph: "InteractionGraph", seed: int = 0) -> float:
        """Overall score using connection-scope (ray-trace adjusted).

        Like overall_score() but uses combined_score instead of auto_score.
        """
        report = self.ray_trace(graph, seed=seed)
        if not report.results:
            return 0.0
        return report.connection_overall

    # ── Tension Map ──────────────────────────────────────────────────

    def tension_report(self) -> str:
        """Generate a Tension Map from the latest scores."""
        from scorerift.claims import tension_report as _tension_report

        scores = self.latest_scores()
        divergences = [
            r.divergence_detail for r in scores
            if r.divergence_detail is not None
        ]
        return _tension_report(divergences)

    # ── Lifecycle ────────────────────────────────────────────────────

    def close(self) -> None:
        """Close DB connections and release resources."""
        if self._db is not None:
            self._db.close()
            self._db = None
