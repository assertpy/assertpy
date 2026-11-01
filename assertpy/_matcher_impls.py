from __future__ import annotations

import functools
import sys
import uuid as _uuid_mod
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from fractions import Fraction
from types import UnionType
from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
    Final,
    NamedTuple,
    NoReturn,
    Protocol,
    SupportsIndex,
    TypeVar,
    Union,
    cast,
    get_origin,
    runtime_checkable,
)

from ._engine._compare import (
    _build_compare_config,
    _config_note,
    _guarded_equal,
    _is_real_number,
    _keyed_types_differ,
    _non_finite,
    _resolve_comparator,
    plainly_within,
    require_rel,
    within_either,
    zero_of,
)
from ._engine._equality import (
    IncludeKeysMissingError,
    filtered_differs,
    key_specs_given,
    mapping_differs,
    mapping_shaped,
    values_differ,
)
from ._engine._introspection import (
    MappingLike,
    is_attrs_instance,
    is_mapping_like,
    is_model_dump_object,
    is_own_iterator,
    materialized,
)
from ._engine._membership import (
    MembershipRefusedError,
    is_searchable,
    is_walkable,
    missing_items,
    only_faults,
    searchable,
    subset_faults,
)
from ._engine._ordering import (
    REFUSALS,
    UnorderableError,
    equal_past,
    equals,
    first_out_of_order,
    first_plainly_out_of_order,
    holds,
    lookup,
    may_broadcast,
    member,
    numpy_duration,
    plainly_sortable,
    require_integer,
    whole_number,
)
from ._engine._path import _ROOT, _Path
from ._engine._require import (
    NON_MATCHER_TYPES,
    VerdictError,
    argument,
    raised_inside,
    raised_on_purpose,
    refuse,
    reject_unknown_kwargs,
    require_pattern,
    verdict,
)
from ._engine._size import length_of
from ._engine._text import contains as text_contains
from ._engine._text import ends_with as text_ends_with
from ._engine._text import starts_with as text_starts_with
from ._hints import matcher_for_a_class, type_beside_a_class
from .errors import _capped, _capped_format, _capped_repr, _safe_repr, _told_apart, _type_expression_name

if TYPE_CHECKING:
    import re
    from collections.abc import Callable
    from typing import TypeAlias

    from typing_extensions import TypeIs

    from ._engine._compare import _CompareConfig
    from .errors import DiffResult

    # nested because `isinstance()` accepts tuples nested to any depth.  Only the recursive reference is
    # quoted: ty ignores an alias whose whole right-hand side is a string, and `is_instance_of("int")`
    # stopped being a type error.  A PEP 695 `type` statement is read by all three and is a SyntaxError on 3.10
    ClassInfo: TypeAlias = type | UnionType | tuple[type | UnionType | tuple["ClassInfo", ...], ...]
    _ExceptionClasses: TypeAlias = type[BaseException] | UnionType | tuple["_ExceptionClasses", ...]
    _WarningClasses: TypeAlias = type[Warning] | UnionType | tuple["_WarningClasses", ...]
    _RetriedClasses: TypeAlias = type[Exception] | UnionType | tuple["_RetriedClasses", ...]
    # several classes, any one of which will do; one class is spelled beside these, where it can stay typed as itself
    ExceptionInfo: TypeAlias = UnionType | tuple[_ExceptionClasses, ...]
    WarningInfo: TypeAlias = UnionType | tuple[_WarningClasses, ...]
    RetriedInfo: TypeAlias = UnionType | tuple[_RetriedClasses, ...]

__tracebackhide__ = raised_on_purpose

_M_contra = TypeVar("_M_contra", contravariant=True)


@runtime_checkable
class Matcher(Protocol[_M_contra]):
    """Protocol for composable matcher objects, parameterised by the value they judge.

    Contravariant, because a matcher *consumes* the value: one written for `object` answers about an
    `int`, and one written for `str` does not.  That is the direction that makes
    `satisfies(match.starts_with("a"))` on an `int` a type error while keeping `match.is_none()` usable
    anywhere.

    Written without a PEP 696 default on purpose: that spelling needs `typing_extensions` on everything
    before 3.13, and this package declares it only for 3.10.  A bare `Matcher` in an annotation is read
    as `Matcher[Any]` by all four checkers anyway, so existing annotations keep their meaning.
    """

    def matches(self, value: _M_contra) -> bool: ...

    def describe(self) -> str: ...

    def describe_mismatch(self, value: _M_contra) -> str: ...


class _Composable(Matcher[_M_contra], Protocol[_M_contra]):
    """A built-in matcher bound to the value it judges that keeps the operators of `BaseMatcher`.

    A factory typed as the bare `Matcher` lost ``&``, ``|`` and ``~`` to every checker, though its
    runtime object has them.  The operators are declared the way `BaseMatcher` declares them, so what
    they return judges anything, as every composition does.
    """

    def __and__(self, other: Matcher[Any]) -> AllOfMatcher: ...

    def __or__(self, other: Matcher[Any]) -> AnyOfMatcher: ...

    def __invert__(self) -> NotMatcher: ...


def _refused(matcher: Matcher[Any], value: object) -> MatchResult:
    """The result for a value a matcher has already turned down, without asking it again.

    The verdict and the reason used to come from two calls, and a matcher that carries state, or reads a
    one-shot source, answers the second one differently: one returning False and then True turned a
    refused value into a passing assertion.
    """
    return MatchResult(matched=False, description=matcher.describe(), mismatch=matcher.describe_mismatch(value))


def _stated_reason(matcher: Matcher[Any], value: object) -> str:
    """What *matcher* says about a value it has already refused, without asking for its verdict again.

    A value that is its own iterator was spent on the verdict, so it gets the requirement alone: read
    again, its remainder was described as the value, and an endless one was read forever.
    """
    if is_own_iterator(value):
        return matcher.describe()
    refused = _refused(matcher, value)
    return f"{refused.description} ({refused.mismatch})"


def _has_own_evaluate(matcher: object) -> bool:
    """Whether *matcher* declares `evaluate()` itself instead of inheriting the composed default.

    Named after what it checks rather than after why it is asked.  The reason is usually that the
    matcher walks its value, but a matcher may override `evaluate()` for a structured result without
    walking anything, and a name promising a walk would invite an optimisation that is not sound.

    One that does has to be asked once: the default asks `matches()` and then `describe_mismatch()`,
    which walks the value again and, over a one-shot value, sees what the first walk left.  One that
    answers from a type check gains nothing, and a `MatchResult` per leaf of a structure is an
    allocation and a rendered description per leaf, measured at 59% of the structural benchmark.

    `getattr` with a default rather than an attribute access: a duck-typed matcher satisfies the
    protocol with three methods and need not have `evaluate` at all.

    A composite answers for what it holds rather than for its own class, since it walks a value only as
    far as its parts do.  Asked by class, `greater_than(0) & less_than(10)` would take the one-call path
    for nothing and pay a `MatchResult` and a recursive `describe()` per structural leaf: 0.35 ms became
    0.75 ms over 200 records.

    A subclass of a composite is a matcher of its own, asked as it answers: the `evaluate()` it inherits
    from the composite would disagree with a `matches()` it overrides, so only one it declares counts.
    """
    if isinstance(matcher, _COMPOSITES):
        if _composed(matcher):
            return matcher.walks_its_value
        inherited = (BaseMatcher.evaluate, AllOfMatcher.evaluate, AnyOfMatcher.evaluate, NotMatcher.evaluate)
        return getattr(type(matcher), "evaluate", BaseMatcher.evaluate) not in inherited
    return getattr(type(matcher), "evaluate", BaseMatcher.evaluate) is not BaseMatcher.evaluate


def _is_matcher(obj: object) -> TypeIs[Matcher[Any]]:
    """Fast membership test for the runtime_checkable ``Matcher`` protocol.

    ``isinstance(x, Matcher)`` is expensive: the runtime_checkable check walks every protocol member
    through ``getattr_static``.  Two fast paths skip it: a builtin operand is never a matcher (frozenset
    membership), and a ``BaseMatcher`` subclass instance is taken as one (a cheap C-level ``isinstance``,
    ~5x faster than the protocol walk).  Any other object - including a duck-typed custom matcher that
    does not inherit ``BaseMatcher`` - falls through to the full protocol check unchanged.

    The second path takes a subclass by inheritance.  One that sets a member to ``None``, which the
    protocol refuses and mypy, Pyright and Pyrefly refuse where it is written, is still a matcher here:
    one that raises ``TypeError`` when the member is called, treated as any matcher that raises, a
    non-match in the any-order pairing.  Asking the three members statically measured about 2.4 us
    against 40 ns per call on a `BaseMatcher`.
    """
    if type(obj) in NON_MATCHER_TYPES:
        return False
    if isinstance(obj, BaseMatcher):
        return True
    return isinstance(obj, Matcher)


