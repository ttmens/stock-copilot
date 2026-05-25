---
name: stock-copilot
category: fintech
description: A股辅助决策系统 — Hermes Agent 自主构建入口
version: 1.0.0
updated: 2026-05-22
---

# Stock Copilot — Hermes 项目指令

## 项目目标

在 Hermes 服务器上构建 **Stock Copilot 全链路**：

采集 A 股数据 → AI 分析 → 生成静态网页 → 发布到 GitHub Pages → 用户浏览器直接访问。

**定位**：个人研究工具，非投顾、不自动下单、不承诺收益。

## 执行入口（自主构建模式）

**主指令文档（最高优先级）**：`docs/design/09-HERMES-AUTONOMOUS-BUILD.md`

按 Phase 0 → Phase 9 自主执行，持续构建直至全链路交付。后端细节见 `08-HERMES-TASK.md`，网页 UI 见 `10-WEB-UI-DESIGN.md`。

## 文档索引

| 文档 | 用途 |
|------|------|
| `docs/design/01-DESIGN.md` | 整体方案 & 演进路线 |
| `docs/design/02-MVP-SPEC.md` | MVP 功能边界 & 验收标准 |
| `docs/design/03-ARCHITECTURE.md` | 模块划分 & 依赖关系 |
| `docs/design/04-DATA-SCHEMA.md` | Pydantic 模型定义 |
| `docs/design/05-API-SPEC.md` | FastAPI 接口 |
| `docs/design/06-AGENT-PROMPTS.md` | LLM Prompt 模板 |
| `docs/design/07-AKSHARE-INTERFACES.md` | 数据采集 & 降级链 |
| `docs/design/09-HERMES-AUTONOMOUS-BUILD.md` | **自主构建主指令（Phase 0-9）** |
| `docs/design/08-HERMES-TASK.md` | 后端实现任务（Phase 0-5） |
| `docs/design/10-WEB-UI-DESIGN.md` | 网页 UI/UX 规范 |
| `docs/design/13-CURRENT-STATUS.md` | 当前系统状态（综合设计文档） |

## 代码目录

所有代码写入项目根目录，不得写入 `docs/`。

```
stock-copilot/
├── config/           # YAML 配置 & 示例
├── src/              # Python 源码
├── tests/            # 单元测试
├── docs/
│   ├── design/       # 设计文档
│   ├── archive/      # 历史报告
│   ├── assets/       # 静态资源
│   └── data/         # 结构化数据
├── output/reports/   # 生成的报告（gitignore）
├── data/             # SQLite（gitignore）
├── requirements.txt
├── .env.example
└── README.md
```

## 技术约束

- Python 3.11+
- FastAPI + APScheduler + AkShare + DeepSeek API（OpenAI 兼容）
- 存储：SQLite + 本地 Markdown 文件
- **自主模式扩展**：静态 Web 站点 + GitHub Pages 发布（见 09、10 文档）
- **禁止**：自动实盘交易、用户登录、LangGraph、回测、QMT、Tushare 付费接口
- 后端编排用简单函数链，不用 LangGraph
- LLM：优先使用 Hermes 已配置的模型，OpenAI 兼容接口抽象

## 编码规范

- 类型注解 + Pydantic v2 模型
- 每个模块单一职责，模块间通过 `src/data/models.py` 定义的模型通信
- 配置通过 `pydantic-settings` + YAML，密钥走 `.env`
- 日志用 `logging`，不用 print
- 中文注释仅用于非 obvious 的业务逻辑
- 测试：`pytest`，至少覆盖 fetcher、report generator、pipeline

## 合规要求

每份报告必须包含固定免责声明（见 `docs/design/02-MVP-SPEC.md` §6.1）。

LLM 输出必须结构化 JSON，禁止编造未提供的数据；无数据时输出 `"status": "unavailable"`。

## 验证原则

- 按 `docs/design/09-HERMES-AUTONOMOUS-BUILD.md` Phase 0→9 顺序执行，每 Phase 验收后 commit
- 重要选型写入 `docs/DECISIONS.md`
- 遇到 AkShare 接口变更，参考 `docs/design/07-AKSHARE-INTERFACES.md` 降级链
- 最终交付：GitHub Pages 可访问 + 服务器 Cron 自动运行
