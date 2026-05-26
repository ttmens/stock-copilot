"""Signal database — SQLite manager for persistent signal history.

Stores:
- Hard signals (computed deterministically from market data)
- Soft signals (LLM-generated sentiment/events)
- Fused results (final score, signal classification)
- Stock metadata (name, industry, ST status, etc.)

Design principles:
- Append-only: never UPDATE historical rows, preserve audit trail
- Point-in-Time friendly: each row is a (code, date) snapshot
- Query-friendly: composite indexes for common access patterns
"""

import json
import logging
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── Schema definition ────────────────────────────────────────────────

_SCHEMA = """
-- Stock metadata
CREATE TABLE IF NOT EXISTS stock_meta (
    code            TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    industry        TEXT DEFAULT '',
    list_date       TEXT DEFAULT '',
    is_st           INTEGER DEFAULT 0,
    market          TEXT DEFAULT '',  -- 'sh' | 'sz'
    updated_at      TEXT DEFAULT (datetime('now'))
);

-- Signal history (append-only, one row per stock per day per run)
CREATE TABLE IF NOT EXISTS signals (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    code            TEXT NOT NULL,
    trade_date      TEXT NOT NULL,          -- YYYY-MM-DD
    report_type     TEXT NOT NULL DEFAULT 'pre',  -- 'pre' | 'post'
    generated_at    TEXT NOT NULL DEFAULT (datetime('now')),

    -- Hard signals (deterministic computation)
    momentum_20d    REAL DEFAULT NULL,      -- 20-day return
    momentum_5d     REAL DEFAULT NULL,      -- 5-day return
    ma_alignment    TEXT DEFAULT NULL,      -- 'bullish' | 'bearish' | 'neutral'
    volume_ratio    REAL DEFAULT NULL,      -- today_vol / 20d_avg_vol
    pe_percentile   REAL DEFAULT NULL,      -- PE historical percentile (if available)
    main_net_inflow REAL DEFAULT NULL,      -- main force net inflow (yuan)
    north_net_inflow REAL DEFAULT NULL,     -- northbound net inflow (yuan)
    hard_score      REAL DEFAULT NULL,      -- -1.0 to +1.0 composite

    -- Soft signals (LLM-generated)
    llm_sentiment   TEXT DEFAULT NULL,      -- 'bullish' | 'bearish' | 'neutral' | 'unavailable'
    llm_confidence  REAL DEFAULT NULL,      -- 0.0 to 1.0
    llm_events      TEXT DEFAULT NULL,      -- JSON array of events
    llm_summary     TEXT DEFAULT NULL,      -- LLM text summary
    soft_score      REAL DEFAULT NULL,      -- -1.0 to +1.0 mapped from sentiment

    -- Gate signals (rule-based confirmation)
    gate_st_filtered    INTEGER DEFAULT 0,  -- 1 if ST stock filtered out
    gate_limit_filtered INTEGER DEFAULT 0,  -- 1 if 涨跌停 filtered
    gate_volume_confirmed INTEGER DEFAULT 0, -- 1 if volume confirms signal
    gate_score      REAL DEFAULT NULL,      -- 0.0 to 1.0

    -- Fused result
    final_score     REAL DEFAULT NULL,      -- -1.0 to +1.0
    final_signal    TEXT DEFAULT NULL,      -- 'strong_buy' | 'buy' | 'hold' | 'sell' | 'strong_sell'
    signal_label    TEXT DEFAULT NULL,      -- Chinese label for display

    -- Metadata
    fetch_errors    TEXT DEFAULT NULL,      -- JSON array of errors
    data_sources    TEXT DEFAULT NULL,      -- JSON: which sources were used

    UNIQUE(code, trade_date, report_type)
);

-- Performance index
CREATE INDEX IF NOT EXISTS idx_signals_code_date ON signals(code, trade_date);
CREATE INDEX IF NOT EXISTS idx_signals_date ON signals(trade_date);
CREATE INDEX IF NOT EXISTS idx_signals_signal ON signals(final_signal);

-- Signal statistics (pre-computed for fast dashboard queries)
CREATE TABLE IF NOT EXISTS signal_stats (
    code            TEXT PRIMARY KEY,
    total_signals   INTEGER DEFAULT 0,
    bullish_count   INTEGER DEFAULT 0,
    bearish_count   INTEGER DEFAULT 0,
    hold_count      INTEGER DEFAULT 0,
    avg_score       REAL DEFAULT 0,
    win_rate        REAL DEFAULT NULL,
    last_signal     TEXT DEFAULT NULL,
    last_signal_date TEXT DEFAULT NULL,
    streak          INTEGER DEFAULT 0,
    updated_at      TEXT DEFAULT (datetime('now'))
);

-- User watchlist (Phase C)
CREATE TABLE IF NOT EXISTS watchlist (
    code        TEXT PRIMARY KEY,
    name        TEXT NOT NULL DEFAULT '',
    pinned      INTEGER DEFAULT 0,
    sort_order  INTEGER DEFAULT 0,
    tags        TEXT DEFAULT '[]',
    added_at    TEXT DEFAULT (datetime('now'))
);

-- Analysis jobs
CREATE TABLE IF NOT EXISTS jobs (
    id          TEXT PRIMARY KEY,
    job_type    TEXT NOT NULL,
    report_type TEXT DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'pending',
    progress    REAL DEFAULT 0,
    message     TEXT DEFAULT '',
    symbol_count INTEGER DEFAULT 0,
    created_at  TEXT DEFAULT (datetime('now')),
    updated_at  TEXT DEFAULT (datetime('now')),
    finished_at TEXT DEFAULT NULL
);

-- Intraday fast quotes cache
CREATE TABLE IF NOT EXISTS intraday_quotes (
    code        TEXT NOT NULL,
    trade_date  TEXT NOT NULL,
    hard_score  REAL,
    final_score REAL,
    signal_label TEXT,
    updated_at  TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (code, trade_date)
);

-- Static publish metadata
CREATE TABLE IF NOT EXISTS published_meta (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    published_at TEXT NOT NULL,
    report_type TEXT,
    symbol_count INTEGER,
    git_commit  TEXT DEFAULT '',
    source      TEXT DEFAULT 'full'
);

-- Evolution suggestions (user must accept)
CREATE TABLE IF NOT EXISTS evolution_suggestions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT NOT NULL,
    name        TEXT DEFAULT '',
    action      TEXT NOT NULL,
    reason      TEXT DEFAULT '',
    status      TEXT DEFAULT 'pending',
    created_at  TEXT DEFAULT (datetime('now'))
);
"""


