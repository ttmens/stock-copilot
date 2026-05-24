"""Signal fusion engine — combines hard signals, LLM soft signals, and rule-based gates.

Architecture:
- Hard signals (60%): deterministic quantitative factors
- Soft signals (30%): LLM-generated sentiment + confidence
- Gate signals (10%): rule-based confirmation (volume, ST filter, etc.)

Final output: score in [-1.0, +1.0] → classified to signal label
"""

import logging
from dataclasses import dataclass
from typing import Optional

from src.data.hard_signals import HardSignals
from src.data.models import AgentResult, AgentStatus

logger = logging.getLogger(__name__)

# ── Signal classification ──────────────────────────────────────────

SIGNAL_LABELS = {
    "strong_buy": "🟢 强烈看多",
    "buy": "🟢 看多",
    "hold": "⚪ 观望",
    "sell": "🔴 看空",
    "strong_sell": "🔴 强烈看空",
}

# Score thresholds for signal classification
_THRESHOLDS = {
    "strong_buy": 0.6,
    "buy": 0.2,
    "hold": -0.2,
    "sell": -0.6,
    # anything < -0.6 → strong_sell
}


@dataclass
class FusedSignal:
    """Result of signal fusion."""
    code: str
    name: str = ""

    # Component scores
    hard_score: float = 0.0
    soft_score: float = 0.0
    gate_score: float = 0.0
    dragon_tiger_score: float = 0.0
    announcement_score: float = 0.0

    # Final
    final_score: float = 0.0
    final_signal: str = "hold"
    signal_label: str = "⚪ 观望"

    # Meta
    confidence: float = 0.0  # 0-1, how confident we are
    data_available: dict[str, bool] = None  # type: ignore

    def __post_init__(self):
        if self.data_available is None:
            self.data_available = {"hard": False, "soft": False, "gate": False, "dragon_tiger": False, "announcement": False}


def fuse_signals(
    code: str,
    name: str,
    hard: Optional[HardSignals] = None,
    agents: Optional[dict[str, AgentResult]] = None,
    is_st: bool = False,
    is_suspended: bool = False,
    limit_up_down: bool = False,
    dragon_tiger_entries: Optional[list[dict]] = None,
    announcement_result: Optional[AgentResult] = None,
) -> FusedSignal:
    """Fuse all signal layers into a final signal.

    Args:
        code: stock code
        name: stock name
        hard: computed hard signals (may be None if no data)
        agents: dict of agent_name → AgentResult (technical, fundamental, capital)
        is_st: whether stock is ST
        is_suspended: whether stock is suspended
        limit_up_down: whether stock hit 涨跌停 today

    Returns:
        FusedSignal with score and classification
    """
    result = FusedSignal(code=code, name=name)

    # ── Gate: hard filters ─────────────────────────────────────
    if is_st or is_suspended:
        result.final_signal = "hold"
        result.signal_label = "⚪ 过滤（ST/停牌）"
        result.gate_st_filtered = True  # type: ignore
        result.confidence = 0.0
        result.data_available = {"hard": False, "soft": False, "gate": True}
        return result

    # ── Layer 1: Hard signals (deterministic) ──────────────────
    if hard is not None:
        result.hard_score = hard.composite_score
        result.data_available["hard"] = True

    # ── Layer 2: Soft signals (LLM agents) ─────────────────────
    if agents:
        result.soft_score = _agents_to_score(agents)
        result.data_available["soft"] = True

    # ── Layer 3: Gate confirmation ─────────────────────────────
    result.gate_score = _gate_score(
        hard=hard,
        limit_up_down=limit_up_down,
        agents=agents,
    )
    result.data_available["gate"] = True

    # ── Layer 4: Dragon & Tiger ──────────────────────────────
    if dragon_tiger_entries:
        from src.data.hard_signals import _dragon_tiger_score
        result.dragon_tiger_score = _dragon_tiger_score(dragon_tiger_entries)
        result.data_available["dragon_tiger"] = True

    # ── Layer 5: Announcement ────────────────────────────────
    if announcement_result and announcement_result.status != AgentStatus.UNAVAILABLE:
        sentiment_map = {
            "bullish": 1.0,
            "bearish": -1.0,
            "neutral": 0.0,
        }
        result.announcement_score = sentiment_map.get(announcement_result.sentiment, 0.0)
        result.data_available["announcement"] = True

