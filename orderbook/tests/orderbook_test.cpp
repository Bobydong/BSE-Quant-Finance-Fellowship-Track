// Tests for ME::orderbook.
//
// The book is a pure data structure: it stores resting orders, maintains
// price/time priority, and hands the matching engine one reduction at a time.
// These tests exercise it strictly through its public API, which means the
// only observable state is best_bid(), best_ask(), number_of_orders(), and the
// sequence of Fills that comes back from draining the book. Every priority
// claim below is therefore verified by draining and checking fill order.

#include <gtest/gtest.h>

#include "matching_engine/orderbook.h"
#include "matching_engine/types.h"

#include <algorithm>
#include <cstddef>
#include <optional>
#include <random>
#include <string>
#include <vector>

using ME::Fill;
using ME::ID;
using ME::Order;
using ME::orderbook;
using ME::OrderType;
using ME::Price;
using ME::Quantity;
using ME::Side;

namespace {

// maker_id is deliberately *not* equal to order_id so that a Fill reporting
// one where the other belongs cannot pass by accident.
constexpr ID kMakerOffset = 1000;

// Distinct from every maker id used below, so a Fill that swaps taker and
// resting cannot pass either.
constexpr ID kTaker = 9999;

Order make_order(ID order_id, Side side, Price price, Quantity quantity) {
    return Order{order_id,
                 order_id + kMakerOffset,
                 "AAPL",
                 side,
                 OrderType::LIMIT,
                 price,
                 quantity};
}

ID maker_of(ID order_id) { return order_id + kMakerOffset; }

// A large reduction request: bigger than any quantity used in these tests, so
// "take everything at the front of the book" reads as one call.
constexpr Quantity kAll = 1'000'000;

// Checks all five Fill members. The expected maker is derived from the resting
// order id via make_order's convention, so a Fill that reports the maker where
// the order id belongs (or vice versa) fails here -- the two never coincide.
::testing::AssertionResult FillIs(const std::optional<Fill>& fill,
                                  ID expected_resting_order_id,
                                  ID expected_taker_id,
                                  Price expected_price,
                                  Quantity expected_quantity) {
    if (!fill.has_value()) {
        return ::testing::AssertionFailure() << "expected a Fill, got std::nullopt";
    }
    const ID expected_maker_id = expected_resting_order_id + kMakerOffset;
    if (fill->resting_order_id != expected_resting_order_id ||
        fill->maker_id != expected_maker_id || fill->taker_id != expected_taker_id ||
        fill->price != expected_price || fill->quantity != expected_quantity) {
        return ::testing::AssertionFailure()
               << "Fill{resting_order_id=" << fill->resting_order_id
               << ", maker_id=" << fill->maker_id << ", taker_id=" << fill->taker_id
               << ", price=" << fill->price << ", quantity=" << fill->quantity
               << "} != Fill{resting_order_id=" << expected_resting_order_id
               << ", maker_id=" << expected_maker_id << ", taker_id=" << expected_taker_id
               << ", price=" << expected_price << ", quantity=" << expected_quantity << "}";
    }
    return ::testing::AssertionSuccess();
}

// Repeatedly takes the whole front order until the side is empty.
std::vector<Fill> drain_side(orderbook& book, Side side) {
    std::vector<Fill> fills;
    while (auto fill = book.reduce_best_order_quantity(side, kAll, kTaker)) {
        fills.push_back(*fill);
        // Guard against an implementation that returns fills forever.
        if (fills.size() > 10'000u) {
            ADD_FAILURE() << "drain_side did not terminate";
            break;
        }
    }
    return fills;
}

std::vector<ID> resting_ids_of(const std::vector<Fill>& fills) {
    std::vector<ID> ids;
    ids.reserve(fills.size());
    for (const Fill& fill : fills) ids.push_back(fill.resting_order_id);
    return ids;
}

}  // namespace

// ---------------------------------------------------------------------------
// Empty book
// ---------------------------------------------------------------------------

TEST(OrderbookEmpty, HasNoOrdersAndNoBestPrices) {
    orderbook book;
    EXPECT_EQ(book.number_of_orders(), 0u);
    EXPECT_FALSE(book.best_bid().has_value());
    EXPECT_FALSE(book.best_ask().has_value());
}

