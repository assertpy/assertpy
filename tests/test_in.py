import pytest

from assertpy import assert_that


def test_is_in():
    assert_that(1).is_in(1)
    assert_that(1).is_in(1, 2, 3)
    assert_that("foo").is_in("foo", "bar", "baz")
    assert_that([1, 2, 3]).is_in([1, 2, 3], [2, 3, 4], [3, 4, 5])


def test_is_in_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(4).is_in(1, 2, 3)
    assert_that(str(exc_info.value)).is_equal_to("Expected <4> to be in <1, 2, 3>, but was not.")


def test_is_in_missing_arg_failure():
    with pytest.raises(ValueError) as exc_info:
        assert_that(1).is_in()
    assert_that(str(exc_info.value)).is_equal_to("one or more args must be given")


def test_is_not_in():
    assert_that(4).is_not_in(1)
    assert_that(4).is_not_in(1, 2, 3)
    assert_that("fred").is_not_in("foo", "bar", "baz")
    assert_that([4, 4, 4]).is_not_in([1, 2, 3], [2, 3, 4], [3, 4, 5])


def test_is_not_in_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(1).is_not_in(1, 2, 3)
    assert_that(str(exc_info.value)).is_equal_to("Expected <1> to not be in <1, 2, 3>, but was.")


def test_is_not_in_missing_arg_failure():
    with pytest.raises(ValueError) as exc_info:
        assert_that(1).is_not_in()
    assert_that(str(exc_info.value)).is_equal_to("one or more args must be given")


def test_is_in_uses_equality_not_ordering():
    # val < every item, but equal to none: membership must fail (not match by `<=`)
    with pytest.raises(AssertionError):
        assert_that(0).is_in(1, 2, 3)


def test_is_not_in_uses_equality_not_ordering():
    # val < every item, but equal to none: it is genuinely not in the items
    assert_that(0).is_not_in(1, 2, 3)


def test_the_very_nan_a_tuple_holds_is_in_it():
    """Compared with `==` alone, a NaN was not in a tuple holding that same NaN, which `in` says it is."""
    nan = float("nan")
    assert_that(nan).is_in(1.0, nan)
    with pytest.raises(AssertionError):
        assert_that(nan).is_not_in(1.0, nan)


def test_a_fresh_nan_is_still_not_in():
    assert_that(float("nan")).is_not_in(float("nan"))
    with pytest.raises(AssertionError):
        assert_that(float("nan")).is_in(float("nan"))
