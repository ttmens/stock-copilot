"""Stock Relationship Graph — inspired by MiroFish's knowledge graph pattern.

MiroFish uses Zep Cloud to build a temporal knowledge graph with entities, relationships,
and validity windows (valid_at / invalid_at / expired_at). We adapt this pattern for
Stock Copilot: a lightweight SQLite-based relationship graph that tracks how stocks
are connected through industry, concept, supply chain, and capital flow relationships.

Key insight: analyzing a stock in isolation misses critical context. When 600519 (Moutai)
moves, it affects the entire liquor sector. When a concept leader surges, related stocks
often follow. This graph provides that context automatically.
"""

import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class StockRelation:
    """Single relationship between two stocks."""
    source_code: str
    target_code: str
    relation_type: str  # same_industry / same_concept / supply_chain / capital_flow / sentiment_spillover
    strength: float = 1.0  # 0.0 ~ 1.0
    valid_from: str = ""
    valid_to: Optional[str] = None  # NULL = still valid
    source: str = "auto_inferred"  # manual / auto_inferred / evolution
    # Extra info
    industry: str = ""
    concept: str = ""

    def to_dict(self) -> dict:
        return {
            "source_code": self.source_code,
            "target_code": self.target_code,
            "relation_type": self.relation_type,
            "strength": round(self.strength, 2),
            "valid_from": self.valid_from,
            "valid_to": self.valid_to,
            "source": self.source,
            "industry": self.industry,
            "concept": self.concept,
        }


