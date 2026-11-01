"""Every assertion and its negation, held to being one question asked twice.

A pair is two assertions meant as complements: `is_X` and `is_not_X`, `contains_X` and
`does_not_contain_X`, `has_X` and `does_not_have_X`, `matches` and `does_not_match`, and the few that are
complements by meaning rather than by name, such as `is_true` and `is_false`.  Duality, asked of one
value and one set of arguments, is three things:

1. Complement.  Exactly one of the two passes, or both refuse alike.  A refusal (an `Exception` raised
   that is not an `AssertionError`) is not a verdict, so it cannot come from one side only: a value the
   positive cannot examine, the negative cannot examine either.  Two refusals are alike when they carry
   the same message and derive from the same builtin class.  Which class below that is raised is not
   public API, so an asymmetry there is outside this property.
2. `not_`.  `assert_that(v).not_.name(*args)` fails where `name(*args)` passes, passes where it fails,
   and refuses alike where it refuses.
3. `check()`.  `assert_that(v).check().name(*args)` never raises an `AssertionError`.  Its outcome's
   `passed` is the hard verdict, and a refusal is raised unchanged.  `check().not_` answers what `not_`
   answers.

A failure on something the question presupposes is not a verdict either.  A pair whose value can miss its
prerequisite declares it and says why in `_PREREQUISITES`: the group assertions ask what a caught group
holds, and a caught exception that is not a group answers neither that nor its negation.  There both
members fail on every surface with one message, and `not_` delivers the hard failure as it stands.  Only
arguments refused alike on a value meeting the prerequisite are refused there instead.

(2) and (3) are asked of both members of every pair, including the calls only one member takes.  (1) is
asked where both take the call.  A pair that is a complement only in part says which part in
`_RESTRICTED`, and what still holds outside that part is asserted rather than skipped.

The pairs named as negations are read off the builder with the vocabulary `tests/test_api_vocabulary.py`
gates, so a new negation is either tested here or says why it is not.  That covers naming patterns, not
every semantic opposite: `_BY_MEANING` lists the complements found by reading the surface, and an opposite
that no naming rule reaches and nobody listed is held to nothing here.
"""

from __future__ import annotations

import dataclasses
import datetime
import decimal
import fractions
import math
import os
import pathlib
import re
import types
import warnings
from typing import TYPE_CHECKING, Any

import pytest
from hypothesis import Phase, example, find, given, settings
from hypothesis import strategies as st

from assertpy import AssertionFailure, _satisfies, assert_that, match
from assertpy._engine._equality import comparable_fields
from tests import chain_model as model
from tests.chain_surfaces import Answer, run_check, run_hard
from tests.group_compat import BaseExceptionGroup, ExceptionGroup, needs_groups
from tests.test_api_vocabulary import _NEGATION, _public_names
from tests.test_property_based import (
    _MIXED,
    _drift_atoms,
    _drifted_pair,
    _Inner,
    _json_atoms,
    _outers,
    _RefusingDict,
    _RefusingList,
    _RefusingSet,
    _RefusingStr,
    _Split,
    _Twin,
    _values_with_nan,
)
from tests.test_property_based import _pairs as _namedtuples

if TYPE_CHECKING:
    from collections.abc import Callable

_HERE = pathlib.Path(__file__).resolve()


@pytest.fixture(autouse=True, scope="module")
def _as_shipped():
    """The vacuous guard off, as it ships.

    With it on, `is_equal_to` whose `ignore` leaves nothing to compare warns, and `not_` does not, on
    purpose: its pass is the failure the caller gets.  Under `filterwarnings = error` that warning reads
    here as a refusal from one surface only, which is the guard's design and not a verdict.
    """
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(_satisfies, "_VACUOUS_GUARD", False)
        yield


class _LegacySequence:
    """Indexed from zero until `IndexError` and nothing else, which `in` and `iter()` both still walk."""

    def __getitem__(self, index: int) -> int:
        if index < 2:
            return index
        raise IndexError(index)

    def __repr__(self) -> str:
        return "_LegacySequence()"


class _NoTruth:
    def __bool__(self) -> bool:
        raise RuntimeError("no truth value")

    def __repr__(self) -> str:
        return "_NoTruth()"


class _Summoned:
    def __call__(self) -> int:
        return 1

    def __repr__(self) -> str:
        return "_Summoned()"


@dataclasses.dataclass(frozen=True)
class _Raiser:
    """A callable that warns with *warning*, then raises *error*, and returns when neither is set."""

    error: Exception | None = None
    warning: type[Warning] | None = None

    def __call__(self) -> int:
        if self.warning is not None:
            warnings.warn("drawn", self.warning, stacklevel=2)
        if self.error is not None:
            raise self.error
        return 1


def _refuses_two(item: object) -> bool:
    if item == 2:
        raise ValueError("two")
    return False


@dataclasses.dataclass(frozen=True)
class Case:
    """One call of a pair: the positive's name, the value, and what both members are handed."""

    pair: str
    value: Any
    args: tuple[Any, ...] = ()
    options: tuple[tuple[str, Any], ...] = ()

    @property
    def kwargs(self) -> dict[str, Any]:
        return dict(self.options)


@dataclasses.dataclass(frozen=True)
class _Question:
    """One member asked as a call: the value, the steps that set the call up, and the step that decides."""

    value: Any
    name: str
    args: tuple[Any, ...]
    kwargs: dict[str, Any]
    setup: tuple[tuple[str, tuple[Any, ...]], ...] = ()

    def __str__(self) -> str:
        steps = "".join(f".{name}{args}" for name, args in self.setup)
        return f"assert_that({self.value!r}){steps}.{self.name}{self.args}{self.kwargs or ''}"


