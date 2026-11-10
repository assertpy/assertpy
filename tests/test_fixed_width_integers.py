"""A `numpy` integer is measured and ordered as the int it holds.

Fixed in width, its own arithmetic wraps: ``uint8(3) - 250`` is ``9`` and a warning.  Closeness and order taken
through that arithmetic called a pixel of 3 close to 250 within 10, and a third less than ``-2**62``.  Every answer
here is held to Python's own integers and fractions.  A `numpy` float standing beside such an integer is read as the
float it holds, or the integer read as an `int` would be rounded to the float's width.  Two integers, of `numpy` or
of Python, are close by their exact difference alone.  The warning is silenced for this module, so a wrong verdict
fails a test by its assertion, and one class of tests records warnings and holds the list empty.
"""

from __future__ import annotations

import decimal
import fractions
import itertools
import numbers
import warnings

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

from assertpy import AssertionFailure, assert_that, match
from assertpy._engine import _compare, _ordering
from assertpy._engine._ordering import numpy_float, python_numbers, unwrapped
from tests.optional import needs

numpy = needs("numpy")
pytestmark = pytest.mark.filterwarnings("ignore:overflow encountered:RuntimeWarning")

_FLOAT_KINDS = (numpy.float16, numpy.float32, numpy.float64)

_KINDS = (
    numpy.int8,
    numpy.int16,
    numpy.int32,
    numpy.int64,
    numpy.uint8,
    numpy.uint16,
    numpy.uint32,
    numpy.uint64,
)


def _passes(check) -> bool:
    try:
        check()
    except AssertionFailure:
        return False
    return True


def _met(monkeypatch, plain: set[type], fixed: dict[type, object] | None = None) -> None:
    """Stand in for what the engine has met: classes that are no fixed width, and the `__index__` of each width."""
    monkeypatch.setattr(_ordering, "_NOT_FIXED", plain)
    monkeypatch.setattr(_compare, "_NOT_FIXED", plain)
    monkeypatch.setattr(_ordering, "_WHOLE_OF", {} if fixed is None else fixed)


def _raised(check) -> Exception | None:
    """What the call raised, or ``None`` where it returned."""
    try:
        check()
    except Exception as raised:
        return raised
    return None


@st.composite
def _fixed(draw: st.DrawFn) -> object:
    """An integer of one of the eight widths, weighted to the ends of its range, where a difference wraps."""
    kind = draw(st.sampled_from(_KINDS))
    low, high = int(numpy.iinfo(kind).min), int(numpy.iinfo(kind).max)
    near = st.sampled_from([low, low + 1, -1, 0, 1, 3, high - 1, high])
    return kind(draw(st.one_of(near.filter(lambda whole: low <= whole <= high), st.integers(low, high))))


_EXACT = st.one_of(
    _fixed(),
    st.integers(-(2**70), 2**70),
    st.fractions(min_value=-(2**66), max_value=2**66, max_denominator=1000),
    st.integers(-(2**66), 2**66).map(decimal.Decimal),
)
_SPANS = st.one_of(st.integers(0, 2**66), _fixed().filter(lambda span: span >= 0))


def _relations(value: object, operand: object) -> tuple[bool, bool, bool, bool]:
    """Whether each of the four relations holds for the pair, as the assertions answer it."""
    return (
        _passes(lambda: assert_that(value).is_less_than(operand)),
        _passes(lambda: assert_that(value).is_less_than_or_equal_to(operand)),
        _passes(lambda: assert_that(value).is_greater_than(operand)),
        _passes(lambda: assert_that(value).is_greater_than_or_equal_to(operand)),
    )


def _exactly(value: object) -> fractions.Fraction:
    if isinstance(value, numbers.Integral):
        return fractions.Fraction(int(value))
    return fractions.Fraction(float(value) if isinstance(value, numpy.floating) else value)


def _held(value: object) -> object:
    """The Python number a `numpy` number holds, by `numpy`'s own conversion, or the value where it is none."""
    if isinstance(value, numpy.integer):
        return int(value)
    return float(value) if isinstance(value, numpy.floating) else value


@st.composite
def _floating(draw: st.DrawFn) -> object:
    """A finite `numpy` float of one of three widths, weighted to where an integer beside it loses its last digit."""
    kind = draw(st.sampled_from(_FLOAT_KINDS))
    top = float(numpy.finfo(kind).max)
    edges = st.sampled_from([0.1, 0.5, 2.0**11, 2.0**24, 2.0**53, 2.0**62]).filter(lambda edge: edge <= top)
    drawn = draw(st.one_of(edges, st.floats(-top, top, allow_nan=False, width=numpy.finfo(kind).bits)))
    return kind(drawn * draw(st.sampled_from([1, -1])))


