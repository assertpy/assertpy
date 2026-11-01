import decimal
import fractions
import math
import numbers
import operator
import re
import types

import pytest

from assertpy import assert_that, match
from assertpy._engine import _ordering
from assertpy._engine._compare import _difference_within


def test_is_zero():
    assert_that(0).is_zero()
    assert_that(0.0).is_zero()
    assert_that(0 + 0j).is_zero()


def test_is_zero_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(1).is_zero()
    assert_that(str(exc_info.value)).is_equal_to("Expected <1> to be equal to <0>, but was not.")


def test_is_zero_bad_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that("foo").is_zero()
    assert_that(str(exc_info.value)).is_equal_to("val must be a number, but was <'foo'> (str)")


def test_is_not_zero():
    assert_that(1).is_not_zero()
    assert_that(0.001).is_not_zero()
    assert_that(0 + 1j).is_not_zero()


def test_is_not_zero_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(0).is_not_zero()
    assert_that(str(exc_info.value)).is_equal_to("Expected <0> to be not equal to <0>, but was.")


def test_is_not_zero_bad_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that("foo").is_not_zero()
    assert_that(str(exc_info.value)).is_equal_to("val must be a number, but was <'foo'> (str)")


def test_is_nan():
    assert_that(float("NaN")).is_nan()
    assert_that(float("Inf") - float("Inf")).is_nan()


class _BrokenFloat:
    """Accepted as a real number and unreadable as one, which is the shape the guard had to tell apart."""

    def __float__(self) -> float:
        raise OverflowError("my __float__ is broken")

    def __repr__(self) -> str:
        return "<BrokenFloat>"


numbers.Real.register(_BrokenFloat)


@pytest.mark.parametrize("question", ["is_nan", "is_not_nan", "is_inf", "is_not_inf"])
def test_a_float_conversion_of_their_own_that_raises_is_not_an_answer(question):
    """The guard for a bignum swallowed an `OverflowError` from the value's own `__float__` as well.

    Swallowed, `is_not_nan()` and `is_not_inf()` held on a value nothing could read, which is an error
    in the value reported as a verdict.  Told apart by where the traceback stops, the way the ordering
    and matcher paths already tell it apart.
    """
    with pytest.raises(OverflowError, match="my __float__ is broken"):
        getattr(assert_that(_BrokenFloat()), question)()


@pytest.mark.parametrize("big", [math.factorial(200), fractions.Fraction(10**400, 3)], ids=["an-int", "a-fraction"])
def test_bignum_does_not_overflow_nan_inf_guards(big):
    """A rational is asked by its type: the `__float__` of a `Fraction` is Python, so its overflow was re-raised."""
    assert_that(big).is_close_to(big, 1)
    assert_that(big).is_not_nan()
    assert_that(big).is_not_inf()
    with pytest.raises(AssertionError):
        assert_that(big).is_nan()
    with pytest.raises(AssertionError):
        assert_that(big).is_inf()


def test_nan_fails_relational_assertions():
    # NaN is unordered: it must FAIL relational assertions (diverges from assertpy, where it passes)
    nan = float("nan")
    for call in (
        lambda: assert_that(nan).is_positive(),
        lambda: assert_that(nan).is_negative(),
        lambda: assert_that(nan).is_between(0, 100),
        lambda: assert_that(nan).is_greater_than(0),
        lambda: assert_that(nan).is_greater_than_or_equal_to(0),
        lambda: assert_that(nan).is_less_than(0),
        lambda: assert_that(nan).is_less_than_or_equal_to(0),
    ):
        with pytest.raises(AssertionError):
            call()


def test_nan_passes_is_not_between():
    assert_that(float("nan")).is_not_between(0, 100)


def test_is_nan_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(0).is_nan()
    assert_that(str(exc_info.value)).is_equal_to("Expected <0> to be <NaN>, but was not.")


def test_is_nan_bad_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that("foo").is_nan()
    assert_that(str(exc_info.value)).is_equal_to("val must be a number, but was <'foo'> (str)")


def test_is_nan_bad_type_failure_complex():
    with pytest.raises(TypeError) as exc_info:
        assert_that(1 + 2j).is_nan()
    assert_that(str(exc_info.value)).is_equal_to("val must be a real number, but was <(1+2j)> (complex)")


def test_is_not_nan():
    assert_that(1).is_not_nan()
    assert_that(1.0).is_not_nan()


def test_is_not_nan_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(float("NaN")).is_not_nan()
    assert_that(str(exc_info.value)).is_equal_to("Expected not <NaN>, but was.")


def test_is_not_nan_bad_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that("foo").is_not_nan()
    assert_that(str(exc_info.value)).is_equal_to("val must be a number, but was <'foo'> (str)")


def test_is_not_nan_bad_type_failure_complex():
    with pytest.raises(TypeError) as exc_info:
        assert_that(1 + 2j).is_not_nan()
    assert_that(str(exc_info.value)).is_equal_to("val must be a real number, but was <(1+2j)> (complex)")


def test_is_inf():
    assert_that(float("Inf")).is_inf()
    assert_that(1e1000).is_inf()


def test_is_inf_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(0).is_inf()
    assert_that(str(exc_info.value)).is_equal_to("Expected <0> to be <Inf>, but was not.")


def test_is_inf_bad_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that("foo").is_inf()
    assert_that(str(exc_info.value)).is_equal_to("val must be a number, but was <'foo'> (str)")


def test_is_inf_bad_type_failure_complex():
    with pytest.raises(TypeError) as exc_info:
        assert_that(1 + 2j).is_inf()
    assert_that(str(exc_info.value)).is_equal_to("val must be a real number, but was <(1+2j)> (complex)")


def test_is_not_inf():
    assert_that(1).is_not_inf()
    assert_that(123.456).is_not_inf()


def test_is_not_inf_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(float("Inf")).is_not_inf()
    assert_that(str(exc_info.value)).is_equal_to("Expected not <Inf>, but was.")


def test_is_not_inf_bad_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that("foo").is_not_inf()
    assert_that(str(exc_info.value)).is_equal_to("val must be a number, but was <'foo'> (str)")


def test_is_not_inf_bad_type_failure_complex():
    with pytest.raises(TypeError) as exc_info:
        assert_that(1 + 2j).is_not_inf()
    assert_that(str(exc_info.value)).is_equal_to("val must be a real number, but was <(1+2j)> (complex)")


def test_is_greater_than():
    assert_that(123).is_greater_than(100)
    assert_that(123).is_greater_than(0)
    assert_that(123).is_greater_than(-100)
    assert_that(123).is_greater_than(122.5)


def test_is_greater_than_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(123).is_greater_than(123)
    assert_that(str(exc_info.value)).is_equal_to("Expected <123> to be greater than <123>, but was not.")


def test_is_greater_than_complex_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(1 + 2j).is_greater_than(0)
    assert_that(str(exc_info.value)).is_equal_to(
        "val must be a value with an ordering (complex numbers have none), but was <(1+2j)> (complex)"
    )


def test_is_greater_than_bad_value_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that("foo").is_greater_than(0)
    assert_that(str(exc_info.value)).is_equal_to(
        "given other arg must be comparable with val <'foo'> (str), but was <0> (int)"
    )


def test_is_greater_than_bad_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123).is_greater_than("foo")
    assert_that(str(exc_info.value)).is_equal_to("given other arg must be a number, but was <'foo'> (str)")


def test_is_greater_than_or_equal_to():
    assert_that(123).is_greater_than_or_equal_to(100)
    assert_that(123).is_greater_than_or_equal_to(123)
    assert_that(123).is_greater_than_or_equal_to(0)
    assert_that(123).is_greater_than_or_equal_to(-100)
    assert_that(123).is_greater_than_or_equal_to(122.5)


def test_is_greater_than_or_equal_to_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(123).is_greater_than_or_equal_to(1000)
    assert_that(str(exc_info.value)).is_equal_to("Expected <123> to be greater than or equal to <1000>, but was not.")


def test_is_greater_than_or_equal_to_complex_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(1 + 2j).is_greater_than_or_equal_to(0)
    assert_that(str(exc_info.value)).is_equal_to(
        "val must be a value with an ordering (complex numbers have none), but was <(1+2j)> (complex)"
    )


def test_is_greater_than_or_equal_to_bad_value_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that("foo").is_greater_than_or_equal_to(0)
    assert_that(str(exc_info.value)).is_equal_to(
        "given other arg must be comparable with val <'foo'> (str), but was <0> (int)"
    )


def test_is_greater_than_or_equal_to_bad_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123).is_greater_than_or_equal_to("foo")
    assert_that(str(exc_info.value)).is_equal_to("given other arg must be a number, but was <'foo'> (str)")


def test_is_less_than():
    assert_that(123).is_less_than(1000)
    assert_that(123).is_less_than(1e6)
    assert_that(-123).is_less_than(-100)
    assert_that(123).is_less_than(123.001)


def test_is_less_than_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(123).is_less_than(123)
    assert_that(str(exc_info.value)).is_equal_to("Expected <123> to be less than <123>, but was not.")


def test_is_less_than_complex_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(1 + 2j).is_less_than(0)
    assert_that(str(exc_info.value)).is_equal_to(
        "val must be a value with an ordering (complex numbers have none), but was <(1+2j)> (complex)"
    )


def test_is_less_than_bad_value_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that("foo").is_less_than(0)
    assert_that(str(exc_info.value)).is_equal_to(
        "given other arg must be comparable with val <'foo'> (str), but was <0> (int)"
    )


def test_is_less_than_bad_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123).is_less_than("foo")
    assert_that(str(exc_info.value)).is_equal_to("given other arg must be a number, but was <'foo'> (str)")


def test_is_less_than_or_equal_to():
    assert_that(123).is_less_than_or_equal_to(1000)
    assert_that(123).is_less_than_or_equal_to(123)
    assert_that(123).is_less_than_or_equal_to(1e6)
    assert_that(-123).is_less_than_or_equal_to(-100)
    assert_that(123).is_less_than_or_equal_to(123.001)


def test_is_less_than_or_equal_to_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(123).is_less_than_or_equal_to(100)
    assert_that(str(exc_info.value)).is_equal_to("Expected <123> to be less than or equal to <100>, but was not.")


def test_is_less_than_or_equal_to_complex_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(1 + 2j).is_less_than_or_equal_to(0)
    assert_that(str(exc_info.value)).is_equal_to(
        "val must be a value with an ordering (complex numbers have none), but was <(1+2j)> (complex)"
    )


def test_is_less_than_or_equal_to_bad_value_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that("foo").is_less_than_or_equal_to(0)
    assert_that(str(exc_info.value)).is_equal_to(
        "given other arg must be comparable with val <'foo'> (str), but was <0> (int)"
    )


def test_is_less_than_or_equal_to_bad_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123).is_less_than_or_equal_to("foo")
    assert_that(str(exc_info.value)).is_equal_to("given other arg must be a number, but was <'foo'> (str)")


def test_is_positive():
    assert_that(1).is_positive()


def test_is_positive_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(0).is_positive()
    assert_that(str(exc_info.value)).is_equal_to("Expected <0> to be greater than <0>, but was not.")


def test_is_negative():
    assert_that(-1).is_negative()


def test_is_negative_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(0).is_negative()
    assert_that(str(exc_info.value)).is_equal_to("Expected <0> to be less than <0>, but was not.")


def test_is_between():
    assert_that(123).is_between(120, 125)
    assert_that(123).is_between(0, 1e6)
    assert_that(-123).is_between(-150, -100)
    assert_that(123).is_between(122.999, 123.001)


