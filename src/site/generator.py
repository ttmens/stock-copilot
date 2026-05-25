"""Static site generator — multi-page site from report data.

Pages:
1. index.html — 首页：市场温度 + 自选股概览
2. stock/{code}.html — 个股详情：5层信号分解 + LLM分析 + 龙虎榜 + 公告
3. history.html — 历史信号：所有股票历史趋势 + 胜率统计
4. dashboard.html — 数据看板：自选股横向对比 + 信号分布

Design system: Deep Space Intelligence Platform (UI-UX-Style.md v1.0)
"""

import json
import logging
import shutil
from datetime import datetime
from pathlib import Path

from jinja2 import Template

from src.config import get_settings
from src.data.models import Report

logger = logging.getLogger(__name__)

# ── CSS tokens: Deep Space Intelligence Platform ─────────────────────────
THEME_CSS = """\
:root {
    /* Brand */
    --rausch: #7b3ff2;
    --rausch-active: #4a5bff;
    --rausch-tint: rgba(123,63,242,0.22);
    --accent-cyan: #00f5ff;
    --accent-blue: #4a5bff;
    --accent-purple: #7b3ff2;
    --accent-warm: #ff6b6b;
    --gradient-brand: linear-gradient(90deg, #7b3ff2 0%, #4a5bff 50%, #00f5ff 100%);

    /* Surfaces */
    --canvas-deep: #0a1628;
    --canvas: #1a2742;
    --surface-soft: #0f1f3a;
    --surface-elevated: #1a2742;
    --surface-elevated-alt: #0f1f3a;

    /* Text */
    --ink: #ffffff;
    --body-ink: rgba(255,255,255,0.86);
    --muted: rgba(255,255,255,0.65);
    --muted-soft: rgba(255,255,255,0.5);
    --text-primary: var(--ink);
    --text-secondary: var(--muted);

    /* Semantic */
    --bullish: #22C55E;
    --bearish: #EF4444;
    --neutral: #94A3B8;
    --warning: #F59E0B;

    /* Borders */
    --hairline: rgba(255,255,255,0.14);
    --hairline-soft: rgba(255,255,255,0.08);
    --border-strong: rgba(255,255,255,0.22);

    /* Shadows */
    --shadow-sm: 0 1px 2px rgba(0,0,0,0.35);
    --shadow-md: 0 6px 20px rgba(0,0,0,0.45);
    --shadow-lg: 0 16px 48px rgba(0,0,0,0.55);

    /* Radius */
    --radius-sm: 8px;
    --radius-md: 14px;
    --radius-lg: 20px;
    --radius-full: 9999px;

    /* Page bg gradient */
    --page-bg-gradient:
        radial-gradient(ellipse 120% 90% at 0% -10%, rgba(123,63,242,0.18), transparent 52%),
        radial-gradient(ellipse 90% 70% at 100% 0%, rgba(0,245,255,0.10), transparent 48%);

    /* Typography */
    --font-sans: Circular, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', sans-serif;
    --font-cn: 'PingFang SC', 'Microsoft YaHei', var(--font-sans);
    --font-mono: ui-monospace, 'Cascadia Code', 'JetBrains Mono', monospace;
}

* { box-sizing: border-box; margin: 0; padding: 0; }

body {
    font-family: var(--font-cn);
    font-size: 14px;
    line-height: 1.58;
    color: var(--body-ink);
    background-color: var(--canvas-deep);
    background-image: var(--page-bg-gradient);
    min-height: 100vh;
    -webkit-font-smoothing: antialiased;
}

a { color: var(--accent-cyan); text-decoration: none; }
a:hover { color: var(--rausch-active); }

/* ── Shell ──────────────────────────────────────────────────── */
.shell {
    max-width: 860px;
    margin: 0 auto;
    padding: calc(64px + 24px) 20px 80px;
}
.shell-wide {
    max-width: 1100px;
    margin: 0 auto;
    padding: calc(64px + 24px) 20px 80px;
}

/* ── Header (glass-morphism) ────────────────────────────────── */
.site-header {
    position: fixed;
    top: 0; left: 0; right: 0;
    min-height: 64px;
    padding: 12px max(20px, 5vw);
    background: rgba(10,22,40,0.92);
    backdrop-filter: blur(16px) saturate(1.1);
    border-bottom: 1px solid var(--hairline-soft);
    box-shadow: 0 1px 0 rgba(0,245,255,0.06);
    z-index: 102;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
}
.brand {
    display: flex;
    align-items: center;
    gap: 10px;
}
.brand-icon {
    width: 28px; height: 28px;
    border-radius: var(--radius-sm);
    background: var(--gradient-brand);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 14px;
}
.brand-name {
    font-size: 16px;
    font-weight: 600;
    letter-spacing: -0.02em;
    color: var(--ink);
}

/* Nav pills */
.site-nav {
    display: flex;
    gap: 4px;
    background: rgba(255,255,255,0.06);
    border: 1px solid var(--hairline-soft);
    border-radius: var(--radius-full);
    padding: 4px;
}
.site-nav a {
    padding: 5px 14px;
    border-radius: var(--radius-full);
    font-size: 12px;
    font-weight: 600;
    color: var(--muted);
    transition: all 0.18s ease;
}
.site-nav a:hover { color: var(--ink); }
.site-nav a.active {
    background: rgba(255,255,255,0.12);
    color: var(--ink);
    box-shadow: 0 1px 0 rgba(0,245,255,0.1), var(--shadow-sm);
}
.header-meta {
    font-size: 12px;
    color: var(--muted);
    font-family: var(--font-mono);
}

/* ── Page title ─────────────────────────────────────────────── */
.page-title {
    font-size: 24px;
    font-weight: 700;
    letter-spacing: -0.03em;
    color: var(--ink);
    margin-bottom: 24px;
    display: flex;
    align-items: center;
    gap: 12px;
}
.page-subtitle {
    font-size: 14px;
    font-weight: 400;
    color: var(--muted);
    margin-bottom: 24px;
}

/* ── Market Temperature ─────────────────────────────────────── */
.market-temp {
    background: var(--canvas);
    border: 1px solid var(--hairline-soft);
    border-radius: var(--radius-md);
    padding: 16px 20px;
    margin-bottom: 24px;
    box-shadow: var(--shadow-sm);
}
.market-temp-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 10px;
}
.market-temp-label {
    font-size: 12px;
    font-weight: 600;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.06em;
}
.market-temp-index {
    font-family: var(--font-mono);
    font-size: 18px;
    font-weight: 600;
    color: var(--ink);
}
.market-temp-change {
    font-family: var(--font-mono);
    font-size: 14px;
    font-weight: 600;
}
.up { color: var(--bullish); }
.down { color: var(--bearish); }

.signal-distribution {
    display: flex;
    gap: 12px;
    font-size: 13px;
}
.sig-stat {
    display: flex;
    align-items: center;
    gap: 4px;
    color: var(--muted);
}
.sig-dot {
    width: 8px; height: 8px;
    border-radius: 50%;
}
.sig-dot.green { background: var(--bullish); }
.sig-dot.red { background: var(--bearish); }
.sig-dot.gray { background: var(--neutral); }

/* ── Section titles ─────────────────────────────────────────── */
.section-title {
    font-size: 18px;
    font-weight: 600;
    color: var(--ink);
    margin-bottom: 16px;
    display: flex;
    align-items: center;
    gap: 8px;
}
.section-title .count {
    font-size: 13px;
    font-weight: 400;
    color: var(--muted);
}

/* ── Stock grid ─────────────────────────────────────────────── */
.stock-grid {
    display: grid;
    gap: 16px;
    margin-bottom: 24px;
}
@media (min-width: 640px) {
    .stock-grid { grid-template-columns: 1fr 1fr; }
}

/* ── Narrative card ─────────────────────────────────────────── */
.narr-card {
    border: 1px solid var(--hairline-soft);
    border-radius: var(--radius-md);
    background: var(--canvas);
    padding: 16px 18px 14px;
    box-shadow: var(--shadow-sm);
    transition: border-color 0.18s ease, box-shadow 0.18s ease;
}
.narr-card:hover {
    border-color: var(--border-strong);
    box-shadow: var(--shadow-md);
}

/* Card header: signal pill + stock name */
.narr-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    margin-bottom: 12px;
}
.narr-stock {
    display: flex;
    flex-direction: column;
    gap: 2px;
}
.narr-stock-code {
    font-family: var(--font-mono);
    font-size: 15px;
    font-weight: 600;
    color: var(--ink);
}
.narr-stock-name {
    font-size: 12px;
    color: var(--muted);
}

/* Signal badge (pill) */
.signal-pill {
    display: flex;
    align-items: center;
    gap: 4px;
    padding: 4px 10px;
    border-radius: var(--radius-full);
    font-size: 11px;
    font-weight: 600;
    white-space: nowrap;
    flex-shrink: 0;
}
.signal-pill.strong-buy,
.signal-pill.buy {
    background: rgba(34,197,94,0.15);
    color: var(--bullish);
    border: 1px solid rgba(34,197,94,0.3);
}
.signal-pill.sell,
.signal-pill.strong-sell {
    background: rgba(239,68,68,0.15);
    color: var(--bearish);
    border: 1px solid rgba(239,68,68,0.3);
}
.signal-pill.hold {
    background: rgba(148,163,184,0.12);
    color: var(--neutral);
    border: 1px solid rgba(148,163,184,0.2);
}

/* ── Score panel ────────────────────────────────────────────── */
.score-panel {
    background: var(--surface-soft);
    border-radius: var(--radius-sm);
    padding: 10px 12px;
    margin-bottom: 12px;
}
.score-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 6px;
}
.score-label { font-size: 12px; color: var(--muted); }
.score-value {
    font-family: var(--font-mono);
    font-size: 14px;
    font-weight: 700;
}
.score-bar-track {
    height: 6px;
    background: rgba(255,255,255,0.06);
    border-radius: 3px;
    overflow: hidden;
    margin-bottom: 6px;
}
.score-bar-fill {
    height: 100%;
    border-radius: 3px;
    transition: width 0.3s ease;
}
.confidence-row {
    display: flex;
    align-items: center;
    gap: 4px;
    font-size: 11px;
    color: var(--muted);
}
.conf-dots { display: flex; gap: 2px; }
.conf-dot {
    width: 6px; height: 6px;
    border-radius: 50%;
    background: rgba(255,255,255,0.1);
}
.conf-dot.filled { background: var(--accent-cyan); }
.conf-value {
    margin-left: auto;
    font-family: var(--font-mono);
    color: var(--accent-cyan);
    font-weight: 500;
}

/* Signal breakdown grid */
.signal-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 4px;
    margin-top: 8px;
}
.signal-cell {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 3px 8px;
    border-radius: 4px;
    background: rgba(255,255,255,0.02);
    font-size: 11px;
}
.signal-cell-label { color: var(--muted-soft); }
.signal-cell-val {
    font-family: var(--font-mono);
    font-weight: 500;
}

/* ── Metrics row ────────────────────────────────────────────── */
.metrics-row {
    display: flex;
    gap: 6px;
    margin-bottom: 12px;
    flex-wrap: wrap;
}
.metric-chip {
    flex: 1;
    min-width: 56px;
    padding: 6px 6px;
    background: var(--surface-elevated-alt);
    border-radius: var(--radius-sm);
    text-align: center;
    border: 1px solid var(--hairline-soft);
}
.metric-chip-label {
    display: block;
    font-size: 10px;
    font-weight: 500;
    color: var(--muted-soft);
    margin-bottom: 2px;
    letter-spacing: 0.02em;
}
.metric-chip-val {
    display: block;
    font-family: var(--font-mono);
    font-size: 13px;
    font-weight: 600;
}

/* ── Dimension table ────────────────────────────────────────── */
.dim-table {
    width: 100%;
    font-size: 12px;
    border-collapse: collapse;
    margin-bottom: 10px;
}
.dim-table td {
    padding: 5px 8px;
    border-bottom: 1px solid var(--hairline-soft);
    vertical-align: top;
}
.dim-table tr:last-child td { border-bottom: none; }
.dim-name {
    font-weight: 600;
    color: var(--muted);
    white-space: nowrap;
    width: 48px;
}
.dim-status { width: 24px; text-align: center; }
.dim-summary {
    color: var(--body-ink);
    line-height: 1.4;
}

/* ── Dragon tiger ───────────────────────────────────────────── */
.dt-block {
    margin: 8px 0;
    padding: 10px 12px;
    background: var(--surface-soft);
    border-radius: var(--radius-sm);
    border-left: 3px solid var(--accent-purple);
}
.dt-title {
    font-size: 11px;
    font-weight: 600;
    color: var(--accent-purple);
    margin-bottom: 6px;
    text-transform: uppercase;
    letter-spacing: 0.06em;
}
.dt-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 12px;
    margin-bottom: 3px;
}
.dt-reason { color: var(--muted); }
.dt-net {
    font-family: var(--font-mono);
    font-weight: 600;
}

/* ── Announcement events ────────────────────────────────────── */
.ann-block {
    margin: 8px 0;
    padding: 10px 12px;
    background: var(--surface-soft);
    border-radius: var(--radius-sm);
    border-left: 3px solid var(--accent-warm);
}
.ann-title {
    font-size: 11px;
    font-weight: 600;
    color: var(--accent-warm);
    margin-bottom: 6px;
    text-transform: uppercase;
    letter-spacing: 0.06em;
}
.ann-event {
    display: flex;
    gap: 6px;
    align-items: flex-start;
    font-size: 12px;
    margin-bottom: 3px;
}
.ann-text { color: var(--body-ink); line-height: 1.4; flex: 1; }
.ann-conf {
    font-family: var(--font-mono);
    font-size: 10px;
    color: var(--muted-soft);
    white-space: nowrap;
}

/* ── Risk points ────────────────────────────────────────────── */
.risk-block {
    font-size: 12px;
    color: var(--warning);
    background: rgba(245,158,11,0.08);
    padding: 8px 12px;
    border-radius: var(--radius-sm);
    border-left: 3px solid var(--warning);
    margin-top: 8px;
    line-height: 1.5;
}

/* ── Archive / Links ────────────────────────────────────────── */
.archive-section {
    background: var(--canvas);
    border: 1px solid var(--hairline-soft);
    border-radius: var(--radius-md);
    padding: 16px 20px;
    margin-bottom: 24px;
}
.archive-list {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-top: 10px;
}
.archive-pill {
    font-size: 12px;
    padding: 4px 12px;
    border-radius: var(--radius-full);
    border: 1px solid var(--hairline);
    color: var(--muted);
    transition: all 0.18s ease;
}
.archive-pill:hover {
    border-color: var(--rausch);
    color: var(--ink);
    background: var(--rausch-tint);
}

/* ── Disclaimer ─────────────────────────────────────────────── */
.disclaimer {
    font-size: 12px;
    color: var(--muted-soft);
    line-height: 1.6;
    padding: 12px 16px;
    background: var(--surface-soft);
    border-radius: var(--radius-sm);
    border: 1px solid var(--hairline-soft);
    margin-bottom: 24px;
}

/* ── Footer ─────────────────────────────────────────────────── */
.site-footer {
    text-align: center;
    padding: 24px 0;
    color: var(--muted-soft);
    font-size: 11px;
    border-top: 1px solid var(--hairline-soft);
}

/* ── Empty state ────────────────────────────────────────────── */
.empty-state {
    text-align: center;
    padding: 48px 24px;
    color: var(--muted);
}
.empty-state-icon { font-size: 32px; margin-bottom: 12px; }
.empty-state-text { font-size: 14px; margin-bottom: 4px; }
.empty-state-sub { font-size: 12px; color: var(--muted-soft); }

/* ── Back button ────────────────────────────────────────────── */
.back-link {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 13px;
    color: var(--muted);
    margin-bottom: 20px;
    padding: 6px 14px;
    border-radius: var(--radius-full);
    border: 1px solid var(--hairline-soft);
    transition: all 0.18s ease;
}
.back-link:hover {
    color: var(--ink);
    border-color: var(--border-strong);
    background: var(--canvas);
}

/* ── Detail page: score breakdown ───────────────────────────── */
.detail-grid {
    display: grid;
    gap: 16px;
    margin-bottom: 24px;
}
@media (min-width: 640px) {
    .detail-grid { grid-template-columns: 1fr 1fr; }
}
.detail-section {
    background: var(--canvas);
    border: 1px solid var(--hairline-soft);
    border-radius: var(--radius-md);
    padding: 16px 18px;
    box-shadow: var(--shadow-sm);
}
.detail-section-title {
    font-size: 14px;
    font-weight: 600;
    color: var(--ink);
    margin-bottom: 12px;
    display: flex;
    align-items: center;
    gap: 6px;
}
.detail-score-big {
    font-family: var(--font-mono);
    font-size: 36px;
    font-weight: 700;
    text-align: center;
    margin: 12px 0;
}
.detail-score-label {
    text-align: center;
    font-size: 12px;
    color: var(--muted);
    margin-bottom: 8px;
}

/* ── History table ──────────────────────────────────────────── */
.history-table {
    width: 100%;
    font-size: 12px;
    border-collapse: collapse;
    margin-bottom: 16px;
}
.history-table th {
    padding: 8px 10px;
    text-align: left;
    font-weight: 600;
    color: var(--muted);
    border-bottom: 1px solid var(--hairline);
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
}
.history-table td {
    padding: 8px 10px;
    border-bottom: 1px solid var(--hairline-soft);
    font-family: var(--font-mono);
}
.history-table tr:hover td {
    background: rgba(255,255,255,0.02);
}

/* ── Dashboard: comparison table ────────────────────────────── */
.comp-table {
    width: 100%;
    font-size: 13px;
    border-collapse: collapse;
    margin-bottom: 16px;
}
.comp-table th {
    padding: 10px 12px;
    text-align: left;
    font-weight: 600;
    color: var(--muted);
    border-bottom: 1px solid var(--hairline);
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
}
.comp-table td {
    padding: 10px 12px;
    border-bottom: 1px solid var(--hairline-soft);
}
.comp-table .stock-cell {
    font-family: var(--font-mono);
    font-weight: 600;
    color: var(--ink);
}

/* ── Stats cards ────────────────────────────────────────────── */
.stats-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
    gap: 12px;
    margin-bottom: 24px;
}
.stat-card {
    background: var(--canvas);
    border: 1px solid var(--hairline-soft);
    border-radius: var(--radius-md);
    padding: 14px 16px;
    text-align: center;
}
.stat-value {
    font-family: var(--font-mono);
    font-size: 24px;
    font-weight: 700;
    color: var(--ink);
}
.stat-label {
    font-size: 11px;
    color: var(--muted);
    margin-top: 4px;
}

/* ── Responsive ─────────────────────────────────────────────── */
@media (max-width: 900px) {
    .shell, .shell-wide { padding: calc(64px + 16px) 16px 80px; }
    .market-temp-head { flex-direction: column; align-items: flex-start; gap: 8px; }
    .site-nav { display: none; }
}
@media (max-width: 480px) {
    .stock-grid { grid-template-columns: 1fr; }
    .signal-grid { grid-template-columns: 1fr; }
    .metrics-row { flex-wrap: nowrap; overflow-x: auto; }
    .brand-name { font-size: 14px; }
    .detail-grid { grid-template-columns: 1fr; }
    .stats-grid { grid-template-columns: 1fr 1fr; }
}

/* ── Reduced motion ─────────────────────────────────────────── */
@media (prefers-reduced-motion: reduce) {
    *, *::before, *::after {
        animation-duration: 0.01ms !important;
        transition-duration: 0.01ms !important;
    }
}
"""

