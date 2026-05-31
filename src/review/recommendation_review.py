"""Recommendation pool vs 5%+ gainers review — Phase G7."""

import logging
from datetime import date

from src.data.db_manager import SignalDB

logger = logging.getLogger(__name__)

HIT_THRESHOLD = 5.0


class RecommendationReview:
    def __init__(self, db: SignalDB | None = None):
        self.db = db or SignalDB()

    def _fetch_gainers(self, min_pct: float = HIT_THRESHOLD) -> list[dict]:
        gainers = []
        try:
            import akshare as ak
            df = ak.stock_zh_a_spot_em()
            if df is not None:
                for _, row in df.iterrows():
                    change = float(row.get("涨跌幅", 0) or 0)
                    if change >= min_pct:
                        gainers.append({
                            "code": str(row["代码"]).zfill(6)[-6:],
                            "name": str(row.get("名称", "")),
                            "change_pct": change,
                        })
        except Exception as e:
            logger.warning("Gainers fetch failed: %s", e)
        return sorted(gainers, key=lambda x: x["change_pct"], reverse=True)[:50]

    def run(self, trade_date: date | None = None) -> dict:
        trade_date = trade_date or date.today()
        td = trade_date.isoformat()

        pool = self.db.get_recommendation_pool(td)
        pool_codes = {r["code"] for r in pool}
        gainers = self._fetch_gainers()
        gainer_codes = {g["code"] for g in gainers}

        hits = [g for g in gainers if g["code"] in pool_codes]
        missed = [g for g in gainers if g["code"] not in pool_codes][:10]
        pool_miss = [r for r in pool if r["code"] not in gainer_codes]

        hit_count = len(hits)
        miss_count = len(missed)
        total = hit_count + miss_count
        hit_rate = hit_count / total if total else 0.0

        review = {
            "trade_date": td,
            "hit_count": hit_count,
            "miss_count": miss_count,
            "hit_rate": round(hit_rate, 3),
            "hits": hits[:10],
            "missed_top": missed,
            "pool_underperform": [{"code": r["code"], "name": r["name"]} for r in pool_miss[:10]],
        }
        self.db.save_recommendation_review(td, review)
        logger.info("Review %s: hit_rate=%.1f%%", td, hit_rate * 100)
        return review

    def export_json(self, trade_date: date | None = None) -> dict:
        td = (trade_date or date.today()).isoformat()
        stored = self.db.get_recommendation_review(td)
        if stored:
            return stored.get("review") or stored
        return self.run(trade_date or date.today())
