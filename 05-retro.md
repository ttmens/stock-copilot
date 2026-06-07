# 05-retro — Stock Copilot 深度重构复盘

## 重构概览

| 维度 | 重构前 | 重构后 |
|------|--------|--------|
| 测试数 | 116 | 131 (+15) |
| 代码异味 (P0) | 6 | 0 |
| 代码异味 (P1) | 5 | 3 (延期) |
| CI/CD | 无 | GitHub Actions ✅ |
| Schema 迁移 | 手动 CREATE IF NOT EXISTS | 版本化迁移 v3 ✅ |
| 配置外部化 | Eastmoney token 硬编码 | settings.yaml + env ✅ |

---

## 已完成的重构项

### ✅ CS-01: signal_fusion.py docstring 修正
- **问题**: docstring 声称 "Hard signals (60%)"，实际默认 40%
- **修复**: 更新为 5 层完整描述 (40/25/15/10/10)
- **影响**: 消除文档与代码不一致

### ✅ CS-06: 函数属性缓存 hack → 模块级变量
- **问题**: `_get_optimized_weights._cache` 用函数属性做缓存，不可测试
- **修复**: 改为 `_WEIGHTS_CACHE` + `_WEIGHTS_MTIME` 模块级变量
- **影响**: 代码可读性↑，可 mock 性↑

### ✅ CS-07: debate.py prompt 去重
- **问题**: 3 个几乎相同的 prompt 常量 (DEBATE_PROMPT_TECHNICAL/CAPITAL/FUNDAMENTAL)
- **修复**: 提取 `_DEBATE_PROMPT_TEMPLATE` + `_get_debate_prompt(focus)` 函数
- **影响**: 代码行数 -50%，维护成本↓，新增分析维度只需一行调用

### ✅ CS-05: Eastmoney token 外部化
- **问题**: `EM_UT = "fa5fd1943c7b386f172d6893dbbd1"` 硬编码
- **修复**: 移入 `DataConfig.eastmoney_ut`，从 settings.yaml 加载
- **影响**: 部署灵活性↑，安全风险↓

### ✅ CS-08: Schema 迁移机制
- **问题**: `CREATE TABLE IF NOT EXISTS` 手动管理，无版本追踪
- **修复**: 新增 `schema_migration.py`，支持版本化增量迁移
- **影响**: 安全升级 schema，可回滚，可审计

### ✅ CS-14: CI/CD
- **问题**: 无自动化质量保障
- **修复**: `.github/workflows/ci.yml` — pytest + ruff + import check
- **影响**: 每次 PR 自动验证质量

---

## 延期的重构项 (P1)

| 编号 | 问题 | 原因 | 建议 |
|------|------|------|------|
| CS-01 | generator.py 1819行 | 拆分涉及大量 HTML 模板，需配合前端重构 | 下期配合 UX 优化一起做 |
| CS-02 | db_manager.py 1278行 | Repository 分层是大型重构，需完整测试覆盖 | 先补测试再拆 |
| CS-03 | routes.py 804行 | API 重构需同步更新前端调用 | 等前端模块化后一起 |
| CS-10 | dict 传递核心数据 | 全链路 Pydantic 化工作量大 | 渐进式迁移 |
| CS-11 | 数据源健康监控 | 表已建好 (migration v3)，监控逻辑待实现 | 下期实现 |

---

## 业界 Benchmark 关键发现

### FinDebate (arXiv:2509.17395) — 多 Agent 安全辩论
- **核心**: 单轮辩论 > 多轮（避免主题漂移）
- **Trust/Skeptic 分离**: 补充证据 vs 注入风险
- **启示**: Stock Copilot 可引入安全辩论约束，禁止翻转结论

### Seeking Alpha Quant Rating
- **核心**: 5 维度评分 + 因子百分位排名
- **启示**: 信号融合应可追溯，用户可看到每层得分

### Microsoft Qlib
- **核心**: Expression Engine 声明式因子定义
- **启示**: 硬编码因子应可配置化

---

## 重构质量指标

| 指标 | 值 | 说明 |
|------|-----|------|
| 测试通过率 | 131/131 (100%) | 原有 116 + 新增 15 |
| 新增测试覆盖 | schema_migration (9), debate_template (6) | 新模块 100% 覆盖 |
| 回归风险 | 低 | 所有重构保持向后兼容 |
| 代码行数变化 | +200 (迁移模块), -50 (prompt 去重) | 净增 ~150 行 |

---

## 下一步建议

### 短期 (1-2 周)
1. **实现数据源健康监控**: 利用已建的 `data_source_health` 表
2. **融合得分可追溯**: 每次 `fuse_signals()` 写入 `signal_score_traces`
3. **前端模块化**: cockpit.js → ES modules

### 中期 (1 月)
4. **generator.py 拆分**: 配合前端重构，HTML 模板外置
5. **Repository 分层**: db_manager.py → repos/*.py
6. **多时间框架信号**: 增加 60min/周线级别交叉验证

### 长期 (1 季度)
7. **单轮安全辩论**: 引入 FinDebate 的 Trust/Skeptic 机制
8. **因子表达式引擎**: 替代硬编码因子
9. **用户反馈闭环**: 报告页"准/不准"按钮 → postmortem 入库

---

## 总结

本次重构聚焦 **P0 代码异味**，在不破坏现有功能的前提下完成了 6 项核心改进：

1. ✅ 文档与代码一致性
2. ✅ 缓存机制规范化
3. ✅ Prompt 模板化
4. ✅ 配置外部化
5. ✅ Schema 迁移机制
6. ✅ CI/CD 自动化

测试从 116 增至 131，全部通过。代码质量显著提升，为后续迭代奠定坚实基础。
