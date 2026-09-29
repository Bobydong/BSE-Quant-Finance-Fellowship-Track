# CLAUDE.md — repo-wide context

## What this repo is

The single source of truth for the Bruin Software Engineers fellowship quant
track. It holds independent projects side by side, one per folder:

```
backtester/   Python teaching backtester (Streamlit) - what fellows use
orderbook/    C++20 limit order book - reference implementation
```

Each project has its own `CLAUDE.md` or docs. Read the one for the folder you
are working in before changing anything there:

- `backtester/CLAUDE.md` — invariants, regression numbers, and decisions that
  must not be broken or re-litigated. Treat it as binding.
- `orderbook/docs/_Overview.md` and `orderbook/docs/OrderbookDoc.md` — the
  intended design of the order book and matching engine.

## Rules for the whole repo

- **Keep projects self-contained.** Each folder builds and runs on its own
  from inside that folder. Do not add cross-folder imports or shared build
  files without asking; connecting the order book to the backtester is a
  planned future step, not something to start unprompted.
- **Do not delete order book code.** It is kept deliberately, as a reference
  and for future use.

## Branch flow

Work for the order book rewrite and the backtester lands on `rewrite` first,
then `rewrite` merges into `main`. Feature branches branch off `rewrite`.

## Order book: current state

- Namespace `ME`, headers in `orderbook/include/matching_engine/`.
- `ME::orderbook` is a pure data structure: it stores resting orders in
  price-time priority and hands out one reduction at a time via
  `reduce_best_order_quantity()`. It does not match or create trades.
- The matching engine that walks the book and produces trades is not written
  yet. Benchmarks are disabled in `orderbook/CMakeLists.txt` until they are
  recreated.
- `orderbook/README.md` still describes the earlier `v0.2` design (combined
  book + matcher, benchmarks). Trust the code and `orderbook/docs/` over it.
- `-Werror=reorder-init-list` in `orderbook/CMakeLists.txt` is Clang-only;
  GCC rejects it. Build with Clang.
