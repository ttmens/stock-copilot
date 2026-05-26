"""Capital flow analysis agent."""

import json
import logging

from src.agents.base import BaseAgent
from src.data.models import AgentResult

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是 A 股投研分析助手，仅基于用户提供的数据进行分析。

规则：
1. 只使用用户提供的 JSON 数据，不得编造任何数字、公告、资金数据
2. 数据缺失时，status 设为 "unavailable"，summary 说明缺失原因
3. 输出必须是合法 JSON，不含 markdown 代码块
4. 不做买卖建议，不使用「必涨」「必买」等词汇
5. summary 100-200 字，focus_points 和 risk_points 各 1-3 条

输出格式（严格按此 JSON 结构）：
{
  "status": "ok" | "unavailable" | "failed",
  "sentiment": "bullish" | "bearish" | "neutral",
  "summary": "100-200字资金面分析",
  "focus_points": ["关注点1", "关注点2"],
  "risk_points": ["风险点1", "风险点2"]
}

sentiment 判断标准：
- bullish: 主力/北向资金持续净流入，且呈加速趋势
- bearish: 主力/北向资金持续净流出，或主力大幅流出
- neutral: 资金小幅进出、方向不明、或数据不足以判断"""

USER_TEMPLATE = """分析以下 A 股资金数据，输出 JSON。

股票: {code} {name}

资金数据:
{capital_json}

关注: 北向/主力态度、资金异常。
无数据时 status=unavailable，不要猜测。"""


class CapitalAgent(BaseAgent):
    agent_name = "capital"

    async def analyze(self, snapshot) -> AgentResult:
        if snapshot.capital is None:
            return self._make_result({
                "status": "unavailable",
                "sentiment": "neutral",
                "summary": f"{snapshot.name} 资金数据暂不可用",
                "focus_points": [],
                "risk_points": [],
            })

        cap_json = json.dumps({
            "north_net_inflow": snapshot.capital.north_net_inflow,
            "main_net_inflow": snapshot.capital.main_net_inflow,
            "period": snapshot.capital.period,
        }, ensure_ascii=False)

        user_prompt = USER_TEMPLATE.format(
            code=snapshot.code,
            name=snapshot.name,
            capital_json=cap_json,
        )

        result_json = await self.call_llm(SYSTEM_PROMPT, user_prompt)
        return self._make_result(result_json)
