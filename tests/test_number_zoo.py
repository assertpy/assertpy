"""Awkward numbers, crossed with every spelling of the numeric questions, each held to what it must answer.

Six defect groups lived here at once, each found by crossing these values rather than by a test someone thought
to write: a `Fraction` past the float range, a `numpy` float against a bignum, a signalling `Decimal`, a NaN bound,
a `numpy` NaN, and a private error class escaping a tolerance.  Every value has its place on the extended real
line, an infinity by its sign and anything finite by its exact `Fraction`, or none for a NaN, and every spelling
of a question is held to the answer that place gives: held, failed, or refused in the one sentence of the
library's that the case calls for.  Anything else, another answer, another sentence or another exception, is a
finding.

The `numpy` values join when the data extra is installed.
"""

from __future__ import annotations

import contextlib
import decimal
import fractions
import itertools
import math
import re
from typing import TYPE_CHECKING, Any

import pytest

from assertpy import AssertionFailure, assert_that, match

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from assertpy.assertpy import AssertionBuilder

try:
    import numpy
except ImportError:  # the data extra is optional, and the reduced cell runs without it
    numpy = None

_ORDINARY: dict[str, Any] = {
    "0": 0,
    "1": 1,
    "-1": -1,
    "half": 0.5,
    "neg-zero": -0.0,
    "bignum": 10**400,
    "-bignum": -(10**400),
    "big-fraction": fractions.Fraction(10**400, 3),
    "third": fractions.Fraction(1, 3),
    "tiny-fraction": fractions.Fraction(1, 10**20),
    "decimal": decimal.Decimal("1.5"),
}
"""Finite real numbers."""

_UNORDERED: dict[str, Any] = {
    "nan": math.nan,
    "decimal-nan": decimal.Decimal("NaN"),
    "decimal-snan": decimal.Decimal("sNaN"),
}
"""NaNs, which order against nothing and are close to nothing."""

_INFINITE: dict[str, Any] = {
    "inf": math.inf,
    "-inf": -math.inf,
    "decimal-inf": decimal.Decimal("Infinity"),
}
"""Infinities, each above or below every finite value and close only to an infinity of its sign."""

_BOOLS: dict[str, Any] = {"true": True, "false": False}
"""Refused as an operand of closeness, compared by plain equality under `tolerance=` (a13a3bc), ordered as ints."""

if numpy is not None:
    _ORDINARY["i64"] = numpy.int64(5)
    _ORDINARY["f32"] = numpy.float32(0.1)
    _UNORDERED["f32-nan"] = numpy.float32("nan")
    _INFINITE["f32-inf"] = numpy.float32("inf")

_ZOO: dict[str, Any] = {**_ORDINARY, **_UNORDERED, **_INFINITE, **_BOOLS}

_NUMPY_REAL: tuple[type, ...] = (
    ()
    if numpy is None
    else tuple({numpy.dtype(code).type for code in numpy.typecodes["AllInteger"] + numpy.typecodes["Float"]})
)
"""`numpy`'s own integer and floating scalar types, whose order a matcher asks at construction as a builtin's."""

_TOLERANCES: dict[str, Any] = {
    "0": 0,
    "tiny": 1e-17,
    "half": 0.5,
    "bignum": 10**400,
    "inf": math.inf,
    "decimal-inf": decimal.Decimal("Infinity"),
    "true": True,
    "nan": math.nan,
    "-1": -1,
    "-half": -0.5,
    "decimal-neg": decimal.Decimal(-1),
}
if numpy is not None:
    _TOLERANCES["f32-half"] = numpy.float32(0.5)
