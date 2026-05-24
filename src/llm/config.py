"""LLM Provider configuration."""

from typing import Optional

from pydantic import BaseModel


class LLMProvider(BaseModel):
    """Single LLM provider configuration."""
    name: str
    base_url: str
    api_key_env: str
    model: str
    temperature: float = 0.3
    max_tokens: int = 1024
    timeout: int = 60
    priority: int = 1  # Lower = higher priority


class LLMConfig(BaseModel):
    """Multi-provider LLM configuration."""
    providers: list[LLMProvider]
    mode: str = "fallback"  # "fallback" | "concurrent"
    max_retries: int = 2
    json_response: bool = True

    @classmethod
    def default(cls) -> "LLMConfig":
        """Default configuration with DeepSeek primary + DashScope fallback."""
        return cls(
            mode="fallback",
            providers=[
                LLMProvider(
                    name="deepseek",
                    base_url="https://api.deepseek.com",
                    api_key_env="DEEPSEEK_API_KEY",
                    model="deepseek-v4-flash",
                    temperature=0.3,
                    max_tokens=1024,
                    timeout=60,
                    priority=1,
                ),
                LLMProvider(
                    name="dashscope",
                    base_url="https://coding.dashscope.aliyuncs.com/v1",
                    api_key_env="DASHSCOPE_API_KEY",
                    model="qwen3.6-plus",
                    temperature=0.3,
                    max_tokens=1024,
                    timeout=60,
                    priority=2,
                ),
            ],
        )