TEST(OrderbookEmpty, ReduceReturnsNulloptOnBothSides) {
    orderbook book;
    EXPECT_FALSE(book.reduce_best_order_quantity(Side::BID, 10, kTaker).has_value());
    EXPECT_FALSE(book.reduce_best_order_quantity(Side::ASK, 10, kTaker).has_value());
    EXPECT_EQ(book.number_of_orders(), 0u);
}

TEST(OrderbookEmpty, CancelUnknownIdReturnsFalse) {
    orderbook book;
    EXPECT_FALSE(book.cancel_order(1));
}

// ---------------------------------------------------------------------------
// add_order
// ---------------------------------------------------------------------------

TEST(OrderbookAdd, RestingABidUpdatesBestBidOnly) {
    orderbook book;
    EXPECT_TRUE(book.add_order(make_order(1, Side::BID, 100, 5)));

    EXPECT_EQ(book.number_of_orders(), 1u);
    ASSERT_TRUE(book.best_bid().has_value());
    EXPECT_EQ(*book.best_bid(), 100);
    EXPECT_FALSE(book.best_ask().has_value());
}

TEST(OrderbookAdd, RestingAnAskUpdatesBestAskOnly) {
    orderbook book;
    EXPECT_TRUE(book.add_order(make_order(1, Side::ASK, 101, 5)));

    EXPECT_EQ(book.number_of_orders(), 1u);
    ASSERT_TRUE(book.best_ask().has_value());
    EXPECT_EQ(*book.best_ask(), 101);
    EXPECT_FALSE(book.best_bid().has_value());
}

TEST(OrderbookAdd, BestBidIsTheHighestPriceRegardlessOfInsertionOrder) {
    orderbook book;
    ASSERT_TRUE(book.add_order(make_order(1, Side::BID, 100, 5)));
    ASSERT_TRUE(book.add_order(make_order(2, Side::BID, 102, 5)));
    ASSERT_TRUE(book.add_order(make_order(3, Side::BID, 101, 5)));

    ASSERT_TRUE(book.best_bid().has_value());
    EXPECT_EQ(*book.best_bid(), 102);
    EXPECT_EQ(book.number_of_orders(), 3u);
}

TEST(OrderbookAdd, BestAskIsTheLowestPriceRegardlessOfInsertionOrder) {
    orderbook book;
    ASSERT_TRUE(book.add_order(make_order(1, Side::ASK, 105, 5)));
    ASSERT_TRUE(book.add_order(make_order(2, Side::ASK, 103, 5)));
    ASSERT_TRUE(book.add_order(make_order(3, Side::ASK, 104, 5)));

    ASSERT_TRUE(book.best_ask().has_value());
    EXPECT_EQ(*book.best_ask(), 103);
    EXPECT_EQ(book.number_of_orders(), 3u);
}

TEST(OrderbookAdd, MultipleOrdersShareAPriceLevel) {
    orderbook book;
    ASSERT_TRUE(book.add_order(make_order(1, Side::BID, 100, 5)));
    ASSERT_TRUE(book.add_order(make_order(2, Side::BID, 100, 7)));
    ASSERT_TRUE(book.add_order(make_order(3, Side::BID, 100, 9)));

    EXPECT_EQ(book.number_of_orders(), 3u);
    ASSERT_TRUE(book.best_bid().has_value());
    EXPECT_EQ(*book.best_bid(), 100);
}

TEST(OrderbookAdd, DuplicateIdIsRejectedAndLeavesTheBookUntouched) {
    orderbook book;
    ASSERT_TRUE(book.add_order(make_order(1, Side::BID, 100, 5)));

    // Same id, better price, different quantity: if it slipped in, best_bid
    // would move to 110 and the fill sequence would change.
    EXPECT_FALSE(book.add_order(make_order(1, Side::BID, 110, 50)));

    EXPECT_EQ(book.number_of_orders(), 1u);
    ASSERT_TRUE(book.best_bid().has_value());
    EXPECT_EQ(*book.best_bid(), 100);

    const std::vector<Fill> fills = drain_side(book, Side::BID);
    ASSERT_EQ(fills.size(), 1u);
    EXPECT_TRUE(FillIs(fills[0], 1, kTaker, 100, 5));
}

