"""Tests for Phase G recommendation engine."""

from datetime import date

import pytest

from src.data.db_manager import SignalDB, SignalRecord
from src.recommendation.engine import RecommendationEngine, MCAP_LIMIT


@pytest.fixture
def mem_db():
    db = SignalDB(":memory:")
    db.upsert_stock("000001", "平安银行", is_st=False)
    db.upsert_stock("600519", "贵州茅台", is_st=False)
    db.upsert_stock("000002", "ST测试", is_st=True)
    db.save_signal(SignalRecord(code="000001", trade_date=date.today(), final_score=0.5))
    db.save_signal(SignalRecord(code="600519", trade_date=date.today(), final_score=0.8))
    return db


class TestRecommendationEngine:
    def test_hard_filter_st(self, mem_db):
        engine = RecommendationEngine(mem_db)
        assert engine._passes_hard_filter("000002", {"is_st": 1, "name": "ST测试"}) is False

    def test_hard_filter_mcap(self, mem_db):
        engine = RecommendationEngine(mem_db)
        assert engine._passes_hard_filter("600519", {"mcap": MCAP_LIMIT + 1}) is False

    def test_build_pool(self, mem_db):
        mem_db.save_daily_digest(date.today().isoformat(), {
            "hot_events": [], "sector_impact": [{"sector": "银行", "direction": "bullish"}],
            "macro_summary": "", "risk_flags": [], "overnight": {}, "futures": [],
        })
        engine = RecommendationEngine(mem_db)
        result = engine.build_pool(date.today())
        assert result["trade_date"] == date.today().isoformat()
        assert len(result["sectors"]) == 3
        rows = mem_db.get_recommendation_pool(date.today().isoformat())
        assert len(rows) >= 1

    def test_add_auction_stock_limit(self, mem_db):
        engine = RecommendationEngine(mem_db)
        td = date.today().isoformat()
        for i in range(10):
            engine.add_auction_stock(td, f"60000{i}", f"股{i}", 0.5)
        rows = mem_db.get_recommendation_pool(td)
        auction = [r for r in rows if r["source"] == "auction"]
        assert len(auction) <= 9
