"""Tests for the self-evolving OODA loop."""

import json
import tempfile
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.evolution.tracker import PerformanceTracker, SignalVerification, PerformanceReport
from src.evolution.optimizer import WeightOptimizer, WeightConfig, DEFAULT_WEIGHTS, MIN_WEIGHT
from src.evolution.stock_pool import StockPoolManager, DEFAULT_WATCHLIST
from src.evolution.engine import EvolutionEngine, EvolutionReport


class TestPerformanceTracker:
    """Test signal verification against actual prices."""

    def test_signal_to_direction(self):
        assert PerformanceTracker._signal_to_direction("strong_buy") == "up"
        assert PerformanceTracker._signal_to_direction("buy") == "up"
        assert PerformanceTracker._signal_to_direction("sell") == "down"
        assert PerformanceTracker._signal_to_direction("strong_sell") == "down"
        assert PerformanceTracker._signal_to_direction("hold") is None

    def test_verify_signals_with_mock_prices(self):
        """Test verification logic with known outcomes."""
        tracker = PerformanceTracker()

        signals = [
            {"code": "000001", "name": "平安银行", "final_signal": "buy", "final_score": 0.5, "hard_score": 0.4, "soft_score": 0.3},
            {"code": "600519", "name": "贵州茅台", "final_signal": "sell", "final_score": -0.5, "hard_score": -0.3, "soft_score": -0.4},
            {"code": "000333", "name": "美的集团", "final_signal": "hold", "final_score": 0.0, "hard_score": 0.0, "soft_score": 0.0},
        ]

        # Mock price fetching
        with patch.object(tracker, '_fetch_actual_prices') as mock_fetch:
            mock_fetch.return_value = {
                "000001": {"close": 10.5, "pct_change": 2.0},   # went up, buy was correct
                "600519": {"close": 1800.0, "pct_change": 1.5},  # went up, sell was wrong
                "000333": {"close": 60.0, "pct_change": -0.3},   # flat, hold was fine
            }

            signal_date = date.today() - timedelta(days=1)
            report = tracker.verify_signals(signal_date, signals)

            assert report.total_signals == 3
            assert report.verified == 3
            assert report.win_count == 1  # 000001 buy → up = correct
            assert report.loss_count == 1  # 600519 sell → up = wrong
            assert report.hold_count == 1
            assert report.win_rate == 0.5  # 1/(1+1)

    def test_verify_signals_no_data(self):
        """Test when no price data is available."""
        tracker = PerformanceTracker()
        signals = [{"code": "999999", "name": "测试", "final_signal": "buy", "final_score": 0.5}]

        with patch.object(tracker, '_fetch_actual_prices', return_value={}):
            report = tracker.verify_signals(date.today() - timedelta(days=1), signals)
            assert report.verified == 0  # no data to verify
            assert report.total_signals == 1

    def test_save_performance_report(self):
        """Test saving report to SQLite."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            mock_db = MagicMock()
            mock_db.db_path = db_path

            report = PerformanceReport(
                trade_date="2026-05-26",
                total_signals=50, verified=48,
                win_count=30, loss_count=18, hold_count=2,
                win_rate=0.625, avg_return=0.5, sharpe_like=0.3,
                bullish_accuracy=0.7, bearish_accuracy=0.55,
            )

            tracker = PerformanceTracker()
            tracker.save_performance_report(mock_db, report)

            # Verify the table was created and data written
            import sqlite3
            conn = sqlite3.connect(str(db_path))
            rows = conn.execute("SELECT * FROM performance_history").fetchall()
            conn.close()
            assert len(rows) == 1
            assert rows[0][1] == 50  # total_signals


class TestWeightOptimizer:
    """Test dynamic weight optimization."""

    def test_default_weights(self):
        opt = WeightOptimizer()
        weights = opt.get_weights()
        assert abs(sum(weights.values()) - 1.0) < 0.01
        assert weights["hard"] == 0.40
        assert weights["soft"] == 0.25

    def test_optimize_with_performance(self):
        """Test weight adjustment based on performance report."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "weights.json"
            opt = WeightOptimizer(config_path=str(config_path))

            # Create a mock performance report with known layer accuracy
            perf = PerformanceReport(
                trade_date="2026-05-26",
                win_rate=0.6,
                verified=10,
                verifications=[
                    SignalVerification(
                        code="000001", name="平安银行",
                        signal_date="2026-05-25", predicted="buy",
                        predicted_score=0.5, actual_direction="up",
                        is_correct=True, next_change_pct=2.0,
                    )
                    for _ in range(6)  # 6 correct
                ] + [
                    SignalVerification(
                        code="600519", name="贵州茅台",
                        signal_date="2026-05-25", predicted="sell",
                        predicted_score=-0.5, actual_direction="up",
                        is_correct=False, next_change_pct=1.0,
                    )
                    for _ in range(4)  # 4 wrong
                ],
            )

            new_weights = opt.optimize(perf)
            assert abs(sum(new_weights.values()) - 1.0) < 0.01

            # All weights should respect minimum
            for k, v in new_weights.items():
                assert v >= MIN_WEIGHT, f"{k} weight {v} below minimum {MIN_WEIGHT}"

    def test_save_and_load_config(self):
        """Test config persistence."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "weights.json"
            opt = WeightOptimizer(config_path=str(config_path))

            opt.weights.hard = 0.50
            opt.weights.soft = 0.20
            opt.save_config()

            # Load fresh instance
            opt2 = WeightOptimizer(config_path=str(config_path))
            assert opt2.weights.hard == 0.50
            assert opt2.weights.soft == 0.20

    def test_reset_to_defaults(self):
        """Test resetting weights."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "weights.json"
            opt = WeightOptimizer(config_path=str(config_path))

            opt.weights.hard = 0.90
            opt.save_config()
            opt.reset_to_defaults()

            assert opt.weights.hard == 0.40
            assert opt.weights.soft == 0.25


