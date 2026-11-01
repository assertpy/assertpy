"""Ordering as one decision: can these two be ordered, and if so, how do they compare.

The comparison itself is an operator and needs no core.  What did need one is the rule *around* it,
because it was written twice and in two different shapes.  The builder listed types (`complex` has no
ordering, a `datetime` wants a `datetime`, a number wants a number) and then tried the operator; the
matcher tried the operator and answered False on `TypeError`.  Two spellings of one rule is exactly how
`bytes` drifted apart in the text matchers, and it is a matter of time rather than of luck.

`compare` gives both callers the same three answers: ordered one way, ordered the other, or not
orderable at all.  What each does with "not orderable" stays theirs, and stays different on purpose: a
builder refuses the call, because a wrong subject there is a mistake in the test, while a matcher
answers "no match", because it feeds `==` and the combinators where raising would be wrong.
"""

from __future__ import annotations

import collections
import collections.abc
import decimal
import fractions
import inspect
import itertools
import numbers
import operator
import sys
import types
from datetime import date, datetime, time, timedelta
from typing import TYPE_CHECKING, Any

from ._require import argument, pure_decimal_code, raised_inside, raised_on_purpose, refuse

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Sequence

__tracebackhide__ = raised_on_purpose

# ordering exists for real numbers and not for complex ones, whatever `numbers.Number` says
_UNORDERED = frozenset({complex})
# types whose ordering needs no rule at all: identical on both sides, total, and not kind-bound
_PLAIN = frozenset({int, float, str, bytes})
_DIRECT = {"lt": operator.lt, "le": operator.le, "gt": operator.gt, "ge": operator.ge}
_SEARCHED_BY_EQUALITY = frozenset({list, tuple, collections.deque, type({}.values())})


class UnorderableError(Exception):
    """The pair cannot be ordered, with the reason the caller needs to explain it.

    ``kind`` is one of ``"value"`` (this value has no ordering at all), ``"kind"`` (both are ordered,
    but not against each other's type) or ``"pair"`` (the operator itself refused them).
    """

    def __init__(self, kind: str, *, wanted: type | None = None) -> None:
        super().__init__(kind)
        self.kind = kind
        self.wanted = wanted


def nan_operand(value: Any) -> bool:
    """A `float`, `Decimal` or `numpy` float NaN, unordered against everything, the `Decimal` one by signalling.

    Asked by type rather than through `math.isnan`, which would call `__float__` on somebody else's
    number and raises on a signalling `Decimal` instead of answering.

    Through the base type's own operator and method rather than the value's, the rule `_is_infinite`
    already follows: this answer decides whether an `InvalidOperation` is a verdict or a bug in the
    value, so a subclass overriding `is_nan` could have its own signal absorbed, and one overriding
    `__ne__` could call itself unordered against everything.  A `numpy` float other than `float64` is no
    `float`, and is read through its own type's `as_integer_ratio` as the exact order reads it: missed, it
    let a `Decimal`'s signal out and passed `is_sorted` over a list a `float` NaN fails.  Subclasses
    included, and only off a class built by `type` itself, since a metaclass of anybody's answers reads.  An
    integer, built in or registered, is never one, and is not read at all.

    A class that holds no number this reads is kept once found, as `integral_kind` keeps its own, and one given
    another `as_integer_ratio` after it was asked is not followed.  Asked afresh, a text or a ``None`` cost 1.3 us,
    and a failure asks this of both sides of every row it reports.
    """
    if isinstance(value, float):
        return bool(float.__ne__(value, value))
    if isinstance(value, decimal.Decimal):
        return decimal.Decimal.is_nan(value)
    kind = type(value)
    if kind is int or type(kind) is not type or kind in _UNREAD_KINDS or kind in _INTEGRAL_KINDS or integral_kind(kind):
        return False
    ratio = _known_number_method(kind, "as_integer_ratio", types.MethodDescriptorType)
    if ratio is None:
        if len(_UNREAD_KINDS) < 256:
            _UNREAD_KINDS.add(kind)
        return False
    return _read_by(value, ratio) == "nan"


def integral_kind(kind: type) -> bool:
    """Whether a class built by `type` itself is a `numbers.Integral`, kept once found: a class never stops being one.

    Asked of a `numpy` integer at every NaN and infinity question, where the ABC check cost an `int64` tie 11%.  At
    most 256 are kept, so classes made on the fly cannot grow it without bound, and an ABC registry cleared by hand
    through its private API is not followed.
    """
    if type(kind) is not type:
        return False
    if kind in _INTEGRAL_KINDS:
        return True
    if issubclass(kind, numbers.Integral):
        if len(_INTEGRAL_KINDS) < 256:
            _INTEGRAL_KINDS.add(kind)
        return True
    return False


_INTEGRAL_KINDS: set[type] = set()
"""What `integral_kind` has found, only classes built by `type` itself, so hashed as `type` hashes."""

_UNREAD_KINDS: set[type] = set()
"""What `nan_operand` has found to hold no number it reads, kept and bounded as `_INTEGRAL_KINDS` is."""


