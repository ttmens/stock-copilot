"""Technical analysis agent."""

import json
import logging

from src.agents.base import BaseAgent
from src.data.models import AgentResult
from src.llm.client import LLMClient

logger = logging.getLogger(__name__)

_BASE_SYSTEM_PROMPT = """你是 A 股投研分析助手，仅基于用户提供的数据进行分析。

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
  "summary": "100-200字技术面分析",
  "focus_points": ["关注点1", "关注点2"],
  "risk_points": ["风险点1", "风险点2"]
}

sentiment 判断标准：
- bullish: 均线多头排列、趋势向上、量价配合良好、有突破迹象
- bearish: 均线空头排列、趋势向下、放量下跌、跌破关键支撑
- neutral: 横盘震荡、多空信号交织、方向不明确"""

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

        # D5: Inject dynamic prompt adjustments based on agent evolution
        try:
            from src.evolution.agent_tracker import AgentEvolutionTracker
            tracker = AgentEvolutionTracker()
            suffix = tracker.build_agent_prompt_suffix("technical")
            system_prompt = _BASE_SYSTEM_PROMPT + suffix
        except Exception:
            system_prompt = _BASE_SYSTEM_PROMPT

        # D3: Inject ReACT context (history + capital flow)
        try:
            from src.agents.tools import AnalysisTools, build_react_context
            tools = AnalysisTools()
            react_context = build_react_context(snapshot.code, tools)
            if react_context:
                user_prompt += "\n\n## 辅助数据（主动查询）\n" + react_context
        except Exception:
            pass

        result_json = await self.call_llm(system_prompt, user_prompt)
        return self._make_result(result_json)
