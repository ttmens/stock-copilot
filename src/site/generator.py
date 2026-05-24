"""Static site generator — HTML from report data."""

import json
import logging
import shutil
from datetime import datetime
from pathlib import Path

from jinja2 import Template

from src.config import get_settings
from src.data.models import Report

logger = logging.getLogger(__name__)

# CSS tokens (design system: dark fintech professional)
THEME_CSS = """\
:root {
    --bg-primary: #0B1220;
    --bg-card: #151E2E;
    --bg-elevated: #1C2738;
    --border: rgba(255,255,255,0.08);
    --text-primary: #E8ECF4;
    --text-secondary: #8892A8;
    --accent: #3B82F6;
    --accent-glow: #60A5FA;
    --bullish: #22C55E;
    --bearish: #EF4444;
    --neutral: #94A3B8;
    --warning: #F59E0B;
    --font-cn: "PingFang SC", "Microsoft YaHei", system-ui, sans-serif;
    --font-mono: "JetBrains Mono", "SF Mono", monospace;
    --radius-card: 12px;
    --radius-btn: 8px;
    --radius-pill: 999px;
}

* { box-sizing: border-box; margin: 0; padding: 0; }
body {
    font-family: var(--font-cn);
    background: var(--bg-primary);
    color: var(--text-primary);
    line-height: 1.6;
    min-height: 100vh;
    padding: 0;
}

.container {
    max-width: 1200px;
    margin: 0 auto;
    padding: 16px;
}

header {
    background: var(--bg-elevated);
    border-bottom: 1px solid var(--border);
    padding: 16px 24px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 8px;
}
header h1 { font-size: 1.25rem; font-weight: 600; }
header .meta { font-size: 0.875rem; color: var(--text-secondary); }

.market-bar {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius-card);
    padding: 12px 20px;
    margin: 16px 0;
    display: flex;
    align-items: center;
    gap: 16px;
    font-size: 0.9rem;
}
.market-bar .index { font-family: var(--font-mono); font-weight: 600; font-size: 1.1rem; }
.market-bar .up { color: var(--bullish); }
.market-bar .down { color: var(--bearish); }

.section-title {
    font-size: 1rem;
    font-weight: 600;
    margin: 24px 0 12px;
    color: var(--text-primary);
}

.stock-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
    gap: 16px;
    margin-bottom: 24px;
}

.stock-card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius-card);
    padding: 16px;
    transition: border-color 0.2s;
}
.stock-card:hover { border-color: var(--accent); }

.stock-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 8px;
}
.stock-code { font-family: var(--font-mono); font-weight: 600; font-size: 1rem; }
.stock-name { color: var(--text-secondary); font-size: 0.875rem; }

.sentiment-badge {
    padding: 2px 10px;
    border-radius: var(--radius-pill);
    font-size: 0.75rem;
    font-weight: 500;
}
.sentiment-bullish { background: rgba(34,197,94,0.15); color: var(--bullish); }
.sentiment-bearish { background: rgba(239,68,68,0.15); color: var(--bearish); }
.sentiment-neutral { background: rgba(148,163,184,0.15); color: var(--neutral); }

.stock-focus {
    font-size: 0.85rem;
    color: var(--text-secondary);
    margin-bottom: 12px;
}

/* 信号评分面板 */
.score-section {
    margin: 8px 0 12px;
    padding: 10px 12px;
    background: var(--bg-elevated);
    border-radius: 8px;
}
.score-bar-bg {
    height: 8px;
    background: rgba(255,255,255,0.06);
    border-radius: 4px;
    overflow: hidden;
    margin-bottom: 4px;
}
.score-bar-fill {
    height: 100%;
    border-radius: 4px;
    transition: width 0.3s, background 0.3s;
}
.score-labels {
    display: flex;
    justify-content: space-between;
    font-size: 0.7rem;
    color: var(--text-secondary);
}
.score-value {
    font-family: var(--font-mono);
    font-weight: 700;
    font-size: 0.85rem;
}
.confidence-row {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-top: 6px;
    font-size: 0.75rem;
}
.confidence-label { color: var(--text-secondary); }
.confidence-dots { display: flex; gap: 3px; }
.conf-dot {
    width: 8px; height: 8px;
    border-radius: 50%;
    background: rgba(255,255,255,0.1);
}
.conf-dot.filled { background: var(--accent); }
.confidence-value {
    font-family: var(--font-mono);
    color: var(--accent);
    font-weight: 600;
    margin-left: auto;
}

/* 硬信号指标行 */
.metrics-row {
    display: flex;
    gap: 8px;
    margin-bottom: 12px;
    flex-wrap: wrap;
}
.metric {
    flex: 1;
    min-width: 60px;
    padding: 6px 8px;
    background: var(--bg-elevated);
    border-radius: 6px;
    text-align: center;
    border: 1px solid var(--border);
}
.metric.up { border-color: rgba(34,197,94,0.3); }
.metric.down { border-color: rgba(239,68,68,0.3); }
.metric-label {
    display: block;
    font-size: 0.65rem;
    color: var(--text-secondary);
    margin-bottom: 2px;
}
.metric-value {
    display: block;
    font-family: var(--font-mono);
    font-weight: 600;
    font-size: 0.8rem;
}
.metric.up .metric-value { color: var(--bullish); }
.metric.down .metric-value { color: var(--bearish); }

.dimension-table {
    width: 100%;
    font-size: 0.8rem;
    border-collapse: collapse;
    margin-bottom: 12px;
}
.dimension-table th, .dimension-table td {
    padding: 6px 8px;
    border: 1px solid var(--border);
    text-align: left;
}
.dimension-table th { background: var(--bg-elevated); color: var(--text-secondary); font-weight: 500; }

.risk-points {
    font-size: 0.8rem;
    color: var(--warning);
    background: rgba(245,158,11,0.08);
    padding: 8px 12px;
    border-radius: 8px;
    border-left: 3px solid var(--warning);
}
.risk-label { font-weight: 600; }

.archive-section {
    margin: 24px 0;
    padding: 16px;
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius-card);
}
.archive-list {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 8px;
}
.archive-item {
    color: var(--accent);
    text-decoration: none;
    font-size: 0.85rem;
    padding: 4px 12px;
    border-radius: var(--radius-btn);
    border: 1px solid var(--border);
    transition: all 0.2s;
}
.archive-item:hover {
    background: var(--bg-elevated);
    border-color: var(--accent);
}

.disclaimer {
    background: var(--bg-elevated);
    border-left: 4px solid var(--warning);
    padding: 12px 16px;
    margin: 24px 0;
    font-size: 0.8rem;
    color: var(--text-secondary);
    border-radius: 0 var(--radius-btn) var(--radius-btn) 0;
    line-height: 1.5;
}

footer {
    text-align: center;
    padding: 16px;
    color: var(--text-secondary);
    font-size: 0.75rem;
    border-top: 1px solid var(--border);
}

@media (max-width: 480px) {
    .stock-grid { grid-template-columns: 1fr; }
    header { padding: 12px 16px; }
    .container { padding: 8px; }
}
"""

