"""A value that cannot render itself still gets its failure, never the exception its rendering raised.

A failure message interpolates the value under test and the operands it was compared with.  Interpolated raw,
a `__repr__`, `__str__` or `__format__` that raises replaced the verdict with the user's exception: the test
reported a crash in the value instead of the difference it was asked about.  Every such site renders through
the guarded renderers in `assertpy.errors`, which name the value `<unreprable ...>` instead.

Parameters that configure an assertion rather than name a value (a length, a tolerance, a pattern, a key name)
are not held to this: they have a declared type, and a string that cannot print itself is outside it.
"""

import datetime

import pytest

from assertpy import assert_conforms, assert_that, match


class _UnrenderedError(Exception):
    """What rendering one of these values raises."""


class _Unrenderable:
    """Raises from every way a message could render it, so only a guarded renderer gets past it."""

    def __repr__(self):
        raise _UnrenderedError

    def __str__(self):
        raise _UnrenderedError

    def __format__(self, spec):
        raise _UnrenderedError


class _Int(_Unrenderable, int):
    pass


class _Float(_Unrenderable, float):
    pass


class _Str(_Unrenderable, str):
    pass


class _Bytes(_Unrenderable, bytes):
    pass


class _List(_Unrenderable, list):
    pass


class _Dict(_Unrenderable, dict):
    pass


class _Moment(_Unrenderable, datetime.datetime):
    pass


class _Thing(_Unrenderable):
    """Equal only to itself."""


_THING = _Thing()


class _Spelled:
    """Three different answers, so a message shows which rendering its site asked for."""

    def __repr__(self):
        return "repr"

    def __str__(self):
        return "str"

    def __format__(self, spec):
        return "formatted"


class _FormatsAgain(str):
    def __format__(self, spec):
        raise _UnrenderedError


class _HandsBackAString:
    """`__format__` may return a `str` subclass, which an f-string interpolates without formatting it again."""

    def __format__(self, spec):
        return _FormatsAgain("handed")


class _OnlyFormatRefuses:
    def __repr__(self):
        return "repr"

    def __format__(self, spec):
        raise _UnrenderedError


