# Stock Copilot / 智策 NexStrat — Version

| Field | Value |
|-------|-------|
| **Product version** | `3.0.0-alpha` |
| **Current phase** | Phase G (in progress) |
| **Status SSOT** | [reference/current-status.md](reference/current-status.md) |
| **Last updated** | 2026-05-26 |

## Phase delivery matrix

| Phase | Name | Status | Notes |
|-------|------|--------|-------|
| A | Signal fusion + SQLite | Delivered | Hard/soft/gate fusion |
| B | Dragon tiger + 5-layer UI | Delivered | Announcement keywords |
| C | Static/dynamic split | Delivered | DeliveryPipeline, watchlist API, `main run` |
| D-debt | Design debt closure | Delivered | 4 LLM agents, gate flags, UI pyramid |
| D-mirofish | Multi-agent intelligence | Partial | Debate, graph, scenario sim |
| E | System hardening | Delivered | self_check, API auth, fusion_weights v3 |
| F | OODA feedback loop | Partial | Postmortem, breadth delivered; stagnation pending |
| **G** | **日更知识库与交易闭环** | **Alpha** | See below |

## Phase G detail (3.0.0-alpha)

| ID | Feature | Status |
|----|---------|--------|
| G1 | 日更知识库 / digest | Delivered |
| G2 | 隔夜外盘 | Delivered |
| G3 | 期货 sector hints | Delivered |
| G4 | 推荐池 3×3 | Delivered |
| G5 | 竞价监测 | Delivered |
| G6 | 盘中监测 + alerts | Delivered |
| G7 | 盘后复盘 + 深度分析 | Delivered |
| G8 | 单用户仓位 | Delivered |
| G-UI | 双轨 UI + Live Cockpit | Delivered |

## Explicitly out of scope

- Tushare local database
- Redis / Celery / Docker
- Multi-tenant / auto-trading
- Tick-level streaming

## Changelog (summary)

| Version | Date | Highlights |
|---------|------|------------|
| 3.0.0-alpha | 2026-05-26 | Phase G: intelligence, recommendation pool, auction/intraday, positions, dual-track UI |
| 2.1.0 | 2026-05-30 | Phase F core: postmortem, thesis, breadth, contradiction |
| 2.0.0 | 2026-05-28 | NexStrat rebrand, Phase D MiroFish, UI v2 |
