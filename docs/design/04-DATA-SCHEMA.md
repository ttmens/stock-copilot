# 数据模型

## 更新记录

- **2026-05-22**: 初始版本
- **2026-05-24**: 新增 ValuationInfo, NewsItem, DragonTigerItem, LatestJson* 系列；StockSnapshot 扩展估值/新闻/龙虎榜字段；更新 settings.yaml 示例为多 provider 格式
- **2026-05-25**: StockAnalysis 新增 announcement 字段 (AgentResult)；LatestJsonStock 扩展 signal_breakdown / dragon_tiger / announcement 字段

## 1. Pydantic 模型（src/data/models.py）

```python
from datetime import date, datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ReportType(str, Enum):
    PRE = "pre"
    POST = "post"


class AgentStatus(str, Enum):
    OK = "ok"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


class WatchlistItem(BaseModel):
    code: str = Field(..., description="6位股票代码，如 600519")
    name: str


class OHLCVBar(BaseModel):
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: Optional[float] = None


class MovingAverages(BaseModel):
    ma5: Optional[float] = None
    ma10: Optional[float] = None
    ma20: Optional[float] = None


class Announcement(BaseModel):
    title: str
    date: date
    url: Optional[str] = None


class CapitalFlow(BaseModel):
    north_net_inflow: Optional[float] = None      # 北向净流入（万元）
    main_net_inflow: Optional[float] = None       # 主力净流入
    period: str = "5d"                            # 统计周期


class ValuationInfo(BaseModel):
    """PE/PB/市值/行业 — 来自东财 push2 或腾讯财经"""
    pe_ttm: Optional[float] = None
    pb: Optional[float] = None
    ps_ttm: Optional[float] = None
    roe: Optional[float] = None
    total_shares: float = 0
    float_shares: float = 0
    mcap: float = 0           # 总市值(元)
    float_mcap: float = 0     # 流通市值(元)
    industry: str = ""
    list_date: str = ""


class NewsItem(BaseModel):
    """新闻条目（目前 API 暂时禁用，返回空列表）"""
    title: str
    url: str = ""
    date: str = ""
    source: str = ""


class DragonTigerItem(BaseModel):
    """龙虎榜条目 — 来自东财 datacenter"""
    date: str = ""
    reason: str = ""
    net_buy: float = 0
    buy_amount: float = 0
    sell_amount: float = 0


class StockSnapshot(BaseModel):
    code: str
    name: str
    fetched_at: datetime
    bars: list[OHLCVBar] = Field(default_factory=list, description="最近60个交易日")
    ma: MovingAverages = Field(default_factory=MovingAverages)
    announcements: list[Announcement] = Field(default_factory=list)
    capital: Optional[CapitalFlow] = None
    fetch_errors: list[str] = Field(default_factory=list)

    # 扩展字段
    valuation: Optional[ValuationInfo] = None
    news: list[NewsItem] = Field(default_factory=list)
    dragon_tiger: list[DragonTigerItem] = Field(default_factory=list)


class AgentResult(BaseModel):
    agent_name: str                               # technical | fundamental | capital
    status: AgentStatus
    summary: str = ""                             # 100-200字摘要
    sentiment: str = "neutral"                    # bullish | bearish | neutral
    focus_points: list[str] = Field(default_factory=list)
    risk_points: list[str] = Field(default_factory=list)
    raw_json: dict = Field(default_factory=dict)


class StockAnalysis(BaseModel):
    snapshot: StockSnapshot
    technical: AgentResult
    fundamental: AgentResult
    capital: AgentResult
    announcement: AgentResult = Field(default_factory=lambda: AgentResult(
        agent_name="announcement", status=AgentStatus.UNAVAILABLE, sentiment="neutral", summary="无公告数据"
    ))
    overall_sentiment: str = "neutral"
    overall_focus: str = ""


class MarketOverview(BaseModel):
    index_code: str = "000001"
    index_name: str = "上证指数"
    close: Optional[float] = None
    change_pct: Optional[float] = None


class Report(BaseModel):
    report_type: ReportType
    generated_at: datetime
    trade_date: date
    market: Optional[MarketOverview] = None
    analyses: list[StockAnalysis]
    failed_symbols: list[str] = Field(default_factory=list)
    markdown: str = ""
    file_path: Optional[str] = None
```

