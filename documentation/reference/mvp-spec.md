# MVP 功能规格（路线 A）

## 1. 用户故事

作为个人投资者，我希望每个交易日盘前/盘后收到自选股 AI 分析报告（Markdown + 静态网页），快速了解关注点和风险，而不必逐个打开行情软件。

## 2. In Scope

| ID | 功能 | 优先级 | 验收 |
|----|------|--------|------|
| F1 | YAML 自选股配置（5-20 只） | P0 | 改 YAML 即可增减 |
| F2 | 日线行情 + MA5/10/20 | P0 | 每只股票有 OHLCV + MA |
| F3 | 近 7 日公告标题 | P0 | 有则列出，无则标注 |
| F4 | 主力/北向资金（有则分析） | P1 | 无数据不阻塞 → unavailable |
| F5 | Technical Agent | P0 | JSON 结构化输出 |
| F6 | Fundamental Agent | P0 | JSON 结构化输出 |
| F7 | Capital Agent | P1 | 无数据 → unavailable |
| F8 | Markdown 报告生成 | P0 | 含免责声明，保存至 output/reports/ |
| F9 | 定时任务（盘前/盘后） | P0 | APScheduler Cron，非交易日跳过 |
| F10 | 推送（企微 Webhook 或 SMTP 邮件） | P0 | 二选一可配置 |
| F11 | CLI 手动触发 | P0 | `analyze --type pre\|post [--symbols CODE,CODE]` |
| F12 | FastAPI 服务 | P1 | GET /health, POST /analyze, GET /reports/latest, GET /site/latest.json |
| F13 | 静态网页生成 | P0 | Jinja2 → site/index.html，暗色金融风格 |
| F14 | 估值数据 | P1 | PE/PB/PS/市值/行业（东财 push2 → 腾讯降级） |
| F15 | 龙虎榜 | P1 | 近 5 日龙虎榜条目（东财 datacenter） |
| F16 | GitHub Pages 发布 | P1 | `analyze --publish` 自动 git commit + push docs/ |

## 3. Out of Scope（禁止实现）

- 用户登录 / 多用户
- LangGraph / 多空辩论
- 盘中实时监控 / 打板
- 回测 / 模拟盘 / QMT
- Tushare 付费数据
- 向量库 / 新闻爬虫（新闻 API 暂时禁用）
- Docker / K8s 部署

> **注意**：静态 Web 站点（Jinja2 HTML + GitHub Pages）已在 MVP 范围内，见 F13/F16。但不需要后端渲染或 SPA 框架。

## 4. 报告模板

### 4.1 Markdown 报告（output/reports/{date}-{type}.md）

```markdown
# A股自选股分析简报
**日期**: {date} | **类型**: {pre|post} | **生成时间**: {time}

> ⚠️ 本报告仅供个人研究参考，不构成投资建议。报告内容基于公开数据和 AI 分析生成，可能存在错误或遗漏。股市有风险，决策需谨慎。作者不对任何投资损失承担责任。

## 市场概览
- 上证指数: {index} ({change}%)

## 自选股分析 ({count})

### {code} {name}
**综合**: {sentiment} | **今日关注**: {focus}

| 维度 | 状态 | 结论 |
|------|------|------|
| technical | ✅/⏸️/❌ | ... |
| fundamental | ✅/⏸️/❌ | ... |
| capital | ✅/⏸️/❌ | ... |

**风险点**: ...

---
*由 Stock Copilot MVP 自动生成*
```

### 4.2 静态网页（site/index.html）

- Jinja2 模板渲染，暗色金融专业风格
- CSS 变量主题系统（--bg-primary, --accent, --bullish, --bearish 等）
- 响应式布局（grid auto-fill，移动端适配）
- 市场概览栏、股票卡片网格、历史报告归档链接
- 固定免责声明区块
- 同步至 `docs/` 目录用于 GitHub Pages

### 4.3 数据文件（site/data/latest.json）

- 供前端/网页消费的结构化 JSON
- 包含 meta、market、stocks、failed_symbols、archive 列表
- 同时通过 API `/site/latest.json` 暴露

## 5. 配置项

| 配置 | 文件 | 说明 |
|------|------|------|
| 自选股 | config/watchlist.yaml | symbols 列表 (code + name) |
| 调度/LLM/推送/数据/站点 | config/settings.yaml | 见下方完整示例 |
| 密钥 | .env | DEEPSEEK_API_KEY, DASHSCOPE_API_KEY, WECOM_WEBHOOK, GITHUB_TOKEN 等 |

### settings.yaml 完整示例

```yaml
llm:
  mode: "fallback"             # "fallback" | "concurrent"
  max_retries: 2
  providers:
    - name: "deepseek"
      base_url: "https://api.deepseek.com"
      api_key_env: "DEEPSEEK_API_KEY"
      model: "deepseek-v4-flash"
      temperature: 0.3
      max_tokens: 1024
      timeout: 60
      priority: 1
    - name: "dashscope"
      base_url: "https://coding.dashscope.aliyuncs.com/v1"
      api_key_env: "DASHSCOPE_API_KEY"
      model: "qwen3.6-plus"
      temperature: 0.3
      max_tokens: 1024
      timeout: 60
      priority: 2

schedule:
  pre_market: "08:30"
  post_market: "16:00"
  timezone: "Asia/Shanghai"

notify:
  type: "wecom"          # wecom | email
  wecom_webhook: "${WECOM_WEBHOOK}"

data:
  bar_count: 60
  announcement_days: 7
  retry: 1
  retry_delay: 1

report:
  include_market_overview: true
  output_dir: "output/reports"

site:
  output_dir: "site"
  archive_dir: "site/archive"
  data_dir: "site/data"
```

### .env.example

```
DEEPSEEK_API_KEY=sk-xxx
DASHSCOPE_API_KEY=sk-xxx

WECOM_WEBHOOK=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=***

# email 模式（可选）
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
SMTP_TO=

# GitHub 发布（可选）
GITHUB_TOKEN=ghp_xxx
```

## 6. 合规

### 6.1 固定免责声明（不可修改）

```
⚠️ 本报告仅供个人研究参考，不构成投资建议。报告内容基于公开数据和 AI 分析生成，可能存在错误或遗漏。股市有风险，决策需谨慎。作者不对任何投资损失承担责任。
```

### 6.2 LLM 约束

- 仅基于 `StockSnapshot` 中提供的数据分析
- 不得编造财务数字、公告内容、资金数据
- 无数据时必须标注「数据暂不可用」(status = "unavailable")
- SYSTEM_PROMPT 要求输出合法 JSON，不含 markdown 代码块

## 7. Definition of Done

- [ ] 10 只自选股 YAML 配置可运行
- [ ] `python -m src.main analyze --type pre` 生成完整 Markdown 报告
- [ ] 报告含免责声明 + 三维分析
- [ ] 部分数据源失败时报告仍生成（降级链）
- [ ] APScheduler 可配置盘前/盘后，非交易日跳过
- [ ] 推送渠道至少一种可用（企微 Webhook）
- [ ] 静态网页生成（site/index.html）正常渲染
- [ ] `analyze --publish` 可发布至 GitHub Pages
- [ ] FastAPI 服务启动，/health 返回 ok
- [ ] pytest 通过
