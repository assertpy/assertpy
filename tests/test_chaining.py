import datetime

from assertpy import assert_that


class TestChaining:
    def test_callable_chain(self):
        assert_that(print).is_callable().is_not_none()

    def test_satisfy_chain(self):
        assert_that([1, 2, 3]).any_satisfy(lambda x: x > 2).none_satisfy(lambda x: x < 0)

    def test_contains_exactly_chain(self):
        assert_that([1, 2, 3]).contains_exactly(1, 2, 3).is_length(3)

    def test_contains_in_order_chain(self):
        assert_that([1, 2, 3]).contains_in_order(1, 3).is_not_empty()

    def test_datetime_chain(self):
        earlier = datetime.datetime(2020, 1, 1)
        later = datetime.datetime(2020, 12, 31)
        assert_that(earlier).is_before_or_equal_to(later).is_after_or_equal_to(earlier)