_FLIP = {"held": "failed", "failed": "held"}
_SURFACES = (("hard", run_hard, False), ("not_", run_hard, True), ("check", run_check, False))


def _kind(answer: Answer) -> str:
    """`held`, `failed`, or `refused:` and the builtin class the refusal derives from."""
    if answer.status != "refused":
        return answer.status
    builtin = next(kind for kind in type(answer.raised).__mro__ if kind.__module__ == "builtins")
    return f"refused:{builtin.__name__}"


def _reduced(answer: Answer) -> str:
    """What two answers to one question must agree on: the kind, and for a refusal its message as well."""
    return f"{_kind(answer)}: {answer.text}" if answer.status == "refused" else answer.status


def _asked(question: _Question, runner: Callable[..., Answer], negated: bool) -> Answer:
    try:
        builder = assert_that(question.value)
        for name, args in question.setup:
            builder = getattr(builder, name)(*args)
    except Exception as refusal:  # a setup step refusing refuses the question on every surface
        return Answer("refused", error=type(refusal).__name__, text=str(refusal), raised=refusal)
    return runner(builder, question.name, question.args, question.kwargs, negated)


def _answers(question: _Question) -> dict[str, Answer]:
    """The question on every surface: hard, `not_`, `check()` and `check().not_`."""
    found = {surface: _asked(question, runner, negated) for surface, runner, negated in _SURFACES}
    found["check.not_"] = _asked(question, run_check, True)
    return found


def _direct(name: str, case: Case) -> _Question:
    return _Question(case.value, name, case.args, case.kwargs)


def _through_the_call(name: str, case: Case) -> _Question:
    """`raises(E)` and `warns(W)` only configure: `when_called_with()` is where either reaches a verdict."""
    return _Question(case.value, "when_called_with", (), {}, setup=((name, case.args),))


def _of_the_caught(name: str, case: Case) -> _Question:
    return _Question(
        _Raiser(case.value), name, case.args, {}, setup=(("raises", (BaseException,)), ("when_called_with", ()))
    )


def _by_argument(case: Case) -> list[Case]:
    return [dataclasses.replace(case, args=(item,), options=()) for item in case.args]


def _by_entry(case: Case) -> list[Case]:
    return _by_argument(case) + [dataclasses.replace(case, args=(), options=(option,)) for option in case.options]


def _never(case: Case) -> bool:
    return False


def _is_nan(value: object) -> bool:
    if isinstance(value, float):
        return math.isnan(value)
    return isinstance(value, decimal.Decimal) and decimal.Decimal.is_nan(value)


def _unordered(case: Case) -> bool:
    """A NaN on either side, or two sets neither of which holds the other: `<` and `>=` are both false there."""
    left, right = case.value, case.args[0]
    if _is_nan(left) or _is_nan(right):
        return True
    sets = (set, frozenset)
    return isinstance(left, sets) and isinstance(right, sets) and not (left <= right or right <= left)


def _is_a_group(case: Case) -> bool:
    return BaseExceptionGroup is not None and isinstance(case.value, BaseExceptionGroup)


def _in_a_group(case: Case) -> Case:
    return dataclasses.replace(case, value=ExceptionGroup("g", [case.value]))


def _without_options(case: Case) -> bool:
    return not case.options


def _always(case: Case) -> bool:
    return True


@dataclasses.dataclass(frozen=True)
class _Prerequisite:
    """What a pair presupposes of its value: whether a case meets it, and that case made to meet it."""

    holds: Callable[[Case], bool]
    meet: Callable[[Case], Case]


_NOTHING_PRESUPPOSED = _Prerequisite(_always, model.identity)


@dataclasses.dataclass(frozen=True)
class _Pair:
    """Two assertions meant as complements, and how a case of them is drawn and asked.

    Attributes:
        positive: The member that asserts the relation.
        negative: The member that asserts its absence.
        subjects: Draws the value.
        arguments: Draws the arguments for a value, as the chain model's makers do.
        whole: Whether the complement holds for any number of arguments, rather than for one at a time.
        ask: Turns a member's name and a case into the call that reaches the verdict.
        parts: Splits a case of several arguments into cases of one.
        both_fail: Where both members fail by design, as `_RESTRICTED` says.
        shared: Whether the negative takes the case at all.
        also: Whole cases drawn together, for a pair whose value and argument are worth drawing as one.
        prerequisite: What the pair presupposes of its value; a case missing it fails on every surface of
            both members with one message, as the module docstring says.
    """

    positive: str
    negative: str
    subjects: st.SearchStrategy[Any]
    arguments: Callable[[Any, model.Draw], model.Arguments]
    whole: bool = True
    ask: Callable[[str, Case], _Question] = _direct
    parts: Callable[[Case], list[Case]] = _by_argument
    both_fail: Callable[[Case], bool] = _never
    shared: Callable[[Case], bool] = _always
    also: st.SearchStrategy[tuple[Any, Any]] | None = None
    prerequisite: _Prerequisite = _NOTHING_PRESUPPOSED

    def cases(self) -> st.SearchStrategy[Case]:
        @st.composite
        def drawn(draw: st.DrawFn) -> Case:
            value = draw(self.subjects)
            args, kwargs = self.arguments(value, draw)
            return Case(self.positive, value, tuple(args), tuple(kwargs.items()))

        if self.also is None:
            return drawn()
        return st.one_of(drawn(), self.also.map(lambda both: Case(self.positive, both[0], (both[1],))))