TEST(OrderbookAdd, DuplicateIdIsRejectedAcrossSides) {
    orderbook book;
    ASSERT_TRUE(book.add_order(make_order(1, Side::BID, 100, 5)));

    EXPECT_FALSE(book.add_order(make_order(1, Side::ASK, 101, 5)));

    EXPECT_EQ(book.number_of_orders(), 1u);
    EXPECT_FALSE(book.best_ask().has_value());
}

// --- quantity validation ---

TEST(OrderbookAdd, ZeroQuantityIsRejected) {
    orderbook book;
    EXPECT_FALSE(book.add_order(make_order(1, Side::BID, 100, 0)));

    EXPECT_EQ(book.number_of_orders(), 0u);
    EXPECT_FALSE(book.best_bid().has_value());
}

TEST(OrderbookAdd, NegativeQuantityIsRejected) {
    orderbook book;
    EXPECT_FALSE(book.add_order(make_order(1, Side::ASK, 100, -5)));

    EXPECT_EQ(book.number_of_orders(), 0u);
    EXPECT_FALSE(book.best_ask().has_value());
}

TEST(OrderbookAdd, ARejectedQuantityDoesNotLeaveAPhantomPriceLevel) {
    orderbook book;
    ASSERT_TRUE(book.add_order(make_order(1, Side::BID, 100, 5)));

    // 200 would be the new best bid. If the quantity check ran *after*
    // bids_[order.price], operator[] would have default-constructed an empty
    // list at 200 and best_bid() would now report a level with nothing in it.
    EXPECT_FALSE(book.add_order(make_order(2, Side::BID, 200, 0)));

    ASSERT_TRUE(book.best_bid().has_value());
    EXPECT_EQ(*book.best_bid(), 100);
    EXPECT_EQ(book.number_of_orders(), 1u);

    // And the phantom level must not surface as a fill either.
    const std::vector<Fill> fills = drain_side(book, Side::BID);
    ASSERT_EQ(fills.size(), 1u);
    EXPECT_TRUE(FillIs(fills[0], 1, kTaker, 100, 5));
}

TEST(OrderbookAdd, AnIdIsStillFreeAfterAQuantityRejection) {
    orderbook book;
    ASSERT_FALSE(book.add_order(make_order(1, Side::BID, 100, 0)));

    // The rejection must not have recorded a location entry under that id.
    EXPECT_TRUE(book.add_order(make_order(1, Side::BID, 100, 5)));
    EXPECT_EQ(book.number_of_orders(), 1u);
}

// ---------------------------------------------------------------------------
// cancel_order
// ---------------------------------------------------------------------------

TEST(OrderbookCancel, CancellingTheOnlyOrderEmptiesTheBook) {
    orderbook book;
    ASSERT_TRUE(book.add_order(make_order(1, Side::BID, 100, 5)));

    EXPECT_TRUE(book.cancel_order(1));

    EXPECT_EQ(book.number_of_orders(), 0u);
    EXPECT_FALSE(book.best_bid().has_value());
}

TEST(OrderbookCancel, CancellingTwiceReturnsFalseTheSecondTime) {
    orderbook book;
    ASSERT_TRUE(book.add_order(make_order(1, Side::ASK, 100, 5)));

    EXPECT_TRUE(book.cancel_order(1));
    EXPECT_FALSE(book.cancel_order(1));
    EXPECT_EQ(book.number_of_orders(), 0u);
}

TEST(OrderbookCancel, CancellingTheLastOrderAtALevelAdvancesTheBestPrice) {
    orderbook book;
    ASSERT_TRUE(book.add_order(make_order(1, Side::BID, 102, 5)));
    ASSERT_TRUE(book.add_order(make_order(2, Side::BID, 101, 5)));

    ASSERT_TRUE(book.cancel_order(1));

    ASSERT_TRUE(book.best_bid().has_value());
    EXPECT_EQ(*book.best_bid(), 101);
    EXPECT_EQ(book.number_of_orders(), 1u);
}

