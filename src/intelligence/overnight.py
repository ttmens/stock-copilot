"""Overnight global market monitor — Phase G2."""

import logging
from datetime import date

logger = logging.getLogger(__name__)

# Fallback static indices when AkShare unavailable
_DEFAULT_INDICES = {
    "nasdaq": {"name": "纳斯达克", "change_pct": 0.0},
    "sp500": {"name": "标普500", "change_pct": 0.0},
    "dow": {"name": "道琼斯", "change_pct": 0.0},
    "nikkei": {"name": "日经225", "change_pct": 0.0},
}


def fetch_overnight_indices() -> dict:
    """Fetch overnight index changes. Degrades gracefully."""
    result = dict(_DEFAULT_INDICES)
    try:
        import akshare as ak
        # US indices via global index spot
        for key, symbol in [("nasdaq", "纳斯达克"), ("sp500", "标普500"), ("dow", "道琼斯")]:
            try:
                df = ak.index_global_hist_em(symbol=symbol)
                if df is not None and len(df) >= 2:
                    last = float(df.iloc[-1]["close"])
                    prev = float(df.iloc[-2]["close"])
                    result[key]["change_pct"] = round((last - prev) / prev * 100, 2)
            except Exception as e:
                logger.debug("Overnight fetch %s failed: %s", key, e)
    except ImportError:
        logger.warning("akshare not available for overnight monitor")
    return result


def apply_overnight_rules(indices: dict) -> dict:
    """Rule engine for foreign market impact."""
    nasdaq = indices.get("nasdaq", {}).get("change_pct", 0)
    rules = {
        "strong_foreign_impact": abs(nasdaq) > 2.0,
        "sector_hints": [],
    }
    if nasdaq > 2:
        rules["sector_hints"].append({"sector": "科技", "direction": "bullish"})
    elif nasdaq < -2:
        rules["sector_hints"].append({"sector": "科技", "direction": "bearish"})
    return rules


def build_overnight_snapshot(trade_date: date | None = None) -> dict:
    trade_date = trade_date or date.today()
    indices = fetch_overnight_indices()
    rules = apply_overnight_rules(indices)
    return {
        "trade_date": trade_date.isoformat(),
        "indices": indices,
        "strong_foreign_impact": rules["strong_foreign_impact"],
        "sector_hints": rules["sector_hints"],
    }