_FINITE_TOLERANCES = ("0", "tiny", "half", "bignum")
"""Finite tolerances every spelling measures, in ascending order."""
_UNBOUNDED = {"inf", "decimal-inf"}
"""Tolerances every finite pair lies within."""
_CLOSE_TO_REFUSES = {
    "-1": "not-negative",
    "-half": "not-negative",
    "decimal-neg": "not-negative",
    "nan": "nan-tolerance",
    "true": "bool-tolerance",
}
"""The tolerances `is_close_to` and `is_not_close_to` refuse, once both operands passed, and in which sentence."""
_TOLERANCE_REFUSES = {
    "-1": "not-negative",
    "-half": "not-negative",
    "decimal-neg": "not-negative",
    "nan": "nan-tolerance",
    "true": "real-tolerance",
}
"""The tolerances `is_equal_to(tolerance=)` refuses, before it looks at the operands at all."""
_MATCHER_REFUSES = {"-1": "not-negative", "-half": "not-negative", "decimal-neg": "not-negative"}
"""The tolerances `match.close_to` refuses at construction; nothing lies within a NaN or a bool one."""

if numpy is not None:
    _TOLERANCES.update({"f32-neg": numpy.float32(-1), "f32-neg-inf": numpy.float32("-inf"), "i64-neg": numpy.int64(-1)})
    for negative in ("f32-neg", "f32-neg-inf", "i64-neg"):
        _CLOSE_TO_REFUSES[negative] = _MATCHER_REFUSES[negative] = "not-negative"
        _TOLERANCE_REFUSES[negative] = "not-negative"

_SHOWN = r"<[^<>\n]+> \((?:[A-Za-z_]\w*\.)*[A-Za-z_]\w*\)"
_REFUSALS: dict[str, tuple[type[Exception], str, Callable[[], object]]] = {
    "nan-tolerance": (
        ValueError,
        "given tolerance arg must not be NaN",
        lambda: assert_that(0).is_close_to(0, math.nan),
    ),
    "not-negative": (
        ValueError,
        "given tolerance arg must not be negative",
        lambda: assert_that(0).is_equal_to(0, tolerance=-1),
    ),
    "real-tolerance": (
        TypeError,
        "given tolerance arg must be a real number",
        lambda: assert_that(0).is_equal_to(0, tolerance=True),
    ),
    "bool-tolerance": (
        TypeError,
        f"given tolerance arg must be a number other than a bool, but was {_SHOWN}",
        lambda: assert_that(0).is_close_to(0, True),
    ),
    "bool-other": (
        TypeError,
        f"given other arg must be a number other than a bool, but was {_SHOWN}",
        lambda: assert_that(0).is_close_to(True, 0),
    ),
    "bool-val": (
        TypeError,
        f"val must be a number other than a bool, or a datetime, but was {_SHOWN}",
        lambda: assert_that(True).is_close_to(0, 0),
    ),
    "real-val": (
        TypeError,
        f"val must be a real number, but was {_SHOWN}",
        lambda: assert_that(decimal.Decimal("1.5")).is_nan(),
    ),
    "low-high": (
        ValueError,
        "given low arg must be less than given high arg",
        lambda: assert_that(0).is_between(1, 0),
    ),
}
"""The library's own refusals these questions may give, whole sentences, each with an operation that says it.

These are the only exceptions not a finding, and a case is held to the one its oracle names.
"""

_CLOSENESS = {
    "forward": lambda held, value, other, tolerance: held(value).is_close_to(other, tolerance),
    "swapped": lambda held, value, other, tolerance: held(other).is_close_to(value, tolerance),
    "negated": lambda held, value, other, tolerance: held(value).is_not_close_to(other, tolerance),
    "tolerance=": lambda held, value, other, tolerance: held(value).is_equal_to(other, tolerance=tolerance),
    "matcher": lambda held, value, other, tolerance: match.close_to(other, tolerance).matches(value),
}
_ORDERING = {
    "less": lambda held, value, other: held(value).is_less_than(other),
    "at-least": lambda held, value, other: held(value).is_greater_than_or_equal_to(other),
    "matcher": lambda held, value, other: match.less_than(other).matches(value),
}
_RANGE = {
    "between": lambda held, value, low, high: held(value).is_between(low, high),
    "matcher": lambda held, value, low, high: match.between(low, high).matches(value),
}
_KIND = {
    "is_nan": lambda held, value: held(value).is_nan(),
    "is_not_nan": lambda held, value: held(value).is_not_nan(),
    "is_inf": lambda held, value: held(value).is_inf(),
    "is_not_inf": lambda held, value: held(value).is_not_inf(),
}
"""Each spelling asks through *held*, which builds the one assertion whose builder a pass must hand back."""


