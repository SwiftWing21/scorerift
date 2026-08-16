"""Tests for the core AuditEngine."""


import pytest

from scorerift import AuditEngine, Dimension, Tier


@pytest.fixture
def tmp_engine(tmp_path):
    """Create an engine with temp DB and sidecar."""
    db_path = str(tmp_path / "test_audit.db")
    baseline_path = str(tmp_path / "test_baseline.json")
    engine = AuditEngine(db_path=db_path, baseline_path=baseline_path)
    return engine


@pytest.fixture
def seeded_engine(tmp_engine):
    """Engine with two dimensions registered."""
    tmp_engine.register(Dimension(
        name="alpha",
        check=lambda: (0.85, {"passed": 85, "total": 100}),
        confidence=0.90,
        tier=Tier.LIGHT,
    ))
    tmp_engine.register(Dimension(
        name="beta",
        check=lambda: (0.60, {"note": "moderate"}),
        confidence=0.75,
        tier=Tier.MEDIUM,
    ))
    return tmp_engine


class TestRegistration:
    def test_register_dimension(self, tmp_engine):
        dim = Dimension(name="test", check=lambda: (1.0, {}), tier=Tier.LIGHT)
        tmp_engine.register(dim)
        assert "test" in tmp_engine.dimensions

    def test_register_many(self, tmp_engine):
        dims = [
            Dimension(name="a", check=lambda: (1.0, {})),
            Dimension(name="b", check=lambda: (0.5, {})),
        ]
        tmp_engine.register_many(dims)
        assert len(tmp_engine.dimensions) == 2

    def test_unregister(self, seeded_engine):
        seeded_engine.unregister("alpha")
        assert "alpha" not in seeded_engine.dimensions


class TestRunTier:
    def test_light_tier_runs_light_dimensions(self, seeded_engine):
        results = seeded_engine.run_tier("light")
        names = [r.name for r in results]
        assert "alpha" in names
        assert "beta" not in names  # beta is medium tier

    def test_medium_tier_includes_light(self, seeded_engine):
        results = seeded_engine.run_tier("medium")
        names = [r.name for r in results]
        assert "alpha" in names
        assert "beta" in names

    def test_scores_are_clamped(self, tmp_engine):
        tmp_engine.register(Dimension(
            name="over", check=lambda: (1.5, {}), tier=Tier.LIGHT,
        ))
        results = tmp_engine.run_tier("light")
        assert results[0].auto_score == 1.0

    def test_check_failure_returns_half(self, tmp_engine):
        """Failed checks return 0.5 (unknown), not 0.0 (failing)."""
        def broken():
            raise RuntimeError("boom")
        tmp_engine.register(Dimension(name="broken", check=broken, tier=Tier.LIGHT))
        results = tmp_engine.run_tier("light")
        assert results[0].auto_score == 0.5
        assert "error" in results[0].auto_detail


class TestReconciliation:
    def test_no_divergence_without_manual(self, seeded_engine):
        results = seeded_engine.run_tier("medium")
        assert all(not r.divergent for r in results)

    def test_divergence_detected(self, seeded_engine):
        # Set manual grade to S (1.0) for beta which auto-scores 0.60
        seeded_engine.sidecar.set_grade("beta", "S")
        results = seeded_engine.run_tier("medium")
        beta = [r for r in results if r.name == "beta"][0]
        assert beta.divergent is True

    def test_acknowledge_clears_divergence(self, seeded_engine):
        seeded_engine.sidecar.set_grade("beta", "S")
        seeded_engine.run_tier("medium")
        seeded_engine.acknowledge("beta")
        divs = seeded_engine.get_divergences()
        assert len(divs) == 0


