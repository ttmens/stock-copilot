"""Lightweight schema migration for SQLite.

Tracks schema version and applies incremental migrations.
Migrations are defined as SQL strings in the MIGRATIONS list.

Usage:
    from src.data.schema_migration import run_migrations
    run_migrations(db_path)  # Applies all pending migrations
"""

import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

# Migration list — append-only, never modify past migrations
# Each entry: (version, description, sql)
MIGRATIONS = [
    (1, "Initial schema", """
        CREATE TABLE IF NOT EXISTS stock_meta (
            code TEXT PRIMARY KEY, name TEXT NOT NULL, industry TEXT DEFAULT '',
            list_date TEXT DEFAULT '', is_st INTEGER DEFAULT 0, market TEXT DEFAULT '',
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT NOT NULL,
            trade_date TEXT NOT NULL, report_type TEXT NOT NULL DEFAULT 'pre',
            generated_at TEXT NOT NULL DEFAULT (datetime('now')),
            momentum_20d REAL, momentum_5d REAL, ma_alignment TEXT,
            volume_ratio REAL, pe_percentile REAL, main_net_inflow REAL,
            north_net_inflow REAL, hard_score REAL,
            llm_sentiment TEXT, llm_confidence REAL, llm_events TEXT,
            llm_summary TEXT, soft_score REAL,
            gate_st_filtered INTEGER DEFAULT 0, gate_limit_filtered INTEGER DEFAULT 0,
            gate_volume_confirmed INTEGER DEFAULT 0, gate_score REAL,
            final_score REAL, final_signal TEXT, signal_label TEXT,
            fetch_errors TEXT, data_sources TEXT,
            UNIQUE(code, trade_date, report_type)
        );
        CREATE INDEX IF NOT EXISTS idx_signals_code_date ON signals(code, trade_date);
        CREATE INDEX IF NOT EXISTS idx_signals_date ON signals(trade_date);
    """),
    (2, "Add signal_score_traces for fusion audit trail", """
        CREATE TABLE IF NOT EXISTS signal_score_traces (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            report_type TEXT NOT NULL DEFAULT 'pre',
            
            -- Per-layer scores and weights
            hard_score REAL, hard_weight REAL,
            soft_score REAL, soft_weight REAL,
            gate_score REAL, gate_weight REAL,
            dragon_tiger_score REAL, dragon_tiger_weight REAL,
            announcement_score REAL, announcement_weight REAL,
            
            -- Final result
            final_score REAL,
            final_signal TEXT,
            
            -- Metadata
            weights_version TEXT,
            consensus_bonus REAL DEFAULT 0.0,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_traces_code_date ON signal_score_traces(code, trade_date);
    """),
    (3, "Add data_source_health for provider monitoring", """
        CREATE TABLE IF NOT EXISTS data_source_health (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider TEXT NOT NULL,
            method TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            status TEXT NOT NULL,  -- 'success' | 'failure' | 'timeout' | 'fallback'
            latency_ms INTEGER,
            error_message TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_health_provider ON data_source_health(provider, trade_date);
    """),
]


def _ensure_version_table(conn: sqlite3.Connection) -> None:
    """Create schema_version table if it doesn't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            description TEXT,
            applied_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()


def get_current_version(conn: sqlite3.Connection) -> int:
    """Get the current schema version."""
    _ensure_version_table(conn)
    cursor = conn.execute("SELECT MAX(version) FROM schema_version")
    row = cursor.fetchone()
    return row[0] if row and row[0] is not None else 0


def run_migrations(db_path: str | Path) -> int:
    """Apply all pending migrations.
    
    Returns:
        Number of migrations applied.
    """
    db_path = Path(db_path)
    if not db_path.exists():
        logger.info("Database %s does not exist, will be created on first connection", db_path)
    
    conn = sqlite3.connect(str(db_path))
    try:
        _ensure_version_table(conn)
        current = get_current_version(conn)
        
        pending = [(v, desc, sql) for v, desc, sql in MIGRATIONS if v > current]
        if not pending:
            logger.debug("Schema is up to date (version %d)", current)
            return 0
        
        logger.info("Applying %d migration(s) from version %d", len(pending), current)
        
        for version, description, sql in pending:
            logger.info("  Migration %d: %s", version, description)
            try:
                # Execute migration SQL (may contain multiple statements)
                conn.executescript(sql)
                # Record the migration
                conn.execute(
                    "INSERT INTO schema_version (version, description) VALUES (?, ?)",
                    (version, description)
                )
                conn.commit()
                logger.info("  ✓ Migration %d applied successfully", version)
            except sqlite3.Error as e:
                logger.error("  ✗ Migration %d failed: %s", version, e)
                conn.rollback()
                raise RuntimeError(f"Schema migration {version} failed: {e}") from e
        
        return len(pending)
    finally:
        conn.close()


def get_migration_status(db_path: str | Path) -> dict:
    """Get migration status summary.
    
    Returns:
        Dict with current_version, pending_count, total_migrations.
    """
    db_path = Path(db_path)
    if not db_path.exists():
        return {"current_version": 0, "pending_count": len(MIGRATIONS), "total_migrations": len(MIGRATIONS)}
    
    conn = sqlite3.connect(str(db_path))
    try:
        current = get_current_version(conn)
        pending = sum(1 for v, _, _ in MIGRATIONS if v > current)
        return {
            "current_version": current,
            "pending_count": pending,
            "total_migrations": len(MIGRATIONS),
        }
    finally:
        conn.close()
