# BSE Quant Backtester

A teaching backtester for the BSE fellowship quant track. Write a strategy in
a few lines of Python, get a full performance report in your browser.

```
pip install -r requirements.txt
streamlit run app.py
```

Then open http://localhost:8501.

---

## Writing a strategy

Open `strategies/my_strategy.py`. Your code is called once per bar (once a
day on daily data), sees only the past, and decides whether to open or close
a position:

```python
from bsequant import EventStrategy

class MyStrategy(EventStrategy):
    name = "Buy the dip"
    description = "Buy 5% below the 20-day average, sell back at the average."

    def on_bar(self, bar, history):
        average = history["close"].tail(20).mean()

        if self.position == 0 and bar["close"] < average * 0.95:
            self.go_long()                 # open a long position
        elif self.position > 0 and bar["close"] >= average:
            self.go_flat()                 # close it
```

Save the file, hit **Reload strategy files** in the sidebar, and it appears in
the dropdown. Any `__init__` argument with a default becomes a slider.

| You can call | It means |
|---|---|
| `self.go_long(size=1.0)` | hold `+size` of your equity from the next bar |
| `self.go_short(size=1.0)` | hold `-size` from the next bar |
| `self.go_flat()` | close your position from the next bar |
| `self.set_position(x)` | hold exactly `x` from the next bar |

| You can read | It is |
|---|---|
| `bar["close"]`, `bar["high"]`, ... | the bar that just closed; `bar.name` is its date |
| `history` | every bar up to and including this one |
| `self.position` | your current position (`1.0`, `0.0`, `-1.0`, `0.5`, ...) |
| `self.entry_price`, `self.entry_time` | where and when you opened the current trade |
| `self.bars_held` | how many bars you have been in the trade |

Any kind of strategy fits this shape: mean reversion, momentum, breakouts,
stop-losses, time limits. `strategies/event_examples.py` has one of each.

**Position convention:** `1.0` fully long, `0.0` flat, `-1.0` fully short.
Fractions are allowed.

### Timing: how precise can my trades be?

Exactly as precise as the data. You decide at the **close** of a bar and your
position starts earning from the **next** bar. On daily data that means once
a day; on hourly data, once an hour. To trade more often, use more granular
data (see [Adding data](#adding-data)).

Because `on_bar` only ever sees bars that have already closed, you cannot
accidentally use the future. If your Sharpe is above 3 anyway, you have a bug,
not an edge.

### The other way: a whole column at once

`strategies/examples.py` shows the original style: subclass `Strategy` and
return every position at once with pandas. It is faster on very large
datasets, but you must end every signal with `.shift(1)` yourself:

```python
from bsequant import Strategy
import numpy as np

class FadeYesterday(Strategy):
    name = "Fade yesterday"

    def generate_positions(self, data):
        signal = -np.sign(data["log_return"])
        return signal.shift(1)          # <- the important part
```

Without the shift you are using today's return to decide today's trade,
which is impossible in real life and makes results look spectacular. The
engine checks for this and warns you; run the `[BROKEN] Lookahead cheater`
example to see what that looks like. Both styles produce identical results
for the same idea.

---

## What you get

| Tab | What it answers |
|---|---|
| **Performance** | Did it make money? How does it compare to just holding? |
| **Risk** | How bad did it get? Would you have held through it? |
| **Costs** | At what fee level does the edge disappear? |
| **Year by year** | Did it work every year, or just one lucky stretch? |
| **Trade log** | Every trade: when it opened and closed, at what price, and what it made. Check your strategy trades where you meant it to. |
| **Data** | The per-bar numbers, downloadable as CSV. |

### Reading the results honestly

- **Compare against buy and hold.** A 300% return means little if holding the
  asset returned 280%.
- **Check the Test period, not just Full history.** Develop on Train, judge on
  Test. The gap between them is the only honest estimate of the future.
- **Watch the cost curve.** Retail crypto fees are roughly 10 bps per side. A
  strategy that only works at 0 bps is not a strategy.
- **Look at the worst year.** A real edge can vanish for twelve months. If you
  would have quit during that stretch, the total return is fiction.

---

## Project layout

```
CLAUDE.md          context for AI assistants working on this repo
bsequant/          the engine - you do not need to edit this
  strategy.py      EventStrategy and Strategy, the two ways to write one
  data.py          loading any CSV, train/test split
  engine.py        backtest, metrics, trade log, lookahead detection
strategies/
  event_examples.py  mean reversion, momentum, stop-loss - read these first
  examples.py        column-at-a-time examples, incl. a deliberate cheater
  my_strategy.py     your work goes here
tests/             pytest suite (pip install pytest; python -m pytest)
data/              CSV datasets
app.py             the web UI
compete.py         competition runner (instructor)
```

---

## Competition (instructor)

Collect submissions as one `.py` file per fellow, then:

```bash
python compete.py --submissions submissions/ --data HELDOUT --fee 10 \
                  --html leaderboard.html
```

Every strategy implements the same interface, so they all run identically
without touching anyone's code. Ranking is by Sharpe rather than raw return,
and anything flagged for lookahead bias or account wipeout is marked.

The generated `leaderboard.html` is a static file — drop it on Vercel, GitHub
Pages, or anywhere else if you want to publish results.

---

## Periods per year

Sharpe is annualized by multiplying by **√(periods per year)**, and that
number is set in the sidebar.

It is not a magic constant — it is *how many return observations your data
contains in a year*:

| Data | Periods per year |
|---|---|
| Daily crypto | **365** — never closes |
| Daily equities | **252** — trading sessions after weekends and holidays |
| Weekly | 52 |
| Monthly | 12 |
| Hourly crypto | 8,760 |

The app auto-detects this from the spacing of your dates and shows the value
it picked, but you can override it. Changing it rescales Sharpe, annualized
return, and volatility — it never changes total return, because total return
is not annualized.

One subtlety worth knowing: this depends on the frequency of the **return
series**, not on how often your strategy trades. A strategy that only takes a
position once a month on daily data still uses the daily factor, because you
are still measuring returns every day.

## Adding data

Drop a CSV in `data/` and it appears in the dataset dropdown. Name it
`SYMBOL-INTERVAL.csv` (`SPY-1d.csv`, `BTC-1h.csv`). Daily, hourly or any other
frequency works, and the frequency is detected on load.

The file needs a date column and a close column. Common exports (crypto
exchanges, Yahoo Finance) work as-is; these column names are recognized,
ignoring upper/lower case:

| Needed | Recognized names |
|---|---|
| date | `date`, `datetime`, `timestamp`, `time`, `t`, `open_time` (text dates or Unix timestamps) |
| close | `Adj Close` (preferred for stocks), `close`, `c` |
| open / high / low | `open`/`o`, `high`/`h`, `low`/`l` (optional) |
| volume | `volume`, `vol`, `v` (optional) |

Missing optional columns become empty (NaN). Times with a time zone are
converted to UTC.

**Stocks: use adjusted prices.** An unadjusted close shows a 4-for-1 stock
split as a 75% crash in one day. When a file has both `Close` and
`Adj Close`, the adjusted one is used.
