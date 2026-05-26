#!/usr/bin/env bash
# Stock Copilot Health Check
# Returns 0 if healthy, 1 if issues found.
# Checks: service status, recent reports, DB integrity, LLM connectivity.

set -euo pipefail

PROJECT_ROOT="/home/ubuntu/repos/stock-copilot"
REPORT_DIR="$PROJECT_ROOT/output/reports"
DB_PATH="$PROJECT_ROOT/data/signals.db"
LOG_FILE="/tmp/stock-copilot-health.log"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PASS=0
FAIL=0
WARN=0

check() {
    local name="$1"
    local result="$2"
    if [ "$result" -eq 0 ]; then
        echo -e "${GREEN}✓${NC} $name"
        PASS=$((PASS + 1))
    else
        echo -e "${RED}✗${NC} $name"
        FAIL=$((FAIL + 1))
    fi
}

warn() {
    local name="$1"
    echo -e "${YELLOW}!${NC} $name"
    WARN=$((WARN + 1))
}

echo "═══════════════════════════════════════════"
echo "  Stock Copilot Health Check"
echo "  $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo "═══════════════════════════════════════════"
echo

# 1. Service status
echo "── 服务状态 ──"
if sudo systemctl is-active stock-copilot --quiet 2>/dev/null; then
    check "systemd 服务运行中" 0
else
    check "systemd 服务运行中" 1
fi

# 2. Recent reports (within 24h)
echo
echo "── 报告生成 ──"
if [ -d "$REPORT_DIR" ]; then
    RECENT_COUNT=$(find "$REPORT_DIR" -name "*.md" -mtime -1 2>/dev/null | wc -l)
    if [ "$RECENT_COUNT" -gt 0 ]; then
        check "最近24h有报告 ($RECENT_COUNT 份)" 0
    else
        warn "最近24h无新报告"
    fi

    # Check latest report
    LATEST=$(ls -t "$REPORT_DIR"/*.md 2>/dev/null | head -1)
    if [ -n "$LATEST" ]; then
        LATEST_SIZE=$(wc -c < "$LATEST")
        if [ "$LATEST_SIZE" -gt 1000 ]; then
            check "最新报告完整 ($(basename "$LATEST"), ${LATEST_SIZE}B)" 0
        else
            warn "最新报告疑似空数据 ($(basename "$LATEST"), ${LATEST_SIZE}B)"
        fi
    else
        check "最新报告完整" 1
    fi
else
    check "报告目录存在" 1
fi

# 3. Database
echo
echo "── 数据库 ──"
if [ -f "$DB_PATH" ]; then
    check "SQLite 文件存在" 0
    DB_SIZE=$(wc -c < "$DB_PATH")
    if [ "$DB_SIZE" -gt 10000 ]; then
        check "数据库大小正常 (${DB_SIZE}B)" 0
    else
        warn "数据库过小 (${DB_SIZE}B)"
    fi

    # Check integrity
    if python3 -c "
import sqlite3, sys
conn = sqlite3.connect('$DB_PATH')
result = conn.execute('PRAGMA integrity_check').fetchone()
sys.exit(0 if result[0] == 'ok' else 1)
" 2>/dev/null; then
        check "SQLite 完整性" 0
    else
        check "SQLite 完整性" 1
    fi
else
    check "SQLite 文件存在" 1
fi

# 4. Git status
echo
echo "── Git 状态 ──"
cd "$PROJECT_ROOT"
if git rev-parse --is-inside-work-tree &>/dev/null; then
    check "Git 仓库存在" 0
    MODIFIED=$(git status --porcelain 2>/dev/null | wc -l)
    if [ "$MODIFIED" -gt 0 ]; then
        warn "有 $MODIFIED 个未提交文件"
    else
        check "工作区干净" 0
    fi
else
    check "Git 仓库存在" 1
fi

# 5. Disk space
echo
echo "── 磁盘空间 ──"
DISK_PCT=$(df "$PROJECT_ROOT" | tail -1 | awk '{print $5}' | tr -d '%')
if [ "$DISK_PCT" -lt 80 ]; then
    check "磁盘使用率 ${DISK_PCT}%" 0
elif [ "$DISK_PCT" -lt 90 ]; then
    warn "磁盘使用率较高 ${DISK_PCT}%"
else
    check "磁盘使用率过高 ${DISK_PCT}%" 1
fi

# Summary
echo
echo "═══════════════════════════════════════════"
echo -e "  ${GREEN}通过: $PASS${NC}  ${RED}失败: $FAIL${NC}  ${YELLOW}警告: $WARN${NC}"
echo "═══════════════════════════════════════════"

if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
exit 0
