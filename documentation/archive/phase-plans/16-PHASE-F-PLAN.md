# Phase F: OODA 反馈闭环增强 — 实现计划

> **目标**: 从"给出信号"升级到"记住每次判断的结果，并据此自我改进"
>
> **借鉴来源**: tradermonty/claude-trading-skills (Signal Postmortem, Trader Memory Core, Contradiction Detection) + himself65/finance-skills (Correlation Analysis, Market Breadth)
>
> **架构**: 棕地项目，在现有 v2.0.0 基础上增量

**Architecture:** 新增 3 个核心模块 + 4 个增强项，复用现有 SQLite/SignalDB/EvolutionEngine 基础设施，不破坏现有 pipeline 接口。

**Tech Stack:** Python 3.11+, SQLite, FastAPI, APScheduler, Pydantic

---

## 三域验收标准

| 域 | 验收项 | 验证方式 |
|----|--------|----------|
| **Functional** | 所有新模块 pytest 通过 | `python -m pytest tests/ -q` |
| **Functional** | self_check 10 阶段全通过 | `python scripts/self_check.py --quick` |
| **UX** | Web 页面新增元素渲染正确 | `python scripts/ui_acceptance.py --quick` |
| **UX** | 页面不破坏现有布局 | 对比 pre/post HTML |
| **Ops** | systemd 服务正常重启 | `sudo systemctl restart stock-copilot && systemctl status` |
| **Ops** | API 端点全部可达 | `curl localhost:8000/health` + 新端点 |

---

### Task 1: 创建 Phase F 设计文档

**Objective:** 编写 Phase F 的详细设计文档，定义数据模型和接口

**Files:**
- Create: `docs/design/16-PHASE-F-PLAN.md` (本文档)

**Design Summary:**

Phase F 包含 7 个优化项，分 3 个模块群：

#### 模块群 A: 反馈闭环核心（P0）
1. **Signal Postmortem** — 逐信号结果追踪 + outcome classification
2. **Thesis/Journal** — 投资论点全生命周期管理
3. **Contradiction Detection** — 多层信号冲突检测

#### 模块群 B: 分析增强（P1）
4. **Market Breadth Score** — 市场广度 0-100 评分
5. **Strategy Stagnation Detection** — 策略停滞检测 + Pivot 建议

#### 模块群 C: 数据深化（P1-P2）
6. **Stock Correlation** — 价格相关性 + Regime-conditional
7. **Multi-timeframe Signals** — 短/中/长期多时间框架

---

### Task 2: 新增数据模型 — Postmortem & Thesis

**Objective:** 在 `src/data/models.py` 中新增 Pydantic 模型

**Files:**
- Modify: `src/data/models.py`

**新增模型:**

