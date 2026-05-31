# Phase G 产品规格 — 日更知识库与交易闭环

> **版本**: 3.0.0-alpha | **状态 SSOT**: [current-status.md](../reference/current-status.md)

## 概述

Phase G 将产品从「自选分析助手」升级为「**日更情报 → 推荐池 → 竞价/盘中闭环 → 复盘进化 → 仓位**」战术助手。

**架构约束**：单用户优先（`user_id='default'`）、SQLite + 单进程、盘中 1–3 分钟轮询、双轨 UI（静态快照 + Live Cockpit）。

---

## G1 日更知识库

| 项 | 说明 |
|----|------|
| **输入** | AkShare/东财：热度 Top20、宏观快讯、行业新闻、持仓公告、前日龙虎榜、北向、ST 风险 |
| **输出** | `daily_digest` 表 + `data/digest.json` |
| **调度** | 06:30 `daily_intelligence` |
| **验收** | 交易日 08:00 前 API/JSON 含 `hot_events[]`, `macro_summary`, `risk_flags[]` |
| **Out of Scope** | 雪球/同花顺全站爬虫 |

## G2 隔夜外盘

| 项 | 说明 |
|----|------|
| **输入** | 道指/纳指/标普、HXC、欧股、日经/KOSPI |
| **输出** | `overnight_snapshots` + digest 内 `overnight` 段 |
| **调度** | 06:45 `overnight_futures` |
| **验收** | digest 含 ≥3 个主要指数涨跌幅；`nasdaq_change > 2%` 触发 `strong_foreign_impact` |

## G3 期货异动

| 项 | 说明 |
|----|------|
| **输入** | 原油/黄金主力合约涨跌幅 |
| **输出** | `futures_snapshots` + `sector_hint` 标签 |
| **调度** | 06:45（与 G2 同 job） |
| **验收** | digest 含 `futures[]`；涨跌幅 > 阈值写入 `energy`/`precious_metals` |

## G4 推荐池（09:00 前）

| 项 | 说明 |
|----|------|
| **输入** | digest + overnight + futures + 硬信号扫描（沪深300/中证500 成分） |
| **输出** | `recommendation_pool` 表 + `data/recommendation.json`：`sectors[3].stocks[3]` |
| **硬过滤** | 市值 > 3000 亿、ST、近 N 日连板 |
| **调度** | 08:45 `recommendation_pool` |
| **验收** | 09:00 前 JSON 含 3 板块 × 3 股，过滤 ST/大盘/连板 |

## G5 竞价监测（09:15–09:25）

| 项 | 说明 |
|----|------|
| **输入** | 推荐池 + 竞价行情 |
| **指标** | 竞价量比、偏离度、撤单率（可选）、最后一分钟波动 |
| **输出** | `auction_snapshots`；最多新增 9 股入池 |
| **调度** | 每 1 min `auction_monitor` |
| **验收** | 竞价时段 DB 写入 ≥2 项指标；API `/api/auction/latest` 可用 |

## G6 盘中监测（09:30–15:00）

| 项 | 说明 |
|----|------|
| **监测对象** | 推荐池 + watchlist 并集 |
| **规则** | 放量突破/缩量回调/均线偏离 → `alerts` + WeCom |
| **调度** | 每 2–3 min `intraday_monitor` |
| **验收** | 至少 1 类量价预警写入 DB；WeCom 测试模式可跳过 |

## G7 深度分析（按需）

| 项 | 说明 |
|----|------|
| **输入** | 单股 graph + 公告 + 新闻 |
| **输出** | `DeepResearchAgent` 报告 |
| **API** | `POST /api/stocks/{code}/deep-analysis` |
| **验收** | API 返回结构化 `hidden_signals[]`, `related_events[]` |

## G8 盘后复盘 + 进化

| 项 | 说明 |
|----|------|
| **输入** | `recommendation_pool` vs 当日涨幅 ≥5% 全市场 |
| **输出** | `data/review.json` + hit/miss 报告 → EvolutionEngine |
| **调度** | 17:00 `recommendation_review` |
| **验收** | review JSON 含 hit_rate、missed_top、hit_top |

## G9 仓位管理（单用户）

| 项 | 说明 |
|----|------|
| **表** | `positions`, `position_rules`（`user_id='default'`） |
| **功能** | 开仓 CRUD、杠杆标记、止损/止盈规则、偏离预警 |
| **API** | `/api/positions` CRUD |
| **验收** | 可 CRUD 持仓；规则触发写入 alerts |

---

## 与 watchlist 关系

- **watchlist** = 长期关注自选
- **recommendation_pool** = 当日战术池（3×3 + 竞价加池）
- 盘中监测 = 两者并集

## 参考

- [knowledge-base-schema.md](../reference/knowledge-base-schema.md)
- [recommendation-engine.md](../reference/recommendation-engine.md)
- [monitoring-schedule.md](../reference/monitoring-schedule.md)
- [ui-phase-g.md](../reference/ui-phase-g.md)