## 2. 站点数据模型（src/data/models.py — 底部）

```python
# Site data models
class LatestJsonStock(BaseModel):
    code: str
    name: str
    overall_sentiment: str
    overall_focus: str
    technical: dict
    fundamental: dict
    capital: dict
    risk_points: list[str]


class LatestJsonMeta(BaseModel):
    report_type: str
    trade_date: str
    generated_at: str
    symbol_count: int
    disclaimer: str


class LatestJsonArchiveItem(BaseModel):
    date: str
    type: str
    url: str


class LatestJson(BaseModel):
    meta: LatestJsonMeta
    market: dict
    stocks: list[LatestJsonStock]
    failed_symbols: list[str] = Field(default_factory=list)
    archive: list[LatestJsonArchiveItem] = Field(default_factory=list)
```

## 3. LLM 配置模型（src/llm/config.py）

```python
class LLMProvider(BaseModel):
    """Single LLM provider configuration."""
    name: str
    base_url: str
    api_key_env: str              # 环境变量名，如 "DEEPSEEK_API_KEY"
    model: str
    temperature: float = 0.3
    max_tokens: int = 1024
    timeout: int = 60
    priority: int = 1             # 数字越小优先级越高


class LLMConfig(BaseModel):
    """Multi-provider LLM configuration."""
    providers: list[LLMProvider]
    mode: str = "fallback"        # "fallback" | "concurrent"
    max_retries: int = 2
    json_response: bool = True
```

## 4. Settings 配置模型（src/config.py）

```python
class LLMConfig(BaseModel):
    """多 provider LLM 配置（config.py 中的版本，含向后兼容字段）"""
    providers: list[dict] = Field(default_factory=list)
    mode: str = "fallback"
    max_retries: int = 2
    # 向后兼容（单 provider 旧格式）
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
    llm: LLMConfig
    schedule: ScheduleConfig
    notify: NotifyConfig
    data: DataConfig
    report: ReportConfig
    site: SiteConfig
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
```

## 5. LLM 输出 JSON Schema（Agent 必须返回）

```json
{
  "status": "ok | unavailable | failed",
  "sentiment": "bullish | bearish | neutral",
  "summary": "string, 100-200字",
  "focus_points": ["string"],
  "risk_points": ["string"]
}
```

## 6. watchlist.yaml

```yaml
symbols:
  - code: "600519"
    name: "贵州茅台"
  - code: "000001"
    name: "平安银行"
  - code: "300750"
    name: "宁德时代"
```

## 7. settings.yaml（完整多 provider 示例）

```yaml
llm:
  mode: "fallback"             # "fallback" | "concurrent"
  max_retries: 2

  providers:
    - name: "deepseek"
      base_url: "https://api.deepseek.com"
      api_key_env: "DEEPSEEK_API_KEY"
      model: "deepseek-v4-flash"
      temperature: 0.3
      max_tokens: 1024
      timeout: 60
      priority: 1

    - name: "dashscope"
      base_url: "https://coding.dashscope.aliyuncs.com/v1"
      api_key_env: "DASHSCOPE_API_KEY"
      model: "qwen3.6-plus"
      temperature: 0.3
      max_tokens: 1024
      timeout: 60
      priority: 2

schedule:
  pre_market: "08:30"
  post_market: "16:00"
  timezone: "Asia/Shanghai"

notify:
  type: "wecom"          # wecom | email
  wecom_webhook: "${WECOM_WEBHOOK}"

data:
  bar_count: 60
  announcement_days: 7
  retry: 1
  retry_delay: 1

report:
  include_market_overview: true
  output_dir: "output/reports"

site:
  output_dir: "site"
  archive_dir: "site/archive"
  data_dir: "site/data"
```

## 8. .env.example

```
DEEPSEEK_API_KEY=sk-xxx
DASHSCOPE_API_KEY=sk-xxx

WECOM_WEBHOOK=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=***

# email 模式（可选）
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
SMTP_TO=

# GitHub 发布（可选）
GITHUB_TOKEN=ghp_xxx
```
