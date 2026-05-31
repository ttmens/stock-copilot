"""APScheduler jobs — production schedule for Stock Copilot (Phase C)."""

import asyncio
import logging
from datetime import date

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src.config import get_settings
from src.data.calendar import is_trading_day
from src.data.models import ReportType
from src.delivery.pipeline import DeliveryPipeline

logger = logging.getLogger(__name__)


def _parse_hm(time_str: str) -> tuple[int, int]:
    parts = time_str.strip().split(":")
    return int(parts[0]), int(parts[1]) if len(parts) > 1 else 0


async def run_pre_market():
    if not is_trading_day():
        logger.info("Non-trading day, skipping pre-market")
        return
    logger.info("[full] Running pre-market analysis")
    pipe = DeliveryPipeline()
    try:
        await pipe.run_full(ReportType.PRE, publish=True)
    except Exception as e:
        logger.error("Pre-market failed: %s", e, exc_info=True)


async def run_post_market():
    if not is_trading_day():
        logger.info("Non-trading day, skipping post-market")
        return
    logger.info("[full] Running post-market analysis")
    pipe = DeliveryPipeline()
    try:
        await pipe.run_full(ReportType.POST, publish=True)
    except Exception as e:
        logger.error("Post-market failed: %s", e, exc_info=True)


async def run_intraday_update():
    if not is_trading_day():
        return
    logger.info("[fast] Running intraday update")
    pipe = DeliveryPipeline()
    try:
        await pipe.run_fast()
    except Exception as e:
        logger.error("Intraday update failed: %s", e, exc_info=True)


async def run_evolution_cycle():
    if not is_trading_day():
        return
    settings = get_settings()
    if not settings.evolution.enabled:
        logger.info("Evolution disabled in settings")
        return
    logger.info("🧬 Running evolution cycle")
    try:
        from src.data.db_manager import SignalDB
        from src.evolution.engine import EvolutionEngine

        db = SignalDB()
        engine = EvolutionEngine(db=db)
        report = engine.run_cycle(db=db)
        logger.info(
            "Evolution done: win_rate=%.1f%% weights_changed=%s",
            report.win_rate * 100, report.weights_changed,
        )
    except Exception as e:
        logger.error("Evolution failed: %s", e, exc_info=True)


async def run_db_cleanup():
    try:
        from src.data.db_manager import SignalDB
        db = SignalDB()
        deleted = db.cleanup_old_signals(keep_days=90)
        if deleted:
            logger.info("DB cleanup: deleted %d rows", deleted)
    except Exception as e:
        logger.error("DB cleanup failed: %s", e)


async def run_daily_intelligence():
    if not is_trading_day():
        return
    settings = get_settings()
    if not settings.phase_g.enabled:
        return
    logger.info("[phase_g] daily_intelligence")
    try:
        from src.intelligence.ingester import KnowledgeIngester
        KnowledgeIngester().run()
    except Exception as e:
        logger.error("daily_intelligence failed: %s", e, exc_info=True)


async def run_recommendation_pool():
    if not is_trading_day():
        return
    settings = get_settings()
    if not settings.phase_g.enabled:
        return
    logger.info("[phase_g] recommendation_pool")
    try:
        from src.recommendation.engine import RecommendationEngine
        RecommendationEngine().build_pool()
    except Exception as e:
        logger.error("recommendation_pool failed: %s", e, exc_info=True)


async def run_auction_monitor():
    if not is_trading_day():
        return
    settings = get_settings()
    if not settings.phase_g.enabled:
        return
    try:
        from src.monitoring.auction import AuctionMonitor
        await asyncio.to_thread(AuctionMonitor().run_once)
    except Exception as e:
        logger.error("auction_monitor failed: %s", e, exc_info=True)


async def run_intraday_monitor():
    if not is_trading_day():
        return
    settings = get_settings()
    if not settings.phase_g.enabled:
        return
    try:
        from src.monitoring.intraday import IntradayMonitor
        from src.portfolio.tracker import PositionTracker
        await asyncio.to_thread(IntradayMonitor().run_once)
        await asyncio.to_thread(PositionTracker().check_rules)
    except Exception as e:
        logger.error("intraday_monitor failed: %s", e, exc_info=True)


async def run_recommendation_review():
    if not is_trading_day():
        return
    settings = get_settings()
    if not settings.phase_g.enabled:
        return
    logger.info("[phase_g] recommendation_review")
    try:
        from src.review.recommendation_review import RecommendationReview
        RecommendationReview().run()
    except Exception as e:
        logger.error("recommendation_review failed: %s", e, exc_info=True)


async def _startup_catch_up():
    from src.data.db_manager import SignalDB

    if not is_trading_day():
        return
    db = SignalDB()
    today_signals = db.get_latest_signals(date.today(), report_type="pre")
    if today_signals:
        logger.info("Today has %d pre signals, skip catch-up", len(today_signals))
        return
    logger.info("Startup catch-up: running pre-market full pipeline")
    try:
        await run_pre_market()
    except Exception as e:
        logger.error("Catch-up failed: %s", e)


