#!/usr/bin/env python3
"""Stock Copilot 系统自检脚本 — 检查一致性、稳定性、可靠性。

用法:
    python scripts/self_check.py              # 全量检查
    python scripts/self_check.py --quick       # 快速检查（跳过网络请求）
    python scripts/self_check.py --fix         # 检查后自动修复可修复项
"""

import asyncio
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Optional

# ── Project root resolution ──────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

# ── ANSI colors ──────────────────────────────────────────────────────
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
BOLD = "\033[1m"
RESET = "\033[0m"
DIM = "\033[2m"


@dataclass
class CheckResult:
    name: str
    category: str
    passed: bool
    message: str
    fixable: bool = False
    fix_command: str = ""
    severity: str = "info"  # info, warning, error


@dataclass
class Report:
    checks: list[CheckResult] = field(default_factory=list)

    def add(self, name: str, category: str, passed: bool, message: str,
            fixable: bool = False, fix_command: str = "", severity: str = "info"):
        self.checks.append(CheckResult(name, category, passed, message, fixable, fix_command, severity))

    def summary(self) -> str:
        total = len(self.checks)
        passed = sum(1 for c in self.checks if c.passed)
        failed = total - passed
        errors = sum(1 for c in self.checks if not c.passed and c.severity == "error")
        warnings = sum(1 for c in self.checks if not c.passed and c.severity == "warning")
        return f"\n{'=' * 60}\n{BOLD}总检: {passed}/{total} 通过{RESET}  " \
               f"(❌ 错误={errors}, ⚠️  警告={warnings})\n{'=' * 60}"

    def fixable_items(self) -> list[CheckResult]:
        return [c for c in self.checks if c.fixable and not c.passed]


report = Report()


# ══════════════════════════════════════════════════════════════════════
# CHECK CATEGORIES
# ══════════════════════════════════════════════════════════════════════

# ── 1. Configuration ─────────────────────────────────────────────────
def check_config():
    """YAML 配置、.env 密钥格式、settings 加载。"""
    print(f"\n{CYAN}━━━ 配置检查 ━━━{RESET}")

    # 1.1 settings.yaml exists & valid YAML
    yaml_path = _PROJECT_ROOT / "config" / "settings.yaml"
    if yaml_path.exists():
        try:
            import yaml
            cfg = yaml.safe_load(yaml_path.read_text())
            assert isinstance(cfg, dict), "Not a YAML mapping"
            report.add("settings.yaml", "配置", True, f"YAML 有效，{len(cfg)} 个顶层键")
        except Exception as e:
            report.add("settings.yaml", "配置", False, f"YAML 解析失败: {e}",
                       severity="error")
    else:
        report.add("settings.yaml", "配置", False, "文件不存在", severity="error")

    # 1.2 .env exists
    env_path = _PROJECT_ROOT / ".env"
    if env_path.exists():
        content = env_path.read_text()
        report.add(".env", "配置", True, "文件存在")

        # 1.3 Key format validation (don't print values)
        for key_name, pattern, desc in [
            ("DEEPSEEK_API_KEY", r"sk-[a-f0-9]{20,}", "DeepSeek Key 格式"),
            ("DASHSCOPE_API_KEY", r"sk-sp-[a-f0-9]{20,}", "DashScope Key 格式"),
        ]:
            match = re.search(rf"^{key_name}=(.+)$", content, re.MULTILINE)
            if match:
                val = match.group(1).strip()
                if re.match(pattern, val):
                    report.add(f"{key_name} 格式", "配置", True, desc)
                else:
                    report.add(f"{key_name} 格式", "配置", False,
                               f"{desc} 异常 (len={len(val)})", severity="error")
            else:
                report.add(f"{key_name} 格式", "配置", False,
                           f"{key_name} 未在 .env 中定义", severity="warning")
    else:
        report.add(".env", "配置", False, "文件不存在，无法加载密钥", severity="error")

    # 1.4 Settings singleton loadable
    try:
        from src.config import get_settings
        get_settings.cache_clear()
        s = get_settings()
        report.add("Settings 加载", "配置", True,
                   f"LLM mode={s.llm.mode}, providers={len(s.llm.providers)}")
    except Exception as e:
        report.add("Settings 加载", "配置", False, f"{e}", severity="error")


