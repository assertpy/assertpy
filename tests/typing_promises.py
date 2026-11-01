"""Chains whose declared result is compared against the object that comes back.

Every other typing gate compares a declaration with another declaration.  None asks whether the value at
the end of a chain is the type the checker promised, and two defects lived there: a negated
`is_instance_of` narrowed as though it had been positive, and a pivot on the capability facade kept the
container's type after the value had become an element.

The `assert_type` is the promise and the return annotation is the same promise, so
`test_typing_promises.py` can read both halves from one place.
"""

from __future__ import annotations

import datetime
import enum
import warnings
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from assertpy import assert_that

if TYPE_CHECKING:
    from collections.abc import Iterator

    from typing_extensions import TypeIs, assert_type
else:
    from tests.typing_harness import assert_type


def _is_str(value: object) -> TypeIs[str]:
    return isinstance(value, str)


def _is_int(value: object) -> TypeIs[int]:
    return isinstance(value, int)


class _OnlyIterable:
    """Iterable and nothing else, the narrowest thing the capability umbrella claims."""

    def __iter__(self) -> Iterator[int]:
        return iter((1, 2))


class _Counted:
    """Iterable, sized and searchable, so it satisfies `Collection` where `_OnlyIterable` does not."""

    def __iter__(self) -> Iterator[int]:
        return iter((1, 2))

    def __len__(self) -> int:
        return 2

    def __contains__(self, item: object) -> bool:
        return item in (1, 2)


_ONE_ITERABLE = _OnlyIterable()


class _Palette(enum.Enum):
    """An enum class, callable and iterable, so the umbrella claims it before the callable overload can."""

    RED = "red"


class _Deprecated:
    """A callable instance that is also iterable, the other shape the umbrella takes from the callable view."""

    def __iter__(self) -> Iterator[int]:
        return iter((1,))

    def __call__(self) -> int:
        warnings.warn("deprecated", DeprecationWarning, stacklevel=2)
        return 42


def _maybe_text() -> str | None:
    return None


def _a_number() -> int:
    return 7


def _ready() -> str | None:
    return "ready"


def a_string_stays_a_string() -> str:
    return assert_type(assert_that("alice").is_not_empty().value, str)


def a_polled_value_narrows_when_the_assertion_holds() -> str:
    return assert_type(assert_that(_ready).eventually_sync(timeout=0.5, interval=0.01).is_not_none().val, str)


def a_negated_poll_keeps_the_value_it_had() -> str | None:
    """`not_.is_not_none()` asserts the value *is* `None`, so narrowing it to `str` was backwards."""
    return assert_type(
        assert_that(_maybe_text).eventually_sync(timeout=0.5, interval=0.01).not_.is_not_none().val, "str | None"
    )


async def an_awaited_poll_narrows_when_the_assertion_holds() -> str:
    """The awaitable chain hands back a builder, so its promise is about `.value` rather than `.val`."""
    chain = await assert_that(_ready).eventually(timeout=0.5, interval=0.01).is_not_none()
    return assert_type(chain.value, str)


async def an_awaited_negated_poll_keeps_the_value_it_had() -> str | None:
    """The defect on the sync chain, asked of the asynchronous twin it was generated beside."""
    chain = await assert_that(_maybe_text).eventually(timeout=0.5, interval=0.01).not_.is_not_none()
    return assert_type(chain.value, "str | None")


def a_negated_poll_instance_check_keeps_the_value() -> int:
    """`not_.is_instance_of(str)` asserts the value is *not* a `str`, so it cannot hand back one."""
    return assert_type(
        assert_that(_a_number).eventually_sync(timeout=0.5, interval=0.01).not_.is_instance_of(str).val, int
    )


def a_negated_poll_instance_pair_keeps_the_value() -> int:
    return assert_type(
        assert_that(_a_number).eventually_sync(timeout=0.5, interval=0.01).not_.is_instance_of_any(str, bytes).val, int
    )


def a_negated_poll_predicate_keeps_the_value() -> int:
    return assert_type(
        assert_that(_a_number).eventually_sync(timeout=0.5, interval=0.01).not_.satisfies(_is_str).val, int
    )


def a_number_stays_a_number() -> int:
    return assert_type(assert_that(7).is_positive().value, int)


def a_list_yields_its_element() -> int:
    return assert_type(assert_that([1, 2]).first().value, int)


def a_mapping_yields_its_key() -> str:
    return assert_type(assert_that({"a": 1}).first().value, str)


def a_tuple_yields_its_last() -> int:
    return assert_type(assert_that((1, 2)).last().value, int)


def a_list_yields_the_element_at_an_index() -> int:
    return assert_type(assert_that([1, 2]).element(0).value, int)


def a_one_item_list_yields_that_item() -> int:
    return assert_type(assert_that([1]).single().value, int)


def a_collection_yields_its_element() -> int:
    return assert_type(assert_that(_Counted()).first().value, int)


def an_iterable_yields_its_element() -> int:
    return assert_type(assert_that(_OnlyIterable()).first().value, int)


def an_iterable_yields_its_last() -> int:
    return assert_type(assert_that(_OnlyIterable()).last().value, int)


def an_iterable_yields_the_element_at_an_index() -> int:
    return assert_type(assert_that(_OnlyIterable()).element(0).value, int)


