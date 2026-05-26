# Stock Copilot 设计文档索引

> **版本 v1.4.0 (Phase C)** | 更新 2026-05-26

## 项目状态

- **仓库**: https://github.com/ttmens/stock-copilot
- **线上站点**: https://ttmens.github.io/stock-copilot/
- **Phase A/B**: ✅ 完成
- **Phase C**: ✅ 静动分离 + 自选 API + Fast/Full + 文档 v1.4
- **现行状态 SSOT**: [08-CURRENT-STATUS.md](08-CURRENT-STATUS.md)

## 文档列表

| # | 文件 | 说明 |
|---|------|------|
| 01 | [01-DESIGN.md](01-DESIGN.md) | 整体方案与演进路线 |
| 02 | [02-MVP-SPEC.md](02-MVP-SPEC.md) | MVP 功能规格 |
| 03 | [03-ARCHITECTURE.md](03-ARCHITECTURE.md) | 模块架构（数据/分析/交付平面） |
| 04 | [04-DATA-SCHEMA.md](04-DATA-SCHEMA.md) | 数据模型与 SQLite 表 |
| 05 | [05-API-SPEC.md](05-API-SPEC.md) | REST API（含 watchlist/jobs） |
| 06 | [06-AGENT-PROMPTS.md](06-AGENT-PROMPTS.md) | LLM Prompt |
| 07 | [07-DATA-SOURCES.md](07-DATA-SOURCES.md) | 数据源与 Provider |
| 08 | **[08-CURRENT-STATUS.md](08-CURRENT-STATUS.md)** | **现行系统状态 SSOT** |
| 09 | [09-UI-PRODUCT.md](09-UI-PRODUCT.md) | Web UI 产品说明（视觉见 `../UI-UX-Style.md`） |
| 14 | [14-PHASE-C-PLAN.md](14-PHASE-C-PLAN.md) | Phase C 交付与验收 |

### 历史文档（archive/）

Hermes 构建指令、Phase B 研究/计划、旧版 DESIGN token 等已移至 [archive/](archive/)，不再维护。

## 常用命令（v1.4）

```bash
python -m src.main run          # 生产：scheduler + API 单进程
python -m src.main analyze --type pre [--publish]
python -m src.main fast       # 盘中 Fast（无 LLM）
python -m src.main serve
pytest tests/ -v
```

## 架构概要

```
SQLite (中枢) ← 采集/分析/进化
     ├─ Full → site/docs + git push (静态)
     └─ Fast → intraday_quotes + API (动态)

GitHub Pages: latest.json + app/ 壳 → 运行时拉 API
```
