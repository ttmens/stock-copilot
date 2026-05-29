"""Report generator — Markdown and JSON output."""

import json
import logging
from datetime import date, datetime
from pathlib import Path

from src.config import get_settings
from src.data.models import Report, ReportType, StockAnalysis, MarketOverview

logger = logging.getLogger(__name__)

DISCLAIMER = (
    "⚠️ 本报告仅供个人研究参考，不构成投资建议。"
    "报告内容基于公开数据和 AI 分析生成，可能存在错误或遗漏。"
    "股市有风险，决策需谨慎。作者不对任何投资损失承担责任。"
)

_SENTIMENT_LABEL = {
    "bullish": "🟢 偏多",
    "bearish": "🔴 偏空",
    "neutral": "⚪ 中性",
}


def _compute_overall(analysis: StockAnalysis) -> None:
    """Compute overall_sentiment and overall_focus from 3 agent results."""
    sentiments = [
        analysis.technical.sentiment,
        analysis.fundamental.sentiment,
        analysis.capital.sentiment,
    ]
    # Filter out unavailable
    active = [s for s in sentiments if s != "unavailable"]

    if not active:
        analysis.overall_sentiment = "neutral"
    else:
        bullish = active.count("bullish")
        bearish = active.count("bearish")
        if bullish >= 2:
            analysis.overall_sentiment = "bullish"
        elif bearish >= 2:
            analysis.overall_sentiment = "bearish"
        else:
            analysis.overall_sentiment = "neutral"

    # Focus: take first technical focus point
    if analysis.technical.focus_points:
        analysis.overall_focus = analysis.technical.focus_points[0]


