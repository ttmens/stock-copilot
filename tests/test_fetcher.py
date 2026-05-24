"""Tests for data fetcher."""

from datetime import date
from unittest.mock import patch, MagicMock

import pytest

from src.data.models import OHLCVBar, MovingAverages, StockSnapshot
from src.data.fetcher import calc_ma


class TestCalcMA:
    def test_basic_ma(self):
        closes = [10.0] * 25
        ma = calc_ma(closes)
        assert ma.ma5 == 10.0
        assert ma.ma10 == 10.0
        assert ma.ma20 == 10.0

    def test_insufficient_data(self):
        closes = [10.0, 11.0]
        ma = calc_ma(closes)
        assert ma.ma5 is None
        assert ma.ma10 is None
        assert ma.ma20 is None

    def test_partial_data(self):
        closes = [float(i) for i in range(1, 16)]  # 15 values
        ma = calc_ma(closes)
        assert ma.ma5 is not None
        assert ma.ma10 is not None
        assert ma.ma20 is None  # only 15 values


class TestStockSnapshot:
    def test_empty_snapshot(self):
        from datetime import datetime
        snap = StockSnapshot(code="000001", name="测试", fetched_at=datetime.now())
        assert snap.code == "000001"
        assert len(snap.bars) == 0
        assert snap.fetch_errors == []

    def test_snapshot_with_bars(self):
        from datetime import datetime
        bars = [
            OHLCVBar(
                date=date(2026, 5, 20),
                open=100.0, high=105.0, low=99.0, close=103.0,
                volume=1000000.0,
            )
        ]
        snap = StockSnapshot(
            code="600519", name="茅台",
            fetched_at=datetime.now(),
            bars=bars,
            fetch_errors=["capital: unavailable"],
        )
        assert len(snap.bars) == 1
        assert len(snap.fetch_errors) == 1
        assert snap.bars[0].close == 103.0