def _require_matcher(operand: object, operator: str) -> None:
    """Reject a non-matcher operand where the combinator is built, not where it is later applied.

    Combining silently would hand back a matcher that raises ``AttributeError: 'int' object has no
    attribute 'matches'`` at assertion time, far from the line that built it.
    """
    if not _is_matcher(operand):
        named = matcher_for_a_class(operand)
        message = f"cannot combine a Matcher with <{type(operand).__name__}> using '{operator}'{named}"
        _assertpy_refusal = True
        raise TypeError(message)


def _require_matcher_argument(value: object) -> Matcher[Any]:
    """The matcher a factory was handed, refused where the factory is called, for the reason above."""
    if not _is_matcher(value):
        refuse(value, "a Matcher", subject=argument("matcher"), note=matcher_for_a_class(value))
    return value


@dataclass(frozen=True, slots=True, kw_only=True)
class MatchResult:
    """What a matcher decided about one value, in one object instead of three calls.

    Deliberately not an [`AssertionOutcome`][assertpy.outcome.AssertionOutcome], which is the record of
    a *failed assertion*.  A matcher is asked about every leaf of a structure and about every element of
    a collection, so its result has to stay cheap: four fields, no location, no group, nothing that has
    to be computed before it is known whether anyone will read it.
    """

    matched: bool
    """Whether the value matched."""

    description: str
    """What the matcher requires, in the words it uses in a failure message: ``a positive value``."""

    mismatch: str = ""
    """Why this value did not match, in the words a failure message continues with: ``was <-1>``.

    Empty when it matched.  There is nothing to say about a value that satisfied the matcher, and the
    text would have to be invented.
    """

    diff: DiffResult | None = None
    """A structured diff, from a matcher that compares rather than tests: equality has one, ``is_odd``
    does not."""

    def __bool__(self) -> bool:
        """The verdict, so a result reads the same way the ``matches()`` it can replace did."""
        return self.matched


# the options `is_equal_to` takes: with `strict_types` alone a spec could not say "close enough"
_EQUAL_TO_OPTIONS = frozenset({"ignore", "include", "tolerance", "rel", "comparators", "ignore_null"})


class BaseMatcher:
    """Abstract base for all matchers with operator support.

    A subclass implements either `matches()` or `evaluate()`, and gets the other one from here.
    `matches()` is the cheap primitive: it is what ``==`` calls, and matchers are used as dict values in
    `matches_structure` and as snapshot placeholders, so a comparison must not have to build a result
    object.  `evaluate()` is the whole answer, for a caller that would otherwise ask the same value
    three questions in a row.
    """

    reads_items: ClassVar[bool] = True
    """Whether a one-shot iterator is handed to this matcher as its items rather than as itself.

    An iterator hands its items out once, so a matcher combined with others, or asked after an earlier
    link of a chain read the value, would judge what is left of it.  A matcher that reads the items gets
    them in a list, the same list for every matcher and every link reading the same value.  One that asks
    about the value itself, its type, identity, length or an attribute, sets this to ``False`` and is
    handed the iterator, as a predicate is.  ``True`` by default: a matcher written before this was
    handed the items by `satisfies()`, and goes on being handed them.
    """

    def matches(self, value: Any) -> bool:
        if type(self).evaluate is BaseMatcher.evaluate:
            _assertpy_refusal = True
            raise NotImplementedError("a matcher must implement matches() or evaluate()")
        return self.evaluate(value).matched

    def evaluate(self, value: Any) -> MatchResult:
        """The verdict, the requirement and the reason, from one look at *value*.

        The default composes the three older methods, so a matcher written before this existed answers
        it without changing.  Overriding it is for a matcher whose reason costs what the verdict already
        paid for: the alternative is `matches()` and `describe_mismatch()` walking the same value twice,
        which is how a matcher over a one-shot iterator used to name the wrong element.
        """
        if type(self).matches is BaseMatcher.matches:
            _assertpy_refusal = True
            raise NotImplementedError("a matcher must implement matches() or evaluate()")
        if verdict(self.matches(value), subject="the matcher"):
            return MatchResult(matched=True, description=self.describe())
        return _refused(self, value)

    def describe(self) -> str:
        _assertpy_refusal = True
        raise NotImplementedError

    def describe_mismatch(self, value: Any) -> str:
        return f"was <{_capped(value)}>"

    def __and__(self, other: Matcher[Any]) -> AllOfMatcher:
        _require_matcher(other, "&")
        left = list(self.matchers) if isinstance(self, AllOfMatcher) else [self]
        right = list(other.matchers) if isinstance(other, AllOfMatcher) else [other]
        return AllOfMatcher(*left, *right)

    def __or__(self, other: Matcher[Any]) -> AnyOfMatcher:
        _require_matcher(other, "|")
        left = list(self.matchers) if isinstance(self, AnyOfMatcher) else [self]
        right = list(other.matchers) if isinstance(other, AnyOfMatcher) else [other]
        return AnyOfMatcher(*left, *right)

    def __invert__(self) -> NotMatcher:
        return NotMatcher(self)

    def __eq__(self, other: object) -> bool:
        # an operand the predicate cannot evaluate means "no match"; ``==`` must never raise
        try:
            return bool(verdict(self.matches(other), subject="the matcher"))
        except VerdictError:  # never a non-match, always a mistake in the test
            raise
        except (TypeError, ValueError):
            return False

    def __hash__(self) -> int:
        return id(self)

    def __repr__(self) -> str:
        return self.describe()


class _OfTheValueItself(BaseMatcher):
    """A matcher of this library that asks about the value itself and takes nothing from it.

    Its type, identity, truthiness, length, an attribute, its equality to an operand.  A one-shot
    iterator is handed to it as it is, and without the guard a predicate gets, which refuses the links
    after it once a part of the value was read: nothing here walks what it is handed.  A subclass defined
    elsewhere gets the guard, since its `matches()` may walk it, and so does one whose operand is code of
    the caller's, an operand `==` hands the value to or a comparator (`_hands_the_value_on`).
    """

    reads_items: ClassVar[bool] = False

    def _hands_the_value_on(self) -> bool:
        """Whether code of the caller's is handed the value: the `__eq__` of an operand, or a comparator.

        A built-in operand (`NON_MATCHER_TYPES`) compares a foreign value without reading it.  Any other one,
        a matcher among them, is asked through its own `__eq__`, which may walk the value.
        """
        return False


_UNREAD: Final = object()


def _reads_items(matcher: object) -> bool:
    """Whether *matcher* is handed a one-shot value's items rather than the value: what `reads_items` says, else so."""
    return getattr(type(matcher), "reads_items", True) is not False


class _ReadOnce:
    """The value one question is asked about, as each matcher asking it should see it.

    A one-shot value handed whole to several matchers is consumed by the first of them, so the rest judge
    what is left of it.  Draining it for every one of them instead is also wrong: a type or identity check
    would be asked about a list the caller never passed.  So a matcher that reads items gets them, drained
    at most once and the same list for every one of them, and one that asks about the value gets the value.

    *items* supplies the items where the value is the subject of a chain, which keeps what every link
    reads, and otherwise they are drained from the value.  *itself* hands the value over to a matcher of
    somebody else's that asks about it, which may still walk it, as a predicate may.
    """

    __slots__ = ("_items", "_itself", "_supply", "value")

    def __init__(
        self, value: Any, items: Callable[[], Any] | None = None, itself: Callable[[], Any] | None = None
    ) -> None:
        self.value = value
        self._supply = items
        self._itself = itself
        self._items: Any = _UNREAD

    def items(self) -> Any:
        if self._items is _UNREAD:
            self._items = materialized(self.value) if self._supply is None else self._supply()
        return self._items

    def handed(self, matcher: object) -> Any:
        """What a matcher that is not a composite is asked about."""
        if _reads_items(matcher):
            return self.items()
        if self._itself is None or (
            isinstance(matcher, _OfTheValueItself)
            and type(matcher).__module__ == __name__
            and not matcher._hands_the_value_on()
        ):
            return self.value
        return self._itself()

    def shown(self) -> Any:
        """The value as a failure names it: its items once a matcher read them, the value itself before that."""
        return self.value if self._items is _UNREAD else self._items


def _verdict_of(matcher: Matcher[Any], read: _ReadOnce) -> bool:
    """`matches()` of *matcher*, asked about the value *read* holds as that matcher should see it."""
    if isinstance(matcher, _COMPOSITES) and _composed(matcher):
        return matcher._holds(read)
    return bool(verdict(matcher.matches(read.handed(matcher)), subject="the matcher"))


def _outcome_of(matcher: Matcher[Any], read: _ReadOnce) -> MatchResult | None:
    """Why *matcher* refused the value *read* holds, as a result, or `None` where it held.

    One look through `evaluate()` where the matcher has its own, and otherwise the verdict from
    `matches()` and the reason after it, so a passing value builds no result at all.
    """
    if _has_own_evaluate(matcher):
        if isinstance(matcher, _COMPOSITES) and _composed(matcher):
            outcome = matcher._evaluated(read)
        else:
            outcome = cast("BaseMatcher", matcher).evaluate(read.handed(matcher))
        return None if outcome.matched else outcome
    if _verdict_of(matcher, read):
        return None
    if isinstance(matcher, _COMPOSITES) and _composed(matcher):
        return matcher._refusal(read)
    return _refused(matcher, read.handed(matcher))