def _configure_scheduler(scheduler: AsyncIOScheduler) -> None:
    settings = get_settings()
    tz = settings.schedule.timezone

    pre_h, pre_m = _parse_hm(settings.schedule.pre_market)
    post_h, post_m = _parse_hm(settings.schedule.post_market)
    evo_h, evo_m = _parse_hm(settings.schedule.evolution)
    clean_h, clean_m = _parse_hm(settings.schedule.db_cleanup)

    scheduler.add_job(
        run_pre_market, "cron",
        hour=pre_h, minute=pre_m, day_of_week="mon-fri", timezone=tz,
        id="pre_market", name="盘前 Full",
    )
    for hour in settings.schedule.intraday_hours:
        scheduler.add_job(
            run_intraday_update, "cron",
            hour=hour, minute=0, day_of_week="mon-fri", timezone=tz,
            id=f"intraday_{hour:02d}", name=f"盘中 Fast {hour:02d}:00",
        )
    scheduler.add_job(
        run_post_market, "cron",
        hour=post_h, minute=post_m, day_of_week="mon-fri", timezone=tz,
        id="post_market", name="盘后 Full",
    )
    scheduler.add_job(
        run_evolution_cycle, "cron",
        hour=evo_h, minute=evo_m, day_of_week="mon-fri", timezone=tz,
        id="evolution_cycle", name="进化",
    )
    dow = settings.schedule.db_cleanup_dow[:3].lower()
    scheduler.add_job(
        run_db_cleanup, "cron",
        hour=clean_h, minute=clean_m, day_of_week=dow, timezone=tz,
        id="db_cleanup", name="DB 清理",
    )

    # Phase G jobs
    if settings.phase_g.enabled:
        pg = settings.phase_g.schedule
        di_h, di_m = _parse_hm(pg.daily_intelligence)
        of_h, of_m = _parse_hm(pg.overnight_futures)
        rp_h, rp_m = _parse_hm(pg.recommendation_pool)
        rv_h, rv_m = _parse_hm(pg.recommendation_review)
        auc_start_h, auc_start_m = _parse_hm(pg.auction_start)
        auc_end_h, auc_end_m = _parse_hm(pg.auction_end)

        scheduler.add_job(
            run_daily_intelligence, "cron",
            hour=di_h, minute=di_m, day_of_week="mon-fri", timezone=tz,
            id="daily_intelligence", name="日更知识库",
        )
        scheduler.add_job(
            run_daily_intelligence, "cron",
            hour=of_h, minute=of_m, day_of_week="mon-fri", timezone=tz,
            id="overnight_futures", name="外盘期货",
        )
        scheduler.add_job(
            run_recommendation_pool, "cron",
            hour=rp_h, minute=rp_m, day_of_week="mon-fri", timezone=tz,
            id="recommendation_pool", name="推荐池",
        )
        scheduler.add_job(
            run_recommendation_review, "cron",
            hour=rv_h, minute=rv_m, day_of_week="mon-fri", timezone=tz,
            id="recommendation_review", name="推荐复盘",
        )
        scheduler.add_job(
            run_auction_monitor, "cron",
            hour=f"{auc_start_h}-{auc_end_h}", minute="*", day_of_week="mon-fri", timezone=tz,
            id="auction_monitor", name="竞价监测",
        )
        interval = pg.intraday_interval_min
        scheduler.add_job(
            run_intraday_monitor, "cron",
            hour="9-11,13-14", minute=f"*/{interval}", day_of_week="mon-fri", timezone=tz,
            id="intraday_monitor_am", name="盘中监测上午",
        )
        scheduler.add_job(
            run_intraday_monitor, "cron",
            hour="14", minute=f"*/{interval}", day_of_week="mon-fri", timezone=tz,
            id="intraday_monitor_pm", name="盘中监测下午",
        )


async def _run_scheduler():
    scheduler = AsyncIOScheduler()
    _configure_scheduler(scheduler)
    logger.info("Scheduler started (%d jobs)", len(scheduler.get_jobs()))
    scheduler.start()
    await _startup_catch_up()
    await asyncio.Event().wait()


async def _run_combined():
    """Single process: APScheduler + uvicorn API."""
    import uvicorn
    from src.api.routes import app

    settings = get_settings()
    config = uvicorn.Config(
        app,
        host=settings.pipeline.api_host,
        port=settings.pipeline.api_port,
        log_level="info",
        loop="asyncio",
    )
    server = uvicorn.Server(config)

    scheduler = AsyncIOScheduler()
    _configure_scheduler(scheduler)
    scheduler.start()
    logger.info("Combined run: scheduler + API :%d", settings.pipeline.api_port)

    await _startup_catch_up()
    await server.serve()


def start_scheduler() -> None:
    try:
        asyncio.run(_run_scheduler())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped")


def start_combined() -> None:
    try:
        asyncio.run(_run_combined())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Combined service stopped")
