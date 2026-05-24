"""Fundamental analysis agent — announcement / news."""

import json
import logging

from src.agents.base import BaseAgent, SYSTEM_PROMPT
from src.data.models import AgentResult

logger = logging.getLogger(__name__)

USER_TEMPLATE = """分析以下 A 股公告信息，输出 JSON。

股票: {code} {name}

近7日公告:
{announcements_json}

关注: 利好/利空/中性、业绩相关、风险事件。
无公告时 status=unavailable。"""


class FundamentalAgent(BaseAgent):
    agent_name = "fundamental"

    async def analyze(self, snapshot) -> AgentResult:
        if not snapshot.announcements:
            return self._make_result({
                "status": "unavailable",
                "sentiment": "neutral",
                "summary": f"{snapshot.name} 近7日无公告数据",
                "focus_points": [],
                "risk_points": [],
            })

        ann_json = json.dumps([
            {"title": a.title, "date": str(a.date), "url": a.url}
            for a in snapshot.announcements
        ], ensure_ascii=False)

        user_prompt = USER_TEMPLATE.format(
            code=snapshot.code,
            name=snapshot.name,
            announcements_json=ann_json,
        )

        result_json = await self.call_llm(SYSTEM_PROMPT, user_prompt)
        return self._make_result(result_json)
