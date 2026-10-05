"""YOUR STRATEGY GOES HERE.

Steps:
  1. Rename the class and fill in `name` and `description`.
  2. Write your hypothesis in the docstring BEFORE you write any code.
     If you cannot state it in one sentence, you do not have one yet.
  3. Fill in on_bar(): look at the past, then decide whether to open or close
     a position with go_long(), go_short() or go_flat().
  4. Run `streamlit run app.py`, pick your strategy from the sidebar, and look
     at the Trades tab to check it opens and closes when you expect.

How it runs: the engine calls on_bar() once per bar (once a day on daily
data), oldest first. You only ever see bars that have already happened, and
whatever you decide takes effect from the NEXT bar. So you cannot cheat by
accident.

Read strategies/event_examples.py for complete examples of mean reversion,
momentum, and a trade with a stop-loss.
"""

from __future__ import annotations

import pandas as pd

from bsequant import EventStrategy


class MyStrategy(EventStrategy):
    """HYPOTHESIS: (write it here, in plain English, before coding)

    Example: "When the last few bars have all gone up, the trend tends to
    continue for a while."
    """

    name = "My strategy"
    description = "TODO: one line on what this bets on."

    def __init__(self, lookback: int = 5):
        # Any argument with a default shows up as a slider in the UI.
        self.lookback = lookback

    def on_bar(self, bar: pd.Series, history: pd.DataFrame) -> None:
        # ------------------------------------------------------------------
        # STEP 1 - compute an indicator from the past (just a number)
        # ------------------------------------------------------------------
        if len(history) < self.lookback:
            return                              # not enough data yet
        recent_move = history["log_return"].tail(self.lookback).sum()

        # ------------------------------------------------------------------
        # STEP 2 - if you have no position, decide whether to open one
        # ------------------------------------------------------------------
        if self.position == 0:
            if recent_move > 0:
                self.go_long()                  # follow the recent trend up
            elif recent_move < 0:
                self.go_short()                 # follow it down

        # ------------------------------------------------------------------
        # STEP 3 - if you have a position, decide whether to close it
        # ------------------------------------------------------------------
        elif self.position > 0 and recent_move < 0:
            self.go_flat()                      # trend turned: get out
        elif self.position < 0 and recent_move > 0:
            self.go_flat()


# Things you can use inside on_bar:
#
#   bar["close"], bar["high"], bar["low"], bar["open"], bar["volume"]
#   bar["simple_return"]          this bar's % change
#   bar.name                      this bar's date/time
#   history["close"].tail(20)     the last 20 closes (including this bar)
#   self.position                 1.0 long, -1.0 short, 0.0 flat
#   self.entry_price              the price you opened your trade at
#   self.bars_held                how long you have been in the trade
#
# Things to try once this works:
#
#   - Add a stop-loss: close the trade if bar["close"] / self.entry_price - 1
#     falls below -5%.
#   - Size by conviction: self.go_long(0.5) holds half your equity.
#   - Go long-only (never call go_short) and see how much of the result came
#     from the shorts.
#
# After each change, check the Test period - not just the full history.
# Anything that only works in-sample is overfitting, not an edge.
