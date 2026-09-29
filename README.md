# BSE Quant Finance Fellowship Track

Code for the Bruin Software Engineers fellowship quant track. Each project
lives in its own folder with its own README; start with the one you need.

| Folder | What it is | Language |
|---|---|---|
| [`backtester/`](backtester/) | The teaching backtester fellows use to write and evaluate trading strategies | Python |
| [`orderbook/`](orderbook/) | A limit order book (and, in progress, a matching engine) | C++20 |

---

## Backtester (fellows start here)

Write a strategy in a few lines of Python and get a full performance report
in your browser.

```bash
cd backtester
pip install -r requirements.txt
streamlit run app.py
```

Then open http://localhost:8501. See [`backtester/README.md`](backtester/README.md)
for how to write a strategy and read the results.

## Order book

A single-symbol limit order book that keeps resting orders in price-time
priority. It is a pure data structure; matching is the job of a separate
matching engine that is still being written. See
[`orderbook/docs/`](orderbook/docs/) for the design.

```bash
cd orderbook
cmake -B build
cmake --build build
ctest --test-dir build --output-on-failure
```

The build currently uses a Clang-only warning flag, so build with Clang
(the default on macOS).

The earlier combined order book + matching engine, with its benchmarks, is
preserved at tags `v0.1` and `v0.2`.

---

## Why both live here

This repo is meant to be the single source of truth for the track. The order
book is kept as a reference implementation, and may later be used from the
backtester or other tools to simulate and visualize how orders actually
match.
