"""BSE Quant Backtester — a teaching backtester for the BSE fellowship."""

from .strategy import Strategy, EventStrategy, StrategyError
from .data import (load, split, available_datasets, infer_periods_per_year,
                   DEFAULT_PERIODS_PER_YEAR)
from .engine import run, run_positions, cost_sweep, trade_log, BacktestResult

__all__ = ["Strategy", "EventStrategy", "StrategyError", "load", "split",
           "available_datasets", "infer_periods_per_year",
           "DEFAULT_PERIODS_PER_YEAR", "run", "run_positions", "cost_sweep",
           "trade_log", "BacktestResult"]
__version__ = "0.3.0"