def test_is_between_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(123).is_between(0, 1)
    assert_that(str(exc_info.value)).is_equal_to("Expected <123> to be between <0> and <1>, but was not.")


def test_is_between_complex_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(1 + 2j).is_between(0, 1)
    assert_that(str(exc_info.value)).is_equal_to(
        "val must be a value with an ordering (complex numbers have none), but was <(1+2j)> (complex)"
    )


def test_is_between_bad_value_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that("foo").is_between(0, 1)
    assert_that(str(exc_info.value)).is_equal_to(
        "val must be a number or a date, which is what an ordering is defined for, but was <'foo'> (str)"
    )


def test_is_between_low_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123).is_between("foo", 1)
    assert_that(str(exc_info.value)).is_equal_to("given low arg must be a number, but was <'foo'> (str)")


def test_is_between_high_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123).is_between(0, "foo")
    assert_that(str(exc_info.value)).is_equal_to("given high arg must be a number, but was <'foo'> (str)")


def test_is_between_bad_arg_delta_failure():
    with pytest.raises(ValueError) as exc_info:
        assert_that(123).is_between(1, 0)
    assert_that(str(exc_info.value)).is_equal_to("given low arg must be less than given high arg")


def test_is_not_between():
    assert_that(123).is_not_between(124, 125)
    assert_that(123).is_not_between(1e5, 1e6)
    assert_that(-123).is_not_between(-1000, -150)
    assert_that(123).is_not_between(122.999, 122.9999)


def test_is_not_between_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(123).is_not_between(0, 1000)
    assert_that(str(exc_info.value)).is_equal_to("Expected <123> to not be between <0> and <1000>, but was.")


def test_is_not_between_complex_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(1 + 2j).is_not_between(0, 1)
    assert_that(str(exc_info.value)).is_equal_to(
        "val must be a value with an ordering (complex numbers have none), but was <(1+2j)> (complex)"
    )


def test_is_not_between_bad_value_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that("foo").is_not_between(0, 1)
    assert_that(str(exc_info.value)).is_equal_to(
        "val must be a number or a date, which is what an ordering is defined for, but was <'foo'> (str)"
    )


def test_is_not_between_low_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123).is_not_between("foo", 1)
    assert_that(str(exc_info.value)).is_equal_to("given low arg must be a number, but was <'foo'> (str)")


def test_is_not_between_high_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123).is_not_between(0, "foo")
    assert_that(str(exc_info.value)).is_equal_to("given high arg must be a number, but was <'foo'> (str)")


def test_is_not_between_bad_arg_delta_failure():
    with pytest.raises(ValueError) as exc_info:
        assert_that(123).is_not_between(1, 0)
    assert_that(str(exc_info.value)).is_equal_to("given low arg must be less than given high arg")


@pytest.mark.parametrize("nan", [decimal.Decimal("NaN"), decimal.Decimal("sNaN")], ids=["quiet", "signalling"])
@pytest.mark.parametrize("side", ["low", "high"])
def test_a_decimal_nan_bound_holds_nothing_between_it_and_the_other(nan, side):
    """Checking the bounds' order asked `low > high` itself, and a `Decimal` NaN signals there.

    The ordering engine reads the signal as unordered, which is what `match.between` already answered.
    """
    low, high = (nan, 9) if side == "low" else (-9, nan)
    with pytest.raises(AssertionError, match="to be between"):
        assert_that(-1).is_between(low, high)
    assert_that(-1).is_not_between(low, high)
    assert_that(match.between(low, high).matches(-1)).is_false()


@pytest.mark.parametrize(
    ("value", "low", "high", "message"),
    [
        (1, 1j, 2, "given low arg must be a number, but was <1j> (complex)"),
        (1, 0, 2j, "given high arg must be a number, but was <2j> (complex)"),
        (0, 1, 1 + 2j, "given high arg must be a number, but was <(1+2j)> (complex)"),
    ],
    ids=["low", "high", "high-with-the-value-below-low"],
)
def test_a_bound_with_no_ordering_is_refused_under_its_own_name(value, low, high, message):
    """The raw `>` used to let the operator's own `not supported between` out, naming neither bound.

    Refused with the bounds, not where the value meets them: below the low bound the high one is never asked.
    """
    for question in ("is_between", "is_not_between"):
        with pytest.raises(TypeError) as caught:
            getattr(assert_that(value), question)(low, high)
        assert_that(str(caught.value)).is_equal_to(message)


class _RaisingGreaterThan:
    """Registered as a real, with a `>` of its own that raises what it was built with."""

    def __init__(self, error: Exception) -> None:
        self.error = error

    def __gt__(self, other: object) -> bool:
        raise self.error


numbers.Real.register(_RaisingGreaterThan)


@pytest.mark.parametrize(
    "error",
    [TypeError("my __gt__ is broken"), decimal.InvalidOperation("my __gt__ is broken")],
    ids=["type-error", "decimal-signal"],
)
def test_a_bound_whose_own_comparison_raises_is_handed_on(error):
    """Only a `Decimal` NaN among the bounds makes a signal a verdict, and only the operator's own refusal a pair."""
    with pytest.raises(type(error), match="my __gt__ is broken"):
        assert_that(5).is_between(_RaisingGreaterThan(error), 9)


def test_a_signal_from_a_bounds_own_comparison_surfaces_beside_a_nan_bound():
    """A NaN high bound makes the bounds' order no question, and the value is still ordered against the low one."""
    raising = _RaisingGreaterThan(decimal.InvalidOperation("my __gt__ is broken"))
    with pytest.raises(decimal.InvalidOperation, match="my __gt__ is broken"):
        assert_that(5).is_between(raising, decimal.Decimal("NaN"))


def test_is_close_to():
    assert_that(123.01).is_close_to(123, 1)
    assert_that(0.01).is_close_to(0, 1)
    assert_that(-123.01).is_close_to(-123, 1)


def test_is_close_to_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(123.01).is_close_to(100, 1)
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <123.01> to be close to <100> within tolerance <1>, but was not."
    )


def test_is_close_to_complex_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(1 + 2j).is_close_to(0, 1)
    assert_that(str(exc_info.value)).is_equal_to(
        "val must be a value with an ordering (complex numbers have none), but was <(1+2j)> (complex)"
    )


def test_is_close_to_bad_value_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that("foo").is_close_to(123, 1)
    assert_that(str(exc_info.value)).is_equal_to("val must be a number or a datetime, but was <'foo'> (str)")


def test_is_close_to_bad_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123.01).is_close_to("foo", 1)
    assert_that(str(exc_info.value)).is_equal_to("given other arg must be a number, but was <'foo'> (str)")


def test_is_close_to_bad_tolerance_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123.01).is_close_to(0, "foo")
    assert_that(str(exc_info.value)).is_equal_to("given tolerance arg must be a number, but was <'foo'> (str)")


@pytest.mark.parametrize("assertion", ["is_close_to", "is_not_close_to"])
@pytest.mark.parametrize("flag", [True, False])
def test_a_bool_tolerance_is_refused_as_tolerance_refuses_it(assertion, flag):
    # a flag passed where the distance goes used to read as 1 or 0, while `tolerance=` and the matcher refused it
    with pytest.raises(TypeError) as exc_info:
        getattr(assert_that(1.0), assertion)(5.0, flag)
    assert_that(str(exc_info.value)).is_equal_to(
        f"given tolerance arg must be a number other than a bool, but was <{flag}> (bool)"
    )


@pytest.mark.parametrize("assertion", ["is_close_to", "is_not_close_to"])
@pytest.mark.parametrize(
    ("val", "other", "refusal"),
    [
        (True, 5.0, "val must be a number other than a bool, or a datetime, but was <True> (bool)"),
        (1.0, False, "given other arg must be a number other than a bool, but was <False> (bool)"),
    ],
    ids=["val", "other"],
)
def test_a_bool_operand_is_refused_as_tolerance_compares_it_exactly(assertion, val, other, refusal):
    # `tolerance=` leaves a bool out of the distance, and a flag measured against a number is a mistake
    with pytest.raises(TypeError) as exc_info:
        getattr(assert_that(val), assertion)(other, 0.5)
    assert_that(str(exc_info.value)).is_equal_to(refusal)


def test_is_close_to_negative_tolerance_failure():
    with pytest.raises(ValueError) as exc_info:
        assert_that(123.01).is_close_to(123, -1)
    assert_that(str(exc_info.value)).is_equal_to("given tolerance arg must not be negative")


def test_is_close_to_nan_val_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(float("nan")).is_close_to(123, 0.1)
    assert_that(str(exc_info.value)).contains("to be close to")


def test_is_close_to_nan_other_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(123).is_close_to(float("nan"), 0.1)
    assert_that(str(exc_info.value)).contains("to be close to")


def test_is_close_to_nan_tolerance_failure():
    with pytest.raises(ValueError) as exc_info:
        assert_that(123).is_close_to(123, float("nan"))
    assert_that(str(exc_info.value)).is_equal_to("given tolerance arg must not be NaN")


def test_is_not_close_to_nan():
    assert_that(float("nan")).is_not_close_to(123, 0.1)


def test_is_not_close_to():
    assert_that(123.01).is_not_close_to(122, 1)
    assert_that(0.01).is_not_close_to(0, 0.001)
    assert_that(-123.01).is_not_close_to(-122, 1)


def test_is_not_close_to_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(123.01).is_not_close_to(123, 1)
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <123.01> to not be close to <123> within tolerance <1>, but was."
    )


def test_is_not_close_to_complex_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(1 + 2j).is_not_close_to(0, 1)
    assert_that(str(exc_info.value)).is_equal_to(
        "val must be a value with an ordering (complex numbers have none), but was <(1+2j)> (complex)"
    )


def test_is_not_close_to_bad_value_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that("foo").is_not_close_to(123, 1)
    assert_that(str(exc_info.value)).is_equal_to("val must be a number or a datetime, but was <'foo'> (str)")


def test_is_not_close_to_bad_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123.01).is_not_close_to("foo", 1)
    assert_that(str(exc_info.value)).is_equal_to("given other arg must be a number, but was <'foo'> (str)")


def test_is_not_close_to_bad_tolerance_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123.01).is_not_close_to(0, "foo")
    assert_that(str(exc_info.value)).is_equal_to("given tolerance arg must be a number, but was <'foo'> (str)")


def test_is_not_close_to_negative_tolerance_failure():
    with pytest.raises(ValueError) as exc_info:
        assert_that(123.01).is_not_close_to(123, -1)
    assert_that(str(exc_info.value)).is_equal_to("given tolerance arg must not be negative")


def test_comparable_duck_typing():
    assert_that("b").is_greater_than("a")
    assert_that("a").is_less_than("b")
    assert_that("b").is_greater_than_or_equal_to("a")
    assert_that("b").is_greater_than_or_equal_to("b")
    assert_that("a").is_less_than_or_equal_to("b")
    assert_that("a").is_less_than_or_equal_to("a")


def test_comparable_duck_typing_custom_class():
    class Rank:
        def __init__(self, level):
            self.level = level

        def __lt__(self, other):
            return self.level < other.level

        def __le__(self, other):
            return self.level <= other.level

        def __gt__(self, other):
            return self.level > other.level

        def __ge__(self, other):
            return self.level >= other.level

        def __repr__(self):
            return f"Rank({self.level})"

    low = Rank(1)
    mid = Rank(5)
    high = Rank(10)

    assert_that(high).is_greater_than(low)
    assert_that(low).is_less_than(high)
    assert_that(mid).is_greater_than_or_equal_to(mid)
    assert_that(mid).is_less_than_or_equal_to(mid)


