"""Market data API router — breadth, stagnation, session, quotes."""

from datetime import date
from fastapi import APIRouter
from .helpers import read_latest_json, safe_parse_date

router = APIRouter(tags=["market"])


@router.get("/api/breadth")
async def market_breadth():
    """Market breadth metrics derived from latest.json stock data."""
    data = read_latest_json()
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


@router.get("/api/stagnation")
async def stagnation_check():
    """Identify stagnating stocks from latest.json data."""
    data = read_latest_json()
    stocks = data.get("stocks", [])
    meta = data.get("meta", {})

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


@router.get("/api/market/session")
async def market_session():
    """Current market session status (pre-market, trading, closed)."""
    from src.monitoring.session import get_market_session
    return get_market_session()


@router.get("/api/quotes/intraday")
async def intraday_quotes(trade_date: str | None = None):
    """Get intraday quotes for watchlist stocks."""
    from src.data.db_manager import SignalDB
    td = safe_parse_date(trade_date) or date.today()
    return {"quotes": SignalDB().get_intraday_quotes(td)}
