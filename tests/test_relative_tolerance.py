"""A tolerance relative to the size of the numbers, beside the absolute one, wherever a tolerance is taken.

Scaled by the expected side, as `pytest.approx` scales: scaled by the larger of the two, as `math.isclose`
scales a pair with no expected side, the value under test widened its own allowance, and 10 was within
`rel=1` of 1.  Given beside an absolute tolerance, either holding is enough, which keeps an expected value
near zero within reach.
"""

import datetime
import decimal
import fractions
import math

import pytest
from hypothesis import assume, example, given, settings
from hypothesis import strategies as st

from assertpy import AssertionFailure, assert_that, match
from tests.optional import needs

_DIRECTED = [
    (102.0, 100.0, 0.02, True),
    (98.0, 100.0, 0.02, True),
    (100.0, 98.0, 0.02, False),
    (102.1, 100.0, 0.02, False),
    (-102.0, -100.0, 0.02, True),
    (-102.1, -100.0, 0.02, False),
    (10, 1, 1, False),
    (2, 1, 1, True),
    (2, 1, 0.5, False),
    (1, 0, 1, False),
    (0, 1, 1, True),
]


def _verdicts(value, other, rel):
    """What each spelling of a relative closeness answers for one pair."""
    return {
        "is_close_to": assert_that(value).check().is_close_to(other, rel=rel).passed,
        "is_not_close_to": not assert_that(value).check().is_not_close_to(other, rel=rel).passed,
        "close_to": match.close_to(other, rel=rel).matches(value),
        "is_equal_to": assert_that([value]).check().is_equal_to([other], rel=rel).passed,
    }


