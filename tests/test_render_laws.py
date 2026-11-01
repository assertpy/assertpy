"""A failed comparison, held to printing what differs.

The third law of a failure, beside the two of `tests/test_diff_laws.py`.  The entries of a diff say what
differs.  This holds what a reader is shown of them, on every surface that prints a pair: the diff block, the
line a soft block keeps, and the headline.

1. Every row shows a difference a reader can see, or the failure says why it does not.  Two sides of two classes
   that print alike are each printed with its class.  Two sides of one class that print alike have a line of
   their own: a NaN, a class compared by identity, or the plain statement that their repr does not show it.
2. What is printed is what the value is.  A record read through its fields under ``ignore=`` or ``include=`` is
   printed as its class with the fields compared, and so is a mapping of a class of its own.
3. Printing asks nothing.  Once the failure exists, rendering it calls no ``==`` of the values and no comparator,
   and leaves the entries as they were.

A row that prints the same on both sides is not made to differ: a NaN against a NaN is one type and one repr,
and a comparator may turn down ``1`` against ``1``.  There the law is the line that says so.
"""

from __future__ import annotations

import collections
import dataclasses
import re
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from assertpy import AssertionFailure, assert_that, soft_assertions
from assertpy._engine._introspection import TakenApart, class_name, kind_of
from assertpy._engine._ordering import nan_operand
from assertpy._hints import (
    _IDENTITY_FACT,
    _NAN_FACT,
    _ORDER_FACT,
    _UNSEEN_FACT,
    _UNSEEN_IDENTITY_FACT,
    _UNSEEN_ORDER_FACT,
    _unseen,
)
from assertpy.assertpy import _indented_diff
from assertpy.errors import DiffEntry, DiffResult, _class_names, _diff_sides, _render_diff, _safe_repr, _told_apart
from tests.test_diff_laws import _KEY_OPTIONS, _OPTIONS, _ROWS, _built, _graph_pairs, _outcome
from tests.test_duality import _PAIRS, Case

_SGR = re.compile("\x1b\\[[0-9;]*m")
_OF_ONE_CLASS = (_IDENTITY_FACT, _UNSEEN_IDENTITY_FACT, _UNSEEN_FACT, _UNSEEN_ORDER_FACT)
"""The lines that account for a row of two values of one class that print the same."""

_OF_TWO_CLASSES = (
    *_OF_ONE_CLASS,
    "the values on both sides are equal, and only their types differ",
    "every difference here is the same text against a value of another type",
    "the contents match field for field, and only the type of the two sides differs",
)
"""The lines that account for a row of two classes nothing a reader would see tells apart."""


def _accounted_for(entry: DiffEntry, message: str) -> bool:
    """Whether a line of the failure says why this row, which prints the same on both sides, is one."""
    if nan_operand(entry.actual) or nan_operand(entry.expected):
        return _NAN_FACT in message
    one_class = kind_of(entry.actual) is kind_of(entry.expected)
    return any(line in message for line in (_OF_ONE_CLASS if one_class else _OF_TWO_CLASSES))


def _block_sides(kind: str, entry: DiffEntry) -> tuple[list[str], list[str]]:
    """The two sides of one entry as the diff block prints them, colours and side marks taken off."""
    lines = _SGR.sub("", _render_diff(DiffResult(kind=kind, entries=[entry]), color=True)).splitlines()[1:]
    marked = [line.strip() for line in lines]
    return (
        [line[2:] for line in marked if line.startswith("- ")],
        [line[2:] for line in marked if line.startswith("+ ")],
    )


