# Stock Copilot Web UI 产品说明 (Phase C)

> **视觉 SSOT**: [../UI-UX-Style.md](../UI-UX-Style.md)  
> 实现: `src/site/generator.py` + `src/site/app/` + `docs/assets/theme.css`

## Phase C 交互

- 静态 `latest.json` 首屏 + API 动态合并
- 筛选/排序（`app/app.js`）
- 单页详情 `app/stock.html?code=`
- 自选管理 `app/watchlist.html`

---

> **历史**: 以下为 Phase A/B UI 规格正文（深色 Fintech、5层面板等）

> **状态**: ✅ Phase A + Phase B 全部完成 — 深色 Fintech 主题，5层信号分解面板，龙虎榜/公告区块，响应式布局，GitHub Pages 部署  
> **实现文件**: `src/site/generator.py` (711行) + `site/assets/theme.css`  
> **线上地址**: https://ttmens.github.io/stock-copilot/

> Hermes 在 Phase 6 已选定深色 Fintech 设计系统并全站贯彻。本文档为约束与参考。

---

## 1. 产品类型与场景

| 维度 | 定义 |
|------|------|
| 产品类型 | Fintech / 投研仪表盘 / 数据密集型 |
| 使用场景 | 盘前/盘后快速浏览自选股 AI 分析结论 |
| 设备 | 桌面优先，必须支持手机（375px+） |
| 访问方式 | GitHub Pages 静态页，无后端依赖 |
| 语言 | 简体中文为主 |

---

## 2. 设计系统生成（必做）

Hermes **必须**在实现页面前，通过以下方式之一生成设计系统：

### 方式 A：ui-ux-pro-max（推荐）

```bash
python3 ~/.cursor/skills/ui-ux-pro-max/scripts/search.py \
  "fintech stock market dashboard dark professional data visualization" \
  --design-system -p "Stock Copilot"
```

将输出整理到 `stock-copilot/docs/DESIGN-SYSTEM.md`。

### 方式 B：参考成熟 Fintech Dark Dashboard 模式

若 ui-ux-pro-max 不可用，采用以下默认设计系统（写入 DESIGN-SYSTEM.md 并注明来源）：

| Token | 值 | 用途 |
|-------|-----|------|
| `--bg-primary` | `#0B1220` | 页面背景 |
| `--bg-card` | `#151E2E` | 卡片背景 |
| `--bg-elevated` | `#1C2738` | 悬浮/Header |
| `--border` | `rgba(255,255,255,0.08)` | 分割线 |
| `--text-primary` | `#E8ECF4` | 主文字 |
| `--text-secondary` | `#8892A8` | 次要文字 |
| `--accent` | `#3B82F6` | 链接、强调 |
| `--accent-glow` | `#60A5FA` | Hover |
| `--bullish` | `#22C55E` | 偏多/涨 |
| `--bearish` | `#EF4444` | 偏空/跌 |
| `--neutral` | `#94A3B8` | 中性 |
| `--warning` | `#F59E0B` | 风险提示 |

**字体**:
- 中文：`"PingFang SC", "Microsoft YaHei", system-ui, sans-serif`
- 数字/代码：`"JetBrains Mono", "SF Mono", monospace`

**圆角**: 卡片 12px，按钮 8px，标签 999px（pill）

---

## 3. 页面结构

### 3.1 index.html（首页 / 最新报告）

```
┌──────────────────────────────────────────────────┐
│ [Logo] Stock Copilot          2026-05-22 盘前 08:35│
├──────────────────────────────────────────────────┤
│ 📊 市场概览                                       │
│ 上证指数 3200.12 (+0.85%)                         │
├──────────────────────────────────────────────────┤
│ 自选股分析 (3)                                    │
│ ┌────────────────┐ ┌────────────────┐          │
│ │ 600519 贵州茅台 │ │ 000001 平安银行 │  ...     │
│ │ [中性]          │ │ [偏多]          │          │
│ │ 关注: ...       │ │ 关注: ...       │          │
│ │ 技术 | 公告 | 资金│ │ ...            │          │
│ │ ⚠ 风险: ...     │ │                 │          │
│ └────────────────┘ └────────────────┘          │
├──────────────────────────────────────────────────┤
│ 📁 历史报告                                       │
│ 2026-05-21 盘后 · 2026-05-21 盘前 · ...          │
├──────────────────────────────────────────────────┤
│ ⚠️ 免责声明（完整文本，见 02-MVP-SPEC §6.1）      │
└──────────────────────────────────────────────────┘
```

