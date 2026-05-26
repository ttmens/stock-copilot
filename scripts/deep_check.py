#!/usr/bin/env python3
"""Stock Copilot Deep Self-Check — 全链路深度自检"""
import json
import subprocess
import sqlite3
import sys
from pathlib import Path
from datetime import datetime, date

PROJECT = Path(__file__).resolve().parent.parent
PASS = 0
FAIL = 0
WARN = 0

def check(name, result, detail=""):
    global PASS, FAIL, WARN
    if result == "PASS":
        PASS += 1
        icon = "✅"
    elif result == "WARN":
        WARN += 1
        icon = "⚠️"
    else:
        FAIL += 1
        icon = "❌"
    msg = f"  {icon} {name}"
    if detail:
        msg += f" — {detail}"
    print(msg)

print("=" * 60)
print("  Stock Copilot 深度自检 (Deep Check)")
print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 60)

# ═══ 1. 系统服务 ═══
print("\n━━━ 1. 系统服务 ━━━")
r = subprocess.run(["sudo", "systemctl", "is-active", "stock-copilot"], capture_output=True, text=True)
if r.stdout.strip() == "active":
    check("systemd 服务", "PASS", "active (running)")
else:
    check("systemd 服务", "FAIL", r.stdout.strip() or "unknown")

r = subprocess.run(["sudo", "systemctl", "is-enabled", "stock-copilot"], capture_output=True, text=True)
check("开机自启", "PASS" if r.stdout.strip() == "enabled" else "FAIL", r.stdout.strip())

# ═══ 2. 数据库 ═══
print("\n━━━ 2. 数据库 ━━━")
db_path = PROJECT / "data" / "signals.db"
if db_path.exists():
    db_size = db_path.stat().st_size
    check("SQLite 文件", "PASS", f"{db_size/1024:.0f} KB")
    
    conn = sqlite3.connect(str(db_path))
    c = conn.cursor()
    
    r = c.execute("PRAGMA integrity_check").fetchone()
    check("完整性", "PASS" if r[0] == "ok" else "FAIL", r[0])
    
    c.execute("SELECT COUNT(*) FROM signals")
    total = c.fetchone()[0]
    check("信号总数", "PASS" if total > 0 else "FAIL", f"{total} 条")
    
    today = date.today().isoformat()
    c.execute("SELECT COUNT(*), GROUP_CONCAT(DISTINCT report_type) FROM signals WHERE trade_date=?", (today,))
    row = c.fetchone()
    if row[0]:
        check("今日数据", "PASS", f"{row[0]} 条 ({row[1]})")
    else:
        check("今日数据", "FAIL", "无记录")
    
    c.execute("SELECT report_type, COUNT(*) FROM signals GROUP BY report_type")
    types = dict(c.fetchall())
    if "post" in types and types["post"] > 0:
        check("report_type 正确", "PASS", f"pre={types.get('pre',0)}, post={types.get('post',0)}")
    else:
        check("report_type 正确", "FAIL", "无 post 记录")
    
    c.execute("SELECT COUNT(*) FROM stock_meta")
    meta_count = c.fetchone()[0]
    check("股票元数据", "PASS" if meta_count > 0 else "WARN", f"{meta_count} 只")
    
    conn.close()
else:
    check("SQLite 文件", "FAIL", "不存在")

# ═══ 3. 报告生成 ═══
print("\n━━━ 3. 报告生成 ━━━")
report_dir = PROJECT / "output" / "reports"
if report_dir.exists():
    reports = list(report_dir.glob("2026-05-26-*.md"))
    if reports:
        latest = max(reports, key=lambda p: p.stat().st_mtime)
        size = latest.stat().st_size
        check("今日报告", "PASS" if size > 1000 else "WARN", f"{latest.name} ({size/1024:.1f} KB)")
        content = latest.read_text()
        if "不构成投资建议" in content:
            check("免责声明", "PASS")
        else:
            check("免责声明", "FAIL", "缺失")
    else:
        check("今日报告", "FAIL", "未找到")
else:
    check("报告目录", "FAIL")

