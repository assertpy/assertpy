"""Relations a type checker either catches or does not, one per line, each tagged with its own name.

Nothing here runs.  The body is never called, so the checkers read it and the interpreter does not: half
of these would raise at import, which is the point of writing them down.

`tests/test_typing_negative.py` reads the tags, runs ty, mypy and pyright over this file, and compares
what each one reported against `typing_negative_baseline.py`.  The file exists because the shipped
library advertises a typed surface, and nothing measured which incompatible operands actually reach the
checkers.  A gap nobody wrote down is a gap nobody can close on purpose.
"""

from __future__ import annotations

import datetime
import re
import warnings
from collections.abc import Callable, Mapping
from decimal import Decimal
from enum import Enum
from fractions import Fraction
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, TypedDict

import numpy
from typing_extensions import TypeIs

from assertpy import assert_that, match

if TYPE_CHECKING:
    from collections import Counter
    from collections.abc import Iterator

    from assertpy._engine._typing import _IterableAssertion, _RepeatableAssertion


class _Person:
    name: str = "x"


class _Colour(Enum):
    RED = "red"


class _Row(TypedDict):
    id: int
    name: str


class _Records(list[str]):
    """A container of one's own, which suites write more often than a bare `list`."""


class _OnlyFloat:
    """Convertible to a float and not a number: the gap between the capability and the runtime check."""

    def __float__(self) -> float:
        return 0.0


class _Base:
    """A base and its subclass, for the variance half of the membership matchers."""


class _Derived(_Base):
    pass


def _truthy_int(row: object) -> int:
    """A predicate answering with something other than `bool`, which the runtime reads for truth."""
    return 1


def _numpy_verdict(row: object) -> numpy.bool_:
    """The verdict a numpy comparison produces, and the reason the parameter is not typed `bool`."""
    return numpy.bool_(True)


def _is_int(value: object) -> TypeIs[int]:
    """A predicate that carries the type onward, which is how a json path chain narrows.

    The parameter is `object` rather than `Any` on purpose: `Any` would satisfy the signature of
    `satisfies` whether or not the two really fit, so the narrowing case would prove nothing.
    """
    return isinstance(value, int)


class _Probe:
    """Capable and callable at once, which the umbrella claims above the callable view."""

    def __iter__(self) -> Iterator[str]:
        return iter(("a",))

    def __call__(self) -> int:
        return 1


class _TakesAnyKey(Mapping[object, str]):
    """A row that reads a key without hashing it, mirrored in `test_property_based.py`.

    Both halves of the selector claim use this same shape on purpose: one proves the call type-checks,
    the other proves it runs, and naming two different rows would have proved neither together.
    """

    def __getitem__(self, key: object) -> str:
        return f"got {key!r}"

    def __iter__(self) -> Iterator[object]:
        return iter(())

    def __len__(self) -> int:
        return 0


class _ConvertibleRow(_TakesAnyKey):
    """The same row that converts, which is what a value the umbrella claims and can be asked `is_nan()`.

    `numpy.float64` reads as a `float` subclass and lands on the numeric view, so it measures that view
    and not this one: the umbrella's own float restriction needs a subject that reaches the umbrella.
    """

    def __float__(self) -> float:
        return 0.0


class _Walkable:
    """Capable by being iterable and by nothing else, which is the narrowest value the umbrella claims."""

    def __iter__(self) -> Iterator[str]:
        return iter(())


class _Ordered:
    """Ordered against anything and convertible to nothing, which both sides refuse alike."""

    def __lt__(self, other: object) -> bool:
        return True

    def __gt__(self, other: object) -> bool:
        return False


def _maybe_count() -> int | None:
    """An optional number, which `is_not_none()` has to land on the numeric view for the operand to be read."""
    return 1


def _maybe_counts() -> list[int] | None:
    return [1]


def _maybe_moment() -> datetime.datetime | None:
    return None


