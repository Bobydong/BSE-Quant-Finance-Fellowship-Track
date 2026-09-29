# Orderbook.h + Orderbook.cpp Explanation

## Definition Overview
```

```

```
    typedef std::int64_t Price; // Prices use int64_t to avoid floating point precision issues.
    typedef std::int64_t ID;
    typedef std::int64_t Quantity;
    typedef std::int64_t Timestamp;
  
    struct OrderLocation{
        Side side;
        Price price;
        std::list<Order>::iterator iterator; 
    };

    struct Trade{
        ID maker_id;
        ID taker_id;
        Price price;
        Quantity quantity; 
        Timestamp timestamp;
    };```

bids_ and asks_
    STL BST Map of price level to an STL List of all orders in that price level.
        The list is used to maintain the FIFO consumption of orders in that price level.
    BST implementation of map is used soley for O(1) fetch of best price for bids and asks, and easy sweeping/walking of the book.
    However, the tradeoff is that insertion and deletion of price levels is O(log(N)) instead of O(1) for a hash map.
        Adding a new order is O(log(N)) to search for the price level, and the O(1) to insert to the end of the list.

order_locations_    
    To mitigate the O(log(N)) cancellation/deletion of BST Map, we maintain a separate STL Hash Map of order id to a struct containing the side, 
        price, and iterator to the order in the list of orders at that price level.
    This allows for essentially O(1) deletion/cancellation of an order by id, as we can directly access the order's memory 
        location in the list and remove it without having to search for it.

OrderLocation struct
    This struct is used to store the side, price, and an iterator to memory location of the order of an OrderId.
    The Side and Price is required to cancel for cleanup after canceling orders:
        The iterator removes the order from the list, but if the list is empty, the price level needs to be remmoved from the map.
        Without knowing which side the order lives on, we would have to search both maps to find the price level to remove, 
            which is O(log(N)) instead of O(1).  
        Knowing which side the order lives on lets us directly check that price level for emptiness and remove it if necessary, which is O(1).


std::vector<Trade> add_order(const Order& order)
    This function adds an order to the orderbook in O(log(N)).
    When adding an order, the book may match it and execute a trade.
        The function returns a vector of trades that were executed as a result of adding the order.        
    Note, the matching engine class doesn't perform the matching of orders, the orderbook maintains itself.

        
bool cancel_order(const OrderId& id)
    This function cancels an order in O(1) if other orders exist at the same price level, O(log(N))) if it was the last in its price level.
    The function returns true if the order was found and canceled, false if the order was not found.
    When canceling an order, the matching engine may remove a price level from the orderbook.
        This is handled behind the scenes.
    
        
best_bid() and best_ask()
    This function returns the best price for bids and asks in O(1).
    If there are no bids or asks, the function returns std::nullopt due to the use of std::optional.

std::size_t numberOfOrders() const { return order_locations_.size(); }
    This function returns the number of orders in the orderbook in O(1).
    It is primarily used to verify that the orderbook state is correct during testing and benchmarking.