def _kind_of(value: Any) -> type | None:
    """The date-and-time kind a value orders within, subclasses included, or ``None`` for anything else.

    By kind rather than by exact type: `pandas.Timestamp` and `freezegun`'s clock are `datetime`
    subclasses, and refusing them against a `datetime` boundary failed an assertion that holds.
    """
    for kind in (datetime, date, timedelta, time):  # `datetime` ahead of `date`, which it subclasses
        if isinstance(value, kind):
            return kind
    return None


def _equal(actual: Any, expected: Any) -> bool:
    """``==``, with a NaN on either side answering ``False`` rather than signalling."""
    if nan_operand(actual) or nan_operand(expected):
        return False
    return equals(actual, expected)


def equals(actual: Any, expected: Any) -> bool:
    """``actual == expected`` as a verdict, where Python's own ``==`` would raise instead of answering.

    A signalling `Decimal` NaN signals at ``==``, a `numpy` float overflows converting a Python int past its
    range and a `Decimal` refuses a `numpy` integer, in a list or a mapping as much as on its own.  A `numpy`
    scalar against a list or a tuple answers an array, element by element (`broadcasts`), and is unequal to it
    as a number is.  Asked as written first, so every other pair keeps the answer and the cost it always had.
    """
    try:
        equal = actual == expected
    except (decimal.InvalidOperation, OverflowError, TypeError, ValueError) as refusal:
        return equal_past(actual, expected, refusal)
    if type(equal) is not bool and type(actual) is not type(expected) and broadcasts(actual, expected, answer=equal):
        return False
    return bool(equal)


_SEQUENCES = (list, tuple)


def numpy_duration(value: object) -> bool:
    """Whether *value* is a `numpy.timedelta64`, a duration `numpy` registers as an integer all the same."""
    numpy = sys.modules.get("numpy")
    return numpy is not None and type(value) is numpy.timedelta64


_UNANSWERED: Any = object()


def broadcasts(actual: Any, expected: Any, *, ordering: bool = False, answer: object = _UNANSWERED) -> bool:
    """Whether `numpy` answered ``actual == expected``, or ``actual < expected`` with *ordering*, element by element.

    One is a `numpy` scalar and the other a list or a tuple, which the scalar turns into an array.  It answers an
    array, true where one element was equal, or raises on its truth where there were several, or on building the
    array of a ragged list.  A number is simply unequal to a list and unordered against it.  Only where the scalar's
    operator in that place is one `numpy` wrote, its own on the left and its reflected one on the right, and where
    the *answer* is at hand, only for the array itself: a subclass that wrote the operator keeps the answer it
    gives, and a sequence's own operator that declined the scalar leaves the answer to `numpy`.
    """
    numpy = sys.modules.get("numpy")
    if numpy is None or (answer is not _UNANSWERED and type(answer) is not numpy.ndarray):
        return False
    first, second = type(actual), type(expected)
    if issubclass(first, numpy.generic) and issubclass(second, _SEQUENCES):
        return _written_by_numpy(first, "__lt__" if ordering else "__eq__")
    if issubclass(second, numpy.generic) and issubclass(first, _SEQUENCES):
        return _written_by_numpy(second, "__gt__" if ordering else "__eq__")
    return False


def _written_by_numpy(kind: type, name: str) -> bool:
    """Whether *kind*'s operator *name* is one `numpy` wrote, read off the class without running it."""
    owner = getattr(inspect.getattr_static(kind, name, None), "__objclass__", None)
    return getattr(owner, "__module__", None) == "numpy"


def may_broadcast(value: Any) -> bool:
    """Whether *value* can be one side of a pair `broadcasts` names, while `numpy` is loaded."""
    numpy = sys.modules.get("numpy")
    return numpy is not None and issubclass(type(value), (numpy.generic, *_SEQUENCES))


def mixes_broadcasting(values: Any, others: Any = ()) -> bool:
    """Whether a `numpy` scalar and a list or a tuple meet across *values* and *others*, or within *values*.

    One linear pass over the types, for a walk that compares every pair and is quadratic already.
    """
    numpy = sys.modules.get("numpy")
    if numpy is None:
        return False
    try:
        kinds: Any = {*map(type, values), *map(type, others)}
    except TypeError:  # a metaclass may refuse to hash its classes
        kinds = [*map(type, values), *map(type, others)]
    return any(issubclass(kind, numpy.generic) for kind in kinds) and any(
        issubclass(kind, _SEQUENCES) for kind in kinds
    )


def member(item: Any, container: Any, verify: bool = True) -> bool:
    """``item in container`` as a verdict, each element asked as `equals` asks it once ``in`` raised.

    A set or a mapping cannot hold a signalling NaN, which refuses to hash, alone or inside a tuple, so it holds
    none: answered where the lookup ends in a built-in set's or dict's own (`_searches_by_hash`), which refuses
    nothing but an unhashable key, and the item would hash but for the NaNs in it.  A built-in list, tuple, deque
    or dict's values, or a set or mapping the item hashes for, whose comparison refused a pair, is searched
    element by element too.  Any other error raised inside the container's or an element's own code is handed
    on.  An iterator is searched on from where the raising ``in`` stopped, which is enough: every element before
    it compared unequal, or ``in`` would have answered, and the one that raised met a NaN or an int no float can
    equal.  An item that may broadcast (`may_broadcast`) is searched element by element in a container that
    walks by ``==``, before ``in`` could take the truth of an array; *verify* false is a caller that knows no such
    item comes.  A set or a mapping meets one only through a hash collision, whose ambiguous truth is answered
    by the same walk.
    """
    if verify and type(item) not in _PLAIN and may_broadcast(item) and _walks_by_equality(container):
        return any(element is item or equals(element, item) for element in container)
    try:
        return item in container
    except MEMBERSHIP_REFUSALS as refusal:
        found = member_past(item, container, refusal)
        if found is None:
            raise
        return found


