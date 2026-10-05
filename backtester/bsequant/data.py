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


# Different data sources name the same thing differently. For each column the
# backtester needs, these are the names we recognize, in order of preference.
# Matching ignores upper/lower case, but an exact match always wins - so a
# file with both "t" and "T" columns (like BCH-1d) still picks "t".
COLUMN_ALIASES = {
    "date": ("date", "datetime", "timestamp", "time", "t", "open_time",
             "open time"),
    "open": ("open", "o"),
    "high": ("high", "h"),
    "low": ("low", "l"),
    # Stocks: ALWAYS prefer the adjusted close. An unadjusted close shows a
    # 4-for-1 split as a 75% crash in one day, which no strategy could trade.
    "close": ("adj close", "adj_close", "adjclose", "adjusted close",
              "adjusted_close", "close", "c"),
    "volume": ("volume", "vol", "v"),
}

PRICE_COLUMNS = ["open", "high", "low", "close", "volume"]


def _find_column(columns: list[str], aliases: tuple, taken: set) -> str | None:
    """Return the raw column that best matches one of the aliases."""
    free = [c for c in columns if c not in taken]
    for alias in aliases:
        exact = [c for c in free if c.strip() == alias]
        if exact:
            return exact[0]
        loose = [c for c in free if c.strip().lower() == alias]
        if len(loose) == 1:
            return loose[0]
    return None


def _parse_dates(values: pd.Series) -> pd.DatetimeIndex:
    """Turn a date column into timestamps, whatever format it came in."""
    if pd.api.types.is_numeric_dtype(values):
        # Unix timestamps. Exchanges usually give milliseconds (13 digits);
        # some give seconds (10 digits).
        unit = "ms" if values.abs().max() > 1e11 else "s"
        parsed = pd.to_datetime(values, unit=unit, utc=True)
    else:
        parsed = pd.to_datetime(values, utc=True)
    # Store everything as plain UTC times, so data from different sources and
    # time zones lines up the same way.
    return pd.DatetimeIndex(parsed).tz_localize(None)


def _resolve_path(name: str) -> Path:
    """A dataset name like "BCH-1d", or a path to any CSV file."""
    as_path = Path(name).expanduser()
    if as_path.suffix.lower() == ".csv" or as_path.exists():
        if not as_path.exists():
            raise FileNotFoundError(f"No CSV file at {as_path}")
        return as_path

    path = DATA_DIR / f"{name}.csv"
    if not path.exists():
        raise FileNotFoundError(
            f"No dataset named {name!r}. Available: {available_datasets()}"
        )
    return path


def load(name: str = "BCH-1d") -> pd.DataFrame:
    """Load a dataset and attach return columns.

    `name` is either a dataset in data/ ("BCH-1d") or a path to a CSV file.
    The file can come from most sources - crypto exchanges, Yahoo Finance and
    similar exports work as-is - and can be daily, hourly or any other
    frequency. See COLUMN_ALIASES for the column names that are recognized.

    Returns a DataFrame indexed by timestamp, oldest first, with exactly:
        open, high, low, close, volume   - market data (NaN if the file
                                           does not have that column)
        simple_return                    - (P_t / P_t-1) - 1
        log_return                       - ln(P_t / P_t-1)

    Every dataset gets the same columns, so a strategy that works on one
    dataset cannot crash on another because a column is missing.

    The first row is dropped, since it has no previous close to compare to.
    """
    path = _resolve_path(name)
    raw = pd.read_csv(path)
    raw.columns = [str(c) for c in raw.columns]

    found: dict[str, str] = {}
    for field, aliases in COLUMN_ALIASES.items():
        column = _find_column(list(raw.columns), aliases, set(found.values()))
        if column is not None:
            found[field] = column

    for required in ("date", "close"):
        if required not in found:
            raise ValueError(
                f"{path.name}: could not find a {required!r} column. "
                f"Columns in the file: {list(raw.columns)}. "
                f"Recognized names: {list(COLUMN_ALIASES[required])}"
            )

    df = pd.DataFrame(index=_parse_dates(raw[found["date"]]))
    for field in PRICE_COLUMNS:
        if field in found:
            df[field] = pd.to_numeric(raw[found[field]], errors="coerce").to_numpy()
        else:
            df[field] = np.nan
    df.index.name = "date"

    # Rows without a closing price cannot be traded on; drop them.
    df = df.dropna(subset=["close"])
    if (df["close"] <= 0).any():
        first = df.index[df["close"] <= 0][0]
        raise ValueError(f"{path.name}: non-positive close price on {first}")

    # The same bar listed twice is harmless; two DIFFERENT prices for the same
    # timestamp means the file is broken, and guessing would be worse.
    df = df[~(df.index.duplicated(keep="first")
              & df.reset_index().duplicated(keep="first").to_numpy())]
    if df.index.duplicated().any():
        first = df.index[df.index.duplicated()][0]
        raise ValueError(
            f"{path.name}: two different rows share the timestamp {first}"
        )

    df = df.sort_index()

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