_WHOLE = st.one_of(
    _fixed(),
    st.integers(-(2**70), 2**70),
    st.sampled_from([2**52, 2**53, 2**53 + 1, 2**62, 2**64 - 1]).flatmap(lambda edge: st.integers(edge - 4, edge + 4)),
    st.fractions(min_value=-(2**66), max_value=2**66, max_denominator=1000),
)
_PLAIN = st.one_of(
    st.integers(-(2**70), 2**70),
    st.floats(-1e18, 1e18, allow_nan=False),
    st.fractions(min_value=-(2**66), max_value=2**66, max_denominator=1000),
)
_BESIDE = st.one_of(_fixed(), _floating(), st.integers(-(2**70), 2**70), st.floats(-1e18, 1e18, allow_nan=False))


class TestClosenessIsMeasuredOnTheIntegersHeld:
    def test_a_pixel_of_three_is_not_close_to_two_hundred_and_fifty(self):
        pixel = numpy.uint8(3)
        assert_that(_passes(lambda: assert_that(pixel).is_close_to(250, 10))).is_false()
        assert_that(_passes(lambda: assert_that(numpy.uint8(250)).is_close_to(pixel, 10))).is_false()
        assert_that(_passes(lambda: assert_that(0).is_close_to(numpy.uint8(200), 100))).is_false()
        assert_that(pixel).is_not_close_to(250, 10)
        assert_that(match.close_to(250, 10).matches(pixel)).is_false()
        assert_that(pixel).is_close_to(numpy.uint8(12), 10)

    def test_inside_a_value_under_a_tolerance(self):
        held, wanted = {"px": numpy.uint8(3)}, {"px": numpy.uint8(250)}
        assert_that(_passes(lambda: assert_that(held).is_equal_to(wanted, tolerance=10))).is_false()
        assert_that(held).is_equal_to({"px": numpy.uint8(9)}, tolerance=10)

    @pytest.mark.parametrize(
        ("value", "other", "tolerance"),
        [
            (numpy.int8(100), numpy.int8(-100), 60),
            (numpy.int32(2**30), numpy.int32(-(2**30)), 5),
            (numpy.int64(2**62), numpy.int64(-(2**62)), 5),
            (numpy.int64(-(2**63)), numpy.int64(2**63 - 1), 1),
            (numpy.uint64(0), numpy.uint64(2**64 - 1), 1),
        ],
        ids=["int8", "int32", "int64", "int64-ends", "uint64-ends"],
    )
    def test_two_ends_of_a_width_are_not_close(self, value, other, tolerance):
        assert_that(_passes(lambda: assert_that(value).is_close_to(other, tolerance))).is_false()
        assert_that(_passes(lambda: assert_that(other).is_close_to(value, tolerance))).is_false()

    def test_a_tolerance_of_a_fixed_width_is_read_as_its_integer(self):
        assert_that(0).is_close_to(numpy.uint8(1), numpy.uint8(100))
        assert_that(numpy.uint8(1)).is_close_to(0, numpy.uint8(100))
        assert_that(_passes(lambda: assert_that(0).is_close_to(numpy.uint8(200), numpy.uint8(100)))).is_false()

    @given(_EXACT, _EXACT, _SPANS)
    def test_every_spelling_answers_as_exact_arithmetic_does(self, value, other, tolerance):
        close = abs(_exactly(value) - _exactly(other)) <= _exactly(tolerance)
        assert _passes(lambda: assert_that(value).is_close_to(other, tolerance)) is close
        assert _passes(lambda: assert_that(other).is_close_to(value, tolerance)) is close
        assert _passes(lambda: assert_that(value).is_not_close_to(other, tolerance)) is not close
        assert match.close_to(other, tolerance).matches(value) is close
        assert _passes(lambda: assert_that([value]).is_equal_to([other], tolerance=tolerance)) is close


