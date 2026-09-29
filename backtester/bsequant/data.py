"""Data loading and preparation.

Fellows never compute returns themselves - this module does it once,
consistently, so every strategy is evaluated on identical inputs.
"""

from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# Fallback used only when a frequency cannot be inferred and none is given.
DEFAULT_PERIODS_PER_YEAR = 365

# Common annualization factors, snapped to when inference lands nearby.
#   365   daily crypto        - trades every day, never closes
#   252   daily equities      - trading sessions after weekends and holidays
#   52    weekly
#   12    monthly
#   8760  hourly crypto       - 24 x 365
COMMON_FREQUENCIES = (12, 52, 252, 365, 8760)


def infer_periods_per_year(df: pd.DataFrame) -> int:
    """Estimate how many return observations this data contains per year.

    This is the number you multiply the square root of to annualize Sharpe.
    It is a property of the DATA's frequency, not of your strategy - a
    strategy that trades once a month on daily data still uses the daily
    factor, because the return series is still daily.

    Counts observations against the calendar span, then snaps to a common
    value when it lands close to one.
    """
    if len(df) < 2:
        return DEFAULT_PERIODS_PER_YEAR

    span_days = (df.index[-1] - df.index[0]).days
    if span_days <= 0:
        return DEFAULT_PERIODS_PER_YEAR

    estimate = len(df) / (span_days / 365.25)

    # Snap to a standard value if we are within 5% of one.
    for common in COMMON_FREQUENCIES:
        if abs(estimate - common) / common < 0.05:
            return common
    return int(round(estimate))


def available_datasets() -> list[str]:
    """Names of every CSV sitting in the data directory."""
    return sorted(p.stem for p in DATA_DIR.glob("*.csv"))


def load(name: str = "BCH-1d") -> pd.DataFrame:
    """Load a dataset and attach return columns.

    Returns a DataFrame indexed by date with:
        open, high, low, close, volume, trades   - raw market data
        simple_return                            - (P_t / P_t-1) - 1
        log_return                               - ln(P_t / P_t-1)

    The first row is dropped, since it has no previous close to compare to.
    """
    path = DATA_DIR / f"{name}.csv"
    if not path.exists():
        raise FileNotFoundError(
            f"No dataset named {name!r}. Available: {available_datasets()}"
        )

    raw = pd.read_csv(path)

    # These files use short column names; map them to something readable.
    rename = {
        "t": "date", "o": "open", "c": "close",
        "h": "high", "l": "low", "v": "volume", "n": "trades",
    }
    df = raw.rename(columns={k: v for k, v in rename.items() if k in raw.columns})

    keep = [c for c in ["date", "open", "high", "low", "close", "volume", "trades"]
            if c in df.columns]
    df = df[keep].copy()

    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").set_index("date")

    df["simple_return"] = df["close"].pct_change()
    df["log_return"] = np.log(df["close"] / df["close"].shift(1))

    return df.dropna(subset=["simple_return"])


def split(df: pd.DataFrame, train_frac: float = 0.75
          ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Chronological train/test split.

    The test set is always the MOST RECENT data - never shuffle time series,
    because training on the future to predict the past is meaningless.
    """
    cut = int(len(df) * train_frac)
    return df.iloc[:cut], df.iloc[cut:]
