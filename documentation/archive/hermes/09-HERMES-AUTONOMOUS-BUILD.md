---
name: stock-copilot-autonomous-build
version: 2.0.0
updated: 2026-05-24 (全链路交付完成)
mode: autonomous
priority: master-instruction
---

# Hermes 自主构建主指令 — Stock Copilot 全链路

> **本文档优先级高于 `08-HERMES-TASK.md`**。在自主构建模式下，Hermes 应持续执行直至全链路交付完成，而非仅完成 MVP 后端。

---

## 0. 使命陈述（Mission）

你要在 **Hermes 服务器**（如 `/home/ubuntu`）上，从零构建并持续运维 **Stock Copilot**：

1. **采集** A 股自选股数据（AkShare）
2. **处理** 清洗、结构化、持久化
3. **分析** 调用 Hermes 已配置的大模型能力（优先使用本机/已接入的 LLM，不强制 DeepSeek）
4. **发布** 将分析结果生成静态站点，推送到 **GitHub 仓库**
5. **访问** 用户打开 GitHub Pages URL 即可看到统一 UI/UX 的网页报告

**工作方式**：自主洞察、自主选型、自主排障、自主迭代，直到全部验收通过。

---

## 1. 启动 Prompt（用户复制给 Hermes）

```
你是 Hermes Agent，请对 Stock Copilot 项目执行「自主构建模式」。

【必读】
1. tx-cloud/AGENTS.md
2. docs/stock-copilot/09-HERMES-AUTONOMOUS-BUILD.md（本文档，最高优先级）
3. docs/stock-copilot/08-HERMES-TASK.md（Phase 0-5 后端实现）
4. docs/stock-copilot/10-WEB-UI-DESIGN.md（网页 UI/UX 规范）

【使命】
在 Hermes 服务器上完成：数据采集 → AI 分析 → 静态网页生成 → 推送到 GitHub → GitHub Pages 可访问。

【自主权限】
- 你可以根据实际情况调整实现细节、库选型、目录结构，但必须写入 stock-copilot/docs/DECISIONS.md 并说明理由
- 遇到阻塞时：先查文档 → 尝试备选方案 → 记录问题 → 继续推进，不要停下来等用户
- LLM：优先使用 Hermes 已配置的模型/API；若无 DeepSeek，用 OpenRouter/Anthropic/本地 Ollama 等已接入能力
- 设计：按 10-WEB-UI-DESIGN.md，用 ui-ux-pro-max 或等价方法选定设计系统，全站统一

【禁止】
- 不要实现自动实盘交易
- 不要删除免责声明
- 不要提交 .env、API Key 到 GitHub
- 不要对外宣称投顾/保证收益

【执行】
从 Phase 0 开始，按本文档 Phase 0→9 顺序执行。每 Phase 验收通过后 commit 并 push（若 remote 已配置）。全部 Phase 完成后输出交付报告（仓库 URL、Pages URL、Cron 状态）。

现在开始 Phase 0。
```

---

## 2. 文档阅读顺序

| 顺序 | 文档 | 用途 |
|------|------|------|
| 1 | `AGENTS.md` | 项目入口 |
| 2 | **本文档** | 自主构建总控 |
| 3 | `08-HERMES-TASK.md` | 后端 Phase 0-5 细节 |
| 4 | `10-WEB-UI-DESIGN.md` | 网页设计规范 |
| 5 | `01-DESIGN.md` ~ `07-AKSHARE-INTERFACES.md` | 按需查阅 |
| 6 | `stock-copilot/docs/DECISIONS.md` | 自行维护的决策日志 |

---

## 3. 自主构建原则

### 3.1 洞察与选型

遇到技术选型时，按以下优先级决策：

1. **文档已有明确规定** → 遵循文档
2. **文档未规定** → 选择最简单、可维护、与现有栈一致的方案
3. **方案阻塞** → 尝试备选，记录到 `DECISIONS.md`，继续推进

**记录格式**（`stock-copilot/docs/DECISIONS.md`）：

