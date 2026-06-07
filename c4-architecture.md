# C4 Architecture — Stock Copilot (重构后目标架构)

## Level 1: Context Diagram

```mermaid
graph TB
    User[个人投资者] -->|浏览| Pages[GitHub Pages 静态站]
    User -->|接收推送| WeCom[企微 Webhook]
    User -->|手动触发| CLI[CLI 命令行]
    
    Pages -->|读取 JSON| StaticSite[静态站点产物]
    WeCom -->|推送报告| ReportService[报告生成服务]
    CLI -->|触发分析| Pipeline[分析流水线]
    
    Pipeline -->|获取行情| AkShare[AkShare / Eastmoney / Sina]
    Pipeline -->|调用 LLM| DeepSeek[DeepSeek / DashScope]
    Pipeline -->|存储信号| SQLite[(SQLite 信号库)]
    Pipeline -->|生成报告| ReportService
    ReportService -->|输出 HTML/MD| StaticSite
    Pipeline -->|发布站点| GitHub[GitHub Pages]
    
    style Pipeline fill:#e1f5fe
    style SQLite fill:#fff3e0
    style StaticSite fill:#f3e5f5
```

**说明**:
- **User**: 个人投资者（当前仅自用）
- **Pipeline**: 核心分析流水线（数据采集 → Agent 分析 → 信号融合 → 报告生成）
- **SQLite**: 信号历史 + 元数据 + 进化记录
- **StaticSite**: GitHub Pages 静态产物（HTML + JSON）

---

## Level 2: Container Diagram

```mermaid
graph TB
    subgraph "Stock Copilot System"
        CLI[CLI 入口<br/>src/main.py]
        Scheduler[调度器<br/>APScheduler]
        Pipeline[分析流水线<br/>src/orchestrator/pipeline.py]
        
        subgraph "数据层"
            Fetcher[数据采集器<br/>src/data/fetcher.py]
            Providers[数据源 Provider<br/>AkShare/Eastmoney/Sina/Tencent]
            DBManager[数据库管理<br/>src/data/db_manager.py]
        end
        
        subgraph "分析层"
            Agents[4 Agent 分析<br/>Technical/Fundamental/Capital/Announcement]
            Debate[辩论编排器<br/>src/agents/debate.py]
            Fusion[信号融合引擎<br/>src/data/signal_fusion.py]
        end
        
        subgraph "输出层"
            ReportGen[报告生成器<br/>src/reports/generator.py]
            SiteBuilder[站点构建器<br/>src/site/builder.py]
            Publisher[GitHub 发布<br/>src/publish/github_pages.py]
            Notifier[通知推送<br/>src/notify/wecom.py]
        end
        
        subgraph "进化层"
            Evolution[进化引擎<br/>src/evolution/engine.py]
            Postmortem[信号复盘<br/>src/evolution/postmortem.py]
            Optimizer[权重优化<br/>src/evolution/optimizer.py]
        end
        
        API[FastAPI 服务<br/>src/api/routes.py]
    end
    
    CLI --> Pipeline
    Scheduler --> Pipeline
    Scheduler --> Evolution
    
    Pipeline --> Fetcher
    Fetcher --> Providers
    Pipeline --> Agents
    Agents --> Debate
    Debate --> Fusion
    Fusion --> DBManager
    Pipeline --> ReportGen
    ReportGen --> SiteBuilder
    SiteBuilder --> Publisher
    
    Evolution --> Postmortem
    Postmortem --> Optimizer
    Optimizer -->|更新权重| Fusion
    
    API -->|读取| DBManager
    API -->|触发| Pipeline
    API -->|服务静态文件| SiteBuilder
    
    style Pipeline fill:#e1f5fe
    style Fusion fill:#fff3e0
    style DBManager fill:#ffebee
```

**重构重点**:
1. **Pipeline** 保持核心地位，但拆分为更细粒度的 Step
2. **DBManager** 拆为多个 Repository（StockMetaRepo / SignalRepo / EvolutionRepo）
3. **Fusion** 增加可观测性（每层得分可追溯）
4. **SiteBuilder** 从 generator.py 拆出，独立负责 HTML 生成

---

## Level 3: Component Diagram (核心模块)

### 3.1 数据层重构

```mermaid
graph LR
    subgraph "重构前"
        OldDB[db_manager.py<br/>1278行<br/>所有表操作]
    end
    
    subgraph "重构后"
        BaseRepo[base_repo.py<br/>SQLite 连接池 + 事务]
        StockMetaRepo[stock_meta_repo.py<br/>股票元数据 CRUD]
        SignalRepo[signal_repo.py<br/>信号历史查询/写入]
        EvolutionRepo[evolution_repo.py<br/>theses/postmortems]
        SchemaMigration[schema_migration.py<br/>版本化迁移]
    end
    
    OldDB -.->|拆分为| BaseRepo
    BaseRepo --> StockMetaRepo
    BaseRepo --> SignalRepo
    BaseRepo --> EvolutionRepo
    BaseRepo --> SchemaMigration
    
    style OldDB fill:#ffcdd2
    style BaseRepo fill:#c8e6c9
```

