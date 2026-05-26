"""StockPoolManager — dynamic stock pool management.

Evolves the watchlist:
- Removes stocks with consistently poor prediction accuracy
- Discovers and adds promising stocks from broader market
- Maintains industry diversification
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Default watchlist (50 stocks)
DEFAULT_WATCHLIST = [
    "000001", "000002", "000063", "000100", "000157",
    "000333", "000538", "000568", "000596", "000625",
    "000651", "000661", "000725", "000776", "000858",
    "000895", "002001", "002007", "002027", "002049",
    "002230", "002304", "002352", "002415", "002456",
    "002475", "002594", "002714", "300015", "300059",
    "300122", "300124", "300274", "300750", "300760",
    "600000", "600009", "600016", "600028", "600030",
    "600031", "600036", "600048", "600050", "600104",
    "600276", "600309", "600519", "600585", "600900",
]

# Thresholds
CANDIDATE_POOL_SIZE = 500  # search top 500 by market cap
EVICT_THRESHOLD = 0.35     # win rate below this → candidate for removal
ADD_THRESHOLD = 0.55       # win rate above this for candidates → add
MIN_HOLD_DAYS = 10         # must be in pool for at least 10 days before eviction
MAX_EVICT_PER_CYCLE = 3    # max stocks to remove per evolution cycle
MAX_ADD_PER_CYCLE = 3      # max stocks to add per evolution cycle


@dataclass
class StockStats:
    """Performance stats for a single stock."""
    code: str
    name: str = ""
    industry: str = ""
    days_in_pool: int = 0
    signal_count: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    avg_return: float = 0.0
    last_signal_date: str = ""
    status: str = "active"  # active | candidate_evict | evicted | candidate_add


@dataclass
class PoolReport:
    """Stock pool evolution report."""
    date: str = ""
    pool_size: int = 0
    evicted: list[dict] = field(default_factory=list)
    added: list[dict] = field(default_factory=list)
    candidates: list[dict] = field(default_factory=list)
    industry_distribution: dict = field(default_factory=dict)
    stats: list[StockStats] = field(default_factory=list)


class StockPoolManager:
    """Manage dynamic stock watchlist based on performance."""

    def __init__(
        self,
        watchlist_path: str = "config/watchlist.json",
        db=None,
    ):
        self.watchlist_path = Path(watchlist_path)
        self.db = db
        self.watchlist = self._load_watchlist()
        self.stats: dict[str, StockStats] = {}

    def _load_watchlist(self) -> list[str]:
        if self.watchlist_path.exists():
            try:
                d = json.loads(self.watchlist_path.read_text())
                if isinstance(d, dict):
                    return d.get("stocks", DEFAULT_WATCHLIST)
                return d if isinstance(d, list) else DEFAULT_WATCHLIST
            except Exception as e:
                logger.warning("Failed to load watchlist: %s, using defaults", e)
        return list(DEFAULT_WATCHLIST)

    def save_watchlist(self):
        """Persist current watchlist."""
        self.watchlist_path.parent.mkdir(parents=True, exist_ok=True)
        self.watchlist_path.write_text(
            json.dumps({"stocks": self.watchlist, "version": 2}, ensure_ascii=False, indent=2)
        )

    def analyze_pool(self, db=None) -> PoolReport:
        """Analyze current pool performance and identify candidates."""
        db = db or self.db
        report = PoolReport(date=date.today().isoformat())
        report.pool_size = len(self.watchlist)

        # Build stats for each stock
        for code in self.watchlist:
            stats = self._compute_stock_stats(code, db)
            self.stats[code] = stats
            report.stats.append(stats)

        # Identify eviction candidates
        for code, stats in self.stats.items():
            if stats.days_in_pool >= MIN_HOLD_DAYS and stats.win_rate < EVICT_THRESHOLD:
                stats.status = "candidate_evict"
                report.candidates.append({
                    "code": code,
                    "name": stats.name,
                    "win_rate": round(stats.win_rate, 3),
                    "signal_count": stats.signal_count,
                    "reason": "低胜率",
                })

        # Industry distribution
        industry_count = {}
        for code in self.watchlist:
            if db:
                meta = db.get_stock(code)
                if meta:
                    ind = meta.get("industry", "未知") or "未知"
                    industry_count[ind] = industry_count.get(ind, 0) + 1
        report.industry_distribution = industry_count

        return report

    def evolve(
        self,
        db=None,
        max_evict: int = MAX_EVICT_PER_CYCLE,
        max_add: int = MAX_ADD_PER_CYCLE,
    ) -> PoolReport:
        """Execute one evolution cycle: remove worst, add best candidates."""
        db = db or self.db
        report = self.analyze_pool(db)

        # ── Evict worst performers ──────────────────────────────
        candidates = [s for s in report.stats if s.status == "candidate_evict"]
        candidates.sort(key=lambda s: s.win_rate)

        evicted = []
        for c in candidates[:max_evict]:
            if c.code in self.watchlist:
                self.watchlist.remove(c.code)
                evicted.append({
                    "code": c.code,
                    "name": c.name,
                    "win_rate": round(c.win_rate, 3),
                    "reason": f"胜率{c.win_rate:.1%}低于阈值{EVICT_THRESHOLD:.0%}",
                })
                logger.info("Evicted %s (%s) — win rate %.1f%%", c.code, c.name, c.win_rate * 100)

        report.evicted = evicted

        # ── Add best candidates from broader market ─────────────
        if evicted or len(self.watchlist) < 45:
            added = self._discover_and_add(db, max_add=max_add)
            report.added = added

        # ── Save ────────────────────────────────────────────────
        if evicted or report.added:
            self.save_watchlist()
            logger.info("Pool evolved: -%d +%d, new size %d",
                         len(evicted), len(report.added), len(self.watchlist))

        return report

    def get_watchlist(self) -> list[str]:
        """Return current watchlist."""
        return list(self.watchlist)

    # ── Private helpers ──────────────────────────────────────────

    def _compute_stock_stats(self, code: str, db=None) -> StockStats:
        """Compute performance stats for a single stock."""
        stats = StockStats(code=code)

        if db is None:
            return stats

        # Get metadata
        meta = db.get_stock(code)
        if meta:
            stats.name = meta.get("name", "")
            stats.industry = meta.get("industry", "")

        # Get signal history
        try:
            history = db.get_history(code, days=60)
        except Exception:
            return stats

        if not history:
            return stats

        stats.signal_count = len(history)

        # Compute days in pool (from first signal)
        if history:
            first_date = history[-1].trade_date  # oldest
            stats.days_in_pool = (date.today() - first_date).days
            stats.last_signal_date = str(history[0].trade_date)  # newest

        # This would need actual price verification — for now use signal consistency
        # A better approach: compare consecutive signals with actual returns
        wins = 0
        losses = 0
        total_return = 0.0

        for i in range(len(history) - 1):
            sig = history[i]
            # Use next day's signal direction as proxy for actual outcome
            # (simplified: if signal was bullish and next day's score is higher, count as win)
            if i + 1 < len(history):
                next_sig = history[i + 1]
                if sig.final_score is not None and next_sig.final_score is not None:
                    if sig.final_signal in ("strong_buy", "buy") and next_sig.final_score > sig.final_score:
                        wins += 1
                    elif sig.final_signal in ("strong_sell", "sell") and next_sig.final_score < sig.final_score:
                        wins += 1
                    elif sig.final_signal in ("strong_buy", "buy", "strong_sell", "sell"):
                        losses += 1

        total = wins + losses
        stats.wins = wins
        stats.losses = losses
        stats.win_rate = wins / total if total > 0 else 0.5

        return stats

    def _discover_and_add(self, db, max_add: int = MAX_ADD_PER_CYCLE) -> list[dict]:
        """Discover promising stocks to add to the pool."""
        try:
            import akshare as ak
            # Get top stocks by market cap as candidates
            df = ak.stock_zh_a_spot_em()
            if df is None or df.empty:
                return []

            # Filter: exclude ST, 北交所, new stocks
            df = df[~df["名称"].str.contains("ST", na=False)]
            df = df[~df["代码"].str.startswith(("8", "4"), na=False)]

            # Sort by market cap, take top candidates
            if "总市值" in df.columns:
                df = df.sort_values("总市值", ascending=False).head(CANDIDATE_POOL_SIZE)
            else:
                df = df.head(100)

            current_set = set(self.watchlist)
            added = []

            for _, row in df.iterrows():
                if len(added) >= max_add:
                    break

                code = str(row.get("代码", ""))
                name = str(row.get("名称", ""))

                if not code or code in current_set:
                    continue

                # Skip if already in recent evictions
                if any(e["code"] == code for e in getattr(self, '_recently_evicted', [])):
                    continue

                # Add to pool
                self.watchlist.append(code)
                current_set.add(code)

                # Update metadata in DB
                if db:
                    try:
                        market = "sh" if code.startswith("6") else "sz"
                        industry = str(row.get("行业", "")) if "行业" in df.columns else ""
                        db.upsert_stock(code, name, industry=industry, market=market)
                    except Exception:
                        pass

                added.append({
                    "code": code,
                    "name": name,
                    "reason": "市值前500，新纳入观察",
                })
                logger.info("Added %s (%s) to watchlist", code, name)

            return added

        except Exception as e:
            logger.error("Failed to discover new stocks: %s", e)
            return []
