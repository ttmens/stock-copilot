"""Tests for report generator."""

from datetime import datetime

from src.data.models import (
    AgentResult,
    AgentStatus,
    MarketOverview,
    MovingAverages,
    ReportType,
    StockAnalysis,
    StockSnapshot,
)
from src.reports.generator import generate_report, _compute_overall, DISCLAIMER


class TestComputeOverall:
    def test_bullish_majority(self):
        snap = StockSnapshot(code="000001", name="test", fetched_at=datetime.now())
        a = StockAnalysis(
            snapshot=snap,
            technical=AgentResult(agent_name="technical", status=AgentStatus.OK, sentiment="bullish"),
            fundamental=AgentResult(agent_name="fundamental", status=AgentStatus.OK, sentiment="bullish"),
            capital=AgentResult(agent_name="capital", status=AgentStatus.OK, sentiment="bearish"),
        )
        _compute_overall(a)
        assert a.overall_sentiment == "bullish"

    def test_bearish_majority(self):
        snap = StockSnapshot(code="000001", name="test", fetched_at=datetime.now())
        a = StockAnalysis(
            snapshot=snap,
            technical=AgentResult(agent_name="technical", status=AgentStatus.OK, sentiment="bearish"),
            fundamental=AgentResult(agent_name="fundamental", status=AgentStatus.OK, sentiment="bearish"),
            capital=AgentResult(agent_name="capital", status=AgentStatus.OK, sentiment="bullish"),
        )
        _compute_overall(a)
        assert a.overall_sentiment == "bearish"

    def test_neutral_mixed(self):
        snap = StockSnapshot(code="000001", name="test", fetched_at=datetime.now())
        a = StockAnalysis(
            snapshot=snap,
            technical=AgentResult(agent_name="technical", status=AgentStatus.OK, sentiment="bullish"),
            fundamental=AgentResult(agent_name="fundamental", status=AgentStatus.OK, sentiment="bearish"),
            capital=AgentResult(agent_name="capital", status=AgentStatus.OK, sentiment="neutral"),
        )
        _compute_overall(a)
        assert a.overall_sentiment == "neutral"

    def test_all_unavailable(self):
        snap = StockSnapshot(code="000001", name="test", fetched_at=datetime.now())
        a = StockAnalysis(
            snapshot=snap,
            technical=AgentResult(agent_name="technical", status=AgentStatus.UNAVAILABLE, sentiment="neutral"),
            fundamental=AgentResult(agent_name="fundamental", status=AgentStatus.UNAVAILABLE, sentiment="neutral"),
            capital=AgentResult(agent_name="capital", status=AgentStatus.UNAVAILABLE, sentiment="neutral"),
        )
        _compute_overall(a)
        assert a.overall_sentiment == "neutral"


class TestGenerateReport:
    def test_basic_report(self, tmp_path):
        snap = StockSnapshot(
            code="600519", name="茅台",
            fetched_at=datetime.now(),
            ma=MovingAverages(ma5=1400, ma10=1380, ma20=1360),
        )
        analysis = StockAnalysis(
            snapshot=snap,
            technical=AgentResult(agent_name="technical", status=AgentStatus.OK, sentiment="bullish", summary="Test"),
            fundamental=AgentResult(agent_name="fundamental", status=AgentStatus.UNAVAILABLE, sentiment="neutral"),
            capital=AgentResult(agent_name="capital", status=AgentStatus.UNAVAILABLE, sentiment="neutral"),
        )
        market = MarketOverview(close=3200.0, change_pct=1.0)

        report = generate_report([analysis], ReportType.PRE, market)

        assert report.markdown is not None
        assert DISCLAIMER in report.markdown
        assert "600519" in report.markdown
        assert "贵州茅台" in report.markdown or "茅台" in report.markdown
        assert report.file_path is not None

    def test_failed_symbols_included(self):
        snap = StockSnapshot(code="000001", name="test", fetched_at=datetime.now())
        analysis = StockAnalysis(
            snapshot=snap,
            technical=AgentResult(agent_name="technical", status=AgentStatus.OK, sentiment="neutral"),
            fundamental=AgentResult(agent_name="fundamental", status=AgentStatus.UNAVAILABLE),
            capital=AgentResult(agent_name="capital", status=AgentStatus.UNAVAILABLE),
        )

        report = generate_report(
            [analysis], ReportType.POST,
            failed_symbols=["300750"],
        )
        assert "300750" in report.markdown
        assert "数据获取失败" in report.markdown
