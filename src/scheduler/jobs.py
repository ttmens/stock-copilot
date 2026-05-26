"""APScheduler jobs — production schedule for Stock Copilot.

Schedule (trading days only):
- 盘前 08:00: 全量分析（含 LLM）+ 站点生成 + 推送 GitHub
- 盘中 10:00, 11:00, 14:00: 全量分析（含 LLM）+ 站点生成 + 推送 GitHub
- 盘后 15:30: 全量分析（含 LLM）+ 站点生成 + 推送 GitHub
- 数据库清理 每周日 23:00

Every job runs the FULL analysis pipeline including LLM calls, site
generation, and GitHub push — no lightweight shortcuts.
"""

import asyncio
import logging
import os
import subprocess
from datetime import datetime, date

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src.config import get_settings
from src.data.calendar import is_trading_day
from src.data.models import ReportType
from src.orchestrator.pipeline import run_analysis

logger = logging.getLogger(__name__)

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _publish_to_github(report_type: str = "post") -> bool:
    """Commit and push docs/ to GitHub for Pages deployment."""
    try:
        os.chdir(_PROJECT_ROOT)

        # Check git user configured
        r = subprocess.run(["git", "config", "user.name"], capture_output=True, text=True)
        if not r.stdout.strip():
            logger.warning("Git user.name not configured, skipping publish")
            return False

        r = subprocess.run(["git", "config", "user.email"], capture_output=True, text=True)
        if not r.stdout.strip():
            logger.warning("Git user.email not configured, skipping publish")
            return False

        # Stage docs/
        subprocess.run(["git", "add", "docs/"], capture_output=True, text=True)

        # Check if there are changes
        r = subprocess.run(["git", "diff", "--cached", "--quiet"], capture_output=True, text=True)
        if r.returncode == 0:
            logger.info("No changes to publish")
            return True

        # Commit
        type_label = "盘前" if report_type == "pre" else "盘后"
        msg = f"auto: report {date.today()}-{report_type} {type_label}"
        r = subprocess.run(["git", "commit", "-m", msg], capture_output=True, text=True)
        if r.returncode != 0:
            logger.warning("Git commit failed: %s", r.stderr.strip() or r.stdout.strip())
            return False

        # Push
        r = subprocess.run(["git", "push", "origin", "main"], capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            logger.error("Git push failed: %s", r.stderr.strip() or r.stdout.strip())
            return False

        logger.info("Published to GitHub: %s", msg)
        return True

    except Exception as e:
        logger.error("Publish failed: %s", e)
        return False


async def _run_full_pipeline(report_type: ReportType):
    """Run full analysis + generate site + publish to GitHub."""
    from src.site.generator import generate_site

    report = await run_analysis(report_type, persist=True)
    logger.info("Full analysis completed: %s (%d stocks)", report.file_path, len(report.analyses))

    # Generate site
    try:
        site_path = generate_site(report)
        logger.info("Site generated: %s", site_path)
    except Exception as e:
        logger.error("Site generation failed: %s", e, exc_info=True)
        return

    # Publish to GitHub
    try:
        _publish_to_github(report_type.value)
    except Exception as e:
        logger.error("Publish failed: %s", e, exc_info=True)


async def run_intraday_update():
    """Intraday update — full analysis with LLM + auto publish."""
    if not is_trading_day():
        return

    logger.info("Running intraday update (full analysis)")
    try:
        await _run_full_pipeline(ReportType.POST)
    except Exception as e:
        logger.error("Intraday update failed: %s", e, exc_info=True)


async def run_post_market():
    """Post-market full analysis (once per day at 15:30)."""
    if not is_trading_day():
        logger.info("Non-trading day, skipping post-market analysis")
        return

    logger.info("Running post-market full analysis")
    try:
        await _run_full_pipeline(ReportType.POST)
    except Exception as e:
        logger.error("Post-market analysis failed: %s", e, exc_info=True)


async def run_pre_market():
    """Pre-market analysis (once per day at 8:00)."""
    if not is_trading_day():
        logger.info("Non-trading day, skipping pre-market analysis")
        return

    logger.info("Running pre-market analysis")
    try:
        await _run_full_pipeline(ReportType.PRE)
    except Exception as e:
        logger.error("Pre-market analysis failed: %s", e, exc_info=True)


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
    run a full analysis immediately so the website has today's data."""
    from src.data.db_manager import SignalDB

    if not is_trading_day():
        logger.debug("Non-trading day, skipping startup catch-up")
        return

    db = SignalDB()
    today_signals = db.get_latest_signals(date.today(), report_type="pre")
    if today_signals:
        logger.info("Today already has %d pre-market signals, skipping catch-up", len(today_signals))
        return

    logger.info("No signals for today — running startup catch-up analysis")
    try:
        await _run_full_pipeline(ReportType.PRE)
    except Exception as e:
        logger.error("Catch-up analysis failed: %s", e, exc_info=True)


async def _run_scheduler():
    """Async entry point — configure and run APScheduler."""
    import asyncio

    settings = get_settings()
    scheduler = AsyncIOScheduler(timezone=settings.schedule.timezone)

    # 1. Pre-market: 08:00 on trading days
    scheduler.add_job(
        run_pre_market,
        "cron",
        hour=8, minute=0,
        day_of_week="mon-fri",
        timezone=settings.schedule.timezone,
        id="pre_market",
        name="盘前分析",
    )

    # 2. Intraday: 10:00, 11:00, 14:00 on trading days (full analysis)
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

    # 4. Weekly DB cleanup: every Sunday at 23:00
    scheduler.add_job(
        run_db_cleanup,
        "cron",
        hour=23, minute=0,
        day_of_week="sun",
        timezone=settings.schedule.timezone,
        id="db_cleanup",
        name="数据库清理",
    )

    logger.info("Scheduler configured — production mode (all tasks = full analysis + auto push):")
    logger.info("  - 盘前: 08:00 (全量 + 自动推送)")
    logger.info("  - 盘中: 10:00, 11:00, 14:00 (全量 + 自动推送)")
    logger.info("  - 盘后: 15:30 (全量 + 自动推送)")
    logger.info("  - 清理: 每周日 23:00")
    logger.info("Total jobs: %d", len(scheduler.get_jobs()))

    scheduler.start()
    logger.info("Scheduler started — waiting for triggers")

    # Startup check: run full analysis if today has no data yet
    await _startup_catch_up()

    # Keep alive forever
    await asyncio.Event().wait()


def start_scheduler() -> None:
    """Sync entry point — wraps the async scheduler in asyncio.run()."""
    try:
        asyncio.run(_run_scheduler())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped")
