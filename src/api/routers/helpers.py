"""Shared helpers for API routers."""

import json
import logging
import sqlite3
from datetime import date
from pathlib import Path
from typing import Optional

from fastapi import HTTPException

from src.config import get_settings

logger = logging.getLogger(__name__)


def read_latest_json() -> dict:
    """Safely read latest.json with fallback and error handling."""
    data_dir = Path(get_settings().site.data_dir)
    json_path = data_dir / "latest.json"
    if not json_path.exists():
        docs_path = Path("docs/data/latest.json")
        if docs_path.exists():
            json_path = docs_path
        else:
            raise HTTPException(status_code=404, detail="latest.json not found")
    try:
        return json.loads(json_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        logger.error("Failed to parse latest.json: %s", e)
        raise HTTPException(status_code=500, detail=f"latest.json parse error: {e}")


def safe_parse_date(date_str: Optional[str]):
    """Safely parse ISO date string, raise 400 on failure."""
    if not date_str:
        return None
    try:
        return date.fromisoformat(date_str)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail=f"Invalid date format: {date_str} (expected YYYY-MM-DD)")


def get_db_stats() -> dict:
    """Safely query DB stats with proper connection cleanup."""
    db_path = Path("data/signals.db")
    if not db_path.exists():
        return {}
    conn = None
    try:
        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()
        stats = {}
        cur.execute("SELECT COUNT(*) FROM signals")
        stats["signal_count"] = cur.fetchone()[0]
        cur.execute("SELECT COUNT(DISTINCT code) FROM signals")
        stats["unique_stocks"] = cur.fetchone()[0]
        cur.execute("SELECT MAX(trade_date) FROM signals")
        stats["last_signal_date"] = cur.fetchone()[0]
        return stats
    except Exception:
        return {}
    finally:
        if conn:
            conn.close()
