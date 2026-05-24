"""Announcement analysis agent — extracts key events from announcements using LLM."""

import logging
from src.agents.base import BaseAgent
from src.data.models import AgentResult, AgentStatus

logger = logging.getLogger(__name__)

ANNOUNCEMENT_PROMPT = """你是一个专业的 A 股公告分析助手。基于以下公告标题列表，提取关键信息。

【公告列表】
{announcements}

【输出要求】（严格按 JSON 格式，不含 markdown 代码块）
{{
  "key_events": [
    {{"event": "一季度净利润同比增长 15%", "impact": "positive", "confidence": 0.85}}
  ],
  "overall_sentiment": "positive|negative|neutral",
  "summary": "一句话总结公告核心内容",
  "risk_flags": ["股东减持计划", "业绩下滑预警"]
}}

【约束】
- 仅基于提供的公告标题
- 不编造未提及的信息
- impact: positive/negative/neutral
- confidence: 0-1
- 无公告时输出 {{"key_events": [], "overall_sentiment": "neutral", "summary": "无近期公告", "risk_flags": []}}
"""


class AnnouncementAgent(BaseAgent):
    """Extract key events from stock announcements using LLM."""
    
    agent_name: str = "announcement"
    
    async def analyze(self, code: str, name: str, announcements: list[str]) -> AgentResult:
        """Analyze announcements and extract key events.
        
        Args:
            code: Stock code
            name: Stock name
            announcements: List of announcement titles/summaries
            
        Returns:
            AgentResult with extracted events and sentiment
        """
        if not announcements:
            return AgentResult(
                agent_name="announcement",
                status=AgentStatus.UNAVAILABLE,
                sentiment="neutral",
                summary="无近期公告",
                raw_json={
                    "key_events": [],
                    "risk_flags": []
                }
            )
        
        try:
            user_prompt = ANNOUNCEMENT_PROMPT.format(
                announcements="\n".join(f"- {a}" for a in announcements[:10])
            )
            
            system_prompt = "你是专业的 A 股公告分析助手，仅基于提供的公告标题提取关键信息。"
            
            result = await self.call_llm(system_prompt, user_prompt)
            
            if result.get("status") == "failed":
                return AgentResult(
                    agent_name="announcement",
                    status=AgentStatus.UNAVAILABLE,
                    sentiment="neutral",
                    summary=result.get("summary", "分析失败"),
                    raw_json={
                        "key_events": [],
                        "risk_flags": []
                    }
                )
            
            # Count positive vs negative events
            events = result.get("key_events", [])
            pos = sum(1 for e in events if e.get("impact") == "positive")
            neg = sum(1 for e in events if e.get("impact") == "negative")
            
            if pos > neg:
                sentiment = "bullish"
            elif neg > pos:
                sentiment = "bearish"
            else:
                sentiment = "neutral"
            
            return AgentResult(
                agent_name="announcement",
                status=AgentStatus.OK,
                sentiment=sentiment,
                summary=result.get("summary", ""),
                risk_points=result.get("risk_flags", []),
                raw_json={
                    "key_events": events,
                    "risk_flags": result.get("risk_flags", [])
                }
            )
            
        except Exception as e:
            logger.error(f"Announcement analysis failed for {code}: {e}")
            return AgentResult(
                agent_name="announcement",
                status=AgentStatus.UNAVAILABLE,
                sentiment="neutral",
                summary=f"分析失败：{str(e)}",
                raw_json={
                    "key_events": [],
                    "risk_flags": []
                }
            )
