# Phase G UI 规格 — 单页 Cockpit + 双端适配

> **视觉 SSOT**: [design-system/tokens.md](../design-system/tokens.md)  
> **实现**: `src/site/` → `docs/`

## 产品定位

「**AI 结论先行的日更战术助手**」— 按交易日程在一站完成：情报 → 推荐 → 竞价 → 盯盘 → 复盘。

## 双轨架构

| 轨道 | 入口 | 时段 | 数据源 |
|------|------|------|--------|
| 快照轨 | GitHub Pages | 07:00–09:00 digest；15:30+ review | baked JSON/HTML |
| 实时轨 | FastAPI + `app/cockpit.html` | 09:15–15:00 | REST 轮询 |
| 通知轨 | 企微 | 全天 | Webhook |

## 导航 IA（3 Tab）

**桌面 `site-nav` / 移动 `bottom-nav`**（语义一致）：

| Tab | Hash | 内容 |
|-----|------|------|
| 今日 | `#today` | Session 驱动 5 面板 Cockpit |
| 自选 | `#watchlist` | 自选股卡片 + 市场广度摘要 |
| 我的 | `#me` | 仓位 CRUD + history/dashboard 链接 |

**主入口**: `app/cockpit.html`  
**index.html**: meta refresh → `app/cockpit.html`

**保留 drill-down**:
- `app/stock.html?code=` — 个股详情
- `app/watchlist.html` — 自选管理

**旧页 redirect stub**（兼容书签）:
- `digest|recommend|auction|live|review.html` → `cockpit.html#today`
- `positions.html` → `cockpit.html#me`

## Journey 交互（Now → Focus → Peek）

| 模块 | 说明 |
|------|------|
| `.journey-hero` | 战术 Hero：当前阶段、行动指引、倒计时、CTA |
| `.journey-timeline` | 5 步进度条（mobile 横滑 / desktop 等分+连接线） |
| `.cockpit-panel--focus` | 当前 session 面板：渐变左边框 + shadow |
| `.cockpit-panel--peek` | 非当前面板折叠时一行摘要（peek meta） |

## Session 驱动

Hero + Timeline 替代旧 Session Rail 外链；CTA 滚动到 Focus 面板。

| session | 默认展开面板 | 轮询 |
|---------|-------------|------|
| pre_market | 情报 + 推荐池 | digest 5min, pool 1min |
| auction | 推荐池 + 竞价 | auction 60s |
| morning / afternoon | 盯盘 D | alerts+pool 120s |
| lunch | 池摘要 + 最近预警 | 5min 或暂停 |
| post_market / closed | 复盘 E | 静态 review.json |

## 组件（theme.css + ui-render.js）

| Class / API | 用途 |
|-------------|------|
| `ui-render.js` → `renderStockCard` | 与 TPL_HOME 同等 card 结构 |
| `renderSignalDashboard` | 市场温度 + signal-bar + legend |
| `renderReviewStats` | 命中率环 + 数字卡 |
| `.journey-hero` / `.journey-timeline` | 日程导航 |
| `.cockpit-panel--focus` / `--peek` | Focus/Peek 态 |
| `.event-card` | digest 热点 |
| `.pool-stock-card--compact` | 推荐池 3×3 |
| `.live-cockpit` | 盯盘双栏 (≥1024px) |

## 共享 JS

| 文件 | 职责 |
|------|------|
| ui-render.js | HTML 渲染 SSOT（stock-card、dashboard、review） |
| layout.js | Tab hash 路由、双端 nav、alert badge |
| cockpit.js | 面板 load、Focus/Peek、compare、view-toggle |
| live.js | PHASE_LABELS、轮询工具 |
| api-client.js | 统一 fetch、离线 Banner |

## 视觉回归标准

- 自选 Tab 卡片须含 `decision-card` + `metrics-row`（与 index TPL_HOME parity）
- Header 含 brand SVG + 交易日 meta
- Timeline 当前步 `--active` 明确可见

## 降级 UI

| 场景 | 表现 |
|------|------|
| Pages 无 API | 顶栏 Banner + 只读静态 JSON |
| API 离线 | stale 标记 + 上次更新时间 |
| 非竞价时段 | 竞价面板显示最近快照或空态 |
| Mobile 表格 | 竞价/池 table → `.cockpit-mobile-card` |

## 验收

- 375px：bottom-nav、safe-area、无整页横向滚动
- 1280px：site-nav、盘前双列、盯盘双栏同屏
- `scripts/ui_acceptance.py --full`
