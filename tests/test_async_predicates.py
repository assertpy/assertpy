"""A coroutine handed to an assertion as a predicate, which used to read as a verdict.

A coroutine object is truthy and an unawaited one never runs, so `async def` predicates made the
assertions that read them pass whatever the value was.  Measured before the fix: ten of the thirteen
places that take a callable went green on a predicate that always answers `False`.

The refusal is asked of the answer rather than of the callable, so a lambda handing one back is caught
as well, and it carries its own exception type because several assertions catch `TypeError` from a probe
on purpose and would otherwise report the mistake as an ordinary non-match.

The same mistake reaches the *value* side, and this file covers that too: `assert_that(fetch())` on a
forgotten `await` used to satisfy `is_true()` whatever awaiting it would have answered.

The neighbouring shapes live with their own subjects rather than here: a value whose `__bool__` or
`__eq__` raises in `test_equals.py` and `test_evaluation_core.py`, one whose `repr` raises in
`test_refusals.py`, and an awaitable handed to `eventually_sync` as a probe in `test_sync_eventually.py`.
"""

from __future__ import annotations

import warnings

import pytest

from assertpy import assert_that, match
from assertpy._engine._require import CoroutineVerdictError
from assertpy.matchers import BaseMatcher, Matcher


async def _never(value: object, *rest: object) -> bool:
    return False


_SITES = {
    "satisfies": lambda predicate: assert_that(1).satisfies(predicate),
    "each": lambda predicate: assert_that([1]).each(predicate),
    "all_satisfy": lambda predicate: assert_that([1]).all_satisfy(predicate),
    "any_satisfy": lambda predicate: assert_that([1]).any_satisfy(predicate),
    "none_satisfy": lambda predicate: assert_that([1]).none_satisfy(predicate),
    "filtered_on": lambda predicate: assert_that([1]).filtered_on(predicate),
    "extracting filter": lambda predicate: assert_that([{"a": 1}]).extracting("a", filter=predicate),
    "zip_satisfies": lambda predicate: assert_that([1]).zip_satisfies([1], predicate),
    "satisfies_exactly": lambda predicate: assert_that([1]).satisfies_exactly(predicate),
    "satisfies_exactly_in_any_order": lambda predicate: assert_that([1]).satisfies_exactly_in_any_order(predicate),
    # a comparator asks about a pair, and reaches the same mistake through three different entry points
    "is_equal_to comparator": lambda predicate: assert_that(1).is_equal_to(2, comparators={int: predicate}),
    "match.equal_to comparator": lambda predicate: assert_that(1).satisfies(
        match.equal_to(2, comparators={int: predicate})
    ),
}


def _duck_matcher() -> object:
    """A matcher by the protocol's own reading, with an `async def matches`.

    Read off the protocol rather than guessed: a first probe left out `describe_mismatch`, so the object
    was not a matcher at all and the refusal it got was about that instead.

    Walked rather than taken from `__protocol_attrs__`, which arrived in 3.12 and this suite runs 3.10.
    """
    declared = {
        name
        for base in Matcher.__mro__
        for name, member in vars(base).items()
        if not name.startswith("_") and callable(member)
    }
    members = {name: (lambda self, *args: "never") for name in declared}

    async def matches(self: object, value: object) -> bool:
        return False

    members["matches"] = matches
    return type("DuckMatcher", (), members)()


_MATCHER_SITES = {
    "satisfies": lambda matcher: assert_that(1).satisfies(matcher),
    "each": lambda matcher: assert_that([1]).each(matcher),
    "all_satisfy": lambda matcher: assert_that([1]).all_satisfy(matcher),
    "any_satisfy": lambda matcher: assert_that([1]).any_satisfy(matcher),
    "satisfies_exactly": lambda matcher: assert_that([1]).satisfies_exactly(matcher),
    "satisfies_exactly_in_any_order": lambda matcher: assert_that([1]).satisfies_exactly_in_any_order(matcher),
    "contains": lambda matcher: assert_that([1]).contains(matcher),
    "matches_structure": lambda matcher: assert_that({"x": 1}).matches_structure({"x": matcher}),
    # the combinators the first sweep missed: each truth-tests the inner matcher before the outer read
    "composed with &": lambda matcher: assert_that(1).satisfies(match.is_positive() & matcher),
    "composed with |": lambda matcher: assert_that(1).satisfies(match.is_negative() | matcher),
    "each_item": lambda matcher: assert_that([1]).satisfies(match.each_item(matcher)),
    "has_property": lambda matcher: assert_that(1).satisfies(match.has_property("real", matcher)),
}