# ── Nav bar (shared across all pages) ──────────────────────────
NAV_HTML = """
<div class="site-nav">
    <a href="index.html"{{ ' class="active"' if page == 'home' else '' }}>首页</a>
    <a href="dashboard.html"{{ ' class="active"' if page == 'dashboard' else '' }}>看板</a>
    <a href="history.html"{{ ' class="active"' if page == 'history' else '' }}>历史</a>
</div>
"""


# ── Template: Homepage (index.html) ───────────────────────────
TPL_HOME = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
    <title>Stock Copilot — {{ meta.trade_date }} {{ type_label }}</title>
    <link rel="stylesheet" href="assets/theme.css">
</head>
<body>

<header class="site-header">
    <div class="brand">
        <div class="brand-icon">📊</div>
        <span class="brand-name">Stock Copilot</span>
    </div>
    """ + NAV_HTML.replace("page == 'home'", "True") + """
    <span class="header-meta">{{ meta.trade_date }} {{ type_label }} · {{ meta.generated_at[11:16] }}</span>
</header>

<div class="shell">

    {% if market and market.close %}
    <div class="market-temp">
        <div class="market-temp-head">
            <span class="market-temp-label">市场温度</span>
            <div>
                <span class="market-temp-index">{{ market.index_name }} {{ "%.2f"|format(market.close) }}</span>
                {% if market.change_pct >= 0 %}
                <span class="market-temp-change up">&nbsp;+{{ "%.2f"|format(market.change_pct) }}%</span>
                {% else %}
                <span class="market-temp-change down">&nbsp;{{ "%.2f"|format(market.change_pct) }}%</span>
                {% endif %}
            </div>
        </div>
        <div class="signal-distribution">
            <span class="sig-stat"><span class="sig-dot green"></span> 看多 {{ bullish_count }}</span>
            <span class="sig-stat"><span class="sig-dot gray"></span> 观望 {{ hold_count }}</span>
            <span class="sig-stat"><span class="sig-dot red"></span> 看空 {{ bearish_count }}</span>
        </div>
    </div>
    {% endif %}

    <div class="section-title">
        今日重点 <span class="count">({{ stocks|length }} 只自选)</span>
    </div>

    {% if not stocks %}
    <div class="empty-state">
        <div class="empty-state-icon">📭</div>
        <div class="empty-state-text">暂无分析数据</div>
        <div class="empty-state-sub">非交易日或数据采集失败，下次交易日自动更新</div>
    </div>
    {% endif %}

    <div class="stock-grid">
        {% for stock in stocks %}
        <a href="stock/{{ stock.code }}.html" style="text-decoration:none;color:inherit">
        <div class="narr-card">
            <div class="narr-header">
                <div class="narr-stock">
                    <span class="narr-stock-code">{{ stock.code }}</span>
                    <span class="narr-stock-name">{{ stock.name }}</span>
                </div>
                {% set pill_class = 'strong-buy' if stock.overall_sentiment == 'strong_buy'
                    else 'buy' if stock.overall_sentiment in ['buy', 'bullish']
                    else 'strong-sell' if stock.overall_sentiment == 'strong_sell'
                    else 'sell' if stock.overall_sentiment == 'sell'
                    else 'hold' %}
                <span class="signal-pill {{ pill_class }}">
                    {{ stock.overall_focus }}
                </span>
            </div>

            <div class="score-panel">
                <div class="score-row">
                    <span class="score-label">综合评分</span>
                    <span class="score-value" style="color:{{ '#22C55E' if stock.signal_breakdown.final_score > 0.2 else '#EF4444' if stock.signal_breakdown.final_score < -0.2 else '#94A3B8' }}">
                        {{ '%+.3f'|format(stock.signal_breakdown.final_score) }}
                    </span>
                </div>
                <div class="score-bar-track">
                    <div class="score-bar-fill" style="width: {{ ((stock.signal_breakdown.final_score + 1) / 2 * 100) }}%; background: {{ '#22C55E' if stock.signal_breakdown.final_score > 0.2 else '#EF4444' if stock.signal_breakdown.final_score < -0.2 else '#94A3B8' }};"></div>
                </div>
                <div class="confidence-row">
                    <span>置信度</span>
                    <div class="conf-dots">
                        {% for i in range(5) %}
                        <span class="conf-dot {{ 'filled' if i < (stock.confidence * 5)|round(0, 'floor')|int else '' }}"></span>
                        {% endfor %}
                    </div>
                    <span class="conf-value">{{ (stock.confidence * 100)|round(0) }}%</span>
                </div>
            </div>

            <div class="metrics-row">
                {% if stock.momentum_5d is not none %}
                <div class="metric-chip" style="{{ 'border-color:rgba(34,197,94,0.3)' if stock.momentum_5d > 0 else 'border-color:rgba(239,68,68,0.3)' if stock.momentum_5d < 0 else '' }}">
                    <span class="metric-chip-label">5日</span>
                    <span class="metric-chip-val" style="color:{{ '#22C55E' if stock.momentum_5d > 0 else '#EF4444' if stock.momentum_5d < 0 else 'var(--body-ink)' }}">{{ '%+.1f'|format(stock.momentum_5d) }}%</span>
                </div>
                {% endif %}
                {% if stock.ma_alignment %}
                <div class="metric-chip" style="{{ 'border-color:rgba(34,197,94,0.3)' if stock.ma_alignment == 'bullish' else 'border-color:rgba(239,68,68,0.3)' if stock.ma_alignment == 'bearish' else '' }}">
                    <span class="metric-chip-label">均线</span>
                    <span class="metric-chip-val" style="color:{{ '#22C55E' if stock.ma_alignment == 'bullish' else '#EF4444' if stock.ma_alignment == 'bearish' else 'var(--body-ink)' }}">{{ {'bullish': '多头', 'bearish': '空头', 'neutral': '交叉'}[stock.ma_alignment] }}</span>
                </div>
                {% endif %}
                {% if stock.volume_ratio is not none %}
                <div class="metric-chip" style="{{ 'border-color:rgba(34,197,94,0.3)' if stock.volume_ratio > 1.2 else 'border-color:rgba(239,68,68,0.3)' if stock.volume_ratio < 0.8 else '' }}">
                    <span class="metric-chip-label">量比</span>
                    <span class="metric-chip-val">{{ stock.volume_ratio }}</span>
                </div>
                {% endif %}
                {% if stock.pe_ttm is not none %}
                <div class="metric-chip">
                    <span class="metric-chip-label">PE</span>
                    <span class="metric-chip-val">{{ stock.pe_ttm }}</span>
                </div>
                {% endif %}
            </div>

            {% if stock.risk_points %}
            <div class="risk-block">
                <strong>⚠ 风险：</strong>{{ stock.risk_points | join('、') }}
            </div>
            {% endif %}
        </div>
        </a>
        {% endfor %}
    </div>

    {% if archive %}
    <div class="archive-section">
        <div style="font-size:14px;font-weight:600;color:var(--ink);margin-bottom:4px;">📁 历史报告</div>
        <div class="archive-list">
            {% for item in archive[:10] %}
            <a class="archive-pill" href="archive/{{ item.date }}-{{ item.type }}.html">{{ item.date }} {{ '盘前' if item.type == 'pre' else '盘后' }}</a>
            {% endfor %}
        </div>
    </div>
    {% endif %}

    <div class="disclaimer">{{ disclaimer }}</div>

    <footer class="site-footer">
        Stock Copilot v1.3 · AI 辅助决策 · 不构成投资建议
    </footer>
