"""Tencent Finance direct HTTP API provider.

Fallback for K-line and valuation when AkShare/Eastmoney fail.
Zero akshare dependency — pure HTTP calls to qt.gtimg.cn.
"""

import logging
from datetime import datetime
from typing import Optional

import httpx

from src.data.models import OHLCVBar

logger = logging.getLogger(__name__)

QUOTE_URL = "https://qt.gtimg.cn/q="
KLINE_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
}


def _get_tencent_code(code: str) -> str:
    prefix = "sh" if code.startswith("6") else "sz"
    return f"{prefix}{code}"


def get_stock_quote(code: str) -> dict:
    """Get real-time quote with PE/PB/market cap from Tencent."""
    tencent_code = _get_tencent_code(code)
    url = f"{QUOTE_URL}{tencent_code}"

    try:
        r = httpx.get(url, headers=HEADERS, timeout=8)
        text = r.text
        if not text or "=" not in text:
            return {}

        parts = text.split("~")
        if len(parts) < 50:
            return {}

        return {
            "code": parts[2],
            "name": parts[1],
            "price": float(parts[3]) if parts[3] else 0,
            "prev_close": float(parts[4]) if parts[4] else 0,
            "open": float(parts[5]) if parts[5] else 0,
            "high": float(parts[33]) if parts[33] else 0,
            "low": float(parts[34]) if parts[34] else 0,
            "volume": float(parts[36]) if parts[36] else 0,
            "amount": float(parts[37]) if parts[37] else 0,
            "turnover_rate": float(parts[38]) if parts[38] else 0,
            "pe_ttm": float(parts[39]) if len(parts) > 39 and parts[39] else None,
            "pb": float(parts[46]) if len(parts) > 46 and parts[46] else None,
            "total_mcap": float(parts[45]) if len(parts) > 45 and parts[45] else 0,
            "float_mcap": float(parts[44]) if len(parts) > 44 and parts[44] else 0,
            "upper_limit": float(parts[47]) if len(parts) > 47 and parts[47] else 0,
            "lower_limit": float(parts[48]) if len(parts) > 48 and parts[48] else 0,
        }
    except Exception as e:
        logger.debug("Tencent quote failed for %s: %s", code, e)
        return {}


def get_kline_tencent(code: str, days: int = 60) -> list[OHLCVBar]:
    """Get daily K-line from Tencent."""
    tencent_code = _get_tencent_code(code)
    params = {
        "param": f"{tencent_code},day,{days}",
        "type": "qfq",
    }

    try:
        r = httpx.get(KLINE_URL, params=params, headers=HEADERS, timeout=10)
        data = r.json()

        stock_data = data.get("data", {}).get(tencent_code, {})
        klines = stock_data.get("day", []) or stock_data.get("data", [])

        bars = []
        for item in klines:
            if len(item) < 6:
                continue
            bars.append(OHLCVBar(
                date=datetime.strptime(item[0], "%Y-%m-%d").date(),
                open=float(item[1]),
                close=float(item[2]),
                high=float(item[3]),
                low=float(item[4]),
                volume=float(item[5]),
                amount=float(item[6]) if len(item) > 6 else None,
            ))
        return bars
    except Exception as e:
        logger.debug("Tencent K-line failed for %s: %s", code, e)
        return []
