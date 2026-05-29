"""Multi-Agent Debate Orchestrator — inspired by MiroFish's swarm intelligence interaction pattern.

MiroFish uses thousands of agents that interact, influence, and evolve through social dynamics.
We adapt this pattern for Stock Copilot: instead of 3 independent LLM agents outputting in parallel,
agents now go through 2 rounds — independent analysis → see each other's conclusions → revise/confirm/rebut.

Key insight from MiroFish: disagreement is valuable information. When agents disagree,
it signals uncertainty / blind spots. Consensus is a confidence multiplier.
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Optional

from src.data.models import AgentResult, AgentStatus

logger = logging.getLogger(__name__)

# ── Debate round 2 system prompts (per agent type) ──────────────

DEBATE_PROMPT_TECHNICAL = """你是 A 股投研分析助手，负责技术面分析。

你已经对 {code} {name} 完成了第一轮技术分析。现在请查看资金面和基本面分析师的观点，
评估你的分析是否需要修正、补充或反驳。

规则：
1. 只使用用户提供的数据，不得编造任何数字
2. 如果其他分析师的观点与你一致，可以确认并补充细节
3. 如果其他分析师的观点与你矛盾，请分析分歧原因并坚持你的专业判断
4. 输出必须是合法 JSON，不含 markdown 代码块
5. summary 80-150 字

输出格式（严格按此 JSON 结构）：
{{
  "sentiment": "bullish" | "bearish" | "neutral",
  "summary": "80-150字技术面分析（含对其他观点的回应）",
  "focus_points": ["关注点1", "关注点2"],
  "risk_points": ["风险点1", "风险点2"],
  "agree_with_others": true | false,
  "disagreement_reason": "如不同意，说明理由（同意则留空）"
}}"""

DEBATE_PROMPT_CAPITAL = """你是 A 股投研分析助手，负责资金面分析。

你已经对 {code} {name} 完成了第一轮资金面分析。现在请查看技术面和基本面分析师的观点，
评估你的分析是否需要修正、补充或反驳。

规则：
1. 只使用用户提供的数据，不得编造任何数字
2. 如果其他分析师的观点与你一致，可以确认并补充细节
3. 如果其他分析师的观点与你矛盾，请分析分歧原因并坚持你的专业判断
4. 输出必须是合法 JSON，不含 markdown 代码块
5. summary 80-150 字

输出格式（严格按此 JSON 结构）：
{{
  "sentiment": "bullish" | "bearish" | "neutral",
  "summary": "80-150字资金面分析（含对其他观点的回应）",
  "focus_points": ["关注点1", "关注点2"],
  "risk_points": ["风险点1", "风险点2"],
  "agree_with_others": true | false,
  "disagreement_reason": "如不同意，说明理由（同意则留空）"
}}"""

DEBATE_PROMPT_FUNDAMENTAL = """你是 A 股投研分析助手，负责基本面分析。

你已经对 {code} {name} 完成了第一轮基本面分析。现在请查看技术面和资金面分析师的观点，
评估你的分析是否需要修正、补充或反驳。

规则：
1. 只使用用户提供的数据，不得编造任何数字
2. 如果其他分析师的观点与你一致，可以确认并补充细节
3. 如果其他分析师的观点与你矛盾，请分析分歧原因并坚持你的专业判断
4. 输出必须是合法 JSON，不含 markdown 代码块
5. summary 80-150 字