def _failure(matcher: Matcher[Any], read: _ReadOnce) -> str | None:
    """Why *matcher* turned the value *read* holds down, or `None` when it held.

    What this recovers is the reason.  The composites used to list what a failing child *requires* and
    drop what the child had computed about the value, so `an instance of <str>` arrived where the child
    would have said `was <50> of type <int>`.  A composite answers for its own failing part, so a nested
    one reaches a leaf rather than restating a sub-expression `describe()` has already shown.

    One look per leaf, through `evaluate()` where the leaf has its own, for the reason in `_refused`: a
    matcher over a one-shot value answers a second call from what the first walk left.
    """
    if isinstance(matcher, _COMPOSITES) and _composed(matcher):
        held, failure = matcher._decided(read)
        return None if held else failure or matcher.describe()
    value = read.handed(matcher)
    if _has_own_evaluate(matcher):
        outcome = cast("BaseMatcher", matcher).evaluate(value)
    elif verdict(matcher.matches(value), subject="the matcher"):
        return None
    else:
        outcome = _refused(matcher, value)
    return None if outcome.matched else f"{outcome.description} ({outcome.mismatch})"


class AllOfMatcher(BaseMatcher):
    """Matches when all sub-matchers match (``&`` operator)."""

    def __init__(self, *matchers: Matcher[Any]):
        for one in matchers:
            _require_matcher_argument(one)
        self.matchers: tuple[Matcher[Any], ...] = matchers
        self.walks_its_value: bool = any(_has_own_evaluate(one) for one in matchers)
        """Whether anything under here has to be asked once, which is what `_has_own_evaluate` reads."""

    def matches(self, value: Any) -> bool:
        return self._holds(_ReadOnce(value))

    def _holds(self, read: _ReadOnce) -> bool:
        return all(_verdict_of(matcher, read) for matcher in self.matchers)

    def describe(self) -> str:
        return f"({' and '.join(matcher.describe() for matcher in self.matchers)})"

    def _decided(self, read: _ReadOnce) -> tuple[bool, str]:
        """The verdict and the reason from one pass, so the two cannot disagree.

        Deriving the verdict from whether there was a reason instead read a satisfied child as a failure
        and, on a matcher answering two calls differently, an unsatisfied one as a pass.
        """
        failed = [why for one in self.matchers if (why := _failure(one, read)) is not None]
        return not failed, ", ".join(failed)

    def evaluate(self, value: Any) -> MatchResult:
        return self._evaluated(_ReadOnce(value))

    def _evaluated(self, read: _ReadOnce) -> MatchResult:
        held, failure = self._decided(read)
        if held:
            return MatchResult(matched=True, description=self.describe())
        return MatchResult(matched=False, description=self.describe(), mismatch=self._line(read.shown(), failure))

    def _refusal(self, read: _ReadOnce) -> MatchResult:
        """The result for a value already refused, with the reason a second look gives, or the requirement."""
        return MatchResult(
            matched=False, description=self.describe(), mismatch=self._line(read.shown(), self._decided(read)[1])
        )

    def describe_mismatch(self, value: Any) -> str:
        return self._refusal(_ReadOnce(value)).mismatch

    def _line(self, value: Any, failure: str) -> str:
        return f"<{_capped(value)}> did not satisfy: {failure or self.describe()}"


class AnyOfMatcher(BaseMatcher):
    """Matches when at least one sub-matcher matches (``|`` operator)."""

    def __init__(self, *matchers: Matcher[Any]):
        for one in matchers:
            _require_matcher_argument(one)
        self.matchers: tuple[Matcher[Any], ...] = matchers
        self.walks_its_value: bool = any(_has_own_evaluate(one) for one in matchers)
        """Whether anything under here has to be asked once, which is what `_has_own_evaluate` reads."""

    def matches(self, value: Any) -> bool:
        return self._holds(_ReadOnce(value))

    def _holds(self, read: _ReadOnce) -> bool:
        return any(_verdict_of(matcher, read) for matcher in self.matchers)

    def describe(self) -> str:
        return f"({' or '.join(matcher.describe() for matcher in self.matchers)})"

    def _decided(self, read: _ReadOnce) -> tuple[bool, str]:
        """Held as soon as one alternative holds, and otherwise every alternative with its own reason."""
        reasons = []
        for one in self.matchers:
            why = _failure(one, read)
            if why is None:
                return True, ""
            reasons.append(why)
        return False, " or ".join(reasons)

    def evaluate(self, value: Any) -> MatchResult:
        return self._evaluated(_ReadOnce(value))

    def _evaluated(self, read: _ReadOnce) -> MatchResult:
        held, failure = self._decided(read)
        if held:
            return MatchResult(matched=True, description=self.describe())
        return MatchResult(matched=False, description=self.describe(), mismatch=self._line(read.shown(), failure))

    def _refusal(self, read: _ReadOnce) -> MatchResult:
        """The result for a value already refused, with the reason a second look gives, or the requirement."""
        return MatchResult(
            matched=False, description=self.describe(), mismatch=self._line(read.shown(), self._decided(read)[1])
        )

    def describe_mismatch(self, value: Any) -> str:
        return self._refusal(_ReadOnce(value)).mismatch

    def _line(self, value: Any, failure: str) -> str:
        return f"<{_capped(value)}> satisfied none of: {failure or self.describe()}"


class NotMatcher(BaseMatcher):
    """Matches when the wrapped matcher does not match (``~`` operator)."""

    def __init__(self, matcher: Matcher[Any]):
        self.matcher: Matcher[Any] = _require_matcher_argument(matcher)
        self.walks_its_value: bool = _has_own_evaluate(matcher)
        """Whether the wrapped matcher has to be asked once, which is what `_has_own_evaluate` reads."""

    def matches(self, value: Any) -> bool:
        return self._holds(_ReadOnce(value))

    def _holds(self, read: _ReadOnce) -> bool:
        return not _verdict_of(self.matcher, read)

    def describe(self) -> str:
        return f"not {self.matcher.describe()}"

    def _decided(self, read: _ReadOnce) -> tuple[bool, str]:
        """Held when the wrapped matcher refused.  What failed, otherwise, is that the wrapped one held."""
        held = _failure(self.matcher, read) is not None
        return held, "" if held else f"{self.describe()} (it matched)"

    def evaluate(self, value: Any) -> MatchResult:
        return self._evaluated(_ReadOnce(value))

    def _evaluated(self, read: _ReadOnce) -> MatchResult:
        if self._decided(read)[0]:
            return MatchResult(matched=True, description=self.describe())
        return self._refusal(read)

    def _refusal(self, read: _ReadOnce) -> MatchResult:
        """The result for a value already refused: the wrapped matcher held, which needs no second look."""
        return MatchResult(matched=False, description=self.describe(), mismatch=self._line(read.shown()))

    def describe_mismatch(self, value: Any) -> str:
        return self._line(value)

    def _line(self, value: Any) -> str:
        return f"<{_capped(value)}> unexpectedly matched {self.matcher.describe()}"


_COMPOSITES: Final = (AllOfMatcher, AnyOfMatcher, NotMatcher)
"""The matchers built from others: they are handed the reader of a value rather than the value, and pass it on."""


def _composed(matcher: AllOfMatcher | AnyOfMatcher | NotMatcher) -> bool:
    """Whether a composite answers with a composite's own `matches()` and `evaluate()`: one of them, or a subclass
    that overrides neither, which is handed the reader as they are.  One that overrides either is asked as it is,
    told by identity: a wrapper `functools.wraps` makes carries the composite's module and name."""
    kind = type(matcher)
    if kind in _COMPOSITES:
        return True
    composite = next(base for base in _COMPOSITES if isinstance(matcher, base))
    return kind.matches is composite.matches and kind.evaluate is composite.evaluate