TEST(OrderbookCancel, CancellingOneOfManyAtALevelKeepsTheLevel) {
    orderbook book;
    ASSERT_TRUE(book.add_order(make_order(1, Side::ASK, 100, 5)));
    ASSERT_TRUE(book.add_order(make_order(2, Side::ASK, 100, 5)));

    ASSERT_TRUE(book.cancel_order(1));

    ASSERT_TRUE(book.best_ask().has_value());
    EXPECT_EQ(*book.best_ask(), 100);
    EXPECT_EQ(book.number_of_orders(), 1u);
}

TEST(OrderbookCancel, CancellingAwayFromTheTopDoesNotMoveTheBestPrice) {
    orderbook book;
    ASSERT_TRUE(book.add_order(make_order(1, Side::BID, 102, 5)));
    ASSERT_TRUE(book.add_order(make_order(2, Side::BID, 100, 5)));

    ASSERT_TRUE(book.cancel_order(2));

    ASSERT_TRUE(book.best_bid().has_value());
    EXPECT_EQ(*book.best_bid(), 102);
    EXPECT_EQ(book.number_of_orders(), 1u);
}

TEST(OrderbookCancel, CancellingFromTheMiddleOfALevelPreservesFifoForTheRest) {
    orderbook book;
    for (ID id = 1; id <= 4; ++id) {
        ASSERT_TRUE(book.add_order(make_order(id, Side::BID, 100, 5)));
    }

    ASSERT_TRUE(book.cancel_order(2));

    const std::vector<Fill> fills = drain_side(book, Side::BID);
    EXPECT_EQ(resting_ids_of(fills),
              (std::vector<ID>{1, 3, 4}));
}

TEST(OrderbookCancel, CancellingOneSideLeavesTheOtherAlone) {
    orderbook book;
    ASSERT_TRUE(book.add_order(make_order(1, Side::BID, 100, 5)));
    ASSERT_TRUE(book.add_order(make_order(2, Side::ASK, 101, 5)));

    ASSERT_TRUE(book.cancel_order(1));

    EXPECT_FALSE(book.best_bid().has_value());
    ASSERT_TRUE(book.best_ask().has_value());
    EXPECT_EQ(*book.best_ask(), 101);
    EXPECT_EQ(book.number_of_orders(), 1u);
}

TEST(OrderbookCancel, AnIdIsReusableOnceItsOrderIsCancelled) {
    orderbook book;
    ASSERT_TRUE(book.add_order(make_order(1, Side::BID, 100, 5)));
    ASSERT_TRUE(book.cancel_order(1));

    // The id must be free again: cancel_order has to drop the location entry,
    // not just unlink the list node.
    EXPECT_TRUE(book.add_order(make_order(1, Side::BID, 99, 8)));

    ASSERT_TRUE(book.best_bid().has_value());
    EXPECT_EQ(*book.best_bid(), 99);
    EXPECT_EQ(book.number_of_orders(), 1u);
}

// ---------------------------------------------------------------------------
// reduce_best_order_quantity — argument handling
// ---------------------------------------------------------------------------

TEST(OrderbookReduce, NonPositiveAmountIsRejectedAndLeavesTheBookUntouched) {
    orderbook book;
    ASSERT_TRUE(book.add_order(make_order(1, Side::BID, 100, 5)));

    EXPECT_FALSE(book.reduce_best_order_quantity(Side::BID, 0, kTaker).has_value());
    EXPECT_FALSE(book.reduce_best_order_quantity(Side::BID, -7, kTaker).has_value());

    EXPECT_EQ(book.number_of_orders(), 1u);
    ASSERT_TRUE(book.best_bid().has_value());
    EXPECT_EQ(*book.best_bid(), 100);

    // A negative amount must not have inflated the resting quantity.
    const std::vector<Fill> fills = drain_side(book, Side::BID);
    ASSERT_EQ(fills.size(), 1u);
    EXPECT_TRUE(FillIs(fills[0], 1, kTaker, 100, 5));
}

TEST(OrderbookReduce, ReducingAnEmptySideLeavesTheOtherSideUntouched) {
    orderbook book;
    ASSERT_TRUE(book.add_order(make_order(1, Side::ASK, 101, 5)));

    EXPECT_FALSE(book.reduce_best_order_quantity(Side::BID, 5, kTaker).has_value());

    EXPECT_EQ(book.number_of_orders(), 1u);
    ASSERT_TRUE(book.best_ask().has_value());
    EXPECT_EQ(*book.best_ask(), 101);
}

