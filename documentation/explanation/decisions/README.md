# 决策记录

## 2026-05-24 — LLM Provider 抽象化

- **背景**: 设计文档默认 DeepSeek，但实际 Hermes 可能接入多种 LLM
- **备选**: A) 硬编码 DeepSeek B) OpenAI SDK 兼容抽象 C) 自定义 HTTP 客户端
- **选择**: B — OpenAI SDK 兼容抽象
- **理由**: OpenAI SDK 已成事实标准，DeepSeek/OpenRouter/Ollama/Azure 均支持兼容接口
- **影响**: 用户只需改 base_url + API Key 即可切换模型，代码零修改

## 2026-05-24 — AkShare 同步调用包装为 async

- **背景**: AkShare 是同步库，pipeline 需要异步并发
- **备选**: A) 全部用 asyncio.to_thread B) 用 httpx 重写采集 C) 多进程
- **选择**: A — asyncio.to_thread 包装
- **理由**: 最小改动，AkShare 接口可能变化，不重写采集逻辑
- **影响**: 采集层 async/await 语法统一，但底层是线程池

## 2026-05-24 — 资金流降级策略

- **背景**: AkShare 资金流接口不稳定（北向/主力都可能失败）
- **备选**: A) 强制失败阻塞 B) 降级为 unavailable C) 多数据源
- **选择**: B — 降级为 unavailable
- **理由**: 资金流是 P1 非必需，单维度失败不阻塞整份报告
- **影响**: 报告中资金面可能标注「数据暂不可用」

## 2026-05-24 — 无 LLM API Key 时的降级

- **背景**: 部署环境可能未配置 LLM API Key
- **备选**: A) 启动报错 B) Agent 返回 unavailable C) 使用规则摘要
- **选择**: B — Agent 返回 unavailable
- **理由**: 数据采集层仍可工作，报告可生成，只是缺少 AI 分析
- **影响**: 系统可在无 LLM 情况下部分运行

## 2026-05-24 — 静态站点设计系统

- **背景**: 需要在 GitHub Pages 上展示深色 fintech 风格页面
- **备选**: A) ui-ux-pro-max 生成 B) 手动设计 C) Tailwind CDN
- **选择**: B — 手动设计 token + 内联 Jinja2 模板
- **理由**: 零外部 CDN 依赖（国内访问），单一 theme.css 文件，兼容 GitHub Pages
- **影响**: 全站统一 CSS 变量，移动端响应式，无需构建工具

## 2026-05-24 — GitHub Pages 部署策略

- **背景**: 需要将生成的静态页面推送到 GitHub Pages
- **备选**: A) gh-pages 分支 B) /docs 目录 C) 独立 pages 仓库
- **选择**: B — /docs 目录
- **理由**: 代码和页面在同一仓库同一分支，管理简单，GitHub Pages 原生支持
- **影响**: site/ 生成后自动同步到 docs/，push 即部署

## 2026-05-24 — 通知模块工厂模式

- **背景**: 支持企微和邮件两种通知渠道
- **备选**: A) 硬编码单一渠道 B) 工厂模式 C) 插件注册表
- **选择**: B — 工厂模式 + settings.notify.type 切换
- **理由**: 简单明了，配置决定行为，无需额外依赖
- **影响**: .env 配置 WECOM_WEBHOOK 即可启用企微推送

## 2026-05-24 — 多源数据 Provider 架构

- **背景**: AkShare 在此服务器上不稳定的问题（RemoteDisconnected），单一数据源不可靠
- **调研**: a-stock-data (⭐1985) V3.1 完全移除 AkShare 依赖，直连 HTTP API
- **选择**: 多源 Provider 架构 — AkShare (主) → Eastmoney/Sina/Tencent (备选)
- **理由**: 每个数据类型至少有 2 个独立数据源，一个挂了自动切另一个
- **影响**: fetcher.py 重构为链式降级；新增 ValuationInfo/DragonTigerItem 等模型
- **验证**: 3只股票（茅台/平安/宁德）全部获取 60 日K线 + PE/PB/市值 + 龙虎榜

## 2026-05-24 — Eastmoney push2 鉴权 token

