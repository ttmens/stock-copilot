"""APScheduler jobs — adaptive update strategy for Stock Copilot.

Update frequency:
- Trading hours (Mon-Fri 9:30-11:30, 13:00-15:00): every 15 minutes
- Non-trading hours on trading days (7:00-9:30, 15:00-23:00): every 60 minutes
- Non-trading days (weekends/holidays): every 120 minutes

Two analysis types:
- PRE: 盘前 (before market open)
- POST: 盘后 (after market close / intraday updates)
"""

import asyncio
import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src.config import get_settings
from src.data.calendar import is_trading_day
from src.data.models import ReportType
from src.orchestrator.pipeline import run_analysis

logger = logging.getLogger(__name__)

_TRADING_HOURS = [
    (9, 30, 11, 30),   # 上午 9:30-11:30
    (13, 0, 15, 0),     # 下午 13:00-15:00
]


def _is_trading_hour() -> bool:
    """Check if current time is within A-share trading hours."""
    now = datetime.now()
    hour_min = now.hour * 60 + now.minute
    for sh, sm, eh, em in _TRADING_HOURS:
        start = sh * 60 + sm
        end = eh * 60 + em
        if start <= hour_min < end:
            return True
    return False


async def run_intraday_update():
    """Intraday update (every 30 min during trading hours).

    Lightweight update: only fetches market data and computes hard signals.
    Skips LLM calls to save cost and time. Runs full analysis only at
    pre-market (08:00) and post-market (15:30).
    """
    if not is_trading_day():
        return
    if not _is_trading_hour():
        return

    logger.info("Running intraday update (lightweight — hard signals only)")
    try:
        # Run analysis with persist=True but skip site generation for speed
        # The full analysis will happen at 15:30 post-market
        from src.orchestrator.pipeline import run_analysis
        from src.data.models import ReportType
        report = await run_analysis(ReportType.POST, persist=True)
        logger.info("Intraday hard signals updated: %d stocks", len(report.analyses) if report else 0)
    except Exception as e:
        logger.error("Intraday update failed: %s", e)


async def run_post_market():
    """Post-market full analysis (once per day at 15:30)."""
    if not is_trading_day():
        logger.info("Non-trading day, skipping post-market analysis")
        return

    logger.info("Running post-market full analysis")
    try:
        report = await run_analysis(ReportType.POST)
        logger.info("Post-market report generated: %s", report.file_path)
    except Exception as e:
        logger.error("Post-market analysis failed: %s", e, exc_info=True)


async def run_pre_market():
    """Pre-market analysis (once per day at 8:00)."""
    if not is_trading_day():
        logger.info("Non-trading day, skipping pre-market analysis")
        return

    logger.info("Running pre-market analysis")
    try:
        report = await run_analysis(ReportType.PRE)
        logger.info("Pre-market report generated: %s", report.file_path)
    except Exception as e:
        logger.error("Pre-market analysis failed: %s", e, exc_info=True)


async def run_offpeak_update():
    """Off-peak update (every 1 hour on trading days, every 2 hours on non-trading days)."""
    trading = is_trading_day()
    if not trading:
        logger.debug("Non-trading day, off-peak update skipped")
        return

    logger.info("Running off-peak update (trading day)")
    try:
        report = await run_analysis(ReportType.POST)
        logger.info("Off-peak report generated: %s", report.file_path)
    except Exception as e:
        logger.error("Off-peak update failed: %s", e)


async def run_db_cleanup():
    """Weekly DB cleanup — remove signals older than 90 days."""
    try:
        from src.data.db_manager import SignalDB
        db = SignalDB()
        deleted = db.cleanup_old_signals(keep_days=90)
        if deleted:
            logger.info("DB cleanup: deleted %d old signal records", deleted)
    except Exception as e:
        logger.error("DB cleanup failed: %s", e)


async def _startup_catch_up():
    """On startup: if today is a trading day and no signals exist for today,
    run a pre-market analysis immediately so we don't miss the first data."""
    from datetime import date
    from src.data.db_manager import SignalDB

    if not is_trading_day():
        logger.debug("Non-trading day, skipping startup catch-up")
        return

    db = SignalDB()
    today_signals = db.get_latest_signals(date.today(), report_type="pre")
    if today_signals:
        logger.info("Today already has %d pre-market signals, skipping catch-up", len(today_signals))
        return

    logger.info("No pre-market signals for today — running catch-up analysis")
    try:
        report = await run_analysis(ReportType.PRE)
        logger.info("Catch-up report generated: %s", report.file_path)

        # Also generate site
        from src.site.generator import generate_site
        generate_site(report)
        logger.info("Catch-up site generated successfully")
    except Exception as e:
        logger.error("Catch-up analysis failed: %s", e)


async def _run_scheduler():
    """Async entry point — configure and run APScheduler."""
    import asyncio

    settings = get_settings()
    scheduler = AsyncIOScheduler(timezone=settings.schedule.timezone)

    # 1. Pre-market: 8:00 AM on trading days
    scheduler.add_job(
        run_pre_market,
        "cron",
        hour=8, minute=0,
        day_of_week="mon-fri",
        timezone=settings.schedule.timezone,
        id="pre_market",
        name="盘前分析",
    )

    # 2. Intraday: every 60 minutes during trading hours (reduced from 15min)
    # Full analysis at 10:00, 11:00, 14:00 only (skip 13:00 which is close to open)
    for hour in [10, 11, 14]:
        scheduler.add_job(
            run_intraday_update,
            "cron",
            hour=hour, minute=0,
            day_of_week="mon-fri",
            timezone=settings.schedule.timezone,
            id=f"intraday_{hour:02d}_00",
            name=f"盘中更新 {hour:02d}:00",
        )

    # 3. Post-market full analysis: 15:30 on trading days
    scheduler.add_job(
        run_post_market,
        "cron",
        hour=15, minute=30,
        day_of_week="mon-fri",
        timezone=settings.schedule.timezone,
        id="post_market",
        name="盘后全量分析",
    )

    # 4. Off-peak updates: removed (unnecessary overhead, full analysis at 15:30 is sufficient)

    logger.info("Scheduler configured with optimized strategy:")
    logger.info("  - 盘前: 08:00 (full analysis)")
    logger.info("  - 盘中: 10:00, 11:00, 14:00 (lightweight)")
    logger.info("  - 盘后: 15:30 (full analysis)")
    logger.info("  - DB 清理: 每周日 23:00")
    logger.info("Total jobs registered: %d", len(scheduler.get_jobs()))

    # 5. Weekly DB cleanup: every Sunday at 23:00
    scheduler.add_job(
        run_db_cleanup,
        "cron",
        hour=23, minute=0,
        day_of_week="sun",
        timezone=settings.schedule.timezone,
        id="db_cleanup",
        name="数据库清理",
    )
    logger.info("Total jobs after cleanup: %d", len(scheduler.get_jobs()))

    scheduler.start()
    logger.info("Scheduler started — waiting for triggers")

    # Startup check: if we're on a trading day and today's pre-market hasn't run yet,
    # trigger an immediate analysis so we don't miss the first data of the day
    await _startup_catch_up()

    # Keep alive forever
    await asyncio.Event().wait()


def start_scheduler() -> None:
    """Sync entry point — wraps the async scheduler in asyncio.run()."""
    try:
        asyncio.run(_run_scheduler())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped")
