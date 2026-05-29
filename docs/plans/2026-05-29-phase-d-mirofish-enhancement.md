# Phase D: MiroFish-Inspired Multi-Agent Enhancement

> 借鉴 MiroFish 群体智能引擎核心模式，将 Stock Copilot 从「3 Agent 独立分析 → 线性融合」升级为「多 Agent 辩论交互 + 图谱关联 + 场景推演」的智能体系统。

## 背景

MiroFish (https://github.com/666ghj/MiroFish) 是一个群体智能预测引擎，核心能力：
- 从种子文本自动构建知识图谱（本体 + 实体 + 关系 + 时序）
- 生成带个性/立场的 Agent Profile，在平行世界中自由交互
- Agent 之间互相影响 → 群体共识涌现
- ReportAgent 用 ReACT 模式深度分析模拟结果

本文档定义从 MiroFish 借鉴的 5 个核心优化点及落地计划。

## 优化点总览

| # | 优化点 | MiroFish 模式 | SC 现状 | 预期收益 |
|---|--------|--------------|---------|---------|
| D1 | 多 Agent 辩论交互 | Agent 互相影响 → 共识涌现 | 3 Agent 独立分析，互不可见 | 减少 LLM 偏见，发现盲区，分歧=风险信号 |
| D2 | 股票关系图谱 | Zep 图谱：实体+关系+时序 | SQLite 扁平表，每只股票孤立 | 分析时自动获取行业/概念/资金联动上下文 |
| D3 | ReACT 深度分析 | ReportAgent 规划→检索→撰写 | 模板填充式报告 | 主动追问异常数据、对比历史、交叉验证 |
| D4 | 场景推演模拟 | 上帝视角注入变量推演 | 无假设分析能力 | "如果龙头跌停→我的持仓影响多大？" |
| D5 | Agent 动态进化 | Agent 积累记忆/改变立场 | 进化系统只调权重，prompt 固定 | 追踪 Agent 维度准确率，动态优化 prompt |

---

## D1: 多 Agent 辩论交互 (debate_fusion)

### 设计

```
传统流程:
  数据 → TechnicalAgent ─┐
  数据 → CapitalAgent   ─┼→ fuse_signals() → 最终信号
  数据 → FundamentalAgent┘

辩论流程:
  Round 1: 数据 → TechnicalAgent ─┐
           数据 → CapitalAgent   ─┼→ 各自独立分析（不变）
           数据 → FundamentalAgent┘
                    ↓
           收集 3 个 AgentResult
                    ↓
  Round 2: 构造辩论 prompt:
    "你是技术面分析师。以下是资金面和基本面分析师的观点：
     [资金面]: bullish, 主力资金连续3日净流入...
     [基本面]: neutral, PE处于历史中位数...
     请评估：你是否同意？是否有补充或反驳？"
                    ↓
           3 个 Agent 各看到其他 2 个的结论 → 修正/确认/反驳
                    ↓
           汇总 Round 1 + Round 2 → 计算共识度
                    ↓
           共识度 → 新增 confidence 因子
           分歧点 → 新增 risk_points
```

### 共识度算法
```python
# 3 Agent sentiment 一致性
sentiments = [t.sentiment, c.sentiment, f.sentiment]  # bullish/bearish/neutral
if all same direction: consensus = 1.0
if 2 same, 1 neutral: consensus = 0.7
if 2 same, 1 opposite: consensus = 0.4
if all different: consensus = 0.2

# 共识度融入 confidence
final_confidence = 0.6 * old_confidence + 0.4 * consensus
```

### 文件变更
- **NEW** `src/agents/debate.py` — DebateOrchestrator
- **MOD** `src/orchestrator/pipeline.py` — _analyze_and_fuse() 加辩论轮
- **MOD** `src/data/models.py` — StockAnalysis 加 debate 字段
- **MOD** `src/data/signal_fusion.py` — consensus 融入 confidence

---

## D2: 股票关系图谱 (stock_graph)

### 设计
轻量级 SQLite 关系图谱（不引入外部图数据库）：

```sql
-- 新增表
CREATE TABLE stock_relations (
    source_code TEXT,
    target_code TEXT,
    relation_type TEXT,  -- same_industry / same_concept / supply_chain / capital_flow / sentiment_spillover
    strength REAL,       -- 0.0 ~ 1.0
    valid_from DATE,
    valid_to DATE,       -- NULL = still valid
    source TEXT          -- how discovered: manual / auto_inferred / evolution
);

-- 新增表
CREATE TABLE concept_groups (
    concept_name TEXT,
    stock_code TEXT,
    discovered_at DATE
);
```

### 用途
- 分析某只股票时，自动查询同概念/同行业股票的信号 → "行业整体看多/看空"
- 龙头股异动时，快速找到关联股票
- 进化系统用关联图谱做群体分析

### 文件变更
- **NEW** `src/data/stock_graph.py` — StockRelationGraph
- **MOD** `src/data/db_manager.py` — 新增表 + 查询方法
- **MOD** `src/orchestrator/pipeline.py` — 分析前查关联

---

## D3: ReACT 深度分析 (react_agent)

### 设计
```
AnalysisAgent (增强版):
  1. 接收 StockSnapshot + 基础数据
  2. 首轮分析 → 初步结论
  3. IF 发现异常数据:
       → 调用 tool: query_history(code) 查历史表现
       → 调用 tool: compare_peers(code) 查同行业对比
       → 调用 tool: check_sector_momentum(industry) 查板块动量
  4. 综合所有信息 → 最终分析
  5. 输出: summary + sentiment + focus_points + risk_points + reasoning_chain
```

### 工具定义
```python
class AnalysisTools:
    def query_history(code: str, days: int = 30) -> str
    def compare_peers(code: str) -> str
    def check_sector_momentum(industry: str) -> str
    def check_capital_flow(code: str, days: int = 5) -> str
```

### 文件变更
- **NEW** `src/agents/tools.py` — AnalysisTools
- **NEW** `src/agents/react_base.py` — ReactAgent 基类
- **MOD** `src/agents/technical.py` — 继承 ReactAgent
- **MOD** `src/agents/capital.py` — 继承 ReactAgent
- **MOD** `src/agents/fundamental.py` — 继承 ReactAgent

---

## D4: 场景推演 (scenario_sim)

### 设计
```
ScenarioSimulator:
  输入: {
    watchlist: [...],
    scenario: "龙头股600519跌停",
    parameters: {impact_range: "industry", severity: 0.8}
  }
  
  流程:
  1. 从 stock_graph 找到关联股票（同行业/同概念）
  2. 对每只关联股票:
     → LLM 分析: "在 {scenario} 下，{stock} 可能的影响是？"
     → 参考历史类似事件的实际涨跌
  3. 输出影响矩阵:
     - 直接影响: 高/中/低
     - 预估跌幅范围
     - 建议操作
```

### API 端点
```
POST /api/scenario/simulate
Body: { "scenario": "...", "parameters": {...} }
Response: { "impact_matrix": [...], "reasoning": "..." }
```

### 文件变更
- **NEW** `src/analysis/scenario_sim.py` — ScenarioSimulator
- **NEW** `src/api/scenario_routes.py` — 场景推演 API
- **MOD** `src/main.py` — CLI: `python -m src.main scenario`

---

## D5: Agent 动态进化 (agent_evolution)

### 扩展进化系统
现有进化系统（EvolutionEngine）只优化融合权重 → 扩展到 Agent 层面：

```python
class AgentEvolutionTracker:
    """追踪每个 Agent 维度的历史准确率"""
    
    def track_agent_accuracy(self, agent_name: str, predictions, actuals):
        """计算 technical/capital/fundamental 各维度准确率"""
    
    def generate_prompt_adjustments(self) -> dict:
        """基于历史表现生成 prompt 调整建议"""
        # 例: technical agent 在震荡市准确率低
        #   → prompt 调整: "请特别关注横盘区间的支撑/压力位"
    
    def adjust_agent_focus(self, agent_name: str, focus: str):
        """动态调整 Agent 的关注重点"""
```

### 文件变更
- **NEW** `src/evolution/agent_tracker.py` — Agent 维度追踪
- **MOD** `src/evolution/engine.py` — 增加 agent 进化阶段
- **MOD** `src/agents/technical.py` — 支持动态 prompt 注入

---

## 前端展示增强

辩论和推演结果需要前端可见体现：

### 个股页新增
- **辩论面板**: 3 Agent Round1 vs Round2 结论对比 + 共识度仪表盘
- **关联股票**: "同概念" 信号联动（同行业 N 只股票平均信号）
- **场景推演入口**: "假设推演" 按钮 → 弹窗输入场景 → 显示影响矩阵

### 看板页新增
- **市场情绪热力图**: 基于共识度（高共识=强信号，低共识=高不确定性）
- **行业共振**: 某行业多只股票同时出现相同信号时高亮

---

## 验收标准

### Functional
- [ ] 辩论轮正确执行：3 Agent 各输出 Round2 修正
- [ ] 共识度正确计算并融入 confidence
- [ ] 股票关系图谱可查询关联
- [ ] ReACT Agent 在异常数据时主动调用工具
- [ ] 场景推演 API 返回合理影响矩阵
- [ ] Agent 进化追踪各维度准确率

### UX
- [ ] 辩论面板在个股页可见
- [ ] 共识度在首页卡片展示
- [ ] 关联股票在详情页展示
- [ ] self_check.py 通过所有检查

### Ops
- [ ] systemd 服务正常重启
- [ ] API 端点 /health 正常
- [ ] 辩论轮增加 LLM 调用次数但总时间 < 2x 当前

---

## 执行顺序

1. **D1 辩论交互** (最高优先级，最大收益) → `src/agents/debate.py`
2. **D2 关系图谱** (基础设) → `src/data/stock_graph.py`
3. **D3 ReACT 分析** (增强分析质量) → `src/agents/react_base.py`
4. **D4 场景推演** (新功能) → `src/analysis/scenario_sim.py`
5. **D5 Agent 进化** (持续优化) → `src/evolution/agent_tracker.py`
