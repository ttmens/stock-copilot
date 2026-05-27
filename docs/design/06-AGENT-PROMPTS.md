# LLM Agent Prompt 模板

## 更新记录

- **2026-05-24 (v2)**: 修复 SYSTEM_PROMPT — 必须包含 "json" 小写字样（DeepSeek/DashScope 的 `json_object` response_format 强制要求）
- **2026-05-24**: 更新为多 Provider 架构（DeepSeek + DashScope），统一 SYSTEM_PROMPT，Technical Agent 改用 bars_json 格式

## 架构概览

```
src/llm/client.py          → LLMClient (多 Provider + fallback/concurrent)
src/agents/base.py         → BaseAgent (统一 LLM 调用 + 重试)
src/agents/technical.py    → TechnicalAgent (技术面分析)
src/agents/fundamental.py  → FundamentalAgent (公告/基本面分析)
src/agents/capital.py      → CapitalAgent (资金流向分析)
src/agents/announcement.py → AnnouncementAgent (公告事件分析)

Pipeline (`src/orchestrator/pipeline.py`) 并行调用 Technical / Fundamental / Capital + Announcement；
FundamentalAgent 独立 LLM 分析公告基本面，仅在 LLM unavailable 时降级复用 Announcement 结果。
```

## 通用 System Prompt

所有 Agent 使用相同的 System Prompt（定义在各自模块中）：

```
你是 A 股投研分析助手，仅基于用户提供的数据进行分析。

规则：
1. 只使用用户提供的 json 数据，不得编造任何数字、公告、资金数据
2. 数据缺失时，status 设为 "unavailable"，summary 说明缺失原因
3. 输出必须是合法 json 格式，不含 markdown 代码块
4. 不做买卖建议，不使用「必涨」「必买」等词汇
5. summary 100-200 字，focus_points 和 risk_points 各 1-3 条
```

> `LLMClient.SYSTEM_PROMPT` 中也有一份完全相同的定义，作为 fallback system prompt。

---

## Technical Agent

**模块**: `src/agents/technical.py`

**User Prompt 模板:**

```
分析以下 A 股技术面数据，输出 JSON。

股票: {code} {name}

最近20条日线 (OHLCV):
{bars_json}

均线: MA5={ma5}, MA10={ma10}, MA20={ma20}

关注: 趋势方向、均线关系（多头/空头排列）、量能变化、支撑压力位。
```

**输入数据:**

| 字段 | 来源 | 说明 |
|------|------|------|
| `code`, `name` | StockSnapshot | 股票代码和名称 |
| `bars_json` | `snapshot.bars[-20:]` | 最近 20 条 OHLCV，格式: `[{"date","open","high","low","close","volume"}, ...]` |
| `ma5/10/20` | `snapshot.ma` | 5/10/20 日均线 |

**降级处理:** 无日线数据 (`snapshot.bars` 为空) → 直接返回 `unavailable`，不调用 LLM。

---

## Fundamental Agent

**模块**: `src/agents/fundamental.py`

**User Prompt 模板:**

```
分析以下 A 股公告信息，输出 JSON。

股票: {code} {name}

近7日公告:
{announcements_json}

关注: 利好/利空/中性、业绩相关、风险事件。
无公告时 status=unavailable。
```

**输入数据:**

| 字段 | 来源 | 说明 |
|------|------|------|
| `announcements_json` | `snapshot.announcements` | 近 7 日公告，格式: `[{"title","date","url"}, ...]` |

**降级处理:** 无公告 (`snapshot.announcements` 为空) → 直接返回 `unavailable`。

---

## Capital Agent

**模块**: `src/agents/capital.py`

**User Prompt 模板:**

```
分析以下 A 股资金数据，输出 JSON。

股票: {code} {name}

资金数据:
{capital_json}

关注: 北向/主力态度、资金异常。
无数据时 status=unavailable，不要猜测。
```

**输入数据:**

| 字段 | 来源 | 说明 |
|------|------|------|
| `capital_json` | `snapshot.capital` | 资金流数据，格式: `{"north_net_inflow","main_net_inflow","period"}` |

**降级处理:** 无资金数据 (`snapshot.capital` 为 None) → 直接返回 `unavailable`。

---

## JSON 输出格式

所有 Agent 期望 LLM 返回统一的 JSON 格式：

```json
{
  "status": "ok",
  "sentiment": "neutral",
  "summary": "100-200字的分析结论",
  "focus_points": ["关注点1", "关注点2"],
  "risk_points": ["风险点1", "风险点2"]
}
```

## sentiment 取值

| 值 | 含义 |
|----|------|
| bullish | 偏多 |
| bearish | 偏空 |
| neutral | 中性 |
| unavailable | 数据缺失（非 LLM 输出） |

---

## LLM Client 架构

**模块**: `src/llm/client.py`

### 多 Provider 配置

```python
# src/llm/config.py
class LLMProvider(BaseModel):
    name: str                # "deepseek", "dashscope"
    base_url: str            # API base URL
    api_key_env: str         # 环境变量名 (如 "DEEPSEEK_API_KEY")
    model: str               # 模型名
    temperature: float = 0.3
    max_tokens: int = 1024
    timeout: int = 60
    priority: int = 1        # 数字越小优先级越高

class LLMConfig(BaseModel):
    providers: list[LLMProvider]
    mode: str = "fallback"   # "fallback" | "concurrent"
    max_retries: int = 2
```

**默认配置:**
- Primary: DeepSeek `deepseek-v4-flash` (priority=1, `DEEPSEEK_API_KEY`)
- Fallback: DashScope `qwen3.6-plus` (priority=2, `DASHSCOPE_API_KEY`)

### 运行模式

| 模式 | 行为 |
|------|------|
| `fallback` | 按 priority 顺序逐个尝试，第一个成功即返回 |
| `concurrent` | 同时向所有可用 Provider 发请求，取最先成功的结果 |

### JSON 解析

- 自动剥离 ````json ... ```` markdown 代码块
- 解析失败视为 Provider 调用失败，触发重试/降级

### 调用链

```
Agent.call_llm()
  → LLMClient.chat_json()
    → mode 判断
      → fallback: 逐 Provider 尝试（内置失败重试）
      → concurrent: asyncio.gather 并发所有 Provider
    → 自动 JSON 解析
```

---

## BaseAgent 实现要点

**模块**: `src/agents/base.py`

- 通过 `get_llm_client()` 获取 LLMClient 单例
- 支持 `config.max_retries` 次重试（默认 2 次），间隔 2 秒
- 无可用 Provider 时直接返回 `unavailable`
- `_make_result()` 统一将 LLM JSON 转为 `AgentResult` 模型
- status 映射: 任意成功状态（ok/available/analyzed/success）→ `ok`

---

## 综合结论（Report Generator 内计算，非 LLM）

在 `src/reports/generator.py` 的 `_compute_overall()` 中根据三个 Agent 的 sentiment 汇总：

- 2+ bullish（排除 unavailable）→ `overall_sentiment=bullish`
- 2+ bearish（排除 unavailable）→ `overall_sentiment=bearish`
- 否则 → `neutral`
- `overall_focus` 取 `technical.focus_points[0]`（若有）
