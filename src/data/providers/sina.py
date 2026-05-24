"""Sina Finance direct HTTP API provider — K-line fallback.

Reliable source for daily OHLCV when AkShare and Eastmoney push2his fail.
"""

import logging
from datetime import datetime
from typing import Optional

import httpx

from src.data.models import OHLCVBar

logger = logging.getLogger(__name__)

SINA_KLINE_URL = "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
}


def _get_sina_code(code: str) -> str:
    prefix = "sh" if code.startswith("6") else "sz"
    return f"{prefix}{code}"


def get_kline_sina(code: str, days: int = 60) -> list[OHLCVBar]:
    """Get daily K-line from Sina Finance.

    Returns list of OHLCVBar sorted by date.
    """
    sina_code = _get_sina_code(code)
    params = {
        "symbol": sina_code,
        "scale": "240",  # 240min = daily
        "ma": "no",
        "datalen": str(days),
    }

    try:
        r = httpx.get(SINA_KLINE_URL, params=params, headers=HEADERS, timeout=10)
        if r.status_code != 200:
            return []

        data = r.json()
        if not isinstance(data, list):
            return []

        bars = []
        for item in data:
            try:
                bars.append(OHLCVBar(
                    date=datetime.strptime(item["day"], "%Y-%m-%d").date(),
                    open=float(item["open"]),
                    high=float(item["high"]),
                    low=float(item["low"]),
                    close=float(item["close"]),
                    volume=float(item["volume"]),
                ))
            except (KeyError, ValueError):
                continue

        return sorted(bars, key=lambda b: b.date)
    except Exception as e:
        logger.debug("Sina K-line failed for %s: %s", code, e)
        return []