# ── 2. Module Imports ────────────────────────────────────────────────
def check_imports():
    """所有 src 模块可正常导入。"""
    print(f"\n{CYAN}━━━ 模块导入检查 ━━━{RESET}")

    modules = [
        "src.config",
        "src.data.models",
        "src.data.fetcher",
        "src.data.fetcher_utils",
        "src.data.calendar",
        "src.data.providers.eastmoney",
        "src.data.providers.sina",
        "src.data.providers.tencent",
        "src.llm.client",
        "src.llm.config",
        "src.agents.base",
        "src.agents.technical",
        "src.agents.fundamental",
        "src.agents.capital",
        "src.reports.generator",
        "src.site.generator",
        "src.notify.wecom",
        "src.notify.email",
        "src.scheduler.jobs",
        "src.api.routes",
        "src.publish.github",
        "src.orchestrator.pipeline",
        "src.main",
    ]

    passed_count = 0
    failed_modules = []
    for mod in modules:
        try:
            __import__(mod)
            passed_count += 1
        except Exception as e:
            failed_modules.append((mod, str(e)))
            report.add(f"导入: {mod}", "模块", False, str(e), severity="error")

    report.add(f"模块导入 ({passed_count}/{len(modules)})", "模块",
               len(failed_modules) == 0,
               f"{passed_count}/{len(modules)} 模块可导入" +
               (f"，失败: {', '.join(m[0] for m in failed_modules)}" if failed_modules else ""))


# ── 3. Dependencies ──────────────────────────────────────────────────
def check_dependencies():
    """requirements.txt vs 已安装包的版本一致性。"""
    print(f"\n{CYAN}━━━ 依赖检查 ━━━{RESET}")

    req_path = _PROJECT_ROOT / "requirements.txt"
    if not req_path.exists():
        report.add("requirements.txt", "依赖", False, "文件不存在", severity="error")
        return

    try:
        import importlib.metadata as im
        reqs = {}
        for line in req_path.read_text().strip().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # Parse package name (ignore version spec for simplicity)
            name = re.split(r"[>=<!]", line)[0].strip().lower().replace("-", "_")
            reqs[name] = line

        missing = []
        for pkg, spec in reqs.items():
            try:
                ver = im.version(pkg.replace("_", "-"))
                report.add(f"已安装: {spec}", "依赖", True, f"版本 {ver}")
            except im.PackageNotFoundError:
                missing.append(spec)
                report.add(f"缺失: {spec}", "依赖", False, "未安装", severity="warning")

        if missing:
            report.add("依赖完整性", "依赖", False,
                       f"缺失: {', '.join(missing)}",
                       fixable=True,
                       fix_command=f"cd {_PROJECT_ROOT} && uv pip install {' '.join(missing)}")
        else:
            report.add("依赖完整性", "依赖", True, f"全部 {len(reqs)} 个依赖已安装")
    except Exception as e:
        report.add("依赖检查", "依赖", False, str(e), severity="error")


# ── 4. Git Security ──────────────────────────────────────────────────
def check_git_security():
    """Git 安全：Key 泄露检测、.env 追踪状态。"""
    print(f"\n{CYAN}━━━ Git 安全检查 ━━━{RESET}")

    git_dir = _PROJECT_ROOT / ".git"
    if not git_dir.exists():
        report.add("Git 仓库", "安全", False, "不是 Git 仓库", severity="warning")
        return

    # 4.1 .env not tracked
    try:
        result = subprocess.run(
            ["git", "ls-files", "--exclude-standard", ".env"],
            capture_output=True, text=True, cwd=_PROJECT_ROOT, timeout=10
        )
        env_tracked = result.stdout.strip() != ""
        if env_tracked:
            report.add(".env 追踪状态", "安全", False, "⚠️ .env 被 Git 追踪！",
                       severity="error", fixable=True,
                       fix_command=f"cd {_PROJECT_ROOT} && git rm --cached .env && echo '.env' >> .gitignore")
        else:
            report.add(".env 追踪状态", "安全", True, ".env 未追踪（安全）")
    except Exception as e:
        report.add(".env 追踪状态", "安全", False, str(e), severity="warning")

    # 4.2 .gitignore contains .env
    gitignore = _PROJECT_ROOT / ".gitignore"
    if gitignore.exists():
        content = gitignore.read_text()
        if ".env" in content:
            report.add(".gitignore .env", "安全", True, ".gitignore 已排除 .env")
        else:
            report.add(".gitignore .env", "安全", False, ".gitignore 未排除 .env",
                       severity="error", fixable=True,
                       fix_command=f"echo '.env' >> {_PROJECT_ROOT}/.gitignore")
    else:
        report.add(".gitignore", "安全", False, "文件不存在", severity="warning")

    # 4.3 No keys in git history
    try:
        patterns = ["sk-sp-", "sk-82c279"]
        leaked = []
        for pat in patterns:
            result = subprocess.run(
                ["git", "log", "--all", "-p", "--grep", pat],
                capture_output=True, text=True, cwd=_PROJECT_ROOT, timeout=30
            )
            if pat in result.stdout:
                leaked.append(pat)

        if leaked:
            report.add("Git 历史 Key", "安全", False,
                       f"⚠️ 以下模式出现在 Git 历史中: {', '.join(leaked)}",
                       severity="error")
        else:
            report.add("Git 历史 Key", "安全", True, "无 API Key 泄露")
    except Exception as e:
        report.add("Git 历史 Key", "安全", False, str(e), severity="warning")