class EqualToMatcher(_OfTheValueItself):
    """Equality, optionally requiring the same type.

    ``strict_types`` is the same relation ``is_equal_to(..., strict_types=True)`` applies, spelled for a
    structural spec: one matcher covering value and type, rather than an `IsTypeOfMatcher` combined with
    a second matcher on every field that needs both.
    """

    def __init__(self, expected: object, strict_types: bool = False, **options: object):
        if options:  # the plain `equal_to(value)` builds nothing: it is constructed inside loops
            reject_unknown_kwargs(options, _EQUAL_TO_OPTIONS, "equal_to")
        self.expected = expected
        self.strict_types = strict_types
        self.ignore: object = options.get("ignore")
        self.include: object = options.get("include")
        # `equal_to(value)` alone is what `matches_structure` and the loops use, so it is decided once here
        self.guarded: bool = not (strict_types or options) and _sequence_or_numpy(expected)
        self.plain: bool = not (strict_types or options or self.guarded)
        self.config: _CompareConfig | None = (
            _build_compare_config(
                options.get("tolerance"),
                options.get("comparators"),
                bool(options.get("ignore_null", False)),
                strict_types,
                options.get("rel"),
            )
            if options or strict_types
            else None
        )

    def _hands_the_value_on(self) -> bool:
        return type(self.expected) not in NON_MATCHER_TYPES or bool(self.config is not None and self.config.comparators)

    def matches(self, value: Any) -> bool:
        if self.plain:
            try:
                return bool(value == self.expected)  # the hot path stays a plain comparison
            except REFUSALS as refusal:
                return equal_past(value, self.expected, refusal)
        if self.guarded:
            return equals(value, self.expected)
        return self._configured_match(value)

    def _configured_match(self, value: Any) -> bool:
        """The comparison under options: a comparator owning the root, strict types, a key filter, then the walk."""
        if self.config is not None and _resolve_comparator(value, self.config, field=None) is not None:
            return not values_differ(value, self.expected, self.config, at_root=True)
        if self.strict_types and type(value) is not type(self.expected):
            return False
        if mapping_shaped(value, check_values=False) and mapping_shaped(self.expected, check_values=False):
            try:
                return not mapping_differs(
                    value, self.expected, ignore=self.ignore, include=self.include, config=self.config
                )
            except IncludeKeysMissingError:
                return False  # an include naming an absent key: a mistake in the spec, so nothing matches
        if self.strict_types and _keyed_types_differ(value, self.expected):
            # the flag walks to the leaves: a composite whose `==` is true says nothing about the types inside
            return False  # a set the walker does not decompose, and a mapping key it walks straight past
        if key_specs_given(self.ignore) or key_specs_given(self.include):
            try:
                return not filtered_differs(
                    value, self.expected, ignore=self.ignore, include=self.include, config=self.config
                )
            except IncludeKeysMissingError:
                return False
        return not values_differ(value, self.expected, self.config, at_root=True)

    def _settings(self) -> str:
        """The comparison settings in force, in the same words the assertion uses for them.

        Without this the matcher computed with a tolerance and then reported a plain "not equal", so a
        reader questioning why a field they thought was tolerated still failed had nothing to read.
        `_config_note` renders the same line for `is_equal_to`; `ignore`/`include` are named here too,
        because the assertion puts them in its own sentence and a matcher has no sentence to put them in.
        """
        selectors = []
        if self.ignore is not None:
            selectors.append(f"ignoring {self.ignore!r}")
        if self.include is not None:
            selectors.append(f"including {self.include!r}")
        note = _config_note(self.config).strip()
        parts = [*selectors, note.removeprefix("compared with ")] if note else selectors
        return f" ({', '.join(parts)})" if parts else ""

    def describe(self) -> str:
        if self.strict_types:
            return (
                f"a value equal to <{_capped_format(self.expected)}>"
                f" of type <{type(self.expected).__name__}>{self._settings()}"
            )
        return f"a value equal to <{_capped_format(self.expected)}>{self._settings()}"

    def describe_mismatch(self, value: Any) -> str:
        if self.strict_types and type(value) is not type(self.expected):
            return f"was <{_capped(value)}> of type <{type(value).__name__}>"
        return f"was <{_capped(value)}>"


class GreaterThanMatcher(_OfTheValueItself):
    def __init__(self, boundary: object):
        self.boundary = boundary

    def matches(self, value: Any) -> bool:
        try:
            return holds(value, self.boundary, "gt")
        except UnorderableError:
            return False  # an operand this cannot be ordered against is a non-match, not an error

    def describe(self) -> str:
        return f"a value greater than <{_capped_format(self.boundary)}>"


class GreaterThanOrEqualToMatcher(_OfTheValueItself):
    def __init__(self, boundary: object):
        self.boundary = boundary

    def matches(self, value: Any) -> bool:
        try:
            return holds(value, self.boundary, "ge")
        except UnorderableError:
            return False  # an operand this cannot be ordered against is a non-match, not an error

    def describe(self) -> str:
        return f"a value greater than or equal to <{_capped_format(self.boundary)}>"


class LessThanMatcher(_OfTheValueItself):
    def __init__(self, boundary: object):
        self.boundary = boundary

    def matches(self, value: Any) -> bool:
        try:
            return holds(value, self.boundary, "lt")
        except UnorderableError:
            return False  # an operand this cannot be ordered against is a non-match, not an error

    def describe(self) -> str:
        return f"a value less than <{_capped_format(self.boundary)}>"


class LessThanOrEqualToMatcher(_OfTheValueItself):
    def __init__(self, boundary: object):
        self.boundary = boundary

    def matches(self, value: Any) -> bool:
        try:
            return holds(value, self.boundary, "le")
        except UnorderableError:
            return False  # an operand this cannot be ordered against is a non-match, not an error

    def describe(self) -> str:
        return f"a value less than or equal to <{_capped_format(self.boundary)}>"


def _sequence_or_numpy(value: object) -> bool:
    """Whether *value* can meet a `numpy` scalar's element-wise ``==``: a list or a tuple, or a `numpy` scalar.

    Decided when the matcher is built, so every other value keeps the plain comparison as its hot path.  A list or a
    tuple counts whether or not `numpy` is loaded yet; a `numpy` scalar, of any subclass, exists only once it is.
    """
    return issubclass(type(value), (list, tuple)) or may_broadcast(value)


def _ordered_kind(value: object) -> str | None:
    """``"plain"`` or ``"duration"`` where asking a value's order at construction runs no code of anybody's.

    A builtin's order is plain, and so is a `numpy` number's, whose tolerance below zero was never refused and
    covered every distance.  A `numpy` duration orders only against another.
    """
    kind = id(type(value))
    if kind in _BUILT_IN_ORDERED:
        return "plain"
    numpy = sys.modules.get("numpy")
    if numpy is None or kind not in _numpy_ordered_types(numpy):
        return None
    return "duration" if type(value) is numpy.timedelta64 else "plain"


_BUILT_IN_ORDERED = frozenset(map(id, (int, float, Decimal, Fraction, datetime, date, time, timedelta)))
"""By id: a membership test of the classes themselves asks a metaclass's `__eq__`, which is anybody's code."""


@functools.cache
def _numpy_ordered_types(numpy: Any) -> frozenset[int]:
    """The ids of `numpy`'s own integer, floating and duration scalar types.

    Told by identity, which neither a subclass naming its module `numpy` nor a metaclass answering attribute
    reads can claim, and without hashing a class of anybody's.
    """
    codes = numpy.typecodes["AllInteger"] + numpy.typecodes["Float"] + "m"
    return frozenset(id(numpy.dtype(code).type) for code in codes)


def _swapped(low: object, high: object) -> bool:
    """Whether these two are the wrong way round, asked only where the answer costs nothing.

    Two values may each order plainly and still not order against each other, a `datetime` against a
    `date` among them, and a pair with no ordering is judged where it is used rather than here.
    """
    low_kind = _ordered_kind(low)
    if low_kind is None or low_kind != _ordered_kind(high):
        return False
    try:
        return holds(low, high, "gt")
    except UnorderableError:
        return False


class BetweenMatcher(_OfTheValueItself):
    def __init__(self, low: object, high: object):
        if _swapped(low, high):
            _assertpy_refusal = True
            raise ValueError("given low arg must be less than given high arg")
        self.low = low
        self.high = high

    def matches(self, value: Any) -> bool:
        try:
            return holds(value, self.low, "ge") and holds(value, self.high, "le")
        except UnorderableError:
            return False  # an operand this cannot be ordered against is a non-match, not an error

    def describe(self) -> str:
        return f"a value between <{_capped_format(self.low)}> and <{_capped_format(self.high)}>"


def _measured_under(operand: object, tolerance: object, duration: bool) -> bool:
    """Whether `is_close_to` measures *operand* under *tolerance*: a datetime under a duration, else a number.

    Any number but a complex one or a `bool`, as `is_close_to` reads it, and a `numpy` duration only under
    another, which *duration* says the tolerance is. Outside that domain an equal pair would count as close,
    since equality answers before any distance does.
    """
    if duration:
        return numpy_duration(operand)
    if isinstance(tolerance, timedelta):
        return isinstance(operand, datetime)
    return type(operand) in (int, float) or _is_real_number(operand)


