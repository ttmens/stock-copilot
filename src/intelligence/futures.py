"""Futures monitor — Phase G3 (oil/gold sector hints)."""

import logging
from datetime import date

logger = logging.getLogger(__name__)

THRESHOLD_PCT = 1.5


def fetch_futures() -> list[dict]:
    """Fetch crude/gold futures change. Returns list with sector hints."""
    contracts = [
        {"symbol": "原油", "ak_name": "原油", "sector_hint": "energy"},
        {"symbol": "黄金", "ak_name": "黄金", "sector_hint": "precious_metals"},
    ]
    results = []
    try:
        import akshare as ak
        for c in contracts:
            change_pct = 0.0
            try:
                df = ak.futures_main_sina(symbol=c["ak_name"])
                if df is not None and len(df) >= 2:
                    last = float(df.iloc[-1]["close"])
                    prev = float(df.iloc[-2]["close"])
                    change_pct = round((last - prev) / prev * 100, 2)
            except Exception as e:
                logger.debug("Futures %s failed: %s", c["symbol"], e)
            entry = {
                "symbol": c["symbol"],
                "change_pct": change_pct,
                "sector_hint": c["sector_hint"] if abs(change_pct) >= THRESHOLD_PCT else None,
            }
            results.append(entry)
    except ImportError:
        for c in contracts:
            results.append({"symbol": c["symbol"], "change_pct": 0.0, "sector_hint": None})
    return results


def build_futures_snapshot(trade_date: date | None = None) -> dict:
    trade_date = trade_date or date.today()
    contracts = fetch_futures()
    hints = [c["sector_hint"] for c in contracts if c.get("sector_hint")]
    return {
        "trade_date": trade_date.isoformat(),
        "contracts": contracts,
        "sector_hints": list(set(hints)),
    }
