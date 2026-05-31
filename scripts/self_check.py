#!/usr/bin/env python3
"""Comprehensive system self-check — Phase E reliability audit.

Covers: API health, data integrity, CSS/HTML consistency, scheduler status,
DB health, file sync, signal quality, and evolution engine.
"""
import json
import logging
import sqlite3
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

PASS = 0
FAIL = 0
WARN = 0


def check(name: str, condition: bool, detail: str = "") -> bool:
    global PASS, FAIL
    if condition:
        PASS += 1
        logger.info(f"  ✅ {name}")
        return True
    else:
        FAIL += 1
        msg = f"  ❌ {name}"
        if detail:
            msg += f" — {detail}"
        logger.warning(msg)
        return False


def warn(name: str, detail: str = ""):
    global WARN
    WARN += 1
    msg = f"  ⚠️  {name}"
    if detail:
        msg += f" — {detail}"
    logger.warning(msg)


def main():
    project_root = Path(__file__).resolve().parent.parent
    logger.info("=" * 60)
    logger.info("🔍 智策 NexStrat — 系统深度自检")
    logger.info("=" * 60)

    # ── 1. API Service ──────────────────────────────────────────
    logger.info("\n📡 API 服务")
    try:
        r = subprocess.run(
            ["curl", "-s", "http://127.0.0.1:8000/health"],
            capture_output=True, text=True, timeout=10,
        )
        h = json.loads(r.stdout)
        check("API 可达", h.get("status") == "ok")
        check("版本 3.0.0-alpha", h.get("version") == "3.0.0-alpha", h.get("version"))
        check("自选股 > 0", h.get("watchlist_count", 0) > 0, str(h.get("watchlist_count", 0)))
        check("数据新鲜度", h.get("data_freshness") in ("fresh", "unknown"), h.get("data_freshness"))

        # System status endpoint
        r2 = subprocess.run(
            ["curl", "-s", "http://127.0.0.1:8000/api/system/status"],
            capture_output=True, text=True, timeout=10,
        )
        if r2.returncode == 0:
            s = json.loads(r2.stdout)
            check("系统状态端点", s.get("status") == "ok")
            if s.get("db_stats"):
                check("DB 信号数", s["db_stats"].get("signal_count", 0) > 0, str(s["db_stats"].get("signal_count", 0)))
        else:
            warn("系统状态端点不可用", f"exit code {r2.returncode}")

        # Static files via API
        for path in ["/index.html", "/app/stock.html", "/app/watchlist.html", "/assets/theme.css"]:
            r3 = subprocess.run(
                ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", f"http://127.0.0.1:8000{path}"],
                capture_output=True, text=True, timeout=5,
            )
            check(f"静态文件 {path}", r3.stdout == "200", f"HTTP {r3.stdout}")
    except Exception as e:
        check("API 连接", False, str(e))

    # ── 2. Data Integrity ───────────────────────────────────────
    logger.info("\n📊 数据完整性")
    latest_path = project_root / "docs" / "data" / "latest.json"
    if latest_path.exists():
        data = json.loads(latest_path.read_text())
        stocks = data.get("stocks", [])
        check("latest.json 存在", True, f"{len(stocks)} 只股票")

        # Name consistency
        bad_names = [s for s in stocks if s["name"] == s["code"]]
        check("股票名称完整", len(bad_names) == 0, f"{len(bad_names)} 只名称异常" if bad_names else "")

        # Score completeness
        no_score = [s for s in stocks if s.get("signal_breakdown", {}).get("final_score") is None]
        check("评分完整", len(no_score) == 0, f"{len(no_score)} 只缺失" if no_score else "")

        # Signal breakdown keys
        required_keys = ["hard_score", "soft_score", "gate_score", "final_score"]
        missing_keys = []
        for s in stocks[:5]:  # Check first 5
            sb = s.get("signal_breakdown", {})
            for k in required_keys:
                if k not in sb:
                    missing_keys.append(f"{s['code']}.{k}")
        check("信号分解键完整", len(missing_keys) == 0, str(missing_keys[:5]) if missing_keys else "")

        # Data freshness
        mtime = latest_path.stat().st_mtime
        age_hours = (time.time() - mtime) / 3600
        if age_hours < 24:
            check("数据新鲜", True, f"{age_hours:.1f} 小时前")
        elif age_hours < 72:
            warn("数据较旧", f"{age_hours:.1f} 小时前")
        else:
            check("数据过期", False, f"{age_hours:.1f} 小时前")
    else:
        check("latest.json", False, "文件不存在")

    # ── 3. CSS Design System ────────────────────────────────────
    logger.info("\n🎨 CSS 设计体系")
    css = (project_root / "docs" / "assets" / "theme.css").read_text()

    css_checks = [
        ("--signal-bull", "信号色板"),
        ("--signal-bear", "信号色板"),
        ("--dim-hard", "维度色板"),
        ("--dim-soft", "维度色板"),
        ("--dim-gate", "维度色板"),
        ("--dim-dragon", "维度色板"),
        ("--dim-announce", "维度色板"),
        ("--z-header", "z-index 栈"),
        ("--z-dropdown", "z-index 栈"),
        ("--z-bottom-nav", "z-index 栈"),
        ("--touch:", "触摸目标"),
        (".bottom-nav", "底部导航"),
        (".decision-card", "决策卡片"),
        (".dim-card", "维度卡片"),
        (".signal-badge", "信号徽章"),
        (".view-toggle", "视图切换"),
        (".stock-table", "表格视图"),
        (".compare-panel", "对比面板"),
        ("@media (min-width: 1200px)", "1200px 断点"),
        ("@media (min-width: 1600px)", "1600px 断点"),
        ("@media (min-width: 480px)", "480px 断点"),
        ("env(safe-area-inset-bottom", "刘海适配"),
        ("prefers-reduced-motion", "无障碍"),
    ]
    for pattern, desc in css_checks:
        check(f"{desc}", pattern in css, pattern[:30])

    # src and docs CSS in sync
    src_css = (project_root / "src" / "site" / "theme.css").read_text()
    check("CSS src/docs 同步", src_css == css, "内容不一致" if src_css != css else "")

    # ── 4. HTML Structure ───────────────────────────────────────
    logger.info("\n📄 HTML 结构")
    for page in ["index.html", "dashboard.html", "history.html"]:
        html = (project_root / "docs" / page).read_text()
        check(f"{page}: 底部导航", 'class="bottom-nav"' in html)
        check(f"{page}: header", 'class="site-header"' in html)

    idx = (project_root / "docs" / "index.html").read_text()
    check("首页: 动态路由", "app/stock.html?code=" in idx)
    check("首页: 视图切换", "view-toggle" in idx)
    check("首页: 对比面板", "compare-panel" in idx)
    check("首页: 表格视图", "table-view" in idx)
    check("首页: 决策卡片 ≥ 5", idx.count("decision-card") >= 5, str(idx.count("decision-card")))

    stock_html = (project_root / "docs" / "app" / "stock.html").read_text()
    check("个股: 88px padding", "88px" in stock_html)
    check("个股: 底部导航", 'class="bottom-nav"' in stock_html)

    # ── 5. DB Health ────────────────────────────────────────────
    logger.info("\n🗄️ 数据库健康")
    db_path = project_root / "data" / "signals.db"
    if db_path.exists():
        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()
        try:
            cur.execute("SELECT COUNT(*) FROM signals")
            count = cur.fetchone()[0]
            check("signals 表", count > 0, f"{count} 条记录")

            cur.execute("SELECT COUNT(DISTINCT code) FROM signals")
            unique = cur.fetchone()[0]
            check("唯一股票数", unique > 0, f"{unique} 只")

            # Check for orphaned records
            cur.execute("SELECT COUNT(*) FROM signals WHERE code IS NULL OR code = ''")
            orphaned = cur.fetchone()[0]
            check("无孤儿记录", orphaned == 0, f"{orphaned} 条" if orphaned else "")

            # DB file size
            size_mb = db_path.stat().st_size / 1024 / 1024
            check("DB 大小合理", size_mb < 100, f"{size_mb:.1f}MB")
        except Exception as e:
            check("DB 查询", False, str(e))
        finally:
            conn.close()
    else:
        warn("DB 不存在", "signals.db 未找到")

    # ── 6. Git Status ──────────────────────────────────────────
    logger.info("\n📦 Git 状态")
    r = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
    dirty = r.stdout.strip()
    check("工作区干净", dirty == "", f"{len(dirty.split(chr(10)))} 个文件" if dirty else "")

    r = subprocess.run(["git", "log", "-1", "--format=%s"], capture_output=True, text=True)
    check("最新提交", len(r.stdout.strip()) > 0, r.stdout.strip()[:80])

    # ── 7. Config Validation ────────────────────────────────────
    logger.info("\n⚙️ 配置验证")
    weights_path = project_root / "config" / "fusion_weights.json"
    if weights_path.exists():
        weights = json.loads(weights_path.read_text())
        total = weights.get("hard", 0) + weights.get("soft", 0) + weights.get("gate", 0) + weights.get("dragon_tiger", 0) + weights.get("announcement", 0)
        check("融合权重 sum=1.0", abs(total - 1.0) < 0.001, f"sum={total:.4f}")
        check("版本字段", "version" in weights)
    else:
        check("fusion_weights.json", False, "文件不存在")

    settings_path = project_root / "config" / "settings.yaml"
    check("settings.yaml", settings_path.exists())

    # ── 8. Scripts ─────────────────────────────────────────────
    logger.info("\n📜 脚本")
    for script in ["check_docs_ssot.py", "ui_acceptance.py", "self_check.py"]:
        script_path = project_root / "scripts" / script
        check(f"scripts/{script}", script_path.exists() and script_path.stat().st_size > 0)

    # ── Summary ────────────────────────────────────────────────
    logger.info("\n" + "=" * 60)
    total = PASS + FAIL + WARN
    logger.info(f"📊 自检结果: {PASS}/{total} 通过, {FAIL} 错误, {WARN} 警告")
    if FAIL > 0:
        logger.warning(f"❌ 有 {FAIL} 个错误需要修复")
    elif WARN > 0:
        logger.warning(f"⚠️  有 {WARN} 个警告值得关注")
    else:
        logger.info("✅ 系统状态良好，无错误无警告")
    logger.info("=" * 60)

    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
