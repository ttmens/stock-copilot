# 本地开发指南

## 环境

```bash
cd stock-copilot
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux
pip install -r requirements.txt
cp .env.example .env            # 填写 DEEPSEEK_API_KEY 等
```

## 常用命令

```bash
# 全量分析（LLM + 站点）
python -m src.main analyze --type pre
python -m src.main analyze --type post --publish

# 盘中 Fast（无 LLM）
python -m src.main fast

# API + 调度（生产同款）
python -m src.main run

# 仅 API
python -m src.main serve --port 8000
```

## 重生成站点（无 LLM）

从现有 JSON 刷新 GitHub Pages 壳：

```bash
python scripts/regenerate_docs_site.py
```

## 测试

```bash
python -m pytest tests/ -q
python scripts/check_docs_ssot.py --project-root .
python scripts/ui_acceptance.py --quick
```

## 文档

设计 SSOT 在 [`documentation/`](../README.md)，不在 `docs/`。

## API 本地联调

编辑 `docs/app/config.js`（源文件 `src/site/app/config.js`）：

```javascript
window.STOCK_COPILOT = { API_BASE: "http://127.0.0.1:8000" };
```

详见 [ui-hybrid-setup.md](./ui-hybrid-setup.md)。
