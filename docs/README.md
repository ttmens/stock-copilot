# Stock Copilot 文档索引

> 产品版本 **v1.4.0 (Phase C)** | 更新 2026-05-26

## 角色导航

| 角色 | 文档 |
|------|------|
| 运维 / 部署 | [RUNBOOK.md](RUNBOOK.md) |
| 架构 | [C4-ARCHITECTURE.md](C4-ARCHITECTURE.md)、[design/03-ARCHITECTURE.md](design/03-ARCHITECTURE.md) |
| 产品 / 需求 | [design/01-DESIGN.md](design/01-DESIGN.md)、[design/02-MVP-SPEC.md](design/02-MVP-SPEC.md) |
| 现行状态 SSOT | [design/08-CURRENT-STATUS.md](design/08-CURRENT-STATUS.md) |
| API | [design/05-API-SPEC.md](design/05-API-SPEC.md) |
| UI 视觉 SSOT | [DESIGN.md](DESIGN.md) |
| Agent 工作流 | [workflow_state.yaml](workflow_state.yaml) |
| Phase C 交付 | [design/14-PHASE-C-PLAN.md](design/14-PHASE-C-PLAN.md) |
| 决策记录 | [DECISIONS.md](DECISIONS.md) |

## GitHub Pages（静态发布）

根目录 `index.html`、`data/latest.json`、`app/` 为 **GitHub Pages 发布产物**，由服务端 Full 流水线导出后 push。

- **静态**：盘前/盘后快照、`latest.json`、页面壳
- **动态**：自选 CRUD、任务状态、盘中报价 — 需连接 FastAPI（`python -m src.main run`）

本地开发 API 时，在 `docs/app/config.js` 设置：

```javascript
window.STOCK_COPILOT = { API_BASE: "http://127.0.0.1:8000" };
```

## 设计文档目录

见 [design/README.md](design/README.md)。历史 Hermes / Phase B 文档已移至 [design/archive/](design/archive/)。

## 维护规则

1. 现行状态只维护 `design/08-CURRENT-STATUS.md`
2. 禁止在测试/自检中写入 `docs/data/latest.json`
3. 架构变更同步 `C4-ARCHITECTURE.md`、`03-ARCHITECTURE.md`、`DECISIONS.md`
