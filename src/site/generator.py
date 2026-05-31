"""Static site generator — multi-page site from report data.

Pages:
1. index.html — 首页：信号仪表盘 + 自选股概览 (L1 → L2 progressive)
2. app/stock.html?code=XXX — 个股详情：决策卡片 + 5层维度 + 证据链
3. history.html — 历史信号：胜率统计 + 时间线
4. dashboard.html — 数据看板：信号矩阵 + 对比表

Design: Seeking Alpha Quant Ratings + TradingView Technical Ratings + 富途牛牛
"""

import json
import logging
import shutil
from datetime import datetime
from pathlib import Path

from jinja2 import Template

from src.config import get_settings
from src.data.models import Report, StockAnalysis

logger = logging.getLogger(__name__)


def _analysis_to_stock_dict(a: StockAnalysis) -> dict:
    """Build site/JSON stock dict from pipeline output — no refusion."""
    snap = a.snapshot
    sb = dict(a.signal_breakdown or {})
    if "final_score" not in sb:
        sb.setdefault("final_score", 0)
        sb.setdefault("hard_score", 0)
        sb.setdefault("soft_score", 0)
        sb.setdefault("gate_score", 0)
        sb.setdefault("dragon_tiger_score", 0)
        sb.setdefault("announcement_score", 0)
    hm = a.hard_metrics or {}
    valuation = snap.valuation

    dt_entries = []
    for dt in snap.dragon_tiger[:5]:
        dt_entries.append({
            "date": dt.date, "reason": dt.reason, "net_buy": dt.net_buy,
            "buy_amount": dt.buy_amount, "sell_amount": dt.sell_amount,
            "participants": dt.participants[:5] if dt.participants else [],
        })

    ann_events = []
    if a.announcement.status.value != "unavailable" and a.announcement.raw_json:
        ann_events = a.announcement.raw_json.get("key_events", [])

    news_items = [
        {"title": n.title, "url": n.url, "date": n.date, "source": n.source}
        for n in (snap.news or [])[:5]
    ]

    stock = {
        "code": snap.code,
        "name": snap.name,
        "overall_sentiment": a.overall_sentiment,
        "overall_focus": a.overall_focus,
        "overall_summary": a.overall_summary,
        "key_basis": a.key_basis,
        "confidence": a.confidence,
        "hard_score": hm.get("hard_score", sb.get("hard_score")),
        "momentum_20d": hm.get("momentum_20d"),
        "momentum_5d": hm.get("momentum_5d"),
        "ma_alignment": hm.get("ma_alignment"),
        "volume_ratio": hm.get("volume_ratio"),
        "pe_ttm": round(valuation.pe_ttm, 1) if valuation and valuation.pe_ttm else None,
        "pb": round(valuation.pb, 2) if valuation and valuation.pb else None,
        "mcap_yi": round(valuation.mcap / 1e8, 0) if valuation else None,
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
        "news": news_items,
        "risk_points": [
            r for agent in [a.technical, a.fundamental, a.capital, a.announcement]
            for r in agent.risk_points
        ],
        "signal_breakdown": sb,
        "dragon_tiger": dt_entries,
        "consensus_score": a.debate.get("consensus_score") if a.debate else None,
        "debate": a.debate,
        "related_stocks": a.related_stocks if a.related_stocks else [],
    }
    return _enrich_stock_dict(stock)


def _enrich_stock_dict(stock: dict) -> dict:
    """Fill L2 fields for legacy JSON or partial pipeline output."""
    out = dict(stock)
    sb = out.get("signal_breakdown") or {}
    if not out.get("overall_summary"):
        focus = out.get("overall_focus", "")
        tech = (out.get("technical") or {}).get("summary", "")
        if tech:
            out["overall_summary"] = f"{focus} — {tech[:80]}{'…' if len(tech) > 80 else ''}"
        elif focus:
            out["overall_summary"] = f"{focus}，综合评分 {sb.get('final_score', 0):+.2f}"
    if not out.get("key_basis"):
        basis: list[str] = []
        ma = out.get("ma_alignment")
        if ma:
            label = {"bullish": "均线多头排列", "bearish": "均线空头排列", "neutral": "均线交叉"}.get(ma, ma)
            basis.append(f"技术：{label}")
        m5 = out.get("momentum_5d")
        if m5 is not None:
            basis.append(f"5日动量 {m5:+.1f}%")
        for key, prefix in [("technical", "技术"), ("fundamental", "基本面"), ("capital", "资金")]:
            summary = (out.get(key) or {}).get("summary")
            if summary:
                basis.append(f"{prefix}：{summary[:48]}{'…' if len(summary) > 48 else ''}")
                break
        out["key_basis"] = basis[:3]
    out.setdefault("news", [])
    return out


def report_from_latest_json(path: Path) -> Report:
    """Rebuild a Report from published latest.json (for site regeneration)."""
    from datetime import date

    from src.data.models import (
        AgentResult,
        AgentStatus,
        MarketOverview,
        ReportType,
        StockSnapshot,
    )

    data = json.loads(path.read_text(encoding="utf-8"))
    meta = data["meta"]

    def _agent(name: str, block: dict | None) -> AgentResult:
        block = block or {}
        status_raw = block.get("status", "unavailable")
        try:
            status = AgentStatus(status_raw)
        except ValueError:
            status = AgentStatus.UNAVAILABLE
        return AgentResult(
            agent_name=name,
            status=status,
            summary=block.get("summary", ""),
            sentiment=block.get("sentiment", "neutral"),
        )

    analyses: list[StockAnalysis] = []
    for raw in data.get("stocks", []):
        s = _enrich_stock_dict(raw)
        snap = StockSnapshot(code=s["code"], name=s["name"], fetched_at=datetime.now())
        analyses.append(StockAnalysis(
            snapshot=snap,
            technical=_agent("technical", s.get("technical")),
            fundamental=_agent("fundamental", s.get("fundamental")),
            capital=_agent("capital", s.get("capital")),
            announcement=_agent("announcement", s.get("announcement")),
            overall_sentiment=s.get("overall_sentiment", "hold"),
            overall_focus=s.get("overall_focus", ""),
            overall_summary=s.get("overall_summary", ""),
            key_basis=s.get("key_basis", []),
            confidence=s.get("confidence", 0),
            signal_breakdown=s.get("signal_breakdown") or {},
            hard_metrics={
                "hard_score": s.get("hard_score"),
                "momentum_5d": s.get("momentum_5d"),
                "momentum_20d": s.get("momentum_20d"),
                "ma_alignment": s.get("ma_alignment"),
                "volume_ratio": s.get("volume_ratio"),
            },
            debate=s.get("debate"),
            related_stocks=s.get("related_stocks", []),
        ))

    market = None
    if data.get("market"):
        m = data["market"]
        market = MarketOverview(
            index_name=m.get("index_name", "上证指数"),
            close=m.get("close"),
            change_pct=m.get("change_pct"),
        )

    report_type = ReportType.PRE if meta.get("report_type") == "pre" else ReportType.POST
    return Report(
        report_type=report_type,
        generated_at=datetime.fromisoformat(meta["generated_at"]),
        trade_date=date.fromisoformat(meta["trade_date"]),
        market=market,
        analyses=analyses,
        failed_symbols=data.get("failed_symbols", []),
    )

_THEME_CSS_PATH = Path(__file__).parent / "theme.css"
THEME_CSS = _THEME_CSS_PATH.read_text(encoding="utf-8")

# ── Shared header brand SVG ───────────────────────────────────
BRAND_SVG = """<svg viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg" class="brand-svg">
    <rect width="32" height="32" rx="8" fill="url(#logo-grad)"/>
    <path d="M8 22 L14 14 L18 18 L24 10" stroke="white" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
    <path d="M20 10 L24 10 L24 14" stroke="white" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
    <defs><linearGradient id="logo-grad" x1="0" y1="0" x2="32" y2="32">
        <stop offset="0%" stop-color="#7b3ff2"/><stop offset="100%" stop-color="#00f5ff"/>
    </linearGradient></defs>
</svg>"""

# ── Top Nav ───────────────────────────────────────────────────
NAV_HTML = """
<div class="site-nav">
    <a href="app/cockpit.html#today"{% if page == 'today' %} class="active"{% endif %}>今日<span class="alert-badge" id="nav-alert-badge" hidden>0</span></a>
    <a href="app/cockpit.html#watchlist"{% if page == 'watchlist' %} class="active"{% endif %}>自选</a>
    <a href="app/cockpit.html#me"{% if page == 'me' %} class="active"{% endif %}>我的</a>
</div>
"""
NAV_HTML_SUB = """
<div class="site-nav">
    <a href="cockpit.html#today"{% if page == 'today' %} class="active"{% endif %}>今日</a>
    <a href="cockpit.html#watchlist"{% if page == 'watchlist' %} class="active"{% endif %}>自选</a>
    <a href="cockpit.html#me"{% if page == 'me' %} class="active"{% endif %}>我的</a>
</div>
"""

SESSION_RAIL = """
<div class="session-rail" id="session-rail">
    <span class="session-rail-phase" id="session-phase">盘前</span>
    <span class="session-rail-countdown" id="session-countdown"></span>
    <a href="app/cockpit.html#today" class="session-rail-cta" id="session-cta">查看今日战术</a>
</div>
<div class="live-banner" id="live-banner" hidden>
    实时看板需连接服务器 — 当前为只读快照模式
</div>
"""

# ── Bottom Nav (mobile) ───────────────────────────────────────
BOTTOM_NAV = """
<nav class="bottom-nav">
    <div class="bottom-nav-inner">
        <a href="app/cockpit.html#today"{% if page == 'today' %} class="active"{% endif %}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
            今日
        </a>
        <a href="app/cockpit.html#watchlist"{% if page == 'watchlist' %} class="active"{% endif %}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/></svg>
            自选
        </a>
        <a href="app/cockpit.html#me"{% if page == 'me' %} class="active"{% endif %}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
            我的
        </a>
    </div>
</nav>
"""

# ── Helper: signal badge class ────────────────────────────────
# Used inline in templates via {% set ... %}

