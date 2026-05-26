"""Export static snapshot for GitHub Pages."""

from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime
from pathlib import Path

from src.config import get_settings
from src.data.models import Report

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class StaticExporter:
    """Copy site artifacts to docs/ and write publish metadata."""

    def export_from_report(self, report: Report) -> Path:
        settings = get_settings()
        site_dir = Path(settings.site.output_dir)
        docs_dir = _PROJECT_ROOT / "docs"
        docs_dir.mkdir(exist_ok=True)

        # Copy data + assets
        for sub in ("data", "assets"):
            src = site_dir / sub
            dst = docs_dir / sub
            if src.exists():
                if dst.exists():
                    shutil.rmtree(dst)
                shutil.copytree(src, dst)

        # Copy shell pages (not per-stock HTML when skip enabled)
        for name in ("index.html", "history.html", "dashboard.html", "stock.html", "app"):
            src = site_dir / name
            if src.exists():
                if src.is_dir():
                    dst = docs_dir / name
                    if dst.exists():
                        shutil.rmtree(dst)
                    shutil.copytree(src, dst)
                else:
                    shutil.copy2(src, docs_dir / name)

        if not settings.pipeline.skip_stock_html:
            stock_src = site_dir / "stock"
            if stock_src.exists():
                stock_dst = docs_dir / "stock"
                if stock_dst.exists():
                    shutil.rmtree(stock_dst)
                shutil.copytree(stock_src, stock_dst)

        meta = {
            "published_at": datetime.now().isoformat(),
            "report_type": report.report_type.value,
            "trade_date": str(report.trade_date),
            "symbol_count": len(report.analyses),
            "source": "full",
        }
        meta_dir = docs_dir / "meta"
        meta_dir.mkdir(exist_ok=True)
        (meta_dir / "published_at.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        logger.info("StaticExporter: docs updated (%d symbols)", len(report.analyses))
        return docs_dir / "data" / "latest.json"
