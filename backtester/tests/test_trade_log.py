"""trade_log(): one row per round trip, from any position series."""

from __future__ import annotations

import pandas as pd
import pytest

import bsequant as bq


def _frame(positions, closes):
    index = pd.date_range("2025-01-01", periods=len(closes), freq="D")
    close = pd.Series(closes, index=index, dtype=float)
    data = pd.DataFrame({"close": close})
    data["simple_return"] = close.pct_change()
    data = data.iloc[1:]
    return bq.run_positions(pd.Series(positions, index=data.index), data)


def test_long_then_flat():
    # Closes by bar:   0     1    2    3    4   (bar 0 is dropped as in load())
    # Position held:         0    1    1    0
    # Long is held DURING bars 2 and 3, so it was decided at the close of
    # bar 1 (100) and earns 100 -> 110 -> 121.
    result = _frame([0, 1, 1, 0], [100, 100, 110, 121, 121])
    trades = result.trades
    assert len(trades) == 1
    trade = trades.iloc[0]
    assert trade["side"] == "long" and trade["status"] == "closed"
    assert trade["entry_price"] == pytest.approx(100)
    assert trade["exit_price"] == pytest.approx(121)
    assert trade["bars_held"] == 2
    assert trade["return"] == pytest.approx(0.21)


def test_short_trade_return_and_open_status():
    result = _frame([-1, -1], [100, 90, 81])
    trade = result.trades.iloc[0]
    assert trade["side"] == "short" and trade["status"] == "open"
    assert trade["entry_price"] == pytest.approx(100)
    assert trade["return"] == pytest.approx((1.1) * (1.1) - 1)
    assert pd.isna(trade["exit_time"])


def test_resizing_is_one_trade_but_flipping_is_two():
    assert len(_frame([0.5, 1.0, 0.5], [1, 1, 1, 1]).trades) == 1
    assert len(_frame([1, -1, 1], [1, 1, 1, 1]).trades) == 3


def test_fees_reduce_trade_return():
    index = pd.date_range("2025-01-01", periods=3, freq="D")
    data = pd.DataFrame({"close": [100.0, 100.0, 100.0]}, index=index)
    data["simple_return"] = data["close"].pct_change()
    data = data.iloc[1:]
    result = bq.run_positions(pd.Series([1.0, 0.0], index=data.index), data,
                              fee_bps=10)
    assert result.trades.iloc[0]["return"] == pytest.approx(-0.002)


def test_no_positions_no_trades(bch):
    result = bq.run_positions(pd.Series(0.0, index=bch.index), bch)
    assert result.trades.empty
