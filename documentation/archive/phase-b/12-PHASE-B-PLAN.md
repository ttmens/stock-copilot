# Phase B 实施方案

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** 升级 Stock Copilot 的信息挖掘和交互方式，实现真正有价值的决策辅助。

**Architecture:** 
- 信息挖掘：新增龙虎榜、公告关键词提取，重构 LLM Prompt 为信息提取模式
- 信号融合：升级融合引擎，新增龙虎榜因子和事件因子
- 交互方式：采用金字塔结构，信号强度排序，可展开卡片

**Tech Stack:** Python, AkShare, LLM API, Jinja2, CSS

---

### Task B1: 新增龙虎榜数据获取

**Objective:** 从东方财富获取龙虎榜数据，解析机构买卖信息

**Files:**
- Create: `src/data/providers/dragon_tiger.py`
- Modify: `src/data/fetcher.py` (新增龙虎榜获取方法)
- Test: `tests/data/test_dragon_tiger.py`

**Step 1: 创建龙虎榜 Provider**

```python
"""Dragon & Tiger list (龙虎榜) data provider."""

import logging
import httpx
from typing import Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class DragonTigerProvider:
    """Fetch dragon & tiger list data from Eastmoney."""
    
    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.client = httpx.Client(timeout=timeout, follow_redirects=True)
    
    def get_stock_dragon_tiger(
        self, 
        code: str, 
        days: int = 5
    ) -> Optional[dict]:
        """Get dragon & tiger list for a stock.
        
        Returns:
            {
                "code": "600519",
                "name": "贵州茅台",
                "entries": [
                    {
                        "date": "2026-05-24",
                        "reason": "连续三个交易日内，涨幅偏离值累计达到 20% 的证券",
                        "net_buy": 123456789.0,  # 净买入额
                        "buy_amount": 234567890.0,
                        "sell_amount": 111111101.0,
                        "participants": [
                            {"name": "机构专用", "buy": 100000000, "sell": 0},
                            {"name": "沪股通", "buy": 50000000, "sell": 30000000},
                        ]
                    }
                ]
            }
        """
        # Eastmoney dragon & tiger API
        url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
        params = {
            "reportName": "RPT_DAILYBILLBOARD_DETAILSNEW",
            "columns": "ALL",
            "filter": f'(SECURITY_CODE="{code}")',
            "pageNumber": "1",
            "pageSize": str(days),
            "sortColumns": "TRADE_DATE",
            "sortTypes": "-1",
            "source": "WEB",
            "client": "WEB",
        }
        
        try:
            resp = self.client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            
            if not data.get("success") or not data.get("result", {}).get("data"):
                return None
            
            entries = []
            for item in data["result"]["data"]:
                entry = {
                    "date": item.get("TRADE_DATE", ""),
                    "reason": item.get("EXPLAIN", ""),
                    "net_buy": float(item.get("NET_BUY_AMT", 0) or 0),
                    "buy_amount": float(item.get("TOTAL_BUY_AMT", 0) or 0),
                    "sell_amount": float(item.get("TOTAL_SELL_AMT", 0) or 0),
                    "participants": []
                }
                
                # Parse participants if available
                # This depends on the API response structure
                entries.append(entry)
            
            return {
                "code": code,
                "entries": entries
            }
            
        except Exception as e:
            logger.warning(f"Dragon tiger fetch failed for {code}: {e}")
            return None
```

**Step 2: 集成到 Fetcher**

在 `src/data/fetcher.py` 中添加：
```python
from src.data.providers.dragon_tiger import DragonTigerProvider

class DataFetcher:
    def __init__(self, ...):
        ...
        self.dragon_tiger = DragonTigerProvider()
    
    def fetch_dragon_tiger(self, code: str, days: int = 5) -> Optional[dict]:
        return self.dragon_tiger.get_stock_dragon_tiger(code, days)
```

**Step 3: 创建测试**

