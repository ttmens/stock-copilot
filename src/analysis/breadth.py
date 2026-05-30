"""市场广度评分模块 — Market Breadth Scorer.

基于当日全部股票分析结果计算市场广度评分（0-100），
用于判断整体市场健康程度并给出建议仓位范围。

6 个分量：
1. bull_ratio:      final_score > 0.2 的股票占比（多头占比）
2. strong_bull_ratio: final_score > 0.6 的股票占比（强多头占比）
3. avg_confidence:  平均置信度
4. capital_net_positive: capital_score > 0 的股票占比（资金净流入占比）
5. ma_bullish_ratio: ma_alignment == 'bullish' 的股票占比（均线多头占比）
6. low_contradiction:  没有 contradiction_flags 的股票占比（无矛盾信号占比）

加权合成：
    bull_ratio × 25 + strong_bull_ratio × 20 + avg_confidence × 20 +
    capital_net_positive × 15 + ma_bullish_ratio × 10 + low_contradiction × 10

Zone 分类：
    80-100: strong   → 建议仓位 90-100%
    60-79:  healthy  → 建议仓位 75-90%
    40-59:  neutral  → 建议仓位 60-75%
    20-39:  weakening→ 建议仓位 40-60%
    0-19:   critical → 建议仓位 25-40%

数据源：
- StockAnalysis.signal_breakdown["final_score"]  → 最终融合得分
- StockAnalysis.confidence                        → 置信度
- StockAnalysis.hard_metrics["ma_alignment"]      → 均线排列
- StockAnalysis.signal_breakdown["capital_score"] → 资金得分
- StockAnalysis.signal_breakdown["contradiction_flags"] → 矛盾标志
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


# ── 分量权重配置 ──────────────────────────────────────────────────

COMPONENT_WEIGHTS = {
    "bull_ratio": 25,
    "strong_bull_ratio": 20,
    "avg_confidence": 20,
    "capital_net_positive": 15,
    "ma_bullish_ratio": 10,
    "low_contradiction": 10,
}


# ── Zone 分类与仓位映射 ──────────────────────────────────────────

ZONE_THRESHOLDS = [
    (80, "strong", "90-100%"),
    (60, "healthy", "75-90%"),
    (40, "neutral", "60-75%"),
    (20, "weakening", "40-60%"),
    (0, "critical", "25-40%"),
]


def _classify_zone(score: int) -> tuple[str, str]:
    """将分数映射到 zone 类别和建议仓位范围。

    Args:
        score: 0-100 的广度评分

    Returns:
        (zone_name, recommended_exposure)
    """
    for threshold, zone, exposure in ZONE_THRESHOLDS:
        if score >= threshold:
            return zone, exposure
    # 理论上不会走到这里（最低 threshold=0）
    return "critical", "25-40%"


def _safe_get(obj: Any, *keys: str, default: Any = None) -> Any:
    """安全地多层嵌套取值，任一环节缺失则返回 default。

    支持对象属性访问和字典键访问。
    """
    val = obj
    for key in keys:
        if val is None:
            return default
        if isinstance(val, dict):
            val = val.get(key, default)
        elif hasattr(val, key):
            val = getattr(val, key)
        else:
            return default
    return val


class MarketBreadthScorer:
    """市场广度评分器。

    基于当日全部股票分析结果，计算反映整体市场健康程度的 0-100 评分，
    并给出相应的仓位建议。

    典型用法::

        scorer = MarketBreadthScorer()
        result = scorer.compute(analyses)
        print(f"市场广度: {result['score']}, 区域: {result['zone']}")
        print(f"建议仓位: {result['recommended_exposure']}")
    """

    def compute(self, analyses: list) -> dict:
        """基于当日全部股票分析结果计算市场广度 0-100 评分。

        Args:
            analyses: StockAnalysis 对象列表（来自 pipeline._analyze_and_fuse 输出）

        Returns:
            广度评分结果字典，包含：
            - score (int): 0-100 综合评分
            - zone (str): 区域分类 (strong/healthy/neutral/weakening/critical)
            - components (dict): 6 个分量的详细值
            - recommended_exposure (str): 建议仓位范围
            - total_stocks (int): 参与计算的股票总数
        """
        # 空列表保护：返回中性默认值
        if not analyses:
            logger.warning("MarketBreadthScorer: 无分析数据，返回中性评分")
            return self._default_result()

        total = len(analyses)

        # ── 收集各分量所需的计数 ─────────────────────────────────

        bull_count = 0          # final_score > 0.2
        strong_bull_count = 0   # final_score > 0.6
        confidence_sum = 0.0    # 置信度累加
        capital_positive_count = 0  # capital_score > 0
        ma_bullish_count = 0    # ma_alignment == 'bullish'
        no_contradiction_count = 0  # 无 contradiction_flags

        for a in analyses:
            # 1 & 2. 基于 final_score 判断多头/强多头
            final_score = _safe_get(a, "signal_breakdown", "final_score", default=0.0)
            if final_score is None:
                final_score = 0.0

            if final_score > 0.2:
                bull_count += 1
            if final_score > 0.6:
                strong_bull_count += 1

            # 3. 置信度
            confidence = _safe_get(a, "confidence", default=0.0)
            if confidence is None:
                confidence = 0.0
            confidence_sum += confidence

            # 4. 资金净流入 (capital_score > 0)
            capital_score = _safe_get(a, "signal_breakdown", "capital_score", default=None)
            if capital_score is None:
                # 备选：尝试从 HardSignals 直接获取
                capital_score = _safe_get(a, "hard_signals", "capital_score", default=None)
            if capital_score is not None and capital_score > 0:
                capital_positive_count += 1

            # 5. 均线多头排列
            ma_alignment = _safe_get(a, "hard_metrics", "ma_alignment", default=None)
            if ma_alignment is None:
                # 备选：尝试从 HardSignals 直接获取
                ma_alignment = _safe_get(a, "hard_signals", "ma_alignment", default=None)
            if ma_alignment == "bullish":
                ma_bullish_count += 1

            # 6. 无矛盾信号
            contradiction_flags = _safe_get(
                a, "signal_breakdown", "contradiction_flags", default=None
            )
            if contradiction_flags is None:
                # 备选：尝试从 fused_signal 直接获取
                contradiction_flags = _safe_get(
                    a, "fused_signal", "contradiction_flags", default=None
                )
            if not contradiction_flags:
                no_contradiction_count += 1

        # ── 计算分量比例（0-1 之间） ──────────────────────────────

        components = {
            "bull_ratio": round(bull_count / total, 4),
            "strong_bull_ratio": round(strong_bull_count / total, 4),
            "avg_confidence": round(confidence_sum / total, 4),
            "capital_net_positive": round(capital_positive_count / total, 4),
            "ma_bullish_ratio": round(ma_bullish_count / total, 4),
            "low_contradiction": round(no_contradiction_count / total, 4),
        }

        # ── 加权合成 0-100 评分 ───────────────────────────────────

        raw_score = 0.0
        for component_name, weight in COMPONENT_WEIGHTS.items():
            raw_score += components[component_name] * weight

        # 截断到 0-100 并取整
        score = max(0, min(100, int(round(raw_score))))

        # ── Zone 分类与仓位映射 ───────────────────────────────────

        zone, recommended_exposure = _classify_zone(score)

        result = {
            "score": score,
            "zone": zone,
            "components": components,
            "recommended_exposure": recommended_exposure,
            "total_stocks": total,
        }

        logger.info(
            "MarketBreadthScorer: score=%d zone=%s exposure=%s "
            "(bull=%.2f strong_bull=%.2f confidence=%.2f "
            "capital=%.2f ma_bullish=%.2f low_contra=%.2f, stocks=%d)",
            score, zone, recommended_exposure,
            components["bull_ratio"],
            components["strong_bull_ratio"],
            components["avg_confidence"],
            components["capital_net_positive"],
            components["ma_bullish_ratio"],
            components["low_contradiction"],
            total,
        )

        return result

    def _default_result(self) -> dict:
        """空数据时返回的中性默认结果。"""
        return {
            "score": 50,
            "zone": "neutral",
            "components": {
                "bull_ratio": 0.0,
                "strong_bull_ratio": 0.0,
                "avg_confidence": 0.0,
                "capital_net_positive": 0.0,
                "ma_bullish_ratio": 0.0,
                "low_contradiction": 0.0,
            },
            "recommended_exposure": "60-75%",
            "total_stocks": 0,
        }
