"""Hard signal computation — deterministic quantitative factors.

All signals are computed from market data without any LLM involvement.
Each signal outputs a score in [-1.0, +1.0] range for fusion.

Factors:
- momentum_20d: 20-day return (trend following)
- momentum_5d: 5-day return (short-term momentum)
- ma_alignment: MA5 vs MA10 vs MA20 arrangement
- volume_ratio: today's volume / 20-day average volume
- valuation_score: PE/PB composite (lower is better for value)
- capital_flow: main force net inflow signal
"""

import logging
from dataclasses import dataclass
from typing import Optional

from src.data.models import OHLCVBar, MovingAverages, ValuationInfo, CapitalFlow

logger = logging.getLogger(__name__)

# Default factor weights for composite score
DEFAULT_WEIGHTS = {
    "momentum": 0.30,
    "ma": 0.25,
    "volume": 0.15,
    "valuation": 0.15,
    "capital": 0.15,
}


@dataclass
class HardSignals:
    """Computed hard signals for a single stock."""
    # Raw values
    momentum_20d: Optional[float] = None
    momentum_5d: Optional[float] = None
    ma_alignment: Optional[str] = None  # 'bullish' | 'bearish' | 'neutral'
    volume_ratio: Optional[float] = None
    pe_percentile: Optional[float] = None
    main_net_inflow: Optional[float] = None

    # Normalized scores (-1.0 to +1.0)
    momentum_score: float = 0.0
    ma_score: float = 0.0
    volume_score: float = 0.0
    valuation_score: float = 0.0
    capital_score: float = 0.0

    # Composite
    composite_score: float = 0.0  # weighted average of all scores


def compute_hard_signals(
    bars: list[OHLCVBar],
    ma: Optional[MovingAverages] = None,
    valuation: Optional[ValuationInfo] = None,
    capital: Optional[CapitalFlow] = None,
) -> HardSignals:
    """Compute all hard signals from available data.

    Missing data fields are silently skipped (score = 0.0).
    """
    signals = HardSignals()

    # 1. Momentum
    if bars and len(bars) >= 5:
        closes = [b.close for b in bars]

        signals.momentum_5d = _pct_change(closes, 5)
        signals.momentum_20d = _pct_change(closes, 20) if len(closes) >= 20 else signals.momentum_5d

        # Normalize: 5% return = +1.0, -5% return = -1.0 (clipped)
        signals.momentum_score = _clip(signals.momentum_5d / 5.0)
        if signals.momentum_20d is not None:
            # Blend short + medium term
            mom_20_norm = _clip(signals.momentum_20d / 10.0)
            signals.momentum_score = 0.6 * signals.momentum_score + 0.4 * mom_20_norm

    # 2. MA alignment
    if ma and ma.ma5 is not None and ma.ma10 is not None and ma.ma20 is not None:
        if bars:
            current_close = bars[-1].close
            signals.ma_alignment, signals.ma_score = _ma_alignment_score(
                current_close, ma.ma5, ma.ma10, ma.ma20
            )

    # 3. Volume ratio
    if bars and len(bars) >= 20:
        volumes = [b.volume for b in bars]
        today_vol = volumes[-1]
        avg_vol = sum(volumes[-20:-1]) / 19  # exclude today
        if avg_vol > 0:
            signals.volume_ratio = today_vol / avg_vol
            # Volume ratio > 2.0 = strong breakout (+1.0), < 0.5 = weak (-1.0)
            signals.volume_score = _clip((signals.volume_ratio - 1.0) / 0.5)

    # 4. Valuation score (lower PE/PB = better value = bullish)
    if valuation and (valuation.pe_ttm or valuation.pb):
        pe = valuation.pe_ttm or 30.0
        signals.pe_percentile = _pe_to_percentile(pe)
        # PE < 15 = +1.0, PE > 50 = -1.0
        signals.valuation_score = _clip((30.0 - pe) / 15.0)

    # 5. Capital flow
    if capital and capital.main_net_inflow is not None:
        signals.main_net_inflow = capital.main_net_inflow
        # Normalize: 1亿 = +1.0, -1亿 = -1.0
        signals.capital_score = _clip(capital.main_net_inflow / 1e8)

    # Composite score
    signals.composite_score = _composite_score(signals)

    return signals


def _pct_change(closes: list[float], n: int) -> float:
    """Return percentage change over n periods."""
    if len(closes) < 2:
        return 0.0
    if len(closes) >= n + 1:
        old = closes[-n - 1]
    else:
        old = closes[0]
    if old == 0:
        return 0.0
    return (closes[-1] / old - 1) * 100


def _ma_alignment_score(close: float, ma5: float, ma10: float, ma20: float) -> tuple[str, float]:
    """Score MA arrangement.

    Returns:
        (alignment_label, score) where score is -1.0 to +1.0
    """
    # Perfect bullish: close > MA5 > MA10 > MA20
    # Perfect bearish: close < MA5 < MA10 < MA20
    above_count = sum([close > ma5, ma5 > ma10, ma10 > ma20])

    if above_count == 3:
        return "bullish", 1.0
    elif above_count == 2:
        return "bullish", 0.5
    elif above_count == 1:
        return "neutral", -0.5
    else:
        return "bearish", -1.0


def _pe_to_percentile(pe: float) -> float:
    """Map PE to a rough historical percentile (0-100).

    Simplified: assumes PE 5-60 maps to 5th-95th percentile.
    """
    if pe <= 5:
        return 5.0
    elif pe >= 60:
        return 95.0
    return 5 + (pe - 5) / 55 * 90


def _clip(x: float) -> float:
    """Clip to [-1.0, +1.0] range."""
    return max(-1.0, min(1.0, x))


def _dragon_tiger_score(entries: list[dict]) -> float:
    """Score dragon tiger entries.
    
    Positive net buy = bullish, negative = bearish.
    Normalized: 1 亿 = +1.0, -1 亿 = -1.0
    """
    if not entries:
        return 0.0
    
    total_net = sum(e.get("net_buy", 0) for e in entries)
    return max(-1.0, min(1.0, total_net / 1e8))


def _composite_score(signals: HardSignals) -> float:
    """Weighted composite of all hard signals.

    Only includes factors that have non-zero scores.
    If no factors are available, returns 0.0 (neutral).
    """
    w = DEFAULT_WEIGHTS
    weighted_sum = 0.0
    total_weight = 0.0

    factor_scores = [
        (signals.momentum_score, w["momentum"]),
        (signals.ma_score, w["ma"]),
        (signals.volume_score, w["volume"]),
        (signals.valuation_score, w["valuation"]),
        (signals.capital_score, w["capital"]),
    ]

    for score, weight in factor_scores:
        if score != 0:
            weighted_sum += score * weight
            total_weight += weight

    if total_weight > 0:
        return weighted_sum / total_weight
    return 0.0