```python
def test_dragon_tiger_fetch():
    """Test dragon tiger data fetch."""
    provider = DragonTigerProvider()
    result = provider.get_stock_dragon_tiger("600519", days=5)
    # May return None if no dragon tiger data
    if result:
        assert "code" in result
        assert "entries" in result
        assert isinstance(result["entries"], list)
```

**Step 4: Run tests**

Run: `pytest tests/data/test_dragon_tiger.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/data/providers/dragon_tiger.py src/data/fetcher.py tests/data/test_dragon_tiger.py
git commit -m "feat: add dragon tiger list data provider"
```

---

### Task B2: 公告关键词提取

**Objective:** 使用 LLM 从公告标题/摘要中提取关键词和情绪

**Files:**
- Create: `src/agents/announcement.py`
- Modify: `src/agents/__init__.py`
- Test: `tests/agents/test_announcement.py`

**Step 1: 创建 Announcement Agent**

```python
"""Announcement analysis agent - extracts key events from announcements."""

import logging
import json
from typing import Optional
from src.agents.base import BaseAgent
from src.data.models import AgentResult, AgentStatus

logger = logging.getLogger(__name__)

ANNOUNCEMENT_PROMPT = """你是一个专业的 A 股公告分析助手。基于以下公告标题列表，提取关键信息。

【公告列表】
{announcements}

【输出要求】（严格按 JSON 格式，不含 markdown）
{{
  "key_events": [
    {{"event": "一季度净利润同比增长 15%", "impact": "positive", "confidence": 0.85}}
  ],
  "overall_sentiment": "positive|negative|neutral",
  "summary": "一句话总结公告核心内容",
  "risk_flags": ["股东减持计划", "业绩下滑预警"]
}}

【约束】
- 仅基于提供的公告标题
- 不编造未提及的信息
- impact: positive/negative/neutral
- confidence: 0-1
- 无公告时输出 {{"key_events": [], "overall_sentiment": "neutral", "summary": "无近期公告", "risk_flags": []}}
"""

class AnnouncementAgent(BaseAgent):
    """Extract key events from stock announcements."""
    
    def analyze(self, code: str, name: str, announcements: list[str]) -> AgentResult:
        if not announcements:
            return AgentResult(
                agent_name="announcement",
                status=AgentStatus.UNAVAILABLE,
                sentiment="neutral",
                summary="无近期公告"
            )
        
        try:
            prompt = ANNOUNCEMENT_PROMPT.format(
                announcements="\n".join(f"- {a}" for a in announcements[:10])
            )
            
            response = self.llm_client.chat(prompt)
            data = json.loads(response)
            
            # Count positive vs negative events
            events = data.get("key_events", [])
            pos = sum(1 for e in events if e.get("impact") == "positive")
            neg = sum(1 for e in events if e.get("impact") == "negative")
            
            if pos > neg:
                sentiment = "bullish"
            elif neg > pos:
                sentiment = "bearish"
            else:
                sentiment = "neutral"
            
            return AgentResult(
                agent_name="announcement",
                status=AgentStatus.OK,
                sentiment=sentiment,
                summary=data.get("summary", ""),
                details={
                    "key_events": events,
                    "risk_flags": data.get("risk_flags", [])
                }
            )
            
        except Exception as e:
            logger.error(f"Announcement analysis failed for {code}: {e}")
            return AgentResult(
                agent_name="announcement",
                status=AgentStatus.ERROR,
                sentiment="neutral",
                summary=f"分析失败：{str(e)}"
            )
```

**Step 2: 更新 __init__.py**

```python
from src.agents.announcement import AnnouncementAgent

__all__ = ["TechnicalAgent", "FundamentalAgent", "CapitalAgent", "AnnouncementAgent"]
```

**Step 3: 创建测试**

