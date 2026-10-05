"""The regression table and invariants from backtester/CLAUDE.md.

If one of these fails, the change that broke it is wrong unless it was
*supposed* to move the numbers - in which case update CLAUDE.md too.
"""

from __future__ import annotations

import pytest

import bsequant as bq
from strategies.examples import BuyAndHold, LookaheadCheater, ShortTermReversal


@pytest.mark.parametrize("strategy, fee, sharpe, total, max_dd, win, trades", [
    (ShortTermReversal, 0.0, 0.9028, 3.5282, -0.7649, 0.5288, 774),
    (ShortTermReversal, 1.5, 0.8351, 2.5939, -0.7703, 0.5281, 774),
    (BuyAndHold, 0.0, 0.4715, 0.2482, -0.7401, 0.4966, 0),
])
def test_regression_table(bch, strategy, fee, sharpe, total, max_dd, win, trades):
    m = bq.run(strategy(), bch, fee_bps=fee).metrics
    assert m["sharpe"] == pytest.approx(sharpe, abs=1e-4)
    assert m["total_return"] == pytest.approx(total, abs=1e-4)
    assert m["max_drawdown"] == pytest.approx(max_dd, abs=1e-4)
    assert m["win_rate"] == pytest.approx(win, abs=1e-4)
    assert m["trades"] == trades


def test_dataset_shape(bch):
    assert len(bch) == 1460
    assert str(bch.index[0].date()) == "2022-04-14"
    assert str(bch.index[-1].date()) == "2026-04-12"
    assert bq.infer_periods_per_year(bch) == 365


def test_yearly_returns(bch):
    yearly = bq.run(ShortTermReversal(), bch, fee_bps=1.5).yearly["return"]
    expected = {2022: 0.626, 2023: 0.546, 2024: -0.481, 2025: 1.327, 2026: 0.184}
    for year, value in expected.items():
        assert yearly[year] == pytest.approx(value, abs=5e-4)


def test_lookahead_cheater_is_caught_once(bch):
    result = bq.run(LookaheadCheater(), bch)
    assert result.metrics["sharpe"] == pytest.approx(16.4, abs=0.1)
    assert len(result.warnings) == 1
    assert "LOOKAHEAD" in result.warnings[0]


def test_periods_per_year_only_scales_annualized_numbers(bch):
    a = bq.run(ShortTermReversal(), bch, fee_bps=10, periods_per_year=365).metrics
    b = bq.run(ShortTermReversal(), bch, fee_bps=10, periods_per_year=252).metrics
    assert a["total_return"] == b["total_return"]
    assert a["max_drawdown"] == b["max_drawdown"]
    assert a["sharpe"] != b["sharpe"]


def test_short_pnl_uses_simple_returns(bch):
    # A -1 position must lose exactly what the asset gains, bar for bar.
    import pandas as pd
    short = bq.run_positions(pd.Series(-1.0, index=bch.index), bch)
    gross = short.data["gross_return"]
    assert (gross == -bch["simple_return"]).all()


def test_fees_only_on_position_change(bch):
    import pandas as pd
    hold = bq.run_positions(pd.Series(1.0, index=bch.index), bch, fee_bps=10)
    # Entering once costs one fee; holding afterwards costs nothing.
    assert hold.data["cost"].iloc[0] == pytest.approx(0.001)
    assert (hold.data["cost"].iloc[1:] == 0).all()


def test_cost_sweep_matches_individual_runs(bch):
    sweep = bq.cost_sweep(ShortTermReversal(), bch, levels=(0, 1.5, 10))
    for fee in (0, 1.5, 10):
        single = bq.run(ShortTermReversal(), bch, fee_bps=fee).metrics
        assert sweep.loc[fee, "sharpe"] == pytest.approx(single["sharpe"])
