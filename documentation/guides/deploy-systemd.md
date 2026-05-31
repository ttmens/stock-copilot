# systemd 部署

> 摘自 [runbook.md](./runbook.md) 部署章节

## 服务单元

文件：[`stock-copilot.service`](../../stock-copilot.service)

```ini
ExecStart=/home/ubuntu/repos/stock-copilot/.venv/bin/python3 -m src.main run
MemoryMax=1G
```

`run` = APScheduler（6 jobs）+ FastAPI :8000 单进程。

## 安装

```bash
sudo cp stock-copilot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable stock-copilot
sudo systemctl start stock-copilot
```

## 验证

```bash
sudo systemctl status stock-copilot
curl http://127.0.0.1:8000/health
journalctl -u stock-copilot -f
```

## 更新代码

```bash
cd /home/ubuntu/repos/stock-copilot
git pull
pip install -r requirements.txt
sudo systemctl restart stock-copilot
```

## 环境变量

- `DEEPSEEK_API_KEY` / `DASHSCOPE_API_KEY` — LLM
- `WECOM_WEBHOOK` — 通知
- `STOCK_COPILOT_TOKEN` — API 鉴权（可选）