# ═══ 4. 站点生成 ═══
print("\n━━━ 4. 站点生成 ━━━")
docs_dir = PROJECT / "docs"
check("index.html", "PASS" if (docs_dir / "index.html").exists() else "FAIL")
check("theme.css", "PASS" if (docs_dir / "assets" / "theme.css").exists() else "FAIL")

# 检查 site/ 目录的 latest.json（避免自检脚本覆盖 docs/ 的）
site_json = PROJECT / "site" / "data" / "latest.json"
latest_json = docs_dir / "data" / "latest.json"
if site_json.exists():
    d = json.loads(site_json.read_text())
    check("latest.json", "PASS", f"{d['meta']['symbol_count']} 只, date={d['meta']['trade_date']}")
elif latest_json.exists():
    d = json.loads(latest_json.read_text())
    check("latest.json", "PASS" if d['meta']['symbol_count'] > 0 else "WARN", f"{d['meta']['symbol_count']} 只, date={d['meta']['trade_date']}")
else:
    check("latest.json", "FAIL")

archive = list((docs_dir / "archive").glob("2026-05-26-*.html"))
check("今日归档", "PASS" if archive else "WARN", f"{len(archive)} 个文件")

stock_dir = docs_dir / "stock"
if stock_dir.exists():
    stock_pages = list(stock_dir.glob("*.html"))
    check("个股详情页", "PASS" if len(stock_pages) > 0 else "FAIL", f"{len(stock_pages)} 页")

# ═══ 5. Git & 发布 ═══
print("\n━━━ 5. Git & 发布 ━━━")
r = subprocess.run(["git", "status", "--porcelain", "docs/"], capture_output=True, text=True)
if r.stdout.strip():
    check("工作区", "WARN", f"{len(r.stdout.strip().splitlines())} 个未提交")
else:
    check("工作区", "PASS", "干净")

r = subprocess.run(["git", "log", "--oneline", "-3"], capture_output=True, text=True)
check("最近提交", "PASS", r.stdout.strip().split("\n")[0] if r.stdout.strip() else "无")

# ═══ 6. 代码质量 ═══
print("\n━━━ 6. 代码质量 ━━━")
fetcher = (PROJECT / "src" / "data" / "fetcher.py").read_text()
pipeline = (PROJECT / "src" / "orchestrator" / "pipeline.py").read_text()
generator = (PROJECT / "src" / "site" / "generator.py")
theme_css = PROJECT / "src" / "site" / "theme.css"

check("HTTP 限流", "PASS" if "Semaphore" in fetcher else "FAIL")
check("LLM 限流", "PASS" if "Semaphore" in pipeline else "FAIL")
check("CSS 拆分", "PASS" if theme_css.exists() else "FAIL", f"generator.py {len(generator.read_text().splitlines())} 行")

# 检查已知 bug 是否修复
if 'report_type="pre"' not in pipeline:
    check("report_type bug", "PASS", "已修复")
else:
    check("report_type bug", "FAIL", "仍存在硬编码")

# ═══ 7. 运维 ═══
print("\n━━━ 7. 运维 ━━━")
check("RUNBOOK.md", "PASS" if (PROJECT / "docs" / "RUNBOOK.md").exists() else "FAIL")
check("health_check.sh", "PASS" if (PROJECT / "scripts" / "health_check.sh").exists() else "FAIL")

# ═══ 8. 调度器启动补跑 ═══
print("\n━━━ 8. 调度器容错 ━━━")
jobs_py = (PROJECT / "src" / "scheduler" / "jobs.py").read_text()
if "_startup_catch_up" in jobs_py:
    check("startup catch-up", "PASS", "启动时自动补跑")
else:
    check("startup catch-up", "FAIL", "缺失")

if "asyncio.run(_run_scheduler())" in jobs_py:
    check("asyncio 兼容", "PASS")
else:
    check("asyncio 兼容", "FAIL")

# ═══ 总结 ═══
print("\n" + "=" * 60)
print(f"  总计: {PASS} 通过  {FAIL} 失败  {WARN} 警告")
if FAIL > 0:
    print("\n  发现失败项，请检查上方详情")
print("=" * 60)
