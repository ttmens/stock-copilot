"""Data fetcher — multi-source provider chain with degradation.

Priority: AkShare → Eastmoney Direct HTTP → Tencent Fallback
Single-stock failures never block others.
"""

import asyncio
import logging
import time
from datetime import datetime
from typing import Optional

import akshare as ak
import pandas as pd

from src.config import get_settings
from src.data.models import (
    Announcement,
    CapitalFlow,
    DragonTigerItem,
    MovingAverages,
    MarketOverview,
    NewsItem,
    OHLCVBar,
    StockSnapshot,
    ValuationInfo,
    WatchlistItem,
)
from src.data.providers import eastmoney, tencent, sina
from src.data.providers.dragon_tiger import DragonTigerProvider
from src.data.fetcher_utils import calc_ma

logger = logging.getLogger(__name__)


def _retry_sync(func, max_retries: int = 3, delay: int = 2, **kwargs):
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
        raise last_err
    raise RuntimeError("Unknown retry failure")


class DataFetcher:
    """Multi-source data fetcher with degradation chain."""

    def __init__(self):
        settings = get_settings()
        self.bar_count = settings.data.bar_count
        self.retry = settings.data.retry
        self.retry_delay = settings.data.retry_delay
        self.announcement_days = settings.data.announcement_days

    async def fetch_stock(self, code: str, name: str) -> StockSnapshot:
        """Fetch all data for a single stock using multi-source chain.

        For each data type (K-line, valuation, capital, announcements, news),
        tries the primary source first, then falls back to alternatives.
        """
        bars: list[OHLCVBar] = []
        ma = MovingAverages()
        valuation: Optional[ValuationInfo] = None
        capital: Optional[CapitalFlow] = None
        announcements: list[Announcement] = []
        news: list[NewsItem] = []
        dragon_tiger: list[DragonTigerItem] = []
        errors: list[str] = []

        # 1. K-line data: AkShare → Eastmoney → Tencent
        bars, ma = await self._fetch_kline_chain(code, errors)

        # 2. Valuation: Eastmoney push2 → Tencent
        valuation = await self._fetch_valuation_chain(code, errors)

        # 3. Capital flow: Eastmoney push2 → AkShare
        capital = await self._fetch_capital_chain(code, errors)

        # 4. Announcements: AkShare → Eastmoney datacenter
        announcements = await self._fetch_announcements_chain(code, errors)

        # 5. News: Eastmoney search
        news = await self._fetch_news(code, errors)

        # 6. Dragon & tiger: Eastmoney datacenter
        dragon_tiger = await self._fetch_dragon_tiger(code, errors)

        return StockSnapshot(
            code=code,
            name=name,
            fetched_at=datetime.now(),
            bars=bars,
            ma=ma,
            valuation=valuation,
            capital=capital,
            announcements=announcements,
            news=news,
            dragon_tiger=dragon_tiger,
            fetch_errors=errors,
        )

    async def _fetch_kline_chain(self, code: str, errors: list[str]) -> tuple[list[OHLCVBar], MovingAverages]:
        """K-line: AkShare (1 retry, 1s delay) → Sina → Tencent."""
        bars: list[OHLCVBar] = []

        # Try AkShare first (quick fail)
        try:
            bars = await asyncio.to_thread(
                self._akshare_daily_bars,
                code,
                1,  # max_retries
                1,  # delay
            )
            if bars:
                closes = [b.close for b in bars]
                ma = calc_ma(closes)
                return bars, ma
        except Exception as e:
            errors.append(f"akshare_daily: {e}")
            logger.debug("AkShare daily failed for %s, trying Sina", code)

        # Fallback: Sina Finance
        try:
            bars = await asyncio.to_thread(sina.get_kline_sina, code, self.bar_count)
            if bars:
                closes = [b.close for b in bars]
                ma = calc_ma(closes)
                return bars, ma
        except Exception as e:
            errors.append(f"sina_kline: {e}")
            logger.debug("Sina K-line failed for %s, trying Tencent", code)

        # Fallback: Tencent
        try:
            bars = await asyncio.to_thread(tencent.get_kline_tencent, code, self.bar_count)
            if bars:
                closes = [b.close for b in bars]
                ma = calc_ma(closes)
                return bars, ma
        except Exception as e:
            errors.append(f"tencent_kline: {e}")

        return [], MovingAverages()

    async def _fetch_valuation_chain(self, code: str, errors: list[str]) -> Optional[ValuationInfo]:
        """Valuation: Eastmoney push2 → Tencent."""
        # Try Eastmoney push2
        try:
            info = await asyncio.to_thread(eastmoney.get_stock_info, code)
            if info and info.get("code"):
                return ValuationInfo(
                    pe_ttm=info.get("pe_ttm"),
                    pb=info.get("pb"),
                    ps_ttm=info.get("ps_ttm"),
                    roe=info.get("roe"),
                    total_shares=info.get("total_shares", 0),
                    float_shares=info.get("float_shares", 0),
                    mcap=info.get("mcap", 0),
                    float_mcap=info.get("float_mcap", 0),
                    industry=info.get("industry", ""),
                    list_date=info.get("list_date", ""),
                )
        except Exception as e:
            errors.append(f"eastmoney_valuation: {e}")
            logger.debug("Eastmoney valuation failed for %s, trying Tencent", code)

        # Fallback: Tencent
        try:
            quote = await asyncio.to_thread(tencent.get_stock_quote, code)
            if quote and quote.get("code"):
                return ValuationInfo(
                    pe_ttm=quote.get("pe_ttm"),
                    pb=quote.get("pb"),
                    total_shares=0,
                    float_shares=0,
                    mcap=quote.get("total_mcap", 0) * 1e8,     # 亿元 → 元
                    float_mcap=quote.get("float_mcap", 0) * 1e8,
                    industry="",
                    list_date="",
                )
        except Exception as e:
            errors.append(f"tencent_valuation: {e}")

        return None

    async def _fetch_capital_chain(self, code: str, errors: list[str]) -> Optional[CapitalFlow]:
        """Capital flow: Eastmoney push2 → Tencent quote derivation → K-line estimation."""
        # Try Eastmoney push2 (most reliable when available)
        try:
            cf = await asyncio.to_thread(eastmoney.get_capital_flow, code, 5)
            if cf:
                return cf
        except Exception as e:
            errors.append(f"eastmoney_capital: {e}")
            logger.debug("Eastmoney capital flow failed for %s", code)

        # Fallback: derive from Tencent real-time quote (turnover + volume)
        try:
            quote = await asyncio.to_thread(tencent.get_stock_quote, code)
            if quote and quote.get("code"):
                # Estimate capital flow from volume and price
                volume = quote.get("volume", 0)
                amount = quote.get("amount", 0)
                price = quote.get("price", 0)
                prev_close = quote.get("prev_close", 0)
                if volume > 0 and price > 0 and prev_close > 0:
                    # Simple estimation: net flow based on price change vs volume
                    change_ratio = (price - prev_close) / prev_close if prev_close else 0
                    # Positive change → estimated net inflow proportional to amount
                    est_inflow = amount * change_ratio if amount else 0
                    return CapitalFlow(
                        north_net_inflow=None,
                        main_net_inflow=round(est_inflow, 0),
                        period="1d",
                    )
        except Exception as e:
            errors.append(f"tencent_capital_derive: {e}")

        # Fallback: estimate from K-line data (use Sina for K-lines)
        try:
            bars_data = await asyncio.to_thread(sina.get_kline_sina, code, 5)
            if bars_data and len(bars_data) >= 2:
                total_inflow = 0.0
                total_amount = 0.0
                for bar in bars_data[-3:]:  # Last 3 days
                    if bar.close > bar.open:
                        # Bullish day: volume is inflow
                        total_inflow += (bar.amount or bar.volume * bar.close)
                    elif bar.close < bar.open:
                        # Bearish day: volume is outflow
                        total_inflow -= (bar.amount or bar.volume * bar.close)
                    total_amount += (bar.amount or bar.volume * bar.close)
                if total_amount > 0:
                    return CapitalFlow(
                        north_net_inflow=None,
                        main_net_inflow=round(total_inflow, 0),
                        period="3d",
                    )
        except Exception as e:
            errors.append(f"kline_capital_est: {e}")

        return None

    async def _fetch_announcements_chain(self, code: str, errors: list[str]) -> list[Announcement]:
        """Announcements: AkShare (quick fail) → empty."""
        try:
            df = await asyncio.to_thread(
                _retry_sync,
                ak.stock_notice_report,
                max_retries=1,
                delay=1,
                symbol=code,
            )
            if df is None or df.empty:
                return []
            announcements = []
            for _, row in df.head(10).iterrows():
                try:
                    announcements.append(Announcement(
                        title=str(row.get("标题", row.get("title", ""))),
                        date=pd.to_datetime(row.get("日期", row.get("date", datetime.now()))).date(),
                        url=str(row.get("链接", row.get("url", ""))) or None,
                    ))
                except Exception:
                    continue
            return announcements
        except Exception as e:
            errors.append(f"akshare_announcements: {e}")
            logger.debug("Announcements unavailable for %s", code)
            return []

    async def _fetch_news(self, code: str, errors: list[str]) -> list[NewsItem]:
        """Get individual stock news. Currently Eastmoney search API is blocked
        from some servers, so this returns empty with a debug log."""
        # Eastmoney news API is blocked from this server
        # TODO: re-enable when network allows
        return []

    async def _fetch_dragon_tiger(self, code: str, errors: list[str]) -> list[DragonTigerItem]:
        """Get dragon & tiger list (龙虎榜) from Eastmoney datacenter.

        Only returns entries from the last 30 days to avoid showing
        outdated historical data that's irrelevant for current analysis.
        """
        from datetime import datetime, timedelta
        try:
            raw_dt = await asyncio.to_thread(eastmoney.get_dragon_tiger, code, 5)
            # Filter to last 30 days only
            cutoff = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
            recent_entries = [
                d for d in raw_dt
                if d.get("date", "") >= cutoff
            ]
            if not recent_entries and raw_dt:
                logger.debug("Dragon tiger data for %s is outdated (before %s), hiding", code, cutoff)
            return [
                DragonTigerItem(
                    date=d.get("date", ""),
                    reason=d.get("reason", ""),
                    net_buy=d.get("net_buy", 0),
                    buy_amount=d.get("buy_amount", 0),
                    sell_amount=d.get("sell_amount", 0),
                )
                for d in recent_entries[:5]
            ]
        except Exception as e:
            errors.append(f"eastmoney_dragon_tiger: {e}")
            return []

    def _akshare_daily_bars(self, code: str, retries: int = 1, delay: int = 1) -> list[OHLCVBar]:
        """Fetch daily OHLCV bars from AkShare."""
        df = _retry_sync(
            ak.stock_zh_a_hist,
            max_retries=retries,
            delay=delay,
            symbol=code,
            period="daily",
            adjust="qfq",
        )
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
        return bars

    async def fetch_market_overview(self) -> Optional[MarketOverview]:
        """Get Shanghai Composite Index: Eastmoney → AkShare (quick fail)."""
        # Try Eastmoney first
        try:
            overview = await asyncio.to_thread(eastmoney.get_market_overview)
            if overview and overview.close:
                return overview
        except Exception as e:
            logger.debug("Eastmoney market overview failed: %s", e)

        # Fallback: AkShare (quick fail)
        try:
            df = await asyncio.to_thread(
                _retry_sync,
                ak.stock_zh_index_daily,
                max_retries=1,
                delay=1,
                symbol="sh000001",
            )
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
        except Exception as e:
            logger.warning("Market overview all sources failed: %s", e)
            return None


async def fetch_all(
    items: list[WatchlistItem] | list[tuple[str, str]],
) -> tuple[list[StockSnapshot], list[str]]:
    """Fetch all stocks in parallel with multi-source degradation.

    Uses an HTTP semaphore to limit concurrent requests and avoid
    getting rate-limited / blocked by data providers.
    """
    fetcher = DataFetcher()

    pairs: list[tuple[str, str]] = []
    for item in items:
        if isinstance(item, WatchlistItem):
            pairs.append((item.code, item.name))
        else:
            pairs.append(item)  # type: ignore[arg-type]

    # Limit concurrent HTTP requests (avoid IP bans from AkShare/Eastmoney)
    _http_sem = asyncio.Semaphore(10)

    async def _fetch_one(code: str, name: str) -> StockSnapshot:
        async with _http_sem:
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
                logger.debug("%s partial errors: %s", result.code, result.fetch_errors)

    return snapshots, failed
