# Stock Copilot 当前系统状态（SSOT）

> **版本 v2.0.0 (Phase D: MiroFish 增强)** | 更新 2026-05-29  
> 代码仓库: `ttmens/stock-copilot` | 线上: https://ttmens.github.io/stock-copilot/

## Phase D 要点（MiroFish 群体智能增强）

- **D1 多 Agent 辩论交互**: 3 Agent Round1 → 互相看到结论 → Round2 修正/确认 → 共识度融入 confidence
  - `src/agents/debate.py` — DebateOrchestrator（共识度算法、分歧检测、情感偏移追踪）
  - 共识度 1.0 → confidence +0.15；0.4 → confidence -0.03
- **D2 股票关系图谱**: SQLite 轻量图谱（同行业/同概念/供应链关系 + 时效窗口）
  - `src/data/stock_graph.py` — StockRelationGraph（关联查询、概念分组、自动推断）
- **D3 ReACT 深度分析**: Agent 主动查询历史信号、资金流趋势（不再被动接收数据）
  - `src/agents/tools.py` — AnalysisTools + build_react_context
  - TechnicalAgent 已注入 ReACT 上下文
- **D4 场景推演模拟**: "如果龙头跌停/板块轮动 → 持仓影响矩阵"
  - `src/analysis/scenario_sim.py` — ScenarioSimulator（LLM 逐股影响分析）
- **D5 Agent 动态进化**: 追踪各 Agent 维度准确率，动态调整 prompt 侧重点
  - `src/evolution/agent_tracker.py` — AgentEvolutionTracker（维度统计、prompt 调整建议）
  - 已集成到 EvolutionEngine OODA 循环

## Phase C 要点

- **静动分离**: Full → `latest.json` + GitHub Pages；动态 → FastAPI
- **双 Pipeline**: Full（LLM+发布）/ Fast（硬信号+intraday）
- **自选**: DB + `/api/watchlist`；默认模板，无硬上限
- **Evolution**: 默认不自动改自选/权重
- **站点**: `skip_stock_html` → `app/stock.html?code=`
- **运维**: `python -m src.main run`（6 jobs + API）

---

## 1. 产品定位

| 维度 | 定义 |
|------|------|
| 产品名 | Stock Copilot（智策） |
| 一句话 | 基于 AI 的 A 股个人投研助手：看全、看懂、及时提醒 |
| 目标用户 | 有个人炒股经验、希望提升决策效率的投资者（Phase 1 自用） |
| 核心价值 | 聚合行情、公告、资金、估值等分散信息 → 结构化决策参考 + 静态网页发布 |
| 不做 | 不承诺收益、不自动下单、不对外投顾 |

---

## 2. 系统架构总览

```
用户层: 静态 HTML (GitHub Pages) / CLI / FastAPI (/health, /analyze, /reports/*, /api/scenario/*)
        ↓
编排层: run_analysis() → 采集 → 硬信号 → 4 Agent → 辩论Round2 → 5层融合+共识度 → 报告 → 持久化 → 通知 → 站点
        ↓
决策层:
  ├─ 硬信号引擎: HardSignals (动量/均线/量能/估值/资金流 → 综合评分)
  ├─ 软信号引擎: 4 LLM Agent + ReACT工具 (技术面/基本面/资金/公告 → 情感评分)
  ├─ 辩论引擎: DebateOrchestrator (Round1→互相查看→Round2修正→共识度)
  ├─ 门控引擎: 规则确认 (量能确认/涨跌停过滤/Agent一致性)
  ├─ 图谱引擎: StockRelationGraph (同行业/概念关联查询)
  └─ 融合引擎: FusedSignal (5层加权 + 辩论共识度bonus)
        ↓
数据层:
  ├─ 采集链: AkShare → Sina → Tencent (K线) / Eastmoney → Tencent (估值) / Eastmoney → AkShare (资金)
  ├─ 扩展源: 东财 datacenter (龙虎榜) / AkShare (公告)
  └─ 存储: SQLite (SignalDB 信号历史) + JSON (latest.json)
        ↓
LLM 层: 统一 LLMClient (fallback/concurrent 模式)
  ├─ Primary: DeepSeek (deepseek-v4-flash, api.deepseek.com)
  └─ Fallback: 阿里百炼 DashScope (qwen3.6-plus, coding.dashscope.aliyuncs.com)
```

