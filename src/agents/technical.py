"""Technical analysis agent."""

import json
import logging

from src.agents.base import BaseAgent, SYSTEM_PROMPT
from src.data.models import AgentResult

logger = logging.getLogger(__name__)

USER_TEMPLATE = """分析以下 A 股技术面数据，输出 JSON。

股票: {code} {name}

最近20条日线 (OHLCV):
{bars_json}

均线: MA5={ma5}, MA10={ma10}, MA20={ma20}

关注: 趋势方向、均线关系（多头/空头排列）、量能变化、支撑压力位。"""


class TechnicalAgent(BaseAgent):
    agent_name = "technical"

    async def analyze(self, snapshot) -> AgentResult:
        if not snapshot.bars:
            return self._make_result({
                "status": "unavailable",
                "sentiment": "neutral",
                "summary": "无日线数据，无法进行技术分析",
                "focus_points": [],
                "risk_points": [],
            })

        # Limit to last 20 bars to reduce tokens
        recent_bars = snapshot.bars[-20:]
        bars_json = json.dumps([
            {
                "date": str(b.date),
                "open": b.open, "high": b.high, "low": b.low,
                "close": b.close, "volume": b.volume,
            }
            for b in recent_bars
        ], ensure_ascii=False)

        user_prompt = USER_TEMPLATE.format(
            code=snapshot.code,
            name=snapshot.name,
            bars_json=bars_json,
            ma5=snapshot.ma.ma5,
            ma10=snapshot.ma.ma10,
            ma20=snapshot.ma.ma20,
        )

        result_json = await self.call_llm(SYSTEM_PROMPT, user_prompt)
        return self._make_result(result_json)