_SPECIAL_NUMBERS = st.sampled_from(
    [
        -0.0,
        math.nan,
        math.inf,
        -math.inf,
        5e-324,
        2**64,
        10**400,
        decimal.Decimal("-0"),
        decimal.Decimal("NaN"),
        decimal.Decimal("sNaN"),
        decimal.Decimal("Infinity"),
        fractions.Fraction(1, 3),
        complex(0, 0),
        complex(math.nan, 0),
        True,
        False,
    ]
)
_NUMBERS = st.one_of(st.integers(), st.floats(), st.fractions(), st.decimals(), _SPECIAL_NUMBERS)
_MOMENTS = st.one_of(
    model.DATETIMES,
    st.dates(min_value=datetime.date(2025, 12, 31), max_value=datetime.date(2026, 1, 3)),
    st.just(datetime.datetime(2026, 1, 2, tzinfo=datetime.timezone.utc)),
)
_SETS = st.frozensets(st.integers(0, 2), max_size=2) | st.sets(st.integers(0, 2), max_size=2)
_OPERANDS = st.one_of(_NUMBERS, _MIXED, _MOMENTS, _SETS)

_HOSTILE = st.sampled_from(
    [
        _Split(0),
        _Twin(0),
        _LegacySequence(),
        _NoTruth(),
        _Summoned(),
        object(),
        int,
        len,
        _RefusingDict(a=1),
        _RefusingList([1]),
        _RefusingSet({1}),
        _RefusingStr("text"),
        ValueError("x"),
        range(3),
        range(0),
        frozenset({1}),
        bytearray(b"ab"),
        types.MappingProxyType({"a": 1}),
        [math.nan, math.nan],
        [float("nan"), float("nan")],
        [[1], [1]],
        [1, True, 1.0],
    ]
)
_ANYTHING = st.one_of(
    *model.KINDS.values(), _MIXED, _HOSTILE, _values_with_nan, st.lists(_drift_atoms, max_size=6), _outers, _namedtuples
)

_PLAIN = frozenset({type(None), bool, int, float, str, bytes, list, tuple, set, dict, datetime.datetime})
"""The types the chain model's argument makers read without asking the value anything it may refuse."""
_ITEMS = st.one_of(model.PLAIN, st.sampled_from([math.nan, "t", b"a", [1], {"a": 1}]))
_ITEM_MATCHERS = st.sampled_from(
    [match.greater_than(0), match.is_none(), match.equal_to("a"), match.matches_regex("a")]
)


def _how_many(draw: model.Draw) -> int:
    return draw(st.sampled_from([1, 1, 1, 1, 2, 3, 0]))


def _no_args(value: object, draw: model.Draw) -> model.Arguments:
    return (), {}


def _an_other(value: object, draw: model.Draw) -> model.Arguments:
    if type(value) in _PLAIN and draw(st.booleans()):
        return model.an_other(value, draw)
    return (draw(st.one_of(st.just(value), _ANYTHING)),), {}


_EQUALITY_OPTIONS = st.sampled_from(
    [
        {},
        {"ignore": "a"},
        {"ignore": ["a", "b"]},
        {"tolerance": 0.5},
        {"ignore_null": True},
        {"strict_types": True},
    ]
)


def _fields_of(value: object) -> dict | None:
    return value if isinstance(value, dict) else comparable_fields(value)


def _present_includes(value: object) -> list:
    """Include specs the compared value holds: its keys or fields, one level deeper as a path, and for a
    sequence the keys every element holds, which is how the comparison walks each of those shapes."""
    if isinstance(value, (list, tuple)) and value and all(_fields_of(item) is not None for item in value):
        held = set.intersection(*(set(_fields_of(item)) for item in value))
        return sorted(held, key=repr)
    fields = _fields_of(value)
    if fields is None:
        return []
    found: list = list(fields)
    # by key and item, which a refusing mapping in the pool leaves alone where its own `items()` raises
    for key in list(fields):
        found.extend((key, deeper) for deeper in _fields_of(fields[key]) or ())
    return sorted(found, key=repr)


def _an_other_with_options(value: object, draw: model.Draw) -> model.Arguments:
    """An `include=` naming only what the compared value holds, over mappings, fields, paths and elements.

    One naming a key the value lacks is a prerequisite that fails on every surface, held by
    `tests/test_prerequisites.py`.  The keys come from the reading the comparison itself makes, so a key
    drawn here is one it finds, and a duality defect on any of those shapes stays in reach.
    """
    args, _ = _an_other(value, draw)
    options = draw(st.one_of(st.just({}), _EQUALITY_OPTIONS))
    present = _present_includes(value)
    if not options and present and draw(st.booleans()):
        options = {"include": draw(st.sampled_from(present))}
        if draw(st.booleans()):
            args = (value,)
    return args, options


def _items(value: object, draw: model.Draw) -> model.Arguments:
    """Members half the time where the value is plain enough to list, strangers and matchers otherwise."""
    found = []
    for _ in range(_how_many(draw)):
        if draw(st.integers(0, 5)) == 0:
            found.append(draw(_ITEM_MATCHERS))
        elif type(value) in _PLAIN:
            found.append(model.an_item(value, draw))
        else:
            found.append(draw(_ITEMS))
    return tuple(found), {}


def _candidates(value: object, draw: model.Draw) -> model.Arguments:
    if draw(st.integers(0, 9)) == 0:
        return (), {}
    return model.some_candidates(value, draw)


def _a_stranger(value: object, draw: model.Draw) -> model.Arguments:
    return (draw(_ITEMS),), {}


def _keys(value: object, draw: model.Draw) -> model.Arguments:
    one = model.a_key if isinstance(value, dict) else _a_stranger
    return tuple(one(value, draw)[0][0] for _ in range(_how_many(draw))), {}


def _dict_values(value: object, draw: model.Draw) -> model.Arguments:
    one = model.a_dict_value if isinstance(value, dict) else _a_stranger
    return tuple(one(value, draw)[0][0] for _ in range(_how_many(draw))), {}