```python
# === Signal Postmortem ===
class SignalOutcome(str, Enum):
    TRUE_POSITIVE = "true_positive"
    FALSE_POSITIVE = "false_positive"
    MISSED_OPPORTUNITY = "missed_opportunity"
    REGIME_MISMATCH = "regime_mismatch"

class SignalPostmortem(BaseModel):
    """逐信号级 postmortem 记录"""
    signal_id: str                           # 唯一信号ID
    ticker: str
    signal_date: str                         # YYYY-MM-DD
    predicted_direction: str                 # buy / sell / hold
    fusion_score: float                      # 融合评分
    hard_score: float                        # 硬信号分
    soft_score: float                        # 软信号分
    gate_score: float                        # 门控分
    dragon_tiger_score: float               # 龙虎榜分
    announcement_score: float               # 公告分
    consensus_bonus: float = 0.0            # 辩论共识度 bonus
    contradiction_flags: list[str] = []      # 冲突标记
    market_regime: str = "unknown"           # bull/choppy/bear
    
    # 实际结果（延迟填入）
    actual_return_5d: float | None = None
    actual_return_20d: float | None = None
    outcome_category: SignalOutcome | None = None
    outcome_notes: str = ""
    recorded_at: str | None = None
    
    def classify_outcome(self) -> SignalOutcome:
        """根据预测方向和实际收益分类"""
        if self.predicted_direction == "buy":
            if self.actual_return_5d and self.actual_return_5d > 0:
                return SignalOutcome.TRUE_POSITIVE
            elif self.actual_return_5d and self.actual_return_5d < 0:
                return SignalOutcome.FALSE_POSITIVE
        elif self.predicted_direction == "sell":
            if self.actual_return_5d and self.actual_return_5d < 0:
                return SignalOutcome.TRUE_POSITIVE
            elif self.actual_return_5d and self.actual_return_5d > 0:
                return SignalOutcome.FALSE_POSITIVE
        # 更多规则...
        return SignalOutcome.REGIME_MISMATCH


# === Thesis / Journal ===
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
    """投资论点全生命周期记录"""
    thesis_id: str                           # th_{ticker}_{date}_{hash}
    ticker: str
    created_at: str
    thesis_type: ThesisType
    thesis_statement: str                    # 一句话理由（LLM生成）
    status: ThesisStatus = ThesisStatus.IDEA
    
    # 预期
    expected_holding_days: int = 10
    stop_price: float | None = None
    target_price: float | None = None
    
    # 实际（CLOSED 时填入）
    entry_price: float | None = None
    entry_date: str | None = None
    exit_price: float | None = None
    exit_date: str | None = None
    exit_reason: str = ""
    pnl_pct: float | None = None
    mae: float | None = None                 # 最大不利偏移%
    mfe: float | None = None                 # 最大有利偏移%
    
    # 来源
    source_signal_id: str | None = None
    status_history: list[dict] = []          # 状态变更历史
```

---

### Task 3: 创建 Postmortem 模块

**Objective:** 实现逐信号结果记录和 outcome 分类

**Files:**
- Create: `src/evolution/postmortem.py`
- Create: `tests/test_postmortem.py`

**核心逻辑:**

```python
class PostmortemRecorder:
    """记录和分析信号结果"""
    
    def __init__(self, db_path: str):
        self.db = sqlite3.connect(db_path)
        self._init_tables()
    
    def record_signal(self, signal: SignalPostmortem):
        """记录新信号（待后续比对结果）"""
        # INSERT INTO postmortems ...
        
    def check_mature_signals(self, fetcher, as_of: str | None = None):
        """检查已到期的信号，填入实际收益"""
        # 查询 signal_date + 5d / 20d 已到的信号
        # 调用 fetcher 获取当前价格
        # 计算 actual_return
        # 调用 classify_outcome
        # 更新记录
        
    def generate_feedback(self) -> dict:
        """生成反馈给融合权重和 Agent 的建议"""
        # 按 source_skill / thesis_type / regime 统计胜率
        # 输出权重调整建议
        return {
            "skill_feedback": [...],
            "regime_feedback": [...],
            "contradiction_patterns": [...],
        }
    
    def get_summary(self, days: int = 30) -> dict:
        """统计摘要"""
        # win_rate, avg_pnl, by_type, by_regime
```

**关键特性:**
- 复用现有 SignalDB 的 `save()` / `history()` 机制
- outcome classification 考虑 market_regime（区分信号失败和环境不匹配）
- feedback 输出结构化 JSON，可被 EvolutionEngine 消费

---

### Task 4: 创建 Thesis Manager 模块

**Objective:** 投资论点生命周期管理

**Files:**
- Create: `src/evolution/thesis.py`
- Create: `tests/test_thesis.py`

**核心逻辑:**

```python
class ThesisManager:
    """Thesis 全生命周期管理"""
    
    def create_thesis(self, signal: dict, snapshot: StockSnapshot) -> ThesisRecord:
        """从高分信号自动创建 thesis"""
        # 自动生成 thesis_type（基于信号特征）
        # LLM 生成 thesis_statement
        # 设置预期持有期、止损价
        # 写入 SQLite
        
    def transition(self, thesis_id: str, new_status: ThesisStatus, **kwargs):
        """状态转换（IDEA → ENTRY_READY → ACTIVE → CLOSED）"""
        # 验证转换合法性
        # 更新状态 + 记录 history
        
    def close_thesis(self, thesis_id: str, exit_price: float, exit_reason: str):
        """关闭 thesis，计算 P&L + MAE + MFE"""
        # 需要历史价格数据计算 MAE/MFE
        # 生成 postmortem summary
        
    def list_due_for_review(self, as_of: str) -> list[ThesisRecord]:
        """列出需要复查的 thesis"""
        
    def get_statistics(self) -> dict:
        """按 thesis_type 统计胜率、平均盈亏等"""
```