// ---------------------------------------------------------------------------
// reduce_best_order_quantity — fill semantics
// ---------------------------------------------------------------------------

TEST(OrderbookReduce, PartialFillLeavesTheOrderResting) {
    orderbook book;
    ASSERT_TRUE(book.add_order(make_order(1, Side::BID, 100, 10)));

    EXPECT_TRUE(FillIs(book.reduce_best_order_quantity(Side::BID, 4, kTaker),
                       1, kTaker, 100, 4));

    EXPECT_EQ(book.number_of_orders(), 1u);
    ASSERT_TRUE(book.best_bid().has_value());
    EXPECT_EQ(*book.best_bid(), 100);

    // The remainder — exactly 6 — is still there.
    EXPECT_TRUE(FillIs(book.reduce_best_order_quantity(Side::BID, kAll, kTaker),
                       1, kTaker, 100, 6));
    EXPECT_EQ(book.number_of_orders(), 0u);
}

TEST(OrderbookReduce, ExactFillRemovesTheOrderAndItsLevel) {
    orderbook book;
    ASSERT_TRUE(book.add_order(make_order(1, Side::ASK, 101, 5)));

    EXPECT_TRUE(FillIs(book.reduce_best_order_quantity(Side::ASK, 5, kTaker),
                       1, kTaker, 101, 5));

    EXPECT_EQ(book.number_of_orders(), 0u);
    EXPECT_FALSE(book.best_ask().has_value());
    EXPECT_FALSE(book.reduce_best_order_quantity(Side::ASK, 5, kTaker).has_value());
}

TEST(OrderbookReduce, OverAskingIsClampedToWhatIsResting) {
    orderbook book;
    ASSERT_TRUE(book.add_order(make_order(1, Side::BID, 100, 3)));

    // The engine may ask for the full incoming quantity; the book reports back
    // only what it actually had.
    EXPECT_TRUE(FillIs(book.reduce_best_order_quantity(Side::BID, 100, kTaker),
                       1, kTaker, 100, 3));
    EXPECT_EQ(book.number_of_orders(), 0u);
}

TEST(OrderbookReduce, FillFieldsAreNotTransposed) {
    orderbook book;
    // Every field gets a distinct, recognizable value, so a Fill whose members
    // are populated in the wrong order cannot look correct.
    ASSERT_TRUE(book.add_order(make_order(7, Side::ASK, 101, 5)));
    ASSERT_TRUE(book.add_order(make_order(8, Side::ASK, 103, 5)));

    const std::optional<Fill> fill = book.reduce_best_order_quantity(Side::ASK, 2, kTaker);
    ASSERT_TRUE(fill.has_value());
    EXPECT_EQ(fill->resting_order_id, 7);       // the order, not its owner
    EXPECT_EQ(fill->maker_id, maker_of(7));     // the owner, not the order
    EXPECT_EQ(fill->taker_id, kTaker);          // the taker passed in by the caller
    EXPECT_EQ(fill->price, 101);                // the maker's price, not the taker's
    EXPECT_EQ(fill->quantity, 2);               // what was actually taken
}

TEST(OrderbookReduce, EachFillCarriesItsOwnTakerId) {
    orderbook book;
    ASSERT_TRUE(book.add_order(make_order(1, Side::BID, 100, 10)));

    EXPECT_TRUE(FillIs(book.reduce_best_order_quantity(Side::BID, 3, 4242),
                       1, 4242, 100, 3));
    EXPECT_TRUE(FillIs(book.reduce_best_order_quantity(Side::BID, 3, 7373),
                       1, 7373, 100, 3));
}

TEST(OrderbookReduce, ReducingOneSideDoesNotDisturbTheOther) {
    orderbook book;
    ASSERT_TRUE(book.add_order(make_order(1, Side::BID, 100, 5)));
    ASSERT_TRUE(book.add_order(make_order(2, Side::ASK, 101, 5)));

    ASSERT_TRUE(book.reduce_best_order_quantity(Side::BID, kAll, kTaker).has_value());

    EXPECT_FALSE(book.best_bid().has_value());
    ASSERT_TRUE(book.best_ask().has_value());
    EXPECT_EQ(*book.best_ask(), 101);
    EXPECT_EQ(book.number_of_orders(), 1u);
}