# ── 5. Data Source Connectivity ──────────────────────────────────────
async def check_data_sources():
    """数据源连通性：东财、新浪、腾讯。"""
    print(f"\n{CYAN}━━━ 数据源连通性 ━━━{RESET}")

    import httpx

    sources = [
        {
            "name": "Eastmoney push2 (PE/PB/市值)",
            "url": "https://push2.eastmoney.com/api/qt/stock/get",
            "params": {
                "secid": "1.600519",
                "fields": "f170,f171,f173,f162",
                "ut": "fa5fd1943c7b386f172d6893dbfba10b",
                "invt": 2,
            },
            "timeout": 10,
        },
        {
            "name": "Sina K 线",
            "url": "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData",
            "params": {"symbol": "sh600519", "scale": "240", "ma": "no", "datalen": "5"},
            "timeout": 10,
        },
        {
            "name": "Tencent 实时行情",
            "url": "https://qt.gtimg.cn/q=sh600519",
            "params": {},
            "timeout": 10,
            "check_fn": lambda r: len(r.content) > 50 and r.status_code == 200,
        },
    ]

    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        for src in sources:
            try:
                resp = await client.get(src["url"], params=src["params"])
                check_fn = src.get("check_fn", lambda r: 200 <= r.status_code < 300)
                ok = check_fn(resp)
                status_detail = f"HTTP {resp.status_code}, {len(resp.content)} bytes"
                if ok:
                    report.add(f"数据源: {src['name']}", "数据源", True, status_detail)
                else:
                    # 5xx 是服务端问题，算 warning 不是 error
                    sev = "warning" if resp.status_code >= 500 else "error"
                    report.add(f"数据源: {src['name']}", "数据源", False,
                               f"响应异常: {status_detail}", severity=sev)
            except Exception as e:
                report.add(f"数据源: {src['name']}", "数据源", False,
                           f"连接失败: {e}", severity="warning")


# ── 6. LLM Provider Health ───────────────────────────────────────────
async def check_llm_providers():
    """LLM Provider 连通性。"""
    print(f"\n{CYAN}━━━ LLM Provider 检查 ━━━{RESET}")

    try:
        from src.llm.client import get_llm_client
        client = get_llm_client()
        status = client.status()
        providers = status.get("providers", [])

        report.add("LLMClient 初始化", "LLM", True,
                   f"{len(providers)} 个 Provider 已注册")

        for p in providers:
            name = p.get("name", "unknown")
            model = p.get("model", "unknown")
            avail = p.get("available")

            if avail:
                report.add(f"LLM: {name} ({model})", "LLM", True, "可用")
            elif avail is None:
                report.add(f"LLM: {name} ({model})", "LLM", True,
                           f"已配置（未测试，首次调用时验证）")
            else:
                report.add(f"LLM: {name} ({model})", "LLM", False,
                           "不可用", severity="warning")
    except Exception as e:
        report.add("LLM Provider", "LLM", False, str(e), severity="error")

    # 6.1 快速 LLM 连通测试（发送一个极简请求）
    try:
        from src.llm.client import get_llm_client
        client = get_llm_client()
        if client.available_providers:
            # 发送一个轻量请求验证实际连通性
            result = await client.chat_json(
                system_prompt="Reply with json: {\"test\": true}",
                user_prompt="Test - respond with json",
            )
            if result.get("test") is True or result.get("status"):
                report.add("LLM 实际调用", "LLM", True, "连通性验证成功")
            else:
                report.add("LLM 实际调用", "LLM", False,
                           f"返回异常: {json.dumps(result, ensure_ascii=False)[:100]}",
                           severity="warning")
        else:
            report.add("LLM 实际调用", "LLM", False, "无可用 Provider",
                       severity="warning")
    except Exception as e:
        err_msg = str(e)
        # 超时不算 error（网络问题），算 warning
        sev = "warning" if "timeout" in err_msg.lower() or "connection" in err_msg.lower() else "error"
        report.add("LLM 实际调用", "LLM", False,
                   f"调用失败: {err_msg[:120]}", severity=sev)