class CloseToMatcher(_OfTheValueItself):
    def __init__(self, expected: object, tolerance: object = None, rel: object = None):
        if tolerance is None and rel is None:
            refuse(tolerance, "a number, or a rel given instead", subject=argument("tolerance"))
        if tolerance is not None:
            zero = timedelta(0) if isinstance(tolerance, timedelta) else zero_of(tolerance)
            if _swapped(zero, tolerance):
                _assertpy_refusal = True
                raise ValueError("given tolerance arg must not be negative")
        self._duration: bool = type(tolerance) not in (int, float) and numpy_duration(tolerance)
        if rel is not None:
            require_rel(rel)
            if isinstance(tolerance, timedelta) or self._duration:
                refuse(rel, "None beside a duration, which has no size to take a fraction of", subject=argument("rel"))
        self.expected = expected
        self.tolerance = tolerance
        self.rel = rel
        # a tolerance that is no ordered distance has nothing within it, not even the value itself
        self._measures = (
            (tolerance is None or _is_real_number(tolerance) or isinstance(tolerance, timedelta) or self._duration)
            and _non_finite(tolerance) != "nan"
            and _measured_under(expected, tolerance, self._duration)
        )
        self._plain = (
            self._measures and rel is None and type(expected) in (int, float) and type(tolerance) in (int, float)
        )

    def matches(self, value: Any) -> bool:
        if self._plain and type(value) in (int, float):
            within = plainly_within(value, self.expected, self.tolerance)
            if within is not None:
                return within
        if not self._measures or not _measured_under(value, self.tolerance, self._duration):
            return False
        try:
            return within_either(value, self.expected, self.tolerance, self.rel)
        except UnorderableError:
            return False

    def describe(self) -> str:
        relative = f"relative tolerance <{_capped_format(self.rel)}>"
        if self.tolerance is None:
            return f"a value within {relative} of <{_capped_format(self.expected)}>"
        absolute = f"<{_capped_format(self.tolerance)}>"
        within = absolute if self.rel is None else f"{absolute} or {relative}"
        return f"a value within {within} of <{_capped_format(self.expected)}>"


class IsNoneMatcher(_OfTheValueItself):
    def matches(self, value: Any) -> bool:
        return value is None

    def describe(self) -> str:
        return "None"


class IsNotNoneMatcher(_OfTheValueItself):
    def matches(self, value: Any) -> bool:
        return value is not None

    def describe(self) -> str:
        return "a non-None value"


_UNION_ORIGINS: Final = (Union, UnionType)
"""What `get_origin` answers for a union, which is one class on 3.14+ and two below it."""


def _require_class_info(
    expected: object,
    *,
    name: str,
    expectation: str = "a class",
    probe: object = None,
    check: Callable[[Any, Any], bool] = isinstance,
) -> None:
    """Refuse what *check* cannot take, member by member, since it stops at the first match.

    A union or a tuple holding `list[str]` is otherwise answered by whichever member comes first: taken
    when an earlier one matches, a `TypeError` when none does, and on 3.10 a union refused either way.
    *check* is `isinstance`, or `issubclass`, which refuses more: a runtime protocol with data members
    answers `isinstance` and not `issubclass`.

    Every member is asked `check(probe, member)`, left to right as *check* reads them, so each one meets
    only a value it would have met had the members before it not matched.  An assertion passes the value
    it holds.  A matcher has none yet and passes `None`.  Asking every member is the point, so a member
    after one that matched is asked too, and a member that is not a plain class is asked again by the
    check that follows.  Answering from these probes instead would change the answer: below 3.14
    `isinstance(x, Optional[int])` reads `issubclass(type(x), int)`, which a `Mock(spec=int)` fails and
    `int | None` passes.

    Unions and tuples are flattened to any depth, both union spellings included: below 3.14
    `typing.Union[A, B]` is not a `types.UnionType`, so `get_origin` reads it.  A tuple is read from its
    storage, as *check* reads it, never through an `__iter__` a subclass overrides.  A class whose
    metaclass is `type` itself is not asked, since nothing in it can override either hook.  The
    walk keeps its own stack so that every probe runs in this frame, which is the frame `raised_inside`
    reads.  A recursive flatten probing every member took `is_instance_of((int, str))` from 0.19 to
    0.72 us, and this walk takes it to 0.48.
    """
    pending: list[Any] = [expected]
    try:
        while pending:
            member = pending.pop()
            if type(member) is type:
                continue
            if isinstance(member, tuple):
                pending.extend(tuple.__getitem__(member, slice(None, None, -1)))
            elif isinstance(member, UnionType) or get_origin(member) in _UNION_ORIGINS:
                pending.extend(member.__args__[::-1])
            else:
                check(probe, member)
    except TypeError as exc:
        if raised_inside(exc):  # their operator raised: that is a bug in the value, not a non-match
            raise
        refuse(expected, expectation, subject=argument(name))


class IsInstanceOfMatcher(_OfTheValueItself):
    def __init__(self, expected_type: ClassInfo):
        # eagerly, like the regex matcher
        _require_class_info(expected_type, name="class")
        self.expected_type = expected_type

    def matches(self, value: Any) -> bool:
        return isinstance(value, self.expected_type)

    def describe(self) -> str:
        return f"an instance of <{_type_expression_name(self.expected_type)}>"

    def describe_mismatch(self, value: Any) -> str:
        return f"was <{_capped(value)}> of type <{type(value).__name__}>"


class IsTypeOfMatcher(_OfTheValueItself):
    """Exact type, mirroring the ``is_type_of`` assertion.

    `IsInstanceOfMatcher` accepts a subclass, which makes it unable to say "an ``int``, not a ``bool``"
    - the distinction a structural spec needs most, since ``bool`` subclasses ``int`` and JSON turns
    one into the other.
    """

    def __init__(self, expected_type: type):
        # `type(value) is <a union>` is never true, so accepting one makes a matcher that silently never matches
        if type(expected_type) is not type and not issubclass(type(expected_type), type):
            refuse(expected_type, "a type", subject=argument("type"))
        self.expected_type = expected_type

    def matches(self, value: Any) -> bool:
        return type(value) is self.expected_type

    def describe(self) -> str:
        return f"exactly type <{_type_expression_name(self.expected_type)}>"

    def describe_mismatch(self, value: Any) -> str:
        return f"was <{_capped(value)}> of type <{type(value).__name__}>"


class IsTruthyMatcher(_OfTheValueItself):
    def matches(self, value: Any) -> bool:
        return bool(value)

    def describe(self) -> str:
        return "a truthy value"


class IsFalsyMatcher(_OfTheValueItself):
    def matches(self, value: Any) -> bool:
        return not bool(value)

    def describe(self) -> str:
        return "a falsy value"


class HasLengthMatcher(_OfTheValueItself):
    def __init__(self, expected_length: SupportsIndex | Matcher[int]):
        # a matcher is asked about the number `len()` gives, so a bound or a range is one matcher
        self.of_length: Matcher[int] | None = expected_length if _is_matcher(expected_length) else None
        if self.of_length is None:
            self.expected_length: int = require_integer(expected_length, "length")
            if self.expected_length < 0:
                _assertpy_refusal = True
                raise ValueError("given arg must be a positive int")

    def matches(self, value: Any) -> bool:
        # the core answers `None` for no length, and a raising `__len__` travels out rather than being swallowed
        length = length_of(value)
        if self.of_length is None:
            return length == self.expected_length
        return length is not None and _verdict_of(self.of_length, _ReadOnce(length))

    def describe(self) -> str:
        if self.of_length is not None:
            return f"a value with a length that is {self.of_length.describe()}"
        return f"a value of length <{self.expected_length}>"

    def describe_mismatch(self, value: Any) -> str:
        length = length_of(value)
        if length is None:
            return f"was <{_capped_repr(value)}>, which has no length"
        return f"was <{_capped(value)}> with length <{length}>"


class IsEmptyMatcher(_OfTheValueItself):
    def matches(self, value: Any) -> bool:
        return length_of(value) == 0

    def describe(self) -> str:
        return "an empty value"


class IsNotEmptyMatcher(_OfTheValueItself):
    def matches(self, value: Any) -> bool:
        length = length_of(value)
        return length is not None and length > 0

    def describe(self) -> str:
        return "a non-empty value"


class IsPositiveMatcher(_OfTheValueItself):
    def matches(self, value: Any) -> bool:
        # through the ordering engine, which answers for a NaN of either kind rather than signalling
        try:
            return holds(value, 0, "gt")
        except UnorderableError:
            return False

    def describe(self) -> str:
        return "a positive value"


class IsNegativeMatcher(_OfTheValueItself):
    def matches(self, value: Any) -> bool:
        try:
            return holds(value, 0, "lt")
        except UnorderableError:
            return False

    def describe(self) -> str:
        return "a negative value"


class IsZeroMatcher(_OfTheValueItself):
    def matches(self, value: Any) -> bool:
        return bool(value == 0)

    def describe(self) -> str:
        return "zero"


class IsEvenMatcher(_OfTheValueItself):
    def matches(self, value: Any) -> bool:
        whole = value if type(value) is int else whole_number(value)
        return whole is not None and whole % 2 == 0

    def describe(self) -> str:
        return "an even integer"

    def describe_mismatch(self, value: Any) -> str:
        if whole_number(value) is None:
            return f"was <{_capped_repr(value)}> of type <{type(value).__name__}>, not an integer"
        return f"was <{_capped(value)}>, which is odd"


