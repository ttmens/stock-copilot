"""Scenario Simulation — inspired by MiroFish's "God's-eye view" variable injection.

MiroFish allows users to inject variables mid-simulation ("如果 XX 政策落地")
to deduce future trajectories. We adapt this for Stock Copilot: users can specify
a hypothetical scenario and the system analyzes how it would impact their watchlist.

Key MiroFish pattern: seed event → simulate interaction → predict trajectory.
Our pattern: scenario description → LLM impact analysis → impact matrix.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ImpactItem:
    """Impact analysis for a single stock under a scenario."""
    code: str
    name: str
    impact_level: str = "medium"  # high / medium / low / none
    direction: str = "neutral"  # positive / negative / neutral
    estimated_range: str = ""  # e.g., "-3% ~ -8%"
    reasoning: str = ""
    suggestion: str = ""  # e.g., "关注支撑位", "考虑减仓", "无直接影响"

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "name": self.name,
            "impact_level": self.impact_level,
            "direction": self.direction,
            "estimated_range": self.estimated_range,
            "reasoning": self.reasoning,
            "suggestion": self.suggestion,
        }


@dataclass
class ScenarioResult:
    """Complete scenario simulation result."""
    scenario: str
    impact_matrix: list[ImpactItem] = field(default_factory=list)
    overall_assessment: str = ""
    high_risk_count: int = 0
    safe_count: int = 0

    def to_dict(self) -> dict:
        return {
            "scenario": self.scenario,
            "impact_matrix": [item.to_dict() for item in self.impact_matrix],
            "overall_assessment": self.overall_assessment,
            "summary": {
                "total_analyzed": len(self.impact_matrix),
                "high_risk": self.high_risk_count,
                "safe": self.safe_count,
            },
        }

    def to_markdown(self) -> str:
        lines = [
            f"# 场景推演：{self.scenario}",
            "",
            f"**整体评估**：{self.overall_assessment}",
            "",
            f"📊 分析 {len(self.impact_matrix)} 只股票 | "
            f"🔴 高风险 {self.high_risk_count} | "
            f"🟢 安全 {self.safe_count}",
            "",
            "---",
            "",
        ]
        for item in self.impact_matrix:
            icon = {"high": "🔴", "medium": "🟡", "low": "🟢", "none": "⚪"}.get(
                item.impact_level, "⚪"
            )
            dir_icon = {
                "positive": "📈",
                "negative": "📉",
                "neutral": "➡️",
            }.get(item.direction, "➡️")
            lines.append(
                f"### {icon} {item.code} {item.name} — 影响：{item.impact_level} {dir_icon}"
            )
            if item.estimated_range:
                lines.append(f"- **预估波动**: {item.estimated_range}")
            lines.append(f"- **分析**: {item.reasoning}")
            lines.append(f"- **建议**: {item.suggestion}")
            lines.append("")
        return "\n".join(lines)


class ScenarioSimulator:
    """推演特定场景对自选股的影响。

    MiroFish pattern: "上帝视角注入变量 → 推演未来轨迹"。
    我们简化为：场景描述 → LLM 逐股分析影响 → 生成影响矩阵。
    """

    _SYSTEM_PROMPT = """你是 A 股市场分析师，擅长评估特定事件/场景对个股的影响。

请基于用户提供的场景，分析对指定股票的可能影响。

规则：
1. 不要编造具体价格，给出合理的波动范围估计
2. 考虑行业关联、概念联动、资金流向
3. 影响等级：high（直接影响，波动>5%）、medium（间接影响，波动2-5%）、low（轻微影响，<2%）、none（无明显影响）
4. 方向：positive（利好）、negative（利空）、neutral（中性）
5. 输出合法 JSON，不含 markdown 代码块

输出格式（数组，每只股票一个对象）：
[
  {
    "code": "股票代码",
    "name": "股票名称",
    "impact_level": "high" | "medium" | "low" | "none",
    "direction": "positive" | "negative" | "neutral",
    "estimated_range": "预估波动范围，如 -3% ~ -8%",
    "reasoning": "分析理由，50-100字",
    "suggestion": "操作建议，20-40字"
  }
]"""

    async def simulate(
        self,
        scenario: str,
        watchlist: list[dict],  # [{"code": "600519", "name": "贵州茅台"}, ...]
        llm_client=None,
    ) -> ScenarioResult:
        """Execute scenario simulation.

        Args:
            scenario: Description of the hypothetical scenario
            watchlist: List of stocks to analyze
            llm_client: LLM client for analysis (uses default if None)

        Returns:
            ScenarioResult with impact matrix
        """
        from src.llm.client import get_llm_client

        client = llm_client or get_llm_client()

        # Build user prompt
        stock_list = "\n".join(
            f"- {s['code']} {s['name']}" for s in watchlist
        )
        user_prompt = f"""场景描述：
{scenario}

需要分析的股票列表：
{stock_list}

请逐一分析每只股票在此场景下可能受到的影响。"""

        try:
            result_json = await client.chat_json(
                user_prompt=user_prompt,
                system_prompt=self._SYSTEM_PROMPT,
            )

            impact_matrix = []
            high_risk = 0
            safe = 0

            if isinstance(result_json, list):
                for item in result_json:
                    if isinstance(item, dict) and "code" in item:
                        impact_item = ImpactItem(
                            code=item.get("code", ""),
                            name=item.get("name", ""),
                            impact_level=item.get("impact_level", "medium"),
                            direction=item.get("direction", "neutral"),
                            estimated_range=item.get("estimated_range", ""),
                            reasoning=item.get("reasoning", ""),
                            suggestion=item.get("suggestion", ""),
                        )
                        impact_matrix.append(impact_item)
                        if impact_item.impact_level == "high" and impact_item.direction == "negative":
                            high_risk += 1
                        elif impact_item.impact_level in ("low", "none"):
                            safe += 1

            # Overall assessment
            total = len(impact_matrix)
            if high_risk > total * 0.3:
                overall = f"⚠️ 场景对持仓影响较大，{high_risk}/{total} 只股票面临高风险，建议重点关注"
            elif high_risk > 0:
                overall = f"⚡ 场景对部分持仓有影响，{high_risk}/{total} 只股票需关注，其余影响有限"
            else:
                overall = f"✅ 场景对持仓影响有限，{safe}/{total} 只股票基本不受影响"

            return ScenarioResult(
                scenario=scenario,
                impact_matrix=impact_matrix,
                overall_assessment=overall,
                high_risk_count=high_risk,
                safe_count=safe,
            )

        except Exception as e:
            logger.error("Scenario simulation failed: %s", e)
            return ScenarioResult(
                scenario=scenario,
                overall_assessment=f"推演失败：{e}",
            )
