"""FastAPI API routes — modular architecture with domain routers.

Main app setup + core routes (health, analyze, jobs, reports, system, config).
Domain-specific routes are in src/api/routers/.
"""

import asyncio
import json
import logging
import os
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.config import get_settings
from src.data.models import ReportType
from src.api.routers.helpers import get_db_stats, safe_parse_date
from src.api.routers.watchlist import router as watchlist_router
from src.api.routers.portfolio import router as portfolio_router
from src.api.routers.market import router as market_router
from src.api.routers.evolution import router as evolution_router
from src.api.routers.intelligence import router as intelligence_router

logger = logging.getLogger(__name__)

settings = get_settings()

app = FastAPI(
    title="智策 NexStrat API",
    description="A股AI智能投研助手 — 5层信号融合 + LLM分析",
    version="3.0.0-alpha",
)

# ── Optional API auth middleware (fixed) ──────────────────────
auth_token = None
_auth_env = settings.api.auth_token_env
if _auth_env:
    auth_token = os.environ.get(_auth_env)

if auth_token:
    from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
    from starlette.requests import Request
    from starlette.responses import JSONResponse

    class AuthMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next: RequestResponseEndpoint):
            path = request.url.path
            if path.startswith(("/site/", "/assets/", "/health")):
                return await call_next(request)
            token = request.headers.get("X-API-Key")
            if token != auth_token:
                return JSONResponse(status_code=401, content={"detail": "Invalid API key"})
            return await call_next(request)

    app.add_middleware(AuthMiddleware)

# CORS
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

# ── Include domain routers ────────────────────────────────────
app.include_router(watchlist_router)
app.include_router(portfolio_router)
app.include_router(market_router)
app.include_router(evolution_router)
app.include_router(intelligence_router)


# ── Request/Response models ──────────────────────────────────
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


class ReportResponse(BaseModel):
    file_path: str
    markdown: str


class ScenarioSimRequest(BaseModel):
    scenario: str
    symbols: Optional[list[str]] = None


# ── Core routes ──────────────────────────────────────────────
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    from src.data.db_manager import SignalDB
    from src.watchlist.manager import WatchlistManager
    import socket
    from datetime import datetime

    db = SignalDB()
    pub = db.get_last_published()
    wl = WatchlistManager().list_dicts()
    try:
        host_ip = socket.gethostbyname(socket.gethostname())
    except Exception:
        host_ip = "unknown"

    # Data freshness check
    data_fresh = "unknown"
    latest_path = Path("docs/data/latest.json")
    if latest_path.exists():
        mtime = latest_path.stat().st_mtime
        age_hours = (datetime.now().timestamp() - mtime) / 3600
        if age_hours < 24:
            data_fresh = "fresh"
        elif age_hours < 72:
            data_fresh = "stale"
        else:
            data_fresh = "expired"

    db_stats = get_db_stats()

    return {
        "status": "ok",
        "version": "3.0.0-alpha",
        "product": "智策 NexStrat",
        "data_freshness": data_fresh,
        "watchlist_count": len(wl),
        "db_stats": db_stats,
        "last_published": pub,
        "api_base": f"http://{host_ip}:8000",
        "github_pages": "https://ttmens.github.io/stock-copilot/",
        "design_system": "v2.0 (Seeking Alpha + TradingView inspired)",
    }


@app.post("/analyze", response_model=AnalyzeResponse)
async def trigger_analysis(req: AnalyzeRequest):
    """Trigger full analysis pipeline."""
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
    """Create async analysis job."""
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
    """Get latest job status."""
    from src.data.db_manager import SignalDB
    job = SignalDB().get_latest_job()
    if not job:
        return {"status": "none"}
    return job


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    """Get job by ID."""
    from src.data.db_manager import SignalDB
    job = SignalDB().get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/api/published")
async def last_published():
    """Get last published report metadata."""
    from src.data.db_manager import SignalDB
    pub = SignalDB().get_last_published()
    meta_path = Path("docs/meta/published_at.json")
    file_meta = {}
    if meta_path.exists():
        file_meta = json.loads(meta_path.read_text(encoding="utf-8"))
    return {"db": pub, "file": file_meta}


@app.get("/reports/latest", response_model=ReportResponse)
async def get_latest_report():
    """Get latest markdown report."""
    output_dir = Path(get_settings().report.output_dir)
    reports = sorted(output_dir.glob("*.md"), reverse=True)
    if not reports:
        raise HTTPException(status_code=404, detail="No reports found")
    latest = reports[0]
    return ReportResponse(file_path=str(latest), markdown=latest.read_text(encoding="utf-8"))