```markdown
## YYYY-MM-DD — 决策标题
- **背景**: ...
- **备选**: A / B / C
- **选择**: B
- **理由**: ...
- **影响**: ...
```

### 3.2 LLM 使用策略

```
优先级:
1. Hermes 环境变量 / config 中已配置的 LLM Provider
2. OpenAI 兼容端点（DeepSeek、OpenRouter、Azure 等）
3. 本地 Ollama（若可用且质量可接受）

要求:
- 在 settings 中抽象 LLM 配置，不硬编码单一厂商
- Agent 层只依赖 OpenAI SDK 兼容接口
- 在 README 说明如何切换模型
```

### 3.3 服务器运行环境

- **工作目录**: `{PROJECT_ROOT}/stock-copilot/`（PROJECT_ROOT 为 tx-cloud 克隆路径）
- **Python**: 3.11+，建议 venv：`stock-copilot/.venv`
- **Cron**: 使用 Hermes Cron 或系统 crontab / APScheduler 常驻
- **密钥**: `~/.hermes/.env` 或 `stock-copilot/.env`（不入库）

### 3.4 GitHub 发布策略

参考 F_aiRadar 模式：**数据与页面分离 → 生成静态 HTML → push 到 GitHub → GitHub Pages 自动部署**

```
stock-copilot/
├── site/                      # GitHub Pages 发布目录（或 /docs）
│   ├── index.html             # 最新报告首页
│   ├── archive/               # 历史报告
│   │   └── 2026-05-22-pre.html
│   ├── assets/
│   │   ├── theme.css          # 统一主题
│   │   └── app.js             # 轻量交互（可选）
│   └── data/
│       └── latest.json        # 最新报告 JSON（供页面渲染）
```

**GitHub Pages 配置**:
- 方案 A（推荐）: 使用 `/docs` 文件夹作为 Pages 源 → 将 `site/` 内容同步到仓库根 `docs/`
- 方案 B: 使用 `gh-pages` 分支
- 在仓库 Settings → Pages 启用，记录最终 URL 到 README

---

## 4. 全链路 Phase（0 → 9）— ✅ 全部完成

### Phase 0-5: 后端 MVP ✅ 完成

**实现状态**: 全部完成并通过验收。

**实际实现**:
- **Phase 0**: 项目结构 + venv + requirements + config/settings.yaml + .env.example
- **Phase 1**: `src/data/models.py` — Pydantic v2 模型（WatchlistItem, OHLCVBar, MovingAverages, StockSnapshot, ValuationInfo, CapitalFlow, DragonTigerItem, NewsItem, Announcement, MarketOverview, StockAnalysis, Report, AgentResult, AgentStatus, ReportType）
- **Phase 2**: `src/data/fetcher.py` — 多源数据降级链采集器（AkShare → Sina → Tencent / Eastmoney → Tencent）
- **Phase 3**: `src/agents/{technical,fundamental,capital}.py` — 三维 LLM Agent（LLM 不可用时返回 unavailable）
- **Phase 4**: `src/reports/generator.py` — Markdown 报告生成（含固定免责声明）
- **Phase 5**: `src/orchestrator/pipeline.py` — 完整编排流水线（fetch → agents → report → notify）

**CLI 命令**:
```bash
python -m src.main analyze --type pre    # 盘前分析
python -m src.main analyze --type post   # 盘后分析
python -m src.main serve --port 8000     # FastAPI 服务
python -m src.main schedule              # APScheduler 常驻
```

**验收通过**:
- [x] `python -m src.main analyze --type pre` 生成 Markdown + JSON
- [x] 输出包含结构化 `latest.json`（数据契约见 §5）
- [x] 13/13 测试全部通过
- [x] 自检脚本 10 维度 46 项检查

---

### Phase 6: 设计系统选定