def _incompatible_operands() -> None:
    """Pairs where the two sides cannot be compared, whatever the runtime does with them."""
    assert_that([1, 2, 3]).contains("wrong type")  # case: contains-item-of-another-type
    assert_that(1).is_greater_than("wrong type")  # case: numeric-compared-to-text
    assert_that(_maybe_count()).is_not_none().is_greater_than("wrong type")  # case: narrowed-number-compared-to-text
    assert_that(_maybe_counts()).is_not_none().contains("wrong type")  # case: narrowed-items-of-another-type
    assert_that(_maybe_moment()).is_not_none().is_before("wrong type")  # case: narrowed-moment-before-text
    assert_that({"id": 1}).contains_key(3.14)  # case: mapping-key-of-another-type
    assert_that({"id": 1}).contains_value(object())  # case: mapping-value-of-another-type
    assert_that(1).is_between("a", "b")  # case: numeric-range-of-text
    assert_that([1, 2]).contains_exactly("a", "b")  # case: exact-items-of-another-type
    _keys: list[str] = ["a"]
    assert_that({"a": 1}).is_subset_of(_keys)  # case: mapping-subset-of-a-sequence
    assert_that("text").is_length("3")  # case: length-given-text
    assert_that(b"data").starts_with("text")  # case: bytes-prefixed-with-text
    assert_that(datetime.date(2026, 1, 1)).is_before(5)  # case: date-compared-to-number
    # the chronological seven take a `datetime` on both sides, and a plain date raises on the value
    assert_that(datetime.date(2026, 1, 1)).is_before(datetime.date(2026, 2, 1))  # case: date-ordered-as-a-datetime
    _day = datetime.datetime(2026, 1, 1).date()
    assert_that(_day).is_after(datetime.date(2020, 1, 1))  # case: date-taken-from-a-datetime
    # ordered against anything, convertible to nothing: checker and runtime agree to refuse it
    assert_that(1).is_greater_than(_Ordered())  # case: ordered-but-not-convertible
    assert_that(1).satisfies(match.starts_with("a"))  # case: matcher-for-another-type
    assert_that(1).satisfies(match.contains("x"))  # case: membership-matcher-for-a-scalar
    assert_that(1).satisfies(match.contains_only("x"))  # case: only-matcher-for-a-scalar
    assert_that(1).satisfies(match.is_subset_of(["x"]))  # case: subset-matcher-for-a-scalar
    assert_that(1).satisfies(match.is_sorted())  # case: sorted-matcher-for-a-scalar
    # a composition judges anything, as `BaseMatcher` declares it, so the binding of its parts does not reach it
    assert_that(1).satisfies(match.starts_with("a") & match.ends_with("z"))  # case: composed-text-matchers-for-a-number
    # the pairwise quantifier names both sides, so a character operation on the other element is refused
    assert_that("ab").zip_satisfies([1], lambda _character, number: number.isalpha())  # case: zip-reads-the-wrong-side
    # a pattern compiled from bytes is never found in a string, and the runtime refuses it as well
    assert_that("text").matches(re.compile(b"t"))  # case: text-matched-by-a-bytes-pattern
    match.matches_regex(re.compile(b"t"))  # case: regex-matcher-of-a-bytes-pattern
    # HTML is read in one of two whitespace modes, and the runtime refuses any other name
    assert_that("<p>").is_html_equal_to("<p>", whitespace="strict")  # case: html-equality-in-an-unknown-mode
    match.html_equal_to("<p>", whitespace="strict")  # case: html-matcher-in-an-unknown-mode


def _numbers_that_are_not_ordinary_numbers() -> None:
    """`complex` and `bool` are numbers whose assertion set is smaller, and the runtime already says so.

    Every line here raises `TypeError` when run. They used to type-check, because both resolved to the
    numeric protocol: `complex` is one, and `bool` is a subclass of `int`.
    """
    assert_that(1 + 2j).is_greater_than(1)  # case: complex-ordered
    assert_that(1 + 2j).is_positive()  # case: complex-signed
    assert_that(1 + 2j).is_nan()  # case: complex-nan
    assert_that(True).is_even()  # case: bool-parity
    assert_that(True).is_divisible_by(2)  # case: bool-divisibility
    assert_that(True).is_close_to(1, 0.5)  # case: bool-closeness
    assert_that(False).is_not_close_to(1, 0.5)  # case: bool-distance


def _chaining_must_not_widen_what_the_value_offers() -> None:
    """A step returns `Self`, so the protocol after it is the protocol before it.

    Worth stating rather than assuming: a chain that collapsed to the generic builder would hand back
    every assertion there is, and the narrowing would hold only for the first call.
    """
    assert_that(1 + 2j).is_not_zero().is_positive()  # case: complex-widened-by-chaining
    assert_that(True).is_greater_than(0).is_even()  # case: bool-widened-by-chaining
    # `.not_` used to accept what the protocol does not, the proxy resolving any name through `__getattr__`.
    # It is declared as the protocol it was reached from, refusing the same calls the un-negated chain does
    assert_that(1 + 2j).not_.is_greater_than(0)  # case: negation-widens-the-protocol
    # refused by all four now that the negation twins carry only what reaches a verdict, and the runtime
    # refuses it too: `described_as() only sets the failure description, so it cannot be negated`
    assert_that(1).not_.described_as("x")  # case: negation-allows-a-non-negatable-name
    # the twin substitutes what the view bound its base to, so the negated operand is held to `str`
    assert_that("abc").not_.contains_in_order(1)  # case: negated-element-of-another-type
    # the same rule on the surface a value no overload names by type gets, which lives in its own module
    assert_that(_Walkable()).not_.described_as("x")  # case: umbrella-negation-allows-a-non-negatable-name
    # neither half of an ordering matcher is typed: a wrong-type boundary and a foreign subject both fit
    assert_that(1).satisfies(match.greater_than("x"))  # case: ordering-matcher-takes-any-boundary
    assert_that("x").satisfies(match.greater_than(0))  # case: ordering-matcher-judges-any-subject


def _takes_repeats_of_derived(assertion: _RepeatableAssertion[_Derived]) -> None:
    """A caller that wants to ask about repeats of one exact element type."""


def _an_element_type_must_not_be_substitutable_by_a_wider_one(over_bases: _IterableAssertion[_Base]) -> None:
    """Why `_RepeatableAssertion` keeps an invariant element, against the checkers' own advice.

    Pyright asks for the parameter to be contravariant, because every method that names it takes it as an
    argument.  One of those arguments is `Matcher[_E]`, and `Matcher` is contravariant itself, so the two
    flips cancel and the parameter is in fact used covariantly.  Declaring it would make the line below
    legal, and a `Matcher[_Derived]` would then reach an assertion holding base instances.

    Measured before this case was written: with the parameter declared contravariant, both pyright and
    mypy accept this substitution silently, and the diagnostic recorded in `pyright_baseline.py` is what
    refusing it costs.
    """
    _takes_repeats_of_derived(over_bases)  # case: repeats-of-a-wider-element-substituted


