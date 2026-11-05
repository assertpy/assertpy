"""A matcher asked about a one-shot iterator answers alike wherever it is asked.

`satisfies()` used to drain the value into a list before any matcher saw it, so `match.is_instance_of(list)`
passed on an iterator and `match.is_instance_of(Iterator)` failed, while the same matcher asked directly, inside a
structure, over the items of a collection or as the builder's own `is_instance_of` answered the other way.  A
composite picked what to drain by whether a child had its own `evaluate()`, which a type check can have too.

A matcher now says whether it reads the items of a value or asks about the value itself, and every place that
hands it a value goes by that: the items, read once and shared, or the value as it is.
"""

from __future__ import annotations

import datetime
import functools
import itertools
from collections.abc import Iterator

import pytest

import assertpy._matcher_impls as _impls
from assertpy import AssertionFailure, BaseMatcher, MatchResult, assert_that, match


class _Counting:
    """Its own iterator over a few items, counting how many it has handed out."""

    def __init__(self, items=(1, 2, 3)):
        self.left = list(items)
        self.taken = 0

    def __iter__(self):
        return self

    def __next__(self):
        if not self.left:
            raise StopIteration
        self.taken += 1
        return self.left.pop(0)


_NOW = datetime.datetime.now()

_BUILT = {
    "is_none": match.is_none(),
    "html_equal_to": match.html_equal_to("<p>a</p>"),
    "is_not_none": match.is_not_none(),
    "is_instance_of(list)": match.is_instance_of(list),
    "is_instance_of(Iterator)": match.is_instance_of(Iterator),
    "is_type_of(list)": match.is_type_of(list),
    "is_truthy": match.is_truthy(),
    "is_falsy": match.is_falsy(),
    "is_callable": match.is_callable(),
    "has_length(3)": match.has_length(3),
    "is_empty": match.is_empty(),
    "is_not_empty": match.is_not_empty(),
    "equal_to([1, 2, 3])": match.equal_to([1, 2, 3]),
    "equal_to with tolerance": match.equal_to([1, 2, 3], tolerance=0.5),
    "is_in": match.is_in([1, 2, 3], 4),
    "has_property(__next__)": match.has_property("__next__"),
    "greater_than": match.greater_than(0),
    "greater_than_or_equal_to": match.greater_than_or_equal_to(0),
    "less_than": match.less_than(0),
    "less_than_or_equal_to": match.less_than_or_equal_to(0),
    "between": match.between(0, 9),
    "close_to": match.close_to(1, 0.5),
    "is_positive": match.is_positive(),
    "is_negative": match.is_negative(),
    "is_zero": match.is_zero(),
    "is_even": match.is_even(),
    "is_odd": match.is_odd(),
    "is_divisible_by": match.is_divisible_by(2),
    "contains_string": match.contains_string("a"),
    "matches_regex": match.matches_regex("a"),
    "starts_with": match.starts_with("a"),
    "ends_with": match.ends_with("a"),
    "ignore": match.ignore(),
    "is_uuid": match.is_uuid(),
    "is_non_empty_string": match.is_non_empty_string(),
    "is_now": match.is_now(),
    "is_before": match.is_before(_NOW),
    "is_after": match.is_after(_NOW),
    "structure": match.structure({"a": 1}),
    "contains": match.contains(2),
    "contains_only": match.contains_only(1, 2, 3),
    "is_subset_of": match.is_subset_of([1, 2, 3, 4]),
    "is_sorted": match.is_sorted(),
    "each_item": match.each_item(match.greater_than(0)),
}

_WALKERS = frozenset(
    {
        _impls.ContainsMatcher,
        _impls.ContainsOnlyMatcher,
        _impls.IsSubsetOfMatcher,
        _impls.IsSortedMatcher,
        _impls.EachMatcher,
    }
)


def _verdict(ask):
    try:
        return bool(ask())
    except AssertionFailure:
        return False


def _asked_everywhere(matcher, items):
    """The verdict of every place that hands *matcher* a value, each over a fresh one-shot iterator."""
    return _everywhere(matcher, lambda: iter(list(items)))


