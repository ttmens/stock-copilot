"""Configuration loader — YAML + .env via pydantic-settings."""

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve project root (parent of src/)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_CONFIG_DIR = _PROJECT_ROOT / "config"


def _load_yaml(path: Path) -> dict:
    if path.exists():
        with open(path) as f:
            return yaml.safe_load(f) or {}
    return {}


class LLMConfig(BaseModel):
    """Multi-provider LLM configuration."""
    providers: list[dict] = Field(default_factory=list)
    mode: str = "fallback"  # "fallback" | "concurrent"
    max_retries: int = 2
    # Backward compat (single-provider legacy)
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-chat"
    temperature: float = 0.3
    max_tokens: int = 1024
    timeout: int = 60


class ScheduleConfig(BaseModel):
    pre_market: str = "08:30"
    post_market: str = "16:00"
    timezone: str = "Asia/Shanghai"


class NotifyConfig(BaseModel):
    type: Literal["wecom", "email"] = "wecom"
    wecom_webhook: str = ""


class DataConfig(BaseModel):
    bar_count: int = 60
    announcement_days: int = 7
    retry: int = 3
    retry_delay: int = 2


class ReportConfig(BaseModel):
    include_market_overview: bool = True
    output_dir: str = "output/reports"


class SiteConfig(BaseModel):
    output_dir: str = "site"
    archive_dir: str = "site/archive"
    data_dir: str = "site/data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    llm: LLMConfig = Field(default_factory=LLMConfig)
    schedule: ScheduleConfig = Field(default_factory=ScheduleConfig)
    notify: NotifyConfig = Field(default_factory=NotifyConfig)
    data: DataConfig = Field(default_factory=DataConfig)
    report: ReportConfig = Field(default_factory=ReportConfig)
    site: SiteConfig = Field(default_factory=SiteConfig)

    # Env-based secrets
    deepseek_api_key: str = ""
    openai_api_key: str = ""
    openai_base_url: str = ""
    wecom_webhook: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_to: str = ""
    github_token: str = ""

    @classmethod
    def from_yaml(cls, yaml_path: Path | None = None) -> "Settings":
        """Load settings from YAML file, overriding with env vars."""
        if yaml_path is None:
            yaml_path = _CONFIG_DIR / "settings.yaml"

        cfg = _load_yaml(yaml_path)

        # Load .env for secrets
        env_file = _PROJECT_ROOT / ".env"
        load_dotenv(env_file)

        # Build kwargs for Settings
        kwargs: dict = {}
        if "llm" in cfg:
            kwargs["llm"] = LLMConfig(**cfg["llm"])
        if "schedule" in cfg:
            kwargs["schedule"] = ScheduleConfig(**cfg["schedule"])
        if "notify" in cfg:
            kwargs["notify"] = NotifyConfig(**cfg["notify"])
        if "data" in cfg:
            kwargs["data"] = DataConfig(**cfg["data"])
        if "report" in cfg:
            kwargs["report"] = ReportConfig(**cfg["report"])
        if "site" in cfg:
            kwargs["site"] = SiteConfig(**cfg["site"])

        # Override notify.wecom_webhook from env
        wecom_env = os.getenv("WECOM_WEBHOOK", "")
        if wecom_env:
            nc = kwargs.get("notify", NotifyConfig())
            nc.wecom_webhook = wecom_env
            kwargs["notify"] = nc

        # Env secrets
        kwargs["deepseek_api_key"] = os.getenv("DEEPSEEK_API_KEY", "")
        kwargs["openai_api_key"] = os.getenv("OPENAI_API_KEY", "")
        kwargs["openai_base_url"] = os.getenv("OPENAI_BASE_URL", "")
        kwargs["wecom_webhook"] = wecom_env
        kwargs["smtp_host"] = os.getenv("SMTP_HOST", "")
        kwargs["smtp_port"] = int(os.getenv("SMTP_PORT", "587"))
        kwargs["smtp_user"] = os.getenv("SMTP_USER", "")
        kwargs["smtp_password"] = os.getenv("SMTP_PASSWORD", "")
        kwargs["smtp_to"] = os.getenv("SMTP_TO", "")
        kwargs["github_token"] = os.getenv("GITHUB_TOKEN", "")

        return cls(**kwargs)

    def get_llm_api_key(self) -> str:
        """Return the active LLM API key."""
        return self.deepseek_api_key or self.openai_api_key

    def get_llm_base_url(self) -> str:
        """Return the active LLM base URL."""
        return self.openai_base_url or self.llm.base_url


@lru_cache
def get_settings() -> Settings:
    """Cached singleton — call once at startup."""
    return Settings.from_yaml()
