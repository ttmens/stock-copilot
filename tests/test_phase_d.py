"""Phase D design-debt tests — gate wiring, fusion consistency, announcement filter."""

from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from src.data.hard_signals import compute_hard_signals
from src.data.models import (
    AgentResult,
    AgentStatus,
    MovingAverages,
    OHLCVBar,
    StockAnalysis,
    StockSnapshot,
)
from src.data.signal_fusion import fuse_signals
from src.orchestrator.pipeline import _build_key_basis, _detect_gate_flags
from src.site.generator import _analysis_to_stock_dict


@pytest.fixture
def rising_bars():
    return [
        OHLCVBar(
            date=date(2026, 5, i),
            open=10 + i * 0.1,
            high=11 + i * 0.1,
            low=9 + i * 0.1,
            close=10 + i * 0.1,
            volume=1_000_000,
        )
        for i in range(1, 22)
    ]


class TestGateFlags:
    def test_limit_up_detection(self, rising_bars):
        bars = list(rising_bars)
        prev_close = bars[-2].close
        bars[-1] = OHLCVBar(
            date=date(2026, 5, 22),
            open=prev_close,
            high=prev_close * 1.1,
            low=prev_close,
            close=round(prev_close * 1.099, 2),
            volume=2_000_000,
        )
        snap = StockSnapshot(code="600519", name="贵州茅台", fetched_at=datetime.now(), bars=bars)
        suspended, limit = _detect_gate_flags(snap)
        assert suspended is False
        assert limit is True

    def test_suspended_on_zero_volume(self, rising_bars):
        bars = list(rising_bars)
        last = bars[-1]
        bars[-1] = OHLCVBar(
            date=last.date,
            open=last.open,
            high=last.high,
            low=last.low,
            close=last.close,
            volume=0,
        )
        snap = StockSnapshot(code="000001", name="平安银行", fetched_at=datetime.now(), bars=bars)
        suspended, limit = _detect_gate_flags(snap)
        assert suspended is True
        assert limit is False


class TestFusionConsistency:
    def test_site_dict_matches_pipeline_fusion(self, rising_bars):
        ma = MovingAverages(ma5=11.0, ma10=10.5, ma20=10.0)
        hard = compute_hard_signals(rising_bars, ma)
        agents = {
            "technical": AgentResult(agent_name="technical", status=AgentStatus.OK, sentiment="bullish"),
            "fundamental": AgentResult(agent_name="fundamental", status=AgentStatus.OK, sentiment="neutral"),
            "capital": AgentResult(agent_name="capital", status=AgentStatus.OK, sentiment="bullish"),
        }
        fused = fuse_signals("600519", "贵州茅台", hard=hard, agents=agents, limit_up_down=True)
        analysis = StockAnalysis(
            snapshot=StockSnapshot(code="600519", name="贵州茅台", fetched_at=datetime.now(), bars=rising_bars, ma=ma),
            technical=agents["technical"],
            fundamental=agents["fundamental"],
            capital=agents["capital"],
            overall_sentiment=fused.final_signal,
            overall_focus=fused.signal_label,
            overall_summary="看多 — 测试",
            key_basis=["技术：均线多头排列", "5日动量 +2.0%"],
            confidence=round(fused.confidence, 2),
            signal_breakdown={
                "hard_score": round(fused.hard_score, 3),
                "soft_score": round(fused.soft_score, 3),
                "gate_score": round(fused.gate_score, 3),
                "dragon_tiger_score": round(fused.dragon_tiger_score, 3),
                "announcement_score": round(fused.announcement_score, 3),
                "final_score": round(fused.final_score, 3),
            },
            hard_metrics={
                "hard_score": round(hard.composite_score, 3),
                "momentum_5d": round(hard.momentum_5d, 2) if hard.momentum_5d else None,
                "ma_alignment": hard.ma_alignment,
            },
        )
        stock = _analysis_to_stock_dict(analysis)
        assert stock["overall_sentiment"] == fused.final_signal
        assert stock["signal_breakdown"]["final_score"] == round(fused.final_score, 3)
        assert stock["key_basis"] == analysis.key_basis

    def test_limit_up_lowers_gate_score(self, rising_bars):
        ma = MovingAverages(ma5=11.0, ma10=10.5, ma20=10.0)
        hard = compute_hard_signals(rising_bars, ma)
        agents = {
            "technical": AgentResult(agent_name="technical", status=AgentStatus.OK, sentiment="bullish"),
        }
        normal = fuse_signals("600519", "贵州茅台", hard=hard, agents=agents, limit_up_down=False)
        limited = fuse_signals("600519", "贵州茅台", hard=hard, agents=agents, limit_up_down=True)
        assert limited.gate_score < normal.gate_score


