---
name: stock-copilot-design
version: 1.2.0
updated: 2026-05-25
---

# Stock Copilot 整体方案设计

## 1. 产品定位

| 维度 | 定义 |
|------|------|
| 产品名 | Stock Copilot（智策） |
| 一句话 | 基于 AI 的 A 股个人投研助手：看全、看懂、及时提醒 |
| 目标用户 | 有个人炒股经验、希望提升决策效率的投资者（Phase 1 自用） |
| 核心价值 | 聚合行情、公告、资金、估值等分散信息 → 结构化决策参考 + 静态网页发布 |
| 不做 | 不承诺收益、不自动下单、不对外投顾 |

**合规定位**：个人研究工具 + 信息聚合 + 风险提示。

## 2. 业界参考

| 类型 | 代表 | 借鉴点 |
|------|------|--------|
| AI 多 Agent | TradingAgents-AShare, FinAgent | Agent 分工、报告结构 |
| 数据管道 | stock_datasource, quant-data-pipeline | 插件化采集、降级链 |
| 量化平台 | 聚宽、QMT | Phase 3 回测/实盘参考 |
| 合规标杆 | 盈米且慢 AI小顾 | 免责声明、适当性提示 |

## 3. 系统分层（完整愿景）

```
用户层: Web (静态 HTML) / 企微推送 / CLI / API
应用层: API Gateway, 自选管理, 任务调度, 通知, 发布
决策层: 编排器, 多 Agent(Technical/Fundamental/Capital), 规则引擎, 回测(Phase3)
数据层: 采集(AkShare/Eastmoney/Sina/Tencent), ETL, SQLite, 缓存
执行层: 模拟盘, miniQMT(Phase3)
```

## 4. 演进路线

| 阶段 | 名称 | 周期 | 核心能力 | 状态 |
|------|------|------|----------|------|
| **MVP** | 路线 A 轻量版 | 4-6 周 | 自选股 + 3 Agent + Markdown 报告 + 静态网页 + GitHub Pages 发布 | ✅ 完成 |
| **Phase A** | 信号融合 + 持久化 | +2 周 | 三层信号融合(硬50%+软30%+门控20%) + SQLite 持久化 | ✅ 完成 |
| **Phase B** | 信息挖掘 + UI 升级 | +2 周 | 龙虎榜 + 公告关键词提取 + 5层融合 + UI 重构 + 自检脚本 | ✅ 完成 |
| Phase 2 | 完整决策平台 | +2-3 月 | Web UI 交互, 多空辩论, Tushare 本地库, 龙虎榜深度分析 | 📋 规划 |
| Phase 3 | 量化闭环 | +3-6 月 | 回测, 模拟盘, miniQMT | 📋 规划 |

## 5. MVP 数据流程

```
watchlist.yaml
  → DataFetcher.fetch_stock() (多源降级链，单股并行)
     ├─ K线: AkShare → Sina → Tencent
     ├─ 估值: Eastmoney push2 → Tencent
     ├─ 资金流: Eastmoney push2 → AkShare
     ├─ 公告: AkShare → 空
     ├─ 新闻: Eastmoney (暂时禁用)
     └─ 龙虎榜: Eastmoney datacenter
  → StockSnapshot (统一 Pydantic 模型)
  → Technical / Fundamental / Capital Agent (每只股票顺序，股票间并行)
     └─ LLMClient (multi-provider: deepseek-v4-flash 优先, qwen3.6-plus 备选)
  → Report Generator (Markdown + latest.json)
  → Site Generator (Jinja2 HTML → site/index.html)
  → Notify (企微 Webhook / SMTP 邮件)
  → Publish (git commit docs/ → GitHub Pages)
```

## 6. Agent 角色（v1.2 — 4 Agent）

| Agent | 职责 | 输入 | 输出 |
|-------|------|------|------|
| Technical | K 线(近20条)、均线(MA5/10/20)、量能、支撑压力位 | OHLCV + MA | trend, key_signals, summary, confidence |
| Fundamental | 公告摘要、利好/利空判断 | 近7日公告列表 | 利好/利空, summary, risk_points |
| Capital | 主力/北向资金流（无数据 → unavailable，不阻塞） | 资金流数据 | 资金态度, summary, risk_points |
| **Announcement** | **公告关键词提取 (LLM)** | **公告标题列表** | **key_events[], sentiment, risk_flags[]** |

> 综合研判由 `fuse_signals()` 信号融合引擎完成（5层加权），不再使用简单投票机制。

## 6.1 信号融合架构（v1.2 新增）

```
最终评分 = 硬信号(40%) + LLM软信号(25%) + 规则门控(15%) + 龙虎榜(10%) + 公告(10%)
```

- 动态权重：数据不可用时自动重新分配
- ST/停牌股直接过滤
- 置信度 = 层间一致性 + 信号强度 + 数据完整度
- 详见 `13-CURRENT-STATUS.md` §5

## 7. 非功能需求

| 指标 | MVP 目标 |
|------|----------|
| 10 只自选股分析耗时 | < 5 分钟 |
| 数据源部分失败 | 报告仍可生成（降级链 + 单股失败隔离） |
| LLM 降级 | 主 provider 失败自动切换备选，支持 fallback / concurrent 模式 |
| 调度 | 盘前 08:30、盘后 16:00（可配置，非交易日跳过） |
| 可用性 | 非交易日自动跳过（AkShare 交易日日历 + 工作日兜底） |

## 8. 风险

| 风险 | 缓解 |
|------|------|
| AkShare 不稳定 | 多源降级链(AkShare→Sina→Tencent)、重试、单股失败隔离 |
| LLM 幻觉 | 结构化 JSON 输出、SYSTEM_PROMPT 约束仅基于给定数据 |
| LLM 服务中断 | 双 provider 配置(deepseek-v4-flash + qwen3.6-plus)，fallback 模式自动切换 |
| 合规 | 免责声明、个人自用定位 |
| 成本 | DeepSeek 按量计费，每日 2 次 × N 只，备选 Qwen 成本可控 |
