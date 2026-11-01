"""Per-call configuration for tolerant / custom-comparator equality, shared by the equality and diff code.

``is_equal_to`` builds a `_CompareConfig` from its ``tolerance``/``comparators`` kwargs and threads it
through both the boolean comparison (`HelpersMixin._dict_not_equal()`) and the diff/message rendering
(`assertpy._engine._diff._sub_diff_entries()`, `HelpersMixin._dict_err()`).  `_node_decision()` is the single
switch both sides consult, so a tolerated or comparator-equal leaf is reported in neither.  With ``config is
None`` every helper reproduces plain ``actual == expected`` exactly.

Following the package convention, the impl helpers take unannotated args (the typed public surface lives in
`assertpy._engine._typing`); they operate on arbitrary user values whose operators ``numbers.Number`` cannot
express to the type checker.
"""

from __future__ import annotations

import dataclasses
import datetime
import decimal
import fractions
import inspect
import math
import numbers
import pathlib
import re
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from ._introspection import (
    as_held,
    definition_of,
    eq_keyed,
    is_attrs_instance,
    is_mapping_like,
    is_model_dump_object,
    kind_of,
    model_field_values,
)
from ._ordering import (
    _NOT_FIXED,
    _SEQUENCES,
    REFUSALS,
    UnorderableError,
    _exact_real,
    broadcasts,
    equal_past,
    held_key,
    holds,
    integral_kind,
    numpy_duration,
    numpy_float,
    python_number,
    python_numbers,
    rational_overflow,
    unwrapped,
)
from ._require import raised_inside, verdict

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable


_EQ_ATOMIC = frozenset(
    {
        int,
        float,
        bool,
        complex,
        str,
        bytes,
        bytearray,
        type(None),
        datetime.datetime,
        datetime.date,
        datetime.time,
        datetime.timedelta,
        decimal.Decimal,
        uuid.UUID,
        pathlib.PurePosixPath,
        pathlib.PureWindowsPath,
        pathlib.PosixPath,
        pathlib.WindowsPath,
    }
)
"""Types whose ``==`` is a plain bool and which have nothing inside to walk into.

The stdlib scalars past the builtins are here for cost, not for correctness.  ``strict_types`` walks
past any value it does not know to be atomic, because a container's own ``==`` says nothing about the
types inside it - and a ``datetime`` is not a container, so that walk runs the whole introspection
ladder to come back with nothing.  Over 200 records of timestamps, decimals and UUIDs that was 3.7 ms
against 0.5 ms with them listed.

Listing one changes no verdict: a type difference is decided by `_types_differ()` before atomicity is
ever consulted, so ``date`` against ``datetime`` still fails.  Exact types, not ``isinstance``, so a
subclass with its own structure is still walked.
"""


@dataclass(frozen=True, slots=True, kw_only=True)
class _CompareConfig:
    """Tolerance and custom comparators for a single ``is_equal_to`` call.

    ``tolerance`` is an absolute tolerance applied to real-number leaves; ``comparators`` maps a ``type`` or
    an immediate field name to a ``(actual, expected) -> bool`` predicate that decides every leaf it matches;
    ``ignore_null`` skips a named field whenever the *expected* side leaves it ``None``;
    ``strict_types`` additionally requires both sides of every node a comparator does not decide to be the
    same type, which plain ``==`` does not (``True == 1``, ``Decimal("1") == 1``, and so on all the way down
    a payload).
    """

    tolerance: float | None = None
    rel: float | None = None
    """A tolerance relative to the expected number, held beside the absolute one: either is enough."""
    # `dict` and not `Mapping`: the runtime refuses anything else, so a checker-approved `MappingProxyType` would fail
    comparators: dict[Any, Callable[[Any, Any], Any]] | None = None
    ignore_null: bool = False
    strict_types: bool = False
    # read once for the whole comparison: a `numpy` duration measures only another
    duration: bool = False


def _build_compare_config(
    tolerance, comparators, ignore_null=False, strict_types=False, rel=None
) -> _CompareConfig | None:
    """Validate the ``is_equal_to`` comparison kwargs and build a config.

    Returns ``None`` when none are set.  ``tolerance`` and ``rel`` must be non-negative real numbers (not
    ``bool``/``complex``/``NaN``); ``comparators`` must be a dict of ``(actual, expected) -> bool`` callables
    keyed by ``type`` or field name; ``ignore_null`` and ``strict_types`` must be bools.
    """
    if ignore_null is not False and ignore_null is not True:
        raise TypeError("given ignore_null arg must be a bool")
    if strict_types is not False and strict_types is not True:
        raise TypeError("given strict_types arg must be a bool")
    if tolerance is None and rel is None and comparators is None and not ignore_null and not strict_types:
        return None
    if rel is not None:
        require_rel(rel)
    if tolerance is not None:
        _require_tolerance(tolerance)
    if comparators is not None:
        if not isinstance(comparators, dict):
            raise TypeError("given comparators arg must be a dict")
        for comparator in comparators.values():
            if not callable(comparator):
                raise TypeError("each comparator must be callable")
    duration = type(tolerance) not in (int, float) and numpy_duration(tolerance)
    if duration and rel is not None:
        raise TypeError("given rel arg is a fraction of a number's size, which a numpy duration tolerance has none of")
    return _CompareConfig(
        tolerance=tolerance,
        rel=rel,
        comparators=comparators,
        ignore_null=ignore_null,
        strict_types=strict_types,
        duration=duration,
    )