class TestTheScaleIsTheExpectedSide:
    @pytest.mark.parametrize(("value", "other", "rel", "close"), _DIRECTED)
    def test_as_pytest_approx_scales_it(self, value, other, rel, close):
        verdicts = _verdicts(value, other, rel)
        assert_that(verdicts).is_equal_to(dict.fromkeys(verdicts, close))
        assert_that(close).is_equal_to(value == pytest.approx(other, rel=rel, abs=0))

    @pytest.mark.parametrize(("value", "other", "rel", "close"), _DIRECTED)
    def test_as_exact_numbers_scale_it_too(self, value, other, rel, close):
        verdicts = _verdicts(*(fractions.Fraction(number) for number in (value, other, rel)))
        assert_that(verdicts).is_equal_to(dict.fromkeys(verdicts, close))

    def test_the_boundary_is_a_fraction_of_the_expected_side(self):
        assert_that(110).is_close_to(100, rel=0.1)
        assert_that(100).is_close_to(110, rel=0.091)
        assert_that(110).is_not_close_to(100, rel=0.091)
        assert_that(100).is_not_close_to(110, rel=0.09)

    def test_either_tolerance_is_enough_and_they_are_not_added(self):
        assert_that(0.0).is_close_to(0.001, 0.01, rel=0.02)
        assert_that(1000.0).is_close_to(1019.0, 0.01, rel=0.02)
        # 3 apart: the sum of 1 and 2% of 103 would cover it, and neither alone does
        assert_that(100).is_not_close_to(103, 1, rel=0.02)
        assert_that(match.close_to(1019.0, 0.01, rel=0.02).matches(1000.0)).is_true()
        assert_that(match.close_to(103, 1, rel=0.02).matches(100)).is_false()

    def test_an_expected_zero_is_reached_relatively_only_by_zero(self):
        assert_that(0).is_close_to(0, rel=0.5)
        assert_that(-0.0).is_close_to(0.0, rel=0)
        assert_that(1e-300).is_not_close_to(0.0, rel=1e300)
        assert_that(0.0).is_not_close_to(1e-300, rel=0.5)
        assert_that(0.0).is_close_to(1e-300, rel=1)

    def test_an_infinite_rel_covers_every_finite_pair_a_zeros_too(self):
        assert_that(5).is_close_to(0, rel=math.inf)
        assert_that(-1e308).is_close_to(1e-300, rel=math.inf)

    @pytest.mark.parametrize(
        ("value", "other", "rel", "close"),
        [
            (math.inf, decimal.Decimal("1e9"), decimal.Decimal(10), False),
            (decimal.Decimal("9e9"), decimal.Decimal("-9e9"), math.inf, True),
        ],
    )
    def test_a_rule_answers_before_any_arithmetic_a_decimal_context_may_trap(self, value, other, rel, close):
        with decimal.localcontext() as context:
            context.Emax = 9
            context.traps[decimal.Overflow] = True
            verdicts = assert_that(_verdicts).does_not_raise(decimal.Overflow).when_called_with(value, other, rel)
        verdicts.returned().is_equal_to(
            dict.fromkeys(("is_close_to", "is_not_close_to", "close_to", "is_equal_to"), close)
        )

    def test_a_decimal_context_trapping_its_overflow_raises_it_as_the_absolute_tolerance_does(self):
        with decimal.localcontext() as context:
            context.Emax = 9
            context.traps[decimal.Overflow] = True
            with pytest.raises(decimal.Overflow):
                assert_that(decimal.Decimal(0)).is_close_to(decimal.Decimal("1e9"), rel=decimal.Decimal(10))
            with pytest.raises(decimal.Overflow):
                assert_that(decimal.Decimal("9e9")).is_close_to(decimal.Decimal("-9e9"), decimal.Decimal("1e9"))

    def test_an_infinity_and_a_nan_are_read_as_the_absolute_tolerance_reads_them(self):
        assert_that(math.inf).is_close_to(math.inf, rel=0.1)
        assert_that(math.inf).is_not_close_to(-math.inf, rel=0.1)
        assert_that(math.inf).is_not_close_to(1e308, rel=10)
        assert_that(math.nan).is_not_close_to(math.nan, rel=1)
        assert_that(1e308).is_close_to(-1e308, rel=math.inf)

    def test_exact_numbers_are_measured_exactly(self):
        assert_that(2**80 + 1).is_close_to(2**80, rel=fractions.Fraction(1, 2**80))
        assert_that(2**80 + 2).is_not_close_to(2**80, rel=fractions.Fraction(1, 2**80))
        assert_that(decimal.Decimal("1.02")).is_close_to(decimal.Decimal("1.00"), rel=0.02)
        assert_that(decimal.Decimal("1.03")).is_not_close_to(decimal.Decimal("1.00"), rel=0.02)
        assert_that(10**400).is_close_to(10**400 + 10**398, rel=0.01)
        assert_that(1e300).is_close_to(10**400, rel=1)
        assert_that(1e300).is_not_close_to(10**400, rel=0)

    @pytest.mark.parametrize(
        ("value", "other", "rel", "close"),
        [
            (1e308, -1e308, 1.9, False),
            (1.7e308, -1.7e308, 1.5, False),
            (1e308, -1e308, 2.5, True),
            (-1e308, 1.7e308, 1.6, True),
            (1.7e308, 1e308, 1.8, True),
        ],
    )
    def test_an_allowance_past_the_float_range_is_measured_exactly(self, value, other, rel, close):
        exact = fractions.Fraction
        assert_that(abs(exact(value) - exact(other)) <= exact(rel) * abs(exact(other))).is_equal_to(close)
        verdicts = _verdicts(value, other, rel)
        assert_that(verdicts).is_equal_to(dict.fromkeys(verdicts, close))


class TestTheMessageNamesWhatWasAsked:
    def test_relative_alone(self):
        with pytest.raises(AssertionFailure) as failure:
            assert_that(110).is_close_to(100, rel=0.02)
        assert_that(str(failure.value)).starts_with(
            "Expected <110> to be close to <100> within relative tolerance <0.02>, but was not."
        )
        assert_that(failure.value.expected).is_equal_to((100, None, 0.02))

    def test_both(self):
        with pytest.raises(AssertionFailure) as failure:
            assert_that(100).is_not_close_to(101, 2, rel=0.02)
        assert_that(str(failure.value)).starts_with(
            "Expected <100> to not be close to <101> within tolerance <2> or relative tolerance <0.02>, but was."
        )

    def test_the_matcher_says_it_too(self):
        assert_that(match.close_to(100, rel=0.02).describe()).is_equal_to(
            "a value within relative tolerance <0.02> of <100>"
        )
        assert_that(match.close_to(100, 1, rel=0.02).describe()).is_equal_to(
            "a value within <1> or relative tolerance <0.02> of <100>"
        )