# ── 7. Report Generation ─────────────────────────────────────────────
def check_report_generation():
    """报告生成完整性：只读验证现有报告文件，绝不生成测试数据。"""
    print(f"\n{CYAN}━━━ 报告生成检查 ━━━{RESET}")

    try:
        out_dir = _PROJECT_ROOT / "output" / "reports"
        report.add("输出目录", "报告", out_dir.is_dir(), str(out_dir))

        # Find the most recent report file
        report_files = sorted(out_dir.glob("*.md"), key=lambda f: f.stat().st_mtime, reverse=True)
        if not report_files:
            report.add("报告文件", "报告", False, "无报告文件", severity="warning")
            return

        latest_report = report_files[0]
        report.add("最新报告", "报告", True, f"{latest_report.name} ({latest_report.stat().st_size} bytes)")

        # Check file is non-empty
        content = latest_report.read_text(encoding="utf-8")
        report.add("报告非空", "报告", len(content) > 100, f"{len(content)} 字符")

        # Check disclaimer (read-only)
        disclaimer_found = any(kw in content for kw in [
            "不构成投资建议", "不构成任何投资建议", "免责声明", "投资有风险",
            "仅供参考", "DISCLAIMER",
        ])
        if disclaimer_found:
            report.add("免责声明", "报告", True, "已包含")
        else:
            report.add("免责声明", "报告", False,
                       "报告中未找到免责声明关键词", severity="error")

        # Check JSON data integrity (read-only)
        import json
        for json_path in [_PROJECT_ROOT / "site" / "data" / "latest.json",
                          _PROJECT_ROOT / "docs" / "data" / "latest.json"]:
            if json_path.exists():
                data = json.loads(json_path.read_text())
                stocks = data.get("stocks", [])
                report.add(f"latest.json ({json_path.parent.parent.name})", "数据",
                           len(stocks) >= 10, f"{len(stocks)} stocks")

    except Exception as e:
        import traceback
        report.add("报告检查", "报告", False, f"{e}\n{traceback.format_exc()}",
                   severity="error")


# ── 8. Site Generation ───────────────────────────────────────────────
def check_site_generation():
    """静态站点生成：验证现有 HTML 文件，不再生成测试报告覆盖线上数据。"""
    print(f"\n{CYAN}━━━ 站点生成检查 ━━━{RESET}")

    try:
        from pathlib import Path
        import re
        from src.config import get_settings
        settings = get_settings()
        site_dir = Path(settings.site.output_dir)
        index_path = site_dir / "index.html"

        if not index_path.exists():
            report.add("站点: index.html", "站点", False, "index.html 不存在", severity="error")
            return

        html = index_path.read_text(encoding="utf-8")

        # Count stock links in index
        import re
        stock_links = len(re.findall(r'href="stock/\d+\.html"', html))

        # Check latest.json
        data_dir = Path(settings.site.data_dir)
        latest_path = data_dir / "latest.json"
        latest_stocks = 0
        if latest_path.exists():
            import json
            d = json.loads(latest_path.read_text())
            latest_stocks = len(d.get("stocks", []))

        checks = {
            "HTML 输出": len(html) > 500,
            "DOCTYPE": "<!DOCTYPE" in html or "<html" in html.lower(),
            "viewport 响应式": "viewport" in html.lower(),
            "深色/CSS": "<style" in html.lower() or "stylesheet" in html.lower() or "theme.css" in html.lower(),
            "Stock 标题": "stock" in html.lower() or "A股" in html or "决策" in html,
            f"个股链接数 ({stock_links})": stock_links > 0,
            f"latest.json 股票数 ({latest_stocks})": latest_stocks > 0,
        }

        for check_name, ok in checks.items():
            report.add(f"站点: {check_name}", "站点", ok, "" if ok else "未检测到")

    except Exception as e:
        report.add("站点生成", "站点", False, str(e), severity="error")


# ── 9. API Server ────────────────────────────────────────────────────
def check_api_server():
    """FastAPI 路由注册。"""
    print(f"\n{CYAN}━━━ API 服务检查 ━━━{RESET}")

    try:
        from src.api.routes import app
        routes = [r.path for r in app.routes if hasattr(r, "path")]

        required = ["/health", "/analyze", "/reports/latest", "/site/latest.json"]
        for r in required:
            present = r in routes
            report.add(f"路由: {r}", "API", present, "" if present else "缺失")

        report.add(f"API 路由总数", "API", True, f"{len(routes)} 个路由")
    except Exception as e:
        report.add("API 服务", "API", False, str(e), severity="error")


