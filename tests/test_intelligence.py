"""Tests for Phase G intelligence module."""

from datetime import date
from unittest.mock import patch

import pytest

from src.data.db_manager import SignalDB
from src.intelligence.ingester import KnowledgeIngester
from src.intelligence.overnight import apply_overnight_rules, build_overnight_snapshot
from src.intelligence.futures import build_futures_snapshot


@pytest.fixture
def mem_db():
    return SignalDB(":memory:")


class TestOvernightRules:
    def test_strong_foreign_impact(self):
        indices = {"nasdaq": {"change_pct": 2.5}}
        rules = apply_overnight_rules(indices)
        assert rules["strong_foreign_impact"] is True

    def test_no_impact(self):
        indices = {"nasdaq": {"change_pct": 0.5}}
        rules = apply_overnight_rules(indices)
        assert rules["strong_foreign_impact"] is False


class TestKnowledgeIngester:
    @patch("src.intelligence.ingester._fetch_hot_events")
    @patch("src.intelligence.ingester.build_overnight_snapshot")
    @patch("src.intelligence.ingester.build_futures_snapshot")
    def test_run_saves_digest(self, mock_fut, mock_ov, mock_hot, mem_db):
        mock_hot.return_value = [{"rank": 1, "title": "测试热点", "impact_score": 0.8, "sector_tags": []}]
        mock_ov.return_value = {"indices": {}, "strong_foreign_impact": False, "sector_hints": []}
        mock_fut.return_value = {"contracts": [], "sector_hints": []}

        ingester = KnowledgeIngester(mem_db)
        result = ingester.run(date(2026, 5, 26))

        assert result["trade_date"] == "2026-05-26"
        assert len(result["hot_events"]) == 1
        stored = mem_db.get_daily_digest("2026-05-26")
        assert stored is not None
        assert stored["macro_summary"]


class TestFuturesSnapshot:
    @patch("src.intelligence.futures.fetch_futures")
    def test_build_snapshot(self, mock_fetch):
        mock_fetch.return_value = [{"symbol": "原油", "change_pct": 2.0, "sector_hint": "energy"}]
        snap = build_futures_snapshot(date(2026, 5, 26))
        assert snap["trade_date"] == "2026-05-26"
        assert "energy" in snap["sector_hints"]
