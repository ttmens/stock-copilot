"""Signal Postmortem — 逐信号结果记录与 outcome 分类（Phase F）.

记录每个交易信号的预测方向，延迟比对实际涨跌，
分类为 true_positive / false_positive / missed_opportunity / regime_mismatch，
并生成反馈给融合权重和 Agent 的调整建议。
"""

import logging
import hashlib
from datetime import datetime, date, timedelta
from typing import Optional

from src.data.db_manager import SignalDB, SignalPostmortem
from src.data.fetcher import DataFetcher

logger = logging.getLogger(__name__)

# ── Signal direction mapping ─────────────────────────────────────────

_DIRECTION_MAP = {
    "strong_buy": "buy",
    "buy": "buy",
    "hold": "hold",
    "sell": "sell",
    "strong_sell": "sell",
}


def _map_direction(signal_label: str) -> str:
    """将 final_signal 映射为 buy/sell/hold."""
    return _DIRECTION_MAP.get(signal_label, "hold")


def _generate_signal_id(code: str, signal_date: str, score: float) -> str:
    """生成唯一 signal_id."""
    raw = f"{code}_{signal_date}_{score}"
    hash_prefix = hashlib.md5(raw.encode()).hexdigest()[:6]
    return f"sig_{code}_{signal_date}_{hash_prefix}"


# ── PostmortemRecorder ───────────────────────────────────────────────

