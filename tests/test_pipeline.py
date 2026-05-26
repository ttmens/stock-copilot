"""Tests for pipeline and site generator."""

import json
import pathlib
from datetime import datetime
from unittest.mock import patch, AsyncMock

from src.data.models import (
    AgentResult,
    AgentStatus,
    MovingAverages,
    ReportType,
    StockAnalysis,
    StockSnapshot,
)


class TestPipeline:
    @patch("src.orchestrator.pipeline.is_trading_day")
    @patch("src.orchestrator.pipeline.fetch_all")
    @patch("src.orchestrator.pipeline._load_watchlist")
    @patch("src.orchestrator.pipeline.generate_report")
    def test_pipeline_calls_all_steps(self, mock_gen, mock_load, mock_fetch, mock_trading):
        import asyncio
        from src.orchestrator.pipeline import run_analysis
        from src.data.models import Report, MarketOverview

        mock_trading.return_value = True
        mock_load.return_value = []
        mock_fetch.return_value = (
            [StockSnapshot(code="000001", name="平安银行", fetched_at=datetime.now())],
            [],
        )

        mock_report = Report(
            report_type=ReportType.PRE,
            generated_at=datetime.now(),
            trade_date=datetime.now().date(),
            analyses=[],
            markdown="# test",
            file_path="/tmp/test.md",
        )
        mock_gen.return_value = mock_report

        async def run():
            return await run_analysis(ReportType.PRE)

        result = asyncio.run(run())
        assert result == mock_report
        mock_fetch.assert_called_once()
        mock_gen.assert_called_once()


class TestSiteGenerator:
    def test_generate_site(self, tmp_path):
        """Generate site to a temporary directory — never touches docs/."""
        from src.reports.generator import generate_report
        from src.site.generator import generate_site
        from src.data.models import MarketOverview

        snap = StockSnapshot(
            code="600519", name="贵州茅台",
            fetched_at=datetime.now(),
            ma=MovingAverages(ma5=1400, ma10=1380, ma20=1360),
        )
        analysis = StockAnalysis(
            snapshot=snap,
            technical=AgentResult(agent_name="technical", status=AgentStatus.OK, sentiment="bullish", summary="均线多头排列"),
            fundamental=AgentResult(agent_name="fundamental", status=AgentStatus.UNAVAILABLE),
            capital=AgentResult(agent_name="capital", status=AgentStatus.UNAVAILABLE),
        )
        market = MarketOverview(close=3200.0, change_pct=1.5)

        report = generate_report([analysis], ReportType.PRE, market)

        # CRITICAL: target_dir=tmp_path ensures test NEVER writes to docs/
        index_path = generate_site(report, target_dir=str(tmp_path))

        assert index_path is not None
        assert "index.html" in index_path

        import pathlib
        index = pathlib.Path(index_path)
        assert index.exists()
        content = index.read_text(encoding="utf-8")
        assert "600519" in content
        assert "贵州茅台" in content
        assert "智策" in content  # brand name (was "Stock Copilot")
        assert "theme.css" in content
        assert "免责声明" in content or "不构成投资建议" in content

        # Verify latest.json in temp dir
        json_path = tmp_path / "data" / "latest.json"
        assert json_path.exists()
        import json
        data = json.loads(json_path.read_text(encoding="utf-8"))
        assert "meta" in data
        assert "stocks" in data
        assert len(data["stocks"]) == 1

    def test_generate_site_multiple_stocks(self, tmp_path):
        """Generate site with multiple stocks — still isolated to tmp_path."""
        from src.reports.generator import generate_report
        from src.site.generator import generate_site
        from src.data.models import MarketOverview

        snapshots = [
            StockSnapshot(code="600519", name="贵州茅台", fetched_at=datetime.now()),
            StockSnapshot(code="000001", name="平安银行", fetched_at=datetime.now()),
            StockSnapshot(code="000333", name="美的集团", fetched_at=datetime.now()),
        ]
        analyses = [
            StockAnalysis(
                snapshot=s,
                technical=AgentResult(agent_name="technical", status=AgentStatus.OK, sentiment="bullish"),
                fundamental=AgentResult(agent_name="fundamental", status=AgentStatus.UNAVAILABLE),
                capital=AgentResult(agent_name="capital", status=AgentStatus.UNAVAILABLE),
            )
            for s in snapshots
        ]
        market = MarketOverview(close=3200.0, change_pct=1.5)

        report = generate_report(analyses, ReportType.PRE, market)
        index_path = generate_site(report, target_dir=str(tmp_path))

        # Verify all 3 stocks rendered
        content = pathlib.Path(index_path).read_text(encoding="utf-8")
        assert "600519" in content
        assert "000001" in content
        assert "000333" in content

        # Verify latest.json has 3 stocks
        json_path = tmp_path / "data" / "latest.json"
        data = json.loads(json_path.read_text(encoding="utf-8"))
        assert len(data["stocks"]) == 3

        # Phase C: per-stock HTML skipped when skip_stock_html; app shell deployed
        from src.config import get_settings
        if get_settings().pipeline.skip_stock_html:
            assert (tmp_path / "app" / "stock.html").exists()
            assert "app/stock.html?code=" in content
        else:
            stock_dir = tmp_path / "stock"
            assert (stock_dir / "600519.html").exists()
            assert (stock_dir / "000001.html").exists()
            assert (stock_dir / "000333.html").exists()
