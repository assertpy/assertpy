"""The abstract model the chain machine walks: value kinds, operations, pivots, and their oracles.

A kind names a family of subjects and the strategy that draws one. An `Op` is a verdict-bearing
assertion together with the kinds it applies to, the arguments drawn for it, its matcher twin and its
opposite. A `Pivot` is a transform together with the plain-Python oracle for the value it hands back.
`python_verdict` is the one oracle for verdicts that shares no code with the library.
"""

from __future__ import annotations

import copy
import datetime
import inspect
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from hypothesis import strategies as st

from assertpy import match
from assertpy.assertpy import AssertionBuilder

Draw = Callable[[st.SearchStrategy[Any]], Any]
Arguments = tuple[tuple[Any, ...], dict[str, Any]]
ArgumentMaker = Callable[[Any, Draw], Arguments]

NAN = float("nan")
INF = float("inf")


def double(item: Any) -> Any:
    return item * 2


def negate(item: Any) -> Any:
    return -item


def is_even_int(item: object) -> bool:
    return isinstance(item, int) and not isinstance(item, bool) and item % 2 == 0


def is_positive_number(item: object) -> bool:
    return isinstance(item, (int, float)) and not isinstance(item, bool) and item > 0


def twice(item: object) -> list[object]:
    return [item, item]


def identity(item: object) -> object:
    return item


def call_me(number: int) -> int:
    """The function kind: raises ValueError below zero, KeyError at zero, returns double above."""
    if number < 0:
        raise ValueError(f"negative {number}")
    if number == 0:
        raise KeyError("zero")
    return number * 2


SMALL_INT = st.integers(-4, 4)
FLOATS = st.one_of(
    st.floats(-4, 4, allow_nan=False, allow_infinity=False),
    st.sampled_from([NAN, INF, -INF, 0.0, -0.0, 0.5, 2.0]),
)
TEXT = st.text(alphabet="abAB1 ", max_size=5)
DATETIMES = st.datetimes(min_value=datetime.datetime(2026, 1, 1), max_value=datetime.datetime(2026, 1, 3))

KINDS: dict[str, st.SearchStrategy[Any]] = {
    "int": SMALL_INT,
    "float": FLOATS,
    "bool": st.booleans(),
    "none": st.none(),
    "str": TEXT,
    "bytes": st.binary(max_size=4),
    "list": st.lists(SMALL_INT, max_size=5),
    "tuple": st.lists(SMALL_INT, max_size=5).map(tuple),
    "set": st.sets(SMALL_INT, max_size=4),
    "dict": st.dictionaries(st.sampled_from("abc"), SMALL_INT, max_size=3),
    "records": st.lists(st.fixed_dictionaries({"id": st.integers(0, 3), "rank": st.integers(0, 3)}), max_size=4),
    "nested": st.lists(st.lists(SMALL_INT, max_size=3), max_size=3),
    "datetime": DATETIMES,
    "function": st.just(call_me),
}

PLAIN = st.one_of(SMALL_INT, FLOATS, TEXT, st.none(), st.booleans(), st.lists(SMALL_INT, max_size=3))

SIZED = {"str", "bytes", "list", "tuple", "set", "dict", "records", "nested"}
NUMERIC = {"int", "float"}
ITERABLE = {"str", "bytes", "list", "tuple", "set", "dict", "records", "nested"}


def kind_of(value: object) -> str:
    """The kind a value belongs to, including the two no strategy draws: an exception and any other object."""
    if value is None:
        return "none"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "str"
    if isinstance(value, bytes):
        return "bytes"
    if isinstance(value, datetime.datetime):
        return "datetime"
    if isinstance(value, BaseException):
        return "exception"
    if isinstance(value, dict):
        return "dict"
    if isinstance(value, tuple):
        return "tuple"
    if isinstance(value, (set, frozenset)):
        return "set"
    if isinstance(value, list):
        if value and all(isinstance(item, dict) for item in value):
            return "records"
        if value and all(isinstance(item, list) for item in value):
            return "nested"
        return "list"
    if callable(value):
        return "function"
    return "object"


def members(value: object) -> list[Any]:
    """What iterating the value yields, which is what the pivots and membership read."""
    try:
        return list(value)  # ty: ignore[invalid-argument-type]  # any iterable the kinds produce
    except TypeError:
        return []


