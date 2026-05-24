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
                {% set sent_class = 'sentiment-' + stock.overall_sentiment %}
                {% set sent_label = {'bullish': '🟢 偏多', 'bearish': '🔴 偏空', 'neutral': '⚪ 中性'}[stock.overall_sentiment] %}
                <span class="sentiment-badge {{ sent_class }}">{{ sent_label }}</span>
            </div>

            {% if stock.overall_focus %}
            <div class="stock-focus">关注: {{ stock.overall_focus }}</div>
            {% endif %}

            <table class="dimension-table">
                <thead><tr><th>维度</th><th>状态</th><th>结论</th></tr></thead>
                <tbody>
                {% for dim_name, dim in [('技术面', stock.technical), ('公告', stock.fundamental), ('资金', stock.capital)] %}
                <tr>
                    <td>{{ dim_name }}</td>
                    <td>{% if dim.status == 'ok' %}✅{% elif dim.status == 'unavailable' %}⏸️{% else %}❌{% endif %}</td>
                    <td>{{ dim.summary[:80] }}{% if dim.summary|length > 80 %}...{% endif %}</td>
                </tr>
                {% endfor %}
                </tbody>
            </table>

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