def test_comparable_duck_typing_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that("a").is_greater_than("b")
    assert_that(str(exc_info.value)).is_equal_to("Expected <a> to be greater than <b>, but was not.")


def test_comparable_no_ordering_failure():
    class NoOrder:
        pass

    with pytest.raises(TypeError) as exc_info:
        assert_that(NoOrder()).is_greater_than(NoOrder())
    # the repr of a local class carries its address, so the assertion is on the sentence around it
    message = str(exc_info.value)
    assert_that(message).starts_with("given other arg must be comparable with val <")
    assert_that(message).ends_with("(NoOrder)")


class _NumberWithNoOrder:
    """Registered as a real and converting to a float, and ordered against nothing."""

    def __float__(self) -> float:
        return 0.0

    def __repr__(self) -> str:
        return "<NumberWithNoOrder>"


numbers.Real.register(_NumberWithNoOrder)


@pytest.mark.parametrize(
    ("question", "arguments", "operand"),
    [
        ("is_between", (0, 9), "low"),
        ("is_not_between", (0, 9), "low"),
        ("is_close_to", (0, 1), "other"),
        ("is_not_close_to", (0, 1), "other"),
    ],
)
def test_a_range_over_a_pair_with_no_order_refuses_as_one_relation_does(question, arguments, operand):
    """The ordering engine's private `UnorderableError` reached the caller from these four, reading "pair".

    Not a `TypeError`, so `except TypeError` let it through, where 2.26.0 raised one.  The single relations
    refuse the same pair with this sentence, because they ask whether it orders before comparing.
    """
    with pytest.raises(TypeError) as caught:
        getattr(assert_that(_NumberWithNoOrder()), question)(*arguments)
    assert_that(str(caught.value)).is_equal_to(
        f"given {operand} arg must be comparable with val <<NumberWithNoOrder>> (_NumberWithNoOrder), but was <0> (int)"
    )


def test_bounds_with_no_order_between_them_are_refused_as_a_pair():
    with pytest.raises(TypeError) as caught:
        assert_that(5).is_between(_NumberWithNoOrder(), 9)
    assert_that(str(caught.value)).is_equal_to(
        "given high arg must be comparable with given low arg <<NumberWithNoOrder>> (_NumberWithNoOrder),"
        " but was <9> (int)"
    )


class _RealWithNoFloat:
    """Registered as a real number and offering no conversion to one."""


numbers.Real.register(_RealWithNoFloat)


def test_a_real_number_that_cannot_be_converted_is_no_infinity_and_no_match():
    assert_that(match.close_to(_RealWithNoFloat(), 1).matches(1)).is_false()


def test_a_float_conversion_of_their_own_that_raises_is_handed_on_by_a_match():
    with pytest.raises(OverflowError, match="my __float__ is broken"):
        match.close_to(_BrokenFloat(), 1).matches(1)


_HUGE = 10**400


@pytest.mark.parametrize(
    ("value", "other", "tolerance", "close"),
    [
        (math.inf, math.inf, 0, True),
        (-math.inf, -math.inf, 0, True),
        (decimal.Decimal("Infinity"), math.inf, 0, True),
        (math.inf, -math.inf, math.inf, False),
        (1, math.inf, math.inf, False),
        (_HUGE, decimal.Decimal("Infinity"), math.inf, False),
        (_HUGE, _HUGE * 10, math.inf, True),
        (1, 2, decimal.Decimal("Infinity"), True),
        (math.nan, 1, math.inf, False),
    ],
    ids=[
        "infinity-to-itself",
        "negative-infinity-to-itself",
        "a-decimal-infinity-to-a-float-one",
        "opposite-infinities",
        "a-finite-value-to-an-infinity",
        "a-bignum-to-an-infinity",
        "two-bignums",
        "a-finite-pair-under-a-decimal-infinity",
        "nan",
    ],
)
def test_an_infinity_is_close_only_to_itself_however_it_is_asked(value, other, tolerance, close):
    """An infinite tolerance covers every finite pair and no infinity: `1` was close to `inf` within `inf`."""
    for first, second in ((value, other), (other, value)):
        answers = {
            "is_close_to": assert_that(first).check().is_close_to(second, tolerance).passed,
            "is_not_close_to": not assert_that(first).check().is_not_close_to(second, tolerance).passed,
            "negated": not assert_that(first).check().not_.is_close_to(second, tolerance).passed,
            "matcher": match.close_to(second, tolerance).matches(first),
            "tolerance": assert_that(first).check().is_equal_to(second, tolerance=tolerance).passed,
        }
        assert_that(answers).described_as(f"{first!r} against {second!r}").is_equal_to(dict.fromkeys(answers, close))


def test_the_special_values_numpy_holds_are_read_as_themselves():
    """A `numpy.float32` is neither a `float` nor a `Decimal`: its infinity matched every finite value."""
    numpy = pytest.importorskip("numpy")
    infinity = numpy.float32("inf")
    assert_that(1).is_not_close_to(infinity, math.inf)
    assert_that(match.close_to(infinity, math.inf).matches(1)).is_false()
    assert_that(infinity).is_close_to(math.inf, 0)
    assert_that(match.close_to(1, numpy.float32("nan")).matches(1)).is_false()
    with pytest.raises(ValueError, match="NaN"):
        assert_that(1).is_close_to(1, numpy.float32("nan"))
    with pytest.raises(ValueError, match="NaN"):
        assert_that(1).is_equal_to(1, tolerance=numpy.float32("nan"))


class _EqualToEverything(float):
    """A finite float whose own equality calls it equal to anything, an infinity included."""

    def __eq__(self, other):
        return True

    __hash__ = float.__hash__


def test_an_infinity_is_classified_before_equality_is_asked():
    assert_that(_EqualToEverything(1.0)).is_not_close_to(math.inf, 1)
    assert_that(match.close_to(math.inf, 1).matches(_EqualToEverything(1.0))).is_false()


class _PastTheFloatRange:
    """A finite value past the float range: its conversion says infinity, and its own comparison does not."""

    def __float__(self):
        return math.inf

    def __eq__(self, other):
        return other is self

    __hash__ = object.__hash__


numbers.Real.register(_PastTheFloatRange)


def test_a_finite_value_the_conversion_overflows_is_no_infinity():
    assert_that(_PastTheFloatRange()).is_not_inf()
    held = _PastTheFloatRange()
    assert_that(match.close_to(held, 1).matches(held)).is_true()


def test_a_registered_number_with_no_arithmetic_is_close_to_nothing():
    """Inside the matcher's domain, and neither subtracted nor converted exactly, so no window forms around it."""
    assert_that(match.close_to(_NumberWithNoOrder(), 1).matches(1)).is_false()


def test_a_tolerance_over_a_pair_with_no_distance_leaves_the_answer_to_equality():
    """`is_equal_to(tolerance=)` let the ordering engine's private `UnorderableError` out on this pair."""
    with pytest.raises(AssertionError, match="to be equal to <0>"):
        assert_that(_NumberWithNoOrder()).is_equal_to(0, tolerance=1)


_CLOSENESS_SPELLINGS = {
    "is_close_to": lambda value, other, tolerance: assert_that(value).check().is_close_to(other, tolerance).passed,
    "is_not_close_to": lambda value, other, tolerance: (
        not assert_that(value).check().is_not_close_to(other, tolerance).passed
    ),
    "tolerance=": lambda value, other, tolerance: (
        assert_that(value).check().is_equal_to(other, tolerance=tolerance).passed
    ),
    "match.close_to": lambda value, other, tolerance: match.close_to(other, tolerance).matches(value),
}


@pytest.mark.parametrize("spelling", list(_CLOSENESS_SPELLINGS))
@pytest.mark.parametrize("int64_first", [True, False], ids=["int64-first", "decimal-first"])
@pytest.mark.parametrize(("tolerance", "within"), [(0, False), (4, True)], ids=["apart", "within"])
def test_a_pair_a_decimal_will_not_order_is_measured_by_its_difference(spelling, int64_first, tolerance, within):
    """`Decimal("1.5") == numpy.int64(5)` raises rather than answering, and so does ordering them that way round.

    The difference between them is exact, so every spelling answers from it: before, `is_equal_to(tolerance=)`
    let the private `UnorderableError` out, `is_close_to` over the `Decimal` a bare `TypeError`, and over the
    `numpy.int64` refused a pair it can measure.
    """
    numpy = pytest.importorskip("numpy")
    value, other = numpy.int64(5), decimal.Decimal("1.5")
    if not int64_first:
        value, other = other, value
    assert_that(_CLOSENESS_SPELLINGS[spelling](value, other, tolerance)).is_equal_to(within)


@pytest.mark.parametrize("spelling", list(_CLOSENESS_SPELLINGS))
@pytest.mark.parametrize("fraction_first", [True, False], ids=["fraction-first", "float-first"])
@pytest.mark.parametrize(("tolerance", "within"), [(0.5, False), (10**401, True)], ids=["apart", "within"])
def test_a_fraction_past_the_float_range_is_measured_against_a_float(spelling, fraction_first, tolerance, within):
    """`Fraction` converts to a `float` inside its own Python code to subtract one, and past the range that overflows.

    Read as a bug in the value, every spelling let the `OverflowError` out, where the exact difference answers.
    """
    value, other = fractions.Fraction(10**400, 3), 0.5
    if not fraction_first:
        value, other = other, value
    assert_that(_CLOSENESS_SPELLINGS[spelling](value, other, tolerance)).is_equal_to(within)


class _OverflowingFloat(float):
    """A `float` whose own subtraction overflows, which no exact measure is allowed to paper over."""

    def __sub__(self, other: object) -> float:
        raise OverflowError("my own subtraction overflows")

    def __rsub__(self, other: object) -> float:
        raise OverflowError("my own subtraction overflows")


class _OverflowingUnderAStandardName(float):
    """The same own overflow, from a function whose module claims the standard library's name."""

    __sub__ = types.FunctionType(_OverflowingFloat.__sub__.__code__, {"__name__": "numbers"})
    __rsub__ = types.FunctionType(_OverflowingFloat.__rsub__.__code__, {"__name__": "numbers"})


class _OverflowingInAStandardNamespace(float):
    """The same own overflow, from a function built over the standard library module's own namespace."""

    __sub__ = types.FunctionType(_OverflowingFloat.__sub__.__code__, vars(numbers))
    __rsub__ = types.FunctionType(_OverflowingFloat.__rsub__.__code__, vars(numbers))


class _HugeDistance:
    """What `_ReachingTheConversion` subtracts to: a distance whose own `abs()` runs the standard conversion."""

    numerator = 10**400
    denominator = 1
    __abs__ = numbers.Rational.__float__


class _ReachingTheConversion(float):
    """A `float` whose own subtraction hands back something that overflows in the standard conversion's code."""

    def __sub__(self, other: object) -> _HugeDistance:
        return _HugeDistance()


