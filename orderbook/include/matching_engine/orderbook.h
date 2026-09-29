#pragma once
#include <map>
#include <list>
#include <unordered_map>
#include <optional>
#include "types.h"
#include <functional>
#include <cstddef>

namespace ME {
    // A pure data structure. 
    // The orderbook stores resting orders and maintains price-time priority.
    // It does not match and does not generate trades.
    //
    // The matching engine owns matching and trade generation: 
    // it receives an order, walks the book, generates Trades, and rests the remaining quantity if a limit order. 
    //
    // The book validates only what protects its own invariants.
    // Everything else (price bands, tick size, self-trade prevention, order types) is the matchine engine's responsibility.

    class orderbook {
        private:
            std::map<Price, std::list<Order>, std::greater<Price>> bids_;  
            std::map<Price, std::list<Order>> asks_;
            std::unordered_map<ID, OrderLocation> order_locations_;

        public:
            // Rests an order. 
            // Returns false if the order's ID already exists in orderbook or its quantity <= 0, and book is left untouched.
            //
            // The orderbook checks the order's quantity rather than the matching engine because a negative resting quantity 
            // corrupts this class: it would make reduce_best_order_quantity() emit a zero or negative Fill.
            //
            // Price is deliberately NOT validated. Any int64 price keeps the book's invariants intact, and negative prices 
            // are legal in real markets (commodities, spreads), so what counts as a sane price is the engine's responsibility.
            bool add_order(const Order& order);

            // Removes a resting order. Returns false if the id doesn't exist.
            bool cancel_order(const ID order_id);

            // Returns the best bid/ask price, or std::nullopt if that side is empty.
            std::optional<Price> best_bid() const;
            std::optional<Price> best_ask() const;
            // Returns the number of resting orders in the book.
            std::size_t number_of_orders() const { return order_locations_.size(); }


            // Reduces the best order's quantity on the given side by "amount", returning Fill with the amount reduced. 
            // Returns std::nullopt if that side is empty or amount <= 0, and book is left completely untouched.
            // 
            // If the order reaches quantity 0 after reduction, it is removed from the book.
            // If "amount" isn't fully consumed after reduction, Fill tells the engine who much was consumed.
            // A single call never spans two resting orders; walking the rest of the level is the engine's job.
            //
            // The engine adds a timestamp to turn the returned Fill into a Trade.
            std::optional<Fill> reduce_best_order_quantity(Side side, Quantity amount, ID taker_id);

    };
}