@app.get("/reports/{report_date}", response_model=ReportResponse)
async def get_report_by_date(report_date: str, type: str = "pre"):
    """Get report by date."""
    output_dir = Path(get_settings().report.output_dir)
    report_file = output_dir / f"{report_date}-{type}.md"
    if not report_file.exists():
        raise HTTPException(status_code=404, detail=f"Report not found: {report_file}")
    return ReportResponse(file_path=str(report_file), markdown=report_file.read_text(encoding="utf-8"))


@app.get("/site/latest.json")
async def get_latest_json():
    """Get latest.json data file."""
    data_dir = Path(get_settings().site.data_dir)
    json_path = data_dir / "latest.json"
    if not json_path.exists():
        docs_path = Path("docs/data/latest.json")
        if docs_path.exists():
            json_path = docs_path
        else:
            raise HTTPException(status_code=404, detail="latest.json not found")
    return json.loads(json_path.read_text(encoding="utf-8"))


@app.get("/api/system/status")
async def system_status():
    """Comprehensive system status: DB, data freshness, scheduler jobs, evolution."""
    from src.data.db_manager import SignalDB
    from datetime import datetime

    result = {"status": "ok", "timestamp": datetime.now().isoformat()}

    # DB stats
    try:
        db_stats = get_db_stats()
        result.update(db_stats)
    except Exception as e:
        result["db_error"] = str(e)

    # Data freshness
    latest_path = Path("docs/data/latest.json")
    if latest_path.exists():
        mtime = latest_path.stat().st_mtime
        age_hours = (datetime.now().timestamp() - mtime) / 3600
        result["data_age_hours"] = round(age_hours, 1)
        result["data_freshness"] = "fresh" if age_hours < 24 else "stale" if age_hours < 72 else "expired"

    # Evolution status
    evo_path = Path("docs/data/evolution.json")
    if evo_path.exists():
        result["evolution_enabled"] = True
        try:
            evo = json.loads(evo_path.read_text())
            result["evolution_runs"] = len(evo.get("history", []))
        except Exception:
            pass

    return result


@app.post("/api/scenario/simulate")
async def simulate_scenario(req: ScenarioSimRequest):
    """Simulate scenario impact on watchlist."""
    from src.analysis.scenario_sim import ScenarioSimulator
    from src.watchlist.manager import WatchlistManager

    if not req.scenario.strip():
        raise HTTPException(status_code=400, detail="scenario description is required")

    wl_manager = WatchlistManager()

    # Resolve symbols: use provided list or fall back to full watchlist
    if req.symbols:
        all_items = {item["code"]: item for item in wl_manager.list_dicts()}
        watchlist = []
        missing = []
        for sym in req.symbols:
            sym = sym.strip()
            if sym in all_items:
                watchlist.append(all_items[sym])
            else:
                missing.append(sym)
        if not watchlist:
            raise HTTPException(
                status_code=400,
                detail=f"None of the provided symbols found in watchlist: {missing}",
            )
        if missing:
            logger.warning("Symbols not in watchlist, skipped: %s", missing)
    else:
        watchlist = wl_manager.list_dicts()
        if not watchlist:
            raise HTTPException(status_code=400, detail="Watchlist is empty and no symbols provided")

    simulator = ScenarioSimulator()
    result = await simulator.simulate(scenario=req.scenario, watchlist=watchlist)

    return {
        "impact_matrix": [item.to_dict() for item in result.impact_matrix],
        "overall_assessment": result.overall_assessment,
        "report": result.to_markdown(),
    }


@app.post("/api/stocks/{code}/deep-analysis")
async def deep_analysis(code: str):
    """Deep research analysis for a single stock."""
    from src.agents.deep_research import DeepResearchAgent
    agent = DeepResearchAgent()
    return await agent.analyze(code.strip())


@app.get("/api/config")
async def runtime_config():
    """Frontend runtime config: API base, version, features."""
    return {
        "version": "3.0.0-alpha",
        "product": "智策 NexStrat",
        "api_base": f"http://{settings.pipeline.api_host}:{settings.pipeline.api_port}",
        "production_api_base": settings.phase_g.production_api_base or "",
        "features": {
            "phase_g_enabled": settings.phase_g.enabled,
            "evolution_enabled": settings.evolution.enabled,
            "notify_type": settings.notify.type,
            "llm_mode": settings.llm.mode,
        },
    }


# ── Static files (MUST be after all API routes) ──────────────
docs_path = Path("docs")
if docs_path.exists():
    app.mount("/site", StaticFiles(directory=str(docs_path)), name="site")
    app.mount("/", StaticFiles(directory=str(docs_path), html=True), name="docs")
