"""Daily knowledge ingester — Phase G1."""

import json
import logging
from datetime import date

from src.data.db_manager import SignalDB
from src.intelligence.futures import build_futures_snapshot
from src.intelligence.overnight import build_overnight_snapshot

logger = logging.getLogger(__name__)


def _fetch_hot_events(limit: int = 20) -> list[dict]:
    events = []
    try:
        import akshare as ak
        df = ak.stock_hot_rank_em()
        if df is not None:
            for i, row in df.head(limit).iterrows():
                events.append({
                    "rank": len(events) + 1,
                    "title": str(row.get("股票名称", row.get("名称", ""))),
                    "code": str(row.get("代码", row.get("股票代码", ""))).zfill(6)[-6:],
                    "impact_score": max(0.3, 1.0 - len(events) * 0.03),
                    "sector_tags": [],
                })
    except Exception as e:
        logger.warning("Hot rank fetch failed: %s", e)
        events = [{"rank": 1, "title": "数据采集暂不可用", "code": "", "impact_score": 0.5, "sector_tags": []}]
    return events


def _fetch_macro_summary() -> str:
    return "宏观快讯：关注美联储政策、A股北向资金流向及行业政策动向。"


def _fetch_risk_flags(db: SignalDB) -> list[str]:
    flags = []
    with db._connect() as conn:
        rows = conn.execute("SELECT code, name FROM stock_meta WHERE is_st = 1 LIMIT 5").fetchall()
        for r in rows:
            flags.append(f"ST 风险: {r['code']} {r['name']}")
    if not flags:
        flags.append("暂无 ST 持仓风险")
    return flags


class KnowledgeIngester:
    """Collect and persist daily digest."""

    def __init__(self, db: SignalDB | None = None):
        self.db = db or SignalDB()

    def run(self, trade_date: date | None = None) -> dict:
        trade_date = trade_date or date.today()
        td = trade_date.isoformat()

        hot_events = _fetch_hot_events()
        for ev in hot_events:
            if ev.get("title"):
                self.db.save_market_event(
                    td, "hot", ev["title"], source="eastmoney",
                    impact_score=ev.get("impact_score", 0.5),
                    sector_tags=ev.get("sector_tags", []),
                    raw_json=ev,
                )

        overnight = build_overnight_snapshot(trade_date)
        futures = build_futures_snapshot(trade_date)

        digest = {
            "trade_date": td,
            "hot_events": hot_events,
            "macro_summary": _fetch_macro_summary(),
            "sector_impact": overnight.get("sector_hints", []),
            "risk_flags": _fetch_risk_flags(self.db),
            "overnight": {
                k: v for k, v in overnight.get("indices", {}).items()
            } | {"strong_foreign_impact": overnight.get("strong_foreign_impact", False)},
            "futures": futures.get("contracts", []),
            "llm_summary": "",
        }
        self.db.save_daily_digest(td, digest)
        logger.info("Daily digest saved for %s (%d hot events)", td, len(hot_events))
        return digest

    def export_json(self, trade_date: date | None = None) -> dict:
        trade_date = trade_date or date.today()
        td = trade_date.isoformat()
        stored = self.db.get_daily_digest(td)
        if stored:
            return {
                "trade_date": td,
                "generated_at": stored.get("generated_at", ""),
                "hot_events": stored.get("hot_events", []),
                "macro_summary": stored.get("macro_summary", ""),
                "sector_impact": stored.get("sector_impact", []),
                "risk_flags": stored.get("risk_flags", []),
                "overnight": stored.get("overnight", {}),
                "futures": stored.get("futures", []),
            }
        return self.run(trade_date)
