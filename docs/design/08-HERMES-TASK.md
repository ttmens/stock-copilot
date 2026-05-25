---
name: stock-copilot-implementation
version: 1.0.0
updated: 2026-05-24
priority: reference
---

# Stock Copilot 实现状态文档

> 本文档记录系统全部实现状态。Phase 0-9 已全部完成。

## 0. 架构概览

```
采集 A 股数据 → AI 多 Provider 分析 → Markdown 报告 → 静态站点 → GitHub Pages
                                    ↓
                              企微/邮件通知
                                    ↓
                            APScheduler 定时调度
```

## 实现状态总览

| Phase | 模块 | 状态 | 文件 |
|-------|------|------|------|
| 0 | 项目脚手架 | ✅ 完成 | `config/`, `src/config.py`, `src/main.py` |
| 1 | 数据采集层 | ✅ 完成 | `src/data/fetcher.py`, `src/data/providers/` |
| 2 | Agent 层 | ✅ 完成 | `src/agents/`, `src/llm/` |
| 3 | 编排 & 报告 | ✅ 完成 | `src/orchestrator/`, `src/reports/` |
| 4 | 通知 & 调度 | ✅ 完成 | `src/notify/`, `src/scheduler/` |
| 5 | API 服务 | ✅ 完成 | `src/api/routes.py` |
| 6 | 静态站点 | ✅ 完成 | `src/site/generator.py` |
| 7 | GitHub Pages | ✅ 完成 | `src/publish/github.py` |
| 8 | 运维自检 | ✅ 完成 | `scripts/self_check.py` |
| 9 | Cron 运维 | ⏳ 就绪 | 代码就绪，需配置 Hermes Cron |

## Phase 0: 项目脚手架 ✅

**完成文件**:
- `config/settings.yaml` — 多 Provider LLM 配置 + 调度/通知/数据/站点配置
- `src/config.py` — Settings(BaseSettings) + YAML 加载 + @lru_cache 单例
- `src/data/models.py` — 19 个 Pydantic 模型
- `src/main.py` — CLI 入口 (`analyze`, `serve`, `schedule`)

**配置结构**:
```yaml
llm:
  mode: "fallback"              # fallback | concurrent
  providers:                    # 多 Provider
    - name: "deepseek"
      model: "deepseek-v4-flash"
      priority: 1
    - name: "dashscope"
      model: "qwen3.6-plus"
      priority: 2
schedule:
  pre_market: "08:30"
  post_market: "16:00"
data:
  bar_count: 60
  retry: 1
report:
  output_dir: "output/reports"
site:
  output_dir: "site"
  archive_dir: "site/archive"
  data_dir: "site/data"
```

## Phase 1: 数据采集层 ✅

**核心**: `DataFetcher` 类 + 多源降级链

| 数据类型 | 主源 | 备选 | Provider 文件 |
|---------|------|------|-------------|
| K 线 OHLCV | AkShare | Sina → Tencent | `providers/sina.py`, `providers/tencent.py` |
| PE/PB/市值 | Eastmoney push2 | Tencent | `providers/eastmoney.py` |
| 资金流 | Eastmoney | AkShare | `providers/eastmoney.py` |
| 龙虎榜 | Eastmoney datacenter | - | `providers/eastmoney.py` |
| 公告 | AkShare | - | `fetcher.py` |
| 市场概览 | Eastmoney push2 | - | `providers/eastmoney.py` |

**降级策略**: 单源失败不抛异常，记入 `fetch_errors`，Pipeline 自动跳过。

## Phase 2: Agent 层 ✅

**LLM 多 Provider 架构** (`src/llm/`):

| 组件 | 文件 | 说明 |
|------|------|------|
| LLMProvider | `src/llm/config.py` | 单 Provider 配置（name, base_url, model, priority） |
| LLMConfig | `src/llm/config.py` | 多 Provider 集合 + mode + max_retries |
| ProviderClient | `src/llm/client.py` | 单 Provider 客户端（AsyncOpenAI 封装） |
| LLMClient | `src/llm/client.py` | 统一客户端（fallback/concurrent 模式） |

**分析 Agent** (`src/agents/`):

| Agent | 文件 | 输入 | 输出 |
|-------|------|------|------|
| TechnicalAgent | `technical.py` | K 线 20 条 + 均线 | 趋势/量价/支撑压力 |
| FundamentalAgent | `fundamental.py` | 公告列表 | 利好/利空/业绩 |
| CapitalAgent | `capital.py` | 资金流 | 主力/北向态度 |

**SYSTEM_PROMPT**（所有 Agent 共用）:
```
你是 A 股投研分析助手，仅基于用户提供的数据进行分析。
规则：
1. 只使用用户提供的 json 数据，不得编造任何数字
2. 数据缺失时，status 设为 "unavailable"
3. 输出必须是合法 json 格式
4. 不做买卖建议
5. summary 100-200 字
```

> **注意**: prompt 必须包含 "json" 字样（DeepSeek/DashScope 要求）。

