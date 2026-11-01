"""What a value is asked *about* is read off its base type, never off the value.

Twice now the same question was answered by the value: `is_infinite` in one release and `is_nan` in the
next, in two helpers that decide whether a signal is a verdict or a bug in the value.  Both were found
by hand, both from the same subclass trick, so the rule is stated here over the source instead.

The rule is narrow on purpose.  Duck typing is the library's contract and a value answers for almost
everything it is asked.  What it must not answer is the library's *own* question about what kind of
thing it is, because that answer decides which of two error paths a reader is sent down.

When the syntactic rule below fails, do not add the receiver to an allowlist to make it pass.  The set
of names is derived from this interpreter's `Decimal` and `float`, so a domain object of somebody's own
with an `is_integer()` would be stopped by it, and whether that call classifies a number or asks a
question of its own is a judgement nobody can make from the name.  Establish what the call means first.
The two tests under it do not depend on the name at all, which is what makes relaxing the rule safe.
"""

from __future__ import annotations

import ast
import decimal
import pathlib

import pytest

from assertpy import assert_that

_PACKAGE = pathlib.Path(__file__).resolve().parent.parent / "assertpy"


def _own_kind() -> frozenset[str]:
    """Every `is_*` a number answers about itself, read off the base types rather than listed.

    Listed by hand the set was six names and missed `is_normal`, `is_subnormal`, `is_canonical` and
    `float.is_integer`, none of which the package calls today.  Derived, a new one arrives with the
    interpreter rather than with somebody remembering.
    """
    found = set()
    for base in (decimal.Decimal, float):
        found |= {
            name
            for name in dir(base)
            if name.startswith("is_") and callable(getattr(base, name, None)) and not name.startswith("__")
        }
    return frozenset(found)


_OWN_KIND = _own_kind()

# where the base type is the receiver, which is the right spelling
_BASE_TYPES = frozenset({"decimal.Decimal", "Decimal", "float", "int", "complex"})


def _virtual_reads() -> list[str]:
    """Every `<value>.is_nan()` and friends in the package whose receiver is not a base type."""
    found = []
    for source in sorted(_PACKAGE.rglob("*.py")):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr not in _OWN_KIND:
                continue
            receiver = ast.unparse(node.func.value)
            if receiver in _BASE_TYPES:
                continue
            found.append(f"{source.relative_to(_PACKAGE.parent)}:{node.lineno} {ast.unparse(node)}")
    return found


def test_no_value_is_asked_what_kind_of_number_it_is() -> None:
    """Read off the source rather than probed, since the answer only differs for a hostile subclass.

    A docstring beside each call says why it reads the base type; this is what keeps the next one from
    being written the short way and passing every test until somebody writes the subclass.
    """
    assert_that(_virtual_reads()).described_as("predicates read off the value instead of its base type").is_empty()


def test_the_walk_finds_the_calls_it_is_about() -> None:
    """A walk that found nothing would pass the gate above whatever the package did."""
    calls = []
    for source in sorted(_PACKAGE.rglob("*.py")):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        calls += [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in _OWN_KIND
        ]
    assert_that(calls).described_as("calls the gate above is about").is_not_empty()


class _Liar(decimal.Decimal):
    """Not a NaN, and says it is."""

    def is_nan(self) -> bool:
        return True


class _SignallingLiar(_Liar):
    """The same lie, over a comparison of its own that signals."""

    def __lt__(self, other: object) -> bool:
        raise decimal.InvalidOperation("own comparison failed")

    def __gt__(self, other: object) -> bool:
        raise decimal.InvalidOperation("own comparison failed")


class _Hidden(decimal.Decimal):
    """A NaN, and says it is not."""

    def is_nan(self) -> bool:
        return False


def test_a_lie_does_not_absorb_the_value_s_own_signal() -> None:
    with pytest.raises(decimal.InvalidOperation, match="own comparison failed"):
        assert_that(_SignallingLiar(1)).is_less_than(decimal.Decimal(2))


def test_a_lie_does_not_change_a_tolerance_verdict() -> None:
    assert_that(_Liar(1)).is_close_to(decimal.Decimal(1), decimal.Decimal("0.1"))


def test_a_nan_cannot_hide_what_it_is() -> None:
    with pytest.raises(AssertionError) as caught:
        assert_that(_Hidden("NaN")).is_less_than(decimal.Decimal(2))
    assert_that(str(caught.value)).starts_with("Expected <NaN> to be less than <2>")