---

## 3. 数据流程（完整版）

```
watchlist.yaml
  → DataFetcher.fetch_stock() (多源降级链，单股并行)
     ├─ K线: AkShare (重试1次) → Sina → Tencent
     ├─ 估值: Eastmoney push2 → Tencent
     ├─ 资金流: Eastmoney push2 → AkShare
     ├─ 公告: AkShare → 空列表（近 N 日过滤，config `announcement_days`）
     ├─ 新闻: AkShare stock_news_em → `StockSnapshot.news` → latest.json
     └─ 龙虎榜: Eastmoney datacenter
  → StockSnapshot (统一 Pydantic 模型)
  → compute_hard_signals() (确定性量化因子)
  → 4 LLM Agent 并行 (Technical / Fundamental / Capital / Announcement)
     └─ LLMClient (fallback 模式: DeepSeek → DashScope)
  → fuse_signals() (5层加权: 硬40% + 软25% + 门控15% + 龙虎10% + 公告10%，可 evolution 覆盖)
  → generate_report() (Markdown + StockAnalysis 含 fusion 字段)
  → generate_site() (Jinja2 HTML — **不重算 fusion**)
  → _sync_to_docs() (同步到 docs/ 供 GitHub Pages)
  → SignalDB.save() (持久化到 SQLite)
  → Notifier.send() (企微 Webhook / SMTP)
  → publish_to_github() (可选 --publish 标志)
```

---

## 4. 核心模块清单

### 4.1 数据采集层 (`src/data/`)

| 文件 | 职责 | 关键函数 |
|------|------|----------|
| `fetcher.py` | 多源采集编排 + 降级链 | `DataFetcher.fetch_stock()`, `fetch_all()` |
| `providers/eastmoney.py` | 东财 push2 直连 (估值/资金流/龙虎榜/市场概览) | `get_stock_info()`, `get_capital_flow()`, `get_dragon_tiger()` |
| `providers/sina.py` | 新浪 K 线备选 | `get_kline_sina()` |
| `providers/tencent.py` | 腾讯行情 + K 线备选 | `get_stock_quote()`, `get_kline_tencent()` |
| `providers/dragon_tiger.py` | 龙虎榜专用 Provider | `DragonTigerProvider.get_stock_dragon_tiger()` |
| `hard_signals.py` | 确定性硬信号计算 | `compute_hard_signals()`, `HardSignals` dataclass |
| `signal_fusion.py` | 5层信号融合引擎 | `fuse_signals()`, `FusedSignal` dataclass |
| `db_manager.py` | SQLite 持久化 | `SignalDB.upsert_stock()`, `save()`, `history()` |
| `calendar.py` | 交易日判断 | `is_trading_day()` |
| `models.py` | 全部 Pydantic 数据模型 | `StockSnapshot`, `AgentResult`, `StockAnalysis`, `Report` 等 |

### 4.2 Agent 层 (`src/agents/`)

| Agent | 职责 | 输入 | 输出 |
|-------|------|------|------|
| `TechnicalAgent` | 技术面分析 (K线/均线/量能/支撑压力位) | 近20条日线 + MA5/10/20 | trend, key_signals, summary, confidence |
| `FundamentalAgent` | 基本面分析 (公告/新闻) | 近7日公告列表 | 利好/利空判断, summary, risk_points |
| `CapitalAgent` | 资金面分析 (主力/北向) | 资金流数据 | 资金态度, summary, risk_points |
| `AnnouncementAgent` | 公告关键词提取 | 公告标题列表 | key_events[], sentiment, risk_flags[] |

所有 Agent 继承 `BaseAgent`，共享 `call_llm()` 方法，输出统一为 `AgentResult`。

### 4.3 编排层 (`src/orchestrator/`)

| 文件 | 职责 |
|------|------|
| `pipeline.py` | 全流程编排: `run_analysis()` — 交易日检查 → 加载自选 → 并行采集 → 硬信号 → 4 Agent → 5层融合 → 报告 → SQLite 持久化 → 通知 |

