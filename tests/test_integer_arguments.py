"""Every integer an assertion takes, as an argument or as the value, read as the int it stands for.

An `int`, a subclass of one such as an `IntEnum` member, and a `numpy` integer are integers.  A bool is not,
and nor is any other number, or a type whose `__index__` of its own claims to be one.
"""

from __future__ import annotations

import decimal
import enum
import fractions
import numbers

import pytest

from assertpy import assert_that, match
from tests.optional import needs


class _Two(enum.IntEnum):
    TWO = 2


class _OwnIndex:
    """Registered as an integral with an `__index__` of its own, which could answer anything."""

    def __index__(self) -> int:
        return 2


numbers.Integral.register(_OwnIndex)


def _numpy(name: str, *args: object) -> object:
    return getattr(needs("numpy"), name)(*args)


_ACCEPTED = {
    "int": lambda: 2,
    "int-enum": lambda: _Two.TWO,
    "numpy-int64": lambda: _numpy("int64", 2),
    "numpy-uint8": lambda: _numpy("uint8", 2),
    "numpy-uint64": lambda: _numpy("uint64", 2),
}
_REFUSED = {
    "bool": lambda: True,
    "numpy-bool": lambda: _numpy("bool_", True),
    "float": lambda: 2.0,
    "decimal": lambda: decimal.Decimal(2),
    "fraction": lambda: fractions.Fraction(2),
    "str": lambda: "2",
    "none": lambda: None,
    "own-index": _OwnIndex,
    "numpy-timedelta": lambda: _numpy("timedelta64", 2, "s"),
}
_ASKED = {
    "element": lambda number: assert_that([10, 20, 30]).element(number).val,
    "is_length": lambda number: assert_that("ab").check().is_length(number).passed,
    "is_length_between-low": lambda number: assert_that("ab").check().is_length_between(number, 5).passed,
    "is_length_between-high": lambda number: assert_that("ab").check().is_length_between(0, number).passed,
    "has_size_greater_than": lambda number: assert_that("abc").check().has_size_greater_than(number).passed,
    "has_size_less_than": lambda number: assert_that("a").check().has_size_less_than(number).passed,
    "has_size_between-low": lambda number: assert_that("ab").check().has_size_between(number, 5).passed,
    "has_size_between-high": lambda number: assert_that("ab").check().has_size_between(0, number).passed,
    "is_divisible_by": lambda number: assert_that(4).check().is_divisible_by(number).passed,
    "is_divisible_by-value": lambda number: assert_that(number).check().is_divisible_by(2).passed,
    "is_even": lambda number: assert_that(number).check().is_even().passed,
    "is_odd": lambda number: assert_that(number).check().is_odd().passed,
    "has_byte_at": lambda number: assert_that(b"\x00\x01\x02").check().has_byte_at(number, 2).passed,
    "match.is_length": lambda number: match.is_length(number).matches("ab"),
    "match.has_length": lambda number: match.has_length(number).matches("ab"),
    "match.is_divisible_by": lambda number: match.is_divisible_by(number).matches(4),
}
_MATCHED = {
    "match.is_even": lambda number: match.is_even().matches(number),
    "match.is_odd": lambda number: match.is_odd().matches(number),
    "match.is_divisible_by": lambda number: match.is_divisible_by(2).matches(number),
}


@pytest.mark.parametrize("asked", list(_ASKED))
@pytest.mark.parametrize("kind", list(_ACCEPTED))
def test_an_integer_of_any_kind_is_asked_as_the_int_it_stands_for(asked, kind):
    assert_that(_ASKED[asked](_ACCEPTED[kind]())).is_equal_to(_ASKED[asked](2))


@pytest.mark.parametrize("asked", list(_ASKED))
@pytest.mark.parametrize("kind", list(_REFUSED))
def test_what_is_no_integer_is_refused_by_name(asked, kind):
    with pytest.raises(TypeError, match="must be an integer"):
        _ASKED[asked](_REFUSED[kind]())


@pytest.mark.parametrize("kind", list(_ACCEPTED))
def test_an_expected_byte_of_any_integer_kind_is_compared_as_the_int_it_stands_for(kind):
    """Compared by `==` and never refused, since what it meets may be anything answering one."""
    assert_that(assert_that(b"\x00\x01\x02").check().has_byte_at(2, _ACCEPTED[kind]()).passed).is_true()


@pytest.mark.parametrize("asked", list(_MATCHED))
@pytest.mark.parametrize("kind", list(_ACCEPTED))
def test_a_matcher_takes_an_integer_of_any_kind_as_the_int_it_stands_for(asked, kind):
    assert_that(_MATCHED[asked](_ACCEPTED[kind]())).is_equal_to(_MATCHED[asked](2))


@pytest.mark.parametrize("asked", list(_MATCHED))
@pytest.mark.parametrize("kind", list(_REFUSED))
def test_a_matcher_does_not_match_what_is_no_integer(asked, kind):
    assert_that(_MATCHED[asked](_REFUSED[kind]())).is_false()


def test_a_length_matcher_refuses_a_negative_length_as_the_assertion_does():
    with pytest.raises(ValueError, match="positive"):
        match.is_length(-1)
