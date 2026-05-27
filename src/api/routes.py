"""FastAPI API routes — static + dynamic (Phase C)."""

import asyncio
import json
import logging
import os
from datetime import date
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.config import get_settings
from src.data.models import ReportType

logger = logging.getLogger(__name__)

settings = get_settings()

app = FastAPI(
    title="Stock Copilot API",
    description="A股个人投研助手 API",
    version="1.5.0",
)

# CORS: allow GitHub Pages, localhost, and server IP access
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.api.cors_origins + [
        "https://ttmens.github.io",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AnalyzeRequest(BaseModel):
    type: ReportType
    symbols: Optional[list[str]] = None
    publish: bool = False


class AnalyzeResponse(BaseModel):
    status: str
    report_path: str = ""
    symbol_count: int = 0
    failed_symbols: list[str] = Field(default_factory=list)
    job_id: str = ""


class JobCreateRequest(BaseModel):
    type: ReportType = ReportType.PRE
    mode: str = "full"
    symbols: Optional[list[str]] = None
    publish: bool = True


class WatchlistAdd(BaseModel):
    code: str
    name: str = ""


class ReportResponse(BaseModel):
    file_path: str
    markdown: str


@app.get("/health")
async def health_check():
    from src.data.db_manager import SignalDB
    from src.watchlist.manager import WatchlistManager
    db = SignalDB()
    pub = db.get_last_published()
    wl = WatchlistManager().list_dicts()
    # Get server IP for CORS
    import socket
    try:
        host_ip = socket.gethostbyname(socket.gethostname())
    except Exception:
        host_ip = "unknown"
    return {
        "status": "ok",
        "version": "1.5.0",
        "last_published": pub,
        "watchlist_count": len(wl),
        "api_base": f"http://{host_ip}:8000",
        "github_pages": "https://ttmens.github.io/stock-copilot/",
        "design_system": "v2.0 (Seeking Alpha + TradingView inspired)",
    }


@app.post("/analyze", response_model=AnalyzeResponse)
async def trigger_analysis(req: AnalyzeRequest):
    from src.delivery.pipeline import DeliveryPipeline

    pipe = DeliveryPipeline()
    try:
        report = await pipe.run_full(req.type, req.symbols, publish=req.publish)
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


@app.post("/api/jobs")
async def create_job(req: JobCreateRequest):
    from src.data.db_manager import SignalDB
    from src.delivery.pipeline import DeliveryPipeline

    pipe = DeliveryPipeline()
    job_id = pipe.new_job_id()
    db = SignalDB()
    db.create_job(job_id, req.mode, req.type.value)

    async def _run():
        try:
            if req.mode == "fast":
                await pipe.run_fast(job_id)
            else:
                await pipe.run_full(req.type, req.symbols, req.publish, job_id)
        except Exception as e:
            logger.error("Job %s failed: %s", job_id, e)

    asyncio.create_task(_run())
    return {"job_id": job_id, "status": "pending"}


@app.get("/api/jobs/latest")
async def latest_job():
    from src.data.db_manager import SignalDB
    job = SignalDB().get_latest_job()
    if not job:
        return {"status": "none"}
    return job


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    from src.data.db_manager import SignalDB
    job = SignalDB().get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/api/watchlist")
async def list_watchlist():
    from src.watchlist.manager import WatchlistManager
    return {"stocks": WatchlistManager().list_dicts()}


@app.post("/api/watchlist")
async def add_watchlist(body: WatchlistAdd):
    from src.watchlist.manager import WatchlistManager
    item = WatchlistManager().add(body.code.strip(), body.name.strip())
    return item


@app.delete("/api/watchlist/{code}")
async def remove_watchlist(code: str):
    from src.watchlist.manager import WatchlistManager
    if not WatchlistManager().remove(code):
        raise HTTPException(status_code=404, detail="Not in watchlist")
    return {"removed": code}


@app.patch("/api/watchlist/{code}")
async def patch_watchlist(code: str, pinned: bool | None = None, name: str | None = None):
    from src.watchlist.manager import WatchlistManager
    WatchlistManager().update(code, pinned=pinned, name=name)
    return {"code": code, "pinned": pinned, "name": name}


@app.post("/api/watchlist/import-default")
async def import_default_watchlist():
    from src.watchlist.manager import WatchlistManager
    n = WatchlistManager().import_default_template()
    return {"imported": n}


@app.get("/api/quotes/intraday")
async def intraday_quotes(trade_date: str | None = None):
    from src.data.db_manager import SignalDB
    td = date.fromisoformat(trade_date) if trade_date else date.today()
    return {"quotes": SignalDB().get_intraday_quotes(td)}


@app.get("/api/evolution/suggestions")
async def evolution_suggestions(status: str = "pending"):
    from src.data.db_manager import SignalDB
    return {"suggestions": SignalDB().list_evolution_suggestions(status)}


@app.post("/api/evolution/suggestions/{suggestion_id}/accept")
async def accept_suggestion(suggestion_id: int, accept: bool = True):
    from src.data.db_manager import SignalDB
    from src.watchlist.manager import WatchlistManager

    db = SignalDB()
    rows = db.list_evolution_suggestions("pending")
    row = next((r for r in rows if r["id"] == suggestion_id), None)
    if not row:
        raise HTTPException(status_code=404, detail="Suggestion not found")
    db.resolve_evolution_suggestion(suggestion_id, accept)
    if accept:
        wl = WatchlistManager()
        if row["action"] == "add":
            wl.add(row["code"], row.get("name", row["code"]))
        elif row["action"] == "evict":
            wl.remove(row["code"])
    return {"id": suggestion_id, "accepted": accept}


@app.get("/api/published")
async def last_published():
    from src.data.db_manager import SignalDB
    pub = SignalDB().get_last_published()
    meta_path = Path("docs/meta/published_at.json")
    file_meta = {}
    if meta_path.exists():
        file_meta = json.loads(meta_path.read_text(encoding="utf-8"))
    return {"db": pub, "file": file_meta}


@app.get("/reports/latest", response_model=ReportResponse)
async def get_latest_report():
    output_dir = Path(get_settings().report.output_dir)
    reports = sorted(output_dir.glob("*.md"), reverse=True)
    if not reports:
        raise HTTPException(status_code=404, detail="No reports found")
    latest = reports[0]
    return ReportResponse(file_path=str(latest), markdown=latest.read_text(encoding="utf-8"))


@app.get("/reports/{report_date}", response_model=ReportResponse)
async def get_report_by_date(report_date: str, type: str = "pre"):
    output_dir = Path(get_settings().report.output_dir)
    report_file = output_dir / f"{report_date}-{type}.md"
    if not report_file.exists():
        raise HTTPException(status_code=404, detail=f"Report not found: {report_file}")
    return ReportResponse(file_path=str(report_file), markdown=report_file.read_text(encoding="utf-8"))


@app.get("/site/latest.json")
async def get_latest_json():
    data_dir = Path(get_settings().site.data_dir)
    json_path = data_dir / "latest.json"
    if not json_path.exists():
        docs_path = Path("docs/data/latest.json")
        if docs_path.exists():
            json_path = docs_path
        else:
            raise HTTPException(status_code=404, detail="latest.json not found")
    return json.loads(json_path.read_text(encoding="utf-8"))


# ── Static files (MUST be after all API routes) ──────────────
docs_path = Path("docs")
if docs_path.exists():
    app.mount("/site", StaticFiles(directory=str(docs_path)), name="site")
    app.mount("/", StaticFiles(directory=str(docs_path), html=True), name="docs")