@pytest.mark.parametrize(
    "call",
    [
        lambda: assert_that(_OverflowingFloat(1.0)).is_close_to(3.0, 0.5),
        lambda: assert_that(_OverflowingFloat(1.0)).is_close_to(3, 0.5),
        lambda: assert_that(_OverflowingFloat(1.0)).is_close_to(fractions.Fraction(10**400, 3), 0.5),
        lambda: assert_that(3).is_close_to(_OverflowingFloat(1.0), 0.5),
        lambda: assert_that(_OverflowingFloat(1.0)).is_equal_to(fractions.Fraction(10**400, 3), tolerance=0.5),
        lambda: match.close_to(3, 0.5).matches(_OverflowingFloat(1.0)),
        lambda: match.close_to(_OverflowingFloat(1.0), 0.5).matches(fractions.Fraction(10**400, 3)),
        lambda: assert_that(_OverflowingUnderAStandardName(1.0)).is_close_to(fractions.Fraction(10**400, 3), 0.5),
        lambda: assert_that(_OverflowingInAStandardNamespace(1.0)).is_close_to(fractions.Fraction(10**400, 3), 0.5),
    ],
    ids=[
        "float",
        "int",
        "big-fraction",
        "int-first",
        "tolerance=",
        "matcher",
        "matcher-around-it",
        "spoofed-name",
        "spoofed-namespace",
    ],
)
def test_an_overflow_of_the_values_own_is_handed_on_beside_any_other_operand(call):
    """Only an overflow raised in the standard library's conversion is measured exactly instead.

    Deciding by the operands would have measured this one whenever a rational, an `int` included, sat beside it.
    """
    with pytest.raises(OverflowError, match="my own subtraction overflows"):
        call()


class _BorrowingFractionArithmetic(float):
    """A `float` that borrows `Fraction`'s own subtraction and the standard conversion, over a huge numerator."""

    numerator = 10**400
    denominator = 1
    __sub__ = fractions.Fraction.__sub__
    __float__ = numbers.Rational.__float__


def test_a_value_borrowing_fractions_own_code_is_still_handed_on():
    """Both code objects match, and the value converted is not a `Fraction`, so the overflow is its own."""
    with pytest.raises(OverflowError, match="too large for a float"):
        assert_that(_BorrowingFractionArithmetic(1.0)).is_close_to(0.5, 0.5)


def test_an_own_method_reaching_the_standard_conversion_is_still_handed_on():
    """The conversion's code alone is not enough: the operator that reached it has to be `Fraction`'s own."""
    with pytest.raises(OverflowError, match="too large for a float"):
        assert_that(_ReachingTheConversion(1.0)).is_close_to(fractions.Fraction(10**400, 3), 0.5)


_TINY = fractions.Fraction(1, 10**20)


@pytest.mark.parametrize("width", ["int8", "int64", "uint64"])
@pytest.mark.parametrize(
    ("ask", "holds"),
    [
        (lambda tiny, five: assert_that(tiny).check().is_less_than(five).passed, True),
        (lambda tiny, five: assert_that(tiny).check().is_greater_than(five).passed, False),
        (lambda tiny, five: assert_that(five).check().is_less_than_or_equal_to(tiny).passed, False),
        (lambda tiny, five: assert_that(1).check().is_between(tiny, five).passed, True),
        (lambda tiny, five: assert_that([tiny, five]).check().is_sorted().passed, True),
        (lambda tiny, five: assert_that([five, tiny]).check().is_sorted().passed, False),
        (lambda tiny, five: match.less_than(five).matches(tiny), True),
        (lambda tiny, five: assert_that(decimal.Decimal("0.1")).check().is_close_to(five, 1e-17).passed, False),
    ],
    ids=["less", "greater", "at-most-reversed", "between", "sorted", "unsorted", "matcher", "exact-window"],
)
def test_a_fraction_past_a_numpy_integers_width_is_ordered_by_exact_value(width, ask, holds):
    """`Fraction` orders against a `numpy` integer by multiplying its own denominator into the integer's width.

    That overflows inside `Fraction`'s own code, which read as a bug in the value, so every ordering let numpy's
    `OverflowError` out.  An exact closeness window around a `Decimal` is such a `Fraction`.
    """
    numpy = pytest.importorskip("numpy")
    five = getattr(numpy, width)(5)
    assert_that(ask(_TINY, five)).is_equal_to(holds)


def test_an_integral_class_is_kept_at_most_so_many_times(monkeypatch):
    """Found and answered past the bound, and not kept: classes made on the fly cannot grow the cache without end."""
    kept = set(range(256))
    monkeypatch.setattr(_ordering, "_INTEGRAL_KINDS", kept)
    counted = type("Counted", (int,), {})
    assert_that(_ordering.integral_kind(counted)).is_true()
    assert_that(kept).is_length(256)


def test_a_class_that_holds_no_number_is_read_once(monkeypatch):
    """Kept once found, and answered from there: read afresh, each side of every row of a failure cost 1.3 us."""
    kept: set[type] = set()
    monkeypatch.setattr(_ordering, "_UNREAD_KINDS", kept)
    plain = type("Plain", (), {})
    assert_that(_ordering.nan_operand(plain())).is_false()
    assert_that(kept).is_equal_to({plain})
    looked_up = []
    monkeypatch.setattr(_ordering, "_known_number_method", lambda *asked: looked_up.append(asked))
    assert_that(_ordering.nan_operand(plain())).is_false()
    assert_that(looked_up).is_empty()


def test_a_class_is_asked_for_its_method_once_at_its_first_reading(monkeypatch):
    """Asked a second time to decide whether to keep the class, a method that answers once raised out of a failure."""

    class AnswersOnce:
        asked = 0

        @property
        def __objclass__(self) -> None:
            type(self).asked += 1
            if type(self).asked > 1:
                raise RuntimeError("asked twice")

    class Plain:
        as_integer_ratio = AnswersOnce()

    monkeypatch.setattr(_ordering, "_UNREAD_KINDS", set())
    assert_that(_ordering.nan_operand(Plain())).is_false()
    assert_that(AnswersOnce.asked).is_equal_to(1)


@pytest.mark.parametrize(("held", "after"), [(255, 256), (256, 256)], ids=["room-for-one", "full"])
def test_a_class_that_holds_no_number_is_kept_at_most_so_many_times(monkeypatch, held, after):
    """Answered past the bound, and not kept: classes made on the fly cannot grow the cache without end."""
    kept = set(range(held))
    monkeypatch.setattr(_ordering, "_UNREAD_KINDS", kept)
    assert_that(_ordering.nan_operand(type("Plain", (), {})())).is_false()
    assert_that(kept).is_length(after)


def test_a_class_whose_numbers_are_read_is_never_kept(monkeypatch):
    """Not for a value of it that gave no exact value either: an infinity under an ordering of the class's own.

    Kept on that answer, the class would then call its NaN no NaN.
    """
    numpy = pytest.importorskip("numpy")

    class OrdersItself(numpy.float32):
        def __gt__(self, other: object) -> bool:
            return False

    kept: set[type] = set()
    monkeypatch.setattr(_ordering, "_UNREAD_KINDS", kept)
    for value, holds in [(numpy.float32("inf"), False), (OrdersItself("inf"), False), (OrdersItself("nan"), True)]:
        assert_that(_ordering.nan_operand(value)).is_equal_to(holds)
    assert_that(kept).is_empty()


class _OrderingOverflowsOfItsOwn(fractions.Fraction):
    """A `Fraction` whose own ordering overflows, which the exact order is not allowed to paper over."""

    def __lt__(self, other: object) -> bool:
        raise OverflowError("my own ordering overflows")

    __gt__ = __le__ = __ge__ = __lt__


class _BorrowingFractionOrdering(float):
    """A `float` that borrows `Fraction`'s own ordering and the code it runs, over a huge denominator."""

    _numerator = 1
    _denominator = 10**20
    __lt__ = fractions.Fraction.__lt__
    __gt__ = fractions.Fraction.__gt__
    _richcmp = vars(fractions.Fraction)["_richcmp"]


def test_an_ordering_overflow_of_the_values_own_is_handed_on():
    """Only `Fraction`'s own ordering running its own comparison, for a `Fraction`, is ordered exactly instead."""
    numpy = pytest.importorskip("numpy")
    with pytest.raises(OverflowError, match="my own ordering overflows"):
        assert_that(_OrderingOverflowsOfItsOwn(1, 3)).is_less_than(numpy.int64(5))


class _FractionOfItsOwn(fractions.Fraction):
    """A `Fraction` subclass, whose fields `Fraction`'s own code reads could be its own."""


def test_a_conversion_overflow_off_an_exact_fraction_is_still_handed_on():
    """The arithmetic's overflow is measured exactly for an exact `Fraction` only, as the ordering's is."""
    with pytest.raises(OverflowError, match="too large"):
        assert_that(_FractionOfItsOwn(10**400, 3)).is_close_to(0.5, 0.5)


@pytest.mark.parametrize(
    "value", [_BorrowingFractionOrdering(1.0), _FractionOfItsOwn(1, 10**20)], ids=["borrowed", "subclass"]
)
def test_an_ordering_overflow_off_an_exact_fraction_is_still_handed_on(value):
    """Both code objects match, but the value compared is no exact `Fraction`, so the overflow is left as it is."""
    numpy = pytest.importorskip("numpy")
    try:
        10**20 * numpy.int64(5)
    except OverflowError:
        pass
    else:
        pytest.skip("numpy before 2 widens the product rather than overflowing")
    # a `numpy` integer itself is read as the int it holds, so the width is kept by a subclass of one
    kept = type("Kept", (numpy.int64,), {})
    with pytest.raises(OverflowError):
        assert_that(value).is_less_than(kept(5))
    assert_that(value).is_less_than(numpy.int64(5))


@pytest.mark.parametrize("spelling", list(_CLOSENESS_SPELLINGS))
@pytest.mark.parametrize("scalar", ["int64", "float32"])
@pytest.mark.parametrize("scalar_first", [True, False], ids=["scalar-first", "bignum-first"])
@pytest.mark.parametrize(("tolerance", "within"), [(0.5, False), (10**401, True)], ids=["apart", "within"])
def test_a_numpy_scalar_against_a_bignum_is_measured(spelling, scalar, scalar_first, tolerance, within):
    """`numpy` converts a Python int past its own range and overflows, in `==`, `-` and `<` alike.

    The exact difference answers, where every spelling let the `OverflowError` out, and a `numpy.int64` goes
    into `Fraction` through `int`, since `Fraction` kept it as a fixed-width numerator that overflowed again.
    """
    numpy = pytest.importorskip("numpy")
    value, other = getattr(numpy, scalar)(5), 10**400
    if not scalar_first:
        value, other = other, value
    assert_that(_CLOSENESS_SPELLINGS[spelling](value, other, tolerance)).is_equal_to(within)


@pytest.mark.parametrize("spelling", list(_CLOSENESS_SPELLINGS))
@pytest.mark.parametrize(
    ("value", "tolerance"),
    [(0.5, decimal.Decimal("Infinity")), (-0.0, decimal.Decimal("Infinity")), (decimal.Decimal("1.5"), math.inf)],
)
@pytest.mark.parametrize("fraction_first", [False, True], ids=["fraction-second", "fraction-first"])
def test_an_infinite_tolerance_covers_a_pair_measured_exactly(spelling, value, tolerance, fraction_first):
    """The exact measure read the tolerance through `Fraction`, which refuses an infinity, and so measured nothing."""
    pair = [value, fractions.Fraction(10**400, 3)]
    if fraction_first:
        pair.reverse()
    assert_that(_CLOSENESS_SPELLINGS[spelling](*pair, tolerance)).is_true()


@pytest.mark.parametrize("spelling", list(_CLOSENESS_SPELLINGS))
@pytest.mark.parametrize(("value", "tolerance"), [("decimal", "float32"), ("float32", "decimal")])
@pytest.mark.parametrize("fraction_first", [False, True], ids=["fraction-second", "fraction-first"])
def test_an_infinite_tolerance_covers_a_numpy_pair_measured_exactly(spelling, value, tolerance, fraction_first):
    """A `numpy` infinity read as the ordering engine reads one, where `Fraction` refuses a `numpy` float."""
    numpy = pytest.importorskip("numpy")
    kinds = {
        "decimal": (decimal.Decimal("1.5"), decimal.Decimal("Infinity")),
        "float32": (numpy.float32(2), numpy.float32("inf")),
    }
    pair = [kinds[value][0], fractions.Fraction(10**400, 3)]
    if fraction_first:
        pair.reverse()
    assert_that(_CLOSENESS_SPELLINGS[spelling](*pair, kinds[tolerance][1])).is_true()