class IsOddMatcher(_OfTheValueItself):
    def matches(self, value: Any) -> bool:
        whole = value if type(value) is int else whole_number(value)
        return whole is not None and whole % 2 != 0

    def describe(self) -> str:
        return "an odd integer"

    def describe_mismatch(self, value: Any) -> str:
        if whole_number(value) is None:
            return f"was <{_capped_repr(value)}> of type <{type(value).__name__}>, not an integer"
        return f"was <{_capped(value)}>, which is even"


class IsDivisibleByMatcher(_OfTheValueItself):
    def __init__(self, divisor: SupportsIndex):
        self.divisor: int = require_integer(divisor, "divisor")
        if self.divisor == 0:
            _assertpy_refusal = True
            raise ValueError("given divisor arg must not be zero")

    def matches(self, value: Any) -> bool:
        whole = value if type(value) is int else whole_number(value)
        return whole is not None and whole % self.divisor == 0

    def describe(self) -> str:
        return f"an integer divisible by <{self.divisor}>"

    def describe_mismatch(self, value: Any) -> str:
        whole = value if type(value) is int else whole_number(value)
        if whole is None:
            return f"was <{_capped_repr(value)}> of type <{type(value).__name__}>, not an integer"
        return f"was <{_capped(value)}>, which has remainder <{whole % self.divisor}>"


class IsCallableMatcher(_OfTheValueItself):
    def matches(self, value: Any) -> bool:
        return callable(value)

    def describe(self) -> str:
        return "a callable"

    def describe_mismatch(self, value: Any) -> str:
        return f"was <{_capped_repr(value)}> of type <{type(value).__name__}>, which is not callable"


class _SearchedByMember:
    """Candidates searched as `member` searches them, where a `numpy` scalar may meet a list among them."""

    __slots__ = ("values",)

    def __init__(self, values: tuple[object, ...]):
        self.values = values

    def __contains__(self, item: object) -> bool:
        return member(item, self.values)


class IsInMatcher(_OfTheValueItself):
    def __init__(self, *values: object):
        self.values = values
        broadcasting = any(_sequence_or_numpy(candidate) for candidate in values)
        self._candidates: tuple[object, ...] | _SearchedByMember = _SearchedByMember(values) if broadcasting else values

    def _hands_the_value_on(self) -> bool:
        return any(type(candidate) not in NON_MATCHER_TYPES for candidate in self.values)

    def matches(self, value: Any) -> bool:
        try:
            return value in self._candidates
        except REFUSALS:
            return member(value, self.values)

    def describe(self) -> str:
        return f"a value in <{_capped_repr(self.values)}>"

    def describe_mismatch(self, value: Any) -> str:
        return f"was <{_capped_repr(value)}>, which is not in <{_capped_repr(self.values)}>"


class HasPropertyMatcher(_OfTheValueItself):
    def __init__(self, name: str, matcher: Matcher[Any] | None = None):
        self.name = name
        self.matcher: Matcher[Any] | None = None if matcher is None else _require_matcher_argument(matcher)

    def matches(self, value: Any) -> bool:
        try:
            held = getattr(value, self.name)
        except AttributeError:
            return False
        if self.matcher is not None:
            return bool(verdict(self.matcher.matches(held), subject="the matcher"))
        return True

    def describe(self) -> str:
        if self.matcher is not None:
            return f"an object with property <{self.name}> matching {self.matcher.describe()}"
        return f"an object with property <{self.name}>"

    def describe_mismatch(self, value: Any) -> str:
        # one read: asked through `hasattr` and then again, a property that counts its reads answered twice
        try:
            held = getattr(value, self.name)
        except AttributeError:
            return f"<{_capped_repr(value)}> has no property <{self.name}>"
        if self.matcher is not None:
            return f"property <{self.name}> <{_capped_repr(held)}> did not match {_stated_reason(self.matcher, held)}"
        return f"was <{_capped_repr(value)}>"


# `str` and `bytes` are never each other's operands, and accepting `str` alone made a matcher disagree with itself
def _textlike_noun(operand: object) -> str:
    """What to call the operand in a description, so a bytes match does not read as a string one."""
    return "bytes" if isinstance(operand, (bytes, bytearray)) else "a string"


class ContainsStringMatcher(_OfTheValueItself):
    def __init__(self, substring: str | bytes):
        if type(substring) is not str and not issubclass(type(substring), _TEXTS):
            refuse(substring, "a string or bytes", subject=argument("substring"))
        self.substring = substring

    def matches(self, value: Any) -> bool:
        return text_contains(value, self.substring)

    def describe(self) -> str:
        return f"{_textlike_noun(self.substring)} containing <{_capped_format(self.substring)}>"


def _refuse_empty(name: str) -> NoReturn:
    """Refuse an empty text or bytes as the assertion of the same name does: every text starts and ends with it."""
    message = f"given {name} arg must not be empty"
    _assertpy_refusal = True
    raise ValueError(message)


_TEXTS = (str, bytes, bytearray)


class MatchesRegexMatcher(_OfTheValueItself):
    def __init__(self, pattern: str | re.Pattern[str]):
        self.pattern = pattern
        # compiled eagerly so an invalid pattern raises at the call site, not inside `matches()` or a combinator
        self._compiled = require_pattern(pattern)

    def matches(self, value: Any) -> bool:
        if not isinstance(value, str):
            return False
        return self._compiled.search(value) is not None

    def describe(self) -> str:
        return f"a string matching pattern <{self.pattern}>"


class StartsWithMatcher(_OfTheValueItself):
    def __init__(self, prefix: str | bytes):
        # a list or a number built a matcher that never matched anything, and said nothing
        if type(prefix) is not str and not issubclass(type(prefix), _TEXTS):
            refuse(prefix, "a string or bytes", subject=argument("prefix"))
        if len(prefix) == 0:
            _refuse_empty("prefix")
        self.prefix = prefix

    def matches(self, value: Any) -> bool:
        return text_starts_with(value, self.prefix)

    def describe(self) -> str:
        return f"{_textlike_noun(self.prefix)} starting with <{_capped_format(self.prefix)}>"


class EndsWithMatcher(_OfTheValueItself):
    def __init__(self, suffix: str | bytes):
        if type(suffix) is not str and not issubclass(type(suffix), _TEXTS):
            refuse(suffix, "a string or bytes", subject=argument("suffix"))
        if len(suffix) == 0:
            _refuse_empty("suffix")
        self.suffix = suffix

    def matches(self, value: Any) -> bool:
        return text_ends_with(value, self.suffix)

    def describe(self) -> str:
        return f"{_textlike_noun(self.suffix)} ending with <{_capped_format(self.suffix)}>"


def _listed(items: Any) -> str:
    """Items as a reader sees them, with a matcher naming itself rather than showing its repr."""
    return ", ".join(item.describe() if _is_matcher(item) else _safe_repr(item) for item in items)


def _unsearchable(searched: object, refusal: MembershipRefusedError) -> str:
    """Why a membership question could not be asked at all, kept as a mismatch so `~` and `|` still work."""
    return f"was <{_capped(searched)}>, which cannot be asked about these items: {refusal}"


class ContainsMatcher(BaseMatcher):
    """Membership, spelled for a structural spec.

    `each_item` says every element matches and `is_in` says the value is one of these, but the plain
    relation the builder has had all along -- this collection contains that -- could not be written in a
    spec at all.  The decision is the same one `contains()` reaches, asked of `_engine._membership`.
    """

    def __init__(self, *items: object):
        if not items:
            _assertpy_refusal = True
            raise ValueError("one or more items must be given")
        self.items = items

    def matches(self, value: Any) -> bool:
        searched = searchable(value)
        if not is_searchable(searched):
            return False  # a value membership cannot be asked of simply does not contain anything
        try:
            return not missing_items(searched, self.items, _is_matcher, marked=True)
        except MembershipRefusedError:
            return False  # an item this value cannot even be searched for is not one it holds

    def describe(self) -> str:
        return f"a collection containing {_listed(self.items)}"

    def describe_mismatch(self, value: Any) -> str:
        return self.evaluate(value).mismatch

    def evaluate(self, value: Any) -> MatchResult:
        """The verdict and the reason from one look, which is the only way to be right about both.

        The default composition asks `matches()` and then `describe_mismatch()`, and each of them walks
        the value.  Over a one-shot iterator the second walk sees what the first left behind, so the
        message named items that were there and missed the ones that were not.
        """
        searched = searchable(value)
        if not is_searchable(searched):
            return MatchResult(
                matched=False,
                description=self.describe(),
                mismatch=f"was <{_capped_repr(value)}>, which cannot be searched",
            )
        try:
            absent = missing_items(searched, self.items, _is_matcher, marked=True)
        except MembershipRefusedError as refusal:
            return MatchResult(matched=False, description=self.describe(), mismatch=_unsearchable(searched, refusal))
        return MatchResult(
            matched=not absent,
            description=self.describe(),
            mismatch="" if not absent else f"was <{_capped(searched)}>, missing {_listed(absent)}",
        )