### 3.2 archive/{date}-{type}.html

与首页结构相同，内容为历史快照。可复用同一模板。

---

## 4. 组件规范

### 4.1 股票卡片（Stock Card）

- 顶部：代码 + 名称 + sentiment 标签（bullish/bearish/neutral 配色）
- 中部：`overall_focus` 一句话
- 三维 Tab 或折叠区：技术面 / 公告 / 资金
- 底部：risk_points 列表（warning 色）
- 数据 unavailable 时显示灰色「暂无数据」，不用空白

### 4.2 Sentiment 标签

| sentiment | 背景 | 文字 |
|-----------|------|------|
| bullish | `rgba(34,197,94,0.15)` | `#22C55E` |
| bearish | `rgba(239,68,68,0.15)` | `#EF4444` |
| neutral | `rgba(148,163,184,0.15)` | `#94A3B8` |

### 4.3 免责声明条

- 固定在页脚或首屏下方
- 背景 `--bg-elevated`，左边框 `--warning` 4px
- 文字不可小于 13px
- **内容与 02-MVP-SPEC §6.1 完全一致**

### 4.4 历史报告列表

- 时间倒序
- 链接到 `archive/` 下对应 HTML
- 当前最新报告在首页，archive 仅历史

---

## 5. UX 准则

| 准则 | 要求 |
|------|------|
| 首屏 3 秒 | 用户应看到：日期、报告类型、至少 1 只股票卡片 |
| 信息密度 | 数据密集型，但卡片间距 ≥ 16px，不拥挤 |
| 可读性 | 正文 ≥ 14px，行高 ≥ 1.6 |
| 对比度 | 文字与背景对比度 ≥ WCAG AA |
| 无 JS 降级 | 核心内容 SSR/静态写入 HTML；JS 仅用于增强（折叠、搜索） |
| 加载 | 无外部 CDN 依赖（GitHub Pages 国内访问考虑）；CSS/JS 本地化 |
| 图表 | MVP 可选；若做，用 CSS 条形/纯 SVG，不用重型 chart 库 |

---

## 6. 技术实现约束

```
site/
├── index.html              # 最新报告（generator 输出）
├── archive/
│   └── YYYY-MM-DD-{pre|post}.html
├── assets/
│   ├── theme.css           # 设计 token + 组件样式（唯一样式源）
│   └── app.js              # 可选：折叠、搜索
├── data/
│   └── latest.json         # 机器可读最新报告
└── template.html           # Jinja2 模板（generator 用，可不发布）
```

**禁止**:
- 每个 HTML 页面写不同 inline style
- 引入 Tailwind CDN / 大型 UI 框架（增加体积与加载风险）
- 页面间风格不一致

**推荐**:
- 单一 `theme.css`，用 CSS 变量
- Generator 将 JSON 渲染为静态 HTML（F_aiRadar 模板注入模式）

---

## 7. 参考项目

| 项目 | 借鉴点 |
|------|--------|
| F_aiRadar (anmunuo) | 模板+数据分离、GitHub Pages、深色主题 |
| ui-ux-pro-max | 设计系统生成 workflow |
| Bloomberg / 同花顺 | 信息密度与 fintech 语感（仅参考布局，不抄品牌色） |

---

## 8. 验收标准（Phase 6-7）

- [ ] `DESIGN-SYSTEM.md` 已创建，含完整 token
- [ ] 所有页面共用 `theme.css`
- [ ] 桌面 1280px 与手机 375px 均可读
- [ ] 免责声明可见且文案正确
- [ ] sentiment 颜色语义一致
- [ ] 无数据状态有明确提示
- [ ] Lighthouse 性能：首屏无阻塞外部请求
