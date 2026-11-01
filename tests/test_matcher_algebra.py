"""The algebra matchers promise, held over every built-in matcher and values of every kind.

A matcher is compared through ``==`` inside structures and composed with ``&``, ``|`` and ``~``, so what it answers
has to obey the laws those spellings imply, on any value it is handed:

* it is total: it answers every value and raises on none, which ``==`` may not do;
* every spelling of one question agrees: ``matches``, ``evaluate().matched``, ``value == matcher``,
  ``matcher == value`` and ``value != matcher``;
* ``~~m`` answers as ``m``, ``not_(m)`` as ``~m``, ``ignore()`` is the identity of ``&`` and absorbs ``|``;
* ``all_of``/``any_of`` answer as ``&``/``|``, both De Morgan laws hold, ``&`` and ``|`` commute and associate;
* a failure explains itself, and a negation that fails names the value and what it unexpectedly matched.

Laws compare verdicts on the same value, never the matchers themselves: ``~~m == m`` would ask the overloaded ``==``.
"""

import datetime
import decimal
import fractions
import itertools
import uuid

from hypothesis import example, given, settings
from hypothesis import strategies as st

from assertpy import assert_that, match
from assertpy.errors import _safe_str

_DAY = datetime.timedelta(days=1)
_MOMENT = datetime.datetime(2026, 1, 1, 12)
_MATCHERS = {
    "all_of": match.all_of(match.greater_than(0), match.less_than(10)),
    "any_of": match.any_of(match.equal_to("a"), match.is_none()),
    "between": match.between(1, 5),
    "close_to": match.close_to(1.0, 0.5),
    "contains": match.contains(1),
    "contains_only": match.contains_only(1, 2),
    "contains_string": match.contains_string("a"),
    "each_item": match.each_item(match.is_positive()),
    "ends_with": match.ends_with("c"),
    "equal_to": match.equal_to(1),
    "equal_to_text": match.equal_to("a"),
    "equal_to_tolerance": match.equal_to(1.0, tolerance=0.1),
    "greater_than": match.greater_than(2),
    "greater_than_or_equal_to": match.greater_than_or_equal_to(2),
    "has_length": match.has_length(2),
    "has_property": match.has_property("real", match.equal_to(1)),
    "ignore": match.ignore(),
    "is_after": match.is_after(_MOMENT - _DAY),
    "is_before": match.is_before(_MOMENT + _DAY),
    "is_callable": match.is_callable(),
    "is_divisible_by": match.is_divisible_by(2),
    "is_empty": match.is_empty(),
    "is_even": match.is_even(),
    "is_falsy": match.is_falsy(),
    "is_in": match.is_in(1, "a", None),
    "is_instance_of": match.is_instance_of(int),
    "is_length": match.is_length(1),
    "is_negative": match.is_negative(),
    "is_non_empty_string": match.is_non_empty_string(),
    "is_none": match.is_none(),
    "is_not_empty": match.is_not_empty(),
    "is_not_none": match.is_not_none(),
    "is_odd": match.is_odd(),
    "is_positive": match.is_positive(),
    "is_sorted": match.is_sorted(),
    "is_subset_of": match.is_subset_of(1, 2, 3),
    "is_truthy": match.is_truthy(),
    "is_type_of": match.is_type_of(int),
    "is_uuid": match.is_uuid(),
    "is_zero": match.is_zero(),
    "less_than": match.less_than(2),
    "less_than_or_equal_to": match.less_than_or_equal_to(2),
    "matches_regex": match.matches_regex("^a"),
    "not_": match.not_(match.equal_to(1)),
    "starts_with": match.starts_with("a"),
    "structure": match.structure({"k": match.is_positive()}),
}
_VALUES = [
    None,
    True,
    False,
    0,
    1,
    2,
    -3,
    1.0,
    1.05,
    float("nan"),
    float("inf"),
    decimal.Decimal(1),
    decimal.Decimal("NaN"),
    fractions.Fraction(1, 2),
    3 + 4j,
    "",
    "a",
    "abc",
    b"abc",
    bytearray(b"a"),
    [],
    [1],
    [1, 2],
    [2, 1],
    [1, "a"],
    (1, 2),
    {1, 2},
    frozenset(),
    {},
    {"k": 1},
    {"k": -1},
    {"k": "x"},
    range(3),
    object(),
    len,
    str(uuid.UUID(int=1)),
    _MOMENT,
    datetime.date(2020, 1, 1),
]
_NAMES = sorted(_MATCHERS)
_VALUE_STRATEGY = st.one_of(
    st.sampled_from(_VALUES),
    st.integers(),
    st.floats(),
    st.text(max_size=5),
    st.lists(st.integers(-3, 3), max_size=4),
    st.dictionaries(st.sampled_from(["k", "x"]), st.integers(-2, 2), max_size=2),
)