@pytest.mark.parametrize("spelling", list(_CLOSENESS_SPELLINGS))
def test_a_negative_infinite_numpy_tolerance_is_refused_in_every_spelling(spelling):
    """The matcher asks a `numpy` number's sign at construction too, which runs no code but `numpy`'s."""
    numpy = pytest.importorskip("numpy")
    with pytest.raises(ValueError, match="given tolerance arg must"):
        _CLOSENESS_SPELLINGS[spelling](decimal.Decimal("1.5"), fractions.Fraction(10**400, 3), numpy.float32("-inf"))


@pytest.mark.parametrize("tolerance", [-math.inf, decimal.Decimal("-Infinity")], ids=["float", "decimal"])
@pytest.mark.parametrize("spelling", list(_CLOSENESS_SPELLINGS))
def test_a_negative_infinite_tolerance_is_refused_in_every_spelling(spelling, tolerance):
    with pytest.raises(ValueError, match="given tolerance arg must"):
        _CLOSENESS_SPELLINGS[spelling](decimal.Decimal("1.5"), fractions.Fraction(10**400, 3), tolerance)


@pytest.mark.parametrize(
    ("tolerance", "within"),
    [
        (fractions.Fraction(1, 2), True),
        (fractions.Fraction(1, 2) - fractions.Fraction(1, 10**30), False),
        ("float32", True),
        ("float32-below", False),
    ],
    ids=["fraction", "fraction-below", "float32", "float32-below"],
)
@pytest.mark.parametrize("spelling", list(_CLOSENESS_SPELLINGS))
@pytest.mark.parametrize("fraction_first", [False, True], ids=["fraction-second", "fraction-first"])
def test_a_pair_its_arithmetic_refuses_is_within_a_tolerance_exactly_its_distance(
    spelling, tolerance, within, fraction_first
):
    """`Decimal` refuses to subtract a `Fraction`; a tolerance of exactly their distance holds it, one ulp less not."""
    if isinstance(tolerance, str):
        numpy = pytest.importorskip("numpy")
        half = numpy.float32(0.5)
        tolerance = half if tolerance == "float32" else numpy.nextafter(half, numpy.float32(0))
    pair = [decimal.Decimal("1.5"), fractions.Fraction(1)]
    if fraction_first:
        pair.reverse()
    assert_that(_CLOSENESS_SPELLINGS[spelling](*pair, tolerance)).is_equal_to(within)


@pytest.mark.parametrize(
    "nan",
    [math.nan, decimal.Decimal("NaN"), decimal.Decimal("sNaN"), "float32"],
    ids=["float", "decimal", "sNaN", "f32"],
)
def test_the_exact_measure_takes_no_nan_tolerance(nan):
    """Out of reach of the public spellings, which refuse a NaN tolerance or hold nothing within one."""
    if isinstance(nan, str):
        nan = pytest.importorskip("numpy").float32("nan")
    assert_that(_difference_within(decimal.Decimal("1.5"), fractions.Fraction(1), nan)).is_none()


_BIGNUM = 10**400


@pytest.mark.parametrize(
    ("question", "value", "other", "holds"),
    [
        ("less_than", "inf", _BIGNUM, False),
        ("greater_than", "inf", _BIGNUM, True),
        ("less_than", "1", _BIGNUM, True),
        ("greater_than", "1", -_BIGNUM, True),
        ("less_than", "-inf", -_BIGNUM, True),
        ("less_than_or_equal_to", _BIGNUM, "inf", True),
        ("greater_than", _BIGNUM, "1", True),
        ("less_than", "nan", _BIGNUM, False),
        ("greater_than_or_equal_to", "nan", _BIGNUM, False),
        ("less_than", _BIGNUM, "nan", False),
    ],
)
def test_a_numpy_float_against_a_bignum_is_ordered_by_its_exact_value(question, value, other, holds):
    """numpy 2 converts the Python int to a float to compare, which overflows, where numpy 1 answered.

    The engine orders the pair by the exact values both stand for: an infinity above every finite value, and
    a NaN against nothing.  Before, the assertion and the matcher let the `OverflowError` out.  Written as
    text, the `numpy.float32` side.
    """
    numpy = pytest.importorskip("numpy")
    value, other = (numpy.float32(side) if isinstance(side, str) else side for side in (value, other))
    with numpy.errstate(all="ignore"):
        assert_that(getattr(assert_that(value).check(), f"is_{question}")(other).passed).is_equal_to(holds)
        assert_that(getattr(match, question)(other).matches(value)).is_equal_to(holds)


def _ratio_raising(error: type[Exception]):
    def as_integer_ratio(self: object) -> tuple[int, int]:
        raise error("my own ratio refuses")

    return as_integer_ratio


@pytest.mark.parametrize(
    "as_integer_ratio",
    [None, _ratio_raising(OverflowError), _ratio_raising(ValueError), int.as_integer_ratio, "float32"],
    ids=[
        "none",
        "overflow-for-a-finite-value",
        "value-error-for-a-finite-value",
        "another-types-c-method",
        "another-numpy-types-method",
    ],
)
def test_an_overflow_with_no_trusted_exact_value_is_handed_on(as_integer_ratio):
    """No exact value, or one read from Python code that could call a finite value an infinity or a NaN."""
    numpy = pytest.importorskip("numpy", minversion="2", reason="numpy 1 turns the bignum into a float and answers")
    if as_integer_ratio == "float32":
        as_integer_ratio = numpy.float32.as_integer_ratio
    finite = type("Finite", (numpy.float64,), {"as_integer_ratio": as_integer_ratio})(1.0)
    with pytest.raises(OverflowError, match="too large"):
        assert_that(finite).is_less_than(_BIGNUM)


def _lying_through_the_instance(numpy):
    shadowed = type("Shadowed", (numpy.float64,), {})(1.0)
    shadowed.as_integer_ratio = _ratio_raising(OverflowError).__get__(shadowed)
    return shadowed


def _lying_through_attribute_lookup(numpy):
    def intercepting(self, name):
        if name == "as_integer_ratio":
            return _ratio_raising(OverflowError).__get__(self)
        return numpy.float64.__getattribute__(self, name)

    return type("Intercepting", (numpy.float64,), {"__getattribute__": intercepting})(1.0)


def _lying_about_its_sign(numpy, value=float("-inf")):
    return type("Signed", (numpy.float64,), {"__gt__": lambda self, other: True})(value)


@pytest.mark.parametrize(
    "build",
    [_lying_through_the_instance, _lying_through_attribute_lookup],
    ids=["instance-attribute", "getattribute"],
)
def test_a_finite_value_is_read_through_its_types_own_ratio(build):
    """The ratio is called as the type holds it, so neither the instance nor its lookup can call it infinite."""
    numpy = pytest.importorskip("numpy", minversion="2", reason="numpy 1 turns the bignum into a float and answers")
    assert_that(build(numpy)).is_less_than(_BIGNUM)


def test_a_finite_value_with_a_comparison_of_its_own_is_still_measured():
    """Its own `>` is only needed for an infinity's sign, so a finite value is ordered by its exact value."""
    numpy = pytest.importorskip("numpy", minversion="2", reason="numpy 1 turns the bignum into a float and answers")
    assert_that(_lying_about_its_sign(numpy, 1.0)).is_less_than(_BIGNUM)


def test_an_infinitys_sign_is_not_read_from_a_comparison_of_its_own():
    numpy = pytest.importorskip("numpy", minversion="2", reason="numpy 1 turns the bignum into a float and answers")
    with pytest.raises(OverflowError, match="too large"):
        assert_that(_lying_about_its_sign(numpy)).is_less_than(-_BIGNUM)


@pytest.mark.parametrize(("bound", "outcome"), [("inf", ValueError), ("nan", AssertionError)])
def test_a_numpy_float_bound_against_a_bignum_is_ordered(bound, outcome):
    """An infinite low bound sits above the bignum high one, and a NaN bound holds nothing between."""
    numpy = pytest.importorskip("numpy")
    with numpy.errstate(all="ignore"), pytest.raises(outcome):
        assert_that(-1).is_between(numpy.float32(bound), 10**401)
    with numpy.errstate(all="ignore"):
        assert_that(match.between(numpy.float32("-inf"), 10**401).matches(-1)).is_true()


class _ArrayShapedEqualityThatOverflows:
    """Shaped like an array for the guard in front of `==`, with an `__eq__` of its own that overflows."""

    __array__ = None

    def __eq__(self, other: object) -> bool:
        raise OverflowError("my own equality overflows")


def test_an_overflow_from_the_values_own_equality_is_handed_on_through_the_array_guard():
    with pytest.raises(OverflowError, match="my own equality overflows"):
        assert_that(_ArrayShapedEqualityThatOverflows()).is_equal_to(1, tolerance=0.5)


@pytest.mark.parametrize("width", ["float16", "float32"])
@pytest.mark.parametrize(
    "check",
    [
        lambda nan: assert_that([1.0, nan, 2.0]).check().is_sorted().passed,
        lambda nan: match.is_sorted().matches([1.0, nan, 2.0]),
        lambda nan: assert_that(decimal.Decimal("Infinity")).check().is_less_than(nan).passed,
        lambda nan: assert_that(decimal.Decimal(1)).check().is_greater_than_or_equal_to(nan).passed,
        lambda nan: assert_that(nan).check().is_less_than(decimal.Decimal(1)).passed,
        lambda nan: match.less_than(nan).matches(decimal.Decimal(1)),
        lambda nan: assert_that(decimal.Decimal(1)).check().is_between(nan, 10**401).passed,
    ],
    ids=["is_sorted", "match.is_sorted", "decimal-below", "decimal-at-least", "nan-below", "matcher", "between"],
)
def test_a_numpy_float_nan_is_unordered_as_a_float_one_is(width, check):
    """Not a `float`, so the NaN check read by type missed it.

    A sort holding it passed where one holding a `float` NaN fails, and a `Decimal` compared with it let
    `InvalidOperation` out where a `float` NaN is answered.
    """
    numpy = pytest.importorskip("numpy")
    with numpy.errstate(all="ignore"):
        assert_that(check(getattr(numpy, width)("nan"))).is_false()


_ASKED: list[str] = []


class _ClaimsNumpysModule:
    """A class of this file's own that claims `numpy`'s module, with a ratio that records being asked."""

    def as_integer_ratio(self) -> tuple[int, int]:
        _ASKED.append("as_integer_ratio")
        raise ValueError("claims to be a NaN")


_ClaimsNumpysModule.__module__ = "numpy"


class _Watching(type):
    def __getattribute__(cls, name: str) -> object:
        _ASKED.append(name)
        return super().__getattribute__(name)


class _WatchedKind(metaclass=_Watching):
    """A class whose metaclass records every attribute read off it."""


@pytest.mark.parametrize(
    ("value", "unasked"),
    [(_ClaimsNumpysModule(), "as_integer_ratio"), (_WatchedKind(), "__module__")],
    ids=["claimed-module", "metaclass"],
)
def test_a_nan_check_runs_no_code_of_the_values_own(value, unasked):
    """The module is read only off a class `type` built, and the ratio only as a `numpy` type holds it."""
    _ASKED.clear()
    assert_that(match.is_sorted().matches([value, value])).is_false()
    assert_that(_ASKED).does_not_contain(unasked)