# Jinja2 template for the report page
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Stock Copilot — {{ meta.trade_date }} {{ type_label }}</title>
    <link rel="stylesheet" href="assets/theme.css">
</head>
<body>
<header>
    <h1>📊 Stock Copilot</h1>
    <div class="meta">{{ meta.trade_date }} {{ type_label }} · {{ meta.generated_at[:16] }}</div>
</header>

<div class="container">
    {% if market and market.close %}
    <div class="market-bar">
        <span class="index">{{ market.index_name }} {{ "%.2f"|format(market.close) }}</span>
        {% if market.change_pct >= 0 %}
        <span class="up">↑ +{{ "%.2f"|format(market.change_pct) }}%</span>
        {% else %}
        <span class="down">↓ {{ "%.2f"|format(market.change_pct) }}%</span>
        {% endif %}
    </div>
    {% endif %}

    <div class="section-title">自选股分析 ({{ stocks|length }})</div>

    <div class="stock-grid">
            {% for stock in stocks %}
        <div class="stock-card">
            <div class="stock-header">
                <div>
                    <span class="stock-code">{{ stock.code }}</span>
                    <span class="stock-name">{{ stock.name }}</span>
                </div>
                {% set sent_class = 'sentiment-' + (stock.overall_sentiment if stock.overall_sentiment in ['strong_buy','buy','bullish'] else 'bullish' if '买' in stock.overall_focus or '多' in stock.overall_focus else 'bearish' if '卖' in stock.overall_focus or '空' in stock.overall_focus else 'neutral') %}
                <span class="sentiment-badge {{ sent_class }}">{{ stock.overall_focus }}</span>
            </div>

            <!-- 5 层信号分解面板 -->
            <div class="score-section">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
                    <span style="font-size:0.75rem;color:var(--text-secondary)">综合评分</span>
                    <span class="score-value" style="color:{{ '#22C55E' if stock.signal_breakdown.final_score > 0.2 else '#EF4444' if stock.signal_breakdown.final_score < -0.2 else '#94A3B8' }}">{{ '%+.3f'|format(stock.signal_breakdown.final_score) }}</span>
                </div>
                <div class="score-bar-bg">
                    <div class="score-bar-fill" style="width: {{ ((stock.signal_breakdown.final_score + 1) / 2 * 100) }}%; background: {{ '#22C55E' if stock.signal_breakdown.final_score > 0.2 else '#EF4444' if stock.signal_breakdown.final_score < -0.2 else '#94A3B8' }};"></div>
                </div>
                <div class="confidence-row">
                    <span class="confidence-label">置信度</span>
                    <div class="confidence-dots">
                        {% for i in range(5) %}
                        <span class="conf-dot {{ 'filled' if i < (stock.confidence * 5)|round(0, 'floor')|int else '' }}"></span>
                        {% endfor %}
                    </div>
                    <span class="confidence-value">{{ (stock.confidence * 100)|round(0) }}%</span>
                </div>
                <!-- 权重分解 -->
                <div style="margin-top:8px;display:grid;grid-template-columns:1fr 1fr;gap:4px;font-size:0.7rem">
                    <div style="display:flex;justify-content:space-between;padding:2px 6px;background:rgba(255,255,255,0.03);border-radius:4px">
                        <span style="color:var(--text-secondary)">硬信号 (40%)</span>
                        <span style="font-family:var(--font-mono);color:{{ '#22C55E' if stock.signal_breakdown.hard_score > 0 else '#EF4444' if stock.signal_breakdown.hard_score < 0 else 'var(--text-secondary)' }}">{{ '%+.3f'|format(stock.signal_breakdown.hard_score) }}</span>
                    </div>
                    <div style="display:flex;justify-content:space-between;padding:2px 6px;background:rgba(255,255,255,0.03);border-radius:4px">
                        <span style="color:var(--text-secondary)">软信号 (25%)</span>
                        <span style="font-family:var(--font-mono);color:{{ '#22C55E' if stock.signal_breakdown.soft_score > 0 else '#EF4444' if stock.signal_breakdown.soft_score < 0 else 'var(--text-secondary)' }}">{{ '%+.3f'|format(stock.signal_breakdown.soft_score) }}</span>
                    </div>
                    <div style="display:flex;justify-content:space-between;padding:2px 6px;background:rgba(255,255,255,0.03);border-radius:4px">
                        <span style="color:var(--text-secondary)">门控 (15%)</span>
                        <span style="font-family:var(--font-mono);color:{{ '#22C55E' if stock.signal_breakdown.gate_score > 0.5 else '#EF4444' if stock.signal_breakdown.gate_score < 0.5 else 'var(--text-secondary)' }}">{{ '%+.3f'|format(stock.signal_breakdown.gate_score) }}</span>
                    </div>
                    {% if stock.signal_breakdown.has_dragon_tiger %}
                    <div style="display:flex;justify-content:space-between;padding:2px 6px;background:rgba(255,255,255,0.03);border-radius:4px">
                        <span style="color:var(--text-secondary)">龙虎榜 (10%)</span>
                        <span style="font-family:var(--font-mono);color:{{ '#22C55E' if stock.signal_breakdown.dragon_tiger_score > 0 else '#EF4444' if stock.signal_breakdown.dragon_tiger_score < 0 else 'var(--text-secondary)' }}">{{ '%+.3f'|format(stock.signal_breakdown.dragon_tiger_score) }}</span>
                    </div>
                    {% endif %}
                    {% if stock.signal_breakdown.has_announcement %}
                    <div style="display:flex;justify-content:space-between;padding:2px 6px;background:rgba(255,255,255,0.03);border-radius:4px">
                        <span style="color:var(--text-secondary)">公告 (10%)</span>
                        <span style="font-family:var(--font-mono);color:{{ '#22C55E' if stock.signal_breakdown.announcement_score > 0 else '#EF4444' if stock.signal_breakdown.announcement_score < 0 else 'var(--text-secondary)' }}">{{ '%+.3f'|format(stock.signal_breakdown.announcement_score) }}</span>
                    </div>
                    {% endif %}
                </div>
            </div>

            <!-- 硬信号指标 -->
            <div class="metrics-row">
                {% if stock.momentum_5d is not none %}
                <div class="metric {{ 'up' if stock.momentum_5d > 0 else 'down' }}">
                    <span class="metric-label">5日动量</span>
                    <span class="metric-value">{{ '%+.1f'|format(stock.momentum_5d) }}%</span>
                </div>
                {% endif %}
                {% if stock.ma_alignment %}
                <div class="metric {{ 'up' if stock.ma_alignment == 'bullish' else 'down' if stock.ma_alignment == 'bearish' else '' }}">
                    <span class="metric-label">均线</span>
                    <span class="metric-value">{{ {'bullish': '多头', 'bearish': '空头', 'neutral': '交叉'}[stock.ma_alignment] }}</span>
                </div>
                {% endif %}
                {% if stock.volume_ratio is not none %}
                <div class="metric {{ 'up' if stock.volume_ratio > 1.2 else 'down' if stock.volume_ratio < 0.8 else '' }}">
                    <span class="metric-label">量比</span>
                    <span class="metric-value">{{ stock.volume_ratio }}</span>
                </div>
                {% endif %}
                {% if stock.pe_ttm is not none %}
                <div class="metric">
                    <span class="metric-label">PE</span>
                    <span class="metric-value">{{ stock.pe_ttm }}</span>
                </div>
                {% endif %}
            </div>

            <!-- LLM 分析维度 -->
            <table class="dimension-table">
                <thead><tr><th>维度</th><th>状态</th><th>结论</th></tr></thead>
                <tbody>
                {% for dim_name, dim in [('技术面', stock.technical), ('基本面', stock.fundamental), ('资金', stock.capital), ('公告', stock.announcement)] %}
                {% if dim.status != 'unavailable' or dim_name in ['技术面', '资金'] %}
                <tr>
                    <td>{{ dim_name }}</td>
                    <td>{% if dim.status == 'ok' %}✅{% elif dim.status == 'unavailable' %}⏸️{% else %}❌{% endif %}</td>
                    <td>{{ dim.summary[:50] }}{% if dim.summary|length > 50 %}...{% endif %}</td>
                </tr>
                {% endif %}
                {% endfor %}
                </tbody>
            </table>

            <!-- 龙虎榜数据 -->
            {% if stock.dragon_tiger %}
            <div style="margin:8px 0;padding:10px 12px;background:var(--bg-elevated);border-radius:8px;border-left:3px solid #8B5CF6">
                <div style="font-size:0.75rem;font-weight:600;color:#8B5CF6;margin-bottom:6px">🐉 龙虎榜</div>
                {% for dt in stock.dragon_tiger %}
                <div style="font-size:0.75rem;margin-bottom:4px;display:flex;justify-content:space-between;align-items:center">
                    <span style="color:var(--text-secondary)">{{ dt.reason }}</span>
                    <span style="font-family:var(--font-mono);color:{{ '#22C55E' if dt.net_buy > 0 else '#EF4444' }}">
                        {{ '%+.0f'|format(dt.net_buy) if dt.net_buy | abs >= 10000 else '%+.2f万'|format(dt.net_buy / 10000) }}
                    </span>
                </div>
                {% endfor %}
            </div>
            {% endif %}

            <!-- 公告关键事件 -->
            {% if stock.announcement.key_events %}
            <div style="margin:8px 0;padding:10px 12px;background:var(--bg-elevated);border-radius:8px;border-left:3px solid #F59E0B">
                <div style="font-size:0.75rem;font-weight:600;color:#F59E0B;margin-bottom:6px">📢 公告关键事件</div>
                {% for evt in stock.announcement.key_events[:3] %}
                <div style="font-size:0.75rem;margin-bottom:3px;display:flex;gap:6px;align-items:flex-start">
                    <span style="color:{{ '#22C55E' if evt.impact == 'positive' else '#EF4444' if evt.impact == 'negative' else 'var(--text-secondary)' }}">
                        {{ '🟢' if evt.impact == 'positive' else '🔴' if evt.impact == 'negative' else '⚪' }}
                    </span>
                    <span style="color:var(--text-primary)">{{ evt.event }}</span>
                    {% if evt.confidence %}
                    <span style="font-family:var(--font-mono);color:var(--text-secondary);margin-left:auto;font-size:0.65rem">{{ (evt.confidence * 100)|round(0) }}%</span>
                    {% endif %}
                </div>
                {% endfor %}
            </div>
            {% endif %}

            {% if stock.risk_points %}
            <div class="risk-points">
                <span class="risk-label">⚠ 风险:</span> {{ stock.risk_points | join('、') }}
            </div>
            {% endif %}
        </div>
        {% endfor %}
    </div>

    {% if failed_symbols %}
    <div class="section-title">数据获取失败</div>
    <p style="color: var(--bearish); font-size: 0.85rem;">以下股票数据获取失败: {{ failed_symbols | join(', ') }}</p>
    {% endif %}

    {% if archive %}
    <div class="archive-section">
        <div class="section-title" style="margin-top:0">📁 历史报告</div>
        <div class="archive-list">
            {% for item in archive %}
            <a class="archive-item" href="{{ item.url }}">{{ item.date }} {{ '盘前' if item.type == 'pre' else '盘后' }}</a>
            {% endfor %}
        </div>
    </div>
    {% endif %}

    <div class="disclaimer">{{ disclaimer }}</div>