def _require_tolerance(tolerance: Any) -> None:
    """Refuse an absolute tolerance that is no non-negative real number: a `bool`, a complex one, a NaN."""
    if isinstance(tolerance, bool) or not isinstance(tolerance, numbers.Number) or isinstance(tolerance, complex):
        raise TypeError("given tolerance arg must be a real number")
    if _is_nan(tolerance):
        raise ValueError("given tolerance arg must not be NaN")
    if tolerance < zero_of(tolerance):
        raise ValueError("given tolerance arg must not be negative")


def require_rel(rel: object) -> None:
    """Refuse a relative tolerance that is no non-negative real number: a `bool`, a complex one, a NaN, a duration."""
    if isinstance(rel, bool) or not _is_real_number(rel):
        raise TypeError("given rel arg must be a real number")
    if _is_nan(rel):
        raise ValueError("given rel arg must not be NaN")
    if cast("float", rel) < 0:
        raise ValueError("given rel arg must not be negative")


def _ambiguous_array_operand(value: object, other: object) -> object | None:
    """Return the array/frame-like operand whose ``==`` has no single truth value, else ``None``.

    numpy/pandas/polars containers expose ``__array__`` and compare element-wise, so ``bool(a == b)``
    raises rather than yielding one bool (and a ``DataFrame`` also quacks dict-like, which would otherwise
    mis-dispatch the comparison).  The ``__array__`` gate keeps the extra comparison off the hot path; the
    truth test is actually attempted, so 0-d / scalar array values (which *are* truth-testable) pass
    through unchanged.
    """
    if not hasattr(value, "__array__") and not hasattr(other, "__array__"):
        return None  # fast path: no array-like operand, skip the tuple/loop on every is_equal_to
    if (
        type(value) is not type(other)
        and (isinstance(value, _SEQUENCES) or isinstance(other, _SEQUENCES))
        and broadcasts(value, other)
    ):
        return None  # a `numpy` scalar against a list, which `_guarded_equal` answers as unequal
    for candidate, counterpart in ((value, other), (other, value)):
        if hasattr(candidate, "__array__"):
            try:
                bool(candidate == counterpart)
            except (ValueError, TypeError):
                return candidate
            except OverflowError as overflow:
                if raised_inside(overflow):
                    raise
                continue  # a `numpy` scalar converting a bignum, which says nothing about element-wise `==`
            except decimal.InvalidOperation as signal:
                if raised_inside(signal):
                    raise
                continue  # a signalling NaN, which `_guarded_equal` answers
    return None


def _array_equality_error(method: str, operand: object) -> TypeError:
    """Build the actionable error raised when ``method`` is given an element-wise array/frame-like."""
    # the dedicated assertion names the differing column or index, where wrapping `.equals()` reports a bare False
    dedicated = "is_frame_equal(expected)" if hasattr(operand, "equals") else "is_array_equal(expected)"
    return TypeError(
        f"{method}() cannot directly compare <{type(operand).__name__}>: its '==' is element-wise and has"
        f" no single truth value. Use {dedicated}, assert on extracted scalars (columns, shape, length),"
        " or use satisfies(...) with an explicit predicate."
    )


def _find_ambiguous_operand(actual, expected, _seen=None):
    """Locate the array/frame-like member that broke a comparison, walking the diff engine's containers.

    Cold error-path only; ``None`` means the error was not array-caused and must be re-raised unchanged.
    """
    if _seen is None:
        _seen = set()
    pair = (id(actual), id(expected))
    if pair in _seen:
        return None
    _seen = _seen | {pair}
    operand = _ambiguous_array_operand(actual, expected)
    if operand is not None:
        return operand
    for left, right in _members_compared(actual, expected):
        found = _find_ambiguous_operand(left, right, _seen)
        if found is not None:
            return found
    return None


def _members_compared(actual: Any, expected: Any) -> Iterable[tuple[Any, Any]]:
    """The pairs ``==`` walks into for two values of one container kind, and none for any other pair."""
    if is_mapping_like(actual) and is_mapping_like(expected):
        expected_keys = set(expected)
        found = ((key, *held_key(expected_keys, key)) for key in actual)
        return ((actual[key], expected[held]) for key, present, held in found if present)
    if (
        dataclasses.is_dataclass(actual)
        and not isinstance(actual, type)
        and dataclasses.is_dataclass(expected)
        and not isinstance(expected, type)
    ):
        return (
            (getattr(actual, one.name), getattr(expected, one.name, None))
            for one in dataclasses.fields(actual)
            if one.compare
        )
    if is_attrs_instance(actual) and is_attrs_instance(expected):
        return _keyed_members(actual, expected)
    if is_model_dump_object(actual) and is_model_dump_object(expected):
        return ((model_field_values(actual), model_field_values(expected)),)
    if isinstance(actual, (list, tuple)) and isinstance(expected, (list, tuple)):
        return zip(actual, expected, strict=False)
    return ()


def _keyed_members(actual: Any, expected: Any) -> tuple[tuple[Any, Any], ...]:
    """The attrs fields ``==`` compares, each read through its key as ``==`` reads it, or none.

    Only what ``==`` compares can have broken it.  attrs reads every key before it compares a field, so a key
    that raises is the error being explained and no array is to blame: read again here, it raised a second
    error while the first was handled, and skipped, it let a later array take the blame.
    """
    try:
        return tuple(
            (
                eq_keyed(one, getattr(actual, one.name)),
                eq_keyed(one, getattr(expected, one.name)) if hasattr(expected, one.name) else None,
            )
            for one in actual.__attrs_attrs__
            if one.eq is not False
        )
    except (TypeError, ValueError):  # the two errors `_guarded_equal` hands to this search
        return ()