### 4.4 报告 & 站点层 (`src/reports/`, `src/site/`)

| 文件 | 职责 |
|------|------|
| `reports/generator.py` | AgentResult → Markdown 报告 + latest.json |
| `site/generator.py` (711行) | Jinja2 模板渲染 → 深色 Fintech 主题 HTML → 自动同步到 docs/ |

### 4.5 基础设施

| 模块 | 职责 |
|------|------|
| `llm/client.py` | 统一 LLM 调用: `LLMClient(fallback/concurrent)`, `get_llm_client()` |
| `llm/config.py` | 多 provider 配置: `LLMProvider`, `LLMConfig` |
| `config.py` | pydantic-settings 加载 YAML + .env, `Settings` 单例 |
| `main.py` | CLI 入口: `analyze`, `serve`, `schedule` |
| `api/routes.py` | FastAPI: `/health`, `/analyze`, `/reports/*`, `/site/latest.json` |
| `scheduler/jobs.py` | APScheduler: 盘前 08:30 / 盘后 16:00 |
| `notify/` | 企微 Webhook + SMTP 邮件通知 |
| `publish/github.py` | git commit docs/ → push 到 GitHub Pages |
| `scripts/self_check.py` | 系统自检: 10阶段 46项检查 |

---

## 5. 信号融合引擎（核心创新）

### 5.1 5层架构

```
最终评分 = 硬信号(40%) + 软信号(25%) + 门控(15%) + 龙虎榜(10%) + 公告(10%)
```

**动态权重**: 根据数据可用性自动调整。当某层数据不可用时，权重重新分配到其他层。

### 5.2 各层详解

| 层级 | 名称 | 来源 | 评分范围 | 说明 |
|------|------|------|----------|------|
| Layer 1 | 硬信号 (Hard) | 确定性量化因子 | -1.0 ~ +1.0 | 动量30% + 均线25% + 量能15% + 估值15% + 资金流15% |
| Layer 2 | 软信号 (Soft) | 3 LLM Agent 加权平均 | -1.0 ~ +1.0 | 技术面40% + 资金35% + 基本面25% |
| Layer 3 | 门控 (Gate) | 规则引擎 | 0.0 ~ 1.0 | 量能确认(±0.2) + 涨跌停过滤(-0.3) + Agent一致性(±0.2) |
| Layer 4 | 龙虎榜 | 东财龙虎榜净买入额 | -1.0 ~ +1.0 | 1亿 = ±1.0 |
| Layer 5 | 公告 | LLM 提取关键事件情感 | -1.0 ~ +1.0 | bullish=+1.0, bearish=-1.0, neutral=0.0 |

### 5.3 置信度计算

```
confidence = 层间一致性(40%) + 信号强度(40%) + 数据完整度(20%)
```

- 硬软同向 → 0.8，反向 → 0.3，单层 → 0.6
- 信号绝对值越大，置信度越高
- 数据层越多，置信度越高

### 5.4 信号分类

| 分数区间 | 信号 | 图标 |
|----------|------|------|
| ≥ +0.6 | strong_buy | 🟢 强烈看多 |
| +0.2 ~ +0.6 | buy | 🟢 看多 |
| -0.2 ~ +0.2 | hold | ⚪ 观望 |
| -0.6 ~ -0.2 | sell | 🔴 看空 |
| < -0.6 | strong_sell | 🔴 强烈看空 |

### 5.5 ST/停牌过滤

ST 股和停牌股直接过滤，返回 `⚪ 过滤（ST/停牌）`，不进入融合流程。

---

## 6. 硬信号因子

```python
HardSignals:
  momentum_20d: 20日涨跌幅 (原始值%)
  momentum_5d: 5日涨跌幅 (原始值%)
  ma_alignment: bullish | bearish | neutral
  volume_ratio: 当日量/20日均量
  pe_percentile: PE 历史百分位 (估算)
  main_net_inflow: 主力净流入 (元)

  → momentum_score: 5日×0.6 + 20日×0.4, /5% 归一化
  → ma_score: 4档 (1.0/0.5/-0.5/-1.0)
  → volume_score: (量比-1.0)/0.5 归一化
  → valuation_score: (30-PE)/15 归一化
  → capital_score: 净流入/1亿 归一化
  → composite_score: 加权平均 (仅非零因子参与)
```