MEMBERSHIP_REFUSALS = (decimal.InvalidOperation, OverflowError, ValueError, DeprecationWarning, TypeError)
"""What ``in`` raises that `member_past` may answer."""


def member_past(item: Any, container: Any, refusal: Exception) -> bool | None:
    """`member`'s verdict once ``item in container`` raised *refusal*, or ``None`` to hand the refusal on as raised.

    Answered from the refusal already caught, never by asking ``in`` again: an element whose ``==`` answers
    differently the second time would have turned the refusal into a verdict.
    """
    if isinstance(refusal, (decimal.InvalidOperation, OverflowError)):
        if raised_inside(refusal):
            return None
    elif isinstance(refusal, (ValueError, DeprecationWarning)):
        # a hash collision met a `numpy` scalar with a tuple, and `in` took the truth of their array
        if raised_inside(refusal) or not may_broadcast(item) or not _searched_again(container):
            return None
    else:
        # a dict's items view hashes the key of a pair alone, and asks about the value only once the key is there
        pair = type(container) is type({}.items()) and isinstance(item, tuple) and len(item) == 2
        key = item[0] if pair else item
        hashed = _searches_by_hash(container)
        if hashed and _unhashable_for_a_nan_alone(key):
            return False
        if raised_inside(refusal) or not (_walks_by_equality(container) or (hashed and _hashes(key))):
            return None
    return any(element is item or equals(element, item) for element in container)


def _walks_by_equality(container: Any) -> bool:
    """Whether ``in`` walks *container* asking ``==``: a built-in list, tuple, deque or dict's values.

    A subclass counts where it keeps both the search and the iteration of the one it derives from, read off the
    class without running either.
    """
    kind = type(container)
    if kind in _SEARCHED_BY_EQUALITY:
        return True
    return any(
        issubclass(kind, base)
        and inspect.getattr_static(kind, "__contains__") is inspect.getattr_static(base, "__contains__")
        and inspect.getattr_static(kind, "__iter__") is inspect.getattr_static(base, "__iter__")
        for base in (list, tuple, collections.deque)
    )


def _searched_again(container: Any) -> bool:
    """Whether *container* can be searched a second time: a built-in sequence, set or mapping, never an iterator."""
    return _walks_by_equality(container) or _searches_by_hash(container)


REFUSALS = (TypeError, decimal.InvalidOperation, OverflowError, ValueError)
"""What ``==`` raises for a pair it refuses to compare: a `Decimal` against a `numpy` integer, a signalling NaN, a
`numpy` float against a Python int past its range, and the truth of the array a `numpy` integer answers against a
tuple key its hash collided with."""


def held_key(keys: Any, key: Any) -> tuple[bool, Any]:
    """Whether *keys* holds *key*, as `member` asks it, and the very key it holds there.

    Where ``in`` answers, that is *key* itself.  Where it refused a comparison after an equal hash, as a `Decimal`
    refuses a `numpy` integer, the key held is the one `equals` finds, which a lookup by that very object reaches
    through identity and never compares again.  Only a set or a mapping whose lookup ends in a built-in one
    (`_searches_by_hash`) is searched that way; anybody else's refusal is handed on.
    """
    try:
        return key in keys, key
    except REFUSALS:
        if not _searches_by_hash(keys):
            raise
        if not member(key, keys):
            return False, key
    return True, next(held for held in keys if held is key or equals(held, key))


def lookup(mapping: Any, key: Any, refusal: BaseException | None = None) -> tuple[bool, Any]:
    """Whether *mapping* holds *key*, and ``mapping[key]`` where it does, the key found as `held_key` finds it.

    *refusal* is what the caller's own lookup raised, handed on where it came from code of the mapping's, the
    key's or a value's own rather than from the comparison of two keys.
    """
    if refusal is not None and raised_inside(refusal):
        raise refusal
    found, held = held_key(mapping, key)
    return found, mapping[held] if found else None


def _hashes(key: Any) -> bool:
    """Whether *key* hashes, so a lookup that refused it refused a comparison rather than the key."""
    try:
        hash(key)
    except TypeError:
        return False
    return True


def _unhashable_for_a_nan_alone(item: Any) -> bool:
    """Whether *item* is a `Decimal` NaN, or a tuple holding one that would hash if its NaNs did."""
    if nan_operand(item):
        return True
    if not isinstance(item, tuple):
        return False
    held = False
    for element in item:
        if _unhashable_for_a_nan_alone(element):
            held = True
            continue
        try:
            hash(element)
        except TypeError:
            return False
    return held