class PostmortemRecorder:
    """记录和分析信号结果."""

    def __init__(self, db: SignalDB):
        self.db = db

    def record_signal(
        self,
        code: str,
        signal_date: str,
        final_signal: str,
        fusion_score: float,
        hard_score: float = 0.0,
        soft_score: float = 0.0,
        gate_score: float = 0.0,
        dragon_tiger_score: float = 0.0,
        announcement_score: float = 0.0,
        consensus_bonus: float = 0.0,
        contradiction_flags: list[dict] | None = None,
        market_regime: str = "unknown",
    ) -> str:
        """从当日分析结果创建 postmortem 记录，返回 signal_id."""
        import json

        signal_id = _generate_signal_id(code, signal_date, fusion_score)
        predicted_direction = _map_direction(final_signal)

        postmortem = SignalPostmortem(
            signal_id=signal_id,
            ticker=code,
            signal_date=signal_date,
            predicted_direction=predicted_direction,
            fusion_score=fusion_score,
            hard_score=hard_score,
            soft_score=soft_score,
            gate_score=gate_score,
            dragon_tiger_score=dragon_tiger_score,
            announcement_score=announcement_score,
            consensus_bonus=consensus_bonus,
            contradiction_flags=contradiction_flags or [],
            market_regime=market_regime,
            recorded_at=datetime.now().isoformat(),
        )

        self.db.save_postmortem(postmortem)
        logger.info("Recorded postmortem: %s (%s → %s)", signal_id, code, predicted_direction)
        return signal_id

    def classify_outcome(
        self,
        predicted_direction: str,
        actual_return: float,
        market_regime: str = "unknown",
        expected_direction: str | None = None,
    ) -> str:
        """分类信号结果.

        Args:
            predicted_direction: buy / sell / hold
            actual_return: 实际涨跌幅（百分比，如 +3.2 表示涨 3.2%）
            market_regime: bull / choppy / bear
            expected_direction: 在 bull 市场中预期涨，bear 市场中预期跌
        """
        threshold = 1.0  # 1% 阈值

        if predicted_direction == "buy":
            if actual_return > threshold:
                return "true_positive"
            elif actual_return < -threshold:
                return "false_positive"
            else:
                return "missed_opportunity"  # 涨跌不明显

        elif predicted_direction == "sell":
            if actual_return < -threshold:
                return "true_positive"
            elif actual_return > threshold:
                return "false_positive"
            else:
                return "missed_opportunity"

        else:  # hold
            if abs(actual_return) < 2.0:
                return "true_positive"  # 确实不该动
            else:
                # 如果市场 regime 与信号方向冲突
                if market_regime == "bull" and actual_return > 2.0:
                    return "regime_mismatch"  # 牛市中看空错过涨幅
                elif market_regime == "bear" and actual_return < -2.0:
                    return "regime_mismatch"  # 熊市中看多错过跌幅
                else:
                    return "false_positive"

    def check_mature_signals(
        self,
        as_of: str | None = None,
    ) -> dict:
        """检查已到期的信号，填入实际收益并分类.

        使用 signals 表中的历史数据估算收益。
        对于 signal_date + 7 个日历日已到的信号，通过 momentum_5d 推算。
        """
        import json

        check_date = as_of or date.today().isoformat()
        check_dt = date.fromisoformat(check_date)

        # 获取所有未分类的记录
        all_postmortems = self.db.get_postmortems(days=60)
        immature = [p for p in all_postmortems if p.get("outcome_category") is None]

        updated = 0
        errors = 0
        skipped = 0

        for pm in immature:
            signal_dt = date.fromisoformat(pm["signal_date"])
            days_elapsed = (check_dt - signal_dt).days

            # 至少需要 7 个日历日
            if days_elapsed < 7:
                skipped += 1
                continue

            ticker = pm["ticker"]
            signal_date = pm["signal_date"]

            try:
                # 从 signals 表获取历史信号
                history = self.db.get_history(ticker, days=days_elapsed + 10)
                if not history:
                    skipped += 1
                    continue

                # 找到信号日期附近的记录
                signal_rec = None
                current_rec = history[0]  # 最新的记录

                for rec in history:
                    if str(rec.trade_date) == signal_date:
                        signal_rec = rec
                        break

                if signal_rec is None:
                    # 找最接近的
                    for rec in history:
                        diff = abs((rec.trade_date - signal_dt).days)
                        if diff <= 2:
                            signal_rec = rec
                            break

                if signal_rec is None:
                    skipped += 1
                    continue

                # 从 signals 表的 momentum 获取收益
                actual_return_5d = current_rec.momentum_5d if current_rec.momentum_5d is not None else None
                actual_return_20d = current_rec.momentum_20d if current_rec.momentum_20d is not None else None

                # 使用可用的收益率
                if actual_return_5d is not None:
                    actual_return = actual_return_5d
                elif actual_return_20d is not None:
                    actual_return = actual_return_20d
                else:
                    skipped += 1
                    continue

                # 分类
                outcome = self.classify_outcome(
                    pm["predicted_direction"],
                    actual_return,
                    pm.get("market_regime", "unknown"),
                )

                # 解析 contradiction_flags
                contra_flags = pm.get("contradiction_flags", [])
                if isinstance(contra_flags, str):
                    try:
                        contra_flags = json.loads(contra_flags)
                    except Exception:
                        contra_flags = []

                pm_obj = SignalPostmortem(
                    signal_id=pm["signal_id"],
                    ticker=pm["ticker"],
                    signal_date=pm["signal_date"],
                    predicted_direction=pm["predicted_direction"],
                    fusion_score=pm["fusion_score"],
                    hard_score=pm.get("hard_score"),
                    soft_score=pm.get("soft_score"),
                    gate_score=pm.get("gate_score"),
                    dragon_tiger_score=pm.get("dragon_tiger_score"),
                    announcement_score=pm.get("announcement_score"),
                    consensus_bonus=pm.get("consensus_bonus", 0),
                    contradiction_flags=contra_flags if isinstance(contra_flags, list) else [],
                    market_regime=pm.get("market_regime", "unknown"),
                    actual_return_5d=round(actual_return_5d, 2) if actual_return_5d is not None else None,
                    actual_return_20d=round(actual_return_20d, 2) if actual_return_20d is not None else None,
                    outcome_category=outcome,
                    outcome_notes=f"5d return: {actual_return_5d:.1f}% | 20d return: {actual_return_20d:.1f}%" if actual_return_5d is not None else f"20d return: {actual_return_20d:.1f}%",
                    recorded_at=datetime.now().isoformat(),
                )
                self.db.save_postmortem(pm_obj)
                updated += 1
                logger.info(
                    "Matured signal %s: %s → %s (%.1f%%)",
                    pm["signal_id"], pm["predicted_direction"], outcome, actual_return,
                )

            except Exception as e:
                logger.error("Error processing signal %s: %s", pm.get("signal_id"), e)
                errors += 1

        return {
            "checked": len(immature),
            "updated": updated,
            "errors": errors,
            "skipped": skipped,
        }

    def generate_feedback(self, days: int = 30) -> dict:
        """生成反馈建议给融合权重和 Agent."""
        postmortems = self.db.get_postmortems(days=days)
        matured = [p for p in postmortems if p.get("outcome_category") is not None]

        if not matured:
            return {
                "overall_win_rate": None,
                "by_direction": {},
                "by_regime": {},
                "contradiction_impact": {},
                "total_matured": 0,
            }

        # 总体胜率
        tp_count = sum(1 for p in matured if p["outcome_category"] == "true_positive")
        overall_win_rate = tp_count / len(matured) if matured else 0

        # 按 direction 统计
        by_direction = {}
        for direction in ["buy", "sell", "hold"]:
            subset = [p for p in matured if p["predicted_direction"] == direction]
            if subset:
                tp = sum(1 for p in subset if p["outcome_category"] == "true_positive")
                by_direction[direction] = {
                    "win_rate": round(tp / len(subset), 3),
                    "count": len(subset),
                    "tp": tp,
                    "fp": sum(1 for p in subset if p["outcome_category"] == "false_positive"),
                }

        # 按 regime 统计
        by_regime = {}
        for regime in ["bull", "choppy", "bear", "unknown"]:
            subset = [p for p in matured if p.get("market_regime") == regime]
            if subset:
                tp = sum(1 for p in subset if p["outcome_category"] == "true_positive")
                by_regime[regime] = {
                    "win_rate": round(tp / len(subset), 3),
                    "count": len(subset),
                }

        # Contradiction 影响
        with_contra = [p for p in matured if p.get("contradiction_flags") and p["contradiction_flags"] != "[]"]
        without_contra = [p for p in matured if not p.get("contradiction_flags") or p["contradiction_flags"] == "[]"]

        contradiction_impact = {
            "with_contradiction": {
                "win_rate": round(sum(1 for p in with_contra if p["outcome_category"] == "true_positive") / len(with_contra), 3) if with_contra else None,
                "count": len(with_contra),
            },
            "without_contradiction": {
                "win_rate": round(sum(1 for p in without_contra if p["outcome_category"] == "true_positive") / len(without_contra), 3) if without_contra else None,
                "count": len(without_contra),
            },
        }

        return {
            "overall_win_rate": round(overall_win_rate, 3),
            "by_direction": by_direction,
            "by_regime": by_regime,
            "contradiction_impact": contradiction_impact,
            "total_matured": len(matured),
            "period_days": days,
        }

    def get_summary(self, days: int = 30) -> dict:
        """统计摘要."""
        postmortems = self.db.get_postmortems(days=days)
        matured = [p for p in postmortems if p.get("outcome_category") is not None]
        immature = [p for p in postmortems if p.get("outcome_category") is None]

        # 按 outcome 分类统计
        by_outcome = {}
        for p in matured:
            cat = p["outcome_category"]
            by_outcome[cat] = by_outcome.get(cat, 0) + 1

        # 平均实际收益
        returns_5d = [p["actual_return_5d"] for p in matured if p.get("actual_return_5d") is not None]
        returns_20d = [p["actual_return_20d"] for p in matured if p.get("actual_return_20d") is not None]

        return {
            "total_signals": len(postmortems),
            "matured": len(matured),
            "immature": len(immature),
            "by_outcome": by_outcome,
            "avg_return_5d": round(sum(returns_5d) / len(returns_5d), 2) if returns_5d else None,
            "avg_return_20d": round(sum(returns_20d) / len(returns_20d), 2) if returns_20d else None,
            "win_rate": round(by_outcome.get("true_positive", 0) / len(matured), 3) if matured else None,
        }
