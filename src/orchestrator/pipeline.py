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
    AgentStatus,
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
from src.agents.fundamental import FundamentalAgent
from src.reports.generator import generate_report
from src.watchlist.manager import WatchlistManager

logger = logging.getLogger(__name__)


def _load_watchlist(symbols: list[str] | None = None) -> list[WatchlistItem]:
    """Load watchlist items. If symbols are codes-only, resolve names from DB or Tencent."""
    if symbols:
        from src.data.db_manager import SignalDB
        from src.data.providers.tencent import get_stock_quote

        db = SignalDB()
        items = []
        for s in symbols:
            # Try DB first (fastest)
            meta = db.get_stock(s)
            if meta and meta.get("name") and meta["name"] != s:
                items.append(WatchlistItem(code=s, name=meta["name"]))
                continue
            # Fallback: resolve from Tencent quote API (always returns name)
            try:
                quote = get_stock_quote(s)
                name = quote.get("name", s) if quote else s
            except Exception:
                name = s
            items.append(WatchlistItem(code=s, name=name))
        return items
    return WatchlistManager().list_items()


def _fundamental_from_announcement(ann: AgentResult, snap: StockSnapshot) -> AgentResult:
    """Fallback when FundamentalAgent LLM is unavailable."""
    return AgentResult(
        agent_name="fundamental",
        status=ann.status,
        sentiment=ann.sentiment,
        summary=ann.summary or f"{snap.name} 公告面参考 Announcement 分析",
        focus_points=list(ann.focus_points),
        risk_points=list(ann.risk_points),
    )


def _detect_gate_flags(snap: StockSnapshot) -> tuple[bool, bool]:
    """Detect suspension and limit-up/down from latest bar."""
    bars = snap.bars or []
    if not bars:
        return False, False
    last = bars[-1]
    if last.volume == 0:
        return True, False
    if len(bars) < 2 or bars[-2].close <= 0:
        return False, False
    pct = (last.close - bars[-2].close) / bars[-2].close * 100
    limit = 4.8 if "ST" in snap.name.upper() else 9.8
    return False, abs(pct) >= limit


def _build_key_basis(
    t_result: AgentResult,
    c_result: AgentResult,
    a_result: AgentResult,
    f_result: AgentResult,
    hard,
    fused,
) -> list[str]:
    """Top 3 key basis lines for homepage pyramid L2."""
    basis: list[str] = []
    if hard.ma_alignment:
        ma_label = {"bullish": "均线多头排列", "bearish": "均线空头排列", "neutral": "均线交叉"}.get(
            hard.ma_alignment, hard.ma_alignment,
        )
        basis.append(f"技术：{ma_label}")
    if hard.momentum_5d is not None:
        basis.append(f"5日动量 {hard.momentum_5d:+.1f}%")
    for agent, prefix in [
        (t_result, "技术"),
        (f_result, "基本面"),
        (c_result, "资金"),
        (a_result, "公告"),
    ]:
        if agent.status == AgentStatus.OK and agent.focus_points:
            basis.append(f"{prefix}：{agent.focus_points[0]}")
        elif agent.status == AgentStatus.OK and agent.summary:
            text = agent.summary[:48] + ("…" if len(agent.summary) > 48 else "")
            basis.append(f"{prefix}：{text}")
    if fused.data_available.get("dragon_tiger"):
        basis.append("龙虎榜：近期有席位异动")
    return basis[:3]


def _build_overall_summary(fused, t_result: AgentResult, f_result: AgentResult) -> str:
    """One-line summary for card L2."""
    label = fused.signal_label.replace("🟢 ", "").replace("🔴 ", "").replace("⚪ ", "")
    if t_result.status == AgentStatus.OK and t_result.summary:
        lead = t_result.summary[:80] + ("…" if len(t_result.summary) > 80 else "")
        return f"{label} — {lead}"
    if f_result.status == AgentStatus.OK and f_result.summary:
        lead = f_result.summary[:80] + ("…" if len(f_result.summary) > 80 else "")
        return f"{label} — {lead}"
    return f"{label}，综合评分 {fused.final_score:+.2f}"


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
    fund = FundamentalAgent()
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
            t_result, c_result, a_result, f_result = await asyncio.gather(
                tech.analyze(snap),
                cap.analyze(snap),
                ann.analyze(snap.code, snap.name, ann_titles),
                fund.analyze(snap),
            )
            if f_result.status == AgentStatus.UNAVAILABLE and a_result.status == AgentStatus.OK:
                f_result = _fundamental_from_announcement(a_result, snap)

            agents = {
                "technical": t_result,
                "fundamental": f_result,
                "capital": c_result,
            }
            is_suspended, limit_up_down = _detect_gate_flags(snap)
            fused = fuse_signals(
                code=snap.code,
                name=snap.name,
                hard=hard,
                agents=agents,
                is_st="ST" in snap.name,
                is_suspended=is_suspended,
                limit_up_down=limit_up_down,
                dragon_tiger_entries=[e.model_dump() for e in snap.dragon_tiger] if snap.dragon_tiger else None,
                announcement_result=a_result,
            )
            key_basis = _build_key_basis(t_result, c_result, a_result, f_result, hard, fused)
            overall_summary = _build_overall_summary(fused, t_result, f_result)
            signal_breakdown = {
                "hard_score": round(fused.hard_score, 3),
                "soft_score": round(fused.soft_score, 3),
                "gate_score": round(fused.gate_score, 3),
                "dragon_tiger_score": round(fused.dragon_tiger_score, 3),
                "announcement_score": round(fused.announcement_score, 3),
                "final_score": round(fused.final_score, 3),
                "has_dragon_tiger": fused.data_available.get("dragon_tiger", False),
                "has_announcement": fused.data_available.get("announcement", False),
            }
            hard_metrics = {
                "hard_score": round(hard.composite_score, 3),
                "momentum_20d": round(hard.momentum_20d, 2) if hard.momentum_20d else None,
                "momentum_5d": round(hard.momentum_5d, 2) if hard.momentum_5d else None,
                "ma_alignment": hard.ma_alignment,
                "volume_ratio": round(hard.volume_ratio, 2) if hard.volume_ratio else None,
            }
            analysis = StockAnalysis(
                snapshot=snap,
                technical=t_result,
                fundamental=f_result,
                capital=c_result,
                announcement=a_result,
                overall_sentiment=fused.final_signal,
                overall_focus=fused.signal_label,
                overall_summary=overall_summary,
                key_basis=key_basis,
                confidence=round(fused.confidence, 2),
                signal_breakdown=signal_breakdown,
                hard_metrics=hard_metrics,
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