def _a_json_path_lands_on_an_unknown_shape() -> None:
    """What the document holds at a path is not knowable statically, so the view offers no shape.

    Both of these used to type-check and raise at runtime: the mapping view offered `contains_key` on
    what turned out to be an `int`, and the sequence view offered `contains` on the same value.
    """
    assert_that({"id": 1}).at_json_path("$.id").is_positive()  # case: numeric-assertion-after-a-json-path
    assert_that({"id": 1}).at_json_path("$.id").contains_key("x")  # case: mapping-assertion-after-a-json-path
    assert_that([{"id": 1}]).at_json_path("$[0].id").contains(1)  # case: membership-assertion-after-a-json-path
    assert_that({"id": 1}).at_json_path("$.id").value.bit_length()  # case: reading-a-json-path-value-as-a-type
    rows = [{"id": 1}]
    assert_that(rows).extracting("id", filtr=lambda row: True)  # case: extracting-with-an-unknown-option
    assert_that(rows).extracting("id", filter=lambda left, right: True)  # case: extracting-filter-of-wrong-arity
    assert_that(rows).extracting("id", sort=lambda left, right: 0)  # case: extracting-sort-of-wrong-arity
    assert_that([1, 2]).filtered_on(lambda item: item.missing)  # case: predicate-reading-a-field-the-element-lacks
    assert_that({"a": 1}).filtered_on(lambda key: key.missing)  # case: mapping-predicate-reading-a-missing-field
    assert_that([1, 2]).any_satisfy(lambda item: item.missing)  # case: quantifier-reading-a-missing-field
    assert_that(b"ab").filtered_on(lambda byte: byte.missing)  # case: byte-predicate-reading-a-missing-field
    assert_that([1, 2]).each(lambda item: item.missing)  # case: each-reading-a-missing-field
    assert_that({"a": 1}).all_satisfy(lambda key: key.missing)  # case: all-satisfy-reading-a-missing-field
    assert_that(rows).extracting()  # case: extracting-with-no-selector


def _where_the_numeric_bound_is_wider_than_the_runtime() -> None:
    """`SupportsFloat` is the closest expressible approximation of what the runtime accepts, not a match.

    The runtime asks `isinstance(other, numbers.Number)`, and a numeric tower built on registration is
    invisible to a checker: `numpy.int64` is a `numbers.Number` at runtime and inherits nothing static.
    So the type says "anything that can produce a float", which lets through shapes the runtime then
    refuses by name.  A `bool` on either side of closeness is one: it is an `int` to a checker, and no
    annotation takes an `int` and leaves a `bool` out.

    They are recorded rather than fixed, because the error runs the other way from the one that hurt:
    letting through a value the runtime rejects with `given arg must be a number, but was <ndarray>` is
    a worse message, while rejecting `numpy.int64` outright was a broken test suite.
    """
    assert_that(1).is_greater_than(_OnlyFloat())  # case: convertible-but-not-a-number
    assert_that(1).is_greater_than(numpy.array([0, 1]))  # case: array-as-a-scalar-operand
    assert_that(5).is_close_to(5.5, True)  # case: bool-as-a-closeness-tolerance
    assert_that(2).is_close_to(True, 1)  # case: bool-as-a-closeness-operand
    # a datetime has no size for a relative tolerance to be a fraction of
    moment = datetime.datetime(2026, 1, 1)
    assert_that(moment).is_close_to(moment, rel=0.1)  # case: relative-closeness-of-moments


