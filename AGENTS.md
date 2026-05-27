---
name: stock-copilot
category: fintech
description: A股辅助决策系统 — product-orchestrator 自主构建入口
version: 1.4.0
updated: 2026-05-27
---

# Stock Copilot — Agent 项目指令

## 项目目标

**Stock Copilot（智策）** 全链路：采集 A 股数据 → AI 分析 → 静态/动态 Web → GitHub Pages + FastAPI。

**定位**：个人研究工具，非投顾、不自动下单、不承诺收益。

## 执行入口

1. **Skill**：`product-orchestrator`（ttmens-skills）
2. **状态 SSOT**：`docs/design/08-CURRENT-STATUS.md`
3. **工作流状态**：`docs/workflow_state.yaml`（断点续跑）
4. **视觉 SSOT**：`docs/DESIGN.md` ↔ `src/site/theme.css`

按 orchestrator 三里程碑门禁（G1 调研 / G2 设计 / G3 UI 验收）推进；棕地默认 **phase-increment** 模式。

历史 Hermes Phase 0–9 见 `docs/design/archive/09-HERMES-AUTONOMOUS-BUILD.md`（已归档，勿作现行入口）。

## 文档索引

| 文档 | 用途 |
|------|------|
| `docs/design/08-CURRENT-STATUS.md` | **现行系统状态 SSOT** |
| `docs/DECISIONS.md` | 架构决策记录 |
| `docs/DESIGN.md` | **视觉 / token SSOT** |
| `docs/workflow_state.yaml` | Agent 工作流断点 |
| `docs/design/01-DESIGN.md` | 整体方案 & 演进路线 |
| `docs/design/02-MVP-SPEC.md` | MVP 功能边界 & 验收标准 |
| `docs/design/09-UI-PRODUCT.md` | Web UI 产品说明 |
| `docs/design/14-PHASE-C-PLAN.md` | Phase C 交付与验收 |
| `docs/RUNBOOK.md` | 运维 |
| `docs/design/archive/` | 历史文档（Hermes、Phase B 等） |

## 验证原则

```bash
python -m pytest tests/ -q
python scripts/self_check.py --quick
python scripts/check_docs_ssot.py --project-root .
python scripts/ui_acceptance.py --quick   # UI 改动时
python scripts/ui_acceptance.py --full    # Phase Ship / G3 前
```

- 每个 Phase 计划必须含 **functional / ux / ops** 三域验收
- UI 大改：保存 `docs/archive/YYYY-MM-DD-pre.html` 与 `-post.html`
- 架构变更写入 `docs/DECISIONS.md`

## 技术约束

- Python 3.11+，FastAPI + APScheduler + AkShare + OpenAI 兼容 LLM
- 静态站：单文件 `theme.css`，**零 CDN / 无 Tailwind**（见 DECISIONS.md）
- 禁止：自动实盘、用户登录、LangGraph、对外投顾承诺

## 合规

每份报告含固定免责声明（`docs/design/02-MVP-SPEC.md` §6.1）。LLM 禁止编造数据；无数据时 `unavailable`。
