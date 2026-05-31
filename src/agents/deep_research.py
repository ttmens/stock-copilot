"""Deep research agent — Phase G7 on-demand."""

import logging
from datetime import datetime

from src.data.db_manager import SignalDB
from src.data.stock_graph import StockRelationGraph

logger = logging.getLogger(__name__)


class DeepResearchAgent:
    """Hidden-info analysis using graph + announcements."""

    def __init__(self, db: SignalDB | None = None):
        self.db = db or SignalDB()

    async def analyze(self, code: str) -> dict:
        meta = self.db.get_stock(code) or {"code": code, "name": code}
        name = meta.get("name", code)

        hidden_signals = []
        related_events = []

        try:
            graph = StockRelationGraph()
            relations = graph.get_related(code, limit=5)
            for rel in relations:
                related_events.append({
                    "type": rel.relation_type,
                    "title": rel.target_code if rel.source_code == code else rel.source_code,
                    "detail": str(rel.extra_info) if rel.extra_info else "",
                })
        except Exception as e:
            logger.debug("Graph for %s: %s", code, e)

        signals = self.db.get_latest_signals(datetime.now().date(), report_type="pre")
        stock_sig = next((s for s in signals if (s.code if hasattr(s, "code") else s.get("code")) == code), None)
        if stock_sig:
            main_inflow = getattr(stock_sig, "main_net_inflow", None) or (stock_sig.get("main_net_inflow") if hasattr(stock_sig, "get") else None)
            if main_inflow:
                hidden_signals.append({
                    "signal": "main_inflow",
                    "value": main_inflow,
                    "interpretation": "主力资金净流入",
                })
            final = getattr(stock_sig, "final_score", None) or 0
            hidden_signals.append({
                "signal": "baseline",
                "value": final,
                "interpretation": "基于最新融合信号",
            })
        elif not hidden_signals:
            hidden_signals.append({
                "signal": "baseline",
                "value": 0,
                "interpretation": "暂无信号数据",
            })

        return {
            "code": code,
            "name": name,
            "generated_at": datetime.now().isoformat(),
            "hidden_signals": hidden_signals,
            "related_events": related_events,
            "summary": f"{name}({code}) 深度分析：发现 {len(hidden_signals)} 条隐藏信号，"
                       f"{len(related_events)} 条关联事件。",
        }
