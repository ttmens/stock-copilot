"""Trading calendar utilities."""

import logging
from datetime import date, datetime
from functools import lru_cache

import akshare as ak
import pandas as pd

logger = logging.getLogger(__name__)

# Cache trading days for the current year
_trading_days: set[date] | None = None


def _load_trading_days() -> set[date]:
    """Load trading calendar from AkShare and cache in memory."""
    global _trading_days
    try:
        df = ak.tool_trade_date_hist_sina()
        # df has a column named 'trade_date' (type: datetime or str)
        dates = pd.to_datetime(df["trade_date"]).dt.date
        _trading_days = set(dates)
        logger.info("Loaded %d trading days from AkShare", len(_trading_days))
    except Exception as e:
        logger.warning("Failed to load trading calendar, falling back to weekday check: %s", e)
        _trading_days = None
    return _trading_days or set()


def is_trading_day(d: date | None = None) -> bool:
    """Check if a date is a trading day.

    Uses AkShare calendar if available, falls back to Mon-Fri check.
    """
    if d is None:
        d = datetime.now().date()

    global _trading_days
    if _trading_days is None:
        _load_trading_days()

    if _trading_days:
        return d in _trading_days

    # Fallback: Mon=0 .. Fri=4
    return d.weekday() < 5


@lru_cache
def is_trading_day_cached(d_str: str) -> bool:
    """Cached version for scheduler use (string key)."""
    d = datetime.strptime(d_str, "%Y-%m-%d").date()
    return is_trading_day(d)
