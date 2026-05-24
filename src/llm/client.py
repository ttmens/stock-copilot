"""Unified LLM client — multi-provider with fallback and concurrent modes.

Design:
- Multiple providers (DeepSeek, DashScope, etc.) with priority ordering
- Fallback mode: Try primary first, cascade to fallback on failure
- Concurrent mode: Fire all providers simultaneously, use first success
- Auto JSON parsing with markdown code block stripping
- Never exposes API keys — reads from environment only
"""

import asyncio
import json
import logging
import os
from typing import Optional

from openai import AsyncOpenAI

from src.llm.config import LLMConfig, LLMProvider

logger = logging.getLogger(__name__)


class ProviderClient:
    """Single provider client with connection management."""

    def __init__(self, provider: LLMProvider):
        self.provider = provider
        self._client: Optional[AsyncOpenAI] = None

    @property
    def is_available(self) -> bool:
        """Check if API key is configured."""
        return bool(os.environ.get(self.provider.api_key_env, ""))

    def get_client(self) -> Optional[AsyncOpenAI]:
        """Get or create OpenAI client."""
        if self._client is not None:
            return self._client

        api_key = os.environ.get(self.provider.api_key_env, "")
        if not api_key:
            logger.warning("LLM provider '%s' has no API key configured", self.provider.name)
            return None

        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=self.provider.base_url,
            timeout=self.provider.timeout,
        )
        return self._client

    async def chat(
        self,
        messages: list[dict],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
    ) -> dict:
        """Send chat completion request.

        Returns: parsed JSON dict (if json_mode) or raw response dict.
        Raises: Exception on failure.
        """
        client = self.get_client()
        if client is None:
            raise ValueError(f"Provider '{self.provider.name}' not configured (no API key)")

        kwargs = {
            "model": self.provider.model,
            "messages": messages,
            "temperature": temperature or self.provider.temperature,
            "max_tokens": max_tokens or self.provider.max_tokens,
        }

        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        response = await client.chat.completions.create(**kwargs)

        content = response.choices[0].message.content
        if content is None:
            raise ValueError("Empty response from LLM")

        if json_mode:
            return self._parse_json(content)

        return {"content": content, "raw": response}

    def _parse_json(self, content: str) -> dict:
        """Parse JSON from LLM response, stripping markdown code blocks."""
        content = content.strip()
        # Strip ```json ... ``` blocks
        if content.startswith("```"):
            content = content.split("\n", 1)[-1]  # Remove first line (```json)
            content = content.rsplit("```", 1)[0]  # Remove last line (```)
            content = content.strip()

        return json.loads(content)

    def __repr__(self) -> str:
        return f"ProviderClient({self.provider.name}, {self.provider.model})"


class LLMClient:
    """Unified multi-provider LLM client.

    Modes:
    - fallback: Try providers in priority order, cascade on failure
    - concurrent: Fire all providers simultaneously, use first success
    """

    SYSTEM_PROMPT = """你是 A 股投研分析助手，仅基于用户提供的数据进行分析。

规则：
1. 只使用用户提供的 JSON 数据，不得编造任何数字、公告、资金数据
2. 数据缺失时，status 设为 "unavailable"，summary 说明缺失原因
3. 输出必须是合法 json 格式，不含 markdown 代码块
4. 不做买卖建议，不使用「必涨」「必买」等词汇
5. summary 100-200 字，focus_points 和 risk_points 各 1-3 条"""

    def __init__(self, config: Optional[LLMConfig] = None):
        self.config = config or LLMConfig.default()
        # Initialize provider clients sorted by priority
        self.providers = [
            ProviderClient(p) for p in sorted(self.config.providers, key=lambda p: p.priority)
        ]

    @property
    def available_providers(self) -> list[ProviderClient]:
        """Get list of configured providers with API keys."""
        return [p for p in self.providers if p.is_available]

    async def chat_json(
        self,
        user_prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> dict:
        """Send chat request expecting JSON response.

        Uses fallback or concurrent mode based on config.
        Returns parsed JSON dict.
        """
        messages = [
            {"role": "system", "content": system_prompt or self.SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        available = self.available_providers
        if not available:
            logger.error("No LLM providers configured")
            return self._unavailable_result()

        if self.config.mode == "concurrent" and len(available) > 1:
            return await self._concurrent_json(messages, available, temperature, max_tokens)
        else:
            return await self._fallback_json(messages, available, temperature, max_tokens)

    async def _fallback_json(
        self,
        messages: list[dict],
        providers: list[ProviderClient],
        temperature: Optional[float],
        max_tokens: Optional[int],
    ) -> dict:
        """Try providers in order, fallback on failure."""
        last_error = None

        for provider in providers:
            try:
                result = await provider.chat(
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    json_mode=True,
                )
                logger.debug("LLM response from %s", provider.provider.name)
                return result
            except Exception as e:
                last_error = e
                logger.warning("Provider '%s' failed, trying next: %s", provider.provider.name, e)
                continue

        # All providers failed
        logger.error("All LLM providers failed: %s", last_error)
        return {
            "status": "failed",
            "sentiment": "neutral",
            "summary": f"所有 LLM 调用失败: {last_error}",
            "focus_points": [],
            "risk_points": [],
        }

    async def _concurrent_json(
        self,
        messages: list[dict],
        providers: list[ProviderClient],
        temperature: Optional[float],
        max_tokens: Optional[int],
    ) -> dict:
        """Fire all providers simultaneously, use first success."""
        async def try_provider(p: ProviderClient) -> tuple[ProviderClient, dict | Exception]:
            try:
                result = await p.chat(
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    json_mode=True,
                )
                return (p, result)
            except Exception as e:
                return (p, e)

        # Fire all concurrently
        tasks = [try_provider(p) for p in providers]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Use first success, prefer higher priority
        for provider in providers:
            for p, result in results:
                if isinstance(result, Exception):
                    continue
                if p is provider:
                    logger.debug("LLM concurrent response from %s", provider.provider.name)
                    return result

        # All failed
        errors = [str(r[1]) for r in results if isinstance(r[1], Exception)]
        logger.error("All concurrent LLM providers failed: %s", errors)
        return {
            "status": "failed",
            "sentiment": "neutral",
            "summary": f"所有 LLM 并发调用失败: {'; '.join(errors[:2])}",
            "focus_points": [],
            "risk_points": [],
        }

    @staticmethod
    def _unavailable_result() -> dict:
        """Return unavailable result when no providers configured."""
        return {
            "status": "unavailable",
            "sentiment": "neutral",
            "summary": "LLM API 未配置，无法分析",
            "focus_points": [],
            "risk_points": [],
        }

    def status(self) -> dict:
        """Get provider status for debugging."""
        return {
            "mode": self.config.mode,
            "providers": [
                {
                    "name": p.provider.name,
                    "model": p.provider.model,
                    "configured": p.is_available,
                    "base_url": p.provider.base_url,
                }
                for p in self.providers
            ],
        }


# Module-level singleton
_default_client: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    """Get or create the default LLM client singleton."""
    global _default_client
    if _default_client is None:
        _default_client = LLMClient()
    return _default_client