</div>
</body>
</html>
"""


# ── Template: Stock Detail Page ───────────────────────────────
TPL_STOCK = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
    <title>{{ stock.name }} ({{ stock.code }}) — Stock Copilot</title>
    <link rel="stylesheet" href="../assets/theme.css">
</head>
<body>

<header class="site-header">
    <div class="brand">
        <div class="brand-icon">📊</div>
        <span class="brand-name">Stock Copilot</span>
    </div>
    """ + NAV_HTML + """
    <span class="header-meta">{{ stock.code }} {{ stock.name }}</span>
</header>

<div class="shell">

    <a href="../index.html" class="back-link">← 返回首页</a>

    <div class="page-title">
        {{ stock.code }} <span style="font-weight:400;color:var(--muted)">{{ stock.name }}</span>
    </div>

    {% set pill_class = 'strong-buy' if stock.overall_sentiment == 'strong_buy'
        else 'buy' if stock.overall_sentiment in ['buy', 'bullish']
        else 'strong-sell' if stock.overall_sentiment == 'strong_sell'
        else 'sell' if stock.overall_sentiment == 'sell'
        else 'hold' %}
    <div style="margin-bottom:24px">
        <span class="signal-pill {{ pill_class }}" style="font-size:14px;padding:6px 16px">
            {{ stock.overall_focus }}
        </span>
    </div>

    <!-- Score breakdown -->
    <div class="detail-grid">
        <div class="detail-section">
            <div class="detail-section-title">📊 综合评分</div>
            <div class="detail-score-big" style="color:{{ '#22C55E' if stock.signal_breakdown.final_score > 0.2 else '#EF4444' if stock.signal_breakdown.final_score < -0.2 else '#94A3B8' }}">
                {{ '%+.3f'|format(stock.signal_breakdown.final_score) }}
            </div>
            <div class="detail-score-label">置信度 {{ (stock.confidence * 100)|round(0) }}%</div>
            <div class="score-bar-track" style="margin-top:8px">
                <div class="score-bar-fill" style="width: {{ ((stock.signal_breakdown.final_score + 1) / 2 * 100) }}%; background: {{ '#22C55E' if stock.signal_breakdown.final_score > 0.2 else '#EF4444' if stock.signal_breakdown.final_score < -0.2 else '#94A3B8' }};"></div>
            </div>
            <!-- 5-layer breakdown -->
            <div class="signal-grid" style="margin-top:16px">
                <div class="signal-cell">
                    <span class="signal-cell-label">硬信号 40%</span>
                    <span class="signal-cell-val" style="color:{{ '#22C55E' if stock.signal_breakdown.hard_score > 0 else '#EF4444' if stock.signal_breakdown.hard_score < 0 else 'var(--muted-soft)' }}">{{ '%+.3f'|format(stock.signal_breakdown.hard_score) }}</span>
                </div>
                <div class="signal-cell">
                    <span class="signal-cell-label">软信号 25%</span>
                    <span class="signal-cell-val" style="color:{{ '#22C55E' if stock.signal_breakdown.soft_score > 0 else '#EF4444' if stock.signal_breakdown.soft_score < 0 else 'var(--muted-soft)' }}">{{ '%+.3f'|format(stock.signal_breakdown.soft_score) }}</span>
                </div>
                <div class="signal-cell">
                    <span class="signal-cell-label">门控 15%</span>
                    <span class="signal-cell-val" style="color:{{ '#22C55E' if stock.signal_breakdown.gate_score > 0.5 else '#EF4444' if stock.signal_breakdown.gate_score < 0.5 else 'var(--muted-soft)' }}">{{ '%+.3f'|format(stock.signal_breakdown.gate_score) }}</span>
                </div>
                {% if stock.signal_breakdown.has_dragon_tiger %}
                <div class="signal-cell">
                    <span class="signal-cell-label">龙虎 10%</span>
                    <span class="signal-cell-val" style="color:{{ '#22C55E' if stock.signal_breakdown.dragon_tiger_score > 0 else '#EF4444' if stock.signal_breakdown.dragon_tiger_score < 0 else 'var(--muted-soft)' }}">{{ '%+.3f'|format(stock.signal_breakdown.dragon_tiger_score) }}</span>
                </div>
                {% endif %}
                {% if stock.signal_breakdown.has_announcement %}
                <div class="signal-cell">
                    <span class="signal-cell-label">公告 10%</span>
                    <span class="signal-cell-val" style="color:{{ '#22C55E' if stock.signal_breakdown.announcement_score > 0 else '#EF4444' if stock.signal_breakdown.announcement_score < 0 else 'var(--muted-soft)' }}">{{ '%+.3f'|format(stock.signal_breakdown.announcement_score) }}</span>
                </div>
                {% endif %}
            </div>
        </div>

        <!-- Hard signal metrics -->
        <div class="detail-section">
            <div class="detail-section-title">📈 硬信号指标</div>
            <div class="metrics-row" style="flex-wrap:wrap">
                {% if stock.momentum_5d is not none %}
                <div class="metric-chip" style="min-width:80px">
                    <span class="metric-chip-label">5日动量</span>
                    <span class="metric-chip-val" style="color:{{ '#22C55E' if stock.momentum_5d > 0 else '#EF4444' if stock.momentum_5d < 0 else 'var(--body-ink)' }}">{{ '%+.1f'|format(stock.momentum_5d) }}%</span>
                </div>
                {% endif %}
                {% if stock.momentum_20d is not none %}
                <div class="metric-chip" style="min-width:80px">
                    <span class="metric-chip-label">20日动量</span>
                    <span class="metric-chip-val" style="color:{{ '#22C55E' if stock.momentum_20d > 0 else '#EF4444' if stock.momentum_20d < 0 else 'var(--body-ink)' }}">{{ '%+.1f'|format(stock.momentum_20d) }}%</span>
                </div>
                {% endif %}
                {% if stock.ma_alignment %}
                <div class="metric-chip" style="min-width:80px">
                    <span class="metric-chip-label">均线排列</span>
                    <span class="metric-chip-val" style="color:{{ '#22C55E' if stock.ma_alignment == 'bullish' else '#EF4444' if stock.ma_alignment == 'bearish' else 'var(--body-ink)' }}">{{ {'bullish': '多头', 'bearish': '空头', 'neutral': '交叉'}[stock.ma_alignment] }}</span>
                </div>
                {% endif %}
                {% if stock.volume_ratio is not none %}
                <div class="metric-chip" style="min-width:80px">
                    <span class="metric-chip-label">量比</span>
                    <span class="metric-chip-val">{{ stock.volume_ratio }}</span>
                </div>
                {% endif %}
                {% if stock.pe_ttm is not none %}
                <div class="metric-chip" style="min-width:80px">
                    <span class="metric-chip-label">PE(TTM)</span>
                    <span class="metric-chip-val">{{ stock.pe_ttm }}</span>
                </div>
                {% endif %}
                {% if stock.pb is not none %}
                <div class="metric-chip" style="min-width:80px">
                    <span class="metric-chip-label">PB</span>
                    <span class="metric-chip-val">{{ stock.pb }}</span>
                </div>
                {% endif %}
                {% if stock.mcap_yi is not none %}
                <div class="metric-chip" style="min-width:80px">
                    <span class="metric-chip-label">总市值</span>
                    <span class="metric-chip-val">{{ "%.0f"|format(stock.mcap_yi) }}亿</span>
                </div>
                {% endif %}
            </div>
        </div>
    </div>

    <!-- LLM Analysis dimensions -->
    <div class="detail-section" style="margin-bottom:16px">
        <div class="detail-section-title">🤖 LLM 分析维度</div>
        <table class="dim-table">
            {% for dim_name, dim in [('技术面', stock.technical), ('基本面', stock.fundamental), ('资金面', stock.capital), ('公告', stock.announcement)] %}
            {% if dim.status != 'unavailable' or dim_name in ['技术面', '资金面'] %}
            <tr>
                <td class="dim-name" style="width:56px">{{ dim_name }}</td>
                <td class="dim-status" style="width:28px">{% if dim.status == 'ok' %}✅{% elif dim.status == 'unavailable' %}⏸{% else %}❌{% endif %}</td>
                <td class="dim-summary">{{ dim.summary }}</td>
            </tr>
            {% endif %}
            {% endfor %}
        </table>
    </div>

    <!-- Dragon tiger -->
    {% if stock.dragon_tiger %}
    <div class="detail-section" style="margin-bottom:16px">
        <div class="detail-section-title">🐉 龙虎榜</div>
        {% for dt in stock.dragon_tiger %}
        <div class="dt-row" style="margin-bottom:6px">
            <span class="dt-reason">{{ dt.reason }}</span>
            <span class="dt-net" style="color:{{ '#22C55E' if dt.net_buy > 0 else '#EF4444' }}">
                {{ '%+.0f'|format(dt.net_buy) if dt.net_buy | abs >= 10000 else '%+.2f万'|format(dt.net_buy / 10000) }}
            </span>
        </div>
        {% endfor %}
    </div>
    {% endif %}

    <!-- Announcement events -->
    {% if stock.announcement.key_events %}
    <div class="detail-section" style="margin-bottom:16px">
        <div class="detail-section-title">📢 公告关键事件</div>
        {% for evt in stock.announcement.key_events[:5] %}
        <div class="ann-event" style="margin-bottom:6px">
            <span style="color:{{ '#22C55E' if evt.impact == 'positive' else '#EF4444' if evt.impact == 'negative' else 'var(--muted-soft)' }}">
                {{ '🟢' if evt.impact == 'positive' else '🔴' if evt.impact == 'negative' else '⚪' }}
            </span>
            <span class="ann-text">{{ evt.event }}</span>
            {% if evt.confidence %}
            <span class="ann-conf">{{ (evt.confidence * 100)|round(0) }}%</span>
            {% endif %}
        </div>
        {% endfor %}
    </div>
    {% endif %}

    <!-- Risk points -->
    {% if stock.risk_points %}
    <div class="risk-block" style="margin-bottom:16px">
        <strong>⚠ 风险提示：</strong>{{ stock.risk_points | join('、') }}
    </div>
    {% endif %}

    <div class="disclaimer">{{ disclaimer }}</div>

    <footer class="site-footer">
        Stock Copilot v1.3 · AI 辅助决策 · 不构成投资建议
    </footer>
</div>
</body>
</html>
"""