**MAE/MFE 计算:**
- 从 entry_date 到 exit_date 期间的最低/最高价
- MAE = (entry_price - min_price) / entry_price
- MFE = (max_price - entry_price) / entry_price

---

### Task 5: Contradiction 检测集成到融合引擎

**Objective:** 在 `fuse_signals()` 中增加冲突检测

**Files:**
- Modify: `src/data/signal_fusion.py`
- Create: `tests/test_contradiction.py`

**核心逻辑:**

```python
def detect_contradictions(hard: float, soft: float, gate: float, 
                          dragon_tiger: float, announcement: float) -> list[dict]:
    """检测多层信号之间的冲突"""
    contradictions = []
    
    # 硬信号 vs 软信号冲突
    if hard * soft < 0 and abs(hard) > 0.3 and abs(soft) > 0.3:
        contradictions.append({
            "type": "hard_vs_soft",
            "severity": "high",
            "hard_score": hard,
            "soft_score": soft,
            "description": "硬信号与软信号方向相反",
        })
    
    # 资金面 vs 技术面冲突
    # 龙虎榜 vs 公告冲突
    # ... 更多规则
    
    return contradictions

# 修改 fuse_signals():
def fuse_signals(..., detect_contradiction: bool = True):
    # 原有融合逻辑...
    
    contradictions = []
    if detect_contradiction:
        contradictions = detect_contradictions(hard_score, soft_score, ...)
    
    # 如果有 contradiction，降低最终 confidence
    contradiction_penalty = len(contradictions) * 0.05
    
    return FusedSignal(
        ...,
        contradiction_flags=contradictions,
        confidence=max(0, confidence - contradiction_penalty),
    )
```

---

### Task 6: Market Breadth Score 模块

**Objective:** 基于自选股池计算市场广度评分

**Files:**
- Create: `src/analysis/breadth.py`
- Create: `tests/test_breadth.py`

**核心逻辑:**

```python
class MarketBreadthScorer:
    """市场广度 0-100 评分"""
    
    def compute(self, analyses: list[StockAnalysis]) -> dict:
        """基于当日全部股票分析结果计算广度"""
        total = len(analyses)
        if total == 0:
            return {"score": 50, "zone": "neutral", "components": {}}
        
        # 6 个分量
        components = {
            "bull_ratio": sum(1 for a in analyses if a.fused_signal.score > 0.2) / total,
            "strong_bull_ratio": sum(1 for a in analyses if a.fused_signal.score > 0.6) / total,
            "avg_confidence": sum(a.fused_signal.confidence for a in analyses) / total,
            "capital_net_positive": sum(1 for a in analyses if a.hard_signals.capital_score > 0) / total,
            "ma_bullish_ratio": sum(1 for a in analyses if a.hard_signals.ma_alignment == "bullish") / total,
            "low_contradiction": sum(1 for a in analyses if not a.fused_signal.contradiction_flags) / total,
        }
        
        # 加权合成 0-100
        score = int(
            components["bull_ratio"] * 25 +
            components["strong_bull_ratio"] * 20 +
            components["avg_confidence"] * 20 +
            components["capital_net_positive"] * 15 +
            components["ma_bullish_ratio"] * 10 +
            components["low_contradiction"] * 10
        ) * 100
        
        zone = self._classify_zone(score)
        
        return {
            "score": score,
            "zone": zone,
            "components": components,
            "recommended_exposure": self._exposure_map(zone),
        }
    
    def _classify_zone(self, score: int) -> str:
        if score >= 80: return "strong"
        if score >= 60: return "healthy"
        if score >= 40: return "neutral"
        if score >= 20: return "weakening"
        return "critical"
```

