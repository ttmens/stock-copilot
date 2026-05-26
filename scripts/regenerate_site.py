#!/usr/bin/env python3
"""Regenerate HTML site from latest.json (no LLM calls needed)."""
import sys, json
sys.path.insert(0, '.')
from pathlib import Path
from jinja2 import Template

# Load data
data = json.loads(Path("site/data/latest.json").read_text())
stocks = data["stocks"]
meta = data["meta"]
market = data.get("market", {})

# Sort by absolute score
stocks.sort(key=lambda s: abs(s.get("signal_breakdown", {}).get("final_score", 0)), reverse=True)

bullish = sum(1 for s in stocks if s["overall_sentiment"] in ("strong_buy", "buy"))
bearish = sum(1 for s in stocks if s["overall_sentiment"] in ("strong_sell", "sell"))
hold = len(stocks) - bullish - bearish

type_label = "盘后" if meta["report_type"] == "post" else "盘前"

# Read template from generator
from src.site.generator import TPL_HOME, TPL_STOCK

# Generate index.html
tmpl = Template(TPL_HOME)
html = tmpl.render(
    meta=meta, type_label=type_label, market=market,
    stocks=stocks, archive=data.get("archive", []),
    disclaimer=meta.get("disclaimer", ""),
    bullish_count=bullish, hold_count=hold, bearish_count=bearish,
)
Path("site/index.html").write_text(html, encoding="utf-8")
Path("docs/index.html").write_text(html, encoding="utf-8")
print(f"Generated index.html with {len(stocks)} stocks")

# Generate stock pages
stock_dir = Path("site/stock")
stock_dir.mkdir(exist_ok=True)
docs_stock = Path("docs/stock")
docs_stock.mkdir(exist_ok=True)

for stock in stocks:
    tmpl = Template(TPL_STOCK)
    stock_html = tmpl.render(stock=stock, disclaimer=meta.get("disclaimer", ""),
                              meta=meta, type_label=type_label)
    (stock_dir / f'{stock["code"]}.html').write_text(stock_html, encoding="utf-8")
    (docs_stock / f'{stock["code"]}.html').write_text(stock_html, encoding="utf-8")

print(f"Generated {len(stocks)} stock pages")

# Sync dashboard/history
from src.site.generator import TPL_HISTORY, TPL_DASHBOARD, _load_archive_entries, _load_history
from src.config import get_settings
settings = get_settings()

try:
    archive = _load_archive_entries(settings)
    history = _load_history(settings)
except:
    archive = data.get("archive", [])
    history = []

tmpl = Template(TPL_HISTORY)
hist_html = tmpl.render(history=history, disclaimer=meta.get("disclaimer", ""),
                        meta=meta, type_label=type_label)
Path("site/history.html").write_text(hist_html, encoding="utf-8")
Path("docs/history.html").write_text(hist_html, encoding="utf-8")
print("Generated history.html")

# Copy assets
import shutil
assets_src = Path("site/assets")
if assets_src.exists():
    for src_dir in ["assets", "archive", "data", "stock"]:
        src = Path("site") / src_dir
        dst = Path("docs") / src_dir
        if src.exists():
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
    for page in ["index.html", "history.html", "dashboard.html"]:
        src = Path("site") / page
        if src.exists():
            shutil.copy2(src, Path("docs") / page)
    print("Synced site/ to docs/")

print(f"Done — full site regenerated with {len(stocks)} stocks")
