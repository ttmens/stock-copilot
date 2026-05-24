---
name: stock-copilot-self-check
description: Use when verifying Stock Copilot system health — configuration, data sources, LLM providers, git security, report/site generation, API routes, and test suite. Includes auto-fix capability.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [stock-copilot, self-check, health, verification, maintenance]
    related_skills: [systematic-debugging, requesting-code-review]
---

# Stock Copilot 系统自检

## Overview

Stock Copilot 全链路系统的自动化健康检查工具，覆盖 10 大检查维度、46 个检查项。用于：
- 部署后验证系统完整性
- 日常巡检发现潜在问题
- 代码修改后回归验证
- 发现可修复问题时自动修复

核心脚本位于 `scripts/self_check.py`，无需额外依赖，直接运行即可。

## When to Use

- 完成代码修改后运行回归检查
- 用户要求"检查系统状态"或"跑一下自检"
- 部署新版本到服务器后验证
- 数据源/API 异常时诊断根因
- 定期巡检（可配合 cron 任务）

**不要用于**：单次代码审查（用 `requesting-code-review`）、复杂 bug 根因分析（用 `systematic-debugging`）

## Quick Start

```bash
# 全量检查（含网络请求）
cd /home/ubuntu/repos/stock-copilot && python scripts/self_check.py

# 快速检查（跳过网络请求）
python scripts/self_check.py --quick

# 检查后自动修复可修复项
python scripts/self_check.py --fix
```

## Check Categories (10 个维度)

| # | 维度 | 检查项数 | 说明 |
|---|------|---------|------|
| 1 | 配置检查 | ~5 | settings.yaml 有效性、.env 存在、API Key 格式、Settings 加载 |
| 2 | 模块导入 | ~1 | 所有 src/ 模块可正常导入 |
| 3 | 依赖检查 | ~2 | requirements.txt 与已安装包的一致性 |
| 4 | Git 安全 | ~4 | .env 未追踪、.gitignore 排除、历史无 Key 泄露 |
| 5 | 数据源连通性 | 3 | 东财 push2、新浪 K 线、腾讯行情（网络请求） |
| 6 | LLM Provider | ~3 | DeepSeek/DashScope 注册状态 + 实际调用验证 |
| 7 | 报告生成 | 4 | Markdown 内容、免责声明、输出目录、文件写入 |
| 8 | 站点生成 | 5 | HTML 有效性、DOCTYPE、viewport、CSS、标题 |
| 9 | API 服务 | 5 | /health、/analyze、/reports/latest 等路由注册 |
| 10 | 测试套件 | 2 | pytest 执行结果统计 |

## Interpreting Results

### Exit Codes
- `0`: 所有 error 级别检查通过（可能有 warning）
- `1`: 存在 error 级别失败

### Severity Levels
- **error (❌)**: 必须修复的问题（配置缺失、模块导入失败、免责声明缺失等）
- **warning (⚠️)**: 建议关注但不阻断运行的问题（数据源短暂不可用、测试数量少等）
- **info (✅)**: 正常通过项

### Auto-Fixable Items

以下问题可通过 `--fix` 自动修复：

| 问题 | 修复动作 |
|------|---------|
| .env 被 Git 追踪 | `git rm --cached .env` |
| .gitignore 未排除 .env | 追加 `.env` 到 .gitignore |
| 缺失 Python 依赖 | `uv pip install <missing>` |

## Known Warnings (预期中的警告)

### Eastmoney push2 502 / 连接失败
当前服务器网络环境对东财域名有部分限制（push2his、search-api 被屏蔽）。
- 这是已知基础设施限制
- 系统已实现降级链：东财 → 新浪 → 腾讯
- 自检中此检查标记为 warning（非 error），不影响整体通过状态

## Common Pitfalls

1. **`get_settings()` 缓存污染**：`src.config.get_settings()` 使用 `@lru_cache`。自检脚本已调用 `cache_clear()`，但如果你在自检后运行其他代码，记得清理缓存或重启进程。

2. **LLM "json" 关键词要求**：DeepSeek 和 DashScope 使用 `response_format: json_object` 时，prompt 中必须包含 "json" 字样（不区分大小写但有些 provider 实现有 bug）。`src/llm/client.py` 的 `SYSTEM_PROMPT` 和自检中的测试 prompt 都已包含此关键词。如果自建测试请求，务必确保 prompt 中有 "json"。

3. **`generate_site()` 返回值是文件路径**：该函数返回 `site/index.html` 路径字符串，不是 HTML 内容。需要读取文件内容才能检查 HTML。自检脚本已正确处理。

4. **快速模式 `--quick` 跳过网络检查**：数据源连通性和 LLM 实际调用不会执行。适用于离线环境或只想验证代码完整性的场景。

5. **`.env` 中 Key 被截断**：历史上出现过 Key 写入时被截断的问题。自检会验证 Key 格式（正则匹配），如果格式不对会报 error。

## Verification Checklist

自检通过后，应满足：
- [x] 45+ 项检查通过（允许 1-2 个 warning）
- [x] 0 个 error 级别失败
- [x] API Key 格式正确
- [x] .env 未被 Git 追踪
- [x] 免责声明存在于报告模板中
- [x] LLM Provider 可实际调用（非仅配置）
- [x] pytest 测试全部通过

## One-Shot Recipes

### 日常巡检
```bash
cd /home/ubuntu/repos/stock-copilot && python scripts/self_check.py
```

### 部署后验证
```bash
cd /home/ubuntu/repos/stock-copilot && python scripts/self_check.py --fix
```

### CI/CD 集成
```bash
cd /home/ubuntu/repos/stock-copilot && python scripts/self_check.py --quick
# 检查退出码
echo $?
```

### Cron 定时自检（配合 Hermes）
```
# 每天 07:00 运行快速自检，发现问题通知用户
cronjob: create with prompt "Run python scripts/self_check.py --quick in /home/ubuntu/repos/stock-copilot and report any failures"
schedule: "0 7 * * *"
```

### 数据源专项诊断
```bash
python scripts/self_check.py 2>&1 | grep -A2 "数据源"
```

## Extending the Self-Check

要添加新的检查项，在 `scripts/self_check.py` 中：
1. 新增 `check_<category>()` 函数
2. 在 `main()` 中调用
3. 使用 `report.add(name, category, passed, message, fixable, fix_command, severity)` 添加结果
4. fixable=True 且 fix_command 不为空时，`--fix` 模式会自动执行修复
