"""Eastmoney direct HTTP API provider — push2, datacenter.

Ported from a-stock-data V3.1 (simonlin1212/a-stock-data).
Note: push2his (K-line) may be blocked from some servers;
      falls back to Tencent K-line in fetcher.
"""

import logging
import uuid
from datetime import datetime
from typing import Optional

import httpx

from src.data.models import CapitalFlow, DragonTigerItem, MarketOverview

logger = logging.getLogger(__name__)

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

PUSH2_URL = "https://push2.eastmoney.com/api/qt/stock/get"
PUSH2_FLOW_URL = "https://push2.eastmoney.com/api/qt/stock/fflow/daykline/get"
DATACENTER_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
MARKET_OVERVIEW_URL = "https://push2.eastmoney.com/api/qt/stock/get"

# Auth token for Eastmoney push2 (stable)
EM_UT = "fa5fd1943c7b386f172d6893dbbd1"

HEADERS = {
    "User-Agent": UA,
    "Referer": "https://quote.eastmoney.com/",
}


def _get_secid(code: str) -> str:
    """Convert 6-digit code to eastmoney secid (1.xxxxxx = SH, 0.xxxxxx = SZ)."""
    return f"1.{code}" if code.startswith("6") else f"0.{code}"


def get_stock_info(code: str) -> dict:
    """Get stock info: PE, PB, market cap, industry.

    Fields: f57=code, f58=name, f84=total_shares, f85=float_shares,
            f116=mcap, f117=float_mcap, f127=industry, f189=list_date,
            f162=PE_TTM, f167=PB, f168=PS, f173=ROE, f43=price
    """
    secid = _get_secid(code)
    params = {
        "fltt": "2", "invt": "2", "ut": EM_UT,
        "fields": "f57,f58,f84,f85,f116,f117,f127,f162,f167,f168,f170,f173,f189,f43",
        "secid": secid,
    }
    try:
        with httpx.Client(timeout=8) as client:
            r = client.get(PUSH2_URL, params=params, headers=HEADERS)
            d = r.json().get("data", {})
            if not d or not d.get("f57"):
                return {}
            return {
                "code": d.get("f57", ""),
                "name": d.get("f58", ""),
                "industry": d.get("f127", ""),
                "total_shares": d.get("f84", 0),
                "float_shares": d.get("f85", 0),
                "mcap": d.get("f116", 0),
                "float_mcap": d.get("f117", 0),
                "list_date": str(d.get("f189", "")),
                "price": (d.get("f43") or 0) / 100,
                "pe_ttm": d.get("f162"),
                "pb": d.get("f167"),
                "ps_ttm": d.get("f168"),
                "roe": d.get("f173"),
            }
    except Exception as e:
        logger.debug("Eastmoney stock_info failed for %s: %s", code, e)
        return {}


def get_capital_flow(code: str, days: int = 5) -> Optional[CapitalFlow]:
    """Get daily capital flow from Eastmoney push2."""
    secid = _get_secid(code)
    params = {
        "secid": secid,
        "fields1": "f1,f2,f3",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65",
        "klt": "101",
        "lmt": str(days),
    }
    try:
        with httpx.Client(timeout=8) as client:
            r = client.get(PUSH2_FLOW_URL, params=params, headers=HEADERS)
            data = r.json().get("data", {})
            klines = data.get("klines", [])
            if not klines:
                return None
            last = klines[-1].split(",")
            main_inflow = float(last[1]) if len(last) > 1 and last[1] != "-" else None
            return CapitalFlow(
                north_net_inflow=None,
                main_net_inflow=main_inflow,
                period=f"{days}d",
            )
    except Exception as e:
        logger.debug("Eastmoney capital flow failed for %s: %s", code, e)
        return None


def get_market_overview() -> Optional[MarketOverview]:
    """Get Shanghai Composite Index."""
    params = {
        "fltt": "2", "invt": "2",
        "fields": "f43,f44,f45,f46,f47,f57,f58,f60,f170",
        "secid": "1.000001",
    }
    try:
        with httpx.Client(timeout=8) as client:
            r = client.get(MARKET_OVERVIEW_URL, params=params, headers=HEADERS)
            d = r.json().get("data", {})
            if not d:
                return None
            close = (d.get("f43") or 0) / 100
            change = (d.get("f170") or 0) / 100
            return MarketOverview(
                index_code="000001",
                index_name="上证指数",
                close=round(close, 2),
                change_pct=round(change, 2),
            )
    except Exception as e:
        logger.debug("Eastmoney market overview failed: %s", e)
        return None