**Zone → Exposure 映射:**
| Score | Zone | 建议仓位 |
|-------|------|----------|
| 80-100 | Strong | 90-100% |
| 60-79 | Healthy | 75-90% |
| 40-59 | Neutral | 60-75% |
| 20-39 | Weakening | 40-60% |
| 0-19 | Critical | 25-40% |

---

### Task 7: 策略停滞检测模块

**Objective:** 检测回测/信号准确率停滞，触发 pivot 建议

**Files:**
- Create: `src/evolution/stagnation.py`
- Create: `tests/test_stagnation.py`

**核心逻辑:**

```python
class StagnationDetector:
    """检测策略性能停滞"""
    
    def check(self, performance_history: list[dict], window: int = 10) -> dict:
        """检查最近 N 个交易日的准确率趋势"""
        if len(performance_history) < window:
            return {"status": "insufficient_data"}
        
        recent = performance_history[-window:]
        accuracies = [p["accuracy"] for p in recent]
        
        # 计算趋势（线性回归斜率）
        slope = self._linear_slope(accuracies)
        
        # 检测停滞：斜率接近 0 且方差小
        variance = np.var(accuracies)
        
        if abs(slope) < 0.001 and variance < 0.001:
            return {
                "status": "stagnant",
                "slope": slope,
                "avg_accuracy": np.mean(accuracies),
                "pivot_suggestions": self._generate_pivots(),
            }
        
        return {"status": "evolving", "slope": slope}
    
    def _generate_pivots(self) -> list[dict]:
        """生成 pivot 建议"""
        return [
            {"type": "assumption_inversion", "desc": "如果量能不能确认，只看硬信号"},
            {"type": "architecture_switch", "desc": "从 5 层融合 → 3 层核心"},
            {"type": "objective_reframe", "desc": "从准确率最大化 → 盈亏比最大化"},
        ]
```

---

### Task 8: Stock Correlation 模块

**Objective:** 计算股票间价格相关性

**Files:**
- Create: `src/data/correlation.py`
- Create: `tests/test_correlation.py`

**核心逻辑:**

```python
class StockCorrelationAnalyzer:
    """股票价格相关性分析"""
    
    def compute_pairwise(self, ticker_a: str, ticker_b: str, 
                         klines_a: list, klines_b: list,
                         window: int = 60) -> dict:
        """计算两只股票的相关性"""
        # 提取收盘价序列
        closes_a = [k.close for k in klines_a]
        closes_b = [k.close for k in klines_b]
        
        # 对齐日期
        # 计算 log returns
        # Pearson correlation
        # 滚动相关性 (60d)
        # Beta
        # Regime-conditional (up days vs down days)
        
        return {
            "correlation": corr,
            "beta": beta,
            "rolling_corr_mean": rolling_mean,
            "rolling_corr_std": rolling_std,
            "up_day_corr": up_corr,
            "down_day_corr": down_corr,
            "correlation_stability": "stable" if rolling_std < 0.1 else "unstable",
        }
    
    def find_correlated(self, target: str, candidates: list[dict], 
                        target_klines: list) -> list[dict]:
        """找出与目标股最相关的股票"""
        results = []
        for c in candidates:
            corr = self.compute_pairwise(target, c["ticker"], 
                                        target_klines, c["klines"])
            results.append({**c, **corr})
        return sorted(results, key=lambda x: abs(x["correlation"]), reverse=True)
```

---

### Task 9: 多时间框架信号

**Objective:** 增加短/中/长期多时间维度信号

**Files:**
- Modify: `src/data/hard_signals.py`
- Create: `tests/test_multitimeframe.py`

**修改内容:**

