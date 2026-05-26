#!/usr/bin/env python3
"""Restore latest.json and full site from DB data."""
import sys
sys.path.insert(0, '.')
import json
import sqlite3
from pathlib import Path

db = sqlite3.connect('data/signals.db')
db.row_factory = sqlite3.Row
signals = db.execute("""
    SELECT s.*, m.name, m.industry 
    FROM signals s 
    LEFT JOIN stock_meta m ON s.code = m.code 
    WHERE s.trade_date = '2026-05-26' AND s.report_type = 'post'
    ORDER BY s.final_score DESC
""").fetchall()
print(f"Found {len(signals)} signals in DB")

stocks = []
for row in signals:
    d = dict(row)
    signal = d.get('final_signal', 'hold')
    stocks.append({
        "code": d["code"], "name": d.get("name", d["code"]),
        "overall_sentiment": signal, "overall_focus": d.get("signal_label", ""),
        "technical": {"status": "ok", "summary": "", "sentiment": d.get("llm_sentiment", "neutral")},
        "fundamental": {"status": "ok", "summary": "", "sentiment": "neutral"},
        "capital": {"status": "ok", "summary": "", "sentiment": "neutral"},
        "signal_breakdown": {
            "hard_score": d.get("hard_score", 0), "soft_score": d.get("soft_score", 0),
            "gate_score": d.get("gate_score", 0), "final_score": d.get("final_score", 0),
            "final_signal": signal,
        },
        "momentum_5d": d.get("momentum_5d", 0), "momentum_20d": d.get("momentum_20d", 0),
        "ma_alignment": d.get("ma_alignment", ""), "volume_ratio": d.get("volume_ratio", 0),
        "pe_ttm": d.get("pe_percentile", 0), "pe_percentile": d.get("pe_percentile", 0),
        "pb": 0, "mcap_yi": 0,
        "announcement": [], "dragon_tiger": [],
        "confidence": 0.5, "risk_points": [],
    })

latest = {
    "meta": {"report_type": "post", "trade_date": "2026-05-26", "generated_at": "2026-05-26T16:30:00",
             "symbol_count": len(stocks), "disclaimer": "⚠️ 本报告仅供个人研究参考，不构成投资建议。"},
    "market": {"index_name": "上证指数", "close": 3200, "change_pct": 1.5},
    "stocks": stocks, "failed_symbols": [], "archive": [],
}

# Write to both locations
for data_dir in ["site/data", "docs/data"]:
    Path(data_dir).mkdir(parents=True, exist_ok=True)
    (Path(data_dir) / "latest.json").write_text(json.dumps(latest, ensure_ascii=False, indent=2))
    print(f"Wrote {data_dir}/latest.json with {len(stocks)} stocks")

# Build archive
archive_dir = Path("site/archive")
if archive_dir.exists():
    archive = []
    for f in sorted(archive_dir.glob("*.html"), reverse=True)[:20]:
        parts = f.stem.rsplit("-", 1)
        if len(parts) == 2:
            archive.append({"date": parts[0], "type": parts[1], "url": f"archive/{f.stem}.html"})
    latest["archive"] = archive
    for data_dir in ["site/data", "docs/data"]:
        (Path(data_dir) / "latest.json").write_text(json.dumps(latest, ensure_ascii=False, indent=2))

db.close()
print("Done — site data restored")