@pytest.mark.parametrize("width", ["float16", "float32", "float64"])
@pytest.mark.parametrize("text", ["1", "inf", "-inf", "nan"])
@pytest.mark.parametrize("bignum", [10**400, -(10**400)], ids=["above", "below"])
@pytest.mark.parametrize("relation", ["le", "ge"])
def test_every_numpy_float_width_orders_against_a_bignum_as_python_does(width, text, bignum, relation):
    """A `float` against a Python int is exact in Python itself, which is the oracle for these numpy widths.

    On numpy 2 they overflow converting the int, and are ordered by their exact value, a NaN being caught
    before equality is asked of it; numpy 1 answers them itself.  A `longdouble` is left out: its own operator
    answers without overflowing, numpy 1 by refusing the pair and numpy 2 by turning the int into a
    `longdouble` with a warning, which is lossy where that type is a double, and the engine asks no further.
    """
    numpy = pytest.importorskip("numpy")
    value = getattr(numpy, width)(text)
    expected = getattr(operator, relation)(float(text), bignum)
    question = {"le": "is_less_than_or_equal_to", "ge": "is_greater_than_or_equal_to"}[relation]
    matcher = {"le": match.less_than_or_equal_to, "ge": match.greater_than_or_equal_to}[relation]
    with numpy.errstate(all="ignore"):
        assert_that(getattr(assert_that(value).check(), question)(bignum).passed).is_equal_to(expected)
        assert_that(matcher(bignum).matches(value)).is_equal_to(expected)


def test_a_nan_of_a_numpy_float_subclass_is_unordered_too():
    """A subclass carries its own module's name, so the NaN is read off the numpy type it inherits from."""
    numpy = pytest.importorskip("numpy")
    nan = type("Measured", (numpy.float32,), {})("nan")
    with numpy.errstate(all="ignore"):
        assert_that(assert_that([1.0, nan, 2.0]).check().is_sorted().passed).is_false()
        assert_that(assert_that(decimal.Decimal("Infinity")).check().is_less_than(nan).passed).is_false()
        assert_that(match.less_than(nan).matches(decimal.Decimal(1))).is_false()


def test_a_nan_beside_a_value_it_has_no_order_with_still_breaks_a_sort():
    """Asked only once the pair did not order, the NaN still answers before the pair is refused."""
    assert_that(assert_that([float("nan"), "a"]).check().is_sorted().passed).is_false()


def test_a_numpy_longdouble_nan_vouches_for_no_order_either():
    numpy = pytest.importorskip("numpy")
    nan = numpy.longdouble("nan")
    assert_that(assert_that([1.0, nan, 2.0]).check().is_sorted().passed).is_false()
    assert_that(match.is_sorted().matches([1.0, nan, 2.0])).is_false()


def test_a_pair_a_decimal_will_not_order_fails_as_an_assertion_rather_than_refusing():
    numpy = pytest.importorskip("numpy")
    message = r"^Expected <1.5> to be close to <5> within tolerance <0>, but was not\.$"
    with pytest.raises(AssertionError, match=message):
        assert_that(decimal.Decimal("1.5")).is_close_to(numpy.int64(5), 0)


_ORDER_SPELLINGS = {
    "is_less_than": lambda value, other: assert_that(value).check().is_less_than(other).passed,
    "is_less_than_or_equal_to": lambda value, other: assert_that(value).check().is_less_than_or_equal_to(other).passed,
    "is_greater_than": lambda value, other: assert_that(value).check().is_greater_than(other).passed,
    "is_greater_than_or_equal_to": lambda value, other: (
        assert_that(value).check().is_greater_than_or_equal_to(other).passed
    ),
    "is_between-low": lambda value, other: assert_that(value).check().is_between(other, 100).passed,
    "is_between-high": lambda value, other: assert_that(value).check().is_between(-100, other).passed,
    "is_not_between": lambda value, other: assert_that(value).check().is_not_between(other, 100).passed,
    "is_sorted": lambda value, other: assert_that([value, other]).check().is_sorted().passed,
    "match.less_than": lambda value, other: match.less_than(other).matches(value),
    "match.greater_than_or_equal_to": lambda value, other: match.greater_than_or_equal_to(other).matches(value),
    "match.between": lambda value, other: match.between(other, 100).matches(value),
    "match.is_sorted": lambda value, other: match.is_sorted().matches([value, other]),
}


@pytest.mark.parametrize("spelling", list(_ORDER_SPELLINGS))
@pytest.mark.parametrize("text", ["1.5", "5", "7"])
@pytest.mark.parametrize("decimal_first", [True, False], ids=["decimal-first", "int64-first"])
def test_a_decimal_against_a_numpy_integer_orders_as_against_the_int_it_holds(spelling, text, decimal_first):
    """The `Decimal` reads the integer's numerator, a `numpy` one, and refused a pair with an exact order."""
    numpy = pytest.importorskip("numpy")
    pair, stand_in = [decimal.Decimal(text), numpy.int64(5)], [decimal.Decimal(text), 5]
    if not decimal_first:
        pair.reverse()
        stand_in.reverse()
    assert_that(_ORDER_SPELLINGS[spelling](*pair)).is_equal_to(_ORDER_SPELLINGS[spelling](*stand_in))


_SEQUENCE_ORDER = {
    "is_less_than": lambda value, other: assert_that(value).check().is_less_than(other).passed,
    "is_greater_than_or_equal_to": lambda value, other: (
        assert_that(value).check().is_greater_than_or_equal_to(other).passed
    ),
    "is_sorted": lambda value, other: assert_that([value, other]).check().is_sorted().passed,
    "match.less_than": lambda value, other: match.less_than(other).matches(value),
}


@pytest.mark.parametrize("spelling", list(_SEQUENCE_ORDER))
@pytest.mark.parametrize("kind", [list, tuple])
@pytest.mark.parametrize(
    "built",
    [
        lambda number: ([decimal.Decimal(5), 1], [number]),
        lambda number: ([decimal.Decimal(5), 1], [number, 2]),
        lambda number: ([decimal.Decimal("1.5")], [number]),
        lambda number: ([decimal.Decimal(7), 0], [number, 9]),
        lambda number: ([[decimal.Decimal(5)], 2], [[number], 1]),
    ],
    ids=["longer", "later-element", "first-element", "first-element-above", "nested"],
)
@pytest.mark.parametrize("decimal_first", [True, False], ids=["decimal-first", "int64-first"])
def test_two_sequences_holding_a_decimal_against_a_numpy_integer_order_as_with_the_int(
    spelling, kind, built, decimal_first
):
    """The built-in order asks `==` of each pair and `<` of the first unequal one, where the `Decimal` raises."""
    numpy = pytest.importorskip("numpy")
    pair = [kind(side) for side in built(numpy.int64(5))]
    stand_in = [kind(side) for side in built(5)]
    if not decimal_first:
        pair.reverse()
        stand_in.reverse()
    assert_that(_SEQUENCE_ORDER[spelling](*pair)).is_equal_to(_SEQUENCE_ORDER[spelling](*stand_in))


@pytest.mark.parametrize(
    ("value", "other", "less", "at_least"),
    [
        ([decimal.Decimal("NaN")], [1], False, False),
        ([decimal.Decimal("sNaN")], [1], False, False),
        ([1, decimal.Decimal("NaN")], [1, 2], False, False),
        ([1, decimal.Decimal("NaN")], [0, 2], False, True),
        ((1, decimal.Decimal("NaN")), (2, 0), True, False),
    ],
)
def test_a_decimal_nan_inside_a_sequence_orders_it_as_a_nan_does(value, other, less, at_least):
    """Python's own `<` lets the signal out; the first unequal pair decides, and a NaN there orders neither way."""
    assert_that(assert_that(value).check().is_less_than(other).passed).is_equal_to(less)
    assert_that(assert_that(value).check().is_greater_than_or_equal_to(other).passed).is_equal_to(at_least)


_EXACT_SPELLINGS = {
    **{name: _ORDER_SPELLINGS[name] for name in ("is_less_than", "is_greater_than_or_equal_to", "is_sorted")},
    "is_equal_to": lambda value, other: assert_that(value).check().is_equal_to(other).passed,
    "is_not_equal_to": lambda value, other: assert_that(value).check().is_not_equal_to(other).passed,
    "contains": lambda value, other: assert_that([value]).check().contains(other).passed,
    "set-contains": lambda value, other: assert_that({value}).check().contains(other).passed,
    "match.equal_to": lambda value, other: match.equal_to(other).matches(value),
}


@pytest.mark.parametrize(
    "text", ["1.5", "5", "-7", "0", "-128", "255", "18446744073709551615", "Infinity", "-Infinity", "NaN", "sNaN"]
)
@pytest.mark.parametrize(
    ("width", "held"),
    [("int8", -128), ("uint8", 255), ("int16", 0), ("int64", -(2**63)), ("int64", 5), ("uint64", 2**64 - 1)],
)
@pytest.mark.parametrize("decimal_first", [True, False], ids=["decimal-first", "integer-first"])
def test_a_decimal_against_every_numpy_integer_width_answers_as_against_the_int_it_holds(
    text, width, held, decimal_first
):
    """A `Decimal("sNaN")` refuses to go into a set on either side, so that one spelling is not asked of it."""
    numpy = pytest.importorskip("numpy")
    pair, stand_in = [decimal.Decimal(text), getattr(numpy, width)(held)], [decimal.Decimal(text), held]
    if not decimal_first:
        pair.reverse()
        stand_in.reverse()
    asked = [name for name in _EXACT_SPELLINGS if not (name == "set-contains" and text == "sNaN" and decimal_first)]
    answers = {name: _EXACT_SPELLINGS[name](*pair) for name in asked}
    assert_that(answers).is_equal_to({name: _EXACT_SPELLINGS[name](*stand_in) for name in asked})


class _EqualityThatRaises:
    """Registered as a real and converting to a float, with an `__eq__` of its own that raises."""

    def __float__(self) -> float:
        return 1.0

    def __eq__(self, other: object) -> bool:
        raise TypeError("my __eq__ is broken")


numbers.Real.register(_EqualityThatRaises)


def test_closeness_hands_on_an_error_from_the_values_own_equality():
    """An operator refusing the pair leaves equality unknown, where the value's own `__eq__` raising is a bug."""
    with pytest.raises(TypeError, match="my __eq__ is broken"):
        assert_that(_EqualityThatRaises()).is_close_to(1, 1)


class _OrderedAgainstIntsOnly:
    """A registered real standing for five, ordered against an `int` and against nothing else."""

    def __float__(self) -> float:
        return 5.0

    def __lt__(self, other: object) -> bool:
        return 5 < other if type(other) is int else NotImplemented

    def __gt__(self, other: object) -> bool:
        return 5 > other if type(other) is int else NotImplemented

    def __repr__(self) -> str:
        return "<OrderedAgainstIntsOnly>"


numbers.Real.register(_OrderedAgainstIntsOnly)


def test_the_bound_a_range_never_reaches_is_never_asked():
    """Below the low bound the answer is known, so a high bound the value cannot be ordered against is not asked.

    Refused up front, it turned this passing `is_not_between` into a `TypeError`, where 2.26.0's chained
    comparison answered.
    """
    assert_that(_OrderedAgainstIntsOnly()).is_not_between(10, 20.5)
    with pytest.raises(AssertionError) as caught:
        assert_that(_OrderedAgainstIntsOnly()).is_between(10, 20.5)
    assert_that(str(caught.value)).is_equal_to(
        "Expected <<OrderedAgainstIntsOnly>> to be between <10> and <20.5>, but was not."
    )


_FINER_THAN_ITS_CONTEXT = decimal.Decimal("8.6999999999999999555910790149937383830547332763671875")


