"""ReACT Analysis Tools — inspired by MiroFish's ReportAgent tool-use pattern.

MiroFish's ReportAgent uses a ReACT (Reasoning + Acting) loop:
1. Think about what information is needed
2. Call a tool to retrieve it (InsightForge / PanoramaSearch / Interview)
3. Reflect on the result
4. Repeat until sufficient information
5. Write the report section

We adapt this for Stock Copilot: agents can now actively query historical data,
compare peers, and check sector momentum — instead of passively analyzing
whatever data is handed to them.
"""

import json
import logging
from datetime import date, datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


class AnalysisTools:
    """Tools available to ReACT-enabled analysis agents.

    Each tool returns a text summary suitable for injection into LLM prompts.
    """

    def __init__(self, db_path: str = "data/signals.db"):
        self.db_path = db_path

    def _get_conn(self):
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def query_history(self, code: str, days: int = 30) -> str:
        """查询股票最近 N 个交易日的信号历史。

        MiroFish pattern: InsightForge — retrieve historical context.
        """
        conn = self._get_conn()
        try:
            cutoff = (date.today() - timedelta(days=days)).isoformat()
            rows = conn.execute(
                """
                SELECT trade_date, final_score, final_signal, signal_label,
                       hard_score, soft_score, confidence
                FROM signals
                WHERE code = ? AND trade_date >= ?
                ORDER BY trade_date DESC
                LIMIT ?
                """,
                (code, cutoff, days),
            ).fetchall()

            if not rows:
                return f"⚪ {code} 无历史信号记录（最近{days}天）"

            lines = [f"📊 {code} 最近信号历史（{len(rows)}个交易日）："]
            for row in rows:
                score = row["final_score"]
                label = row["signal_label"] or ""
                conf = row["confidence"]
                lines.append(
                    f"  {row['trade_date']}: {label} (score={score:+.2f}, conf={conf:.2f})"
                )

            # Trend summary
            recent = rows[:5]
            bullish = sum(1 for r in recent if r["final_score"] > 0.2)
            bearish = sum(1 for r in recent if r["final_score"] < -0.2)
            if bullish > bearish:
                lines.append(f"\n📈 近5日偏向看多 ({bullish}/{len(recent)})")
            elif bearish > bullish:
                lines.append(f"\n📉 近5日偏向看空 ({bearish}/{len(recent)})")
            else:
                lines.append(f"\n⚪ 近5日多空交织")

            return "\n".join(lines)
        finally:
            conn.close()

    def check_capital_flow(self, code: str, days: int = 5) -> str:
        """查询主力资金流向趋势。"""
        conn = self._get_conn()
        try:
            rows = conn.execute(
                """
                SELECT trade_date, main_net_inflow
                FROM signals
                WHERE code = ? AND main_net_inflow IS NOT NULL
                ORDER BY trade_date DESC
                LIMIT ?
                """,
                (code, days),
            ).fetchall()

            if not rows:
                return f"⚪ {code} 无资金流数据"

            lines = [f"💰 {code} 主力资金流向（最近{len(rows)}日）："]
            total = 0
            for row in rows:
                inflow = row["main_net_inflow"] or 0
                total += inflow
                direction = "🟢 净流入" if inflow > 0 else "🔴 净流出"
                # Convert to 万元 for readability
                amount_wan = inflow / 10000 if inflow else 0
                lines.append(f"  {row['trade_date']}: {direction} {amount_wan:+.0f}万")

            total_wan = total / 10000
            trend = "🟢 累计净流入" if total > 0 else "🔴 累计净流出"
            lines.append(f"\n{trend}: {total_wan:+.0f}万")
            return "\n".join(lines)
        finally:
            conn.close()

    def get_stock_meta(self, code: str) -> dict:
        """获取股票基本信息（行业、市值等）。"""
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT code, name, industry, market FROM stock_meta WHERE code = ?",
                (code,),
            ).fetchone()
            if row:
                return {
                    "code": row["code"],
                    "name": row["name"],
                    "industry": row["industry"] or "",
                    "market": row["market"] or "",
                }
            return {}
        finally:
            conn.close()


def build_react_context(
    code: str,
    tools: AnalysisTools,
    include_history: bool = True,
    include_capital: bool = True,
) -> str:
    """Build ReACT context string for injection into agent prompts.

    MiroFish pattern: pre-fetch relevant context before LLM analysis,
    simulating the tool-use loop without the overhead.
    """
    parts = []

    if include_history:
        history = tools.query_history(code, days=20)
        if history:
            parts.append("\n## 历史信号参考\n" + history)

    if include_capital:
        capital = tools.check_capital_flow(code, days=5)
        if capital:
            parts.append("\n## 资金流趋势\n" + capital)

    return "\n".join(parts) if parts else ""
