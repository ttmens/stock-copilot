"""Orchestration pipeline — fetch → compute hard signals → analyze → fuse → report → persist."""

import asyncio
import logging
from datetime import date
from pathlib import Path
from typing import Optional

from src.config import get_settings
from src.data.calendar import is_trading_day
from src.data.fetcher import DataFetcher, fetch_all
from src.data.models import (
    AgentResult,
    MarketOverview,
    Report,
    ReportType,
    StockAnalysis,
    StockSnapshot,
    WatchlistItem,
)
from src.agents.technical import TechnicalAgent
from src.agents.capital import CapitalAgent
from src.agents.announcement import AnnouncementAgent
from src.reports.generator import generate_report
from src.watchlist.manager import WatchlistManager

logger = logging.getLogger(__name__)


def _load_watchlist(symbols: list[str] | None = None) -> list[WatchlistItem]:
    if symbols:
        return [WatchlistItem(code=s, name=s) for s in symbols]
    return WatchlistManager().list_items()


def _fundamental_from_announcement(ann: AgentResult, snap: StockSnapshot) -> AgentResult:
    """Rule-based fundamental layer from announcement LLM (no duplicate LLM call)."""
    return AgentResult(
        agent_name="fundamental",
        status=ann.status,
        sentiment=ann.sentiment,
        summary=ann.summary or f"{snap.name} 公告面参考 Announcement 分析",
        focus_points=list(ann.focus_points),
        risk_points=list(ann.risk_points),
    )


async def run_analysis(
    report_type: ReportType,
    symbols: list[str] | None = None,
    persist: bool = True,
) -> Report:
    """Full analysis pipeline with LLM agents."""
    settings = get_settings()

    if not is_trading_day():
        logger.info("Today is not a trading day, skipping analysis")
        raise RuntimeError("非交易日，跳过分析")

    watchlist = _load_watchlist(symbols)
    logger.info("Watchlist: %d symbols", len(watchlist))

    fetcher = DataFetcher()
    snapshots, failed_symbols = await fetch_all(watchlist)
    logger.info("Fetched: %d success, %d failed", len(snapshots), len(failed_symbols))

    market: Optional[MarketOverview] = None
    if settings.report.include_market_overview:
        try:
            market = await fetcher.fetch_market_overview()
        except Exception as e:
            logger.warning("Market overview failed: %s", e)

    analyses, fused_records = await _analyze_and_fuse(snapshots, report_type)
    report = generate_report(analyses, report_type, market, failed_symbols)
    logger.info("Report generated: %s", report.file_path)

    if persist and fused_records:
        try:
            from src.data.db_manager import SignalDB

            db = SignalDB()
            for code in fused_records:
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

    try:
        from src.notify.base import get_notifier
        notifier = get_notifier()
        if notifier:
            await notifier.send(report)
    except Exception as e:
        logger.warning("Notification failed: %s", e)

    return report


async def run_fast_analysis(symbols: list[str] | None = None) -> dict:
    """Fast intraday path: fetch + hard signals only, no LLM."""
    if not is_trading_day():
        return {"skipped": True, "reason": "non_trading_day"}

    from src.data.hard_signals import compute_hard_signals
    from src.data.db_manager import SignalDB

    watchlist = _load_watchlist(symbols)
    snapshots, failed_symbols = await fetch_all(watchlist)
    db = SignalDB()
    today = date.today()
    count = 0

    for snap in snapshots:
        hard = compute_hard_signals(
            bars=snap.bars or [],
            ma=snap.ma if snap.ma and snap.ma.ma5 else None,
            valuation=snap.valuation,
            capital=snap.capital,
        )
        label = "🟢 偏多" if hard.composite_score > 0.2 else (
            "🔴 偏空" if hard.composite_score < -0.2 else "⚪ 观望"
        )
        db.upsert_intraday(
            snap.code, today, hard.composite_score, hard.composite_score, label,
        )
        count += 1

    logger.info("[fast] Updated %d intraday quotes", count)
    return {"count": count, "failed_symbols": failed_symbols}


async def _analyze_and_fuse(
    snapshots: list[StockSnapshot],
    report_type: ReportType,
) -> tuple[list[StockAnalysis], dict]:
    from src.data.hard_signals import compute_hard_signals
    from src.data.signal_fusion import fuse_signals

    settings = get_settings()
    tech = TechnicalAgent()
    cap = CapitalAgent()
    ann = AnnouncementAgent()
    concurrency = max(1, settings.pipeline.llm_concurrency)
    sem = asyncio.Semaphore(concurrency)

    async def process_one(snap: StockSnapshot):
        async with sem:
            hard = compute_hard_signals(
                bars=snap.bars or [],
                ma=snap.ma if snap.ma and snap.ma.ma5 else None,
                valuation=snap.valuation,
                capital=snap.capital,
            )
            ann_titles = [a.title for a in snap.announcements] if snap.announcements else []
            t_result, c_result, a_result = await asyncio.gather(
                tech.analyze(snap),
                cap.analyze(snap),
                ann.analyze(snap.code, snap.name, ann_titles),
            )
            f_result = _fundamental_from_announcement(a_result, snap)

            agents = {
                "technical": t_result,
                "fundamental": f_result,
                "capital": c_result,
            }
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

    results = await asyncio.gather(*[process_one(s) for s in snapshots], return_exceptions=True)

    analyses: list[StockAnalysis] = []
    fused_records: dict = {}

    for r in results:
        if isinstance(r, BaseException):
            logger.error("Analysis failed: %s", r)
            continue
        code, analysis, fused, hard = r
        analyses.append(analysis)

        from src.data.db_manager import SignalRecord
        record = SignalRecord(
            code=code,
            trade_date=date.today(),
            report_type=report_type.value,
            momentum_20d=hard.momentum_20d,
            momentum_5d=hard.momentum_5d,
            ma_alignment=hard.ma_alignment,
            volume_ratio=hard.volume_ratio,
            pe_percentile=hard.pe_percentile,
            main_net_inflow=hard.main_net_inflow,
            hard_score=hard.composite_score,
            llm_sentiment="bullish" if fused.soft_score > 0.2 else (
                "bearish" if fused.soft_score < -0.2 else "neutral"
            ) if fused.soft_score != 0 else None,
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
