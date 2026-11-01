import pytest

from assertpy import assert_that, fail


def test_fail():
    with pytest.raises(AssertionError) as exc_info:
        fail()
    assert_that(str(exc_info.value)).is_equal_to("Fail!")


def test_fail_msg():
    with pytest.raises(AssertionError) as exc_info:
        fail("some msg")
    assert_that(str(exc_info.value)).is_equal_to("Fail: some msg!")
