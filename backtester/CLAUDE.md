# CLAUDE.md — context for working on this repo

## What this is

A backtester built as a **teaching tool** for the Bruin Software Engineers
fellowship quant track (Fall 2026, 4 weeks, ~8-10 freshmen with weak Python
and no finance background).

It is used two ways:

1. **During the track** — fellows write a strategy in one method, run
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

### 4. Every strategy signal ends in `.shift(1)`

The position for day *t* may only use data from *t-1* or earlier. Every
example strategy demonstrates this, and `_check_lookahead()` in `engine.py`
warns when positions correlate suspiciously with the same day's return.

`LookaheadCheater` in `strategies/examples.py` is **deliberately broken** and
must stay that way — fellows run it to see what cheating looks like.

### 5. Fees are charged on position *change*, not on every day

```python
turnover = positions.diff().abs().fillna(positions.abs())
```

A position held from one day to the next costs nothing. Flipping +1 → -1
trades two units of equity and pays two fees.

## Layout

```
bsequant/
  strategy.py    Strategy ABC - the interface fellows implement
  data.py        loading, train/test split, frequency inference
  engine.py      backtest, metrics, lookahead detection, cost sweep
strategies/
  examples.py    reference strategies (read-only for fellows)
  my_strategy.py the template fellows edit
data/            CSVs; any file dropped here appears in the dropdown
app.py           Streamlit UI (5 tabs: Performance / Risk / Costs / Year / Data)
compete.py       batch runner + static HTML leaderboard
submissions/     mock submissions for testing compete.py
```

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

There is no test suite yet — adding `pytest` tests around the invariants above
would be a genuinely useful contribution.

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
- Fee model uses one rate for both sides. Real exchanges charge different
  maker and taker fees; entering/exiting at the close means crossing the
  spread, so taker is arguably the honest rate.

## Style

- Comments explain **why**, not what. Assume the reader is a smart freshman
  who has never backtested anything.
- Prefer a named intermediate variable over a clever one-liner.
- Keep the plain-ASCII arrows and box characters already used in docstrings;
  they render fine in terminals fellows may be using.