def generate_report(
    analyses: list[StockAnalysis],
    report_type: ReportType,
    market: MarketOverview | None = None,
    failed_symbols: list[str] | None = None,
) -> Report:
    """Generate a full Markdown report."""
    trade_date = datetime.now().date()
    now = datetime.now()

    # Compute overall for each stock
    for a in analyses:
        _compute_overall(a)

    # Build Markdown
    lines: list[str] = []
    type_label = "盘前" if report_type == ReportType.PRE else "盘后"
    lines.append(f"# A股自选股分析简报")
    lines.append(f"**日期**: {trade_date} | **类型**: {type_label} | **生成时间**: {now.strftime('%H:%M')}")
    lines.append("")
    lines.append(f"> {DISCLAIMER}")
    lines.append("")

    # Market overview
    if market:
        lines.append("## 市场概览")
        arrow = "↑" if (market.change_pct or 0) >= 0 else "↓"
        lines.append(f"- {market.index_name}: {market.close} ({arrow}{market.change_pct}%)")
        lines.append("")

    # Stock analyses
    lines.append(f"## 自选股分析 ({len(analyses)})")
    lines.append("")

    for a in analyses:
        sent_label = _SENTIMENT_LABEL.get(a.overall_sentiment, "⚪ 中性")
        lines.append(f"### {a.snapshot.code} {a.snapshot.name}")
        lines.append(f"**综合**: {sent_label} | **今日关注**: {a.overall_focus}")
        lines.append("")
        lines.append("| 维度 | 状态 | 结论 |")
        lines.append("|------|------|------|")

        for agent in [a.technical, a.fundamental, a.capital]:
            status_icon = "✅" if agent.status.value == "ok" else ("⏸️" if agent.status.value == "unavailable" else "❌")
            summary = agent.summary if agent.summary else "暂无"
            lines.append(f"| {agent.agent_name} | {status_icon} | {summary} |")

        lines.append("")

        # Risk points
        all_risks = []
        for agent in [a.technical, a.fundamental, a.capital]:
            all_risks.extend(agent.risk_points)
        if all_risks:
            lines.append(f"**风险点**: {'、'.join(all_risks)}")
            lines.append("")

        lines.append("---")
        lines.append("")

    # Failed symbols
    if failed_symbols:
        lines.append("## 数据获取失败")
        lines.append(f"以下股票数据获取失败: {', '.join(failed_symbols)}")
        lines.append("")

    lines.append(f"*由 Stock Copilot MVP 自动生成*")

    markdown = "\n".join(lines)

    # Save to disk
    settings = get_settings()
    output_dir = Path(settings.report.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{trade_date}-{report_type.value}.md"
    file_path = output_dir / filename
    file_path.write_text(markdown, encoding="utf-8")

    # Also save latest.json
    _save_latest_json(analyses, market, failed_symbols or [], report_type, trade_date, now)

    return Report(
        report_type=report_type,
        generated_at=now,
        trade_date=trade_date,
        market=market,
        analyses=analyses,
        failed_symbols=failed_symbols or [],
        markdown=markdown,
        file_path=str(file_path),
    )


def _save_latest_json(
    analyses: list[StockAnalysis],
    market: MarketOverview | None,
    failed: list[str],
    report_type: ReportType,
    trade_date: date,
    now: datetime,
) -> None:
    """Save latest.json for site consumption."""
    settings = get_settings()
    data_dir = Path(settings.site.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    stocks = []
    for a in analyses:
        # Debate / consensus data
        consensus = None
        debate_data = None
        if a.debate:
            consensus = a.debate.get("consensus_score")
            debate_data = a.debate
        stocks.append({
            "code": a.snapshot.code,
            "name": a.snapshot.name,
            "overall_sentiment": a.overall_sentiment,
            "overall_focus": a.overall_focus,
            "technical": {
                "status": a.technical.status.value,
                "summary": a.technical.summary,
                "sentiment": a.technical.sentiment,
            },
            "fundamental": {
                "status": a.fundamental.status.value,
                "summary": a.fundamental.summary,
                "sentiment": a.fundamental.sentiment,
            },
            "capital": {
                "status": a.capital.status.value,
                "summary": a.capital.summary,
                "sentiment": a.capital.sentiment,
            },
            "risk_points": [
                r for agent in [a.technical, a.fundamental, a.capital]
                for r in agent.risk_points
            ],
            "consensus_score": consensus,
            "debate": debate_data,
        })

    latest = {
        "meta": {
            "report_type": report_type.value,
            "trade_date": str(trade_date),
            "generated_at": now.isoformat(),
            "symbol_count": len(analyses),
            "disclaimer": DISCLAIMER,
        },
        "market": {
            "index_name": market.index_name if market else "N/A",
            "close": market.close if market else None,
            "change_pct": market.change_pct if market else None,
        } if market else {},
        "stocks": stocks,
        "failed_symbols": failed,
        "archive": _load_archive(),
    }

    json_path = data_dir / "latest.json"

    # PROTECT: never overwrite good data with partial data
    new_count = len(stocks)
    existing_count = 0
    if json_path.exists():
        try:
            existing = json.loads(json_path.read_text())
            existing_count = len(existing.get("stocks", []))
        except Exception:
            pass

    if new_count == 0 and existing_count > 0:
        logger.warning("_save_latest_json: skipping — new report has 0 stocks, "
                        "existing has %d. Protecting against data loss.", existing_count)
    elif new_count < existing_count and new_count > 0:
        if new_count < existing_count * 0.8:
            logger.warning("_save_latest_json: skipping — new report has %d stocks, "
                            "existing has %d (>20%% drop). Possible partial analysis.",
                            new_count, existing_count)
        else:
            json_path.write_text(json.dumps(latest, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        json_path.write_text(json.dumps(latest, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_archive() -> list[dict]:
    """Build archive list from existing report files."""
    settings = get_settings()
    output_dir = Path(settings.report.output_dir)
    archive = []

    if output_dir.exists():
        for f in sorted(output_dir.glob("*.md"), reverse=True)[:30]:
            # Parse filename: 2026-05-22-pre.md
            stem = f.stem
            parts = stem.rsplit("-", 1)
            if len(parts) == 2:
                archive.append({
                    "date": parts[0],
                    "type": parts[1],
                    "url": f"archive/{stem}.html",
                })

    # Also check archive dir for HTML files
    archive_dir = Path(settings.site.archive_dir)
    if archive_dir.exists():
        for f in sorted(archive_dir.glob("*.html"), reverse=True)[:30]:
            stem = f.stem
            parts = stem.rsplit("-", 1)
            if len(parts) == 2:
                entry = {"date": parts[0], "type": parts[1], "url": f"archive/{stem}.html"}
                if entry not in archive:
                    archive.append(entry)

    return archive
