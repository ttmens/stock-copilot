# Phase G 交付 Checklist

> 对齐 [phase-g-product-spec.md](../../explanation/phase-g-product-spec.md)

## Wave 0 — 文档 + UI 骨架

- [ ] phase-g-product-spec.md
- [ ] knowledge-base-schema.md
- [ ] recommendation-engine.md
- [ ] monitoring-schedule.md
- [ ] ui-phase-g.md
- [ ] VERSION.md → 3.0.0-alpha
- [ ] api-client.js, live.js, config.js PRODUCTION_API_BASE
- [ ] theme.css Phase G 组件
- [ ] generator.py 导航 + Session Rail
- [ ] check_docs_ssot.py 扩展

## Wave 1 — G1–G3 + 静态页

- [ ] src/intelligence/
- [ ] DB migration（market_events, daily_digest, overnight, futures）
- [ ] daily_intelligence job
- [ ] recommendation_pool job
- [ ] data/digest.json, data/recommendation.json
- [ ] digest.html, recommend.html
- [ ] tests/test_intelligence.py, test_recommendation.py

## Wave 2 — G5 竞价

- [ ] src/monitoring/auction.py
- [ ] GET /api/auction/latest
- [ ] auction.html（60s poll）

## Wave 3 — G6 盘中

- [ ] src/monitoring/intraday.py, alerts.py
- [ ] GET /api/alerts, /api/recommendations/today
- [ ] live.html（120s poll）
- [ ] WeCom 预警

## Wave 4 — G7–G8 复盘 + 仓位

- [ ] recommendation_review.py
- [ ] portfolio/tracker.py
- [ ] review.html, positions.html
- [ ] dashboard 改造

## Wave 5 — G7 深度

- [ ] DeepResearchAgent
- [ ] POST /api/stocks/{code}/deep-analysis
- [ ] stock.html 深度区块

## 验收

- [ ] pytest ≥20 新用例
- [ ] check_docs_ssot PASS
- [ ] ui_acceptance 扩展 PASS