def _a_stranger_entry(draw: model.Draw) -> model.Arguments:
    return ({"a": draw(model.SMALL_INT)},), {}


def _entries(value: object, draw: model.Draw) -> model.Arguments:
    """Entries, each a one-key dict or a keyword, and now and then a dict of two keys or not a dict at all."""
    args, kwargs = [], {}
    for _ in range(_how_many(draw)):
        (entry,), _ = model.an_entry(value, draw) if isinstance(value, dict) else _a_stranger_entry(draw)
        [(key, held)] = entry.items()
        shape = draw(st.integers(0, 7))
        if shape == 0 and isinstance(key, str) and key.isidentifier():
            kwargs[key] = held
        elif shape == 1:
            args.append({**entry, "zz": 1})
        elif shape == 2:
            args.append(draw(_ITEMS))
        else:
            args.append(entry)
    return tuple(args), kwargs


def _strings(value: object, draw: model.Draw) -> model.Arguments:
    """Parts of the text where there is text, and strangers, including one that is not a string."""
    text = value if type(value) is str else ""
    found = []
    for _ in range(_how_many(draw)):
        if text and draw(st.booleans()):
            start = draw(st.integers(0, len(text) - 1))
            found.append(text[start : start + draw(st.integers(1, 2))])
        else:
            found.append(draw(st.sampled_from(["zz", "", "a", "B", 1])))
    return tuple(found), {}


def _patterns(value: object, draw: model.Draw) -> model.Arguments:
    if draw(st.booleans()):
        return model.a_pattern(value, draw)
    return (draw(st.sampled_from(["(", "", "(?i)A", re.compile("a"), re.compile(b"a"), b"a", 1, None])),), {}


def _predicates(value: object, draw: model.Draw) -> model.Arguments:
    if draw(st.booleans()):
        return model.a_predicate(value, draw)
    return (draw(st.one_of(_ITEM_MATCHERS, st.sampled_from([_refuses_two, 1, None]))),), {}


_BOUNDS = st.one_of(model.SMALL_INT, model.FLOATS, _OPERANDS)


_STEPS = st.sampled_from([0, 1, -1, 0.5, -0.5, 1.5, -1.5, 2])


def _near(value: Any, unit: Any, draw: model.Draw) -> Any:
    """*value* moved by a drawn multiple of *unit*, for the relations whose answer turns on a boundary.

    An int past the float range moved by half a unit has no float to land on, and stays where it is.
    """
    step = draw(_STEPS)
    try:
        return value + step * unit
    except OverflowError:
        return value


def _bounds(value: object, draw: model.Draw) -> model.Arguments:
    if type(value) in (int, float, datetime.datetime) and draw(st.booleans()):
        unit = datetime.timedelta(hours=1) if type(value) is datetime.datetime else 1
        return (_near(value, unit, draw), _near(value, unit, draw)), {}
    if isinstance(value, (int, float)) and draw(st.booleans()):
        return model.a_range(value, draw)
    return (draw(_BOUNDS), draw(_BOUNDS)), {}


_TOLERANCES = st.sampled_from(
    [
        0,
        0.5,
        1,
        2.5,
        -1,
        math.nan,
        math.inf,
        True,
        decimal.Decimal("0.1"),
        fractions.Fraction(1, 2),
        "1",
        None,
        datetime.timedelta(0),
        datetime.timedelta(days=1),
        datetime.timedelta(days=-1),
    ]
)


def _closeness(value: object, draw: model.Draw) -> model.Arguments:
    tolerance = draw(_TOLERANCES)
    numbers = type(value) in (int, float) and type(tolerance) in (int, float)
    moments = type(value) is datetime.datetime and type(tolerance) is datetime.timedelta
    if (numbers or moments) and draw(st.booleans()):
        return (_near(value, tolerance, draw), tolerance), {}
    if isinstance(value, (int, float)) and draw(st.booleans()):
        return model.a_tolerance(value, draw)
    return (draw(st.one_of(st.just(value), _BOUNDS)), tolerance), {}


def _an_operand(value: object, draw: model.Draw) -> model.Arguments:
    return (draw(st.one_of(st.just(value), _OPERANDS)),), {}


def _a_moment(value: object, draw: model.Draw) -> model.Arguments:
    return (draw(st.one_of(st.just(value), _MOMENTS, _MIXED)),), {}


_JSON = st.recursive(
    _json_atoms,
    lambda children: st.lists(children, max_size=3) | st.dictionaries(st.sampled_from("abc"), children, max_size=3),
    max_leaves=8,
)
_JSON_PATHS = st.sampled_from(["$", "$.a", "$.a.b", "$.b", "$..a", "$[0]", "$[1]", "$[*]", "$.a[0]", "$[", "", "$.", 1])


def _a_json_path(value: object, draw: model.Draw) -> model.Arguments:
    return (draw(_JSON_PATHS),), {}


_ERROR_TYPES = [ValueError, KeyError, TypeError, OSError, LookupError, Exception, BaseException, int, 1]
_GROUP_TYPES = [] if ExceptionGroup is None else [ExceptionGroup, BaseExceptionGroup]
_ERRORS = st.sampled_from([ValueError, KeyError, TypeError, OSError]).map(lambda kind: kind("drawn"))
"""Built fresh per draw: raising one instance again prepends to its traceback, which would grow for the whole run."""
_CAUGHT = (
    _ERRORS
    if ExceptionGroup is None
    else st.recursive(
        _ERRORS,
        lambda children: st.lists(children, min_size=1, max_size=3).map(lambda found: ExceptionGroup("g", found)),
    )
)


