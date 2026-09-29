# Matching Engine

A limit order book and matching engine written in C++20. It accepts a stream of orders, maintains a sorted view of resting orders, matches incoming orders against resting ones using price-time priority, and emits trade events when matches occur. The engine is currently single-instrument, single-threaded, and purely in-memory. No networking, persistence, or I/O (although that may be added in later versions).

---

## Quick Start

```bash
git clone <repo-url>
cd matching-engine

cmake -B build
cmake --build build
ctest --test-dir build --output-on-failure
```

---

## Design Overview

### Price-time priority

When an order arrives, the engine matches it against the opposite side of the book according to two rules applied in order:

1. **Price priority** — match the most aggressive resting price first. An incoming buy is matched to the lowest ask. Conversely, an incoming sell is matched to the highest bid.
2. **Time priority** — among orders at the same price, match the one that arrived earliest (FIFO).

Matching continues until the incoming order is fully filled, its limit price is no longer competitive, or no opposite orders remain. Any unfilled remainder of a limit order rests in the book. Market orders never rest, and any unfilled quantity is discarded.

### Two-level data structure

The book is organized as two nested structures per side:

```
std::map<Price, std::list<Order>, Comparator>
         ^^^^^  ^^^^^^^^^^^^^^^^
         price  FIFO queue of all
         level  orders at that price
```

- **`std::map`** keeps price levels sorted at all times. `begin()` always returns the best price in O(1). Bids use `std::greater<Price>` (highest first); asks use `std::less<Price>` (lowest first).
- **`std::list<Order>`** at each level holds orders in arrival order. `push_back` adds new orders to the back; the matching loop consumes from the front. `std::list` is chosen because it supports O(1) removal at any position by iterator — which the cancel operation requires.

### Order-ID index for O(1) cancel

A separate hash map stores the location of every resting order:

```cpp
std::unordered_map<OrderId, OrderLocation>

struct OrderLocation {
    Side side;
    Price price;
    std::list<Order>::iterator iter;  // points directly into the FIFO
};
```

Given an order ID, the index gives a direct iterator into the list node. `std::list::erase(iterator)` is O(1), so cancel is O(1) regardless of book depth. Without this index, canceling by ID would require scanning every price level — O(n) — which is unacceptable given that market makers cancel and re-quote constantly.

### Matching algorithm sketch

```
add_order(incoming):
  while incoming.quantity > 0 and opposite side not empty:
    best_price = opposite_side.begin()->first      // O(1)
    if limit order and price doesn't cross: break

    for each resting order at best_price (front to back):
      traded = min(incoming.qty, resting.qty)
      emit Trade{maker=resting, taker=incoming, price=best_price, qty=traded}
      reduce both quantities
      if resting fully consumed: remove from list and index

    if price level now empty: erase from map    // keeps best_price honest

  if incoming has remainder and is a limit order: rest it in the book
  return trades
```

---

## Project Status

**Phase 0 — Complete ✓**

- Domain types (`Price`, `Quantity`, `OrderId`, `Timestamp`, `Side`, `OrderType`)
- `Order` and `Trade` plain aggregates
- `OrderBook` with full price-time priority matching, partial fills, market orders, and O(1) cancel
- `MatchingEngine` thin wrapper over `OrderBook`
- 34 unit tests covering: non-crossing inserts, single-fill matches, multi-level sweeps, partial fills both directions, market orders, time priority, cancel in all states
- Randomized cross-check: 5 × 5000 operations compared against a simple reference implementation, all seeds pass

**Phase 1 — Benchmark harness ✓**

- `OrderGenerator`: reproducible mixed workload (60% limit adds, 35% cancels, 5% market orders)
- Google Benchmark steady-state throughput harness (`me_bench`)
- Latency distribution harness recording 1M individual `add_order` timings (`me_latency`)
- Analysis script computing p50/p99/p99.9 from raw nanosecond data (`analyze.py`)
- Baseline results captured (see below)

**Phase 2 — Optimization** *(planned)*

---

## Benchmark Results — Baseline (Phase 1)

**Hardware:** Intel Core i5-8210Y @ 1.60 GHz (MacBook Air, dual-core)  
**Compiler:** Apple Clang 16.0.0  
**Build:** `-O3 -DNDEBUG` (CMake Release)  
**Methodology:** Steady-state book pre-populated with ~5,000 resting orders; mixed workload (60% limit adds, 35% cancels, 5% market orders). Google Benchmark run 3×, median taken (run 3 discarded as outlier). Latency harness records 10,000-op warmup then 1,000,000 timed `add_order` calls individually.

### Throughput (`add_order`, Google Benchmark)

| Run | Wall time | CPU time | Throughput |
|-----|-----------|----------|------------|
| 1   | 540 ns    | 514 ns   | 1.94 M/s   |
| 2 *(median)* | 660 ns | 548 ns | 1.83 M/s |
| 3 *(outlier)* | 2211 ns | 843 ns | 1.19 M/s |

**Baseline: ~1.83M orders/sec (548 ns CPU time per op)**

### Latency Distribution (`add_order`, 1M samples)

| Percentile | Latency |
|---|---|
| p50   | 300 ns  |
| p99   | 1,344 ns |
| p99.9 | 3,364 ns |

---

## Key Design Decisions

**Integer prices, not floats.**
Floating-point arithmetic introduces rounding errors that make exact equality comparisons unreliable. Real exchanges represent prices as integer tick counts (`$100.01` → `10001`). We follow that convention throughout. `Price` is `int64_t`.

**`std::map` for price levels.**
`std::map` keeps prices sorted, so the best bid/ask is always `begin()->first` in O(1). The alternative, `std::unordered_map`, has faster key lookup but no ordering — finding the best price would require a full scan. For an order book, best-price access dominates, so the sorted structure wins. The cost is O(log n) insertion; with at most a few hundred active price levels in practice, this is negligible. Phase 2 will replace this with a flat sorted structure for better cache behavior.

**`std::list` for the per-level FIFO queue.**
Cancel-by-ID requires O(1) removal at an arbitrary position. `std::list` is the only standard container where `erase(iterator)` is O(1) and iterators remain valid through other insertions and removals. `std::vector` and `std::deque` both invalidate iterators on modification. The cost is a heap allocation per order node — acceptable in Phase 0, optimization target in Phase 2 (intrusive lists with pooled allocation).

**Separate reference matcher for testing.**
`ReferenceMatcher` is a deliberately simple second implementation of the same matching logic — `std::vector` per side, linear scans, sort before each match. It shares no code with `OrderBook`. The randomized test suite feeds identical order streams to both and asserts they agree on every trade and every best-price query. This catches bugs that hand-written unit tests miss — phantom price levels, stale index entries, wrong FIFO ordering — because the two implementations are independently correct rather than independently wrong in the same way.

**Known limitations (Phase 0 scope).**
Self-trades are allowed — the engine has no concept of participant IDs. Zero-quantity orders are silently ignored. These are documented limitations, not bugs, and are standard simplifications for a Phase 0 implementation.