_FAILURES = [
    pytest.param(lambda: assert_that(_List([1.0])).is_equal_to([2.0], tolerance=0.1), id="equal-tolerance-actual"),
    pytest.param(lambda: assert_that([1.0]).is_equal_to(_List([2.0]), tolerance=0.1), id="equal-tolerance-expected"),
    pytest.param(
        lambda: assert_that(_Float(1.0)).is_equal_to(2.0, comparators={float: lambda actual, expected: False}),
        id="equal-comparator",
    ),
    pytest.param(lambda: assert_that([_Int(1)]).is_equal_to([2], ignore="k"), id="equal-filtered-item"),
    pytest.param(lambda: assert_that(_Dict(a=1)).is_equal_to({"a": 1}, include="b"), id="equal-include-missing"),
    pytest.param(lambda: assert_that(_Int(1)).is_not_equal_to(1), id="not-equal-actual"),
    pytest.param(lambda: assert_that(1).is_not_equal_to(_Int(1)), id="not-equal-other"),
    pytest.param(lambda: assert_that(1).is_same_as(_THING), id="same-as"),
    pytest.param(lambda: assert_that(_THING).is_not_same_as(_THING), id="not-same-as"),
    pytest.param(lambda: assert_that(_List([1])).contains(2), id="contains-values"),
    pytest.param(lambda: assert_that([1]).contains(_THING), id="contains-item"),
    pytest.param(lambda: assert_that({"a": 1}).contains(_Str("b")), id="contains-key"),
    pytest.param(lambda: assert_that([{"k": 1, "v": _Int(2)}]).contains({"k": 1, "v": 3}), id="contains-closest"),
    pytest.param(lambda: assert_that(_List([1])).contains(match.greater_than(5)), id="contains-matcher"),
    pytest.param(lambda: assert_that([1]).contains(1, _THING), id="contains-items"),
    pytest.param(lambda: assert_that({"a": 1}).contains("a", _Str("b")), id="contains-keys"),
    pytest.param(lambda: assert_that([_THING]).does_not_contain(_THING), id="does-not-contain-item"),
    pytest.param(lambda: assert_that([_THING]).does_not_contain(_THING, 2), id="does-not-contain-items"),
    pytest.param(lambda: assert_that([1]).contains_only(_THING), id="contains-only"),
    pytest.param(lambda: assert_that("abc").contains_sequence(_Str("x")), id="contains-sequence-text"),
    pytest.param(lambda: assert_that([1, 2]).contains_sequence(_THING), id="contains-sequence"),
    pytest.param(lambda: assert_that([1, 2]).contains_in_order(1, _THING), id="contains-in-order"),
    pytest.param(lambda: assert_that([_Int(1)]).contains_only_once(2), id="contains-only-once"),
    pytest.param(lambda: assert_that([1]).contains_exactly(_THING), id="contains-exactly"),
    pytest.param(lambda: assert_that([_Int(1), _Int(2)]).contains_exactly_in_any_order(3, 4), id="any-order"),
    pytest.param(lambda: assert_that(_Int(1)).is_greater_than(2), id="greater-than-actual"),
    pytest.param(lambda: assert_that(1).is_greater_than(_Int(2)), id="greater-than-other"),
    pytest.param(lambda: assert_that(1).is_greater_than_or_equal_to(_Int(2)), id="at-least"),
    pytest.param(lambda: assert_that(3).is_less_than(_Int(2)), id="less-than"),
    pytest.param(lambda: assert_that(3).is_less_than_or_equal_to(_Int(2)), id="at-most"),
    pytest.param(lambda: assert_that(1).is_between(_Int(2), _Int(3)), id="between"),
    pytest.param(lambda: assert_that(2).is_not_between(_Int(1), _Int(3)), id="not-between"),
    pytest.param(lambda: assert_that(1.0).is_close_to(_Float(5.0), 0.1), id="close-to"),
    pytest.param(lambda: assert_that(5.0).is_not_close_to(_Float(5.0), 0.1), id="not-close-to"),
    pytest.param(lambda: assert_that(datetime.datetime(2020, 1, 1)).is_after(_Moment(2021, 1, 1)), id="datetime-after"),
    pytest.param(lambda: assert_that("a").is_equal_to_ignoring_case(_Str("b")), id="ignoring-case"),
    pytest.param(lambda: assert_that("a").is_equal_to_ignoring_whitespace(_Str("b")), id="ignoring-whitespace"),
    pytest.param(lambda: assert_that("abc").contains_ignoring_case(_Str("z")), id="contains-ignoring-case"),
    pytest.param(lambda: assert_that("abc").starts_with(_Str("z")), id="starts-with-text"),
    pytest.param(lambda: assert_that("abc").ends_with(_Str("z")), id="ends-with-text"),
    pytest.param(lambda: assert_that(_Bytes(b"abc")).starts_with(b"z"), id="starts-with-bytes"),
    pytest.param(lambda: assert_that(_Bytes(b"abc")).ends_with(b"z"), id="ends-with-bytes"),
    pytest.param(lambda: assert_that([1]).starts_with(_THING), id="starts-with-item"),
    pytest.param(lambda: assert_that([1]).ends_with(_THING), id="ends-with-item"),
    pytest.param(lambda: assert_that("abc").starts_with_ignoring_case(_Str("z")), id="starts-ignoring-case"),
    pytest.param(lambda: assert_that([1]).has_same_size_as(_List([1, 2])), id="same-size"),
    pytest.param(lambda: assert_that({"a": 1}).is_subset_of({"b": _Int(2)}), id="subset-of-mapping"),
    pytest.param(lambda: assert_that([1]).is_subset_of(_THING, 2), id="subset-of"),
    pytest.param(lambda: assert_that([_Int(-1)]).each(match.is_positive()), id="each-matcher"),
    pytest.param(lambda: assert_that([_Int(-1)]).each(lambda item: item > 0), id="each-predicate"),
    pytest.param(lambda: assert_that([_Int(1)]).none_satisfy(match.is_positive()), id="none-satisfy-matcher"),
    pytest.param(lambda: assert_that([_Int(1)]).none_satisfy(lambda item: item > 0), id="none-satisfy-predicate"),
    pytest.param(lambda: assert_that({"a": _Int(1)}).has_a(2), id="dynamic-has"),
    pytest.param(lambda: assert_that(1).satisfies(match.equal_to(_Int(2))), id="matcher-equal-to"),
    pytest.param(lambda: assert_that(1).satisfies(match.equal_to(_Int(2), strict_types=True)), id="matcher-strict"),
    pytest.param(lambda: assert_that(1).satisfies(match.greater_than(_Int(5))), id="matcher-greater-than"),
    pytest.param(lambda: assert_that(9).satisfies(match.less_than_or_equal_to(_Int(5))), id="matcher-at-most"),
    pytest.param(lambda: assert_that(1).satisfies(match.between(_Int(5), 6)), id="matcher-between"),
    pytest.param(lambda: assert_that(1.0).satisfies(match.close_to(_Float(5.0), 0.1)), id="matcher-close-to"),
    pytest.param(lambda: assert_that("abc").satisfies(match.contains_string(_Str("z"))), id="matcher-substring"),
    pytest.param(lambda: assert_that("abc").satisfies(match.starts_with(_Str("z"))), id="matcher-prefix"),
    pytest.param(lambda: assert_that("abc").satisfies(match.ends_with(_Str("z"))), id="matcher-suffix"),
    pytest.param(lambda: assert_that([1]).satisfies(match.is_subset_of(_List([2]))), id="matcher-superset"),
    pytest.param(
        lambda: assert_that(datetime.datetime(2022, 1, 1)).satisfies(match.is_before(_Moment(2021, 1, 1))),
        id="matcher-before",
    ),
    pytest.param(lambda: assert_that(_List([2, 1])).satisfies(match.is_sorted()), id="matcher-sorted"),
    pytest.param(lambda: assert_that(_List([1])).satisfies(match.contains_only(2)), id="matcher-contains-only"),
    pytest.param(lambda: assert_that(_List([1])).satisfies(match.structure({"k": 1})), id="matcher-not-a-mapping"),
    pytest.param(lambda: assert_that({"k": _Int(1)}).satisfies(match.structure({"k": 2})), id="matcher-structure"),
    pytest.param(lambda: assert_that({"k": 1}).satisfies(match.structure({"k": _Int(2)})), id="matcher-spec-value"),
]


