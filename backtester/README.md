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

Open `strategies/my_strategy.py` and fill in one method:

```python
from bsequant import Strategy
import numpy as np

class MyStrategy(Strategy):
    name = "My strategy"
    description = "Fade yesterday's move."

    def generate_positions(self, data):
        signal = -np.sign(data["log_return"])
        return signal.shift(1)          # <- the important part
```

Save the file, hit **Reload strategy files** in the sidebar, and it appears in
the dropdown. Any `__init__` argument with a default becomes a slider.

**Position convention:** `1.0` fully long, `0.0` flat, `-1.0` fully short.
Fractions are allowed.

### The one rule

Every signal must end in `.shift(1)`.

Your position for day *t* may only use data from day *t-1* or earlier. Without
the shift you are using today's return to decide today's trade, which is
impossible in real life and will make your results look spectacular.

The engine checks for this and warns you. If your Sharpe is above 3, you have
a bug, not an edge. Run the `[BROKEN] Lookahead cheater` example to see what
cheating looks like.

---

## What you get

| Tab | What it answers |
|---|---|
| **Performance** | Did it make money? How does it compare to just holding? |
| **Risk** | How bad did it get? Would you have held through it? |
| **Costs** | At what fee level does the edge disappear? |
| **Year by year** | Did it work every year, or just one lucky stretch? |
| **Data** | The per-day numbers, downloadable as CSV. |

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
  strategy.py      the Strategy base class
  data.py          loading and train/test split
  engine.py        backtest, metrics, lookahead detection
strategies/
  examples.py      read these first
  my_strategy.py   your work goes here
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

Drop a CSV in `data/` with columns `t, o, c, h, l` (date, open, close, high,
low). It appears in the dataset dropdown automatically, and its frequency is
detected on load.
