"""EventStrategy: open and close positions bar by bar."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import bsequant as bq
from bsequant import EventStrategy, StrategyError
from strategies.event_examples import (BreakoutMomentum, DipBuyWithStop,
                                       MeanReversionZScore)
from strategies.examples import ShortTermReversal
from strategies.my_strategy import MyStrategy

EVENT_EXAMPLES = [MeanReversionZScore, BreakoutMomentum, DipBuyWithStop,
                  MyStrategy]


class ReversalEvents(EventStrategy):
    """ShortTermReversal, rewritten one bar at a time."""
    name = "Reversal (events)"

    def on_bar(self, bar, history):
        if bar["log_return"] > 0:
            self.go_short()
        elif bar["log_return"] < 0:
            self.go_long()
        else:
            self.go_flat()


def test_event_version_matches_vectorized_version_exactly(bch):
    events = ReversalEvents().generate_positions(bch)
    vectorized = ShortTermReversal().generate_positions(bch).fillna(0.0)
    assert np.array_equal(events.to_numpy(), vectorized.to_numpy())

    m = bq.run(ReversalEvents(), bch, fee_bps=1.5).metrics
    assert m["sharpe"] == pytest.approx(0.8351, abs=1e-4)
    assert m["total_return"] == pytest.approx(2.5939, abs=1e-4)


def test_decision_takes_effect_on_the_next_bar(bch):
    class BuyOnFifthBar(EventStrategy):
        def on_bar(self, bar, history):
            if len(history) == 5:
                self.go_long()

    positions = BuyOnFifthBar().generate_positions(bch)
    assert (positions.iloc[:5] == 0).all()        # bars 0-4: still flat
    assert (positions.iloc[5:] == 1).all()        # decided on bar 4 -> held from bar 5


def test_on_bar_never_sees_the_future(bch):
    seen = []

    class Spy(EventStrategy):
        def on_bar(self, bar, history):
            seen.append((bar.name, history.index[-1], len(history)))

    Spy().generate_positions(bch)
    assert len(seen) == len(bch)
    for i, (bar_time, last_time, length) in enumerate(seen):
        assert bar_time == last_time == bch.index[i]
        assert length == i + 1


def _scramble_last_bar(data, factor):
    cut = data.copy()
    for col in ("open", "high", "low", "close"):
        cut.iloc[-1, cut.columns.get_loc(col)] *= factor
    prev = cut["close"].iloc[-2]
    cut.iloc[-1, cut.columns.get_loc("simple_return")] = cut["close"].iloc[-1] / prev - 1
    cut.iloc[-1, cut.columns.get_loc("log_return")] = np.log(cut["close"].iloc[-1] / prev)
    return cut


@pytest.mark.parametrize("cls", EVENT_EXAMPLES)
def test_examples_pass_truncation_test(bch, cls):
    """Changing bar k (and dropping everything after it) must not change the
    position held on bar k - the position may only depend on earlier bars."""
    full = cls().generate_positions(bch).to_numpy()
    rng = np.random.default_rng(0)
    for k in sorted(rng.choice(np.arange(30, len(bch)), size=15, replace=False)):
        for factor in (1.4, 0.6):
            cut = _scramble_last_bar(bch.iloc[:k + 1], factor)
            assert cls().generate_positions(cut).iloc[-1] == full[k]


@pytest.mark.parametrize("cls", EVENT_EXAMPLES)
def test_examples_run_without_warnings(bch, cls):
    result = bq.run(cls(), bch, fee_bps=10)
    assert result.warnings == []
    assert len(result.trades) > 0


def test_state_tracks_the_open_trade(bch):
    log = []

    class Recorder(EventStrategy):
        def on_bar(self, bar, history):
            log.append((self.position, self.entry_price, self.entry_time,
                        self.bars_held))
            if len(history) == 3:
                self.go_long()
            elif len(history) == 8:
                self.go_flat()

    Recorder().generate_positions(bch)
    # Bars 0-2: flat. Decision on bar 2 at its close.
    assert log[2] == (0.0, None, None, 0)
    # Bar 3 onwards: long, entered at bar 2's close.
    position, price, when, held = log[3]
    assert position == 1.0 and price == bch["close"].iloc[2]
    assert when == bch.index[2] and held == 1
    assert log[7][3] == 5
    # After the exit decision on bar 7: flat again.
    assert log[8] == (0.0, None, None, 0)


def test_going_long_twice_is_one_trade(bch):
    class KeepBuying(EventStrategy):
        def on_bar(self, bar, history):
            self.go_long()

    result = bq.run(KeepBuying(), bch, fee_bps=10)
    assert result.metrics["trades"] == 1
    assert len(result.trades) == 1


def test_flip_closes_one_trade_and_opens_another(bch):
    class Flip(EventStrategy):
        def on_bar(self, bar, history):
            if len(history) == 2:
                self.go_long()
            elif len(history) == 6:
                self.go_short()
            elif len(history) == 10:
                self.go_flat()

    trades = bq.run(Flip(), bch).trades
    assert list(trades["side"]) == ["long", "short"]
    assert list(trades["bars_held"]) == [4, 4]
    assert trades["exit_time"].iloc[0] == trades["entry_time"].iloc[1]


def test_runs_do_not_leak_state(bch):
    class Counter(EventStrategy):
        def __init__(self):
            self.count = 0

        def on_bar(self, bar, history):
            self.count += 1
            if self.count == 10:
                self.go_long()

    strategy = Counter()
    first = strategy.generate_positions(bch)
    second = strategy.generate_positions(bch)
    assert first.equals(second)


def test_errors_name_the_bar(bch):
    class Typo(EventStrategy):
        name = "Typo"

        def on_bar(self, bar, history):
            if len(history) > 50:
                bar["closee"]

    with pytest.raises(StrategyError, match=r"bar 51 of 1460.*KeyError"):
        Typo().generate_positions(bch)


@pytest.mark.parametrize("call", [
    lambda s: s.go_long(-1),
    lambda s: s.go_short(float("nan")),
    lambda s: s.go_long("1"),
    lambda s: s.set_position(None),
])
def test_bad_sizes_are_rejected(bch, call):
    class Bad(EventStrategy):
        def on_bar(self, bar, history):
            call(self)

    with pytest.raises(StrategyError, match="ValueError"):
        Bad().generate_positions(bch)


def test_position_cannot_be_assigned(bch):
    class Assign(EventStrategy):
        def on_bar(self, bar, history):
            self.position = 1

    with pytest.raises(StrategyError, match="go_long"):
        Assign().generate_positions(bch)


def test_dip_buyer_respects_its_exit_rules(bch):
    strategy = DipBuyWithStop(max_bars=10)
    trades = bq.run(strategy, bch).trades
    closed = trades[trades["status"] == "closed"]
    assert closed["bars_held"].max() <= 10
    assert (trades["side"] == "long").all()