def _searches_by_hash(container: Any) -> bool:
    """Whether ``in`` over *container* ends in a built-in set's or dict's own lookup, all the way down.

    A built-in set or dict, or a view of one, directly.  A `UserDict` whose `data` is a built-in dict, and the
    keys view over such a mapping, by following the path, read without running a descriptor of anybody's.
    """
    searched = inspect.getattr_static(type(container), "__contains__", None)
    built_in = (set, frozenset, dict, type({}.keys()), type({}.items()))
    if any(searched is inspect.getattr_static(kind, "__contains__") for kind in built_in):
        return True
    if searched is collections.UserDict.__contains__:
        return type(inspect.getattr_static(container, "data", None)) is dict
    if searched is collections.abc.KeysView.__contains__:
        # the slot `MappingView` declares, read by its own descriptor, and only where no subclass has shadowed it
        slot = inspect.getattr_static(collections.abc.MappingView, "_mapping")
        return inspect.getattr_static(type(container), "_mapping") is slot and _searches_by_hash(
            slot.__get__(container)
        )
    return False


def equal_past(actual: Any, expected: Any, refusal: Exception) -> bool:
    """Whether a pair whose own ``==`` raised *refusal* is equal, or *refusal* again where nothing can answer.

    A NaN equals nothing, which answers a signal wherever one of the pair is a NaN, as the operands decide it for
    ordering.  Two lists, two tuples or two mappings compared by the built-in ``==`` are equal element by
    element, each asked as `equals` asks it.  Two numbers whose operator overflowed or refused the other are equal
    where their exact values are.  An error raised inside a comparison of the value's own is handed on first,
    whatever else the pair holds, and so is a refusal nothing here answers.  A `ValueError` is otherwise answered
    only for a pair `broadcasts` names, as unequal.
    """
    if raised_inside(refusal):
        raise refusal
    if isinstance(refusal, decimal.InvalidOperation) and (nan_operand(actual) or nan_operand(expected)):
        return False
    walked = _equal_by_element(actual, expected)
    if walked is not None:
        return walked
    if isinstance(refusal, ValueError):
        if broadcasts(actual, expected):
            return False
        raise refusal
    left, right = _exact_real(actual), _exact_real(expected)
    if not isinstance(refusal, decimal.InvalidOperation) and left is not None and right is not None:
        return not isinstance(left, str) and left == right
    # a scalar against a container broadcast by `numpy`: the NaN that signalled equals nothing it met
    if isinstance(refusal, decimal.InvalidOperation) and (_holds_nan(actual) or _holds_nan(expected)):
        return False
    raise refusal


def _holds_nan(value: Any, seen: frozenset[int] = frozenset()) -> bool:
    """Whether *value* is a `Decimal` NaN or a list, tuple or dict holding one at any depth."""
    if id(value) in seen:
        return False
    within = seen | {id(value)}
    if isinstance(value, dict):
        return any(_holds_nan(held, within) for held in value.values())
    if isinstance(value, (list, tuple)):
        return any(_holds_nan(held, within) for held in value)
    return nan_operand(value)


def _equal_by_element(actual: Any, expected: Any) -> bool | None:
    """Built-in ``==`` over two lists, tuples, sets or mappings, asked of each element, else ``None``.

    A set equals another of its size that holds each of its elements, and a mapping one of its size that holds
    each of its keys, found as `member` finds it, under an equal value.
    """
    for kind in (list, tuple):
        if isinstance(actual, kind) and isinstance(expected, kind):
            if type(actual).__eq__ is not kind.__eq__ or type(expected).__eq__ is not kind.__eq__:
                return None
            pairs = zip(actual, expected, strict=False)
            return len(actual) == len(expected) and all(left is right or equals(left, right) for left, right in pairs)
    if isinstance(actual, (set, frozenset)) and isinstance(expected, (set, frozenset)):
        if not {type(actual).__eq__, type(expected).__eq__} <= {set.__eq__, frozenset.__eq__}:
            return None
        return len(actual) == len(expected) and all(member(element, expected) for element in actual)
    if isinstance(actual, dict) and isinstance(expected, dict):
        return _mappings_equal(actual, expected)
    return None


def _mappings_equal(actual: dict, expected: dict) -> bool | None:
    """Two dicts, as ``==`` compares them: two `OrderedDict` values item by item in order, else key by key."""
    kinds = {type(actual).__eq__, type(expected).__eq__}
    if not kinds <= {dict.__eq__, collections.OrderedDict.__eq__}:
        return None
    if kinds == {collections.OrderedDict.__eq__}:
        return equals(list(actual.items()), list(expected.items()))
    return len(actual) == len(expected) and all(_held_alike(key, held, expected) for key, held in actual.items())


def _held_alike(key: Any, held: Any, mapping: Any) -> bool:
    """Whether *mapping* holds *key* under a value equal to *held*."""
    found, other = lookup(mapping, key)
    return found and (other is held or equals(held, other))


