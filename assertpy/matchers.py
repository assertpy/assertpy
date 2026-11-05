from __future__ import annotations

import threading
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, NamedTuple, SupportsIndex, TypeVar, cast, overload

from ._engine._introspection import is_same_implementation
from ._engine._require import argument, raised_on_purpose, refuse, verdict
from ._matcher_impls import (
    AllOfMatcher,
    AnyOfMatcher,
    BetweenMatcher,
    CloseToMatcher,
    ContainsMatcher,
    ContainsOnlyMatcher,
    ContainsStringMatcher,
    EachMatcher,
    EndsWithMatcher,
    EqualToMatcher,
    GreaterThanMatcher,
    GreaterThanOrEqualToMatcher,
    HasLengthMatcher,
    HasPropertyMatcher,
    HtmlEqualToMatcher,
    IgnoreMatcher,
    IsAfterMatcher,
    IsBeforeMatcher,
    IsCallableMatcher,
    IsDivisibleByMatcher,
    IsEmptyMatcher,
    IsEvenMatcher,
    IsFalsyMatcher,
    IsInMatcher,
    IsNegativeMatcher,
    IsNoneMatcher,
    IsNonEmptyStringMatcher,
    IsNotEmptyMatcher,
    IsNotNoneMatcher,
    IsNowMatcher,
    IsOddMatcher,
    IsPositiveMatcher,
    IsSortedMatcher,
    IsSubsetOfMatcher,
    IsTruthyMatcher,
    IsUuidMatcher,
    IsZeroMatcher,
    LessThanMatcher,
    LessThanOrEqualToMatcher,
    MatchesRegexMatcher,
    NotMatcher,
    StartsWithMatcher,
    StructureMatcher,
    _Composable,
    _is_matcher,
    _refused,
)
from ._matcher_impls import (
    BaseMatcher as BaseMatcher,
)
from ._matcher_impls import (
    IsInstanceOfMatcher as IsInstanceOfMatcher,
)
from ._matcher_impls import (
    IsTypeOfMatcher as IsTypeOfMatcher,
)
from ._matcher_impls import (
    Matcher as Matcher,
)
from ._matcher_impls import (
    MatchResult as MatchResult,
)

if TYPE_CHECKING:
    import re
    from collections.abc import Callable, Iterable
    from typing import Literal

    # the element a membership matcher judges, so `match.contains("x")` is a matcher for collections of strings
    _Item = TypeVar("_Item")

    from ._matcher_impls import ClassInfo

__tracebackhide__ = raised_on_purpose


class _Resolved(NamedTuple):
    """What one reading of the argument decided: how to ask it, and how to say what was asked."""

    apply: Callable[[object], bool]
    describe: Callable[[], str]


def _resolved(matcher: Matcher[Any] | Callable[..., object]) -> _Resolved:
    """`_apply_matcher`'s dispatch, decided once for a matcher a loop is about to ask many times.

    `_is_matcher` walks the protocol for anything that is not a `BaseMatcher`, which a loop over ten
    thousand items pays per item: `any_satisfy` over ten thousand measured 13.05 ms against 0.59 ms.

    Kept beside `_apply_matcher` rather than under it: routing the single-call form through a closure
    measured 2.54 ms against 2.75 ms over two thousand matchers asked once each, which is what
    `satisfies_exactly` does.

    The rule this states for a whole loop, in the same order `_apply_matcher` reads it: the matcher
    protocol first, a callable second, and that reading holds for every value the loop asks about.  An
    argument that grows or drops the three members while the loop runs keeps being asked the way it was
    read at the start, and the description in the failure comes from that same reading rather than from
    reading it again afterwards.  Nothing here is an immutability claim: a function and a
    `functools.partial` both take attributes, which is exactly why the reading is fixed rather than
    repeated.
    """
    if _is_matcher(matcher):
        # bound here, not looked up per value: a matcher that replaces its own member mid-loop would
        # otherwise be asked something other than what was read, and the lookup costs per item besides
        matches = matcher.matches
        return _Resolved(lambda value: bool(verdict(matches(value), subject="the matcher")), matcher.describe)
    if callable(matcher):
        predicate = cast("Callable[..., object]", matcher)
        return _Resolved(lambda value: bool(verdict(predicate(value))), lambda: _describe_callable(predicate))
    refuse(matcher, "a Matcher or a callable", subject=argument("matcher"))