```python
def test_announcement_agent():
    """Test announcement analysis."""
    agent = AnnouncementAgent(llm_client=mock_llm)
    
    announcements = [
        "贵州茅台：2026 年一季度净利润同比增长 15%",
        "贵州茅台：关于控股股东增持计划完成的公告",
    ]
    
    result = agent.analyze("600519", "贵州茅台", announcements)
    assert result.status == AgentStatus.OK
    assert result.sentiment in ["bullish", "bearish", "neutral"]
    assert "key_events" in result.details
```

**Step 4: Run tests**

Run: `pytest tests/agents/test_announcement.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/agents/announcement.py src/agents/__init__.py tests/agents/test_announcement.py
git commit -m "feat: add announcement analysis agent"
```

---

### Task B3: 重构 LLM Prompt 为信息提取模式

**Objective:** 将所有 Agent 的 Prompt 从"预测涨跌"改为"信息提取"

**Files:**
- Modify: `src/agents/technical.py`
- Modify: `src/agents/fundamental.py`
- Modify: `src/agents/capital.py`
- Modify: `docs/stock-copilot/06-AGENT-PROMPTS.md`

**Step 1: 重构 Technical Agent Prompt**

```python
TECHNICAL_PROMPT = """你是一个专业的 A 股技术面分析助手。基于以下市场数据，提取关键技术信号。

【市场数据】
- 股票代码：{code} {name}
- 当前价格：{price}
- 涨跌幅：{change}%
- 均线：MA5={ma5}, MA10={ma10}, MA20={ma20}
- 5 日涨跌幅：{mom_5d}%
- 20 日涨跌幅：{mom_20d}%
- 量比：{volume_ratio}
- 成交额：{amount}

【输出要求】（严格按 JSON 格式，不含 markdown）
{{
  "trend": "uptrend|downtrend|sideways",
  "support_level": 支撑位价格 (float),
  "resistance_level": 压力位价格 (float),
  "key_signals": [
    {{"signal": "均线多头排列", "impact": "positive"}},
    {{"signal": "量比 1.8 放量", "impact": "positive"}}
  ],
  "summary": "一句话技术面总结",
  "confidence": 0.75
}}

【约束】
- 仅基于提供的数据
- 不预测未来走势
- 无数据时标注 null
"""
```

**Step 2: 更新文档**

同步更新 `docs/stock-copilot/06-AGENT-PROMPTS.md`

**Step 3: Run tests**

Run: `pytest tests/agents/ -v`
Expected: All PASS

**Step 4: Commit**

```bash
git add src/agents/*.py docs/stock-copilot/06-AGENT-PROMPTS.md
git commit -m "refactor: update all agent prompts to information extraction mode"
```

---

### Task B4: 升级信号融合引擎

**Objective:** 新增龙虎榜因子和事件因子到信号融合

**Files:**
- Modify: `src/data/hard_signals.py`
- Modify: `src/data/signal_fusion.py`
- Test: `tests/data/test_signal_fusion.py`

**Step 1: 新增龙虎榜信号**

在 `hard_signals.py` 中添加：
```python
def _dragon_tiger_score(entries: list[dict]) -> float:
    """Score dragon tiger entries.
    
    Positive net buy = bullish, negative = bearish.
    """
    if not entries:
        return 0.0
    
    total_net = sum(e.get("net_buy", 0) for e in entries)
    # Normalize: 1 亿 = +1.0, -1 亿 = -1.0
    return max(-1.0, min(1.0, total_net / 1e8))
```

**Step 2: 更新融合引擎**

在 `signal_fusion.py` 中添加龙虎榜和公告因子：
```python
# Updated weights
DEFAULT_WEIGHTS = {
    "momentum": 0.25,
    "ma": 0.20,
    "volume": 0.10,
    "valuation": 0.10,
    "capital": 0.15,
    "dragon_tiger": 0.10,
    "announcement": 0.10,
}
```

**Step 3: 更新测试**

添加龙虎榜和公告因子的测试用例。

**Step 4: Run tests**

