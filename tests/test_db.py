"""Tests for the audit database layer."""

import pytest

from scorerift.db import AuditDB


@pytest.fixture
def db(tmp_path):
    return AuditDB(str(tmp_path / "test.db"))


class TestAuditDB:
    def test_schema_created(self, db):
        counts = db.row_count()
        assert counts["audit_scores"] == 0
        assert counts["user_feedback"] == 0

    def test_write_and_read_feedback(self, db):
        row_id = db.write_feedback(score=0.8, scope="overall", text="Nice work")
        assert row_id > 0
        summary = db.feedback_summary()
        assert summary["count"] == 1
        assert summary["avg_score"] == 0.8

    def test_score_history_empty(self, db):
        history = db.score_history(days=30)
        assert history == []

    def test_acknowledge_missing_dimension(self, db):
        # Should not raise
        db.acknowledge("nonexistent")
        assert db.is_acknowledged("nonexistent") is False

    def test_write_score_roundtrip(self, db):
        from scorerift.engine import DimensionResult
        result = DimensionResult(
            name="test_dim", auto_score=0.85, auto_detail={"ok": True},
            auto_confidence=0.9, manual_grade="A", manual_score=0.9,
            divergent=False, acknowledged=False, tier="light",
            timestamp="2026-04-02T00:00:00",
        )
        db.write_score(result)
        scores = db.latest_scores()
        assert len(scores) == 1
        assert scores[0].name == "test_dim"
        assert scores[0].auto_score == 0.85
        assert scores[0].manual_grade == "A"

    def test_score_history_filter(self, db):
        import time

        from scorerift.engine import DimensionResult
        # Dynamic timestamp: a hardcoded date rots out of the 30-day window
        ts = time.strftime("%Y-%m-%dT%H:%M:%S")
        for name, score in [("alpha", 0.9), ("beta", 0.7)]:
            db.write_score(DimensionResult(
                name=name, auto_score=score, auto_detail={},
                auto_confidence=0.8, manual_grade=None, manual_score=None,
                divergent=False, acknowledged=False, tier="light",
                timestamp=ts,
            ))
        history = db.score_history(dimension="alpha", days=30)
        assert len(history) == 1
        assert history[0]["dimension"] == "alpha"

    def test_close(self, db):
        db.close()
        # Should be able to reconnect after close
        assert db.row_count()["audit_scores"] == 0