class TestOrderIsReadOffTheIntegersHeld:
    def test_a_third_is_not_less_than_a_large_negative(self):
        low = numpy.int64(-(2**62))
        third = fractions.Fraction(1, 3)
        assert_that(_passes(lambda: assert_that(third).is_less_than(low))).is_false()
        assert_that(third).is_greater_than(low)
        assert_that(low).is_less_than(third)
        assert_that(match.less_than(low).matches(third)).is_false()

    def test_a_tenth_orders_one_way_against_a_large_positive(self):
        large = numpy.int64(1_700_000_000_000_000_000)
        tenth = fractions.Fraction(1, 10)
        assert_that(tenth).is_less_than(large)
        assert_that(_passes(lambda: assert_that(tenth).is_greater_than(large))).is_false()
        assert_that(_passes(lambda: assert_that([large, tenth]).is_sorted())).is_false()
        assert_that([tenth, large]).is_sorted()

    def test_two_widths_order_by_value(self):
        assert_that(numpy.int64(2**62 + 1)).is_less_than(numpy.uint64(2**62 + 2))
        assert_that(numpy.int8(-1)).is_less_than(numpy.uint64(2**63))
        assert_that(numpy.uint64(2**64 - 1)).is_greater_than(numpy.int64(2**63 - 1))

    @given(_fixed(), _EXACT)
    def test_every_relation_answers_as_exact_values_do(self, fixed, other):
        left, right = _exactly(fixed), _exactly(other)
        assert _relations(fixed, other) == (left < right, left <= right, left > right, left >= right)
        assert _relations(other, fixed) == (right < left, right <= left, right > left, right >= left)

    @given(st.lists(_EXACT, min_size=2, max_size=6))
    def test_a_mixed_list_is_sorted_exactly_where_its_exact_values_are(self, items):
        ordered = all(_exactly(earlier) <= _exactly(later) for earlier, later in itertools.pairwise(items))
        assert _passes(lambda: assert_that(items).is_sorted()) is ordered

    def test_bounds_of_two_kinds_are_not_taken_for_swapped(self):
        low, high = fractions.Fraction(-2, 3), numpy.int64(2**62)
        assert_that(_raised(lambda: assert_that(0).is_between(low, high))).is_none()
        assert_that(_raised(lambda: match.between(low, high))).is_none()
        assert_that(match.between(low, high).matches(0)).is_true()
        assert_that(lambda: assert_that(0).is_between(high, low)).raises(ValueError).when_called_with()

    @given(_fixed(), st.integers(-(2**70), 2**70), st.integers(-(2**70), 2**70))
    def test_between_two_bounds_as_exact_values_are(self, fixed, low, high):
        low, high = min(low, high), max(low, high)
        assert _passes(lambda: assert_that(fixed).is_between(low, high)) is (low <= int(fixed) <= high)