def _soft_line_reads_alike(diff: DiffResult, entry: DiffEntry) -> bool:
    """Whether the line a soft block keeps for one entry has the same text on both sides of its ``!=``.

    Asked the way the block asks: an entry that stands alone goes through the dispatch for one, which keeps no
    line for a root pair, and one among others through the loop.
    """
    alone = len(diff.entries) == 1
    lines = _indented_diff(DiffResult(kind=diff.kind, entries=[entry] if alone else [entry, entry]), "")
    if not lines:
        return False
    line = lines[0].split(": ", 1)[1] if ": " in lines[0] else lines[0]
    half = line[: (len(line) - 4) // 2]
    return line == f"{half} != {half}"


def _held(diff: DiffResult) -> list[tuple[object, ...]]:
    """What the entries of a diff are, to compare before and after it is printed."""
    return [
        (id(entry), entry.path, entry.absent, id(entry.actual), id(entry.expected), entry.steps)
        for entry in diff.entries
    ]


def _hold_the_rendering(failure: AssertionFailure, said: str) -> None:
    """The third law, asked of one failure."""
    diff = failure.diff
    assert diff is not None
    before = _held(diff)
    message = failure._message
    for entry in diff.entries:
        where = f"{entry.path!r} of {said}"
        for side in (entry.actual, entry.expected):
            if isinstance(side, TakenApart):
                assert_that(_safe_repr(side)).described_as(f"a value taken apart, at {where}").starts_with(
                    f"{class_name(side.kind)}("
                )
        if entry.absent is not None or diff.kind in ("string", "match", "set", "contains"):
            continue
        minus, plus = _block_sides(diff.kind, entry)
        assert_that(minus).described_as(f"the actual side of {where}").is_not_empty()
        assert_that(plus).described_as(f"the expected side of {where}").is_not_empty()
        alike = minus == plus or _soft_line_reads_alike(diff, entry)
        if _class_names(entry.actual, entry.expected) is not None:
            # two classes a reader can tell apart: the row itself has to, whatever line stands above it
            assert_that(alike).described_as(f"two classes printed as one: {where}\n{message}").is_false()
        elif alike:
            assert_that(_accounted_for(entry, message)).described_as(
                f"a row that prints the same on both sides and no line that says why: {where}\n{message}"
            ).is_true()
    assert_that(_held(diff)).is_equal_to(before)


@settings(deadline=None, max_examples=2000, suppress_health_check=[HealthCheck.too_slow])
@given(case=_PAIRS["is_equal_to"].cases())
def test_a_failed_comparison_prints_what_differs(case: Case) -> None:
    (expected,) = case.args
    verdict, failure = _outcome(lambda: assert_that(case.value).is_equal_to(expected, **case.kwargs))
    if verdict == "failed":
        assert failure is not None
        _hold_the_rendering(failure, f"{case.value!r} against {expected!r} under {case.kwargs}")


@settings(deadline=None, max_examples=400, suppress_health_check=[HealthCheck.too_slow])
@given(
    pairs=st.lists(st.tuples(_ROWS, _ROWS), min_size=1, max_size=4),
    option=st.sampled_from(sorted(_KEY_OPTIONS)),
)
def test_a_failed_sequence_under_a_key_option_prints_what_differs(pairs, option) -> None:
    options = _KEY_OPTIONS[option]
    actual, expected = [one for one, _ in pairs], [other for _, other in pairs]
    verdict, failure = _outcome(lambda: assert_that(actual).is_equal_to(expected, **options))
    if verdict == "failed":
        assert failure is not None
        _hold_the_rendering(failure, f"{actual!r} against {expected!r} under {options}")


@settings(deadline=None, max_examples=600, suppress_health_check=[HealthCheck.too_slow])
@given(pair=_graph_pairs(), option=st.sampled_from(sorted(_OPTIONS)))
def test_a_failed_comparison_of_graphs_prints_what_differs(pair, option) -> None:
    actual, expected = _built(pair[0]), _built(pair[1])
    verdict, failure = _outcome(lambda: assert_that(actual).is_equal_to(expected, **_OPTIONS[option]))
    if verdict == "failed":
        assert failure is not None
        _hold_the_rendering(failure, f"{pair} under {option}")


class _Kept(dict):
    """A dict of a class of its own, which prints as a dict does."""


@dataclasses.dataclass
class _Row:
    id: int
    name: str


def _named_alike(module: str) -> type:
    """A dataclass called ``Row``, of the module given: two of them print the same and are two classes."""
    made = dataclasses.make_dataclass("Row", [("id", int)])
    made.__module__ = module
    return made


class _Counted:
    """A value that counts the times its ``==`` is asked and holds every other value apart."""

    asked = 0

    def __init__(self, held: int) -> None:
        self.held = held

    def __eq__(self, other: object) -> bool:
        type(self).asked += 1
        return isinstance(other, _Counted) and self.held == other.held

    __hash__ = None  # ty: ignore[invalid-assignment]  # a class that defines `__eq__` alone is unhashable anyway

    def __repr__(self) -> str:
        return "counted"


class _Unreadable:
    def __init__(self, held: int) -> None:
        self.held = held

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _Unreadable) and self.held == other.held

    __hash__ = None  # ty: ignore[invalid-assignment]  # a class that defines `__eq__` alone is unhashable anyway

    def __repr__(self) -> str:
        raise RuntimeError("no repr")