# ── Template: History Page ────────────────────────────────────
TPL_HISTORY = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
    <title>历史信号 — Stock Copilot</title>
    <link rel="stylesheet" href="assets/theme.css">
</head>
<body>

<header class="site-header">
    <div class="brand">
        <div class="brand-icon">📊</div>
        <span class="brand-name">Stock Copilot</span>
    </div>
    """ + NAV_HTML.replace("page == 'history'", "True") + """
    <span class="header-meta">历史信号</span>
</header>

<div class="shell-wide">

    <a href="index.html" class="back-link">← 返回首页</a>

    <div class="page-title">📈 历史信号回顾</div>
    <div class="page-subtitle">所有自选股的历史信号记录，按时间倒序</div>

    {% if not history %}
    <div class="empty-state">
        <div class="empty-state-icon">📭</div>
        <div class="empty-state-text">暂无历史信号数据</div>
        <div class="empty-state-sub">需要多个交易日积累数据</div>
    </div>
    {% endif %}

    {% for code, data in history.items() %}
    <div style="margin-bottom:32px">
        <div class="section-title">
            <a href="stock/{{ code }}.html" style="text-decoration:none;color:inherit">
                {{ code }} {{ data.name }}
            </a>
            <span class="count">({{ data.records|length }} 条记录)</span>
        </div>

        <!-- Stats summary -->
        <div class="stats-grid" style="margin-bottom:16px">
            <div class="stat-card">
                <div class="stat-value" style="color:{{ '#22C55E' if data.stats.avg_score > 0 else '#EF4444' if data.stats.avg_score < 0 else 'var(--neutral)' }}">
                    {{ '%+.2f'|format(data.stats.avg_score) }}
                </div>
                <div class="stat-label">平均评分</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" style="color:var(--bullish)">{{ data.stats.bullish_count }}</div>
                <div class="stat-label">看多次数</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" style="color:var(--bearish)">{{ data.stats.bearish_count }}</div>
                <div class="stat-label">看空次数</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{{ data.stats.hold_count }}</div>
                <div class="stat-label">观望次数</div>
            </div>
        </div>

        <table class="history-table">
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
                    <td style="color:var(--muted)">{{ '盘前' if r.report_type == 'pre' else '盘后' }}</td>
                    <td style="color:{{ '#22C55E' if r.hard_score > 0 else '#EF4444' if r.hard_score < 0 else 'var(--muted)' }}">
                        {{ '%+.3f'|format(r.hard_score) }}
                    </td>
                    <td style="color:{{ '#22C55E' if r.soft_score > 0 else '#EF4444' if r.soft_score < 0 else 'var(--muted)' }}">
                        {{ '%+.3f'|format(r.soft_score) }}
                    </td>
                    <td>{{ '%+.3f'|format(r.gate_score) }}</td>
                    <td style="color:{{ '#22C55E' if r.final_score > 0.2 else '#EF4444' if r.final_score < -0.2 else 'var(--muted)' }}">
                        {{ '%+.3f'|format(r.final_score) }}
                    </td>
                    <td>
                        {% if r.final_signal in ['strong_buy', 'buy', 'bullish'] %}
                        <span style="color:var(--bullish)">🟢 看多</span>
                        {% elif r.final_signal in ['sell', 'strong_sell'] %}
                        <span style="color:var(--bearish)">🔴 看空</span>
                        {% else %}
                        <span style="color:var(--neutral)">⚪ 观望</span>
                        {% endif %}
                    </td>
                    <td>{{ (r.confidence * 100)|round(0) }}%</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
    {% endfor %}

    <div class="disclaimer">{{ disclaimer }}</div>

    <footer class="site-footer">
        Stock Copilot v1.3 · AI 辅助决策 · 不构成投资建议
    </footer>
