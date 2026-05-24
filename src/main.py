"""CLI entry point for Stock Copilot."""

import argparse
import logging
import sys
from pathlib import Path

# Add project root to path so src.* imports work
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.config import get_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("stock-copilot")


def cmd_analyze(args: argparse.Namespace) -> None:
    """Run analysis pipeline."""
    from src.orchestrator.pipeline import run_analysis
    from src.data.models import ReportType

    report_type = ReportType(args.type)
    symbols = None
    if args.symbols:
        symbols = [s.strip() for s in args.symbols.split(",")]

    logger.info("Starting analysis: type=%s symbols=%s", report_type.value, symbols or "watchlist")
    report = run_analysis(report_type, symbols)
    logger.info("Report saved to: %s", report.file_path)

    # Also generate site
    try:
        from src.site.generator import generate_site
        generate_site(report)
        logger.info("Site generated successfully")
    except Exception as e:
        logger.warning("Site generation failed: %s", e)

    # Optionally publish
    if args.publish:
        try:
            from src.publish.github import publish_to_github
            publish_to_github(report)
            logger.info("Published to GitHub")
        except Exception as e:
            logger.warning("Publish failed: %s", e)


def cmd_serve(args: argparse.Namespace) -> None:
    """Start FastAPI server."""
    import uvicorn
    logger.info("Starting API server on port %d", args.port)
    uvicorn.run("src.api.routes:app", host="0.0.0.0", port=args.port)


def cmd_schedule(args: argparse.Namespace) -> None:
    """Start APScheduler."""
    from src.scheduler.jobs import start_scheduler
    logger.info("Starting scheduler")
    start_scheduler()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="stock-copilot",
        description="A股辅助决策系统 — AI 驱动的自选股分析工具",
    )
    sub = parser.add_subparsers(dest="command")

    # analyze
    p_analyze = sub.add_parser("analyze", help="Run analysis pipeline")
    p_analyze.add_argument("--type", required=True, choices=["pre", "post"], help="Report type")
    p_analyze.add_argument("--symbols", default=None, help="Comma-separated stock codes (default: watchlist)")
    p_analyze.add_argument("--publish", action="store_true", help="Publish to GitHub after analysis")
    p_analyze.set_defaults(func=cmd_analyze)

    # serve
    p_serve = sub.add_parser("serve", help="Start FastAPI server")
    p_serve.add_argument("--port", type=int, default=8000, help="Port to listen on")
    p_serve.set_defaults(func=cmd_serve)

    # schedule
    p_schedule = sub.add_parser("schedule", help="Start APScheduler daemon")
    p_schedule.set_defaults(func=cmd_schedule)

    args = parser.parse_args()

    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(1)

    # Load settings (triggers env validation)
    settings = get_settings()
    logger.info("Settings loaded: LLM=%s, notify=%s", settings.llm.model, settings.notify.type)

    args.func(args)


if __name__ == "__main__":
    main()