@pytest.mark.parametrize("failing", _FAILURES)
def test_the_failure_survives_a_value_that_cannot_render_itself(failing):
    with pytest.raises(AssertionError) as caught:
        failing()
    assert_that(str(caught.value)).contains("unreprable")


def test_a_rejected_model_input_survives_it():
    pydantic = pytest.importorskip("pydantic")

    class Model(pydantic.BaseModel):
        name: str

    with pytest.raises(AssertionError) as caught:
        assert_conforms(_Dict(name=1), Model)
    assert_that(str(caught.value)).contains("unreprable _Dict")


def test_a_drifted_contract_snapshot_survives_it(tmp_path):
    with pytest.warns(UserWarning):
        assert_that({"a": 1}).matches_contract_snapshot(id="drift", path=str(tmp_path))
    with pytest.raises(AssertionError) as caught:
        assert_that(_Dict(b=1)).matches_contract_snapshot(id="drift", path=str(tmp_path))
    assert_that(str(caught.value)).contains("unreprable _Dict")


def test_an_unmet_snapshot_placeholder_survives_it(tmp_path):
    with pytest.warns(UserWarning):
        assert_that({"id": 1}).snapshot(id="held", path=str(tmp_path), placeholders={"id": match.is_positive()})
    with pytest.raises(AssertionError) as caught:
        assert_that({"id": _Int(-1)}).snapshot(id="held", path=str(tmp_path), placeholders={"id": match.is_positive()})
    assert_that(str(caught.value)).contains("unreprable _Int")


class TestARenderableValueReadsAsItAlwaysDid:
    """The guard changes nothing for a value that renders: each site keeps the spelling it always asked for."""

    def test_an_interpolated_operand_is_formatted_not_converted(self):
        with pytest.raises(AssertionError) as caught:
            assert_that(1).is_same_as(_Spelled())
        assert_that(str(caught.value)).is_equal_to("Expected <1> to be identical to <formatted>, but was not.")

    def test_a_converted_value_is_still_converted(self):
        spelled = _Spelled()
        with pytest.raises(AssertionError) as caught:
            assert_that(spelled).is_not_equal_to(spelled)
        assert_that(str(caught.value)).is_equal_to("Expected <str> to be not equal to <str>, but was.")

    def test_a_string_handed_back_by_format_is_not_formatted_again(self):
        with pytest.raises(AssertionError) as caught:
            assert_that(1).is_same_as(_HandsBackAString())
        assert_that(str(caught.value)).is_equal_to("Expected <1> to be identical to <handed>, but was not.")

    def test_a_value_refusing_only_format_falls_back_to_its_repr(self):
        with pytest.raises(AssertionError) as caught:
            assert_that(1).is_same_as(_OnlyFormatRefuses())
        assert_that(str(caught.value)).is_equal_to("Expected <1> to be identical to <repr>, but was not.")

    def test_items_render_as_the_tuple_printed_them(self):
        with pytest.raises(AssertionError) as caught:
            assert_that([1]).contains(1, _Spelled(), "a")
        assert_that(str(caught.value)).starts_with("Expected <[1]> to contain items <1, repr, 'a'>,")