def _leaves(error: BaseException) -> list[BaseException]:
    if BaseExceptionGroup is not None and isinstance(error, BaseExceptionGroup):
        return [leaf for inner in error.exceptions for leaf in _leaves(inner)]
    return [error]


def _error_types(value: BaseException, draw: model.Draw) -> model.Arguments:
    """Types the caught group holds half the time, so both verdicts are reached, and any type otherwise."""
    held = st.sampled_from([type(leaf) for leaf in _leaves(value)])
    anything = st.sampled_from(_ERROR_TYPES + _GROUP_TYPES)
    return tuple(draw(st.one_of(held, anything)) for _ in range(_how_many(draw))), {}


def _an_expected_error(value: _Raiser, draw: model.Draw) -> model.Arguments:
    if value.error is not None and draw(st.booleans()):
        return (draw(st.sampled_from(type(value.error).__mro__[:-1])),), {}
    return (draw(st.sampled_from(_ERROR_TYPES + _GROUP_TYPES)),), {}


_CATEGORIES = [UserWarning, DeprecationWarning, RuntimeWarning, Warning]


def _an_expected_warning(value: _Raiser, draw: model.Draw) -> model.Arguments:
    if value.warning is not None and draw(st.booleans()):
        return (draw(st.sampled_from([kind for kind in value.warning.__mro__ if issubclass(kind, Warning)])),), {}
    return (draw(st.sampled_from([*_CATEGORIES, ValueError, 1])),), {}


_CALLS = st.builds(_Raiser, error=st.none() | _ERRORS)
_WARNING_CALLS = st.builds(
    _Raiser, error=st.none() | st.builds(ValueError, st.just("drawn")), warning=st.none() | st.sampled_from(_CATEGORIES)
)
_PATHS = st.sampled_from([_HERE, _HERE.parent, _HERE.parent / "no such file"]).flatmap(
    lambda path: st.sampled_from([path, str(path), os.fsencode(path)])
)


_TEXTS = st.one_of(model.TEXT, st.text(alphabet="abAB1 \n", max_size=6), _ANYTHING)


_BY_NAME = [
    _Pair(
        "is_equal_to",
        "is_not_equal_to",
        _ANYTHING,
        _an_other_with_options,
        shared=_without_options,
        also=st.one_of(
            _drifted_pair(),
            st.tuples(_outers, _outers),
            st.tuples(_values_with_nan, _values_with_nan),
            st.tuples(st.builds(_Split, st.integers(0, 1)), st.builds(_Split, st.integers(0, 1))),
        ),
    ),
    _Pair("is_same_as", "is_not_same_as", _ANYTHING, _an_other),
    _Pair("is_none", "is_not_none", _ANYTHING, _no_args),
    _Pair("is_callable", "is_not_callable", _ANYTHING, _no_args),
    _Pair("is_iterable", "is_not_iterable", _ANYTHING, _no_args),
    _Pair("is_empty", "is_not_empty", _ANYTHING, _no_args),
    _Pair("contains_duplicates", "does_not_contain_duplicates", _ANYTHING, _no_args),
    _Pair("is_zero", "is_not_zero", st.one_of(_NUMBERS, _ANYTHING), _no_args),
    _Pair("is_nan", "is_not_nan", st.one_of(_NUMBERS, _ANYTHING), _no_args),
    _Pair("is_inf", "is_not_inf", st.one_of(_NUMBERS, _ANYTHING), _no_args),
    _Pair("is_between", "is_not_between", _OPERANDS, _bounds),
    _Pair("is_close_to", "is_not_close_to", _OPERANDS, _closeness),
    _Pair("is_in", "is_not_in", _ANYTHING, _candidates),
    _Pair("contains", "does_not_contain", _ANYTHING, _items, whole=False),
    _Pair("contains_key", "does_not_contain_key", _ANYTHING, _keys, whole=False),
    _Pair("contains_value", "does_not_contain_value", _ANYTHING, _dict_values, whole=False),
    _Pair("contains_entry", "does_not_contain_entry", _ANYTHING, _entries, whole=False, parts=_by_entry),
    _Pair("matches", "does_not_match", _TEXTS, _patterns),
    _Pair("has_json_path", "does_not_have_json_path", st.one_of(_JSON, _ANYTHING), _a_json_path),
    _Pair("exists", "does_not_exist", st.one_of(_PATHS, _ANYTHING), _no_args),
    _Pair(
        "contains_error",
        "does_not_contain_error",
        _CAUGHT,
        _error_types,
        whole=False,
        ask=_of_the_caught,
        prerequisite=_Prerequisite(_is_a_group, _in_a_group),
    ),
    _Pair("raises", "does_not_raise", _CALLS, _an_expected_error, ask=_through_the_call),
    _Pair("warns", "does_not_warn", _WARNING_CALLS, _an_expected_warning, ask=_through_the_call),
]

_BY_MEANING = [
    _Pair("is_true", "is_false", st.one_of(_ANYTHING, st.just(_NoTruth())), _no_args),
    _Pair("is_even", "is_odd", st.one_of(st.integers(), _NUMBERS, _ANYTHING), _no_args),
    _Pair("contains_any_of", "contains_none_of", _TEXTS, _strings),
    _Pair("any_satisfy", "none_satisfy", _ANYTHING, _predicates),
    _Pair("is_less_than", "is_greater_than_or_equal_to", _OPERANDS, _an_operand, both_fail=_unordered),
    _Pair("is_greater_than", "is_less_than_or_equal_to", _OPERANDS, _an_operand, both_fail=_unordered),
    _Pair("is_before", "is_after_or_equal_to", st.one_of(_MOMENTS, _MIXED), _a_moment),
    _Pair("is_after", "is_before_or_equal_to", st.one_of(_MOMENTS, _MIXED), _a_moment),
]
"""Complements that no naming rule pairs, so they are listed rather than discovered."""

