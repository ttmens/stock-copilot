"""Fundamental analysis agent — announcement / news."""

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
  "summary": "100-200字基本面分析",
  "focus_points": ["关注点1", "关注点2"],
  "risk_points": ["风险点1", "风险点2"]
}

sentiment 判断标准：
- bullish: 业绩增长、利好公告、行业政策利好、估值合理偏低
- bearish: 业绩下滑、利空公告、监管风险、估值明显偏高
- neutral: 无明显利好利空、信息不足、或多空因素交织"""

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