- **背景**: 东财 push2 API 需要 ut 参数才能正常返回
- **选择**: 使用固定 token `fa5fd1943c7b386f172d6893dbbd1`
- **影响**: PE/PB/市值/资金流等 Eastmoney 接口正常返回

## 2026-05-26 — Phase C 静动分离 + 单进程

- **背景**: 50× HTML 进 git 成本高；自选需 API；盘中不宜频繁 push
- **选择**: SQLite 为中枢；Full 导出静态到 GitHub Pages；Fast 只写库+API；`main run` 单进程
- **影响**: `skip_stock_html`、DeliveryPipeline、watchlist/jobs API、`docs/app/` 混合前端

## 2026-05-26 — Evolution 默认闸门

- **选择**: `auto_mutate_watchlist: false`、`auto_apply_weights: false`
- **影响**: 权重写入 `fusion_weights.proposed.json`；自选变动进 `evolution_suggestions` 待确认

## 2026-05-26 — 融合权重归一化

- **背景**: `fusion_weights.json` 曾出现 sum≠1.0
- **选择**: 配置修正 + `_normalize_layer_weights()` 运行时归一化
- **影响**: 最终评分不再因权重和漂移

## 2026-05-30 — Phase F OODA 反馈闭环增强

- **背景**: 借鉴 tradermonty/claude-trading-skills 的 Signal Postmortem 和 Trader Memory Core
- **选择**: 新增逐信号 postmortem 记录 + thesis 全生命周期管理 + contradiction 检测 + 市场广度评分
- **影响**: 
  - `src/evolution/postmortem.py` — PostmortemRecorder
  - `src/evolution/thesis.py` — ThesisManager
  - `src/data/signal_fusion.py` — detect_contradictions() 集成
  - `src/analysis/breadth.py` — MarketBreadthScorer
  - `src/data/db_manager.py` — signal_postmortems + theses 表
  - `src/data/models.py` — SignalOutcome/ThesisType/ThesisStatus enums + SignalPostmortem/ThesisRecord models

## 2026-05-26 — Phase G 双轨 UI + 单用户优先

- **背景**: Phase G 需竞价/盘中/仓位实时能力，GitHub Pages 纯静态不足
- **选择**: 快照轨（Pages）+ Live Cockpit（FastAPI 轮询）+ 企微通知轨；`user_id='default'` 预留多用户
- **影响**: `app/live.js`, `PRODUCTION_API_BASE`, 新页面 digest/recommend/auction/live/positions/review

## 2026-05-26 — 推荐池 vs watchlist 分离

- **背景**: 战术池 3×3 与长期自选语义不同
- **选择**: `recommendation_pool` 表独立；盘中监测 = 池 ∪ watchlist
- **影响**: `src/recommendation/engine.py`, `app/recommend.html`

## 2026-05-26 — 盘中分钟轮询（非 Tick）

- **背景**: 1G 内存 VPS 无法支撑 Tick 流
- **选择**: 竞价 1min、盘中 2–3min Fast + 规则预警
- **影响**: `src/scheduler/jobs.py`, `src/monitoring/`

## 2026-05-30 — 文档迁离 docs/ 至 documentation/

- **背景**: `docs/` 与 GitHub Pages 混放，版本索引分裂（v1.4 vs v2.1）
- **选择**: `docs/` 仅静态站；Markdown SSOT 迁至 `documentation/`（Diátaxis 结构）
- **影响**: AGENTS.md、workflow_state、check_docs_ssot 路径更新

## 2026-05-30 — 产品版本统一为 2.1.0

- **背景**: API health 2.0.0、索引 v1.4、SSOT v2.1 并存
- **选择**: `documentation/VERSION.md` 为单一版本源；Phase F 标 partial
- **影响**: routes.py、AGENTS.md、RUNBOOK 对齐 2.1.0

## 2026-05-27 — Phase D 纳入多 Agent 辩论

- **背景**: Phase C 曾将辩论标为 Out of Scope
- **选择**: 轻量 2-round DebateOrchestrator（非 LangGraph）
- **影响**: `debate.py`、pipeline、confidence 共识加成
