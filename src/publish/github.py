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
    Validates git config and token before attempting push.
    """
    settings = get_settings()
    type_label = "盘前" if report.report_type.value == "pre" else "盘后"
    commit_msg = f"publish: report {report.trade_date}-{report.report_type.value} {type_label}"

    # Pre-flight checks
    if not _check_git_config():
        return False

    try:
        os.chdir(_PROJECT_ROOT)

        # Stage docs/ (GitHub Pages source)
        result = _run("git", "add", "docs/")
        logger.debug("git add stdout: %s", result.stdout)

        # Check if there are changes
        result = _run("git", "diff", "--cached", "--quiet", check=False)
        if result.returncode == 0:
            logger.info("No changes to publish")
            return True

        # Commit
        result = _run("git", "commit", "-m", commit_msg)
        logger.info("Committed: %s", result.stdout.strip())

        # Push
        result = _run("git", "push", "origin", "main")
        logger.info("Pushed to GitHub: %s", result.stdout.strip() or result.stderr.strip())

        logger.info("Published to GitHub: %s", commit_msg)
        return True

    except subprocess.CalledProcessError as e:
        logger.error("Publish failed (exit %d): %s", e.returncode, e.stderr.strip() or e.stdout.strip())
        return False
    except Exception as e:
        logger.error("Publish failed: %s", e, exc_info=True)
        return False


def _check_git_config() -> bool:
    """Validate git environment before publishing."""
    try:
        os.chdir(_PROJECT_ROOT)

        # Check git user config
        result = _run("git", "config", "user.name", check=False)
        if result.returncode != 0 or not result.stdout.strip():
            logger.warning("Git user.name not configured — set with: git config user.name 'Your Name'")

        result = _run("git", "config", "user.email", check=False)
        if result.returncode != 0 or not result.stdout.strip():
            logger.warning("Git user.email not configured — set with: git config user.email 'you@example.com'")

        # Check if we can reach origin
        result = _run("git", "remote", "get-url", "origin", check=False)
        if result.returncode != 0:
            logger.error("No git remote 'origin' found in %s", _PROJECT_ROOT)
            return False

        remote_url = result.stdout.strip()
        logger.info("Git remote: %s", remote_url)

        # Check if token is embedded in URL (not recommended but works for PAT)
        if "@" in remote_url:
            logger.debug("Remote URL contains credentials (PAT embedded)")
        elif "github.com" in remote_url and ":" in remote_url:
            logger.warning("SSH remote detected — ensure SSH key is loaded (ssh-add -l)")

        return True

    except Exception as e:
        logger.error("Git config check failed: %s", e)
        return False


def _run(*args: str, check: bool = True):
    """Run subprocess command with full output capture."""
    logger.debug("Running: %s", " ".join(args))
    return subprocess.run(args, capture_output=True, text=True, check=check)