## Phase 3: 编排 & 报告 ✅

**Pipeline** (`src/orchestrator/pipeline.py`):
- `run_analysis(report_type, symbols)` → 完整分析流程
- `asyncio.gather` 并行采集多只股票
- 3 Agent 并发分析每只股票

**报告生成** (`src/reports/generator.py`):
- `generate_report(analyses, report_type)` → `Report` 对象
- `_compute_overall()` — 3 Agent 投票（≥2 bullish → bullish）
- `_save_latest_json()` — 同步到 `site/data/latest.json`
- 固定免责声明：`⚠️ 本报告仅供个人研究参考，不构成投资建议。`

## Phase 4: 通知 & 调度 ✅

**通知模块** (`src/notify/`):
- `WeComNotifier` — 企微 Webhook 发送 Markdown
- `EmailNotifier` — SMTP 发送 HTML 邮件
- `BaseNotifier` — ABC + `get_notifier()` 工厂函数

**调度器** (`src/scheduler/jobs.py`):
- `run_pre_market()` / `run_post_market()` — 定时任务
- `start_scheduler()` — APScheduler Cron 启动
- 交易日判断 + 跳过非交易日

## Phase 5: API 服务 ✅

**FastAPI** (`src/api/routes.py`):

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/health` | 健康检查 `{status, version}` |
| POST | `/analyze` | 触发分析 `{type, symbols}` → `{status, report_path}` |
| GET | `/reports/latest` | 最新报告 Markdown |
| GET | `/reports/{date}` | 按日期取报告 |
| GET | `/site/latest.json` | 站点数据 JSON |

**CLI**: `python -m src.main serve [--port 8000]`

## Phase 6: 静态站点 ✅

**站点生成** (`src/site/generator.py`):
- `generate_site(report)` → 生成 `site/index.html`
- 深色 Fintech 主题 (`assets/theme.css`)
- 响应式布局 (`viewport`)
- `_sync_to_docs()` — 同步到 `docs/` 用于 GitHub Pages
- `_load_archive_entries()` — 归档列表

**站点结构**:
```
site/
├── index.html          # 主页
├── assets/theme.css    # 深色主题
├── data/latest.json    # 数据文件
└── archive/            # 历史报告 HTML
```

## Phase 7: GitHub Pages 发布 ✅

**发布脚本** (`src/publish/github.py`):
- `publish_to_github(report)` — git add docs/ → commit → push
- 需手动在 GitHub 开启 Pages 功能

**CLI**: `python -m src.main analyze --type pre --publish`

## Phase 8: 系统自检 ✅

**自检脚本** (`scripts/self_check.py`):

| 维度 | 检查项数 | 说明 |
|------|---------|------|
| 配置验证 | ~5 | settings.yaml、.env、Key 格式 |
| 模块导入 | ~1 | 所有 src/ 模块 |
| 依赖检查 | ~2 | requirements.txt 一致性 |
| Git 安全 | ~4 | .env 追踪、Key 泄露 |
| 数据源连通性 | 3 | 东财/新浪/腾讯 |
| LLM Provider | ~3 | 注册 + 实际调用 |
| 报告生成 | 4 | Markdown/免责声明/文件 |
| 站点生成 | 5 | HTML/响应式/主题 |
| API 服务 | 5 | 路由注册 |
| 测试套件 | 2 | pytest 执行 |

**用法**:
```bash
python scripts/self_check.py          # 全量
python scripts/self_check.py --quick   # 跳过网络
python scripts/self_check.py --fix     # 自动修复
```

## Phase 9: Cron 运维 ⏳

代码全部就绪，等待配置 Hermes Cron：
- 盘前 08:30: `analyze --type pre --publish`
- 盘后 16:00: `analyze --type post --publish`
- 每日 07:00: `self_check.py --quick` 健康检查

## CLI 命令汇总

```bash
# 分析
python -m src.main analyze --type pre [--symbols 600519,000001] [--publish]

# 启动 API 服务
python -m src.main serve [--port 8000]

# 启动调度器
python -m src.main schedule

# 系统自检
python scripts/self_check.py [--quick] [--fix]
```

## 测试状态

- 13 个测试，全部通过
- `tests/test_fetcher.py` — MA 计算 + Snapshot
- `tests/test_pipeline.py` — Pipeline 调用 + 站点生成
- `tests/test_report_generator.py` — 综合结论 + 报告生成

## 故障处理

| 问题 | 处理 |
|------|------|
| 数据源连接失败 | 降级链自动切换，记录 fetch_errors |
| LLM 调用失败 | fallback 到备选 Provider，最终 unavailable |
| 企微推送失败 | 日志记录，报告仍落盘 |
| API Key 缺失 | 优雅降级，不调用 LLM |
| 东财 push2his 502 | 已知限制，使用 push2 + ut 参数 |

## 禁止事项

- ❌ 不自动实盘交易
- ❌ 不实现用户登录
- ❌ 不引入 LangGraph
- ❌ 不删除免责声明
- ❌ 不实现 Tushare/QMT 集成
