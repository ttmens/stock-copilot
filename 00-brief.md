# 00-brief — Stock Copilot (智策) 深度重构

## 产品原始意图

**一句话**: AI 驱动的 A 股个人投研助手 — 看全、看懂、及时提醒

**核心价值**: 将分散的行情/公告/资金/估值数据，通过 4 个 LLM Agent + 5 层信号融合，转化为结构化决策参考，以静态网页 + 企微推送交付。

**目标用户**: 有炒股经验、追求决策效率的个人投资者（当前自用）

**边界**: 不构成投资建议、不自动下单、不对外投顾

## 当前状态

- **版本**: v3.0.0-alpha (Phase G)
- **代码量**: ~12,777 行 Python + HTML/JS/CSS
- **测试**: 116 passed ✅
- **功能**: MVP + Phase A~G 全部实现
- **部署**: GitHub Pages (静态) + FastAPI (动态 Live Cockpit)

## 重构动因（用户不满意点）

### 1. 代码质量 — 巨型文件、职责混乱
| 文件 | 行数 | 问题 |
|------|------|------|
| `src/site/generator.py` | 1819 | 混合数据转换 + HTML 模板 + Jinja2 渲染，86KB 单文件 |
| `src/data/db_manager.py` | 1278 | 所有表操作集中，无 Repository 分层 |
| `src/api/routes.py` | 804 | 路由 + 业务逻辑 + 数据访问混杂 |
| `src/agents/debate.py` | 362 | 三个 debate prompt 几乎一样，大量重复 |

### 2. 架构问题 — 伪分层、真耦合
- **SQLite 单文件承载 10+ 表**，无迁移机制（手动 CREATE TABLE IF NOT EXISTS）
- **Evolution 引擎是开环的**: `auto_mutate=false`, `auto_apply=false`，`market_regime="unknown"` 占位符从未实现
- **5 层融合权重文档不一致**: docstring 说 60/30/10，实际默认 40/25/15/10/10
- **硬编码泛滥**: Eastmoney token `fa5fd1943c7b386f172d6893dbbd1` 直接写在代码里
- **函数属性 hack**: `_get_optimized_weights._cache` 用函数属性做缓存

### 3. 产品/UX 问题 — 双轨割裂
- **静态 Pages vs Live Cockpit** 概念好但实现割裂，数据同步靠轮询
- **cockpit.js** 588 行 IIFE，全局状态管理混乱
- **无错误边界**: API 失败时 UI 降级逻辑不清晰
- **移动端**: 仅 CSS 适配，交互未优化

### 4. 缺失能力
- **无数据质量监控**: 数据源成功率、延迟无追踪
- **无用户反馈闭环**: 用户看到报告后无法标记"准/不准"
- **无 A/B 测试**: 无法对比不同融合权重效果
- **Postmortem 是单向的**: 记录信号但从不反向修正融合权重

### 5. 工程问题
- **无 CI/CD**: 无 GitHub Actions 自动测试
- **无类型检查**: 大量 `dict` 传递，无 Pydantic 严格校验
- **无日志结构化**: `logger.info` 纯文本，无法接入可观测性平台
- **测试覆盖盲区**: evolution、site generator、debate 模块测试薄弱

## 重构目标（MVP 范围）

### P0 — 必须完成
1. **代码分层重构**: 拆巨型文件，引入 Repository/Service 层
2. **数据模型严格化**: 全链路 Pydantic v2 校验，消除 dict 传递
3. **融合引擎修正**: 统一权重文档，引入可观测性（每层得分可追溯）
4. **配置外部化**: 消灭硬编码（Eastmoney token、API URL 等）
5. **基础 CI**: GitHub Actions 自动 pytest + lint

### P1 — 应该完成
6. **Evolution 闭环**: postmortem → 权重建议 → 人工确认 → 自动应用
7. **数据源健康监控**: 成功率/延迟追踪 + 告警
8. **用户反馈机制**: 报告页增加"准/不准"按钮，数据入库
9. **API 分层**: routes → service → repository 三层

### P2 — 可以延后
10. **前端重构**: cockpit.js → 模块化 + 状态管理
11. **移动端交互优化**
12. **A/B 测试框架**

## 约束
- **必须保持向后兼容**: 现有 API 端点、数据格式、GitHub Pages 产物不变
- **116 测试必须继续通过**: 重构不破坏现有功能
- **不引入重型框架**: 保持 FastAPI + SQLite 轻量栈
- **简体中文**: 所有产物与界面文案

## 非目标
- 不重写数据采集层（AkShare/Eastmoney 降级链已稳定）
- 不替换 LLM 框架（保持 OpenAI 兼容接口）
- 不做多租户/用户系统
- 不做实时 WebSocket 推送（保持轮询）
- 不做回测/模拟盘（Phase 3 范围）

## 成功指标
1. 最大单文件 < 500 行（当前 generator.py 1819 行）
2. 全链路 Pydantic 模型覆盖，0 处裸 dict 传递关键数据
3. 融合 5 层得分 100% 可追溯（每层输入/输出/权重可查）
4. 116 测试继续通过 + 新增 ≥20 测试覆盖重构模块
5. GitHub Actions CI 跑通（lint + test + build）