@pytest.mark.parametrize("call", _MATCHER_SITES.values(), ids=_MATCHER_SITES.keys())
def test_a_matcher_whose_verdict_is_a_coroutine_is_refused(call) -> None:
    """The same mistake wearing the other shape, and it reaches further than the callable one."""
    with pytest.raises(CoroutineVerdictError):
        call(_duck_matcher())


def test_equality_against_a_matcher_refuses_rather_than_answering_no() -> None:
    """`==` on a matcher must never raise, which is why it swallows a probe's `TypeError`.

    That is right for an operand the predicate cannot judge and wrong for one that was never awaited,
    so the refusal travels through while the rest still reads as "no match".  Reached through `==`
    rather than through an assertion, because a matcher is compared that way as a dict value.
    """

    class Never(BaseMatcher):
        async def matches(self, value: object) -> bool:  # ty: ignore[invalid-return-type]  # the shape under test
            return False

        def describe(self) -> str:
            return "never"

    with pytest.raises(CoroutineVerdictError):
        _ = Never() == 1
    with pytest.raises(CoroutineVerdictError):
        assert_that(1).satisfies(~Never())


def test_a_comparator_nested_inside_a_structure_is_refused(call=None) -> None:
    """Two traps read `TypeError` from a matcher as a mismatch, and swallowed the refusal with it."""
    with pytest.raises(CoroutineVerdictError):
        assert_that({"x": 1}).matches_structure({"x": match.equal_to(2, comparators={int: _never})})


@pytest.mark.parametrize("call", _SITES.values(), ids=_SITES.keys())
def test_a_coroutine_is_refused_rather_than_read_as_true(call) -> None:
    with pytest.raises(CoroutineVerdictError) as refusal:
        call(_never)
    assert_that(str(refusal.value)).described_as("the refusal").contains(
        "handed back a coroutine", "await the call yourself"
    )


def test_a_callable_that_merely_returns_one_is_caught_too() -> None:
    """Asked of the answer, not of the callable: `iscoroutinefunction` would miss this shape."""
    with pytest.raises(CoroutineVerdictError):
        assert_that(1).satisfies(lambda value: _never(value))


def test_the_refusal_leaves_no_unawaited_coroutine_behind() -> None:
    """Closing it is the difference between one clear refusal and a refusal plus a RuntimeWarning."""
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        with pytest.raises(CoroutineVerdictError):
            assert_that([1]).each(_never)


def test_an_ordinary_type_error_from_a_predicate_still_means_no_match() -> None:
    """The behaviour the dedicated type exists to protect.

    `satisfies_exactly_in_any_order` catches `TypeError` from each probe on purpose, because a predicate
    may be unable to judge some item of a mixed collection.  That must keep working, and only the
    coroutine refusal may travel through it.
    """

    def only_sized(value: object) -> bool:
        return len(value) > 0  # ty: ignore[invalid-argument-type]  # TypeError on the number

    def only_number(value: object) -> bool:
        return value > 0  # ty: ignore[unsupported-operator]  # TypeError on the text

    assert_that(["ab", 1]).satisfies_exactly_in_any_order(only_sized, only_number)


_TRUTH_READS = {"is_true": lambda builder: builder.is_true(), "is_false": lambda builder: builder.is_false()}


@pytest.mark.parametrize("read", _TRUTH_READS.values(), ids=_TRUTH_READS.keys())
def test_a_coroutine_handed_in_as_the_value_is_refused(read) -> None:
    """The predicate guard read the answer; nothing read the value the assertion was built on.

    Every coroutine is truthy, so `assert_that(fetch()).is_true()` held whatever `await fetch()` would
    have answered, and the mirror refused for the same wrong reason.  `eventually_sync` already refuses
    an awaitable probe by name, so one API over the same mistake was already a usage error.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        with pytest.raises(CoroutineVerdictError) as refusal:
            read(assert_that(_never(1)))
    assert_that(str(refusal.value)).contains("handed back a coroutine", "await the call yourself")


def test_an_assertion_that_is_answering_about_the_object_is_left_alone() -> None:
    """Only the truthiness reads are guarded, because only they cannot mean anything about a coroutine.

    `is_callable()` and `is_iterable()` answer correctly: a coroutine is neither.  Guarding those would
    refuse a test that is deliberately asserting about the object it was handed.
    """
    coroutine = _never(1)
    try:
        assert_that(coroutine).is_not_callable().is_not_iterable().is_not_none()
    finally:
        coroutine.close()