Run: `pytest tests/data/test_signal_fusion.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/data/hard_signals.py src/data/signal_fusion.py tests/data/test_signal_fusion.py
git commit -m "feat: upgrade signal fusion with dragon tiger and announcement factors"
```

---

### Task B5: 重构页面 UI（金字塔结构）

**Objective:** 采用金字塔结构重构页面，结论先行，渐进式披露

**Files:**
- Modify: `src/site/generator.py`
- Modify: `site/assets/theme.css`
- Create: `site/template.html` (Jinja2 模板)

**Step 1: 创建新模板**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Stock Copilot - {{ date }}</title>
  <link rel="stylesheet" href="assets/theme.css">
</head>
<body>
  <header class="header">
    <div class="logo">Stock Copilot</div>
    <div class="datetime">{{ date }} {{ report_type }}</div>
  </header>
  
  <main class="main">
    <!-- 市场温度 -->
    <section class="market-temp">
      <h2>📊 市场温度</h2>
      <div class="temp-bar">
        <div class="temp-fill" style="width: {{ market_temp }}%"></div>
      </div>
      <span class="temp-label">{{ market_temp_label }}</span>
    </section>
    
    <!-- 今日重点（按信号强度排序） -->
    <section class="focus-stocks">
      <h2>🎯 今日重点</h2>
      {% for stock in stocks|sort(attribute='final_score', reverse=true) %}
      <article class="stock-card" data-score="{{ stock.final_score }}">
        <div class="card-header">
          <span class="stock-name">{{ stock.code }} {{ stock.name }}</span>
          <span class="signal-badge signal-{{ stock.signal_class }}">
            {{ stock.signal_label }}
          </span>
        </div>
        
        <div class="signal-strength">
          <div class="strength-bar">
            <div class="strength-fill" style="width: {{ (stock.final_score + 1) * 50 }}%"></div>
          </div>
          <span class="strength-value">{{ "%.2f"|format(stock.final_score) }}</span>
        </div>
        
        <div class="key-evidence">
          <h4>关键依据</h4>
          <ul>
            {% for evidence in stock.key_evidence[:3] %}
            <li>{{ evidence }}</li>
            {% endfor %}
          </ul>
        </div>
        
        <details class="card-details">
          <summary>展开详情</summary>
          <div class="details-content">
            <!-- 详细数据 -->
          </div>
        </details>
      </article>
      {% endfor %}
    </section>
    
    <!-- 风险提示 -->
    <footer class="disclaimer">
      <p>⚠️ 本报告仅供个人研究参考，不构成投资建议...</p>
    </footer>
  </main>
</body>
</html>
```

**Step 2: 更新 CSS**

添加新的组件样式：
```css
.signal-strength {
  margin: 8px 0;
}

.strength-bar {
  height: 6px;
  background: var(--bg-elevated);
  border-radius: 3px;
  overflow: hidden;
}

.strength-fill {
  height: 100%;
  transition: width 0.3s ease;
}

.signal-bullish .strength-fill { background: var(--bullish); }
.signal-bearish .strength-fill { background: var(--bearish); }
.signal-neutral .strength-fill { background: var(--neutral); }
```

**Step 3: 更新 Generator**

修改 `generator.py` 使用新模板。

**Step 4: Run tests**

Run: `pytest tests/site/ -v`
Expected: PASS

**Step 5: Commit**

```bash
git add site/template.html site/assets/theme.css src/site/generator.py
git commit -m "feat: redesign UI with pyramid structure"
```

---

### Task B6: 新增交互组件

**Objective:** 实现信号强度条、置信度指示器、可展开卡片

**Files:**
- Modify: `site/assets/theme.css`
- Modify: `site/assets/app.js`
- Modify: `site/template.html`

**Step 1: 信号强度条**

已在 B5 中实现。

**Step 2: 置信度指示器**

```html
<div class="confidence-badge" title="置信度 {{ "%.0f"|format(stock.confidence * 100) }}%">
  <svg viewBox="0 0 36 36" class="confidence-ring">
    <path class="confidence-bg" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"/>
    <path class="confidence-fill" stroke-dasharray="{{ "%.0f"|format(stock.confidence * 100) }}, 100" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"/>
  </svg>
  <span class="confidence-text">{{ "%.0f"|format(stock.confidence * 100) }}%</span>
