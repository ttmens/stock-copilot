"""Evolution engine — self-improving OODA loop for Stock Copilot."""

from .tracker import PerformanceTracker
from .optimizer import WeightOptimizer
from .stock_pool import StockPoolManager
from .engine import EvolutionEngine, EvolutionReport

__all__ = [
    "PerformanceTracker",
    "WeightOptimizer",
    "StockPoolManager",
    "EvolutionEngine",
    "EvolutionReport",
]
