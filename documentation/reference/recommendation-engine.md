# 推荐池引擎 — Phase G

## 概念

| 池 | 用途 | 生命周期 |
|----|------|----------|
| watchlist | 长期自选 | 用户手动维护 |
| recommendation_pool | 当日战术池 | 每日 08:45 生成，竞价可加池 |

## 输出结构

```json
{
  "trade_date": "2026-05-26",
  "generated_at": "2026-05-26T08:45:00",
  "filters_applied": ["no_st", "mcap_lt_3000b", "no_limit_up_streak"],
  "sectors": [
    {
      "name": "半导体",
      "reason": "热点重合 + 资金流入",
      "stocks": [
        {"code": "688981", "name": "中芯国际", "score": 0.72, "source": "scan", "focus_flag": false}
      ]
    }
  ],
  "auction_added": []
}
```

## 硬过滤规则

1. **ST** — `stock_meta.is_st = 1` 或名称含 ST
2. **大盘** — 总市值 > 3000 亿（30e10 元）
3. **连板** — 近 3 日连续涨停（`limit_up_streak >= 3`）

## 软排序权重（默认）

| 因子 | 权重 |
|------|------|
| 热点重合 | 0.30 |
| 硬信号 score | 0.25 |
| 资金流入 | 0.20 |
| 技术形态 | 0.15 |
| digest sector_impact | 0.10 |

## 板块选择

1. 从 digest `sector_impact` 取 Top 3 方向为 bullish 的板块
2. 每板块从 universe（沪深300 ∪ 中证500 成分）按软排序取 Top 3
3. 不足 3 板块时用 breadth 强势行业补位

## 竞价加池（G5）

- 09:15–09:25 每分钟扫描非池内股
- 竞价量比 > 2 且偏离度 > 1% → 候选
- 最多新增 9 股，`source: "auction"`

## API

- `GET /api/recommendations/today` — 当日完整池（含竞价加池）
- 静态：`data/recommendation.json`
