# Code Smells — Stock Copilot 代码异味清单

## 🔴 Critical（必须重构）

### CS-01: 巨型文件 — generator.py (1819行)
- **位置**: `src/site/generator.py`
- **问题**: 混合数据转换 (`_analysis_to_stock_dict`) + HTML 模板 (内联 Jinja2) + 文件 I/O + 站点生成
- **影响**: 不可测试、不可维护、改一处牵全身
- **建议**: 拆为 `site/data_transform.py` + `site/templates/*.html` + `site/builder.py`

### CS-02: 巨型文件 — db_manager.py (1278行)
- **位置**: `src/data/db_manager.py`
- **问题**: 所有表操作集中（stock_meta, signals, signal_stats, recommendation_pool, theses, postmortems...），无 Repository 分层
- **影响**: 职责不清、测试困难、并发风险
- **建议**: 拆为 `repos/stock_meta_repo.py` + `repos/signal_repo.py` + `repos/evolution_repo.py`

### CS-03: 巨型文件 — routes.py (804行)
- **位置**: `src/api/routes.py`
- **问题**: 路由定义 + 业务逻辑 + 数据访问混杂
- **影响**: 路由不可复用、业务逻辑不可测试
- **建议**: 拆为 `api/routes/*.py` (按资源) + `services/*.py` (业务逻辑)

### CS-04: 融合权重文档不一致
- **位置**: `src/data/signal_fusion.py` 第 4-6 行
- **问题**: docstring 说 "Hard signals (60%)"，实际默认权重 40%
- **影响**: 开发者误解、文档失信
- **建议**: 统一为实际值 40/25/15/10/10，并引用 `config/fusion_weights.json`

### CS-05: 硬编码泛滥
- **位置**: 多处
  - `src/data/providers/eastmoney.py`: token `fa5fd1943c7b386f172d6893dbbd1`
  - `src/data/signal_fusion.py`: 默认权重硬编码
  - `src/agents/debate.py`: prompt 模板硬编码
- **影响**: 无法配置化部署、安全风险
- **建议**: 全部移入 `config/settings.yaml` + `.env`

### CS-06: 函数属性 hack 缓存
- **位置**: `src/data/signal_fusion.py` 第 28-54 行
- **问题**: `_get_optimized_weights._cache` 用函数属性做缓存
- **影响**: 不可测试、不可 mock、线程不安全
- **建议**: 用 `@lru_cache` 或 `@cached` 装饰器

---

## 🟡 Major（应该重构）

### CS-07: 辩论 prompt 重复
- **位置**: `src/agents/debate.py` 第 22-80 行
- **问题**: 三个 debate prompt 几乎一样，仅角色名不同
- **影响**: 维护成本高、改一处需改三处
- **建议**: 提取模板 `DEBATE_PROMPT_TEMPLATE.format(role=..., focus=...)`

### CS-08: SQLite 无迁移机制
- **位置**: `src/data/db_manager.py` 第 28-100 行
- **问题**: `CREATE TABLE IF NOT EXISTS` 手动管理 schema
- **影响**: 无法安全升级 schema、无回滚能力
- **建议**: 引入 `alembic` 或轻量 `schema_version` 表 + 迁移脚本

### CS-09: Evolution 引擎开环
- **位置**: `src/evolution/engine.py`
- **问题**: `auto_mutate_watchlist=false`, `auto_apply_weights=false`, `market_regime="unknown"` 占位符
- **影响**: 自进化名存实亡，从未真正自适应
- **建议**: 实现 postmortem → 权重建议 → 人工确认 → 自动应用闭环

### CS-10: dict 传递关键数据
- **位置**: 全链路
- **问题**: `StockSnapshot` → `AgentResult` → `FusedSignal` 大量裸 dict
- **影响**: 无类型检查、运行时才发现错误
- **建议**: 全链路 Pydantic v2 模型，禁止 dict 传递核心数据

### CS-11: 无数据源健康监控
- **位置**: `src/data/fetcher.py` + `src/data/providers/*.py`
- **问题**: 降级链工作但无追踪（哪个源成功/失败/延迟）
- **影响**: 数据质量问题不可见
- **建议**: 引入 `DataSourceHealth` 模型，记录每次调用的源/状态/延迟

---

## 🟢 Minor（可以延后）

### CS-12: cockpit.js 全局状态
- **位置**: `src/site/app/cockpit.js`
- **问题**: 588 行 IIFE，全局变量 `currentSession`, `poolCache`, `reviewCache`
- **影响**: 状态管理混乱、难调试
- **建议**: 重构为 ES modules + 简单状态管理

### CS-13: 无结构化日志
- **位置**: 全项目
- **问题**: `logger.info("xxx")` 纯文本
- **影响**: 无法接入可观测性平台
- **建议**: 引入 `structlog` 或 JSON 格式日志

### CS-14: 无 CI/CD
- **位置**: 项目根目录
- **问题**: 无 `.github/workflows/`
- **影响**: 质量无保障
- **建议**: GitHub Actions 自动 pytest + ruff + build

### CS-15: 测试覆盖盲区
- **位置**: `tests/`
- **问题**: evolution、site generator、debate 模块测试薄弱
- **影响**: 重构风险高
- **建议**: 补充 ≥20 测试覆盖重构模块

---

## 重构优先级矩阵

| 优先级 | 异味编号 | 预期工作量 | 依赖 |
|--------|---------|-----------|------|
| **P0** | CS-01~06 | 3-5 天 | 无 |
| **P1** | CS-07~11 | 2-3 天 | P0 |
| **P2** | CS-12~15 | 2-3 天 | P1 |

**总计**: 7-11 天（单人全职）