### 3.2 信号融合重构

```mermaid
graph TB
    subgraph "重构前"
        OldFusion[signal_fusion.py<br/>权重硬编码<br/>得分不可追溯]
    end
    
    subgraph "重构后"
        WeightLoader[weight_loader.py<br/>从 config 加载 + 归一化]
        LayerScorer[layer_scorer.py<br/>每层独立打分]
        FusionEngine[fusion_engine.py<br/>加权合成 + 可观测性]
        ScoreTrace[score_trace.py<br/>记录每层输入/输出/权重]
    end
    
    OldFusion -.->|拆分为| WeightLoader
    WeightLoader --> LayerScorer
    LayerScorer --> FusionEngine
    FusionEngine --> ScoreTrace
    
    ScoreTrace -->|写入| DB[(signal_score_traces 表)]
    
    style OldFusion fill:#ffcdd2
    style ScoreTrace fill:#c8e6c9
```

**新增表**: `signal_score_traces`
```sql
CREATE TABLE signal_score_traces (
    id INTEGER PRIMARY KEY,
    code TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    report_type TEXT NOT NULL,
    
    -- 每层得分
    hard_score REAL,
    hard_weight REAL,
    soft_score REAL,
    soft_weight REAL,
    gate_score REAL,
    gate_weight REAL,
    dragon_tiger_score REAL,
    dragon_tiger_weight REAL,
    announcement_score REAL,
    announcement_weight REAL,
    
    -- 最终得分
    final_score REAL,
    final_signal TEXT,
    
    -- 元数据
    weights_version TEXT,  -- 引用 fusion_weights.json 版本
    created_at TEXT DEFAULT (datetime('now'))
);
```

### 3.3 多 Agent 辩论重构

```mermaid
graph TB
    subgraph "重构前"
        OldDebate[debate.py<br/>3个重复 prompt<br/>2轮互相看结论]
    end
    
    subgraph "重构后"
        PromptTemplate[prompt_template.py<br/>单模板 + 角色参数化]
        Round1Agent[round1_analysis.py<br/>独立分析]
        SafeDebate[safe_debate.py<br/>Trust/Skeptic 单轮]
        ConsensusScorer[consensus_scorer.py<br/>共识评分]
    end
    
    OldDebate -.->|重构为| PromptTemplate
    PromptTemplate --> Round1Agent
    Round1Agent --> SafeDebate
    SafeDebate --> ConsensusScorer
    
    style OldDebate fill:#ffcdd2
    style SafeDebate fill:#c8e6c9
```

**FinDebate 启发**:
- **单轮安全辩论**: Trust Agent 补充证据，Skeptic Agent 注入风险，Leader Agent 综合
- **禁止翻转**: 辩论不改变方向性结论（bullish/bearish），仅精炼
- **共识加成**: 3 Agent 一致 → confidence +0.1；分歧 → confidence -0.1

---

## 重构实施计划

### Phase 1: 基础设施（Day 1-2）
- [ ] 引入 `alembic` 或轻量 schema migration
- [ ] 拆 `db_manager.py` → `repos/*.py`
- [ ] 配置外部化（Eastmoney token / API URL → settings.yaml）

### Phase 2: 融合引擎（Day 3-4）
- [ ] 修正 docstring（60/30/10 → 40/25/15/10/10）
- [ ] 引入 `signal_score_traces` 表
- [ ] 拆 `signal_fusion.py` → `weight_loader.py` + `layer_scorer.py` + `fusion_engine.py`

### Phase 3: Agent 辩论（Day 5）
- [ ] 提取 prompt 模板（参数化角色）
- [ ] 实现单轮安全辩论（Trust/Skeptic/Leader）
- [ ] 共识评分加成

### Phase 4: 站点生成（Day 6-7）
- [ ] 拆 `generator.py` → `data_transform.py` + `templates/*.html` + `builder.py`
- [ ] HTML 模板外置（Jinja2 文件）

### Phase 5: API 分层（Day 8）
- [ ] 拆 `routes.py` → `routes/*.py` + `services/*.py`
- [ ] 业务逻辑下沉到 Service 层

### Phase 6: CI/CD + 测试（Day 9-10）
- [ ] GitHub Actions 自动 pytest + ruff
- [ ] 补充 ≥20 测试覆盖重构模块
- [ ] 116 原有测试继续通过

**总计**: 10 天（单人全职）