def _guarded_equal(actual, expected, *, method="is_equal_to") -> bool:
    """``bool(actual == expected)``, converting the ambiguity raised from *inside* a container's ``==``
    (where the top-level operand gate cannot see the array member) into the actionable ``TypeError``.

    The one question every equality verdict asks, the negative ones included: a type's ``__ne__`` need
    not be the negation of its ``__eq__``, and asking it made ``is_equal_to`` and ``is_not_equal_to``
    fail the same pair while a list holding that pair, which compares its members with ``==``, passed.
    A signalling NaN or an overflowing `numpy` float, anywhere in the pair, is answered as `equals` answers it.
    """
    try:
        equal = actual == expected
        if type(equal) is bool or type(actual) is type(expected):
            return bool(equal)
        return not broadcasts(actual, expected, answer=equal) and bool(equal)
    except REFUSALS as refusal:
        return _equal_past_refusal(actual, expected, refusal, method)


def _equal_past_refusal(actual, expected, refusal: Exception, method: str) -> bool:
    """What a pair whose ``==`` raised *refusal* answers: the actionable error for an array, else `equal_past`."""
    if issubclass(type(refusal), (ValueError, TypeError)):
        operand = _find_ambiguous_operand(actual, expected)
        if operand is not None:
            raise _array_equality_error(method, operand) from refusal
    return equal_past(actual, expected, refusal)


def _is_real_number(value) -> bool:
    """Return whether ``value`` is a real number eligible for tolerance (excludes ``bool`` and ``complex``).

    Array/frame-likes are not `numbers.Number`, so they are excluded too - tolerance never triggers
    their element-wise ``==`` that has no single truth value.  An exact `int` or `float` answers before
    the ABC check, which cost a hundred nanoseconds on every leaf a tolerance is asked about.  A `numpy`
    duration is none, though `numpy` registers it as an integer: only another duration measures it.
    """
    return type(value) in (int, float) or (
        isinstance(value, numbers.Number) and not isinstance(value, (bool, complex)) and not numpy_duration(value)
    )


def zero_of(tolerance: Any) -> Any:
    """The zero a *tolerance* is signed against: a `numpy` duration's in its own unit, which a bare ``0`` is not."""
    return tolerance - tolerance if type(tolerance) not in (int, float) and numpy_duration(tolerance) else 0


def plainly_within(actual, expected, tolerance) -> bool | None:
    """`_within_tolerance` over three exact `int` or `float` operands, or ``None`` where an `int` overflows a `float`.

    The same rule in its fewest steps: a NaN is close to nothing, an infinity only to an equal one, and a finite
    pair by its difference or by the window around either side, two integers by their difference alone.
    """
    if actual != actual or expected != expected:
        return False
    try:
        if actual in (math.inf, -math.inf) or expected in (math.inf, -math.inf):
            return actual == expected
        if actual == expected or abs(actual - expected) <= tolerance:
            return True
        if type(actual) is int and type(expected) is int:
            return False
        return (
            expected - tolerance <= actual <= expected + tolerance
            or actual - tolerance <= expected <= actual + tolerance
        )
    except OverflowError:
        return None


def within_either(actual, expected, tolerance, rel) -> bool:
    """Whether the absolute tolerance holds, where one is given, or else the relative one, where one is given.

    Either is enough, as `pytest.approx` takes the larger of its two allowances.  Added together, the two
    widened each other: ``100`` against ``103`` within ``1`` and ``0.02`` held by their sum and by neither.
    """
    if tolerance is not None and _within_tolerance(actual, expected, tolerance):
        return True
    return rel is not None and relatively_within(actual, expected, rel)


def relatively_within(actual, expected, rel) -> bool:
    """Whether *actual* is within *rel* of the size of *expected*, measured as that absolute tolerance is.

    Scaled by the expected side, as `pytest.approx`, `numpy.testing.assert_allclose` and AssertJ scale it.
    Scaled by the larger of the two, as `math.isclose` scales a pair with no expected side, the value under
    test widened its own allowance: any two numbers of one sign were within ``1`` of each other, and ``2``
    was within ``0.5`` of ``1``.  The allowance is then measured as `_within_tolerance` measures any, so a NaN
    is within nothing, an infinity only of an equal one, and an infinite *rel* covers every finite pair, a
    zero's too, where ``inf * 0`` would be a NaN.
    """
    if type(actual) in (int, float) and type(expected) in (int, float) and type(rel) in (int, float):
        try:
            allowance = rel * abs(expected)
        except OverflowError:
            allowance = math.inf
        # an overflowed or infinite allowance, or the NaN of `inf * 0`, is the general path's
        if allowance - allowance == 0:
            within = plainly_within(actual, expected, allowance)
            if within is not None:
                return within
    actual, expected, rel = _as_measured(actual, expected, rel)
    # answered by rule before any arithmetic, which a trapping `Decimal` context may refuse
    actual_kind, expected_kind = _non_finite(actual), _non_finite(expected)
    if actual_kind or expected_kind:
        return actual_kind == expected_kind == "inf" and bool(actual == expected)
    if _non_finite(rel) == "inf":
        return True
    return _within_tolerance(actual, expected, _fraction_of(expected, rel))


