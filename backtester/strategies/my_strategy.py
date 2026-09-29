"""YOUR STRATEGY GOES HERE.

Steps:
  1. Rename the class and fill in `name` and `description`.
  2. Write your hypothesis in the docstring BEFORE you write any code.
     If you cannot state it in one sentence, you do not have one yet.
  3. Implement generate_positions().
  4. Run `streamlit run app.py` and pick your strategy from the sidebar.

The one rule you cannot break: every signal must end in .shift(1).
Your position for today may only use data from yesterday or earlier.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from bsequant import Strategy


class MyStrategy(Strategy):
    """HYPOTHESIS: (write it here, in plain English, before coding)

    Example: "After a large single-day drop, buyers step in and price
    partially recovers over the following day."
    """

    name = "My strategy"
    description = "TODO: one line on what this bets on."

    def __init__(self, lookback: int = 5):
        # Any argument with a default shows up as a slider in the UI.
        self.lookback = lookback

    def generate_positions(self, data: pd.DataFrame) -> pd.Series:
        # ------------------------------------------------------------------
        # STEP 1 - compute an indicator (just a number, no claim attached)
        # ------------------------------------------------------------------
        indicator = data["log_return"].rolling(self.lookback).mean()

        # ------------------------------------------------------------------
        # STEP 2 - turn it into a signal (a number WITH a predictive claim)
        # ------------------------------------------------------------------
        signal = -np.sign(indicator)      # fade the recent average move

        # ------------------------------------------------------------------
        # STEP 3 - shift it, so today's position uses yesterday's information
        # ------------------------------------------------------------------
        return signal.shift(1)


# Things to try once this works:
#
#   - Add a threshold so you only trade when the signal is strong. You will
#     trade less, pay fewer fees, and probably keep most of the edge.
#   - Size by conviction: return a fraction instead of ±1.
#   - Go long-only (0 or 1) and see how much of the return came from shorts.
#   - Combine two signals and see whether they are better together.
#
# After each change, check the Test period - not just the full history.
# Anything that only works in-sample is overfitting, not an edge.
