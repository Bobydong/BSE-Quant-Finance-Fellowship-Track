import numpy as np, pandas as pd
from bsequant import Strategy
class AliceReversal(Strategy):
    name = "Reversal + threshold"
    def generate_positions(self, data):
        r = data["log_return"]
        pos = pd.Series(0.0, index=data.index)
        pos[r > 0.015] = -1.0
        pos[r < -0.015] = 1.0
        return pos.shift(1)
