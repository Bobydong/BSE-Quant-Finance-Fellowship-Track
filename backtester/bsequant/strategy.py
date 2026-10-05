"""The Strategy interfaces fellows implement.

A strategy answers one question: given what the market has done up to and
including yesterday, what position should I hold today?

There are two ways to answer it, and both produce the same thing - one
position per bar - which the engine then turns into P&L:

  EventStrategy (start here)
      Write on_bar(). The engine walks through the data one bar at a time,
      shows you only the past, and you call go_long(), go_short() or
      go_flat() whenever you want to open or close a position. Good for
      rules like "enter when X, exit when Y, stop out if Z".

  Strategy (the column-at-a-time version)
      Write generate_positions(), which returns every position at once using
      pandas. Faster, but you must remember .shift(1) yourself.

Position convention:
     1.0  = fully long  (100% of equity)
     0.0  = flat        (no position, in cash)
    -1.0  = fully short (100% of equity)

Fractional values are allowed (0.5 = half your equity).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import copy
import math

import numpy as np
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


class StrategyError(RuntimeError):
    """Raised when a fellow's on_bar() fails, naming the bar it failed on."""


class EventStrategy(Strategy):
    """Subclass this and implement on_bar(bar, history).

    How a backtest runs:

        for every bar in the data, oldest first:
            the engine calls  on_bar(bar, history)
            you look at the past and maybe call go_long / go_short / go_flat
            your new position is held starting from the NEXT bar

    That last line is the whole trick. You decide at the close of a bar, using
    that bar and everything before it, and your position starts earning from
    the next bar. You never see a bar before it happens, so you cannot cheat
    by accident - no .shift(1) needed.

    Timing is as precise as the data and no more: on daily data you can act
    once a day, on hourly data once an hour.

    Inside on_bar you can read:
        self.position      your current position (1.0, 0.0, -1.0, 0.5, ...)
        self.entry_price   the price you opened the current trade at
                           (None when flat)
        self.entry_time    the bar you opened it on (None when flat)
        self.bars_held     how many bars the current trade has been held
                           (0 when flat)
    """

    @abstractmethod
    def on_bar(self, bar: pd.Series, history: pd.DataFrame) -> None:
        """Called once per bar, oldest first.

        Args:
            bar: the bar that just closed. Read prices with bar["close"],
                 bar["high"], etc.; bar.name is its timestamp.
            history: every bar up to and INCLUDING this one, as a DataFrame
                 with the same columns as the data (open, high, low, close,
                 volume, simple_return, log_return). The last row is `bar`.
                 Use history["close"].tail(20).mean() for a 20-bar average.

        Do not return anything. Call one of these instead (or nothing, to
        keep your current position):
            self.go_long(size=1.0)    hold +size from the next bar
            self.go_short(size=1.0)   hold -size from the next bar
            self.go_flat()            hold nothing from the next bar
            self.set_position(x)      hold exactly x from the next bar
        """
        raise NotImplementedError

    # ------------------------------------------------------------- actions
    # Each action sets a TARGET position. Calling go_long() while already
    # long does nothing - you do not buy twice. Fees are only charged when the
    # position actually changes.

    def go_long(self, size: float = 1.0) -> None:
        """Be long `size` of equity from the next bar on."""
        self._target = _checked_size(size, "go_long")

    def go_short(self, size: float = 1.0) -> None:
        """Be short `size` of equity from the next bar on."""
        self._target = -_checked_size(size, "go_short")

    def go_flat(self) -> None:
        """Close any open position from the next bar on."""
        self._target = 0.0

    def set_position(self, position: float) -> None:
        """Hold exactly `position` (positive = long, negative = short)."""
        if not _is_finite_number(position):
            raise ValueError(f"set_position() needs a number, got {position!r}")
        self._target = float(position)

    # ------------------------------------------------------------- state
    # Read-only views of the trade you are currently in.

    @property
    def position(self) -> float:
        return getattr(self, "_position", 0.0)

    @position.setter
    def position(self, value) -> None:
        raise AttributeError(
            "Do not set self.position directly - call self.go_long(), "
            "self.go_short(), self.go_flat() or self.set_position(x) instead."
        )

    @property
    def entry_price(self) -> float | None:
        return getattr(self, "_entry_price", None)

    @property
    def entry_time(self):
        return getattr(self, "_entry_time", None)

    @property
    def bars_held(self) -> int:
        entry = getattr(self, "_entry_bar", None)
        if entry is None:
            return 0
        return self._bar_number - entry

    # ------------------------------------------------------------- engine
    def generate_positions(self, data: pd.DataFrame) -> pd.Series:
        """Walk through the data bar by bar and record the positions.

        Fellows do not call or override this; it is what lets the engine
        treat an EventStrategy exactly like any other strategy.
        """
        # Run on a fresh copy so every backtest starts from the state that
        # __init__ set up. Without this, anything on_bar() stored on self
        # (a trailing high, a counter) would leak from one run into the next,
        # and the Performance and Costs tabs could disagree.
        runner = _fresh_copy(self)
        return runner._walk(data)

    def _walk(self, data: pd.DataFrame) -> pd.Series:
        self._position = 0.0
        self._target = 0.0
        self._entry_price = None
        self._entry_time = None
        self._entry_bar = None

        positions = np.zeros(len(data))
        for i in range(len(data)):
            self._bar_number = i
            bar = data.iloc[i]
            history = data.iloc[: i + 1]

            try:
                self.on_bar(bar, history)
            except Exception as exc:
                raise StrategyError(
                    f"{self.name}: on_bar() failed on the bar dated {bar.name} "
                    f"(bar {i + 1} of {len(data)}): {type(exc).__name__}: {exc}"
                ) from exc

            self._apply_target(bar, i)

            # The decision made on bar i is the position held during bar i+1.
            # The very last decision has no next bar to act on, so it is
            # dropped - exactly like the last value of a .shift(1).
            if i + 1 < len(data):
                positions[i + 1] = self._position

        return pd.Series(positions, index=data.index, name="position")

    def _apply_target(self, bar: pd.Series, i: int) -> None:
        """Move to the target position and keep the trade bookkeeping."""
        new = self._target
        old = self._position
        if new == old:
            return

        opened_new_trade = new != 0 and (old == 0 or np.sign(new) != np.sign(old))
        if new == 0:
            self._entry_price = None
            self._entry_time = None
            self._entry_bar = None
        elif opened_new_trade:
            self._entry_price = float(bar["close"])
            self._entry_time = bar.name
            self._entry_bar = i
        self._position = new


def _is_finite_number(x) -> bool:
    return (isinstance(x, (int, float, np.integer, np.floating))
            and not isinstance(x, bool) and math.isfinite(float(x)))


def _checked_size(size, action: str) -> float:
    if not _is_finite_number(size) or size < 0:
        raise ValueError(
            f"{action}() needs a size of 0 or more (1.0 = all of your equity), "
            f"got {size!r}. Use go_short() to go short instead of a negative size."
        )
    return float(size)


def _fresh_copy(strategy):
    try:
        return copy.deepcopy(strategy)
    except Exception:          # something on self cannot be deep-copied
        return copy.copy(strategy)
