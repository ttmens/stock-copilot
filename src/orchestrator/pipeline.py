"""Orchestration pipeline — fetch → compute hard signals → analyze → fuse → report → persist.

Updated 2026-05-24: Integrated hard signal computation, signal fusion engine,
and SQLite persistence (SignalDB).
"""

import asyncio
import logging
from datetime import date
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
from src.agents.announcement import AnnouncementAgent
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
    persist: bool = True,
) -> Report:
    """Run the full analysis pipeline.

    1. Check trading day
    2. Load watchlist
    3. Fetch data (parallel)
    4. Compute hard signals (deterministic)
    5. Run 3 LLM agents per stock
    6. Fuse signals (hard + soft + gate)
    7. Generate report
    8. Persist to SQLite
    9. Notify (optional)
    """
    settings = get_settings()
    today = date.today()

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

    # 5. Compute hard signals + run agents + fuse (per stock)
    analyses, fused_records = await _analyze_and_fuse(snapshots)

    # 6. Generate report
    report = generate_report(analyses, report_type, market, failed_symbols)
    logger.info("Report generated: %s", report.file_path)

    # 7. Persist to SQLite
    if persist and fused_records:
        try:
            from src.data.db_manager import SignalDB
            from src.data.signal_fusion import FusedSignal

            db = SignalDB()
            for code, fused in fused_records.items():
                # Save stock metadata
                snap = next((s for s in snapshots if s.code == code), None)
                if snap:
                    db.upsert_stock(
                        code=code,
                        name=snap.name,
                        industry="",
                        market="sh" if code.startswith("6") else "sz",
                    )
            db.save_batch(list(fused_records.values()))
            logger.info("Signals persisted to SQLite: %d records", len(fused_records))
        except Exception as e:
            logger.warning("Signal persistence failed: %s", e)

    # 8. Notify
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


async def _analyze_and_fuse(
    snapshots: list[StockSnapshot],
) -> tuple[list[StockAnalysis], dict]:
    """Run hard signal computation + LLM agents + fusion for each stock.

    Returns:
        (analyses, fused_records) where fused_records maps code -> SignalRecord
    """
    from src.data.hard_signals import compute_hard_signals
    from src.data.signal_fusion import fuse_signals

    tech = TechnicalAgent()
    fund = FundamentalAgent()
    cap = CapitalAgent()
    ann = AnnouncementAgent()

    async def process_one(snap: StockSnapshot):
        # A. Compute hard signals (fast, no LLM)
        hard = compute_hard_signals(
            bars=snap.bars or [],
            ma=snap.ma if hasattr(snap, 'ma') and snap.ma and snap.ma.ma5 else None,
            valuation=snap.valuation if hasattr(snap, 'valuation') else None,
            capital=snap.capital if hasattr(snap, 'capital') else None,
        )

        # B. Run LLM agents
        t_result = await tech.analyze(snap)
        f_result = await fund.analyze(snap)
        c_result = await cap.analyze(snap)
        # C. Announcement analysis
        ann_titles = [a.title for a in snap.announcements] if snap.announcements else []
        a_result = await ann.analyze(snap.code, snap.name, ann_titles)

        agents = {
            "technical": t_result,
            "fundamental": f_result,
            "capital": c_result,
        }

        # D. Fuse signals
        fused = fuse_signals(
            code=snap.code,
            name=snap.name,
            hard=hard,
            agents=agents,
            is_st="ST" in snap.name,
            dragon_tiger_entries=[e.model_dump() for e in snap.dragon_tiger] if snap.dragon_tiger else None,
            announcement_result=a_result,
        )

        analysis = StockAnalysis(
            snapshot=snap,
            technical=t_result,
            fundamental=f_result,
            capital=c_result,
            announcement=a_result,
            overall_sentiment=fused.final_signal,
            overall_focus=fused.signal_label,
        )

        return snap.code, analysis, fused, hard

    results = await asyncio.gather(
        *[process_one(s) for s in snapshots],
        return_exceptions=True,
    )

    analyses: list[StockAnalysis] = []
    fused_records: dict = {}

    for r in results:
        if isinstance(r, BaseException):
            logger.error("Analysis failed: %s", r)
        else:
            code, analysis, fused, hard = r
            analyses.append(analysis)

            # Build SignalRecord for DB
            from src.data.db_manager import SignalRecord
            from datetime import date as date_type
            record = SignalRecord(
                code=code,
                trade_date=date_type.today(),
                report_type="pre",
                momentum_20d=hard.momentum_20d,
                momentum_5d=hard.momentum_5d,
                ma_alignment=hard.ma_alignment,
                volume_ratio=hard.volume_ratio,
                pe_percentile=hard.pe_percentile,
                main_net_inflow=hard.main_net_inflow,
                hard_score=hard.composite_score,
                llm_sentiment="bullish" if fused.soft_score > 0.2 else ("bearish" if fused.soft_score < -0.2 else "neutral") if fused.soft_score != 0 else None,
                llm_confidence=fused.confidence,
                soft_score=fused.soft_score,
                gate_score=fused.gate_score,
                final_score=fused.final_score,
                final_signal=fused.final_signal,
                signal_label=fused.signal_label,
                fetch_errors=analysis.snapshot.fetch_errors,
            )
            fused_records[code] = record

    return analyses, fused_records