def _outcome(ask: Callable[..., object], *arguments: object, matcher: bool = False) -> str:
    """``held``, ``failed``, ``refused:<key>`` of `_REFUSALS`, or ``leak:<what>`` for anything else.

    An assertion holds by handing back the very builder it was asked through and fails by raising
    `AssertionFailure`; a matcher answers exactly a `bool`.  Anything else, a bare `AssertionError`, an unlisted
    exception, an assertion answering a `bool` or another builder, or a matcher answering a builder, is a leak.
    """
    built: list[AssertionBuilder] = []

    def held(value: object) -> AssertionBuilder:
        built.append(assert_that(value))
        return built[-1]

    try:
        answer = ask(held, *arguments)
    except AssertionFailure:
        return "leak:AssertionFailure" if matcher else "failed"
    except Exception as error:  # everything but the library's own failure is judged here, which is the point
        for key, (kind, text, _) in _REFUSALS.items():
            if type(error) is kind and re.fullmatch(text, str(error)):
                return f"refused:{key}"
        return f"leak:{type(error).__name__}"
    if matcher:
        return _verdict(answer) if type(answer) is bool else f"leak:{type(answer).__name__}"
    return "held" if len(built) == 1 and answer is built[0] else f"leak:{type(answer).__name__}"


def _answers(spellings: Mapping[str, Callable[..., object]], *arguments: object) -> dict[str, str]:
    return {name: _outcome(ask, *arguments, matcher=name == "matcher") for name, ask in spellings.items()}


def _wrong(shape: str, answers: dict[str, str], expected: dict[str, str]) -> list[tuple[str, str, str]]:
    return [(shape, name, f"{answers[name]} != {want}") for name, want in expected.items() if answers[name] != want]


def _quiet() -> contextlib.AbstractContextManager[object]:
    return numpy.errstate(all="ignore") if numpy is not None else contextlib.nullcontext()


def _verdict(holds: bool) -> str:
    return "held" if holds else "failed"


def _exact(value: Any) -> fractions.Fraction:
    if numpy is not None and isinstance(value, numpy.integer):
        return fractions.Fraction(int(value))
    if numpy is not None and isinstance(value, numpy.floating):
        return fractions.Fraction(*value.as_integer_ratio())
    return fractions.Fraction(value)


def _real(name: str) -> tuple[int, fractions.Fraction]:
    """A value's place on the extended real line: an infinity's sign, else ``0`` and its exact value."""
    value = _ZOO[name]
    if name in _INFINITE:
        return (1 if value > 0 else -1), fractions.Fraction(0)
    return 0, _exact(value)


def _within(value: Any, other: Any, tolerance: Any) -> bool:
    """Whether a finite pair is within a finite *tolerance*, as `_within_tolerance` states its contract.

    One distance measured three ways, the difference and the window around each side, in the pair's own
    arithmetic, any one holding being enough; and measured exactly where that arithmetic refuses the pair,
    which a window measured exactly would answer alike.  So a `Decimal` that rounds its distance to a bignum
    down to the tolerance is within it.  Two of `int` and `Fraction` have an exact difference, and it alone
    answers for them: a window under a float tolerance rounds one past ``2**53``.
    """
    if type(value) in (int, fractions.Fraction) and type(other) in (int, fractions.Fraction):
        written = _measured(lambda: abs(value - other) <= tolerance)
        return abs(_exact(value) - _exact(other)) <= _exact(tolerance) if written is None else written
    measured = [
        _measured(lambda: abs(value - other) <= tolerance),
        _measured(lambda: other - tolerance <= value <= other + tolerance),
        _measured(lambda: value - tolerance <= other <= value + tolerance),
    ]
    return any(measured) or (None in measured and abs(_exact(value) - _exact(other)) <= _exact(tolerance))


