"""Tests for market breadth scoring module."""

from datetime import datetime

import pytest

from src.analysis.breadth import MarketBreadthScorer
from src.data.models import (
    AgentResult,
    AgentStatus,
    MovingAverages,
    StockAnalysis,
    StockSnapshot,
)


# ── 辅助函数：构造 mock StockAnalysis ───────────────────────────

def _make_analysis(
    code: str = "000001",
    name: str = "测试股票",
    final_score: float = 0.0,
    confidence: float = 0.5,
    capital_score: float = 0.0,
    ma_alignment: str = "neutral",
    contradiction_flags: list | None = None,
) -> StockAnalysis:
    """构造一个用于测试的 StockAnalysis 对象。"""
    return StockAnalysis(
        snapshot=StockSnapshot(
            code=code,
            name=name,
            fetched_at=datetime.now(),
            ma=MovingAverages(),
        ),
        technical=AgentResult(
            agent_name="technical", status=AgentStatus.OK, sentiment="neutral"
        ),
        fundamental=AgentResult(
            agent_name="fundamental", status=AgentStatus.OK, sentiment="neutral"
        ),
        capital=AgentResult(
            agent_name="capital", status=AgentStatus.OK, sentiment="neutral"
        ),
        confidence=confidence,
        signal_breakdown={
            "final_score": final_score,
            "capital_score": capital_score,
            "contradiction_flags": contradiction_flags or [],
        },
        hard_metrics={
            "ma_alignment": ma_alignment,
            "hard_score": final_score * 0.6,
        },
    )


# ── 测试用例 ─────────────────────────────────────────────────────