def eastmoney_datacenter(
    report_name: str,
    columns: str = "ALL",
    filter_str: str = "",
    page_size: int = 50,
    sort_columns: str = "",
    sort_types: str = "-1",
) -> list[dict]:
    """Unified Eastmoney datacenter query."""
    params = {
        "reportName": report_name,
        "columns": columns,
        "filter": filter_str,
        "pageNumber": "1",
        "pageSize": str(page_size),
        "sortColumns": sort_columns,
        "sortTypes": sort_types,
        "source": "WEB",
        "client": "WEB",
    }
    headers = {"User-Agent": UA}
    try:
        with httpx.Client(timeout=10) as client:
            r = client.get(DATACENTER_URL, params=params, headers=headers)
            d = r.json()
            if d.get("result") and d["result"].get("data"):
                return d["result"]["data"]
            return []
    except Exception as e:
        logger.debug("Eastmoney datacenter failed [%s]: %s", report_name, e)
        return []


def get_dragon_tiger(code: str, page_size: int = 10) -> list[dict]:
    """Get dragon & tiger list (龙虎榜) for a stock."""
    filter_str = f'(SECURITY_CODE="{code}")'
    data = eastmoney_datacenter(
        "RPT_DAILYBILLBOARD_DETAILSNEW",
        filter_str=filter_str,
        page_size=page_size,
        sort_columns="TRADE_DATE",
        sort_types="-1",
    )
    results = []
    for item in data[:page_size]:
        results.append({
            "date": str(item.get("TRADE_DATE", "")),
            "reason": str(item.get("EXPLAIN", "")),
            "net_buy": float(item.get("NET_BUY_AMT") or 0),
            "buy_amount": float(item.get("BUY_AMT") or 0),
            "sell_amount": float(item.get("SELL_AMT") or 0),
        })
    return results


def get_margin_trading(code: str, page_size: int = 30) -> list[dict]:
    """Get margin trading (融资融券) data."""
    filter_str = f'(SECURITY_CODE="{code}")'
    data = eastmoney_datacenter(
        "RPT_MUTUAL_MARGIN_LIST",
        filter_str=filter_str,
        page_size=page_size,
        sort_columns="TRADE_DATE",
        sort_types="-1",
    )
    results = []
    for item in data[:page_size]:
        results.append({
            "date": str(item.get("TRADE_DATE", "")),
            "fin_balance": float(item.get("RZYE") or 0),
            "fin_buy": float(item.get("RZMRE") or 0),
            "fin_repay": float(item.get("RZCHE") or 0),
            "sec_balance": float(item.get("RQYE") or 0),
        })
    return results


def get_holder_count(code: str, page_size: int = 10) -> list[dict]:
    """Get shareholder count (股东户数)."""
    filter_str = f'(SECURITY_CODE="{code}")'
    data = eastmoney_datacenter(
        "RPT_AVE_LIST_FREEHOLDERS",
        filter_str=filter_str,
        page_size=page_size,
        sort_columns="END_DATE",
        sort_types="-1",
    )
    results = []
    for item in data[:page_size]:
        results.append({
            "date": str(item.get("END_DATE", "")),
            "holders": int(item.get("HOLDER_NUM") or 0),
            "change_pct": float(item.get("HOLDER_NUM_CHANGE_RATE") or 0),
            "avg_holding": float(item.get("AVG_FREE_SHARES") or 0),
        })
    return results


def get_dividend_history(code: str, page_size: int = 20) -> list[dict]:
    """Get dividend history (分红送转)."""
    filter_str = f'(SECURITY_CODE="{code}")'
    data = eastmoney_datacenter(
        "RPT_CUSTOM_DIVIDEND_LIST",
        filter_str=filter_str,
        page_size=page_size,
        sort_columns="NOTICE_DATE",
        sort_types="-1",
    )
    results = []
    for item in data[:page_size]:
        results.append({
            "date": str(item.get("NOTICE_DATE", "")),
            "cash_per_share": float(item.get("ASSIGNMENT_PROP") or 0),
            "bonus_shares": float(item.get("BONUS_SHARE_RATIO") or 0),
            "convert_shares": float(item.get("CONVERT_RATIO") or 0),
        })
    return results
