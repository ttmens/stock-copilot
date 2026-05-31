# 全链路调度 — Phase G

> 配置 SSOT：`config/settings.yaml` → `phase_g.schedule`  
> 实现：`src/scheduler/jobs.py`

## Cron 时间表（Asia/Shanghai, mon-fri）

| 时间 | Job ID | 模式 | 模块 |
|------|--------|------|------|
| 06:30 | daily_intelligence | 采集 + LLM digest | `src/intelligence/ingester.py` |
| 06:45 | overnight_futures | 规则标记 | `src/intelligence/overnight.py`, `futures.py` |
| 08:30 | pre_market | Full（保留） | `DeliveryPipeline.run_full(PRE)` |
| 08:45 | recommendation_pool | 扫描 3×3 | `src/recommendation/engine.py` |
| 09:15–09:25 | auction_monitor | 每 1 min | `src/monitoring/auction.py` |
| 09:30–11:30 | intraday_monitor | 每 2 min | `src/monitoring/intraday.py` |
| 13:00–15:00 | intraday_monitor | 每 2 min | 同上 |
| 15:30 | post_market | Full（保留） | `DeliveryPipeline.run_full(POST)` |
| 16:00 | evolution | 进化 + 推荐复盘输入 | `EvolutionEngine` |
| 17:00 | recommendation_review | hit/miss 报告 | `src/review/recommendation_review.py` |

## 交易时段检测

`src/monitoring/session.py` → `get_market_session()` 返回：

- `pre_market` — 06:00–09:15
- `auction` — 09:15–09:25
- `morning` — 09:30–11:30
- `lunch` — 11:30–13:00
- `afternoon` — 13:00–15:00
- `post_market` — 15:00+
- `closed` — 非交易日

## 轮询间隔（前端 Live Cockpit）

| 页面 | 时段 | 间隔 |
|------|------|------|
| digest.html | 盘前 | 5 min |
| recommend.html | 09:00–09:30 | 1 min |
| auction.html | 09:15–09:25 | 60 s |
| live.html | 盘中 | 120 s |
| positions.html | 全天 | 120 s + CRUD 即时 |

## 降级

- 非交易日：跳过 realtime jobs
- 1G 内存：禁止并发 Full LLM；digest 每日 1 次
- 竞价撤单率不可得：指标标 `unavailable`
