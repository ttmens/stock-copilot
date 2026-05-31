# 静动混合 UI 配置（Phase G 单页 Cockpit）

GitHub Pages 提供**静态快照**（digest/recommendation/review JSON）；**交易时段**在 Cockpit 连 FastAPI 轮询。

## 双轨架构

| 轨道 | 时段 | 入口 |
|------|------|------|
| 快照轨 | 盘前/盘后 | `index.html` → `app/cockpit.html`（只读 JSON） |
| 实时轨 | 09:15–15:00 | `app/cockpit.html#today` |
| 通知轨 | 全天 | 企微 Webhook |

## 配置 API 地址

**源文件**：[`src/site/app/config.js`](../../src/site/app/config.js)

```javascript
window.STOCK_COPILOT = {
  PRODUCTION_API_BASE: "https://your-vps:8000",  // GitHub Pages 用
  API_BASE: ""  // 留空则自动检测
};
```

- 本地 / 服务器同源：自动使用 `window.location.origin`
- GitHub Pages：使用 `PRODUCTION_API_BASE`

## CORS

`config/settings.yaml` → `api.cors_origins` 需包含 `https://ttmens.github.io`

## Cockpit Tab 与轮询

| Tab / 面板 | 轮询 | 功能 |
|------------|------|------|
| 今日 · 情报 | 5min | 日更 digest |
| 今日 · 推荐池 | 1min (09:00–09:30) | 3×3 池 |
| 今日 · 竞价 | 60s | 竞价监测 |
| 今日 · 盯盘 | 120s | 预警流 + 池状态 |
| 今日 · 复盘 | 静态 | 盘后 hit/miss |
| 自选 | 按需 | latest.json + 盘中涨跌 |
| 我的 | 120s | 仓位 CRUD |

## 共享 JS

- `ui-render.js` — 卡片/dashboard HTML render SSOT
- `layout.js` — Tab hash 路由、双端 nav
- `cockpit.js` — 面板 load、Focus/Peek、compare
- `api-client.js` — 统一 fetch、离线 Banner
- `live.js` — PHASE_LABELS、轮询工具

Hermes Agent 运维见 [hermes-cockpit-handoff.md](../guides/hermes-cockpit-handoff.md)。

详见 [ui-phase-g.md](../reference/ui-phase-g.md)
