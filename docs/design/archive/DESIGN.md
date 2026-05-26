---
version: alpha
name: Stock Copilot Deep Space
description: 暗色主题 · 深空科技感情报平台 — 面向 A 股个人投资者的 AI 辅助决策看板。
colors:
  primary: "#7b3ff2"
  secondary: "#4a5bff"
  tertiary: "#00f5ff"
  warm: "#ff6b6b"
  canvas-deep: "#0a1628"
  canvas: "#1a2742"
  surface-soft: "#0f1f3a"
  ink: "#ffffff"
  body-ink: "rgba(255,255,255,0.86)"
  muted: "rgba(255,255,255,0.65)"
  muted-soft: "rgba(255,255,255,0.5)"
  bullish: "#22C55E"
  bearish: "#EF4444"
  hairline: "rgba(255,255,255,0.14)"
  hairline-soft: "rgba(255,255,255,0.08)"
typography:
  h1:
    fontFamily: "Circular, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica Neue, sans-serif"
    fontSize: 24px
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "-0.03em"
  h2:
    fontFamily: "Circular, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica Neue, sans-serif"
    fontSize: 18px
    fontWeight: 600
    lineHeight: 1.3
  body:
    fontFamily: "Circular, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica Neue, sans-serif"
    fontSize: 14px
    fontWeight: 400
    lineHeight: 1.58
  label:
    fontFamily: "Circular, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica Neue, sans-serif"
    fontSize: 12px
    fontWeight: 500
  mono:
    fontFamily: "ui-monospace, Cascadia Code, monospace"
    fontSize: 13px
    fontWeight: 400
rounded:
  sm: 8px
  md: 14px
  lg: 20px
  full: 9999px
spacing:
  xs: 4px
  sm: 8px
  md: 16px
  lg: 24px
  xl: 32px
components:
  card-primary:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.body-ink}"
    rounded: "{rounded.md}"
    padding: 16px
  card-elevated:
    backgroundColor: "{colors.surface-soft}"
    textColor: "{colors.body-ink}"
    rounded: "{rounded.md}"
    padding: 12px
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "#ffffff"
    rounded: "{rounded.full}"
    padding: 12px
  button-primary-hover:
    backgroundColor: "{colors.secondary}"
    textColor: "#ffffff"
    rounded: "{rounded.full}"
    padding: 12px
---

# Stock Copilot — UI/UX 设计规范（v2）

## 竞品分析与定位

### 竞品对比

| 产品 | 定位 | 信息呈现方式 | 决策辅助 | 核心痛点 |
|------|------|-------------|---------|---------|
| 同花顺 | 大众行情软件 | 全量数据堆砌 | 技术指标公式 | 信息过载，需用户自行解读 |
| 东方财富 | 行情+社区 | 数据+股吧讨论 | 龙虎榜/研报 | 社区噪音大，信息质量参差 |
| Wind | 专业机构终端 | 专业数据+分析工具 | 量化模型 | 年费2万+，学习成本高 |
| 雪球 | 投资社区 | 用户生成内容 | 组合跟踪 | KOL质量不一，时效性差 |
| **Stock Copilot** | **AI 辅助决策** | **结论先行+证据链** | **5层信号融合** | **新品牌，需建立信任** |

### 核心竞争力

Stock Copilot 与传统产品的本质差异：

- **不是"给你所有数据"** — 而是"**我帮你看完了，这是你需要知道的**"
- **不是"社区讨论"** — 而是"**结构化分析 + 透明证据链**"
- **不是"专业终端"** — 而是"**个人投资者用得起的 AI 投研助手**"

### 如何建立用户信任

1. **透明化** — 展示每一层信号的原始数据和计算逻辑，不黑箱
2. **多源交叉验证** — 硬信号(量化) + 软信号(LLM) + 门控(规则) + 龙虎榜 + 公告
3. **置信度标注** — 不给出绝对判断，而是信号强度和置信度
4. **风险优先** — 先提示风险，再给机会
5. **可追溯** — 历史信号归档，Phase 3 引入回测验证

## 用户旅程设计

### 典型用户画像

- 有个人炒股经验，希望提升决策效率
- 每天盘前(8:30)和盘后(16:00)查看分析报告
- 关注自选股(3-10只)，不追求全市场覆盖
- 需要快速了解"今天该关注什么"

