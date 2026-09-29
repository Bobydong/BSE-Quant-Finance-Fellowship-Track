# System Design for V1 
## Notes
- Single-threaded for now
- No networking for now


## Flow of Operations
### Order Placement and Matching
1. User creates an order
2. User sends order to exchange
3. Exchange performs some initial checks of the order
4. Exchange gives order to the matching engine
5. Matching engine matches the order if possible and walks the book
   - If limit order, the matching engine rests it in the book
   - If market order, the matching enigne discards unused quantity


## Data Structure Design
### Order
An order needs to have:
- Order-specific ID
- Who made the order (user ID)
- Price 
- What symbol the order is buying/selling
- Which side it is (Bid/Ask)
- The type of order it is (Market/Limit)
- The quantity of the order

### The Orderbook
The order book should soley be a data structure to hold all the bids + asks for a single symbol.   
- It should keep the data organized in price-time priority, but should not perform any trades. 
- It should only expose methods to:
  - Fetch the best bed/ask price
  - Fetch total current number of bids + asks for that symbol
  - Add orders to the book after matching engine is finished processing
  - Cancel orders  


More info in OrderbookDoc


### The Matching Engine
- Maintains a hashmap of OrderBooks.
- When receiving an order:
  1. Find correct OrderBook for that symbol
  2. Check if there's a collision with the best ask/bid price to the current order
  3. If there is a collision:
     1. Decrement the order quantity and the resting order quantity 
        1. If resting order isn't completely consumed, return successful trades
        2. If resting order is completely consumed, return successful trades and delete the empty order from the price level
           1. If the price level is empty, delete the price level
     2. repeat until current order is used up
  4. Return list of trades and success status