"""Market session detection for Phase G scheduling and UI."""

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from src.config import get_settings
from src.data.calendar import is_trading_day

TZ = ZoneInfo("Asia/Shanghai")

SESSIONS = [
    ("pre_market", time(6, 0), time(9, 15)),
    ("auction", time(9, 15), time(9, 25)),
    ("morning", time(9, 30), time(11, 30)),
    ("lunch", time(11, 30), time(13, 0)),
    ("afternoon", time(13, 0), time(15, 0)),
    ("post_market", time(15, 0), time(23, 59, 59)),
]


def _now_sh() -> datetime:
    return datetime.now(TZ)


def get_market_session(dt: datetime | None = None) -> dict:
    """Return current market session info."""
    now = dt or _now_sh()
    t = now.time()
    d = now.date()

    if not is_trading_day(d):
        return {
            "session": "closed",
            "is_trading_day": False,
            "trade_date": d.isoformat(),
            "next_milestone": None,
            "minutes_to_milestone": None,
        }

    current = "post_market"
    next_name = None
    next_time = None
    for i, (name, start, end) in enumerate(SESSIONS):
        if start <= t < end:
            current = name
            if i + 1 < len(SESSIONS):
                next_name = SESSIONS[i + 1][0]
                next_time = SESSIONS[i + 1][1]
            break

    minutes_to = None
    if next_time:
        target = datetime.combine(d, next_time, tzinfo=TZ)
        minutes_to = max(0, int((target - now).total_seconds() / 60))

    return {
        "session": current,
        "is_trading_day": True,
        "trade_date": d.isoformat(),
        "next_milestone": next_name,
        "minutes_to_milestone": minutes_to,
        "now": now.isoformat(),
    }


def is_auction_window(dt: datetime | None = None) -> bool:
    return get_market_session(dt)["session"] == "auction"


def is_intraday_window(dt: datetime | None = None) -> bool:
    return get_market_session(dt)["session"] in ("morning", "afternoon")