def a_narrowing_keeps_what_it_narrowed_to(value: object = "alice") -> str:
    return assert_type(assert_that(value).is_instance_of(str).value, str)


def a_narrowing_to_a_number_keeps_the_number(value: object = 7) -> int:
    return assert_type(assert_that(value).is_instance_of(int).value, int)


def a_narrowing_to_a_moment_keeps_the_moment(
    value: object = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc),
) -> datetime.datetime:
    return assert_type(assert_that(value).is_instance_of(datetime.datetime).value, datetime.datetime)


def dropping_none_keeps_the_rest(value: str | None = "alice") -> str:
    return assert_type(assert_that(value).is_not_none().value, str)


def a_negated_type_check_keeps_the_subject(value: object = 42) -> object:
    return assert_type(assert_that(value).not_.is_instance_of(str).value, object)


def a_negated_any_type_check_keeps_the_subject(value: object = 42) -> object:
    return assert_type(assert_that(value).not_.is_instance_of_any(str, bytes).value, object)


def a_negated_none_check_keeps_the_subject(value: str | None = None) -> str | None:
    return assert_type(assert_that(value).not_.is_not_none().value, str | None)


def a_negation_on_a_string_stays_a_string() -> str:
    return assert_type(assert_that("alice").not_.starts_with("z").value, str)


def a_negation_on_a_number_stays_a_number() -> int:
    return assert_type(assert_that(7).not_.is_negative().value, int)


def a_negation_on_a_mapping_stays_a_mapping() -> dict[str, int]:
    return assert_type(assert_that({"a": 1}).not_.is_empty().value, dict[str, int])


def a_negation_before_a_pivot_still_pivots() -> int:
    return assert_type(assert_that([1, 2]).not_.is_empty().first().value, int)


def a_pivot_after_a_negation_yields_the_key() -> str:
    return assert_type(assert_that({"a": 1}).not_.is_empty().first().value, str)


def a_negated_predicate_keeps_the_subject(value: object = 42) -> object:
    return assert_type(assert_that(value).not_.satisfies(_is_str).value, object)


def a_negation_on_a_capable_value_keeps_it(value: _OnlyIterable = _ONE_ITERABLE) -> _OnlyIterable:
    return assert_type(assert_that(value).not_.is_instance_of(str).value, _OnlyIterable)


def a_negated_predicate_on_a_capable_value_keeps_it(value: _OnlyIterable = _ONE_ITERABLE) -> _OnlyIterable:
    return assert_type(assert_that(value).not_.satisfies(_is_str).value, _OnlyIterable)


def a_positive_step_after_a_negated_one_narrows(value: object = b"x") -> bytes:
    return assert_type(assert_that(value).not_.is_instance_of(str).is_instance_of(bytes).value, bytes)


def a_positive_step_after_a_negated_one_on_a_capable_value(value: _OnlyIterable = _ONE_ITERABLE) -> _OnlyIterable:
    return assert_type(assert_that(value).not_.is_instance_of(str).is_not_none().value, _OnlyIterable)


def an_ordinary_negated_assertion_also_hands_the_view_back(value: object = b"x") -> bytes:
    """The proof that the whole class closed rather than four known routes.

    `is_none()` is an ordinary inherited assertion, not one of the narrowing ladders, and the chain
    still leaves the negated view: the positive `is_instance_of` after it narrows.
    """
    return assert_type(assert_that(value).not_.is_none().is_instance_of(bytes).value, bytes)


def a_caught_error_on_a_capable_callable_is_the_message() -> str:
    """`int` above takes the callable overload, so it never reached the façade, where this kept the enum class."""
    return assert_type(assert_that(_Palette).raises(ValueError).when_called_with("blue").value, str)


def a_warning_from_a_capable_callable_is_the_message() -> str:
    return assert_type(assert_that(_Deprecated()).warns(DeprecationWarning).when_called_with().value, str)


def a_completed_call_on_a_capable_callable_keeps_the_callable() -> Callable[..., Any]:
    return assert_type(
        assert_that(_Deprecated()).does_not_raise(ValueError).when_called_with().value, Callable[..., Any]
    )


def a_negated_predicate_on_a_caught_error_keeps_the_message() -> str:
    """The view a call reaches, which no `assert_that` overload names and the first twin set missed."""
    caught = assert_that(int).raises(ValueError).when_called_with("x")
    return assert_type(caught.not_.satisfies(_is_int).value, str)


def a_negated_predicate_on_a_pipeline_keeps_the_list() -> list[Any]:
    return assert_type(assert_that([{"n": 1}]).extracting("n").not_.satisfies(_is_int).value, list[Any])


def a_negation_on_a_number_hands_the_number_back(value: int = 7) -> int:
    return assert_type(assert_that(value).not_.satisfies(_is_str).value, int)


def an_ordinary_negated_assertion_on_a_capable_value_hands_the_facade_back(
    value: _OnlyIterable = _ONE_ITERABLE,
) -> _OnlyIterable:
    """`is_equal_to()` is an ordinary assertion rather than a ladder, and the twin still leaves the negation."""
    return assert_type(assert_that(value).not_.is_equal_to(3).is_not_none().value, _OnlyIterable)