```python
# 在 HardSignals 中新增:
class HardSignals(BaseModel):
    # 现有字段...
    momentum_20d: float
    momentum_5d: float
    
    # 新增: 多时间框架
    momentum_60d: float = 0.0        # 中期动量
    momentum_score_short: float = 0.0   # 5d 动量得分
    momentum_score_medium: float = 0.0  # 20d 动量得分
    momentum_score_long: float = 0.0    # 60d 动量得分
    timeframe_consistency: str = "unknown"  # consistent / mixed / conflicting

def compute_multi_timeframe_momentum(klines: list) -> dict:
    """计算多时间框架动量"""
    closes = [k.close for k in klines]
    
    momentum_5d = (closes[-1] - closes[-5]) / closes[-5] * 100 if len(closes) >= 5 else 0
    momentum_20d = (closes[-1] - closes[-20]) / closes[-20] * 100 if len(closes) >= 20 else 0
    momentum_60d = (closes[-1] - closes[-60]) / closes[-60] * 100 if len(closes) >= 60 else 0
    
    # 一致性检查
    directions = []
    if momentum_5d > 1: directions.append("up")
    elif momentum_5d < -1: directions.append("down")
    if momentum_20d > 2: directions.append("up")
    elif momentum_20d < -2: directions.append("down")
    if momentum_60d > 3: directions.append("up")
    elif momentum_60d < -3: directions.append("down")
    
    if len(set(directions)) <= 1:
        consistency = "consistent"
    elif len(set(directions)) == 2:
        consistency = "mixed"
    else:
        consistency = "conflicting"
    
    return {
        "momentum_5d": momentum_5d,
        "momentum_20d": momentum_20d,
        "momentum_60d": momentum_60d,
        "timeframe_consistency": consistency,
    }
```

---

### Task 10: 数据库迁移 — 新增表

**Objective:** 在 SQLite 中新增 postmortems 和 theses 表

**Files:**
- Modify: `src/data/db_manager.py`

**新增表结构:**

```sql
-- Signal Postmortem 表
CREATE TABLE IF NOT EXISTS signal_postmortems (
    signal_id TEXT PRIMARY KEY,
    ticker TEXT NOT NULL,
    signal_date TEXT NOT NULL,
    predicted_direction TEXT NOT NULL,
    fusion_score REAL NOT NULL,
    hard_score REAL,
    soft_score REAL,
    gate_score REAL,
    dragon_tiger_score REAL,
    announcement_score REAL,
    consensus_bonus REAL DEFAULT 0,
    contradiction_flags TEXT DEFAULT '[]',
    market_regime TEXT DEFAULT 'unknown',
    actual_return_5d REAL,
    actual_return_20d REAL,
    outcome_category TEXT,
    outcome_notes TEXT DEFAULT '',
    recorded_at TEXT
);

-- Thesis 表
CREATE TABLE IF NOT EXISTS theses (
    thesis_id TEXT PRIMARY KEY,
    ticker TEXT NOT NULL,
    created_at TEXT NOT NULL,
    thesis_type TEXT NOT NULL,
    thesis_statement TEXT,
    status TEXT DEFAULT 'idea',
    expected_holding_days INTEGER DEFAULT 10,
    stop_price REAL,
    target_price REAL,
    entry_price REAL,
    entry_date TEXT,
    exit_price REAL,
    exit_date TEXT,
    exit_reason TEXT DEFAULT '',
    pnl_pct REAL,
    mae REAL,
    mfe REAL,
    source_signal_id TEXT,
    status_history TEXT DEFAULT '[]'
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_postmortems_ticker ON signal_postmortems(ticker);
CREATE INDEX IF NOT EXISTS idx_postmortems_outcome ON signal_postmortems(outcome_category);
CREATE INDEX IF NOT EXISTS idx_theses_status ON theses(status);
```

---

### Task 11: Pipeline 集成 — 自动记录信号

**Objective:** 在 `run_analysis()` 中自动记录信号到 postmortem

**Files:**
- Modify: `src/orchestrator/pipeline.py`

**修改点:**

