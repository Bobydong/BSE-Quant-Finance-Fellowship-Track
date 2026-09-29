# Backtester plan: from prototype to something 10 fellows can use

Status: **proposal for review**. Nothing in here has been built yet. Every
claim marked *verified* was tested on 2026-09-29 against the code in this
folder; the scripts are described inline so they can be re-run.

---

## TL;DR

The engine is sound: every regression number in `CLAUDE.md` reproduces, on
both pandas 2.0 and 3.0, and the app runs end to end. What it lacks is not
features but **robustness at the edges**: it reads exactly one file format,
it will break on the next Streamlit release, one script crashes on Windows,
and the competition runner trusts every submission completely.

Recommendations, in priority order:

1. **Keep the core contract** (`data` in, one position per day out) and keep
   everything local. No hosted service.
2. **Let fellows write a plain function** instead of a class. A thin adapter
   wraps it, so the engine and every invariant stay untouched.
3. **Generalize the data loader** so any common crypto or stock CSV drops in,
   with a small metadata file per dataset. Stocks must use adjusted prices.
4. **Add a `check.py` validator** fellows run before submitting. Collect
   submissions privately via a Google Form file upload.
5. **Replace the lookahead heuristic with a truncation test** that catches
   subtle cheating the current check misses (verified below).
6. **Harden `compete.py`**: one subprocess per submission with a timeout,
   one entry per fellow, HTML escaping, UTF-8 output, duplicate detection.
7. **Make it install the same way on Windows and Mac** with pinned versions
   and a CI matrix that runs the tests on both.
8. **Offer GitHub Codespaces as the zero-install fallback.** It runs in the
   browser over HTTPS, so it works on eduroam even if a laptop won't cooperate.