class TestStockPoolManager:
    """Test dynamic stock pool management."""

    def test_load_default_watchlist(self):
        spm = StockPoolManager()
        assert len(spm.get_watchlist()) == 50
        assert "000001" in spm.get_watchlist()
        assert "600519" in spm.get_watchlist()

    def test_save_and_load_watchlist(self):
        """Test watchlist persistence."""
        with tempfile.TemporaryDirectory() as tmpdir:
            wl_path = Path(tmpdir) / "watchlist.json"
            spm = StockPoolManager(watchlist_path=str(wl_path))

            # Modify and save
            spm.watchlist.append("002594")
            spm.save_watchlist()

            # Load fresh instance
            spm2 = StockPoolManager(watchlist_path=str(wl_path))
            assert "002594" in spm2.get_watchlist()

    def test_analyze_pool(self):
        """Test pool analysis returns a report."""
        spm = StockPoolManager()
        report = spm.analyze_pool(db=None)
        assert report.pool_size == 50
        assert isinstance(report.stats, list)


class TestEvolutionEngine:
    """Test the full OODA loop orchestration."""

    def test_report_to_markdown(self):
        """Test markdown report generation."""
        report = EvolutionReport(
            cycle_id="evo-0001",
            date="2026-05-26",
            win_rate=0.62,
            avg_return=0.45,
            sharpe_like=0.3,
            signals_verified=48,
            old_weights={"hard": 0.40, "soft": 0.25},
            new_weights={"hard": 0.42, "soft": 0.23},
            weights_changed=True,
            pool_size=50,
            summary="测试进化报告",
            recommendations=["建议1", "建议2"],
        )

        md = report.to_markdown()
        assert "进化报告" in md
        assert "62.0%" in md
        assert "evo-0001" in md
        assert "建议1" in md

    def test_report_to_dict(self):
        """Test dict serialization."""
        report = EvolutionReport(
            cycle_id="evo-0001",
            date="2026-05-26",
            win_rate=0.62,
            new_weights={"hard": 0.40},
        )
        d = report.to_dict()
        assert d["cycle_id"] == "evo-0001"
        assert d["win_rate"] == 0.62

    def test_generate_summary(self):
        """Test summary generation."""
        engine = EvolutionEngine()

        report = EvolutionReport(
            signals_verified=48,
            win_rate=0.62,
            avg_return=0.5,
            weights_changed=True,
            evicted=[{"code": "000001"}],
            added=[{"code": "002594"}],
        )

        summary = engine._generate_summary(report)
        assert "48" in summary
        assert "62.0%" in summary
        assert "剔除" in summary
        assert "纳入" in summary

    def test_generate_recommendations_low_winrate(self):
        """Test recommendations when win rate is low."""
        engine = EvolutionEngine()

        report = EvolutionReport(
            win_rate=0.35,
            signals_verified=20,
            sharpe_like=-0.6,
        )
        recs = engine._generate_recommendations(report)
        assert any("胜率" in r for r in recs)
        assert any("夏普" in r for r in recs)
