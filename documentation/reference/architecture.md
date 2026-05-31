# 技术架构

> **Version 2.1.0** | Phase C–F | 详图见 [c4-diagrams.md](./c4-diagrams.md)

## v2.1 增量模块（Phase C–F）

| 模块 | 路径 | 说明 |
|------|------|------|
| DeliveryPipeline | `src/delivery/pipeline.py` | Full/Fast 统一交付 |
| WatchlistManager | `src/watchlist/manager.py` | DB 自选 |
| DebateOrchestrator | `src/agents/debate.py` | 2-round 辩论 |
| StockRelationGraph | `src/data/stock_graph.py` | 关联图谱 |
| ScenarioSimulator | `src/analysis/scenario_sim.py` | 场景推演 |
| PostmortemRecorder | `src/evolution/postmortem.py` | 信号复盘 |
| ThesisManager | `src/evolution/thesis.py` | 投资论点 |
| MarketBreadthScorer | `src/analysis/breadth.py` | 市场广度 |
| StaticExporter | `src/export/static_exporter.py` | 静态导出 |

## 1. 模块图

```
┌──────────────┐     ┌──────────────────┐     ┌──────────────┐
│   CLI / API  │────▶│  Orchestrator    │────▶│   Notify     │
└──────────────┘     │  (pipeline.py)   │     │ (wcom/email) │
                     └────────┬─────────┘     └──────────────┘
                              │
           ┌──────────────────┼──────────────────┬───────────────┐
           ▼                  ▼                  ▼               ▼
     ┌───────────┐     ┌───────────┐     ┌───────────┐   ┌───────────┐
     │ Data      │     │ Agents    │     │ Report    │   │ Site      │
     │ Fetcher   │     │ (4个)     │     │ Generator │   │ Generator │
     └─────┬─────┘     └───────────┘     └───────────┘   └─────┬─────┘
           │                                                   │
     ┌─────┴─────────────┐                              Publish │
     │ Providers         │                              to GitHub
     ├───────────────────┤
     │ AkShare   (K线)   │     ┌──────────────────┐
     │ Eastmoney (估值/  │     │ Signal Engine    │
     │  资金/龙虎榜/概览) │────▶│ Hard + Soft +    │
     │ Sina      (K线备) │     │ Gate + DragonTig │
     │ Tencent   (K线/   │     │ er + Announcement│
     │  估值备/报价)     │     │  5层加权融合      │
     └───────────────────┘     └──────────────────┘
```

## 2. 目录结构