class _Long:
    """A value that is no text and whose repr differs from another's only past where a row is cut."""

    def __init__(self, tail: str) -> None:
        self.tail = tail

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _Long) and self.tail == other.tail

    __hash__ = None  # ty: ignore[invalid-assignment]  # a class that defines `__eq__` alone is unhashable anyway

    def __repr__(self) -> str:
        return f"Long({'x' * 900}{self.tail})"


def _failed(call: Any) -> AssertionFailure:
    verdict, failure = _outcome(call)
    assert_that(verdict).is_equal_to("failed")
    assert failure is not None
    return failure


def _soft_lines(call: Any) -> list[str]:
    with pytest.raises(AssertionError) as caught, soft_assertions():
        call()
    return [line.strip() for line in str(caught.value).splitlines()]


class TestTwoSidesOfTwoClassesThatPrintAlike:
    """Each side is printed with its class, on every surface that prints the pair."""

    def test_a_dict_of_a_class_of_its_own_against_a_plain_dict(self):
        actual, expected = {"a": _Kept(x=1)}, {"a": {"x": 1}}
        failure = _failed(lambda: assert_that(actual).is_equal_to(expected, strict_types=True))
        assert_that(_block_sides("dict", failure.diff.entries[0])).is_equal_to((["{'x': 1}:_Kept"], ["{'x': 1}:dict"]))
        lines = _soft_lines(lambda: assert_that(actual).is_equal_to(expected, strict_types=True))
        assert_that(lines).contains("a: {'x': 1}:_Kept != {'x': 1}:dict")
        _hold_the_rendering(failure, "a dict subclass against a dict")

    def test_at_the_top_the_headline_names_them(self):
        failure = _failed(lambda: assert_that(_Kept(x=1)).is_equal_to({"x": 1}, strict_types=True))
        assert_that(failure._message).starts_with(
            "Expected <{'x': 1}:_Kept> to be equal to <{'x': 1}:dict>, but was not."
        )

    def test_two_classes_of_one_name_are_told_apart_by_their_modules(self):
        one, other = _named_alike("billing"), _named_alike("orders")
        failure = _failed(lambda: assert_that([one(1)]).is_equal_to([other(1)]))
        assert_that(_block_sides("sequence", failure.diff.entries[0])).is_equal_to(
            (["Row(id=1):billing.Row"], ["Row(id=1):orders.Row"])
        )
        at_the_top = _failed(lambda: assert_that(one(1)).is_equal_to(other(1)))
        assert_that(at_the_top._message).starts_with(
            "Expected <Row(id=1):billing.Row> to be equal to <Row(id=1):orders.Row>, but was not."
        )

    def test_under_a_compare_option_the_headline_names_them(self):
        label = type("Label", (str,), {})
        failure = _failed(lambda: assert_that(label("x")).is_equal_to("x", strict_types=True))
        assert_that(failure._message).starts_with("Expected <x:Label> to be equal to <x:str>, but was not.")

    def test_where_a_comparator_owns_the_top_pair_the_headline_names_them(self):
        label = type("Label", (str,), {})
        failure = _failed(lambda: assert_that(label("x")).is_equal_to("x", comparators={label: lambda a, b: False}))
        assert_that(failure._message).starts_with("Expected <x:Label> to be equal to <x:str>, but was not.")

    def test_a_class_made_without_a_module_is_still_told_apart(self):
        one = _named_alike("billing")
        # made in a namespace with no ``__name__``, which is the one way a class comes to say no module at all
        other = eval('type("Row", (), {"__repr__": lambda self: "Row(id=1)"})', {})
        failure = _failed(lambda: assert_that([one(1)]).is_equal_to([other()]))
        assert_that(_block_sides("sequence", failure.diff.entries[0])).is_equal_to(
            (["Row(id=1):billing.Row"], ["Row(id=1):?.Row"])
        )

    def test_two_classes_nothing_tells_apart_get_the_line_that_says_their_types_differ(self):
        one, other = _named_alike("billing"), _named_alike("billing")
        failure = _failed(lambda: assert_that([one(1)]).is_equal_to([other(1)]))
        assert_that(_block_sides("sequence", failure.diff.entries[0])).is_equal_to((["Row(id=1)"], ["Row(id=1)"]))
        assert_that(failure._message).contains("the same text against a value of another type")

    def test_two_records_taken_apart_under_a_key_option(self):
        one, other = _named_alike("billing"), _named_alike("orders")
        options: dict[str, Any] = {"ignore": ("r", "missing"), "strict_types": True}
        failure = _failed(lambda: assert_that({"r": one(1)}).is_equal_to({"r": other(1)}, **options))
        assert_that(_block_sides("dict", failure.diff.entries[0])).is_equal_to(
            (["Row(id=1):billing.Row"], ["Row(id=1):orders.Row"])
        )

    def test_the_named_values_of_a_report_are_told_apart_too(self):
        assert_that(_diff_sides(_Kept(x=1), {"x": 1})).is_equal_to(("{'x': 1}:_Kept", "{'x': 1}:dict"))
        assert_that(_diff_sides({"x": 1}, {"x": 1})).is_equal_to(("{'x': 1}", "{'x': 1}"))

    def test_the_closest_element_of_a_contains_failure_is_told_apart_too(self):
        one, other = _named_alike("billing"), _named_alike("orders")
        failure = _failed(lambda: assert_that([{"k": 1, "r": one(1)}]).contains({"k": 1, "r": other(1)}))
        assert_that(failure._message).contains("r (Row(id=1):billing.Row != Row(id=1):orders.Row)")

    def test_a_value_that_answers_for_its_class_with_code_of_its_own_is_not_asked(self):
        class Hostile:
            @property
            def __class__(self):
                raise RuntimeError("no class")

            def __repr__(self) -> str:
                raise RuntimeError("no repr")

        assert_that(_safe_repr(Hostile())).is_equal_to("<unreprable Hostile>")
        assert_that(_told_apart("x", "x", Hostile(), 1)).is_equal_to(("x:Hostile", "x:int"))
        assert_that(_class_names(Hostile(), Hostile())).is_none()

    def test_a_row_of_such_values_is_printed_without_asking_them(self):
        class Hostile:
            @property
            def __class__(self):
                raise RuntimeError("no class")

            def __repr__(self) -> str:
                raise RuntimeError("no repr")

        entry = DiffEntry(path="[0]", actual=Hostile(), expected=Hostile())
        for kind in ("sequence", "dict", "scalar"):
            assert_that(_block_sides(kind, entry)).is_equal_to((["<unreprable Hostile>"], ["<unreprable Hostile>"]))
        assert_that(_indented_diff(DiffResult(kind="sequence", entries=[entry, entry]), "")[0]).is_equal_to(
            "[0]: <unreprable Hostile> != <unreprable Hostile>"
        )

    def test_a_module_that_cannot_be_printed_costs_only_its_name(self):
        class Unprintable:
            def __str__(self) -> str:
                raise RuntimeError("no text")

            __repr__ = __str__

        one, other = _named_alike("billing"), _named_alike("orders")
        one.__module__ = Unprintable()  # ty: ignore[invalid-assignment]  # a module name that is no text
        names = _class_names(one(1), other(1))
        assert names is not None
        assert_that(names[0]).is_equal_to("<unreprable Unprintable>.Row")
        assert_that(names[1]).is_equal_to("orders.Row")

    def test_two_texts_of_two_classes_are_not_drawn_as_one_common_line(self):
        # the caret guide found nothing to point at and printed the pair as a line both sides share
        label = type("Label", (str,), {})
        failure = _failed(lambda: assert_that({"a": label("x")}).is_equal_to({"a": "x"}, strict_types=True))
        assert_that(_block_sides("dict", failure.diff.entries[0])).is_equal_to((["'x':Label"], ["'x':str"]))