---

## 7. LLM 多 Provider 设计

```
LLMConfig
├── mode: "fallback" (默认) | "concurrent"
├── max_retries: 2
└── providers:
      ├── deepseek (priority=1): deepseek-v4-flash, api.deepseek.com
      └── dashscope (priority=2): qwen3.6-plus, coding.dashscope.aliyuncs.com

LLMClient.chat_json():
├── fallback: 按 priority 顺序尝试，第一个成功即返回
└── concurrent: 同时调用，取第一个成功 (优先高优先级)

⚠️ DeepSeek/DashScope 要求: prompt 中必须包含 "json" 字样才能使用 json_object 模式
```

---

## 8. 数据源降级链

| 数据类型 | 主选 | 备选1 | 备选2 | 状态 |
|----------|------|-------|-------|------|
| K线 | AkShare (重试1次) | Sina | Tencent | ✅ 全通 |
| 估值 | Eastmoney push2 | Tencent | - | ⚠️ 东财偶发502 |
| 资金流 | Eastmoney push2 | AkShare | - | ⚠️ 东财偶发502 |
| 公告 | AkShare (快速失败) | - | - | ✅ 可用 |
| 新闻 | 暂时禁用 | - | - | ⏸️ |
| 龙虎榜 | Eastmoney datacenter | - | - | ✅ 可用 |
| 市场概览 | Eastmoney push2 | AkShare 指数 | - | ✅ 可用 |

**错误隔离**: 单股失败不阻塞其他股票，单数据源失败不阻塞整份报告。

---

## 9. UI 设计（深色 Fintech 主题）

### 9.1 页面结构

```
┌─────────────────────────────────────────────────┐
│ Header: Stock Copilot | 日期 | 盘前/盘后 | 市场指数 │
├─────────────────────────────────────────────────┤
│ 市场温度: 看涨/中性/看跌 股票数分布                  │
├─────────────────────────────────────────────────┤
│ 股票卡片 (按最终评分排序):                          │
│ ┌─────────────────────────────────────────────┐  │
│ │ 600519 贵州茅台    🟢 看多  评分: +0.342      │  │
│ │ ████████████░░░░░░░░░░ 置信度: 72%          │  │
│ │ ┌─────────┬─────────┬─────────┬──────────┐   │  │
│ │ │硬 40%   │软 25%   │门控 15% │龙虎 10%  │   │  │
│ │ │+0.420   │+0.350   │+0.600   │+0.100    │   │  │
│ │ └─────────┴─────────┴─────────┴──────────┘   │  │
│ │ 5日+2.1% | 均线多头 | 量比1.3 | PE 19.5      │  │
│ │ ┌──────┬──────┬──────┬──────┐               │  │
│ │ │技术面│基本面│ 资金 │ 公告 │               │  │
│ │ │✅ xxx│⏸️ 无 │✅ xxx│✅ xxx│               │  │
│ │ └──────┴──────┴──────┴──────┘               │  │
│ │ 🐉 龙虎榜: 涨幅偏离 +20%  净买入 +1.2亿       │  │
│ │ 📢 公告: Q1净利润+15% 🟢 85%                 │  │
│ │ ⚠️ 风险点: ...                               │  │
│ └─────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────┤
│ Footer: ⚠️ 免责声明 + 数据更新时间                │
└─────────────────────────────────────────────────┘
```

### 9.2 视觉规范