def is_empty_subject(value: object) -> bool:
    """Whether the value is a sized subject with nothing in it, where a matcher's answer is the vacuous one."""
    return kind_of(value) in SIZED and len(value) == 0  # ty: ignore[invalid-argument-type]  # sized kinds only


def an_item(value: object, draw: Draw) -> object:
    """Something a containment check can be asked about: a member half the time, a stranger otherwise."""
    kind = kind_of(value)
    if kind == "str":
        text = str(value)
        if text and draw(st.booleans()):
            start = draw(st.integers(0, len(text) - 1))
            return text[start : start + draw(st.integers(1, 2))]
        return draw(st.sampled_from(["a", "B", "zz", "1"]))
    if kind == "bytes":
        blob = bytes(value)  # ty: ignore[invalid-argument-type]  # kind says bytes
        if blob and draw(st.booleans()):
            return blob[:1]
        return draw(st.sampled_from([b"\x00", b"z"]))
    found = members(value)
    if found and draw(st.booleans()):
        return draw(st.sampled_from(found))
    if kind == "records":
        return {"id": 9, "rank": 9}
    if kind == "nested":
        return [9]
    if kind == "dict":
        return draw(st.sampled_from(["a", "b", "z"]))
    return draw(SMALL_INT)


def some_items(value: object, draw: Draw, low: int = 1, high: int = 3) -> tuple[object, ...]:
    return tuple(an_item(value, draw) for _ in range(draw(st.integers(low, high))))


def no_args(value: object, draw: Draw) -> Arguments:
    return (), {}


def an_other(value: object, draw: Draw) -> Arguments:
    """The value itself, an equal copy, another value of its kind, or a plain stranger."""
    # an exception is re-raised on every replay, so no surface but hard can hold the same instance
    if kind_of(value) == "exception":
        return (draw(PLAIN),), {}
    choice = draw(st.sampled_from(["same", "copy", "same-kind", "plain"]))
    if choice == "same":
        return (value,), {}
    if choice == "copy":
        return ((float(repr(value)) if isinstance(value, float) else copy.deepcopy(value)),), {}
    if choice == "same-kind" and kind_of(value) in KINDS:
        return (draw(KINDS[kind_of(value)]),), {}
    return (draw(PLAIN),), {}


def a_number(value: object, draw: Draw) -> Arguments:
    base = value if isinstance(value, (int, float)) and not isinstance(value, bool) else 0
    return (draw(st.one_of(st.just(base), SMALL_INT, FLOATS)),), {}


def a_range(value: object, draw: Draw) -> Arguments:
    low = draw(st.one_of(SMALL_INT, FLOATS))
    return (low, draw(st.one_of(st.just(low), SMALL_INT, FLOATS))), {}


def a_tolerance(value: object, draw: Draw) -> Arguments:
    (other,), _ = a_number(value, draw)
    return (other, draw(st.sampled_from([0, 0.5, 1, 2.5]))), {}


def a_divisor(value: object, draw: Draw) -> Arguments:
    return (draw(st.sampled_from([1, 2, 3, -2])),), {}


def a_length(value: object, draw: Draw) -> Arguments:
    size = len(value) if kind_of(value) in SIZED else 0  # ty: ignore[invalid-argument-type]  # sized kinds only
    return (draw(st.sampled_from([size, size + 1, max(size - 1, 0), 0])),), {}


def a_length_range(value: object, draw: Draw) -> Arguments:
    size = len(value) if kind_of(value) in SIZED else 0  # ty: ignore[invalid-argument-type]  # sized kinds only
    low = draw(st.integers(0, size + 1))
    return (low, draw(st.integers(low, size + 2))), {}


def many_items(value: object, draw: Draw) -> Arguments:
    return some_items(value, draw), {}


def a_type(value: object, draw: Draw) -> Arguments:
    return (draw(st.sampled_from([int, float, str, bytes, list, tuple, set, dict, bool, object, type(None)])),), {}


def some_candidates(value: object, draw: Draw) -> Arguments:
    keep = draw(st.booleans()) and kind_of(value) != "exception"
    pool = [value, *draw(st.lists(PLAIN, max_size=2))] if keep else draw(st.lists(PLAIN, max_size=3))
    return tuple(pool), {}