def _everywhere(matcher, fresh):
    """The verdict of every place that hands *matcher* a value, each over a value *fresh* makes."""
    never = match.is_none()
    return {
        "satisfies": _verdict(lambda: assert_that(fresh()).satisfies(matcher)),
        "check": assert_that(fresh()).check().satisfies(matcher).passed,
        "matches": _verdict(lambda: matcher.matches(fresh())),
        "evaluate": matcher.evaluate(fresh()).matched,
        "and": _verdict(lambda: (matcher & match.is_not_none()).matches(fresh())),
        "satisfies and": _verdict(lambda: assert_that(fresh()).satisfies(match.is_not_none() & matcher)),
        "nested": _verdict(lambda: (match.is_not_none() & (matcher | never)).matches(fresh())),
        "satisfies nested": _verdict(lambda: assert_that(fresh()).satisfies(match.is_not_none() & (never | matcher))),
        "not not": _verdict(lambda: (~~matcher).matches(fresh())),
        "structure": _verdict(lambda: assert_that({"a": fresh()}).matches_structure({"a": matcher})),
        "all_satisfy": _verdict(lambda: assert_that([fresh()]).all_satisfy(matcher)),
    }


class TestEveryPlaceAsksTheSameQuestion:
    @pytest.mark.parametrize("items", [(1, 2, 3), ()], ids=["three", "none"])
    @pytest.mark.parametrize("name", list(_BUILT))
    def test_every_entry_point_answers_alike(self, name, items):
        answers = _asked_everywhere(_BUILT[name], items)
        assert_that(set(answers.values())).described_as(f"{name} over {items}: {answers}").is_length(1)

    def test_a_type_check_is_asked_about_the_iterator(self):
        assert_that(iter([1, 2, 3])).satisfies(match.is_instance_of(Iterator)).satisfies(~match.is_instance_of(list))
        assert_that(assert_that(iter([1])).check().satisfies(match.is_type_of(list)).passed).is_false()

    def test_a_length_is_asked_of_the_iterator_which_has_none(self):
        with pytest.raises(AssertionFailure) as failure:
            assert_that(iter([1, 2, 3])).satisfies(match.has_length(3))
        assert_that(str(failure.value)).contains("which has no length")

    def test_after_an_earlier_link_a_type_check_leaves_the_rest_to_the_next_one(self):
        chain = assert_that(iter([1, 2, 3])).starts_with(1).satisfies(match.is_instance_of(Iterator))
        chain.contains(3).satisfies(match.contains(2))

    def test_an_endless_value_is_answered_by_an_alternative_that_needs_none_of_it(self):
        assert_that(itertools.count()).satisfies(match.is_instance_of(Iterator) | match.contains(5))
        assert_that((match.is_instance_of(Iterator) | match.contains(5)).matches(itertools.count())).is_true()


class TestABuiltInTypeCheckTakesNothing:
    """Handed the iterator without the guard a predicate gets, which is sound only if it reads none of it."""

    @pytest.mark.parametrize(
        "name", [name for name, matcher in _BUILT.items() if isinstance(matcher, _impls._OfTheValueItself)]
    )
    def test_no_item_is_taken(self, name):
        matcher = _BUILT[name]
        for ask in (matcher.matches, matcher.evaluate, matcher.describe_mismatch):
            value = _Counting()
            ask(value)
            assert_that(value.taken).described_as(f"{name}.{ask.__name__}").is_zero()

    def test_every_matcher_class_says_which_it_reads(self):
        classes = {
            kind
            for kind in vars(_impls).values()
            if isinstance(kind, type) and issubclass(kind, BaseMatcher) and kind.__module__ == _impls.__name__
        }
        readers = {kind for kind in classes if issubclass(kind, _impls._OfTheValueItself)} - {_impls._OfTheValueItself}
        composites = set(_impls._COMPOSITES)
        assert_that(classes - readers - composites - {BaseMatcher, _impls._OfTheValueItself}).is_equal_to(set(_WALKERS))
        assert_that({type(matcher) for matcher in _BUILT.values()}).is_equal_to(readers | _WALKERS)
        assert_that(all(kind.reads_items for kind in _WALKERS)).is_true()


class _OwnEquality:
    """A value whose `__eq__` answers every operand, a matcher included, rather than leaving it to the other side."""

    def __eq__(self, other):
        return isinstance(other, _OwnEquality)

    __hash__ = object.__hash__

    def __repr__(self):
        return "own"


class _Deferring:
    """A value whose `__eq__` leaves a foreign operand to the other side."""

    def __eq__(self, other):
        return True if isinstance(other, _Deferring) else NotImplemented

    __hash__ = object.__hash__

    def __repr__(self):
        return "deferring"


class _Yes:
    """A matcher by its three methods alone, with no `__eq__` of its own: `==` against it is identity."""

    def matches(self, value):
        return True

    def describe(self):
        return "anything"

    def describe_mismatch(self, value):
        return "never"


class _HoldsTwo:
    """No matcher: equal to an iterable that holds 2, read through its own `__eq__`."""

    def __eq__(self, other):
        return 2 in other

    __hash__ = object.__hash__


