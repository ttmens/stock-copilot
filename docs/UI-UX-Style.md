# UI / UX 视觉设计规范

> 本文档提取自 `assets/site-chrome.css`、`assets/brief-page.css`、`assets/anmunuo-theme.css`，供新页面、子应用或外部项目复用全站统一风格。

---

## 一、设计语言

**暗色主题 · 深空科技感情报平台**

- 深蓝底色 + 紫/青/蓝三色渐变，毛玻璃质感面板
- 大圆角卡片，层级分明的信息密度
- 整体风格接近 Linear / Vercel Dark，但不使用纯黑
- 品牌色为**紫色**（`#7b3ff2`），非红色

---

## 二、快速接入

新建 HTML 页面时，在 `<head>` 引入：

```html
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<link rel="stylesheet" href="./assets/site-chrome.css">
<link rel="stylesheet" href="./assets/anmunuo-theme.css">
```

`<body>` 推荐样式：

```html
<body style="
  margin: 0;
  background-color: var(--canvas-deep);
  color: var(--ink);
  font-family: Circular, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', sans-serif;
  font-size: 14px;
  line-height: 1.43;
  background-image: var(--page-bg-gradient);
">
```

---

## 三、色彩系统

### 3.1 品牌色


| 用途           | 变量                | 色值                         | 说明                |
| ------------ | ----------------- | -------------------------- | ----------------- |
| **主强调（CTA）** | `--rausch`        | `#7b3ff2`                  | 紫色按钮、活跃态          |
| **强调激活**     | `--rausch-active` | `#4a5bff`                  | hover / active 切换 |
| **紫色点缀**     | `--rausch-tint`   | `rgba(123, 63, 242, 0.22)` | 半透明装饰             |
| **暖色辅助**     | `--accent-warm`   | `#ff6b6b`                  | 警告 / 高亮           |


### 3.2 品牌渐变

```css
--gradient-brand: linear-gradient(90deg, #7b3ff2 0%, #4a5bff 50%, #00f5ff 100%);
```

用于 Logo 装饰、节点色标等。

### 3.3 辅助色


| 变量                | 色值        | 用途            |
| ----------------- | --------- | ------------- |
| `--accent-cyan`   | `#00f5ff` | 焦点环、链接、HUD 指示 |
| `--accent-blue`   | `#4a5bff` | 节点色、图表色       |
| `--accent-purple` | `#7b3ff2` | 节点色、分区标题      |


### 3.4 文本色


| 层级       | 变量                            | 色值                          |
| -------- | ----------------------------- | --------------------------- |
| 主文本 / 标题 | `--ink` / `--text-primary`    | `#ffffff`                   |
| 正文       | `--body-ink`                  | `rgba(255, 255, 255, 0.86)` |
| 次要 / 辅助  | `--muted` / `--text-tertiary` | `rgba(255, 255, 255, 0.65)` |
| 更弱       | `--muted-soft`                | `rgba(255, 255, 255, 0.5)`  |


### 3.5 表面色（面板/卡片背景）


| 层级       | 变量                        | 色值               |
| -------- | ------------------------- | ---------------- |
| 页面最深底    | `--canvas-deep`           | `#0a1628`        |
| 主画布 / 面板 | `--canvas` / `--panel-bg` | `#1a2742`        |
| 软表面（次层）  | `--surface-soft`          | `#0f1f3a`        |
| 强表面（最深）  | `--surface-strong`        | `--canvas-deep`  |
| 抬升表面     | `--surface-elevated`      | `--canvas`       |
| 交替表面     | `--surface-elevated-alt`  | `--surface-soft` |


### 3.6 边框色


| 层级   | 变量                              | 色值                          |
| ---- | ------------------------------- | --------------------------- |
| 常规   | `--hairline` / `--border-solid` | `rgba(255, 255, 255, 0.14)` |
| 弱边框  | `--hairline-soft`               | `rgba(255, 255, 255, 0.08)` |
| 强调边框 | `--border-strong`               | `rgba(255, 255, 255, 0.22)` |


### 3.7 阴影

```css
--shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.35);
--shadow-md: 0 6px 20px rgba(0, 0, 0, 0.45);
--shadow-lg: 0 16px 48px rgba(0, 0, 0, 0.55);
```

### 3.8 页面背景渐变

```css
--page-bg-gradient:
  radial-gradient(ellipse 120% 90% at 0% -10%, rgba(123, 63, 242, 0.18), transparent 52%),
  radial-gradient(ellipse 90% 70% at 100% 0%, rgba(0, 245, 255, 0.1), transparent 48%);
```

### 3.9 简报页支柱颜色（四大分类色标）

```css
--pillar-cap:  #58a6ff;  /* 蓝色 — 技术能力 */
--pillar-pat:  #3fb950;  /* 绿色 — 产品模式 */
--pillar-eco:  #a371f7;  /* 紫色 — 工具生态 */
--pillar-bus:  #f0883e;  /* 橙色 — 商业趋势 */
```

---

## 四、圆角规范


