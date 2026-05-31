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
    title="智策 NexStrat API",
    description="A股AI智能投研助手 — 5层信号融合 + LLM分析",
    version="3.0.0-alpha",
)

# ── Optional API auth middleware ──────────────────────────────
auth_token = None
_auth_env = settings.api.auth_token_env
if _auth_env:
    import os as _os
    auth_token = _os.environ.get(_auth_env)

if auth_token:
    from fastapi import Depends, Security
    from fastapi.security import APIKeyHeader
    api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
    async def verify_api_key(api_key: str = Security(api_key_header)):
        if api_key != auth_token:
            raise HTTPException(status_code=401, detail="Invalid API key")
    app.dependency_overrides.setdefault(lambda: None, verify_api_key)

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


class ScenarioSimRequest(BaseModel):
    scenario: str
    symbols: Optional[list[str]] = None


@app.get("/health")
async def health_check():
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

    # DB stats
    try:
        import sqlite3
        db_path = Path("data/signals.db")
        db_stats = {}
        if db_path.exists():
            conn = sqlite3.connect(str(db_path))
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM signals")
            db_stats["signal_count"] = cur.fetchone()[0]
            cur.execute("SELECT COUNT(DISTINCT code) FROM signals")
            db_stats["unique_stocks"] = cur.fetchone()[0]
            cur.execute("SELECT MAX(trade_date) FROM signals")
            last_date = cur.fetchone()[0]
            db_stats["last_signal_date"] = last_date
            conn.close()
    except Exception:
        db_stats = {}

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


@app.get("/api/system/status")
async def system_status():
    """Comprehensive system status: DB, data freshness, scheduler jobs, evolution."""
    from src.data.db_manager import SignalDB
    import sqlite3
    from datetime import datetime

    result = {"status": "ok", "timestamp": datetime.now().isoformat()}

    # DB stats
    try:
        db_path = Path("data/signals.db")
        if db_path.exists():
            conn = sqlite3.connect(str(db_path))
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM signals")
            result["signal_count"] = cur.fetchone()[0]
            cur.execute("SELECT COUNT(DISTINCT code) FROM signals")
            result["unique_stocks"] = cur.fetchone()[0]
            cur.execute("SELECT MAX(trade_date) FROM signals")
            result["last_signal_date"] = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM jobs WHERE status = 'completed'")
            result["completed_jobs"] = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM jobs WHERE status = 'failed'")
            result["failed_jobs"] = cur.fetchone()[0]
            conn.close()
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


# ── Phase F: Postmortems, Theses, Breadth, Stagnation ──────────


class CheckMatureRequest(BaseModel):
    check_date: Optional[str] = None


@app.get("/api/postmortems")
async def list_postmortems(ticker: Optional[str] = None, days: int = 30):
    """List signal postmortems with optional ticker and date range filter."""
    from src.data.db_manager import SignalDB
    return {"postmortems": SignalDB().get_postmortems(ticker=ticker, days=days)}


@app.get("/api/postmortems/summary")
async def postmortem_summary(days: int = 30):
    """Postmortem statistical summary."""
    from src.data.db_manager import SignalDB
    from src.evolution.postmortem import PostmortemRecorder
    return PostmortemRecorder(SignalDB()).get_summary(days=days)


@app.post("/api/postmortems/check-mature")
async def check_mature(req: Optional[CheckMatureRequest] = None):
    """Check matured signals and update outcomes."""
    from src.data.db_manager import SignalDB
    from src.evolution.postmortem import PostmortemRecorder
    check_date = req.check_date if req else None
    return PostmortemRecorder(SignalDB()).check_mature_signals(as_of=check_date)


@app.get("/api/theses")
async def list_theses(status: Optional[str] = None, ticker: Optional[str] = None):
    """List thesis records with optional status and ticker filter."""
    from src.data.db_manager import SignalDB
    return {"theses": SignalDB().get_theses(status=status, ticker=ticker)}


@app.get("/api/theses/statistics")
async def thesis_statistics(days: int = 90):
    """Thesis performance statistics over a given period."""
    from src.data.db_manager import SignalDB
    from datetime import timedelta

    db = SignalDB()
    all_theses = db.get_theses()

    # Filter by creation date
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    recent = [t for t in all_theses if t.get("created_at", "") >= cutoff]

    by_status = {}
    for t in recent:
        s = t.get("status", "unknown")
        by_status[s] = by_status.get(s, 0) + 1

    # PnL stats for exited theses
    exited = [t for t in recent if t.get("exit_date") and t.get("pnl_pct") is not None]
    pnls = [t["pnl_pct"] for t in exited]
    avg_pnl = round(sum(pnls) / len(pnls), 2) if pnls else None
    max_pnl = round(max(pnls), 2) if pnls else None
    min_pnl = round(min(pnls), 2) if pnls else None

    # Win rate (positive PnL)
    wins = sum(1 for p in pnls if p > 0)
    win_rate = round(wins / len(pnls), 3) if pnls else None

    # By thesis type
    by_type = {}
    for t in recent:
        tt = t.get("thesis_type", "unknown")
        if tt not in by_type:
            by_type[tt] = {"count": 0, "exited": 0, "win": 0}
        by_type[tt]["count"] += 1
        if t.get("exit_date"):
            by_type[tt]["exited"] += 1
            if t.get("pnl_pct") is not None and t["pnl_pct"] > 0:
                by_type[tt]["win"] += 1

    return {
        "period_days": days,
        "total": len(recent),
        "by_status": by_status,
        "exited_count": len(exited),
        "avg_pnl": avg_pnl,
        "max_pnl": max_pnl,
        "min_pnl": min_pnl,
        "win_rate": win_rate,
        "by_type": by_type,
    }


