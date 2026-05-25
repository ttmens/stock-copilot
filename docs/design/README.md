# Stock Copilot 文档索引

## 项目状态

- **仓库**: https://github.com/ttmens/stock-copilot
- **分支**: main
- **版本**: 1.2.0
- **最后更新**: 2026-05-25
- **Phase A**: ✅ 完成（三层信号融合 + SQLite 持久化）
- **Phase B**: ✅ 完成（龙虎榜 + 公告关键词提取 + 5层融合 + UI 重构 + 自检脚本）
- **线上站点**: https://ttmens.github.io/stock-copilot/
- **测试**: 36/36 通过
- **自检**: 45/46 项通过（1 个东财 502 为已知网络限制）

## 给 Hermes Agent — 自主构建模式

> **注意**：Phase 0-9 已全部完成，本文档当前状态为 **运维/迭代模式**。

1. 读 `AGENTS.md`（项目根）
2. 读 **`09-HERMES-AUTONOMOUS-BUILD.md`**（自主构建主指令，已标记为交付完成）
3. 系统实现状态参照 `08-HERMES-TASK.md`（v1.0.0，Phase 0-9 全记录）
4. 新增/修改功能后运行自检：`python scripts/self_check.py`

## 文档列表

| # | 文件 | 状态 | 最后更新 | 说明 |
|---|------|------|---------|------|
| 01 | [01-DESIGN.md](01-DESIGN.md) | ✅ 已更新 | 2026-05-25 | 整体方案（含 Phase A/B 演进路线） |
| 02 | [02-MVP-SPEC.md](02-MVP-SPEC.md) | ✅ 已更新 | 2026-05-24 | MVP 功能规格 |
| 03 | [03-ARCHITECTURE.md](03-ARCHITECTURE.md) | ✅ 已更新 | 2026-05-25 | 模块架构（4 Agent + 5层融合 + 信号引擎） |
| 04 | [04-DATA-SCHEMA.md](04-DATA-SCHEMA.md) | ✅ 已更新 | 2026-05-25 | 数据模型（含 announcement 扩展） |
| 05 | [05-API-SPEC.md](05-API-SPEC.md) | ✅ 已确认 | 2026-05-24 | REST API（5 个端点） |
| 06 | [06-AGENT-PROMPTS.md](06-AGENT-PROMPTS.md) | ✅ 已更新 | 2026-05-24 | LLM Prompt（多 Provider） |
| 07 | [07-AKSHARE-INTERFACES.md](07-AKSHARE-INTERFACES.md) | ✅ 已更新 | 2026-05-24 | 数据源 & 多源 Provider |
| 08 | [08-HERMES-TASK.md](08-HERMES-TASK.md) | ✅ 已更新 | 2026-05-24 | 实现状态总览（Phase 0-9） |
| 09 | **[09-HERMES-AUTONOMOUS-BUILD.md](09-HERMES-AUTONOMOUS-BUILD.md)** | ✅ 已交付 | 2026-05-24 | 自主构建主指令（v2.0.0） |
| 10 | [10-WEB-UI-DESIGN.md](10-WEB-UI-DESIGN.md) | ✅ 已确认 | 2026-05-25 | 网页 UI/UX 规范（5层面板 + 龙虎榜/公告） |
| 11 | [11-PHASE-B-RESEARCH.md](11-PHASE-B-RESEARCH.md) | 📋 研究 | 2026-05-24 | Phase B 前期调研 |
| 12 | [12-PHASE-B-PLAN.md](12-PHASE-B-PLAN.md) | ✅ 已实施 | 2026-05-24 | Phase B 实施方案（B1-B8） |
| 13 | **[13-CURRENT-STATUS.md](13-CURRENT-STATUS.md)** | ✅ 新增 | 2026-05-25 | **当前系统状态（综合设计文档）** |

## 快速参考

### 系统架构
```
采集 (AkShare/Eastmoney/Sina/Tencent) → 硬信号 (5因子) → 4 Agent (LLM) → 5层融合 → 报告 → 静态站点 → GitHub Pages
                                                          ↓
                                                    企微/邮件通知
                                                          ↓
                                                  APScheduler 定时调度
                                                          ↓
                                                  SignalDB (SQLite 持久化)
```

### 常用命令
```bash
# 分析
python -m src.main analyze --type pre [--publish]

# 启动 API
python -m src.main serve

# 启动调度
python -m src.main schedule

# 系统自检
python scripts/self_check.py [--quick] [--fix]

# 测试
pytest tests/ -v
```

### 信号融合（5层架构）
```
最终评分 = 硬信号(40%) + 软信号(25%) + 门控(15%) + 龙虎榜(10%) + 公告(10%)
```
- 动态权重：数据不可用时自动重新分配
- 置信度 = 层间一致性 + 信号强度 + 数据完整度

### LLM 配置
- Primary: DeepSeek `deepseek-v4-flash` (api.deepseek.com)
- Fallback: DashScope `qwen3.6-plus` (coding.dashscope.aliyuncs.com/v1)
- 模式: fallback（可切换为 concurrent）

### 数据源降级链
- K 线: AkShare → Sina → Tencent
- 估值: Eastmoney push2 → Tencent
- 资金流: Eastmoney → AkShare
- 龙虎榜: Eastmoney datacenter
