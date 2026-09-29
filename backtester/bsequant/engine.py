"""The backtest engine.

Runs a Strategy over a dataset and produces a BacktestResult.

Two things this engine is careful about, because they are the two ways
student backtests usually go wrong:

1. SHORT POSITIONS.  P&L is computed from SIMPLE returns, not by flipping
   the sign of a log return.  A short that loses 20% must show -20%, and
   -1 * ln(1.20) gives -16.7%, which silently flatters every short.

2. LOOKAHEAD BIAS.  The engine checks whether your positions correlate with
   the SAME day's return more than with yesterday's, which is the fingerprint
   of trading on information you would not have had.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import numpy as np
import pandas as pd

from .data import infer_periods_per_year
from .strategy import Strategy


@dataclass
class BacktestResult:
    """Everything produced by one backtest run."""

    strategy_name: str
    data: pd.DataFrame          # per-day frame: position, returns, equity
    metrics: dict               # headline numbers
    yearly: pd.DataFrame        # per-calendar-year breakdown
    warnings: list[str] = field(default_factory=list)
    fee_bps: float = 0.0
    periods_per_year: int = 365  # annualization factor actually used

    @property
    def equity(self) -> pd.Series:
        return self.data["equity"]

    def summary(self) -> str:
        m = self.metrics
        lines = [
            f"{self.strategy_name}",
            f"  Total return      {m['total_return']:>10.1%}",
            f"  Growth multiple   {m['growth_multiple']:>10.2f}x",
            f"  Annual return     {m['annual_return']:>10.1%}",
            f"  Sharpe            {m['sharpe']:>10.2f}",
            f"  Max drawdown      {m['max_drawdown']:>10.1%}",
            f"  Win rate          {m['win_rate']:>10.1%}",
            f"  Days traded       {m['days_in_market']:>10d}",
        ]
        for w in self.warnings:
            lines.append(f"  !! {w}")
        return "\n".join(lines)


def _max_drawdown(equity: pd.Series) -> float:
    """Worst peak-to-trough decline, as a negative fraction."""
    return float((equity / equity.cummax() - 1.0).min())


def _check_lookahead(positions: pd.Series, returns: pd.Series) -> list[str]:
    """Flag positions that look like they used same-day information.

    A legitimate strategy decides today's position from yesterday's data, so
    its positions should line up with YESTERDAY'S return. If they line up far
    better with TODAY'S return, the strategy is peeking at the future.
    """
    warnings: list[str] = []

    pos = positions.fillna(0.0)

    # A constant position (buy-and-hold) has no variance, so correlation is
    # undefined - and it cannot be peeking at anything either way.
    if pos.std() == 0 or pd.isna(pos.std()):
        return warnings

    same_day = pos.corr(returns)
    prior_day = pos.corr(returns.shift(1))

    if pd.isna(same_day):
        return warnings

    if abs(same_day) > 0.30 and abs(same_day) > abs(prior_day or 0) * 2:
        warnings.append(
            f"Possible LOOKAHEAD BIAS: positions correlate {same_day:+.2f} with "
            f"the SAME day's return (vs {prior_day:+.2f} with yesterday's). "
            f"Did you forget .shift(1)?"
        )
    return warnings


def run(strategy: Strategy, data: pd.DataFrame, fee_bps: float = 0.0,
        periods_per_year: int | None = None) -> BacktestResult:
    """Backtest one strategy.

    Args:
        strategy: an instance implementing generate_positions()
        data: output of bsequant.data.load()
        fee_bps: cost in basis points charged on each side of a trade.
                 Charged only when the position actually changes.
        periods_per_year: annualization factor - the number of return
                 observations in a year. 365 for daily crypto, 252 for daily
                 equities, 12 for monthly. If omitted, it is inferred from
                 the spacing of the data's dates.

    Returns:
        BacktestResult
    """
    if periods_per_year is None:
        periods_per_year = infer_periods_per_year(data)

    positions = strategy.generate_positions(data)

    if not isinstance(positions, pd.Series):
        positions = pd.Series(positions, index=data.index)
    positions = positions.reindex(data.index).fillna(0.0).astype(float)

    warnings = _check_lookahead(positions, data["simple_return"])

    if positions.abs().max() > 1.0:
        warnings.append(
            f"Position size reaches {positions.abs().max():.2f}x equity - this is "
            f"leverage, and losses are magnified the same way gains are."
        )

    out = pd.DataFrame(index=data.index)
    out["close"] = data["close"]
    out["position"] = positions
    out["market_return"] = data["simple_return"]

    # --- P&L, computed from SIMPLE returns (see module docstring) ---
    out["gross_return"] = positions * data["simple_return"]

    # Fees are charged on the amount of position that actually changed.
    # Flipping +1 -> -1 trades 2 units of equity and costs 2 fees.
    turnover = positions.diff().abs().fillna(positions.abs())
    out["turnover"] = turnover
    out["cost"] = turnover * (fee_bps / 10_000.0)
    out["net_return"] = out["gross_return"] - out["cost"]

    # Equity compounds: each day's growth multiplies the previous balance.
    out["equity"] = (1.0 + out["net_return"]).cumprod()
    out["drawdown"] = out["equity"] / out["equity"].cummax() - 1.0

    # Buy-and-hold benchmark over the identical period.
    out["benchmark_equity"] = (1.0 + data["simple_return"]).cumprod()

    if (out["net_return"] <= -1.0).any():
        first = out.index[out["net_return"] <= -1.0][0]
        warnings.append(
            f"ACCOUNT WIPED OUT on {first.date()} - a single day lost more than "
            f"100% of equity. Every number after this date is meaningless."
        )

    r = out["net_return"]
    traded = r[positions != 0]
    n = len(r)
    years = n / periods_per_year
    final = float(out["equity"].iloc[-1])

    metrics = {
        "total_return": final - 1.0,
        "growth_multiple": final,
        "annual_return": final ** (1 / years) - 1 if years > 0 and final > 0 else float("nan"),
        "sharpe": float(r.mean() / r.std() * np.sqrt(periods_per_year)) if r.std() > 0 else float("nan"),
        "max_drawdown": _max_drawdown(out["equity"]),
        "volatility": float(r.std() * np.sqrt(periods_per_year)),
        "win_rate": float((traded > 0).mean()) if len(traded) else float("nan"),
        "days_in_market": int((positions != 0).sum()),
        "total_days": n,
        "trades": int((positions.diff().fillna(0) != 0).sum()),
        "avg_turnover": float(turnover.mean()),
        "total_fees_paid": float(out["cost"].sum()),
        "best_day": float(r.max()),
        "worst_day": float(r.min()),
        "benchmark_return": float(out["benchmark_equity"].iloc[-1]) - 1.0,
        "benchmark_sharpe": float(
            data["simple_return"].mean() / data["simple_return"].std()
            * np.sqrt(periods_per_year)
        ),
        "periods_per_year": periods_per_year,
    }

    # Per-calendar-year breakdown. A strategy that works on average can still
    # have a catastrophic year, and that is what fellows need to see.
    rows = []
    for year, g in out.groupby(out.index.year):
        gr = g["net_return"]
        rows.append({
            "year": year,
            "return": (1 + gr).prod() - 1,
            "sharpe": gr.mean() / gr.std() * np.sqrt(periods_per_year) if gr.std() > 0 else np.nan,
            "max_drawdown": _max_drawdown((1 + gr).cumprod()),
            "days": len(gr),
        })
    yearly = pd.DataFrame(rows).set_index("year")

    return BacktestResult(
        strategy_name=strategy.name,
        data=out,
        metrics=metrics,
        yearly=yearly,
        warnings=warnings,
        fee_bps=fee_bps,
        periods_per_year=periods_per_year,
    )


def cost_sweep(strategy: Strategy, data: pd.DataFrame,
               levels=(0, 1, 2, 5, 10, 20),
               periods_per_year: int | None = None) -> pd.DataFrame:
    """Re-run the strategy across several fee levels.

    The question this answers: at what cost does the edge disappear?
    A strategy that dies at 2bps is not tradeable.
    """
    rows = []
    for bps in levels:
        m = run(strategy, data, fee_bps=bps,
                periods_per_year=periods_per_year).metrics
        rows.append({
            "fee_bps": bps,
            "sharpe": m["sharpe"],
            "annual_return": m["annual_return"],
            "total_return": m["total_return"],
            "max_drawdown": m["max_drawdown"],
        })
    return pd.DataFrame(rows).set_index("fee_bps")
