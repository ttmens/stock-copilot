# Phase D 交付计划 — 设计债清零

> 版本 v1.5.0 (Phase D) | 2026-05-27

## 目标

在不扩 Phase 2 scope 前提下，让 Phase B/C 设计文档描述的能力 **真实可验证**。

## 交付清单

| 模块 | 状态 | 说明 |
|------|------|------|
| FundamentalAgent 真调用 | done | pipeline 并行 4 LLM Agent |
| 门控涨跌停/停牌 | done | fetcher 检测 + fuse_signals 接线 |
| site 不重算 fusion | done | latest.json 使用 pipeline 融合结果 |
| announcement_days 过滤 | done | fetcher 按配置天数过滤 |
| news 进 JSON | done | snapshot.news surfaced |
| fusion_weights sum=1.0 | done | config 修正 |
| 价格/信号色分离 | done | theme.css + generator |
| 首页金字塔 L2 | done | summary + key_basis + accordion |
| 静动混合 | done | config.js + intraday chips |
| stock SSR fallback | done | latest.json 首屏 |
| filter 表格 | done | app.js 统一过滤 |
| SSOT 文档 | done | 08-CURRENT-STATUS + API version |

## 明确不做

- 历史信号 ↑↓→ 对比
- 三维 Tab（技术/公告/资金）全量 Tab
- Tushare / 回测 / LangGraph

## 验收矩阵

| 域 | 标准 | 命令 |
|----|------|------|
| functional | Agent/门控/fusion 一致 | `pytest tests/` |
| ux | 颜色/金字塔/静动 | `python scripts/ui_acceptance.py --full` |
| ops | SSOT 无漂移 | `python scripts/check_docs_ssot.py` |