### 用户旅程（盘前场景）

```
打开页面
  ↓ 第一眼（3秒）
【市场温度】大盘涨跌 + 整体信号分布
  ↓ 第二眼（10秒）
【今日重点】按信号强度排序的自选股卡片
  信号标签(🟢🔴⚪) + 综合评分 + 一句话结论
  ↓ 第三眼（30秒）
【展开详情】点击感兴趣的股票
  5层信号分解 + 硬信号指标 + LLM分析维度
  ↓ 第四眼（1分钟）
【深度信息】龙虎榜 + 公告关键事件
  ↓
形成决策框架 → 决定今天的操作
```

### 信息层级（金字塔结构）

```
第1层：结论    — 信号标签 + 评分 + 置信度（3秒获取）
第2层：原因    — 5层信号分解 + 一句话结论（10秒理解）
第3层：证据    — 硬信号指标 + LLM分析维度（30秒验证）
第4层：上下文  — 龙虎榜 + 公告 + 历史信号（1分钟深度）
```

### 设计原则

1. **结论先行** — 每只股票卡片首屏展示信号结论
2. **渐进式披露** — 从结论 → 原因 → 证据 → 上下文，逐层展开
3. **风险优先** — 风险点用醒目颜色，优先展示
4. **透明证据** — 每个信号都有对应的原始数据支撑
5. **移动端优先** — 80%使用场景在手机上，响应式设计

## Overview

深空科技感情报平台 — 暗色主题，深蓝底色 + 紫/青/蓝三色渐变，毛玻璃质感面板。

大圆角卡片，层级分明的信息密度，整体风格接近 Linear / Vercel Dark，但不使用纯黑。

品牌色为**紫色**（`#7b3ff2`），非红色。

## Colors

- **主强调（#7b3ff2）**: 紫色 CTA 按钮、活跃态、品牌标识
- **次强调（#4a5bff）**: hover / active 切换色
- **青色点缀（#00f5ff）**: 焦点环、链接、HUD 指示
- **暖色辅助（#ff6b6b）**: 警告 / 高亮
- **看多色（#22C55E）**: 绿色，正面信号
- **看空色（#EF4444）**: 红色，负面信号
- **观望色（#94A3B8）**: 灰色，中性信号
- **深空底（#0a1628）**: 页面最深底色
- **面板色（#1a2742）**: 卡片/面板背景
- **软表面（#0f1f3a）**: 次层背景
- **边框（rgba(255,255,255,0.14)）**: 常规分隔线

## Typography

- **页面主标题**: 24px / 700 / -0.03em
- **分区标题**: 18px / 600
- **正文**: 14px / 400 / 1.58行高
- **标签/元数据**: 12px / 500
- **数值/等宽**: 13px / ui-monospace

字体栈: Circular → -apple-system → Segoe UI → Roboto → sans-serif

## Layout

- **内容壳**: max-width 860px，居中
- **卡片网格**: 桌面双列，手机单列
- **间距**: 4/8/16/24/32px 五级
- **响应式断点**: ≥901px 桌面，≤900px 手机

## Components

### 股票卡片（核心组件）

每个卡片包含：
- 头部：股票代码 + 名称 + 信号标签 + 评分
- 评分条：综合评分 + 置信度 + 5层信号分解
- 硬信号指标：5日动量 / 均线 / 量比 / PE
- LLM分析维度：技术面/基本面/资金/公告
- 龙虎榜区块（有数据时显示）
- 公告关键事件（有数据时显示）
- 风险点（有数据时显示）

### 信号标签

- 🟢 强烈看多 / 看多 → 绿色
- ⚪ 观望 → 灰色
- 🔴 看空 / 强烈看空 → 红色

### 市场温度条

显示大盘指数 + 涨跌 + 看多/看空/观望股票数量分布

## Do's and Don'ts

### Do
- ✅ 结论先行，先给信号再给证据
- ✅ 风险点用醒目颜色优先展示
- ✅ 所有信号标注置信度和来源
- ✅ 数值使用等宽字体
- ✅ 移动端优先设计

### Don't
- ❌ 堆砌数据不提炼结论
- ❌ 使用黑色背景（用深空蓝 #0a1628）
- ❌ 使用红色作为品牌色（品牌色是紫色）
- ❌ 给直接买卖建议
- ❌ 隐藏信号计算逻辑