def _methods_that_do_not_fit_the_value() -> None:
    """Assertions the value's own type has no business answering."""
    assert_that(_Person()).is_positive()  # case: numeric-assertion-on-an-object
    assert_that(_Person()).is_zero()  # case: conversion-assertion-on-an-object
    # `is_nan` sits behind `numbers.Real` rather than `numbers.Number`, and no structural key tells the
    # two registrations apart, so the fallback declares none of that four and `Fraction` keeps the refusal
    assert_that(Fraction(3, 2)).is_not_nan()  # case: real-only-assertion-on-a-registered-number
    assert_that(_Person()).has_name("x")  # case: dynamic-attribute-on-an-object
    assert_that("text").is_close_to(1, 2)  # case: numeric-assertion-on-text

    assert_that(1).check().starts_with("x")  # case: text-assertion-on-a-number-through-check
    assert_that("text").check().is_positive()  # case: numeric-assertion-on-text-through-check
    assert_that([1]).check().contains_key("a")  # case: mapping-assertion-on-a-list-through-check
    assert_that(1).check().no_such_assertion()  # case: a-name-that-exists-nowhere-through-check
    assert_that({"id": 1}).has_id("no such comparison")  # case: dynamic-attribute-on-a-mapping

    # a predicate is handed the subject, so a view that knows its value knows what the lambda gets
    assert_that("text").satisfies(lambda item: item.upperr())  # case: predicate-reading-a-missing-string-method
    assert_that(7).satisfies(lambda item: item.bit_lengthh())  # case: predicate-reading-a-missing-numeric-method
    # a verdict asked of a value the builder holds: an element pivot used to land on the untyped proxy
    assert_that([1, 2]).first().check().starts_with("x")  # case: text-verdict-on-a-pivoted-number
    assert_that([1, 2]).first().check().contains_key("x")  # case: key-verdict-on-a-pivoted-number
    assert_that([1, 2]).first().check().not_.starts_with("x")  # case: negated-text-verdict-on-a-pivoted-number
    assert_that([{"a": 1}]).first().check().is_positive()  # case: numeric-verdict-on-a-pivoted-mapping
    assert_that(_a_number_or_a_text()).first().check().starts_with("a")  # case: text-verdict-on-a-pivoted-union
    assert_that([object()]).first().check().starts_with("a")  # case: text-verdict-on-a-pivoted-object
    assert_that(_either).eventually_sync().starts_with("a")  # case: text-assertion-on-a-polled-union
    # a pivot keeps the umbrella's type variable, which mypy does not hold to its bound: written with the bound
    # itself, ty read every polled pivot as `Unknown`
    assert_that(_a_thing).eventually_sync().first()  # case: pivot-on-a-polled-value-no-rung-claims

    # a member that is not a class, at the outer level and nested
    assert_that(object()).is_instance_of((int, "nope"))  # case: a-tuple-member-that-is-not-a-class
    assert_that(object()).is_instance_of((int, (str, "nope")))  # case: a-nested-member-that-is-not-a-class

    # a polling chain used to be `Any` from its first assertion, so none of these were read at all
    assert_that(_a_number).eventually_sync().starts_with("x")  # case: text-assertion-on-a-polled-number
    assert_that(_a_number).eventually_sync().is_close_to("x", 1)  # case: bad-operand-on-a-polled-number
    # a name no declaration lists comes off `__getattr__`, which keeps a dynamic assertion working
    assert_that(_a_number).eventually_sync().no_such_assertion()  # case: a-name-that-exists-nowhere-on-a-chain
    # a `str` is iterable, so it reaches the umbrella rung, as wide as a value the umbrella claims
    assert_that(_some_text).eventually_sync().is_positive()  # case: numeric-assertion-on-polled-text
    # two more of the same family, from other capabilities, so the table `poll_parity_baseline.py`
    # derives from the declarations is anchored to what the checkers actually accept
    assert_that(_a_mapping).eventually_sync().starts_with("x")  # case: text-assertion-on-a-polled-mapping
    assert_that(_some_bytes).eventually_sync().has_json_path("$.a")  # case: json-pivot-on-polled-bytes
    # a call with no expectation set, which raises.  Refused here because the rung asks the chain to hold
    # a callable and this one holds a number
    assert_that(_adder).eventually_sync().when_called_with(1, 2)  # case: called-with-on-a-chain-over-a-number
    # the same call where the chain does hold a callable, refused because the chain declares the name as
    # a refusal and only what `raises()` and the rest hand back carries the call
    assert_that(_a_factory).eventually_sync().when_called_with()  # case: called-with-on-a-chain-over-a-callable
    assert_that(_a_factory).eventually().when_called_with()  # case: called-with-on-an-async-chain
    # over a callable whose parameters are written out all four refuse it: mypy reads `assert_that()` over a
    # probe returning `Callable[..., int]` as `Any`, and the two above are silent for it from there on
    assert_that(_a_closed_factory).eventually_sync().when_called_with()  # case: called-with-on-a-closed-callable
    assert_that(_a_closed_factory).eventually().when_called_with()  # case: called-with-on-an-async-closed-callable
    # and the same call once an expectation is set, which is what the state exists for
    assert_that(_a_factory).eventually_sync().raises(
        ValueError
    ).when_called_with()  # case: valid-call-after-an-expectation
    assert_that(_a_factory).eventually().does_not_raise(
        ValueError
    ).when_called_with()  # case: valid-async-call-after-an-expectation
    # a polled `raises()` carries the class it was given to the call, and a bare `type` gives none: ty reads it as
    # `type[object]`, and the rung that would take it takes `raises(int)` under all four, so the chain leaves it off
    assert_that(_a_factory).eventually_sync().raises(_an_exception_class())  # case: bare-type-expectation-on-a-poll
    assert_that(_a_closed_factory).eventually_sync().raises(int)  # case: expectation-of-a-class-that-is-no-exception
    # several classes are taken as `except` takes them, and each still has to be an exception
    assert_that(_boom).raises((int, str))  # case: expectation-of-classes-that-are-no-exceptions
    assert_that(_a_closed_factory).eventually_sync().raises((int, str))  # case: polled-classes-that-are-no-exceptions
    assert_that(_noisy).warns((int,))  # case: warning-classes-that-are-no-warnings
    # a poll delivers its own failure, so `check()` is refused at run time and declared as not callable
    # a chain hands its value back under `val`; `value` is the builder's name and was recorded as an
    # assertion, which failed inside the replay rather than where it was written.  Read through a use,
    # since the declaration is a type nothing can do anything with rather than a missing name
    assert_that(_a_number).eventually_sync().value.bit_length()  # case: value-on-a-sync-poll
    assert_that(_a_number).eventually().value.bit_length()  # case: value-on-an-async-poll
    assert_that(_a_number).eventually_sync().check()  # case: check-on-a-sync-poll
    assert_that(_a_number).eventually().check()  # case: check-on-an-async-poll
    # `not_` negates the assertion after it, and a description, a transform and an expectation are not
    # assertions.  The chain's negation carries them as refusals, since `__getattr__` answers anything
    assert_that(_a_number).eventually_sync().not_.described_as("x")  # case: describe-on-a-negated-poll
    assert_that(_some_rows).eventually_sync().not_.first()  # case: pivot-on-a-negated-poll
    assert_that(_a_number).eventually().not_.raises(ValueError)  # case: expectation-on-a-negated-poll
    # a second poll asks the value the first hands back to be callable, which a number is not.  The rung
    # is restricted rather than left open, so the refusal is the overload resolution itself
    assert_that(_a_number).eventually_sync().eventually_sync()  # case: poll-on-a-sync-poll
    assert_that(_a_number).eventually().eventually()  # case: poll-on-an-async-poll
    # mypy and ty let this through while the pivot's element was `Never` and `Unknown` to them
    assert_that(_some_rows).eventually_sync().first().starts_with(1)  # case: wrong-element-after-a-polled-pivot
    # the rung the chain reaches now carries `str` operands, so mypy and pyright refuse this.  ty and
    # pyrefly still bind the element off the argument, which is what keeps the case here
    assert_that(_some_text).eventually_sync().contains_in_order(1)  # case: element-of-another-type-on-a-polled-string
    # the same assertion off the chain, which is where the width above comes from: `assert_that()` hands
    # a capable value the whole builder, and this call raises `TypeError` when it runs
    assert_that(_TakesAnyKey()).is_positive()  # case: numeric-assertion-on-a-capable-value
    # the dict family splits three ways because the necessity does: the key pair reads `keys()` and the
    # walk, entries add the lookup, values add `values()`
    assert_that(_Walkable()).contains_key("a")  # case: key-assertion-on-a-value-with-no-keys
    assert_that(_Walkable()).contains_entry({"a": 1})  # case: entry-assertion-on-a-value-with-no-keys
    assert_that(_Walkable()).contains_value(1)  # case: value-assertion-on-a-value-with-no-values
    # `float()` is necessary for these and for no other numeric, so the umbrella asks the value for it
    assert_that(_TakesAnyKey()).is_nan()  # case: nan-assertion-on-a-capable-value
    assert_that(_TakesAnyKey()).is_close_to(1, 1)  # case: closeness-assertion-on-a-capable-value
    assert_that(_a_row).eventually_sync().is_nan()  # case: nan-assertion-on-a-polled-capable-value
    # a value with no capability at all reaches neither, so the core narrowing follows onto the chain
    assert_that(_a_person).eventually_sync().is_positive()  # case: numeric-assertion-on-a-polled-object
    # the bridge: the same capable value polled, the rung `str` reaches by being iterable. Recorded so a
    # chain cannot be narrowed alone, leaving a polled value stricter than the same value off the chain
    assert_that(_a_row).eventually_sync().is_positive()  # case: numeric-assertion-on-a-polled-capable-value
    # the hook hands back the chain over the same value, so what follows a dynamic assertion is read
    assert_that(_a_number).eventually_sync().has_status("PAID").starts_with(  # case: text-assertion-after-a-dynamic-one
        "x"
    )

    # the call ladder, whose four landings the run time tells apart and the one view did not.  Each of
    # these raises: no expectation set, no return value captured, no exception captured, or the value
    # under test is the callable and not a message
    assert_that(_adder).when_called_with(1, 2)  # case: called-with-no-expectation
    assert_that(_Colour).when_called_with("red")  # case: called-with-no-expectation-on-a-capable-callable
    assert_that(_boom).raises(ValueError).when_called_with().returned()  # case: returned-after-raises
    assert_that(_adder).does_not_raise(ValueError).when_called_with(1, 2).raised()  # case: raised-after-no-raise
    assert_that(_noisy).warns(DeprecationWarning).when_called_with().raised()  # case: raised-after-warns
    assert_that(_noisy).warns(DeprecationWarning).when_called_with().caused_by(TypeError)  # case: caused-by-after-warns
    assert_that(_noisy).warns(DeprecationWarning).when_called_with().errors()  # case: errors-after-warns
    assert_that(_adder).does_not_raise(ValueError).when_called_with(1, 2).starts_with("x")  # case: text-after-no-raise
    assert_that(_adder).does_not_warn(UserWarning).when_called_with(1, 2).contains("x")  # case: contains-after-no-warn
    # what the call returned is typed as its return, so reading it as text is refused: an `Any` would let it by
    completed = assert_that(_adder).does_not_raise(ValueError).when_called_with(1, 2).returned()
    _read_as_text(completed.value)  # case: completed-return-read-as-text
    warned = assert_that(_noisy).warns(DeprecationWarning).when_called_with().returned()
    _read_as_text(warned.value)  # case: warned-return-read-as-text
    # what was caught is typed as what `raises()` named, and after a pivot as what it found
    caught = assert_that(_boom).raises(ValueError).when_called_with().raised()
    _read_as_text(caught.value)  # case: raised-exception-read-as-text
    cause = assert_that(_boom).raises(ValueError).when_called_with().caused_by(KeyError).raised()
    _read_as_text(cause.value)  # case: raised-cause-read-as-text
    # a group member is picked by one class: `error_of()` refuses a union at run time, where the cause pivots take one
    invoked = assert_that(_boom).raises(ValueError).when_called_with()
    invoked.error_of(KeyError | OSError)  # case: group-member-by-a-union


