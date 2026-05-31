# 知识库 Schema — Phase G

## SQLite 表

### market_events

| 列 | 类型 | 说明 |
|----|------|------|
| id | INTEGER PK | |
| trade_date | TEXT | YYYY-MM-DD |
| event_type | TEXT | hot / macro / sector / announcement / dragon_tiger / northbound / st_risk |
| title | TEXT | |
| summary | TEXT | |
| source | TEXT | akshare / eastmoney / manual |
| impact_score | REAL | 0–1 |
| sector_tags | TEXT | JSON array |
| raw_json | TEXT | 原始数据 |
| created_at | TEXT | |

### daily_digest

| 列 | 类型 | 说明 |
|----|------|------|
| trade_date | TEXT PK | |
| hot_events | TEXT | JSON array |
| sector_impact | TEXT | JSON array |
| macro_summary | TEXT | |
| risk_flags | TEXT | JSON array |
| overnight_json | TEXT | G2 快照 |
| futures_json | TEXT | G3 快照 |
| llm_summary | TEXT | DailyDigestAgent 输出 |
| generated_at | TEXT | |

## digest.json 静态结构

```json
{
  "trade_date": "2026-05-26",
  "generated_at": "2026-05-26T06:45:00",
  "hot_events": [
    {"rank": 1, "title": "...", "sector_tags": ["新能源"], "impact_score": 0.8}
  ],
  "macro_summary": "美联储维持利率不变...",
  "sector_impact": [
    {"sector": "半导体", "direction": "bullish", "reason": "..."}
  ],
  "risk_flags": ["ST 退市风险警示 3 只"],
  "overnight": {
    "nasdaq": {"change_pct": 1.2},
    "sp500": {"change_pct": 0.8},
    "nikkei": {"change_pct": -0.3},
    "strong_foreign_impact": false
  },
  "futures": [
    {"symbol": "原油", "change_pct": 2.1, "sector_hint": "energy"}
  ]
}
```

## 实体关系

```
market_events ──► daily_digest (聚合)
daily_digest ──► recommendation_pool (G4 输入)
overnight_snapshots ──► daily_digest.overnight_json
futures_snapshots ──► daily_digest.futures_json
```