def _fraction_of(expected, rel):
    """*rel* of the size of *expected*, in their own arithmetic, and exactly where that refuses or overflows a float.

    Overflowed to an infinity, the allowance covered every finite pair: ``1e308`` was within ``1.9`` of
    ``-1e308``, when ``2e308`` exceeds ``1.9e308``.  A `Decimal` refuses a `float` and a bignum overflows
    one, and those are taken as fractions too.  A `Decimal` context that traps its own overflow raises it
    here, as it does in the difference an absolute tolerance takes.
    """
    try:
        allowance = rel * abs(expected)
    except (TypeError, OverflowError) as error:
        # their own `__abs__` or `__mul__` raised: a bug in the value, not a refusal
        if raised_inside(error) and not rational_overflow(error):
            raise
    else:
        if _non_finite(allowance) != "inf":
            return allowance
    return _as_fraction(rel) * abs(_as_fraction(expected))


def _within_tolerance(actual, expected, tolerance) -> bool:
    """Whether two values lie within ``tolerance`` of each other, the same answer whichever comes first.

    One distance, measured three ways that a float rounds differently at the boundary: the difference,
    and the window around each side.  Any of them holding is enough.  Measured one way each, the three
    spellings disagreed: ``-1.1`` was close to ``-0.9`` within ``0.2`` for `is_close_to`, which windows
    around the other operand, and not for `match.close_to`, which windows around the value, nor for
    ``is_equal_to(tolerance=)``, which takes the difference.  Each spelling now takes any of the three, so a
    pair all of them measure gets one answer.

    A window the ordering engine cannot order is one way fewer of holding, and the difference still
    answers: a `Decimal` refuses to order against a `numpy.int64` it subtracts exactly.  Only a pair with
    no difference either raises `UnorderableError` out of the windows, for the caller to refuse or to read
    as no match.

    ``NaN`` is never within, and an infinity is within only of itself, whatever the tolerance, the rule
    `math.isclose` keeps.  The operands are classified before equality is asked, since a value's own
    `__eq__` could otherwise call a NaN or a finite number equal to what it is not, and the distance is
    never classified: two finite values far enough apart overflow their difference to an infinity and are
    still measured.  An infinite tolerance was a wildcard before this, `1` was close to `inf` within `inf`
    through the window around `1`, and it now covers every finite pair and no more.

    A `numpy` integer is measured as the `int` it holds (`_as_measured`): taken through its own arithmetic,
    `uint8(3)` was 9 away from 250.  Two of `int` and of a `Fraction` of two `int` are measured by their
    difference alone, which is exact: a window under a float tolerance rounds an integer past ``2**53``, and
    ``2**53 + 1`` was within ``0.0`` of ``2**53``.  A `Fraction` built from a `numpy` integer keeps it as a
    part, wraps in its own arithmetic as it does in Python's, and is measured as before.
    """
    kind, other, span = type(actual), type(expected), type(tolerance)
    # asked of the classes kept: a call for every triple cost two `float64` 10%
    if not (kind is float and other is float and span is float) and (
        (kind is not int and type(kind) is type and kind not in _NOT_FIXED)
        or (other is not int and type(other) is type and other not in _NOT_FIXED)
        or (span is not int and span is not float and (kind is int or (type(span) is type and span not in _NOT_FIXED)))
    ):
        actual, expected, tolerance = _as_measured(actual, expected, tolerance)
    actual_kind, expected_kind = _non_finite(actual), _non_finite(expected)
    if actual_kind or expected_kind:
        return actual_kind == expected_kind == "inf" and bool(actual == expected)
    try:
        if actual == expected:
            return True
    except (TypeError, OverflowError) as refusal:
        # `Decimal` refuses to compare a `numpy.int64` it subtracts exactly: the equality is unknown, not false
        if raised_inside(refusal):
            raise
    difference = _difference_within(actual, expected, tolerance)
    if difference or (difference is not None and _differ_exactly(actual, expected)):
        return bool(difference)
    unordered = None
    try:
        if _window_holds(expected, actual, tolerance):
            return True
    except UnorderableError as refusal:
        unordered = refusal
    try:
        if _window_holds(actual, expected, tolerance):
            return True
    except UnorderableError as refusal:
        unordered = unordered or refusal
    if unordered is not None and difference is None:
        raise unordered
    return False


def _differ_exactly(actual, expected) -> bool:
    """Whether each of the two is an `int` or a `Fraction` of two, so their difference is exact.

    A `Fraction` built from a `numpy` integer keeps it as a part, and its own arithmetic wraps at that width.
    """
    return _exact_rational(actual) and _exact_rational(expected)


def _exact_rational(value) -> bool:
    kind = type(value)
    if kind is int:
        return True
    return kind is fractions.Fraction and type(value.numerator) is int and type(value.denominator) is int


def _as_measured(actual, expected, tolerance) -> tuple[Any, Any, Any]:
    """The operands of a closeness as they are measured where one of them may be a `numpy` integer.

    With one in the pair, all three are read as the Python numbers they hold (`python_numbers`).  So is the
    tolerance of a pair whose difference is exact: held against a `numpy` float, an exact distance would be
    rounded to the float's width, and ``2**24 + 1`` was within ``float32(2**24)`` of zero.  Standing as the
    tolerance alone a `numpy` integer is read as its `int`, since a window around a Python number wraps it.  Not
    beside a pair that holds a `numpy` float, whatever that float holds: `numpy` measures a float against an
    integer of any width without wrapping, and a Python `int` in its place would be rounded to the float's
    width.
    """
    one, other = python_numbers(actual, expected)
    if one is not actual or other is not expected or _differ_exactly(one, other):
        return one, other, python_number(tolerance)
    if numpy_float(actual) or numpy_float(expected):
        return actual, expected, tolerance
    return actual, expected, unwrapped(tolerance)


