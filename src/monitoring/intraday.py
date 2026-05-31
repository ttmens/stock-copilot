"""Intraday monitor — Phase G6."""

import logging
from datetime import date

from src.data.db_manager import SignalDB
from src.monitoring.alerts import AlertDispatcher
from src.monitoring.session import is_intraday_window
from src.watchlist.manager import WatchlistManager

logger = logging.getLogger(__name__)


class IntradayMonitor:
    def __init__(self, db: SignalDB | None = None):
        self.db = db or SignalDB()
        self.alerts = AlertDispatcher(self.db)

    def _monitor_codes(self) -> list[tuple[str, str]]:
        td = date.today().isoformat()
        codes = {}
        for r in self.db.get_recommendation_pool(td):
            codes[r["code"]] = r.get("name", r["code"])
        for w in WatchlistManager().list_dicts():
            codes[w["code"]] = w.get("name", w["code"])
        return list(codes.items())

    def run_once(self) -> dict:
        if not is_intraday_window():
            return {"status": "skipped", "reason": "outside_intraday_window"}

        triggered = 0
        for code, name in self._monitor_codes():
            metrics = self._fetch_intraday(code)
            if not metrics:
                continue
            vol_ratio = metrics.get("volume_ratio", 1)
            change = metrics.get("change_pct", 0)

            if vol_ratio > 2.5 and change > 1:
                self.alerts.dispatch(
                    code, name, "volume_breakout",
                    f"放量突破：量比 {vol_ratio:.1f}，涨跌幅 {change:+.2f}%",
                    severity="action",
                )
                triggered += 1
            elif vol_ratio < 0.5 and change < -0.5:
                self.alerts.dispatch(
                    code, name, "volume_shrink",
                    f"缩量回调：量比 {vol_ratio:.1f}，涨跌幅 {change:+.2f}%",
                    severity="watch",
                )
                triggered += 1

        logger.info("Intraday monitor: %d alerts", triggered)
        return {"status": "ok", "alerts_triggered": triggered}

    def _fetch_intraday(self, code: str) -> dict | None:
        try:
            import akshare as ak
            df = ak.stock_zh_a_spot_em()
            row = df[df["代码"] == code]
            if row.empty:
                return None
            r = row.iloc[0]
            return {
                "volume_ratio": float(r.get("量比", 1) or 1),
                "change_pct": float(r.get("涨跌幅", 0) or 0),
            }
        except Exception as e:
            logger.debug("Intraday %s: %s", code, e)
            return None