@pytest.mark.parametrize(
    ("value", "other", "tolerance"),
    [
        (-1.1, -0.9, 0.2),
        (-0.9, -1.1, 0.2),
        (1, -0.4, 1.4),
        (-0.4, 1, 1.4),
        (0.7, _FINER_THAN_ITS_CONTEXT, 8),
        (_FINER_THAN_ITS_CONTEXT, 0.7, 8),
    ],
    ids=["value-below", "value-above", "only-the-difference", "only-the-difference-swapped", "exact", "exact-swapped"],
)
def test_a_distance_the_floats_round_past_the_tolerance_is_within_it_every_way_it_is_asked(value, other, tolerance):
    """Each pair is within its tolerance by one measure alone.

    `-1.1` and `-0.9` differ by `0.20000000000000007` as floats. `1 - -0.4` rounds to exactly `1.4`, while both
    windows round the other operand out by one ulp. The `Decimal` is exactly `Decimal(0.7) + 8`, and its window
    rounds to 28 digits and the float's to 53 bits, both past `0.7`, so only the exact difference holds.
    """
    assert_that(value).is_close_to(other, tolerance)
    assert_that(match.close_to(other, tolerance).matches(value)).is_true()
    assert_that(value).is_equal_to(other, tolerance=tolerance)


@pytest.mark.parametrize(
    ("value", "other", "tolerance"),
    [(1, -1, 1), (decimal.Decimal(-1), 1.0, 0.5)],
    ids=["ints", "a-decimal-against-a-float"],
)
def test_a_value_is_not_close_to_its_own_negation(value, other, tolerance):
    assert_that(value).is_not_close_to(other, tolerance)
    assert_that(match.close_to(other, tolerance).matches(value)).is_false()


class _FloatsToNan:
    """A registered number whose float is NaN while its own equality calls it one."""

    def __float__(self):
        return math.nan

    def __eq__(self, other):
        return other == 1

    __hash__ = None


numbers.Number.register(_FloatsToNan)


def test_a_value_that_converts_to_nan_is_close_to_nothing_whatever_its_equality_says():
    """The assertion converted it to find the NaN, and the matcher asked its equality."""
    with pytest.raises(AssertionError):
        assert_that(_FloatsToNan()).is_close_to(1, 0.5)
    assert_that(match.close_to(1, 0.5).matches(_FloatsToNan())).is_false()


def test_a_tolerance_only_widens_what_equality_already_holds():
    """`tolerance=` asks `==` first, so a pair `==` accepts stays equal, whatever the measure would say."""
    assert_that(_FloatsToNan()).is_equal_to(1)
    assert_that(_FloatsToNan()).is_equal_to(1, tolerance=0.5)


@pytest.mark.parametrize(
    "call",
    [lambda: assert_that(0).is_close_to(10**400, 10**400), lambda: assert_that(0).is_equal_to(1, tolerance=10**400)],
    ids=["is_close_to", "tolerance"],
)
def test_a_tolerance_past_the_float_range_is_a_tolerance(call):
    """Asked whether it was a NaN as a float, it raised `OverflowError` instead of measuring."""
    call()


@pytest.mark.parametrize("question", ["is_close_to", "is_not_close_to"])
def test_a_window_bound_the_value_cannot_be_ordered_against_is_refused_under_other(question):
    """The window is `other` plus and minus the tolerance, and it is those the value is ordered against.

    Checking `other` alone passed here, `10` being an `int`, and the float bounds let the engine's own
    error out.
    """
    with pytest.raises(TypeError) as caught:
        getattr(assert_that(_OrderedAgainstIntsOnly()), question)(10, 0.5)
    assert_that(str(caught.value)).is_equal_to(
        "given other arg must be comparable with val <<OrderedAgainstIntsOnly>> (_OrderedAgainstIntsOnly),"
        " but was <10> (int)"
    )


@pytest.mark.parametrize("value", ["a", b"a", [1], (1,), {"a": 1}], ids=["str", "bytes", "list", "tuple", "dict"])
def test_a_nan_on_the_right_does_not_make_an_unorderable_pair_a_verdict(value):
    """Answered before the pair was tried, a NaN turned "these cannot be compared" into "it was not".

    `assert_that("a").is_less_than(1)` refuses the operands; with a NaN in its place the same pair
    reported a failed comparison, which says a comparison happened.
    """
    with pytest.raises(TypeError) as caught:
        assert_that(value).is_less_than(float("nan"))
    assert_that(str(caught.value)).starts_with("given other arg must be comparable with val <")


def test_a_decimal_nan_still_answers_rather_than_signalling():
    """It signals instead of answering, which is why the pre-check existed: the answer is still neither."""
    with pytest.raises(AssertionError) as caught:
        assert_that(decimal.Decimal(1)).is_less_than(decimal.Decimal("NaN"))
    assert_that(str(caught.value)).is_equal_to("Expected <1> to be less than <NaN>, but was not.")

    with pytest.raises(AssertionError) as caught:
        assert_that(decimal.Decimal("NaN")).is_greater_than(decimal.Decimal(1))
    assert_that(str(caught.value)).is_equal_to("Expected <NaN> to be greater than <1>, but was not.")


def test_a_nan_is_absorbed_however_deep_the_signal_comes_from():
    """The operands decide, not the traceback: `Decimal` signals from one frame or from four.

    Measured, the C accelerator raises at the comparison site and `_pydecimal` raises four frames in,
    so reading the depth answered which interpreter build was running rather than what was compared.
    CI found it on a build this machine does not have.
    """

    class Deeply(decimal.Decimal):
        def __lt__(self, other):
            return self._signal()

        def __gt__(self, other):
            return self._signal()

        def _signal(self):
            return decimal.Decimal("NaN") < decimal.Decimal(1)

    with pytest.raises(AssertionError) as caught:
        assert_that(Deeply("NaN")).is_less_than(decimal.Decimal(1))
    assert_that(str(caught.value)).starts_with("Expected <NaN> to be less than <1>")


def test_a_subclass_does_not_decide_whether_its_own_signal_is_a_verdict():
    """It is not a NaN, and saying so must not turn its own `InvalidOperation` into a failed comparison."""

    class Liar(decimal.Decimal):
        def is_nan(self):
            return True

        def __lt__(self, other):
            raise decimal.InvalidOperation("own comparison failed")

        def __gt__(self, other):
            raise decimal.InvalidOperation("own comparison failed")

    with pytest.raises(decimal.InvalidOperation, match="own comparison failed"):
        assert_that(Liar(1)).is_less_than(decimal.Decimal(2))


def test_a_subclass_cannot_hide_that_it_is_a_nan():
    """The other direction: a real NaN saying it is not must still answer rather than signal."""

    class Hidden(decimal.Decimal):
        def is_nan(self):
            return False

    with pytest.raises(AssertionError) as caught:
        assert_that(Hidden("NaN")).is_less_than(decimal.Decimal(2))
    assert_that(str(caught.value)).starts_with("Expected <NaN> to be less than <2>")


def test_a_float_subclass_does_not_call_itself_unordered():
    """`value != value` is the NaN test, and a subclass owning `__ne__` owned the answer with it."""

    class Contrary(float):
        def __ne__(self, other):
            return True

        def __hash__(self):
            return 0

    assert_that([Contrary(1.0), 2.0]).is_sorted()
    with pytest.raises(AssertionError):
        assert_that([2.0, Contrary(1.0)]).is_sorted()


def test_a_subclass_saying_it_is_a_nan_does_not_change_a_tolerance_verdict():
    """The same lie in the other helper: it turned a passing `is_close_to` into a failure."""

    class Liar(decimal.Decimal):
        def is_nan(self):
            return True

    assert_that(Liar(1)).is_close_to(decimal.Decimal(1), decimal.Decimal("0.1"))
    assert_that(decimal.Decimal("NaN")).is_not_close_to(decimal.Decimal(1), decimal.Decimal("0.1"))


def test_a_signal_raised_inside_their_own_comparison_travels_out():
    """A bug in the value, not a pair without an order: answering it would send the reader elsewhere."""

    class Signalling(decimal.Decimal):
        def __lt__(self, other):
            raise decimal.InvalidOperation("from my own __lt__")

        def __gt__(self, other):
            raise decimal.InvalidOperation("from my own __gt__")

    with pytest.raises(decimal.InvalidOperation, match="from my own"):
        assert_that(Signalling(1)).is_less_than(decimal.Decimal(2))


def test_is_even():
    assert_that(0).is_even()
    assert_that(2).is_even()
    assert_that(-4).is_even()
    assert_that(1000000).is_even()


def test_is_even_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(1).is_even()
    assert_that(str(exc_info.value)).is_equal_to("Expected <1> to be even, but was not.")


def test_is_even_negative_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(-3).is_even()
    assert_that(str(exc_info.value)).is_equal_to("Expected <-3> to be even, but was not.")


def test_is_even_bad_type_float_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(2.0).is_even()
    assert_that(str(exc_info.value)).is_equal_to("val must be an integer, but was <2.0> (float)")


def test_is_even_bad_type_str_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that("foo").is_even()
    assert_that(str(exc_info.value)).is_equal_to("val must be an integer, but was <'foo'> (str)")


def test_is_even_bad_type_bool_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(True).is_even()
    assert_that(str(exc_info.value)).is_equal_to("val must be an integer, but was <True> (bool)")


def test_is_odd():
    assert_that(1).is_odd()
    assert_that(3).is_odd()
    assert_that(-5).is_odd()
    assert_that(999999).is_odd()


def test_is_odd_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(0).is_odd()
    assert_that(str(exc_info.value)).is_equal_to("Expected <0> to be odd, but was not.")


def test_is_odd_negative_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(-4).is_odd()
    assert_that(str(exc_info.value)).is_equal_to("Expected <-4> to be odd, but was not.")


def test_is_odd_bad_type_float_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(1.0).is_odd()
    assert_that(str(exc_info.value)).is_equal_to("val must be an integer, but was <1.0> (float)")


def test_is_odd_bad_type_bool_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(False).is_odd()
    assert_that(str(exc_info.value)).is_equal_to("val must be an integer, but was <False> (bool)")


def test_is_divisible_by():
    assert_that(10).is_divisible_by(5)
    assert_that(10).is_divisible_by(2)
    assert_that(10).is_divisible_by(1)
    assert_that(0).is_divisible_by(7)
    assert_that(-12).is_divisible_by(3)
    assert_that(12).is_divisible_by(-3)


def test_is_divisible_by_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(10).is_divisible_by(3)
    assert_that(str(exc_info.value)).is_equal_to("Expected <10> to be divisible by <3>, but was not.")


def test_is_divisible_by_bad_type_float_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(10.0).is_divisible_by(5)
    assert_that(str(exc_info.value)).is_equal_to("val must be an integer, but was <10.0> (float)")


def test_is_divisible_by_bad_divisor_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(10).is_divisible_by(2.5)
    assert_that(str(exc_info.value)).is_equal_to("given divisor arg must be an integer, but was <2.5> (float)")


def test_is_divisible_by_bad_divisor_bool_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(10).is_divisible_by(True)
    assert_that(str(exc_info.value)).is_equal_to("given divisor arg must be an integer, but was <True> (bool)")


def test_is_divisible_by_zero_divisor_failure():
    with pytest.raises(ValueError) as exc_info:
        assert_that(10).is_divisible_by(0)
    assert_that(str(exc_info.value)).is_equal_to("given divisor arg must not be zero")


def test_chaining():
    assert_that(123).is_greater_than(100).is_less_than(1000).is_between(120, 125).is_close_to(100, 25)


