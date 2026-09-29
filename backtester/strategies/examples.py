"""Example strategies.

Read these to see the shape of a strategy, then write your own in
strategies/my_strategy.py.

Notice that EVERY strategy here ends its signal with .shift(1). That is not
optional - it is what makes the position depend only on data you would have
had at the time. Without it you are trading on the future.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from bsequant import Strategy


class BuyAndHold(Strategy):
    """The benchmark. Every strategy has to beat just owning the thing."""

    name = "Buy and hold"
    description = "Always fully long. No signal, no trading."

    def generate_positions(self, data: pd.DataFrame) -> pd.Series:
        return pd.Series(1.0, index=data.index)


class ShortTermReversal(Strategy):
    """Yesterday up -> short today. Yesterday down -> long today.

    Hypothesis: short-horizon moves overshoot and partially reverse.
    In AR(1) terms, this is betting that w < 0.
    """

    name = "Short-term reversal"
    description = "Bet against yesterday's direction."

    def generate_positions(self, data: pd.DataFrame) -> pd.Series:
        yesterday = np.sign(data["log_return"])
        return (-yesterday).shift(1)


class Momentum(Strategy):
    """Yesterday up -> long today. The mirror of reversal.

    In AR(1) terms, this is betting that w > 0.
    """

    name = "Momentum (1-day)"
    description = "Follow yesterday's direction."

    def generate_positions(self, data: pd.DataFrame) -> pd.Series:
        return np.sign(data["log_return"]).shift(1)


class MovingAverageCrossover(Strategy):
    """Long when the fast average is above the slow one.

    A classic trend-following rule. Note the two parameters - the moment a
    strategy has knobs, you can tune it until the past looks beautiful.
    That is overfitting, and it is why we hold out a test set.
    """

    name = "MA crossover"

    def __init__(self, fast: int = 20, slow: int = 50):
        self.fast, self.slow = fast, slow
        self.name = f"MA crossover ({fast}/{slow})"
        self.description = f"Long when the {fast}-day MA is above the {slow}-day MA."

    def generate_positions(self, data: pd.DataFrame) -> pd.Series:
        fast = data["close"].rolling(self.fast).mean()
        slow = data["close"].rolling(self.slow).mean()
        signal = pd.Series(np.where(fast > slow, 1.0, 0.0), index=data.index)
        return signal.shift(1)


class ThresholdReversal(Strategy):
    """Only fade moves bigger than a threshold.

    Trades less often than plain reversal, so it pays fewer fees - which
    matters once you add realistic costs.
    """

    name = "Threshold reversal"

    def __init__(self, threshold: float = 0.02):
        self.threshold = threshold
        self.name = f"Threshold reversal ({threshold:.1%})"
        self.description = f"Fade moves larger than {threshold:.1%}; otherwise stay flat."

    def generate_positions(self, data: pd.DataFrame) -> pd.Series:
        r = data["log_return"]
        pos = pd.Series(0.0, index=data.index)
        pos[r > self.threshold] = -1.0
        pos[r < -self.threshold] = 1.0
        return pos.shift(1)


class LookaheadCheater(Strategy):
    """DELIBERATELY BROKEN - uses today's return to trade today.

    Run this to see what cheating looks like: an impossible Sharpe and a
    warning from the engine. If your own strategy's numbers look like this,
    you have a bug, not an edge.
    """

    name = "[BROKEN] Lookahead cheater"
    description = "Deliberately biased example. Do not copy."

    def generate_positions(self, data: pd.DataFrame) -> pd.Series:
        return np.sign(data["log_return"])  # no .shift(1) - this is the bug


ALL = [BuyAndHold, ShortTermReversal, Momentum,
       MovingAverageCrossover, ThresholdReversal]
