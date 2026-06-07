"""Data source health monitoring.

Tracks success/failure/timeout for each data provider and method.
Enables:
- Alerting on degraded sources
- Automatic fallback decisions
- Historical reliability analysis

Usage:
    from src.data.health_monitor import monitor
    
    # Record a successful fetch
    monitor.record_success("eastmoney", "get_stock_info", latency_ms=150)
    
    # Record a failure
    monitor.record_failure("eastmoney", "get_stock_info", "Connection timeout")
    
    # Get health status
    status = monitor.get_health("eastmoney", "2024-01-15")
"""

import logging
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class HealthRecord:
    """A single health check record."""
    provider: str
    method: str
    trade_date: str
    status: str  # 'success' | 'failure' | 'timeout' | 'fallback'
    latency_ms: Optional[int] = None
    error_message: Optional[str] = None
    created_at: Optional[str] = None


@dataclass
class HealthSummary:
    """Aggregated health summary for a provider on a date."""
    provider: str
    trade_date: str
    total_calls: int
    success_count: int
    failure_count: int
    timeout_count: int
    fallback_count: int
    avg_latency_ms: Optional[float]
    success_rate: float
    status: str  # 'healthy' | 'degraded' | 'down'


class DataSourceHealthMonitor:
    """Monitor data source health by recording fetch outcomes."""
    
    def __init__(self, db_path: str | Path = "data/signals.db"):
        self.db_path = Path(db_path)
    
    def _connect(self) -> sqlite3.Connection:
        """Get a database connection."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn
    
    def record(
        self,
        provider: str,
        method: str,
        status: str,
        latency_ms: Optional[int] = None,
        error_message: Optional[str] = None,
        trade_date: Optional[str] = None,
    ) -> None:
        """Record a data fetch outcome.
        
        Args:
            provider: Data provider name (e.g., 'eastmoney', 'tencent')
            method: Method name (e.g., 'get_stock_info', 'get_kline')
            status: One of 'success', 'failure', 'timeout', 'fallback'
            latency_ms: Request latency in milliseconds
            error_message: Error details if failed
            trade_date: Trade date (defaults to today)
        """
        if trade_date is None:
            trade_date = date.today().isoformat()
        
        try:
            conn = self._connect()
            conn.execute(
                """INSERT INTO data_source_health 
                   (provider, method, trade_date, status, latency_ms, error_message)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (provider, method, trade_date, status, latency_ms, error_message)
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning("Failed to record health check: %s", e)
    
    def record_success(
        self,
        provider: str,
        method: str,
        latency_ms: Optional[int] = None,
        trade_date: Optional[str] = None,
    ) -> None:
        """Record a successful fetch."""
        self.record(provider, method, "success", latency_ms, None, trade_date)
    
    def record_failure(
        self,
        provider: str,
        method: str,
        error_message: str,
        latency_ms: Optional[int] = None,
        trade_date: Optional[str] = None,
    ) -> None:
        """Record a failed fetch."""
        self.record(provider, method, "failure", latency_ms, error_message, trade_date)
    
    def record_timeout(
        self,
        provider: str,
        method: str,
        latency_ms: Optional[int] = None,
        trade_date: Optional[str] = None,
    ) -> None:
        """Record a timed-out fetch."""
        self.record(provider, method, "timeout", latency_ms, "Request timeout", trade_date)
    
    def record_fallback(
        self,
        provider: str,
        method: str,
        reason: str,
        latency_ms: Optional[int] = None,
        trade_date: Optional[str] = None,
    ) -> None:
        """Record a fallback to alternative source."""
        self.record(provider, method, "fallback", latency_ms, reason, trade_date)
    
    def get_health(self, provider: str, trade_date: str) -> Optional[HealthSummary]:
        """Get health summary for a provider on a specific date.
        
        Returns:
            HealthSummary if data exists, None otherwise.
        """
        conn = self._connect()
        cursor = conn.execute(
            """SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as success,
                SUM(CASE WHEN status = 'failure' THEN 1 ELSE 0 END) as failure,
                SUM(CASE WHEN status = 'timeout' THEN 1 ELSE 0 END) as timeout,
                SUM(CASE WHEN status = 'fallback' THEN 1 ELSE 0 END) as fallback,
                AVG(latency_ms) as avg_latency
               FROM data_source_health
               WHERE provider = ? AND trade_date = ?""",
            (provider, trade_date)
        )
        row = cursor.fetchone()
        conn.close()
        
        if not row or row["total"] == 0:
            return None
        
        total = row["total"]
        success = row["success"] or 0
        success_rate = success / total if total > 0 else 0
        
        # Determine status
        if success_rate >= 0.9:
            status = "healthy"
        elif success_rate >= 0.5:
            status = "degraded"
        else:
            status = "down"
        
        return HealthSummary(
            provider=provider,
            trade_date=trade_date,
            total_calls=total,
            success_count=success,
            failure_count=row["failure"] or 0,
            timeout_count=row["timeout"] or 0,
            fallback_count=row["fallback"] or 0,
            avg_latency_ms=row["avg_latency"],
            success_rate=success_rate,
            status=status,
        )
    
    def get_all_health(self, trade_date: str) -> list[HealthSummary]:
        """Get health summary for all providers on a date."""
        conn = self._connect()
        cursor = conn.execute(
            """SELECT DISTINCT provider FROM data_source_health WHERE trade_date = ?""",
            (trade_date,)
        )
        providers = [row["provider"] for row in cursor.fetchall()]
        conn.close()
        
        return [h for p in providers if (h := self.get_health(p, trade_date)) is not None]
    
    def get_recent_health(self, provider: str, days: int = 7) -> list[HealthSummary]:
        """Get health summary for a provider over recent days."""
        conn = self._connect()
        cursor = conn.execute(
            """SELECT DISTINCT trade_date FROM data_source_health 
               WHERE provider = ? 
               ORDER BY trade_date DESC LIMIT ?""",
            (provider, days)
        )
        dates = [row["trade_date"] for row in cursor.fetchall()]
        conn.close()
        
        return [h for d in dates if (h := self.get_health(provider, d)) is not None]


# Global singleton instance
monitor = DataSourceHealthMonitor()