class TestKeyBasis:
    def test_returns_at_most_three(self, rising_bars):
        ma = MovingAverages(ma5=11.0, ma10=10.5, ma20=10.0)
        hard = compute_hard_signals(rising_bars, ma)
        t = AgentResult(agent_name="technical", status=AgentStatus.OK, sentiment="bullish", focus_points=["A", "B"])
        c = AgentResult(agent_name="capital", status=AgentStatus.OK, sentiment="bullish", focus_points=["C"])
        a = AgentResult(agent_name="announcement", status=AgentStatus.OK, sentiment="neutral", focus_points=["D"])
        f = AgentResult(agent_name="fundamental", status=AgentStatus.OK, sentiment="bullish", focus_points=["E"])
        fused = fuse_signals("600519", "贵州茅台", hard=hard, agents={"technical": t, "capital": c, "fundamental": f})
        basis = _build_key_basis(t, c, a, f, hard, fused)
        assert len(basis) <= 3
        assert len(basis) >= 1


class TestAnnouncementDaysFilter:
    @pytest.mark.asyncio
    async def test_old_announcements_filtered(self):
        from src.data.fetcher import DataFetcher

        fetcher = DataFetcher()
        fetcher.announcement_days = 7
        old = date.today() - timedelta(days=30)
        recent = date.today() - timedelta(days=2)

        with patch("src.data.fetcher.ak.stock_notice_report") as mock_report:
            import pandas as pd

            mock_report.return_value = pd.DataFrame([
                {"标题": "旧公告", "日期": old.isoformat(), "链接": ""},
                {"标题": "新公告", "日期": recent.isoformat(), "链接": ""},
            ])
            with patch("src.data.fetcher._retry_sync", side_effect=lambda fn, *a, **k: fn(*a, **k)):
                result = await fetcher._fetch_announcements_chain("600519", [])
        assert len(result) == 1
        assert result[0].title == "新公告"


class TestFundamentalAgentCall:
    @pytest.mark.asyncio
    async def test_pipeline_calls_fundamental_agent(self, rising_bars):
        from src.orchestrator.pipeline import _analyze_and_fuse
        from src.data.models import ReportType

        snap = StockSnapshot(
            code="600519",
            name="贵州茅台",
            fetched_at=datetime.now(),
            bars=rising_bars,
            ma=MovingAverages(ma5=11.0, ma10=10.5, ma20=10.0),
        )
        mock_fund = AsyncMock(
            return_value=AgentResult(
                agent_name="fundamental",
                status=AgentStatus.OK,
                sentiment="bullish",
                summary="基本面良好",
            )
        )
        mock_tech = AsyncMock(return_value=AgentResult(agent_name="technical", status=AgentStatus.OK, sentiment="bullish"))
        mock_cap = AsyncMock(return_value=AgentResult(agent_name="capital", status=AgentStatus.UNAVAILABLE))
        mock_ann = AsyncMock(return_value=AgentResult(agent_name="announcement", status=AgentStatus.UNAVAILABLE))

        with patch("src.orchestrator.pipeline.TechnicalAgent") as Tech, \
             patch("src.orchestrator.pipeline.CapitalAgent") as Cap, \
             patch("src.orchestrator.pipeline.AnnouncementAgent") as Ann, \
             patch("src.orchestrator.pipeline.FundamentalAgent") as Fund:
            Tech.return_value.analyze = mock_tech
            Cap.return_value.analyze = mock_cap
            Ann.return_value.analyze = mock_ann
            Fund.return_value.analyze = mock_fund

            analyses, _ = await _analyze_and_fuse([snap], ReportType.PRE)

        assert len(analyses) == 1
        assert analyses[0].fundamental.summary == "基本面良好"
        mock_fund.assert_awaited_once()