_PAIRS = {pair.positive: pair for pair in _BY_NAME + _BY_MEANING}

_RESTRICTED = {
    "contains": "several items ask all present against none present, so only one item at a time is a complement",
    "contains_key": "several keys ask all present against none present, so only one key at a time is a complement",
    "contains_value": "several values ask all held against none held, so only one value at a time is a complement",
    "contains_entry": "several entries ask all held against none held, so only one entry at a time is a complement",
    "contains_error": "several types ask all held against none held, so only one type at a time is a complement",
    "is_equal_to": "its keyword options have no negated spelling, so they are held to not_ and check() only",
    "raises": "only configures, so the pair is asked through when_called_with(), where its verdict is reached",
    "warns": "only configures, so the pair is asked through when_called_with(), where its verdict is reached",
    "is_less_than": "a partial order: a NaN, or two sets neither of which holds the other, fails both by design",
    "is_greater_than": "a partial order: a NaN, or two sets neither of which holds the other, fails both by design",
}
"""Pairs that are complements only in part, each with the part that is not and why."""

_UNPAIRED = {
    "has_no_none_fields": "the named case of all_fields_satisfy, and no has_none_fields exists for it to negate",
}
"""Names shaped like a negation that negate nothing, each with why."""

_PREREQUISITES = {
    "contains_error": "the group assertions ask what a caught group holds, which a caught exception that is no group"
    " answers neither way, so both fail on every surface",
}
"""Pairs whose value can miss what the question presupposes, each with why."""


def _hold_the_pair(case: Case) -> None:
    """The three parts of duality the module docstring states, asked of one call of one pair."""
    pair = _PAIRS[case.pair]
    met = pair.prerequisite.holds(case)
    positive = pair.ask(pair.positive, case)
    one = _answers(positive)
    _hold_the_surfaces(positive, one, met)
    if not met:
        _hold_a_refusal_before_the_prerequisite(case, pair.positive, one["hard"])
    if not pair.shared(case):
        return
    negative = pair.ask(pair.negative, case)
    other = _answers(negative)
    _hold_the_surfaces(negative, other, met)
    if not met:
        _hold_a_refusal_before_the_prerequisite(case, pair.negative, other["hard"])
    _hold_the_complement(case, positive, negative, one["hard"], other["hard"])


def _hold_a_refusal_before_the_prerequisite(case: Case, name: str, hard: Answer) -> None:
    """A case missing the prerequisite fails, so a refusal there is one its arguments earn on a value meeting it."""
    if hard.status != "refused":
        return
    pair = _PAIRS[case.pair]
    met = pair.prerequisite.meet(case)
    answered = _reduced(_asked(pair.ask(name, met), run_hard, False))
    assert_that(_reduced(hard)).described_as(f"{name} on {case}, against {met}").is_equal_to(answered)


def _hold_the_surfaces(question: _Question, answers: dict[str, Answer], met: bool) -> None:
    """`not_` inverts a verdict and keeps a refusal or an unmet prerequisite, and `check()` reports the hard call."""
    hard = answers["hard"]
    assert_that(hard.status).described_as(f"{question} took an illegal shape").is_in("held", "failed", "refused")
    if not met and hard.status != "refused":
        found = {surface: (answer.status, answer.text) for surface, answer in answers.items()}
        expected = dict.fromkeys(answers, ("failed", hard.text))
        assert_that(found).described_as(f"{question} on an unmet prerequisite").is_equal_to(expected)
        return
    reduced = {surface: _reduced(answer) for surface, answer in answers.items()}
    flipped = _FLIP.get(reduced["hard"], reduced["hard"])
    assert_that(reduced["not_"]).described_as(f"not_ on {question}").is_equal_to(flipped)
    assert_that(reduced["check"]).described_as(f"check() on {question}").is_equal_to(reduced["hard"])
    assert_that(reduced["check.not_"]).described_as(f"check().not_ on {question}").is_equal_to(reduced["not_"])


def _hold_the_complement(case: Case, positive: _Question, negative: _Question, one: Answer, other: Answer) -> None:
    pair = _PAIRS[case.pair]
    said = f"{positive} said {_reduced(one)}, {negative} said {_reduced(other)}"
    if "refused" in (one.status, other.status):
        assert_that(_reduced(other)).described_as(f"refusals that differ: {said}").is_equal_to(_reduced(one))
    elif not pair.prerequisite.holds(case):
        assert_that(other.text).described_as(f"one prerequisite, two messages: {said}").is_equal_to(one.text)
    elif pair.both_fail(case):
        assert_that((one.status, other.status)).described_as(f"both fail by design: {said}").is_equal_to(
            ("failed", "failed")
        )
    elif pair.whole or len(case.args) + len(case.options) == 1:
        assert_that({one.status, other.status}).described_as(f"not complements: {said}").is_equal_to({"held", "failed"})
    else:
        _hold_each_argument(case, one.status, other.status)


def _hold_each_argument(case: Case, one: str, other: str) -> None:
    """Several arguments: each member holds exactly when it holds for every argument alone, so never both."""
    pair = _PAIRS[case.pair]
    assert_that((one, other)).described_as(f"{case} held for both members").is_not_equal_to(("held", "held"))
    for name, whole in ((pair.positive, one), (pair.negative, other)):
        parts = [_asked(pair.ask(name, part), run_hard, False).status for part in pair.parts(case)]
        assert_that(parts).described_as(f"{name} on {case} refused a part and not the whole").does_not_contain(
            "refused"
        )
        expected = "held" if all(part == "held" for part in parts) else "failed"
        assert_that(whole).described_as(f"{name} on {case} against its parts {parts}").is_equal_to(expected)