class _IsAnIterator(BaseMatcher):
    """A matcher of somebody else's that asks about the value itself, and says so."""

    reads_items = False

    def describe(self):
        return "an iterator"

    def evaluate(self, value):
        held = isinstance(value, Iterator)
        return MatchResult(matched=held, description=self.describe(), mismatch="" if held else f"was {value!r}")


class _SaysNothing(_IsAnIterator):
    """The same check left at the default, which hands it the items, as `satisfies()` always did."""

    reads_items = True


class TestAMatcherOfSomebodyElses:
    def test_one_that_says_it_asks_about_the_value_is_handed_the_value_everywhere(self):
        answers = _asked_everywhere(_IsAnIterator(), (1, 2, 3))
        assert_that(set(answers.values())).described_as(str(answers)).is_equal_to({True})

    def test_one_that_says_nothing_is_handed_the_items_wherever_it_shares_the_value(self):
        assert_that(assert_that(iter([1])).check().satisfies(_SaysNothing()).passed).is_false()
        assert_that((_SaysNothing() & match.is_not_none()).matches(iter([1]))).is_false()
        assert_that(_SaysNothing().matches(iter([1]))).is_true()

    def test_one_that_asks_about_the_value_after_a_part_was_read_stops_the_links_after_it(self):
        chain = assert_that(iter([1, 2, 3])).starts_with(1).satisfies(_IsAnIterator())
        with pytest.raises(TypeError, match="a predicate was handed after a part of it was read"):
            chain.contains(3)


_HANDING_ON = {
    "walker": (lambda: match.equal_to(match.contains(2)), (True, False)),
    "composite": (lambda: match.equal_to(match.all_of(match.contains(2))), (True, False)),
    "negated": (lambda: match.not_(match.equal_to(match.contains(9))), (True, True)),
    "among": (lambda: match.is_in(match.contains(2)), (True, False)),
    "comparator": (
        lambda: match.equal_to([2], comparators={type(iter([])): lambda actual, expected: 2 in actual}),
        (True, False),
    ),
    "operand": (lambda: match.equal_to(_HoldsTwo()), (True, False)),
    "operand among": (lambda: match.is_in(_HoldsTwo()), (True, False)),
}
"""Built-in matchers that hand a value on through `==` to code of the caller's, and what they say over 1, 2, 3 and
over nothing."""