def _measured(measure: Callable[[], object]) -> bool | None:
    """One measure's answer, or ``None`` where the pair's arithmetic refuses it."""
    try:
        return bool(measure())
    except (TypeError, ArithmeticError):
        return None


def _close_to_refuses(asked: str, other: str, tolerance_name: str) -> str | None:
    """What `is_close_to` asked of *asked* refuses, in the order it looks: its value, the other, the tolerance."""
    if asked in _BOOLS:
        return "refused:bool-val"
    if other in _BOOLS:
        return "refused:bool-other"
    refusal = _CLOSE_TO_REFUSES.get(tolerance_name)
    return None if refusal is None else f"refused:{refusal}"


def _closeness_expected(value_name: str, other_name: str, tolerance_name: str) -> dict[str, str]:
    """A NaN is close to nothing, an infinity only to one of its sign, and a finite pair by `_within`."""
    names = {value_name, other_name}
    if names & _BOOLS.keys():
        within = not names & _UNORDERED.keys() and _real(value_name) == _real(other_name)
    elif names & _UNORDERED.keys():
        within = False
    elif names & _INFINITE.keys():
        within = _real(value_name) == _real(other_name)
    elif tolerance_name in _UNBOUNDED:
        within = True
    elif tolerance_name in _CLOSE_TO_REFUSES:
        within = False
    else:
        within = _within(_ZOO[value_name], _ZOO[other_name], _TOLERANCES[tolerance_name])
    refused = {
        "forward": _close_to_refuses(value_name, other_name, tolerance_name),
        "swapped": _close_to_refuses(other_name, value_name, tolerance_name),
        "negated": _close_to_refuses(value_name, other_name, tolerance_name),
        "tolerance=": _TOLERANCE_REFUSES.get(tolerance_name) and f"refused:{_TOLERANCE_REFUSES[tolerance_name]}",
        "matcher": _MATCHER_REFUSES.get(tolerance_name) and f"refused:{_MATCHER_REFUSES[tolerance_name]}",
    }
    answered = dict.fromkeys(_CLOSENESS, _verdict(within)) | {"negated": _verdict(not within)}
    if tolerance_name in _CLOSE_TO_REFUSES or names & _BOOLS.keys():
        answered["matcher"] = "failed"
    return {name: refused[name] or answered[name] for name in _CLOSENESS}


def _ordering_expected(value_name: str, other_name: str) -> dict[str, str]:
    if {value_name, other_name} & _UNORDERED.keys():
        return dict.fromkeys(_ORDERING, "failed")
    less = _real(value_name) < _real(other_name)
    return {"less": _verdict(less), "at-least": _verdict(not less), "matcher": _verdict(less)}


def _range_expected(value_name: str, low_name: str, high_name: str) -> dict[str, str]:
    """Reversed bounds are refused before the value is asked, and a NaN anywhere else holds nothing between.

    The matcher asks its bounds at construction only where that runs no code but the interpreter's or `numpy`'s
    (`_ordered_kind`), and between reversed bounds it did not ask, which nothing lies between, answers no match.
    """
    if not {low_name, high_name} & _UNORDERED.keys() and _real(low_name) > _real(high_name):
        bounds = (_ZOO[low_name], _ZOO[high_name])
        plain = all(type(bound) in (int, float, decimal.Decimal, fractions.Fraction, *_NUMPY_REAL) for bound in bounds)
        return {"between": "refused:low-high", "matcher": "refused:low-high" if plain else "failed"}
    if {value_name, low_name, high_name} & _UNORDERED.keys():
        return dict.fromkeys(_RANGE, "failed")
    return dict.fromkeys(_RANGE, _verdict(_real(low_name) <= _real(value_name) <= _real(high_name)))


