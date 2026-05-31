"""3×3 recommendation pool — Phase G4."""

import logging
from datetime import date

from src.config import get_settings
from src.data.db_manager import SignalDB

logger = logging.getLogger(__name__)

MCAP_LIMIT = 3_000_000_000_000  # 3000亿
DEFAULT_SECTORS = ["半导体", "新能源", "消费"]


class RecommendationEngine:
    """Build daily tactical recommendation pool."""

    def __init__(self, db: SignalDB | None = None):
        self.db = db or SignalDB()
        self.settings = get_settings()

    def _get_candidate_codes(self) -> list[tuple[str, str, float]]:
        """Return (code, name, score) from latest signals."""
        today = date.today()
        signals = self.db.get_latest_signals(today, report_type="pre")
        if not signals:
            signals = self.db.get_latest_signals(today, report_type="post")
        candidates = []
        for s in signals:
            code = s.code if hasattr(s, "code") else s.get("code", "")
            meta = self.db.get_stock(code) or {}
            name = meta.get("name") or code
            if self._passes_hard_filter(code, meta):
                score = float(s.final_score if hasattr(s, "final_score") else s.get("final_score") or 0)
                candidates.append((code, name, score))
        candidates.sort(key=lambda x: x[2], reverse=True)
        return candidates

    def _passes_hard_filter(self, code: str, meta: dict) -> bool:
        if meta.get("is_st"):
            return False
        name = meta.get("name", "")
        if "ST" in name.upper():
            return False
        mcap = meta.get("mcap", 0)
        if mcap and mcap > MCAP_LIMIT:
            return False
        streak = meta.get("limit_up_streak", 0)
        if streak and streak >= 3:
            return False
        return True

    def _sector_names(self) -> list[str]:
        digest = self.db.get_daily_digest(date.today().isoformat())
        if digest and digest.get("sector_impact"):
            sectors = []
            for item in digest["sector_impact"]:
                if isinstance(item, dict):
                    name = item.get("sector") or item.get("name")
                    if name:
                        sectors.append(name)
            if len(sectors) >= 3:
                return sectors[:3]
        return DEFAULT_SECTORS

    def build_pool(self, trade_date: date | None = None) -> dict:
        trade_date = trade_date or date.today()
        td = trade_date.isoformat()
        sectors = self._sector_names()
        candidates = self._get_candidate_codes()

        self.db.clear_recommendation_pool(td)
        used = set()
        sector_outputs = []

        for rank, sector_name in enumerate(sectors):
            stocks = []
            for code, name, score in candidates:
                if code in used:
                    continue
                used.add(code)
                self.db.save_recommendation_stock(
                    td, sector_name, rank, code, name, score, source="scan"
                )
                stocks.append({
                    "code": code, "name": name, "score": score,
                    "source": "scan", "focus_flag": False,
                })
                if len(stocks) >= 3:
                    break
            sector_outputs.append({"name": sector_name, "reason": "硬信号+热点", "stocks": stocks})

        result = {
            "trade_date": td,
            "generated_at": date.today().isoformat(),
            "filters_applied": ["no_st", "mcap_lt_3000b", "no_limit_up_streak"],
            "sectors": sector_outputs,
            "auction_added": [],
        }
        logger.info("Recommendation pool: %s (%d sectors)", td, len(sector_outputs))
        return result

    def export_json(self, trade_date: date | None = None) -> dict:
        trade_date = trade_date or date.today()
        td = trade_date.isoformat()
        rows = self.db.get_recommendation_pool(td)
        if not rows:
            return self.build_pool(trade_date)

        sectors_map: dict[str, list] = {}
        for r in rows:
            sn = r["sector_name"]
            if sn not in sectors_map:
                sectors_map[sn] = []
            sectors_map[sn].append({
                "code": r["code"], "name": r["name"], "score": r["score"],
                "source": r["source"], "focus_flag": bool(r["focus_flag"]),
            })

        return {
            "trade_date": td,
            "generated_at": td,
            "filters_applied": ["no_st", "mcap_lt_3000b", "no_limit_up_streak"],
            "sectors": [{"name": k, "reason": "", "stocks": v} for k, v in sectors_map.items()],
            "auction_added": [r for r in rows if r["source"] == "auction"],
        }

    def add_auction_stock(self, trade_date: str, code: str, name: str,
                          score: float, sector_name: str = "竞价加池") -> bool:
        existing = self.db.get_recommendation_pool(trade_date)
        auction_count = sum(1 for r in existing if r["source"] == "auction")
        if auction_count >= 9:
            return False
        self.db.save_recommendation_stock(
            trade_date, sector_name, 99, code, name, score, source="auction", focus_flag=True
        )
        return True