class ContainsOnlyMatcher(BaseMatcher):
    """ "Nothing but these", spelled for a structural spec.

    Reaches the same decision `contains_only()` reaches: what is present but unwanted, and what is
    wanted but absent.  Either half makes it a non-match.
    """

    def __init__(self, *items: object):
        if not items:
            _assertpy_refusal = True
            raise ValueError("one or more items must be given")
        self.items = items

    def matches(self, value: Any) -> bool:
        return self.evaluate(value).matched

    def describe(self) -> str:
        return f"a collection containing only {_listed(self.items)}"

    def describe_mismatch(self, value: Any) -> str:
        return self.evaluate(value).mismatch

    def evaluate(self, value: Any) -> MatchResult:
        """One walk: "only these" needs everything that is there, and two walks cannot both see it."""
        searched = searchable(value)
        if not is_walkable(searched):
            # membership is not enough: every element must be seen, and `__contains__` alone cannot be listed
            return MatchResult(
                matched=False,
                description=self.describe(),
                mismatch=f"was <{_capped_repr(value)}>, which cannot be listed",
            )
        try:
            extra, missing = only_faults(searched, self.items, marked=True)
        except MembershipRefusedError as refusal:
            return MatchResult(matched=False, description=self.describe(), mismatch=_unsearchable(searched, refusal))
        faults = []
        if extra:
            faults.append(f"also had {_listed(extra)}")
        if missing:
            faults.append(f"lacked {_listed(missing)}")
        return MatchResult(
            matched=not faults,
            description=self.describe(),
            mismatch="" if not faults else f"was <{_capped_format(searched)}>, which {' and '.join(faults)}",
        )


class IsSubsetOfMatcher(BaseMatcher):
    """Every element of the value is somewhere in the given collection."""

    def __init__(self, *superset: object):
        if not superset:
            _assertpy_refusal = True
            raise ValueError("one or more items must be given")
        given = superset[0] if len(superset) == 1 and is_searchable(superset[0]) else superset
        # drained here, not per call: a generator handed in as the superset was consumed by the first `matches()`
        self.superset = searchable(given)
        # the assertion's own supersets: one collection, or several args, each flattened the way it flattens them
        self.supersets: tuple[object, ...] = superset if len(superset) > 1 else (self.superset,)

    def matches(self, value: Any) -> bool:
        return self.evaluate(value).matched

    def describe(self) -> str:
        return f"a collection whose items all appear in <{_capped_format(self.superset)}>"

    def describe_mismatch(self, value: Any) -> str:
        return self.evaluate(value).mismatch

    def evaluate(self, value: Any) -> MatchResult:
        """One walk: the subject is listed, while the superset is only asked about membership."""
        searched = searchable(value)
        if not is_walkable(searched):
            return MatchResult(
                matched=False,
                description=self.describe(),
                mismatch=f"was <{_capped_repr(value)}>, which cannot be listed",
            )
        absent = subset_faults(searched, self.supersets)
        return MatchResult(
            matched=not absent,
            description=self.describe(),
            mismatch="" if not absent else f"was <{_capped_format(searched)}>, with {_listed(absent)} outside it",
        )


def _itself(item: Any) -> Any:
    """The key `match.is_sorted()` orders by when it was given none."""
    return item


class IsSortedMatcher(BaseMatcher):
    """The value is in order, by the same walk `is_sorted()` uses."""

    def __init__(self, key: Callable[[Any], Any] | None = None, reverse: bool = False):
        self.key = key or _itself
        self.reverse = reverse

    def matches(self, value: Any) -> bool:
        return self.evaluate(value).matched

    def describe(self) -> str:
        return "a collection sorted in reverse" if self.reverse else "a collection sorted in order"

    def describe_mismatch(self, value: Any) -> str:
        return self.evaluate(value).mismatch

    def evaluate(self, value: Any) -> MatchResult:
        """One walk, which also means the user's `key` is called once per element rather than twice."""
        if not is_walkable(value):
            return MatchResult(
                matched=False,
                description=self.describe(),
                mismatch=f"was <{_capped_repr(value)}>, which cannot be walked",
            )
        items = searchable(value)
        try:
            if self.key is _itself and plainly_sortable(items):
                broken = first_plainly_out_of_order(items, reverse=self.reverse)
            else:
                broken = first_out_of_order(items, key=self.key, reverse=self.reverse)
        except UnorderableError:
            return MatchResult(
                matched=False,
                description=self.describe(),
                mismatch=f"was <{_capped_format(items)}>, holding items that cannot be ordered against each other",
            )
        if broken is None:
            return MatchResult(matched=True, description=self.describe(), mismatch="")
        index, earlier, later = broken
        return MatchResult(
            matched=False,
            description=self.describe(),
            mismatch=f"was <{_capped_format(items)}>, out of order at index {index}:"
            f" <{_capped_format(earlier)}> then <{_capped_format(later)}>",
        )


class IgnoreMatcher(_OfTheValueItself):
    def matches(self, value: Any) -> bool:
        return True

    def describe(self) -> str:
        return "anything (ignored)"


class IsUuidMatcher(_OfTheValueItself):
    def matches(self, value: Any) -> bool:
        if not isinstance(value, str):
            return False
        try:
            _uuid_mod.UUID(value)
        except ValueError:
            return False
        return True

    def describe(self) -> str:
        return "a valid UUID string"


class IsNonEmptyStringMatcher(_OfTheValueItself):
    def matches(self, value: Any) -> bool:
        return isinstance(value, str) and len(value) > 0

    def describe(self) -> str:
        return "a non-empty string"


class IsNowMatcher(_OfTheValueItself):
    """Matches a ``datetime`` within a tolerance of the current time."""

    def __init__(self, delta: timedelta):
        if isinstance(delta, timedelta) and timedelta.__lt__(delta, timedelta(0)):
            _assertpy_refusal = True
            raise ValueError("given delta arg must not be negative")
        self._delta = delta

    def matches(self, value: Any) -> bool:
        if not isinstance(value, datetime):
            return False
        # as moments: on one zone object the two readings of a repeated hour subtract to nothing, an hour apart
        now = datetime.now(timezone.utc) if value.utcoffset() is not None else datetime.now()
        return abs(value - now) <= self._delta

    def describe(self) -> str:
        return f"a datetime within {self._delta} of now"


class IsBeforeMatcher(_OfTheValueItself):
    """Matches a ``datetime`` strictly before a reference ``datetime``."""

    def __init__(self, other: datetime):
        self._other = other

    def matches(self, value: Any) -> bool:
        try:
            return isinstance(value, datetime) and value < self._other
        except TypeError as exc:  # naive vs aware operands are not comparable -> no match
            if raised_inside(exc):  # their operator raised: that is a bug in the value, not a non-match
                raise
            return False

    def describe(self) -> str:
        return f"a datetime before {_capped_format(self._other)}"


class IsAfterMatcher(_OfTheValueItself):
    """Matches a ``datetime`` strictly after a reference ``datetime``."""

    def __init__(self, other: datetime):
        self._other = other

    def matches(self, value: Any) -> bool:
        try:
            return isinstance(value, datetime) and value > self._other
        except TypeError as exc:  # naive vs aware operands are not comparable -> no match
            if raised_inside(exc):  # their operator raised: that is a bug in the value, not a non-match
                raise
            return False

    def describe(self) -> str:
        return f"a datetime after {_capped_format(self._other)}"


class EachMatcher(BaseMatcher):
    """Matches when every item in an iterable satisfies the wrapped matcher."""

    def __init__(self, matcher: Matcher[Any]):
        self.matcher: Matcher[Any] = _require_matcher_argument(matcher)

    def matches(self, value: Any) -> bool:
        try:
            return all(verdict(self.matcher.matches(item), subject="the matcher") for item in value)
        except TypeError as exc:
            if raised_inside(exc):  # their operator raised: that is a bug in the value, not a non-match
                raise
            return False

    def describe(self) -> str:
        return f"each item matching {self.matcher.describe()}"

    def describe_mismatch(self, value: Any) -> str:
        return self.evaluate(value).mismatch

    def evaluate(self, value: Any) -> MatchResult:
        """One walk: deciding drained a one-shot value, and describing afterwards named its remainder.

        The walk stops at the first item that fails, so an endless value is answered rather than read.
        The reason is what the item's matcher says about the item that failed, asked without asking for
        its verdict again.  Asking every item for its reason cost 2.2x on a passing walk of ten thousand.
        """
        try:
            for index, item in enumerate(value):
                if not verdict(self.matcher.matches(item), subject="the matcher"):
                    return MatchResult(
                        matched=False,
                        description=self.describe(),
                        mismatch=(
                            f"item at index {index} <{_capped(item)}> did not match "
                            f"{_stated_reason(self.matcher, item)}"
                        ),
                    )
        except TypeError as exc:
            if raised_inside(exc):  # their operator raised: that is a bug in the value, not a non-match
                raise
            return MatchResult(
                matched=False, description=self.describe(), mismatch=f"was not iterable: <{_capped(value)}>"
            )
        return MatchResult(matched=True, description=self.describe(), mismatch=f"was <{_capped(value)}>")