def _difference_within(actual, expected, tolerance) -> bool | None:
    """``abs(actual - expected) <= tolerance``, or ``None`` for two values that cannot be subtracted.

    Tried as written, so two floats keep the arithmetic they always had.  A `Decimal` against a ``float``
    refuses to subtract at all and a bignum ``int`` or a `Fraction` past the float range overflows one, and
    those pairs are measured exactly instead, through `fractions.Fraction`.  The tolerance is read as the
    ordering engine reads a number, so an infinite one keeps its sign and covers every finite distance, and
    through `fractions.Fraction` where that reader has no exact value for it.
    """
    try:
        return abs(actual - expected) <= tolerance
    except (TypeError, OverflowError) as error:
        # their own `__sub__` or `__abs__` raised: a bug in the value, not a refusal
        if raised_inside(error) and not rational_overflow(error):
            raise
        try:
            distance = abs(_as_fraction(actual) - _as_fraction(expected))
            bound = _exact_real(tolerance)
            rank, exact = bound if isinstance(bound, tuple) else (0, _as_fraction(tolerance))
        except (TypeError, ValueError, OverflowError):
            return None
        return rank > 0 if rank else distance <= exact


def _as_fraction(value: Any) -> fractions.Fraction:
    """*value* as an exact `fractions.Fraction`, read as the ordering engine reads a finite number where it can.

    `Fraction` keeps the numerator an `Integral` gives it, so a `numpy.int64` stayed a fixed-width integer inside
    it and overflowed again the moment a bignum met it in the exact arithmetic, and some interpreters' `Fraction`
    refuses a `numpy` float outright.  An infinity or a NaN is left to `Fraction`, which refuses both.
    """
    exact = _exact_real(value)
    if isinstance(exact, tuple) and not exact[0]:
        return exact[1]
    return fractions.Fraction(int(value) if isinstance(value, numbers.Integral) else value)


def _window_holds(middle, value, tolerance) -> bool:
    """Whether *value* lies in the closed window *tolerance* either side of *middle*."""
    try:
        low, high = tolerance_window(middle, tolerance)
    except WindowRefusedError:
        return False
    if type(value) is type(low) is type(high) is float:
        return low <= value <= high
    return holds(value, low, "ge") and holds(value, high, "le")


def _is_nan(value) -> bool:
    """Whether the value is a NaN, without converting what never is one.

    A `Decimal` is asked through its base type: a signalling NaN refuses to become a float, and reading
    it as "not a NaN" is the one answer it certainly is not.  Not through the value's own `is_nan`,
    which a subclass owns: measured, one saying it was a NaN turned a passing `is_close_to` into a
    failure.  `_is_infinite` reads the same question the same way.

    An `int` or any other rational is never a NaN and is not converted: past the float range the
    conversion overflows, and for a `Fraction` it overflows inside Python code, which read as a bug in the
    value.  Any other value is converted, and an error from a conversion of its own is handed on:
    swallowed, `is_not_nan()` held on a value nothing could read.
    """
    if isinstance(value, float):
        return math.isnan(value)
    if isinstance(value, decimal.Decimal):
        return decimal.Decimal.is_nan(value)
    if isinstance(value, (int, numbers.Rational)):
        return False
    return math.isnan(value)


def _is_infinite(value) -> bool:
    """Whether a real number other than a `Decimal` is itself an infinity.

    A `float` directly.  Any other value is asked through `math.isinf`, since a `numpy.float32` infinity is
    not a `float` and was read as finite, and one with no conversion is refused there, as the assertions
    always refused it.  A rational never is one, and an `int` or a `Fraction` past the float range would
    overflow the conversion.  `_non_finite` reads a `Decimal` through its base type's own method, and the
    assertions asking this refuse one.

    The conversion alone would call a finite value past the float range infinite, a `numpy.longdouble` or
    an arbitrary-precision float, so the value's own comparison has to agree.  A conversion of their own
    that raises is a bug in the value and is handed on, as `_is_nan` does.
    """
    if isinstance(value, float):
        return math.isinf(value)
    if isinstance(value, (int, numbers.Rational)):
        return False
    return math.isinf(value) and bool(value == math.inf or value == -math.inf)


def _non_finite(value) -> str:
    """``"nan"`` or ``"inf"`` for a value closeness answers by rule, ``""`` for one it measures.

    One pass per operand: a float, a `Decimal` and a type with no conversion answer before either question.
    The conversion is read off the type rather than the `numbers` ABCs, which cost a datetime pair a quarter
    of its `is_close_to`, measured, and a datetime is measured rather than refused.
    """
    if isinstance(value, float):
        if math.isfinite(value):
            return ""
        return "nan" if math.isnan(value) else "inf"
    if isinstance(value, decimal.Decimal):
        if decimal.Decimal.is_finite(value):
            return ""
        return "nan" if decimal.Decimal.is_nan(value) else "inf"
    if isinstance(value, int) or not hasattr(type(value), "__float__") or integral_kind(type(value)):
        return ""
    if _is_nan(value):
        return "nan"
    return "inf" if _is_infinite(value) else ""


class WindowRefusedError(TypeError):
    """The two operands form no window: neither the arithmetic nor an exact conversion takes them.

    A `TypeError` still, so a caller that let the operand's own refusal out keeps letting this one out,
    and a matcher, which may not raise, can tell it from a `__sub__` of somebody's own that raised.
    """


