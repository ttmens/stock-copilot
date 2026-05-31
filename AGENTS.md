---
name: stock-copilot
category: fintech
description: A股辅助决策系统 — product-orchestrator 自主构建入口
version: 3.0.0-alpha
updated: 2026-05-30
---

# Stock Copilot — Agent 项目指令

## 项目目标

**Stock Copilot（智策 NexStrat）** 全链路：采集 A 股数据 → AI 分析 → 静态/动态 Web → GitHub Pages + FastAPI。

**定位**：个人研究工具，非投顾、不自动下单、不承诺收益。

## 执行入口

1. **Skill**：`product-orchestrator`（ttmens-skills）
2. **状态 SSOT**：[`documentation/reference/current-status.md`](documentation/reference/current-status.md)
3. **版本 SSOT**：[`documentation/VERSION.md`](documentation/VERSION.md)
4. **工作流**：[`documentation/workflow_state.yaml`](documentation/workflow_state.yaml)
5. **视觉 SSOT**：[`documentation/design-system/tokens.md`](documentation/design-system/tokens.md) ↔ `src/site/theme.css`

历史 Hermes 见 [`documentation/archive/hermes/`](documentation/archive/hermes/)（只读）。

## 文档索引

| 文档 | 用途 |
|------|------|
| [`documentation/README.md`](documentation/README.md) | **文档总入口** |
| `documentation/reference/current-status.md` | 系统现状 SSOT |
| `documentation/reference/api-spec.md` | REST API |
| `documentation/explanation/roadmap.md` | 阶段路线图 |
| `documentation/guides/runbook.md` | 运维 |
| `documentation/guides/local-dev.md` | 本地开发 |
| `documentation/archive/` | 历史 Phase 计划 |

`docs/` 目录**仅** GitHub Pages 静态产物（HTML/JSON/CSS），不含设计 Markdown。

## 验证原则

```bash
python -m pytest tests/ -q
python scripts/self_check.py          # 需本地 API :8000
python scripts/check_docs_ssot.py --project-root .
python scripts/ui_acceptance.py --quick
python scripts/regenerate_docs_site.py  # 无 LLM 刷新站点
```

## 技术约束

- Python 3.11+，FastAPI + APScheduler + AkShare + OpenAI 兼容 LLM
- 单进程生产：`python -m src.main run`
- 静态站：单文件 `theme.css`，零 CDN
- 禁止：自动实盘、多租户、对外投顾承诺

## 合规

每份报告含固定免责声明（`documentation/reference/mvp-spec.md` §6.1）。