</div>
```

**Step 3: 可展开卡片**

使用 HTML5 `<details>` 元素，无需 JS。

**Step 4: 运行测试**

手动验证页面渲染。

**Step 5: Commit**

```bash
git add site/assets/theme.css site/assets/app.js site/template.html
git commit -m "feat: add interactive components"
```

---

### Task B7: 历史信号对比

**Objective:** 显示与昨日信号的对比（↑↓→）

**Files:**
- Modify: `src/data/db_manager.py`
- Modify: `src/site/generator.py`
- Modify: `site/template.html`

**Step 1: 数据库查询**

添加方法查询昨日信号：
```python
def get_yesterday_signal(self, code: str) -> Optional[dict]:
    """Get yesterday's fused signal for a stock."""
    # Query signals table for yesterday's record
```

**Step 2: 模板更新**

```html
<div class="signal-change">
  {% if stock.score_change > 0.1 %}
  <span class="change-up">↑ +{{ "%.2f"|format(stock.score_change) }}</span>
  {% elif stock.score_change < -0.1 %}
  <span class="change-down">↓ {{ "%.2f"|format(stock.score_change) }}</span>
  {% else %}
  <span class="change-neutral">→ {{ "%.2f"|format(stock.score_change) }}</span>
  {% endif %}
</div>
```

**Step 3: 运行测试**

Run: `pytest tests/data/test_db_manager.py -v`
Expected: PASS

**Step 4: Commit**

```bash
git add src/data/db_manager.py src/site/generator.py site/template.html
git commit -m "feat: add historical signal comparison"
```

---

### Task B8: 筛选器功能

**Objective:** 添加按信号类型/强度筛选

**Files:**
- Create: `site/assets/app.js`
- Modify: `site/template.html`

**Step 1: 筛选器 UI**

```html
<div class="filters">
  <button class="filter-btn active" data-filter="all">全部</button>
  <button class="filter-btn" data-filter="bullish">🟢 看多</button>
  <button class="filter-btn" data-filter="neutral">⚪ 观望</button>
  <button class="filter-btn" data-filter="bearish">🔴 看空</button>
</div>
```

**Step 2: JS 实现**

```javascript
document.querySelectorAll('.filter-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    const filter = btn.dataset.filter;
    document.querySelectorAll('.stock-card').forEach(card => {
      if (filter === 'all' || card.dataset.signal === filter) {
        card.style.display = '';
      } else {
        card.style.display = 'none';
      }
    });
    document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
  });
});
```

**Step 3: 运行测试**

手动验证筛选功能。

**Step 4: Commit**

```bash
git add site/assets/app.js site/template.html
git commit -m "feat: add signal filter"
```

---

### Task B9: 测试与自检

**Objective:** 运行全量测试和自检脚本

**Step 1: 运行测试**

```bash
pytest tests/ -v --tb=short
```

**Step 2: 运行自检**

```bash
python scripts/self_check.py --quick
```

**Step 3: 修复问题**

修复所有失败项。

**Step 4: 提交**

```bash
git add .
git commit -m "test: all tests passing, self-check 100%"
```

---

## 验收标准

- [ ] 龙虎榜数据正常获取并显示
- [ ] 公告提取 3-5 个关键词
- [ ] LLM 输出结构化 JSON
- [ ] 信号融合包含新因子
- [ ] 页面按信号强度排序
- [ ] 3 秒内看到核心结论
- [ ] 所有交互组件正常工作
- [ ] 自检脚本 100% 通过
- [ ] 所有测试通过