def test_the_derived_set_covers_the_names_the_package_was_caught_on() -> None:
    """The derivation is the point; these three are what it has to keep containing."""
    assert_that(sorted(_OWN_KIND)).contains("is_nan", "is_infinite", "is_integer")


class _Honest(decimal.Decimal):
    """The same value without the lie, which is what every verdict below is compared against."""


def _recording(value: str = "1") -> tuple[decimal.Decimal, list[str]]:
    """A `Decimal` that notes every predicate anybody asks it about its own kind.

    Stronger than spoofing one name: an alias, a wrapper or a `getattr` reaches the override too, and a
    predicate nobody thought to spoof is recorded rather than missed.  The override delegates to the
    base type, so the verdicts stay the ones the value deserves and only the reading is observed.
    """
    read: list[str] = []

    def watcher(name: str):
        def answer(self, *args, **kwargs):
            read.append(name)
            return getattr(decimal.Decimal, name)(self, *args, **kwargs)

        return answer

    watched = type(
        "_Watched", (decimal.Decimal,), {name: watcher(name) for name in _OWN_KIND if hasattr(decimal.Decimal, name)}
    )
    return watched(value), read


_NUMERIC_CALLS = [
    ("is_close_to", (decimal.Decimal(1), decimal.Decimal("0.1"))),
    ("is_not_close_to", (decimal.Decimal(9), decimal.Decimal("0.1"))),
    ("is_greater_than", (decimal.Decimal(0),)),
    ("is_greater_than_or_equal_to", (decimal.Decimal(1),)),
    ("is_less_than", (decimal.Decimal(2),)),
    ("is_less_than_or_equal_to", (decimal.Decimal(1),)),
    ("is_between", (decimal.Decimal(0), decimal.Decimal(2))),
    ("is_not_between", (decimal.Decimal(5), decimal.Decimal(9))),
    ("is_equal_to", (decimal.Decimal(1),)),
    ("is_not_equal_to", (decimal.Decimal(2),)),
    ("is_positive", ()),
    ("is_not_zero", ()),
]


def _verdict(value: object, name: str, arguments: tuple) -> str:
    try:
        getattr(assert_that(value), name)(*arguments)
    except AssertionError:
        return "failed"
    except BaseException as error:
        return type(error).__name__
    return "passed"


@pytest.mark.parametrize(("name", "arguments"), _NUMERIC_CALLS, ids=lambda one: one if isinstance(one, str) else "")
def test_a_lie_about_its_own_kind_changes_no_verdict(name: str, arguments: tuple) -> None:
    """The sweep the AST rule cannot be: an alias or a wrapper would slip past a syntax check.

    Found this way rather than by hand, `is_close_to` was the second helper reading the value's own
    `is_nan`, and a lie there turned a passing assertion into a failure.
    """
    honest = _verdict(_Honest(1), name, arguments)
    lying = _verdict(_Liar(1), name, arguments)
    assert_that(lying).described_as(f"{name} on a value lying about being a NaN").is_equal_to(honest)


@pytest.mark.parametrize(("name", "arguments"), _NUMERIC_CALLS, ids=lambda one: one if isinstance(one, str) else "")
def test_no_assertion_asks_the_value_what_kind_it_is(name: str, arguments: tuple) -> None:
    """The gate the other two approximate: nothing is spoofed, every reading is simply observed."""
    value, read = _recording()
    _verdict(value, name, arguments)
    assert_that(read).described_as(f"{name} read these off the value").is_empty()


def test_a_conversion_of_their_own_cannot_make_a_number_a_nan() -> None:
    """The surface beyond the predicates, measured rather than argued about.

    `_is_nan` falls back to `math.isnan`, which asks the value to become a float, so a `__float__` of
    their own is the one reading left.  It reaches nothing: a value that is not a number is refused
    before the fallback, and `math.isnan` reads a `float` subclass at the C level rather than through
    its `__float__`.
    """

    class Contrary(float):
        def __float__(self) -> float:
            return float("nan")

    class NotANumber:
        def __float__(self) -> float:
            return float("nan")

    with pytest.raises(AssertionError):
        assert_that(Contrary(1.0)).is_nan()
    assert_that(Contrary(1.0)).is_not_nan()

    with pytest.raises(TypeError, match="val must be a number"):
        assert_that(NotANumber()).is_nan()


def test_the_watcher_records_a_reading_when_there_is_one() -> None:
    """A watcher nobody triggers would report cleanliness for any package at all."""
    value, read = _recording("NaN")
    assert_that(value.is_nan()).is_true()
    assert_that(read).is_equal_to(["is_nan"])
