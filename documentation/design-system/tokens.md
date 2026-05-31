---
version: "2.0"
name: Stock Copilot NexStrat
description: 智策 NexStrat 设计系统 — 视觉 SSOT，与 src/site/theme.css 同步
implementation: src/site/theme.css
published: docs/assets/theme.css
---

# 智策 NexStrat — 设计系统（视觉 SSOT）

> **路径**: `documentation/design-system/tokens.md`  
> **维护规则**：先改本文档 → 再改 `src/site/theme.css` → sync 到 `docs/assets/theme.css`  
> 废弃摘要：`docs/UI-UX-Style.md`（redirect）  
> 历史版本：[archive/snapshots/DESIGN-v1-alpha.md](../archive/snapshots/DESIGN-v1-alpha.md)

## 约束（DECISIONS.md）

- 单文件 `theme.css`，**零 CDN / 无 Tailwind**
- GitHub Pages 静态发布
- 源码：`src/site/`，发布：`docs/`（须 sync）

## 色彩语义（重要）

### A 股价格 vs 信号（分离）

| 用途 | CSS 变量 | 值 | 说明 |
|------|---------|-----|------|
| 价格上涨 | `--price-up` | `#EF4444` | 红涨（A 股惯例） |
| 价格下跌 | `--price-down` | `#22C55E` | 绿跌 |
| 看多信号 | `--signal-bull` | `#22C55E` | 国际惯例 |
| 看空信号 | `--signal-bear` | `#EF4444` | |
| 观望 | `--signal-hold` | `#94A3B8` | |

**禁止** 在信号标签上使用价格色逻辑混淆。

### 品牌与表面

| Token | 值 |
|-------|-----|
| `--accent-purple` | `#7b3ff2` |
| `--accent-blue` | `#4a5bff` |
| `--accent-cyan` | `#00f5ff` |
| `--canvas-deep` | `#0a1628` |
| `--canvas` | `#1a2742` |
| `--canvas-alt` | `#0f1f3a` |
| `--text-primary` | `#ffffff` |
| `--text-secondary` | `rgba(255,255,255,0.72)` |
| `--border-hair` | `rgba(255,255,255,0.08)` |

### 五层信号维度色

`--dim-hard` 青 / `--dim-soft` 紫 / `--dim-gate` 蓝 / `--dim-dragon` 紫罗兰 / `--dim-announce` 琥珀

## 字体与间距

- 中文：`--font-cn`（PingFang SC, Microsoft YaHei）
- 等宽：`--font-mono`
- 间距：`--sp-xs` 4px … `--sp-2xl` 32px
- 圆角：`--r-sm` 8px … `--r-full` 9999px

## 信息架构（金字塔）

```
第1层 结论   — 信号标签 + 评分（3 秒）
第2层 原因   — 5 层信号分解 + 一句话
第3层 证据   — 硬信号 + LLM 维度
第4层 上下文 — 龙虎榜 + 公告 + 历史
```

## 核心组件

- **signal-dashboard** — 市场温度 + 信号分布条
- **stock-card** / **decision-card** — 自选股卡片（结论先行）
- **journey-hero** / **journey-timeline** — Cockpit 日程导航
- **ui-render.js** — 客户端 render SSOT（与 generator 结构对齐）
- **filter-bar** — 搜索 / 信号筛选 / 排序
- **app/cockpit.html** — 单页主入口（今日/自选/我的）
- **app/stock.html** — 单股详情（query `?code=`）
- **app/watchlist.html** — 自选管理

## 静动混合（Phase C + G）

- 静态：`docs/data/latest.json` + digest/recommendation/review JSON
- 动态：`cockpit.js` + `live.js` + FastAPI 轮询
- 主入口：`app/cockpit.html`（旧 digest/live 等 redirect stub）
- 空态 / unavailable / stale 须有明确文案

## Do / Don't

**Do**：结论先行、风险优先、token 一致、移动端 375px+、免责声明可见  
**Don't**：CDN 外链、页面 inline style 漂移、必涨必买措辞、黑色纯底
