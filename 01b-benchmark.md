# 01b-benchmark — 业界量化投研 AI 工具最佳实践

## 1. FinDebate (2025) — 多 Agent 安全辩论

**来源**: arXiv:2509.17395v1, 西交利物浦 + 上交

**架构**:
- 5 个专业 Agent（盈利/市场/情绪/估值/风险）并行分析
- 3 个辩论 Agent（信任/怀疑/领导）单轮精炼
- Safe Debate Protocol: 禁止改变方向性结论，仅补充/质疑

**可借鉴**:
- **单轮辩论 > 多轮**: 避免主题漂移，Stock Copilot 当前 2 轮可精简为 1 轮
- **Trust/Skeptic 分离**: 比 Stock Copilot 的"互相看结论"更结构化
- **共识评分**: FinDebate 的 consensus_score 可作为 confidence 加成因子

**差距**: Stock Copilot 辩论 prompt 重复度高，缺少安全约束（可能翻转结论）

---

## 2. Microsoft Qlib — AI 量化平台

**来源**: github.com/microsoft/qlib (15k+ stars)

**架构**:
- Data Server: 高性能二进制存储 + 表达式引擎
- Model Zoo: LightGBM/LSTM/Transformer 等 20+ 模型
- Workflow Engine: YAML 配置驱动的端到端流水线
- RL Framework: 连续决策建模

**可借鉴**:
- **Expression Engine**: `Ref($close, -5) / $close - 1` 声明式因子定义
- **Workflow Config**: YAML 驱动，可复现、可对比实验
- **Adaptive Models**: 在线学习应对市场动态变化

**差距**: Stock Copilot 因子硬编码在 `hard_signals.py`，无表达式引擎；权重静态配置

---

## 3. Seeking Alpha Quant Rating

**来源**: seekingalpha.com

**架构**:
- 5 维度评分: Value / Growth / Profitability / Momentum / Revision
- 每维度 0-100 分，加权合成 Quant Grade (A+ to F)
- 完全透明: 每个因子的百分位排名可查

**可借鉴**:
- **因子可追溯**: 用户可看到每个维度的具体因子和排名
- **分级标签**: A+/A/A-/B+/.../F 比 bullish/bearish 更精细
- **历史胜率**: 每只股票的 Quant Rating 历史命中率可查

**差距**: Stock Copilot 5 层得分不透明，用户看不到底层因子

---

## 4. TradingView Technical Ratings

**来源**: tradingview.com

**架构**:
- 多时间框架: 1m / 5m / 15m / 1h / 4h / 1d / 1W
- 指标分类: Oscillators (RSI/MACD/Stoch) + Moving Averages (MA/EMA/ICHIMOKU)
- 综合评级: Buy / Neutral / Sell + 强度条

**可借鉴**:
- **多时间框架**: 同一指标在不同周期的信号一致性
- **可视化强度条**: 直观展示 Buy/Sell 强度
- **实时更新**: WebSocket 推送，非轮询

**差距**: Stock Copilot 仅日线级别，无多时间框架交叉验证

---

## 5. 富途牛牛 / 同花顺

**架构**: 商业产品，不公开技术细节

**可借鉴 UX**:
- **决策卡片**: 一图胜千言，关键指标突出
- **资金流向**: 主力/北向/散户分层展示
- **龙虎榜**: 机构席位 + 买卖金额 + 历史胜率
- **新闻情绪**: NLP 标注正面/负面，时间线展示

**差距**: Stock Copilot UI 信息密度高但层次不清晰，移动端体验差

---

## 6. 重构建议汇总（按优先级）

### P0 — 必须完成

| # | 建议 | 来源 | 预期收益 |
|---|------|------|----------|
| 1 | **融合引擎可观测性**: 每层输入/输出/权重 100% 可追溯 | Seeking Alpha | 用户信任度↑，调试效率↑ |
| 2 | **单轮安全辩论**: 引入 Trust/Skeptic 约束，禁止翻转结论 | FinDebate | 分析稳定性↑，token 成本↓50% |
| 3 | **Repository 分层**: db_manager.py 拆为 StockMetaRepo/SignalRepo/... | Qlib | 可测试性↑，代码异味↓ |
| 4 | **配置外部化**: Eastmoney token / API URL / 权重 → settings.yaml | 通用 | 部署灵活性↑ |
| 5 | **CI/CD**: GitHub Actions 自动 pytest + lint + build | 通用 | 质量保障↑ |

### P1 — 应该完成

| # | 建议 | 来源 | 预期收益 |
|---|------|------|----------|
| 6 | **数据源健康监控**: 成功率/延迟追踪 + 降级告警 | Qlib Data Server | 可靠性↑ |
| 7 | **用户反馈闭环**: 报告页"准/不准"按钮 → postmortem 入库 | Seeking Alpha 胜率 | Evolution 闭环 |
| 8 | **多时间框架**: 增加 60min/周线级别信号交叉验证 | TradingView | 信号质量↑ |
| 9 | **因子表达式引擎**: 声明式因子定义，替代硬编码 | Qlib Expression | 可扩展性↑ |

### P2 — 可以延后

| # | 建议 | 来源 | 预期收益 |
|---|------|------|----------|
| 10 | **前端模块化**: cockpit.js → ES modules + 状态管理 | 通用 | 可维护性↑ |
| 11 | **WebSocket 实时推送**: 替代轮询 | TradingView | 延迟↓ |
| 12 | **A/B 测试框架**: 对比不同融合权重效果 | Qlib Workflow | 科学决策↑ |

---

## 7. 与 Stock Copilot 当前架构对比

| 维度 | Stock Copilot 现状 | 业界最佳实践 | 差距 |
|------|-------------------|-------------|------|
| **信号融合** | 5 层静态权重，不可追溯 | Seeking Alpha 因子百分位 | 🔴 高 |
| **多 Agent** | 2 轮互相看结论，可能翻转 | FinDebate 单轮安全辩论 | 🟡 中 |
| **数据存储** | SQLite 单文件，无迁移 | Qlib 二进制 + 版本管理 | 🟡 中 |
| **数据源** | 降级链但无监控 | Qlib Data Server 健康检查 | 🟡 中 |
| **UX** | 信息密度高，层次不清 | 富途决策卡片 + 强度条 | 🟡 中 |
| **自进化** | 开环（auto=false） | Qlib Adaptive Models | 🔴 高 |
| **CI/CD** | 无 | GitHub Actions 标配 | 🔴 高 |

---

**结论**: Stock Copilot 功能完整度高（Phase A-G），但工程质量（可观测性/可测试性/可维护性）与业界最佳实践差距明显。重构应优先解决 P0 的 5 项，预计 2-3 周可完成。
