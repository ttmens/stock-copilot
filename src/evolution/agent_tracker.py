"""Agent Evolution Tracker — extends the existing OODA evolution system.

MiroFish pattern: agents accumulate memory and evolve their stance through interactions.
Current Stock Copilot evolution only optimizes fusion weights. We extend it to track
individual agent dimension accuracy and dynamically adjust agent prompts/focus.

Key insight: if the TechnicalAgent consistently misses signals in ranging markets,
we should adjust its prompt to emphasize support/resistance analysis.
If CapitalAgent is wrong about north-bound flow impact, we add more context.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentDimensionStats:
    """Performance stats for a single agent dimension."""
    agent_name: str  # technical / capital / fundamental
    total_predictions: int = 0
    correct_predictions: int = 0
    bullish_correct: int = 0
    bullish_total: int = 0
    bearish_correct: int = 0
    bearish_total: int = 0
    neutral_correct: int = 0
    neutral_total: int = 0
    avg_confidence: float = 0.0
    last_updated: str = ""

    @property
    def accuracy(self) -> float:
        if self.total_predictions == 0:
            return 0.5
        return self.correct_predictions / self.total_predictions

    @property
    def bullish_accuracy(self) -> float:
        if self.bullish_total == 0:
            return 0.5
        return self.bullish_correct / self.bullish_total

    @property
    def bearish_accuracy(self) -> float:
        if self.bearish_total == 0:
            return 0.5
        return self.bearish_correct / self.bearish_total

    def to_dict(self) -> dict:
        return {
            "agent_name": self.agent_name,
            "total_predictions": self.total_predictions,
            "correct_predictions": self.correct_predictions,
            "accuracy": round(self.accuracy, 3),
            "bullish_accuracy": round(self.bullish_accuracy, 3),
            "bearish_accuracy": round(self.bearish_accuracy, 3),
            "avg_confidence": round(self.avg_confidence, 3),
            "last_updated": self.last_updated,
        }


# Agent-specific prompt adjustments based on performance patterns
PROMPT_ADJUSTMENTS = {
    "technical": {
        "low_ranging_accuracy": (
            "请特别关注横盘震荡区间的支撑/压力位。当股价在窄幅区间内波动时，"
            "重点分析成交量变化和均线收敛/发散，而非简单判断方向。"
        ),
        "low_bullish_accuracy": (
            "看多信号需要更严格的确认：必须有量价配合（放量上涨）+ 均线多头排列 + "
            "突破关键阻力位。缺少任一条件时请倾向于 neutral 而非 bullish。"
        ),
        "low_bearish_accuracy": (
            "看空信号需要更严格的确认：必须有放量下跌 + 跌破关键支撑 + "
            "均线空头排列。缺少任一条件时请倾向于 neutral 而非 bearish。"
        ),
    },
    "capital": {
        "low_overall_accuracy": (
            "资金面分析请更多关注主力资金的连续性（连续多日同方向）而非单日异动。"
            "单日净流入/流出可能是噪音，连续3日同方向才更有参考意义。"
        ),
    },
    "fundamental": {
        "low_overall_accuracy": (
            "基本面分析在A股短期走势中权重较低。当估值和公告面没有重大变化时，"
            "请倾向于 neutral，避免过度解读小幅估值变动。"
        ),
    },
}


class AgentEvolutionTracker:
    """追踪和优化每个 Agent 维度的表现。

    MiroFish pattern: agent evolution through interaction feedback.
    Extends the existing EvolutionEngine to operate at the agent level.
    """

    def __init__(self, config_path: str = "config/agent_evolution.json"):
        self.config_path = config_path
        self.stats: dict[str, AgentDimensionStats] = {}
        self._load()

    def _load(self):
        path = Path(self.config_path)
        if path.exists():
            try:
                data = json.loads(path.read_text())
                for name, stats_data in data.items():
                    self.stats[name] = AgentDimensionStats(
                        agent_name=name,
                        **{k: v for k, v in stats_data.items()
                           if k != "agent_name"},
                    )
                logger.info("[agent_evolution] Loaded stats for %d agents", len(self.stats))
            except Exception as e:
                logger.warning("[agent_evolution] Failed to load config: %s", e)

    def _save(self):
        path = Path(self.config_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {name: stats.to_dict() for name, stats in self.stats.items()}
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2))

    def record_prediction(
        self,
        agent_name: str,
        predicted_sentiment: str,
        actual_direction: str,  # "bullish" if stock went up, "bearish" if down
        confidence: float = 0.5,
    ):
        """Record a single agent prediction and its outcome.

        Called during the evolution cycle (16:00) to verify yesterday's signals.
        """
        if agent_name not in self.stats:
            self.stats[agent_name] = AgentDimensionStats(agent_name=agent_name)

        stats = self.stats[agent_name]
        stats.total_predictions += 1
        stats.last_updated = date.today().isoformat()

        # Update direction-specific stats
        if predicted_sentiment == "bullish":
            stats.bullish_total += 1
            if actual_direction == "bullish":
                stats.bullish_correct += 1
                stats.correct_predictions += 1
        elif predicted_sentiment == "bearish":
            stats.bearish_total += 1
            if actual_direction == "bearish":
                stats.bearish_correct += 1
                stats.correct_predictions += 1
        else:  # neutral
            stats.neutral_total += 1
            if actual_direction == "neutral":
                stats.neutral_correct += 1
                stats.correct_predictions += 1

        # Update running average confidence
        n = stats.total_predictions
        stats.avg_confidence = (stats.avg_confidence * (n - 1) + confidence) / n

        self._save()

    def get_prompt_adjustments(self, agent_name: str) -> list[str]:
        """Get prompt adjustment suggestions based on performance.

        Returns a list of prompt additions that should be injected into the
        agent's system prompt for better accuracy.
        """
        if agent_name not in self.stats:
            return []

        stats = self.stats[agent_name]
        adjustments = []
        agent_rules = PROMPT_ADJUSTMENTS.get(agent_name, {})

        # Check overall accuracy (need at least 20 predictions)
        if stats.total_predictions >= 20 and stats.accuracy < 0.45:
            key = "low_overall_accuracy"
            if key in agent_rules:
                adjustments.append(agent_rules[key])

        # Check bullish accuracy
        if stats.bullish_total >= 10 and stats.bullish_accuracy < 0.4:
            key = "low_bullish_accuracy"
            if key in agent_rules:
                adjustments.append(agent_rules[key])

        # Check bearish accuracy
        if stats.bearish_total >= 10 and stats.bearish_accuracy < 0.4:
            key = "low_bearish_accuracy"
            if key in agent_rules:
                adjustments.append(agent_rules[key])

        # Special case for technical agent in ranging markets
        if (agent_name == "technical" and stats.total_predictions >= 15
                and 0.35 < stats.accuracy < 0.55):
            # Accuracy around random = struggling with direction calls
            key = "low_ranging_accuracy"
            if key in agent_rules:
                adjustments.append(agent_rules[key])

        return adjustments

    def build_agent_prompt_suffix(self, agent_name: str) -> str:
        """Build a prompt suffix to inject into the agent's system prompt.

        This is called at analysis time to dynamically adjust the agent's focus
        based on historical performance.
        """
        adjustments = self.get_prompt_adjustments(agent_name)
        if not adjustments:
            return ""

        lines = [
            "\n\n## 动态调优建议（基于历史表现）",
            "以下建议来自系统对你历史准确率的分析，请在分析时特别注意：",
        ]
        for adj in adjustments:
            lines.append(f"- {adj}")

        return "\n".join(lines)

    def get_summary(self) -> dict:
        """Get evolution summary for all agents."""
        return {
            name: stats.to_dict()
            for name, stats in self.stats.items()
        }

    def get_suggestions(self) -> list[str]:
        """Get human-readable evolution suggestions."""
        suggestions = []
        for name, stats in self.stats.items():
            if stats.total_predictions < 10:
                suggestions.append(
                    f"[{name}] 数据不足（{stats.total_predictions}条），"
                    f"需要至少20条才能准确评估"
                )
                continue

            if stats.accuracy >= 0.6:
                suggestions.append(
                    f"[{name}] 表现良好（准确率 {stats.accuracy:.0%}），"
                    f"保持当前分析策略"
                )
            elif stats.accuracy >= 0.45:
                suggestions.append(
                    f"[{name}] 表现一般（准确率 {stats.accuracy:.0%}），"
                    f"已应用动态调优建议"
                )
            else:
                suggestions.append(
                    f"[{name}] 准确率偏低（{stats.accuracy:.0%}），"
                    f"建议重点关注该维度的分析质量"
                )

        return suggestions
