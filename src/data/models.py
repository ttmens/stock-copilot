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


class ValuationInfo(BaseModel):
    """PE/PB/market cap/industry from Eastmoney or Tencent."""
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
    """News item from Eastmoney or announcements."""
    title: str
    url: str = ""
    date: str = ""
    source: str = ""


class DragonTigerItem(BaseModel):
    """Dragon & tiger list (龙虎榜) entry."""
    date: str = ""
    reason: str = ""
    net_buy: float = 0
    buy_amount: float = 0
    sell_amount: float = 0
    participants: list[dict] = Field(default_factory=list)


class StockSnapshot(BaseModel):
    code: str
    name: str
    fetched_at: datetime
    bars: list[OHLCVBar] = Field(default_factory=list, description="最近60个交易日")
    ma: MovingAverages = Field(default_factory=MovingAverages)
    announcements: list[Announcement] = Field(default_factory=list)
    capital: Optional[CapitalFlow] = None
    fetch_errors: list[str] = Field(default_factory=list)

    # Extended fields (a-stock-data V3.1 integration)
    valuation: Optional[ValuationInfo] = None
    news: list[NewsItem] = Field(default_factory=list)
    dragon_tiger: list[DragonTigerItem] = Field(default_factory=list)


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
    announcement: AgentResult = Field(default_factory=lambda: AgentResult(
        agent_name="announcement", status=AgentStatus.UNAVAILABLE, sentiment="neutral", summary="无公告数据"
    ))
    overall_sentiment: str = "neutral"
    overall_focus: str = ""
    overall_summary: str = ""
    key_basis: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    signal_breakdown: dict = Field(default_factory=dict)
    hard_metrics: dict = Field(default_factory=dict)

    # D1: Debate results (MiroFish-inspired multi-agent interaction)
    debate: Optional[dict] = Field(default=None, description="辩论交互结果：consensus_score, disagreements, shifts")
    # D2: Related stocks from graph
    related_stocks: list[dict] = Field(default_factory=list, description="关联股票：同行业/同概念的信号联动")


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
    consensus_score: Optional[float] = Field(default=None, description="辩论共识分数 0-1")
    debate: Optional[dict] = Field(default=None, description="辩论交互结果")


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


# ─── Signal Postmortem models ────────────────────────────────────────

class SignalOutcome(str, Enum):
    TRUE_POSITIVE = "true_positive"
    FALSE_POSITIVE = "false_positive"
    MISSED_OPPORTUNITY = "missed_opportunity"
    REGIME_MISMATCH = "regime_mismatch"


class SignalPostmortem(BaseModel):
    signal_id: str
    ticker: str
    signal_date: date
    predicted_direction: str = Field(..., description="up/down/sideways")
    fusion_score: float = 0.0
    hard_score: float = 0.0
    soft_score: float = 0.0
    gate_score: float = 0.0
    dragon_tiger_score: float = 0.0
    announcement_score: float = 0.0
    consensus_bonus: float = 0.0
    contradiction_flags: list[str] = Field(default_factory=list)
    market_regime: str = Field(default="", description="bull/bear/oscillation")
    actual_return_5d: Optional[float] = None
    actual_return_20d: Optional[float] = None
    outcome_category: Optional[SignalOutcome] = None
    outcome_notes: str = ""
    recorded_at: datetime = Field(default_factory=datetime.now)


# ─── Thesis Record models ────────────────────────────────────────────

class ThesisType(str, Enum):
    MOMENTUM_BREAKOUT = "momentum_breakout"
    VALUATION_REPAIR = "valuation_repair"
    CAPITAL_DRIVEN = "capital_driven"
    EVENT_CATALYST = "event_catalyst"
    SECTOR_ROTATION = "sector_rotation"


class ThesisStatus(str, Enum):
    IDEA = "idea"
    ENTRY_READY = "entry_ready"
    ACTIVE = "active"
    CLOSED = "closed"
    INVALIDATED = "invalidated"


class ThesisRecord(BaseModel):
    thesis_id: str
    ticker: str
    created_at: datetime = Field(default_factory=datetime.now)
    thesis_type: ThesisType
    thesis_statement: str = Field(..., description="投资逻辑陈述")
    status: ThesisStatus = ThesisStatus.IDEA
    expected_holding_days: Optional[int] = None
    stop_price: Optional[float] = None
    target_price: Optional[float] = None
    entry_price: Optional[float] = None
    entry_date: Optional[date] = None
    exit_price: Optional[float] = None
    exit_date: Optional[date] = None
    exit_reason: str = ""
    pnl_pct: Optional[float] = None
    mae: Optional[float] = Field(default=None, description="最大不利偏离 Maximum Adverse Excursion")
    mfe: Optional[float] = Field(default=None, description="最大有利偏离 Maximum Favorable Excursion")
    source_signal_id: Optional[str] = None
    status_history: list[dict] = Field(default_factory=list, description="状态变更记录: {status, changed_at, reason}")
