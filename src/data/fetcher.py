"""Data fetcher — AkShare wrapper with retry and fallback."""

import asyncio
import logging
import time
from datetime import date, datetime
from typing import Optional

import akshare as ak
import pandas as pd

from src.config import get_settings
from src.data.models import (
    Announcement,
    CapitalFlow,
    MovingAverages,
    OHLCVBar,
    MarketOverview,
    StockSnapshot,
    WatchlistItem,
)

logger = logging.getLogger(__name__)


def _retry(func, max_retries: int = 3, delay: int = 2, **kwargs):
    """Retry a sync function with exponential backoff."""
    last_err: Exception | None = None
    for attempt in range(max_retries):
        try:
            return func(**kwargs)
        except Exception as e:
            last_err = e
            if attempt < max_retries - 1:
                wait = delay * (2 ** attempt)
                logger.warning("Retry %d/%d for %s: %s", attempt + 1, max_retries, func.__name__, e)
                time.sleep(wait)
    if last_err is not None:
        logger.error("All retries failed for %s: %s", func.__name__, last_err)
        raise last_err
    raise RuntimeError("Unknown retry failure")


def _get_market(code: str) -> str:
    """Determine market prefix from stock code."""
    return "sh" if code.startswith("6") else "sz"


def calc_ma(closes: list[float]) -> MovingAverages:
    """Calculate MA5/10/20 from a list of closing prices."""
    def ma(n):
        return sum(closes[-n:]) / n if len(closes) >= n else None
    return MovingAverages(ma5=ma(5), ma10=ma(10), ma20=ma(20))