def _verdict(matcher, value):
    """What *matcher* answers about *value*, as it answered it, or the kind of error it raised instead."""
    try:
        return matcher.matches(value)
    except Exception as e:
        return type(e).__name__


def _spellings_disagree(name, value):
    """Every law of one matcher on one value that it breaks, by name."""
    matcher = _MATCHERS[name]
    matched = _verdict(matcher, value)
    if type(matched) is not bool:
        return [f"answered {matched!r}"]
    broken = []
    evaluated = matcher.evaluate(value)
    if evaluated.matched is not matched:
        broken.append("evaluate")
    if not matched and not evaluated.mismatch:
        broken.append("an unexplained mismatch")
    if (
        (value == matcher) is not matched
        or (matcher == value) is not matched
        or (value != matcher) is not (not matched)
    ):
        broken.append("==")
    if _verdict(~~matcher, value) is not matched:
        broken.append("~~")
    if _verdict(match.not_(matcher), value) is not (not matched) or _verdict(~matcher, value) is not (not matched):
        broken.append("not_ and ~")
    if (
        _verdict(matcher & match.ignore(), value) is not matched
        or _verdict(match.ignore() & matcher, value) is not matched
    ):
        broken.append("ignore under &")
    if _verdict(matcher | match.ignore(), value) is not True or _verdict(match.ignore() | matcher, value) is not True:
        broken.append("ignore under |")
    if matched:
        said = f"<{_safe_str(value)}> unexpectedly matched {matcher.describe()}"
        broken.extend(
            "a negation that does not say what it unexpectedly matched"
            for negated in ((~matcher).evaluate(value), match.not_(matcher).evaluate(value))
            if negated.description != f"not {matcher.describe()}" or negated.mismatch != said
        )
    return broken


def _pair_disagrees(left, right, value):
    a, b = _MATCHERS[left], _MATCHERS[right]
    verdict_a, verdict_b = _verdict(a, value), _verdict(b, value)
    if type(verdict_a) is not bool or type(verdict_b) is not bool:
        return ["a part raised"]
    laws = {
        "all_of": (_verdict(match.all_of(a, b), value), verdict_a and verdict_b),
        "any_of": (_verdict(match.any_of(a, b), value), verdict_a or verdict_b),
        "&": (_verdict(a & b, value), verdict_a and verdict_b),
        "|": (_verdict(a | b, value), verdict_a or verdict_b),
        "De Morgan over &": (_verdict(~(a & b), value), _verdict(~a | ~b, value)),
        "De Morgan over |": (_verdict(~(a | b), value), _verdict(~a & ~b, value)),
        "& commutes": (_verdict(a & b, value), _verdict(b & a, value)),
        "| commutes": (_verdict(a | b, value), _verdict(b | a, value)),
    }
    return [law for law, (got, wanted) in laws.items() if type(got) is not bool or got is not wanted]


class TestEveryMatcherOnEveryValue:
    def test_each_matcher_keeps_its_own_laws(self):
        broken = {
            (name, repr(value)): laws
            for name, value in itertools.product(_NAMES, _VALUES)
            if (laws := _spellings_disagree(name, value))
        }
        assert_that(broken).is_empty()

    def test_every_pair_keeps_the_laws_of_its_composition(self):
        broken = {
            (left, right, repr(value)): laws
            for left, right in itertools.product(_NAMES, repeat=2)
            for value in _VALUES
            if (laws := _pair_disagrees(left, right, value))
        }
        assert_that(broken).is_empty()


class TestOnValuesNobodyChose:
    @settings(deadline=None, max_examples=300)
    @given(st.sampled_from(_NAMES), _VALUE_STRATEGY)
    @example("equal_to_tolerance", float("nan"))
    @example("structure", {"k": -1})
    def test_a_matcher_keeps_its_own_laws(self, name, value):
        assert_that(_spellings_disagree(name, value)).is_empty()

    @settings(deadline=None, max_examples=300)
    @given(st.sampled_from(_NAMES), st.sampled_from(_NAMES), st.sampled_from(_NAMES), _VALUE_STRATEGY)
    @example("is_positive", "is_even", "less_than", 4)
    def test_a_composition_keeps_its_laws_and_associates(self, left, middle, right, value):
        a, b, c = _MATCHERS[left], _MATCHERS[middle], _MATCHERS[right]
        assert_that(_pair_disagrees(left, middle, value)).is_empty()
        for grouped_left, grouped_right in (((a & b) & c, a & (b & c)), ((a | b) | c, a | (b | c))):
            answers = (_verdict(grouped_left, value), _verdict(grouped_right, value))
            assert_that([type(answer) for answer in answers]).is_equal_to([bool, bool])
            assert_that(answers[0]).is_same_as(answers[1])