def _order_past(actual: Any, expected: Any, refusal: Exception) -> int | None:
    """How a pair orders once its own operator raised *refusal*: ``-1``, ``0`` or ``1``, ``None`` for a NaN.

    An `OverflowError` is a `numpy` float converting a Python int past its range, and a `TypeError` the operator
    refusing the pair, as a `Decimal` refuses a `numpy` integer.  Where both stand for exact values the pair
    orders by them, an infinity above every finite value and a NaN against nothing.  A `TypeError` between any
    other two leaves the pair with no order.  Raised inside a comparison of the value's own, either is a bug in
    the value and is handed on, unless `rational_overflow` names it, and so is an overflow from a value with no
    exact value to order by.  A `ValueError` otherwise leaves only a pair `broadcasts` names either way with no
    order, and is handed on.
    """
    if raised_inside(refusal) and not rational_overflow(refusal):
        raise refusal
    if _lexicographic(actual, expected):
        return _order_by_element(actual, expected)
    if isinstance(refusal, ValueError):
        if broadcasts(actual, expected, ordering=True) or broadcasts(expected, actual, ordering=True):
            raise UnorderableError("pair") from None
        raise refusal
    left, right = _exact_real(actual), _exact_real(expected)
    if left is None or right is None:
        if isinstance(refusal, TypeError):
            raise UnorderableError("pair") from None
        raise refusal
    if isinstance(left, str) or isinstance(right, str):
        return None
    return (left > right) - (left < right)


def _own_code(owner: type, name: str) -> types.CodeType | None:
    """The code of the function *owner* itself defines as *name*, or ``None`` where it defines no Python one."""
    return getattr(vars(owner).get(name), "__code__", None)


_FRACTION_ARITHMETIC = frozenset(
    filter(None, (_own_code(fractions.Fraction, "__sub__"), _own_code(fractions.Fraction, "__rsub__")))
)
_FRACTION_CONVERSION = frozenset(
    filter(None, (_own_code(numbers.Rational, "__float__"), _own_code(fractions.Fraction, "__float__")))
)
_FRACTION_ORDERING = frozenset(
    filter(None, (_own_code(fractions.Fraction, name) for name in ("__lt__", "__le__", "__gt__", "__ge__")))
)
_FRACTION_COMPARISON = _own_code(fractions.Fraction, "_richcmp")


def rational_overflow(error: BaseException) -> bool:
    """Whether *error* is `Fraction`'s own code overflowing, which the exact values of the pair remove.

    Two places in `Fraction` meet the other operand in Python code, so `raised_inside` read their overflow as a
    bug in the value: its arithmetic converting itself to ``float`` through `numbers.Rational.__float__`, and its
    ordering multiplying its denominator by a fixed-width `numpy` integer.  The call decides instead: the
    operator called is `Fraction`'s own, and the overflow was raised in the code that operator runs, for a
    `Fraction`.  Checked by code object at both ends, since a module's name or namespace can be claimed by a
    function of anybody's, the inner code alone can be reached from a value's own method, and both can be
    borrowed by a class of anybody's, which is why the value has to be a `Fraction` as well, and an exact one,
    since a subclass can hand either code fields of its own.  The code objects are read once, and an
    interpreter whose `Fraction` runs either in C names nothing.
    """
    called = error.__traceback__.tb_next if error.__traceback__ is not None else None
    if not isinstance(error, OverflowError) or called is None:
        return False
    raised = called
    while raised.tb_next is not None:
        raised = raised.tb_next
    if type(raised.tb_frame.f_locals.get("self")) is not fractions.Fraction:
        return False
    if called.tb_frame.f_code in _FRACTION_ARITHMETIC:
        return raised.tb_frame.f_code in _FRACTION_CONVERSION
    return called.tb_frame.f_code in _FRACTION_ORDERING and raised.tb_frame.f_code is _FRACTION_COMPARISON


def _lexicographic(actual: Any, expected: Any) -> bool:
    """Whether the pair is two lists or two tuples ordered by the built-in ``<``, element by element."""
    return any(
        isinstance(actual, kind)
        and isinstance(expected, kind)
        and type(actual).__lt__ is kind.__lt__
        and type(expected).__lt__ is kind.__lt__
        for kind in (list, tuple)
    )


def _order_by_element(actual: Any, expected: Any) -> int | None:
    """Two sequences in the built-in order: the first pair `equals` calls unequal decides, else the length.

    That pair ordered by `compare`, and ``None`` where it orders neither way, as a NaN does.
    """
    for left, right in zip(actual, expected, strict=False):
        if left is right or equals(left, right):
            continue
        return compare(left, right) or None
    return (len(actual) > len(expected)) - (len(actual) < len(expected))