# ═══════════════════════════════════════════════════════════════
# Template 1: Homepage
# ═══════════════════════════════════════════════════════════════
TPL_HOME = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
    <meta http-equiv="refresh" content="0;url=app/cockpit.html">
    <meta name="description" content="智策 NexStrat — AI 辅助 A 股战术投研，盘前情报、推荐池、竞价、盯盘、复盘一站闭环">
    <title>智策 NexStrat — {{ meta.trade_date }} {{ type_label }}</title>
    <link rel="stylesheet" href="assets/theme.css">
    <script>location.replace("app/cockpit.html");</script>
</head>
<body>

<header class="site-header">
    <div class="brand">
        <div class="brand-icon">{{ brand_svg }}</div>
        <div class="brand-text">
            <span class="brand-name">智策 NexStrat</span>
            <span class="brand-tagline">面向投资者的AI智能投研</span>
        </div>
    </div>
    {{ nav }}
    <span class="header-meta">{{ meta.trade_date }} {{ type_label }} · {{ meta.generated_at[11:16] }}</span>
</header>

{{ session_rail }}

<div class="shell">

{# ── Signal Dashboard (Market Temperature + Breadth) ── #}
{% if market and market.close %}
<div class="signal-dashboard">
    <div class="signal-dashboard-head">
        <div>
            <span class="signal-dashboard-label">市场温度</span>
            <span class="signal-dashboard-value">{{ market.index_name }} {{ "%.2f"|format(market.close) }}</span>
            {% if market.change_pct >= 0 %}
            <span class="signal-dashboard-change change-up">+{{ "%.2f"|format(market.change_pct) }}%</span>
            {% else %}
            <span class="signal-dashboard-change change-down">{{ "%.2f"|format(market.change_pct) }}%</span>
            {% endif %}
        </div>
        {# ── Phase F: Market Breadth Score ── #}
        {% if breadth %}
        <div class="breadth-widget">
            <span class="breadth-label">市场广度</span>
            <span class="breadth-score" style="color:{{ breadth.color }}">{{ breadth.score }}</span>
            <span class="breadth-zone" style="color:{{ breadth.color }}">{{ breadth.zone_label }}</span>
            <span class="breadth-exposure">建议仓位 {{ breadth.recommended_exposure }}</span>
        </div>
        {% endif %}
    </div>
    {# Signal distribution bar #}
    {% set total = bullish_count + hold_count + bearish_count %}
    {% if total > 0 %}
    <div class="signal-bar">
        {% if bullish_count > 0 %}<div class="signal-bar-seg bull" style="width:{{ (bullish_count/total*100)|round }}%"></div>{% endif %}
        {% if hold_count > 0 %}<div class="signal-bar-seg hold" style="width:{{ (hold_count/total*100)|round }}%"></div>{% endif %}
        {% if bearish_count > 0 %}<div class="signal-bar-seg bear" style="width:{{ (bearish_count/total*100)|round }}%"></div>{% endif %}
    </div>
    {% endif %}
    <div class="signal-legend">
        <span class="signal-legend-item"><span class="signal-legend-dot bull"></span> 看多 {{ bullish_count }}</span>
        <span class="signal-legend-item"><span class="signal-legend-dot hold"></span> 观望 {{ hold_count }}</span>
        <span class="signal-legend-item"><span class="signal-legend-dot bear"></span> 看空 {{ bearish_count }}</span>
    </div>
</div>
{% endif %}

{# ── Stock List ── #}
<div class="section-title">
    今日重点 <span class="count" id="stock-count">({{ stocks|length }} 只自选)</span>
    <span class="kbd-hint"><span class="kbd">V</span> 切换视图</span>
</div>

<div class="filter-bar" id="filter-bar">
    <input type="search" id="filter-search" placeholder="搜索代码 / 名称" aria-label="搜索">
    <select id="filter-signal" aria-label="信号筛选">
        <option value="">全部信号</option>
        <option value="bullish">看多</option>
        <option value="hold">观望</option>
        <option value="bearish">看空</option>
    </select>
    <select id="filter-sort" aria-label="排序">
        <option value="score">按评分</option>
        <option value="confidence">按置信度</option>
        <option value="code">按代码</option>
    </select>
    <a href="app/watchlist.html" class="filter-link">管理自选</a>
    <div class="view-toggle">
        <button class="view-toggle-btn active" id="btn-view-cards" title="卡片视图 (V)">
            <svg viewBox="0 0 16 16" fill="currentColor"><rect x="1" y="1" width="6" height="6" rx="1"/><rect x="9" y="1" width="6" height="6" rx="1"/><rect x="1" y="9" width="6" height="6" rx="1"/><rect x="9" y="9" width="6" height="6" rx="1"/></svg>
            卡片
        </button>
        <button class="view-toggle-btn" id="btn-view-table" title="表格视图 (V)">
            <svg viewBox="0 0 16 16" fill="currentColor"><rect x="1" y="1" width="14" height="3" rx="1"/><rect x="1" y="6" width="14" height="3" rx="1"/><rect x="1" y="11" width="14" height="3" rx="1"/></svg>
            表格
        </button>
    </div>
</div>

{# ── Compare Panel (Desktop) ── #}
<div class="compare-panel" id="compare-panel">
    <div class="compare-panel-title">
        对比面板 <span id="compare-count">(0)</span>
        <span class="compare-panel-close" id="compare-close">×</span>
    </div>
    <div id="compare-list"></div>
</div>

{% if not stocks %}
<div class="empty-state">
    <div class="empty-state-icon">📭</div>
    <div class="empty-state-text">暂无分析数据</div>
    <div class="empty-state-sub">非交易日或数据采集失败，下次交易日自动更新</div>
</div>
{% endif %}

<div class="stock-grid" id="stock-grid">
{% for stock in stocks %}
{% set score = stock.signal_breakdown.final_score %}
{% set score_cls = 'signal-score-bull' if score > 0.2 else 'signal-score-bear' if score < -0.2 else 'signal-score-hold' %}
{% set bar_cls = 'signal-bar-bull' if score > 0.2 else 'signal-bar-bear' if score < -0.2 else 'signal-bar-hold' %}
{% set detail_href = 'app/stock.html?code=' ~ stock.code if use_app_pages else 'stock/' ~ stock.code ~ '.html' %}
<div class="stock-card-link" data-code="{{ stock.code }}" data-name="{{ stock.name }}" data-signal="{{ stock.overall_sentiment }}" data-score="{{ score }}" data-confidence="{{ stock.confidence }}">
<div class="stock-card">
    <div class="card-header">
        <a href="{{ detail_href }}" class="card-title-link">
            <div class="stock-select" data-code="{{ stock.code }}" title="加入对比"></div>
            <div>
                <div class="card-stock-code">{{ stock.code }}</div>
                <div class="card-stock-name">{{ stock.name }}</div>
            </div>
        </a>
        {% set s = stock.overall_sentiment %}
        {% set badge_cls = 'bullish' if s in ['strong_buy','buy','bullish'] else 'bearish' if s in ['sell','strong_sell'] else 'hold' %}
        <span class="signal-badge {{ badge_cls }}">{{ stock.overall_focus }}</span>
        {% if stock.consensus_score is not none %}
        {% set cs = stock.consensus_score %}
        {% set cs_label = '高共识' if cs >= 0.8 else '中共识' if cs >= 0.5 else '低共识' %}
        {% set cs_color = '#22C55E' if cs >= 0.8 else '#F59E0B' if cs >= 0.5 else '#EF4444' %}
        <span class="consensus-badge" style="color:{{ cs_color }}" title="Agent 辩论共识度 {{ (cs * 100)|round(0) }}%">🤖 {{ cs_label }} {{ (cs * 100)|round(0) }}%</span>
        {% endif %}
        {# ── Phase F: Contradiction Flags ── #}
        {% if stock.signal_breakdown.contradiction_flags and stock.signal_breakdown.contradiction_flags|length > 0 %}
        <span class="contradiction-badge" title="{% for flag in stock.signal_breakdown.contradiction_flags %}⚠ {{ flag.type }}: {{ flag.description }}{% if not loop.last %}; {% endif %}{% endfor %}">⚠️ 冲突×{{ stock.signal_breakdown.contradiction_flags|length }}</span>
        {% endif %}
    </div>

    <div class="decision-card">
        <div class="decision-score-row">
            <span class="decision-score-label">综合评分</span>
            <span class="decision-score-value {{ score_cls }}">{{ '%+.3f'|format(score) }}</span>
        </div>
        <div class="decision-bar-track">
            <div class="decision-bar-fill {{ bar_cls }}" style="width:{{ ((score + 1) / 2 * 100)|round(1) }}%"></div>
        </div>
        <div class="decision-confidence">
            <span>置信度</span>
            <div class="conf-dots">
                {% for i in range(5) %}
                <span class="conf-dot {{ 'filled' if i < (stock.confidence * 5)|round(0, 'floor')|int else '' }}"></span>
                {% endfor %}
            </div>
            <span class="conf-value">{{ (stock.confidence * 100)|round(0) }}%</span>
        </div>
    </div>

    {% if stock.overall_summary %}
    <p class="card-summary">{{ stock.overall_summary }}</p>
    {% endif %}
    {% if stock.key_basis %}
    <ul class="key-basis-list">
        {% for item in stock.key_basis %}
        <li>{{ item }}</li>
        {% endfor %}
    </ul>
    {% endif %}

    <div class="metrics-row">
        {% if stock.momentum_5d is not none %}
        <div class="metric-chip">
            <span class="metric-chip-label">5日</span>
            <span class="metric-chip-val {{ 'change-up' if stock.momentum_5d > 0 else 'change-down' if stock.momentum_5d < 0 else '' }}">{{ '%+.1f'|format(stock.momentum_5d) }}%</span>
        </div>
        {% endif %}
        {% if stock.ma_alignment %}
        <div class="metric-chip">
            <span class="metric-chip-label">均线</span>
            <span class="metric-chip-val {{ 'signal-score-bull' if stock.ma_alignment == 'bullish' else 'signal-score-bear' if stock.ma_alignment == 'bearish' else 'signal-score-hold' }}">{{ {'bullish': '多头', 'bearish': '空头', 'neutral': '交叉'}[stock.ma_alignment] }}</span>
        </div>
        {% endif %}
        <div class="metric-chip intraday">
            <span class="metric-chip-label">日内</span>
            <span class="metric-chip-val">—</span>
        </div>
        {% if stock.volume_ratio is not none %}
        <div class="metric-chip">
            <span class="metric-chip-label">量比</span>
            <span class="metric-chip-val">{{ '%.2f'|format(stock.volume_ratio) }}</span>
        </div>
        {% endif %}
        {% if stock.pe_ttm is not none %}
        <div class="metric-chip">
            <span class="metric-chip-label">PE</span>
            <span class="metric-chip-val">{{ '%.1f'|format(stock.pe_ttm) }}</span>
        </div>
        {% endif %}
    </div>

    <details class="card-accordion">
        <summary>展开摘要</summary>
        <div class="card-accordion-body">
            {% if stock.technical.summary %}<p><strong>技术</strong> {{ stock.technical.summary[:120] }}{% if stock.technical.summary|length > 120 %}…{% endif %}</p>{% endif %}
            {% if stock.fundamental.summary %}<p><strong>基本面</strong> {{ stock.fundamental.summary[:120] }}{% if stock.fundamental.summary|length > 120 %}…{% endif %}</p>{% endif %}
            {% if stock.capital.summary %}<p><strong>资金</strong> {{ stock.capital.summary[:120] }}{% if stock.capital.summary|length > 120 %}…{% endif %}</p>{% endif %}
        </div>
    </details>

    {% if stock.risk_points %}
    <div class="risk-block">⚠ {{ stock.risk_points[:1] | join('') }}</div>
    {% endif %}
    <a href="{{ detail_href }}" class="card-detail-link">查看详情 →</a>
</div>
</div>
{% endfor %}
</div>

{# ── Table View (Desktop) ── #}
<div class="table-view" id="table-view">
<div class="table-scroll table-scroll-main">
<table class="stock-table" id="stock-table">
    <thead>
        <tr>
            <th data-sort="code" class="col-code">代码 <span class="sort-icon">↕</span></th>
            <th class="col-name">名称</th>
            <th class="col-signal">信号</th>
            <th data-sort="score" class="col-score sorted">评分 <span class="sort-icon">↓</span></th>
            <th class="col-momentum">5日动量</th>
            <th class="col-ma">均线</th>
            <th class="col-volume">量比</th>
            <th class="col-pe">PE</th>
            <th class="col-confidence">置信度</th>
            <th class="col-dragon">龙虎</th>
            <th class="col-announce">公告</th>
        </tr>
    </thead>
    <tbody>
{% for stock in stocks %}
{% set s = stock.overall_sentiment %}
{% set score = stock.signal_breakdown.final_score %}
{% set score_cls = 'signal-score-bull' if score > 0.2 else 'signal-score-bear' if score < -0.2 else 'signal-score-hold' %}
{% set bar_cls = 'signal-bar-bull' if score > 0.2 else 'signal-bar-bear' if score < -0.2 else 'signal-bar-hold' %}
{% set badge_cls = 'bullish' if s in ['strong_buy','buy','bullish'] else 'bearish' if s in ['sell','strong_sell'] else 'hold' %}
        <tr data-code="{{ stock.code }}" data-name="{{ stock.name }}" data-signal="{{ s }}" data-score="{{ score }}" data-confidence="{{ stock.confidence }}">
            <td class="stock-code"><a href="{% if use_app_pages %}app/stock.html?code={{ stock.code }}{% else %}stock/{{ stock.code }}.html{% endif %}" class="stock-code-link">{{ stock.code }}</a></td>
            <td><span class="stock-name">{{ stock.name }}</span></td>
            <td>
{% set s2 = stock.overall_sentiment %}
{% set badge_cls2 = 'bullish' if s2 in ['strong_buy','buy','bullish'] else 'bearish' if s2 in ['sell','strong_sell'] else 'hold' %}
<span class="signal-badge {{ badge_cls2 }}" title="{{ stock.overall_focus }}">{{ stock.overall_focus[:20]}}{% if stock.overall_focus|length > 20 %}…{% endif %}</span>
{% if stock.consensus_score is not none %}
{% set cs2 = stock.consensus_score %}
{% set cs_label2 = '高共识' if cs2 >= 0.8 else '中共识' if cs2 >= 0.5 else '低共识' %}
{% set cs_color2 = '#22C55E' if cs2 >= 0.8 else '#F59E0B' if cs2 >= 0.5 else '#EF4444' %}
<span class="consensus-badge-table" style="color:{{ cs_color2 }}" title="共识度 {{ (cs2 * 100)|round(0) }}%">🤖{{ cs_label2 }}{{ (cs2 * 100)|round(0) }}%</span>
{% endif %}
</td>
            <td>
                <div class="score-mini">
                    <span class="score-mini-val {{ score_cls }}">{{ '%+.3f'|format(score) }}</span>
                    <div class="score-mini-bar"><div class="score-mini-fill {{ bar_cls }}" style="width:{{ ((score + 1) / 2 * 100)|round }}%"></div></div>
                </div>
            </td>
            <td class="{{ 'change-up' if (stock.momentum_5d or 0) > 0 else 'change-down' if (stock.momentum_5d or 0) < 0 else '' }}">{{ '%+.1f'|format(stock.momentum_5d) if stock.momentum_5d is not none else '-' }}%</td>
            <td>{{ {'bullish': '多头', 'bearish': '空头', 'neutral': '交叉'}.get(stock.ma_alignment, '-') }}</td>
            <td>{{ '%.2f'|format(stock.volume_ratio) if stock.volume_ratio is not none else '-' }}</td>
            <td>{{ '%.1f'|format(stock.pe_ttm) if stock.pe_ttm is not none else '-' }}</td>
            <td>{{ (stock.confidence * 100)|round(0) }}%</td>
            <td>{% if stock.signal_breakdown.has_dragon_tiger %}<span class="text-dragon">●</span>{% else %}<span class="text-faint">—</span>{% endif %}</td>
            <td>{% if stock.signal_breakdown.has_announcement %}<span class="text-announce">●</span>{% else %}<span class="text-faint">—</span>{% endif %}</td>
        </tr>
{% endfor %}
    </tbody>
</table>
</div>
</div>
{% if archive %}
<div class="archive-section">
    <div class="archive-title">📁 历史报告</div>
    <div class="archive-list">
        {% for item in archive[:10] %}
        <a class="archive-pill" href="archive/{{ item.date }}-{{ item.type }}.html">{{ item.date }} {{ '盘前' if item.type == 'pre' else '盘后' }}</a>
        {% endfor %}
    </div>
</div>
{% endif %}

<div class="disclaimer">{{ disclaimer }}</div>

<footer class="site-footer">智策 NexStrat v2.0 · AI 辅助决策 · 不构成投资建议</footer>
</div>

{{ bottom_nav }}

{# ── Desktop JavaScript: View Toggle, Table Sort, Compare Panel, Keyboard ── #}
<script>
(function() {
  'use strict';
  if (typeof window === 'undefined') return;

  // ── View Toggle ──
  const gridEl = document.getElementById('stock-grid');
  const tableEl = document.getElementById('table-view');
  const btnCards = document.getElementById('btn-view-cards');
  const btnTable = document.getElementById('btn-view-table');
  let isTableView = false;

  function setView(table) {
    isTableView = table;
    if (table) {
      gridEl && gridEl.classList.add('table-hidden');
      tableEl && tableEl.classList.add('active');
      btnCards && btnCards.classList.remove('active');
      btnTable && btnTable.classList.add('active');
      localStorage.setItem('nexstrat-view', 'table');
    } else {
      gridEl && gridEl.classList.remove('table-hidden');
      tableEl && tableEl.classList.remove('active');
      btnCards && btnCards.classList.add('active');
      btnTable && btnTable.classList.remove('active');
      localStorage.setItem('nexstrat-view', 'cards');
    }
  }

  // Restore preference
  if (localStorage.getItem('nexstrat-view') === 'table') setView(true);

  btnCards && btnCards.addEventListener('click', () => setView(false));
  btnTable && btnTable.addEventListener('click', () => setView(true));

  // ── Table Sort ──
  const stockTable = document.getElementById('stock-table');
  if (stockTable) {
    const headers = stockTable.querySelectorAll('th[data-sort]');
    let sortKey = 'score';
    let sortAsc = false;

    headers.forEach(th => {
      th.addEventListener('click', () => {
        const key = th.dataset.sort;
        if (key === sortKey) { sortAsc = !sortAsc; }
        else { sortKey = key; sortAsc = true; }

        headers.forEach(h => h.classList.remove('sorted'));
        th.classList.add('sorted');
        th.querySelector('.sort-icon').textContent = sortAsc ? '↑' : '↓';

        const tbody = stockTable.querySelector('tbody');
        const rows = Array.from(tbody.querySelectorAll('tr'));
        rows.sort((a, b) => {
          let va = a.dataset[sortKey] || '';
          let vb = b.dataset[sortKey] || '';
          if (sortKey === 'score') { va = parseFloat(va) || 0; vb = parseFloat(vb) || 0; }
          else if (sortKey === 'confidence') { va = parseFloat(va) || 0; vb = parseFloat(vb) || 0; }
          else { va = va.toLowerCase(); vb = vb.toLowerCase(); }
          if (va < vb) return sortAsc ? -1 : 1;
          if (va > vb) return sortAsc ? 1 : -1;
          return 0;
        });
        rows.forEach(r => tbody.appendChild(r));
      });
    });

    // Click row to navigate
    stockTable.querySelectorAll('tbody tr').forEach(tr => {
      tr.addEventListener('click', (e) => {
        if (e.target.tagName === 'A') return;
        const code = tr.dataset.code;
        if (code) window.location.href = 'app/stock.html?code=' + code;
      });
    });
  }

  // ── Compare Panel ──
  const comparePanel = document.getElementById('compare-panel');
  const compareList = document.getElementById('compare-list');
  const compareCount = document.getElementById('compare-count');
  const compareClose = document.getElementById('compare-close');
  let compareStocks = [];

  function updateCompare() {
    if (!compareList) return;
    compareCount && (compareCount.textContent = '(' + compareStocks.length + ')');
    if (compareStocks.length === 0) {
      compareList.innerHTML = '<div class="empty-hint">点击卡片左上角复选框添加对比</div>';
      comparePanel && comparePanel.classList.remove('active');
      return;
    }
    comparePanel && comparePanel.classList.add('active');
    compareList.innerHTML = compareStocks.map(s => {
      const score = s.score || 0;
      const color = score > 0.2 ? '#22C55E' : score < -0.2 ? '#EF4444' : '#94A3B8';
      const width = ((score + 1) / 2 * 100).toFixed(0);
      return '<div class="compare-item">' +
        '<div><span class="compare-item-code">' + s.code + '</span> <span class="compare-item-name">' + s.name + '</span>' +
        '<div class="compare-bar"><div class="compare-bar-fill" style="width:' + width + '%;background:' + color + '"></div></div></div>' +
        '<span class="compare-item-remove" data-code="' + s.code + '">×</span></div>';
    }).join('');

    compareList.querySelectorAll('.compare-item-remove').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const code = btn.dataset.code;
        compareStocks = compareStocks.filter(s => s.code !== code);
        updateCompare();
        document.querySelectorAll('.stock-select[data-code="' + code + '"]').forEach(el => el.classList.remove('checked'));
      });
    });
  }

  document.querySelectorAll('.stock-select').forEach(el => {
    el.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      const code = el.dataset.code;
      const card = el.closest('.stock-card-link') || el.closest('tr');
      if (!card) return;
      const name = card.dataset.name || '';
      const score = parseFloat(card.dataset.score) || 0;

      if (compareStocks.some(s => s.code === code)) {
        compareStocks = compareStocks.filter(s => s.code !== code);
        el.classList.remove('checked');
      } else {
        if (compareStocks.length >= 5) { alert('最多对比 5 只股票'); return; }
        compareStocks.push({ code, name, score });
        el.classList.add('checked');
      }
      updateCompare();
    });
  });

  compareClose && compareClose.addEventListener('click', () => {
    comparePanel && comparePanel.classList.remove('active');
  });

  updateCompare();

  // ── Keyboard Shortcuts ──
  document.addEventListener('keydown', (e) => {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') return;
    if (e.key === 'v' || e.key === 'V') {
      e.preventDefault();
      setView(!isTableView);
    }
    if (e.key === 'Escape') {
      comparePanel && comparePanel.classList.remove('active');
    }
  });
})();
</script>

<script src="app/config.js"></script>
<script src="app/api-client.js"></script>
<script src="app/live.js" defer></script>
<script src="app/app.js" defer></script>
</body>
</html>
"""

# ═══════════════════════════════════════════════════════════════
# Template 2: Stock Detail Page
# ═══════════════════════════════════════════════════════════════
TPL_STOCK = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
    <title>{{ stock.name }} ({{ stock.code }}) — 智策 NexStrat</title>
    <link rel="stylesheet" href="../assets/theme.css">
</head>
<body>

<header class="site-header">
    <div class="brand">
        <div class="brand-icon">{{ brand_svg }}</div>
        <div class="brand-text">
            <span class="brand-name">智策 NexStrat</span>
            <span class="brand-tagline">面向投资者的AI智能投研</span>
        </div>
    </div>
    {{ nav }}
    <span class="header-meta">{{ stock.code }}</span>
</header>

<div class="shell">

<a href="../index.html" class="back-link">← 返回</a>

{# ── L1: Decision Header ── #}
<div class="page-title">
    {{ stock.code }} <span class="stock-name-muted">{{ stock.name }}</span>
</div>

{% set s = stock.overall_sentiment %}
{% set badge_cls = 'bullish' if s in ['strong_buy','buy','bullish'] else 'bearish' if s in ['sell','strong_sell'] else 'hold' %}
<div class="detail-signal-row">
    <span class="signal-badge {{ badge_cls }} signal-badge-lg">{{ stock.overall_focus }}</span>
</div>

{# ── L1: Big Score + 5-Layer Breakdown ── #}
<div class="detail-grid">
    <div class="detail-section">
        <div class="detail-section-title">🎯 AI 决策评分</div>
        <div class="big-score">
            <div class="big-score-value" style="color:{{ '#22C55E' if stock.signal_breakdown.final_score > 0.2 else '#EF4444' if stock.signal_breakdown.final_score < -0.2 else '#94A3B8' }}">
                {{ '%+.3f'|format(stock.signal_breakdown.final_score) }}
            </div>
            <div class="big-score-label">置信度 {{ (stock.confidence * 100)|round(0) }}%</div>
            <div class="big-score-bar">
                <div class="big-score-fill" style="width:{{ ((stock.signal_breakdown.final_score + 1) / 2 * 100)|round(1) }}%; background:{{ '#22C55E' if stock.signal_breakdown.final_score > 0.2 else '#EF4444' if stock.signal_breakdown.final_score < -0.2 else '#94A3B8' }}"></div>
            </div>
        </div>
        {# 5-Layer Dimension Cards #}
        <div class="dim-grid dim-grid-detail">
            <div class="dim-card">
                <span class="dim-card-label"><span class="dim-card-dot" class="dot-hard"></span>硬信号 40%</span>
                <span class="dim-card-value" style="color:{{ '#22C55E' if stock.signal_breakdown.hard_score > 0 else '#EF4444' if stock.signal_breakdown.hard_score < 0 else 'var(--text-muted)' }}">{{ '%+.3f'|format(stock.signal_breakdown.hard_score) }}</span>
            </div>
            <div class="dim-card">
                <span class="dim-card-label"><span class="dim-card-dot" class="dot-soft"></span>软信号 25%</span>
                <span class="dim-card-value" style="color:{{ '#22C55E' if stock.signal_breakdown.soft_score > 0 else '#EF4444' if stock.signal_breakdown.soft_score < 0 else 'var(--text-muted)' }}">{{ '%+.3f'|format(stock.signal_breakdown.soft_score) }}</span>
            </div>
            <div class="dim-card">
                <span class="dim-card-label"><span class="dim-card-dot" class="dot-gate"></span>门控 15%</span>
                <span class="dim-card-value" style="color:{{ '#22C55E' if stock.signal_breakdown.gate_score > 0.5 else '#EF4444' if stock.signal_breakdown.gate_score < 0.5 else 'var(--text-muted)' }}">{{ '%+.3f'|format(stock.signal_breakdown.gate_score) }}</span>
            </div>
            {% if stock.signal_breakdown.has_dragon_tiger %}
            <div class="dim-card">
                <span class="dim-card-label"><span class="dim-card-dot" class="dot-dragon"></span>龙虎 10%</span>
                <span class="dim-card-value" style="color:{{ '#22C55E' if stock.signal_breakdown.dragon_tiger_score > 0 else '#EF4444' if stock.signal_breakdown.dragon_tiger_score < 0 else 'var(--text-muted)' }}">{{ '%+.3f'|format(stock.signal_breakdown.dragon_tiger_score) }}</span>
            </div>
            {% endif %}
            {% if stock.signal_breakdown.has_announcement %}
            <div class="dim-card">
                <span class="dim-card-label"><span class="dim-card-dot" class="dot-announce"></span>公告 10%</span>
                <span class="dim-card-value" style="color:{{ '#22C55E' if stock.signal_breakdown.announcement_score > 0 else '#EF4444' if stock.signal_breakdown.announcement_score < 0 else 'var(--text-muted)' }}">{{ '%+.3f'|format(stock.signal_breakdown.announcement_score) }}</span>
            </div>
            {% endif %}
        </div>
    </div>

    {# ── L2: Hard Signal Metrics ── #}
    <div class="detail-section">
        <div class="detail-section-title">📈 硬信号指标</div>
        <div class="metrics-row" style="flex-wrap:wrap">
            {% if stock.momentum_5d is not none %}
            <div class="metric-chip" class="min-w-lg">
                <span class="metric-chip-label">5日动量</span>
                <span class="metric-chip-val" style="color:{{ '#22C55E' if stock.momentum_5d > 0 else '#EF4444' if stock.momentum_5d < 0 else 'var(--text-secondary)' }}">{{ '%+.1f'|format(stock.momentum_5d) }}%</span>
            </div>
            {% endif %}
            {% if stock.momentum_20d is not none %}
            <div class="metric-chip" class="min-w-lg">
                <span class="metric-chip-label">20日动量</span>
                <span class="metric-chip-val" style="color:{{ '#22C55E' if stock.momentum_20d > 0 else '#EF4444' if stock.momentum_20d < 0 else 'var(--text-secondary)' }}">{{ '%+.1f'|format(stock.momentum_20d) }}%</span>
            </div>
            {% endif %}
            {% if stock.ma_alignment %}
            <div class="metric-chip" class="min-w-lg">
                <span class="metric-chip-label">均线排列</span>
                <span class="metric-chip-val" style="color:{{ '#22C55E' if stock.ma_alignment == 'bullish' else '#EF4444' if stock.ma_alignment == 'bearish' else 'var(--text-secondary)' }}">{{ {'bullish': '多头', 'bearish': '空头', 'neutral': '交叉'}[stock.ma_alignment] }}</span>
            </div>
            {% endif %}
            {% if stock.volume_ratio is not none %}
            <div class="metric-chip">
                <span class="metric-chip-label">量比</span>
                <span class="metric-chip-val">{{ '%.2f'|format(stock.volume_ratio) }}</span>
            </div>
            {% endif %}
            {% if stock.pe_ttm is not none %}
            <div class="metric-chip">
                <span class="metric-chip-label">PE</span>
                <span class="metric-chip-val">{{ '%.1f'|format(stock.pe_ttm) }}</span>
            </div>
            {% endif %}
            {% if stock.pb is not none %}
            <div class="metric-chip">
                <span class="metric-chip-label">PB</span>
                <span class="metric-chip-val">{{ '%.2f'|format(stock.pb) }}</span>
            </div>
            {% endif %}
            {% if stock.mcap_yi is not none %}
            <div class="metric-chip" class="min-w-lg">
                <span class="metric-chip-label">总市值</span>
                <span class="metric-chip-val">{{ "%.0f"|format(stock.mcap_yi) }}亿</span>
            </div>
            {% endif %}
        </div>
    </div>
</div>

{# ── L2: LLM Analysis Dimensions ── #}
<div class="detail-section" class="mb-md">
    <div class="detail-section-title">🤖 LLM 分析维度</div>
    <table class="llm-table">
        {% for dim_name, dim in [('技术面', stock.technical), ('基本面', stock.fundamental), ('资金面', stock.capital), ('公告', stock.announcement)] %}
        {% if dim.status != 'unavailable' or dim_name in ['技术面', '资金面'] %}
        <tr>
            <td class="dim-icon">{% if dim.status == 'ok' %}✅{% elif dim.status == 'unavailable' %}⏸{% else %}❌{% endif %}</td>
            <td class="dim-label">{{ dim_name }}</td>
            <td class="dim-text">{{ dim.summary }}</td>
        </tr>
        {% endif %}
        {% endfor %}
    </table>
</div>

{# ── Phase D: Agent Debate Panel ── #}
{% if stock.debate %}
<div class="detail-section" class="mb-md">
    <div class="detail-section-title">🤖 Agent 辩论面板</div>
    {% set deb = stock.debate %}
    {% set cs = deb.get('consensus_score', 0) %}
    {% set cs_pct = (cs * 100)|round(0) %}
    {% set cs_color = '#22C55E' if cs >= 0.8 else '#F59E0B' if cs >= 0.5 else '#EF4444' %}
    {% set cs_label = '高共识' if cs >= 0.8 else '中共识' if cs >= 0.5 else '低共识/分歧' %}
    <div class="debate-header">
        <span class="debate-consensus" style="color:{{ cs_color }}">共识度 {{ cs_pct }}% — {{ cs_label }}</span>
        {% if deb.has_disagreement %}
        <span class="debate-warning">⚠️ 存在分歧</span>
        {% endif %}
    </div>
    <div class="debate-grid">
        {% for agent_name in ['technical', 'capital', 'fundamental'] %}
        {% set agent_labels = {'technical': '技术面', 'capital': '资金面', 'fundamental': '基本面'} %}
        {% set r1 = deb.get('round1', {}).get(agent_name, '') %}
        {% set r2 = deb.get('round2', {}).get(agent_name, '') %}
        {% set shifted = deb.get('shifts', {}).get(agent_name + '_shifted', false) %}
        {% set r1_icon = '🟢' if r1 == 'bullish' else '🔴' if r1 == 'bearish' else '⚪' %}
        {% set r2_icon = '🟢' if r2 == 'bullish' else '🔴' if r2 == 'bearish' else '⚪' %}
        <div class="debate-agent-card">
            <div class="debate-agent-title">{{ agent_labels.get(agent_name, agent_name) }}{% if shifted %} <span class="debate-shift-tag">已修正</span>{% endif %}</div>
            <div class="debate-round">
                <span class="debate-round-label">R1</span>
                <span class="debate-sentiment">{{ r1_icon }} {{ r1 }}</span>
            </div>
            <div class="debate-arrow">↓</div>
            <div class="debate-round">
                <span class="debate-round-label">R2</span>
                <span class="debate-sentiment">{{ r2_icon }} {{ r2 }}</span>
            </div>
        </div>
        {% endfor %}
    </div>
    {% if deb.has_disagreement and deb.get('disagreement_points') %}
    <div class="debate-disagreements">
        <div class="debate-disagree-title">🔀 分歧点：</div>
        {% for dp in deb.disagreement_points[:3] %}
        <div class="debate-disagree-item">• {{ dp }}</div>
        {% endfor %}
    </div>
    {% endif %}
</div>
{% endif %}

{# ── Phase D: Related Stocks ── #}
{% if stock.related_stocks and stock.related_stocks|length > 0 %}
<div class="detail-section" class="mb-md">
    <div class="detail-section-title">🔗 关联股票</div>
    <div class="related-grid">
        {% for rel in stock.related_stocks[:6] %}
        <a href="{% if use_app_pages %}app/stock.html?code={{ rel.code }}{% else %}stock/{{ rel.code }}.html{% endif %}" class="related-card">
            <div class="related-card-code">{{ rel.code }}</div>
            <div class="related-card-type">{{ rel.type }}</div>
            {% if rel.industry %}<div class="related-card-meta">{{ rel.industry }}</div>{% endif %}
        </a>
        {% endfor %}
    </div>
</div>
{% endif %}

{# ── L3: Dragon Tiger Evidence ── #}
{% if stock.dragon_tiger %}
<div class="detail-section" class="mb-md">
    <div class="detail-section-title">🐉 龙虎榜</div>
    {% for dt in stock.dragon_tiger %}
    <div class="dt-block">
        <div class="dt-title">{{ dt.reason }}</div>
        <div class="dt-row">
            <span class="text-muted">净额</span>
            <span style="color:{{ '#22C55E' if dt.net_buy > 0 else '#EF4444' }}; font-family:var(--font-mono); font-weight:600">
                {{ '%+.0f'|format(dt.net_buy) if dt.net_buy | abs >= 10000 else '%+.2f万'|format(dt.net_buy / 10000) }}
            </span>
        </div>
    </div>
    {% endfor %}
</div>
{% endif %}

{# ── L3: Announcement Evidence ── #}
{% if stock.announcement.key_events %}
<div class="detail-section" class="mb-md">
    <div class="detail-section-title">📢 公告关键事件</div>
    {% for evt in stock.announcement.key_events[:5] %}
    <div class="ann-block">
        <div class="ann-event">
            <span>{{ '🟢' if evt.impact == 'positive' else '🔴' if evt.impact == 'negative' else '⚪' }}</span>
            <span class="ann-text">{{ evt.event }}</span>
            {% if evt.confidence %}
            <span class="ann-conf">{{ (evt.confidence * 100)|round(0) }}%</span>
            {% endif %}
        </div>
    </div>
    {% endfor %}
</div>
{% endif %}

{# ── Risk ── #}
{% if stock.risk_points %}
<div class="risk-block" class="mb-md">⚠ 风险提示：{{ stock.risk_points | join('、') }}</div>
{% endif %}

<div class="disclaimer">{{ disclaimer }}</div>
<footer class="site-footer">智策 NexStrat v2.0 · AI 辅助决策 · 不构成投资建议</footer>
</div>

{{ bottom_nav }}
</body>
</html>
"""

# ═══════════════════════════════════════════════════════════════
# Template 3: History Page
# ═══════════════════════════════════════════════════════════════
TPL_HISTORY = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
    <title>历史信号 — 智策 NexStrat</title>
    <link rel="stylesheet" href="assets/theme.css">
</head>
<body>

<header class="site-header">
    <div class="brand">
        <div class="brand-icon">{{ brand_svg }}</div>
        <div class="brand-text">
            <span class="brand-name">智策 NexStrat</span>
            <span class="brand-tagline">面向投资者的AI智能投研</span>
        </div>
    </div>
    {{ nav }}
    <span class="header-meta">历史信号</span>
</header>

<div class="shell-wide">

<a href="index.html" class="back-link">← 返回</a>

<div class="page-title">📈 历史信号回顾</div>
<div class="page-subtitle">所有自选股的历史信号记录，按时间倒序</div>

{% if not history %}
<div class="empty-state">
    <div class="empty-state-icon">📭</div>
    <div class="empty-state-text">暂无历史信号数据</div>
    <div class="empty-state-sub">需要多个交易日积累数据</div>
</div>
{% endif %}

{# ── Phase F: Signal Postmortem / 复盘统计 ── #}
{% if postmortem_stats and postmortem_stats.total > 0 %}
<div class="detail-section mb-lg">
    <div class="detail-section-title">📊 信号复盘统计 <span class="section-subtitle">最近 30 日信号验证</span></div>
    <div class="stats-grid mb-md">
        <div class="stat-card">
            <div class="stat-value" style="color:{{ '#22C55E' if postmortem_stats.win_rate >= 0.5 else '#EF4444' }}">{{ (postmortem_stats.win_rate * 100)|round(1) }}%</div>
            <div class="stat-label">胜率</div>
        </div>
        <div class="stat-card">
            <div class="stat-value text-bull">{{ postmortem_stats.tp }}</div>
            <div class="stat-label">✅ 正确信号</div>
        </div>
        <div class="stat-card">
            <div class="stat-value text-bear">{{ postmortem_stats.fp }}</div>
            <div class="stat-label">❌ 误报</div>
        </div>
        <div class="stat-card">
            <div class="stat-value text-hold">{{ postmortem_stats.missed }}</div>
            <div class="stat-label">⏭ 遗漏机会</div>
        </div>
        <div class="stat-card">
            <div class="stat-value" style="color:var(--text-muted)">{{ postmortem_stats.regime }}</div>
            <div class="stat-label">🔄 风格错配</div>
        </div>
    </div>
    {# Returns #}
    <div class="postmortem-returns">
        {% if postmortem_stats.avg_return_5d is not none %}
        <span class="return-chip">5日均收益 <span class="{{ 'change-up' if postmortem_stats.avg_return_5d > 0 else 'change-down' }}">{{ '%+.2f'|format(postmortem_stats.avg_return_5d) }}%</span></span>
        {% endif %}
        {% if postmortem_stats.avg_return_20d is not none %}
        <span class="return-chip">20日均收益 <span class="{{ 'change-up' if postmortem_stats.avg_return_20d > 0 else 'change-down' }}">{{ '%+.2f'|format(postmortem_stats.avg_return_20d) }}%</span></span>
        {% endif %}
        {% if postmortem_stats.contra_win_rate is not none and postmortem_stats.no_contra_win_rate is not none %}
        <span class="return-chip">有冲突信号胜率 <span class="{{ 'change-up' if postmortem_stats.contra_win_rate >= 0.5 else 'change-down' }}">{{ (postmortem_stats.contra_win_rate * 100)|round(1) }}%</span> ({{ postmortem_stats.contra_count }})</span>
        <span class="return-chip">无冲突信号胜率 <span class="{{ 'change-up' if postmortem_stats.no_contra_win_rate >= 0.5 else 'change-down' }}">{{ (postmortem_stats.no_contra_win_rate * 100)|round(1) }}%</span> ({{ postmortem_stats.no_contra_count }})</span>
        {% endif %}
    </div>
</div>
{% endif %}

{% for code, data in history.items() %}
<div style="margin-bottom:32px">
    <div class="section-title">
        <a href="{% if use_app_pages %}app/stock.html?code={{ code }}{% else %}stock/{{ code }}.html{% endif %}" class="stock-code-link">
            {{ code }} {{ data.name }}
        </a>
        <span class="count">({{ data.records|length }} 条)</span>
    </div>

    {# Stats Cards #}
    <div class="stats-grid" class="mb-md">
        <div class="stat-card">
            <div class="stat-value" style="color:{{ '#22C55E' if data.stats.avg_score > 0 else '#EF4444' if data.stats.avg_score < 0 else 'var(--signal-hold)' }}">
                {{ '%+.2f'|format(data.stats.avg_score) }}
            </div>
            <div class="stat-label">平均评分</div>
        </div>
        <div class="stat-card">
            <div class="stat-value" class="text-bull">{{ data.stats.bullish_count }}</div>
            <div class="stat-label">看多</div>
        </div>
        <div class="stat-card">
            <div class="stat-value" class="text-bear">{{ data.stats.bearish_count }}</div>
            <div class="stat-label">看空</div>
        </div>
        <div class="stat-card">
            <div class="stat-value" class="text-hold">{{ data.stats.hold_count }}</div>
            <div class="stat-label">观望</div>
        </div>
    </div>

    <div class="table-scroll">
    <table class="data-table">
        <thead>
            <tr>
                <th>日期</th>
                <th>类型</th>
                <th>硬信号</th>
                <th>软信号</th>
                <th>门控</th>
                <th>最终评分</th>
                <th>信号</th>
                <th>置信度</th>
            </tr>
        </thead>
        <tbody>
            {% for r in data.records|reverse %}
            <tr>
                <td>{{ r.trade_date }}</td>
                <td class="text-muted">{{ '盘前' if r.report_type == 'pre' else '盘后' }}</td>
                <td style="color:{{ '#22C55E' if r.hard_score > 0 else '#EF4444' if r.hard_score < 0 else 'var(--text-muted)' }}">{{ '%+.3f'|format(r.hard_score) }}</td>
                <td style="color:{{ '#22C55E' if r.soft_score > 0 else '#EF4444' if r.soft_score < 0 else 'var(--text-muted)' }}">{{ '%+.3f'|format(r.soft_score) }}</td>
                <td>{{ '%+.3f'|format(r.gate_score) }}</td>
                <td style="font-weight:700;color:{{ '#22C55E' if r.final_score > 0.2 else '#EF4444' if r.final_score < -0.2 else 'var(--text-muted)' }}">{{ '%+.3f'|format(r.final_score) }}</td>
                <td>
                    {% if r.final_signal in ['strong_buy', 'buy', 'bullish'] %}
                    <span class="text-bull">🟢 看多</span>
                    {% elif r.final_signal in ['sell', 'strong_sell'] %}
                    <span class="text-bear">🔴 看空</span>
                    {% else %}
                    <span class="text-hold">⚪ 观望</span>
                    {% endif %}
                </td>
                <td>{{ (r.confidence * 100)|round(0) }}%</td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
    </div>
</div>
{% endfor %}

<div class="disclaimer">{{ disclaimer }}</div>
<footer class="site-footer">智策 NexStrat v2.0 · AI 辅助决策 · 不构成投资建议</footer>
</div>

{{ bottom_nav }}
</body>
</html>
"""

# ═══════════════════════════════════════════════════════════════
# Template 4: Dashboard Page
# ═══════════════════════════════════════════════════════════════
TPL_DASHBOARD = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
    <title>数据看板 — 智策 NexStrat</title>
    <link rel="stylesheet" href="assets/theme.css">
</head>
<body>

<header class="site-header">
    <div class="brand">
        <div class="brand-icon">{{ brand_svg }}</div>
        <div class="brand-text">
            <span class="brand-name">智策 NexStrat</span>
            <span class="brand-tagline">面向投资者的AI智能投研</span>
        </div>
    </div>
    {{ nav }}
    <span class="header-meta">{{ meta.trade_date }} {{ type_label }}</span>
</header>

<div class="shell-wide">

<a href="index.html" class="back-link">← 返回</a>

<div class="page-title">📋 数据看板</div>
<div class="page-subtitle">自选股横向对比 + 信号矩阵</div>

{# ── Market Temperature ── #}
{% if market and market.close %}
<div class="signal-dashboard" class="mb-lg">
    <div class="signal-dashboard-head">
        <div>
            <span class="signal-dashboard-label">市场温度</span>
            <span class="signal-dashboard-value">{{ market.index_name }} {{ "%.2f"|format(market.close) }}</span>
            {% if market.change_pct >= 0 %}
            <span class="signal-dashboard-change change-up">+{{ "%.2f"|format(market.change_pct) }}%</span>
            {% else %}
            <span class="signal-dashboard-change change-down">{{ "%.2f"|format(market.change_pct) }}%</span>
            {% endif %}
        </div>
    </div>
    {# ── Phase F: Market Breadth Score ── #}
    {% if breadth %}
    <div class="breadth-widget">
        <span class="breadth-label">市场广度</span>
        <span class="breadth-score" style="color:{{ breadth.color }}">{{ breadth.score }}</span>
        <span class="breadth-zone" style="color:{{ breadth.color }}">{{ breadth.zone_label }}</span>
        <span class="breadth-exposure">建议仓位 {{ breadth.recommended_exposure }}</span>
    </div>
    {% endif %}
    {% set total = bullish_count + hold_count + bearish_count %}
    {% if total > 0 %}
    <div class="signal-bar">
        {% if bullish_count > 0 %}<div class="signal-bar-seg bull" style="width:{{ (bullish_count/total*100)|round }}%"></div>{% endif %}
        {% if hold_count > 0 %}<div class="signal-bar-seg hold" style="width:{{ (hold_count/total*100)|round }}%"></div>{% endif %}
        {% if bearish_count > 0 %}<div class="signal-bar-seg bear" style="width:{{ (bearish_count/total*100)|round }}%"></div>{% endif %}
    </div>
    {% endif %}
    <div class="signal-legend">
        <span class="signal-legend-item"><span class="signal-legend-dot bull"></span> 看多 {{ bullish_count }}</span>
        <span class="signal-legend-item"><span class="signal-legend-dot hold"></span> 观望 {{ hold_count }}</span>
        <span class="signal-legend-item"><span class="signal-legend-dot bear"></span> 看空 {{ bearish_count }}</span>
    </div>
</div>
{% endif %}

{# ── Phase D: Consensus Heatmap ── #}
{% set stocks_with_consensus = stocks | selectattr('consensus_score', 'defined') | rejectattr('consensus_score', 'none') | list %}
{% if stocks_with_consensus %}
<div class="detail-section" class="mb-lg">
    <div class="detail-section-title">🤖 共识度热力图 <span class="section-subtitle">Agent 辩论后的一致性评估</span></div>
    <div class="heatmap-grid">
        {% for stock in stocks %}
        {% if stock.consensus_score is not none %}
        {% set cs = stock.consensus_score %}
        {% set cs_pct = (cs * 100)|round(0) %}
        {% set bg = '#0D2818' if cs >= 0.8 else '#1C1203' if cs >= 0.5 else '#2D0A0A' %}
        {% set border = '#22C55E' if cs >= 0.8 else '#F59E0B' if cs >= 0.5 else '#EF4444' %}
        {% set text_c = '#22C55E' if cs >= 0.8 else '#F59E0B' if cs >= 0.5 else '#EF4444' %}
        <a href="{% if use_app_pages %}app/stock.html?code={{ stock.code }}{% else %}stock/{{ stock.code }}.html{% endif %}" class="heatmap-cell" style="background:{{ bg }}; border-color:{{ border }}">
            <div class="heatmap-code">{{ stock.code }}</div>
            <div class="heatmap-name">{{ stock.name }}</div>
            <div class="heatmap-value" style="color:{{ text_c }}">{{ cs_pct }}%</div>
            <div class="heatmap-bar-track"><div class="heatmap-bar-fill" style="width:{{ cs_pct }}%; background:{{ border }}"></div></div>
        </a>
        {% endif %}
        {% endfor %}
    </div>
    <div class="heatmap-legend">
        <span>🟢 高共识 ≥80%</span>
        <span>🟡 中共识 50-80%</span>
        <span>🔴 低共识 <50%（分歧大，需谨慎）</span>
    </div>
</div>
{% endif %}

{# ── Comparison Matrix ── #}
<div class="detail-section" class="mb-lg">
    <div class="detail-section-title">自选股对比矩阵</div>
    <div class="table-scroll">
    <table class="data-table">
        <thead>
            <tr>
                <th>股票</th>
                <th>信号</th>
                <th>评分</th>
                <th>5日动量</th>
                <th>均线</th>
                <th>量比</th>
                <th>PE</th>
                <th>置信度</th>
                <th>龙虎榜</th>
                <th>公告</th>
            </tr>
        </thead>
        <tbody>
            {% for stock in stocks %}
            {% set s = stock.overall_sentiment %}
            {% set badge_cls = 'bullish' if s in ['strong_buy','buy','bullish'] else 'bearish' if s in ['sell','strong_sell'] else 'hold' %}
            <tr>
                <td class="stock-cell">
                    <a href="{% if use_app_pages %}app/stock.html?code={{ stock.code }}{% else %}stock/{{ stock.code }}.html{% endif %}" class="stock-code-link">
                        {{ stock.code }}<br>
                        <span style="font-size:11px;color:var(--text-muted);font-weight:400">{{ stock.name }}</span>
                    </a>
                </td>
                <td><span class="signal-badge {{ badge_cls }}">{{ stock.overall_focus }}</span></td>
                <td style="color:{{ '#22C55E' if stock.signal_breakdown.final_score > 0.2 else '#EF4444' if stock.signal_breakdown.final_score < -0.2 else 'var(--text-muted)' }}">
                    {{ '%+.3f'|format(stock.signal_breakdown.final_score) }}
                </td>
                <td style="color:{{ '#22C55E' if (stock.momentum_5d or 0) > 0 else '#EF4444' if (stock.momentum_5d or 0) < 0 else 'var(--text-muted)' }}">
                    {{ '%+.1f'|format(stock.momentum_5d) if stock.momentum_5d is not none else '-' }}%
                </td>
                <td>{{ {'bullish': '多头', 'bearish': '空头', 'neutral': '交叉'}.get(stock.ma_alignment, '-') }}</td>
                <td>{{ '%.2f'|format(stock.volume_ratio) if stock.volume_ratio is not none else '-' }}</td>
                <td>{{ '%.1f'|format(stock.pe_ttm) if stock.pe_ttm is not none else '-' }}</td>
                <td>{{ (stock.confidence * 100)|round(0) }}%</td>
                <td>{% if stock.signal_breakdown.has_dragon_tiger %}<span class="text-dragon">●</span>{% else %}<span class="text-faint">—</span>{% endif %}</td>
                <td>{% if stock.signal_breakdown.has_announcement %}<span class="text-announce">●</span>{% else %}<span class="text-faint">—</span>{% endif %}</td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
    </div>
</div>

{# ── 5-Layer Signal Breakdown ── #}
<div class="detail-section" class="mb-lg">
    <div class="detail-section-title">5层信号分解</div>
    <div class="table-scroll">
    <table class="data-table">
        <thead>
            <tr>
                <th>股票</th>
                <th style="color:var(--dim-hard)">硬 40%</th>
                <th style="color:var(--dim-soft)">软 25%</th>
                <th style="color:var(--dim-gate)">门控 15%</th>
                <th class="text-dragon">龙虎 10%</th>
                <th class="text-announce">公告 10%</th>
                <th>最终评分</th>
            </tr>
        </thead>
        <tbody>
            {% for stock in stocks %}
            <tr>
                <td class="stock-cell">
                    <a href="{% if use_app_pages %}app/stock.html?code={{ stock.code }}{% else %}stock/{{ stock.code }}.html{% endif %}" class="stock-code-link">
                        {{ stock.code }} {{ stock.name }}
                    </a>
                </td>
                <td style="color:{{ '#22C55E' if stock.signal_breakdown.hard_score > 0 else '#EF4444' if stock.signal_breakdown.hard_score < 0 else 'var(--text-muted)' }}">{{ '%+.3f'|format(stock.signal_breakdown.hard_score) }}</td>
                <td style="color:{{ '#22C55E' if stock.signal_breakdown.soft_score > 0 else '#EF4444' if stock.signal_breakdown.soft_score < 0 else 'var(--text-muted)' }}">{{ '%+.3f'|format(stock.signal_breakdown.soft_score) }}</td>
                <td style="color:{{ '#22C55E' if stock.signal_breakdown.gate_score > 0.5 else '#EF4444' if stock.signal_breakdown.gate_score < 0.5 else 'var(--text-muted)' }}">{{ '%+.3f'|format(stock.signal_breakdown.gate_score) }}</td>
                <td>{% if stock.signal_breakdown.has_dragon_tiger %}{{ '%+.3f'|format(stock.signal_breakdown.dragon_tiger_score) }}{% else %}<span class="text-faint">—</span>{% endif %}</td>
                <td>{% if stock.signal_breakdown.has_announcement %}{{ '%+.3f'|format(stock.signal_breakdown.announcement_score) }}{% else %}<span class="text-faint">—</span>{% endif %}</td>
                <td style="font-weight:700;color:{{ '#22C55E' if stock.signal_breakdown.final_score > 0.2 else '#EF4444' if stock.signal_breakdown.final_score < -0.2 else 'var(--text-muted)' }}">{{ '%+.3f'|format(stock.signal_breakdown.final_score) }}</td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
    </div>
</div>

{# ── Signal Distribution Bar ── #}
{% if stocks %}
<div class="detail-section" class="mb-lg">
    <div class="detail-section-title">信号分布</div>
    {% set total = bullish_count + hold_count + bearish_count %}
    {% if total > 0 %}
    <div class="signal-bar" style="height:36px;border-radius:var(--r-md)">
        {% if bullish_count > 0 %}
        <div class="signal-bar-seg bull" style="width:{{ (bullish_count/total*100)|round }}%;display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:700;color:#fff">看多 {{ bullish_count }}</div>
        {% endif %}
        {% if hold_count > 0 %}
        <div class="signal-bar-seg hold" style="width:{{ (hold_count/total*100)|round }}%;display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:700;color:#fff">观望 {{ hold_count }}</div>
        {% endif %}
        {% if bearish_count > 0 %}
        <div class="signal-bar-seg bear" style="width:{{ (bearish_count/total*100)|round }}%;display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:700;color:#fff">看空 {{ bearish_count }}</div>
        {% endif %}
    </div>
    {% endif %}
    <div style="font-size:12px;color:var(--text-muted);margin-top:8px">共 {{ stocks|length }} 只自选股</div>
</div>
{% endif %}

<div class="disclaimer">{{ disclaimer }}</div>
<footer class="site-footer">智策 NexStrat v2.0 · AI 辅助决策 · 不构成投资建议</footer>
</div>

{{ bottom_nav }}
</body>
</html>
"""


def generate_site(report: Report, target_dir: str | None = None) -> str:
    """Generate multi-page static site from a Report."""
    settings = get_settings()
    is_test = target_dir is not None

    if is_test:
        site_dir = Path(target_dir)
        archive_dir = site_dir / "archive"
        data_dir = site_dir / "data"
    else:
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
    bullish_count = 0
    hold_count = 0
    bearish_count = 0

    for a in report.analyses:
        stock = _analysis_to_stock_dict(a)
        if stock["overall_sentiment"] in ("strong_buy", "buy"):
            bullish_count += 1
        elif stock["overall_sentiment"] in ("sell", "strong_sell"):
            bearish_count += 1
        else:
            hold_count += 1
        stocks.append(stock)

    stocks.sort(key=lambda s: abs(s["signal_breakdown"]["final_score"]), reverse=True)

    # ── Phase F: Market Breadth Score ──────────────────────────────────
    from src.analysis.breadth import MarketBreadthScorer
    breadth_scorer = MarketBreadthScorer()
    breadth_raw = breadth_scorer.compute(report.analyses)

    # 为模板添加 zone_label 和 color
    zone_labels = {
        "strong": "强势", "healthy": "健康", "neutral": "中性",
        "weakening": "走弱", "critical": "极弱",
    }
    zone_colors = {
        "strong": "#22C55E", "healthy": "#84CC16", "neutral": "#F59E0B",
        "weakening": "#F97316", "critical": "#EF4444",
    }
    breadth_data = {
        **breadth_raw,
        "zone_label": zone_labels.get(breadth_raw["zone"], breadth_raw["zone"]),
        "color": zone_colors.get(breadth_raw["zone"], "#94A3B8"),
    }

    # ── Phase F: Postmortem / Signal Review Stats ──────────────────────
    postmortem_stats = _load_postmortem_stats(settings)

    archive = _load_archive_entries(settings)
    history = _load_history(settings)

    latest = {"meta": meta, "market": market, "stocks": stocks, "failed_symbols": report.failed_symbols, "archive": archive, "breadth": breadth_data}
    json_path = data_dir / "latest.json"
    new_count = len(stocks)
    existing_count = 0
    if json_path.exists():
        try:
            existing = json.loads(json_path.read_text())
            existing_count = len(existing.get("stocks", []))
        except Exception:
            pass

    if new_count == 0 and existing_count > 0:
        logger.warning("generate_site: skipping latest.json — 0 new vs %d existing", existing_count)
    elif new_count < existing_count and new_count > 0:
        if new_count < existing_count * 0.8:
            logger.warning("generate_site: skipping latest.json — %d vs %d (>20%% drop)", new_count, existing_count)
        else:
            json_path.write_text(json.dumps(latest, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        json_path.write_text(json.dumps(latest, ensure_ascii=False, indent=2), encoding="utf-8")

    # ── Render pages ───────────────────────────────────────────
    use_app_pages = get_settings().pipeline.skip_stock_html
    common = {"brand_svg": BRAND_SVG, "disclaimer": meta["disclaimer"]}

    # Page 1: index.html
    html = Template(TPL_HOME).render(
        **common, meta=meta, type_label=type_label, market=market,
        stocks=stocks, archive=archive,
        bullish_count=bullish_count, hold_count=hold_count, bearish_count=bearish_count,
        use_app_pages=use_app_pages, bottom_nav=Template(BOTTOM_NAV).render(page="home"),
        nav=Template(NAV_HTML).render(page="home"),
        session_rail=SESSION_RAIL,
        breadth=breadth_data,
    )
    (site_dir / "index.html").write_text(html, encoding="utf-8")

    # Page 2: stock/{code}.html
    if not get_settings().pipeline.skip_stock_html:
        stock_dir = site_dir / "stock"
        stock_dir.mkdir(exist_ok=True)
        sub_nav = Template(NAV_HTML_SUB).render(page="stock").replace("cockpit.html", "../app/cockpit.html")
        sub_bottom = Template(BOTTOM_NAV).render(page="stock").replace("app/cockpit.html", "../app/cockpit.html")
        for stock in stocks:
            shtml = Template(TPL_STOCK).render(
                **common, stock=stock, meta=meta, type_label=type_label,
                nav=sub_nav, bottom_nav=sub_bottom, page="stock",
            )
            (stock_dir / f"{stock['code']}.html").write_text(shtml, encoding="utf-8")
    else:
        logger.info("skip_stock_html=true — skipping %d per-stock pages", len(stocks))

    # Page 3: history.html
    hhtml = Template(TPL_HISTORY).render(
        **common, history=history,
        meta=meta, type_label=type_label,
        postmortem_stats=postmortem_stats,
        use_app_pages=use_app_pages,
        bottom_nav=Template(BOTTOM_NAV).render(page="history"),
        nav=Template(NAV_HTML).render(page="history"),
    )
    (site_dir / "history.html").write_text(hhtml, encoding="utf-8")

    # Page 4: dashboard.html
    dhtml = Template(TPL_DASHBOARD).render(
        **common, meta=meta, type_label=type_label, market=market,
        stocks=stocks,
        bullish_count=bullish_count, hold_count=hold_count, bearish_count=bearish_count,
        breadth=breadth_data,
        postmortem_stats=postmortem_stats,
        use_app_pages=use_app_pages,
        bottom_nav=Template(BOTTOM_NAV).render(page="dashboard"),
        nav=Template(NAV_HTML).render(page="dashboard"),
    )
    (site_dir / "dashboard.html").write_text(dhtml, encoding="utf-8")

    # Archive
    archive_file = archive_dir / f"{report.trade_date}-{report.report_type.value}.html"
    archive_file.write_text(html, encoding="utf-8")

    _copy_app_assets(site_dir)
    _export_phase_g_json(site_dir, report.trade_date)

    if not is_test:
        _sync_to_docs(settings)

    logger.info("Site generated: %s (%d stocks, %d pages)", site_dir / "index.html", len(stocks), 3 + len(stocks))
    return str(site_dir / "index.html")


def _load_archive_entries(settings) -> list[dict]:
    archive_dir = Path(settings.site.archive_dir)
    archive = []
    if archive_dir.exists():
        for f in sorted(archive_dir.glob("*.html"), reverse=True)[:20]:
            stem = f.stem
            parts = stem.rsplit("-", 1)
            if len(parts) == 2:
                archive.append({"date": parts[0], "type": parts[1], "url": f"archive/{stem}.html"})
    return archive


def _load_history(settings) -> dict:
    import sqlite3
    db_path = Path("data") / "signals.db"
    if not db_path.exists():
        return {}
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("""
        SELECT code, trade_date, report_type,
               hard_score, soft_score, gate_score,
               final_score, final_signal, signal_label, llm_confidence
        FROM signals ORDER BY code, trade_date
    """)
    rows = cur.fetchall()
    history = {}
    for r in rows:
        code = r["code"]
        if code not in history:
            cur2 = conn.cursor()
            cur2.execute("SELECT name FROM stock_meta WHERE code = ?", (code,))
            meta_row = cur2.fetchone()
            name = meta_row["name"] if meta_row else code
            cur3 = conn.cursor()
            cur3.execute("""
                SELECT AVG(final_score) as avg_score,
                       SUM(CASE WHEN final_signal IN ('strong_buy','buy') THEN 1 ELSE 0 END) as bullish,
                       SUM(CASE WHEN final_signal IN ('sell','strong_sell') THEN 1 ELSE 0 END) as bearish,
                       SUM(CASE WHEN final_signal = 'hold' THEN 1 ELSE 0 END) as hold,
                       COUNT(*) as total
                FROM signals WHERE code = ?
            """, (code,))
            stats = cur3.fetchone()
            history[code] = {
                "name": name, "records": [],
                "stats": {"avg_score": stats["avg_score"] or 0, "bullish_count": stats["bullish"] or 0,
                          "bearish_count": stats["bearish"] or 0, "hold_count": stats["hold"] or 0,
                          "total": stats["total"] or 0}
            }
        history[code]["records"].append({
            "trade_date": str(r["trade_date"]), "report_type": r["report_type"],
            "hard_score": r["hard_score"] or 0, "soft_score": r["soft_score"] or 0,
            "gate_score": r["gate_score"] or 0.5, "final_score": r["final_score"] or 0,
            "final_signal": r["final_signal"] or "hold",
            "signal_label": r["signal_label"] or "⚪ 观望",
            "confidence": r["llm_confidence"] or 0.5,
        })
    conn.close()
    return history


def _load_postmortem_stats(settings) -> dict:
    """Load signal postmortem summary stats from DB for last 30 days."""
    import sqlite3
    db_path = Path("data") / "signals.db"
    if not db_path.exists():
        return {}
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # Check if postmortem table exists
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='signal_postmortems'")
        if not cur.fetchone():
            conn.close()
            return {}

        # Get postmortem summary
        cur.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN outcome_category = 'true_positive' THEN 1 ELSE 0 END) as tp,
                SUM(CASE WHEN outcome_category = 'false_positive' THEN 1 ELSE 0 END) as fp,
                SUM(CASE WHEN outcome_category = 'missed_opportunity' THEN 1 ELSE 0 END) as missed,
                SUM(CASE WHEN outcome_category = 'regime_mismatch' THEN 1 ELSE 0 END) as regime
            FROM signal_postmortems
            WHERE outcome_category IS NOT NULL
        """)
        row = cur.fetchone()
        if not row or row["total"] == 0:
            conn.close()
            return {}

        total = row["total"]
        result = {
            "total": total,
            "tp": row["tp"] or 0,
            "fp": row["fp"] or 0,
            "missed": row["missed"] or 0,
            "regime": row["regime"] or 0,
            "win_rate": round((row["tp"] or 0) / total, 3),
        }

        # Average returns
        cur.execute("""
            SELECT AVG(actual_return_5d) as avg_5d, AVG(actual_return_20d) as avg_20d
            FROM signal_postmortems WHERE outcome_category IS NOT NULL
        """)
        ret_row = cur.fetchone()
        result["avg_return_5d"] = round(ret_row["avg_5d"], 2) if ret_row["avg_5d"] is not None else None
        result["avg_return_20d"] = round(ret_row["avg_20d"], 2) if ret_row["avg_20d"] is not None else None

        # Contradiction impact
        cur.execute("""
            SELECT
                SUM(CASE WHEN outcome_category = 'true_positive' THEN 1 ELSE 0 END) * 1.0 / COUNT(*) as win_rate,
                COUNT(*) as cnt
            FROM signal_postmortems
            WHERE outcome_category IS NOT NULL
              AND contradiction_flags IS NOT NULL AND contradiction_flags != '[]'
              AND contradiction_flags != 'null'
        """)
        contra_row = cur.fetchone()
        result["contra_win_rate"] = round(contra_row["win_rate"], 3) if contra_row and contra_row["cnt"] > 0 else None
        result["contra_count"] = contra_row["cnt"] if contra_row else 0

        cur.execute("""
            SELECT
                SUM(CASE WHEN outcome_category = 'true_positive' THEN 1 ELSE 0 END) * 1.0 / COUNT(*) as win_rate,
                COUNT(*) as cnt
            FROM signal_postmortems
            WHERE outcome_category IS NOT NULL
              AND (contradiction_flags IS NULL OR contradiction_flags = '[]' OR contradiction_flags = 'null')
        """)
        no_contra_row = cur.fetchone()
        result["no_contra_win_rate"] = round(no_contra_row["win_rate"], 3) if no_contra_row and no_contra_row["cnt"] > 0 else None
        result["no_contra_count"] = no_contra_row["cnt"] if no_contra_row else 0

        conn.close()
        return result
    except Exception as e:
        logger.warning("Failed to load postmortem stats: %s", e)
        return {}


def _export_phase_g_json(site_dir: Path, trade_date) -> None:
    """Export Phase G static JSON snapshots."""
    data_dir = site_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    td = str(trade_date)
    try:
        from src.intelligence.ingester import KnowledgeIngester
        digest = KnowledgeIngester().export_json(trade_date)
        (data_dir / "digest.json").write_text(
            json.dumps(digest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception as e:
        logger.warning("digest.json export failed: %s", e)
    try:
        from src.recommendation.engine import RecommendationEngine
        rec = RecommendationEngine().export_json(trade_date)
        (data_dir / "recommendation.json").write_text(
            json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception as e:
        logger.warning("recommendation.json export failed: %s", e)
    try:
        from src.review.recommendation_review import RecommendationReview
        from datetime import date as d
        if trade_date == d.today() or str(trade_date) == d.today().isoformat():
            review = RecommendationReview().export_json(trade_date)
            (data_dir / "review.json").write_text(
                json.dumps(review, ensure_ascii=False, indent=2), encoding="utf-8"
            )
    except Exception as e:
        logger.debug("review.json export skipped: %s", e)


def _copy_app_assets(site_dir: Path) -> None:
    src_app = Path(__file__).resolve().parent / "app"
    dst_app = site_dir / "app"
    if not src_app.exists():
        return
    if dst_app.exists():
        shutil.rmtree(dst_app)
    shutil.copytree(src_app, dst_app)
    logger.debug("Copied app assets to %s", dst_app)


def _sync_to_docs(settings) -> None:
    import pathlib
    project_root = pathlib.Path(__file__).resolve().parent.parent.parent
    docs_dir = project_root / "docs"
    site_dir = Path(settings.site.output_dir)

    new_count = 0
    existing_count = 0
    site_latest = site_dir / "data" / "latest.json"
    docs_latest = docs_dir / "data" / "latest.json"
    if site_latest.exists():
        try: new_count = len(json.loads(site_latest.read_text()).get("stocks", []))
        except Exception: pass
    if docs_latest.exists():
        try: existing_count = len(json.loads(docs_latest.read_text()).get("stocks", []))
        except Exception: pass

    if new_count == 0 and existing_count > 0:
        logger.warning("_sync_to_docs: SKIPPED — 0 new vs %d existing", existing_count)
        return
    if new_count < existing_count and new_count < existing_count * 0.8:
        logger.warning("_sync_to_docs: SKIPPED — %d vs %d (>20%% drop)", new_count, existing_count)
        return

    if not docs_dir.exists():
        docs_dir.mkdir(exist_ok=True)

    for src_dir in ["assets", "archive", "data"]:
        src = site_dir / src_dir
        dst = docs_dir / src_dir
        if src.exists():
            if dst.exists(): shutil.rmtree(dst)
            shutil.copytree(src, dst)

    if not get_settings().pipeline.skip_stock_html:
        stock_src = site_dir / "stock"
        if stock_src.exists():
            stock_dst = docs_dir / "stock"
            if stock_dst.exists(): shutil.rmtree(stock_dst)
            shutil.copytree(stock_src, stock_dst)

    app_src = site_dir / "app"
    if app_src.exists():
        app_dst = docs_dir / "app"
        if app_dst.exists(): shutil.rmtree(app_dst)
        shutil.copytree(app_src, app_dst)

    meta_src = site_dir / "meta"
    if meta_src.exists():
        meta_dst = docs_dir / "meta"
        if meta_dst.exists(): shutil.rmtree(meta_dst)
        shutil.copytree(meta_src, meta_dst)

    for page in ["index.html", "history.html", "dashboard.html"]:
        src = site_dir / page
        if src.exists():
            shutil.copy2(src, docs_dir / page)

    logger.info("Site synced to docs/ (%d stocks)", new_count)
