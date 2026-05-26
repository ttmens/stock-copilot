# Phase C 交付计划与验收

> 版本 v1.4.0 | 2026-05-26

## 目标

服务端为数据中枢；GitHub Pages 承载静态快照；FastAPI 提供动态能力；单进程 `systemd → python -m src.main run`。

## 交付清单

| 模块 | 状态 | 说明 |
|------|------|------|
| fusion 权重归一化 | ✅ | `config/fusion_weights.json` sum=1.0 + `_normalize_layer_weights` |
| Fast/Full 双 pipeline | ✅ | 盘中 Fast 无 LLM；盘前/盘后 Full + publish |
| DeliveryPipeline | ✅ | CLI / scheduler / API 统一 |
| Evolution 闸门 | ✅ | `auto_apply_weights` / `auto_mutate_watchlist` 默认 false |
| SQLite 扩展表 | ✅ | watchlist, jobs, intraday_quotes, published_meta, evolution_suggestions |
| Watchlist API | ✅ | `/api/watchlist` CRUD |
| Jobs / Published API | ✅ | `/api/jobs`, `/api/published` |
| 静动混合前端 | ✅ | `docs/app/` 筛选、单页详情、自选管理 |
| skip_stock_html | ✅ | 停 50× HTML，链接 `app/stock.html?code=` |
| 新闻 AkShare | ✅ | `_fetch_news` 尝试 `stock_news_em` |
| 龙虎榜 participants | ✅ | 营业部明细写入 JSON（网络允许时） |
| 文档 v1.4 | ✅ | 本文件 + README + RUNBOOK |

## 明确不做（Phase 2b / 3）

- 多空辩论 / LangGraph
- Tushare 本地库
- 回测 / 模拟盘
- Redis / Celery / Docker

## 验收

1. `python -m pytest tests/` 全部通过
2. `python -m src.main run` 启动 scheduler + API
3. `GET /health` 返回 ok
4. Full 后 `docs/data/latest.json` 与 DB 一致；`_sync_to_docs` 护栏生效
5. 盘中 job 仅 Fast，不 push git

## 运维切换

```bash
# stock-copilot.service
ExecStart=.../python3 -m src.main run
```
