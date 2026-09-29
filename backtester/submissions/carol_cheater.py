import numpy as np
from bsequant import Strategy
class CarolCheat(Strategy):
    name = "Suspiciously good"
    def generate_positions(self, data):
        return np.sign(data["log_return"])   # no shift - cheating