def _apply_matcher(matcher: Matcher[Any] | Callable[..., object], value: object) -> bool:
    """Evaluate a ``Matcher`` or one-arg callable against ``value``.

    Shared resolution for an assertion that accepts either a `Matcher` or a callable predicate,
    mirroring the dispatch in ``satisfies``/``each``: a `Matcher` is checked via ``matches``, a callable
    via its return value.  Its callers, ``satisfies_exactly`` and the snapshot placeholders, refuse
    anything else before the value is read, so that a refusal does not wait on the data.
    """
    if _is_matcher(matcher):
        return bool(verdict(matcher.matches(value), subject="the matcher"))
    return bool(verdict(cast("Callable[..., object]", matcher)(value)))


def _evaluate_matcher(matcher: Matcher[Any], value: object) -> MatchResult:
    """One `MatchResult` from any matcher, including one that never heard of `evaluate()`.

    `BaseMatcher` gets `evaluate()` from its base, but a matcher is allowed to be duck-typed: the
    `Matcher` protocol is three methods and stays three, because widening it would un-match every
    third-party matcher written against the documented shape.  The composition that `BaseMatcher` does
    for its subclasses is done here for everything else.
    """
    evaluate = getattr(matcher, "evaluate", None)
    if evaluate is not None:
        return evaluate(value)
    if verdict(matcher.matches(value), subject="the matcher"):
        return MatchResult(matched=True, description=matcher.describe())
    return _refused(matcher, value)


def _describe_callable(predicate: Callable[..., object]) -> str:
    """A readable, deterministic name for a predicate callable in a message.

    Avoids the ``<function <lambda> at 0x...>`` repr, whose address is noise that changes every run,
    while keeping a named function's name (the useful part) and still flagging a lambda as a lambda.
    """
    name = getattr(predicate, "__name__", None)
    if name == "<lambda>":
        return "a lambda predicate"
    if name:
        return f"predicate {name}()"
    return "the given predicate"


def _describe_matcher(matcher: Matcher[Any] | Callable[..., object]) -> str:
    """Describe a ``Matcher`` or callable for the "expected" half of an error or diff entry."""
    if _is_matcher(matcher):
        return matcher.describe()
    return _describe_callable(cast("Callable[..., object]", matcher))


_custom_matchers: dict[str, Callable[..., BaseMatcher]] = {}
_custom_matchers_lock = threading.Lock()


def register_matcher(
    name: str, *, override: bool = False
) -> Callable[[Callable[..., BaseMatcher]], Callable[..., BaseMatcher]]:
    """Register a custom matcher factory on the ``match`` namespace.

    A name already taken by another custom matcher is refused unless ``override`` says otherwise, so
    two libraries registering ``has_status`` find out at import rather than by whichever imported
    last quietly winning.

    A name already taken by a *built-in* matcher is refused outright, and ``override`` cannot lift it.
    ``match.equal_to`` resolves through ordinary attribute lookup, which never reaches this registry,
    so such a registration would not lose an argument - it would simply never run.

    Args:
        name: the name to register on ``match`` (e.g. ``"is_valid_email"``)
        override: replace an existing custom matcher of the same name instead of refusing

    Returns:
        A decorator that registers the wrapped function and returns it unchanged.

    Raises:
        TypeError: if ``name`` is not a string, or the decorated object is not callable
        ValueError: if ``name`` is not an identifier, names a built-in matcher, or names a custom one
            already registered and ``override`` is false

    Examples:
        Register a simple matcher:

            @register_matcher("is_valid_email")
            def is_valid_email():
                return match.matches_regex(r"^[\\w.-]+@[\\w.-]+\\.\\w+$")

            assert_that(email).satisfies(match.is_valid_email())

        Register a parametrised matcher:

            @register_matcher("has_status")
            def has_status(expected: str):
                return match.has_property("status", match.equal_to(expected))

            assert_that(order).satisfies(match.has_status("active"))
    """
    if not isinstance(name, str):
        refuse(name, "a string", subject=argument("name"))
    if not name.isidentifier():
        message = f"name must be a valid Python identifier, got {name!r}"
        _assertpy_refusal = True
        raise ValueError(message)
    if hasattr(_MatchNamespace, name):
        message = (
            f"match.{name} is a built-in matcher, and attribute lookup reaches it before this "
            f"registry: a custom {name!r} would never be called. Register it under another name."
        )
        _assertpy_refusal = True
        raise ValueError(message)

    def decorator(func: Callable[..., BaseMatcher]) -> Callable[..., BaseMatcher]:
        if not callable(func):
            refuse(func, "callable", subject=argument("func"))
        with _custom_matchers_lock:
            # a module imported twice, or a per-module fixture, is not two libraries fighting over one name
            clash = name in _custom_matchers and not is_same_implementation(_custom_matchers[name], func)
            if clash and not override:
                message = (
                    f"a custom matcher named {name!r} is already registered; pass override=True to "
                    f"replace it, or unregister_matcher({name!r}) first"
                )
                _assertpy_refusal = True
                raise ValueError(message)
            _custom_matchers[name] = func
        return func

    return decorator