// ---------------------------------------------------------------------------
// reduce_best_order_quantity — priority
// ---------------------------------------------------------------------------

TEST(OrderbookPriority, OrdersAtOnePriceFillInArrivalOrder) {
    orderbook book;
    for (ID id = 1; id <= 3; ++id) {
        ASSERT_TRUE(book.add_order(make_order(id, Side::BID, 100, 5)));
    }

    const std::vector<Fill> fills = drain_side(book, Side::BID);
    EXPECT_EQ(resting_ids_of(fills),
              (std::vector<ID>{1, 2, 3}));
}

TEST(OrderbookPriority, BidsFillFromHighestPriceDown) {
    orderbook book;
    // Inserted out of price order on purpose.
    ASSERT_TRUE(book.add_order(make_order(1, Side::BID, 100, 5)));
    ASSERT_TRUE(book.add_order(make_order(2, Side::BID, 102, 5)));
    ASSERT_TRUE(book.add_order(make_order(3, Side::BID, 101, 5)));

    const std::vector<Fill> fills = drain_side(book, Side::BID);
    ASSERT_EQ(fills.size(), 3u);
    EXPECT_EQ(fills[0].price, 102);
    EXPECT_EQ(fills[1].price, 101);
    EXPECT_EQ(fills[2].price, 100);
}

TEST(OrderbookPriority, AsksFillFromLowestPriceUp) {
    orderbook book;
    ASSERT_TRUE(book.add_order(make_order(1, Side::ASK, 105, 5)));
    ASSERT_TRUE(book.add_order(make_order(2, Side::ASK, 103, 5)));
    ASSERT_TRUE(book.add_order(make_order(3, Side::ASK, 104, 5)));

    const std::vector<Fill> fills = drain_side(book, Side::ASK);
    ASSERT_EQ(fills.size(), 3u);
    EXPECT_EQ(fills[0].price, 103);
    EXPECT_EQ(fills[1].price, 104);
    EXPECT_EQ(fills[2].price, 105);
}

TEST(OrderbookPriority, PriceBeatsTimeAndTimeBreaksTies) {
    orderbook book;
    // Arrival order 1..5, prices deliberately interleaved.
    ASSERT_TRUE(book.add_order(make_order(1, Side::BID, 100, 5)));  // 3rd level
    ASSERT_TRUE(book.add_order(make_order(2, Side::BID, 102, 5)));  // top, first
    ASSERT_TRUE(book.add_order(make_order(3, Side::BID, 101, 5)));  // 2nd level, first
    ASSERT_TRUE(book.add_order(make_order(4, Side::BID, 102, 5)));  // top, second
    ASSERT_TRUE(book.add_order(make_order(5, Side::BID, 101, 5)));  // 2nd level, second

    const std::vector<Fill> fills = drain_side(book, Side::BID);
    EXPECT_EQ(resting_ids_of(fills),
              (std::vector<ID>{2, 4, 3, 5,
                               1}));
}

TEST(OrderbookPriority, ASingleReductionNeverSpansTwoOrders) {
    orderbook book;
    ASSERT_TRUE(book.add_order(make_order(1, Side::ASK, 100, 5)));
    ASSERT_TRUE(book.add_order(make_order(2, Side::ASK, 100, 5)));

    // Asking for 8 must yield 5 from the front order only — walking the rest of
    // the level is the matching engine's job, not the book's.
    EXPECT_TRUE(FillIs(book.reduce_best_order_quantity(Side::ASK, 8, kTaker),
                       1, kTaker, 100, 5));
    EXPECT_EQ(book.number_of_orders(), 1u);
}

TEST(OrderbookPriority, EmptyingTheTopLevelExposesTheNextOne) {
    orderbook book;
    ASSERT_TRUE(book.add_order(make_order(1, Side::ASK, 100, 5)));
    ASSERT_TRUE(book.add_order(make_order(2, Side::ASK, 101, 5)));

    ASSERT_TRUE(book.reduce_best_order_quantity(Side::ASK, 5, kTaker).has_value());

    ASSERT_TRUE(book.best_ask().has_value());
    EXPECT_EQ(*book.best_ask(), 101);
}