def a_prefix(value: object, draw: Draw) -> Arguments:
    if isinstance(value, (list, tuple)):
        return ((value[0] if value and draw(st.booleans()) else draw(SMALL_INT)),), {}
    text = value if isinstance(value, (str, bytes)) else ""
    if text and draw(st.booleans()):
        return (text[: draw(st.integers(1, len(text)))],), {}
    return (draw(st.sampled_from(["a", "B"])) if isinstance(text, str) else b"z",), {}


def a_suffix(value: object, draw: Draw) -> Arguments:
    if isinstance(value, (list, tuple)):
        return ((value[-1] if value and draw(st.booleans()) else draw(SMALL_INT)),), {}
    text = value if isinstance(value, (str, bytes)) else ""
    if text and draw(st.booleans()):
        return (text[-draw(st.integers(1, len(text))) :],), {}
    return (draw(st.sampled_from(["a", "B"])) if isinstance(text, str) else b"z",), {}


def a_pattern(value: object, draw: Draw) -> Arguments:
    return (draw(st.sampled_from(["a", "^a", "b$", "[0-9]", ".*", "^$", "A+"])),), {}


def a_cased(value: object, draw: Draw) -> Arguments:
    text = value if isinstance(value, str) else ""
    return (draw(st.sampled_from([text, text.upper(), text.lower(), "zz"])),), {}


def a_predicate(value: object, draw: Draw) -> Arguments:
    return (draw(st.sampled_from([bool, is_even_int, is_positive_number])),), {}