输出格式（严格按此 JSON 结构）：
{{
  "sentiment": "bullish" | "bearish" | "neutral",
  "summary": "80-150字基本面分析（含对其他观点的回应）",
  "focus_points": ["关注点1", "关注点2"],
  "risk_points": ["风险点1", "风险点2"],
  "agree_with_others": true | false,
  "disagreement_reason": "如不同意，说明理由（同意则留空）"
}}"""


@dataclass
class DebateResult:
    """辩论结果 — 记录 Round1 和 Round2 的变化"""
    # Round 1 sentiments
    r1_technical: str = ""
    r1_capital: str = ""
    r1_fundamental: str = ""

    # Round 2 sentiments (after seeing others)
    r2_technical: str = ""
    r2_capital: str = ""
    r2_fundamental: str = ""

    # Consensus metrics
    consensus_score: float = 0.0  # 0.0 ~ 1.0
    has_disagreement: bool = False
    disagreement_points: list[str] = field(default_factory=list)

    # Sentiment shifts
    technical_shifted: bool = False
    capital_shifted: bool = False
    fundamental_shifted: bool = False

    def to_dict(self) -> dict:
        return {
            "round1": {
                "technical": self.r1_technical,
                "capital": self.r1_capital,
                "fundamental": self.r1_fundamental,
            },
            "round2": {
                "technical": self.r2_technical,
                "capital": self.r2_capital,
                "fundamental": self.r2_fundamental,
            },
            "consensus_score": round(self.consensus_score, 2),
            "has_disagreement": self.has_disagreement,
            "disagreement_points": self.disagreement_points,
            "shifts": {
                "technical_shifted": self.technical_shifted,
                "capital_shifted": self.capital_shifted,
                "fundamental_shifted": self.fundamental_shifted,
            },
        }


class DebateOrchestrator:
    """协调多 Agent 辩论交互。

    MiroFish 模式：Agent 不是孤立输出，而是通过「看到彼此观点 → 修正/确认/反驳」
    产生群体智能。这里的辩论轮模拟了这种交互。

    流程：
    1. Round 1: 3 个 Agent 各自独立分析（现有流程不变）
    2. 收集 Round 1 结果
    3. Round 2: 每个 Agent 看到其他 2 个的结论 → 修正/确认/反驳
    4. 计算共识度 + 分歧点
    5. 返回辩论结果 + 更新后的 AgentResult
    """

    _debate_prompts = {
        "technical": DEBATE_PROMPT_TECHNICAL,
        "capital": DEBATE_PROMPT_CAPITAL,
        "fundamental": DEBATE_PROMPT_FUNDAMENTAL,
    }

    async def run_debate_round(
        self,
        code: str,
        name: str,
        round1_results: dict[str, AgentResult],
        agents: dict,  # TechnicalAgent, CapitalAgent, FundamentalAgent instances
    ) -> tuple[DebateResult, dict[str, AgentResult]]:
        """执行辩论第二轮。

        Args:
            code: 股票代码
            name: 股票名称
            round1_results: {"technical": AgentResult, "capital": AgentResult, "fundamental": AgentResult}
            agents: {"technical": TechnicalAgent, "capital": CapitalAgent, "fundamental": FundamentalAgent}

        Returns:
            (DebateResult, updated_agent_results)
        """
        debate = DebateResult()

        # 记录 Round 1 sentiments
        for key in ["technical", "capital", "fundamental"]:
            r = round1_results.get(key)
            if r:
                setattr(debate, f"r1_{key}", r.sentiment)

        # 构建其他 Agent 的观点摘要
        other_views = self._build_other_views(round1_results)

        # 并行执行第二轮辩论
        import asyncio
        tasks = []
        for agent_name, agent in agents.items():
            if agent_name in self._debate_prompts and agent_name in round1_results:
                task = self._debate_one(
                    agent=agent,
                    agent_name=agent_name,
                    code=code,
                    name=name,
                    other_views=other_views[agent_name],
                )
                tasks.append((agent_name, task))

        results = await asyncio.gather(
            *[t for _, t in tasks],
            return_exceptions=True,
        )

        # 处理结果
        updated_results = dict(round1_results)  # copy
        for (agent_name, _), result in zip(tasks, results):
            if isinstance(result, BaseException):
                logger.warning("Debate round 2 failed for %s: %s", agent_name, result)
                continue
            if result:
                updated_results[agent_name] = result
                setattr(debate, f"r2_{agent_name}", result.sentiment)
                # Check if sentiment shifted
                r1_sent = getattr(debate, f"r1_{agent_name}", "")
                if r1_sent and result.sentiment != r1_sent:
                    setattr(debate, f"{agent_name}_shifted", True)

        # 计算共识度
        r2_sentiments = [
            debate.r2_technical,
            debate.r2_capital,
            debate.r2_fundamental,
        ]
        r2_sentiments = [s for s in r2_sentiments if s]  # filter empty
        debate.consensus_score = self._compute_consensus(r2_sentiments)

        # 检测分歧
        debate.has_disagreement, debate.disagreement_points = self._detect_disagreements(
            updated_results,
        )

        return debate, updated_results

    async def _debate_one(
        self,
        agent,
        agent_name: str,
        code: str,
        name: str,
        other_views: str,
    ) -> Optional[AgentResult]:
        """执行单个 Agent 的辩论轮。"""
        system_prompt = self._debate_prompts[agent_name].format(code=code, name=name)
        user_prompt = f"""以下是其他分析师对 {code} {name} 的观点：