// ---------------------------------------------------------------------------
// Cross-container invariants: the price maps and order_locations_ must never
// disagree about what is resting.
// ---------------------------------------------------------------------------

TEST(OrderbookInvariants, AFullyFilledOrderCanNoLongerBeCancelled) {
    orderbook book;
    ASSERT_TRUE(book.add_order(make_order(1, Side::BID, 100, 5)));

    ASSERT_TRUE(book.reduce_best_order_quantity(Side::BID, 5, kTaker).has_value());

    // If the fill path forgot to erase the location entry, this would return
    // true and then erase a dangling iterator.
    EXPECT_FALSE(book.cancel_order(1));
    EXPECT_EQ(book.number_of_orders(), 0u);
}

TEST(OrderbookInvariants, APartiallyFilledOrderCanStillBeCancelled) {
    orderbook book;
    ASSERT_TRUE(book.add_order(make_order(1, Side::BID, 100, 10)));
    ASSERT_TRUE(book.add_order(make_order(2, Side::BID, 100, 10)));

    ASSERT_TRUE(book.reduce_best_order_quantity(Side::BID, 4, kTaker).has_value());

    // The partial fill must not have invalidated the stored iterator.
    EXPECT_TRUE(book.cancel_order(1));
    EXPECT_EQ(book.number_of_orders(), 1u);

    const std::vector<Fill> fills = drain_side(book, Side::BID);
    ASSERT_EQ(fills.size(), 1u);
    EXPECT_TRUE(FillIs(fills[0], 2, kTaker, 100, 10));
}

TEST(OrderbookInvariants, AnIdIsReusableOnceItsOrderIsFullyFilled) {
    orderbook book;
    ASSERT_TRUE(book.add_order(make_order(1, Side::ASK, 100, 5)));
    ASSERT_TRUE(book.reduce_best_order_quantity(Side::ASK, 5, kTaker).has_value());

    EXPECT_TRUE(book.add_order(make_order(1, Side::ASK, 99, 3)));
    EXPECT_EQ(book.number_of_orders(), 1u);
    ASSERT_TRUE(book.best_ask().has_value());
    EXPECT_EQ(*book.best_ask(), 99);
}

TEST(OrderbookInvariants, LevelsAreReusableAfterBeingEmptiedAndRefilled) {
    orderbook book;
    ASSERT_TRUE(book.add_order(make_order(1, Side::BID, 100, 5)));
    ASSERT_TRUE(book.reduce_best_order_quantity(Side::BID, 5, kTaker).has_value());
    ASSERT_FALSE(book.best_bid().has_value());

    ASSERT_TRUE(book.add_order(make_order(2, Side::BID, 100, 7)));
    ASSERT_TRUE(book.add_order(make_order(3, Side::BID, 100, 7)));

    const std::vector<Fill> fills = drain_side(book, Side::BID);
    EXPECT_EQ(resting_ids_of(fills), (std::vector<ID>{2, 3}));
}

TEST(OrderbookInvariants, BookSurvivesRepeatedAddCancelChurnAtOneLevel) {
    orderbook book;
    for (int round = 0; round < 100; ++round) {
        for (ID id = 1; id <= 5; ++id) {
            ASSERT_TRUE(book.add_order(make_order(id, Side::BID, 100, 5)));
        }
        for (ID id = 1; id <= 5; ++id) {
            ASSERT_TRUE(book.cancel_order(id));
        }
        ASSERT_EQ(book.number_of_orders(), 0u);
        ASSERT_FALSE(book.best_bid().has_value());
    }
}

// ---------------------------------------------------------------------------
// Randomized differential test against a naive reference book.
//
// The reference is deliberately dumb — a flat vector scanned linearly — so it
// is obviously correct by inspection. Insertion order in the vector *is* time
// priority, and std::vector::erase preserves relative order, so FIFO holds.
// ---------------------------------------------------------------------------

namespace {

class ReferenceBook {
  public:
    bool add_order(const Order& order) {
        if (find(order.order_id) != orders_.end()) return false;
        if (order.quantity <= 0) return false;
        orders_.push_back(order);
        return true;
    }