class TestAValueTakenApartPrintsAsItsClass:
    """A record under ``ignore=`` or ``include=`` is read through its fields, and printed as the record it is."""

    def test_the_headline_names_the_record(self):
        failure = _failed(lambda: assert_that(_Row(1, "a")).is_equal_to(_Row(2, "b"), ignore="id"))
        assert_that(failure._message).is_equal_to(
            "Expected <_Row(name='a')> to be equal to <_Row(name='b')> ignoring keys <id>, but was not."
        )

    def test_what_matched_is_left_out_as_in_a_dict(self):
        point = collections.namedtuple("point", "x y z")
        failure = _failed(lambda: assert_that(point(1, 2, 3)).is_equal_to(point(1, 9, 3), ignore="missing"))
        assert_that(failure._message).is_equal_to(
            "Expected <point(.., y=2, ..)> to be equal to <point(.., y=9, ..)> ignoring keys <missing>, but was not."
        )

    def test_an_element_of_a_sequence_and_a_row_with_one_side(self):
        rows = [_Row(1, "a"), _Row(2, "b")]
        failure = _failed(lambda: assert_that(rows).is_equal_to([_Row(9, "a")], ignore="id"))
        assert_that(failure._message).is_equal_to(
            "Expected <[.., _Row(name='b')]> to be equal to <[..]> ignoring keys <id>, but was not."
        )
        assert_that(_safe_repr(failure.diff.entries[0].actual)).is_equal_to("_Row(name='b')")

    def test_a_mapping_of_a_class_of_its_own_is_written_as_one(self):
        options: dict[str, Any] = {"ignore": "id", "strict_types": True}
        failure = _failed(lambda: assert_that([_Kept(x=1), 0]).is_equal_to([{"x": 1}, 0], **options))
        assert_that(failure._message).starts_with(
            "Expected <[_Kept({'x': 1}), ..]> to be equal to <[{'x': 1}, ..]> ignoring keys <id>, but was not."
        )
        assert_that(_block_sides("sequence", failure.diff.entries[0])).is_equal_to((["_Kept({'x': 1})"], ["{'x': 1}"]))

    def test_a_record_that_holds_itself_is_written_as_a_record_where_it_comes_back(self):
        one, other = _Row(1, "a"), _Row(2, "b")
        one.name, other.name = one, other  # ty: ignore[invalid-assignment]  # a field made to hold the record
        failure = _failed(lambda: assert_that({"r": one, "n": 1}).is_equal_to({"r": other, "n": 2}, ignore=("r", "x")))
        assert_that(failure._message).contains("_Row(<circular ref>)")
        assert_that(repr(failure.diff.entries[0].actual)).is_equal_to("1")
        taken = TakenApart(_Row, {})
        taken["name"] = taken
        assert_that(repr(taken)).is_equal_to("_Row(name=...)")

    def test_a_field_whose_repr_raises_costs_the_record_its_fields_and_not_its_name(self):
        assert_that(_safe_repr(TakenApart(_Row, {"id": _Unreadable(1)}))).is_equal_to("<unreprable _Row>")

    def test_the_missing_key_of_an_include_names_the_record(self):
        with pytest.raises(AssertionFailure, match=r"Expected <_Row\(id=1, name='a'\)> to include key <nope>"):
            assert_that(_Row(1, "a")).is_equal_to(_Row(1, "a"), include="nope")


