"""APScheduler jobs — pre-market and post-market analysis."""

import asyncio
import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src.config import get_settings
from src.data.calendar import is_trading_day
from src.data.models import ReportType
from src.orchestrator.pipeline import run_analysis

logger = logging.getLogger(__name__)


async def run_pre_market():
    """Pre-market analysis job."""
    if not is_trading_day():
        logger.info("Non-trading day, skipping pre-market analysis")
        return

    logger.info("Running pre-market analysis")
    try:
        report = await run_analysis(ReportType.PRE)
        logger.info("Pre-market report generated: %s", report.file_path)
    except Exception as e:
        logger.error("Pre-market analysis failed: %s", e, exc_info=True)


async def run_post_market():
    """Post-market analysis job."""
    if not is_trading_day():
        logger.info("Non-trading day, skipping post-market analysis")
        return

    logger.info("Running post-market analysis")
    try:
        report = await run_analysis(ReportType.POST)
        logger.info("Post-market report generated: %s", report.file_path)
    except Exception as e:
        logger.error("Post-market analysis failed: %s", e, exc_info=True)


def start_scheduler() -> None:
    """Configure and start APScheduler."""
    import asyncio

    settings = get_settings()
    scheduler = AsyncIOScheduler()

    pre_hour, pre_min = settings.schedule.pre_market.split(":")
    post_hour, post_min = settings.schedule.post_market.split(":")

    scheduler.add_job(
        run_pre_market,
        "cron",
        hour=int(pre_hour),
        minute=int(pre_min),
        timezone=settings.schedule.timezone,
        id="pre_market",
        name="Pre-market analysis",
    )
    scheduler.add_job(
        run_post_market,
        "cron",
        hour=int(post_hour),
        minute=int(post_min),
        timezone=settings.schedule.timezone,
        id="post_market",
        name="Post-market analysis",
    )

    logger.info("Scheduler configured: pre=%s, post=%s (%s)",
                settings.schedule.pre_market,
                settings.schedule.post_market,
                settings.schedule.timezone)

    scheduler.start()
    logger.info("Scheduler started")

    try:
        asyncio.get_event_loop().run_forever()
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        logger.info("Scheduler stopped")
