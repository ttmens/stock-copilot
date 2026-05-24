"""Pydantic data models for Stock Copilot."""

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
    north_net_inflow: Optional[float] = None
    main_net_inflow: Optional[float] = None
    period: str = "5d"


class StockSnapshot(BaseModel):
    code: str
    name: str
    fetched_at: datetime
    bars: list[OHLCVBar] = Field(default_factory=list, description="最近60个交易日")
    ma: MovingAverages = Field(default_factory=MovingAverages)
    announcements: list[Announcement] = Field(default_factory=list)
    capital: Optional[CapitalFlow] = None
    fetch_errors: list[str] = Field(default_factory=list)


class AgentResult(BaseModel):
    agent_name: str
    status: AgentStatus
    summary: str = ""
    sentiment: str = "neutral"
    focus_points: list[str] = Field(default_factory=list)
    risk_points: list[str] = Field(default_factory=list)
    raw_json: dict = Field(default_factory=dict)


class StockAnalysis(BaseModel):
    snapshot: StockSnapshot
    technical: AgentResult
    fundamental: AgentResult
    capital: AgentResult
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
