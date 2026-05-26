"""PerformanceTracker — verify signals vs actual price moves.

Computes:
- Per-signal accuracy (did bullish stocks go up?)
- Overall win rate, Sharpe-like ratio
- Layer-level accuracy (hard vs soft vs gate)
- Per-stock prediction accuracy
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

import akshare as ak
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class SignalVerification:
    """Result of verifying one signal against actual price move."""
    code: str
    name: str
    signal_date: str
    predicted: str  # 'bullish' | 'bearish' | 'hold'
    predicted_score: float  # final_score from signal
    next_close: Optional[float] = None
    next_change_pct: Optional[float] = None
    actual_direction: Optional[str] = None  # 'up' | 'down' | 'flat'
    is_correct: Optional[bool] = None  # None for hold signals


@dataclass
class PerformanceReport:
    """Aggregate performance metrics."""
    trade_date: str
    total_signals: int = 0
    verified: int = 0
    win_count: int = 0
    loss_count: int = 0
    hold_count: int = 0
    win_rate: float = 0.0  # win / (win + loss)
    avg_return: float = 0.0
    sharpe_like: float = 0.0
    bullish_accuracy: float = 0.0
    bearish_accuracy: float = 0.0
    hard_signal_accuracy: Optional[float] = None
    soft_signal_accuracy: Optional[float] = None
    per_stock: dict = field(default_factory=dict)  # code -> {wins, losses, rate}
    verifications: list[SignalVerification] = field(default_factory=list)


class PerformanceTracker:
    """Track and verify signal accuracy against actual market data."""

    def __init__(self):
        self._cache: dict[str, pd.DataFrame] = {}

    def verify_signals(
        self,
        signal_date: date,
        signals: list[dict],
        db=None,
    ) -> PerformanceReport:
        """Verify a batch of signals against next-day actual prices.

        Args:
            signal_date: date when signals were generated
            signals: list of dicts with keys: code, name, final_signal,
                     final_score, hard_score, soft_score
            db: optional SignalDB for historical stats
        """
        report = PerformanceReport(trade_date=signal_date.isoformat())
        verify_date = signal_date + timedelta(days=1)
        next_trading = self._get_next_trading_day(verify_date)

        logger.info("Verifying %d signals from %s against %s",
                     len(signals), signal_date, next_trading)

        # Fetch actual prices for next trading day
        actual_prices = self._fetch_actual_prices(
            [s["code"] for s in signals], next_trading
        )

        for sig in signals:
            code = sig.get("code", "")
            name = sig.get("name", "")
            final_signal = sig.get("final_signal", "hold")
            final_score = sig.get("final_score", 0.0)
            hard_score = sig.get("hard_score", 0.0)
            soft_score = sig.get("soft_score", 0.0)

            ver = SignalVerification(
                code=code,
                name=name,
                signal_date=signal_date.isoformat(),
                predicted=final_signal,
                predicted_score=final_score,
            )

            actual = actual_prices.get(code)
            if actual is None:
                logger.debug("No price data for %s on %s", code, next_trading)
                report.total_signals += 1
                continue

            ver.next_close = float(actual.get("close", 0))
            ver.next_change_pct = float(actual.get("pct_change", 0))

            # Determine actual direction
            pct = ver.next_change_pct or 0
            if pct > 0.5:
                ver.actual_direction = "up"
            elif pct < -0.5:
                ver.actual_direction = "down"
            else:
                ver.actual_direction = "flat"

            # Check if prediction was correct
            predicted_dir = self._signal_to_direction(final_signal)
            if predicted_dir is None:
                ver.is_correct = None  # hold
                report.hold_count += 1
            elif predicted_dir == ver.actual_direction:
                ver.is_correct = True
                report.win_count += 1
            else:
                ver.is_correct = False
                report.loss_count += 1

            report.verified += 1
            report.total_signals += 1
            report.verifications.append(ver)

            # Per-stock stats
            if code not in report.per_stock:
                report.per_stock[code] = {"name": name, "wins": 0, "losses": 0, "rate": 0.0}
            if ver.is_correct is True:
                report.per_stock[code]["wins"] += 1
            elif ver.is_correct is False:
                report.per_stock[code]["losses"] += 1

        # Aggregate metrics
        total_decisions = report.win_count + report.loss_count
        if total_decisions > 0:
            report.win_rate = report.win_count / total_decisions

        if report.verified > 0:
            returns = [v.next_change_pct or 0 for v in report.verifications if v.next_change_pct is not None]
            if returns:
                report.avg_return = sum(returns) / len(returns)
                if len(returns) > 1:
                    std = (sum((r - report.avg_return) ** 2 for r in returns) / len(returns)) ** 0.5
                    report.sharpe_like = report.avg_return / std if std > 0 else 0

        # Bullish / bearish accuracy
        bullish = [v for v in report.verifications if v.predicted in ("strong_buy", "buy")]
        bearish = [v for v in report.verifications if v.predicted in ("strong_sell", "sell")]
        if bullish:
            correct = sum(1 for v in bullish if v.is_correct)
            report.bullish_accuracy = correct / len(bullish)
        if bearish:
            correct = sum(1 for v in bearish if v.is_correct)
            report.bearish_accuracy = correct / len(bearish)

        logger.info("Performance: %d verified, %.1f%% win rate, avg return %.2f%%",
                     report.verified, report.win_rate * 100, report.avg_return)
        return report

    def get_historical_performance(self, db, days: int = 20) -> list[PerformanceReport]:
        """Get performance reports for the last N trading days."""
        if db is None:
            return []

        from src.data.db_manager import SignalDB
        from datetime import datetime

        reports = []
        today = date.today()

        for i in range(1, days + 1):
            check_date = today - timedelta(days=i)
            signals = db.get_latest_signals(check_date, report_type="post")
            if not signals:
                continue

            signal_dicts = []
            for sig in signals:
                signal_dicts.append({
                    "code": sig.code,
                    "name": db.get_stock(sig.code).get("name", "") if db.get_stock(sig.code) else "",
                    "final_signal": sig.final_signal or "hold",
                    "final_score": sig.final_score or 0.0,
                    "hard_score": sig.hard_score or 0.0,
                    "soft_score": sig.soft_score or 0.0,
                })

            report = self.verify_signals(check_date, signal_dicts, db)
            if report.verified > 0:
                reports.append(report)

        return reports

    def save_performance_report(self, db, report: PerformanceReport):
        """Save performance metrics to DB for dashboard display."""
        if db is None:
            return

        data = {
            "date": report.trade_date,
            "total_signals": report.total_signals,
            "verified": report.verified,
            "win_count": report.win_count,
            "loss_count": report.loss_count,
            "hold_count": report.hold_count,
            "win_rate": round(report.win_rate, 4),
            "avg_return": round(report.avg_return, 4),
            "sharpe_like": round(report.sharpe_like, 4),
            "bullish_accuracy": round(report.bullish_accuracy, 4),
            "bearish_accuracy": round(report.bearish_accuracy, 4),
        }

        try:
            import sqlite3
            db_path = db.db_path if hasattr(db, 'db_path') else "data/signals.db"
            conn = sqlite3.connect(str(db_path))
            conn.execute("""
                CREATE TABLE IF NOT EXISTS performance_history (
                    date TEXT PRIMARY KEY,
                    total_signals INTEGER DEFAULT 0,
                    verified INTEGER DEFAULT 0,
                    win_count INTEGER DEFAULT 0,
                    loss_count INTEGER DEFAULT 0,
                    hold_count INTEGER DEFAULT 0,
                    win_rate REAL DEFAULT 0,
                    avg_return REAL DEFAULT 0,
                    sharpe_like REAL DEFAULT 0,
                    bullish_accuracy REAL DEFAULT 0,
                    bearish_accuracy REAL DEFAULT 0,
                    created_at TEXT DEFAULT (datetime('now'))
                )
            """)
            conn.execute("""
                INSERT INTO performance_history (
                    date, total_signals, verified, win_count, loss_count, hold_count,
                    win_rate, avg_return, sharpe_like, bullish_accuracy, bearish_accuracy
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(date) DO UPDATE SET
                    total_signals = excluded.total_signals,
                    verified = excluded.verified,
                    win_count = excluded.win_count,
                    loss_count = excluded.loss_count,
                    hold_count = excluded.hold_count,
                    win_rate = excluded.win_rate,
                    avg_return = excluded.avg_return,
                    sharpe_like = excluded.sharpe_like,
                    bullish_accuracy = excluded.bullish_accuracy,
                    bearish_accuracy = excluded.bearish_accuracy
            """, (
                data["date"], data["total_signals"], data["verified"],
                data["win_count"], data["loss_count"], data["hold_count"],
                data["win_rate"], data["avg_return"], data["sharpe_like"],
                data["bullish_accuracy"], data["bearish_accuracy"],
            ))
            conn.commit()
            conn.close()
            logger.info("Saved performance report for %s", report.trade_date)
        except Exception as e:
            logger.error("Failed to save performance report: %s", e)

    # ── Private helpers ──────────────────────────────────────────

    def _get_next_trading_day(self, from_date: date) -> date:
        """Find next trading day (skip weekends)."""
        d = from_date
        while d.weekday() >= 5:  # Saturday=5, Sunday=6
            d += timedelta(days=1)
        return d

    def _fetch_actual_prices(self, codes: list[str], target_date: date) -> dict[str, dict]:
        """Fetch actual OHLCV for a list of stocks on target date.

        Returns: {code: {"close": float, "pct_change": float}}
        """
        results = {}
        target_str = target_date.strftime("%Y%m%d")

        for code in codes:
            try:
                df = ak.stock_zh_a_hist(
                    symbol=code, period="daily",
                    start_date=target_str, end_date=target_str, adjust="qfq"
                )
                if df is not None and not df.empty:
                    row = df.iloc[0]
                    close = float(row.get("收盘", 0))
                    pct = float(row.get("涨跌幅", 0))
                    results[code] = {"close": close, "pct_change": pct}
            except Exception as e:
                logger.debug("Failed to fetch price for %s: %s", code, e)

        return results

    @staticmethod
    def _signal_to_direction(signal: str) -> Optional[str]:
        """Map signal to expected direction."""
        if signal in ("strong_buy", "buy"):
            return "up"
        elif signal in ("strong_sell", "sell"):
            return "down"
        return None  # hold