class TestEveryComparisonTakesIt:
    def test_equality_at_every_depth(self):
        assert_that({"a": [100.0, {"b": 1000.0}]}).is_equal_to({"a": [101.0, {"b": 1015.0}]}, rel=0.02)
        with pytest.raises(AssertionFailure) as failure:
            assert_that({"a": 100.0}).is_equal_to({"a": 103.0}, tolerance=1, rel=0.02)
        assert_that(str(failure.value)).contains("compared with tolerance=1, rel=0.02")

    def test_the_equality_matcher(self):
        assert_that({"a": 1000.0}).satisfies(match.equal_to({"a": 1015.0}, rel=0.02))
        assert_that(match.equal_to({"a": 1030.0}, rel=0.02).matches({"a": 1000.0})).is_false()

    def test_a_snapshot_and_an_inline_one(self, tmp_path):
        with pytest.warns(UserWarning):
            assert_that({"latency": 100.0}).snapshot(id="rel", path=str(tmp_path))
        assert_that({"latency": 101.5}).snapshot(id="rel", path=str(tmp_path), rel=0.02)
        assert_that({"latency": 101.5}).matches_inline({"latency": 100.0}, rel=0.02)
        with pytest.raises(AssertionFailure):
            assert_that({"latency": 103.0}).matches_inline({"latency": 100.0}, rel=0.02)

    def test_a_snapshot_and_an_inline_one_scale_by_what_they_hold(self, tmp_path):
        for name, stored in (("low", 98.0), ("high", 100.0)):
            with pytest.warns(UserWarning):
                assert_that({"latency": stored}).snapshot(id=name, path=str(tmp_path))
        assert_that({"latency": 98.0}).snapshot(id="high", path=str(tmp_path), rel=0.02)
        with pytest.raises(AssertionFailure):
            assert_that({"latency": 100.0}).snapshot(id="low", path=str(tmp_path), rel=0.02)
        assert_that({"latency": 98.0}).matches_inline({"latency": 100.0}, rel=0.02)
        with pytest.raises(AssertionFailure):
            assert_that({"latency": 100.0}).matches_inline({"latency": 98.0}, rel=0.02)