def _exact_real(value: Any) -> tuple[int, fractions.Fraction] | str | None:
    """*value* as ``(rank, exact)`` for ordering past an overflow, ``"nan"``, or ``None`` with no exact value.

    The rank puts an infinity above or below every finite value, whose exact value is compared otherwise.  An
    integer is read by `int`'s own `__index__` or a `numpy` integer's, never by a conversion of the value's own,
    which a registered `numbers.Integral` can make answer anything.  A `Fraction` is its own exact value, and a
    subclass of one is read as any other number.  Any other number is read through
    `as_integer_ratio`, which never rounds and refuses an infinity and a NaN by the error it raises, rather than
    through a conversion to ``float``.  Only as `float`, `Decimal` or a `numpy` float wrote it in C,
    whose errors mean exactly that, and called as the type holds it, as is its ``>`` for an infinity's sign:
    any other, on the class or reached through the instance, can raise either error for a finite value, and
    would order it as an infinity or leave it unordered.
    """
    if issubclass(type(value), int) or issubclass(type(value), numbers.Integral):
        whole = exact_int(value)
        return None if whole is None else (0, fractions.Fraction(whole))
    if type(value) is fractions.Fraction:
        return 0, value
    ratio = _known_number_method(type(value), "as_integer_ratio", types.MethodDescriptorType)
    return None if ratio is None else _read_by(value, ratio)


def _read_by(value: Any, ratio: Any) -> tuple[int, fractions.Fraction] | str | None:
    """What `_exact_real` answers for *value* through *ratio*, the `as_integer_ratio` its class holds."""
    try:
        numerator, denominator = ratio(value)
    except OverflowError:
        greater = _known_number_method(type(value), "__gt__", types.WrapperDescriptorType)
        if greater is None:
            return None
        return (1 if greater(value, 0) else -1), fractions.Fraction(0)
    except ValueError:
        return "nan"
    return 0, fractions.Fraction(int(numerator), int(denominator))


def exact_int(value: Any) -> int | None:
    """*value* as the int it holds, read by `int`'s own `__index__` or a `numpy` integer's, else ``None``.

    Never by a conversion of the value's own, which a registered `numbers.Integral` can make answer anything.
    """
    kind = type(value)
    if issubclass(kind, int):
        return int.__index__(value)
    if issubclass(kind, numbers.Integral):
        index = _known_number_method(kind, "__index__", types.WrapperDescriptorType)
        return None if index is None else index(value)
    return None


def unwrapped(value: Any) -> Any:
    """*value*, or the `int` a `numpy` integer holds: fixed in width, its arithmetic wraps where an `int`'s grows.

    ``numpy.uint8(3) - 250`` is ``9`` and a warning, so a distance or a product taken through one is no measure.
    Only a scalar class `numpy` itself made is read.  A subclass of one may have written operators of its own, so
    it is asked through them and keeps its width, and a `numpy` duration, an integer to the ABC, has no
    `__index__`.  The class is asked once while the records have room: asked at every call, a passing
    `is_close_to` on two `int64` cost 90% more.
    """
    kind = type(value)
    if kind is int or kind is float or type(kind) is not type or kind in _NOT_FIXED:
        return value
    index = _WHOLE_OF.get(kind)
    if index is None:
        fixed = not issubclass(kind, int) and _made_ahead(kind) and integral_kind(kind)
        index = _known_number_method(kind, "__index__", types.WrapperDescriptorType) if fixed else None
        if index is None:
            if len(_NOT_FIXED) < 256:
                _NOT_FIXED.add(kind)
            return value
        if len(_WHOLE_OF) < 256:
            _WHOLE_OF[kind] = index
    return index(value)


def python_number(value: Any) -> Any:
    """*value*, or the Python number a `numpy` number holds: the `int` of an integer, else the `float` of a float.

    A float is read only where the `float` is the same number, which a long double past a double's precision is not.
    """
    whole = unwrapped(value)
    return whole if type(whole) is int else _widened(whole)


def _widened(value: Any) -> Any:
    """*value*, or the `float` a `numpy` float holds where that loses nothing, as a long double past a double would."""
    kind = type(value)
    if kind is float or type(kind) is not type:
        return value
    convert = _float_of(kind)
    if convert is None:
        return value
    wide = convert(value)
    return wide if wide == value else value


def numpy_float(value: Any) -> bool:
    """Whether *value* is a float scalar of a class `numpy` itself made, whatever it holds, a NaN too."""
    kind = type(value)
    return type(kind) is type and _float_of(kind) is not None


def _float_of(kind: type) -> Any:
    """The `__float__` of a float scalar class `numpy` itself made, else ``None``, kept while the record has room."""
    convert = _FLOAT_OF.get(kind, _UNANSWERED)
    if convert is _UNANSWERED:
        real = _made_ahead(kind) and issubclass(kind, numbers.Real) and not integral_kind(kind)
        convert = _known_number_method(kind, "__float__", types.WrapperDescriptorType) if real else None
        if len(_FLOAT_OF) < 256:
            _FLOAT_OF[kind] = convert
    return convert


def python_numbers(first: Any, second: Any) -> tuple[Any, Any]:
    """The pair, each `numpy` number read as the Python number it holds where one of the two is a `numpy` integer.

    Beside an `int`, `numpy` rounds a Python integer to the float it meets: ``16777217 > numpy.float32(16777216)``
    is false to it, where the `int64` the integer was read from ordered exactly.  So the float is read as well,
    where a `float` holds the same number, and the pair is measured as Python measures an `int` against a
    `float`.  With no `numpy` integer in it the pair keeps the arithmetic it had.  Taken apart for a pair: over
    any number of operands an `int64` against an `int` paid 55% for its ordering.
    """
    one, other = unwrapped(first), unwrapped(second)
    if one is first and other is second:
        return first, second
    return (one if type(one) is int else _widened(one)), (other if type(other) is int else _widened(other))


