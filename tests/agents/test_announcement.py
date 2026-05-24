"""Tests for announcement analysis agent."""

import pytest
import asyncio
from src.agents.announcement import AnnouncementAgent
from src.data.models import AgentResult, AgentStatus


@pytest.mark.asyncio
async def test_announcement_agent_no_announcements():
    """Test agent behavior when no announcements provided."""
    agent = AnnouncementAgent()
    result = await agent.analyze("600519", "贵州茅台", [])
    
    assert result.status == AgentStatus.UNAVAILABLE
    assert result.sentiment == "neutral"
    assert result.summary == "无近期公告"
    assert result.raw_json["key_events"] == []


@pytest.mark.asyncio
async def test_announcement_agent_with_announcements():
    """Test agent behavior with real announcements.
    
    This test uses the real LLM client, so it may fail if API is unavailable.
    """
    agent = AnnouncementAgent()
    
    announcements = [
        "贵州茅台：2026 年一季度净利润同比增长 15%",
        "贵州茅台：关于控股股东增持计划完成的公告",
    ]
    
    result = await agent.analyze("600519", "贵州茅台", announcements)
    
    # Result depends on LLM response
    assert result.agent_name == "announcement"
    assert result.status in [AgentStatus.OK, AgentStatus.UNAVAILABLE]
    assert result.sentiment in ["bullish", "bearish", "neutral"]
    assert "key_events" in result.raw_json
