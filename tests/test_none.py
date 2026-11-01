import pytest

from assertpy import assert_that


def test_is_none():
    assert_that(None).is_none()


def test_is_none_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that("foo").is_none()
    assert_that(str(exc_info.value)).is_equal_to("Expected <foo> to be <None>, but was not.")


def test_is_not_none():
    assert_that("foo").is_not_none()
    assert_that(123).is_not_none()
    assert_that(False).is_not_none()
    assert_that([]).is_not_none()
    assert_that({}).is_not_none()


def test_is_not_none_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(None).is_not_none()
    assert_that(str(exc_info.value)).is_equal_to("Expected not <None>, but was.")
