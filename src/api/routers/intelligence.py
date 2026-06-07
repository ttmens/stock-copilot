"""Intelligence API router — alerts, digest, overnight, recommendations, review."""

from datetime import date
from fastapi import APIRouter
from .helpers import safe_parse_date

router = APIRouter(tags=["intelligence"])


@router.get("/api/alerts")
async def list_alerts(trade_date: str | None = None, unread_only: bool = False,
                      severity: str | None = None):
    """List alerts with optional filters."""
    from src.monitoring.alerts import AlertDispatcher
    return AlertDispatcher().get_feed(trade_date, unread_only, severity)


@router.post("/api/alerts/read")
async def mark_alerts_read(trade_date: str | None = None):
    """Mark alerts as read."""
    from src.data.db_manager import SignalDB
    from datetime import date as d
    td = trade_date or d.today().isoformat()
    count = SignalDB().mark_alerts_read(td)
    return {"marked_read": count}


@router.get("/api/digest/today")
async def digest_today(trade_date: str | None = None):
    """Today's knowledge digest."""
    from src.intelligence.ingester import KnowledgeIngester
    td = safe_parse_date(trade_date) or date.today()
    return KnowledgeIngester().export_json(td)


@router.get("/api/overnight")
async def overnight_snapshot(trade_date: str | None = None):
    """Overnight snapshot (pre-market global context)."""
    from src.intelligence.overnight import build_overnight_snapshot
    td = safe_parse_date(trade_date) or date.today()
    return build_overnight_snapshot(td)


@router.get("/api/recommendations/today")
async def recommendations_today(trade_date: str | None = None):
    """Today's stock recommendations."""
    from src.recommendation.engine import RecommendationEngine
    td = safe_parse_date(trade_date) or date.today()
    return RecommendationEngine().export_json(td)


@router.get("/api/auction/latest")
async def auction_latest(trade_date: str | None = None):
    """Latest auction (call auction) data."""
    from src.monitoring.auction import AuctionMonitor
    td = safe_parse_date(trade_date) or date.today()
    return AuctionMonitor().get_latest(td)


@router.get("/api/review/today")
async def review_today(trade_date: str | None = None):
    """Today's recommendation review."""
    from src.review.recommendation_review import RecommendationReview
    td = safe_parse_date(trade_date) or date.today()
    return RecommendationReview().export_json(td)
