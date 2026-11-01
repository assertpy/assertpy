"""Boundary, operator-direction, and negative-case coverage.

Each test pins a predicate at an edge - an exact boundary, the direction of a comparison, or a
negative case - that the per-feature suites do not otherwise exercise. Grouped by module.
"""

from dataclasses import FrozenInstanceError

import pytest

from assertpy import assert_that, match
from assertpy._engine._compare import _CompareConfig


def test_is_zero_matcher_rejects_negative():
    assert_that(match.is_zero().matches(-5)).is_false()


def test_is_odd_matcher_uses_modulo_not_bitand():
    assert_that(match.is_odd().matches(5)).is_true()


def test_is_divisible_by_matcher_allows_negative_divisor():
    assert_that(match.is_divisible_by(-3).matches(9)).is_true()
    assert_that(match.is_divisible_by(-3).matches(10)).is_false()


def test_close_to_matcher_boundary_and_operator():
    assert_that(match.close_to(10, 2).matches(12)).is_true()
    assert_that(match.close_to(10, 2).matches(20)).is_false()


def test_matches_structure_value_less_than_expected():
    with pytest.raises(AssertionError):
        assert_that({"n": 3}).matches_structure({"n": 5})


def test_is_between_allows_equal_low_and_high():
    assert_that(5).is_between(5, 5)


def test_is_close_to_allows_zero_tolerance():
    assert_that(5).is_close_to(5, 0)


def test_contains_entry_rejects_empty_entry():
    with pytest.raises(ValueError):
        assert_that({"a": 1}).contains_entry({})


def test_contains_entry_value_greater_than_expected():
    with pytest.raises(AssertionError):
        assert_that({"a": 5}).contains_entry({"a": 3})


def test_has_byte_at_out_of_range_uses_explicit_message():
    with pytest.raises(IndexError, match="to be in range"):
        assert_that(b"abc").has_byte_at(5, 0x00)


def test_has_byte_at_value_greater_than_expected():
    with pytest.raises(AssertionError):
        assert_that(b"\xff").has_byte_at(0, 0x01)


def test_is_hex_equal_to_value_greater_than_expected():
    with pytest.raises(AssertionError):
        assert_that(b"\xff").is_hex_equal_to("00")


def test_element_out_of_range_uses_explicit_message():
    with pytest.raises(IndexError, match="to be in range"):
        assert_that([1, 2, 3]).element(5)


def test_single_rejects_two_elements():
    with pytest.raises(ValueError):
        assert_that([1, 2]).single()


def test_is_equal_to_ignoring_case_lexicographically_less():
    with pytest.raises(AssertionError):
        assert_that("ABC").is_equal_to_ignoring_case("xyz")


def test_is_length_actual_longer_than_expected():
    with pytest.raises(AssertionError):
        assert_that([1, 2, 3]).is_length(2)


def test_zero_tolerance_is_valid_for_exact_equality():
    assert_that(1.5).is_equal_to(1.5, tolerance=0)


def test_tolerance_at_exact_boundary_passes():
    assert_that(100).is_equal_to(102, tolerance=2)


def test_tolerance_just_beyond_boundary_fails():
    with pytest.raises(AssertionError):
        assert_that(100).is_equal_to(103, tolerance=2)


def test_ignore_spec_matches_by_equality_not_identity():
    key = 10**6  # large int, not interned, so == differs from is
    assert_that({key: 1, "k": 2}).is_equal_to({key: 9, "k": 2}, ignore=int(str(key)))


def test_compare_config_is_frozen():
    config = _CompareConfig(tolerance=0.1)
    with pytest.raises(FrozenInstanceError):
        config.tolerance = 0.2
