"""Base agent — uses unified LLM client with multi-provider fallback."""

import asyncio
import logging

from src.data.models import AgentResult, AgentStatus
from src.llm.client import get_llm_client

logger = logging.getLogger(__name__)


class BaseAgent:
    """Base class for all analysis agents.

    Uses the unified LLMClient which supports:
    - Multiple providers (DeepSeek, DashScope, etc.)
    - Fallback mode: cascade on failure
    - Concurrent mode: fire all simultaneously
    - Auto JSON parsing with retry
    """

    agent_name: str = "base"
    user_prompt_template: str = ""

    async def call_llm(self, system_prompt: str, user_prompt: str) -> dict:
        """Call LLM via unified client. Returns parsed JSON dict."""
        client = get_llm_client()

        if not client.available_providers:
            return self._unavailable_result()

        # Try with retry logic
        for attempt in range(client.config.max_retries):
            try:
                result = await client.chat_json(
                    user_prompt=user_prompt,
                    system_prompt=system_prompt,
                )
                return result
            except Exception as e:
                logger.warning("LLM call failed (attempt %d): %s", attempt + 1, e)
                if attempt < client.config.max_retries - 1:
                    await asyncio.sleep(2)
                continue

        return {
            "status": "failed",
            "sentiment": "neutral",
            "summary": f"LLM 调用失败（重试 {client.config.max_retries} 次）",
            "focus_points": [],
            "risk_points": [],
        }

    async def analyze(self, snapshot) -> AgentResult:
        """Override in subclass. Must return AgentResult."""
        raise NotImplementedError

    def _make_result(self, llm_json: dict) -> AgentResult:
        """Convert LLM JSON dict to AgentResult."""
        status_str = llm_json.get("status", "failed")
        # Map any status to our enum
        if status_str not in ("ok", "unavailable", "failed"):
            status_str = "ok" if status_str in ("available", "analyzed", "success") else "failed"

        return AgentResult(
            agent_name=self.agent_name,
            status=AgentStatus(status_str),
            summary=llm_json.get("summary", ""),
            sentiment=llm_json.get("sentiment", "neutral"),
            focus_points=llm_json.get("focus_points", []),
            risk_points=llm_json.get("risk_points", []),
            raw_json=llm_json,
        )

    @staticmethod
    def _unavailable_result() -> dict:
        """Return unavailable result."""
        return {
            "status": "unavailable",
            "sentiment": "neutral",
            "summary": "LLM API 未配置，无法分析",
            "focus_points": [],
            "risk_points": [],
        }
