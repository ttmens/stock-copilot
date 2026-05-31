# 智策 NexStrat 交互视觉优化计划

## 审计发现的问题

### 🔴 严重问题
1. **308 个 inline styles** — 违反 DESIGN.md 约束，维护性差
2. **信号图例文本显示异常** — 审计脚本检测为空，需验证
3. **无标题层级 (h1/h2/h3)** — 语义化和可访问性问题

### 🟡 中等问题
4. **无空态/加载态** — 筛选无结果、数据加载时无反馈
5. **表格排序/对比面板 JS 分散** — 部分在 HTML 内联，部分缺失
6. **底部导航 active 状态** — 仅首页有，其他页面缺失

### 🟢 轻微问题
7. **CSS 重复定义** — 8 个 selector 出现 3+ 次
8. **hover/focus 状态不完整** — 部分交互元素缺少状态

## 优化目标

参考 Linear.app、Sentry 等专业设计系统：
- **减少 inline styles** → 移到 CSS 类
- **完善交互反馈** → hover/focus/active/empty/loading
- **标题语义化** → 添加 h1/h2/h3
- **统一导航状态** → 所有页面 active 一致
- **优化表格交互** → 排序、对比面板功能完整

## 执行步骤

### Step 1: 修复信号图例
- 验证图例文本显示
- 确保颜色 dot 正确

### Step 2: 减少 inline styles
- 将重复的 inline style 提取为 CSS 类
- 目标：从 308 降至 100 以下

### Step 3: 添加标题层级
- index.html: h1 产品名，h2 章节标题
- dashboard.html: h1 页面标题
- history.html: h1 页面标题

### Step 4: 完善交互状态
- 添加空态 (empty state)
- 添加加载态 (loading state)
- 完善 hover/focus 样式

### Step 5: 统一导航
- 确保所有页面底部导航 active 正确
- 顶部导航 active 一致

### Step 6: 表格/对比功能
- 确保排序功能完整
- 确保对比面板功能完整

## 验收标准

- `self_check.py`: 63/63
- `deep_check.py`: 25/25
- `ui_acceptance.py --full`: 100/100
- `check_docs_ssot.py`: PASS
- inline styles < 100