Decisions I need from you are collected in [section 10](#10-decisions-for-bryan).
Each has a default, so none block starting.

---

## 1. What I verified tonight

| Check | Result |
|---|---|
| Uploaded `BCH-1d.csv` vs the copy in the zip | Byte-identical; already committed |
| Regression table in `CLAUDE.md` | All values reproduce exactly |
| Same checks on pandas 2.0.3 and 3.0.6 | Identical numbers |
| `app.py` run headlessly (Streamlit `AppTest`) with all 7 strategies | No exceptions |
| `app.py` deprecation warnings | 88 x "`use_container_width` will be removed after 2025-12-31" |
| Streamlit default `server.address` | Unset, which means it listens on **all** network interfaces |
| Loading a Yahoo-style stock CSV (`Date, Open, ..., Adj Close`) | **Fails**: `KeyError: 'date'` |
| Loading an hourly crypto CSV (`timestamp, open, ...`) | **Fails**: same error |
| Unadjusted close across a 4:1 stock split | Shows a **-75.2%** one-day "return" (adjusted: -0.69%) |
| `compete.py` HTML output on Windows | Will crash: `write_text()` without `encoding=`; `⚠️` is not encodable in cp1252 |
| `compete.py` with a file holding two strategies | Both get leaderboard rows |
| `compete.py` with a strategy named `<b>bold</b>` | Injected raw into the HTML |
| `compete.py` with two identical files | Not detected |

Fetching live stock data was not possible from my environment (the network
policy blocks data sites), so the stock tests used synthetic data with the
same column layout as a Yahoo Finance export.

---

## 2. Constraints this plan is designed around

- **Audience**: ~8-10 freshmen, weak Python, no finance. Readability beats
  cleverness; UI text is curriculum (`CLAUDE.md`).
- **Machines**: a mix of Windows and Mac. Whatever fellows touch must work
  identically on both.
- **Network**: UCLA eduroam. See [section 5.1](#51-eduroam-and-localhost) —
  the concern is real, but it applies to device-to-device traffic, not to
  localhost.
- **Distribution**: fellows fork and/or clone this repo. It is public.
- **Submission**: fellows write their strategy in one Python file; you
  download the files and run them.
- **Data**: crypto and stocks, switchable. The bundled BCH data is not the
  competition data.
- **Binding decisions** from `CLAUDE.md` still hold: Streamlit, not JS;
  Python, not C++; rank by Sharpe; flagged strategies stay on the board;
  Python 3.9+ (though see decision D6).

---

## 3. The standard contract (inputs and outputs)

"Backtest any strategy" works only because every strategy has the same
shape. This is the part to get right, because every fellow writes against it.

### 3.1 Input: `data`

A pandas DataFrame, one row per bar, that is identical for every strategy:

| Column | Meaning | Always present |
|---|---|---|
| index | bar timestamp, sorted, unique | yes |
| `open`, `high`, `low`, `close` | prices; for stocks, **split- and dividend-adjusted** | yes |
| `volume` | traded volume; `NaN` where the source has none | yes (may be NaN) |
| `simple_return` | `close_t / close_{t-1} - 1` | yes |
| `log_return` | `ln(close_t / close_{t-1})` | yes |

Two changes from today:

- `volume` becomes always present (NaN when unknown) so a fellow's code does
  not crash when switching datasets. Today it silently disappears when the
  source lacks it, and on the BCH file it is `0` (not missing) for the first
  443 rows.
- Source-specific columns (like BCH's `trades`) are dropped. Anything a
  strategy can see must exist on every dataset, or a strategy that works in
  development can crash on the competition data.

### 3.2 Output: positions

A Series aligned to `data.index`:

- `1.0` fully long, `0.0` flat, `-1.0` fully short; fractions allowed.
- `NaN` means flat (already the case: `fillna(0.0)`).
- `|position| > 1` is leverage: allowed, warned (already the case).
- The position for bar *t* may use data from bar *t-1* or earlier.
- Deterministic: same data in, same positions out.

### 3.3 Function, not class (decision D1)

You described fellows "writing a function". I agree, and recommend making
that literal. Today fellows must subclass an abstract base class, override a
method, and understand `self`. For freshmen with weak Python that is three
concepts before they write any finance. Proposed template:

```python
# strategies/my_strategy.py
AUTHOR = "Jane Doe"
NAME = "Fade big moves"
HYPOTHESIS = """After a large one-day move, price tends to partially
reverse the next day, because short-term traders overreact."""

def generate_positions(data, threshold: float = 0.02):
    move = data["log_return"]
    signal = pd.Series(0.0, index=data.index)
    signal[move > threshold] = -1.0
    signal[move < -threshold] = 1.0
    return signal.shift(1)
```

- Keyword arguments with defaults become sidebar sliders, exactly as
  `__init__` arguments do today.
- A ~20-line adapter in `bsequant/` wraps the function into a `Strategy`, so
  `engine.run()`, every invariant, and every regression number are untouched.
- The class-based `Strategy` stays for `examples.py` and anyone who wants it.
  Fellows only ever see the function form in the template.
- `AUTHOR` inside the file means the filename no longer matters, which
  matters because Google Forms renames uploads (see 7.3).

### 3.4 Scope: single asset (decision D2)

Everything above is one asset at a time. Multi-asset strategies (pairs,
ranking a basket, rotation) need `data` to become a panel and positions to
become a DataFrame of weights. That is a real redesign of the engine, the
metrics, and the UI.

**Recommendation: stay single-asset for this 4-week track.** Fellows can
still switch *which* asset they test on, which covers "crypto or stocks".
Multi-asset is a clean phase-2 extension later because positions would just
gain columns; nothing proposed here blocks it.

### 3.5 Why not an event-driven `on_bar()` API

The alternative design calls the strategy once per bar with only past data,
which makes lookahead impossible by construction. I considered it and
recommend against switching:

- It removes the lesson. `CLAUDE.md` is explicit that being caught cheating
  is the point, and the truncation test in section 6 catches cheating just as
  reliably without taking the pandas style away.
- Per-bar loops are the slow, unidiomatic way to write pandas, and they are
  what fellows would then learn.

---

## 4. Data: switching sources easily

### 4.1 One canonical file format, many accepted inputs

**Canonical file** in `data/`: `SYMBOL-INTERVAL.csv`
(`BCH-1d.csv`, `SPY-1d.csv`, `BTC-1h.csv`) with columns
`date, open, high, low, close, volume`.

**The loader accepts common exports as-is** by recognizing column aliases, so
a fellow can drop in a file downloaded from almost anywhere:

| Canonical | Accepted aliases (case-insensitive) |
|---|---|
| `date` | `date`, `datetime`, `timestamp`, `time`, `t`, `open_time` |
| `open` / `high` / `low` / `close` | full names, or `o` / `h` / `l` / `c` |
| `close` (stocks) | **`adj close` / `adj_close` preferred over `close` when both exist** |
| `volume` | `volume`, `vol`, `v` |

Plus cleaning, each with a plain-English error message:

- Parse dates; if timestamps carry a timezone, convert to UTC then drop it.
- Sort; drop exact duplicate rows; **error** on duplicate timestamps with
  different prices (the file is broken; do not guess).
- Error on non-positive prices; error when a required column is missing,
  listing the columns that *were* found.
- Leave gaps alone: weekends in stock data are real, and
  `infer_periods_per_year()` already handles them (252 vs 365).

The BCH regression numbers must not move; a test will pin that.

### 4.2 Optional metadata sidecar

`data/SPY-1d.json` next to the CSV, all fields optional:

```json
{
  "asset_class": "equity",
  "source": "Yahoo Finance via yfinance",
  "adjusted": true,
  "fetched": "2026-09-30",
  "notes": "Daily, split- and dividend-adjusted."
}
```

The app shows this under the dataset dropdown. It teaches fellows that data
has provenance, and it records what we could not reconstruct for BCH.

### 4.3 Where data comes from (instructor side only)

Fellows never download data live. The app stays offline, and every fellow
sees identical numbers for the same dataset. You (or I) fetch data once with
a script in `tools/` and commit the CSV plus its metadata.

| Source | Covers | Key? | Notes |
|---|---|---|---|
| Yahoo Finance via `yfinance` | stocks, ETFs, major crypto (`BTC-USD`) | no | Unofficial, can break without notice; returns adjusted prices |
| Coinbase Exchange public candles API | crypto | no | Reachable from the US; paged (about 300 candles per request) |
| Binance.com | crypto | no | **Blocks US IP addresses**; Binance.US is the US option |
| Kaggle datasets | both | account | Static snapshots; good for a frozen competition set |

Suggested `tools/fetch_data.py SPY --interval 1d --start 2018-01-01` for
Yahoo, and a Coinbase variant for crypto. These are instructor tools; they do
not go in `requirements.txt`.

**About the current BCH file**: the raw columns
(`t, T, s, i, o, c, h, l, v, n`, with `T` ending in `23:59:59.999`) match
Binance's kline format, so it very likely came from Binance or a wrapper
around it. Volume and trade count are `0` for every row up to 2023-06-29
(443 rows), which suggests the early history was stitched from a source
without volume. A volume-based strategy would be misled there. I would note
this in `BCH-1d.json` rather than change the file.

### 4.4 Competition data stays out of the repo

The repo is public, so the demo-day dataset must never be committed.
`compete.py --data` should accept a **path** (`--data ~/private/HELDOUT.csv`)
as well as a dataset name, so the file can live anywhere on your machine.

Which held-out set to use is decision D5. The main options:

- **Same asset, later period**: the purest test of "did your idea survive
  the future".
- **Different asset**: tests whether the idea generalizes. It is harsher and
  noisier for a 4-week track.

---

## 5. How fellows run it

### 5.1 eduroam and localhost

`localhost` (127.0.0.1) traffic never leaves the laptop, and never touches the
Wi-Fi, so eduroam cannot block a fellow opening their own
`http://localhost:8501`. What campus networks typically *do* block is one
device reaching another (client isolation). That rules out one person
hosting the app from their laptop for others. It does not affect everyone
running their own copy.

Two practical risks remain, both fixable:

- **Windows firewall prompt.** Streamlit's default listens on all network
  interfaces (verified), which makes Windows Defender ask "allow access?" on
  first run, and a nervous freshman clicks Cancel. Setting
  `server.address = "localhost"` in `.streamlit/config.toml` avoids exposing
  the app to the network at all and should avoid the prompt.
- **Installing packages** needs normal HTTPS to PyPI, which eduroam allows.
  Worth a 5-minute test on campus Wi-Fi before week 1 anyway.

### 5.2 Install path (decision D6)

The largest real risk for Windows freshmen is not the code but Python
itself: several Python installs, `python` vs `py`, PATH, venv activation in
PowerShell. Two options:

- **`uv` (recommended).** One installer per OS, then from the repo folder
  `uv run streamlit run app.py`. `uv` downloads the right Python, creates the
  environment, and installs pinned versions. The same command works on
  Windows and Mac. It costs one extra tool to learn, but removes most setup
  failures.
- **Plain `pip` + venv.** Documented as the fallback, with separate
  copy-pasteable blocks for PowerShell and macOS Terminal.

Either way, versions get pinned to a tested set (see 8.2).

### 5.3 Fallbacks that need no local setup

| Option | Works on eduroam | Setup | Recommendation |
|---|---|---|---|
| Local Streamlit | yes (localhost) | install once | **Primary** |
| GitHub Codespaces | yes (HTTPS) | none; runs in the browser | **Fallback** for broken laptops. Add a `.devcontainer/` so it opens ready to run; the free personal quota (about 60 hours a month on a 2-core machine) is plenty for 4 weeks |
| Command line only (`python run.py`) | yes | install once | Tiny addition. Prints the text summary with no browser, so it is useful for debugging |
| Streamlit Community Cloud | yes | fellow deploys their fork | Not recommended: every code change needs a push-and-redeploy cycle, which is slow while developing |
| A hosted service you run | yes | you build and maintain it | **Not recommended**: it means executing untrusted student code on your server (sandboxing, uptime, cost). `CLAUDE.md` already rejected hosting for the same reason |

---

## 6. Catching lookahead reliably

The engine's current check correlates positions with the same day's return.
It catches the textbook mistake but misses subtler ones.

**Truncation test.** Pick a bar *k*, cut the data off at *k*, scramble bar
*k*'s price, and re-run the strategy. A legitimate strategy's position for
bar *k* cannot change, because it may only use bars before *k*. If it
changes, the strategy used information it could not have had. Repeat for
about 25 bars chosen with a fixed seed.

Prototype results on `BCH-1d` at 10 bps (*verified*):

| Strategy | Sharpe | Current check | Truncation test |
|---|---|---|---|
| Buy and hold, reversal, momentum, MA crossover, threshold, template | -1.35 to 0.51 | ok | ok |
| `LookaheadCheater` (no `.shift(1)`) | 15.85 | FLAG | FLAG |
| z-score using the **full-sample** mean and std | **0.89** | **missed** | FLAG |
| centered rolling window (`center=True`) | -5.66 | **missed** | FLAG |
| `.shift(-1)` typo | -2.30 | **missed** | FLAG |
| tomorrow's return, then shifted once | 15.84 | FLAG | FLAG |

There were no false positives. The z-score case is the important one: a
Sharpe of 0.89 looks like a genuinely good strategy, and normalizing with the
whole series' mean is exactly the mistake a careful freshman makes.

Plan:

- Scramble bar *k* both up and down, so a sign-based cheat cannot slip
  through half the samples. The prototype only scrambled upward and caught
  12/25.
- Put it in the engine, and **fold both detectors into the one existing
  lookahead warning**, so `LookaheadCheater` still produces exactly 1
  warning and the regression table stays true.
- Run it in `check.py` and `compete.py` too.
- Add the z-score cheat to `examples.py` as a second `[BROKEN]` example.
  It teaches that lookahead is not just a missing `.shift(1)`.

Cost: about 25 extra calls per run. Those are milliseconds on 1,500 rows, but
the cost sweep also calls `run()`, so the app should run the check once per
render rather than inside the sweep.

---

## 7. Strategy workflow, submissions and the competition

### 7.1 The structure fellows follow

The template already encodes indicator, then signal, then shift. I would add
a short `GUIDE.md` that turns it into a repeatable loop, with the template's
comments pointing at each step:

1. **Hypothesis** in one sentence, before any code (`HYPOTHESIS` field;
   `check.py` rejects the template's placeholder text).
2. **Indicator**: a number computed from past data, no claim attached.
3. **Signal**: the indicator plus a claim about what happens next.
4. **Position**: signal sized to [-1, 1], then `.shift(1)`.
5. **Evaluate on Train**: beat buy and hold? Survive 10 bps? Worst year?
6. **Change one thing at a time**, and write down what changed.
7. **Look at Test exactly once** before submitting. Every extra peek turns
   Test into Train.
8. **Run `check.py`**, then submit.

Optional but cheap: a `NOTES` string in the submission file for what they
tried and what Train vs Test showed. It gives you something to discuss at demo
day beyond one Sharpe number.

### 7.2 `check.py`: fellows validate before submitting

`python check.py strategies/my_strategy.py` prints a pass/fail checklist in
plain English:

- File imports cleanly, and uses only `numpy`, `pandas` and `math`
  (checked by reading the code, not by running it).
- Exactly one strategy in the file; `AUTHOR`, `NAME` and `HYPOTHESIS` filled
  in and not left as template text.
- Returns a Series of the right length, numeric, no infinities.
- Passes the truncation lookahead test.
- Runs in under a few seconds.
- Prints the Train-period summary so they know the file really works.

Fellows fix their own problems before you ever see the file, and on demo day
nothing fails to import.

### 7.3 Collecting submissions (decision D3)

| Option | Private | Effort for fellows | Effort for you |
|---|---|---|---|
| **Google Form with a file upload, restricted to UCLA accounts** | yes | upload one file | download the folder as a zip |
| Shared Google Drive folder | partly (fellows can see each other's) | drag and drop | none |
| Pull request to this repo | **no**: public repo, everyone sees everything | git skills | review and merge each PR |
| Each fellow's fork, fetched by a script at the deadline | **no**: forks of a public repo are public | push to their fork | list of fork URLs |
| GitHub Classroom private repos | yes | git skills | setup |

**Recommendation: Google Form.** It is private, needs no git skills, sign-in
records who uploaded what and when, and responses can be closed at the
deadline. Forms renames uploads (roughly `my_strategy - Jane Doe.py`), which
is why the author lives inside the file (3.3), not in its name.

Rules to state up front:

- One file, **one strategy**.
- The parameter defaults in the file are what runs.
- Last upload before the deadline counts.

### 7.4 Hardening `compete.py`

| Change | Why |
|---|---|
| Run each submission in its own subprocess with a 60 s timeout | One infinite loop cannot hang demo day. A submission also cannot monkey-patch `bsequant` and change *other* fellows' results, which is possible today because everything shares one process |
| One entry per fellow; reject files with more than one strategy | Today a file with 10 variants gets 10 rows, which rewards trying many things and reporting the best. That is the overfitting lesson in reverse |
| Escape names with `html.escape` | Verified: names go into the HTML raw |
| `write_text(..., encoding="utf-8")` | Verified: `⚠️`, `✓` and `→` are not encodable in Windows' default encoding, so the HTML write crashes whenever anyone is flagged |
| `--data` accepts a path | The held-out set stays off the public repo (4.4) |
| Flag identical position series across authors | Verified: two identical files are not detected today |
| Add a buy-and-hold benchmark row | "Did anyone beat just holding?" should be visible on the board |
| Run the truncation test on every submission | Catches the subtle cheats in section 6 |
| Optional: a one-page report per fellow (equity curve on the held-out data) | Gives each fellow something to look at beyond their rank |

**Safety note.** Running fellows' files executes their code on your laptop.
The import check in `check.py` and `compete.py` catches accidents (file
access, network calls). It is not a sandbox. With about 10 known students and
files of about 30 lines, skimming each file before running is the real
safeguard. If you want isolation, the competition could run in a GitHub
Actions job instead, but that adds setup and needs the held-out data kept as
a secret.

---

## 8. Engineering quality

### 8.1 Tests and CI

- `backtester/tests/` with `pytest`, covering:
  - every invariant in `CLAUDE.md` (simple returns, `cumprod`,
    periods-per-year never affecting total return or drawdown, fees on
    change only);
  - the regression table;
  - the loader aliases, adjusted-close preference and errors;
  - the truncation test (including the cheat cases above);
  - a headless `AppTest` smoke run of the UI.
- Move `submissions/alice.py`, `bob.py` and `carol_cheater.py` into
  `tests/fixtures/`, so the fellows' copy starts clean but the tests keep them.
- A GitHub Actions workflow runs the suite on **Windows, macOS and Linux**,
  on the oldest and newest supported Python. This is how "works for everyone"
  gets checked without owning a Windows laptop. It is free for public repos.

### 8.2 Dependencies

- Today: `streamlit>=1.30`, no upper bound. The app passes 88 times through
  an API that Streamlit says "will be removed after 2025-12-31", so a fresh
  install could break without any change on our side. Fix: replace
  `use_container_width=True` with `width="stretch"`, and pin a tested version
  range.
- pandas 3 requires Python 3.11+, so a fellow on 3.9 or 3.10 silently gets
  pandas 2. Results matched on 2.0.3 and 3.0.6 tonight, but the CI matrix
  should keep proving that. With `uv` (D6) everyone gets the same Python, and
  the question disappears.

### 8.3 Small UI fixes found while reading

- The app's default fee is **1.5 bps**, but `compete.py` judges at **10 bps**.
  Fellows would develop against a cost that flatters them. Recommend the app
  default to the competition fee (D4). This does not change any regression
  number; those are computed at explicit fees.
- Buy and hold reports 0 trades but pays an entry fee. Count the initial
  entry as a trade, or relabel the metric "position changes". Check whether
  the regression "Trades" column would move first; it currently expects 0 for
  buy and hold.
- The cheater's total return prints as a 20-digit percentage. Display
  anything above about 10,000% as "> 10,000%".

---

## 9. Roadmap

Sized so each phase is reviewable on its own. Every phase lands on a branch
off `rewrite`, per the repo's branch flow.

**Phase 1: before fellows clone the repo**

- Pin dependencies; fix the `use_container_width` deprecation; set
  `server.address = "localhost"`.
- `pytest` suite with regression and invariant tests; CI on Windows, macOS
  and Linux.
- Generalized loader, metadata sidecar, BCH provenance note.
- Function-style template and adapter (D1); `GUIDE.md`.
- `check.py`.
- Setup instructions for Windows and Mac (D6); move mock submissions into
  test fixtures.

**Phase 2: before demo day**

- Truncation lookahead test in the engine, `check.py` and `compete.py`;
  z-score `[BROKEN]` example.
- `compete.py` hardening (7.4).
- Competition dataset chosen and prepared, outside the repo (D5).
- Google Form set up (D3).

**Phase 3: nice to have**

- `.devcontainer/` for Codespaces.
- `tools/fetch_data.py` for Yahoo and Coinbase; two or three more
  datasets (say `SPY-1d`, `BTC-1d`).
- `run.py` command-line runner; per-fellow reports.

**Later: order book tie-in**

- The natural link is a visualizer that replays orders through the order book
  so fellows can see what a fill actually is. That needs the rewrite's
  matching engine first.
- Calling the C++ code from Python (pybind11) means fellows need a working
  C++ toolchain, which is painful on Windows. If it happens, ship prebuilt
  wheels (for example via `cibuildwheel` in CI) so fellows never compile.
  Alternatively, keep the C++ as the reference and write a small Python
  version for teaching.
- Separately: `orderbook/CMakeLists.txt` uses a Clang-only flag that GCC
  rejects. It is a two-line fix (only add it when the compiler is Clang).

---

## 10. Decisions for Bryan

Each has a default. I will proceed with the defaults unless you say
otherwise.

| # | Decision | Default |
|---|---|---|
| D1 | Fellows write a **function** (3.3) or keep the **class** | Function, with the class kept for examples |
| D2 | Single-asset only this track (3.4) | Yes, single-asset |
| D3 | Submission collection (7.3) | Google Form with file upload, UCLA accounts only |
| D4 | App's default fee (8.3) | 10 bps, matching the competition |
| D5 | Held-out data: same asset later period, or a different asset (4.4) | Same asset, later period |
| D6 | Install path (5.2); this also decides whether "Python 3.9+" stays | `uv`, with pip documented as a fallback; target Python 3.12 |
| D7 | When do fellows first need the repo? | Unknown. It sets how much of phase 1 comes first |

The one I most need an answer to is **D7**, since it decides what gets built
first.