</div>
</body>
</html>
"""


# ── Template: Dashboard Page ──────────────────────────────────
TPL_DASHBOARD = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
    <title>数据看板 — Stock Copilot</title>
    <link rel="stylesheet" href="assets/theme.css">
</head>
<body>

<header class="site-header">
    <div class="brand">
        <div class="brand-icon">📊</div>
        <span class="brand-name">Stock Copilot</span>
    </div>
    """ + NAV_HTML.replace("page == 'dashboard'", "True") + """
    <span class="header-meta">{{ meta.trade_date }} {{ type_label }}</span>
</header>

<div class="shell-wide">

    <a href="index.html" class="back-link">← 返回首页</a>

    <div class="page-title">📋 数据看板</div>
    <div class="page-subtitle">自选股横向对比 + 信号分布一览</div>

    {% if market and market.close %}
    <div class="market-temp" style="margin-bottom:24px">
        <div class="market-temp-head">
            <span class="market-temp-label">市场温度</span>
            <div>
                <span class="market-temp-index">{{ market.index_name }} {{ "%.2f"|format(market.close) }}</span>
                {% if market.change_pct >= 0 %}
                <span class="market-temp-change up">&nbsp;+{{ "%.2f"|format(market.change_pct) }}%</span>
                {% else %}
                <span class="market-temp-change down">&nbsp;{{ "%.2f"|format(market.change_pct) }}%</span>
                {% endif %}
            </div>
        </div>
        <div class="signal-distribution">
            <span class="sig-stat"><span class="sig-dot green"></span> 看多 {{ bullish_count }}</span>
            <span class="sig-stat"><span class="sig-dot gray"></span> 观望 {{ hold_count }}</span>
            <span class="sig-stat"><span class="sig-dot red"></span> 看空 {{ bearish_count }}</span>
        </div>
    </div>
    {% endif %}

    <!-- Comparison table -->
    <div class="detail-section" style="margin-bottom:24px">
        <div class="detail-section-title">自选股对比</div>
        <div style="overflow-x:auto">
        <table class="comp-table">
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
                {% set pill_class = 'strong-buy' if stock.overall_sentiment == 'strong_buy'
                    else 'buy' if stock.overall_sentiment in ['buy', 'bullish']
                    else 'strong-sell' if stock.overall_sentiment == 'strong_sell'
                    else 'sell' if stock.overall_sentiment == 'sell'
                    else 'hold' %}
                <tr>
                    <td class="stock-cell">
                        <a href="stock/{{ stock.code }}.html" style="text-decoration:none;color:inherit">
                            {{ stock.code }}<br>
                            <span style="font-size:11px;color:var(--muted);font-weight:400">{{ stock.name }}</span>
                        </a>
                    </td>
                    <td><span class="signal-pill {{ pill_class }}">{{ stock.overall_focus }}</span></td>
                    <td style="color:{{ '#22C55E' if stock.signal_breakdown.final_score > 0.2 else '#EF4444' if stock.signal_breakdown.final_score < -0.2 else 'var(--muted)' }}">
                        {{ '%+.3f'|format(stock.signal_breakdown.final_score) }}
                    </td>
                    <td style="color:{{ '#22C55E' if (stock.momentum_5d or 0) > 0 else '#EF4444' if (stock.momentum_5d or 0) < 0 else 'var(--muted)' }}">
                        {{ '%+.1f'|format(stock.momentum_5d) if stock.momentum_5d is not none else '-' }}%
                    </td>
                    <td>{{ {'bullish': '多头', 'bearish': '空头', 'neutral': '交叉'}.get(stock.ma_alignment, '-') }}</td>
                    <td>{{ stock.volume_ratio if stock.volume_ratio is not none else '-' }}</td>
                    <td>{{ stock.pe_ttm if stock.pe_ttm is not none else '-' }}</td>
                    <td>{{ (stock.confidence * 100)|round(0) }}%</td>
                    <td>{% if stock.signal_breakdown.has_dragon_tiger %}<span style="color:var(--accent-purple)">✅</span>{% else %}⏸{% endif %}</td>
                    <td>{% if stock.signal_breakdown.has_announcement %}<span style="color:var(--accent-warm)">✅</span>{% else %}⏸{% endif %}</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
        </div>
    </div>

    <!-- 5-layer signal breakdown for each stock -->
    <div class="section-title">5层信号分解</div>
    <div style="overflow-x:auto;margin-bottom:24px">
    <table class="comp-table">
        <thead>
            <tr>
                <th>股票</th>
                <th>硬信号 40%</th>
                <th>软信号 25%</th>
                <th>门控 15%</th>
                <th>龙虎 10%</th>
                <th>公告 10%</th>
                <th>最终评分</th>
            </tr>
        </thead>
        <tbody>
            {% for stock in stocks %}
            <tr>
                <td class="stock-cell">
                    <a href="stock/{{ stock.code }}.html" style="text-decoration:none;color:inherit">
                        {{ stock.code }} {{ stock.name }}
                    </a>
                </td>
                <td style="color:{{ '#22C55E' if stock.signal_breakdown.hard_score > 0 else '#EF4444' if stock.signal_breakdown.hard_score < 0 else 'var(--muted)' }}">
                    {{ '%+.3f'|format(stock.signal_breakdown.hard_score) }}
                </td>
                <td style="color:{{ '#22C55E' if stock.signal_breakdown.soft_score > 0 else '#EF4444' if stock.signal_breakdown.soft_score < 0 else 'var(--muted)' }}">
                    {{ '%+.3f'|format(stock.signal_breakdown.soft_score) }}
                </td>
                <td style="color:{{ '#22C55E' if stock.signal_breakdown.gate_score > 0.5 else '#EF4444' if stock.signal_breakdown.gate_score < 0.5 else 'var(--muted)' }}">
                    {{ '%+.3f'|format(stock.signal_breakdown.gate_score) }}
                </td>
                <td>{% if stock.signal_breakdown.has_dragon_tiger %}{{ '%+.3f'|format(stock.signal_breakdown.dragon_tiger_score) }}{% else %}-{% endif %}</td>
                <td>{% if stock.signal_breakdown.has_announcement %}{{ '%+.3f'|format(stock.signal_breakdown.announcement_score) }}{% else %}-{% endif %}</td>
                <td style="font-weight:700;color:{{ '#22C55E' if stock.signal_breakdown.final_score > 0.2 else '#EF4444' if stock.signal_breakdown.final_score < -0.2 else 'var(--muted)' }}">
                    {{ '%+.3f'|format(stock.signal_breakdown.final_score) }}
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
    </div>

    <!-- Signal distribution bar -->
    {% if stocks %}
    <div class="detail-section" style="margin-bottom:24px">
        <div class="detail-section-title">信号分布</div>
        <div style="display:flex;gap:4px;height:32px;border-radius:var(--radius-sm);overflow:hidden;margin-bottom:8px">
            {% if bullish_count > 0 %}
            <div style="flex:{{ bullish_count }};background:var(--bullish);display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:600;color:#fff">
                看多 {{ bullish_count }}
            </div>
            {% endif %}
            {% if hold_count > 0 %}
            <div style="flex:{{ hold_count }};background:var(--neutral);display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:600;color:#fff">
                观望 {{ hold_count }}
            </div>
            {% endif %}
            {% if bearish_count > 0 %}
            <div style="flex:{{ bearish_count }};background:var(--bearish);display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:600;color:#fff">
                看空 {{ bearish_count }}
            </div>
            {% endif %}
        </div>
        <div style="font-size:12px;color:var(--muted)">
            共 {{ stocks|length }} 只自选股，{% if bullish_count > 0 %}{{ bullish_count }} 只看多{% endif %}{% if hold_count > 0 %}{% if bullish_count > 0 %}，{% endif %}{{ hold_count }} 只观望{% endif %}{% if bearish_count > 0 %}{% if bullish_count > 0 or hold_count > 0 %}，{% endif %}{{ bearish_count }} 只看空{% endif %}
        </div>
    </div>
    {% endif %}

    <div class="disclaimer">{{ disclaimer }}</div>

    <footer class="site-footer">
        Stock Copilot v1.3 · AI 辅助决策 · 不构成投资建议
    </footer>
</div>
</body>
</html>
"""