class TestTwoSidesOfOneClassThatPrintAlike:
    """Nothing is made to differ.  The failure says why the two are held apart, or that their repr does not."""

    def test_a_nan(self):
        failure = _failed(lambda: assert_that([float("nan")]).is_equal_to([float("nan")]))
        assert_that(_block_sides("sequence", failure.diff.entries[0])).is_equal_to((["nan"], ["nan"]))
        assert_that(failure._message).contains(_NAN_FACT)

    def test_a_row_beside_a_nan_that_prints_the_same_gets_a_line_of_its_own(self):
        actual, expected = {"n": float("nan"), "c": _Counted(1)}, {"n": float("nan"), "c": _Counted(2)}
        failure = _failed(lambda: assert_that(actual).is_equal_to(expected))
        assert_that(failure._message.splitlines()[1:]).is_equal_to(
            [_NAN_FACT, f"{_UNSEEN_FACT} (attributes that differ: held)"]
        )
        _hold_the_rendering(failure, "a row that prints alike beside a NaN")
        alone = _failed(lambda: assert_that({"n": float("nan"), "c": 1}).is_equal_to({"n": float("nan"), "c": 2}))
        assert_that(alone._message.splitlines()[1:]).is_equal_to([_NAN_FACT])

    def test_a_class_compared_by_identity(self):
        token = dataclasses.make_dataclass("Token", [("value", str)], eq=False)
        failure = _failed(lambda: assert_that([token("a")]).is_equal_to([token("a")]))
        assert_that(failure._message).contains(_UNSEEN_IDENTITY_FACT)

    def test_a_comparator_that_turns_down_a_pair(self):
        failure = _failed(lambda: assert_that({"a": 1}).is_equal_to({"a": 1}, comparators={int: lambda a, b: False}))
        assert_that(failure._message.splitlines()[1:]).is_equal_to(["compared with comparators for int", _UNSEEN_FACT])

    def test_a_repr_that_raises(self):
        failure = _failed(lambda: assert_that([_Unreadable(1)]).is_equal_to([_Unreadable(2)]))
        assert_that(_block_sides("sequence", failure.diff.entries[0])).is_equal_to(
            (["<unreprable _Unreadable>"], ["<unreprable _Unreadable>"])
        )
        assert_that(failure._message).contains(_UNSEEN_FACT)

    def test_one_such_row_among_others_and_beside_a_missing_key(self):
        actual, expected = {"a": _Counted(1), "b": 1, "c": 0}, {"a": _Counted(2), "b": 2}
        failure = _failed(lambda: assert_that(actual).is_equal_to(expected))
        assert_that(failure._message).contains(_UNSEEN_FACT)
        _hold_the_rendering(failure, "a row that prints alike beside a missing key")

    def test_the_line_for_a_pair_inside_is_not_the_one_for_the_two_values_compared(self):
        token = dataclasses.make_dataclass("Token", [("value", str)], eq=False)
        top = _failed(lambda: assert_that(token("a")).is_equal_to(token("a")))
        assert_that(top._message.splitlines()[1]).is_equal_to(_IDENTITY_FACT)
        # beside a row that differs in the open, a sentence about "these values" would be read of the two dicts
        inside = _failed(lambda: assert_that({"t": token("a"), "n": 1}).is_equal_to({"t": token("a"), "n": 2}))
        assert_that(inside._message.splitlines()[1]).is_equal_to(_UNSEEN_IDENTITY_FACT)

    def test_identity_is_not_said_where_a_comparator_took_part(self):
        # with nothing to read it by, so a compare option leaves the pair to ``==`` as plain equality does
        token = type("Token", (), {"__slots__": (), "__repr__": lambda self: "Token()"})
        for options in ({}, {"tolerance": 0.1}, {"ignore": "missing"}):
            failure = _failed(
                lambda options=options: assert_that({"t": token()}).is_equal_to({"t": token()}, **options)
            )
            assert_that(failure._message).contains(_UNSEEN_IDENTITY_FACT)
        compared: dict[str, Any] = {"comparators": {float: lambda a, b: a == b}}
        failure = _failed(lambda: assert_that({"t": token()}).is_equal_to({"t": token()}, **compared))
        assert_that(failure._message).contains(_UNSEEN_FACT).does_not_contain(_UNSEEN_IDENTITY_FACT)
        # the builder says so of that comparison only
        builder = assert_that({"t": token()})
        with pytest.raises(AssertionFailure):
            builder.is_equal_to({"t": token()}, **compared)
        with pytest.raises(AssertionFailure, match="leaves __eq__ to object"):
            builder.is_equal_to({"t": token()})

    def test_a_comparison_refused_before_it_ran_leaves_nothing_said_of_the_next(self):
        class Elementwise:
            """An array-like whose ``==`` has no one truth value, which `is_equal_to` refuses to compare."""

            def __array__(self) -> None: ...

            def __eq__(self, other: object) -> bool:
                raise ValueError("no single truth value")

            __hash__ = None  # ty: ignore[invalid-assignment]  # a class that defines `__eq__` alone is unhashable

        builder = assert_that(Elementwise())
        with pytest.raises(TypeError):
            builder.is_equal_to([1], comparators={float: lambda a, b: a == b})
        assert_that(builder._comparators_took_part).is_false()

    def test_a_comparator_that_asserts_on_the_builder_it_serves_leaves_what_is_said_alone(self):
        token = type("Token", (), {"__slots__": (), "__repr__": lambda self: "Token()"})
        builder = assert_that({"t": token()})

        def turned_down(one: object, other: object) -> bool:
            builder.is_equal_to(builder.val, comparators={float: lambda a, b: True})
            return False

        with pytest.raises(AssertionFailure) as caught:
            builder.is_equal_to({"t": token()}, comparators={token: turned_down})
        assert_that(caught.value._message).contains(_UNSEEN_FACT).does_not_contain(_UNSEEN_IDENTITY_FACT)
        assert_that(builder._comparators_took_part).is_false()

    def test_a_pair_past_the_fiftieth_row_is_accounted_for(self):
        # how many rows are printed is the renderer's to decide, and it can be asked for all of them
        actual, expected = [*range(50), _Counted(1)], [*range(1, 51), _Counted(2)]
        failure = _failed(lambda: assert_that(actual).is_equal_to(expected))
        assert_that(_render_diff(failure.diff, max_entries=0).splitlines()[-2:]).is_equal_to(
            ["    - counted", "    + counted"]
        )
        assert_that(failure._message).contains(f"{_UNSEEN_FACT} (attributes that differ: held)")

    def test_elements_that_moved_and_print_the_same_get_both_facts(self):
        class Hashed(_Counted):
            def __hash__(self) -> int:
                return hash(self.held)

        failure = _failed(lambda: assert_that([Hashed(1), Hashed(2)]).is_equal_to([Hashed(2), Hashed(1)]))
        assert_that(failure._message.splitlines()[1]).is_equal_to(_UNSEEN_ORDER_FACT)
        moved = _failed(lambda: assert_that([1, 2]).is_equal_to([2, 1]))
        assert_that(moved._message.splitlines()[1]).is_equal_to(_ORDER_FACT)
        _hold_the_rendering(failure, "two elements that moved and print the same")

    def test_an_attribute_that_cannot_be_compared_is_left_out_and_the_rest_named(self):
        class Touchy:
            def __eq__(self, other: object) -> bool:
                raise RuntimeError("no equality")

            __hash__ = None  # ty: ignore[invalid-assignment]  # a class that defines `__eq__` alone is unhashable

        one, other, same = _Counted(1), _Counted(2), _Counted(1)
        one.touchy, other.touchy = Touchy(), Touchy()  # ty: ignore[unresolved-attribute]  # given to the instance
        one.shared = other.shared = Touchy()  # ty: ignore[unresolved-attribute]  # given to the instance
        failure = _failed(lambda: assert_that([one]).is_equal_to([other]))
        assert_that(failure._message.splitlines()[1]).is_equal_to(f"{_UNSEEN_FACT} (attributes that differ: held)")
        same.touchy = Touchy()  # ty: ignore[unresolved-attribute]  # given to the instance
        unknown = _failed(lambda: assert_that([one]).is_equal_to([same], comparators={_Counted: lambda a, b: False}))
        assert_that(unknown._message.splitlines()[-1]).is_equal_to(f"{_UNSEEN_FACT} (attributes that differ: shared)")

    def test_the_attributes_that_differ_are_named_where_the_repr_leaves_them_out(self):
        failure = _failed(lambda: assert_that([_Counted(1)]).is_equal_to([_Counted(2)]))
        assert_that(failure._message.splitlines()[1]).is_equal_to(f"{_UNSEEN_FACT} (attributes that differ: held)")

    def test_an_attribute_one_side_lacks_is_named_and_a_long_list_is_cut(self):
        one, other = _Counted(1), _Counted(1)
        one.only_here = 1  # ty: ignore[unresolved-attribute]  # an attribute given to one instance alone
        for index in range(6):
            setattr(other, f"extra{index}", index)
        failure = _failed(lambda: assert_that([one]).is_equal_to([other], comparators={_Counted: lambda a, b: False}))
        assert_that(failure._message.splitlines()[-1]).is_equal_to(
            f"{_UNSEEN_FACT} (attributes that differ: only_here, extra0, extra1, extra2, extra3, ..)"
        )

    def test_no_more_attributes_are_compared_than_the_line_can_name(self):
        one, other = _Counted(0), _Counted(0)
        for index in range(40):
            setattr(one, f"part{index}", _Counted(index))
            setattr(other, f"part{index}", _Counted(index + 100))
        _Counted.asked = 0
        assert_that(_unseen([(one, other)], comparators=True)).is_equal_to(
            f"{_UNSEEN_FACT} (attributes that differ: part0, part1, part2, part3, part4, ..)"
        )
        # the six parts it takes to know the list goes on, of the forty that differ
        assert_that(_Counted.asked).is_equal_to(6)

    def test_an_attribute_table_that_cannot_be_read_costs_only_the_names(self):
        class Guarded:
            __slots__ = ("held",)

            def __init__(self, held: int) -> None:
                self.held = held

            def __eq__(self, other: object) -> bool:
                return isinstance(other, Guarded) and self.held == other.held

            __hash__ = None  # ty: ignore[invalid-assignment]  # a class that defines `__eq__` alone is unhashable

            def __repr__(self) -> str:
                return "guarded"

        failure = _failed(lambda: assert_that([Guarded(1)]).is_equal_to([Guarded(2)]))
        assert_that(failure._message.splitlines()[1]).is_equal_to(_UNSEEN_FACT)

    def test_identity_is_the_reason_only_where_it_is_for_every_such_row(self):
        token = dataclasses.make_dataclass("Token", [("value", str)], eq=False)
        actual, expected = [token("a"), _Counted(1)], [token("a"), _Counted(2)]
        failure = _failed(lambda: assert_that(actual).is_equal_to(expected))
        assert_that(failure._message).contains(_UNSEEN_FACT).does_not_contain(_UNSEEN_IDENTITY_FACT)

    def test_a_row_told_apart_by_its_classes_is_not_one_of_them(self):
        one, other = _named_alike("billing"), _named_alike("orders")
        failure = _failed(lambda: assert_that({"r": one(1), "c": 0}).is_equal_to({"r": other(1)}))
        assert_that(failure._message).does_not_contain(_UNSEEN_FACT)
        _hold_the_rendering(failure, "two classes of one name beside a missing key")

    def test_a_failure_whose_rows_all_differ_says_nothing_of_it(self):
        failure = _failed(lambda: assert_that({"a": 1}).is_equal_to({"a": 2}))
        assert_that(failure._message).is_equal_to("Expected <{'a': 1}> to be equal to <{'a': 2}>, but was not.")


