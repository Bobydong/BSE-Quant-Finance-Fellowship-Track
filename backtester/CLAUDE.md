# CLAUDE.md — context for working on this repo

## What this is

A backtester built as a **teaching tool** for the Bruin Software Engineers
fellowship quant track (Fall 2026, 4 weeks, ~8-10 freshmen with weak Python
and no finance background).

It is used two ways:

1. **During the track** — fellows write a strategy in one method (usually
   `on_bar()` on an `EventStrategy`), run
   `streamlit run app.py`, and get a full performance report in the browser.
2. **At demo day** — the instructor runs every submission against a held-out
   dataset with `compete.py` and publishes a static leaderboard.

## The single most important thing to understand

**This is a teaching tool, not a production backtester.** Every design choice
optimizes for a freshman understanding what they are looking at, not for
speed, generality, or feature count.

Concretely, that means:

- **Readability beats cleverness.** Code is commented to explain *why*, in
  plain English, at a level a first-year can follow.
- **Wrong-but-invisible is the enemy.** The engine actively warns about
  lookahead bias, leverage, and account wipeout, because the whole point is
  teaching fellows to distrust good-looking results.
- **UI copy is teaching copy.** The captions under charts ("a real edge can
  vanish for a year or more…") are curriculum, not decoration. Do not strip
  them for brevity.
- **Do not add features to look impressive.** More knobs means more ways to
  overfit, which is the opposite of the lesson.

## Invariants — do not break these

These encode bugs that were found and fixed the hard way. Breaking one
silently produces plausible-looking wrong numbers.

### 1. P&L uses SIMPLE returns, never `signal × log_return`

In `engine.py`:

```python
out["gross_return"] = positions * data["simple_return"]   # correct
```

Flipping the sign of a log return does **not** give a short's P&L. A short
that loses 20% must show -20%, but `-1 * ln(1.20)` gives -16.7%. That error
is always in the trader's favour, compounds over every short day, and
inflated an earlier version of this backtest by roughly 5×.

If a log return of the *position* is ever needed, derive it:
`np.log(1 + position * simple_return)`.

### 2. Equity compounds with `cumprod`, not `cumsum`

```python
out["equity"] = (1.0 + out["net_return"]).cumprod()
```

`capital * (1 + cumsum(r))` is simple interest, not compounding.

### 3. `periods_per_year` is a parameter, never a module constant

It is inferred by `infer_periods_per_year()` and overridable in the UI and in
`compete.py`. It scales Sharpe, annualized return, and volatility — and must
never affect total return or max drawdown. There is an assertion-style check
for this in the verification snippet below.

365 = daily crypto, 252 = daily equities, 12 = monthly. It is a property of
the **data's frequency**, not of how often the strategy trades.

### 4. The position for bar *t* only uses data up to bar *t-1*

For column-at-a-time `Strategy` subclasses this means every signal ends in
`.shift(1)`; every example in `examples.py` demonstrates it, and
`_check_lookahead()` in `engine.py` warns when positions correlate
suspiciously with the same day's return.

For `EventStrategy` it is enforced by construction: `on_bar()` sees bars
`0..t` and its decision is written to `positions[t + 1]`. That is exactly a
`.shift(1)`, and `test_event_version_matches_vectorized_version_exactly`
proves it by reproducing `ShortTermReversal` bit for bit. Do not change
`_walk()` in a way that breaks that test.

`LookaheadCheater` in `strategies/examples.py` is **deliberately broken** and
must stay that way — fellows run it to see what cheating looks like.

### 5. Fees are charged on position *change*, not on every day

```python
turnover = positions.diff().abs().fillna(positions.abs())
```

A position held from one day to the next costs nothing. Flipping +1 → -1
trades two units of equity and pays two fees.

### 6. Every dataset has the same columns

`load()` always returns `open, high, low, close, volume, simple_return,
log_return` (NaN where the source lacks a column), whatever the file looked
like. A strategy developed on one dataset must not crash on the held-out
one because a column is missing. For stocks, `Adj Close` wins over `Close`.

### 7. Every EventStrategy run starts from a fresh copy

`generate_positions()` deep-copies the strategy before walking the data, so
state a fellow stores on `self` cannot leak between runs (the app runs a
strategy for the Performance tab and reuses positions for the Costs tab;
`compete.py` runs each once). `test_runs_do_not_leak_state` guards this.

## Layout

```
bsequant/
  strategy.py    EventStrategy (on_bar, go_long/go_short/go_flat) and the
                 column-at-a-time Strategy ABC it builds on
  data.py        loading any common CSV, train/test split, frequency inference
  engine.py      run / run_positions, metrics, trade log, lookahead
                 detection, cost sweep
strategies/
  event_examples.py  mean reversion, breakout momentum, dip buy with stop
  examples.py        column-at-a-time reference strategies (incl. the cheater)
  my_strategy.py     the template fellows edit (EventStrategy)
data/            CSVs; any file dropped here appears in the dropdown
app.py           Streamlit UI (6 tabs: Performance / Risk / Costs / Year /
                 Trade log / Data)
compete.py       batch runner + static HTML leaderboard
submissions/     mock submissions for testing compete.py
tests/           pytest suite: regression table, invariants, event API,
                 loader, trade log, headless app smoke test
docs/            PLAN.md (roadmap), EVENT_STRATEGIES.md (design report)
```

Both strategy styles reach the engine the same way: the engine only ever
sees a position series. `run()` = `generate_positions()` + `run_positions()`.
The app caches positions per (strategy source, parameters, dataset, period),
so moving the fee slider does not re-run a bar-by-bar strategy.

Strategies are discovered by reflection: `app.py` imports every non-underscore
`.py` in `strategies/` and finds `Strategy` subclasses. Any `__init__`
argument with a default becomes a sidebar widget automatically.

## Running and verifying

```bash
pip install -r requirements.txt
streamlit run app.py
python compete.py --submissions submissions --data BCH-1d --fee 10 --html leaderboard.html
```

### Regression checks

On the bundled `BCH-1d` dataset (1,460 rows, 2022-04-14 → 2026-04-12,
inferred ppy = 365), these values must hold. If a change moves them, the
change is wrong unless it was *supposed* to move them:

| Strategy | fee | Sharpe | Total return | Max DD | Win rate | Trades |
|---|---|---|---|---|---|---|
| ShortTermReversal | 0 | 0.9028 | 352.82% | -76.49% | 52.88% | 774 |
| ShortTermReversal | 1.5 | 0.8351 | 259.39% | -77.03% | 52.81% | 774 |
| BuyAndHold | 0 | 0.4715 | 24.82% | -74.01% | 49.66% | 0 |

Yearly returns for ShortTermReversal @1.5bps:
`2022 +62.6%, 2023 +54.6%, 2024 -48.1%, 2025 +132.7%, 2026 +18.4%`

`LookaheadCheater` must produce Sharpe ≈ 16.4 **and exactly 1 warning**.

```python
import sys; sys.path.insert(0, ".")
import bsequant as bq
from strategies.examples import ShortTermReversal

d = bq.load("BCH-1d")
m = bq.run(ShortTermReversal(), d, fee_bps=1.5).metrics
assert abs(m["sharpe"] - 0.8351) < 1e-3
assert abs(m["total_return"] - 2.5939) < 1e-3

a = bq.run(ShortTermReversal(), d, fee_bps=10, periods_per_year=365).metrics
b = bq.run(ShortTermReversal(), d, fee_bps=10, periods_per_year=252).metrics
assert a["total_return"] == b["total_return"]      # not annualized
assert a["max_drawdown"] == b["max_drawdown"]      # not annualized
assert a["sharpe"] != b["sharpe"]                  # is annualized
```

All of the above is automated:

```bash
pip install -r requirements-dev.txt
python -m pytest            # from backtester/; about 20 seconds
```

Run it before every commit. It passes on Python 3.9 (pandas 2.3) and 3.11
(pandas 3.0).

## Decisions already made (do not re-litigate without asking)

- **Streamlit, not a JS frontend.** Fellows write Python; the instructor did
  not want to maintain JS.
- **Not deployed to Vercel.** Vercel is serverless with short execution
  limits, and hosting would mean running arbitrary student Python on someone
  else's machine. Fellows run it locally. Only the generated
  `leaderboard.html` is a static file suitable for hosting.
- **Not C++.** ~1,500 rows is instant in pandas; C++ would cost the ecosystem
  and gain nothing.
- **Ranking is by Sharpe, not raw return**, and flagged strategies stay on the
  leaderboard with a ⚠️ rather than being removed — being publicly caught is
  the lesson.
- **Python 3.9+** — `from __future__ import annotations` is at the top of
  every module specifically to keep 3.9 working. Keep it there.

## Known open items

- Auto-detect snapping (within 5% of a common frequency) may be too magic for
  a teaching tool; the instructor may prefer showing the raw computed value.
- `submissions/` contains mock files (alice, bob, carol_cheater) deliberately
  left in for testing. Remove before distributing to fellows.
- Only one dataset ships. A held-out dataset for demo day still needs to be
  chosen and kept out of the fellows' copy.
- EventStrategy fills at the bar's close. A stop-loss is checked at the
  close too, so a gap can exit well past the stop (the dip-buy example has a
  -15% exit on a -5% stop). Intrabar stops would need high/low fill logic.
- EventStrategy costs ~70 µs per bar of loop overhead plus whatever on_bar
  does; ~2 s per run for a year of hourly bars. Fine for daily data and the
  app caches positions, but minute data over years would be slow.
- Fee model uses one rate for both sides. Real exchanges charge different
  maker and taker fees; entering/exiting at the close means crossing the
  spread, so taker is arguably the honest rate.

## Style

- Comments explain **why**, not what. Assume the reader is a smart freshman
  who has never backtested anything.
- Prefer a named intermediate variable over a clever one-liner.
- Keep the plain-ASCII arrows and box characters already used in docstrings;
  they render fine in terminals fellows may be using.