def generate_site(report: Report) -> str:
    """Generate multi-page static site from a Report.

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
    bullish_count = 0
    hold_count = 0
    bearish_count = 0

    for a in report.analyses:
        snap = a.snapshot
        bars = snap.bars or []
        ma = getattr(snap, 'ma', None)
        valuation = getattr(snap, 'valuation', None)
        capital = getattr(snap, 'capital', None)

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

        # Count signal distribution
        if fused.final_signal in ('strong_buy', 'buy'):
            bullish_count += 1
        elif fused.final_signal in ('sell', 'strong_sell'):
            bearish_count += 1
        else:
            hold_count += 1

        # Dragon tiger entries
        dt_entries = []
        for dt in snap.dragon_tiger[:5]:
            dt_entries.append({
                "date": dt.date,
                "reason": dt.reason,
                "net_buy": dt.net_buy,
                "buy_amount": dt.buy_amount,
                "sell_amount": dt.sell_amount,
            })

        # Announcement key events
        ann_events = []
        if a.announcement.status.value != "unavailable" and a.announcement.raw_json:
            ann_events = a.announcement.raw_json.get("key_events", [])

        stocks.append({
            "code": snap.code,
            "name": snap.name,
            "overall_sentiment": fused.final_signal,
            "overall_focus": fused.signal_label,
            "confidence": round(fused.confidence, 2),
            "hard_score": round(hard.composite_score, 2),
            "momentum_20d": round(hard.momentum_20d, 2) if hard.momentum_20d else None,
            "momentum_5d": round(hard.momentum_5d, 2) if hard.momentum_5d else None,
            "ma_alignment": hard.ma_alignment,
            "volume_ratio": round(hard.volume_ratio, 2) if hard.volume_ratio else None,
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
            "risk_points": [
                r for agent in [a.technical, a.fundamental, a.capital, a.announcement]
                for r in agent.risk_points
            ],
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
            "dragon_tiger": dt_entries,
        })

    # Sort by absolute final score (most interesting first)
    stocks.sort(key=lambda s: abs(s["signal_breakdown"]["final_score"]), reverse=True)

    # Load archive
    archive = _load_archive_entries(settings)

    # Load history from SQLite
    history = _load_history(settings)

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

    # ── Page 1: index.html ──────────────────────────────────────
    tmpl = Template(TPL_HOME)
    html = tmpl.render(
        meta=meta, type_label=type_label, market=market,
        stocks=stocks, archive=archive, disclaimer=meta["disclaimer"],
        bullish_count=bullish_count, hold_count=hold_count, bearish_count=bearish_count,
    )
    index_path = site_dir / "index.html"
    index_path.write_text(html, encoding="utf-8")

    # ── Page 2: stock/{code}.html (per stock) ───────────────────
    stock_dir = site_dir / "stock"
    stock_dir.mkdir(exist_ok=True)
    for stock in stocks:
        tmpl = Template(TPL_STOCK)
        stock_html = tmpl.render(
            stock=stock, disclaimer=meta["disclaimer"],
            meta=meta, type_label=type_label,
        )
        (stock_dir / f"{stock['code']}.html").write_text(stock_html, encoding="utf-8")

    # ── Page 3: history.html ────────────────────────────────────
    tmpl = Template(TPL_HISTORY)
    history_html = tmpl.render(
        history=history, disclaimer=meta["disclaimer"],
        meta=meta, type_label=type_label,
    )
    (site_dir / "history.html").write_text(history_html, encoding="utf-8")

    # ── Page 4: dashboard.html ──────────────────────────────────
    tmpl = Template(TPL_DASHBOARD)
    dash_html = tmpl.render(
        meta=meta, type_label=type_label, market=market,
        stocks=stocks, disclaimer=meta["disclaimer"],
        bullish_count=bullish_count, hold_count=hold_count, bearish_count=bearish_count,
    )
    (site_dir / "dashboard.html").write_text(dash_html, encoding="utf-8")

    # Archive copy of index
    archive_file = archive_dir / f"{report.trade_date}-{report.report_type.value}.html"
    archive_file.write_text(html, encoding="utf-8")

    # Sync to docs/ for GitHub Pages
    _sync_to_docs(settings)

    logger.info("Site generated: %s (%d stocks, %d pages)", index_path, len(stocks), 3 + len(stocks))
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


def _load_history(settings) -> dict:
    """Load historical signal data from SQLite."""
    import sqlite3

    db_path = Path("data") / "signals.db"
    if not db_path.exists():
        return {}

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Get all signals grouped by code
    cur.execute("""
        SELECT code, trade_date, report_type,
               hard_score, soft_score, gate_score,
               final_score, final_signal, signal_label,
               llm_confidence
        FROM signals
        ORDER BY code, trade_date
    """)
    rows = cur.fetchall()

    # Group by code
    history = {}
    for r in rows:
        code = r["code"]
        if code not in history:
            # Get stock name
            cur2 = conn.cursor()
            cur2.execute("SELECT name FROM stock_meta WHERE code = ?", (code,))
            meta_row = cur2.fetchone()
            name = meta_row["name"] if meta_row else code

            # Calculate stats
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
                "name": name,
                "records": [],
                "stats": {
                    "avg_score": stats["avg_score"] or 0,
                    "bullish_count": stats["bullish"] or 0,
                    "bearish_count": stats["bearish"] or 0,
                    "hold_count": stats["hold"] or 0,
                    "total": stats["total"] or 0,
                }
            }

        history[code]["records"].append({
            "trade_date": str(r["trade_date"]),
            "report_type": r["report_type"],
            "hard_score": r["hard_score"] or 0,
            "soft_score": r["soft_score"] or 0,
            "gate_score": r["gate_score"] or 0.5,
            "final_score": r["final_score"] or 0,
            "final_signal": r["final_signal"] or "hold",
            "signal_label": r["signal_label"] or "⚪ 观望",
            "confidence": r["llm_confidence"] or 0.5,
        })

    conn.close()
    return history


def _sync_to_docs(settings) -> None:
    """Sync site/ to repo docs/ for GitHub Pages."""
    import pathlib

    project_root = pathlib.Path(__file__).resolve().parent.parent.parent
    docs_dir = project_root / "docs"

    if not docs_dir.exists():
        docs_dir.mkdir(exist_ok=True)

    for src_dir in ["assets", "archive", "data", "stock"]:
        src = Path(settings.site.output_dir) / src_dir
        dst = docs_dir / src_dir
        if src.exists():
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)

    # Copy individual pages
    for page in ["index.html", "history.html", "dashboard.html"]:
        src = Path(settings.site.output_dir) / page
        if src.exists():
            shutil.copy2(src, docs_dir / page)

    logger.info("Site synced to docs/ for GitHub Pages")
