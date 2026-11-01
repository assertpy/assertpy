"""Where a relation exists twice, the two spellings must not contradict each other.

Most relations in this library are written twice: once as a fluent assertion (`is_positive()`) and once
as a matcher (`match.is_positive()`), with separate implementations. Nothing made them agree, so this
does: every pair is run over values chosen to make it hold *and* fail, and the verdicts are compared.

The invariant is not "identical". It is narrower and it is the honest one:

* Where both sides answer, they answer the same.
* Where they differ, it is always the assertion refusing a call the matcher answers anyway. The answer
  is a non-match, except on an empty subject, where it is the vacuous one: `match.is_subset_of(0)`
  matches `{}`, while `assert_that({}).is_subset_of(0)` refuses the `0`.

Those are two contracts, not one bug. An assertion says "you handed me the wrong kind of thing, fix
your test"; a matcher is asked about every leaf of a structure and must be total, because
`BaseMatcher.__eq__` is what a structural spec compares with and `==` may not raise.
"""

import datetime

import pytest

from assertpy import BaseMatcher, assert_that, match

_NAN = float("nan")

# (name, build the matcher, call the fluent assertion, values that make it both hold and fail)
PAIRS = [
    ("is_equal_to", lambda: match.equal_to(5), lambda builder: builder.is_equal_to(5), [5, 5.0, True, 4, "5"]),
    (
        "is_greater_than",
        lambda: match.greater_than(3),
        lambda builder: builder.is_greater_than(3),
        [5, 3, 2, 3.5, True],
    ),
    (
        "is_greater_than_or_equal_to",
        lambda: match.greater_than_or_equal_to(3),
        lambda builder: builder.is_greater_than_or_equal_to(3),
        [5, 3, 2, 2.9],
    ),
    ("is_less_than", lambda: match.less_than(3), lambda builder: builder.is_less_than(3), [1, 3, 5, 2.9, False]),
    (
        "is_less_than_or_equal_to",
        lambda: match.less_than_or_equal_to(3),
        lambda builder: builder.is_less_than_or_equal_to(3),
        [1, 3, 5, 3.1],
    ),
    ("is_between", lambda: match.between(1, 9), lambda builder: builder.is_between(1, 9), [5, 1, 9, 0, 10, 1.5]),
    ("is_close_to", lambda: match.close_to(5, 1), lambda builder: builder.is_close_to(5, 1), [5, 5.5, 6, 6.1, 4]),
    ("is_positive", lambda: match.is_positive(), lambda builder: builder.is_positive(), [5, 0, -5, 0.1, True, False]),
    ("is_negative", lambda: match.is_negative(), lambda builder: builder.is_negative(), [-5, 0, 5, -0.1, False]),
    ("is_zero", lambda: match.is_zero(), lambda builder: builder.is_zero(), [0, 0.0, 1, -0.0, False]),
    ("is_even", lambda: match.is_even(), lambda builder: builder.is_even(), [2, 3, 0, -4]),
    ("is_odd", lambda: match.is_odd(), lambda builder: builder.is_odd(), [3, 2, -1, 0]),
    (
        "is_length",
        lambda: match.has_length(3),
        lambda builder: builder.is_length(3),
        ["abc", "ab", [1, 2, 3], {}, (1, 2, 3)],
    ),
    ("is_empty", lambda: match.is_empty(), lambda builder: builder.is_empty(), ["", "a", [], [1], {}, set()]),
    ("is_not_empty", lambda: match.is_not_empty(), lambda builder: builder.is_not_empty(), ["", "a", [], [1], {}]),
    ("is_true", lambda: match.is_truthy(), lambda builder: builder.is_true(), [True, False, 1, 0, "a", ""]),
    ("is_false", lambda: match.is_falsy(), lambda builder: builder.is_false(), [False, True, 0, 1, "", "a"]),
    ("is_none", lambda: match.is_none(), lambda builder: builder.is_none(), [None, 0, "", False]),
    ("is_not_none", lambda: match.is_not_none(), lambda builder: builder.is_not_none(), [None, 0, "", False]),
    (
        "is_instance_of",
        lambda: match.is_instance_of(int),
        lambda builder: builder.is_instance_of(int),
        [5, True, 5.0, "5"],
    ),
    ("is_type_of", lambda: match.is_type_of(int), lambda builder: builder.is_type_of(int), [5, True, 5.0]),
    ("is_callable", lambda: match.is_callable(), lambda builder: builder.is_callable(), [len, 5, str, "x"]),
    ("is_in", lambda: match.is_in(1, 2, 3), lambda builder: builder.is_in(1, 2, 3), [1, 4, True, 1.0]),
    # the same NaN is in a tuple holding it, a fresh one is not: `in` asks identity before `==`
    ("is_in-nan", lambda: match.is_in(_NAN, 2), lambda builder: builder.is_in(_NAN, 2), [_NAN, float("nan"), 2]),
    (
        "matches",
        lambda: match.matches_regex("a.c"),
        lambda builder: builder.matches("a.c"),
        ["abc", "axc", "ab", "xxabcxx"],
    ),
    (
        "is_before",
        lambda: match.is_before(datetime.datetime(2026, 6, 1)),
        lambda builder: builder.is_before(datetime.datetime(2026, 6, 1)),
        [datetime.datetime(2026, 1, 1), datetime.datetime(2026, 12, 1)],
    ),
]