| 元素 | 规范 |
|------|------|
| 主题 | 深色背景 (#0F172A)，白色文字，Fintech 风格 |
| 看多色 | #22C55E (绿) |
| 看空色 | #EF4444 (红) |
| 观望色 | #94A3B8 (灰) |
| 龙虎榜 | 紫色左边框 (#8B5CF6) |
| 公告 | 黄色左边框 (#F59E0B) |
| 布局 | 响应式，移动端单列，桌面端多列 |
| 字体 | system-ui, 等宽字体用于数值 |

---

## 10. 目录结构（实际代码）

```
stock-copilot/
├── config/
│   ├── settings.yaml          # 多 provider LLM + 调度 + 通知 + 数据配置
│   └── watchlist.yaml         # 自选股列表
├── src/
│   ├── main.py                # CLI: analyze / serve / schedule
│   ├── config.py              # pydantic-settings 加载 YAML + .env
│   ├── llm/
│   │   ├── config.py          # LLMProvider + LLMConfig
│   │   └── client.py          # ProviderClient + LLMClient(fallback/concurrent)
│   ├── data/
│   │   ├── fetcher.py         # DataFetcher + fetch_all()
│   │   ├── fetcher_utils.py   # calc_ma()
│   │   ├── models.py          # 全部 Pydantic 模型
│   │   ├── calendar.py        # is_trading_day()
│   │   ├── hard_signals.py    # 硬信号计算
│   │   ├── signal_fusion.py   # 5层融合引擎
│   │   ├── db_manager.py      # SQLite 持久化
│   │   └── providers/
│   │       ├── eastmoney.py   # push2 估值/资金/龙虎榜/概览
│   │       ├── sina.py        # K 线备选
│   │       ├── tencent.py     # 行情 + K 线备选
│   │       └── dragon_tiger.py # 龙虎榜专用
│   ├── agents/
│   │   ├── base.py            # BaseAgent: call_llm, _make_result
│   │   ├── technical.py       # 技术面 (近20条日线)
│   │   ├── fundamental.py     # 基本面 (公告)
│   │   ├── capital.py         # 资金面 (主力/北向)
│   │   └── announcement.py    # 公告关键词提取 (LLM)
│   ├── orchestrator/
│   │   └── pipeline.py        # run_analysis() 全流程编排
│   ├── reports/
│   │   └── generator.py       # Markdown 报告 + latest.json
│   ├── site/
│   │   └── generator.py       # Jinja2 HTML + _sync_to_docs()
│   ├── notify/
│   │   ├── base.py            # BaseNotifier(ABC)
│   │   ├── wecom.py           # 企微 Webhook
│   │   └── email.py           # SMTP
│   ├── scheduler/
│   │   └── jobs.py            # 盘前/盘后调度
│   ├── api/
│   │   └── routes.py          # FastAPI 接口
│   └── publish/
│       └── github.py          # git commit + push
├── tests/                     # 36 个单元测试
│   ├── test_fetcher.py
│   ├── test_pipeline.py
│   ├── test_report_generator.py
│   ├── test_signals.py        # 硬信号 + 融合 + SignalDB
│   ├── agents/test_announcement.py
│   └── data/test_dragon_tiger.py
├── scripts/
│   └── self_check.py          # 系统自检 (10阶段 46项)
├── docs/                      # GitHub Pages 源
│   ├── index.html
│   ├── assets/theme.css
│   ├── archive/               # 历史报告
│   └── data/latest.json
├── site/                      # 站点输出 (gitignore)
├── data/stock.db              # SQLite (gitignore)
├── output/reports/            # Markdown 报告 (gitignore)
├── requirements.txt
├── .env.example
└── README.md
```

---

## 11. 质量保障

### 11.1 测试覆盖

| 类别 | 数量 | 覆盖 |
|------|------|------|
| 单元测试 | 36 | 全部通过 |
| 硬信号 | 6 | 多头/空头/无数据/放量/估值高低 |
| 信号融合 | 6 | 强一致/冲突/ST过滤/无数据/仅硬信号 |
| SignalDB | 5 | upsert/save/history/batch/file模式 |
| Agent | 2 | 公告 (无数据 + 有数据) |
| 龙虎榜 | 4 | init/真实股/无数据/评分计算 |
| Fetcher | 3 | MA计算/快照 |
| Pipeline | 1 | 全流程调用验证 |
| 报告 | 3 | 看涨/看跌/混合/全不可用 |

### 11.2 系统自检

`scripts/self_check.py` — 10 阶段 46 项全链路验证：

| 阶段 | 检查项 | 说明 |
|------|--------|------|
| 1 | 配置验证 | LLM mode, provider 数量 |
| 2 | 模块导入 | 所有 src.* 模块可导入 |
| 3 | 依赖检查 | requirements.txt 匹配 |
| 4 | Git 安全 | .env 未追踪, Key 未泄露 |
| 5 | 报告生成 | 免责声明, Markdown 完整, JSON 可解析 |
| 6 | 站点生成 | HTML 非空, CSS 存在, 同步到 docs/ |
| 7 | API 服务 | FastAPI 可启动, /health 可达 |
| 8 | 测试套件 | pytest 全部通过 |
| 9 | 数据源连通性 | K线/估值/资金流实际请求 |
| 10 | LLM Provider | 所有 provider 健康检查 |

---

## 12. 非功能指标

| 指标 | MVP 目标 | 当前状态 |
|------|----------|----------|
| 3只自选股分析耗时 | < 5 分钟 | ~2-3 分钟 (含3个LLM调用) |
| 数据源部分失败 | 报告仍可生成 | ✅ 降级链 + 单股隔离 |
| LLM 降级 | 自动切换备选 | ✅ fallback 模式 |
| 调度 | 盘前 08:30 / 盘后 16:00 | ✅ APScheduler |
| 非交易日跳过 | 自动跳过 | ✅ AkShare 日历 + 工作日兜底 |

---

## 13. 合规声明

每份报告必须包含固定免责声明：

> ⚠️ 本报告仅供个人研究参考，基于公开数据和 AI 模型生成，不构成任何投资建议。股市有风险，投资需谨慎。AI 分析可能存在错误或遗漏，请独立判断。

LLM 输出约束：
- 仅基于提供的数据，不得编造
- 不使用「必涨」「必买」等确定性词汇
- 数据缺失时标注 `unavailable`

---

## 14. 已知限制与 TODO

| 类别 | 状态 | 说明 |
|------|------|------|
| 新闻获取 | ⏸️ 禁用 | 东财新闻 API 在某些服务器被屏蔽 |
| 龙虎榜参与者详情 | ⏸️ 未解析 | 仅获取净买入额，未解析营业部明细 |
| 估值 PE 百分位 | 📊 估算 | 基于 PE 5-60 的简化映射，非真实历史百分位 |
| 回测 | ❌ 未实现 | Phase 3 规划 |
| 模拟盘 | ❌ 未实现 | Phase 3 规划 |
| 企微推送 | ⚙️ 配置就绪 | 需要 webhook URL 才能启用 |
| 邮件推送 | ⚙️ 配置就绪 | 需要 SMTP 配置才能启用 |

---

## 15. 演进路线

| 阶段 | 状态 | 核心能力 |
|------|------|----------|
| **MVP** | ✅ 完成 | 自选股 + 4 Agent + 5层信号融合 + Markdown 报告 + 静态网页 + GitHub Pages |
| **Phase B** | ✅ 完成 | 龙虎榜 + 公告关键词提取 + LLM Prompt 重构 + UI 升级 + 自检脚本 + SQLite 持久化 |
| Phase 2 | 📋 规划 | Web UI 交互, 多空辩论, Tushare 本地库, 龙虎榜深度分析 |
| Phase 3 | 📋 规划 | 回测, 模拟盘, miniQMT |

---

## 16. 关键文件索引

| 文件 | 用途 |
|------|------|
| `config/settings.yaml` | 全局配置 (LLM/调度/通知/数据/站点) |
| `config/watchlist.yaml` | 自选股列表 |
| `src/data/models.py` | 全部 Pydantic 数据模型 |
| `src/data/signal_fusion.py` | 5层信号融合引擎 |
| `src/data/hard_signals.py` | 硬信号计算 |
| `src/orchestrator/pipeline.py` | 全流程编排 |
| `src/site/generator.py` | 站点生成 (Jinja2 模板) |
| `src/llm/client.py` | 统一 LLM 客户端 |
| `scripts/self_check.py` | 系统自检 |
| `docs/stock-copilot/README.md` | 设计文档索引 |
| `docs/stock-copilot/09-HERMES-AUTONOMOUS-BUILD.md` | Hermes 自主构建指令 |