# ── Fusion: weighted sum ──────────────────────────────────────
    # Dynamic weights based on data availability
    has_hard = result.data_available["hard"]
    has_soft = result.data_available["soft"]
    has_dragon_tiger = result.data_available.get("dragon_tiger", False)
    has_announcement = result.data_available.get("announcement", False)

    if has_hard and has_soft:
        w_hard, w_soft, w_gate = 0.40, 0.25, 0.15
        w_dragon_tiger = 0.10 if has_dragon_tiger else 0.0
        w_announcement = 0.10 if has_announcement else 0.0
    elif has_hard:
        w_hard, w_soft, w_gate = 0.60, 0.00, 0.20
        w_dragon_tiger = 0.10 if has_dragon_tiger else 0.0
        w_announcement = 0.10 if has_announcement else 0.0
    elif has_soft:
        w_hard, w_soft, w_gate = 0.00, 0.60, 0.20
        w_dragon_tiger = 0.10 if has_dragon_tiger else 0.0
        w_announcement = 0.10 if has_announcement else 0.0
    else:
        # No data at all
        result.final_signal = "hold"
        result.signal_label = "⚪ 无数据"
        result.confidence = 0.0
        return result

    result.final_score = (
        result.hard_score * w_hard +
        result.soft_score * w_soft +
        result.gate_score * w_gate +
        result.dragon_tiger_score * w_dragon_tiger +
        result.announcement_score * w_announcement
    )

    # Classify
    result.final_signal = _classify(result.final_score)
    result.signal_label = SIGNAL_LABELS.get(result.final_signal, "⚪ 观望")

    # Confidence: based on agreement between layers and data completeness
    result.confidence = _compute_confidence(
        hard_score=result.hard_score,
        soft_score=result.soft_score,
        gate_score=result.gate_score,
        has_hard=has_hard,
        has_soft=has_soft,
    )

    return result


def _agents_to_score(agents: dict[str, AgentResult]) -> float:
    """Convert AgentResults to a single soft score [-1.0, +1.0].

    Uses weighted average based on agent type importance.
    """
    sentiment_map = {
        "bullish": 1.0,
        "bearish": -1.0,
        "neutral": 0.0,
        "unavailable": 0.0,
        "ok": 0.0,  # fallback
    }

    # Agent weights: technical > capital > fundamental
    agent_weights = {
        "technical": 0.40,
        "capital": 0.35,
        "fundamental": 0.25,
    }

    weighted_sum = 0.0
    total_weight = 0.0

    for agent_name, agent_result in agents.items():
        if agent_result.status != AgentStatus.UNAVAILABLE:
            sentiment = agent_result.sentiment
            score = sentiment_map.get(sentiment, 0.0)
            weight = agent_weights.get(agent_name, 0.25)
            weighted_sum += score * weight
            total_weight += weight

    if total_weight > 0:
        return weighted_sum / total_weight
    return 0.0


def _gate_score(
    hard: Optional[HardSignals] = None,
    limit_up_down: bool = False,
    agents: Optional[dict] = None,
) -> float:
    """Rule-based gate confirmation score [0.0, 1.0].

    Positive confirmation adds to score, negative signals reduce it.
    """
    score = 0.5  # neutral baseline

    # Volume confirmation: if hard signal is strong, volume should confirm
    if hard and hard.volume_ratio is not None:
        if hard.volume_ratio > 1.5:
            score += 0.2  # volume confirms breakout
        elif hard.volume_ratio < 0.5:
            score -= 0.2  # weak volume, doubt the signal

    # 涨跌停 filter: if stock hit limit up/down, reduce confidence
    if limit_up_down:
        score -= 0.3  # limit moves are less reliable for prediction

    # Agent agreement boost
    if agents:
        sentiments = [a.sentiment for a in agents.values()
                      if a.status == AgentStatus.OK]
        if len(sentiments) >= 2:
            if all(s == "bullish" for s in sentiments):
                score += 0.2  # all agents agree bullish
            elif all(s == "bearish" for s in sentiments):
                score -= 0.2  # all agents agree bearish

    return max(0.0, min(1.0, score))


def _classify(score: float) -> str:
    """Classify a score into a signal label."""
    if score >= _THRESHOLDS["strong_buy"]:
        return "strong_buy"
    elif score >= _THRESHOLDS["buy"]:
        return "buy"
    elif score >= _THRESHOLDS["hold"]:
        return "hold"
    elif score >= _THRESHOLDS["sell"]:
        return "sell"
    else:
        return "strong_sell"


def _compute_confidence(
    hard_score: float,
    soft_score: float,
    gate_score: float,
    has_hard: bool,
    has_soft: bool,
) -> float:
    """Compute confidence in the fused signal [0.0, 1.0].

    Higher when:
    - Both hard and soft layers agree (same direction)
    - More data layers are available
    - Signal magnitude is strong
    """
    # 1. Agreement bonus
    agreement = 0.5  # baseline
    if has_hard and has_soft:
        # Same direction = high confidence
        if hard_score * soft_score > 0:
            agreement = 0.8
        else:
            agreement = 0.3  # conflicting signals = low confidence
    elif has_hard or has_soft:
        agreement = 0.6  # single source = moderate confidence

    # 2. Signal strength bonus
    abs_score = abs(hard_score * 0.5 + soft_score * 0.3 + gate_score * 0.2)
    strength = min(1.0, abs_score + 0.3)  # boost by 0.3

    # 3. Data completeness bonus
    data_bonus = 0.0
    if has_hard:
        data_bonus += 0.15
    if has_soft:
        data_bonus += 0.15

    return max(0.0, min(1.0, agreement * 0.4 + strength * 0.4 + data_bonus))