```
stock-copilot/
├── config/
│   ├── settings.yaml          # 多 provider LLM + 调度 + 推送 + 数据 + 站点配置
│   └── watchlist.yaml         # 自选股列表
├── src/
│   ├── __init__.py
│   ├── main.py                # CLI 入口 (analyze / serve / schedule) + uvicorn 启动
│   ├── config.py              # pydantic-settings 加载 YAML + .env
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── config.py          # LLMProvider + LLMConfig (multi-provider)
│   │   └── client.py          # ProviderClient + LLMClient(fallback/concurrent) + get_llm_client()
│   ├── data/
│   │   ├── __init__.py
│   │   ├── fetcher.py         # DataFetcher 类 + fetch_all()，多源降级链
│   │   ├── fetcher_utils.py   # calc_ma() 等工具函数
│   │   ├── models.py          # Pydantic 模型定义
│   │   ├── calendar.py        # 交易日判断 (AkShare 日历 + 工作日兜底)
│   │   └── providers/
│   │       ├── __init__.py
│   │       ├── eastmoney.py   # push2 估值/资金流/龙虎榜/市场概览
│   │       ├── sina.py        # K 线数据
│   │       └── tencent.py     # 行情 + K 线备选
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── base.py            # BaseAgent: call_llm, _make_result
│   │   ├── technical.py       # TechnicalAgent (近20条日线)
│   │   ├── fundamental.py     # FundamentalAgent (公告)
│   │   ├── capital.py         # CapitalAgent (资金流)
│   │   └── announcement.py    # AnnouncementAgent (关键词提取)
│   ├── orchestrator/
│   │   ├── __init__.py
│   │   └── pipeline.py        # run_analysis() — 采集→硬信号→4 Agent→5层融合→报告→持久化→通知
│   ├── reports/
│   │   ├── __init__.py
│   │   └── generator.py       # generate_report() → Markdown + latest.json
│   ├── site/
│   │   ├── __init__.py
│   │   └── generator.py       # generate_site() → HTML (Jinja2) + _sync_to_docs()
│   ├── notify/
│   │   ├── __init__.py
│   │   ├── base.py            # BaseNotifier(ABC) + get_notifier()
│   │   ├── wecom.py           # WeComNotifier
│   │   └── email.py           # EmailNotifier
│   ├── scheduler/
│   │   ├── __init__.py
│   │   └── jobs.py            # run_pre_market() / run_post_market() / start_scheduler()
│   ├── api/
│   │   ├── __init__.py
│   │   └── routes.py          # FastAPI app: /health, /analyze, /reports/*, /site/latest.json
│   └── publish/
│       ├── __init__.py
│       └── github.py          # publish_to_github() — git commit docs/ + push
├── tests/
│   ├── test_fetcher.py
│   ├── test_pipeline.py
│   ├── test_report_generator.py
│   ├── test_signals.py        # 硬信号 + 信号融合 + SignalDB
│   ├── agents/
│   │   └── test_announcement.py
│   └── data/
│       └── test_dragon_tiger.py
├── scripts/
│   └── self_check.py          # 系统自检 (10阶段 46项)
├── output/reports/            # 生成的 Markdown 报告（gitignore）
├── site/                      # 静态站点输出（gitignore）
│   ├── index.html
│   ├── assets/theme.css
│   ├── archive/               # 历史 HTML 报告
│   └── data/latest.json       # 结构化数据
├── data/stock.db              # SQLite（预留，gitignore）
├── docs/                      # GitHub Pages 源目录（site/ 同步至此）
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

## 3. 依赖

```
fastapi>=0.110
uvicorn>=0.27
pydantic>=2.0
pydantic-settings>=2.0
akshare>=1.14
openai>=1.0
apscheduler>=3.10
pyyaml>=6.0
httpx>=0.27
jinja2>=3.1
pytest>=8.0
pytest-asyncio>=0.23
python-dotenv>=1.0
pandas>=2.0
```

## 4. 模块职责

| 模块 | 职责 | 关键类/函数 |
|------|------|-------------|
| config | 加载 YAML + .env，Settings 单例 | Settings, get_settings() |
| llm.config | 多 provider LLM 配置 | LLMProvider, LLMConfig |
| llm.client | 统一 LLM 调用，fallback/concurrent | ProviderClient, LLMClient, get_llm_client() |
| data.fetcher | 多源采集 + 降级链 → StockSnapshot | DataFetcher, fetch_all() |
| data.providers | 各数据源封装 | eastmoney, sina, tencent, dragon_tiger |
| data.calendar | 交易日判断 | is_trading_day() |
| data.models | Pydantic 数据模型 | StockSnapshot, AgentResult, Report, etc. |
| data.hard_signals | 确定性硬信号计算 | compute_hard_signals(), HardSignals |
| data.signal_fusion | 5层信号融合 | fuse_signals(), FusedSignal |
| data.db_manager | SQLite 持久化 | SignalDB, SignalRecord |
| agents | LLM 分析 → AgentResult | TechnicalAgent, FundamentalAgent, CapitalAgent, AnnouncementAgent |
| orchestrator.pipeline | 编排：采集→硬信号→4 Agent→5层融合→报告→持久化→通知 | run_analysis() |
| reports.generator | AgentResult → Markdown + latest.json | generate_report() |
| site.generator | Report → Jinja2 HTML + sync to docs/ | generate_site() |
| notify | 发送报告 | WeComNotifier, EmailNotifier, get_notifier() |
| scheduler | Cron 触发 pipeline | run_pre_market(), run_post_market(), start_scheduler() |
| api | HTTP 接口 | FastAPI app (/health, /analyze, /reports/*, /site/latest.json) |
| publish | git 提交 docs/ 到 GitHub | publish_to_github() |

## 5. 编排流程

```python
async def run_analysis(report_type: ReportType, symbols: list[str] | None = None) -> Report:
    # 1. 检查交易日
    if not is_trading_day():
        raise RuntimeError("非交易日，跳过分析")

    # 2. 加载自选股
    watchlist = _load_watchlist(symbols)

    # 3. 并行采集（多源降级）
    snapshots, failed_symbols = await fetch_all(watchlist)

    # 4. 市场概览
    market = await fetcher.fetch_market_overview()  # 可选

    # 5. 运行 Agent（每只股票顺序，股票间并行）
    analyses = await _run_agents(snapshots)

    # 6. 生成报告（Markdown + latest.json）
    report = generate_report(analyses, report_type, market, failed_symbols)

    # 7. 通知
    notifier = get_notifier()
    if notifier:
        await notifier.send(report)

    return report

# CLI 额外步骤（main.py cmd_analyze）
# 8. 生成静态网页
generate_site(report)

# 9. 发布到 GitHub（--publish 标志）
publish_to_github(report)
```

## 6. 错误策略

| 层级 | 策略 |
|------|------|
| fetcher（K线） | AkShare(重试1次) → Sina → Tencent 降级链，单股失败不阻塞其他股票 |
| fetcher（估值） | Eastmoney push2 → Tencent 降级，502 降级为 warning |
| fetcher（资金流） | Eastmoney push2 → AkShare 降级 |
| fetcher（公告） | AkShare 快速失败 → 空列表 |
| fetcher（新闻） | 暂时禁用，返回空列表 |
| fetcher（龙虎榜） | Eastmoney datacenter，失败记录到 fetch_errors |
| agent（LLM） | max_retries 次重试 → status=failed，summary 说明失败原因 |
| agent（无 provider） | status=unavailable，summary = "LLM API 未配置" |
| notify | 失败 → 日志告警，报告仍落盘 |
| site | 失败 → 日志告警，不影响 Markdown 报告 |
| publish | 失败 → 日志告警，不影响本地文件 |
| 非交易日 | scheduler 跳过，CLI 抛出 RuntimeError |
| ST/停牌股 | 信号融合直接过滤，返回 hold，不进入分析 |

## 7. LLM 多 Provider 设计

```
LLMConfig
├── mode: "fallback" | "concurrent"
├── max_retries: 2
└── providers: [
      LLMProvider(name="deepseek", model="deepseek-v4-flash", priority=1),
      LLMProvider(name="dashscope", model="qwen3.6-plus",    priority=2),
   ]

LLMClient.chat_json()
├── fallback 模式: 按 priority 顺序尝试，第一个成功即返回
└── concurrent 模式: 同时调用所有 provider，取第一个成功结果（优先高优先级）

SYSTEM_PROMPT 要求:
- 仅基于用户提供的 JSON 数据分析
- 输出合法 JSON 格式
- 不做买卖建议
- summary 100-200 字
```
