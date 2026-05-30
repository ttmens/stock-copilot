"""Thesis Manager — 投资论点全生命周期管理（Phase F）.

从高分信号自动创建 thesis，追踪 IDEA → ENTRY_READY → ACTIVE → CLOSED 状态流转，
CLOSE 时计算 P&L、MAE（最大不利偏移）、MFE（最大有利偏移）。
"""

import logging
import hashlib
from datetime import datetime, date
from typing import Optional

from src.data.db_manager import SignalDB, ThesisRecord

logger = logging.getLogger(__name__)

# ── Thesis type classification ──────────────────────────────────────

def _infer_thesis_type(
    hard_score: float,
    soft_score: float,
    capital_score: float,
    ma_alignment: str,
    announcement_sentiment: str = "neutral",
) -> str:
    """基于信号特征推断 thesis 类型."""
    if hard_score > 0.5 and ma_alignment == "bullish":
        return "momentum_breakout"
    elif capital_score > 0.5:
        return "capital_driven"
    elif announcement_sentiment in ("bullish",):
        return "event_catalyst"
    elif hard_score > 0 and soft_score < 0:
        return "valuation_repair"  # 硬信号好但软信号差，可能是估值修复
    else:
        return "sector_rotation"


def _generate_thesis_id(ticker: str, created_at: str) -> str:
    """生成唯一 thesis_id."""
    raw = f"{ticker}_{created_at}"
    hash_prefix = hashlib.md5(raw.encode()).hexdigest()[:6]
    return f"th_{ticker}_{created_at.replace('-', '')}_{hash_prefix}"


# ── ThesisManager ───────────────────────────────────────────────────