def tolerance_window(middle: Any, tolerance: Any) -> tuple[Any, Any]:
    """The closed interval ``middle`` plus and minus ``tolerance``.

    Typed as `Any` because the pairing is a run-time fact: the assertion has refused every combination
    but two before it asks, a number against a number and a datetime against a timedelta, and a checker
    reading the public signature alone is right to refuse the arithmetic.  A pair inside that domain can
    still refuse, since a class registered as a `numbers.Number` need not subtract, which is what
    `WindowRefusedError` is for: it hands back the operands' own refusal as something a matcher may answer
    "no match" to.
    """
    try:
        return middle - tolerance, middle + tolerance
    except (TypeError, OverflowError) as refusal:
        if raised_inside(refusal) and not rational_overflow(refusal):  # their own `__sub__` raised: a bug
            raise
        if not all(isinstance(operand, numbers.Number) for operand in (middle, tolerance)):
            raise WindowRefusedError(str(refusal)) from None
        # a `Decimal` refuses a `float` or a `Fraction` and a bignum overflows a `float`, all converting
        # exactly, while an infinite or NaN one does not convert at all
        try:
            exact, span = _as_fraction(middle), _as_fraction(tolerance)
        except (TypeError, ValueError, OverflowError) as failed:
            raise WindowRefusedError(str(failed)) from None
        return exact - span, exact + span


def _resolve_comparator(actual, config: _CompareConfig, *, field):
    """Resolve the comparator owning a leaf: immediate field name first, then exact type, then ``isinstance``.

    ``field`` is the leaf's immediate key/field name (``None`` for sequence elements and bare scalars, which
    have no name).  Returns ``None`` when no comparator applies, so the caller falls back to tolerance / ``==``.
    """
    comparators = config.comparators
    if comparators is None:
        return None
    actual = as_held(actual)
    if field is not None and not isinstance(field, type) and field in comparators:
        return comparators[field]
    if type(actual) in comparators:
        return comparators[type(actual)]
    for key, comparator in comparators.items():
        if isinstance(key, type) and isinstance(actual, key):
            return comparator
    return None


def _types_differ(actual, expected) -> bool:
    """Whether ``strict_types`` should reject this pair.

    A matcher standing in for a value is not a value, so it is exempt: the expected side of
    ``is_equal_to({"id": match.greater_than(0)})`` is a ``GreaterThanMatcher`` by construction, and
    comparing its type against an ``int`` would break every composed matcher rather than catch a bug.

    ``_is_matcher`` is imported here rather than at module scope because ``_matcher_impls`` imports
    ``_guarded_equal`` from this module, so the module-level import would be a cycle.
    """
    if kind_of(actual) is kind_of(expected):
        return False
    from .._matcher_impls import _is_matcher

    return not _is_matcher(expected) and not _is_matcher(actual)


def _keyed_types_differ(actual, expected) -> bool:
    """Whether two equal containers disagree on the *types* of what they are keyed by.

    The rest of `strict_types` works pair by pair, and a mapping key or a set member never becomes a
    pair: the container matched them itself, by hash and equality, before the walk ever saw them.  So
    `{True: "a"} == {1: "a"}` and `{1} == {1.0}` both passed a strict comparison, which is the one
    thing the flag's name promises they would not.

    Each side is reduced to its members paired with their types.  `(bool, True)` and `(int, 1)` are
    different pairs where `True` and `1` are the same key, which is exactly the distinction being made.
    Values are left alone here: they do become pairs, and the walk judges them.

    A member that is no atom is then read beside the one it was matched with (`typed_apart`): `(1, 2)` and
    `(True, 2)` are both a tuple, and the type that differs is inside.
    """
    # structural, like everything here: the concrete-type check let a `UserDict` pass where the matcher refused it
    keyed = is_mapping_like(actual) and is_mapping_like(expected)
    if not keyed and not (isinstance(actual, (set, frozenset)) and isinstance(expected, (set, frozenset))):
        return False
    if of_one_atom(actual, expected):
        return False
    typed = {(type(member), member) for member in actual}
    if typed != {(type(member), member) for member in expected}:
        return True
    if _EQ_ATOMIC.issuperset(map(type, actual)):
        return False
    held = {member: member for member in expected}
    return any(kind not in _EQ_ATOMIC and typed_apart(member, held.get(member, member)) for kind, member in typed)


def of_one_atom(actual: Any, expected: Any) -> bool:
    """Whether every member of both is of one class, and that class an atom: no two of them differ in type then.

    Asked of the classes alone, ahead of any pass that pairs the members.
    """
    kinds = set(map(type, actual))
    return len(kinds) == 1 and kinds <= _EQ_ATOMIC and kinds == set(map(type, expected))


def typed_apart(member: Any, counterpart: Any) -> bool:
    """Whether two values a hash holds equal differ in type, at any depth of the tuples and frozensets in them.

    Those two are the containers a hash reads through, and each is read where its ``==`` is the builtin one,
    which is what pairs the parts: a tuple or a frozenset of a class with an ``==`` of its own may hold two
    equal with nothing in them alike, and is compared by its class alone, as a record used as a key is.
    Walked on a list, since a tuple nested past the recursion limit is still a key.
    """
    pending = [(member, counterpart)]
    while pending:
        one, other = pending.pop()
        kind = type(one)
        if kind is not type(other):
            return True
        if kind is tuple or (issubclass(kind, tuple) and _keeps_equality_of(kind, tuple)):
            pending.extend(zip(tuple.__iter__(one), tuple.__iter__(other), strict=False))
        elif kind is frozenset or (issubclass(kind, frozenset) and _keeps_equality_of(kind, frozenset)):
            held = {part: part for part in frozenset.__iter__(other)}
            pending.extend((part, held.get(part, part)) for part in frozenset.__iter__(one))
    return False