def _made_ahead(kind: type) -> bool:
    """Whether *kind* is no class made at run time, which bit 9 of its flags marks and a subclass in Python is."""
    return not _flags(kind) & 512


_WHOLE_OF: dict[type, Any] = {}
"""The `__index__` of each `numpy` integer class `unwrapped` has met, bounded as its neighbours are."""
_NOT_FIXED: set[type] = {int, float, decimal.Decimal, fractions.Fraction}
"""The classes `unwrapped` found to be no `numpy` integer.  A set: asked of a dict, two close `float64` paid 9%."""
_FLOAT_OF: dict[type, Any] = {int: None, float: None, decimal.Decimal: None, fractions.Fraction: None}
"""What `_float_of` found for a class, a `numpy` float's `__float__` or ``None``, bounded likewise."""
_flags = type.__dict__["__flags__"].__get__


def whole_number(value: Any) -> int | None:
    """*value* as the int it stands for where it is an integer, which a bool is not, else ``None``."""
    if type(value) is int:
        return value
    return None if isinstance(value, bool) else exact_int(value)


def require_integer(value: object, name: str | None = None) -> int:
    """*value* as the int it stands for (`whole_number`), or refused as no integer: as the argument *name*, else val.

    A caller on an assertion's own path asks ``value if type(value) is int else require_integer(value, name)``:
    asked through the call with its subject built up front, a plain `int` cost `is_length` 37%.
    """
    whole = whole_number(value)
    if whole is None:
        refuse(value, "an integer", subject="val" if name is None else argument(name))
    return whole


def _known_number_method(owner: type, name: str, kind: type) -> Any | None:
    """*owner*'s *name* as the type holds it, if `float`, `Decimal` or a `numpy` number wrote it in C, else ``None``.

    Or as `decimal` wrote it in Python, where CPython was built without its C accelerator (`pure_decimal_code`).
    """
    method = inspect.getattr_static(owner, name, None)
    if isinstance(method, types.FunctionType) and method.__code__ in pure_decimal_code():
        stock = inspect.getattr_static(decimal.Decimal, name, None)
        return method if method is stock and issubclass(owner, decimal.Decimal) else None
    maker = getattr(method, "__objclass__", None)
    known = maker in (float, decimal.Decimal) or getattr(maker, "__module__", None) == "numpy"
    # borrowed from another number type, the method refuses the instance with a `TypeError` of its own
    owned = isinstance(maker, type) and issubclass(owner, maker)
    return method if isinstance(method, kind) and known and owned else None


def compare(actual: Any, expected: Any) -> int:
    """``-1``/``0``/``1`` for *actual* against *expected*, or `UnorderableError` when they cannot be ordered.

    A `TypeError` raised *inside* somebody's own `__lt__` travels out untouched: that is a bug in the
    value, not an unorderable pair, and answering it either way would send the reader to the wrong file.
    """
    actual_type = type(actual)
    # the ordinary case first: in a per-element loop, so the frozenset lookup and two `isinstance` were paid each time.
    # An int against a float orders exactly and never signals, and the walk below spent two ABC checks on it
    if (actual_type is type(expected) and actual_type in _PLAIN) or (
        (actual_type is int or actual_type is float) and (type(expected) is int or type(expected) is float)
    ):
        return (actual > expected) - (actual < expected)
    if actual_type in _UNORDERED:
        raise UnorderableError("value")
    actual_kind: Any = _kind_of(actual)
    # a subclass that wrote its own `<` is asked instead: the rule is about the stock one being wrong across kinds
    if actual_kind is not None and type(actual).__lt__ is actual_kind.__lt__ and _kind_of(expected) is not actual_kind:
        raise UnorderableError("kind", wanted=actual_kind)
    if (
        actual_kind is None
        and isinstance(actual, numbers.Number)
        and (not isinstance(expected, numbers.Number) or type(expected) in _UNORDERED)
    ):
        raise UnorderableError("kind", wanted=numbers.Number)
    # deliberately dynamic: what may be ordered is decided above, and a checker reading the union sees no `<`
    left: Any = actual
    right: Any = expected
    expected_type = type(expected)
    # asked of the class kept, since a call for every pair cost a `Decimal` against an `int` 12%
    if actual_type is not expected_type and (
        (type(actual_type) is type and actual_type not in _NOT_FIXED)
        or (type(expected_type) is type and expected_type not in _NOT_FIXED)
    ):
        left, right = python_numbers(actual, expected)
    try:
        less = left < right
        mixed = actual_type is not type(expected)
        # a pair of one type is never a scalar against a list: asked for it anyway, an `int64` tie cost 19% more
        if mixed and type(less) is not bool and broadcasts(left, right, ordering=True, answer=less):
            raise UnorderableError("pair")
        if less:
            return -1
        greater = right < left
        if mixed and type(greater) is not bool and broadcasts(right, left, ordering=True, answer=greater):
            raise UnorderableError("pair")
        if greater:
            return 1
    except (TypeError, OverflowError, ValueError) as refusal:
        order = _order_past(actual, expected, refusal)
        return 0 if order is None else order
    except decimal.InvalidOperation as signal:
        return _order_past_signal(actual, expected, signal)
    return 0  # neither less nor greater, which is what a float NaN answers and `holds` keeps from reading equal


