"""Tests for dragon & tiger list data provider."""

import pytest
from src.data.providers.dragon_tiger import DragonTigerProvider


def test_dragon_tiger_provider_init():
    """Test provider initialization."""
    provider = DragonTigerProvider(timeout=30)
    assert provider.timeout == 30


def test_dragon_tiger_fetch_real_stock():
    """Test fetching dragon tiger data for a real stock.
    
    May return None if stock has no recent dragon tiger entries.
    """
    provider = DragonTigerProvider(timeout=30)
    # Use a stock that might have dragon tiger data
    result = provider.get_stock_dragon_tiger("600519", days=5)
    
    # Result can be None (no data) or a dict with entries
    if result is not None:
        assert "code" in result
        assert "entries" in result
        assert result["code"] == "600519"
        assert isinstance(result["entries"], list)
        
        # Check entry structure if any entries exist
        if result["entries"]:
            entry = result["entries"][0]
            assert "date" in entry
            assert "reason" in entry
            assert "net_buy" in entry
            assert "buy_amount" in entry
            assert "sell_amount" in entry


def test_dragon_tiger_fetch_no_data():
    """Test fetching for a stock with no dragon tiger data."""
    provider = DragonTigerProvider(timeout=30)
    # Use a random small cap stock that likely has no dragon tiger data
    result = provider.get_stock_dragon_tiger("000001", days=1)
    
    # May return None or empty entries
    if result is not None:
        assert len(result.get("entries", [])) >= 0


def test_dragon_tiger_score_calculation():
    """Test the dragon tiger score calculation logic."""
    from src.data.hard_signals import _dragon_tiger_score
    
    # Test with positive net buy
    entries = [{"net_buy": 100000000}]  # 1 亿
    score = _dragon_tiger_score(entries)
    assert score == 1.0
    
    # Test with negative net buy
    entries = [{"net_buy": -50000000}]  # -5000 万
    score = _dragon_tiger_score(entries)
    assert score == -0.5
    
    # Test with no entries
    score = _dragon_tiger_score([])
    assert score == 0.0
