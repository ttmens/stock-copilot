"""Tests for hard signal computation, signal fusion, and SignalDB."""

import tempfile
from datetime import date

import pytest

from src.data.hard_signals import HardSignals, compute_hard_signals
from src.data.signal_fusion import fuse_signals, SIGNAL_LABELS
from src.data.db_manager import SignalDB, SignalRecord
from src.data.models import (
    OHLCVBar, MovingAverages, ValuationInfo, CapitalFlow,
    AgentResult, AgentStatus,
)


# ── Test fixtures ──────────────────────────────────────────────────

@pytest.fixture
def sample_bars():
    """20 days of rising price data."""
    return [
        OHLCVBar(date=date(2025, 1, i + 1),
                 open=100 + i, high=105 + i, low=95 + i,
                 close=100 + i * 1.5, volume=1e6 + i * 1e4)
        for i in range(20)
    ]


@pytest.fixture
def sample_ma():
    return MovingAverages(ma5=115.0, ma10=110.0, ma20=105.0)


@pytest.fixture
def sample_valuation():
    return ValuationInfo(pe_ttm=18.0, pb=3.0, mcap=1e11)


@pytest.fixture
def sample_capital():
    return CapitalFlow(main_net_inflow=5e7, north_net_inflow=2e7)


# ── Hard Signal Tests ──────────────────────────────────────────────

class TestHardSignals:
    def test_bullish_composite(self, sample_bars, sample_ma, sample_valuation):
        hs = compute_hard_signals(sample_bars, sample_ma, sample_valuation)
        assert hs.composite_score > 0.5
        assert hs.ma_alignment == "bullish"
        assert hs.momentum_5d > 0

    def test_bearish_ma(self, sample_bars):
        # Inverted MA = bearish (close below all MAs, and MAs in descending order)
        bear_ma = MovingAverages(ma5=150.0, ma10=160.0, ma20=170.0)
        hs = compute_hard_signals(sample_bars, bear_ma)
        assert hs.ma_alignment == "bearish"
        assert hs.ma_score < 0

    def test_no_data(self):
        hs = compute_hard_signals([])
        assert hs.composite_score == 0.0
        assert hs.ma_alignment is None

    def test_volume_breakout(self):
        bars = [
            OHLCVBar(date=date(2025, 1, i + 1),
                     open=100, high=101, low=99, close=100,
                     volume=1e6)
            for i in range(19)
        ]
        # Today has 3x volume
        bars.append(
            OHLCVBar(date=date(2025, 1, 20),
                     open=100, high=105, low=99, close=104,
                     volume=3e6)
        )
        hs = compute_hard_signals(bars)
        assert hs.volume_ratio is not None
        assert hs.volume_ratio > 1.5

    def test_valuation_low_pe(self, sample_bars):
        cheap = ValuationInfo(pe_ttm=8.0, pb=1.0)
        hs = compute_hard_signals(sample_bars, valuation=cheap)
        assert hs.valuation_score > 0  # Low PE = bullish value

    def test_valuation_high_pe(self, sample_bars):
        expensive = ValuationInfo(pe_ttm=60.0, pb=10.0)
        hs = compute_hard_signals(sample_bars, valuation=expensive)
        assert hs.valuation_score < 0  # High PE = bearish value


# ── Signal Fusion Tests ────────────────────────────────────────────

class TestSignalFusion:
    def test_strong_buy_agreement(self, sample_bars, sample_ma):
        hard = compute_hard_signals(sample_bars, sample_ma)
        agents = {
            "technical": AgentResult(agent_name="technical", status=AgentStatus.OK, sentiment="bullish"),
            "capital": AgentResult(agent_name="capital", status=AgentStatus.OK, sentiment="bullish"),
        }
        r = fuse_signals("600519", "贵州茅台", hard=hard, agents=agents)
        assert r.final_score > 0.5
        assert r.final_signal in ("strong_buy", "buy")
        assert r.confidence > 0.7

    def test_conflicting_signals(self, sample_bars, sample_ma):
        hard = compute_hard_signals(sample_bars, sample_ma)  # bullish
        agents = {
            "technical": AgentResult(agent_name="technical", status=AgentStatus.OK, sentiment="bearish"),
        }
        r = fuse_signals("000001", "平安银行", hard=hard, agents=agents)
        # Conflicting = lower confidence
        assert r.confidence < 0.7

    def test_st_filter(self):
        r = fuse_signals("000002", "ST某股", is_st=True)
        assert r.final_signal == "hold"
        assert "过滤" in r.signal_label

    def test_no_data(self):
        r = fuse_signals("300750", "宁德时代")
        assert r.final_signal == "hold"
        assert r.confidence == 0.0

    def test_hard_only(self, sample_bars, sample_ma):
        hard = compute_hard_signals(sample_bars, sample_ma)
        r = fuse_signals("600519", "贵州茅台", hard=hard)
        assert r.data_available["hard"] is True
        assert r.data_available["soft"] is False


# ── SignalDB Tests ─────────────────────────────────────────────────

class TestSignalDB:
    def test_upsert_and_query(self):
        db = SignalDB(":memory:")
        db.upsert_stock("600519", "贵州茅台", industry="白酒", market="sh")
        stock = db.get_stock("600519")
        assert stock["name"] == "贵州茅台"
        assert stock["industry"] == "白酒"

    def test_save_and_retrieve_signal(self):
        db = SignalDB(":memory:")
        rec = SignalRecord(
            code="600519", trade_date=date.today(), report_type="pre",
            momentum_20d=2.5, ma_alignment="bullish",
            final_score=0.6, final_signal="buy", signal_label="🟢 看多",
        )
        row_id = db.save_signal(rec)
        assert row_id > 0

        retrieved = db.get_signal("600519", date.today(), "pre")
        assert retrieved is not None
        assert retrieved.final_score == 0.6
        assert retrieved.final_signal == "buy"

    def test_history(self):
        db = SignalDB(":memory:")
        for i in range(5):
            d = date(2025, 1, 1 + i)
            db.save_signal(SignalRecord(
                code="600519", trade_date=d,
                final_score=0.1 * i, final_signal="hold",
            ))
        history = db.get_history("600519", days=10)
        assert len(history) == 5
        # Most recent first
        assert history[0].trade_date == date(2025, 1, 5)

    def test_batch_save(self):
        db = SignalDB(":memory:")
        records = [
            SignalRecord(code="600519", trade_date=date.today(), final_score=0.5, final_signal="buy"),
            SignalRecord(code="000001", trade_date=date.today(), final_score=-0.3, final_signal="sell"),
            SignalRecord(code="300750", trade_date=date.today(), final_score=0.1, final_signal="hold"),
        ]
        count = db.save_batch(records)
        assert count == 3

        all_today = db.get_latest_signals(date.today())
        assert len(all_today) == 3

    def test_upsert_replaces(self):
        db = SignalDB(":memory:")
        rec1 = SignalRecord(code="600519", trade_date=date.today(), final_score=0.3, final_signal="buy")
        db.save_signal(rec1)
        rec2 = SignalRecord(code="600519", trade_date=date.today(), final_score=0.8, final_signal="strong_buy")
        db.save_signal(rec2)

        result = db.get_signal("600519", date.today())
        assert result.final_score == 0.8
        assert result.final_signal == "strong_buy"

    def test_file_mode(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db = SignalDB(f.name)
            db.upsert_stock("600519", "贵州茅台")
            db.save_signal(SignalRecord(
                code="600519", trade_date=date.today(),
                final_score=0.5, final_signal="buy",
            ))
            result = db.get_stock("600519")
            assert result["name"] == "贵州茅台"
