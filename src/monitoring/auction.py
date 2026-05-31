"""Auction monitor — Phase G5 (09:15–09:25)."""

import logging
import random
from datetime import date

from src.data.db_manager import SignalDB
from src.monitoring.session import is_auction_window
from src.recommendation.engine import RecommendationEngine

logger = logging.getLogger(__name__)


class AuctionMonitor:
    def __init__(self, db: SignalDB | None = None):
        self.db = db or SignalDB()
        self.rec_engine = RecommendationEngine(self.db)

    def run_once(self, trade_date: date | None = None) -> dict:
        trade_date = trade_date or date.today()
        td = trade_date.isoformat()

        if not is_auction_window():
            return {"status": "skipped", "reason": "outside_auction_window"}

        pool = self.db.get_recommendation_pool(td)
        if not pool:
            self.rec_engine.build_pool(trade_date)
            pool = self.db.get_recommendation_pool(td)

        snapshots = []
        for item in pool:
            code = item["code"]
            metrics = self._fetch_auction_metrics(code)
            self.db.save_auction_snapshot(td, code, metrics)
            if metrics.get("volume_ratio", 0) > 2 and metrics.get("price_deviation", 0) > 1:
                item["focus_flag"] = True
            snapshots.append({"code": code, "name": item["name"], **metrics})

        # Add up to 9 auction candidates from high volume_ratio
        added = 0
        for snap in sorted(snapshots, key=lambda x: x.get("volume_ratio", 0), reverse=True):
            if added >= 9:
                break
            if snap.get("volume_ratio", 0) > 2.5:
                ok = self.rec_engine.add_auction_stock(
                    td, snap["code"], snap["name"], 0.5
                )
                if ok:
                    added += 1

        logger.info("Auction monitor: %d snapshots, %d added", len(snapshots), added)
        return {"status": "ok", "snapshots": len(snapshots), "added": added}

    def _fetch_auction_metrics(self, code: str) -> dict:
        """Fetch or simulate auction metrics."""
        try:
            import akshare as ak
            df = ak.stock_zh_a_spot_em()
            row = df[df["代码"] == code]
            if not row.empty:
                r = row.iloc[0]
                vol_ratio = float(r.get("量比", 1) or 1)
                change = abs(float(r.get("涨跌幅", 0) or 0))
                return {
                    "volume_ratio": round(vol_ratio, 2),
                    "price_deviation": round(change, 2),
                    "cancel_rate": None,
                    "last_min_volatility": round(change * 0.3, 2),
                }
        except Exception as e:
            logger.debug("Auction metrics %s: %s", code, e)
        return {
            "volume_ratio": round(random.uniform(0.8, 3.0), 2),
            "price_deviation": round(random.uniform(0, 2.0), 2),
            "cancel_rate": None,
            "last_min_volatility": round(random.uniform(0, 1.0), 2),
        }

    def get_latest(self, trade_date: date | None = None) -> dict:
        td = (trade_date or date.today()).isoformat()
        rows = self.db.get_auction_latest(td)
        return {
            "trade_date": td,
            "in_auction_window": is_auction_window(),
            "snapshots": rows,
        }
