# REST API 规格

> **Updated**: 2026-05-26 — v1.4 Phase C，与 `src/api/routes.py` 一致

Base URL: `http://127.0.0.1:8000`（生产与 scheduler 同进程：`python -m src.main run`）

## 启动

```bash
python -m src.main run      # scheduler + API
python -m src.main serve    # 仅 API
```

CORS 默认允许 GitHub Pages 源，见 `config/settings.yaml` → `api.cors_origins`。

---

## 动态 API（Phase C）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/watchlist` | 自选列表 |
| POST | `/api/watchlist` | 添加 `{code, name?}` |
| DELETE | `/api/watchlist/{code}` | 删除 |
| PATCH | `/api/watchlist/{code}` | 更新 pinned/name |
| POST | `/api/watchlist/import-default` | 导入默认模板 |
| POST | `/api/jobs` | 创建任务 `{type, mode, symbols?, publish?}` |
| GET | `/api/jobs/latest` | 最近任务 |
| GET | `/api/jobs/{id}` | 任务详情 |
| GET | `/api/quotes/intraday` | 盘中报价 |
| GET | `/api/evolution/suggestions` | 进化建议 |
| POST | `/api/evolution/suggestions/{id}/accept` | 接受/拒绝建议 |
| GET | `/api/published` | 最近发布时间 |

---

## GET /health

**Response 200:**

```json
{ "status": "ok", "version": "1.4.0", "last_published": { ... } }
```

---

## POST /analyze

触发 **Full DeliveryPipeline**（分析 → 站点 → 可选 publish）。

**Request:**

```json
{
  "type": "pre",
  "symbols": ["600519"],
  "publish": false
}
```

**Response 200:**

```json
{
  "status": "completed",
  "report_path": "output/reports/2026-05-26-pre.md",
  "symbol_count": 1,
  "failed_symbols": []
}
```

---

## 原有端点

以下端点保持不变，详见下文。

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
