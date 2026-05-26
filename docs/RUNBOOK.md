# Stock Copilot 运维手册 (RUNBOOK)

> 版本: v1.4.0 | 更新: 2026-05-26

---

## 快速索引

| 场景 | 命令 |
|------|------|
| 查看服务状态 | `sudo systemctl status stock-copilot` |
| 重启服务 | `sudo systemctl restart stock-copilot` |
| 查看日志 | `sudo journalctl -u stock-copilot -f` |
| 手动 Full 分析 | `python -m src.main analyze --type pre [--publish]` |
| 手动 Fast 更新 | `python -m src.main fast` |
| 健康检查 | `curl http://127.0.0.1:8000/health` |
| 停止服务 | `sudo systemctl stop stock-copilot` |

---

## 架构概要

```
systemd stock-copilot.service (常驻, MemoryMax=1G)
  └─ python -m src.main run
       ├─ APScheduler (6 个 Job)
       │    ├─ 盘前 Full + publish (settings.schedule.pre_market)
       │    ├─ 盘中 Fast × N (intraday_hours, 无 LLM/git)
       │    ├─ 盘后 Full + publish
       │    ├─ 进化 (evolution.enabled)
       │    └─ DB 清理 (weekly)
       └─ FastAPI :8000 (watchlist/jobs/intraday)

数据流: Watchlist(DB) → fetch → hard+LLM → fuse → SQLite → site/docs (静态) + API (动态)
```

**Job 数量**: 6 个 cron（非 29 个）。盘中小时数由 `config/settings.yaml` → `schedule.intraday_hours` 配置。

---

## 故障排查

### 服务启动失败

```bash
# 查看详细日志
sudo journalctl -u stock-copilot --no-pager -n 50

# 常见原因:
# 1. .env 文件不存在或 API Key 未配置
#    → cp .env.example .env && 填写 DEEPSEEK_API_KEY
# 2. venv 依赖缺失
#    → cd /home/ubuntu/repos/stock-copilot && .venv/bin/pip install -r requirements.txt
# 3. 端口被占用 (仅限 serve 模式)
#    → lsof -i :8000
```

### 数据采集全部失败

```bash
# 测试 AkShare 连通性
.venv/bin/python3 -c "import akshare as ak; print(ak.stock_zh_a_hist(symbol='600519', period='daily').tail(3))"

# 测试东财直连
.venv/bin/python3 -c "from src.data.providers import eastmoney; print(eastmoney.get_stock_info('600519'))"

# 检查网络/DNS
curl -s --connect-timeout 5 https://api.deepseek.com/v1/models -H "Authorization: Bearer $DEEPSEEK_API_KEY" | head -1
```

### LLM 调用失败

```bash
# 检查 Provider 状态
.venv/bin/python3 -c "
from src.llm.client import get_llm_client
client = get_llm_client()
print(client.status())
"

# 手动测试 DeepSeek
.venv/bin/python3 -c "
from openai import OpenAI
import os
c = OpenAI(api_key=os.environ['DEEPSEEK_API_KEY'], base_url='https://api.deepseek.com')
r = c.chat.completions.create(model='deepseek-v4-flash', messages=[{'role':'user','content':'你好'}], max_tokens=10)
print(r.choices[0].message.content)
"
```

### 数据库异常增长

```bash
# 查看 DB 大小
ls -lh /home/ubuntu/repos/stock-copilot/data/signals.db

# 手动清理 90 天前的数据
.venv/bin/python3 -c "
from src.data.db_manager import SignalDB
db = SignalDB()
deleted = db.cleanup_old_signals(keep_days=90)
print(f'Deleted {deleted} old records')
"

# 查看记录分布
.venv/bin/python3 -c "
import sqlite3
conn = sqlite3.connect('data/signals.db')
c = conn.cursor()
c.execute('SELECT trade_date, COUNT(*) FROM signals GROUP BY trade_date ORDER BY trade_date DESC LIMIT 20')
for r in c.fetchall():
    print(f'{r[0]}: {r[1]} records')
conn.close()
"
```

### GitHub Pages 不更新

```bash
# 检查 git 状态
cd /home/ubuntu/repos/stock-copilot
git status
git log --oneline -5

# 检查 remote
git remote -v

# 手动发布
.venv/bin/python3 -m src.main analyze --type pre --publish

# 检查 Pages 配置: GitHub → Settings → Pages → Source (应为 main + /docs)
```

### 磁盘空间不足

```bash
# 检查大文件
du -sh /home/ubuntu/repos/stock-copilot/data/signals.db
du -sh /home/ubuntu/repos/stock-copilot/output/reports/
du -sh /home/ubuntu/repos/stock-copilot/docs/archive/

# 清理旧报告 (保留最近30天)
find /home/ubuntu/repos/stock-copilot/output/reports/ -name "*.md" -mtime +30 -delete
find /home/ubuntu/repos/stock-copilot/docs/archive/ -name "*.html" -mtime +60 -delete
```

---

## 配置变更

### 修改自选股

```bash
# 编辑自选股列表
nano /home/ubuntu/repos/stock-copilot/config/watchlist.yaml

# 格式:
# symbols:
#   - code: "600519"
#     name: "贵州茅台"

# 无需重启服务，下次分析自动生效
```

### 修改调度时间

```bash
# 编辑 src/scheduler/jobs.py 中的 cron 参数
# 然后:
sudo systemctl restart stock-copilot
```

### 修改 LLM 配置

```bash
# 编辑 config/settings.yaml 中的 llm 部分
# 或修改 .env 中的 API Key

# 需要重启服务生效 (LRU cache 在进程生命周期内缓存)
sudo systemctl restart stock-copilot

# 或使用热加载 (代码中调用 refresh_settings())
```

---

## 监控建议

### 添加 Cron 健康检查

```bash
# 每 4 小时检查一次服务状态
0 */4 * * * /home/ubuntu/repos/stock-copilot/scripts/health_check.sh >> /tmp/stock-copilot-health.log 2>&1
```

### 关键日志关键词

```bash
# 搜索错误
sudo journalctl -u stock-copilot --grep "ERROR" --since "today"

# 搜索失败的分析
sudo journalctl -u stock-copilot --grep "failed" --since "today"

# 搜索 API 限流
sudo journalctl -u stock-copilot --grep "rate\|429\|blocked" --since "today"
```

---

## 版本历史

| 日期 | 版本 | 变更 |
|------|------|------|
| 2026-05-26 | v1.3.0 | systemd 服务 + 29个调度任务 + DB清理 + health_check |
| 2026-05-25 | v1.2.0 | Phase B 完成 (龙虎榜 + 公告 + UI) |
| 2026-05-24 | v1.1.0 | Phase A 完成 (信号融合 + SQLite) |
| 2026-05-22 | v1.0.0 | MVP 完成 |
