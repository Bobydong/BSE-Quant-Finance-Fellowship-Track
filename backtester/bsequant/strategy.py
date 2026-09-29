"""The Strategy interface every fellow implements.

A strategy answers one question: given what the market has done up to and
including yesterday, what position should I hold today?

Position convention:
     1.0  = fully long  (100% of equity)
     0.0  = flat        (no position, in cash)
    -1.0  = fully short (100% of equity)

Fractional values are allowed (0.5 = half your equity).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import pandas as pd


class Strategy(ABC):
    """Subclass this and implement generate_positions()."""

    #: Shown on the leaderboard. Override in your subclass.
    name: str = "Unnamed strategy"

    #: One line describing the hypothesis. Override in your subclass.
    description: str = ""

    @abstractmethod
    def generate_positions(self, data: pd.DataFrame) -> pd.Series:
        """Return the position to hold on each day.

        Args:
            data: DataFrame indexed by date, with columns:
                    open, high, low, close   - prices
                    simple_return            - close-to-close % change
                    log_return               - close-to-close log return

        Returns:
            A Series aligned to data.index. The value at row t is the
            position held DURING day t, which earns day t's return.

        CRITICAL - avoiding lookahead bias:
            The position for day t must be decided using data from day t-1
            or earlier. In practice this means every signal you compute must
            end with .shift(1) before it becomes a position.

            WRONG:   return np.sign(data['log_return'])
                     (uses today's return to trade today - impossible)

            RIGHT:   return np.sign(data['log_return']).shift(1)
                     (uses yesterday's return to trade today)

            The engine checks for this and will warn you.
        """
        raise NotImplementedError

    def __repr__(self) -> str:
        return f"<Strategy {self.name!r}>"