**任务**:
- [ ] 阅读 `10-WEB-UI-DESIGN.md`
- [ ] 使用 **ui-ux-pro-max** 或等价方法，为「A股 fintech 投研仪表盘」生成设计系统
- [ ] 将选定结果写入 `stock-copilot/docs/DESIGN-SYSTEM.md`，包含：
  - 配色（背景、卡片、强调色、涨跌色）
  - 字体
  - 间距与圆角
  - 组件规范（卡片、表格、标签、免责声明条）
- [ ] 创建 `site/assets/theme.css` 实现设计 token

**验收**:
- [ ] `DESIGN-SYSTEM.md` 存在且可执行
- [ ] 有独立 `preview.html` 或 story 页面展示组件样式

**ui-ux-pro-max 命令示例**（若 skill 可用）:
```bash
python3 ~/.cursor/skills/ui-ux-pro-max/scripts/search.py \
  "fintech stock dashboard dark professional data-dense" \
  --design-system -p "Stock Copilot"
```

---

### Phase 7: 静态站点生成器

**任务**:
- [ ] 实现 `src/site/generator.py`
  - 输入: `Report` 模型 / `latest.json`
  - 输出: `site/index.html` + `site/archive/{date}-{type}.html` + `site/data/latest.json`
- [ ] 实现 `site/template.html`（或 Jinja2 模板）
  - 首页：最新简报摘要 + 自选股卡片列表
  - 个股卡片：代码、名称、综合 sentiment、三维结论、风险点
  - 市场概览区（若有）
  - 固定免责声明（页脚，不可省略）
  - 历史报告链接列表
- [ ] pipeline 完成后自动调用 site generator
- [ ] **零构建依赖**：纯 HTML + CSS + 可选原生 JS，兼容 GitHub Pages
- [ ] 移动端响应式（375px 起可读）

**页面信息架构**:

```
┌─────────────────────────────────────────┐
│ Header: Stock Copilot | 日期 | 盘前/盘后  │
├─────────────────────────────────────────┤
│ 市场概览条（指数、更新时间）              │
├─────────────────────────────────────────┤
│ 自选股卡片 Grid                          │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐   │
│  │ 600519  │ │ 000001  │ │ 300750  │   │
│  │ 技术/公告/资金 │ sentiment │ 风险 │   │
│  └─────────┘ └─────────┘ └─────────┘   │
├─────────────────────────────────────────┤
│ 历史报告 Archive 链接                     │
├─────────────────────────────────────────┤
│ 免责声明（固定）                          │
└─────────────────────────────────────────┘
```

**验收**:
```bash
python -m src.main analyze --type pre
python -m src.site.generator  # 或集成在 pipeline 内
# 本地验证
python3 -m http.server 8080 -d site
# 浏览器打开 index.html，检查布局与免责声明
```

---

### Phase 8: GitHub 仓库与 Pages 部署

**任务**:
- [ ] 初始化或关联 GitHub 仓库（用户未提供时，在 DECISIONS.md 记录待用户提供 repo URL）
- [ ] 配置 `.gitignore`：`.env`, `.venv`, `data/*.db`, 敏感配置
- [ ] 将 `site/` 同步到 GitHub Pages 源路径（`/docs` 或 `gh-pages`）
- [ ] 实现 `scripts/publish.sh` 或 `src/publish/github.py`:
  ```bash
  git add docs/ site/data/latest.json  # 按实际路径
  git commit -m "publish: report YYYY-MM-DD-pre"
  git push origin main
  ```
- [ ] pipeline 完成后可选自动 publish（Cron 任务末尾）
- [ ] README 写入 **GitHub Pages 访问 URL**

**验收**:
- [ ] `git push` 成功
- [ ] GitHub Pages 可访问（HTTP 200）
- [ ] 页面展示最新报告内容
- [ ] 免责声明可见

---

### Phase 9: 服务端 Cron 与运维闭环

**任务**:
- [ ] 配置 Hermes Cron 或 crontab:
  - 盘前 08:30 CST: `analyze --type pre` → generate site → publish
  - 盘后 16:00 CST: `analyze --type post` → generate site → publish
  - 非交易日跳过
