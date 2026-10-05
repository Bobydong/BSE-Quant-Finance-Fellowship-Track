"""load() accepts common CSV layouts and rejects broken files clearly."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import bsequant as bq

COLUMNS = ["open", "high", "low", "close", "volume", "simple_return", "log_return"]


def _prices(n, seed=0):
    rng = np.random.default_rng(seed)
    return 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))


def test_bch_has_the_standard_columns(bch):
    assert list(bch.columns) == COLUMNS


def test_yahoo_style_stock_file_prefers_adjusted_close(tmp_path):
    days = pd.bdate_range("2021-01-04", periods=600)
    adjusted = _prices(len(days))
    unadjusted = adjusted.copy()
    unadjusted[300:] /= 4                        # a 4-for-1 split
    pd.DataFrame({"Date": days.strftime("%Y-%m-%d"), "Open": unadjusted,
                  "High": unadjusted, "Low": unadjusted, "Close": unadjusted,
                  "Adj Close": adjusted, "Volume": 1000}).to_csv(
        tmp_path / "STOCK.csv", index=False)

    data = bq.load(str(tmp_path / "STOCK.csv"))
    assert list(data.columns) == COLUMNS
    assert data["simple_return"].abs().max() < 0.1   # no fake -75% day
    assert bq.infer_periods_per_year(data) == 252


def test_hourly_epoch_milliseconds(tmp_path):
    times = pd.date_range("2025-01-01", periods=24 * 120, freq="h")
    ms = (times.astype("int64") // 1_000_000).astype("int64")
    pd.DataFrame({"open_time": ms, "o": _prices(len(times)),
                  "h": 1.0, "l": 1.0, "c": _prices(len(times))}).to_csv(
        tmp_path / "BTC-1h.csv", index=False)

    data = bq.load(str(tmp_path / "BTC-1h.csv"))
    assert data.index[0] == times[1]
    assert bq.infer_periods_per_year(data) == 8760
    assert data["volume"].isna().all()           # missing column -> NaN, not a crash


def test_timezones_become_utc(tmp_path):
    pd.DataFrame({"timestamp": ["2025-01-01 09:00:00-05:00",
                                "2025-01-01 10:00:00-05:00",
                                "2025-01-01 11:00:00-05:00"],
                  "close": [1.0, 2.0, 3.0]}).to_csv(tmp_path / "tz.csv", index=False)
    data = bq.load(str(tmp_path / "tz.csv"))
    assert data.index[0] == pd.Timestamp("2025-01-01 15:00:00")


def test_unsorted_rows_and_exact_duplicates_are_fixed(tmp_path):
    pd.DataFrame({"date": ["2025-01-03", "2025-01-01", "2025-01-02", "2025-01-02"],
                  "close": [3.0, 1.0, 2.0, 2.0]}).to_csv(tmp_path / "d.csv", index=False)
    data = bq.load(str(tmp_path / "d.csv"))
    assert list(data["close"]) == [2.0, 3.0]


def test_conflicting_duplicates_are_rejected(tmp_path):
    pd.DataFrame({"date": ["2025-01-01", "2025-01-02", "2025-01-02"],
                  "close": [1.0, 2.0, 2.5]}).to_csv(tmp_path / "d.csv", index=False)
    with pytest.raises(ValueError, match="share the timestamp"):
        bq.load(str(tmp_path / "d.csv"))


def test_missing_close_column_lists_what_was_found(tmp_path):
    pd.DataFrame({"date": ["2025-01-01"], "price": [1.0]}).to_csv(
        tmp_path / "d.csv", index=False)
    with pytest.raises(ValueError, match=r"'close'.*price"):
        bq.load(str(tmp_path / "d.csv"))


def test_non_positive_prices_are_rejected(tmp_path):
    pd.DataFrame({"date": ["2025-01-01", "2025-01-02"],
                  "close": [1.0, 0.0]}).to_csv(tmp_path / "d.csv", index=False)
    with pytest.raises(ValueError, match="non-positive"):
        bq.load(str(tmp_path / "d.csv"))


def test_unknown_dataset_name():
    with pytest.raises(FileNotFoundError, match="BCH-1d"):
        bq.load("NOPE")