# ── 10. Tests ────────────────────────────────────────────────────────
def check_tests():
    """pytest 测试套件。"""
    print(f"\n{CYAN}━━━ 测试套件检查 ━━━{RESET}")

    tests_dir = _PROJECT_ROOT / "tests"
    if not tests_dir.exists():
        report.add("测试目录", "测试", False, "tests/ 不存在", severity="warning")
        return

    test_files = list(tests_dir.glob("test_*.py"))
    report.add("测试文件", "测试", True, f"{len(test_files)} 个文件")

    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/", "-v", "--tb=short", "-q"],
            capture_output=True, text=True, cwd=_PROJECT_ROOT, timeout=60
        )
        # Parse output for pass/fail count
        output = result.stdout + result.stderr
        match = re.search(r"(\d+) passed", output)
        if match:
            passed = int(match.group(1))
            report.add("pytest 结果", "测试", True, f"{passed} 个测试通过")
        elif "no tests ran" in output.lower():
            report.add("pytest 结果", "测试", False, "未找到可运行的测试",
                       severity="warning")
        else:
            failed_match = re.search(r"(\d+) failed", output)
            if failed_match:
                report.add("pytest 结果", "测试", False,
                           f"{failed_match.group(1)} 个测试失败", severity="error")
            else:
                report.add("pytest 结果", "测试", result.returncode == 0,
                           output.strip()[-200:] if output else "无输出")
    except subprocess.TimeoutExpired:
        report.add("pytest 结果", "测试", False, "超时 (60s)", severity="warning")
    except Exception as e:
        report.add("pytest 结果", "测试", False, str(e), severity="warning")


# ══════════════════════════════════════════════════════════════════════
# AUTO-FIX
# ══════════════════════════════════════════════════════════════════════
def auto_fix():
    """自动修复可修复的问题。"""
    items = report.fixable_items()
    if not items:
        print(f"\n{GREEN}✅ 没有需要自动修复的问题{RESET}")
        return

    print(f"\n{YELLOW}━━━ 自动修复 ({len(items)} 项) ━━━{RESET}")
    for item in items:
        print(f"\n  🔧 {item.name}: {item.message}")
        print(f"     命令: {item.fix_command}")
        try:
            result = subprocess.run(
                item.fix_command, shell=True, capture_output=True, text=True,
                timeout=30, cwd=_PROJECT_ROOT
            )
            if result.returncode == 0:
                print(f"     {GREEN}✅ 修复成功{RESET}")
                item.passed = True
                item.message = "已自动修复"
            else:
                print(f"     {RED}❌ 修复失败: {result.stderr.strip()}{RESET}")
        except Exception as e:
            print(f"     {RED}❌ 异常: {e}{RESET}")


# ══════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════
def main():
    quick_mode = "--quick" in sys.argv
    fix_mode = "--fix" in sys.argv

    print(f"{BOLD}{'=' * 60}")
    print(f"  🏗️  Stock Copilot 系统自检")
    print(f"  {'=' * 60}{RESET}")
    print(f"{DIM}  项目: {_PROJECT_ROOT}")
    print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  模式: {'快速（跳过网络请求）' if quick_mode else '全量'}{RESET}")

    # Sync checks (no network)
    check_config()
    check_imports()
    check_dependencies()
    check_git_security()
    check_report_generation()
    check_site_generation()
    check_api_server()
    check_tests()

    if not quick_mode:
        # Async checks (network)
        asyncio.run(check_data_sources())
        asyncio.run(check_llm_providers())

    # Auto-fix if requested
    if fix_mode:
        auto_fix()

    # Summary
    print(report.summary())

    # Detailed failure report
    failed = [c for c in report.checks if not c.passed]
    if failed:
        print(f"\n{BOLD}📋 未通过项:{RESET}")
        for c in failed:
            icon = "❌" if c.severity == "error" else "⚠️"
            fix_tag = f" {YELLOW}[可修复]{RESET}" if c.fixable else ""
            print(f"  {icon} [{c.category}] {c.name}: {c.message}{fix_tag}")

    # Print final status
    all_passed = all(c.passed for c in report.checks if c.severity == "error")
    if not all_passed:
        sys.exit(1)


if __name__ == "__main__":
    main()