- [ ] 实现 `scripts/health_check.sh`：检查最近 24h 是否成功生成报告
- [ ] 失败时：日志 + 可选企微告警（若配置了 webhook）
- [ ] 编写 `stock-copilot/docs/RUNBOOK.md` 运维手册

**验收**:
- [ ] Cron 任务已注册（`hermes cron list` 或 crontab -l）
- [ ] 手动触发一次完整链路：采集 → 分析 → 站点 → push → Pages 可访问
- [ ] RUNBOOK.md 含故障排查步骤

---

## 5. 数据契约 — latest.json

站点与 pipeline 通过此 JSON 解耦：

```json
{
  "meta": {
    "report_type": "pre",
    "trade_date": "2026-05-22",
    "generated_at": "2026-05-22T08:35:00+08:00",
    "symbol_count": 3,
    "disclaimer": "⚠️ 本报告仅供个人研究参考，不构成投资建议..."
  },
  "market": {
    "index_name": "上证指数",
    "close": 3200.12,
    "change_pct": 0.85
  },
  "stocks": [
    {
      "code": "600519",
      "name": "贵州茅台",
      "overall_sentiment": "neutral",
      "overall_focus": "放量突破 MA20",
      "technical": { "status": "ok", "summary": "...", "sentiment": "bullish" },
      "fundamental": { "status": "ok", "summary": "...", "sentiment": "neutral" },
      "capital": { "status": "unavailable", "summary": "数据暂不可用", "sentiment": "neutral" },
      "risk_points": ["估值偏高"]
    }
  ],
  "failed_symbols": [],
  "archive": [
    { "date": "2026-05-21", "type": "post", "url": "archive/2026-05-21-post.html" }
  ]
}
```

---

## 6. 最终交付清单（Definition of Done — 全链路）

- [ ] Phase 0-9 全部验收通过
- [ ] 服务器 Cron 自动运行
- [ ] GitHub 仓库有最新代码和站点文件
- [ ] GitHub Pages URL 可公开访问（或私有 repo + 用户已知 URL）
- [ ] 页面 UI 符合 `DESIGN-SYSTEM.md`，全站风格统一
- [ ] 每份报告含免责声明
- [ ] `DECISIONS.md` 记录所有重要选型
- [ ] `RUNBOOK.md` 运维文档完整
- [ ] 交付报告包含：
  - 仓库 URL
  - Pages URL
  - Cron 配置摘要
  - LLM 使用的 Provider/Model
  - 已知限制与后续建议

---

## 7. 自主排障指南

| 现象 | 处理 |
|------|------|
| AkShare 接口失败 | 07-AKSHARE-INTERFACES.md 降级链；单股失败不阻塞 |
| LLM 不可用 | 切换 Provider；降级为规则摘要（标注 AI 不可用） |
| Git push 失败 | 检查 token/SSH；先本地 commit，记录待重试 |
| Pages 404 | 检查 Settings 源路径；确认 index.html 在正确目录 |
| 样式不一致 | 回查 DESIGN-SYSTEM.md，禁止页面内联随意配色 |
| 不确定是否 in scope | 优先完成 §6 交付清单；扩展功能记入 DECISIONS.md 待用户确认 |

---

## 8. 与用户沟通

**仅在以下情况暂停并询问用户**:
1. 需要 GitHub 仓库 URL / deploy token（未在环境变量中）
2. 需要确认 GitHub Pages 使用 public 还是 private
3. 连续 3 次相同步骤失败且无备选方案

**其他情况**: 自主决策，写入 DECISIONS.md，继续执行。

---

## 9. 范围扩展说明（相对 02-MVP-SPEC）

自主构建模式 **扩展** 原 MVP Out-of-Scope 中的以下项：

| 原 Out-of-Scope | 自主模式 |
|-----------------|----------|
| Web UI | ✅ Phase 7 必做（静态站点） |
| Docker/K8s | ❌ 仍不做（Cron + venv 足够） |
| 自动交易 | ❌ 仍不做 |
| LangGraph | ❌ 仍不做（除非 DECISIONS.md 论证必要） |