def unregister_matcher(name: str) -> None:
    """Remove a previously registered custom matcher.

    Args:
        name: the matcher name to remove

    Raises:
        KeyError: if the name is not registered
    """
    with _custom_matchers_lock:
        if name not in _custom_matchers:
            message = f"no custom matcher registered with name {name!r}"
            _assertpy_refusal = True
            raise KeyError(message)
        del _custom_matchers[name]


def clear_custom_matchers() -> None:
    """Remove all registered custom matchers."""
    with _custom_matchers_lock:
        _custom_matchers.clear()


class _MatchNamespace:
    """Factory namespace for creating matcher instances.

    Usage:

        from assertpy import match

        assert_that(value).satisfies(match.greater_than(5) & match.less_than(10))
        assert_that(items).each(match.is_positive())
    """

    @staticmethod
    def equal_to(expected: object, strict_types: bool = False, **options: object) -> EqualToMatcher:
        """Matcher for a value equal to ``expected``.

        Args:
            expected: the value to compare against
            strict_types: also require the same type, so ``True`` no longer matches ``1``.  The same
                relation ``is_equal_to(..., strict_types=True)`` applies, spelled for a spec.
            **options: the rest of what
                [`is_equal_to()`][assertpy.base.BaseMixin.is_equal_to] accepts, with the same meaning:
                ``tolerance``, ``rel``, ``comparators``, ``ignore``, ``include`` and ``ignore_null``.  One
                relation, one set of knobs, whichever way it is spelled.

        Examples:
            Usage:

                assert_that(reading).satisfies(match.equal_to(expected, tolerance=0.01))
                assert_that(payload).matches_structure({"user": match.equal_to(user, ignore="updated_at")})
        """
        return EqualToMatcher(expected, strict_types, **options)

    @staticmethod
    def greater_than(val: object) -> GreaterThanMatcher:
        """Matcher for a value greater than ``val``."""
        return GreaterThanMatcher(val)

    @staticmethod
    def greater_than_or_equal_to(val: object) -> GreaterThanOrEqualToMatcher:
        """Matcher for a value greater than or equal to ``val``."""
        return GreaterThanOrEqualToMatcher(val)

    @staticmethod
    def less_than(val: object) -> LessThanMatcher:
        """Matcher for a value less than ``val``."""
        return LessThanMatcher(val)

    @staticmethod
    def less_than_or_equal_to(val: object) -> LessThanOrEqualToMatcher:
        """Matcher for a value less than or equal to ``val``."""
        return LessThanOrEqualToMatcher(val)

    @staticmethod
    def between(low: object, high: object) -> BetweenMatcher:
        """Matcher for a value in the inclusive range ``low`` to ``high``."""
        return BetweenMatcher(low, high)

    @staticmethod
    def close_to(expected: object, tolerance: object = None, *, rel: object = None) -> CloseToMatcher:
        """Matcher for a value within ``tolerance`` of ``expected``, measured as `is_close_to()` measures it.

        The distance is taken three ways, the difference and the window around each side, and any of them
        holding is enough, which a float rounds differently at the boundary.  An infinity is close only to
        itself, whatever the tolerance, and a NaN to nothing.  ``rel`` measures as
        [`is_close_to()`][assertpy.numeric.NumericMixin.is_close_to] does, a fraction of the size of
        ``expected``, and beside ``tolerance`` either holding is enough.

        Args:
            expected: the target value
            tolerance: the allowed distance from ``expected``
            rel: the maximum allowed difference as a fraction of the size of ``expected``, for numbers
        """
        return CloseToMatcher(expected, tolerance, rel)

    @staticmethod
    def is_none() -> IsNoneMatcher:
        """Matcher for ``None``."""
        return IsNoneMatcher()

    @staticmethod
    def is_not_none() -> IsNotNoneMatcher:
        """Matcher for any value that is not ``None``."""
        return IsNotNoneMatcher()

    @staticmethod
    def is_instance_of(expected_type: ClassInfo) -> IsInstanceOfMatcher:
        """Matcher for an instance of ``expected_type`` (via ``isinstance``).

        Accepts whatever ``isinstance`` accepts: a class, a union (``int | str``), or a tuple of
        either.  The builder assertion of the same name stays narrower on purpose - its overloads
        refine the tracked value to the given class, and a union has no single class to refine to.
        Reach for `is_instance_of_any` there.
        """
        return IsInstanceOfMatcher(expected_type)

    @staticmethod
    def is_type_of(expected_type: type) -> IsTypeOfMatcher:
        """Matcher for exactly ``expected_type``, rejecting subclasses (``int`` but not ``bool``)."""
        return IsTypeOfMatcher(expected_type)

    @staticmethod
    def is_truthy() -> IsTruthyMatcher:
        """Matcher for a truthy value."""
        return IsTruthyMatcher()

    @staticmethod
    def is_falsy() -> IsFalsyMatcher:
        """Matcher for a falsy value."""
        return IsFalsyMatcher()

    @staticmethod
    def has_length(length: SupportsIndex | Matcher[int]) -> HasLengthMatcher:
        """Matcher for a value whose ``len()`` equals ``length``, or satisfies it where it is a matcher."""
        return HasLengthMatcher(length)

    @staticmethod
    def is_length(length: SupportsIndex | Matcher[int]) -> HasLengthMatcher:
        """Matcher for a value whose ``len()`` equals ``length``, or satisfies it where it is a matcher.

        The same matcher as `has_length()`, under the name the fluent assertion uses
        ([`is_length()`][assertpy.base.BaseMixin.is_length]).  One relation was reachable as
        ``has_length`` from the matcher namespace and as ``is_length`` from the builder, so which name
        worked depended on which of the two a reader had seen first.  Both work from both now.
        """
        return HasLengthMatcher(length)

    @staticmethod
    def is_empty() -> IsEmptyMatcher:
        """Matcher for an empty value (``len() == 0``)."""
        return IsEmptyMatcher()

    @staticmethod
    def is_not_empty() -> IsNotEmptyMatcher:
        """Matcher for a non-empty value (``len() > 0``)."""
        return IsNotEmptyMatcher()

    @staticmethod
    def is_positive() -> IsPositiveMatcher:
        """Matcher for a value greater than zero."""
        return IsPositiveMatcher()

    @staticmethod
    def is_negative() -> IsNegativeMatcher:
        """Matcher for a value less than zero."""
        return IsNegativeMatcher()

    @staticmethod
    def is_zero() -> IsZeroMatcher:
        """Matcher for a value equal to zero."""
        return IsZeroMatcher()

    @staticmethod
    def is_even() -> IsEvenMatcher:
        """Matcher for an even integer."""
        return IsEvenMatcher()

    @staticmethod
    def is_odd() -> IsOddMatcher:
        """Matcher for an odd integer."""
        return IsOddMatcher()

    @staticmethod
    def is_divisible_by(divisor: SupportsIndex) -> IsDivisibleByMatcher:
        """Matcher for an integer divisible by ``divisor``."""
        return IsDivisibleByMatcher(divisor)

    @staticmethod
    def is_callable() -> IsCallableMatcher:
        """Matcher for a callable object."""
        return IsCallableMatcher()

    @staticmethod
    def is_in(*values: object) -> IsInMatcher:
        """Matcher for a value present in ``values``.

        Args:
            *values: the candidate values; the matched value must equal one of them
        """
        return IsInMatcher(*values)

    @staticmethod
    def has_property(name: str, matcher: Matcher[Any] | None = None) -> HasPropertyMatcher:
        """Matcher for an object with attribute ``name``, optionally matching ``matcher``.

        Args:
            name: the attribute name the object must have
            matcher: optional matcher the attribute value must satisfy; if ``None``,
                only the presence of the attribute is checked
        """
        return HasPropertyMatcher(name, matcher)

    @staticmethod
    def contains_string(substring: str | bytes) -> _Composable[str | bytes]:
        """Matcher for text containing ``substring``, on `str` and on `bytes` alike."""
        return ContainsStringMatcher(substring)

    @staticmethod
    def matches_regex(pattern: str | re.Pattern[str]) -> _Composable[str]:
        """Matcher for a string in which ``pattern`` (a string, or compiled from one) is found (``re.search``)."""
        return MatchesRegexMatcher(pattern)

    @staticmethod
    def html_equal_to(expected: str, *, whitespace: Literal["lenient", "exact"] = "lenient") -> _Composable[str]:
        """Matcher for a string holding the same HTML as ``expected``, read as
        [`is_html_equal_to()`][assertpy.string.StringMixin.is_html_equal_to] reads it.

        ``expected`` is read when the matcher is built, and markup that cannot be read is refused there.  A
        value that is not a string, or whose markup cannot be read, does not match.
        """
        return HtmlEqualToMatcher(expected, whitespace)

    @staticmethod
    def starts_with(prefix: str | bytes) -> _Composable[str | bytes]:
        """Matcher for text starting with ``prefix``, on `str` and on `bytes` alike."""
        return StartsWithMatcher(prefix)

    @staticmethod
    def ends_with(suffix: str | bytes) -> _Composable[str | bytes]:
        """Matcher for text ending with ``suffix``, on `str` and on `bytes` alike."""
        return EndsWithMatcher(suffix)

    @staticmethod
    def all_of(*matchers: Matcher[Any]) -> AllOfMatcher:
        """Matcher that holds when every one of ``matchers`` matches (the ``&`` operator)."""
        return AllOfMatcher(*matchers)

    @staticmethod
    def any_of(*matchers: Matcher[Any]) -> AnyOfMatcher:
        """Matcher that holds when at least one of ``matchers`` matches (the ``|`` operator)."""
        return AnyOfMatcher(*matchers)

    @staticmethod
    def not_(matcher: Matcher[Any]) -> NotMatcher:
        """Matcher that inverts ``matcher`` (the ``~`` operator)."""
        return NotMatcher(matcher)

    @staticmethod
    def ignore() -> IgnoreMatcher:
        """Matcher that accepts anything; useful as a placeholder in ``structure`` specs."""
        return IgnoreMatcher()

    @staticmethod
    def is_uuid() -> IsUuidMatcher:
        """Matcher for a string parseable as a UUID."""
        return IsUuidMatcher()

    @staticmethod
    def is_non_empty_string() -> IsNonEmptyStringMatcher:
        """Matcher for a non-empty string."""
        return IsNonEmptyStringMatcher()

    @staticmethod
    def is_now(delta: float | timedelta = 2.0) -> IsNowMatcher:
        """Matcher for a ``datetime`` within ``delta`` of the current time.

        Args:
            delta: tolerance as seconds (a number) or a ``timedelta``, zero or more; defaults to 2 seconds.
                Naive and timezone-aware values are both handled (compared against ``now`` in the same
                awareness).

        Raises:
            ValueError: if delta is negative, or a number of seconds no ``timedelta`` holds
        """
        if not isinstance(delta, timedelta):
            # asked of the number: made a span, a tenth of a microsecond below nothing is none, and 1e20 overflows
            if isinstance(delta, (int, float)) and delta < 0:
                _assertpy_refusal = True
                raise ValueError("given delta arg must not be negative")
            try:
                delta = timedelta(seconds=delta)
            except (OverflowError, ValueError):
                message = f"given delta arg must be a number of seconds a timedelta holds, but was <{delta}>"
                _assertpy_refusal = True
                raise ValueError(message) from None
        return IsNowMatcher(delta)

    @staticmethod
    def is_before(other: datetime) -> IsBeforeMatcher:
        """Matcher for a ``datetime`` strictly before ``other`` (a non-comparable value never matches)."""
        return IsBeforeMatcher(other)

    @staticmethod
    def is_after(other: datetime) -> IsAfterMatcher:
        """Matcher for a ``datetime`` strictly after ``other`` (a non-comparable value never matches)."""
        return IsAfterMatcher(other)

    @staticmethod
    def contains(*items: _Item) -> _Composable[Iterable[_Item]]:
        """Matcher for a collection containing every one of ``items``.

        The spec spelling of [`contains()`][assertpy.contains.ContainsMixin.contains], with the same
        rules: a mapping is searched by key, and a matcher among the items is satisfied by any element.

        Examples:
            Usage:

                assert_that(payload).matches_structure({"tags": match.contains("beta")})
                assert_that(rows).satisfies(match.contains(match.greater_than(100)))
        """
        return ContainsMatcher(*items)

    @staticmethod
    def contains_only(*items: _Item) -> _Composable[Iterable[_Item]]:
        """Matcher for a collection holding these items and nothing else.

        The spec spelling of [`contains_only()`][assertpy.contains.ContainsMixin.contains_only].
        """
        return ContainsOnlyMatcher(*items)

    @overload
    @staticmethod
    def is_subset_of(superset: Iterable[_Item], /) -> _Composable[Iterable[_Item]]: ...

    @overload
    @staticmethod
    def is_subset_of(*superset: _Item) -> _Composable[Iterable[_Item]]: ...

    @staticmethod
    def is_subset_of(*superset: object) -> _Composable[Iterable[Any]]:
        """Matcher for a collection whose items all appear in ``superset``.

        The spec spelling of [`is_subset_of()`][assertpy.collection.CollectionMixin.is_subset_of].
        Takes the superset either as one collection or as loose items, which is why it is overloaded:
        read off a single union, a checker cannot tell `[1, 2]` the collection from `[1, 2]` the item.

        An ordinary collection stays a live view of itself, the way ``equal_to`` keeps its expected
        value; a one-shot iterator is drained when the matcher is built, since it could not answer a
        second time otherwise.  Handing in an endless iterator therefore never returns.
        """
        return IsSubsetOfMatcher(*superset)

    @staticmethod
    def is_sorted(key: Callable[[Any], Any] | None = None, reverse: bool = False) -> _Composable[Iterable[Any]]:
        """Matcher for a collection in order, optionally by ``key`` and optionally reversed.

        The spec spelling of [`is_sorted()`][assertpy.collection.CollectionMixin.is_sorted].
        """
        return IsSortedMatcher(key, reverse)

    @staticmethod
    def each_item(matcher: Matcher[Any]) -> EachMatcher:
        """Matcher for an iterable whose every item matches ``matcher``.

        Args:
            matcher: the matcher each item of the iterable must satisfy; a non-iterable
                value never matches
        """
        return EachMatcher(matcher)

    @staticmethod
    def structure(spec: dict[Any, Any]) -> StructureMatcher:
        """Matcher for a dict matching ``spec``.

        Args:
            spec: dict whose values are matchers, raw values (compared with ``==``),
                or nested dict specs. Keys present in the value but absent from the spec are ignored.

        Examples:
            Usage:

                assert_that(user).satisfies(
                    match.structure({"id": match.is_instance_of(int), "name": "Alice"})
                )
        """
        return StructureMatcher(spec)

    def __getattr__(self, name: str) -> Callable[..., BaseMatcher]:
        with _custom_matchers_lock:
            try:
                factory = _custom_matchers[name]
            except KeyError:
                message = f"match has no matcher {name!r}"
                _assertpy_refusal = True
                raise AttributeError(message) from None
        return factory


match: _MatchNamespace = _MatchNamespace()