class TestAFloatBesideAnIntegerIsReadAsTheFloatItHolds:
    def test_an_integer_past_a_narrow_floats_precision_keeps_its_last_digit(self):
        whole, narrow = numpy.int64(2**24 + 1), numpy.float32(2**24)
        assert_that(whole).is_greater_than(narrow)
        assert_that(narrow).is_less_than(whole)
        assert_that(_passes(lambda: assert_that(whole).is_close_to(narrow, 0))).is_false()
        assert_that(_passes(lambda: assert_that(narrow).is_close_to(whole, 0))).is_false()
        assert_that(match.close_to(narrow, 0).matches(whole)).is_false()
        assert_that(whole).is_close_to(narrow, 1)
        assert_that(whole).is_between(narrow, numpy.float32(2**25))

    def test_an_integer_past_a_doubles_precision_orders_exactly(self):
        assert_that(numpy.int64(2**53 + 1)).is_greater_than(numpy.float64(2**53))
        assert_that(numpy.float64(2**53)).is_less_than(numpy.int64(2**53 + 1))

    @pytest.mark.parametrize("span", [numpy.float16(10), numpy.float32(10), numpy.float64(10)], ids=repr)
    def test_two_integers_under_a_float_tolerance_are_measured_as_integers(self, span):
        assert_that(_passes(lambda: assert_that(numpy.uint8(3)).is_close_to(numpy.uint8(250), span))).is_false()
        assert_that(numpy.uint8(3)).is_close_to(numpy.uint8(12), span)

    def test_a_float_that_is_no_number_or_no_finite_one_answers_by_rule(self):
        pixel = numpy.uint8(3)
        assert_that(_passes(lambda: assert_that(pixel).is_close_to(numpy.float32("nan"), 300))).is_false()
        assert_that(_passes(lambda: assert_that(pixel).is_close_to(numpy.float32("inf"), 300))).is_false()
        assert_that(pixel).is_less_than(numpy.float32("inf"))

    @pytest.mark.parametrize(
        "pair",
        [(numpy.float32(0.1), 0), (0.1, numpy.float32(0.1)), (numpy.float32(0.1), numpy.float64(0.1))],
        ids=["float-and-int", "float-and-float", "two-widths"],
    )
    def test_with_no_numpy_integer_in_it_a_pair_is_handed_back_as_it_stood(self, pair):
        read = python_numbers(*pair)
        assert_that([one is other for one, other in zip(read, pair, strict=True)]).is_equal_to([True, True])

    def test_with_no_numpy_integer_among_them_the_operands_keep_the_arithmetic_they_had(self):
        operands = (numpy.float32(0.1), 0, 0.1)
        measured = _compare._as_measured(*operands)
        assert_that([one is other for one, other in zip(measured, operands, strict=True)]).is_equal_to([True] * 3)
        numpys_own = bool(abs(numpy.float32(0.1) - 0) <= 0.1)
        assert_that(_passes(lambda: assert_that(numpy.float32(0.1)).is_close_to(0, 0.1))).is_equal_to(numpys_own)

    @pytest.mark.parametrize(
        ("beside", "kind"),
        [(numpy.float16(1.5), float), (numpy.float32(1.5), float), (numpy.float64(1.5), float), (1.5, float), (7, int)],
        ids=repr,
    )
    def test_each_number_beside_an_integer_becomes_the_python_number_it_holds(self, beside, kind):
        for read in (python_numbers(numpy.uint8(3), beside), python_numbers(beside, numpy.uint8(3))[::-1]):
            assert_that([type(each) for each in read]).is_equal_to([int, kind])
            assert_that(list(read)).is_equal_to([3, beside])

    def test_the_tolerance_beside_a_pair_with_an_integer_is_read_as_well(self):
        measured = _compare._as_measured(numpy.uint8(3), 250, numpy.float32(10))
        assert_that([type(each) for each in measured]).is_equal_to([int, int, float])
        measured = _compare._as_measured(3, numpy.uint8(250), numpy.uint8(10))
        assert_that([type(each) for each in measured]).is_equal_to([int, int, int])

    @pytest.mark.parametrize(
        "beside",
        [
            numpy.complex64(1),
            numpy.timedelta64(5, "s"),
            numpy.bool_(True),
            type("Kept", (numpy.float32,), {})(1.5),
            fractions.Fraction(3, 2),
            decimal.Decimal("1.5"),
            "1.5",
        ],
        ids=["complex", "duration", "bool", "subclass", "fraction", "decimal", "text"],
    )
    def test_what_is_no_float_numpy_made_is_left_as_it_is(self, beside):
        read: list[object] = []
        assert_that(_raised(lambda: read.extend(python_numbers(numpy.uint8(1), beside)))).is_none()
        assert_that(type(read[0])).is_same_as(int)
        assert_that(read[1]).is_same_as(beside)

    def test_a_real_number_of_another_make_is_not_asked_for_its_float(self):
        asked = []

        class Odd:
            def __float__(self) -> float:
                asked.append("float")
                return 0.0

        numbers.Real.register(Odd)
        held = Odd()
        assert_that(python_numbers(numpy.uint8(1), held)[1]).is_same_as(held)
        assert_that(asked).is_empty()

    def test_a_class_with_a_metaclass_of_its_own_is_not_hashed_beside_an_integer(self):
        hashed = []

        class Meta(type):
            def __hash__(cls) -> int:
                hashed.append(cls)
                return 1

        class Held(metaclass=Meta):
            pass

        held = Held()
        assert_that(python_numbers(numpy.uint8(1), held)[1]).is_same_as(held)
        assert_that(hashed).is_empty()

    def test_a_class_with_a_metaclass_of_its_own_is_not_hashed_by_the_measure_itself(self):
        hashed = []

        class Meta(type):
            def __hash__(cls) -> int:
                hashed.append(cls)
                return 1

        class Held(metaclass=Meta):
            __hash__ = None

            def __eq__(self, other: object) -> bool:
                return other == 5.5

            def __sub__(self, other: float) -> float:
                return 5.5 - other

            def __rsub__(self, other: float) -> float:
                return other - 5.5

            def __lt__(self, other: float) -> bool:
                return other > 5.5

            def __gt__(self, other: float) -> bool:
                return other < 5.5

        assert_that(_compare._within_tolerance(5, Held(), 1)).is_true()
        assert_that(_compare._within_tolerance(Held(), 5, 1)).is_true()
        assert_that(hashed).is_empty()

    def test_past_its_bound_the_record_of_float_classes_stops_growing_and_the_answer_holds(self, monkeypatch):
        full = {type(f"Made{n}", (), {}): None for n in range(256)}
        monkeypatch.setattr(_ordering, "_FLOAT_OF", full)
        assert_that(numpy.int64(2**24 + 1)).is_greater_than(numpy.float32(2**24))
        assert_that(full).is_length(256)

    @pytest.mark.skipif(numpy.finfo(numpy.longdouble).nmant <= 52, reason="a long double is a double here")
    def test_a_long_double_past_a_double_keeps_numpys_own_measure(self):
        wide = numpy.longdouble(2**53) + numpy.longdouble(1)
        assert_that(python_numbers(numpy.int64(1), wide)[1]).is_same_as(wide)
        assert_that(python_numbers(wide, numpy.int64(1))[0]).is_same_as(wide)
        for operands in ((wide, 2.5, numpy.int64(5)), (2.5, wide, numpy.int64(5))):
            measured = _compare._as_measured(*operands)
            assert_that([one is other for one, other in zip(measured, operands, strict=True)]).is_equal_to([True] * 3)

    @pytest.mark.parametrize(
        ("value", "told"),
        [
            (numpy.float16(1.5), True),
            (numpy.float32(1.5), True),
            (numpy.float64(1.5), True),
            (numpy.longdouble(1.5), True),
            (numpy.float32("nan"), True),
            (numpy.float64("inf"), True),
            (1.5, False),
            (numpy.int64(1), False),
            (numpy.complex64(1), False),
            (numpy.timedelta64(5, "s"), False),
            (type("Kept", (numpy.float32,), {})(1.5), False),
            (fractions.Fraction(3, 2), False),
            ("1.5", False),
        ],
        ids=repr,
    )
    def test_a_numpy_float_is_told_by_its_class_whatever_it_holds(self, value, told):
        assert_that(numpy_float(value)).is_equal_to(told)

    def test_a_class_with_a_metaclass_of_its_own_is_not_hashed_beside_an_integer_tolerance(self):
        hashed = []

        class Meta(type):
            def __hash__(cls) -> int:
                hashed.append(cls)
                return 1

        class Held(metaclass=Meta):
            pass

        held = Held()
        assert_that(_compare._as_measured(held, 5, numpy.int8(1))[0]).is_same_as(held)
        assert_that(_compare._as_measured(5, held, numpy.int8(1))[1]).is_same_as(held)
        assert_that(hashed).is_empty()

    @given(_fixed(), _floating())
    def test_every_relation_answers_as_exact_values_do(self, fixed, floating):
        left, right = _exactly(fixed), _exactly(floating)
        assert _relations(fixed, floating) == (left < right, left <= right, left > right, left >= right)
        assert _relations(floating, fixed) == (right < left, right <= left, right > left, right >= left)

    @given(_BESIDE, _BESIDE, _BESIDE.filter(lambda span: span >= 0))
    def test_closeness_answers_as_it_does_for_the_python_numbers_held(self, value, operand, tolerance):
        assume(isinstance(value, numpy.integer) or isinstance(operand, numpy.integer))
        held = _passes(lambda: assert_that(_held(value)).is_close_to(_held(operand), _held(tolerance)))
        assert _passes(lambda: assert_that(value).is_close_to(operand, tolerance)) is held
        assert match.close_to(operand, tolerance).matches(value) is held
        assert _passes(lambda: assert_that([value]).is_equal_to([operand], tolerance=tolerance)) is held