class TestWhatIsRefused:
    @pytest.mark.parametrize(
        ("rel", "kind", "said"),
        [
            (True, TypeError, "given rel arg must be a real number"),
            (1j, TypeError, "given rel arg must be a real number"),
            ("0.1", TypeError, "given rel arg must be a real number"),
            (math.nan, ValueError, "given rel arg must not be NaN"),
            (-0.1, ValueError, "given rel arg must not be negative"),
        ],
        ids=["bool", "complex", "text", "nan", "negative"],
    )
    def test_a_rel_that_is_no_non_negative_number(self, rel, kind, said):
        for ask in (
            lambda: assert_that(1.0).is_close_to(1.0, rel=rel),
            lambda: match.close_to(1.0, rel=rel),
            lambda: assert_that(1.0).is_equal_to(1.0, rel=rel),
            lambda: match.equal_to(1.0, rel=rel),
        ):
            with pytest.raises(kind) as refusal:
                ask()
            assert_that(str(refusal.value)).is_equal_to(said)

    def test_a_duration_has_no_size_either(self):
        numpy = needs("numpy")
        second = numpy.timedelta64(1, "s")
        with pytest.raises(TypeError) as refusal:
            assert_that(2 * second).is_close_to(second, second, rel=0.1)
        assert_that(str(refusal.value)).starts_with("given rel arg must be None for a numpy duration")
        with pytest.raises(TypeError, match="which a numpy duration tolerance has none of"):
            assert_that([2 * second]).is_equal_to([second], tolerance=second, rel=0.1)

    def test_a_number_whose_own_subtraction_raises_is_not_answered_for(self):
        class Unsubtractable(float):
            def __sub__(self, other):
                raise TypeError("its own subtraction")

        with pytest.raises(TypeError, match="its own subtraction"):
            assert_that(Unsubtractable(1.0)).is_close_to(2.0, rel=0.1)

    def test_an_expected_number_whose_own_size_raises_is_not_answered_for(self):
        class Sizeless(float):
            def __abs__(self):
                raise TypeError("its own size")

        with pytest.raises(TypeError, match="its own size"):
            assert_that(1.0).is_close_to(Sizeless(2.0), rel=0.1)

    def test_no_tolerance_at_all(self):
        with pytest.raises(TypeError) as refusal:
            assert_that(1.0).is_close_to(1.0)
        assert_that(str(refusal.value)).is_equal_to(
            "given tolerance arg must be a number, or a rel given instead, but was <None> (NoneType)"
        )

    def test_a_datetime_has_no_size_to_take_a_fraction_of(self):
        now = datetime.datetime(2026, 1, 1)
        with pytest.raises(TypeError) as refusal:
            assert_that(now).is_close_to(now, datetime.timedelta(seconds=1), rel=0.1)
        assert_that(str(refusal.value)).starts_with("given rel arg must be None for a datetime")
        with pytest.raises(TypeError, match="given rel arg must be None beside a duration"):
            match.close_to(now, datetime.timedelta(seconds=1), rel=0.1)


_FINITE = st.floats(allow_nan=False, allow_infinity=False)
_RELS = st.floats(min_value=0, max_value=10, allow_nan=False)


class TestTheRuleHeldOverAnyNumbers:
    @settings(deadline=None)
    @example(value=100.0, other=98.0, rel=0.02)
    @example(value=98.0, other=100.0, rel=0.02)
    @given(value=_FINITE, other=_FINITE, rel=_RELS)
    def test_it_is_the_absolute_tolerance_its_fraction_of_the_expected_side_gives(self, value, other, rel):
        allowance = rel * abs(other)
        assume(math.isfinite(allowance))
        expected = assert_that(value).check().is_close_to(other, allowance).passed
        verdicts = _verdicts(value, other, rel)
        assert_that(verdicts).is_equal_to(dict.fromkeys(verdicts, expected))

    @settings(deadline=None)
    @example(value=100.0, other=98.0, rel=0.02)
    @example(value=1e308, other=-1e308, rel=1.9)
    @example(value=1e308, other=-1e308, rel=10.0)
    @given(value=_FINITE, other=_FINITE, rel=_RELS)
    def test_it_is_the_exact_answer_wherever_rounding_cannot_decide(self, value, other, rel):
        exact = fractions.Fraction
        distance, allowance = abs(exact(value) - exact(other)), exact(rel) * abs(exact(other))
        # a float rounds the allowance and the windows by an ulp of the numbers measured, and a subnormal by more
        assume(
            abs(distance - allowance) > (abs(exact(value)) + abs(exact(other)) + allowance) / 2**40 + exact(2) ** -1000
        )
        verdicts = _verdicts(value, other, rel)
        assert_that(verdicts).is_equal_to(dict.fromkeys(verdicts, distance <= allowance))

    @settings(deadline=None)
    @example(value=100.0, other=103.0, tolerance=1.0, rel=0.02)
    @given(value=_FINITE, other=_FINITE, tolerance=st.floats(min_value=0, max_value=1e6), rel=_RELS)
    def test_either_tolerance_holding_is_the_answer(self, value, other, tolerance, rel):
        alone = assert_that(value).check().is_close_to(other, tolerance).passed
        relative = assert_that(value).check().is_close_to(other, rel=rel).passed
        both = assert_that(value).check().is_close_to(other, tolerance, rel=rel).passed
        assert_that(both).is_equal_to(alone or relative)
