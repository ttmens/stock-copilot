"""Tests for Signal Postmortem module."""

import pytest
from datetime import date, timedelta

from src.data.db_manager import SignalDB, SignalPostmortem
from src.evolution.postmortem import (
    PostmortemRecorder,
    _map_direction,
    _generate_signal_id,
)


@pytest.fixture
def db():
    return SignalDB(":memory:")


@pytest.fixture
def recorder(db):
    return PostmortemRecorder(db)


class TestDirectionMapping:
    def test_buy_signals(self):
        assert _map_direction("strong_buy") == "buy"
        assert _map_direction("buy") == "buy"

    def test_sell_signals(self):
        assert _map_direction("strong_sell") == "sell"
        assert _map_direction("sell") == "sell"

    def test_hold_signal(self):
        assert _map_direction("hold") == "hold"

    def test_unknown_defaults_to_hold(self):
        assert _map_direction("unknown") == "hold"


class TestSignalId:
    def test_generates_consistent_id(self):
        id1 = _generate_signal_id("600519", "2026-05-30", 0.5)
        id2 = _generate_signal_id("600519", "2026-05-30", 0.5)
        assert id1 == id2

    def test_different_params_different_id(self):
        id1 = _generate_signal_id("600519", "2026-05-30", 0.5)
        id2 = _generate_signal_id("600519", "2026-05-31", 0.5)
        assert id1 != id2

    def test_id_format(self):
        sig_id = _generate_signal_id("600519", "2026-05-30", 0.5)
        assert sig_id.startswith("sig_600519_")


class TestRecordSignal:
    def test_record_and_retrieve(self, recorder, db):
        sig_id = recorder.record_signal(
            code="600519",
            signal_date="2026-05-30",
            final_signal="buy",
            fusion_score=0.45,
            hard_score=0.3,
            soft_score=0.2,
            gate_score=0.8,
            dragon_tiger_score=0.1,
            announcement_score=0.0,
            consensus_bonus=0.05,
            contradiction_flags=[],
            market_regime="bull",
        )
        assert sig_id.startswith("sig_600519_")

        postmortems = db.get_postmortems(days=60)
        assert len(postmortems) == 1
        assert postmortems[0]["ticker"] == "600519"
        assert postmortems[0]["outcome_category"] is None  # not yet matured

    def test_record_with_contradictions(self, recorder, db):
        contra = [{"type": "hard_vs_soft", "severity": "high"}]
        recorder.record_signal(
            code="000001",
            signal_date="2026-05-30",
            final_signal="buy",
            fusion_score=0.3,
            contradiction_flags=contra,
        )
        postmortems = db.get_postmortems(days=60)
        assert len(postmortems[0]["contradiction_flags"]) == 1


class TestClassifyOutcome:
    def test_buy_true_positive(self, recorder):
        assert recorder.classify_outcome("buy", 3.0) == "true_positive"

    def test_buy_false_positive(self, recorder):
        assert recorder.classify_outcome("buy", -3.0) == "false_positive"

    def test_sell_true_positive(self, recorder):
        assert recorder.classify_outcome("sell", -3.0) == "true_positive"

    def test_sell_false_positive(self, recorder):
        assert recorder.classify_outcome("sell", 3.0) == "false_positive"

    def test_hold_true_positive(self, recorder):
        assert recorder.classify_outcome("hold", 0.5) == "true_positive"

    def test_hold_regime_mismatch_bull(self, recorder):
        result = recorder.classify_outcome("hold", 5.0, market_regime="bull")
        assert result == "regime_mismatch"

    def test_hold_regime_mismatch_bear(self, recorder):
        result = recorder.classify_outcome("hold", -5.0, market_regime="bear")
        assert result == "regime_mismatch"


class TestGenerateFeedback:
    def test_empty_feedback(self, recorder):
        feedback = recorder.generate_feedback(days=30)
        assert feedback["total_matured"] == 0
        assert feedback["overall_win_rate"] is None

    def test_feedback_with_data(self, recorder, db):
        # Record and manually mature a signal
        recorder.record_signal(
            code="600519",
            signal_date="2026-05-01",  # old date, will be matured
            final_signal="buy",
            fusion_score=0.5,
        )
        # Manually update to simulate matured
        pm = SignalPostmortem(
            signal_id=_generate_signal_id("600519", "2026-05-01", 0.5),
            ticker="600519",
            signal_date="2026-05-01",
            predicted_direction="buy",
            fusion_score=0.5,
            actual_return_5d=3.0,
            actual_return_20d=5.0,
            outcome_category="true_positive",
        )
        db.save_postmortem(pm)

        feedback = recorder.generate_feedback(days=60)
        assert feedback["total_matured"] == 1
        assert feedback["overall_win_rate"] == 1.0


class TestGetSummary:
    def test_empty_summary(self, recorder):
        summary = recorder.get_summary(days=30)
        assert summary["total_signals"] == 0
        assert summary["matured"] == 0

    def test_summary_with_data(self, recorder, db):
        recorder.record_signal(
            code="600519",
            signal_date="2026-05-30",
            final_signal="buy",
            fusion_score=0.5,
        )
        summary = recorder.get_summary(days=30)
        assert summary["total_signals"] == 1
        assert summary["matured"] == 0
        assert summary["immature"] == 1