| 变量              | 值        | 用途              |
| --------------- | -------- | --------------- |
| `--radius-sm`   | `8px`    | 按钮、小控件          |
| `--radius-md`   | `14px`   | 卡片、面板、订阅面板      |
| `--radius-lg`   | `20px`   | 底部抽屉（探索页）       |
| `--radius-full` | `9999px` | Pill 按钮、标签、导航滑块 |


---

## 五、字体系统

```css
font-family: Circular, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto,
             'Helvetica Neue', sans-serif;
```

**字号层级**：


| 字号     | 字重                               | 用途         |
| ------ | -------------------------------- | ---------- |
| `24px` | `700`, `letter-spacing: -0.03em` | 页面主标题      |
| `18px` | `600`                            | 分区标题       |
| `16px` | `600`                            | 面板/侧栏标题    |
| `15px` | `400`, `line-height: 1.58`       | 正文段落       |
| `14px` | `600`                            | 按钮文字、正文    |
| `13px` | `400`                            | 说明、空状态描述   |
| `12px` | `500`                            | 标签、元数据、日期  |
| `11px` | `400` / `500`                    | 时间戳、统计 HUD |
| `10px` | `600`                            | 底部 Tab 标签  |


**等宽字体**（统计 / 代码块）：

```css
font-family: ui-monospace, "Cascadia Code", monospace;
```

---

## 六、毛玻璃组件

### 6.1 顶栏（Header）

```css
#header.site-chrome-header {
  position: fixed;
  top: 0; left: 0; right: 0;
  min-height: var(--header-h);  /* 64px */
  padding: calc(var(--safe-top) + 12px) max(20px, var(--safe-right)) 12px max(20px, var(--safe-left));
  background: rgba(10, 22, 40, 0.92);
  backdrop-filter: blur(16px) saturate(1.1);
  border-bottom: 1px solid var(--hairline-soft);
  box-shadow: 0 1px 0 rgba(0, 245, 255, 0.06);
  z-index: 102;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
```

### 6.2 底部 Tab 栏（窄屏）

```css
.mobile-tab-bar {
  position: fixed;
  bottom: 0; left: 0; right: 0;
  background: rgba(255, 255, 255, 0.96);  /* 窄屏为亮色 */
  backdrop-filter: blur(16px) saturate(1.1);
  border-top: 1px solid var(--hairline-soft);
  box-shadow: 0 -1px 8px rgba(0, 0, 0, 0.06);
  z-index: 101;
}
```

### 6.3 订阅面板

```css
.subscribe-panel {
  position: absolute;
  background: var(--canvas);
  backdrop-filter: blur(12px) saturate(1.08);
  border: 1px solid var(--hairline-soft);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-lg);
}
```

---

## 七、按钮样式

### 7.1 主按钮（FAB / CTA）

```css
.nex-agent-fab {
  background: var(--rausch);         /* #7b3ff2 */
  color: #fff;
  border-radius: var(--radius-full);
  padding: 0 18px;
  min-height: 48px;
  font-size: 14px; font-weight: 700;
  box-shadow: var(--shadow-lg);
}
```

### 7.2 次按钮（顶栏白底按钮）

```css
.header-btn {
  background: var(--canvas);
  color: var(--ink);
  border: 1px solid var(--hairline);
  border-radius: var(--radius-sm);
  padding: 10px 18px;
  min-height: 44px;
  font-size: 14px; font-weight: 600;
  box-shadow: var(--shadow-sm);
}
.header-btn:hover {
  background: var(--surface-soft);
  border-color: var(--border-strong);
}
```

### 7.3 Pill 导航（分段控制器）

```css
.site-nav {
  background: var(--nav-track-bg);
  border: 1px solid var(--nav-track-border);
  border-radius: var(--radius-full);
  padding: var(--site-nav-pad);
}
.site-nav-link {
  padding: 5px 12px;
  border-radius: var(--radius-full);
  font-size: 12px; font-weight: 600;
  color: var(--muted);
  transition: background 0.18s, color 0.18s, box-shadow 0.18s;
}
.site-nav-link[aria-current="page"] {
  background: var(--chrome-pill-glass);
  color: var(--ink);
  box-shadow: 0 1px 0 rgba(0, 245, 255, 0.1), var(--shadow-sm);
}
```

### 7.4 焦点环

```css
--chrome-focus-ring: 0 0 0 2px var(--canvas-deep), 0 0 0 4px var(--accent-cyan);
```

所有可聚焦元素 `:focus-visible` 时使用。

---

## 八、卡片与信息容器

### 8.1 叙事卡片（Narrative Card）

```css
.narr-card {
  border: 1px solid var(--hairline-soft);
  border-radius: 14px;
  background: var(--canvas);
  padding: 16px 18px 14px;
}
```

### 8.2 洞察折叠面板

```css
.insight-acc summary {
  font-size: 13px; font-weight: 600;
  color: var(--muted);
  padding: 8px 0;
  border-top: 1px dashed var(--hairline-soft);
}
```

### 8.3 标签/芯片