class TestTwoIntegersAreCloseByTheirDifferenceAlone:
    @pytest.mark.parametrize(
        ("value", "other", "tolerance"),
        [
            (numpy.int64(2**53 + 1), numpy.int64(2**53), 0.0),
            (2**53 + 1, 2**53, 0.0),
            (2**53 + 1, 2**53, 0.5),
            (2**52, 2**52 + 3, 2.5),
            (numpy.uint64(2**64 - 1), 2**64 - 3, 1.5),
            (fractions.Fraction(2**53 + 1), fractions.Fraction(2**53), 0.0),
            (fractions.Fraction(2**53 + 1), 2**53, 0.0),
            (2**53, fractions.Fraction(2**53 + 1), 0.0),
        ],
        ids=["int64", "int", "half", "fractional", "uint64", "fractions", "fraction-and-int", "int-and-fraction"],
    )
    def test_a_window_under_a_float_tolerance_does_not_round_them_together(self, value, other, tolerance):
        assert_that(_passes(lambda: assert_that(value).is_close_to(other, tolerance))).is_false()
        assert_that(_passes(lambda: assert_that(other).is_close_to(value, tolerance))).is_false()
        assert_that(match.close_to(other, tolerance).matches(value)).is_false()
        assert_that(_passes(lambda: assert_that([value]).is_equal_to([other], tolerance=tolerance))).is_false()
        assert_that(value).is_not_close_to(other, tolerance)

    @pytest.mark.parametrize(("value", "other"), [(-20, -19.9), (-19.9, -20)], ids=["int-first", "float-first"])
    def test_an_integer_against_a_float_is_still_close_by_a_window(self, value, other):
        assert_that(abs(value - other) <= 0.1).is_false()
        assert_that(value).is_close_to(other, 0.1)
        assert_that(match.close_to(other, 0.1).matches(value)).is_true()
        assert_that([value]).is_equal_to([other], tolerance=0.1)

    @pytest.mark.parametrize(
        ("far", "tolerance"),
        [
            (2**24 + 1, numpy.float32(2**24)),
            (2**53 + 1, numpy.float64(2**53)),
            (fractions.Fraction(2**24 + 1), numpy.float32(2**24)),
            (2**11 + 1, numpy.float16(2**11)),
        ],
        ids=["float32", "float64", "fraction", "float16"],
    )
    @pytest.mark.parametrize("met", [False, True], ids=["class-not-met", "class-met"])
    def test_a_numpy_float_tolerance_is_held_as_the_float_it_holds(self, monkeypatch, far, tolerance, met):
        plain = {int, float, fractions.Fraction, decimal.Decimal}
        _met(monkeypatch, plain | {type(tolerance)} if met else plain)
        assert_that(_passes(lambda: assert_that(far).is_close_to(0, tolerance))).is_false()
        assert_that(_passes(lambda: assert_that(0).is_close_to(far, tolerance))).is_false()
        assert_that(match.close_to(0, tolerance).matches(far)).is_false()
        assert_that(_passes(lambda: assert_that([far]).is_equal_to([0], tolerance=tolerance))).is_false()
        assert_that(far - 1).is_close_to(0, tolerance)

    @pytest.mark.parametrize(
        "held",
        [
            fractions.Fraction(numpy.int64(5), 3),
            fractions.Fraction(5, numpy.int64(3)),
            numpy.int64(5),
            5.0,
            True,
            decimal.Decimal(5),
        ],
        ids=["numpy-numerator", "numpy-denominator", "numpy-integer", "float", "bool", "decimal"],
    )
    def test_what_is_no_int_and_no_fraction_of_two_is_not_called_exact(self, held):
        assert_that(_compare._differ_exactly(held, 5)).is_false()
        assert_that(_compare._differ_exactly(5, held)).is_false()
        assert_that(_compare._differ_exactly(5, fractions.Fraction(1, 3))).is_true()

    def test_the_tolerance_of_a_pair_that_is_not_exact_keeps_its_class(self):
        operands = (5, 7.5, numpy.float32(1.5))
        measured = _compare._as_measured(*operands)
        assert_that([one is other for one, other in zip(measured, operands, strict=True)]).is_equal_to([True] * 3)

    @given(_WHOLE, _WHOLE, st.one_of(st.floats(0, 2.0**66, allow_nan=False), _floating().map(abs)))
    def test_under_a_float_tolerance_every_spelling_answers_as_exact_arithmetic_does(self, value, other, tolerance):
        close = abs(_exactly(value) - _exactly(other)) <= fractions.Fraction(float(tolerance))
        assert _passes(lambda: assert_that(value).is_close_to(other, tolerance)) is close
        assert _passes(lambda: assert_that(other).is_close_to(value, tolerance)) is close
        assert match.close_to(other, tolerance).matches(value) is close
        assert _passes(lambda: assert_that([value]).is_equal_to([other], tolerance=tolerance)) is close


