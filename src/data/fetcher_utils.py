"""Shared fetcher utilities."""

from src.data.models import MovingAverages


def calc_ma(closes: list[float]) -> MovingAverages:
    """Calculate MA5/10/20 from a list of closing prices."""
    def ma(n):
        return sum(closes[-n:]) / n if len(closes) >= n else None
    return MovingAverages(ma5=ma(5), ma10=ma(10), ma20=ma(20))
