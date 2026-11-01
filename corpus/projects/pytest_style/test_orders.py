"""A suite the way a first-time user writes one: builtin values, no annotations, no typing tricks.

Nothing here is clever, and that is the point.  This is the shape most consumer code has, so it is the
shape a narrowed type breaks first.
"""

from assertpy import assert_that, soft_assertions


def orders():
    return [
        {"id": 1, "customer": "alice", "total": 120.5, "items": ["book", "pen"], "paid": True},
        {"id": 2, "customer": "bob", "total": 12.0, "items": ["pen"], "paid": False},
        {"id": 3, "customer": "carol", "total": 340.0, "items": ["desk", "chair", "lamp"], "paid": True},
    ]


def test_the_payload_has_the_shape_the_api_documents():
    assert_that(orders()).is_length(3)
    assert_that(orders()[0]).contains_key("id", "customer", "total")
    assert_that(orders()[0]["customer"]).is_equal_to("alice")


def test_totals_are_within_the_range_the_report_expects():
    for order in orders():
        assert_that(order["total"]).is_greater_than(0).is_less_than(1000)


def test_the_pipeline_reads_the_way_it_looks():
    paid = assert_that(orders()).filtered_on(lambda order: order["paid"])
    assert_that(paid.value).is_length(2)

    names = assert_that(orders()).extracting("customer")
    names.contains("alice", "bob").does_not_contain("dave")

    totals = assert_that(orders()).mapped(lambda order: order["total"])
    assert_that(totals.value).is_length(3)


def test_a_failure_says_what_went_wrong():
    try:
        assert_that(orders()[1]["total"]).described_as("unpaid order total").is_greater_than(100)
    except AssertionError as failure:
        assert_that(str(failure)).contains("unpaid order total")
    else:  # pragma: no cover - the assertion above is expected to fail
        raise AssertionError("expected the assertion to fail")


def test_soft_assertions_collect_every_complaint():
    try:
        with soft_assertions():
            assert_that(orders()[1]["paid"]).is_true()
            assert_that(orders()[1]["total"]).is_greater_than(100)
    except AssertionError as failure:
        assert_that(str(failure)).contains("2")
    else:  # pragma: no cover - two failures are expected
        raise AssertionError("expected the soft block to fail")


def test_strings_and_texts_behave_as_they_read():
    assert_that("order-2026-08").starts_with("order-").ends_with("08").contains("2026")
    assert_that("  padded  ").is_not_empty()
    assert_that("alice").is_lower().is_length(5)


def test_numbers_and_dates_keep_their_own_assertions():
    assert_that(120.5).is_close_to(120, 1)
    assert_that(7).is_between(1, 10)
    assert_that([1, 2, 3]).contains_sequence(1, 2)


def test_subset_reads_both_ways_round():
    assert_that(["pen"]).is_subset_of(["book", "pen"])
    assert_that([1, 2]).is_subset_of(1, 2, 3)
    assert_that("ab").is_subset_of("abc")
    assert_that({"id": 1}).is_subset_of({"id": 1, "customer": "alice"})
