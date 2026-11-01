"""Hold every assertion that takes a type expression to failing, rather than crashing, on all of them.

`isinstance`, `issubclass` and our own cause matching all accept three shapes: a class, a union, and a
tuple of either.  Each of the assertions below accepts all three when the value *matches*, because the
builtin does the matching.  Composing the failure message is ours, and reading `__name__` off the
argument works for a class and for nothing else: a tuple has never had one, and a union only grew one
in 3.14.

That combination is the worst shape a defect can take in an assertion library.  The passing path works,
so a suite stays green while the code is right, and the moment something breaks the assertion raises
`AttributeError` out of the formatter instead of reporting what went wrong.  It was found on
`is_instance_of` by an external contributor and this table is what a sweep for the same shape turned up.

The version matters and is not decoration.  On 3.14 and later a union renders as the useless but
harmless `<Union>`, so half of these cases look fine there and fail on the supported floor.  Anything
added here has to be run on 3.10 as well as on the development interpreter.
"""

from __future__ import annotations

import sys
import typing

import pytest

from assertpy import assert_that
from assertpy.errors import AssertionFailure


class _Person:
    pass


class _Car:
    pass


def _chained() -> None:
    try:
        raise KeyError("root")
    except KeyError as cause:
        raise RuntimeError("outer") from cause


def _instance_of(spec: object) -> None:
    assert_that(_Car()).is_instance_of(spec)  # ty: ignore[invalid-argument-type]  # the shape under test


def _instance_of_any(spec: object) -> None:
    assert_that(_Car()).is_instance_of_any(spec)  # ty: ignore[invalid-argument-type]  # the shape under test


def _subclass_of(spec: object) -> None:
    assert_that(_Car).is_subclass_of(spec)  # ty: ignore[invalid-argument-type]  # the shape under test


def _caused_by(spec: object) -> None:
    assert_that(_chained).raises(RuntimeError).when_called_with().caused_by(spec)  # ty: ignore[invalid-argument-type]  # the shape under test


def _has_root_cause(spec: object) -> None:
    assert_that(_chained).raises(RuntimeError).when_called_with().has_root_cause(spec)  # ty: ignore[invalid-argument-type]  # the shape under test


_COVERED = {
    "is_subclass_of": _subclass_of,
    "caused_by": _caused_by,
    "has_root_cause": _has_root_cause,
    "is_instance_of": _instance_of,
    "is_instance_of_any": _instance_of_any,
}

# what the builtin behind each accepts besides a bare class. No member matches any subject above: one
# that did would pass the assertion, and a test expecting a failure would report its own fixture
_SHAPES = {
    "a union": _Person | IndexError,
    "a tuple": (_Person, IndexError),
    "a tuple holding a union": (_Person | IndexError, TypeError),
}


@pytest.mark.parametrize("shape", _SHAPES.values(), ids=_SHAPES.keys())
@pytest.mark.parametrize("call", _COVERED.values(), ids=_COVERED.keys())
def test_a_failing_type_expression_fails_rather_than_crashes(call, shape) -> None:
    """The whole point: an assertion that cannot hold must say so, not raise from its own formatter."""
    with pytest.raises(AssertionFailure) as failure:
        call(shape)
    assert_that(failure.value).is_instance_of(AssertionFailure)


@pytest.mark.parametrize("shape", _SHAPES.values(), ids=_SHAPES.keys())
@pytest.mark.parametrize("call", _COVERED.values(), ids=_COVERED.keys())
def test_the_message_names_the_members_rather_than_the_container(call, shape) -> None:
    """`<Union>` and `<(<class '...'>, ...)>` are both answers a reader cannot act on."""
    with pytest.raises(AssertionFailure) as failure:
        call(shape)
    message = str(failure.value)
    assert_that(message).described_as("the failure message").contains("_Person").does_not_contain("<Union>")


def test_the_floor_is_where_this_hides() -> None:
    """A union has carried `__name__` since 3.14, so the union half of the table is silent above it.

    Recorded as a test rather than as a comment because it is the reason the suite has to be run on
    3.10 before this file is believed.
    """
    has_name = hasattr(int | str, "__name__")
    assert_that(has_name).described_as("union carries __name__").is_equal_to(sys.version_info >= (3, 14))


class TestWhatClassInfoCannotSay:
    """Two shapes `isinstance` takes that the declared type cannot describe, recorded rather than fixed.

    `ClassInfo` is `type | UnionType | tuple[ClassInfo, ...]`, which is as close as the type system gets.
    Both gaps below were found by measurement and neither is worth closing: the only spelling that would
    admit them is one that admits everything.
    """

    def test_a_union_holding_a_parameterised_generic_is_unreliable(self):
        """`UnionType` cannot say "a union of valid class info", so a bad member reaches `isinstance`.

        What it does then is not ours and is not even the same across versions.  Measured on both ends of
        the supported range, for `isinstance(1, int | list[int])`:

            3.10   TypeError, the whole union is validated first
            3.15   True, the good member matches and the bad one is never reached

        Only the two orderings below hold everywhere, so only they are asserted.  The version-dependent
        one is written down rather than pinned, because the boundary between the two behaviours is
        somewhere in 3.11 to 3.14 and this suite has not measured which.
        """
        with pytest.raises(TypeError):
            isinstance("x", int | list[int])

        with pytest.raises(TypeError):
            isinstance(1, list[int] | int)

    def test_the_legacy_union_spelling_runs_but_does_not_type_check(self):
        """`typing.Union[int, str]` runs, and `ClassInfo` cannot name it.

        Its static type is `typing._SpecialForm` to mypy and `UnionType` to pyright, so the two do not
        even agree on what it is.  `TypeForm` would admit it, and is rejected for a measured reason
        rather than for lack of a candidate: it also admits `list[int]` and `Any`, which `isinstance`
        refuses, so it trades one gap for a wider one.  `int | str` is the spelling the docs show.
        """
        legacy = typing.Union[int, str]  # noqa: UP007  # the old spelling is the subject of this test
        assert_that(isinstance(1, legacy)).described_as("the legacy spelling at run time").is_true()
        assert_that(assert_that(1).is_instance_of(legacy)).described_as("and through an assertion").is_not_none()