class ThesisManager:
    """Thesis 全生命周期管理."""

    def __init__(self, db: SignalDB):
        self.db = db

    def create_thesis(
        self,
        ticker: str,
        signal_id: str,
        thesis_type: str,
        thesis_statement: str,
        fusion_score: float,
        hard_score: float = 0.0,
        stop_price: Optional[float] = None,
        target_price: Optional[float] = None,
        expected_holding_days: int = 10,
    ) -> str:
        """从高分信号创建 thesis."""
        created_at = date.today().isoformat()
        thesis_id = _generate_thesis_id(ticker, created_at)

        # 计算止损价（如果没有提供）
        if stop_price is None and fusion_score > 0:
            # 默认 7% 止损
            stop_price = None  # 需要价格数据才能计算

        thesis = ThesisRecord(
            thesis_id=thesis_id,
            ticker=ticker,
            created_at=created_at,
            thesis_type=thesis_type,
            thesis_statement=thesis_statement,
            status="idea",
            expected_holding_days=expected_holding_days,
            stop_price=stop_price,
            target_price=target_price,
            source_signal_id=signal_id,
            status_history=[{
                "from_status": None,
                "to_status": "idea",
                "at": datetime.now().isoformat(),
                "reason": "Auto-created from high-score signal",
            }],
        )

        self.db.save_thesis(thesis)
        logger.info("Created thesis: %s (%s → %s)", thesis_id, ticker, thesis_type)
        return thesis_id

    def transition(
        self,
        thesis_id: str,
        new_status: str,
        reason: str = "",
        entry_price: Optional[float] = None,
        entry_date: Optional[str] = None,
    ) -> bool:
        """状态转换."""
        theses = self.db.get_theses(ticker=thesis_id.split("_")[1] if "_" in thesis_id else "")
        thesis = None
        for t in theses:
            if t["thesis_id"] == thesis_id:
                thesis = t
                break

        if not thesis:
            logger.warning("Thesis not found: %s", thesis_id)
            return False

        old_status = thesis["status"]

        # 验证转换合法性
        valid_transitions = {
            "idea": ["entry_ready", "invalidated"],
            "entry_ready": ["active", "invalidated"],
            "active": ["closed", "invalidated"],
            "closed": [],
            "invalidated": [],
        }

        if new_status not in valid_transitions.get(old_status, []):
            logger.warning(
                "Invalid transition: %s → %s for thesis %s",
                old_status, new_status, thesis_id,
            )
            return False

        # 更新
        thesis["status"] = new_status
        if entry_price is not None:
            thesis["entry_price"] = entry_price
        if entry_date is not None:
            thesis["entry_date"] = entry_date

        thesis["status_history"].append({
            "from_status": old_status,
            "to_status": new_status,
            "at": datetime.now().isoformat(),
            "reason": reason,
        })

        import json
        thesis_rec = ThesisRecord(
            thesis_id=thesis["thesis_id"],
            ticker=thesis["ticker"],
            created_at=thesis["created_at"],
            thesis_type=thesis["thesis_type"],
            thesis_statement=thesis.get("thesis_statement"),
            status=new_status,
            expected_holding_days=thesis.get("expected_holding_days", 10),
            stop_price=thesis.get("stop_price"),
            target_price=thesis.get("target_price"),
            entry_price=entry_price or thesis.get("entry_price"),
            entry_date=entry_date or thesis.get("entry_date"),
            exit_price=thesis.get("exit_price"),
            exit_date=thesis.get("exit_date"),
            exit_reason=thesis.get("exit_reason", ""),
            pnl_pct=thesis.get("pnl_pct"),
            mae=thesis.get("mae"),
            mfe=thesis.get("mfe"),
            source_signal_id=thesis.get("source_signal_id"),
            status_history=thesis["status_history"],
        )
        self.db.save_thesis(thesis_rec)
        logger.info("Thesis transition: %s %s → %s", thesis_id, old_status, new_status)
        return True

    def close_thesis(
        self,
        thesis_id: str,
        exit_price: float,
        exit_reason: str = "manual",
        exit_date: Optional[str] = None,
    ) -> bool:
        """关闭 thesis，计算 P&L."""
        theses = self.db.get_theses()
        thesis = None
        for t in theses:
            if t["thesis_id"] == thesis_id:
                thesis = t
                break

        if not thesis:
            logger.warning("Thesis not found: %s", thesis_id)
            return False

        if thesis["status"] not in ("active",):
            logger.warning("Cannot close thesis in status: %s", thesis["status"])
            return False

        entry_price = thesis.get("entry_price")
        if entry_price is None or entry_price <= 0:
            logger.warning("No entry price for thesis %s", thesis_id)
            return False

        # 计算 P&L
        pnl_pct = (exit_price - entry_price) / entry_price * 100

        # MAE/MFE 需要历史价格数据，这里简化处理
        # 实际应该从 K 线数据计算
        mae = None
        mfe = None

        # 更新
        thesis["status"] = "closed"
        thesis["exit_price"] = exit_price
        thesis["exit_date"] = exit_date or date.today().isoformat()
        thesis["exit_reason"] = exit_reason
        thesis["pnl_pct"] = round(pnl_pct, 2)
        thesis["mae"] = mae
        thesis["mfe"] = mfe
        thesis["status_history"].append({
            "from_status": "active",
            "to_status": "closed",
            "at": datetime.now().isoformat(),
            "reason": exit_reason,
        })

        import json
        thesis_rec = ThesisRecord(
            thesis_id=thesis["thesis_id"],
            ticker=thesis["ticker"],
            created_at=thesis["created_at"],
            thesis_type=thesis["thesis_type"],
            thesis_statement=thesis.get("thesis_statement"),
            status="closed",
            expected_holding_days=thesis.get("expected_holding_days", 10),
            stop_price=thesis.get("stop_price"),
            target_price=thesis.get("target_price"),
            entry_price=thesis.get("entry_price"),
            entry_date=thesis.get("entry_date"),
            exit_price=exit_price,
            exit_date=thesis["exit_date"],
            exit_reason=exit_reason,
            pnl_pct=round(pnl_pct, 2),
            mae=mae,
            mfe=mfe,
            source_signal_id=thesis.get("source_signal_id"),
            status_history=thesis["status_history"],
        )
        self.db.save_thesis(thesis_rec)
        logger.info("Closed thesis: %s pnl=%.1f%%", thesis_id, pnl_pct)
        return True

    def list_due_for_review(self, as_of: Optional[str] = None) -> list[dict]:
        """列出需要复查的 thesis."""
        check_date = date.fromisoformat(as_of) if as_of else date.today()
        theses = self.db.get_theses(status="active")

        due = []
        for t in theses:
            entry_date = t.get("entry_date")
            if entry_date:
                entry_dt = date.fromisoformat(entry_date)
                holding_days = (check_date - entry_dt).days
                if holding_days >= t.get("expected_holding_days", 10):
                    due.append({**t, "holding_days": holding_days})

        return due

    def get_statistics(self, days: int = 90) -> dict:
        """按 thesis_type 统计胜率、平均盈亏等."""
        import json

        all_theses = self.db.get_theses()
        closed = [t for t in all_theses if t["status"] == "closed"]

        if not closed:
            return {
                "total_closed": 0,
                "by_type": {},
                "overall_win_rate": None,
            }

        # 总体统计
        wins = sum(1 for t in closed if t.get("pnl_pct") is not None and t["pnl_pct"] > 0)
        pnls = [t["pnl_pct"] for t in closed if t.get("pnl_pct") is not None]

        # 按类型统计
        by_type = {}
        for t in closed:
            ttype = t.get("thesis_type", "unknown")
            if ttype not in by_type:
                by_type[ttype] = {"count": 0, "wins": 0, "pnls": []}
            by_type[ttype]["count"] += 1
            if t.get("pnl_pct") is not None:
                if t["pnl_pct"] > 0:
                    by_type[ttype]["wins"] += 1
                by_type[ttype]["pnls"].append(t["pnl_pct"])

        # 计算胜率
        for ttype, stats in by_type.items():
            stats["win_rate"] = round(stats["wins"] / stats["count"], 3) if stats["count"] > 0 else 0
            stats["avg_pnl"] = round(sum(stats["pnls"]) / len(stats["pnls"]), 2) if stats["pnls"] else None
            del stats["pnls"]  # 不返回详细列表

        return {
            "total_closed": len(closed),
            "overall_win_rate": round(wins / len(closed), 3) if closed else None,
            "avg_pnl": round(sum(pnls) / len(pnls), 2) if pnls else None,
            "by_type": by_type,
        }
