#include "matching_engine/orderbook.h"
#include "matching_engine/types.h"
#include <algorithm>


bool ME::orderbook::add_order(const ME::Order& order) {
    // If order ID already exists, reject the order and return false
    if (order_locations_.find(order.order_id) != order_locations_.end()) {
        return false;
    }
    // If order quantity is not positive, return false
    if (order.quantity <= 0) {
        return false;
    }

    // Check if the order is a bid or an ask and add it to the appropriate map
    if (order.side == ME::Side::BID) {
        // try_emplace inserts an empty level when this price is new and returns the existing one otherwise. 
        auto level = bids_.try_emplace(order.price).first;
        level->second.push_back(order);    // Add the order to the list at that price level
        // Store the location of the order in the order_locations_ map
        order_locations_[order.order_id] = {.side = ME::Side::BID,
                                            .price = order.price,
                                            .level = &level->second,
                                            .iterToOrder = std::prev(level->second.end())};
    }
    else if (order.side == ME::Side::ASK) {
        auto level = asks_.try_emplace(order.price).first;
        level->second.push_back(order);
        order_locations_[order.order_id] = {.side = ME::Side::ASK,
                                            .price = order.price,
                                            .level = &level->second,
                                            .iterToOrder = std::prev(level->second.end())};
    }
    return true;
}

bool ME::orderbook::cancel_order(const ME::ID order_id) {
    auto it = order_locations_.find(order_id);
    // If the order is not found, return false
    if (it == order_locations_.end()) {
        return false;
    }

    const ME::OrderLocation& loc = it->second;

    // Remove the order from its price level. O(1), and identical for both sides.
    loc.level->erase(loc.iterToOrder);

    // If that emptied the level, drop it. Only this rare path needs the map, and
    // only it costs O(log N).
    if (loc.level->empty()) {
        if (loc.side == ME::Side::BID) {
            bids_.erase(loc.price);
        }
        else {
            asks_.erase(loc.price);
        }
    }
    order_locations_.erase(it);
    return true;
}

std::optional<ME::Price> ME::orderbook::best_bid() const {
    if (bids_.empty()) {
        return std::nullopt;
    }
    return bids_.begin()->first;
}

std::optional<ME::Price> ME::orderbook::best_ask() const {
    if (asks_.empty()) {
        return std::nullopt;
    }
    return asks_.begin()->first;
}

std::optional<ME::Fill> ME::orderbook::reduce_best_order_quantity(ME::Side side, ME::Quantity amount, ME::ID taker_id) {
    // A non-positive reduction is a caller bug. Reject it before touching anything 
    // A negative amount would otherwise INFLATE the resting order
    if (amount <= 0) {
        return std::nullopt;
    }

    if (side == ME::Side::BID) {
        if (bids_.empty()) {
            return std::nullopt; // No best bid to reduce
        }
        auto level_it = bids_.begin();           // Best bid price level
        auto& best_level = level_it->second;
        auto& best_order = best_level.front();   // Oldest order at that price (FIFO)

        // Clamp to what is actually resting, and report back what we really took
        const ME::Quantity filled = std::min(amount, best_order.quantity);
        best_order.quantity -= filled;

        const ME::ID resting_order_id = best_order.order_id;
        const ME::Fill fill{.resting_order_id = resting_order_id,
                            .maker_id = best_order.maker_id,
                            .taker_id = taker_id,
                            .price = best_order.price,
                            .quantity = filled};

        // If order is empty:
        if (best_order.quantity == 0) {
            best_level.pop_front();
            order_locations_.erase(resting_order_id);  // Keep the two containers in sync
            // If price level is now empty:
            if (best_level.empty()) {
                bids_.erase(level_it);                 // Drop the now-empty price level
            }
        }
        return fill;
    }
    else if (side == ME::Side::ASK) {
        if (asks_.empty()) {
            return std::nullopt;
        }
        auto level_it = asks_.begin();
        auto& best_level = level_it->second;
        auto& best_order = best_level.front();

        const ME::Quantity filled = std::min(amount, best_order.quantity);
        best_order.quantity -= filled;
        
        const ME::ID resting_order_id = best_order.order_id;
        const ME::Fill fill{.resting_order_id = resting_order_id,
                            .maker_id = best_order.maker_id,
                            .taker_id = taker_id,
                            .price = best_order.price,
                            .quantity = filled};

        if (best_order.quantity == 0) {
            best_level.pop_front();
            order_locations_.erase(resting_order_id);
            if (best_level.empty()) {
                asks_.erase(level_it);
            }
        }
        return fill;
    }
    return std::nullopt;
}