_CASES = st.one_of([pair.cases() for pair in _PAIRS.values()])


@settings(deadline=None, max_examples=5000)
@example(case=Case("is_close_to", math.nan, (math.nan, 1)))
@example(case=Case("is_close_to", math.inf, (math.inf, 0)))
@example(case=Case("is_close_to", 5, (5.5, True)))
@example(
    case=Case("is_close_to", datetime.datetime(2026, 1, 1), (datetime.datetime(2026, 1, 2), datetime.timedelta(1)))
)
@example(case=Case("is_between", math.nan, (0, 1)))
@example(case=Case("is_between", 1, (2, 0)))
@example(case=Case("is_zero", -0.0))
@example(case=Case("is_nan", decimal.Decimal("sNaN")))
@example(case=Case("is_in", model.NAN, (model.NAN,)))
@example(case=Case("contains", [model.NAN], (model.NAN,)))
@example(case=Case("contains", {"a": 1}, (1,)))
@example(case=Case("contains", "abc", (1,)))
@example(case=Case("contains", "ab", ("a", "zz")))
@example(case=Case("contains", "a", ("a", 1)))
@example(case=Case("contains_key", {"a": 1}, ("a", {})))
@example(case=Case("contains", _LegacySequence(), (0,)))
@example(case=Case("contains_entry", {"a": 1}, ({"a": 1, "zz": 1},)))
@example(case=Case("contains_entry", {"a": 1}, ({"a": 1},), (("b", 2),)))
@example(case=Case("contains_entry", {"a": 1}, (), (("a", 1),)))
@example(case=Case("contains_any_of", "ab", ("",)))
@example(case=Case("is_same_as", 2**70, (int(str(2**70)),)))
@example(case=Case("is_equal_to", _Split(0), (_Split(1),)))
@example(case=Case("is_equal_to", {"a": 1}, ({"a": 2},), (("ignore", "a"),)))
@example(case=Case("is_equal_to", _Inner(0, "x"), (_Inner(0, "y"),), (("include", "a"),)))
@example(case=Case("is_equal_to", _Inner(0, "x"), (_Inner(1, "x"),), (("include", "a"),)))
@example(case=Case("is_equal_to", {"k": {"x": 1, "y": 2}}, ({"k": {"x": 1, "y": 3}},), (("include", ("k", "x")),)))
@example(case=Case("is_equal_to", {"k": {"x": 1}}, ({"k": {"x": 2}},), (("include", ("k", "x")),)))
@example(case=Case("is_equal_to", [{"a": 1, "b": 2}], ([{"a": 1, "b": 3}],), (("include", "a"),)))
@example(case=Case("is_equal_to", [{"a": 1}], ([{"a": 2}],), (("include", "a"),)))
@example(case=Case("contains_error", ValueError("drawn"), (ValueError,)))
@example(case=Case("contains_error", ValueError("drawn"), (ValueError, KeyError)))
@example(case=Case("contains_error", ValueError("drawn"), (int,)))
@example(case=Case("raises", _Raiser(KeyError("drawn")), (ValueError,)))
@example(case=Case("warns", _Raiser(ValueError("drawn"), UserWarning), (UserWarning,)))
@example(case=Case("any_satisfy", [], (bool,)))
@example(case=Case("any_satisfy", [1, 2], (_refuses_two,)))
@example(case=Case("contains", _RefusingStr("text"), (1, 2)))
@example(case=Case("contains", _RefusingStr("text"), (match.greater_than(0), None)))
@example(case=Case("is_less_than", {1}, (frozenset({2}),)))
@example(case=Case("is_true", _NoTruth()))
@example(case=Case("has_json_path", {"a": 1}, ("$[",)))
@example(case=Case("matches", "a", ("(",)))
@example(case=Case("exists", os.fsencode(_HERE)))
@example(case=Case("is_equal_to", [], (_RefusingList([1]),)))
@example(case=Case("is_equal_to", _RefusingList([1]), ([1, 2],)))
@example(case=Case("is_equal_to", ["x" * 70], (_RefusingList([1]),)))
@example(case=Case("is_equal_to", _RefusingSet({1}), (set(),)))
@example(case=Case("is_equal_to", {2}, (_RefusingSet({1}),)))
@example(case=Case("any_satisfy", _RefusingStr("text"), (model.is_positive_number,)))
@example(case=Case("contains", _RefusingStr("text"), ("t", "x")))
@given(case=_CASES)
def test_a_pair_is_one_question_asked_twice(case: Case) -> None:
    _hold_the_pair(case)


def _negations() -> dict[str, str | None]:
    """Every name on the builder shaped like a negation, with the positive it negates, or None for none."""
    names = set(_public_names())
    found: dict[str, str | None] = {}
    for name in sorted(names):
        if not name.startswith(("is_not_", "does_not_", "has_no_")):
            continue
        verb = name.removeprefix("does_not_")
        candidates = [
            prefix + name[len(negated) :] for prefix, negated in _NEGATION.items() if name.startswith(negated)
        ]
        found[name] = next((one for one in [*candidates, f"{verb}s", f"{verb}es"] if one in names), None)
    return found


def test_the_discovery_reads_the_surface_it_is_about() -> None:
    """A discovery that found nothing would pass the gate below whatever the builder offered."""
    assert_that(_negations()).is_length_between(20, 60).contains_entry(
        {"does_not_match": "matches"}, {"does_not_contain": "contains"}, {"does_not_have_json_path": "has_json_path"}
    )