class TestMarketBreadthScorer:
    """市场广度评分器测试。"""

    def setup_method(self):
        self.scorer = MarketBreadthScorer()

    # ── 空列表处理 ───────────────────────────────────────────

    def test_empty_list_returns_neutral(self):
        """空列表应返回 score=50, zone=neutral。"""
        result = self.scorer.compute([])
        assert result["score"] == 50
        assert result["zone"] == "neutral"
        assert result["recommended_exposure"] == "60-75%"
        assert result["total_stocks"] == 0
        assert result["components"]["bull_ratio"] == 0.0

    # ── 分量计算准确性 ───────────────────────────────────────

    def test_bull_ratio_all_positive(self):
        """所有股票 final_score > 0.2 → bull_ratio = 1.0。"""
        analyses = [
            _make_analysis(code=f"00000{i}", final_score=0.5, confidence=0.8)
            for i in range(1, 6)
        ]
        result = self.scorer.compute(analyses)
        assert result["components"]["bull_ratio"] == 1.0

    def test_bull_ratio_all_negative(self):
        """所有股票 final_score < 0.2 → bull_ratio = 0.0。"""
        analyses = [
            _make_analysis(code=f"00000{i}", final_score=-0.5, confidence=0.3)
            for i in range(1, 6)
        ]
        result = self.scorer.compute(analyses)
        assert result["components"]["bull_ratio"] == 0.0

    def test_bull_ratio_mixed(self):
        """混合场景：3/5 > 0.2 → bull_ratio = 0.6。"""
        analyses = [
            _make_analysis(code="00001", final_score=0.5),
            _make_analysis(code="00002", final_score=0.8),
            _make_analysis(code="00003", final_score=-0.3),
            _make_analysis(code="00004", final_score=0.1),
            _make_analysis(code="00005", final_score=0.3),
        ]
        result = self.scorer.compute(analyses)
        assert result["components"]["bull_ratio"] == pytest.approx(0.6, abs=0.01)

    def test_strong_bull_ratio(self):
        """2/5 > 0.6 → strong_bull_ratio = 0.4。"""
        analyses = [
            _make_analysis(code="00001", final_score=0.8),
            _make_analysis(code="00002", final_score=0.9),
            _make_analysis(code="00003", final_score=0.5),
            _make_analysis(code="00004", final_score=0.3),
            _make_analysis(code="00005", final_score=0.1),
        ]
        result = self.scorer.compute(analyses)
        assert result["components"]["strong_bull_ratio"] == pytest.approx(0.4, abs=0.01)

    def test_avg_confidence(self):
        """平均置信度计算。"""
        analyses = [
            _make_analysis(code="00001", confidence=1.0),
            _make_analysis(code="00002", confidence=0.6),
            _make_analysis(code="00003", confidence=0.2),
        ]
        result = self.scorer.compute(analyses)
        assert result["components"]["avg_confidence"] == pytest.approx(0.6, abs=0.01)

    def test_capital_net_positive(self):
        """2/3 capital_score > 0 → 0.6667。"""
        analyses = [
            _make_analysis(code="00001", capital_score=0.5),
            _make_analysis(code="00002", capital_score=0.1),
            _make_analysis(code="00003", capital_score=-0.3),
        ]
        result = self.scorer.compute(analyses)
        assert result["components"]["capital_net_positive"] == pytest.approx(
            2 / 3, abs=0.01
        )

    def test_ma_bullish_ratio(self):
        """4/5 bullish → 0.8。"""
        analyses = [
            _make_analysis(code="00001", ma_alignment="bullish"),
            _make_analysis(code="00002", ma_alignment="bullish"),
            _make_analysis(code="00003", ma_alignment="bullish"),
            _make_analysis(code="00004", ma_alignment="bullish"),
            _make_analysis(code="00005", ma_alignment="bearish"),
        ]
        result = self.scorer.compute(analyses)
        assert result["components"]["ma_bullish_ratio"] == pytest.approx(0.8, abs=0.01)

    def test_low_contradiction(self):
        """3/5 无矛盾 → 0.6。"""
        analyses = [
            _make_analysis(code="00001", contradiction_flags=[]),
            _make_analysis(code="00002", contradiction_flags=[]),
            _make_analysis(code="00003", contradiction_flags=[{"type": "hard_vs_soft"}]),
            _make_analysis(code="00004", contradiction_flags=[]),
            _make_analysis(code="00005", contradiction_flags=[{"type": "gate_anomaly"}]),
        ]
        result = self.scorer.compute(analyses)
        assert result["components"]["low_contradiction"] == pytest.approx(0.6, abs=0.01)

    # ── 合成评分与 Zone 分类 ─────────────────────────────────

    def test_strong_zone(self):
        """全牛市场景 → strong zone。"""
        analyses = [
            _make_analysis(
                code=f"0000{i}",
                final_score=0.9,
                confidence=0.9,
                capital_score=0.5,
                ma_alignment="bullish",
                contradiction_flags=[],
            )
            for i in range(1, 11)
        ]
        result = self.scorer.compute(analyses)
        assert result["zone"] == "strong"
        assert result["score"] >= 80
        assert result["recommended_exposure"] == "90-100%"

    def test_critical_zone(self):
        """全熊市场景 → critical zone。"""
        analyses = [
            _make_analysis(
                code=f"0000{i}",
                final_score=-0.8,
                confidence=0.1,
                capital_score=-0.5,
                ma_alignment="bearish",
                contradiction_flags=[{"type": "hard_vs_soft"}],
            )
            for i in range(1, 11)
        ]
        result = self.scorer.compute(analyses)
        assert result["zone"] == "critical"
        assert result["score"] <= 19

    def test_neutral_zone(self):
        """中性场景 → neutral zone（score 40-59）。

        构造: bull_ratio=0.5, strong_bull=0.2, confidence=0.6,
              capital=0.5, ma_bullish=0.4, low_contra=0.8
        Score = 0.5*25 + 0.2*20 + 0.6*20 + 0.5*15 + 0.4*10 + 0.8*10
              = 12.5 + 4 + 12 + 7.5 + 4 + 8 = 48 → neutral
        """
        # 5/10 bull, 2/10 strong_bull
        # capital: 5/10 positive, ma: 4/10 bullish, contra: 8/10 clean
        analyses = [
            # 5 bullish stocks (score > 0.2)
            _make_analysis(code=f"0000{i}", final_score=0.4, confidence=0.7,
                          capital_score=0.3, ma_alignment="bullish", contradiction_flags=[])
            for i in range(1, 4)
        ]
        analyses.extend([
            # 2 strong bullish
            _make_analysis(code=f"0000{i}", final_score=0.7, confidence=0.8,
                          capital_score=0.5, ma_alignment="bullish", contradiction_flags=[])
            for i in range(4, 6)
        ])
        analyses.extend([
            # 3 neutral/bearish
            _make_analysis(code=f"0000{i}", final_score=-0.1, confidence=0.3,
                          capital_score=-0.2, ma_alignment="neutral",
                          contradiction_flags=[{"type": "hard_vs_soft"}])
            for i in range(6, 8)
        ])
        analyses.extend([
            # 2 bearish with contradiction
            _make_analysis(code=f"0000{i}", final_score=-0.5, confidence=0.2,
                          capital_score=-0.8, ma_alignment="bearish",
                          contradiction_flags=[{"type": "hard_vs_soft"}])
            for i in range(8, 10)
        ])
        # 1 more neutral (no contradiction)
        analyses.append(_make_analysis(code="00010", final_score=0.0, confidence=0.5,
                                       capital_score=0.1, ma_alignment="neutral",
                                       contradiction_flags=[]))

        result = self.scorer.compute(analyses)
        assert result["zone"] == "neutral"
        assert 40 <= result["score"] <= 59

    # ── 返回结构验证 ─────────────────────────────────────────

    def test_result_structure(self):
        """返回字典应包含所有必需字段。"""
        analyses = [_make_analysis()]
        result = self.scorer.compute(analyses)

        assert "score" in result
        assert "zone" in result
        assert "components" in result
        assert "recommended_exposure" in result
        assert "total_stocks" in result

        assert isinstance(result["score"], int)
        assert 0 <= result["score"] <= 100
        assert result["total_stocks"] == 1

        # 6 个分量
        expected_components = {
            "bull_ratio",
            "strong_bull_ratio",
            "avg_confidence",
            "capital_net_positive",
            "ma_bullish_ratio",
            "low_contradiction",
        }
        assert set(result["components"].keys()) == expected_components

        # 分量值在 0-1 之间
        for name, value in result["components"].items():
            assert 0.0 <= value <= 1.0, f"{name}={value} 超出 [0,1] 范围"

    # ── 边界条件 ─────────────────────────────────────────────

    def test_single_stock(self):
        """单只股票也能正常计算。"""
        analyses = [
            _make_analysis(
                final_score=0.8,
                confidence=0.9,
                capital_score=0.5,
                ma_alignment="bullish",
                contradiction_flags=[],
            )
        ]
        result = self.scorer.compute(analyses)
        assert result["total_stocks"] == 1
        assert result["components"]["bull_ratio"] == 1.0
        assert result["components"]["strong_bull_ratio"] == 1.0
        assert result["components"]["capital_net_positive"] == 1.0
        assert result["components"]["ma_bullish_ratio"] == 1.0
        assert result["components"]["low_contradiction"] == 1.0

    def test_missing_capital_score_defaults_to_zero(self):
        """capital_score 缺失时不计入 positive。"""
        a = _make_analysis()
        a.signal_breakdown.pop("capital_score", None)
        result = self.scorer.compute([a])
        assert result["components"]["capital_net_positive"] == 0.0

    def test_missing_ma_alignment_defaults_to_non_bullish(self):
        """ma_alignment 缺失时不计入 bullish。"""
        a = _make_analysis()
        a.hard_metrics.pop("ma_alignment", None)
        result = self.scorer.compute([a])
        assert result["components"]["ma_bullish_ratio"] == 0.0

    def test_score_clamped_to_0_100(self):
        """评分应限制在 0-100 范围内。"""
        # 极端全好 → score ≤ 100
        analyses = [
            _make_analysis(
                final_score=1.0,
                confidence=1.0,
                capital_score=1.0,
                ma_alignment="bullish",
                contradiction_flags=[],
            )
        ]
        result = self.scorer.compute(analyses)
        assert result["score"] <= 100
