"""Base agent — OpenAI-compatible LLM client with JSON parsing."""

import json
import logging
from typing import Optional

from openai import AsyncOpenAI

from src.config import get_settings
from src.data.models import AgentResult, AgentStatus

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是 A 股投研分析助手，仅基于用户提供的数据进行分析。

规则：
1. 只使用用户提供的 JSON 数据，不得编造任何数字、公告、资金数据
2. 数据缺失时，status 设为 "unavailable"，summary 说明缺失原因
3. 输出必须是合法 JSON，不含 markdown 代码块
4. 不做买卖建议，不使用「必涨」「必买」等词汇
5. summary 100-200 字，focus_points 和 risk_points 各 1-3 条"""


class BaseAgent:
    """Base class for all analysis agents."""

    agent_name: str = "base"

    def __init__(self):
        self.settings = get_settings()
        self._client: Optional[AsyncOpenAI] = None

    def _get_client(self) -> Optional[AsyncOpenAI]:
        """Create LLM client if API key is available."""
        if self._client is not None:
            return self._client

        api_key = self.settings.get_llm_api_key()
        if not api_key:
            logger.warning("No LLM API key configured — agents will return unavailable")
            return None

        base_url = self.settings.get_llm_base_url()
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=self.settings.llm.timeout,
        )
        return self._client

    async def call_llm(self, system_prompt: str, user_prompt: str) -> dict:
        """Call LLM and parse JSON response with retry."""
        client = self._get_client()
        if client is None:
            return {
                "status": "unavailable",
                "sentiment": "neutral",
                "summary": "LLM API 未配置，无法分析",
                "focus_points": [],
                "risk_points": [],
            }

        fallback = {
            "status": "failed",
            "sentiment": "neutral",
            "summary": "LLM 调用失败",
            "focus_points": [],
            "risk_points": [],
        }

        for attempt in range(2):
            try:
                response = await client.chat.completions.create(
                    model=self.settings.llm.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=self.settings.llm.temperature,
                    max_tokens=self.settings.llm.max_tokens,
                    response_format={"type": "json_object"},
                )
                content = response.choices[0].message.content
                if content is None:
                    raise ValueError("Empty response from LLM")

                # Strip markdown code blocks if present
                content = content.strip()
                if content.startswith("```"):
                    content = content.split("\n", 1)[1].rsplit("```", 1)[0]

                result: dict = json.loads(content)
                return result
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning("LLM JSON parse error (attempt %d): %s", attempt + 1, e)
                if attempt == 0:
                    continue
                return {**fallback, "summary": f"LLM 响应解析失败: {e}"}
            except Exception as e:
                logger.error("LLM call failed: %s", e)
                return {**fallback, "summary": f"LLM 调用失败: {e}"}

    async def analyze(self, snapshot) -> AgentResult:
        """Override in subclass. Must return AgentResult."""
        raise NotImplementedError

    def _make_result(self, llm_json: dict) -> AgentResult:
        """Convert LLM JSON dict to AgentResult."""
        return AgentResult(
            agent_name=self.agent_name,
            status=AgentStatus(llm_json.get("status", "failed")),
            summary=llm_json.get("summary", ""),
            sentiment=llm_json.get("sentiment", "neutral"),
            focus_points=llm_json.get("focus_points", []),
            risk_points=llm_json.get("risk_points", []),
            raw_json=llm_json,
        )
