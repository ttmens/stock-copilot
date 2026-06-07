"""Evolution API router — suggestions and postmortems."""

from datetime import date, timedelta
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

router = APIRouter(tags=["evolution"])


class CheckMatureRequest(BaseModel):
    check_date: Optional[str] = None


@router.get("/api/evolution/suggestions")
async def evolution_suggestions(status: str = "pending"):
    """List evolution suggestions (add/evict candidates)."""
    from src.data.db_manager import SignalDB
    return {"suggestions": SignalDB().list_evolution_suggestions(status)}


@router.post("/api/evolution/suggestions/{suggestion_id}/accept")
async def accept_suggestion(suggestion_id: int, accept: bool = True):
    """Accept or reject an evolution suggestion."""
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


@router.get("/api/postmortems")
async def list_postmortems(ticker: Optional[str] = None, days: int = 30):
    """List signal postmortems with optional ticker and date range filter."""
    from src.data.db_manager import SignalDB
    return {"postmortems": SignalDB().get_postmortems(ticker=ticker, days=days)}


@router.get("/api/postmortems/summary")
async def postmortem_summary(days: int = 30):
    """Postmortem statistical summary."""
    from src.data.db_manager import SignalDB
    from src.evolution.postmortem import PostmortemRecorder
    return PostmortemRecorder(SignalDB()).get_summary(days=days)


@router.post("/api/postmortems/check-mature")
async def check_mature(req: Optional[CheckMatureRequest] = None):
    """Check matured signals and update outcomes."""
    from src.data.db_manager import SignalDB
    from src.evolution.postmortem import PostmortemRecorder
    check_date = req.check_date if req else None
    return PostmortemRecorder(SignalDB()).check_mature_signals(as_of=check_date)


@router.get("/api/theses")
async def list_theses(status: Optional[str] = None, ticker: Optional[str] = None):
    """List thesis records with optional status and ticker filter."""
    from src.data.db_manager import SignalDB
    return {"theses": SignalDB().get_theses(status=status, ticker=ticker)}


@router.get("/api/theses/statistics")
async def thesis_statistics(days: int = 90):
    """Thesis performance statistics over a given period."""
    from src.data.db_manager import SignalDB

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