@dataclasses.dataclass
class _Holder:
    v: int
    next: object = None


class TestADictBesideARecordIsReadAsDeep:
    """Found by the law: a row of two equal records, one taken apart and one not, under a line about types.

    The comparison itself was at fault and is held in `tests/test_dict_compare.py`.  What is held here is that a
    record under the two that does differ is named at its field, with nothing left printing the same.
    """

    def test_a_record_under_them_that_differs_fails_at_its_field(self):
        record, payload = _Holder(0, _Holder(1)), {"v": 0, "next": _Holder(2)}
        failure = _failed(lambda: assert_that(record).is_equal_to(payload, ignore="missing"))
        assert_that([entry.path for entry in failure.diff.entries]).is_equal_to(["next.v"])
        _hold_the_rendering(failure, "a dict beside a record, each holding a record")


class TestARowIsCutAroundWhatDiffers:
    def test_two_long_values_that_are_no_text(self):
        # each side cut on its own at 400 characters, the two printed alike
        failure = _failed(lambda: assert_that([_Long("a")]).is_equal_to([_Long("b")]))
        minus, plus = _block_sides("sequence", failure.diff.entries[0])
        assert_that(minus).is_not_equal_to(plus)
        assert_that((minus[0][-3:], plus[0][-3:])).is_equal_to(("xa)", "xb)"))
        _hold_the_rendering(failure, "two long values")


class TestPrintingAsksNothing:
    def test_no_equality_and_no_comparator_is_asked_once_the_failure_exists(self):
        asked = []

        def close(one: float, other: float) -> bool:
            asked.append((one, other))
            return False

        actual = {"a": _Counted(1), "n": 1.0, "rows": [_Row(1, "a")]}
        expected = {"a": _Counted(2), "n": 1.0, "rows": [_Row(1, "b")]}
        failure = _failed(lambda: assert_that(actual).is_equal_to(expected, comparators={float: close}))
        entries = list(failure.diff.entries)
        before = (_Counted.asked, len(asked))
        for _ in range(2):
            _render_diff(failure.diff, color=True)
            _indented_diff(failure.diff, "  ")
            str(failure)
            repr(failure)
        assert_that((_Counted.asked, len(asked))).is_equal_to(before)
        assert_that(all(now is then for now, then in zip(failure.diff.entries, entries, strict=True))).is_true()