```python
# 在 run_analysis() 的信号保存阶段:
from evolution.postmortem import PostmortemRecorder
from evolution.thesis import ThesisManager

# 1. 记录信号到 postmortem
recorder = PostmortemRecorder(db_path)
for analysis in analyses:
    signal = SignalPostmortem(
        signal_id=f"sig_{analysis.code}_{signal_date}_{hash}",
        ticker=analysis.code,
        signal_date=signal_date,
        predicted_direction=analysis.fused_signal.signal,
        fusion_score=analysis.fused_signal.score,
        hard_score=analysis.fused_signal.hard_score,
        soft_score=analysis.fused_signal.soft_score,
        # ...
    )
    recorder.record_signal(signal)
    
    # 2. 高分信号自动创建 thesis
    if analysis.fused_signal.score > 0.4:
        thesis_mgr.create_thesis(analysis.fused_signal, analysis)
```

---

### Task 12: API 端点新增

**Objective:** 新增 API 端点暴露 postmortem / thesis / breadth 数据

**Files:**
- Modify: `src/api/routes.py`

**新增端点:**

```python
# Postmortem
@app.get("/api/postmortems")
async def get_postmortems(ticker: str = None, outcome: str = None, days: int = 30):
    """查询 postmortem 记录"""

@app.get("/api/postmortems/summary")
async def get_postmortem_summary(days: int = 30):
    """postmortem 统计摘要"""

@app.post("/api/postmortems/check-mature")
async def check_mature_signals():
    """手动触发成熟信号检查"""

# Thesis
@app.get("/api/theses")
async def get_theses(status: str = None, ticker: str = None):
    """查询 thesis 列表"""

@app.post("/api/theses/{thesis_id}/transition")
async def transition_thesis(thesis_id: str, status: str):
    """thesis 状态转换"""

@app.get("/api/theses/statistics")
async def get_thesis_statistics():
    """thesis 统计"""

# Market Breadth
@app.get("/api/breadth")
async def get_market_breadth():
    """当前市场广度评分"""

# Correlation
@app.get("/api/correlation/{ticker}")
async def get_stock_correlation(ticker: str):
    """股票相关性分析"""

# Stagnation
@app.get("/api/stagnation")
async def get_stagnation_status():
    """策略停滞检测状态"""
```

---

### Task 13: UI 更新 — 新增元素渲染

**Objective:** 在 Web 页面中展示新模块的数据

**Files:**
- Modify: `src/site/generator.py` (Jinja2 模板)

**新增 UI 元素:**

1. **顶栏新增 "市场温度计"**
   - 显示 Market Breadth Score (0-100)
   - 颜色映射: green (>60), yellow (40-60), red (<40)
   - 显示 Zone 名称

2. **股票卡片新增 "矛盾标记"**
   - 当 contradiction_flags 非空时显示 ⚠️ 图标
   - 悬停显示冲突详情

3. **股票卡片新增 "时间框架一致性"**
   - 显示 🟢 一致 / 🟡 混合 / 🔴 冲突

4. **新增 "投资论点" 区域**
   - 列出 ACTIVE 状态的 thesis
   - 显示 thesis_type、entry_price、当前盈亏
   - 链接到详情页（如有）

5. **新增 "信号复盘" 区域**
   - 显示最近 30 天的信号统计
   - 按 outcome 分类的柱状图

**注意:** 遵循现有设计规范，零 CDN，单一 theme.css，深色 fintech 主题

---

### Task 14: EvolutionEngine 集成 postmortem feedback

**Objective:** 让 OODA 循环消费 postmortem 反馈

**Files:**
- Modify: `src/evolution/engine.py`
- Modify: `src/evolution/optimizer.py`

**修改点:**

```python
# 在 EvolutionEngine.run() 中:
from evolution.postmortem import PostmortemRecorder

def run_evolution(self):
    # 1. PerformanceTracker 现有逻辑...
    
    # 2. 新增: 消费 postmortem feedback
    recorder = PostmortemRecorder(self.db_path)
    feedback = recorder.generate_feedback()
    
    # 3. WeightOptimizer 现在也考虑 postmortem 数据
    optimizer.optimize(
        performance_data=tracker.get_data(),
        postmortem_feedback=feedback,
    )
    
    # 4. 检查停滞
    detector = StagnationDetector()
    stagnation = detector.check(tracker.get_history())
    if stagnation["status"] == "stagnant":
        # 记录 pivot 建议，待人工审核
        self._log_stagnation(stagnation)
```

