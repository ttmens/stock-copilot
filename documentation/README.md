# Stock Copilot / 智策 NexStrat — 文档索引

> 产品版本 **2.1.0** | 更新 2026-05-30  
> GitHub Pages 静态站仍在 [`docs/`](../docs/)（仅 HTML/JSON/CSS，无设计 Markdown）

本目录为 **Diátaxis** 结构的开发者与产品文档 SSOT。

## 版本与状态

| 文档 | 说明 |
|------|------|
| [VERSION.md](VERSION.md) | 单一版本号与 Phase 交付矩阵 |
| [reference/current-status.md](reference/current-status.md) | **系统现状 SSOT** |
| [workflow_state.yaml](workflow_state.yaml) | Agent 工作流断点 |

## Explanation（为什么）

| 文档 | 说明 |
|------|------|
| [product-overview.md](explanation/product-overview.md) | 产品定位与边界 |
| [roadmap.md](explanation/roadmap.md) | 阶段演进 C → F |
| [decisions/README.md](explanation/decisions/README.md) | 架构决策记录（ADR 索引） |

## Reference（是什么）

| 文档 | 说明 |
|------|------|
| [architecture.md](reference/architecture.md) | 模块架构 |
| [c4-diagrams.md](reference/c4-diagrams.md) | C4 架构图 |
| [data-schema.md](reference/data-schema.md) | 数据模型与 SQLite |
| [api-spec.md](reference/api-spec.md) | REST API 全集 |
| [data-sources.md](reference/data-sources.md) | 多源采集与降级 |
| [agent-prompts.md](reference/agent-prompts.md) | LLM Prompt |
| [mvp-spec.md](reference/mvp-spec.md) | MVP 功能规格 |
| [ui-product.md](reference/ui-product.md) | Web UI 产品说明 |

## Guides（怎么做）

| 文档 | 说明 |
|------|------|
| [runbook.md](guides/runbook.md) | 生产运维 |
| [local-dev.md](guides/local-dev.md) | 本地开发与测试 |
| [deploy-systemd.md](guides/deploy-systemd.md) | systemd 部署 |
| [ui-hybrid-setup.md](guides/ui-hybrid-setup.md) | Pages + API 静动混合 |

## Design system

| 文档 | 说明 |
|------|------|
| [tokens.md](design-system/tokens.md) | 视觉 token SSOT → `src/site/theme.css` |

## Archive（历史只读）

[archive/](archive/) — Hermes、Phase B/C/D/F 计划、旧版快照。**勿作现行入口。**

## 维护规则

1. 状态只维护 `reference/current-status.md`
2. 版本只维护 `VERSION.md`
3. 禁止在 `docs/` 下新增设计 Markdown（允许 `docs/README.md` 迁移 stub）
4. 架构变更同步 `architecture.md`、`c4-diagrams.md`、`decisions/`
5. API 变更同步 `api-spec.md`

```bash
python scripts/check_docs_ssot.py --project-root .
python -m pytest tests/ -q
```