{other_views}

请评估你的分析是否需要修正。输出 JSON。"""

        try:
            result_json = await agent.call_llm(system_prompt, user_prompt)
            if result_json and result_json.get("status") != "failed":
                # Preserve original status as ok since debate succeeded
                result_json["status"] = "ok"
                return agent._make_result(result_json)
        except Exception as e:
            logger.warning("Debate LLM call failed for %s: %s", agent_name, e)

        return None

    def _build_other_views(self, round1_results: dict[str, AgentResult]) -> dict[str, str]:
        """为每个 Agent 构建「其他 Agent 观点」的文本。"""
        views = {}
        agent_labels = {
            "technical": "技术面分析师",
            "capital": "资金面分析师",
            "fundamental": "基本面分析师",
        }

        for agent_name in ["technical", "capital", "fundamental"]:
            others = []
            for other_name, other_result in round1_results.items():
                if other_name != agent_name and other_result.status == AgentStatus.OK:
                    label = agent_labels.get(other_name, other_name)
                    summary = other_result.summary[:120]
                    others.append(
                        f"[{label}]: {other_result.sentiment} — {summary}"
                    )
            if others:
                views[agent_name] = "\n".join(others)
            else:
                views[agent_name] = "（其他分析师暂无有效观点）"

        return views

    def _compute_consensus(self, sentiments: list[str]) -> float:
        """计算共识度 [0.0 ~ 1.0]。

        MiroFish 模式：共识度不是简单的多数表决，而是考虑方向一致性。
        - 全部同向: 1.0
        - 2 同向 + 1 neutral: 0.7
        - 2 同向 + 1 反向: 0.4
        - 全部不同: 0.2
        """
        if not sentiments:
            return 0.5

        bullish = sentiments.count("bullish")
        bearish = sentiments.count("bearish")
        neutral = sentiments.count("neutral")
        total = len(sentiments)

        if total == 1:
            return 0.6  # single agent = moderate confidence

        # All same direction
        if bullish == total or bearish == total:
            return 1.0

        # 2 same + 1 neutral
        if (bullish == 2 and neutral == 1) or (bearish == 2 and neutral == 1):
            return 0.7

        # 2 same + 1 opposite
        if (bullish == 2 and bearish == 1) or (bearish == 2 and bullish == 1):
            return 0.4

        # All different (1 each) or all neutral
        if neutral == total:
            return 0.3
        return 0.2

    def _detect_disagreements(
        self,
        results: dict[str, AgentResult],
    ) -> tuple[bool, list[str]]:
        """检测 Agent 间的分歧点。"""
        disagreements = []
        sentiments = {}
        for name, r in results.items():
            if r.status == AgentStatus.OK:
                sentiments[name] = r.sentiment

        unique_sentiments = set(sentiments.values())
        if len(unique_sentiments) <= 1:
            return False, []

        # Find specific disagreements
        agent_labels = {
            "technical": "技术面",
            "capital": "资金面",
            "fundamental": "基本面",
        }

        # bullish vs bearish
        bulls = [n for n, s in sentiments.items() if s == "bullish"]
        bears = [n for n, s in sentiments.items() if s == "bearish"]

        if bulls and bears:
            bull_labels = ", ".join(agent_labels.get(n, n) for n in bulls)
            bear_labels = ", ".join(agent_labels.get(n, n) for n in bears)
            disagreements.append(
                f"方向分歧：{bull_labels}看多 vs {bear_labels}看空"
            )

        # Add specific risk points from disagreeing agents
        for name, r in results.items():
            if r.status == AgentStatus.OK and r.risk_points:
                label = agent_labels.get(name, name)
                for rp in r.risk_points[:1]:
                    disagreements.append(f"{label}风险：{rp}")

        return len(disagreements) > 0, disagreements[:3]
