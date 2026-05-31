# 数据源 & 多源 Provider 架构

## 更新记录

- **2026-05-24**: 全面重构 — 新增多源 Provider 架构（Eastmoney 直连 HTTP、Sina、Tencent），AkShare 降级为 K 线备选之一
- **2026-05-24**: 新增系统自检脚本 `scripts/self_check.py`，10 维度 46 项检查

## 0. 多源降级架构

### 数据源优先级

| 数据类型 | 主源 | 备选 1 | 备选 2 | 实现位置 |
|---------|------|--------|--------|---------|
| 日线 OHLCV | AkShare `stock_zh_a_hist` | Sina Finance K-line | Tencent K-line | `_fetch_kline_chain` |
| PE/PB/市值 | Eastmoney push2 | Tencent quote | - | `_fetch_valuation_chain` |
| 资金流 | Eastmoney push2 | AkShare `fund_flow` | - | `_fetch_capital_chain` |
| 龙虎榜 | Eastmoney datacenter | - | - | `_fetch_dragon_tiger` |
| 公告 | AkShare `stock_notice_report` | 空列表 | - | `_fetch_announcements_chain` |
| 市场概览 | Eastmoney push2 | AkShare 指数日线 | - | `fetch_market_overview` |

> **注意**: 新闻通过 AkShare `stock_news_em` 获取；失败时降级为空列表。

### 架构图

```
                    ┌─────────────────────────┐
                    │     DataFetcher          │
                    │  (多源降级链)             │
                    └────────────┬────────────┘
                                 │
        ┌────────────────────────┼──────────────────────┐
        ▼                        ▼                      ▼
┌───────────────┐      ┌─────────────────┐    ┌───────────────┐
│  AkShare      │      │  Eastmoney      │    │  Sina/Tencent │
│  (K线/公告)   │      │  (直连HTTP)      │    │  (K线/行情)    │
│  stock_zh_*   │      │  push2/datacenter│    │  qt.gtimg.cn  │
│  notice_report│      │  push2.eastmoney│    │  sina finance │
│  fund_flow    │      │  datacenter.east│    │               │
└───────────────┘      └─────────────────┘    └───────────────┘
```

### Provider 实现

```
src/data/providers/
├── eastmoney.py   # 东财 push2 — PE/PB/市值/资金流 + datacenter — 龙虎榜/融资融券/股东/分红
├── sina.py        # 新浪 K线 — 日线 OHLCV 备选
└── tencent.py     # 腾讯财经 — 实时行情/K线备选
```

#### Eastmoney push2

- **端点**: `https://push2.eastmoney.com/api/qt/stock/get`
- **参数**: `secid` (1.600519=沪, 0.000001=深), `fields` (f170=PE, f171=PB, f162=市值, f173=涨跌幅)
- **UT 参数**: `ut=fa5fd1943c7b386f172d6893dbfba10b` (必需)
- **函数**: `get_stock_info(code)`, `get_capital_flow(code)`, `get_market_overview()`

#### Eastmoney datacenter

- **端点**: `https://datacenter-web.eastmoney.com/api/data/v1/get`
- **数据**: 龙虎榜、融资融券、股东户数、分红送转
- **函数**: `eastmoney_datacenter()`, `get_dragon_tiger()`, `get_margin_trading()`, `get_holder_count()`, `get_dividend_history()`

#### Sina Finance

- **端点**: `https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData`
- **函数**: `get_kline_sina(code, days)`
- **代码转换**: 600519 → `sh600519`, 000001 → `sz000001`

#### Tencent Finance

- **端点**: `https://qt.gtimg.cn/q=sh600519`
- **函数**: `get_stock_quote(code)`, `get_kline_tencent(code, days)`
- **代码转换**: 600519 → `sh600519`, 000001 → `sz000001`

## 1. 股票代码规范

- 输入：6 位纯数字代码（600519, 000001, 300750）
- 沪市: 6 开头 → `sh` 前缀 / `1.` secid
- 深市: 0/3 开头 → `sz` 前缀 / `0.` secid
- 内部统一用 6 位，Provider 层各自转换

## 2. AkShare 接口清单（保留）

| 数据 | 主接口 | 函数 | 降级 |
|------|--------|------|------|
| 日线 OHLCV | 主 | `ak.stock_zh_a_hist(symbol, period="daily", adjust="qfq")` | Sina → Tencent |
| 公告 | 主 | `ak.stock_notice_report(symbol=code)` | 空列表 |
| 主力流向 | 主 | `ak.stock_individual_fund_flow(stock=code, market="sh/sz")` | Eastmoney push2 |
| 大盘指数 | 辅 | `ak.stock_zh_index_daily(symbol="sh000001")` | Eastmoney push2 |

## 3. market 参数判断

```python
def get_market(code: str) -> str:
    if code.startswith("6"):
        return "sh"
    return "sz"
```

## 4. fetcher 实现要求

```python
class DataFetcher:
    async def fetch_stock(self, code: str, name: str) -> StockSnapshot:
        """
        1. K线链: AkShare → Sina → Tencent
        2. 估值链: Eastmoney push2 → Tencent
        3. 资金链: Eastmoney → AkShare
        4. 公告链: AkShare → 空列表
        5. 龙虎榜: Eastmoney datacenter
        6. 返回 StockSnapshot，任何子步骤失败不 raise，记入 fetch_errors
        """
```

## 5. MA 计算

```python
# src/data/fetcher_utils.py
def calc_ma(closes: list[float], periods: list[int] = [5, 10, 20]) -> dict[int, float]:
    """返回 {5: ma5, 10: ma10, 20: ma20}"""
```

## 6. 重试策略

- AkShare 调用：`settings.data.retry` 次（默认 1 次），间隔 `settings.data.retry_delay` 秒
- HTTP Provider: 快速失败，不重试（依赖多源降级）
- 超时：15 秒
- 失败记入 `fetch_errors: ["daily: timeout", "capital: API error"]`

## 7. 并行采集

```python
async def fetch_all(items: list[WatchlistItem]) -> tuple[list[StockSnapshot], list[str]]:
    """
    使用 asyncio.gather(..., return_exceptions=True)
    异常的股票记入 failed_symbols，不阻塞其他
    """
```

## 8. 交易日判断

```python
# src/data/calendar.py
def is_trading_day(d: date) -> bool:
    """使用 sina 交易日历判断"""
```

MVP 要求：
- 启动时或首次调用时加载交易日历并缓存
- 非交易日 scheduler 不执行
- 周末可简单跳过（周一到周五），但以交易日历为准

## 9. 已知网络限制

当前服务器环境对部分东财域名有拦截：
- `push2his.eastmoney.com` — 被屏蔽（改用 push2 + `ut` 参数）
- `search-api` — 被屏蔽

降级方案已验证：腾讯财经 + 新浪 K 线可作为主力备选。

## 10. 注意事项

- AkShare 为同步库，fetcher 中用 `asyncio.to_thread()` 包装避免阻塞事件循环
- HTTP Provider 使用 `httpx` 直连，无需通过 AkShare
- 禁止在 Agent 中直接调用 AkShare，必须通过 DataFetcher
- 采集与 LLM 分析严格分离
- 记录 `ak.__version__` 到日志