def test_chaining_even_odd():
    assert_that(4).is_even().is_positive().is_divisible_by(2)
    assert_that(3).is_odd().is_positive()


def test_is_between_boundary_inclusive():
    assert_that(5).is_between(5, 10)
    assert_that(10).is_between(5, 10)


def test_is_not_between_boundary_fails():
    with pytest.raises(AssertionError):
        assert_that(5).is_not_between(5, 10)
    with pytest.raises(AssertionError):
        assert_that(10).is_not_between(5, 10)


def test_is_close_to_boundary_inclusive():
    assert_that(10).is_close_to(8, 2)
    assert_that(6).is_close_to(8, 2)


def test_is_not_close_to_boundary_fails():
    with pytest.raises(AssertionError):
        assert_that(10).is_not_close_to(8, 2)
    with pytest.raises(AssertionError):
        assert_that(6).is_not_close_to(8, 2)


def test_is_divisible_by_negative_divisor():
    assert_that(9).is_divisible_by(-3)
    with pytest.raises(AssertionError):
        assert_that(10).is_divisible_by(-3)


_BROADCAST_ORDER = {
    "is_less_than": lambda sequence, number: assert_that(sequence).check().is_less_than(number).passed,
    "is_greater_than_or_equal_to": lambda sequence, number: (
        assert_that(sequence).check().is_greater_than_or_equal_to(number).passed
    ),
    "is_less_than-swapped": lambda sequence, number: assert_that(number).check().is_less_than(sequence).passed,
    "is_between": lambda sequence, number: assert_that(sequence).check().is_between(number, number + 9).passed,
    "is_sorted": lambda sequence, number: assert_that([sequence, number]).check().is_sorted().passed,
    "match.less_than": lambda sequence, number: match.less_than(number).matches(sequence),
    "match.between": lambda sequence, number: match.between(number, number + 9).matches(sequence),
}


def _order_outcome(asked, sequence, number) -> object:
    """The verdict, or the refusal's type and sentence with the number's own spelling taken out."""
    try:
        return asked(sequence, number)
    except TypeError as refusal:
        said = re.sub(r"np\.(?:int|float)64\(([\d.]+)\)", r"\1", str(refusal))
        return type(refusal), re.sub(r"\((?:numpy\.)?(?:int|float)(?:64)?\)", "", said)


@pytest.mark.parametrize("asked", list(_BROADCAST_ORDER))
@pytest.mark.parametrize("sequence", [[5], (5,), [5, 6]], ids=["one-element", "tuple", "two-elements"])
@pytest.mark.parametrize("kind", ["int64", "float64"])
def test_a_list_against_a_numpy_scalar_is_unordered_as_against_the_int_it_holds(asked, sequence, kind):
    """`numpy` answered an array for the pair, true for one element and raising for several; a number and a
    list have no order, and each spelling refuses or fails the pair as it does the Python number's.
    """
    numpy = pytest.importorskip("numpy")
    scalar = getattr(numpy, kind)(6)
    expected = _order_outcome(_BROADCAST_ORDER[asked], sequence, scalar.item())
    assert_that(_order_outcome(_BROADCAST_ORDER[asked], sequence, scalar)).is_equal_to(expected)


@pytest.mark.parametrize("asked", list(_BROADCAST_ORDER))
@pytest.mark.parametrize(
    "sequence",
    [[[5], [5, 6]], [decimal.Decimal("NaN")], [decimal.Decimal("sNaN")]],
    ids=["ragged", "decimal-nan", "signalling-nan"],
)
@pytest.mark.parametrize("kind", ["int64", "float64"])
def test_a_list_numpy_cannot_order_against_a_numpy_scalar_is_unordered_as_against_the_int(asked, sequence, kind):
    """`numpy` raised from the comparison itself: `ValueError` building a ragged list's array, and the NaN's
    signal where it ordered the element against the scalar.
    """
    numpy = pytest.importorskip("numpy")
    scalar = getattr(numpy, kind)(6)
    expected = _order_outcome(_BROADCAST_ORDER[asked], sequence, scalar.item())
    assert_that(_order_outcome(_BROADCAST_ORDER[asked], sequence, scalar)).is_equal_to(expected)


class _NeverLess(list):
    """A list whose own `<` answers `False`, so the reverse comparison is `numpy`'s."""

    def __lt__(self, other: object) -> bool:
        return False


@pytest.mark.parametrize("kind", ["int64", "float64"])
def test_the_reverse_comparison_of_a_list_against_a_numpy_scalar_is_asked_as_the_first_is(kind):
    """`numpy.float64(6) < _NeverLess([5])` broadcast, where the first comparison had answered a plain bool."""
    numpy = pytest.importorskip("numpy")
    with pytest.raises(TypeError, match="must be comparable"):
        assert_that(_NeverLess([5])).is_greater_than(getattr(numpy, kind)(6))


class _DecliningOrder(list):
    """A list whose own `<` and `>` decline every operand, leaving the order to the other side's."""

    def __lt__(self, other: object) -> object:
        return NotImplemented

    def __gt__(self, other: object) -> object:
        return NotImplemented


@pytest.mark.parametrize("asked", list(_BROADCAST_ORDER))
@pytest.mark.parametrize("held", [[5], [5, 6]], ids=["one-element", "two-elements"])
def test_a_list_whose_own_order_declined_a_numpy_scalar_is_unordered_as_against_the_int(asked, held):
    numpy = pytest.importorskip("numpy")
    sequence = _DecliningOrder(held)
    expected = _order_outcome(_BROADCAST_ORDER[asked], sequence, 6)
    assert_that(_order_outcome(_BROADCAST_ORDER[asked], sequence, numpy.int64(6))).is_equal_to(expected)


@pytest.mark.parametrize("written", ["__lt__", "__gt__"])
def test_a_numpy_scalar_that_wrote_one_order_is_unordered_against_a_list_by_the_one_numpy_wrote(written):
    """Its own operator answers `False`, and the one inherited from `numpy` broadcasts over the two elements."""
    numpy = pytest.importorskip("numpy")
    scalar = type("Written", (numpy.int64,), {written: lambda self, other: False, "__hash__": numpy.int64.__hash__})
    with pytest.raises(TypeError, match="must be comparable"):
        assert_that([5, 6]).is_greater_than(scalar(6))


def test_two_lists_whose_own_order_raised_on_a_numpy_scalar_are_ordered_as_the_int_is():
    """`numpy`'s array for the first pair had no truth, and the pairs are asked one by one."""
    numpy = pytest.importorskip("numpy")

    def asked(sequence: list[object], number: object) -> bool:
        return assert_that([number]).check().is_less_than(sequence).passed

    assert_that(_order_outcome(asked, [[5, 6]], numpy.int64(5))).is_equal_to(_order_outcome(asked, [[5, 6]], 5))


_DURATIONS_CLOSE = {
    "seconds": (((5, "s"), (6, "s"), (2, "s")), True),
    "seconds-far": (((5, "s"), (9, "s"), (2, "s")), False),
    "mixed-units": (((5, "s"), (5500, "ms"), (1, "s")), True),
    "days-tolerance": (((5, "h"), (6, "h"), (1, "D")), True),
    "not-a-time-value": ((("NaT", "s"), (6, "s"), (2, "s")), False),
    "not-a-time-tolerance": (((5, "s"), (6, "s"), ("NaT", "s")), False),
}


@pytest.mark.parametrize("spelling", list(_CLOSENESS_SPELLINGS))
@pytest.mark.parametrize("case", list(_DURATIONS_CLOSE))
def test_a_numpy_duration_is_measured_against_another_in_every_spelling(spelling, case):
    """Signed against a zero of its own unit: against a bare `0`, numpy 2 warned that a bare int has no unit."""
    numpy = pytest.importorskip("numpy")
    operands, close = _DURATIONS_CLOSE[case]
    value, other, tolerance = (numpy.timedelta64(*operand) for operand in operands)
    assert_that(_CLOSENESS_SPELLINGS[spelling](value, other, tolerance)).is_equal_to(close)


@pytest.mark.parametrize("spelling", list(_CLOSENESS_SPELLINGS))
def test_a_negative_numpy_duration_tolerance_is_refused_in_every_spelling(spelling):
    numpy = pytest.importorskip("numpy")
    with pytest.raises(ValueError, match="given tolerance arg must"):
        _CLOSENESS_SPELLINGS[spelling](numpy.timedelta64(5, "s"), numpy.timedelta64(6, "s"), numpy.timedelta64(-2, "s"))


_MIXED_WITH_A_DURATION = {
    "duration-tolerance": (lambda second: (1, 1.5, second), "given tolerance arg must be a number, to match val"),
    "duration-other": (lambda second: (1, second, 1), "given other arg must be a number, to match val"),
    "duration-value": (lambda second: (second, second, 1), "given tolerance arg must be a numpy timedelta64"),
}


@pytest.mark.parametrize("spelling", ["is_close_to", "is_not_close_to"])
@pytest.mark.parametrize("mixed", list(_MIXED_WITH_A_DURATION))
def test_an_assertion_refuses_a_numpy_duration_measured_against_a_number(spelling, mixed):
    """numpy registers a duration as an integer, and a number within one second has no meaning."""
    numpy = pytest.importorskip("numpy")
    operands, refusal = _MIXED_WITH_A_DURATION[mixed]
    with pytest.raises(TypeError, match=refusal):
        _CLOSENESS_SPELLINGS[spelling](*operands(numpy.timedelta64(1, "s")))


@pytest.mark.parametrize("mixed", list(_MIXED_WITH_A_DURATION))
def test_a_matcher_measures_nothing_between_a_numpy_duration_and_a_number(mixed):
    numpy = pytest.importorskip("numpy")
    value, other, tolerance = _MIXED_WITH_A_DURATION[mixed][0](numpy.timedelta64(1, "s"))
    assert_that(_CLOSENESS_SPELLINGS["match.close_to"](value, other, tolerance)).is_false()


def test_a_tolerance_leaves_a_leaf_of_the_other_kind_to_equality():
    """A duration tolerance measures no number, and a number measures no duration, as a string is not measured."""
    numpy = pytest.importorskip("numpy")
    second = numpy.timedelta64(1, "s")
    assert_that(assert_that({"a": 1}).check().is_equal_to({"a": 1.5}, tolerance=second).passed).is_false()
    assert_that(assert_that({"a": 1}).check().is_equal_to({"a": 1}, tolerance=second).passed).is_true()
    durations = {"a": numpy.timedelta64(5, "s")}, {"a": numpy.timedelta64(6, "s")}
    assert_that(assert_that(durations[0]).check().is_equal_to(durations[1], tolerance=2).passed).is_false()


def test_a_between_matcher_refuses_reversed_numpy_duration_bounds_when_built():
    numpy = pytest.importorskip("numpy")
    with pytest.raises(ValueError, match="given low arg must be less than given high arg"):
        match.between(numpy.timedelta64(5, "s"), numpy.timedelta64(1, "s"))
    assert_that(
        match.between(numpy.timedelta64(1, "s"), numpy.timedelta64(5, "m")).matches(numpy.timedelta64(3, "s"))
    ).is_true()


@pytest.mark.parametrize("duration_low", [True, False], ids=["duration-low", "duration-high"])
def test_a_between_matcher_does_not_order_a_numpy_duration_against_a_number_when_built(duration_low):
    """Asked, numpy 2 warns that a bare int has no unit, and the suite's warnings are errors."""
    numpy = pytest.importorskip("numpy")
    bounds = (numpy.timedelta64(5, "s"), 1) if duration_low else (1, numpy.timedelta64(5, "s"))
    assert_that(match.between(*bounds).describe()).starts_with("a value between")