class _MissingSentinel:
    """Placeholder recorded for a spec key absent from the value during structural matching."""

    def __repr__(self) -> str:
        return "<missing>"


_MISSING: Final = _MissingSentinel()


_A_STRUCTURE: Final = "a mapping matching structure"


def _describe_spec_value(value: object) -> str:
    """Describe a single structure-spec value (matcher, nested dict spec, or raw value)."""
    if _is_matcher(value):
        return value.describe()
    if isinstance(value, dict):
        parts = [f"{key}: {_describe_spec_value(sub_value)}" for key, sub_value in value.items()]
        return f"{{{', '.join(parts)}}}"
    return f"<{_capped(value)}>"


class _SpecMismatch(NamedTuple):
    """One structural mismatch produced by a single spec walk.

    ``expected_desc`` is the public "expected" half (as exposed by ``collect_mismatches``); ``detail``
    carries a matcher's ``describe_mismatch(actual)`` so fail-fast failure text keeps its per-value
    detail without a second traversal.
    """

    path: _Path
    actual: object
    expected_desc: str
    detail: str | None
    literal: object = _MISSING
    """The raw value the spec holds there, where the mismatch is one of `==` against it."""


class StructureMatcher(_OfTheValueItself):
    """Matches dicts (or pydantic-style models via ``model_dump()``) against a structure spec whose
    values are matchers, raw values, or nested dicts."""

    def __init__(self, spec: dict[Any, Any]):
        self._spec = spec

    @staticmethod
    def _as_mapping(value: Any) -> Any:
        """Normalize a pydantic-style model (``model_dump()``) or an attrs instance to its dict, so it
        can be matched structurally just like a plain dict; pass other values through."""
        if is_model_dump_object(value):
            return value.model_dump()
        if is_attrs_instance(value):
            return {field.name: getattr(value, field.name) for field in value.__attrs_attrs__}
        return value

    def matches(self, value: Any) -> bool:
        mapping = self._as_mapping(value)
        if not is_mapping_like(mapping):
            return False
        return not self._walk(mapping, self._spec, _ROOT, set())

    def describe(self) -> str:
        return f"{_A_STRUCTURE} {_describe_spec_value(self._spec)}"

    def describe_mismatch(self, value: Any) -> str:
        mapping = self._as_mapping(value)
        if not is_mapping_like(mapping):
            return f"was not a mapping: <{_capped_format(mapping)}>"
        mismatches = self._walk(mapping, self._spec, _ROOT, set())
        return self.render_mismatch(mismatches) if mismatches else f"was <{_capped_format(mapping)}>"

    def evaluate(self, value: Any) -> MatchResult:
        """One walk of the spec instead of two.

        `matches()` walks it and `describe_mismatch()` walks it again, which is the whole cost of this
        matcher on a payload of any size.  The rendering is shared with `describe_mismatch()` rather
        than repeated, so the two cannot answer differently.

        `matches_structure` does not go through here: it needs every mismatch for its diff, not only the
        first one in words, so it walks once via `walk_mismatches()` and renders from that.
        """
        failure = self._failure(value)
        return MatchResult(matched=True, description=self.describe()) if failure is None else failure

    def _failure(self, value: Any) -> MatchResult | None:
        """What `evaluate()` answers for a value that does not match, from the same walk, and `None` for one that does.

        A pass needs no words.  `each` asks this of every item and describes the spec only for the one that
        failed: on 10 000 passing records the description was 16 of 53 ms.
        """
        mapped = self._as_mapping(value)
        if not is_mapping_like(mapped):
            return MatchResult(
                matched=False, description=self.describe(), mismatch=f"was not a mapping: <{_capped_format(mapped)}>"
            )
        mismatches = self._walk(mapped, self._spec, _ROOT, set())
        if not mismatches:
            return None
        return MatchResult(matched=False, description=self.describe(), mismatch=self.render_mismatch(mismatches))

    @staticmethod
    def render_mismatch(mismatches: list[_SpecMismatch]) -> str:
        """The first mismatch in words, from a walk the caller already paid for.

        Requires a non-empty list.  "Nothing mismatched" is not a mismatch to render, and the two callers
        disagree about what to say then: one has the mapped value to report, the other the raw one.
        """
        first = mismatches[0]
        where = first.path.text
        if first.actual is _MISSING:
            return f"missing key <{where}>"
        if first.expected_desc == "<circular ref>":  # cycle sentinel emitted by _walk
            # the root is unreachable here, so the label only ever names a nested cycle
            return f"circular reference detected at <{where or 'root'}>"
        if first.detail is not None:
            return f"at <{where}>: expected {first.expected_desc}, but {first.detail}"
        return f"at <{where}>: expected {first.expected_desc}, but was <{_capped_format(first.actual)}>"

    def collect_mismatches(self, value: Any) -> list[tuple[_Path, object, str]]:
        """Collect every structural mismatch as ``(path, actual, expected_description)``.

        Unlike `describe_mismatch()`, this does not stop at the first failure and joins nested
        paths, so callers can build a path-level [`DiffResult`][assertpy.errors.DiffResult].
        """
        return [(mismatch.path, mismatch.actual, mismatch.expected_desc) for mismatch in self.walk_mismatches(value)]

    def walk_mismatches(self, value: Any) -> list[_SpecMismatch]:
        """Every mismatch, once, for a caller that needs both the entries and the message.

        `matches_structure` builds a diff entry per mismatch *and* names the first one in its message.
        Asking `collect_mismatches()` and then `describe_mismatch()` walked the spec twice, and the walk
        is the whole cost of this matcher on a payload of any size.
        """
        return self._walk(self._as_mapping(value), self._spec, _ROOT, set())

    def _walk(
        self, value: MappingLike, spec: dict[Any, Any], path: _Path, seen: set[tuple[int, int]]
    ) -> list[_SpecMismatch]:
        pair_id = (id(value), id(spec))
        if pair_id in seen:
            # `path` is empty only on the outermost call, where no cycle can be reported, so this label is a guard
            return [_SpecMismatch(path, "<circular ref>", "<circular ref>", None)]
        seen = seen | {pair_id}
        mismatches: list[_SpecMismatch] = []
        for key, expected in spec.items():
            # built where needed: a spec that matches reads no path, and building one per key was the whole added cost
            try:
                if key not in value:
                    mismatches.append(_SpecMismatch(path.key(key), _MISSING, _describe_spec_value(expected), None))
                    continue
                actual = value[key]
            except REFUSALS as refusal:
                found, actual = lookup(value, key, refusal)
                if not found:
                    mismatches.append(_SpecMismatch(path.key(key), _MISSING, _describe_spec_value(expected), None))
                    continue
            if isinstance(expected, StructureMatcher) and is_mapping_like(normalized := self._as_mapping(actual)):
                mismatches.extend(self._walk(normalized, expected._spec, path.key(key), seen))
            elif _is_matcher(expected):
                # a predicate that cannot evaluate means "no match", asked once so a one-shot leaf keeps its reason
                try:
                    if _has_own_evaluate(expected):
                        # a matcher that walks its value answers once, so its reason holds for a one-shot iterator
                        outcome = cast("BaseMatcher", expected).evaluate(actual)
                        if not outcome.matched:
                            mismatches.append(
                                _SpecMismatch(path.key(key), actual, outcome.description, outcome.mismatch)
                            )
                    elif not verdict(expected.matches(actual), subject="the matcher"):
                        # nothing is rendered until the leaf has failed, which is what keeps a passing spec cheap
                        mismatches.append(
                            _SpecMismatch(
                                path.key(key), actual, expected.describe(), expected.describe_mismatch(actual)
                            )
                        )
                except VerdictError:  # never a mismatch, always a mistake in the test
                    raise
                except (TypeError, ValueError):
                    mismatches.append(
                        _SpecMismatch(path.key(key), actual, expected.describe(), f"was <{_capped(actual)}>")
                    )
            elif isinstance(expected, dict):
                normalized = self._as_mapping(actual)
                if is_mapping_like(normalized):
                    mismatches.extend(self._walk(normalized, expected, path.key(key), seen))
                else:
                    mismatches.append(_SpecMismatch(path.key(key), actual, "a mapping", None))
            elif not _guarded_equal(actual, expected, method="matches_structure"):
                # told apart by class where the two print the same: an id held as text read "expected <7>, but was <7>"
                shown = _capped_format(actual)
                wanted, was = _told_apart(_capped_format(expected), shown, expected, actual)
                # two sides told apart by their classes have said the type already
                kind = type_beside_a_class(actual, expected) if was == shown else ""
                mismatches.append(_SpecMismatch(path.key(key), actual, f"<{wanted}>", f"was <{was}>{kind}", expected))
        return mismatches