```css
.narr-pill {
  background: var(--surface-soft);
  color: var(--muted);
  border-radius: 14px;
  font-size: 11px; font-weight: 500;
  padding: 4px 10px;
}
```

---

## 九、页面布局

### 9.1 内容壳（简报页）

```css
.brief-shell {
  max-width: 860px;
  margin: 0 auto;
  padding: calc(var(--header-h, 64px) + 24px) 20px 120px;
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
}
```

### 9.2 侧栏面板（Agent/探索详情）

```css
.nex-agent-panel {
  position: fixed;
  top: 0; right: 0;
  width: min(420px, 100vw - 40px);
  height: 100dvh;
  background: var(--canvas);
  z-index: 240;
  box-shadow: var(--shadow-lg);
  transform: translateX(100%);
  transition: transform 0.28s cubic-bezier(0.4, 0, 0.2, 1);
}
```

### 9.3 遮罩（Scrim）

```css
.nex-agent-scrim {
  position: fixed; inset: 0;
  background: rgba(0, 0, 0, 0.35);
  z-index: 230;
}
```

---

## 十、动画与过渡


| 组件       | 时长               | 缓动                             |
| -------- | ---------------- | ------------------------------ |
| 面板滑入/滑出  | `0.28s`          | `cubic-bezier(0.4, 0, 0.2, 1)` |
| 按钮 hover | `0.15s`          | `ease`                         |
| 导航滑块     | `0.18s`          | `ease`                         |
| 订阅面板     | `0.2s`           | `ease`                         |
| 打字指示点    | `1.4s` 循环        | —                              |
| 光标闪烁     | `1s step-end` 循环 | —                              |


**减少动效**：

```css
@media (prefers-reduced-motion: reduce) {
  transition: none;
  animation-duration: 0.01ms !important;
  transition-duration: 0.01ms !important;
}
```

**View Transition API**：

```css
@view-transition { navigation: auto; }
```

---

## 十一、响应式断点


| 断点               | 行为                              |
| ---------------- | ------------------------------- |
| `≥ 901px`（桌面）    | 单行顶栏，内容壳居中，FAB 显示，侧栏 420px      |
| `≤ 900px`（手机）    | 隐藏顶部 nav pill，显示底部 3-tab，面板全屏覆盖 |
| `≤ 768px`（小屏）    | 气泡消息 90% 宽                      |
| `≤ 600px`（极小屏）   | 面板 100vw                        |
| `901–1240px`（中屏） | GitHub Star/Fork 按钮隐藏 count 文字  |


---

## 十二、安全区域

```css
--safe-top: env(safe-area-inset-top, 0px);
--safe-right: env(safe-area-inset-right, 0px);
--safe-bottom: env(safe-area-inset-bottom, 0px);
--safe-left: env(safe-area-inset-left, 0px);
```

所有固定定位元素（顶栏、底栏、面板）需预留 safe-area padding。

---

## 十三、语义化组件清单


| 组件         | 类名                                             |
| ---------- | ---------------------------------------------- |
| 顶栏         | `#header.site-chrome-header`                   |
| 品牌区        | `.header-brand-scroll` / `.header-brand-block` |
| 导航 pills   | `.site-nav` / `.site-nav-link`                 |
| 顶栏控制区      | `#header-controls`                             |
| 顶栏按钮       | `.header-btn`                                  |
| 问 AI 入口    | `.header-agent-btn`                            |
| 订阅按钮       | `#header-subscribe-btn`                        |
| 订阅面板       | `.subscribe-panel`                             |
| 节点统计 HUD   | `#stats`                                       |
| GitHub 按钮组 | `.github-btn-group` / `.github-btn`            |
| FAB        | `.nex-agent-fab`                               |
| 底部 Tab     | `.mobile-tab-bar` / `.mobile-tab-item`         |
| 侧栏面板       | `.nex-agent-panel`                             |
| 遮罩         | `.nex-agent-scrim`                             |
| 内容壳        | `.brief-shell`                                 |
| 叙事卡片       | `.narr-card`                                   |
| 洞察折叠       | `.insight-acc`                                 |
| 标签         | `.narr-pill`                                   |


---

## 十四、新页面 checklist

- 引入 `site-chrome.css` + `anmunuo-theme.css`
- `<body>` 使用 `var(--canvas-deep)` 底色 + `var(--page-bg-gradient)` 渐变
- 固定顶栏使用 `backdrop-filter: blur(16px) saturate(1.1)`
- 卡片使用 `var(--canvas)` + `border-radius: 14px` + `1px solid var(--hairline-soft)`
- 按钮 hover 使用 `0.15s` 过渡
- 可聚焦元素 `:focus-visible` 使用 `--chrome-focus-ring`
- 字号使用 `14px` 正文，`24px` 主标题
- 响应式：`max-width: 900px` 隐藏顶栏 nav pill
- 尊重 `@media (prefers-reduced-motion: reduce)`
- 固定元素使用 `env(safe-area-inset-*)`

---

*文档版本 1.0 · 2026-05-25 · 提取自 NexSight 代码仓库*