class DataFetcher:
    """Fetches stock data from AkShare with error handling."""

    def __init__(self):
        settings = get_settings()
        self.bar_count = settings.data.bar_count
        self.retry = settings.data.retry
        self.retry_delay = settings.data.retry_delay
        self.announcement_days = settings.data.announcement_days

    async def fetch_stock(self, code: str, name: str) -> StockSnapshot:
        """Fetch all data for a single stock.

        Individual sub-fetch failures are recorded in fetch_errors but don't raise.
        """
        bars: list[OHLCVBar] = []
        ma = MovingAverages()
        announcements: list[Announcement] = []
        capital: Optional[CapitalFlow] = None
        errors: list[str] = []

        # 1. Daily bars (required)
        try:
            bars, ma = await asyncio.to_thread(self._fetch_daily_bars, code)
        except Exception as e:
            errors.append(f"daily: {e}")
            logger.error("Failed to fetch daily bars for %s: %s", code, e)

        # 2. Announcements (optional)
        try:
            announcements = await asyncio.to_thread(self._fetch_announcements, code)
        except Exception as e:
            errors.append(f"announcements: {e}")
            logger.warning("Failed to fetch announcements for %s: %s", code, e)

        # 3. Capital flow (optional)
        try:
            capital = await asyncio.to_thread(self._fetch_capital_flow, code)
        except Exception as e:
            errors.append(f"capital: {e}")
            logger.debug("Capital flow unavailable for %s: %s", code, e)

        return StockSnapshot(
            code=code,
            name=name,
            fetched_at=datetime.now(),
            bars=bars,
            ma=ma,
            announcements=announcements,
            capital=capital,
            fetch_errors=errors,
        )

    def _fetch_daily_bars(self, code: str) -> tuple[list[OHLCVBar], MovingAverages]:
        """Fetch daily OHLCV bars and compute MAs."""
        df = _retry(
            ak.stock_zh_a_hist,
            max_retries=self.retry,
            delay=self.retry_delay,
            symbol=code,
            period="daily",
            adjust="qfq",
        )

        # Take last N bars
        df = df.tail(self.bar_count).copy()

        bars = []
        for _, row in df.iterrows():
            bars.append(OHLCVBar(
                date=pd.to_datetime(row["日期"]).date(),
                open=float(row["开盘"]),
                high=float(row["最高"]),
                low=float(row["最低"]),
                close=float(row["收盘"]),
                volume=float(row["成交量"]),
                amount=float(row["成交额"]) if "成交额" in row else None,
            ))

        closes = [b.close for b in bars]
        ma = calc_ma(closes)

        return bars, ma

    def _fetch_announcements(self, code: str) -> list[Announcement]:
        """Fetch recent announcements for a stock."""
        try:
            df = _retry(
                ak.stock_notice_report,
                max_retries=self.retry,
                delay=self.retry_delay,
                symbol=code,
            )
        except Exception:
            # Some versions of AkShare use different params
            return []

        if df is None or df.empty:
            return []

        announcements = []
        for _, row in df.head(20).iterrows():
            try:
                announcements.append(Announcement(
                    title=str(row.get("标题", row.get("title", ""))),
                    date=pd.to_datetime(row.get("日期", row.get("date", datetime.now()))).date(),
                    url=str(row.get("链接", row.get("url", ""))) or None,
                ))
            except Exception:
                continue

        return announcements

    def _fetch_capital_flow(self, code: str) -> Optional[CapitalFlow]:
        """Fetch capital flow data (northbound + main force)."""
        market = _get_market(code)

        try:
            df = _retry(
                ak.stock_individual_fund_flow,
                max_retries=self.retry,
                delay=self.retry_delay,
                stock=code,
                market=market,
            )
        except Exception:
            return None

        if df is None or df.empty:
            return None

        # Get most recent row's net inflow if available
        last_row = df.iloc[-1]
        main_inflow = None
        for col in ["主力净流入-净额", "主力净流入", "main_net_inflow"]:
            if col in last_row:
                try:
                    main_inflow = float(last_row[col])
                    break
                except (ValueError, TypeError):
                    pass

        return CapitalFlow(
            north_net_inflow=None,  # Individual northbound not easily available
            main_net_inflow=main_inflow,
            period="1d",
        )

    async def fetch_market_overview(self) -> Optional[MarketOverview]:
        """Fetch Shanghai Composite Index overview."""
        try:
            df = await asyncio.to_thread(
                _retry,
                ak.stock_zh_index_daily,
                max_retries=self.retry,
                delay=self.retry_delay,
                symbol="sh000001",
            )
        except Exception as e:
            logger.warning("Failed to fetch market overview: %s", e)
            return None

        if df is None or df.empty:
            return None

        last = df.iloc[-1]
        close_val = float(last.get("close", last.get("收盘", 0)))
        prev_close = float(df.iloc[-2].get("close", df.iloc[-2].get("收盘", 0))) if len(df) > 1 else close_val
        change_pct = ((close_val - prev_close) / prev_close * 100) if prev_close else 0

        return MarketOverview(
            index_code="000001",
            index_name="上证指数",
            close=round(close_val, 2),
            change_pct=round(change_pct, 2),
        )


async def fetch_all(
    items: list[WatchlistItem] | list[tuple[str, str]],
) -> tuple[list[StockSnapshot], list[str]]:
    """Fetch all stocks in parallel. Single-stock failures don't block others.

    Accepts either WatchlistItem list or (code, name) tuples.
    """
    fetcher = DataFetcher()

    # Normalize to (code, name) tuples
    pairs: list[tuple[str, str]] = []
    for item in items:
        if isinstance(item, WatchlistItem):
            pairs.append((item.code, item.name))
        else:
            pairs.append(item)  # type: ignore[arg-type]

    async def _fetch_one(code: str, name: str) -> StockSnapshot:
        return await fetcher.fetch_stock(code, name)

    results: list[StockSnapshot | BaseException] = await asyncio.gather(
        *[_fetch_one(code, name) for code, name in pairs],
        return_exceptions=True,
    )

    snapshots: list[StockSnapshot] = []
    failed: list[str] = []
    for i, result in enumerate(results):
        if isinstance(result, BaseException):
            code = pairs[i][0] if i < len(pairs) else "?"
            failed.append(code)
            logger.error("Failed to fetch %s: %s", code, result)
        else:
            snapshots.append(result)
            if result.fetch_errors:
                logger.warning("%s fetch errors: %s", result.code, result.fetch_errors)

    return snapshots, failed
