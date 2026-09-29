add_executable(me_tests
  orderbook_test.cpp
)

target_link_libraries(me_tests PRIVATE me_core GTest::gtest_main)

include(GoogleTest)
gtest_discover_tests(me_tests)