---

### Task 15: 调度器新增 job — 自动检查成熟信号

**Objective:** 每日 16:00 的 OODA 循环中增加 postmortem 检查

**Files:**
- Modify: `src/scheduler/jobs.py`

**修改点:**

```python
# 在每日 16:00 job 中:
def daily_evolution_job():
    # 原有逻辑: PerformanceTracker + WeightOptimizer + StockPoolManager
    
    # 新增:
    # 1. 检查成熟信号
    recorder = PostmortemRecorder(db_path)
    recorder.check_mature_signals(fetcher)
    
    # 2. 检查 thesis 是否需要 review
    thesis_mgr = ThesisManager(db_path)
    due_theses = thesis_mgr.list_due_for_review(as_of=today)
    for thesis in due_theses:
        # 触发复查逻辑
        pass
```

---

### Task 16: 测试 — 全部新模块

**Objective:** 为所有新模块编写单元测试

**Files:**
- Create: `tests/test_postmortem.py`
- Create: `tests/test_thesis.py`
- Create: `tests/test_contradiction.py`
- Create: `tests/test_breadth.py`
- Create: `tests/test_stagnation.py`
- Create: `tests/test_correlation.py`
- Create: `tests/test_multitimeframe.py`

**验收标准:**
- 所有测试通过: `python -m pytest tests/ -v`
- 覆盖核心逻辑和边界情况
- mock 外部依赖（LLM、网络请求）

---

### Task 17: 更新 SSOT 文档

**Objective:** 更新 CURRENT-STATUS.md 和 workflow_state.yaml

**Files:**
- Modify: `docs/design/08-CURRENT-STATUS.md`
- Modify: `docs/workflow_state.yaml`
- Modify: `docs/DECISIONS.md` (新增 Phase F 决策)

**更新内容:**
- 新增 Phase F 章节到 CURRENT-STATUS.md
- 更新版本号到 v2.1.0
- 新增模块到架构总览
- workflow_state.yaml 更新 current_phase 到 phase_f

---

### Task 18: 系统深度自检

**Objective:** 全面验证所有改动

**验证步骤:**

```bash
# 1. 单元测试
cd /home/ubuntu/repos/stock-copilot
python -m pytest tests/ -v

# 2. 自检脚本
python scripts/self_check.py --quick

# 3. 重启服务
sudo systemctl restart stock-copilot
sleep 5
curl -s localhost:8000/health | python -m json.tool

# 4. API 端点验证
curl -s localhost:8000/api/breadth | python -m json.tool
curl -s localhost:8000/api/theses | python -m json.tool
curl -s localhost:8000/api/postmortems | python -m json.tool

# 5. UI 验收
python scripts/ui_acceptance.py --quick

# 6. 文档一致性
python scripts/check_docs_ssot.py --project-root .
```

---

## 实施顺序

按依赖关系排序:

1. **Task 1-2**: 数据模型定义
2. **Task 10**: 数据库迁移
3. **Task 3-4**: Postmortem + Thesis 核心逻辑
4. **Task 5**: Contradiction 检测
5. **Task 6**: Market Breadth
6. **Task 8**: Stock Correlation
7. **Task 9**: Multi-timeframe
8. **Task 7**: Stagnation Detection
9. **Task 11**: Pipeline 集成
10. **Task 14**: EvolutionEngine 集成
11. **Task 15**: 调度器更新
12. **Task 12**: API 端点
13. **Task 13**: UI 更新
14. **Task 16**: 测试
15. **Task 17**: 文档更新
16. **Task 18**: 自检

## 风险与应对

| 风险 | 应对 |
|------|------|
| 数据库迁移破坏现有数据 | 迁移前备份 stock.db，使用 ALTER TABLE 而非 DROP |
| LLM 调用增加导致超时 | thesis_statement 生成使用异步非阻塞，不影响主流程 |
| UI 改动破坏布局 | 遵循 theme.css 变量，增量添加，不修改现有结构 |
| 回测数据不足 | postmortem 需要时间积累，首日只记录不分析 |
