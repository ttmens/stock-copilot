"""Orchestration pipeline — fetch → analyze → report → notify."""

import asyncio
import logging
from pathlib import Path
from typing import Optional

from src.config import get_settings
from src.data.calendar import is_trading_day
from src.data.fetcher import DataFetcher, fetch_all
from src.data.models import (
    MarketOverview,
    Report,
    ReportType,
    StockAnalysis,
    StockSnapshot,
    WatchlistItem,
)
from src.agents.technical import TechnicalAgent
from src.agents.fundamental import FundamentalAgent
from src.agents.capital import CapitalAgent
from src.reports.generator import generate_report

logger = logging.getLogger(__name__)


def _load_watchlist(symbols: list[str] | None = None) -> list[WatchlistItem]:
    """Load watchlist from YAML or explicit symbols list."""
    import yaml

    settings = get_settings()
    config_path = Path(__file__).resolve().parent.parent.parent / "config" / "watchlist.yaml"

    if symbols:
        return [WatchlistItem(code=s, name=s) for s in symbols]

    if config_path.exists():
        with open(config_path) as f:
            data = yaml.safe_load(f)
        return [WatchlistItem(**item) for item in data.get("symbols", [])]

    raise FileNotFoundError(f"Watchlist not found: {config_path}")


async def run_analysis(
    report_type: ReportType,
    symbols: list[str] | None = None,
) -> Report:
    """Run the full analysis pipeline.

    1. Check trading day
    2. Load watchlist
    3. Fetch data (parallel)
    4. Run 3 agents per stock (sequential per stock, parallel across stocks)
    5. Generate report
    6. Notify (optional)
    """
    settings = get_settings()

    # 1. Check trading day
    if not is_trading_day():
        logger.info("Today is not a trading day, skipping analysis")
        raise RuntimeError("非交易日，跳过分析")

    # 2. Load watchlist
    watchlist = _load_watchlist(symbols)
    logger.info("Watchlist: %d symbols", len(watchlist))

    # 3. Fetch data
    fetcher = DataFetcher()
    snapshots, failed_symbols = await fetch_all(watchlist)
    logger.info("Fetched: %d success, %d failed", len(snapshots), len(failed_symbols))

    # 4. Market overview
    market: Optional[MarketOverview] = None
    if settings.report.include_market_overview:
        try:
            market = await fetcher.fetch_market_overview()
        except Exception as e:
            logger.warning("Market overview failed: %s", e)

    # 5. Run agents
    analyses = await _run_agents(snapshots)

    # 6. Generate report
    report = generate_report(analyses, report_type, market, failed_symbols)
    logger.info("Report generated: %s", report.file_path)

    # 7. Notify
    try:
        from src.notify.base import get_notifier
        notifier = get_notifier()
        if notifier:
            await notifier.send(report)
    except ImportError:
        logger.debug("Notify module not yet implemented, skipping")
    except Exception as e:
        logger.warning("Notification failed: %s", e)

    return report


async def _run_agents(snapshots: list[StockSnapshot]) -> list[StockAnalysis]:
    """Run all 3 agents for each snapshot.

    Agents are sequential per stock (to save tokens), stocks are parallel.
    """
    tech = TechnicalAgent()
    fund = FundamentalAgent()
    cap = CapitalAgent()

    async def analyze_one(snap: StockSnapshot) -> StockAnalysis:
        t_result = await tech.analyze(snap)
        f_result = await fund.analyze(snap)
        c_result = await cap.analyze(snap)

        return StockAnalysis(
            snapshot=snap,
            technical=t_result,
            fundamental=f_result,
            capital=c_result,
        )

    results = await asyncio.gather(
        *[analyze_one(s) for s in snapshots],
        return_exceptions=True,
    )

    analyses: list[StockAnalysis] = []
    for r in results:
        if isinstance(r, BaseException):
            logger.error("Agent analysis failed: %s", r)
        else:
            analyses.append(r)

    return analyses
