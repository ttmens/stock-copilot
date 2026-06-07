# C4 Level 1 — System Context Diagram

## Stock Copilot (智策 NexStrat) — 系统上下文

```mermaid
graph TB
    subgraph External["外部角色"]
        User["👤 个人投资者<br/>(唯一用户)"]
        GitHub["🐙 GitHub Pages<br/>(静态站托管)"]
    end

    subgraph LLM_Providers["LLM 服务"]
        DeepSeek["DeepSeek API"]
        OpenAI["OpenAI 兼容 API"]
    end

    subgraph Data_Providers["行情数据源"]
        AkShare["AkShare<br/>(A股行情/龙虎榜)"]
        Tencent["腾讯行情<br/>(实时报价)"]
        Sina["新浪财经<br/>(备用行情)"]
        EastMoney["东方财富<br/>(资金流向)"]
    end

    subgraph Notify["通知渠道"]
        WeCom["企业微信 Webhook"]
        Email["SMTP 邮件"]
    end

    StockCopilot["🏦 Stock Copilot<br/>(智策 NexStrat)<br/>A股 AI 智能投研助手<br/>v3.0.0-alpha"]

    User -->|"CLI / Web UI<br/>触发分析、管理自选"| StockCopilot
    StockCopilot -->|"生成静态 HTML/JSON"| GitHub
    StockCopilot -->|"LLM 分析请求"| DeepSeek
    StockCopilot -->|"LLM 分析请求"| OpenAI
    StockCopilot -->|"行情数据获取"| AkShare
    StockCopilot -->|"实时报价"| Tencent
    StockCopilot -->|"备用行情"| Sina
    StockCopilot -->|"资金流向"| EastMoney
    StockCopilot -->|"推送分析报告"| WeCom
    StockCopilot -->|"推送分析报告"| Email

    style StockCopilot fill:#7b3ff2,color:#fff
    style User fill:#4CAF50,color:#fff
    style GitHub fill:#333,color:#fff
```

## 关键关系说明

| 关系 | 协议 | 频率 | 说明 |
|------|------|------|------|
| User → System | HTTP/CLI | 按需 | FastAPI :8000 + CLI 命令 |
| System → GitHub | Git push | 每日 1-2 次 | 静态站发布 |
| System → LLM | HTTPS/REST | 每只股票 2-4 次 | 技术/资金/基本面/公告分析 + 辩论 |
| System → 行情 | HTTPS/REST | 每日 + 盘中 2min | AkShare 为主，腾讯/新浪备用 |
| System → 通知 | Webhook/SMTP | 分析完成后 | 推送报告摘要 |