def _a_number() -> int:
    return 1


def _adder(first: int, second: int) -> int:
    return first + second


def _a_factory() -> Callable[..., int]:
    return lambda: 1


def _a_number_or_a_text() -> list[int | str]:
    return [1, "a"]


def _either() -> int | str:
    return 1


def _a_thing() -> object:
    return object()


def _a_closed_factory() -> Callable[[], int]:
    return lambda: 1


def _an_exception_class() -> type:
    return ValueError


def _boom() -> int:
    raise ValueError("bad thing")


def _noisy() -> int:
    warnings.warn("old", DeprecationWarning, stacklevel=2)
    return 7


def _a_person() -> _Person:
    return _Person()


def _a_row() -> _TakesAnyKey:
    return _TakesAnyKey()


def _read_as_text(text: str) -> None:
    del text


def _some_text() -> str:
    return "x"


def _a_mapping() -> dict[str, int]:
    return {"a": 1}


def _some_bytes() -> bytes:
    return b"x"


def _some_rows() -> list[str]:
    return ["a"]


def _loose_rows() -> list[Any]:
    return [1]


async def _a_number_later() -> int:
    return 1


async def _polls_over_an_async_probe() -> None:
    """The probe is awaited on every poll, so the chain is over what it returns rather than a coroutine."""
    await assert_that(_a_number_later).eventually().is_positive()  # case: valid-poll-over-an-async-probe
    await assert_that(_a_number_later).eventually().starts_with("x")  # case: text-assertion-on-an-async-probe