# no relation ever contradicts its twin, including on a value neither was written for
HOSTILE = [None, "abc", "", 5, -5, 0, 2.5, True, False, [1, 2, 3], [], {}, {"a": 1}, (1, 2), {1, 2}, b"abc", len]


def _matcher_verdict(matcher, value):
    try:
        return "held" if matcher.matches(value) else "failed"
    except (TypeError, ValueError) as exc:
        return f"refused:{type(exc).__name__}"


def _fluent_verdict(call, value):
    try:
        call(assert_that(value))
    except AssertionError:
        return "failed"
    except (TypeError, ValueError) as exc:
        return f"refused:{type(exc).__name__}"
    return "held"


@pytest.mark.parametrize(("name", "build_matcher", "call_fluent", "corpus"), PAIRS, ids=[pair[0] for pair in PAIRS])
class TestARelationAnswersTheSameWhicheverWayItIsCalled:
    def test_neither_spelling_contradicts_the_other(self, name, build_matcher, call_fluent, corpus):
        for value in [*corpus, *HOSTILE]:
            matcher_verdict = _matcher_verdict(build_matcher(), value)
            fluent_verdict = _fluent_verdict(call_fluent, value)
            if "refused" in fluent_verdict and matcher_verdict == "failed":
                continue
            assert_that(matcher_verdict).described_as(f"{name} on {value!r}").is_equal_to(fluent_verdict)

    def test_the_corpus_makes_this_relation_both_hold_and_fail(self, name, build_matcher, call_fluent, corpus):
        # without this the test above passes on a corpus that never holds, which proves nothing
        verdicts = {_matcher_verdict(build_matcher(), value) for value in corpus}
        assert_that(verdicts).described_as(name).contains("held")
        assert_that(verdicts).described_as(name).contains("failed")

    def test_a_matcher_is_total(self, name, build_matcher, call_fluent, corpus):
        # `BaseMatcher.__eq__` is what a structural spec compares with, and `==` may not raise
        for value in [*corpus, *HOSTILE]:
            assert_that(_matcher_verdict(build_matcher(), value)).described_as(f"{name} on {value!r}").is_in(
                "held", "failed"
            )


class _Raising(BaseMatcher):
    def matches(self, value):
        raise TypeError("planted")

    def describe(self):
        return "planted"


class TestTheTotalityGuardCanFail:
    def test_a_matcher_that_raises_fails_it(self):
        # it compared with "refused" while the verdict read "refused:TypeError", so no matcher could fail it
        guard = TestARelationAnswersTheSameWhicheverWayItIsCalled().test_a_matcher_is_total
        assert_that(guard).raises(AssertionError).when_called_with("planted", _Raising, None, [1])


class TestAnEmptySubjectAgainstARefusedArgument:
    def test_the_matcher_holds_vacuously_where_the_assertion_refuses_the_argument(self):
        assert_that(match.is_subset_of(0).matches({})).is_true()
        with pytest.raises(TypeError, match="must be dict-like"):
            assert_that({}).is_subset_of(0)


class TestTheThreeMatchersThatAreNarrowerThanTheirNamesake:
    """`contains`, `starts_with` and `ends_with` are the one place where the two spellings genuinely
    mean different relations, and the parity list leaves them out on purpose rather than by omission.

    The fluent assertions are overloaded across types: on a sequence they are membership, first element
    and last element. The matchers are the string relations only, which `contains_string` says in its
    name and the other two do not.
    """

    def test_containment_is_membership_fluently_and_a_substring_as_a_matcher(self):
        assert_that(["ab", "c"]).contains("ab")
        assert_that(match.contains_string("ab").matches(["ab", "c"])).is_false()

    def test_starts_with_is_the_first_element_fluently_and_a_prefix_as_a_matcher(self):
        assert_that(["ab", "c"]).starts_with("ab")
        assert_that(match.starts_with("ab").matches(["ab", "c"])).is_false()

    def test_ends_with_is_the_last_element_fluently_and_a_suffix_as_a_matcher(self):
        assert_that(["a", "bc"]).ends_with("bc")
        assert_that(match.ends_with("bc").matches(["a", "bc"])).is_false()

    def test_on_a_string_all_three_agree(self):
        for matcher, call in (
            (match.contains_string("ab"), lambda builder: builder.contains("ab")),
            (match.starts_with("ab"), lambda builder: builder.starts_with("ab")),
            (match.ends_with("ab"), lambda builder: builder.ends_with("ab")),
        ):
            for value in ("ab", "xabx", "xx", ""):
                assert_that(_matcher_verdict(matcher, value)).described_as(f"{matcher!r} on {value!r}").is_equal_to(
                    _fluent_verdict(call, value)
                )


class TestOneRelationIsReachableUnderOneNameFromBothNamespaces:
    """A relation written twice should not be reachable under a different name depending on which
    namespace you came from. Length was: `is_length` on the builder, `has_length` in `match`."""

    def test_length_answers_to_both_names_in_the_matcher_namespace(self):
        assert_that(type(match.is_length(3))).is_equal_to(type(match.has_length(3)))

    def test_the_matcher_agrees_with_the_fluent_assertion_of_the_same_name(self):
        for value in ([1, 2, 3], [1, 2], "abc", {}, (1, 2, 3)):
            assert_that(_matcher_verdict(match.is_length(3), value)).described_as(f"on {value!r}").is_equal_to(
                _fluent_verdict(lambda builder: builder.is_length(3), value)
            )