@dataclass
class SignalRecord:
    """Represents a single signal row."""
    code: str
    trade_date: date
    report_type: str = "pre"

    # Hard signals
    momentum_20d: Optional[float] = None
    momentum_5d: Optional[float] = None
    ma_alignment: Optional[str] = None
    volume_ratio: Optional[float] = None
    pe_percentile: Optional[float] = None
    main_net_inflow: Optional[float] = None
    north_net_inflow: Optional[float] = None
    hard_score: Optional[float] = None

    # Soft signals
    llm_sentiment: Optional[str] = None
    llm_confidence: Optional[float] = None
    llm_events: Optional[list[dict]] = None
    llm_summary: Optional[str] = None
    soft_score: Optional[float] = None

    # Gate
    gate_st_filtered: bool = False
    gate_limit_filtered: bool = False
    gate_volume_confirmed: bool = False
    gate_score: Optional[float] = None

    # Fused
    final_score: Optional[float] = None
    final_signal: Optional[str] = None
    signal_label: Optional[str] = None

    # Metadata
    fetch_errors: list[str] = field(default_factory=list)
    data_sources: dict = field(default_factory=dict)


class SignalDB:
    """SQLite database manager for signal history."""

    def __init__(self, db_path: str | Path = "data/signals.db"):
        self.db_path = Path(db_path)
        self._persistent_conn: Optional[sqlite3.Connection] = None

        if str(self.db_path) == ":memory:":
            # In-memory: keep a persistent connection so all operations share the same DB
            self._persistent_conn = sqlite3.connect(":memory:")
            self._persistent_conn.row_factory = sqlite3.Row
            self._persistent_conn.executescript(_SCHEMA)
        else:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._init_db()

    @contextmanager
    def _connect(self):
        if self._persistent_conn is not None:
            # Use persistent connection (in-memory mode)
            yield self._persistent_conn
            self._persistent_conn.commit()
        else:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

    def _init_db(self):
        """Create tables if not exists (file mode)."""
        conn = sqlite3.connect(str(self.db_path))
        conn.executescript(_SCHEMA)
        conn.close()
        logger.info("SignalDB initialized: %s", self.db_path)

    # ── Stock metadata ───────────────────────────────────────────

    def upsert_stock(self, code: str, name: str, industry: str = "",
                     market: str = "", is_st: bool = False):
        """Insert or update stock metadata."""
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO stock_meta (code, name, industry, market, is_st)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(code) DO UPDATE SET
                       name = excluded.name,
                       industry = excluded.industry,
                       market = excluded.market,
                       is_st = excluded.is_st,
                       updated_at = datetime('now')""",
                (code, name, industry, market, int(is_st))
            )

    def get_stock(self, code: str) -> Optional[dict]:
        """Get stock metadata."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM stock_meta WHERE code = ?", (code,)
            ).fetchone()
            return dict(row) if row else None

    # ── Signal CRUD ──────────────────────────────────────────────

    def save_signal(self, record: SignalRecord) -> int:
        """Save or replace a signal record. Returns row id."""
        with self._connect() as conn:
            cursor = conn.execute(
                """INSERT INTO signals (
                    code, trade_date, report_type,
                    momentum_20d, momentum_5d, ma_alignment, volume_ratio,
                    pe_percentile, main_net_inflow, north_net_inflow, hard_score,
                    llm_sentiment, llm_confidence, llm_events, llm_summary, soft_score,
                    gate_st_filtered, gate_limit_filtered, gate_volume_confirmed, gate_score,
                    final_score, final_signal, signal_label,
                    fetch_errors, data_sources
                ) VALUES (
                    ?, ?, ?,
                    ?, ?, ?, ?,
                    ?, ?, ?, ?,
                    ?, ?, ?, ?, ?,
                    ?, ?, ?, ?,
                    ?, ?, ?,
                    ?, ?
                )
                ON CONFLICT(code, trade_date, report_type) DO UPDATE SET
                    momentum_20d = excluded.momentum_20d,
                    momentum_5d = excluded.momentum_5d,
                    ma_alignment = excluded.ma_alignment,
                    volume_ratio = excluded.volume_ratio,
                    pe_percentile = excluded.pe_percentile,
                    main_net_inflow = excluded.main_net_inflow,
                    north_net_inflow = excluded.north_net_inflow,
                    hard_score = excluded.hard_score,
                    llm_sentiment = excluded.llm_sentiment,
                    llm_confidence = excluded.llm_confidence,
                    llm_events = excluded.llm_events,
                    llm_summary = excluded.llm_summary,
                    soft_score = excluded.soft_score,
                    gate_st_filtered = excluded.gate_st_filtered,
                    gate_limit_filtered = excluded.gate_limit_filtered,
                    gate_volume_confirmed = excluded.gate_volume_confirmed,
                    gate_score = excluded.gate_score,
                    final_score = excluded.final_score,
                    final_signal = excluded.final_signal,
                    signal_label = excluded.signal_label,
                    fetch_errors = excluded.fetch_errors,
                    data_sources = excluded.data_sources
                RETURNING id""",
                (
                    record.code, str(record.trade_date), record.report_type,
                    record.momentum_20d, record.momentum_5d, record.ma_alignment,
                    record.volume_ratio, record.pe_percentile,
                    record.main_net_inflow, record.north_net_inflow,
                    record.hard_score,
                    record.llm_sentiment, record.llm_confidence,
                    json.dumps(record.llm_events, ensure_ascii=False) if record.llm_events else None,
                    record.llm_summary, record.soft_score,
                    int(record.gate_st_filtered), int(record.gate_limit_filtered),
                    int(record.gate_volume_confirmed), record.gate_score,
                    record.final_score, record.final_signal, record.signal_label,
                    json.dumps(record.fetch_errors) if record.fetch_errors else None,
                    json.dumps(record.data_sources) if record.data_sources else None,
                )
            )
            row = cursor.fetchone()
            return row[0] if row else 0

    def get_signal(self, code: str, trade_date: date,
                   report_type: str = "pre") -> Optional[SignalRecord]:
        """Get a single signal record."""
        with self._connect() as conn:
            row = conn.execute(
                """SELECT * FROM signals
                   WHERE code = ? AND trade_date = ? AND report_type = ?""",
                (code, str(trade_date), report_type)
            ).fetchone()
            if not row:
                return None
            return self._row_to_record(row)

    def get_history(self, code: str, days: int = 30) -> list[SignalRecord]:
        """Get signal history for a stock, most recent first."""
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT * FROM signals
                   WHERE code = ?
                   ORDER BY trade_date DESC
                   LIMIT ?""",
                (code, days)
            ).fetchall()
            return [self._row_to_record(r) for r in rows]

    def get_latest_signals(self, trade_date: date,
                           report_type: str = "pre") -> list[SignalRecord]:
        """Get all signals for a given date."""
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT * FROM signals
                   WHERE trade_date = ? AND report_type = ?
                   ORDER BY final_score DESC""",
                (str(trade_date), report_type)
            ).fetchall()
            return [self._row_to_record(r) for r in rows]

    def get_signal_summary(self, code: str) -> Optional[dict]:
        """Get aggregate statistics for a stock."""
        with self._connect() as conn:
            row = conn.execute(
                """SELECT
                       COUNT(*) as total_signals,
                       SUM(CASE WHEN final_signal IN ('strong_buy','buy') THEN 1 ELSE 0 END) as bullish_count,
                       SUM(CASE WHEN final_signal IN ('strong_sell','sell') THEN 1 ELSE 0 END) as bearish_count,
                       SUM(CASE WHEN final_signal = 'hold' THEN 1 ELSE 0 END) as hold_count,
                       AVG(final_score) as avg_score,
                       MAX(trade_date) as last_date,
                       (SELECT final_signal FROM signals s2
                        WHERE s2.code = signals.code
                        ORDER BY trade_date DESC LIMIT 1) as last_signal
                   FROM signals WHERE code = ?""",
                (code,)
            ).fetchone()
            if not row or row["total_signals"] == 0:
                return None
            return dict(row)

    # ── Batch operations ─────────────────────────────────────────

    def save_batch(self, records: list[SignalRecord]) -> int:
        """Save multiple signals in a transaction. Returns count."""
        count = 0
        with self._connect() as conn:
            for rec in records:
                conn.execute(
                    """INSERT INTO signals (
                        code, trade_date, report_type,
                        momentum_20d, momentum_5d, ma_alignment, volume_ratio,
                        pe_percentile, main_net_inflow, north_net_inflow, hard_score,
                        llm_sentiment, llm_confidence, llm_events, llm_summary, soft_score,
                        gate_st_filtered, gate_limit_filtered, gate_volume_confirmed, gate_score,
                        final_score, final_signal, signal_label,
                        fetch_errors, data_sources
                    ) VALUES (
                        ?, ?, ?,
                        ?, ?, ?, ?,
                        ?, ?, ?, ?,
                        ?, ?, ?, ?, ?,
                        ?, ?, ?, ?,
                        ?, ?, ?,
                        ?, ?
                    )
                    ON CONFLICT(code, trade_date, report_type) DO UPDATE SET
                        momentum_20d = excluded.momentum_20d,
                        llm_sentiment = excluded.llm_sentiment,
                        llm_confidence = excluded.llm_confidence,
                        final_score = excluded.final_score,
                        final_signal = excluded.final_signal,
                        signal_label = excluded.signal_label,
                        fetch_errors = excluded.fetch_errors,
                        data_sources = excluded.data_sources""",
                    (
                        rec.code, str(rec.trade_date), rec.report_type,
                        rec.momentum_20d, rec.momentum_5d, rec.ma_alignment,
                        rec.volume_ratio, rec.pe_percentile,
                        rec.main_net_inflow, rec.north_net_inflow, rec.hard_score,
                        rec.llm_sentiment, rec.llm_confidence,
                        json.dumps(rec.llm_events, ensure_ascii=False) if rec.llm_events else None,
                        rec.llm_summary, rec.soft_score,
                        int(rec.gate_st_filtered), int(rec.gate_limit_filtered),
                        int(rec.gate_volume_confirmed), rec.gate_score,
                        rec.final_score, rec.final_signal, rec.signal_label,
                        json.dumps(rec.fetch_errors) if rec.fetch_errors else None,
                        json.dumps(rec.data_sources) if rec.data_sources else None,
                    )
                )
                count += 1
        logger.info("Batch saved %d signal records", count)
        return count

    # ── Utility ──────────────────────────────────────────────────

    @staticmethod
    def _row_to_record(row) -> SignalRecord:
        """Convert sqlite Row to SignalRecord."""
        d = dict(row)
        return SignalRecord(
            code=d["code"],
            trade_date=date.fromisoformat(d["trade_date"]),
            report_type=d["report_type"],
            momentum_20d=d.get("momentum_20d"),
            momentum_5d=d.get("momentum_5d"),
            ma_alignment=d.get("ma_alignment"),
            volume_ratio=d.get("volume_ratio"),
            pe_percentile=d.get("pe_percentile"),
            main_net_inflow=d.get("main_net_inflow"),
            north_net_inflow=d.get("north_net_inflow"),
            hard_score=d.get("hard_score"),
            llm_sentiment=d.get("llm_sentiment"),
            llm_confidence=d.get("llm_confidence"),
            llm_events=json.loads(d["llm_events"]) if d.get("llm_events") else None,
            llm_summary=d.get("llm_summary"),
            soft_score=d.get("soft_score"),
            gate_st_filtered=bool(d.get("gate_st_filtered", 0)),
            gate_limit_filtered=bool(d.get("gate_limit_filtered", 0)),
            gate_volume_confirmed=bool(d.get("gate_volume_confirmed", 0)),
            gate_score=d.get("gate_score"),
            final_score=d.get("final_score"),
            final_signal=d.get("final_signal"),
            signal_label=d.get("signal_label"),
            fetch_errors=json.loads(d["fetch_errors"]) if d.get("fetch_errors") else [],
            data_sources=json.loads(d["data_sources"]) if d.get("data_sources") else {},
        )

    def close(self):
        """Close any open connections (no-op with context manager pattern)."""
        if self._persistent_conn is not None:
            self._persistent_conn.close()
            self._persistent_conn = None

    # ── Watchlist (Phase C) ─────────────────────────────────────

    def list_watchlist(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM watchlist ORDER BY pinned DESC, sort_order ASC, code ASC"
            ).fetchall()
            return [dict(r) for r in rows]

    def add_watchlist(self, code: str, name: str = "", pinned: bool = False) -> bool:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO watchlist (code, name, pinned)
                   VALUES (?, ?, ?)
                   ON CONFLICT(code) DO UPDATE SET name=excluded.name""",
                (code, name or code, int(pinned)),
            )
            return True

    def remove_watchlist(self, code: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM watchlist WHERE code = ?", (code,))
            return cur.rowcount > 0

    def update_watchlist(self, code: str, pinned: bool | None = None, name: str | None = None) -> bool:
        with self._connect() as conn:
            if pinned is not None:
                conn.execute("UPDATE watchlist SET pinned = ? WHERE code = ?", (int(pinned), code))
            if name is not None:
                conn.execute("UPDATE watchlist SET name = ? WHERE code = ?", (name, code))
            return True

    def import_watchlist_codes(self, codes: list[str], names: dict[str, str] | None = None) -> int:
        names = names or {}
        count = 0
        for code in codes:
            self.add_watchlist(code, names.get(code, code))
            count += 1
        return count

    # ── Jobs ────────────────────────────────────────────────────

    def create_job(self, job_id: str, job_type: str, report_type: str = "") -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO jobs (id, job_type, report_type, status)
                   VALUES (?, ?, ?, 'pending')""",
                (job_id, job_type, report_type),
            )

    def update_job(self, job_id: str, status: str, progress: float = 0, message: str = "",
                   symbol_count: int = 0) -> None:
        with self._connect() as conn:
            if status in ("completed", "failed"):
                conn.execute(
                    """UPDATE jobs SET status=?, progress=?, message=?, symbol_count=?,
                        updated_at=datetime('now'), finished_at=datetime('now')
                        WHERE id=?""",
                    (status, progress, message, symbol_count, job_id),
                )
            else:
                conn.execute(
                    """UPDATE jobs SET status=?, progress=?, message=?, symbol_count=?,
                        updated_at=datetime('now') WHERE id=?""",
                    (status, progress, message, symbol_count, job_id),
                )

    def get_job(self, job_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            return dict(row) if row else None

    def get_latest_job(self) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
            return dict(row) if row else None

    # ── Intraday ──────────────────────────────────────────────────

    def upsert_intraday(self, code: str, trade_date: date, hard_score: float,
                        final_score: float, signal_label: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO intraday_quotes (code, trade_date, hard_score, final_score, signal_label)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(code, trade_date) DO UPDATE SET
                     hard_score=excluded.hard_score,
                     final_score=excluded.final_score,
                     signal_label=excluded.signal_label,
                     updated_at=datetime('now')""",
                (code, str(trade_date), hard_score, final_score, signal_label),
            )

    def get_intraday_quotes(self, trade_date: date | None = None) -> list[dict]:
        td = str(trade_date or date.today())
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM intraday_quotes WHERE trade_date = ? ORDER BY final_score DESC",
                (td,),
            ).fetchall()
            return [dict(r) for r in rows]

    # ── Published meta ────────────────────────────────────────────

    def record_publish(self, report_type: str, symbol_count: int, git_commit: str = "",
                       source: str = "full") -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO published_meta (published_at, report_type, symbol_count, git_commit, source)
                   VALUES (datetime('now'), ?, ?, ?, ?)""",
                (report_type, symbol_count, git_commit, source),
            )

    def get_last_published(self) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM published_meta ORDER BY id DESC LIMIT 1"
            ).fetchone()
            return dict(row) if row else None

    # ── Evolution suggestions ─────────────────────────────────────

    def add_evolution_suggestion(self, code: str, action: str, name: str = "",
                                   reason: str = "") -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO evolution_suggestions (code, name, action, reason)
                   VALUES (?, ?, ?, ?)""",
                (code, name, action, reason),
            )
            return cur.lastrowid or 0

    def list_evolution_suggestions(self, status: str = "pending") -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM evolution_suggestions WHERE status = ? ORDER BY id DESC",
                (status,),
            ).fetchall()
            return [dict(r) for r in rows]

    def resolve_evolution_suggestion(self, suggestion_id: int, accept: bool) -> None:
        status = "accepted" if accept else "rejected"
        with self._connect() as conn:
            conn.execute(
                "UPDATE evolution_suggestions SET status = ? WHERE id = ?",
                (status, suggestion_id),
            )

    def cleanup_old_signals(self, keep_days: int = 90) -> int:
        """Delete signal records older than keep_days.

        Preserves stock_meta and only cleans the append-only signals table.
        Returns number of deleted rows.
        """
        from datetime import timedelta
        cutoff = (date.today() - timedelta(days=keep_days)).isoformat()
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM signals WHERE trade_date < ?", (cutoff,)
            )
            deleted = cursor.rowcount
            # Also clean up signal_stats (will be recomputed on next analysis)
            conn.execute("DELETE FROM signal_stats")
            if deleted:
                conn.execute("VACUUM")
            return deleted

    def __repr__(self):
        return f"SignalDB({self.db_path})"