class TestEqualityToAMatcherIsItsEquality:
    """`equal_to(m)` is `value == m` wherever it is asked: the value's own `__eq__`, then `BaseMatcher.__eq__`."""

    @pytest.mark.parametrize(
        "value",
        [_OwnEquality(), _Deferring(), 5, "text", None, [1]],
        ids=["own", "deferring", "int", "str", "none", "list"],
    )
    @pytest.mark.parametrize(
        "inner",
        [match.is_not_none(), match.all_of(match.is_not_none()), _Yes(), match.is_instance_of(_OwnEquality)],
        ids=["leaf", "composite", "duck", "type"],
    )
    def test_every_entry_point_answers_as_equality_does(self, value, inner):
        answers = _everywhere(match.equal_to(inner), lambda: value)
        assert_that(answers).described_as(f"{value!r} == {inner!r}").is_equal_to(
            dict.fromkeys(answers, bool(value == inner))
        )

    @pytest.mark.parametrize(("build", "said"), list(_HANDING_ON.values()), ids=list(_HANDING_ON))
    def test_over_a_fresh_one_shot_value_every_entry_point_answers_as_said(self, build, said):
        for items, verdict in zip(((1, 2, 3), ()), said, strict=True):
            answers = _asked_everywhere(build(), items)
            assert_that(answers).described_as(f"over {items}").is_equal_to(dict.fromkeys(answers, verdict))

    @pytest.mark.parametrize(("build", "said"), list(_HANDING_ON.values()), ids=list(_HANDING_ON))
    def test_over_a_one_shot_value_it_is_handed_the_value_as_a_predicate_is(self, build, said):
        chain = assert_that(iter([1, 2, 3])).starts_with(1).satisfies(build())
        with pytest.raises(TypeError, match="a predicate was handed after a part of it was read"):
            chain.contains(3)

    def test_equality_to_a_matcher_of_the_value_itself_is_handed_the_value(self):
        assert_that(match.equal_to(match.is_instance_of(Iterator)).matches(iter([1]))).is_true()
        assert_that(
            assert_that(iter([1])).check().satisfies(match.equal_to(match.is_instance_of(Iterator))).passed
        ).is_true()

    def test_around_a_composite_it_answers_as_the_composite_does(self):
        built = match.equal_to(match.all_of(match.is_instance_of(Iterator)))
        assert_that(built.matches(iter([1]))).is_true()
        assert_that(assert_that(iter([1])).check().satisfies(built).passed).is_true()

    def test_around_somebody_else_s_matcher_the_guard_holds_after_a_read(self):
        chain = assert_that(iter([1, 2, 3])).starts_with(1).satisfies(match.equal_to(_IsAnIterator()))
        with pytest.raises(TypeError, match="a predicate was handed after a part of it was read"):
            chain.contains(3)

    def test_a_subclass_is_asked_as_it_answers(self):
        class Never(_impls.EqualToMatcher):
            def matches(self, value):
                return False

        built = Never(match.is_not_none())
        assert_that(built.matches(5)).is_false()
        assert_that(assert_that(5).check().satisfies(built).passed).is_false()
        assert_that(assert_that(5).check().satisfies(match.all_of(built)).passed).is_false()

    @pytest.mark.parametrize("kind", [_impls.AllOfMatcher, _impls.AnyOfMatcher])
    def test_a_composite_subclass_is_asked_as_it_answers(self, kind):
        class Never(kind):
            def matches(self, value):
                return False

        class Refusing(kind):
            def evaluate(self, value):
                return MatchResult(matched=False, description="refusing", mismatch="always")

        never = Never(match.is_not_none())
        assert_that(never.matches(5)).is_false()
        assert_that(match.any_of(never).matches(5)).is_false()
        # an `evaluate()` overridden alone answers wherever a result is asked for, as a leaf's does
        for built in (never, Refusing(match.is_not_none())):
            assert_that(assert_that(5).check().satisfies(built).passed).is_false()
            assert_that(assert_that(5).check().satisfies(match.all_of(built)).passed).is_false()

    @pytest.mark.parametrize("kind", [_impls.AllOfMatcher, _impls.AnyOfMatcher])
    def test_a_composite_subclass_that_overrides_nothing_is_a_composite(self, kind):
        class Derived(kind):
            pass

        def build():
            return Derived(match.is_instance_of(Iterator))

        assert_that(build().matches(iter([1]))).is_true()
        assert_that(match.any_of(build()).matches(iter([1]))).is_true()
        assert_that(assert_that(iter([1])).check().satisfies(build()).passed).is_true()
        assert_that(assert_that(iter([1])).check().satisfies(match.all_of(build())).passed).is_true()

    @pytest.mark.parametrize("kind", [_impls.AllOfMatcher, _impls.AnyOfMatcher, _impls.NotMatcher])
    def test_a_wrapped_override_is_an_override(self, kind):
        class Wrapped(kind):
            @functools.wraps(kind.matches)
            def matches(self, value):
                return False

        built = Wrapped(match.is_none() if kind is _impls.NotMatcher else match.is_not_none())
        assert_that(match.any_of(built).matches(5)).is_false()
        assert_that(assert_that(5).check().satisfies(match.all_of(built)).passed).is_false()

    def test_a_built_in_object_reader_s_subclass_gets_the_guard(self):
        class Consuming(_impls.IsNotNoneMatcher):
            def matches(self, value):
                next(value, None)
                return True

        chain = assert_that(iter([1, 2, 3])).starts_with(1).satisfies(Consuming())
        with pytest.raises(TypeError, match="a predicate was handed after a part of it was read"):
            chain.contains(2)

    def test_a_negation_subclass_is_asked_as_it_answers(self):
        class Never(_impls.NotMatcher):
            def matches(self, value):
                return False

        built = Never(match.is_none())
        assert_that(match.any_of(built).matches(5)).is_false()
        assert_that(assert_that(5).check().satisfies(match.all_of(built)).passed).is_false()


class _Holding(BaseMatcher):
    """A matcher of somebody else's that walks the value through `matches()` alone, and says nothing."""

    def __init__(self, item):
        self.item = item

    def describe(self):
        return f"holding <{self.item}>"

    def matches(self, value):
        return self.item in value


class TestWalkersWithNoEvaluateOfTheirOwnShareOneRead:
    """A composite of them is asked by verdict alone, and every child, nested ones too, reads the same items."""

    @pytest.mark.parametrize(
        "composite",
        [_Holding(1) & _Holding(3), _Holding(1) & (_Holding(9) | _Holding(3)), ~_Holding(9) & _Holding(3)],
        ids=["side-by-side", "nested", "negated"],
    )
    def test_the_second_child_sees_what_the_first_read(self, composite):
        assert_that(composite.matches(iter([1, 2, 3]))).is_true()
        assert_that(assert_that(iter([1, 2, 3])).check().satisfies(composite).passed).is_true()
