import pytest

from assertpy import assert_that, soft_assertions, soft_fail


def test_soft_fail_without_context():
    with pytest.raises(AssertionError) as exc_info:
        soft_fail()
    out = str(exc_info.value)
    assert_that(out).is_equal_to("Fail!")
    assert_that(out).does_not_contain("should have raised error")


def test_soft_fail_with_msg_without_context():
    with pytest.raises(AssertionError) as exc_info:
        soft_fail("some msg")
    out = str(exc_info.value)
    assert_that(out).is_equal_to("Fail: some msg!")
    assert_that(out).does_not_contain("should have raised error")


def test_soft_fail():
    with pytest.raises(AssertionError) as exc_info, soft_assertions():
        soft_fail()
    out = str(exc_info.value)
    assert_that(out).contains("Fail!")
    assert_that(out).does_not_contain("should have raised error")


def test_soft_fail_with_msg():
    with pytest.raises(AssertionError) as exc_info, soft_assertions():
        soft_fail("foobar")
    out = str(exc_info.value)
    assert_that(out).contains("Fail: foobar!")
    assert_that(out).does_not_contain("should have raised error")


def test_soft_fail_with_soft_failing_asserts():
    with pytest.raises(AssertionError) as exc_info, soft_assertions():
        assert_that("foo").is_length(4)
        assert_that("foo").is_empty()
        soft_fail("foobar")
        assert_that("foo").is_not_equal_to("foo")
        assert_that("foo").is_equal_to_ignoring_case("BAR")
    out = str(exc_info.value)
    assert_that(out).contains("Expected <foo> to be of length <4>, but was <3>.")
    assert_that(out).contains("Expected <foo> to be empty string, but was not.")
    assert_that(out).contains("Fail: foobar!")
    assert_that(out).contains("Expected <foo> to be not equal to <foo>, but was.")
    assert_that(out).contains("Expected <foo> to be case-insensitive equal to <BAR>, but was not.")
    assert_that(out).does_not_contain("should have raised error")


def test_double_soft_fail():
    with pytest.raises(AssertionError) as exc_info, soft_assertions():
        soft_fail()
        soft_fail("foobar")
    out = str(exc_info.value)
    assert_that(out).contains("Fail!")
    assert_that(out).contains("Fail: foobar!")
    assert_that(out).does_not_contain("should have raised error")
