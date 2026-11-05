"""Static typing tests for the ``assert_that`` overloads.

These are verified by type checkers (ty, Pyright, Mypy, Pyrefly), not at runtime: each ``assert_type`` pins the
overload resolution to the documented type-specific Protocol, so a regression that broadens or changes a
return type fails the type check. The body lives under ``TYPE_CHECKING`` because the Protocols in
:mod:`assertpy._engine._typing` exist only for static analysis and are absent at runtime; Pytest imports this
module without executing the block.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import builtins
    import collections
    import datetime
    import decimal
    import enum
    import fractions
    import logging
    import pathlib
    import re
    import sys
    from collections.abc import Awaitable, Callable, Iterator, Mapping, Sequence
    from contextlib import AbstractContextManager
    from typing import Any, cast

    from typing_extensions import TypeIs, assert_type

    from assertpy import AssertionOutcome, assert_conforms, assert_that, assert_warn, log_passes, match
    from assertpy._engine._builder_check_typing import _CheckAnyValue
    from assertpy._engine._capable_typing import _CapableAssertion, _NegatedCapableAssertion
    from assertpy._engine._check_typing import (
        _CheckArrayAssertion,
        _CheckBoolAssertion,
        _CheckBytesAssertion,
        _CheckCallableAssertion,
        _CheckCompletedAssertion,
        _CheckComplexAssertion,
        _CheckCoreAssertion,
        _CheckDateAssertion,
        _CheckDateTimeAssertion,
        _CheckDictAssertion,
        _CheckExpectedCompletionAssertion,
        _CheckExpectedRaiseAssertion,
        _CheckExpectedWarningAssertion,
        _CheckFrameAssertion,
        _CheckInvokedAssertion,
        _CheckIterableAssertion,
        _CheckListAssertion,
        _CheckNumericAssertion,
        _CheckObjectAssertion,
        _CheckPathAssertion,
        _CheckStringAssertion,
        _CheckWarnedAssertion,
    )
    from assertpy._engine._negated_typing import _NegatedObjectAssertion
    from assertpy._engine._poll_typing import _AsyncPoll, _SyncPoll, _SyncPollCompleted, _SyncPollInvoked
    from assertpy._engine._typing import (
        _ArrayAssertion,
        _ArrayShape,
        _BoolAssertion,
        _BytesAssertion,
        _CallableAssertion,
        _CompletedAssertion,
        _ComplexAssertion,
        _CoreAssertion,
        _DateAssertion,
        _DateTimeAssertion,
        _DictAssertion,
        _ExpectedCompletionAssertion,
        _ExpectedRaiseAssertion,
        _ExpectedWarningAssertion,
        _FrameAssertion,
        _FrameShape,
        _InvokedAssertion,
        _IterableAssertion,
        _ListAssertion,
        _NumericAssertion,
        _ObjectAssertion,
        _PathAssertion,
        _StringAssertion,
        _TextAssertion,
        _WarnedAssertion,
    )
    from assertpy._matcher_impls import AllOfMatcher, AnyOfMatcher, NotMatcher, _Composable
    from assertpy.assertpy import AssertionBuilder
    from assertpy.matchers import IsInstanceOfMatcher, IsTypeOfMatcher, Matcher

    assert_type(assert_that("text"), _StringAssertion)
    assert_type(assert_that(42), _NumericAssertion[int])
    assert_type(assert_that(3.14), _NumericAssertion[float])
    # both used to resolve to the numeric protocol and be offered methods whose only outcome was a TypeError
    assert_type(assert_that(complex(1, 2)), _ComplexAssertion)
    assert_type(assert_that(True), _BoolAssertion)
    # a step hands back `Self`, so the smaller protocol holds for the whole chain rather than the first call
    assert_type(assert_that(complex(1, 2)).is_not_zero().value, complex)
    assert_type(assert_that(complex(1, 2)).not_.is_zero().value, complex)
    assert_type(assert_that(True).is_greater_than(0).value, bool)
    assert_type(assert_that({"key": "value"}), _DictAssertion[str, str])
    assert_type(assert_that(["a", "b"]), _IterableAssertion[str])
    assert_type(assert_that(("a", "b")), _IterableAssertion[str])
    assert_type(assert_that({"a", "b"}), _IterableAssertion[str])
    assert_type(assert_that(frozenset({"a"})), _IterableAssertion[str])
    # the chronological nine refuse a plain date at run time, so one view for both offered them to a raiser
    assert_type(assert_that(datetime.date(2026, 1, 1)), _DateAssertion)
    assert_type(assert_that(datetime.datetime(2026, 1, 1, 12, 0)), _DateTimeAssertion)
    assert_type(assert_that(datetime.datetime(2026, 1, 1, 12, 0)).value, datetime.datetime)
    assert_type(assert_that(pathlib.Path("/tmp")), _PathAssertion)
    assert_type(assert_that(b"raw"), _BytesAssertion[bytes])
    assert_type(assert_that(b"raw").starts_with(b"r"), _BytesAssertion[bytes])
    assert_type(assert_that(b"raw").ends_with(b"w"), _BytesAssertion[bytes])
    assert_type(assert_that(b"raw").starts_with_bytes(b"r"), _BytesAssertion[bytes])
    assert_type(assert_that(b"raw").does_not_contain(b"x", 120), _BytesAssertion[bytes])
    assert_type(assert_that({"a": 1}).each(lambda key: True), _DictAssertion[str, int])
    # a text walks character by character, so the element is a `str`: the runtime took them, no view offered one
    assert_type(assert_that("ab").each(lambda character: character.isalpha()), _StringAssertion)
    assert_type(assert_that("ab").any_satisfy(lambda character: character == "a"), _StringAssertion)
    assert_type(assert_that("ab").satisfies_exactly(lambda first: first == "a"), _StringAssertion)
    # the pairwise one names both sides: a character and an element of the sequence walked alongside it
    assert_type(
        assert_that("ab").zip_satisfies([1, 2], lambda character, number: character.isalpha() and number > 0),
        _StringAssertion,
    )
    # and the loose spelling stays ordinary: naming the two sides is not a demand that a caller name them
    _pairs: list[Any] = [1, 2]
    _loose: Callable[[Any, Any], object] = lambda left, right: left == right  # noqa: E731  # the shape under test
    assert_type(assert_that("ab").zip_satisfies(_pairs, _loose), _StringAssertion)
    assert_type(assert_that({"a": 1}).all_satisfy(lambda key: True), _DictAssertion[str, int])
    assert_type(assert_that(bytearray(b"raw")), _BytesAssertion[bytearray])
    assert_type(assert_that(len), _CallableAssertion[int])
    # the pair gate reads literals, so this is what ties `Callable` to the view it dispatches to
    assert_type(assert_that(lambda: None), _CallableAssertion[None])

    class _Countable:
        def __iter__(self) -> object: ...

    class _Rowish(Mapping[str, int]):
        """A capable value that is also a mapping, which is what the element pivot keys on."""

        def __getitem__(self, key: str) -> int: ...
        def __iter__(self) -> Iterator[str]: ...
        def __len__(self) -> int: ...

    class _CallableResponse:
        """An ASGI or WSGI response: a callable, and the one thing an HTTP capability describes."""

        def __call__(self, *args: object, **kwargs: object) -> object: ...
        @property
        def status_code(self) -> int: ...
        @property
        def headers(self) -> Mapping[str, str]: ...

    # the callable view sits under the shapes: above them it claimed a Starlette or Flask response, and
    # `has_status_code()` was a type error in all three checkers while the runtime answered it
    assert_type(assert_that(_CallableResponse()), _CapableAssertion[_CallableResponse])

    assert_type(assert_that(object()), _ObjectAssertion[object])

    # one hook, two names, no signature true of both: a plain object gets the object view and no
    # `__getattr__`, while a capable value has the hook and gets the facade's own surface back
    assert_type(assert_that(_Countable()).has_anything("value"), _CapableAssertion[_Countable])

    assert_type(assert_that(42).not_.is_equal_to(43), _NumericAssertion[int])
    assert_type(assert_that("text").not_.starts_with("x"), _StringAssertion)
    assert_type(assert_that([1, 2]).not_.contains(3), _IterableAssertion[int])
    assert_type(assert_that(42).not_.is_equal_to(43).value, int)

    assert_type(assert_that(42).check().is_positive(), AssertionOutcome)
    # the proxy is the verdict twin of the view it came from, so a wrong-domain assertion is a type error here
    assert_type(assert_that(42).check(), _CheckNumericAssertion[int])
    assert_type(assert_that("text").check(), _CheckStringAssertion)
    assert_type(assert_that({"a": 1}).check(), _CheckDictAssertion[str, int])
    assert_type(assert_that("text").check().starts_with("x"), AssertionOutcome)
    assert_type(assert_that({"a": 1}).check().contains_key("a"), AssertionOutcome)
    assert_type(assert_that(42).check().not_.is_positive(), AssertionOutcome)

    # a pattern compiled from text goes wherever its text goes
    word = re.compile(r"\w+", re.IGNORECASE)
    assert_type(assert_that("text").matches(word), _StringAssertion)
    assert_type(assert_that("text").not_.does_not_match(word), _StringAssertion)
    assert_type(assert_that("text").check().matches(word), AssertionOutcome)
    assert_type(assert_that("text").extracting_group(word, 0), _StringAssertion)
    assert_type(assert_that("text").matches_with_groups(word), AssertionBuilder[Any])
    assert_type(assert_that(str).eventually_sync().matches(word), _SyncPoll[str])
    assert_type(match.matches_regex(word), _Composable[str])
    # bound to the value they judge, and composed the way every other matcher is
    assert_type(match.starts_with("a") & match.ends_with("z"), AllOfMatcher)
    assert_type(match.contains_string("b") | match.matches_regex(word), AnyOfMatcher)
    assert_type(~match.starts_with("z"), NotMatcher)
    assert_type(match.contains(1) & match.contains_only(1, 2), AllOfMatcher)
    assert_type(match.is_subset_of([1, 2]) | ~match.is_sorted(), AnyOfMatcher)
    assert_type(~match.is_subset_of(1, 2), NotMatcher)
    assert_type(assert_that("abz").satisfies(match.starts_with("a") & ~match.ends_with("q")), _StringAssertion)

    assert_type(assert_that([1, 2]).satisfies_exactly(lambda x: x > 0, lambda x: x > 1), _IterableAssertion[int])
    assert_type(assert_that([1, 2]).zip_satisfies([2, 3], lambda left, right: left < right), _IterableAssertion[int])
    assert_type(assert_that([1, 2]).contains_only_once(1), _IterableAssertion[int])
    assert_type(assert_that([1, 2]).has_same_size_as((3, 4)), _IterableAssertion[int])
    assert_type(assert_that("ab").contains_only_once("a"), _StringAssertion)
    assert_type(assert_that("ab").has_same_size_as("cd"), _StringAssertion)
    assert_type(assert_that({"k": 1}).has_same_size_as({"j": 2}), _DictAssertion[str, int])
    assert_type(assert_that(b"ab").has_same_size_as(b"cd"), _BytesAssertion[bytes])

    assert_type(assert_that({"k": 1}).all_fields_satisfy(lambda x: x > 0), _DictAssertion[str, int])
    assert_type(assert_that(42).has_no_none_fields(), _NumericAssertion[int])

    assert_type(assert_that({"k": 1.0}).is_equal_to({"k": 1.0}, tolerance=0.001), _DictAssertion[str, float])
    assert_type(
        assert_that({"k": 1}).is_equal_to({"k": 1}, comparators={int: lambda a, e: a == e}), _DictAssertion[str, int]
    )
    assert_type(assert_that({"k": 1}).is_equal_to({"k": None}, ignore_null=True), _DictAssertion[str, int])

    # `is_close_to` stays datetime-only, so the shared date protocol does not advertise it
    assert_type(assert_that("banana").is_greater_than("apple"), _StringAssertion)
    assert_type(assert_that("apple").is_less_than("banana"), _StringAssertion)
    assert_type(assert_that("b").is_greater_than_or_equal_to("a"), _StringAssertion)
    assert_type(assert_that("a").is_less_than_or_equal_to("b"), _StringAssertion)
    assert_type(assert_that(b"b").is_greater_than(b"a"), _BytesAssertion[bytes])
    assert_type(assert_that(b"a").is_less_than(bytearray(b"b")), _BytesAssertion[bytes])
    assert_type(assert_that(bytearray(b"b")).is_greater_than_or_equal_to(b"a"), _BytesAssertion[bytearray])
    assert_type(assert_that(b"a").is_less_than_or_equal_to(b"b"), _BytesAssertion[bytes])
    assert_type(assert_that(datetime.date(2026, 1, 2)).is_greater_than(datetime.date(2026, 1, 1)), _DateAssertion)
    assert_type(assert_that(datetime.date(2026, 1, 1)).is_less_than(datetime.date(2026, 1, 2)), _DateAssertion)
    assert_type(
        assert_that(datetime.datetime(2026, 1, 2)).is_greater_than_or_equal_to(datetime.datetime(2026, 1, 1)),
        _DateTimeAssertion,
    )
    assert_type(
        assert_that(datetime.datetime(2026, 1, 1)).is_less_than_or_equal_to(datetime.datetime(2026, 1, 2)),
        _DateTimeAssertion,
    )
    assert_type(
        assert_that(datetime.date(2026, 1, 2)).is_between(datetime.date(2026, 1, 1), datetime.date(2026, 1, 3)),
        _DateAssertion,
    )
    assert_type(
        assert_that(datetime.date(2026, 1, 5)).is_not_between(datetime.date(2026, 1, 1), datetime.date(2026, 1, 3)),
        _DateAssertion,
    )
    assert_type(
        assert_that(datetime.datetime(2026, 1, 5)).is_not_between(
            datetime.datetime(2026, 1, 1), datetime.datetime(2026, 1, 3)
        ),
        _DateTimeAssertion,
    )

    assert_type(assert_that([3, 1, 2]).contains_exactly_in_any_order(1, 2, 3), _IterableAssertion[int])
    assert_type(assert_that("cba").contains_exactly_in_any_order("a", "b", "c"), _StringAssertion)
    assert_type(
        assert_that([1, 2]).satisfies_exactly_in_any_order(lambda x: x > 1, lambda x: x < 2), _IterableAssertion[int]
    )
    assert_type(assert_that([1, 2]).has_size_greater_than(1), _IterableAssertion[int])
    assert_type(assert_that("ab").has_size_less_than(3), _StringAssertion)
    assert_type(assert_that({"k": 1}).has_size_between(0, 2), _DictAssertion[str, int])
    assert_type(assert_that(b"ab").has_size_between(1, 2), _BytesAssertion[bytes])
    assert_type(assert_that("ab").is_length_between(1, 3), _StringAssertion)
    assert_type(assert_that(42).is_length_between(0, 9), _NumericAssertion[int])
    assert_type(assert_that("a b").is_equal_to_ignoring_whitespace("ab"), _StringAssertion)
    assert_type(assert_that("<p>a</p>").is_html_equal_to("<p> a </p>"), _StringAssertion)
    assert_type(assert_that("<p>a</p>").is_html_equal_to("<p>a</p>", whitespace="exact"), _StringAssertion)
    assert_type(assert_that("<p>a</p>").not_.is_html_equal_to("<p>b</p>"), _StringAssertion)
    assert_type(assert_that("<p>a</p>").check().is_html_equal_to("<p>a</p>"), AssertionOutcome)
    assert_type(assert_that(str).eventually_sync().is_html_equal_to("<p>a</p>"), _SyncPoll[str])
    assert_type(match.html_equal_to("<p>a</p>"), _Composable[str])
    assert_type(assert_that("FooBar").starts_with_ignoring_case("foo"), _StringAssertion)
    assert_type(assert_that("FooBar").ends_with_ignoring_case("BAR"), _StringAssertion)
    assert_type(assert_that(1).is_instance_of_any(int, float), _NumericAssertion[int])
    assert_type(assert_that(1).is_instance_of_any(str, int | float), _NumericAssertion[int])
    assert_type(assert_that(1).is_instance_of_any(str, (int, float)), _NumericAssertion[int])
    assert_type(assert_that("s").is_subclass_of(object), _StringAssertion)
    assert_type(assert_that("s").is_subclass_of((str, bytes)), _StringAssertion)
    assert_type(assert_that("s").is_subclass_of(str | bytes), _StringAssertion)
    # a caught message is text without being a `str` view, and its pivots are the only way to `_TextAssertion`
    assert_type(assert_that(len).raises(ValueError).when_called_with().first(), _TextAssertion)

    assert_type(assert_that(len).eventually(trace=False), _AsyncPoll[int])
    assert_type(assert_that(len).eventually_sync(timeout=2, trace=False), _SyncPoll[int])
    assert_that(len).eventually_sync(timeout=2, trace=False).is_equal_to(1)
    assert_that(len).eventually_sync(timeout=2, trace=False).is_positive()
    assert_type(assert_that(len).eventually_sync().is_positive().val, int)
    assert_type(assert_that(len).eventually().is_positive(), _AsyncPoll[int])
    assert_that(len).eventually_sync(timeout=2, trace=False).not_.is_equal_to(2)

    # a subclass value reaches the rung written for its base only through covariance: invariant, all three refused
    class _Shade(str, enum.Enum):
        DARK = "dark"

    def _shade() -> _Shade: ...
    def _ordered() -> collections.OrderedDict[str, int]: ...
    def _defaulted() -> collections.defaultdict[str, int]: ...

    assert_type(assert_that(_shade).eventually_sync().is_equal_to_ignoring_case("DARK"), _SyncPoll[_Shade])
    assert_type(assert_that(_shade).eventually().is_equal_to_ignoring_case("DARK"), _AsyncPoll[_Shade])
    assert_type(assert_that(_ordered).eventually_sync().contains_key("a"), _SyncPoll[collections.OrderedDict[str, int]])
    assert_type(
        assert_that(_defaulted).eventually().contains_entry({"a": 0}), _AsyncPoll[collections.defaultdict[str, int]]
    )

    def _counts() -> list[int]: ...
    def _grid() -> tuple[list[int], ...]: ...
    def _tags() -> frozenset[str]: ...
    def _row(row: list[int]) -> list[int]: ...

    # one rung over `list | tuple | set | frozenset` made mypy answer `Never` for the element
    assert_type(assert_that(_counts).eventually_sync().first().val, int)
    assert_type(assert_that(_grid).eventually_sync().last().first().val, int)
    assert_type(assert_that(_tags).eventually_sync().single().val, str)
    assert_type(assert_that(_counts).eventually_sync().filtered_on(bool).val, list[int])
    assert_type(assert_that(_counts).eventually_sync().mapped(str).val, list[str])
    assert_type(assert_that(_grid).eventually_sync().flat_mapped(_row).val, list[int])
    assert_type(assert_that(_counts).eventually().element(0), _AsyncPoll[int])

    async def _settled() -> None:
        assert_type((await assert_that(_counts).eventually().first()).value, int)

    async def _a_count_later() -> int: ...

    # an `async def` probe is awaited on every poll, so the chain is over what the coroutine hands back
    assert_type(assert_that(_a_count_later).eventually(), _AsyncPoll[int])
    assert_type(assert_that(cast("Callable[..., Awaitable[int]]", _a_count_later)).eventually(), _AsyncPoll[int])

    def _maybe_counts() -> list[int] | None: ...
    def _maybe_grid() -> list[list[int]] | None: ...

    # `is_not_none()` read off the view's ladder answered a union of containers, and the pivot after it `list[str]`
    assert_type(assert_that(_maybe_counts).eventually_sync().is_not_none(), _SyncPoll[list[int]])
    assert_type(assert_that(_maybe_grid).eventually_sync().is_not_none().first().val, list[int])
    assert_type(assert_that(_maybe_counts).eventually().is_not_none(), _AsyncPoll[list[int]])

    # a polled callable's call lands where its expectation says, with that landing's own pivots declared
    def _handler() -> Callable[[int], int]: ...

    polled = assert_that(_handler).eventually_sync()
    assert_type(polled.raises(ValueError).when_called_with(1), _SyncPollInvoked[ValueError])
    assert_type(polled.raises(ValueError).when_called_with(1).val, str)
    assert_type(polled.raises(ValueError).when_called_with(1).contains("x").raised().val, ValueError)
    assert_type(polled.raises(ValueError).when_called_with(1).caused_by(KeyError).raised().val, KeyError)
    landed = polled.raises(ValueError).when_called_with(1)
    polled_cause: BaseException = landed.caused_by(KeyError | OSError).raised().val
    assert_type(landed.has_root_cause((KeyError, OSError)), _SyncPollInvoked[BaseException])
    assert_type(polled.raises(ValueError).when_called_with(1).not_.caused_by(KeyError).raised().val, ValueError)
    assert_type(polled.does_not_raise(ValueError).when_called_with(1), _SyncPollCompleted[int])
    assert_type(polled.does_not_raise(ValueError).when_called_with(1).returned().val, int)
    assert_type(polled.warns().when_called_with(1).returned().val, int)
    assert_type(polled.warns().when_called_with(1).val, str)
    assert_type(polled.does_not_warn().when_called_with(1).returned().val, int)
    assert_type(polled.does_not_raise(ValueError).when_called_with(1).is_callable().returned().val, int)
    assert_type(polled.raises(ValueError).when_called_with(1).not_.contains("x").raised().val, ValueError)

    async def _awaited() -> None:
        awaited = assert_that(_handler).eventually()
        assert_type((await awaited.raises(ValueError).when_called_with(1)).raised().value, ValueError)
        assert_type((await awaited.does_not_raise(ValueError).when_called_with(1).returned()).value, int)
        assert_type((await awaited.warns().when_called_with(1).returned()).value, int)
        assert_type((await awaited.does_not_warn().when_called_with(1).returned()).value, int)
        assert_type((await awaited.raises(ValueError).when_called_with(1)).value, str)

    # the four ways to set an expectation, each landing the call somewhere different: an exception
    # message, a warning message, or the callable itself with the return value reachable
    assert_type(assert_that(lambda: int("1")).raises(ValueError), _ExpectedRaiseAssertion[int, ValueError])
    assert_type(assert_that(lambda: int("1")).warns(), _ExpectedWarningAssertion[int])
    assert_type(assert_that(lambda: int("1")).does_not_raise(ValueError), _ExpectedCompletionAssertion[int])
    assert_type(assert_that(lambda: int("1")).does_not_warn(), _ExpectedCompletionAssertion[int])

    def _fails() -> None: ...

    # several classes, any one of which will do, as `except` takes a tuple: the call lands on no one class.  A union
    # is held by what it assigns to, since pyrefly reads `ValueError | KeyError` as one class of either
    assert_type(
        assert_that(lambda: int("1")).raises((ValueError, KeyError)), _ExpectedRaiseAssertion[int, BaseException]
    )
    either: BaseException = assert_that(_fails).raises(ValueError | KeyError).when_called_with().raised().value
    assert_type(assert_that(lambda: int("1")).does_not_raise((ValueError, KeyError)), _ExpectedCompletionAssertion[int])
    assert_type(assert_that(lambda: int("1")).warns((DeprecationWarning, UserWarning)), _ExpectedWarningAssertion[int])
    assert_type(
        assert_that(lambda: int("1")).does_not_warn(UserWarning | DeprecationWarning), _ExpectedCompletionAssertion[int]
    )
    assert_type(polled.raises((ValueError, KeyError)).when_called_with(1), _SyncPollInvoked[BaseException])
    assert_type(polled.does_not_raise(ValueError | KeyError).when_called_with(1), _SyncPollCompleted[int])
    assert_that(_fails).eventually_sync(ignoring=ValueError | KeyError).ignoring((OSError, (LookupError,)))
    assert_that(_fails).raises(Exception).when_called_with().contains_error((ValueError, KeyError), OSError)
    assert_that(_fails).raises(Exception).when_called_with().does_not_contain_error(ValueError | KeyError)
    # the same four on a callable the umbrella claims, over `Any` since `_Callable` names no return
    assert_type(assert_that(_CallableResponse()).raises(ValueError), _ExpectedRaiseAssertion[Any, ValueError])
    assert_type(assert_that(_CallableResponse()).warns(), _ExpectedWarningAssertion[Any])
    assert_type(assert_that(_CallableResponse()).does_not_raise(ValueError), _ExpectedCompletionAssertion[Any])
    assert_type(assert_that(_CallableResponse()).does_not_warn(), _ExpectedCompletionAssertion[Any])
    assert_type(assert_that(_Shade).raises(ValueError).when_called_with("x"), _InvokedAssertion[ValueError])
    assert_type(assert_that(_CallableResponse()).warns().when_called_with(), _WarnedAssertion[Any])
    assert_type(assert_that(len).warns().when_called_with(), _WarnedAssertion[int])
    assert_type(assert_that(len).does_not_raise(ValueError).when_called_with(), _CompletedAssertion[int])
    assert_type(assert_that(len).raises(ValueError).when_called_with(), _InvokedAssertion[ValueError])
    assert_type(assert_that(len).raises(ValueError).when_called_with().caused_by(KeyError), _InvokedAssertion[KeyError])
    assert_type(
        assert_that(len).raises(ValueError).when_called_with().has_root_cause(KeyError), _InvokedAssertion[KeyError]
    )
    assert_type(
        assert_that(len).raises(ValueError).when_called_with().contains_error(KeyError), _InvokedAssertion[ValueError]
    )
    assert_type(
        assert_that(lambda: int("1")).raises(ValueError).when_called_with().raised(), AssertionBuilder[ValueError]
    )
    invoked = assert_that(len).raises(ValueError).when_called_with()
    assert_type(invoked.does_not_contain_error(KeyError), _InvokedAssertion[ValueError])
    assert_type(invoked.errors(), _ListAssertion[BaseException])
    assert_type(invoked.errors().value, list[BaseException])
    assert_type(invoked.error_of(KeyError), _InvokedAssertion[KeyError])
    assert_type(invoked.error_of(KeyError).value, str)
    assert_type(invoked.error_of(KeyError).raised(), AssertionBuilder[KeyError])

    # `raised()` hands back the exception `raises()` named, and after a pivot the one it found
    class _AppError(ValueError): ...

    assert_type(assert_that(len).raises(Exception).when_called_with().raised().value, Exception)
    assert_type(assert_that(len).raises(BaseException).when_called_with().raised().value, BaseException)
    assert_type(assert_that(len).raises(_AppError).when_called_with().raised().value, _AppError)
    assert_type(assert_that(len).raises(cast("Any", ValueError)).when_called_with().raised().value, Any)
    assert_type(invoked.caused_by(KeyError).raised().value, KeyError)
    assert_type(invoked.has_root_cause(OSError).raised().value, OSError)
    assert_type(invoked.contains("x").raised().value, ValueError)
    # the cause is read with `isinstance`, so a tuple or a union is taken and lands on no one class.  pyrefly
    # reads the union as `type[KeyError | OSError]` and lands on that, so the union is held by what it assigns to
    assert_type(invoked.caused_by((KeyError, OSError)), _InvokedAssertion[BaseException])
    assert_type(invoked.has_root_cause((KeyError, OSError)), _InvokedAssertion[BaseException])
    either_cause: BaseException = invoked.caused_by(KeyError | OSError).raised().value
    # a negated pivot asserts the cause is not there, so the chain keeps the exception it was on
    assert_type(invoked.not_.caused_by(KeyError).raised().value, ValueError)

    def _expecting(expected: type[LookupError]) -> None:
        assert_type(assert_that(len).raises(expected).when_called_with().raised().value, LookupError)

    # ty reads the floor from `requires-python` and skips this; the other three check it
    if sys.version_info >= (3, 11):
        grouped = assert_that(len).raises(builtins.ExceptionGroup).when_called_with()
        assert_type(grouped.error_of(TypeError).raised().value, TypeError)
        caught_group: builtins.ExceptionGroup[Exception] = grouped.raised().value

    class _Alpha: ...

    class _Beta: ...

    maybe_name = cast("str | None", "fred")
    anything = cast("object", "fred")
    assert_type(assert_that(maybe_name), _ObjectAssertion[str | None])
    # the refinement answers with the factory's view, since one that ended the narrowing would be a dead end
    assert_type(assert_that(maybe_name).is_not_none(), _StringAssertion)
    assert_type(assert_that(maybe_name).is_not_none().value, str)
    # every rung and not the first alone: one checker read nine of them as `Unknown`, and none was asserted
    assert_type(assert_that(cast("bool | None", True)).is_not_none(), _BoolAssertion)
    assert_type(assert_that(cast("int | None", 1)).is_not_none(), _NumericAssertion[int])
    assert_type(assert_that(cast("int | None", 1)).is_not_none().value, int)
    assert_type(assert_that(cast("float | None", 1.5)).is_not_none(), _NumericAssertion[float])
    assert_type(assert_that(cast("complex | None", 1j)).is_not_none(), _ComplexAssertion)
    assert_type(assert_that(cast("dict[str, int] | None", {})).is_not_none(), _DictAssertion[str, int])
    assert_type(assert_that(cast("list[int] | None", [])).is_not_none(), _IterableAssertion[int])
    assert_type(assert_that(cast("tuple[str, ...] | None", ())).is_not_none(), _IterableAssertion[str])
    assert_type(assert_that(cast("set[int] | None", set())).is_not_none(), _IterableAssertion[int])
    assert_type(assert_that(cast("frozenset[str] | None", frozenset())).is_not_none(), _IterableAssertion[str])
    assert_type(assert_that(cast("datetime.datetime | None", None)).is_not_none(), _DateTimeAssertion)
    assert_type(assert_that(cast("datetime.date | None", None)).is_not_none(), _DateAssertion)
    assert_type(assert_that(cast("pathlib.Path | None", None)).is_not_none(), _PathAssertion)
    assert_type(assert_that(cast("bytes | None", b"")).is_not_none(), _BytesAssertion[bytes])
    assert_type(assert_that(cast("bytearray | None", None)).is_not_none(), _BytesAssertion[bytearray])
    assert_type(assert_that(cast("Callable[[int], str] | None", None)).is_not_none(), _CallableAssertion[Any])
    assert_type(assert_that(cast("decimal.Decimal | None", None)).is_not_none(), _ObjectAssertion[decimal.Decimal])
    assert_type(assert_that(anything).is_instance_of(bool), _BoolAssertion)
    assert_type(assert_that(anything).is_instance_of(bool).value, bool)
    # a tuple of alternatives lands on the widest rung, nested to any depth, as `isinstance` takes it.  A union
    # has no line, and not because the checkers disagree: all four bind it through `TypeForm[_U]`, measured on
    # pyright 1.1.413 with no experimental flag, which then also takes `Literal[1]`, `Never`, `Annotated[int,
    # "x"]` and `list[int]`, each refused by the runtime.  PEP 747 declined a restricted spelling and Python has
    # no intersection type, so a union keeps the view the chain already had.  The runtime side is gated in
    # `tests/test_class.py`, where all four spellings are accepted and named in the failure
    assert_type(assert_that(anything).is_instance_of((_Alpha, _Beta)), _ObjectAssertion[_Alpha | _Beta])
    assert_type(assert_that(anything).not_, _NegatedObjectAssertion[object])

    def _narrows_to_str(value: object) -> TypeIs[str]: ...

    # one negated step hands the positive view back, which is what `NegatedBuilder` does at run time
    assert_type(assert_that(object()).not_.is_instance_of(str), _ObjectAssertion[object])
    assert_type(assert_that(object()).not_.is_instance_of_any(str, bytes), _ObjectAssertion[object])
    assert_type(assert_that(object()).not_.is_not_none(), _ObjectAssertion[object])
    # and the positive rungs that answer the same view, pinned from a receiver the gate can read
    assert_type(assert_that(object()).is_instance_of((_Alpha, _Beta)), _ObjectAssertion[_Alpha | _Beta])
    assert_type(assert_that(object()).is_instance_of_any(_Alpha, _Beta), _ObjectAssertion[_Alpha | _Beta])
    assert_type(assert_that(object()).is_not_none(), _ObjectAssertion[object])
    assert_type(assert_that(object()).not_.satisfies(_narrows_to_str), _ObjectAssertion[object])
    assert_type(assert_that(_Countable()).not_, _NegatedCapableAssertion[_Countable])
    assert_type(assert_that(anything).is_instance_of((_Alpha, _Beta)).value, _Alpha | _Beta)
    assert_type(assert_that(anything).is_instance_of((int, str, bytes)), _ObjectAssertion[int | str | bytes])
    assert_type(assert_that(anything).is_instance_of_any(_Alpha, _Beta), _ObjectAssertion[_Alpha | _Beta])
    assert_type(assert_that(anything).is_instance_of_any(_Alpha, _Beta, str), _ObjectAssertion[_Alpha | _Beta | str])
    # past the arities that bind, and for a tuple nested to any depth, the widest rung answers
    assert_type(assert_that(anything).is_instance_of((_Alpha, (_Beta, str))), _ObjectAssertion[object])
    assert_type(assert_that(anything).is_instance_of_any((_Alpha, _Beta), (str, bytes)), _ObjectAssertion[object])
    assert_type(assert_that(maybe_name).is_not_none().is_instance_of(str).value, str)
    assert_type(assert_that(anything).is_not_none(), _ObjectAssertion[object])

    # a value whose only claim is a shape is where the refinement stops, and a `TypeIs` predicate is the way back
    def _is_countable(value: object) -> TypeIs[_Countable]:
        return isinstance(value, _Countable)

    maybe_bag = cast("_Countable | None", _Countable())
    assert_type(assert_that(maybe_bag).is_not_none(), _ObjectAssertion[_Countable])
    assert_type(assert_that(anything).is_instance_of(_Countable), _ObjectAssertion[_Countable])
    assert_type(assert_that(anything).satisfies(_is_countable), AssertionBuilder[_Countable])

    class _Order: ...

    class _PaidOrder(_Order): ...

    class _Shouted(str): ...

    def _is_paid(order: _Order) -> TypeIs[_PaidOrder]:
        return isinstance(order, _PaidOrder)

    some_order = cast("_Order", _PaidOrder())
    assert_type(assert_that(some_order).satisfies(_is_paid), _ObjectAssertion[_PaidOrder])
    assert_type(assert_that(some_order).satisfies(_is_paid).value, _PaidOrder)
    assert_type(assert_that(anything).is_not_none().satisfies(_is_paid).value, _PaidOrder)
    assert_type(assert_that(some_order).satisfies(lambda item: bool(item)), _ObjectAssertion[_Order])

    # refinement is not confined to the generic fallback: a JSON payload typed `dict[str, Any]` reaches
    # the per-type Protocol, is where a domain predicate is most often applied, and used to stop there
    payload = cast("dict[str, Any]", {"id": 1})
    assert_type(assert_that(payload).satisfies(_is_paid), _ObjectAssertion[_PaidOrder])
    assert_type(assert_that(payload).satisfies(_is_paid).value, _PaidOrder)

    # the guard has to be one the subject can be handed to: a concretely typed view binds the predicate to
    # its own value, so a guard about orders is refused on a `str` rather than promising a narrowing
    def _is_shouted(text: str) -> TypeIs[_Shouted]:
        return text.isupper()

    assert_type(assert_that("x").satisfies(_is_shouted), AssertionBuilder[_Shouted])
    assert_type(assert_that(payload).satisfies(lambda item: bool(item)), _DictAssertion[str, Any])

    # the narrowing capstone: the return type is driven by the model argument and not the value, so the
    # `Any` a decoded payload carries and an explicitly dict-typed one both narrow where a method could not
    json_payload = cast("Any", {"id": 1})
    dict_payload = cast("dict[str, object]", {"id": 1})
    assert_type(assert_conforms(anything, _Order), AssertionBuilder[_Order])
    assert_type(assert_conforms(anything, _Order).value, _Order)
    assert_type(assert_conforms(json_payload, _PaidOrder).value, _PaidOrder)
    assert_type(assert_conforms(dict_payload, _PaidOrder).value, _PaidOrder)
    assert_type(assert_conforms(anything, _Order, each=True), AssertionBuilder[list[_Order]])
    assert_type(assert_conforms(anything, _Order, each=True).value, list[_Order])

    assert_type(assert_that([1, 2, 3]).first().value, int)
    assert_type(assert_that(["a", "b"]).last().value, str)
    assert_type(assert_that((1.0, 2.0)).element(0).value, float)
    order_list = cast("list[_Order]", [])
    assert_type(assert_that(order_list).single().value, _Order)
    assert_type(assert_that(order_list).first(), AssertionBuilder[_Order])
    # a map pivot re-types the element and a filter preserves it, and either way a list comes back
    assert_type(assert_that([1, 2]).mapped(str).value, list[str])
    assert_type(assert_that(order_list).filtered_on(lambda o: True).value, list[_Order])
    assert_type(assert_that((1, 2)).filtered_on(lambda n: True).value, list[int])
    assert_type(assert_that({1, 2}).mapped(str).value, list[str])

    # a character is a string and a byte an int, so both stay put; the invoked view lands on text
    assert_type(assert_that("abc").first(), _StringAssertion)
    assert_type(assert_that("abc").last(), _StringAssertion)
    assert_type(assert_that("abc").element(1), _StringAssertion)
    assert_type(assert_that("a").single(), _StringAssertion)
    assert_type(assert_that("abc").filtered_on(lambda char: True), _ListAssertion[str])
    assert_type(assert_that("abc").mapped(str.upper), _ListAssertion[str])
    assert_type(assert_that("abc").flat_mapped(lambda char: [char]), _ListAssertion[str])
    assert_type(assert_that(b"abc").first(), _NumericAssertion[int])
    assert_type(assert_that(bytearray(b"abc")).last(), _NumericAssertion[int])
    assert_type(assert_that(b"abc").element(0), _NumericAssertion[int])
    assert_type(assert_that(b"a").single(), _NumericAssertion[int])
    assert_type(assert_that(b"abc").filtered_on(lambda byte: True), _ListAssertion[int])
    assert_type(assert_that(b"abc").mapped(lambda byte: byte * 2), _ListAssertion[int])
    assert_type(assert_that({"a": 1}).first(), AssertionBuilder[str])
    assert_type(assert_that({"a": 1}).filtered_on(lambda key: True), _ListAssertion[str])
    assert_type(assert_that({"a": 1}).mapped(str.upper), _ListAssertion[str])

    assert_type(assert_that(42).is_not_iterable(), _NumericAssertion[int])
    assert_type(assert_that(datetime.date(2026, 1, 1)).is_not_iterable(), _DateAssertion)
    assert_type(assert_that(pathlib.Path("/tmp")).is_iterable(), _PathAssertion)
    assert_type(assert_that("abc").is_iterable(), _StringAssertion)
    assert_type(assert_that({"a": 1}).is_iterable(), _DictAssertion[str, int])
    assert_type(assert_that("aBc").is_sorted(key=str.lower), _StringAssertion)
    assert_type(assert_that(b"abc").is_sorted(key=lambda byte: -byte), _BytesAssertion[bytes])
    assert_type(assert_that({"a": 1}).is_sorted(key=str.upper), _DictAssertion[str, int])
    assert_type(assert_that([3, 1]).is_sorted(key=abs), _IterableAssertion[int])
    assert_type(assert_that(b"ab").is_subset_of(b"abc"), _BytesAssertion[bytes])

    assert_type(assert_that("text").value, str)
    assert_type(assert_that(42).value, int)
    assert_type(assert_that({"key": 1}).value, dict[str, int])
    assert_type(assert_that([1, 2]).value, list[int] | tuple[int, ...] | set[int] | frozenset[int])
    assert_type(assert_that(b"raw").value, bytes)
    assert_type(assert_that(pathlib.Path("/tmp")).value, pathlib.Path)
    assert_type(assert_that(datetime.date(2026, 1, 1)).value, datetime.date)
    assert_type(assert_that(len).value, Callable[..., int])

    # A pivot on the builder hands back an element, and used to be declared as handing back the chain.
    # A narrowing at `assert_that()` cannot reach that: the second pivot lands on the builder regardless
    rows = cast("Sequence[Sequence[int]]", [[1]])
    keys = cast("Mapping[str, int]", {"a": 1})
    assert_type(assert_that(rows).first(), AssertionBuilder[Sequence[int]])
    assert_type(assert_that(rows).first().first(), AssertionBuilder[int])
    assert_type(assert_that(rows).last().element(0), AssertionBuilder[int])
    assert_type(assert_that(keys).first(), AssertionBuilder[str])
    assert_type(assert_that(rows).first().single(), AssertionBuilder[int])
    assert_type(assert_that(rows).first().mapped(str), AssertionBuilder[list[str]])

    class _FakeFrame:
        def pivot(self, *args: object, **kwargs: object) -> object: ...

        @property
        def shape(self) -> object: ...

    class _FakeArray:
        def __array__(self) -> object: ...

        @property
        def strides(self) -> object: ...

        def __len__(self) -> int:
            return 0

    class _Unsized:
        """Carries what an array does but a length, as a numpy scalar does, and gets the fallback."""

        def __array__(self) -> object: ...

        @property
        def strides(self) -> object: ...

    assert_type(assert_that(cast("_Unsized", object())), _ObjectAssertion[_Unsized])
    assert_type(assert_that(cast("_FrameShape", object())), _FrameAssertion[_FrameShape])
    assert_type(assert_that(cast("_ArrayShape", object())), _ArrayAssertion[_ArrayShape])
    frame = cast("_FakeFrame", object())
    array = cast("_FakeArray", object())
    assert_type(assert_that(frame), _FrameAssertion[_FakeFrame])
    assert_type(assert_that(array), _ArrayAssertion[_FakeArray])
    assert_type(assert_that(frame).value, _FakeFrame)
    assert_type(assert_that(array).value, _FakeArray)
    assert_type(assert_that(frame).is_frame_equal(frame), _FrameAssertion[_FakeFrame])
    assert_type(assert_that(array).is_array_equal(array), _ArrayAssertion[_FakeArray])
    assert_type(assert_that(array).is_array_close_to(array, rtol=0.1), _ArrayAssertion[_FakeArray])
    assert_type(assert_that(frame).does_not_contain(9), _FrameAssertion[_FakeFrame])
    assert_type(assert_that(array).does_not_contain(9), _ArrayAssertion[_FakeArray])

    assert_type(match.is_instance_of(int), IsInstanceOfMatcher)
    assert_type(match.is_instance_of(int | str), IsInstanceOfMatcher)
    assert_type(match.is_instance_of((int, str)), IsInstanceOfMatcher)
    assert_type(match.is_instance_of((int | str, float)), IsInstanceOfMatcher)
    # nested to a second level, which `isinstance` accepts and the alias is recursive to match
    assert_type(match.is_instance_of((int, (str, float))), IsInstanceOfMatcher)
    assert_type(match.is_type_of(int), IsTypeOfMatcher)

    class _FakeResponse:
        status_code: int
        headers: dict[str, str]

        def json(self) -> Any: ...

    response = _FakeResponse()
    assert_type(assert_that(response), _CapableAssertion[_FakeResponse])
    assert_type(assert_that(response).decoded_as_json(), AssertionBuilder[object])
    assert_type(assert_that(response).decoded_as_json().value, object)

    # every shape `assert_warn` documents a logger as: the docstring says `Logger`, the default is a
    # `LoggerAdapter`, and only `warning()` is ever reached, so a concrete type would refuse working code
    class _OwnLogger:
        def warning(self, msg: object) -> None: ...

    assert_type(assert_warn("foo", logger=logging.getLogger("app")), Any)
    assert_type(assert_warn("foo", logger=logging.LoggerAdapter(logging.getLogger("app"), None)), Any)
    assert_type(assert_warn("foo", logger=_OwnLogger()), Any)
    assert_type(assert_warn("foo"), Any)

    # a logger for `log_passes` is anything that answers `isEnabledFor()` and takes `log()`, as both stdlib shapes do
    class _OwnPassLogger:
        def isEnabledFor(self, level: int) -> bool: ...  # noqa: N802 - the name `logging` gives it

        def log(self, level: int, msg: str) -> None: ...

    def _take(outcome: AssertionOutcome) -> None: ...

    assert_type(log_passes(), AbstractContextManager[None])
    assert_type(log_passes(logging.getLogger("app")), AbstractContextManager[None])
    assert_type(log_passes(logging.LoggerAdapter(logging.getLogger("app"), None)), AbstractContextManager[None])
    assert_type(log_passes(_OwnPassLogger(), level=logging.DEBUG), AbstractContextManager[None])
    assert_type(log_passes(on_pass=_take), AbstractContextManager[None])

    # tables built before the call, as the docs show them. `dict` is invariant in both halves, so a table
    # declared `dict[str, ...]` is not a `dict[object, ...]`; `Mapping[Any, ...]` accepts them and is only read
    by_type: dict[type, Callable[[float, float], bool]] = {float: lambda a, e: round(a, 2) == round(e, 2)}
    by_field: dict[str, Callable[[Any, Any], bool]] = {"name": lambda a, e: a.lower() == e.lower()}
    volatile: dict[str, Matcher[str]] = {"id": match.is_uuid()}
    assert_type(assert_that({"n": 1.0}).snapshot(id="a", comparators=by_type), _DictAssertion[str, float])
    assert_type(assert_that({"name": "A"}).snapshot(id="b", comparators=by_field), _DictAssertion[str, str])
    assert_type(assert_that({"id": "x"}).snapshot(id="c", placeholders=volatile), _DictAssertion[str, str])

    # the pivots that change the type, which `tests/test_pin_coverage.py` requires a pin for. A pivot
    # returning the wrong view is silent: the call runs and the assertions after it are read as something
    # they are not
    assert_type(assert_that([{"id": 1}]).extracting("id"), _ListAssertion[Any])
    assert_type(assert_that({"a": {"b": 1}}).at_json_path("$.a.b"), _CoreAssertion)
    assert_type(assert_that("v1.2").matches_with_groups(r"v(\d)\.(\d)"), AssertionBuilder[Any])
    # what the call returned keeps the callable's return type, as every other pivot keeps its element's
    assert_type(
        assert_that(lambda: int("1")).does_not_raise(ValueError).when_called_with().returned(), AssertionBuilder[int]
    )
    assert_type(assert_that(lambda: int("1")).warns().when_called_with().returned(), AssertionBuilder[int])
    assert_type(assert_that(len).warns().when_called_with().not_.contains("x").returned().value, int)
    assert_type(assert_that(lambda: int("1")).does_not_warn().when_called_with().returned().value, int)
    assert_that(len).does_not_raise(ValueError).when_called_with().returned().is_positive()

    # the object fallback carries four numeric assertions, so `Decimal` and `Fraction` keep them. Neither
    # is an `int` or a `float`, so no overload names them and both land here
    assert_type(assert_that(decimal.Decimal("1.5")).is_not_zero(), _ObjectAssertion[decimal.Decimal])
    assert_type(assert_that(fractions.Fraction(3, 2)).is_close_to(1, 5), _ObjectAssertion[fractions.Fraction])
    assert_type(assert_that(decimal.Decimal(0)).is_zero(), _ObjectAssertion[decimal.Decimal])
    assert_type(assert_that(fractions.Fraction(0)).is_not_close_to(1, 5), _ObjectAssertion[fractions.Fraction])
    # a matcher for the length, which is asked about the number `len()` gives
    assert_that([1, 2]).is_length(match.greater_than(1)).satisfies(match.has_length(match.between(1, 2)))
    # a tolerance relative to the expected value, alone or beside the absolute one
    assert_type(assert_that(fractions.Fraction(3, 2)).is_close_to(1, rel=0.5), _ObjectAssertion[fractions.Fraction])
    assert_that(1.5).is_close_to(1, 0.1, rel=0.5).is_not_close_to(9, rel=0.1)

    # `check()` hands back the twin of the view it was reached from, and the twins are generated. A view
    # returning somebody else's twin runs and reports a verdict about the wrong surface
    assert_type(assert_that(True).check(), _CheckBoolAssertion)
    assert_type(assert_that(complex(1, 2)).check(), _CheckComplexAssertion)
    assert_type(assert_that(b"raw").check(), _CheckBytesAssertion[bytes])
    assert_type(assert_that(pathlib.Path("/tmp")).check(), _CheckPathAssertion)
    assert_type(assert_that(datetime.date(2026, 1, 1)).check(), _CheckDateAssertion)
    assert_type(assert_that(datetime.datetime(2026, 1, 1, 12, 0)).check(), _CheckDateTimeAssertion)
    assert_type(assert_that(["a"]).check(), _CheckIterableAssertion[str])
    assert_type(assert_that(lambda: None).check(), _CheckCallableAssertion[None])
    assert_type(assert_that(object()).check(), _CheckObjectAssertion[object])
    assert_type(assert_that(cast("_FrameShape", object())).check(), _CheckFrameAssertion[_FrameShape])
    assert_type(assert_that(cast("_ArrayShape", object())).check(), _CheckArrayAssertion[_ArrayShape])
    assert_type(assert_that({"a": {"b": 1}}).at_json_path("$.a").check(), _CheckCoreAssertion)
    assert_type(assert_that([{"id": 1}]).extracting("id").check(), _CheckListAssertion[Any])
    assert_type(assert_that(len).raises(ValueError).when_called_with().check(), _CheckInvokedAssertion[ValueError])
    assert_type(assert_that(len).raises(ValueError).check(), _CheckExpectedRaiseAssertion[int, ValueError])
    assert_type(assert_that(len).warns().check(), _CheckExpectedWarningAssertion[int])
    assert_type(assert_that(len).does_not_raise(ValueError).check(), _CheckExpectedCompletionAssertion[int])
    assert_type(assert_that(len).warns().when_called_with().check(), _CheckWarnedAssertion[int])
    assert_type(assert_that(len).does_not_raise(ValueError).when_called_with().check(), _CheckCompletedAssertion[int])

    # the rest of the element pivot on the text view, of which only `first` was pinned
    assert_type(assert_that(len).raises(ValueError).when_called_with().last(), _TextAssertion)
    assert_type(assert_that(len).raises(ValueError).when_called_with().element(0), _TextAssertion)
    assert_type(assert_that(len).raises(ValueError).when_called_with().single(), _TextAssertion)

    assert_type(assert_that(b"raw").decoded_as("utf-8"), _StringAssertion)
    assert_type(assert_that(pathlib.Path("/tmp")).value, pathlib.Path)

    # every rung of the three narrowing ladders. Each is an independent mapping from the type it
    # narrows to onto the view that comes back, and `tests/test_pin_coverage.py` requires all of them
    def _is_str(value: object) -> TypeIs[str]: ...
    def _is_bool(value: object) -> TypeIs[bool]: ...
    def _is_int(value: object) -> TypeIs[int]: ...
    def _is_float(value: object) -> TypeIs[float]: ...
    def _is_complex(value: object) -> TypeIs[complex]: ...
    def _is_dict(value: object) -> TypeIs[dict[str, int]]: ...
    def _is_list(value: object) -> TypeIs[list[str] | tuple[str, ...]]: ...
    def _is_set(value: object) -> TypeIs[set[str] | frozenset[str]]: ...
    def _is_datetime(value: object) -> TypeIs[datetime.datetime]: ...
    def _is_date(value: object) -> TypeIs[datetime.date]: ...
    def _is_path(value: object) -> TypeIs[pathlib.Path]: ...
    def _is_bytes(value: object) -> TypeIs[bytes]: ...
    def _is_bytearray(value: object) -> TypeIs[bytearray]: ...
    def _is_callable(value: object) -> TypeIs[Callable[..., object]]: ...

    assert_type(assert_that({"a": 1}).satisfies(_is_str), _StringAssertion)
    assert_type(assert_that({"a": 1}).satisfies(_is_bool), _BoolAssertion)
    assert_type(assert_that({"a": 1}).satisfies(_is_int), _NumericAssertion[int])
    assert_type(assert_that({"a": 1}).satisfies(_is_float), _NumericAssertion[float])
    assert_type(assert_that({"a": 1}).satisfies(_is_complex), _ComplexAssertion)
    assert_type(assert_that({"a": 1}).satisfies(_is_dict), _DictAssertion[str, int])
    assert_type(assert_that({"a": 1}).satisfies(_is_list), _IterableAssertion[str])
    assert_type(assert_that({"a": 1}).satisfies(_is_set), _IterableAssertion[str])
    assert_type(assert_that({"a": 1}).satisfies(_is_datetime), _DateTimeAssertion)
    assert_type(assert_that({"a": 1}).satisfies(_is_date), _DateAssertion)
    assert_type(assert_that({"a": 1}).satisfies(_is_path), _PathAssertion)
    assert_type(assert_that({"a": 1}).satisfies(_is_bytes), _BytesAssertion[bytes])
    assert_type(assert_that({"a": 1}).satisfies(_is_bytearray), _BytesAssertion[bytearray])
    assert_type(assert_that({"a": 1}).satisfies(_is_callable), _CallableAssertion[Any])

    assert_type(assert_that(42).satisfies(_is_str), _StringAssertion)
    assert_type(assert_that(42).satisfies(_is_bool), _BoolAssertion)
    assert_type(assert_that(42).satisfies(_is_int), _NumericAssertion[int])
    assert_type(assert_that(42).satisfies(_is_float), _NumericAssertion[float])
    assert_type(assert_that(42).satisfies(_is_complex), _ComplexAssertion)
    assert_type(assert_that(42).satisfies(_is_dict), _DictAssertion[str, int])
    assert_type(assert_that(42).satisfies(_is_list), _IterableAssertion[str])
    assert_type(assert_that(42).satisfies(_is_set), _IterableAssertion[str])
    assert_type(assert_that(42).satisfies(_is_datetime), _DateTimeAssertion)
    assert_type(assert_that(42).satisfies(_is_date), _DateAssertion)
    assert_type(assert_that(42).satisfies(_is_path), _PathAssertion)
    assert_type(assert_that(42).satisfies(_is_bytes), _BytesAssertion[bytes])
    assert_type(assert_that(42).satisfies(_is_bytearray), _BytesAssertion[bytearray])
    assert_type(assert_that(42).satisfies(_is_callable), _CallableAssertion[Any])

    assert_type(assert_that("text").satisfies(_is_str), _StringAssertion)
    assert_type(assert_that("text").satisfies(_is_bool), _BoolAssertion)
    assert_type(assert_that("text").satisfies(_is_int), _NumericAssertion[int])
    assert_type(assert_that("text").satisfies(_is_float), _NumericAssertion[float])
    assert_type(assert_that("text").satisfies(_is_complex), _ComplexAssertion)
    assert_type(assert_that("text").satisfies(_is_dict), _DictAssertion[str, int])
    assert_type(assert_that("text").satisfies(_is_list), _IterableAssertion[str])
    assert_type(assert_that("text").satisfies(_is_set), _IterableAssertion[str])
    assert_type(assert_that("text").satisfies(_is_datetime), _DateTimeAssertion)
    assert_type(assert_that("text").satisfies(_is_date), _DateAssertion)
    assert_type(assert_that("text").satisfies(_is_path), _PathAssertion)
    assert_type(assert_that("text").satisfies(_is_bytes), _BytesAssertion[bytes])
    assert_type(assert_that("text").satisfies(_is_bytearray), _BytesAssertion[bytearray])
    assert_type(assert_that("text").satisfies(_is_callable), _CallableAssertion[Any])

    assert_type(assert_that(cast("str | None", "text")).is_not_none(), _StringAssertion)
    assert_type(assert_that(cast("complex | None", complex(1, 2))).is_not_none(), _ComplexAssertion)
    assert_type(assert_that(cast("dict[str, int] | None", {"a": 1})).is_not_none(), _DictAssertion[str, int])
    assert_type(assert_that(cast("list[str] | tuple[str, ...] | None", ["a"])).is_not_none(), _IterableAssertion[str])
    assert_type(assert_that(cast("set[str] | frozenset[str] | None", {"a"})).is_not_none(), _IterableAssertion[str])
    assert_type(assert_that(cast("datetime.date | None", datetime.date(2026, 1, 1))).is_not_none(), _DateAssertion)
    assert_type(assert_that(cast("pathlib.Path | None", pathlib.Path("/tmp"))).is_not_none(), _PathAssertion)
    assert_type(assert_that(cast("bytes | None", b"raw")).is_not_none(), _BytesAssertion[bytes])
    assert_type(assert_that(cast("bytearray | None", bytearray(b"raw"))).is_not_none(), _BytesAssertion[bytearray])
    assert_type(assert_that(cast("Callable[..., object] | None", len)).is_not_none(), _CallableAssertion[Any])

    assert_type(assert_that(object()).is_instance_of(str), _StringAssertion)
    assert_type(assert_that(object()).is_instance_of(bool), _BoolAssertion)
    assert_type(assert_that(object()).is_instance_of(int), _NumericAssertion[int])
    assert_type(assert_that(object()).is_instance_of(float), _NumericAssertion[float])
    assert_type(assert_that(object()).is_instance_of(complex), _ComplexAssertion)
    assert_type(assert_that(object()).is_instance_of(cast("type[dict[str, int]]", dict)), _DictAssertion[str, int])
    assert_type(assert_that(object()).is_instance_of(cast("type[list[str]]", list)), _IterableAssertion[str])
    assert_type(assert_that(object()).is_instance_of(cast("type[set[str]]", set)), _IterableAssertion[str])
    assert_type(assert_that(object()).is_instance_of(datetime.datetime), _DateTimeAssertion)
    assert_type(assert_that(object()).is_instance_of(datetime.date), _DateAssertion)
    assert_type(assert_that(object()).is_instance_of(pathlib.Path), _PathAssertion)
    assert_type(assert_that(object()).is_instance_of(bytes), _BytesAssertion[bytes])
    assert_type(assert_that(object()).is_instance_of(bytearray), _BytesAssertion[bytearray])

    # the flat pivot and the last element on each view that declares its own, which one pin on another
    # view used to answer for
    assert_type(assert_that(["a"]).flat_mapped(lambda item: [item]), _ListAssertion[str])
    assert_type(assert_that({"a": 1}).flat_mapped(lambda key: [key]), _ListAssertion[str])
    assert_type(assert_that(b"raw").flat_mapped(lambda byte: [byte]), _ListAssertion[int])
    assert_type(assert_that(["a"]).last(), AssertionBuilder[str])
    assert_type(assert_that({"a": 1}).last(), AssertionBuilder[str])
    assert_type(assert_that(["a"]).mapped(str.upper), _ListAssertion[str])
    assert_type(assert_that(["a"]).filtered_on(lambda item: item), _ListAssertion[str])

    # the two rungs below the named ones: a capability, then anything at all
    def _is_capable(value: object) -> TypeIs[Mapping[str, int]]: ...
    def _is_anything(value: object) -> TypeIs[_Order]: ...

    assert_type(assert_that({"a": 1}).satisfies(_is_capable), AssertionBuilder[Mapping[str, int]])
    assert_type(assert_that(42).satisfies(_is_capable), AssertionBuilder[Mapping[str, int]])
    assert_type(assert_that({"a": 1}).satisfies(_is_anything), _ObjectAssertion[_Order])
    assert_type(assert_that(42).satisfies(_is_anything), _ObjectAssertion[_Order])
    assert_type(assert_that("text").satisfies(_is_anything), _ObjectAssertion[_Order])

    # the element pivot on each view that declares its own, reached from a subject the gate can read
    assert_type(assert_that(["a"]).first(), AssertionBuilder[str])
    assert_type(assert_that(["a"]).element(0), AssertionBuilder[str])
    assert_type(assert_that(["a"]).single(), AssertionBuilder[str])
    assert_type(assert_that({"a": 1}).element(0), AssertionBuilder[str])
    assert_type(assert_that({"a": 1}).single(), AssertionBuilder[str])
    assert_type(assert_that(object()).value, object)
    assert_type(assert_that(cast("_FrameShape", object())).value, _FrameShape)
    assert_type(assert_that(cast("_ArrayShape", object())).value, _ArrayShape)

    # the capability facade's own pivots, and the two chains a callable view opens
    assert_type(assert_that(lambda: int("1")).eventually(trace=False), _AsyncPoll[int])
    assert_type(assert_that(lambda: int("1")).eventually_sync(timeout=2, trace=False), _SyncPoll[int])
    assert_type(assert_that(_Countable()).eventually(trace=False), _AsyncPoll[Any])
    assert_type(assert_that(_Countable()).eventually_sync(timeout=2, trace=False), _SyncPoll[Any])
    assert_type(assert_that(_Countable()).builder(1), AssertionBuilder[Any])
    assert_type(assert_that(_Countable()).check(), _CheckAnyValue[_Countable])
    assert_type(assert_that(_Countable()).check().val, _Countable)
    assert_type(assert_that([1, 2]).first().check().val, int)
    assert_type(assert_that([1, 2]).first().check().not_.val, int)
    assert_type(assert_that([1, 2]).first().check().value, int)
    assert_type(assert_that([1, 2]).first().check().not_.value, int)
    counters: list[Callable[[], int]] = []
    assert_type(assert_that(counters).first().check().val, Callable[[], int])
    assert_type(assert_that(counters).first().check().not_.value, Callable[[], int])
    assert_type(assert_that(_Countable()).value, _Countable)
    assert_type(assert_that(_Countable()).first(), _CapableAssertion[_Countable])
    assert_type(assert_that(_Countable()).last(), _CapableAssertion[_Countable])
    assert_type(assert_that(_Countable()).single(), _CapableAssertion[_Countable])
    assert_type(assert_that(_Countable()).element(0), _CapableAssertion[_Countable])
    assert_type(assert_that(_Countable()).satisfies(_is_anything), AssertionBuilder[_Order])
    assert_type(assert_that(_Countable()).is_instance_of(str), AssertionBuilder[str])
    assert_type(assert_that(_Countable()).is_instance_of_any(str, int), AssertionBuilder[str | int])
    # two and three classes are rungs of their own, on the facade as on the object view
    assert_type(assert_that(_Countable()).is_instance_of((str, int)), AssertionBuilder[str | int])
    assert_type(assert_that(_Countable()).is_instance_of((str, int, bytes)), AssertionBuilder[str | int | bytes])
    assert_type(assert_that(_Countable()).is_instance_of_any(str, int, bytes), AssertionBuilder[str | int | bytes])
    # pivots the runtime writes `-> Self`: a list from the three a claimed value answers, an open builder otherwise
    assert_type(assert_that(_Countable()).extracting("id"), _ListAssertion[Any])
    assert_type(assert_that(_Countable()).filtered_on(lambda item: True), _ListAssertion[Any])
    assert_type(assert_that(_Countable()).flat_mapped(lambda item: [item]), _ListAssertion[Any])
    assert_type(assert_that(_Countable()).at_json_path("$.id"), AssertionBuilder[Any])
    assert_type(assert_that(_Countable()).returned(), AssertionBuilder[Any])
    assert_type(assert_that(_Countable()).raised(), AssertionBuilder[Any])
    assert_type(assert_that(_Countable()).errors(), AssertionBuilder[Any])
    assert_type(assert_that(_Countable()).error_of(KeyError), AssertionBuilder[Any])
    assert_type(assert_that(_Countable()).caused_by(KeyError), AssertionBuilder[Any])
    assert_type(assert_that(_Countable()).has_root_cause(KeyError), AssertionBuilder[Any])

    # the element pivot on a capable value that is a mapping, which is the rung it keys on
    assert_type(assert_that(_Rowish()).first(), AssertionBuilder[str])
    assert_type(assert_that(_Rowish()).last(), AssertionBuilder[str])
    assert_type(assert_that(_Rowish()).single(), AssertionBuilder[str])
    assert_type(assert_that(_Rowish()).element(0), AssertionBuilder[str])
    # each pivot has two rungs that hand back the builder, told apart by what the claimed value is: a mapping
    # yields its keys, any other source of elements what it holds
    assert_type(assert_that(cast("Mapping[str, int]", {"a": 1})).first(), AssertionBuilder[str])
    assert_type(assert_that(cast("Mapping[str, int]", {"a": 1})).last(), AssertionBuilder[str])
    assert_type(assert_that(cast("Mapping[str, int]", {"a": 1})).element(0), AssertionBuilder[str])
    assert_type(assert_that(cast("Mapping[str, int]", {"a": 1})).single(), AssertionBuilder[str])
    assert_type(assert_that(cast("Sequence[bytes]", [b"a"])).first(), AssertionBuilder[bytes])
    assert_type(assert_that(cast("Sequence[bytes]", [b"a"])).last(), AssertionBuilder[bytes])
    assert_type(assert_that(cast("Sequence[bytes]", [b"a"])).element(0), AssertionBuilder[bytes])
    assert_type(assert_that(cast("Sequence[bytes]", [b"a"])).single(), AssertionBuilder[bytes])