</div>

<footer>Stock Copilot MVP · 由 AI 自动生成 · 不构成投资建议</footer>
</body>
</html>
"""


def generate_site(report: Report) -> str:
    """Generate static HTML site from a Report.

    Returns the path to index.html.
    """
    settings = get_settings()
    site_dir = Path(settings.site.output_dir)
    archive_dir = Path(settings.site.archive_dir)
    data_dir = Path(settings.site.data_dir)

    site_dir.mkdir(parents=True, exist_ok=True)
    archive_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)

    # Write theme.css
    theme_path = site_dir / "assets" / "theme.css"
    theme_path.parent.mkdir(exist_ok=True)
    theme_path.write_text(THEME_CSS, encoding="utf-8")

    # Build site data
    type_label = "盘前" if report.report_type.value == "pre" else "盘后"
    meta = {
        "report_type": report.report_type.value,
        "trade_date": str(report.trade_date),
        "generated_at": report.generated_at.isoformat(),
        "symbol_count": len(report.analyses),
        "disclaimer": "⚠️ 本报告仅供个人研究参考，不构成投资建议。报告内容基于公开数据和 AI 分析生成，可能存在错误或遗漏。股市有风险，决策需谨慎。作者不对任何投资损失承担责任。",
    }

    market = {}
    if report.market:
        market = {
            "index_name": report.market.index_name,
            "close": report.market.close,
            "change_pct": report.market.change_pct,
        }

    stocks = []
    for a in report.analyses:
        # Extract hard signal data from snapshot if available
        snap = a.snapshot
        bars = snap.bars or []
        ma = getattr(snap, 'ma', None)
        valuation = getattr(snap, 'valuation', None)
        capital = getattr(snap, 'capital', None)

        # Compute hard signals inline (same logic as pipeline)
        from src.data.hard_signals import compute_hard_signals
        from src.data.signal_fusion import fuse_signals

        hard = compute_hard_signals(
            bars=bars,
            ma=ma if ma and ma.ma5 else None,
            valuation=valuation,
            capital=capital,
        )
        agents = {"technical": a.technical, "fundamental": a.fundamental, "capital": a.capital}
        fused = fuse_signals(
            code=snap.code, name=snap.name,
            hard=hard, agents=agents,
            is_st="ST" in snap.name,
            dragon_tiger_entries=[e.model_dump() for e in snap.dragon_tiger] if snap.dragon_tiger else None,
            announcement_result=a.announcement,
        )

        # Dragon tiger entries for display
        dt_entries = []
        for dt in snap.dragon_tiger[:3]:  # Show top 3
            dt_entries.append({
                "date": dt.date,
                "reason": dt.reason,
                "net_buy": dt.net_buy,
                "buy_amount": dt.buy_amount,
                "sell_amount": dt.sell_amount,
            })

        # Announcement key events from LLM
        ann_events = []
        if a.announcement.status.value != "unavailable" and a.announcement.raw_json:
            ann_events = a.announcement.raw_json.get("key_events", [])

        stocks.append({
            "code": snap.code,
            "name": snap.name,
            "overall_sentiment": fused.final_signal,
            "overall_focus": fused.signal_label,
            "confidence": round(fused.confidence, 2),
            # Hard signals
            "hard_score": round(hard.composite_score, 2),
            "momentum_20d": round(hard.momentum_20d, 2) if hard.momentum_20d else None,
            "momentum_5d": round(hard.momentum_5d, 2) if hard.momentum_5d else None,
            "ma_alignment": hard.ma_alignment,
            "volume_ratio": round(hard.volume_ratio, 2) if hard.volume_ratio else None,
            "pe_ttm": round(valuation.pe_ttm, 1) if valuation and valuation.pe_ttm else None,
            "pb": round(valuation.pb, 2) if valuation and valuation.pb else None,
            "mcap_yi": round(valuation.mcap / 1e8, 0) if valuation else None,
            # Soft signals (from agents)
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
            "announcement": {
                "status": a.announcement.status.value,
                "summary": a.announcement.summary,
                "sentiment": a.announcement.sentiment,
                "key_events": ann_events,
            },
            "risk_points": [
                r for agent in [a.technical, a.fundamental, a.capital, a.announcement]
                for r in agent.risk_points
            ],
            # 5-layer signal breakdown
            "signal_breakdown": {
                "hard_score": round(fused.hard_score, 3),
                "soft_score": round(fused.soft_score, 3),
                "gate_score": round(fused.gate_score, 3),
                "dragon_tiger_score": round(fused.dragon_tiger_score, 3),
                "announcement_score": round(fused.announcement_score, 3),
                "final_score": round(fused.final_score, 3),
                "has_dragon_tiger": fused.data_available.get("dragon_tiger", False),
                "has_announcement": fused.data_available.get("announcement", False),
            },
            # Dragon tiger data for display
            "dragon_tiger": dt_entries,
        })

    # Load archive
    archive = _load_archive_entries(settings)

    # Write latest.json
    latest = {
        "meta": meta,
        "market": market,
        "stocks": stocks,
        "failed_symbols": report.failed_symbols,
        "archive": archive,
    }
    json_path = data_dir / "latest.json"
    json_path.write_text(json.dumps(latest, ensure_ascii=False, indent=2), encoding="utf-8")

    # Render HTML
    tmpl = Template(HTML_TEMPLATE)
    html = tmpl.render(
        meta=meta,
        type_label=type_label,
        market=market,
        stocks=stocks,
        failed_symbols=report.failed_symbols,
        archive=archive,
        disclaimer=meta["disclaimer"],
    )

    # Write index.html
    index_path = site_dir / "index.html"
    index_path.write_text(html, encoding="utf-8")

    # Write archive copy
    archive_file = archive_dir / f"{report.trade_date}-{report.report_type.value}.html"
    archive_file.write_text(html, encoding="utf-8")

    # Also sync site/ to repo docs/ for GitHub Pages
    _sync_to_docs(settings)

    logger.info("Site generated: %s", index_path)
    return str(index_path)


def _load_archive_entries(settings) -> list[dict]:
    """Load archive entries from site/archive dir."""
    archive_dir = Path(settings.site.archive_dir)
    archive = []

    if archive_dir.exists():
        for f in sorted(archive_dir.glob("*.html"), reverse=True)[:20]:
            stem = f.stem
            parts = stem.rsplit("-", 1)
            if len(parts) == 2:
                archive.append({
                    "date": parts[0],
                    "type": parts[1],
                    "url": f"archive/{stem}.html",
                })

    return archive


def _sync_to_docs(settings) -> None:
    """Sync site/ to repo docs/ for GitHub Pages (Branch: main, /docs)."""
    import pathlib

    project_root = pathlib.Path(__file__).resolve().parent.parent.parent
    docs_dir = project_root / "docs"

    if not docs_dir.exists():
        docs_dir.mkdir(exist_ok=True)

    # Copy site assets, archive, data to docs/
    for src_dir in ["assets", "archive", "data"]:
        src = Path(settings.site.output_dir) / src_dir
        dst = docs_dir / src_dir
        if src.exists():
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)

    # Copy index.html to docs/
    index_src = Path(settings.site.output_dir) / "index.html"
    if index_src.exists():
        shutil.copy2(index_src, docs_dir / "index.html")

    logger.info("Site synced to docs/ for GitHub Pages")
