"""Example strategies written bar by bar with EventStrategy.

Each one shows a different kind of idea:

    MeanReversionZScore   mean reversion - bet that stretched prices snap back
    BreakoutMomentum      momentum       - bet that new highs keep going
    DipBuyWithStop        a single trade with a stop-loss, a profit target and
                          a time limit

Read these after examples.py. They all follow the same pattern:

    def on_bar(self, bar, history):
        1. compute something from the past (history)
        2. if flat, decide whether to open a trade
        3. if in a trade, decide whether to close it

You never need .shift(1) here: on_bar only ever sees bars that have already
closed, and whatever you decide takes effect from the next bar.
"""

from __future__ import annotations

import pandas as pd

from bsequant import EventStrategy


class MeanReversionZScore(EventStrategy):
    """Fade prices that stretch far from their recent average.

    Hypothesis: when price moves unusually far from its recent average, it
    tends to drift back toward it.

    "Unusually far" is measured with a z-score: how many standard deviations
    the price is from its average over the last `lookback` bars.

        z < -entry_z   ->  price is stretched DOWN  ->  go long
        z > +entry_z   ->  price is stretched UP    ->  go short
        |z| < exit_z   ->  price is back near normal ->  close the trade

    Entering at 2 and exiting at 0.5 (not at 2) stops the strategy flipping in
    and out every bar while price hovers around the threshold.
    """

    name = "Mean reversion z-score"

    def __init__(self, lookback: int = 20, entry_z: float = 2.0,
                 exit_z: float = 0.5):
        self.lookback = lookback
        self.entry_z = entry_z
        self.exit_z = exit_z
        self.name = f"Mean reversion z-score ({lookback} bars)"
        self.description = (f"Long below -{entry_z:.1f} std, short above "
                            f"+{entry_z:.1f}, exit inside ±{exit_z:.1f}.")

    def on_bar(self, bar: pd.Series, history: pd.DataFrame) -> None:
        # Not enough history yet to know what "normal" looks like.
        if len(history) < self.lookback:
            return

        recent = history["close"].tail(self.lookback)
        spread = recent.std()
        if spread == 0:
            return
        z = (bar["close"] - recent.mean()) / spread

        if self.position == 0:
            if z < -self.entry_z:
                self.go_long()
            elif z > self.entry_z:
                self.go_short()
        elif self.position > 0 and z > -self.exit_z:
            self.go_flat()           # long trade: price has recovered
        elif self.position < 0 and z < self.exit_z:
            self.go_flat()           # short trade: price has come back down


class BreakoutMomentum(EventStrategy):
    """Buy new highs; sell when the move runs out.

    Hypothesis: when price breaks above everything it did in the last
    `entry_lookback` bars, buyers are in control and the move tends to
    continue.

        close > highest high of the previous entry_lookback bars  ->  go long
        close < lowest low  of the previous exit_lookback  bars   ->  go flat

    The exit window is shorter than the entry window so a trade is given room
    to run but cut once the trend clearly turns. This is long-only on purpose:
    going short on new lows is a separate idea worth testing on its own.
    """

    name = "Breakout momentum"

    def __init__(self, entry_lookback: int = 20, exit_lookback: int = 10):
        self.entry_lookback = entry_lookback
        self.exit_lookback = exit_lookback
        self.name = f"Breakout momentum ({entry_lookback}/{exit_lookback})"
        self.description = (f"Long on a {entry_lookback}-bar high, exit on a "
                            f"{exit_lookback}-bar low.")

    def on_bar(self, bar: pd.Series, history: pd.DataFrame) -> None:
        if len(history) <= self.entry_lookback:
            return

        # "Previous" bars: exclude the current one, or the close could never
        # be above a high that already includes it.
        previous = history.iloc[:-1]

        if self.position == 0:
            breakout_level = previous["high"].tail(self.entry_lookback).max()
            if bar["close"] > breakout_level:
                self.go_long()
        else:
            exit_level = previous["low"].tail(self.exit_lookback).min()
            if bar["close"] < exit_level:
                self.go_flat()


class DipBuyWithStop(EventStrategy):
    """Buy a sharp one-bar drop, then manage the trade.

    Hypothesis: a sharp single-bar drop is often an overreaction, and price
    partly recovers over the next few bars.

    Enter:  the bar fell by more than `drop`.
    Exit at the first of:
        take profit   price is `take_profit` above where we bought
        stop loss     price is `stop_loss` below where we bought
        time limit    we have held for `max_bars` bars and nothing happened

    This kind of rule - "get out if it goes wrong" - is natural bar by bar and
    awkward to write as one pandas column, which is why EventStrategy exists.
    """

    name = "Dip buy with stop"

    def __init__(self, drop: float = 0.05, take_profit: float = 0.08,
                 stop_loss: float = 0.05, max_bars: int = 10):
        self.drop = drop
        self.take_profit = take_profit
        self.stop_loss = stop_loss
        self.max_bars = max_bars
        self.name = f"Dip buy with stop ({drop:.0%} drop)"
        self.description = (f"Buy after a {drop:.0%} drop; exit at +{take_profit:.0%}, "
                            f"-{stop_loss:.0%}, or after {max_bars} bars.")

    def on_bar(self, bar: pd.Series, history: pd.DataFrame) -> None:
        if self.position == 0:
            if bar["simple_return"] < -self.drop:
                self.go_long()
            return

        # We are in a trade: how is it doing since we bought?
        gain = bar["close"] / self.entry_price - 1

        if gain >= self.take_profit:
            self.go_flat()
        elif gain <= -self.stop_loss:
            self.go_flat()
        elif self.bars_held >= self.max_bars:
            self.go_flat()