def _keeps_equality_of(kind: type, builtin: type) -> bool:
    """Whether the ``==`` *kind* answers with is the one *builtin* defines, read off the class tree."""
    return (definition_of(kind, "__eq__") or (object, None))[0] is builtin


def _kinds_never_equal(actual, expected) -> bool:
    """Whether ``==`` rejects the pair by its kind alone, which a walk over the parts cannot see.

    Under a compare config the walker decides by parts, so ``[1.0]`` against ``(1.0,)``, or two dataclasses
    of different classes holding the same fields, had no differing part and passed, while ``==`` rejects
    both outright.  Asked once ``==`` has said no, or of two sequences a key option takes element by element.
    Either way it never fails a pair ``==`` accepts, by the second paragraph.

    The kind alone is not the answer: a list subclass may define ``__eq__`` to accept a tuple.  So a pair
    of different kinds counts only when both sides' own ``__eq__`` decline it, which leaves ``==`` at
    identity whatever the parts hold.  A pydantic model answers ``False`` rather than declining, so which of
    class or fields decided cannot be told apart, and models are left to the walk.
    """
    if isinstance(actual, (list, tuple)) and isinstance(expected, (list, tuple)):
        kinds_differ = isinstance(actual, list) is not isinstance(expected, list)
    else:
        both_dataclasses = all(
            dataclasses.is_dataclass(side) and not isinstance(side, type) for side in (actual, expected)
        )
        both_attrs = is_attrs_instance(actual) and is_attrs_instance(expected)
        kinds_differ = (both_dataclasses or both_attrs) and type(actual) is not type(expected)
    return kinds_differ and _both_decline(actual, expected)


def _declines(value: Any, other: Any) -> bool:
    """Whether *value*'s own ``__eq__`` answers ``NotImplemented`` for *other*, asked as ``==`` asks it.

    Read statically off the type, since `type(x).__eq__` is an ordinary read that a metaclass answers,
    and bound through the descriptor protocol, since that is what turns a function, a `staticmethod` or
    anything else on the class into the callable the operator uses.
    """
    held: Any = inspect.getattr_static(type(value), "__eq__", None)
    bind: Any = getattr(type(held), "__get__", None)
    # measured against `==` itself: a callable that binds to nothing is called with the other side alone
    asking = held if bind is None else bind(held, value, type(value))
    return asking(other) is NotImplemented


def _both_decline(actual: Any, expected: Any) -> bool:
    """Whether each side's own ``__eq__`` answers ``NotImplemented`` for the other."""
    try:
        return _declines(actual, expected) and _declines(expected, actual)
    except Exception:  # an `__eq__` that raises decides nothing here, and the walk goes on as before
        return False


def _node_decision(
    actual, expected, config: _CompareConfig | None, *, field=None, at_root: bool = False, keys_left_out: bool = False
) -> str:
    """Classify a node as ``"equal"``, ``"leaf"``, ``"recurse"``, ``"unanswered"`` or ``"strict"``.

    With ``config is None`` this is exactly the engine's historical behavior: differing values ``"recurse"``
    (to decompose into a sub-diff), equal values are ``"equal"`` (skipped); ``"leaf"`` never occurs.  With a
    config, a matching comparator decides the node, ahead of ``strict_types``, and a tolerance widens ``==``
    for a pair of real numbers; either classifies the node ``"equal"`` or ``"leaf"``, never recursed into.

    ``"strict"`` is the fourth: the two sides are equal, but ``strict_types`` or a comparator still has to
    look inside, because a container's ``==`` says nothing about the types of its members, nor about what a
    comparator says of them.  It differs from ``"recurse"`` only in what an undecomposable value means,
    which `assertpy._engine._diff._Walk.descend()` is the single place to know.

    ``"unanswered"`` is a graph ``==`` ran out of stack on.  It is walked as ``"recurse"`` is, and the walk is
    then the only judge of the pair, where under ``"recurse"`` the pair is already known to differ.
    """
    if config is not None:
        if config.ignore_null and field is not None and as_held(expected) is None:
            return "equal"  # a named field the expected side leaves None is not compared
        comparator = _resolve_comparator(actual, config, field=field)
        if comparator is not None:
            agreed = verdict(comparator(as_held(actual), as_held(expected)), subject="the comparator")
            return "equal" if agreed else "leaf"
        if config.strict_types:
            if actual is expected and not at_root:
                # identity, free from `PyObject_RichCompareBool`.  Not at the root, where it made `strict_types` weaker
                return "equal"
            if _types_differ(actual, expected):
                # ahead of tolerance: how far apart is not the same as may differ in type
                return "leaf"
            if type(actual) not in _EQ_ATOMIC and _walked_equal(actual, expected):
                # `[True] == [1]`: a container says nothing about the types inside it, so the walk keeps going.
                # Its keys first: the walk descends keys into values, so `True` and `1` keys present the same
                # values.  Asked of an equal pair alone: two that differ may differ only in a key left out.
                # Not where a path leaves keys of this pair out: the walk asks the types of the keys it keeps
                return "leaf" if not keys_left_out and _keyed_types_differ(actual, expected) else "strict"
        if (config.tolerance is not None or config.rel is not None) and (
            numpy_duration(as_held(actual)) and numpy_duration(as_held(expected))
            if config.duration
            else _is_real_number(as_held(actual)) and _is_real_number(as_held(expected))
        ):
            return _tolerance_decision(actual, expected, config, at_root=at_root)
        if (
            config.comparators
            and actual is not expected
            and type(actual) not in _EQ_ATOMIC
            and _walked_equal(actual, expected)
        ):
            # a container's `==` says nothing of what a comparator says of the leaves inside it, so the walk goes on
            return "strict"
    return _plain_decision(actual, expected, config, at_root=at_root)


