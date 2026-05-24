# Stock Copilot (智策)

> 基于 AI 的 A 股个人投研助手：看全、看懂、及时提醒

## 定位

个人研究工具 + 信息聚合 + 风险提示。**不构成投资建议，不承诺收益。**

## 功能

- **数据采集**：AkShare 自动获取日线行情、公告、资金流
- **AI 分析**：技术面 / 公告面 / 资金面三维分析（LLM）
- **报告生成**：Markdown 报告 + 静态 Web 站点
- **定时调度**：盘前 08:30 / 盘后 16:00 自动运行
- **GitHub Pages**：分析结果发布为静态网页，浏览器直接访问

## 快速开始

### 1. 安装依赖

```bash
cd stock-copilot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. 配置

```bash
cp .env.example .env
# 编辑 .env 填入 LLM API Key
```

### 3. 运行

```bash
# 手动分析
python -m src.main analyze --type pre

# 启动 API 服务
python -m src.main serve

# 启动定时调度
python -m src.main schedule
```

## 切换 LLM 模型

编辑 `config/settings.yaml` 中的 `llm.base_url` 和 `llm.model`，或在 `.env` 中设置 `OPENAI_BASE_URL` / `OPENAI_API_KEY`。

支持任何 OpenAI 兼容接口：DeepSeek、OpenRouter、Ollama 等。

## 架构

```
watchlist.yaml → Data Fetcher (多源降级链) → StockSnapshot
  → Technical / Fundamental / Capital Agent (LLM)
  → Report Generator (Markdown + HTML)
  → GitHub Pages / Notify

数据源: AkShare (主) → Sina/Tencent/Eastmoney (备选)
```

### 数据源降级链

| 数据类型 | 主源 | 备选 1 | 备选 2 |
|---------|------|--------|--------|
| 日线 OHLCV | AkShare | Sina Finance | Tencent |
| PE/PB/市值 | Eastmoney push2 | Tencent | - |
| 资金流 | Eastmoney | AkShare | - |
| 龙虎榜 | Eastmoney datacenter | - | - |

详细设计见 [docs/](docs/) 目录。

## 合规

每份报告包含固定免责声明：

> ⚠️ 本报告仅供个人研究参考，不构成投资建议。报告内容基于公开数据和 AI 分析生成，可能存在错误或遗漏。股市有风险，决策需谨慎。作者不对任何投资损失承担责任。

## 许可证

MIT