@pytest.mark.parametrize(("negative", "positive"), sorted(_negations().items(), key=str))
def test_every_negation_on_the_builder_is_a_pair_here_or_says_why_not(negative: str, positive: str | None) -> None:
    if positive is None:
        assert_that(_UNPAIRED).described_as(f"{negative!r} negates nothing and says nothing").contains_key(negative)
        return
    assert_that(_PAIRS).described_as(f"{positive!r} and {negative!r} are not held to duality").contains_key(positive)
    assert_that(_PAIRS[positive].negative).is_equal_to(negative)


def test_every_opposite_the_chain_machine_names_is_a_pair_here() -> None:
    """The chain machine keeps its own list of opposites, and the two lists may not drift apart."""
    held = {frozenset((pair.positive, pair.negative)) for pair in _PAIRS.values()}
    named = {frozenset((op.name, op.opposite)) for op in model.OPS if op.opposite is not None}
    assert_that(held).contains(*named)


def test_every_listed_name_is_still_real() -> None:
    """A list of reasons rots the moment a name leaves, so each one is asked for again."""
    names = set(_public_names())
    members = [name for pair in _PAIRS.values() for name in (pair.positive, pair.negative)]
    assert_that(names).contains(*members, *_UNPAIRED)
    assert_that(set(_PAIRS)).contains(*_RESTRICTED, *_PREREQUISITES)
    for reason in [*_RESTRICTED.values(), *_UNPAIRED.values(), *_PREREQUISITES.values()]:
        assert_that(len(reason)).described_as(reason).is_greater_than(40)


def test_every_restriction_is_one_the_pair_declares() -> None:
    """A pair asked in part, or with a prerequisite, is listed with why, and a listed pair is one."""
    partial = {
        name
        for name, pair in _PAIRS.items()
        if not pair.whole or pair.both_fail is not _never or pair.shared is not _always or pair.ask is not _direct
    }
    assert_that(partial).is_equal_to(set(_RESTRICTED))
    declaring = {name for name, pair in _PAIRS.items() if pair.prerequisite is not _NOTHING_PRESUPPOSED}
    assert_that(declaring).is_equal_to(set(_PREREQUISITES))


@pytest.mark.parametrize(
    "positive", [pytest.param(name, marks=needs_groups) if name == "contains_error" else name for name in _PAIRS]
)
@pytest.mark.parametrize("verdict", ["held", "failed"])
def test_every_pair_draws_both_verdicts(positive: str, verdict: str) -> None:
    """A strategy that only ever reached refusals would hold duality without asking it once."""
    pair = _PAIRS[positive]

    def answered(case: Case) -> bool:
        return _asked(pair.ask(pair.positive, case), run_hard, False).status == verdict

    found = find(
        pair.cases(),
        answered,
        settings=settings(max_examples=2000, database=None, derandomize=True, phases=[Phase.generate]),
    )
    assert_that(found.pair).is_equal_to(positive)


_INCLUDE_SHAPES = {
    "a-field": lambda case: not isinstance(case.value, (dict, list, tuple)) and type(_included(case)) is not tuple,
    "a-nested-path": lambda case: type(_included(case)) is tuple,
    "every-element": lambda case: isinstance(case.value, (list, tuple)),
}


def _included(case: Case) -> object:
    return dict(case.options).get("include")


@pytest.mark.parametrize("shape", sorted(_INCLUDE_SHAPES))
def test_every_shape_of_include_is_reached(shape: str) -> None:
    """Drawn from what the value holds, an `include=` still reaches fields, paths and elements.

    Both verdicts on each shape are pinned as examples on the property, since generation reaches a held
    nested path and a failed element rarely enough that asking for them here only measured luck.

    The draw is not the same from one revision to the next either: the engine mixes in the constants of every
    module the process imported, so new code anywhere in the package moves it.  A shape was found on the 174th
    example at one revision and on the 2970th at the next, which a budget of 4000 did not always leave room for.
    """
    found = find(
        _PAIRS["is_equal_to"].cases(),
        lambda case: _included(case) is not None and _INCLUDE_SHAPES[shape](case),
        settings=settings(max_examples=40_000, database=None, derandomize=True, phases=[Phase.generate]),
    )
    assert_that(_included(found)).is_not_none()


_ORACLE = [
    ("held", "is_equal_to", ("failed",)),
    ({"held"}, "is_equal_to", ({"held", "failed"},)),
    (("failed", "failed"), "is_equal_to", (("held", "failed"),)),
    ({"not_": ("failed", "a")}, "is_equal_to", ({"not_": ("failed", "b")},)),
    (("held", "held"), "is_not_equal_to", (("held", "held"),)),
    ("bare-assertion", "is_in", ("held", "failed", "refused")),
    (["held", "refused"], "does_not_contain", ("refused",)),
    (None, "is_not_none", ()),
    (_Summoned(), "is_same_as", (_Summoned(),)),
    ({"held"}, "contains", ("failed",)),
    ({"held": 1}, "contains_key", ("failed",)),
    ({"held": 1}, "contains_entry", ({"held": 2},)),
    ({"held": 1}, "is_length_between", (2, 3)),
    (40, "is_greater_than", (40,)),
]
"""Every assertion this module checks with, each on a shape it checks and an answer it must reject."""


@pytest.mark.parametrize(
    ("value", "name", "args"), _ORACLE, ids=[f"{name}-{index}" for index, (_, name, _) in enumerate(_ORACLE)]
)
def test_the_assertions_this_module_checks_with_can_fail(value: object, name: str, args: tuple[Any, ...]) -> None:
    """The property asserts with the library it examines, so a check that could never fail would pass it silently."""
    with pytest.raises(AssertionFailure):
        getattr(assert_that(value), name)(*args)
