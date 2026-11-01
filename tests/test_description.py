import pytest

from assertpy import assert_that


def test_constructor():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(1, "extra msg").is_equal_to(2)
    assert_that(str(exc_info.value)).is_equal_to("[extra msg] Expected <1> to be equal to <2>, but was not.")


def test_described_as():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(1).described_as("extra msg").is_equal_to(2)
    assert_that(str(exc_info.value)).is_equal_to("[extra msg] Expected <1> to be equal to <2>, but was not.")


def test_described_as_double():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(1).described_as("extra msg").described_as("other msg").is_equal_to(2)
    assert_that(str(exc_info.value)).is_equal_to("[other msg] Expected <1> to be equal to <2>, but was not.")


def test_described_as_chained():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(1).described_as("extra msg").is_equal_to(1).described_as("other msg").is_equal_to(1).described_as(
            "last msg"
        ).is_equal_to(2)
    assert_that(str(exc_info.value)).is_equal_to("[last msg] Expected <1> to be equal to <2>, but was not.")