class StockRelationGraph:
    """Lightweight stock relationship graph backed by SQLite.

    MiroFish pattern: entities + relationships + temporal validity.
    - Each stock is a node
    - Relationships have types, strengths, and validity windows
    - Queries find related stocks for context during analysis
    """

    def __init__(self, db_path: str = "data/signals.db"):
        self.db_path = db_path
        self._ensure_tables()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_tables(self):
        """Create relationship tables if they don't exist."""
        conn = self._get_conn()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS stock_relations (
                    source_code TEXT NOT NULL,
                    target_code TEXT NOT NULL,
                    relation_type TEXT NOT NULL,
                    strength REAL DEFAULT 1.0,
                    valid_from DATE DEFAULT (date('now')),
                    valid_to DATE,
                    source TEXT DEFAULT 'auto_inferred',
                    extra_info TEXT DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (source_code, target_code, relation_type)
                );

                CREATE INDEX IF NOT EXISTS idx_relations_source
                    ON stock_relations(source_code);
                CREATE INDEX IF NOT EXISTS idx_relations_target
                    ON stock_relations(target_code);
                CREATE INDEX IF NOT EXISTS idx_relations_type
                    ON stock_relations(relation_type);

                CREATE TABLE IF NOT EXISTS concept_groups (
                    concept_name TEXT NOT NULL,
                    stock_code TEXT NOT NULL,
                    discovered_at DATE DEFAULT (date('now')),
                    PRIMARY KEY (concept_name, stock_code)
                );

                CREATE INDEX IF NOT EXISTS idx_concept_stock
                    ON concept_groups(stock_code);
            """)
            conn.commit()
            logger.info("[stock_graph] Tables ready")
        finally:
            conn.close()

    # ── Write operations ──────────────────────────────────────────

    def add_relation(
        self,
        source_code: str,
        target_code: str,
        relation_type: str,
        strength: float = 1.0,
        industry: str = "",
        concept: str = "",
        source: str = "auto_inferred",
    ):
        """Add or update a relationship."""
        conn = self._get_conn()
        try:
            extra_info = {"industry": industry, "concept": concept}
            conn.execute(
                """
                INSERT INTO stock_relations
                    (source_code, target_code, relation_type, strength, extra_info, source)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_code, target_code, relation_type)
                DO UPDATE SET strength=excluded.strength, extra_info=excluded.extra_info
                """,
                (source_code, target_code, relation_type, strength,
                 str(extra_info), source),
            )
            conn.commit()
        finally:
            conn.close()

    def add_to_concept(self, concept_name: str, stock_code: str):
        """Add stock to a concept group."""
        conn = self._get_conn()
        try:
            conn.execute(
                """
                INSERT OR IGNORE INTO concept_groups (concept_name, stock_code)
                VALUES (?, ?)
                """,
                (concept_name, stock_code),
            )
            conn.commit()
        finally:
            conn.close()

    def add_batch_relations(self, relations: list[StockRelation]):
        """Batch insert relations."""
        conn = self._get_conn()
        try:
            for r in relations:
                extra_info = {"industry": r.industry, "concept": r.concept}
                conn.execute(
                    """
                    INSERT INTO stock_relations
                        (source_code, target_code, relation_type, strength, valid_from, valid_to, extra_info, source)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(source_code, target_code, relation_type) DO NOTHING
                    """,
                    (r.source_code, r.target_code, r.relation_type, r.strength,
                     r.valid_from or date.today().isoformat(), r.valid_to,
                     str(extra_info), r.source),
                )
            conn.commit()
            logger.info("[stock_graph] Batch inserted %d relations", len(relations))
        finally:
            conn.close()

    # ── Read operations ───────────────────────────────────────────

    def get_related(
        self,
        stock_code: str,
        relation_type: Optional[str] = None,
        active_only: bool = True,
        limit: int = 20,
    ) -> list[StockRelation]:
        """Get stocks related to a given stock.

        MiroFish pattern: find connected entities in the graph.
        """
        conn = self._get_conn()
        try:
            query = """
                SELECT source_code, target_code, relation_type, strength,
                       valid_from, valid_to, source, extra_info
                FROM stock_relations
                WHERE (source_code = ? OR target_code = ?)
            """
            params: list = [stock_code, stock_code]

            if active_only:
                query += " AND (valid_to IS NULL OR valid_to > date('now'))"

            if relation_type:
                query += " AND relation_type = ?"
                params.append(relation_type)

            query += " ORDER BY strength DESC LIMIT ?"
            params.append(limit)

            rows = conn.execute(query, params).fetchall()
            relations = []
            for row in rows:
                import json
                extra = {}
                try:
                    extra = json.loads(row["extra_info"]) if row["extra_info"] else {}
                except (json.JSONDecodeError, TypeError):
                    pass
                relations.append(StockRelation(
                    source_code=row["source_code"],
                    target_code=row["target_code"],
                    relation_type=row["relation_type"],
                    strength=row["strength"],
                    valid_from=row["valid_from"],
                    valid_to=row["valid_to"],
                    source=row["source"],
                    industry=extra.get("industry", ""),
                    concept=extra.get("concept", ""),
                ))
            return relations
        finally:
            conn.close()

    def get_concept_stocks(self, stock_code: str, limit: int = 10) -> list[str]:
        """Get other stocks in the same concept groups."""
        conn = self._get_conn()
        try:
            rows = conn.execute(
                """
                SELECT DISTINCT cg2.stock_code
                FROM concept_groups cg1
                JOIN concept_groups cg2 ON cg1.concept_name = cg2.concept_name
                WHERE cg1.stock_code = ? AND cg2.stock_code != ?
                LIMIT ?
                """,
                (stock_code, stock_code, limit),
            ).fetchall()
            return [row["stock_code"] for row in rows]
        finally:
            conn.close()

    def get_industry_stocks(
        self,
        stock_code: str,
        limit: int = 10,
    ) -> list[StockRelation]:
        """Get stocks in the same industry."""
        return self.get_related(stock_code, relation_type="same_industry", limit=limit)

    def get_context_summary(self, stock_code: str) -> dict:
        """Get a summary of all relationships for analysis context.

        Returns a dict suitable for injecting into LLM prompts.
        """
        relations = self.get_related(stock_code, limit=15)
        concept_stocks = self.get_concept_stocks(stock_code, limit=5)

        # Group by type
        by_type: dict[str, list] = {}
        for r in relations:
            if r.relation_type not in by_type:
                by_type[r.relation_type] = []
            by_type[r.relation_type].append(r.to_dict())

        return {
            "stock_code": stock_code,
            "total_relations": len(relations),
            "by_type": by_type,
            "concept_peers": concept_stocks,
        }

    # ── Auto-inference from data ──────────────────────────────────

    def infer_from_watchlist(self, watchlist_items: list) -> int:
        """Infer industry relationships from watchlist data.

        Uses valuation industry field to auto-create same_industry relations.
        """
        from collections import defaultdict

        industry_map: dict[str, list] = defaultdict(list)
        for item in watchlist_items:
            industry = getattr(item, "industry", "") or ""
            if industry and industry != "未知":
                industry_map[industry].append(item.code)

        count = 0
        for industry, codes in industry_map.items():
            if len(codes) < 2:
                continue
            # Create pairwise relations
            for i, code_a in enumerate(codes):
                for code_b in codes[i + 1:]:
                    self.add_relation(
                        source_code=code_a,
                        target_code=code_b,
                        relation_type="same_industry",
                        strength=0.8,
                        industry=industry,
                    )
                    count += 1

        logger.info("[stock_graph] Inferred %d industry relations", count)
        return count

    # ── Maintenance ───────────────────────────────────────────────

    def expire_relations(self, stock_code: str, relation_type: Optional[str] = None):
        """Mark relations as expired (set valid_to = today)."""
        conn = self._get_conn()
        try:
            query = """
                UPDATE stock_relations
                SET valid_to = date('now')
                WHERE source_code = ? AND valid_to IS NULL
            """
            params: list = [stock_code]
            if relation_type:
                query += " AND relation_type = ?"
                params.append(relation_type)
            conn.execute(query, params)
            conn.commit()
        finally:
            conn.close()

    def stats(self) -> dict:
        """Get graph statistics."""
        conn = self._get_conn()
        try:
            total = conn.execute(
                "SELECT COUNT(*) as cnt FROM stock_relations WHERE valid_to IS NULL",
            ).fetchone()["cnt"]
            by_type = conn.execute(
                "SELECT relation_type, COUNT(*) as cnt FROM stock_relations "
                "WHERE valid_to IS NULL GROUP BY relation_type",
            ).fetchall()
            concepts = conn.execute(
                "SELECT COUNT(DISTINCT concept_name) as cnt FROM concept_groups",
            ).fetchone()["cnt"]
            return {
                "active_relations": total,
                "by_type": {row["relation_type"]: row["cnt"] for row in by_type},
                "concept_groups": concepts,
            }
        finally:
            conn.close()