def _kind_expected(name: str) -> dict[str, str]:
    """A `Decimal` is no real number to these questions, which refuse it."""
    if isinstance(_ZOO[name], decimal.Decimal):
        return dict.fromkeys(_KIND, "refused:real-val")
    nan, infinite = name in _UNORDERED, name in _INFINITE
    return {
        "is_nan": _verdict(nan),
        "is_not_nan": _verdict(not nan),
        "is_inf": _verdict(infinite),
        "is_not_inf": _verdict(not infinite),
    }


def test_closeness_answers_by_its_contract_in_every_spelling():
    findings = []
    with _quiet():
        for value_name, other_name, tolerance_name in itertools.product(_ZOO, _ZOO, _TOLERANCES):
            shape = f"{value_name}|{other_name}|{tolerance_name}"
            value, other, tolerance = _ZOO[value_name], _ZOO[other_name], _TOLERANCES[tolerance_name]
            answers = _answers(_CLOSENESS, value, other, tolerance)
            findings += _wrong(shape, answers, _closeness_expected(value_name, other_name, tolerance_name))
    assert_that(findings).described_as("closeness leaked or answered against its contract").is_empty()


def test_closeness_keeps_the_laws_of_a_distance():
    """Checks no oracle of this file computes: a zero tolerance holds exactly the equal pairs, and a pair within
    one tolerance is within every larger one, the infinite ones last.
    """
    findings = []
    ascending = [*_FINITE_TOLERANCES, "inf"]
    with _quiet():
        for value_name, other_name in itertools.product(_ORDINARY.keys() | _INFINITE.keys(), repeat=2):
            value, other = _ZOO[value_name], _ZOO[other_name]
            shape = f"{value_name}|{other_name}"
            held = [_outcome(_CLOSENESS["forward"], value, other, _TOLERANCES[name]) for name in ascending]
            if held[0] != _verdict(_real(value_name) == _real(other_name)):
                findings.append((shape, "zero tolerance", f"{held[0]} for a pair that is equal: {value == other}"))
            if held != sorted(held, key=lambda answer: answer == "held"):
                findings.append((shape, "a larger tolerance", " < ".join(held)))
    assert_that(findings).described_as("closeness broke a law of a distance").is_empty()


def test_a_nan_and_an_infinity_are_told_by_what_they_are():
    findings = []
    with _quiet():
        for name, value in _ZOO.items():
            findings += _wrong(name, _answers(_KIND, value), _kind_expected(name))
    assert_that(findings).described_as("a NaN or an infinity leaked or was told wrong").is_empty()


def test_ordering_answers_by_the_extended_real_line():
    findings = []
    with _quiet():
        for value_name, other_name in itertools.product(_ZOO, repeat=2):
            answers = _answers(_ORDERING, _ZOO[value_name], _ZOO[other_name])
            findings += _wrong(f"{value_name}|{other_name}", answers, _ordering_expected(value_name, other_name))
    assert_that(findings).described_as("ordering leaked or answered against the line").is_empty()


def test_a_range_answers_by_the_extended_real_line():
    """The value and both bounds crossed with the zoo, so each bound's path meets every awkward number."""
    findings = []
    with _quiet():
        for value_name, low_name, high_name in itertools.product(_ZOO, repeat=3):
            answers = _answers(_RANGE, _ZOO[value_name], _ZOO[low_name], _ZOO[high_name])
            expected = _range_expected(value_name, low_name, high_name)
            findings += _wrong(f"{value_name}|{low_name}|{high_name}", answers, expected)
    assert_that(findings).described_as("a range leaked or answered against the line").is_empty()


def _raising(error: BaseException) -> Callable[..., object]:
    def ask(held: object) -> object:
        raise error

    return ask


_SAMPLE_SHOWN = "<Decimal('1.5')> (decimal.Decimal)"