def _shapes_other_people_write(
    typed: _Row,
    mapping: Mapping[str, int],
    counted: Counter[str],
    mixed: list[int | str],
    heterogeneous: tuple[int, str],
    members: set[int],
    by_enum: dict[_Colour, int],
    payloads: list[dict[str, Any]],
    subclassed: _Records,
    loose: list[Any],
    stamp: datetime.datetime,
) -> None:
    """Container and mapping shapes from real suites, none of which this library wrote.

    An author's idea of ordinary usage is narrower than a user's, which is how a numeric bound written
    as `float | Decimal | Fraction` shipped and rejected `numpy.int64`.  These are the shapes probed
    afterwards: every one of them type-checks, and they are here so that stays true.
    """
    assert_that(typed).contains_key("id")  # case: valid-typed-dict-key
    assert_that(mapping).contains_key("id")  # case: valid-mapping-protocol-key
    assert_that(counted).contains_key("word")  # case: valid-counter-key
    assert_that(by_enum).contains_key(_Colour.RED)  # case: valid-enum-key
    assert_that(mixed).contains(1)  # case: valid-union-element
    assert_that(heterogeneous).contains("a")  # case: valid-heterogeneous-tuple
    assert_that(members).contains(1)  # case: valid-set-member
    assert_that(payloads).contains({"id": 1})  # case: valid-nested-payload
    assert_that(subclassed).contains("row")  # case: valid-list-subclass
    assert_that(loose).contains("whatever")  # case: valid-any-element
    assert_that(stamp).is_before(stamp)  # case: valid-datetime-against-datetime
    assert_that("text").matches(re.compile("t", re.IGNORECASE))  # case: valid-compiled-text-pattern
    match.matches_regex(re.compile("t"))  # case: valid-regex-matcher-of-a-compiled-pattern


