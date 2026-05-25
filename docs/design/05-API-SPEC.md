# REST API 规格

> **Updated**: 2026-05-24 — 确认与 `src/api/routes.py` 实现一致

Base URL: `http://127.0.0.1:8000`

## 启动

```bash
cd stock-copilot
uvicorn src.api.routes:app --host 0.0.0.0 --port 8000
```

或通过 CLI：

```bash
python -m src.main serve [--port 8000]
```

## FastAPI 应用

```python
app = FastAPI(
    title="Stock Copilot API",
    description="A股辅助决策系统 API",
    version="0.1.0",
)
```

---

## GET /health

健康检查。

**Response 200:**

```json
{ "status": "ok", "version": "0.1.0" }
```

---

## POST /analyze

触发分析管线（MVP 同步实现，非异步）。

**Request:**

```json
{
  "type": "pre",
  "symbols": ["600519", "000001"]
}
```

- `type`: `"pre"` | `"post"`，必填 (`ReportType` 枚举)
- `symbols`: 可选，缺省读 `config/watchlist.yaml`

**Response 200:**

```json
{
  "status": "completed",
  "report_path": "output/reports/2026-05-22-pre.md",
  "symbol_count": 2,
  "failed_symbols": []
}
```

**Response 400:** 非交易日或 watchlist 不存在

```json
{ "detail": "非交易日，跳过分析" }
```

**Response 500:** 分析管线内部异常

> **注意**：MVP 为同步实现，`POST /analyze` 会阻塞等待完整管线执行完毕（fetch → agents → report → notify）。未来可改为异步任务队列。

---

## GET /reports/latest

返回最新报告 Markdown 内容。按文件名倒序取最近的 `.md` 文件。

**Response 200:**

```json
{
  "file_path": "/home/ubuntu/repos/stock-copilot/output/reports/2026-05-22-pre.md",
  "markdown": "# A股自选股分析简报\n..."
}
```

**Response 404:** `No reports found`

---

## GET /reports/{report_date}

按日期获取报告。

- Path: `report_date` = `YYYY-MM-DD`
- Query: `type=pre|post`（默认 `pre`）

**Response 200:** 同上 ReportResponse

**Response 404:** `Report not found: {file_path}`

文件名格式: `{report_date}-{type}.md`

---

## GET /site/latest.json

返回 `latest.json` 数据，供前端渲染使用。

**Response 200:**

```json
{
  "meta": {
    "report_type": "pre",
    "trade_date": "2026-05-22",
    "generated_at": "2026-05-22T08:30:00",
    "symbol_count": 3,
    "disclaimer": "⚠️ 本报告仅供个人研究参考..."
  },
  "market": {
    "index_name": "上证指数",
    "close": 3150.25,
    "change_pct": 0.52
  },
  "stocks": [
    {
      "code": "600519",
      "name": "贵州茅台",
      "overall_sentiment": "bullish",
      "overall_focus": "均线多头排列，量能温和放大",
      "technical": { "status": "ok", "summary": "...", "sentiment": "bullish" },
      "fundamental": { "status": "ok", "summary": "...", "sentiment": "neutral" },
      "capital": { "status": "ok", "summary": "...", "sentiment": "bullish" },
      "risk_points": ["估值处于历史高位"]
    }
  ],
  "failed_symbols": [],
  "archive": [
    { "date": "2026-05-22", "type": "pre", "url": "archive/2026-05-22-pre.html" }
  ]
}
```

**Response 404:** `latest.json not found`

---

## Pydantic 模型

```python
class AnalyzeRequest(BaseModel):
    type: ReportType                # ReportType.PRE | ReportType.POST
    symbols: Optional[list[str]] = None

class AnalyzeResponse(BaseModel):
    status: str                     # "completed"
    report_path: str                # 报告文件绝对路径
    symbol_count: int               # 成功分析的股票数
    failed_symbols: list[str]       # 数据采集失败的代码

class ReportResponse(BaseModel):
    file_path: str                  # 报告文件绝对路径
    markdown: str                   # Markdown 全文
```

---

## 路由汇总

| 方法 | 路径 | 描述 | 响应模型 |
|------|------|------|----------|
| GET | `/health` | 健康检查 | `{"status", "version"}` |
| POST | `/analyze` | 触发分析管线 | `AnalyzeResponse` |
| GET | `/reports/latest` | 最新报告 | `ReportResponse` |
| GET | `/reports/{date}` | 按日期取报告 | `ReportResponse` |
| GET | `/site/latest.json` | 站点数据 | `latest.json` 内容 |