class TestToolFailureConfidenceDrop:
    """Tool-failure samples carry no evidence — they must not trigger divergence.

    Repro: a 9-minute suite times out under the pytest check, the check returns
    a neutral placeholder, and the dimension's static confidence (0.95) would
    otherwise still mark it DIVERGED against the manual grade.
    """

    def test_error_detail_zeroes_confidence_and_divergence(self, tmp_engine):
        tmp_engine.register(Dimension(
            name="timed_out",
            check=lambda: (0.5, {"error": "pytest timed out after 120s", "timeout": True}),
            confidence=0.95,
            tier=Tier.LIGHT,
        ))
        tmp_engine.sidecar.set_grade("timed_out", "S")
        results = tmp_engine.run_tier("light")
        r = results[0]
        assert r.divergent is False
        assert r.auto_confidence == 0.0

    def test_check_exception_does_not_diverge(self, tmp_engine):
        def broken():
            raise RuntimeError("boom")
        tmp_engine.register(Dimension(
            name="broken", check=broken, confidence=0.95, tier=Tier.LIGHT,
        ))
        tmp_engine.sidecar.set_grade("broken", "S")
        results = tmp_engine.run_tier("light")
        assert results[0].divergent is False
        assert results[0].auto_confidence == 0.0

    def test_run_dimension_error_detail_does_not_diverge(self, tmp_engine):
        tmp_engine.register(Dimension(
            name="timed_out",
            check=lambda: (0.5, {"error": "pytest timed out after 120s", "timeout": True}),
            confidence=0.95,
            tier=Tier.LIGHT,
        ))
        tmp_engine.sidecar.set_grade("timed_out", "S")
        r = tmp_engine.run_dimension("timed_out")
        assert r.divergent is False
        assert r.auto_confidence == 0.0

    def test_healthy_check_keeps_its_confidence(self, tmp_engine):
        tmp_engine.register(Dimension(
            name="healthy", check=lambda: (0.9, {"passed": 9, "total": 10}),
            confidence=0.95, tier=Tier.LIGHT,
        ))
        results = tmp_engine.run_tier("light")
        assert results[0].auto_confidence == 0.95


class TestFeedback:
    def test_record_and_summarize(self, tmp_engine):
        tmp_engine.record_feedback(score=0.8, scope="overall", text="Looks good")
        tmp_engine.record_feedback(score=0.6, scope="session", text="Slow load")
        summary = tmp_engine.feedback_summary()
        assert summary["count"] == 2
        assert 0.6 <= summary["avg_score"] <= 0.8


class TestHealthCheck:
    def test_healthy_when_no_issues(self, tmp_engine):
        tmp_engine.register(Dimension(
            name="good", check=lambda: (0.90, {}), tier=Tier.LIGHT,
        ))
        tmp_engine.run_tier("light")
        health = tmp_engine.health_check()
        assert health["ok"] is True
        assert health["divergences"] == 0

    def test_unhealthy_with_failing_dimension(self, tmp_engine):
        tmp_engine.register(Dimension(
            name="failing", check=lambda: (0.30, {}), tier=Tier.LIGHT,
        ))
        tmp_engine.run_tier("light")
        health = tmp_engine.health_check()
        assert health["ok"] is False
        assert "failing" in health["failing"]


class TestRelativePathsWithTarget:
    def test_relative_db_resolves_against_invoke_cwd_not_target(self, tmp_path, monkeypatch):
        """A relative db_path must land in the invoking CWD, not inside target_path.

        run_tier chdirs into target_path; the lazily-opened DB and sidecar
        must not resolve their relative paths against the target directory.
        """
        invoke = tmp_path / "invoke"
        target = tmp_path / "target"
        invoke.mkdir()
        target.mkdir()
        monkeypatch.chdir(invoke)

        engine = AuditEngine(
            db_path="x.db",
            baseline_path="x.json",
            target_path=str(target),
        )
        engine.register(Dimension(
            name="alpha", check=lambda: (1.0, {}), tier=Tier.LIGHT,
        ))
        results = engine.run_tier("light")

        assert len(results) == 1
        assert (invoke / "x.db").exists()
        assert not (target / "x.db").exists()
