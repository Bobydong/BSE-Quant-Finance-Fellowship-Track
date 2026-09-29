"""BSE Quant Backtester — a teaching backtester for the BSE fellowship."""

from .strategy import Strategy
from .data import (load, split, available_datasets, infer_periods_per_year,
                   DEFAULT_PERIODS_PER_YEAR)
from .engine import run, cost_sweep, BacktestResult

__all__ = ["Strategy", "load", "split", "available_datasets",
           "infer_periods_per_year", "DEFAULT_PERIODS_PER_YEAR",
           "run", "cost_sweep", "BacktestResult"]
__version__ = "0.2.0"
