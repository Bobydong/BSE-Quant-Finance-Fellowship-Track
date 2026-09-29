#pragma once
#include <cstdint>
#include <list>
#include <string>

// This files defines the types used by the matching engine and orderbook.

namespace ME{
    enum class Side { BID, ASK };
    enum class OrderType { LIMIT, MARKET };
    enum class OrderStatus { ACCEPTED, REJECTED };

    typedef std::int64_t Price; // Prices use int64_t to avoid floating point precision issues.
    typedef std::int64_t ID;        
    typedef std::int64_t Quantity;
    typedef std::int64_t Timestamp;
  
    struct Order{
        ID order_id;
        ID maker_id;
        std::string symbol;
        Side side;
        OrderType type;
        Price price;
        Quantity quantity;
        // Order doesn't need a timestamp variable because the orderbook maintains the time priority of orders 
        // in a price level by always appending to the end of the list, creating a FIFO.
    };

    // Where a resting order lives, so cancel_order can cancel in O(1) instead of O(logN).
    //
    // The level is stored as a pointer rather than an iterator because bids_ and asks_ are different map types 
    // (they use different comparators), so there is no one iterator type valid for both sides. 
    struct OrderLocation{
        Side side;
        Price price;                             // needed to erase the level once it empties
        std::list<Order>* level;                 // the price level this order rests in
        std::list<Order>::iterator iterToOrder;  // this order's node within that level
    };

    // Fill is what the orderbook reports back after reducing a resting order.
    // The matching engine turns this into a Trade by adding a timestamp.
    struct Fill{
        ID resting_order_id; // ID of the resting order reduced
        ID maker_id;         // ID of who owned the reduced order -- becomes Trade::maker_id
        ID taker_id;         // ID of who sent the request to reduce the order
        Price price;         // the resting order's price
        Quantity quantity;   // amount actually reduced, which may be < originally requested amount
    };

    struct Trade{
        ID maker_id;
        ID taker_id;
        Price price;
        Quantity quantity;
        Timestamp timestamp;
    };

    
}
