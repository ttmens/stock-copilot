"""FastAPI API routes."""

import asyncio
import logging
from datetime import date
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from src.data.models import ReportType
from src.config import get_settings

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Stock Copilot API",
    description="A股辅助决策系统 API",
    version="0.1.0",
)


class AnalyzeRequest(BaseModel):
    type: ReportType
    symbols: Optional[list[str]] = None


class AnalyzeResponse(BaseModel):
    status: str
    report_path: str
    symbol_count: int
    failed_symbols: list[str]


class ReportResponse(BaseModel):
    file_path: str
    markdown: str


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "version": "0.1.0"}


@app.post("/analyze", response_model=AnalyzeResponse)
async def trigger_analysis(req: AnalyzeRequest):
    """Trigger analysis pipeline (sync in MVP)."""
    from src.orchestrator.pipeline import run_analysis

    try:
        report = await run_analysis(req.type, req.symbols)
        return AnalyzeResponse(
            status="completed",
            report_path=report.file_path or "",
            symbol_count=len(report.analyses),
            failed_symbols=report.failed_symbols,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Analysis failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/reports/latest", response_model=ReportResponse)
async def get_latest_report():
    """Get latest report Markdown."""
    settings = get_settings()
    output_dir = Path(settings.report.output_dir)

    # Find most recent report
    reports = sorted(output_dir.glob("*.md"), reverse=True)
    if not reports:
        raise HTTPException(status_code=404, detail="No reports found")

    latest = reports[0]
    return ReportResponse(
        file_path=str(latest),
        markdown=latest.read_text(encoding="utf-8"),
    )


@app.get("/reports/{report_date}", response_model=ReportResponse)
async def get_report_by_date(report_date: str, type: str = "pre"):
    """Get report by date and type."""
    settings = get_settings()
    output_dir = Path(settings.report.output_dir)
    report_file = output_dir / f"{report_date}-{type}.md"

    if not report_file.exists():
        raise HTTPException(status_code=404, detail=f"Report not found: {report_file}")

    return ReportResponse(
        file_path=str(report_file),
        markdown=report_file.read_text(encoding="utf-8"),
    )


@app.get("/site/latest.json")
async def get_latest_json():
    """Get latest.json data for site rendering."""
    settings = get_settings()
    data_dir = Path(settings.site.data_dir)
    json_path = data_dir / "latest.json"

    if not json_path.exists():
        raise HTTPException(status_code=404, detail="latest.json not found")

    import json
    return json.loads(json_path.read_text(encoding="utf-8"))