def _order_past_signal(actual: Any, expected: Any, signal: decimal.InvalidOperation) -> int:
    """How a pair orders once a `Decimal` NaN signalled at ``<``: a NaN operand neither way, two sequences by element.

    Asked after the comparison rather than before: checked first, `'a'` against a NaN read as a verdict where the
    same pair without one is refused.  The operands decide and not the traceback: measured, a signal comes from
    one frame under the C accelerator and from four under `_pydecimal`, so `raised_inside` answered the
    interpreter build.  A `numpy` scalar against a sequence holding a NaN is no order, as a number against a list.
    Any other signal is handed on.
    """
    if nan_operand(actual) or nan_operand(expected):
        return 0
    if broadcasts(actual, expected, ordering=True) or broadcasts(expected, actual, ordering=True):
        raise UnorderableError("pair") from None
    if not _lexicographic(actual, expected):
        raise signal
    order = _order_by_element(actual, expected)
    return 0 if order is None else order


def holds(actual: Any, expected: Any, relation: str) -> bool:
    """Whether *relation* (``lt``/``le``/``gt``/``ge``) holds between the two.

    `NaN` is unordered against everything including itself, and `compare` answers ``0`` for it because
    neither side is less than the other.  That would make `le`/`ge` true, which is the one place where
    "not less, not greater" does not mean "equal", so equality is asked separately.
    """
    actual_type = type(actual)
    if (actual_type is type(expected) and actual_type in _PLAIN) or (
        (actual_type is int or actual_type is float) and (type(expected) is int or type(expected) is float)
    ):
        # the shortcut `compare` takes, one call earlier: building the answer through a dict of four keys cost most
        return _DIRECT[relation](actual, expected)
    order = compare(actual, expected)
    if order == 0 and relation in ("le", "ge") and not _equal(actual, expected):
        return False
    return {"lt": order < 0, "le": order <= 0, "gt": order > 0, "ge": order >= 0}[relation]


def first_out_of_order(
    items: Iterable[Any], *, key: Callable[[Any], Any], reverse: bool = False
) -> tuple[int, Any, Any] | None:
    """The first adjacent pair that breaks the order, as ``(index, earlier, later)``, or ``None``.

    Returned rather than reported, so both spellings get what they need from one walk: the assertion
    names the pair and where it sits, and a matcher only looks at whether there was one.
    """
    previous: Any = None
    previous_key: Any = None
    for index, current in enumerate(items):
        current_key = key(current)
        # through `compare`, not `<`: a raise here reads to the origin check as a plain type mismatch.
        # The key is carried rather than recomputed, which doubled the calls to the caller's `key`
        if index > 0 and _out_of_order(current_key, previous_key, reverse=reverse):
            return index - 1, previous, current
        previous = current
        previous_key = current_key
    return None


def plainly_sortable(items: object) -> bool:
    """Whether *items* is an exact list or tuple of one exact `int`, `str` or `bytes` type: `<` orders it totally, in C.

    Such a sequence holds no NaN and runs no code of anybody's, so `first_plainly_out_of_order` compares its pairs
    in one C pass instead of pair by pair through `compare`, which took 106 us over 1000 ints.  Under five items
    the pass costs more to set up than the walk: 344 against 186 ns at two.
    """
    if (type(items) is not list and type(items) is not tuple) or len(items) < 5:
        return False
    kind = type(items[0])
    # by identity, stopping at the first other type: hashing a type asks its metaclass, which may refuse
    if kind is not int and kind is not str and kind is not bytes:
        return False
    return all(map(operator.is_, map(type, items), itertools.repeat(kind)))


def first_plainly_out_of_order(items: Sequence[Any], *, reverse: bool) -> tuple[int, Any, Any] | None:
    """`first_out_of_order` over the items themselves, for a sequence `plainly_sortable` accepted."""
    breaks = operator.lt if reverse else operator.gt
    pairs = map(breaks, items, itertools.islice(items, 1, None))
    index = next(itertools.compress(itertools.count(), pairs), None)
    return None if index is None else (index, items[index], items[index + 1])


def _out_of_order(later: Any, earlier: Any, *, reverse: bool) -> bool:
    """Whether *later* breaks the order after *earlier*, a pair holding a NaN vouching for no order at all.

    The NaN is asked only where the pair did not order, a tie or no order, since a NaN orders against
    nothing: asked of every key, a `numpy` float's NaN check cost a sort of ints 18%.
    """
    try:
        order = compare(later, earlier)
    except UnorderableError:
        if nan_operand(later) or nan_operand(earlier):
            return True
        raise
    if order == 0:
        # a tie of two exact ints or strings holds no NaN: asked anyway, a sort of equal ints cost 19%
        never_nan = (int, str, bytes)
        if type(later) in never_nan and type(earlier) in never_nan:
            return False
        return nan_operand(later) or nan_operand(earlier)
    return order > 0 if reverse else order < 0
