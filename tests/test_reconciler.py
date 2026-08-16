"""Tests for reconciliation logic."""

from scorerift.reconciler import check_ratchet, classify_status, merge_weekly_score


class TestMergeWeeklyScore:
    def test_no_weekly_returns_daily(self):
        assert merge_weekly_score(0.85, None) == 0.85

    def test_fresh_weekly_blends_40_percent(self):
        result = merge_weekly_score(0.80, 1.0, weekly_age_days=0)
        assert abs(result - 0.88) < 0.01  # 0.80*0.6 + 1.0*0.4

    def test_old_weekly_decays_to_10_percent(self):
        result = merge_weekly_score(0.80, 1.0, weekly_age_days=10)
        assert abs(result - 0.82) < 0.01  # 0.80*0.9 + 1.0*0.1


class TestCheckRatchet:
    def test_no_ratchet_returns_none(self):
        assert check_ratchet("testing", 0.50, None) is None

    def test_above_ratchet_returns_none(self):
        assert check_ratchet("testing", 0.95, "A") is None

    def test_below_ratchet_returns_violation(self):
        v = check_ratchet("testing", 0.70, "A")
        assert v is not None
        assert v["ratchet_grade"] == "A"
        assert v["gap"] == 0.2


class TestClassifyStatus:
    def test_ok_when_aligned(self):
        assert classify_status(0.88, 0.90, confidence=0.95) == "ok"

    def test_warn_when_diverged_high_confidence(self):
        assert classify_status(0.60, 0.90, confidence=0.80) == "warn"

    def test_review_suggested_when_diverged_low_confidence(self):
        assert classify_status(0.60, 0.90, confidence=0.30) == "review_suggested"

    def test_fail_when_score_is_failing(self):
        assert classify_status(0.30, 0.90, confidence=0.95) == "fail"

    def test_ok_when_no_manual(self):
        assert classify_status(0.85, None, confidence=0.95) == "ok"

    def test_failing_score_low_confidence_is_review_not_fail(self):
        """An untrusted failing score can't hard-fail — flag for review instead."""
        assert classify_status(0.30, 0.90, confidence=0.30) == "review_suggested"

    def test_failing_score_zero_confidence_no_manual_is_review(self):
        """Tool-failure placeholder (0.5 at confidence 0.0) must not read as failing."""
        assert classify_status(0.5, None, confidence=0.0) == "review_suggested"