    bool cancel_order(ID order_id) {
        auto it = find(order_id);
        if (it == orders_.end()) return false;
        orders_.erase(it);
        return true;
    }

    std::optional<Price> best_bid() const { return best_price(Side::BID); }
    std::optional<Price> best_ask() const { return best_price(Side::ASK); }
    std::size_t number_of_orders() const { return orders_.size(); }

    std::optional<Fill> reduce_best_order_quantity(Side side, Quantity amount, ID taker_id) {
        if (amount <= 0) return std::nullopt;
        const std::optional<Price> best = best_price(side);
        if (!best.has_value()) return std::nullopt;

        auto it = std::find_if(orders_.begin(), orders_.end(), [&](const Order& o) {
            return o.side == side && o.price == *best;
        });
        const Quantity filled = std::min(amount, it->quantity);
        const Fill fill{.resting_order_id = it->order_id,
                        .maker_id = it->maker_id,
                        .taker_id = taker_id,
                        .price = it->price,
                        .quantity = filled};
        it->quantity -= filled;
        if (it->quantity == 0) orders_.erase(it);
        return fill;
    }

  private:
    std::vector<Order>::iterator find(ID order_id) {
        return std::find_if(orders_.begin(), orders_.end(),
                            [&](const Order& o) { return o.order_id == order_id; });
    }

    std::optional<Price> best_price(Side side) const {
        std::optional<Price> best;
        for (const Order& order : orders_) {
            if (order.side != side) continue;
            if (!best.has_value() || (side == Side::BID ? order.price > *best
                                                        : order.price < *best)) {
                best = order.price;
            }
        }
        return best;
    }

    std::vector<Order> orders_;
};

}  // namespace

class OrderbookDifferential : public ::testing::TestWithParam<unsigned> {};

TEST_P(OrderbookDifferential, MatchesReferenceBookUnderRandomOperations) {
    std::mt19937 rng(GetParam());
    // A small id and price space keeps collisions, duplicate ids, and level
    // reuse frequent rather than rare.
    std::uniform_int_distribution<int> op_dist(0, 9);
    std::uniform_int_distribution<int> id_dist(1, 40);
    std::uniform_int_distribution<int> price_dist(95, 105);
    std::uniform_int_distribution<int> qty_dist(-2, 10);     // includes invalid quantities
    std::uniform_int_distribution<int> side_dist(0, 1);
    std::uniform_int_distribution<int> amount_dist(-2, 12);  // includes invalid amounts

    orderbook book;
    ReferenceBook reference;

    for (int step = 0; step < 4000; ++step) {
        SCOPED_TRACE("seed " + std::to_string(GetParam()) + ", step " + std::to_string(step));

        const int op = op_dist(rng);
        const Side side = side_dist(rng) == 0 ? Side::BID : Side::ASK;
        const ID id = id_dist(rng);

        if (op < 5) {  // add
            const Order order = make_order(id, side, price_dist(rng), qty_dist(rng));
            ASSERT_EQ(book.add_order(order), reference.add_order(order));
        } else if (op < 7) {  // cancel
            ASSERT_EQ(book.cancel_order(id), reference.cancel_order(id));
        } else {  // reduce
            const Quantity amount = amount_dist(rng);
            // Vary the taker so a Fill that echoes the wrong id shows up here too.
            const ID taker_id = id + 5000;
            const std::optional<Fill> actual =
                book.reduce_best_order_quantity(side, amount, taker_id);
            const std::optional<Fill> expected =
                reference.reduce_best_order_quantity(side, amount, taker_id);

            ASSERT_EQ(actual.has_value(), expected.has_value());
            if (expected.has_value()) {
                ASSERT_TRUE(FillIs(actual, expected->resting_order_id, expected->taker_id,
                                   expected->price, expected->quantity));
            }
        }

        ASSERT_EQ(book.number_of_orders(), reference.number_of_orders());
        ASSERT_EQ(book.best_bid(), reference.best_bid());
        ASSERT_EQ(book.best_ask(), reference.best_ask());
    }
}

INSTANTIATE_TEST_SUITE_P(Seeds, OrderbookDifferential,
                         ::testing::Values(1u, 2u, 3u, 4u, 5u, 6u, 7u, 8u));