def held_equal_decision(actual, expected, config: _CompareConfig, *, field) -> str:
    """`_node_decision` for a field of two objects their own ``==`` holds equal, where ``"equal"`` is also not judged.

    That ``==`` has judged what the two hold, so a field ``==`` holds apart is not the walk's to fail: it is one
    the object leaves out of its ``==`` or reads another way, and which of the two cannot be told.  A field
    ``==`` holds equal is asked what the options add to that: a comparator that owns it, under ``strict_types``
    its type, and either of what it holds.  A field ``==`` cannot answer for, a graph it runs out of stack
    on, is ``"unanswered"`` here as anywhere, and the walk is its judge.
    """
    if actual is not expected and _walked_equal(actual, expected) is False:
        return "equal"
    decision = _node_decision(actual, expected, config, field=field)
    return decision if decision in ("leaf", "strict", "unanswered") else "equal"


def _tolerance_decision(actual, expected, config: _CompareConfig, *, at_root: bool) -> str:
    """A pair of real numbers under a tolerance, which only widens ``==``: equal if ``==`` says so, else measured.

    Identity counts as ``==`` below the root, as it does inside a container, so the very NaN both sides hold is
    equal in a dict as in a list, and a root NaN still is not.
    """
    if (actual is expected and not at_root) or _guarded_equal(actual, expected):
        return "equal"
    try:
        within = within_either(as_held(actual), as_held(expected), config.tolerance, config.rel)
    except UnorderableError:
        return _plain_decision(actual, expected, config, at_root=at_root)
    return "equal" if within else "leaf"


def _plain_decision(actual, expected, config: _CompareConfig | None, *, at_root: bool = False) -> str:
    """``==``'s answer as a decision, where under a config a pair ruled out by its kind alone is a leaf."""
    if actual is expected and not at_root:
        # the same rule a container's own `==` applies to its members, and the verdict came from that `==`:
        # without it the diff listed a NaN both sides hold as differing, and the hint blamed it
        return "equal"
    equal = _walked_equal(actual, expected)
    if equal:
        return "equal"
    if equal is None:
        return "unanswered"
    return "leaf" if config is not None and _kinds_never_equal(actual, expected) else "recurse"


def _walked_equal(actual, expected) -> bool | None:
    """`_guarded_equal` for a walk, which has its own answer where ``==`` has none: ``None`` for a graph ``==``
    runs out of stack on, which the walk then enters, counting a pair it meets again as equal.

    It asks ``==`` itself: a walk asks this of every pair, and asked through `_guarded_equal` the frame between
    cost 11 ns a pair, a tenth of a failing comparison of two lists of 500.
    """
    try:
        try:
            equal = actual == expected
            if type(equal) is bool or type(actual) is type(expected):
                return bool(equal)
            return not broadcasts(actual, expected, answer=equal) and bool(equal)
        except REFUSALS as refusal:
            return _equal_past_refusal(actual, expected, refusal, "is_equal_to")
    except RecursionError:
        return None


def _spec_matches(key, value, specs) -> bool:
    """Return whether a dict ``key``/``value`` matches any ignore/include ``spec``.

    A spec matches by exact key equality (today's behavior), by a compiled `re.Pattern` searched
    against ``str(key)``, or by a ``type`` the ``value`` is an instance of.  Nested-path tuples never match
    here - they are expanded by the recursion in `HelpersMixin._dict_not_equal()`.
    """
    for spec in specs:
        if isinstance(spec, re.Pattern):
            if spec.search(str(key)):
                return True
        elif isinstance(spec, type):
            if isinstance(value, spec):
                return True
        else:
            try:
                if spec == key:
                    return True
            except REFUSALS as refusal:
                if equal_past(spec, key, refusal):
                    return True
    return False


def _config_note(config: _CompareConfig | None) -> str:
    """A newline plus an echo of the comparison settings that were in force, or ``""`` when none were.

    ``is_equal_to`` already names ``ignore`` and ``include`` inside its sentence, but nothing reports
    the rest, and they are what a reader is questioning when a field they thought was tolerated still
    failed.  Rendered only for a non-default config: `_build_compare_config()` returns ``None`` when
    every setting is at its default, so the check costs nothing and the line never appears on the
    ordinary failure.

    It goes on its own line rather than into the sentence, so the original message stays a prefix and
    a `match=` or ``startswith`` written against it keeps working.
    """
    if config is None:
        return ""
    parts = []
    if config.tolerance is not None:
        parts.append(f"tolerance={config.tolerance!r}")
    if config.rel is not None:
        parts.append(f"rel={config.rel!r}")
    if config.comparators:
        keys = ", ".join(sorted(key.__name__ if isinstance(key, type) else str(key) for key in config.comparators))
        parts.append(f"comparators for {keys}")
    if config.ignore_null:
        parts.append("ignore_null=True")
    if config.strict_types:
        parts.append("strict_types=True")
    return "\ncompared with " + ", ".join(parts) if parts else ""
