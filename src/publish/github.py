"""Publish to GitHub for Pages deployment."""

import logging
import os
import subprocess
from datetime import datetime

from src.config import get_settings
from src.data.models import Report

logger = logging.getLogger(__name__)

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def publish_to_github(report: Report) -> bool:
    """Commit and push site/ to GitHub for Pages deployment.

    Uses docs/ as Pages source (already synced by site generator).
    """
    settings = get_settings()
    type_label = "盘前" if report.report_type.value == "pre" else "盘后"
    commit_msg = f"publish: report {report.trade_date}-{report.report_type.value} {type_label}"

    try:
        os.chdir(_PROJECT_ROOT)

        # Stage docs/ (GitHub Pages source)
        _run("git", "add", "docs/")

        # Check if there are changes
        result = _run("git", "diff", "--cached", "--quiet", check=False)
        if result.returncode == 0:
            logger.info("No changes to publish")
            return True

        # Commit and push
        _run("git", "commit", "-m", commit_msg)
        _run("git", "push", "origin", "main")

        logger.info("Published to GitHub: %s", commit_msg)
        return True

    except Exception as e:
        logger.error("Publish failed: %s", e)
        return False


def _run(*args: str, check: bool = True):
    """Run subprocess command."""
    logger.debug("Running: %s", " ".join(args))
    return subprocess.run(args, capture_output=True, text=True, check=check)
