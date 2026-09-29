import numpy as np
from bsequant import Strategy
class BobMomentum(Strategy):
    name = "Momentum"
    def generate_positions(self, data):
        return np.sign(data["log_return"]).shift(1)
