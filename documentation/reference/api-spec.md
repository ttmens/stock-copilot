# REST API 规格

> **Version 3.0.0-alpha** | 对齐 [`src/api/routes.py`](../../src/api/routes.py) | 2026-05-26

Base URL: `http://127.0.0.1:8000`（生产：`python -m src.main run`）

## 启动

```bash
python -m src.main run      # scheduler + API（推荐）
python -m src.main serve    # 仅 API
```

## 鉴权

当环境变量 `STOCK_COPILOT_TOKEN`（由 `config/settings.yaml` → `api.auth_token_env` 指定）已设置时，受保护路由需请求头：

```
X-API-Key: <token>
```

未设置 token 时 API 无鉴权（仅适合本地开发）。

## CORS

默认允许 `api.cors_origins` + GitHub Pages 源，见 `config/settings.yaml`。

---

## 端点一览

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 + 数据新鲜度 |
| GET | `/api/system/status` | 系统状态（DB、watchlist、发布） |
| POST | `/analyze` | 触发 Full DeliveryPipeline |
| POST | `/api/jobs` | 创建异步任务 `{type, mode, symbols?, publish?}` |
| GET | `/api/jobs/latest` | 最近任务 |
| GET | `/api/jobs/{job_id}` | 任务详情 |
| GET | `/api/watchlist` | 自选列表 |
| POST | `/api/watchlist` | 添加 `{code, name?}` |
| DELETE | `/api/watchlist/{code}` | 删除自选 |
| PATCH | `/api/watchlist/{code}` | 更新 pinned/name |
| POST | `/api/watchlist/import-default` | 导入默认模板 |
| GET | `/api/quotes/intraday` | 盘中报价 |
| GET | `/api/evolution/suggestions` | 进化建议 |
| POST | `/api/evolution/suggestions/{id}/accept` | 接受/拒绝建议 |
| GET | `/api/published` | 最近发布时间 |
| GET | `/reports/latest` | 最新 Markdown 报告 |
| GET | `/reports/{report_date}?type=pre\|post` | 按日期报告 |
| GET | `/site/latest.json` | 站点 JSON 快照 |
| POST | `/api/scenario/simulate` | 场景推演 `{scenario, symbols?}` |
| GET | `/api/postmortems` | 信号复盘列表 `?ticker=&days=` |
| GET | `/api/postmortems/summary` | 复盘统计 `?days=` |
| POST | `/api/postmortems/check-mature` | 检查成熟信号 |
| GET | `/api/theses` | 论点列表 `?status=&ticker=` |
| GET | `/api/theses/statistics` | 论点统计 `?days=` |
| GET | `/api/breadth` | 市场广度（从 latest.json 聚合） |
| GET | `/api/stagnation` | 个股停滞检测（启发式） |

静态站点：`/` 与 `/site` 挂载 `docs/` 目录（GitHub Pages 产物）。

---

## GET /health

**Response 200**（节选）：

```json
{
  "status": "ok",
  "version": "2.1.0",
  "watchlist_count": 50,
  "last_published": {},
  "data_freshness": "fresh"
}
```

---

## POST /analyze

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
  "report_path": "output/reports/2026-05-30-pre.md",
  "symbol_count": 1,
  "failed_symbols": [],
  "job_id": ""
}
```

---

## POST /api/scenario/simulate

**Request:**

```json
{
  "scenario": "如果新能源板块整体下跌5%",
  "symbols": ["300750", "002594"]
}
```

**Response:** `impact_matrix`, `overall_assessment`, `report` (markdown)

---

## Phase F 端点说明

- **Postmortem**：pipeline 自动 `record_signal`；`check-mature` 填充 7 日后 outcome
- **Thesis**：fusion_score > 0.4 自动创建；transition API **未实现**（Pending）
- **Breadth**：首页 widget 数据来自 pipeline 嵌入的 `breadth` 字段；API 从 latest.json 再聚合
- **Stagnation**：当前为 latest.json 启发式，非 Phase F 计划的策略停滞模块（Pending）

---

## Phase G 端点（3.0.0-alpha）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/market/session` | 当前交易时段 |
| GET | `/api/digest/today` | 日更情报 |
| GET | `/api/overnight` | 外盘快照 |
| GET | `/api/recommendations/today` | 推荐池 3×3 |
| GET | `/api/auction/latest` | 竞价指标 |
| GET | `/api/alerts` | 预警流 |
| POST | `/api/alerts/read` | 标记已读 |
| GET/POST/PATCH/DELETE | `/api/positions` | 仓位 CRUD |
| GET | `/api/review/today` | 盘后复盘 |
| POST | `/api/stocks/{code}/deep-analysis` | 深度分析 |

---

## 错误码

| Code | 场景 |
|------|------|
| 400 | 非交易日、空 watchlist、无效 symbols |
| 401 | API Key 无效 |
| 404 | 报告/任务/JSON 不存在 |
| 500 | 管线内部异常 |