def _relations_that_must_keep_working() -> None:
    """The other half of the measurement: tightening a signature must not cost these.

    Every one is ordinary usage, and a checker rejecting any of them is a defect in the typing rather
    than a success.
    """
    assert_that([1, 2, 3]).contains(2)  # case: valid-contains-an-item
    assert_that([1, 2, 3]).contains(match.greater_than(1))  # case: valid-contains-a-matcher
    assert_that(1).is_greater_than(1.5)  # case: valid-int-compared-to-float
    assert_that({"id": 1}).contains_key("id")  # case: valid-mapping-key
    assert_that("abc").contains("a")  # case: valid-substring
    assert_that(b"data").starts_with(b"da")  # case: valid-bytes-prefix
    assert_that(1).satisfies(lambda value: value > 0)  # case: valid-predicate
    assert_that([1, 2, 3]).is_length(3)  # case: valid-length
    assert_that(1).is_greater_than(0.5)  # case: valid-int-against-float
    assert_that(1.0).is_greater_than(0)  # case: valid-float-against-int
    assert_that(Decimal("1.1")).is_greater_than(Decimal("1.0"))  # case: valid-decimal-order
    assert_that(Fraction(3, 2)).is_greater_than(Fraction(1, 2))  # case: valid-fraction-order
    # the half that decides whether the float restriction can ship: a value the umbrella claims that converts
    assert_that(_ConvertibleRow()).is_nan()  # case: valid-capable-nan
    # a real mapping carries all three shapes, so the split refuses none of them
    assert_that(_TakesAnyKey()).contains_key("a")  # case: valid-capable-key
    assert_that(_TakesAnyKey()).contains_entry({"a": "b"})  # case: valid-capable-entry
    assert_that(_TakesAnyKey()).contains_value("b")  # case: valid-capable-value
    assert_that(_ConvertibleRow()).is_close_to(1, 1)  # case: valid-capable-closeness
    # the object fallback carries the four numeric assertions a registered number answers whatever it
    # registered as, so `Decimal` and `Fraction`, which no overload names, keep what the runtime gives
    assert_that(Fraction(3, 2)).is_not_close_to(50, 5)  # case: valid-fraction-closeness
    assert_that(Decimal("1.5")).is_close_to(1, 5)  # case: valid-decimal-closeness
    assert_that(Decimal("1.5")).is_not_zero()  # case: valid-decimal-zero
    assert_that(1 + 2j).is_zero()  # case: valid-complex-zero
    assert_that(True).is_greater_than(0)  # case: valid-bool-compared
    assert_that(1).is_equal_to(True)  # case: valid-int-equals-bool
    assert_that(1 + 2j).is_equal_to(1 + 2j)  # case: valid-complex-equality
    assert_that(1 + 2j).is_instance_of(complex)  # case: valid-complex-instance
    assert_that(1 + 2j).satisfies(lambda value: value == 0)  # case: valid-complex-predicate
    assert_that(True).is_true()  # case: valid-bool-truth
    assert_that([1, 2]).satisfies(match.contains(1))  # case: valid-membership-matcher
    assert_that(["a"]).satisfies(match.contains("a"))  # case: valid-membership-matcher-of-text
    assert_that({"a": 1}).satisfies(match.contains("a"))  # case: valid-membership-matcher-on-mapping
    assert_that([1, 2]).satisfies(match.contains_only(1, 2))  # case: valid-only-matcher
    assert_that([1, 2]).satisfies(match.is_subset_of([1, 2, 3]))  # case: valid-subset-from-collection
    assert_that([1, 2]).satisfies(match.is_subset_of(1, 2, 3))  # case: valid-subset-from-items
    assert_that([1, 2]).is_subset_of(1, 2, 3)  # case: valid-subset-of-loose-items
    assert_that("ab").is_subset_of("abc")  # case: valid-subset-of-characters
    assert_that({"a": 1}).is_subset_of({"a": 1, "b": 2})  # case: valid-subset-of-a-mapping
    assert_that(b"ab").is_subset_of([97, 98])  # case: valid-subset-of-byte-values
    # `==` makes a wider superset ordinary; only the mapping view refuses a shape by name rather than by comparison
    assert_that([1, 2]).is_subset_of("abc")  # case: valid-subset-of-text-items
    assert_that([1]).is_subset_of(1.0)  # case: valid-subset-of-a-wider-number
    assert_that("ab").is_subset_of([1, 2, "a", "b"])  # case: valid-subset-of-mixed-items
    assert_that([1, 2]).satisfies(match.is_sorted())  # case: valid-sorted-matcher
    assert_that([{"n": 1}]).satisfies(match.is_sorted(key=lambda row: row["n"]))  # case: valid-sorted-by-key
    # typed as the bare protocol, the eight matchers bound to their value lost the operators their objects have
    assert_that("abz").satisfies(match.starts_with("a") & match.ends_with("z"))  # case: valid-text-matchers-joined
    assert_that("abz").satisfies(~match.ends_with("q") & ~match.contains_string("q"))  # case: valid-text-inverted
    assert_that("abz").satisfies(match.matches_regex("^a") | match.starts_with("q"))  # case: valid-pattern-or-prefix
    assert_that([1, 2]).satisfies(match.contains(1) & ~match.is_sorted(reverse=True))  # case: valid-collection-joined
    assert_that([1]).satisfies(match.contains_only(1) | ~match.is_subset_of(2, 3))  # case: valid-collection-either
    assert_that([1]).satisfies(~match.is_subset_of([2]))  # case: valid-subset-inverted
    assert_that(1.05).satisfies(match.equal_to(1.0, tolerance=0.1))  # case: valid-equal-to-tolerance
    assert_that({"a": 1}).satisfies(match.equal_to({"a": 2}, ignore="a"))  # case: valid-equal-to-ignore
    # `Iterable` is covariant and `Matcher` contravariant, so these three ordinary calls must keep type-checking
    _mixed: list[int | str] = [1, "x"]
    assert_that(_mixed).satisfies(match.contains("x"))  # case: valid-membership-in-a-union-collection
    _wide: list[object] = [1, "x"]
    assert_that(_wide).satisfies(match.contains("x"))  # case: valid-membership-in-a-wide-collection
    _bases: list[_Base] = [_Derived()]
    assert_that(_bases).satisfies(match.contains(_Derived()))  # case: valid-membership-of-a-subclass
    _takes_repeats_of_derived(assert_that([_Derived()]))  # case: valid-repeats-of-the-exact-element
    assert_that({"id": 1}).at_json_path("$.id").is_equal_to(1)  # case: valid-equality-after-a-json-path
    assert_that({"id": 1}).at_json_path("$.id").satisfies(_is_int).is_positive()  # case: valid-narrowed-json-path
    assert_that({"id": 1}).at_json_path("$.id").satisfies(match.greater_than(0))  # case: valid-matcher-after-json-path
    _rows = [{"id": 1, "name": "a"}]
    assert_that(_rows).extracting("id")  # case: valid-extracting-one-name
    assert_that(_rows).extracting("id", "name")  # case: valid-extracting-several-names
    assert_that(_rows).extracting("id", filter="name")  # case: valid-extracting-filter-by-key
    assert_that(_rows).extracting("id", filter={"name": "a"})  # case: valid-extracting-filter-by-mapping
    assert_that(_rows).extracting("id", filter=lambda row: True)  # case: valid-extracting-filter-callable
    assert_that(_rows).extracting("id", sort="id")  # case: valid-extracting-sort-by-key
    assert_that(_rows).extracting("id", sort=["id", "name"])  # case: valid-extracting-sort-by-keys
    assert_that(_rows).extracting("id", sort=lambda row: row["id"])  # case: valid-extracting-sort-callable
    assert_that(_rows).extracting("id", filter="name", sort="id")  # case: valid-extracting-filter-and-sort
    # a mapping filter held in a variable: `dict` is invariant, so the parameter has to be a `Mapping`
    _criteria: dict[str, str] = {"name": "a"}
    assert_that(_rows).extracting("id", filter=_criteria)  # case: valid-extracting-filter-from-a-variable
    _proxy: Mapping[str, str] = MappingProxyType({"name": "a"})
    assert_that(_rows).extracting("id", filter=_proxy)  # case: valid-extracting-filter-from-a-mapping
    # a slice selects part of a sequence row, and it only became hashable in 3.12
    assert_that([(1, 2, 3)]).extracting(slice(0, 2))  # case: valid-extracting-a-slice
    # the verdict is read for truth, and `numpy.bool_` decided this, the library documenting numpy support
    assert_that(_rows).extracting("id", filter=_truthy_int)  # case: valid-filter-option-verdict-not-a-bool
    assert_that(_rows).each(_truthy_int)  # case: valid-quantifier-predicate-returning-an-int
    assert_that(_rows).filtered_on(_truthy_int)  # case: valid-filter-predicate-returning-an-int
    assert_that(_rows).each(_numpy_verdict)  # case: valid-quantifier-predicate-returning-a-numpy-bool
    # a polling chain keeps its type through a dynamic assertion and through a pivot
    assert_that(_a_number).eventually_sync().is_instance_of(int).is_positive()  # case: valid-polled-refinement
    assert_that(_some_rows).eventually_sync().first().starts_with("a")  # case: valid-polled-pivot
    assert_that(_a_number).eventually_sync().has_status("PAID").is_positive()  # case: valid-polled-dynamic-then-typed
    # the hook has to keep answering on the narrowest chain there is, which is what the case above pays for
    assert_that(_a_person).eventually_sync().has_status("PAID")  # case: valid-polled-dynamic-on-an-object
    # capable and callable at once is claimed by the umbrella, above the callable view, so its polling pivot
    # is declared there. Over `Any`, because no capability says what the call returns
    assert_that(_Probe()).eventually_sync().is_positive()  # case: valid-polled-capable-callable
    # the same value asked what the exception assertions ask, the half polling does not reach
    assert_that(_Probe()).does_not_raise(ValueError).when_called_with()  # case: valid-call-on-a-capable-callable
    # `builder()` builds over the value it is handed, not the capable one it came from. Left to the dynamic
    # hook it read as the facade over the original, where an ordering assertion would have been refused
    assert_that(_TakesAnyKey()).builder(1).is_positive()  # case: valid-builder-pivot-off-the-umbrella
    # the same binding must not refuse a guard the subject can be handed to
    assert_that("text").satisfies(lambda item: item.isupper())  # case: valid-predicate-over-the-subject
    assert_that(7).satisfies(lambda item: item.bit_length() > 0)  # case: valid-numeric-predicate-over-the-subject
    assert_that([1, 2]).first().check().is_positive()  # case: valid-verdict-after-a-pivot
    assert_that(["a"]).first().check().starts_with("a")  # case: valid-text-verdict-after-a-pivot
    # every kind of value the builder's verdict twin restricts a rung to, which has to keep its own assertions
    assert_that([{"a": 1}]).first().check().contains_key("a")  # case: valid-key-verdict-after-a-pivot
    assert_that([[1]]).first().check().not_.contains(2)  # case: valid-negated-verdict-after-a-pivot
    assert_that([1.5]).first().check().is_close_to(1, 1)  # case: valid-closeness-verdict-after-a-pivot
    assert_that([b"a"]).first().check().starts_with(b"a")  # case: valid-bytes-verdict-after-a-pivot
    assert_that([_Walkable()]).first().check().is_empty()  # case: valid-verdict-on-a-pivoted-capable-value
    assert_that([datetime.datetime(2026, 1, 1)]).first().check().is_before(
        datetime.datetime(2026, 1, 2)
    )  # case: valid-moment-verdict-after-a-pivot
    # `dict[str, Any]` is where the alternative spelling put every chain on the first rung
    assert_that(_loose_rows()).first().check().starts_with("x")  # case: valid-verdict-after-a-loose-pivot
    # even a list: a mapping whose `__getitem__` takes one answers, measured, so the selector stays `object`
    # and the runtime says no when the row cannot take what it was handed
    assert_that([_TakesAnyKey()]).extracting([])  # case: valid-extracting-an-unhashable-selector
    assert_that(_wide).satisfies(match.is_subset_of([1, "x", 2.0]))  # case: valid-subset-of-a-wide-collection
    assert_that(_mixed).satisfies(match.contains_only(1, "x"))  # case: valid-only-in-a-union-collection
    # the regression this half exists for: the numeric bound was first a list of types and rejected
    # `numpy.int64`, which this library supports. Named as a capability, so anything producing a float fits
    assert_that(1).is_greater_than(numpy.int64(0))  # case: valid-numpy-integer
    assert_that(1.5).is_greater_than(numpy.float64(0))  # case: valid-numpy-float
    assert_that(1).is_close_to(numpy.float64(1), numpy.float64(0.1))  # case: valid-numpy-tolerance
    assert_that(1).is_greater_than(numpy.int32(0))  # case: valid-numpy-int32
    assert_that(1).is_greater_than(numpy.uint64(0))  # case: valid-numpy-uint64
    assert_that(1.5).is_greater_than(numpy.float32(0))  # case: valid-numpy-float32
    # an integer argument takes what `__index__` answers for, as the runtime does since it read numpy integers
    assert_that([1, 2]).element(numpy.int64(0))  # case: valid-numpy-index
    assert_that([1, 2]).is_length(numpy.int64(2))  # case: valid-numpy-length
    assert_that([1, 2]).has_size_between(numpy.uint8(1), numpy.int64(2))  # case: valid-numpy-size-bounds
    assert_that(4).is_divisible_by(numpy.int64(2))  # case: valid-numpy-divisor
    assert_that(b"ab").has_byte_at(numpy.int64(0), numpy.uint8(97))  # case: valid-numpy-byte-at
    assert_that([4]).satisfies(match.is_length(numpy.int64(1)))  # case: valid-numpy-length-matcher
    # a numpy scalar as the value carries no length, so it leaves the array view for the numeric fallback
    assert_that(numpy.int64(4)).is_greater_than(0)  # case: valid-numpy-integer-value-ordered
    assert_that(numpy.float32(4)).is_close_to(4, 1)  # case: valid-numpy-float32-value-close
    assert_that(numpy.uint8(4)).is_between(0, 9)  # case: valid-numpy-uint8-value-between
    assert_that(numpy.timedelta64(1, "s")).is_greater_than(numpy.timedelta64(0, "s"))  # case: valid-numpy-duration