def a_superset(value: object, draw: Draw) -> Arguments:
    found = members(value)
    extra = draw(st.lists(SMALL_INT, max_size=2))
    kept = found if draw(st.booleans()) else found[: len(found) // 2]
    return tuple(kept + extra), {}


def a_sequence(value: object, draw: Draw) -> Arguments:
    found = members(value)
    if found and draw(st.booleans()):
        start = draw(st.integers(0, len(found) - 1))
        return tuple(found[start : start + draw(st.integers(1, 2))]), {}
    return some_items(value, draw), {}


def exact_items(value: object, draw: Draw) -> Arguments:
    found = members(value)
    choice = draw(st.sampled_from(["same", "reversed", "dropped", "other"]))
    if choice == "same":
        return tuple(found), {}
    if choice == "reversed":
        return tuple(reversed(found)), {}
    if choice == "dropped":
        return tuple(found[1:]), {}
    return some_items(value, draw), {}


def a_key(value: object, draw: Draw) -> Arguments:
    keys = [key for key in members(value) if isinstance(key, (str, int, float, bytes, tuple))]
    if keys and draw(st.booleans()):
        return (draw(st.sampled_from(keys)),), {}
    return (draw(st.sampled_from(["a", "z", "id"])),), {}


def a_dict_value(value: object, draw: Draw) -> Arguments:
    held = list(value.values()) if isinstance(value, dict) else []
    if held and draw(st.booleans()):
        return (draw(st.sampled_from(held)),), {}
    return (draw(SMALL_INT),), {}


def an_entry(value: object, draw: Draw) -> Arguments:
    (key,), _ = a_key(value, draw)
    (held,), _ = a_dict_value(value, draw)
    if isinstance(value, dict) and key in value and draw(st.booleans()):
        held = value[key]
    return ({key: held},), {}


def a_moment(value: object, draw: Draw) -> Arguments:
    if isinstance(value, datetime.datetime) and draw(st.booleans()):
        return (value,), {}
    return (draw(DATETIMES),), {}


@dataclass(frozen=True)
class Op:
    """One verdict-bearing assertion the machine can ask of a view.

    Attributes:
        name: The assertion's name on the builder.
        kinds: The kinds it applies to. The machine also asks it of any other kind, to reach refusals.
        args: Draws the arguments for a view.
        twin: The matcher factory that spells the same relation, if one exists.
        opposite: The assertion whose verdict is always the inverse of this one's.
        single_only_opposite: The opposite holds only for a call with one argument.
    """

    name: str
    kinds: frozenset[str] = field(repr=False)
    args: ArgumentMaker
    twin: Callable[..., Any] | None = None
    opposite: str | None = None
    single_only_opposite: bool = False


ALL = frozenset({*KINDS, "exception", "object"})


def _op(
    name: str,
    kinds: set[str] | frozenset[str],
    args: ArgumentMaker,
    twin: Callable[..., Any] | None = None,
    opposite: str | None = None,
    single_only_opposite: bool = False,
) -> Op:
    return Op(name, frozenset(kinds), args, twin, opposite, single_only_opposite)


OPS: list[Op] = [
    _op("is_equal_to", ALL, an_other, match.equal_to, "is_not_equal_to"),
    _op("is_not_equal_to", ALL, an_other, None, "is_equal_to"),
    _op("is_none", ALL, no_args, match.is_none, "is_not_none"),
    _op("is_not_none", ALL, no_args, match.is_not_none, "is_none"),
    _op("is_instance_of", ALL, a_type, match.is_instance_of),
    _op("is_type_of", ALL, a_type, match.is_type_of),
    _op("is_in", ALL, some_candidates, match.is_in, "is_not_in"),
    _op("is_not_in", ALL, some_candidates, None, "is_in"),
    _op("is_true", ALL, no_args, match.is_truthy, "is_false"),
    _op("is_false", ALL, no_args, match.is_falsy, "is_true"),
    _op("is_same_as", ALL, an_other, None, "is_not_same_as"),
    _op("is_not_same_as", ALL, an_other, None, "is_same_as"),
    _op("is_callable", ALL, no_args, match.is_callable, "is_not_callable"),
    _op("satisfies", ALL, a_predicate),
    _op("is_greater_than", NUMERIC, a_number, match.greater_than),
    _op("is_greater_than_or_equal_to", NUMERIC, a_number, match.greater_than_or_equal_to),
    _op("is_less_than", NUMERIC, a_number, match.less_than),
    _op("is_less_than_or_equal_to", NUMERIC, a_number, match.less_than_or_equal_to),
    _op("is_between", NUMERIC, a_range, match.between, "is_not_between"),
    _op("is_not_between", NUMERIC, a_range, None, "is_between"),
    _op("is_close_to", NUMERIC, a_tolerance, match.close_to, "is_not_close_to"),
    _op("is_not_close_to", NUMERIC, a_tolerance, None, "is_close_to"),
    _op("is_positive", NUMERIC, no_args, match.is_positive),
    _op("is_negative", NUMERIC, no_args, match.is_negative),
    _op("is_zero", NUMERIC, no_args, match.is_zero, "is_not_zero"),
    _op("is_not_zero", NUMERIC, no_args, None, "is_zero"),
    _op("is_even", {"int"}, no_args, match.is_even),
    _op("is_odd", {"int"}, no_args, match.is_odd),
    _op("is_divisible_by", {"int"}, a_divisor, match.is_divisible_by),
    _op("is_nan", {"float"}, no_args, None, "is_not_nan"),
    _op("is_not_nan", {"float"}, no_args, None, "is_nan"),
    _op("is_inf", {"float"}, no_args, None, "is_not_inf"),
    _op("is_not_inf", {"float"}, no_args, None, "is_inf"),
    _op("is_length", SIZED, a_length, match.has_length),
    _op("is_length_between", SIZED, a_length_range),
    _op("is_empty", SIZED, no_args, match.is_empty, "is_not_empty"),
    _op("is_not_empty", SIZED, no_args, match.is_not_empty, "is_empty"),
    _op("contains", SIZED, many_items, None, "does_not_contain", single_only_opposite=True),
    _op("does_not_contain", SIZED, many_items, None, "contains", single_only_opposite=True),
    _op("starts_with", {"str", "bytes", "list", "tuple"}, a_prefix),
    _op("ends_with", {"str", "bytes", "list", "tuple"}, a_suffix),
    _op("matches", {"str"}, a_pattern, match.matches_regex, "does_not_match"),
    _op("does_not_match", {"str"}, a_pattern, None, "matches"),
    _op("is_alpha", {"str"}, no_args),
    _op("is_digit", {"str"}, no_args),
    _op("is_lower", {"str"}, no_args),
    _op("is_upper", {"str"}, no_args),
    _op("is_equal_to_ignoring_case", {"str"}, a_cased),
    _op("contains_ignoring_case", {"str"}, a_cased),
    _op("is_valid_utf8", {"bytes"}, no_args),
    _op("contains_duplicates", {"list", "tuple"}, no_args, None, "does_not_contain_duplicates"),
    _op("does_not_contain_duplicates", {"list", "tuple"}, no_args, None, "contains_duplicates"),
    _op("is_sorted", {"list", "tuple"}, no_args, match.is_sorted),
    _op("contains_only", {"list", "tuple", "set"}, many_items, match.contains_only),
    _op("contains_exactly", {"list", "tuple"}, exact_items),
    _op("contains_sequence", {"list", "tuple"}, a_sequence),
    _op("is_subset_of", {"list", "tuple", "set"}, a_superset, match.is_subset_of),
    _op("all_satisfy", {"list", "tuple", "set"}, a_predicate),
    _op("any_satisfy", {"list", "tuple", "set"}, a_predicate),
    _op("none_satisfy", {"list", "tuple", "set"}, a_predicate),
    _op("is_iterable", ALL, no_args, None, "is_not_iterable"),
    _op("is_not_iterable", ALL, no_args, None, "is_iterable"),
    _op("contains_key", {"dict"}, a_key, None, "does_not_contain_key", single_only_opposite=True),
    _op("does_not_contain_key", {"dict"}, a_key, None, "contains_key", single_only_opposite=True),
    _op("contains_value", {"dict"}, a_dict_value, None, "does_not_contain_value", single_only_opposite=True),
    _op("does_not_contain_value", {"dict"}, a_dict_value, None, "contains_value", single_only_opposite=True),
    _op("contains_entry", {"dict"}, an_entry, None, "does_not_contain_entry", single_only_opposite=True),
    _op("does_not_contain_entry", {"dict"}, an_entry, None, "contains_entry", single_only_opposite=True),
    _op("is_before", {"datetime"}, a_moment, match.is_before),
    _op("is_after", {"datetime"}, a_moment, match.is_after),
]
OPS_BY_NAME = {op.name: op for op in OPS}


def twin_of(op: Op, value: object) -> Callable[..., Any] | None:
    """The matcher spelling of an op on this kind of value, where one exists."""
    kind = kind_of(value)
    if op.name == "contains":
        if kind in ("str", "bytes"):
            return match.contains_string
        return match.contains
    if op.name == "starts_with" and kind in ("str", "bytes"):
        return match.starts_with
    if op.name == "ends_with" and kind in ("str", "bytes"):
        return match.ends_with
    return op.twin


@dataclass(frozen=True)
class Pivot:
    """A transform: hands back a different value and reaches no verdict of its own.

    Attributes:
        name: The transform's name on the builder.
        kinds: The kinds it applies to.
        args: Draws the arguments for a view.
        oracle: The value the transform must hand back, or `RefusalError` naming the error it must raise.
    """

    name: str
    kinds: frozenset[str] = field(repr=False)
    args: ArgumentMaker
    oracle: Callable[..., object]


def _index(value: object, draw: Draw) -> Arguments:
    return (draw(st.integers(-1, len(members(value)))),), {}


def _mapper(value: object, draw: Draw) -> Arguments:
    return (draw(st.sampled_from([double, negate])),), {}


def _filter(value: object, draw: Draw) -> Arguments:
    return (draw(st.sampled_from([is_even_int, is_positive_number, match.greater_than(0)])),), {}


def _flattener(value: object, draw: Draw) -> Arguments:
    return (draw(st.sampled_from([identity, twice])),), {}


def _field(value: object, draw: Draw) -> Arguments:
    return (draw(st.sampled_from(["id", "rank"])),), {}


class RefusalError(Exception):
    """The oracle's word for a pivot the library must refuse, with the name of the error expected as its argument."""


def _first(value: object) -> object:
    found = members(value)
    if not found:
        raise RefusalError("ValueError")
    return found[0]


def _last(value: object) -> object:
    found = members(value)
    if not found:
        raise RefusalError("ValueError")
    return found[-1]


def _element(value: object, index: int) -> object:
    found = members(value)
    if index < 0 or index >= len(found):
        raise RefusalError("IndexError")
    return found[index]


def _single(value: object) -> object:
    found = members(value)
    if len(found) != 1:
        raise RefusalError("ValueError")
    return found[0]


def _mapped(value: object, func: Callable[[Any], object]) -> list[object]:
    return [func(item) for item in members(value)]


def _filtered(value: object, predicate: Any) -> list[object]:
    test = predicate.matches if hasattr(predicate, "matches") else predicate
    return [item for item in members(value) if test(item)]


def _flat(value: object, func: Callable[[Any], list[object]]) -> list[object]:
    return [inner for item in members(value) for inner in func(item)]


def _extracted(value: object, name: str) -> list[object]:
    return [item[name] for item in members(value)]


PIVOTS: list[Pivot] = [
    Pivot("first", frozenset(ITERABLE), no_args, _first),
    Pivot("last", frozenset(ITERABLE), no_args, _last),
    Pivot("element", frozenset(ITERABLE), _index, _element),
    Pivot("single", frozenset(ITERABLE), no_args, _single),
    Pivot("mapped", frozenset({"list", "tuple", "set"}), _mapper, _mapped),
    Pivot("filtered_on", frozenset({"list", "tuple", "set"}), _filter, _filtered),
    Pivot("flat_mapped", frozenset({"nested"}), _flattener, _flat),
    Pivot("extracting", frozenset({"records"}), _field, _extracted),
]


def _number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value == value


def python_verdict(name: str, value: object, args: tuple[Any, ...], kwargs: dict[str, Any]) -> bool | None:
    """What plain Python answers for the call, or None where the answer needs the library's own rules.

    Kept to relations whose meaning is not in doubt: identity, truthiness, type, size, `in` on the
    built-in containers the kinds produce, and ordering between non-NaN real numbers.
    """
    if kwargs:
        return None
    kind = kind_of(value)
    sized = kind in SIZED
    match name, args:
        case "is_equal_to", (other,):
            return value == other
        case "is_not_equal_to", (other,):
            return value != other
        case "is_none", ():
            return value is None
        case "is_not_none", ():
            return value is not None
        case "is_true", ():
            return bool(value)
        case "is_false", ():
            return not value
        case "is_same_as", (other,):
            return value is other
        case "is_not_same_as", (other,):
            return value is not other
        case "is_instance_of", (cls,):
            return isinstance(value, cls)
        case "is_type_of", (cls,):
            return type(value) is cls
        case "is_callable", ():
            return callable(value)
        case "is_empty", () if sized:
            return len(value) == 0  # ty: ignore[invalid-argument-type]  # sized kinds only
        case "is_not_empty", () if sized:
            return len(value) != 0  # ty: ignore[invalid-argument-type]  # sized kinds only
        case "is_length", (size,) if sized and isinstance(size, int):
            return len(value) == size  # ty: ignore[invalid-argument-type]  # sized kinds only
        case "contains", (item,) if kind in ("list", "tuple", "set", "dict", "records", "nested"):
            return item in value  # ty: ignore[unsupported-operator]  # container kinds only
        case "does_not_contain", (item,) if kind in ("list", "tuple", "set", "dict", "records", "nested"):
            return item not in value  # ty: ignore[unsupported-operator]  # container kinds only
        case "contains", (item,) if kind == "str" and isinstance(item, str):
            return item in value  # ty: ignore[unsupported-operator]  # str kind
        case "contains_key", (key,) if kind == "dict":
            return key in value  # ty: ignore[unsupported-operator]  # dict kind
        case "does_not_contain_key", (key,) if kind == "dict":
            return key not in value  # ty: ignore[unsupported-operator]  # dict kind
        case "starts_with", (prefix,) if kind == "str" and isinstance(prefix, str):
            return str(value).startswith(prefix)
        case "ends_with", (suffix,) if kind == "str" and isinstance(suffix, str):
            return str(value).endswith(suffix)
        case "is_greater_than", (other,) if _number(value) and _number(other):
            return value > other
        case "is_less_than", (other,) if _number(value) and _number(other):
            return value < other
        case "is_greater_than_or_equal_to", (other,) if _number(value) and _number(other):
            return value >= other
        case "is_less_than_or_equal_to", (other,) if _number(value) and _number(other):
            return value <= other
        case "is_positive", () if _number(value):
            return value > 0  # ty: ignore[unsupported-operator]  # numbers, checked above
        case "is_negative", () if _number(value):
            return value < 0  # ty: ignore[unsupported-operator]  # numbers, checked above
        case "is_zero", () if _number(value):
            return value == 0
        case "is_between", (low, high) if _number(value) and _number(low) and _number(high) and low <= high:
            return low <= value <= high
    return None


def bound_parameters(name: str, args: tuple[Any, ...], kwargs: dict[str, Any]) -> dict[str, object] | None:
    """What a Requirement for this call should carry: the signature bound to the call, defaults applied."""
    try:
        signature = inspect.signature(getattr(AssertionBuilder, name))
    except (TypeError, ValueError, AttributeError):
        return None
    signature = signature.replace(parameters=list(signature.parameters.values())[1:])
    try:
        bound = signature.bind(*args, **kwargs)
    except TypeError:
        return None
    bound.apply_defaults()
    return dict(bound.arguments)
