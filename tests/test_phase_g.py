"""Tests for Phase G monitoring, portfolio, review, session."""

from datetime import date, datetime
from unittest.mock import patch, MagicMock
from zoneinfo import ZoneInfo

import pytest

from src.data.db_manager import SignalDB
from src.monitoring.session import get_market_session, is_auction_window
from src.monitoring.alerts import AlertDispatcher
from src.monitoring.auction import AuctionMonitor
from src.monitoring.intraday import IntradayMonitor
from src.portfolio.tracker import PositionTracker
from src.review.recommendation_review import RecommendationReview


@pytest.fixture
def mem_db():
    return SignalDB(":memory:")


class TestMarketSession:
    @patch("src.monitoring.session.is_trading_day", return_value=True)
    def test_pre_market_session(self, _):
        dt = datetime(2026, 5, 26, 7, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        info = get_market_session(dt)
        assert info["session"] == "pre_market"
        assert info["is_trading_day"] is True

    @patch("src.monitoring.session.is_trading_day", return_value=True)
    def test_auction_window(self, _):
        dt = datetime(2026, 5, 26, 9, 20, tzinfo=ZoneInfo("Asia/Shanghai"))
        assert is_auction_window(dt) is True


class TestAlertDispatcher:
    def test_save_alert(self, mem_db):
        disp = AlertDispatcher(mem_db)
        aid = disp.dispatch("000001", "平安", "test", "测试预警", severity="watch", notify=False)
        assert aid > 0
        feed = disp.get_feed()
        assert feed["unread_count"] == 1


class TestAuctionMonitor:
    @patch("src.monitoring.auction.is_auction_window", return_value=False)
    def test_skips_outside_window(self, _, mem_db):
        result = AuctionMonitor(mem_db).run_once()
        assert result["status"] == "skipped"


class TestIntradayMonitor:
    @patch("src.monitoring.intraday.is_intraday_window", return_value=False)
    def test_skips_outside_window(self, _, mem_db):
        result = IntradayMonitor(mem_db).run_once()
        assert result["status"] == "skipped"


class TestPositionTracker:
    def test_crud(self, mem_db):
        tracker = PositionTracker(mem_db)
        created = tracker.create("000001", "平安", 1000, 10.5)
        assert created["id"] > 0
        positions = tracker.list_positions()
        assert len(positions) == 1
        assert tracker.close(created["id"]) is True
        assert len(tracker.list_positions()) == 0

    def test_delete(self, mem_db):
        tracker = PositionTracker(mem_db)
        pid = tracker.create("000001", "平安", 100, 10.0)["id"]
        assert tracker.delete(pid) is True


class TestRecommendationReview:
    @patch("src.review.recommendation_review.RecommendationReview._fetch_gainers")
    def test_run_hit_miss(self, mock_gainers, mem_db):
        td = date.today().isoformat()
        mem_db.save_recommendation_stock(td, "半导体", 0, "000001", "平安", 0.7)
        mock_gainers.return_value = [
            {"code": "000001", "name": "平安", "change_pct": 6.0},
            {"code": "600000", "name": "浦发", "change_pct": 7.0},
        ]
        review = RecommendationReview(mem_db).run(date.today())
        assert review["hit_count"] == 1
        assert review["miss_count"] >= 1
        assert 0 <= review["hit_rate"] <= 1


class TestPhaseGDatabase:
    def test_daily_digest_roundtrip(self, mem_db):
        mem_db.save_daily_digest("2026-05-26", {
            "hot_events": [{"rank": 1}],
            "sector_impact": [],
            "macro_summary": "test",
            "risk_flags": ["a"],
            "overnight": {"nasdaq": {"change_pct": 1}},
            "futures": [],
        })
        d = mem_db.get_daily_digest("2026-05-26")
        assert d["macro_summary"] == "test"
        assert d["overnight"]["nasdaq"]["change_pct"] == 1

    def test_auction_snapshot(self, mem_db):
        mem_db.save_auction_snapshot("2026-05-26", "000001", {"volume_ratio": 2.1})
        rows = mem_db.get_auction_latest("2026-05-26")
        assert len(rows) == 1
        assert rows[0]["volume_ratio"] == 2.1

    def test_alerts_read(self, mem_db):
        mem_db.save_alert("2026-05-26", "000001", "x", "t", "msg")
        assert mem_db.count_unread_alerts("2026-05-26") == 1
        mem_db.mark_alerts_read("2026-05-26")
        assert mem_db.count_unread_alerts("2026-05-26") == 0
