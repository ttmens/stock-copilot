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
from src.data.models import Report

logger = logging.getLogger(__name__)

# ── CSS: loaded from theme.css ────────────────────────────────
_THEME_CSS_PATH = Path(__file__).parent / "theme.css"
THEME_CSS = _THEME_CSS_PATH.read_text(encoding="utf-8")

# ── Shared header brand SVG ───────────────────────────────────
BRAND_SVG = """<svg viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg" style="width:32px;height:32px">
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
    <a href="index.html"{% if page == 'home' %} class="active"{% endif %}>首页</a>
    <a href="dashboard.html"{% if page == 'dashboard' %} class="active"{% endif %}>看板</a>
    <a href="history.html"{% if page == 'history' %} class="active"{% endif %}>历史</a>
</div>
"""
NAV_HTML_SUB = """
<div class="site-nav">
    <a href="../index.html"{% if page == 'home' %} class="active"{% endif %}>首页</a>
    <a href="../dashboard.html"{% if page == 'dashboard' %} class="active"{% endif %}>看板</a>
    <a href="../history.html"{% if page == 'history' %} class="active"{% endif %}>历史</a>
</div>
"""

# ── Bottom Nav (mobile) ───────────────────────────────────────
BOTTOM_NAV = """
<nav class="bottom-nav">
    <div class="bottom-nav-inner">
        <a href="index.html"{% if page == 'home' %} class="active"{% endif %}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>
            首页
        </a>
        <a href="dashboard.html"{% if page == 'dashboard' %} class="active"{% endif %}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>
            看板
        </a>
        <a href="app/watchlist.html"{% if page == 'watchlist' %} class="active"{% endif %}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/></svg>
            自选
        </a>
        <a href="history.html"{% if page == 'history' %} class="active"{% endif %}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
            历史
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
    <title>智策 NexStrat — {{ meta.trade_date }} {{ type_label }}</title>
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
    <span class="header-meta">{{ meta.trade_date }} {{ type_label }} · {{ meta.generated_at[11:16] }}</span>
</header>

<div class="shell">

{# ── Signal Dashboard (Market Temperature) ── #}
{% if market and market.close %}
<div class="signal-dashboard">
    <div class="signal-dashboard-head">
        <div>
            <span class="signal-dashboard-label">市场温度</span>
            <span class="signal-dashboard-value" style="margin-left:8px">{{ market.index_name }} {{ "%.2f"|format(market.close) }}</span>
            {% if market.change_pct >= 0 %}
            <span class="signal-dashboard-change change-up">+{{ "%.2f"|format(market.change_pct) }}%</span>
            {% else %}
            <span class="signal-dashboard-change change-down">{{ "%.2f"|format(market.change_pct) }}%</span>
            {% endif %}
        </div>
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
<a href="{% if use_app_pages %}app/stock.html?code={{ stock.code }}{% else %}stock/{{ stock.code }}.html{% endif %}" class="stock-card-link" data-code="{{ stock.code }}" data-name="{{ stock.name }}" data-signal="{{ stock.overall_sentiment }}" data-score="{{ stock.signal_breakdown.final_score }}" data-confidence="{{ stock.confidence }}">
<div class="stock-card">
    {# Card Header #}
    <div class="card-header">
        <div>
            <div class="card-stock-code">{{ stock.code }}</div>
            <div class="card-stock-name">{{ stock.name }}</div>
        </div>
        {% set s = stock.overall_sentiment %}
        {% set badge_cls = 'bullish' if s in ['strong_buy','buy','bullish'] else 'bearish' if s in ['sell','strong_sell'] else 'hold' %}
        <span class="signal-badge {{ badge_cls }}">{{ stock.overall_focus }}</span>
    </div>

    {# L1 Decision Card — Seeking Alpha style #}
    <div class="decision-card">
        <div class="decision-score-row">
            <span class="decision-score-label">综合评分</span>
            <span class="decision-score-value" style="color:{{ '#22C55E' if stock.signal_breakdown.final_score > 0.2 else '#EF4444' if stock.signal_breakdown.final_score < -0.2 else '#94A3B8' }}">
                {{ '%+.3f'|format(stock.signal_breakdown.final_score) }}
            </span>
        </div>
        <div class="decision-bar-track">
            <div class="decision-bar-fill" style="width:{{ ((stock.signal_breakdown.final_score + 1) / 2 * 100)|round(1) }}%; background:{{ '#22C55E' if stock.signal_breakdown.final_score > 0.2 else '#EF4444' if stock.signal_breakdown.final_score < -0.2 else '#94A3B8' }}"></div>
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

    {# Metrics Chips #}
    <div class="metrics-row">
        {% if stock.momentum_5d is not none %}
        <div class="metric-chip" style="{{ 'border-color:rgba(34,197,94,0.3)' if stock.momentum_5d > 0 else 'border-color:rgba(239,68,68,0.3)' if stock.momentum_5d < 0 else '' }}">
            <span class="metric-chip-label">5日</span>
            <span class="metric-chip-val" style="color:{{ '#22C55E' if stock.momentum_5d > 0 else '#EF4444' if stock.momentum_5d < 0 else 'var(--text-secondary)' }}">{{ '%+.1f'|format(stock.momentum_5d) }}%</span>
        </div>
        {% endif %}
        {% if stock.ma_alignment %}
        <div class="metric-chip" style="{{ 'border-color:rgba(34,197,94,0.3)' if stock.ma_alignment == 'bullish' else 'border-color:rgba(239,68,68,0.3)' if stock.ma_alignment == 'bearish' else '' }}">
            <span class="metric-chip-label">均线</span>
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
    </div>

    {# Risk #}
    {% if stock.risk_points %}
    <div class="risk-block">⚠ {{ stock.risk_points[:1] | join('') }}</div>
    {% endif %}
</div>
</a>
{% endfor %}
</div>

{# ── Archive ── #}
{% if archive %}
<div class="archive-section">
    <div style="font-size:13px;font-weight:600;color:var(--text-primary);margin-bottom:4px;">📁 历史报告</div>
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
    {{ stock.code }} <span style="font-weight:400;color:var(--text-muted)">{{ stock.name }}</span>
</div>

{% set s = stock.overall_sentiment %}
{% set badge_cls = 'bullish' if s in ['strong_buy','buy','bullish'] else 'bearish' if s in ['sell','strong_sell'] else 'hold' %}
<div style="margin-bottom:20px">
    <span class="signal-badge {{ badge_cls }}" style="font-size:13px;padding:6px 14px">{{ stock.overall_focus }}</span>
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
        <div class="dim-grid" style="margin-top:16px">
            <div class="dim-card">
                <span class="dim-card-label"><span class="dim-card-dot" style="background:var(--dim-hard)"></span>硬信号 40%</span>
                <span class="dim-card-value" style="color:{{ '#22C55E' if stock.signal_breakdown.hard_score > 0 else '#EF4444' if stock.signal_breakdown.hard_score < 0 else 'var(--text-muted)' }}">{{ '%+.3f'|format(stock.signal_breakdown.hard_score) }}</span>
            </div>
            <div class="dim-card">
                <span class="dim-card-label"><span class="dim-card-dot" style="background:var(--dim-soft)"></span>软信号 25%</span>
                <span class="dim-card-value" style="color:{{ '#22C55E' if stock.signal_breakdown.soft_score > 0 else '#EF4444' if stock.signal_breakdown.soft_score < 0 else 'var(--text-muted)' }}">{{ '%+.3f'|format(stock.signal_breakdown.soft_score) }}</span>
            </div>
            <div class="dim-card">
                <span class="dim-card-label"><span class="dim-card-dot" style="background:var(--dim-gate)"></span>门控 15%</span>
                <span class="dim-card-value" style="color:{{ '#22C55E' if stock.signal_breakdown.gate_score > 0.5 else '#EF4444' if stock.signal_breakdown.gate_score < 0.5 else 'var(--text-muted)' }}">{{ '%+.3f'|format(stock.signal_breakdown.gate_score) }}</span>
            </div>
            {% if stock.signal_breakdown.has_dragon_tiger %}
            <div class="dim-card">
                <span class="dim-card-label"><span class="dim-card-dot" style="background:var(--dim-dragon)"></span>龙虎 10%</span>
                <span class="dim-card-value" style="color:{{ '#22C55E' if stock.signal_breakdown.dragon_tiger_score > 0 else '#EF4444' if stock.signal_breakdown.dragon_tiger_score < 0 else 'var(--text-muted)' }}">{{ '%+.3f'|format(stock.signal_breakdown.dragon_tiger_score) }}</span>
            </div>
            {% endif %}
            {% if stock.signal_breakdown.has_announcement %}
            <div class="dim-card">
                <span class="dim-card-label"><span class="dim-card-dot" style="background:var(--dim-announce)"></span>公告 10%</span>
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
            <div class="metric-chip" style="min-width:80px">
                <span class="metric-chip-label">5日动量</span>
                <span class="metric-chip-val" style="color:{{ '#22C55E' if stock.momentum_5d > 0 else '#EF4444' if stock.momentum_5d < 0 else 'var(--text-secondary)' }}">{{ '%+.1f'|format(stock.momentum_5d) }}%</span>
            </div>
            {% endif %}
            {% if stock.momentum_20d is not none %}
            <div class="metric-chip" style="min-width:80px">
                <span class="metric-chip-label">20日动量</span>
                <span class="metric-chip-val" style="color:{{ '#22C55E' if stock.momentum_20d > 0 else '#EF4444' if stock.momentum_20d < 0 else 'var(--text-secondary)' }}">{{ '%+.1f'|format(stock.momentum_20d) }}%</span>
            </div>
            {% endif %}
            {% if stock.ma_alignment %}
            <div class="metric-chip" style="min-width:80px">
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
            <div class="metric-chip" style="min-width:80px">
                <span class="metric-chip-label">总市值</span>
                <span class="metric-chip-val">{{ "%.0f"|format(stock.mcap_yi) }}亿</span>
            </div>
            {% endif %}
        </div>
    </div>
</div>

{# ── L2: LLM Analysis Dimensions ── #}
<div class="detail-section" style="margin-bottom:16px">
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

{# ── L3: Dragon Tiger Evidence ── #}
{% if stock.dragon_tiger %}
<div class="detail-section" style="margin-bottom:16px">
    <div class="detail-section-title">🐉 龙虎榜</div>
    {% for dt in stock.dragon_tiger %}
    <div class="dt-block">
        <div class="dt-title">{{ dt.reason }}</div>
        <div class="dt-row">
            <span style="color:var(--text-muted)">净额</span>
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
<div class="detail-section" style="margin-bottom:16px">
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
<div class="risk-block" style="margin-bottom:16px">⚠ 风险提示：{{ stock.risk_points | join('、') }}</div>
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

{% for code, data in history.items() %}
<div style="margin-bottom:32px">
    <div class="section-title">
        <a href="{% if use_app_pages %}app/stock.html?code={{ code }}{% else %}stock/{{ code }}.html{% endif %}" style="text-decoration:none;color:inherit">
            {{ code }} {{ data.name }}
        </a>
        <span class="count">({{ data.records|length }} 条)</span>
    </div>

    {# Stats Cards #}
    <div class="stats-grid" style="margin-bottom:16px">
        <div class="stat-card">
            <div class="stat-value" style="color:{{ '#22C55E' if data.stats.avg_score > 0 else '#EF4444' if data.stats.avg_score < 0 else 'var(--signal-hold)' }}">
                {{ '%+.2f'|format(data.stats.avg_score) }}
            </div>
            <div class="stat-label">平均评分</div>
        </div>
        <div class="stat-card">
            <div class="stat-value" style="color:var(--signal-bull)">{{ data.stats.bullish_count }}</div>
            <div class="stat-label">看多</div>
        </div>
        <div class="stat-card">
            <div class="stat-value" style="color:var(--signal-bear)">{{ data.stats.bearish_count }}</div>
            <div class="stat-label">看空</div>
        </div>
        <div class="stat-card">
            <div class="stat-value" style="color:var(--signal-hold)">{{ data.stats.hold_count }}</div>
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
                <td style="color:var(--text-muted)">{{ '盘前' if r.report_type == 'pre' else '盘后' }}</td>
                <td style="color:{{ '#22C55E' if r.hard_score > 0 else '#EF4444' if r.hard_score < 0 else 'var(--text-muted)' }}">{{ '%+.3f'|format(r.hard_score) }}</td>
                <td style="color:{{ '#22C55E' if r.soft_score > 0 else '#EF4444' if r.soft_score < 0 else 'var(--text-muted)' }}">{{ '%+.3f'|format(r.soft_score) }}</td>
                <td>{{ '%+.3f'|format(r.gate_score) }}</td>
                <td style="font-weight:700;color:{{ '#22C55E' if r.final_score > 0.2 else '#EF4444' if r.final_score < -0.2 else 'var(--text-muted)' }}">{{ '%+.3f'|format(r.final_score) }}</td>
                <td>
                    {% if r.final_signal in ['strong_buy', 'buy', 'bullish'] %}
                    <span style="color:var(--signal-bull)">🟢 看多</span>
                    {% elif r.final_signal in ['sell', 'strong_sell'] %}
                    <span style="color:var(--signal-bear)">🔴 看空</span>
                    {% else %}
                    <span style="color:var(--signal-hold)">⚪ 观望</span>
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
<div class="signal-dashboard" style="margin-bottom:24px">
    <div class="signal-dashboard-head">
        <div>
            <span class="signal-dashboard-label">市场温度</span>
            <span class="signal-dashboard-value" style="margin-left:8px">{{ market.index_name }} {{ "%.2f"|format(market.close) }}</span>
            {% if market.change_pct >= 0 %}
            <span class="signal-dashboard-change change-up">+{{ "%.2f"|format(market.change_pct) }}%</span>
            {% else %}
            <span class="signal-dashboard-change change-down">{{ "%.2f"|format(market.change_pct) }}%</span>
            {% endif %}
        </div>
    </div>
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

{# ── Comparison Matrix ── #}
<div class="detail-section" style="margin-bottom:24px">
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
                    <a href="{% if use_app_pages %}app/stock.html?code={{ stock.code }}{% else %}stock/{{ stock.code }}.html{% endif %}" style="text-decoration:none;color:inherit">
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
                <td>{% if stock.signal_breakdown.has_dragon_tiger %}<span style="color:var(--dim-dragon)">●</span>{% else %}<span style="color:var(--text-faint)">—</span>{% endif %}</td>
                <td>{% if stock.signal_breakdown.has_announcement %}<span style="color:var(--dim-announce)">●</span>{% else %}<span style="color:var(--text-faint)">—</span>{% endif %}</td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
    </div>
</div>

{# ── 5-Layer Signal Breakdown ── #}
<div class="detail-section" style="margin-bottom:24px">
    <div class="detail-section-title">5层信号分解</div>
    <div class="table-scroll">
    <table class="data-table">
        <thead>
            <tr>
                <th>股票</th>
                <th style="color:var(--dim-hard)">硬 40%</th>
                <th style="color:var(--dim-soft)">软 25%</th>
                <th style="color:var(--dim-gate)">门控 15%</th>
                <th style="color:var(--dim-dragon)">龙虎 10%</th>
                <th style="color:var(--dim-announce)">公告 10%</th>
                <th>最终评分</th>
            </tr>
        </thead>
        <tbody>
            {% for stock in stocks %}
            <tr>
                <td class="stock-cell">
                    <a href="{% if use_app_pages %}app/stock.html?code={{ stock.code }}{% else %}stock/{{ stock.code }}.html{% endif %}" style="text-decoration:none;color:inherit">
                        {{ stock.code }} {{ stock.name }}
                    </a>
                </td>
                <td style="color:{{ '#22C55E' if stock.signal_breakdown.hard_score > 0 else '#EF4444' if stock.signal_breakdown.hard_score < 0 else 'var(--text-muted)' }}">{{ '%+.3f'|format(stock.signal_breakdown.hard_score) }}</td>
                <td style="color:{{ '#22C55E' if stock.signal_breakdown.soft_score > 0 else '#EF4444' if stock.signal_breakdown.soft_score < 0 else 'var(--text-muted)' }}">{{ '%+.3f'|format(stock.signal_breakdown.soft_score) }}</td>
                <td style="color:{{ '#22C55E' if stock.signal_breakdown.gate_score > 0.5 else '#EF4444' if stock.signal_breakdown.gate_score < 0.5 else 'var(--text-muted)' }}">{{ '%+.3f'|format(stock.signal_breakdown.gate_score) }}</td>
                <td>{% if stock.signal_breakdown.has_dragon_tiger %}{{ '%+.3f'|format(stock.signal_breakdown.dragon_tiger_score) }}{% else %}<span style="color:var(--text-faint)">—</span>{% endif %}</td>
                <td>{% if stock.signal_breakdown.has_announcement %}{{ '%+.3f'|format(stock.signal_breakdown.announcement_score) }}{% else %}<span style="color:var(--text-faint)">—</span>{% endif %}</td>
                <td style="font-weight:700;color:{{ '#22C55E' if stock.signal_breakdown.final_score > 0.2 else '#EF4444' if stock.signal_breakdown.final_score < -0.2 else 'var(--text-muted)' }}">{{ '%+.3f'|format(stock.signal_breakdown.final_score) }}</td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
    </div>
</div>

{# ── Signal Distribution Bar ── #}
{% if stocks %}
<div class="detail-section" style="margin-bottom:24px">
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

        if fused.final_signal in ('strong_buy', 'buy'):
            bullish_count += 1
        elif fused.final_signal in ('sell', 'strong_sell'):
            bearish_count += 1
        else:
            hold_count += 1

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

        stocks.append({
            "code": snap.code, "name": snap.name,
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
            "technical": {"status": a.technical.status.value, "summary": a.technical.summary, "sentiment": a.technical.sentiment},
            "fundamental": {"status": a.fundamental.status.value, "summary": a.fundamental.summary, "sentiment": a.fundamental.sentiment},
            "capital": {"status": a.capital.status.value, "summary": a.capital.summary, "sentiment": a.capital.sentiment},
            "announcement": {"status": a.announcement.status.value, "summary": a.announcement.summary, "sentiment": a.announcement.sentiment, "key_events": ann_events},
            "risk_points": [r for agent in [a.technical, a.fundamental, a.capital, a.announcement] for r in agent.risk_points],
            "signal_breakdown": {
                "hard_score": round(fused.hard_score, 3), "soft_score": round(fused.soft_score, 3),
                "gate_score": round(fused.gate_score, 3), "dragon_tiger_score": round(fused.dragon_tiger_score, 3),
                "announcement_score": round(fused.announcement_score, 3), "final_score": round(fused.final_score, 3),
                "has_dragon_tiger": fused.data_available.get("dragon_tiger", False),
                "has_announcement": fused.data_available.get("announcement", False),
            },
            "dragon_tiger": dt_entries,
        })

    stocks.sort(key=lambda s: abs(s["signal_breakdown"]["final_score"]), reverse=True)

    archive = _load_archive_entries(settings)
    history = _load_history(settings)

    latest = {"meta": meta, "market": market, "stocks": stocks, "failed_symbols": report.failed_symbols, "archive": archive}
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
    )
    (site_dir / "index.html").write_text(html, encoding="utf-8")

    # Page 2: stock/{code}.html
    if not get_settings().pipeline.skip_stock_html:
        stock_dir = site_dir / "stock"
        stock_dir.mkdir(exist_ok=True)
        sub_nav = Template(NAV_HTML_SUB).render(page="stock")
        sub_bottom = Template(BOTTOM_NAV).render(page="stock").replace('index.html', '../index.html').replace('dashboard.html', '../dashboard.html').replace('app/watchlist.html', '../app/watchlist.html').replace('history.html', '../history.html')
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
        use_app_pages=use_app_pages,
        bottom_nav=Template(BOTTOM_NAV).render(page="dashboard"),
        nav=Template(NAV_HTML).render(page="dashboard"),
    )
    (site_dir / "dashboard.html").write_text(dhtml, encoding="utf-8")

    # Archive
    archive_file = archive_dir / f"{report.trade_date}-{report.report_type.value}.html"
    archive_file.write_text(html, encoding="utf-8")

    _copy_app_assets(site_dir)

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
