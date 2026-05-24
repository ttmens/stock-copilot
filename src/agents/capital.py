"""Capital flow analysis agent."""

import json
import logging

from src.agents.base import BaseAgent, SYSTEM_PROMPT
from src.data.models import AgentResult

logger = logging.getLogger(__name__)

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