class TestAnIntegerStandingAsTheToleranceAlone:
    @given(_PLAIN, _PLAIN, _fixed().filter(lambda span: span >= 0))
    def test_around_python_numbers_it_is_read_as_its_int(self, value, operand, tolerance):
        held = _passes(lambda: assert_that(value).is_close_to(operand, int(tolerance)))
        assert _passes(lambda: assert_that(value).is_close_to(operand, tolerance)) is held
        assert match.close_to(operand, tolerance).matches(value) is held
        assert _passes(lambda: assert_that([value]).is_equal_to([operand], tolerance=tolerance)) is held

    @pytest.mark.parametrize(
        "operands",
        [
            (numpy.float16(1), 2.5, numpy.int64(100_000)),
            (2.5, numpy.float16(1), numpy.int64(100_000)),
            (numpy.float32("nan"), 2.5, numpy.int64(5)),
            (2.5, numpy.float64("nan"), numpy.int64(5)),
        ],
        ids=["float-value", "float-operand", "nan-value", "nan-operand"],
    )
    def test_beside_a_pair_that_holds_a_numpy_float_nothing_is_read(self, operands):
        measured = _compare._as_measured(*operands)
        assert_that([one is other for one, other in zip(measured, operands, strict=True)]).is_equal_to([True] * 3)

    def test_a_pair_of_fractions_is_measured_against_the_int_it_holds(self):
        third, none = fractions.Fraction(100, 3), fractions.Fraction(0)
        assert_that(third).is_close_to(none, numpy.uint8(200))
        assert_that(match.close_to(none, numpy.uint8(200)).matches(third)).is_true()
        assert_that([third]).is_equal_to([none], tolerance=numpy.uint8(200))
        assert_that(_passes(lambda: assert_that(third).is_close_to(none, numpy.uint8(30)))).is_false()

    def test_a_narrow_float_pair_under_a_wide_integer_tolerance_answers_without_a_warning(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            answer = _passes(lambda: assert_that(numpy.float16(1)).is_close_to(numpy.float16(2), numpy.int64(100_000)))
        assert_that(answer).is_true()
        assert_that([str(each.message) for each in caught]).is_empty()

    def test_the_three_spellings_agree_on_a_float_pair_under_an_integer_tolerance(self):
        value, operand, tolerance = 1.3393252495451232e-254, numpy.float16(0.0), numpy.int8(0)
        answers = [
            _passes(lambda: assert_that(value).is_close_to(operand, tolerance)),
            match.close_to(operand, tolerance).matches(value),
            _passes(lambda: assert_that([value]).is_equal_to([operand], tolerance=tolerance)),
        ]
        assert_that(answers).is_equal_to([value == operand] * 3)


class TestNoWarningComesOutOfAnAnswer:
    @pytest.mark.parametrize(
        "holds",
        [
            lambda: _passes(lambda: assert_that(numpy.uint8(3)).is_not_close_to(250, 10)),
            lambda: _passes(lambda: assert_that(numpy.uint8(250)).is_not_close_to(numpy.uint8(3), numpy.uint8(10))),
            lambda: _passes(lambda: assert_that(numpy.int8(100)).is_not_close_to(numpy.int8(-100), 60)),
            lambda: not match.close_to(250, 10).matches(numpy.uint8(3)),
            lambda: _passes(
                lambda: assert_that({"px": numpy.uint8(3)}).is_equal_to({"px": numpy.uint8(9)}, tolerance=10)
            ),
            lambda: _passes(lambda: assert_that(250).is_not_close_to(3, numpy.uint8(200))),
            lambda: _passes(lambda: assert_that(numpy.uint8(250)).is_not_close_to(numpy.float32(3), numpy.uint8(10))),
            lambda: _passes(lambda: assert_that(numpy.uint8(250)).is_not_close_to(3.5, numpy.uint8(10))),
            lambda: _passes(lambda: assert_that(3.5).is_not_close_to(numpy.uint8(250), numpy.uint8(10))),
            lambda: _passes(lambda: assert_that(250).is_not_close_to(3.5, numpy.uint8(10))),
            lambda: _passes(lambda: assert_that(3.5).is_not_close_to(250, numpy.uint8(10))),
            lambda: _passes(lambda: assert_that(500.0).is_not_close_to(fractions.Fraction(1, 3), numpy.uint8(100))),
            lambda: _passes(lambda: assert_that(fractions.Fraction(1, 3)).is_greater_than(numpy.int64(-(2**62)))),
            lambda: _passes(
                lambda: assert_that(numpy.int64(1_700_000_000_000_000_000)).is_greater_than(fractions.Fraction(1, 10))
            ),
            lambda: _passes(
                lambda: assert_that([fractions.Fraction(1, 10), numpy.int64(1_700_000_000_000_000_000)]).is_sorted()
            ),
        ],
        ids=[
            "not-close",
            "widths-each-way",
            "one-width",
            "matcher",
            "under-tolerance",
            "tolerance-alone",
            "float-beside",
            "width-and-float",
            "float-and-width",
            "int-and-float-under-a-width",
            "float-and-int-under-a-width",
            "tolerance-beside-a-fraction",
            "fraction-left",
            "width-left",
            "sorted",
        ],
    )
    def test_each_spelling_gives_the_right_answer_and_no_warning(self, holds):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            answer = holds()
        assert_that(answer).is_true()
        assert_that([str(each.message) for each in caught]).is_empty()


class TestWhatIsReadAsAnInteger:
    @pytest.mark.parametrize("kind", _KINDS, ids=lambda kind: kind.__name__)
    def test_each_width_becomes_the_int_it_holds(self, kind):
        top = int(numpy.iinfo(kind).max)
        read = unwrapped(kind(top))
        assert_that(type(read)).is_same_as(int)
        assert_that(read).is_equal_to(top)

    @pytest.mark.parametrize(
        "value",
        [
            7,
            True,
            1.5,
            fractions.Fraction(1, 3),
            decimal.Decimal(5),
            numpy.float64(1.5),
            numpy.float32(1.5),
            numpy.bool_(True),
            numpy.timedelta64(5, "s"),
            numpy.datetime64("2026-01-01"),
            "7",
            None,
        ],
        ids=repr,
    )
    def test_anything_else_is_left_as_it_is(self, value):
        assert_that(unwrapped(value)).is_same_as(value)

    def test_an_integer_of_another_make_is_not_asked_for_its_index(self):
        asked = []

        class Odd:
            def __index__(self) -> int:
                asked.append("index")
                return 0

        numbers.Integral.register(Odd)
        held = Odd()
        assert_that(unwrapped(held)).is_same_as(held)
        assert_that(unwrapped(held)).is_same_as(held)
        assert_that(asked).is_empty()

    def test_a_class_with_a_metaclass_of_its_own_is_not_hashed(self):
        hashed = []

        class Meta(type):
            def __hash__(cls) -> int:
                hashed.append(cls)
                return 1

        class Held(metaclass=Meta):
            pass

        held = Held()
        assert_that(unwrapped(held)).is_same_as(held)
        assert_that(hashed).is_empty()

    def test_a_width_met_first_in_an_ordering_is_read_there(self, monkeypatch):
        _met(monkeypatch, {int, float, fractions.Fraction})
        assert_that(fractions.Fraction(1, 3)).is_greater_than(numpy.int64(-(2**62)))
        _met(monkeypatch, {int, float, fractions.Fraction})
        assert_that(numpy.int64(1_700_000_000_000_000_000)).is_greater_than(fractions.Fraction(1, 10))

    @pytest.mark.parametrize(
        "holds",
        [
            lambda: _passes(lambda: assert_that(numpy.uint8(3)).is_not_close_to(250, 10)),
            lambda: _passes(lambda: assert_that(0).is_not_close_to(numpy.uint8(200), 100)),
            lambda: _passes(lambda: assert_that(250).is_not_close_to(3, numpy.uint8(200))),
        ],
        ids=["value", "operand", "tolerance"],
    )
    def test_a_width_met_first_in_a_closeness_is_read_there(self, monkeypatch, holds):
        _met(monkeypatch, {int, float})
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            answer = holds()
        assert_that(answer).is_true()
        assert_that([str(each.message) for each in caught]).is_empty()

    def test_a_float_class_met_first_is_read_there(self, monkeypatch):
        monkeypatch.setattr(_ordering, "_FLOAT_OF", {int: None, float: None})
        assert_that(numpy.int64(2**24 + 1)).is_greater_than(numpy.float32(2**24))

    def test_past_its_bound_the_record_of_classes_stops_growing_and_the_answer_holds(self, monkeypatch):
        plain = {type(f"Made{n}", (), {}) for n in range(256)}
        fixed: dict[type, object] = {type(f"Fixed{n}", (), {}): None for n in range(256)}
        _met(monkeypatch, plain, fixed)
        five = decimal.Decimal(5)
        assert_that(unwrapped(five)).is_same_as(five)
        assert_that(unwrapped(numpy.uint8(3))).is_equal_to(3)
        assert_that(type(unwrapped(numpy.uint8(3)))).is_same_as(int)
        assert_that(_passes(lambda: assert_that(numpy.uint8(3)).is_close_to(250, 10))).is_false()
        assert_that(five).is_greater_than(numpy.int64(-(2**62)))
        assert_that([len(plain), len(fixed)]).is_equal_to([256, 256])

    def test_a_subclass_with_operators_of_its_own_is_asked_through_them(self):
        never_less = type(
            "NeverLess", (numpy.int64,), {"__lt__": lambda self, other: False, "__hash__": numpy.int64.__hash__}
        )
        held = never_less(1)
        assert_that(unwrapped(held)).is_same_as(held)
        assert_that(_passes(lambda: assert_that(held).is_less_than(5))).is_false()
        assert_that(numpy.int64(1)).is_less_than(5)

    def test_a_fraction_past_the_width_of_such_a_subclass_orders_by_exact_value(self):
        kept = type("Kept", (numpy.int64,), {})
        assert_that(fractions.Fraction(1, 10**20)).is_less_than(kept(5))
        assert_that(_passes(lambda: assert_that(fractions.Fraction(1, 10**20)).is_greater_than(kept(5)))).is_false()

    def test_a_duration_keeps_its_own_closeness(self):
        assert_that(numpy.timedelta64(5, "s")).is_close_to(numpy.timedelta64(7, "s"), numpy.timedelta64(3, "s"))