@app.get("/api/breadth")
async def market_breadth():
    """Market breadth metrics derived from latest.json stock data."""
    from src.data.db_manager import SignalDB
    from datetime import datetime

    data_dir = Path(get_settings().site.data_dir)
    json_path = data_dir / "latest.json"
    if not json_path.exists():
        docs_path = Path("docs/data/latest.json")
        if docs_path.exists():
            json_path = docs_path
        else:
            raise HTTPException(status_code=404, detail="latest.json not found")

    data = json.loads(json_path.read_text(encoding="utf-8"))
    stocks = data.get("stocks", [])
    meta = data.get("meta", {})

    if not stocks:
        return {"error": "No stock data available"}

    total = len(stocks)

    # Sentiment distribution
    sentiments = {"bullish": 0, "neutral": 0, "bearish": 0}
    for s in stocks:
        sent = s.get("overall_sentiment", "neutral")
        if sent in sentiments:
            sentiments[sent] += 1

    # MA alignment distribution
    ma_dist = {"bullish": 0, "bearish": 0, "flat": 0, "unknown": 0}
    for s in stocks:
        ma = s.get("ma_alignment", "unknown")
        if ma in ma_dist:
            ma_dist[ma] += 1
        else:
            ma_dist["unknown"] += 1

    # Score distribution
    hard_scores = [s.get("hard_score") for s in stocks if s.get("hard_score") is not None]
    final_scores = [s.get("signal_breakdown", {}).get("final_score") for s in stocks
                    if s.get("signal_breakdown", {}).get("final_score") is not None]

    # Momentum stats
    mom_5d = [s.get("momentum_5d") for s in stocks if s.get("momentum_5d") is not None]
    mom_20d = [s.get("momentum_20d") for s in stocks if s.get("momentum_20d") is not None]

    # Advance/decline (positive vs negative 5d momentum)
    advances = sum(1 for m in mom_5d if m > 0)
    declines = sum(1 for m in mom_5d if m < 0)
    unchanged = sum(1 for m in mom_5d if m == 0)

    return {
        "trade_date": meta.get("trade_date"),
        "generated_at": meta.get("generated_at"),
        "symbol_count": total,
        "sentiment": sentiments,
        "ma_alignment": ma_dist,
        "advance_decline": {
            "advances": advances,
            "declines": declines,
            "unchanged": unchanged,
            "advance_ratio": round(advances / total, 3) if total else 0,
        },
        "hard_score": {
            "mean": round(sum(hard_scores) / len(hard_scores), 3) if hard_scores else None,
            "median": round(sorted(hard_scores)[len(hard_scores) // 2], 3) if hard_scores else None,
        },
        "final_score": {
            "mean": round(sum(final_scores) / len(final_scores), 3) if final_scores else None,
        },
        "momentum_5d": {
            "mean": round(sum(mom_5d) / len(mom_5d), 2) if mom_5d else None,
        },
        "momentum_20d": {
            "mean": round(sum(mom_20d) / len(mom_20d), 2) if mom_20d else None,
        },
    }


@app.get("/api/stagnation")
async def stagnation_check():
    """Identify stagnating stocks from latest.json data."""
    from src.data.db_manager import SignalDB
    from datetime import datetime

    data_dir = Path(get_settings().site.data_dir)
    json_path = data_dir / "latest.json"
    if not json_path.exists():
        docs_path = Path("docs/data/latest.json")
        if docs_path.exists():
            json_path = docs_path
        else:
            raise HTTPException(status_code=404, detail="latest.json not found")

    data = json.loads(json_path.read_text(encoding="utf-8"))
    stocks = data.get("stocks", [])
    meta = data.get("meta", {})

    # Stagnation criteria:
    # - 5d momentum within ±2% (near-zero)
    # - AND volume_ratio < 1.2 (no unusual volume)
    # - OR flat/unknown MA alignment
    stagnating = []
    for s in stocks:
        mom_5d = s.get("momentum_5d")
        vol_ratio = s.get("volume_ratio")
        ma = s.get("ma_alignment", "unknown")

        is_low_momentum = mom_5d is not None and abs(mom_5d) < 2.0
        is_low_volume = vol_ratio is not None and vol_ratio < 1.2
        is_flat_ma = ma in ("flat", "unknown") or ma is None

        if is_low_momentum and (is_low_volume or is_flat_ma):
            stagnating.append({
                "code": s.get("code"),
                "name": s.get("name"),
                "momentum_5d": mom_5d,
                "volume_ratio": vol_ratio,
                "ma_alignment": ma,
                "hard_score": s.get("hard_score"),
                "final_score": s.get("signal_breakdown", {}).get("final_score"),
                "sentiment": s.get("overall_sentiment"),
            })

    return {
        "trade_date": meta.get("trade_date"),
        "total_analyzed": len(stocks),
        "stagnation_count": len(stagnating),
        "stagnation_ratio": round(len(stagnating) / len(stocks), 3) if stocks else 0,
        "stagnating": sorted(stagnating, key=lambda x: abs(x.get("momentum_5d", 0) or 0)),
    }


# ── Phase G API ──────────────────────────────────────────────

class PositionCreate(BaseModel):
    code: str
    name: str = ""
    shares: float
    entry_price: float
    leverage: float = 1.0
    stop_loss: float | None = None
    take_profit: float | None = None
    notes: str = ""


class PositionUpdate(BaseModel):
    code: str | None = None
    name: str | None = None
    shares: float | None = None
    entry_price: float | None = None
    leverage: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    notes: str | None = None


@app.get("/api/market/session")
async def market_session():
    from src.monitoring.session import get_market_session
    return get_market_session()


@app.get("/api/digest/today")
async def digest_today(trade_date: str | None = None):
    from src.intelligence.ingester import KnowledgeIngester
    from datetime import date as d
    td = d.fromisoformat(trade_date) if trade_date else d.today()
    return KnowledgeIngester().export_json(td)


@app.get("/api/overnight")
async def overnight_snapshot(trade_date: str | None = None):
    from src.intelligence.overnight import build_overnight_snapshot
    from datetime import date as d
    td = d.fromisoformat(trade_date) if trade_date else d.today()
    return build_overnight_snapshot(td)


@app.get("/api/recommendations/today")
async def recommendations_today(trade_date: str | None = None):
    from src.recommendation.engine import RecommendationEngine
    from datetime import date as d
    td = d.fromisoformat(trade_date) if trade_date else d.today()
    return RecommendationEngine().export_json(td)


@app.get("/api/auction/latest")
async def auction_latest(trade_date: str | None = None):
    from src.monitoring.auction import AuctionMonitor
    from datetime import date as d
    td = d.fromisoformat(trade_date) if trade_date else d.today()
    return AuctionMonitor().get_latest(td)


@app.get("/api/alerts")
async def list_alerts(trade_date: str | None = None, unread_only: bool = False,
                      severity: str | None = None):
    from src.monitoring.alerts import AlertDispatcher
    return AlertDispatcher().get_feed(trade_date, unread_only, severity)


@app.post("/api/alerts/read")
async def mark_alerts_read(trade_date: str | None = None):
    from src.data.db_manager import SignalDB
    from datetime import date as d
    td = trade_date or d.today().isoformat()
    count = SignalDB().mark_alerts_read(td)
    return {"marked_read": count}


@app.get("/api/positions")
async def list_positions(open_only: bool = True):
    from src.portfolio.tracker import PositionTracker
    return PositionTracker().summary() if open_only else {"positions": PositionTracker().list_positions(False)}


@app.post("/api/positions")
async def create_position(body: PositionCreate):
    from src.portfolio.tracker import PositionTracker
    return PositionTracker().create(
        body.code, body.name or body.code, body.shares, body.entry_price,
        body.leverage, body.stop_loss, body.take_profit, body.notes,
    )


@app.patch("/api/positions/{position_id}")
async def update_position(position_id: int, body: PositionUpdate):
    from src.portfolio.tracker import PositionTracker
    kwargs = {k: v for k, v in body.model_dump().items() if v is not None}
    try:
        return PositionTracker().update(position_id, **kwargs)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.delete("/api/positions/{position_id}")
async def delete_position(position_id: int):
    from src.portfolio.tracker import PositionTracker
    if not PositionTracker().delete(position_id):
        raise HTTPException(status_code=404, detail="Position not found")
    return {"deleted": position_id}


@app.get("/api/review/today")
async def review_today(trade_date: str | None = None):
    from src.review.recommendation_review import RecommendationReview
    from datetime import date as d
    td = d.fromisoformat(trade_date) if trade_date else d.today()
    return RecommendationReview().export_json(td)


@app.post("/api/stocks/{code}/deep-analysis")
async def deep_analysis(code: str):
    from src.agents.deep_research import DeepResearchAgent
    agent = DeepResearchAgent()
    return await agent.analyze(code.strip())


# ── Static files (MUST be after all API routes) ──────────────
docs_path = Path("docs")
if docs_path.exists():
    app.mount("/site", StaticFiles(directory=str(docs_path)), name="site")
    app.mount("/", StaticFiles(directory=str(docs_path), html=True), name="docs")