@pytest.mark.parametrize("key", list(_REFUSALS))
def test_every_listed_refusal_is_one_whole_sentence_of_one_type(key):
    """Each entry accepts its sentence, and refuses it from another exception type, with more after it, or cut."""
    kind, text, _ = _REFUSALS[key]
    sentence = text.replace(_SHOWN, _SAMPLE_SHOWN)
    other_kind = ValueError if kind is TypeError else TypeError
    assert_that(_outcome(_raising(kind(sentence)))).is_equal_to(f"refused:{key}")
    assert_that(_outcome(_raising(other_kind(sentence)))).is_equal_to(f"leak:{other_kind.__name__}")
    assert_that(_outcome(_raising(kind(f"{sentence}!")))).is_equal_to(f"leak:{kind.__name__}")
    assert_that(_outcome(_raising(kind(sentence[1:])))).is_equal_to(f"leak:{kind.__name__}")
    assert_that(_outcome(_raising(kind(f"{sentence}\nand a second line")))).is_equal_to(f"leak:{kind.__name__}")


@pytest.mark.parametrize("key", list(_REFUSALS))
def test_every_listed_refusal_is_said_by_the_library(key):
    kind, text, said = _REFUSALS[key]
    assert_that(_outcome(lambda held: said())).is_equal_to(f"refused:{key}")
    with pytest.raises(kind) as raised:
        said()
    assert_that(raised.value).is_type_of(kind)
    assert_that(re.fullmatch(text, str(raised.value))).is_not_none()


@pytest.mark.parametrize(
    "shown",
    ["<> (int)", "<1> (.int)", "<1> (int.)", "<1> (numpy..int64)", "<<1>> (int)", "<1> (int) (int)", "<1>(int)"],
)
def test_the_shown_value_is_one_repr_and_one_qualified_type_name(shown):
    sentence = f"given other arg must be a number other than a bool, but was {shown}"
    assert_that(_outcome(_raising(TypeError(sentence)))).is_equal_to("leak:TypeError")


_BUILDER = type(assert_that(0)).__name__


@pytest.mark.parametrize(
    ("ask", "matcher", "expected"),
    [
        (_raising(TypeError("'<' not supported between instances")), False, "leak:TypeError"),
        (_raising(OverflowError("int too large")), False, "leak:OverflowError"),
        (_raising(decimal.InvalidOperation()), False, "leak:InvalidOperation"),
        (_raising(AssertionError("an internal assert")), False, "leak:AssertionError"),
        (lambda held: held(1).is_equal_to(2), False, "failed"),
        (lambda held: held(1).is_equal_to(1), False, "held"),
        (lambda held: held(1).is_equal_to(1) and assert_that(1), False, f"leak:{_BUILDER}"),
        (lambda held: [held(2), held(1).is_equal_to(1)][0], False, f"leak:{_BUILDER}"),
        (lambda held: (held(1), held(2).is_equal_to(2))[1], False, f"leak:{_BUILDER}"),
        (lambda held: assert_that(1).is_equal_to(1), False, f"leak:{_BUILDER}"),
        (lambda held: True, False, "leak:bool"),
        (lambda held: False, False, "leak:bool"),
        (lambda held: None, False, "leak:NoneType"),
        (lambda held: True, True, "held"),
        (lambda held: False, True, "failed"),
        (lambda held: 1, True, "leak:int"),
        (lambda held: None, True, "leak:NoneType"),
        (lambda held: held(1).is_equal_to(1), True, f"leak:{_BUILDER}"),
        (lambda held: held(1).is_equal_to(2), True, "leak:AssertionFailure"),
        (_raising(AssertionError("an internal assert")), True, "leak:AssertionError"),
    ],
)
def test_the_classifier_calls_anything_but_the_spellings_own_verdict_or_a_listed_refusal_a_leak(ask, matcher, expected):
    """The gate is only as good as this: an assertion answers with its builder or its failure, a matcher a bool."""
    assert_that(_outcome(ask, matcher=matcher)).is_equal_to(expected)
