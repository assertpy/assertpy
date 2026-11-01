"""How far ``strict_types`` and a comparator reach: into an object, a deque, and a member matched by hash.

The guide says ``strict_types=True`` holds "at any depth" and covers "anything matched by hash", and that a
container whose ``==`` holds "is still walked" for a comparator.  Three kinds of value stopped the walk: an
object compared by an ``==`` of its own, a deque, and a tuple or a frozenset used as a key or a set member.
"""

from __future__ import annotations

import collections
import numbers
import types
from typing import Any, NamedTuple

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from assertpy import AssertionFailure, assert_that, match
from assertpy._engine import _compare

STRICT: dict[str, Any] = {"strict_types": True}


def _exact(actual: object, expected: object) -> bool:
    return type(actual) is type(expected) and actual == expected


EXACT: dict[str, Any] = {"comparators": {int: _exact, bool: _exact}}


class _User:
    """An object with fields and an ``==`` that reads all of them."""

    def __init__(self, **fields: object) -> None:
        self.__dict__.update(fields)

    def __eq__(self, other: object) -> bool:
        return type(other) is _User and vars(self) == vars(other)

    __hash__ = None

    def __repr__(self) -> str:
        return f"_User({vars(self)})"


class _ById:
    """An object whose ``==`` reads one field of the two it holds."""

    def __init__(self, ident: object, note: object) -> None:
        self.ident = ident
        self.note = note

    def __eq__(self, other: object) -> bool:
        return type(other) is _ById and self.ident == other.ident

    __hash__ = None


class _Point(NamedTuple):
    x: object
    y: object


def _holds(actual: object, expected: object, **options: Any) -> bool:
    return assert_that(actual).check().is_equal_to(expected, **options).passed


def _paths(actual: object, expected: object, **options: Any) -> list[str]:
    with pytest.raises(AssertionFailure) as raised:
        assert_that(actual).is_equal_to(expected, **options)
    diff = raised.value.diff
    assert diff is not None
    return [entry.path for entry in diff.entries]


class TestAnObjectIsLookedInto:
    @pytest.mark.parametrize(
        "options", [STRICT, EXACT, {"comparators": {"active": _exact}}], ids=["strict", "type", "field"]
    )
    @pytest.mark.parametrize(
        "wrap",
        [lambda user: user, lambda user: {"u": user}, lambda user: [user], lambda user: _User(inner=user)],
        ids=["root", "in a dict", "in a list", "in an object"],
    )
    def test_a_field_of_another_type_fails_wherever_the_object_sits(self, wrap, options):
        assert_that(_holds(wrap(_User(active=1)), wrap(_User(active=True)), **options)).is_false()
        assert_that(_holds(wrap(_User(active=True)), wrap(_User(active=True)), **options)).is_true()

    def test_the_failure_names_the_field(self):
        assert_that(_paths(_User(active=1), _User(active=True), **STRICT)).is_equal_to([".active"])
        assert_that(_paths({"u": _User(active=1)}, {"u": _User(active=True)}, **STRICT)).is_equal_to(["u.active"])
        assert_that(_paths([_User(a=_User(b=[1]))], [_User(a=_User(b=[True]))], **STRICT)).is_equal_to(["[0].a.b[0]"])

    def test_a_matcher_reads_it_the_same_way(self):
        assert_that(match.equal_to(_User(active=True), **STRICT).matches(_User(active=1))).is_false()
        assert_that(match.equal_to({"u": _User(active=True)}, **STRICT).matches({"u": _User(active=1)})).is_false()
        assert_that(match.equal_to(_User(active=True), **STRICT).matches(_User(active=True))).is_true()

    def test_a_namespace_is_such_an_object(self):
        assert_that(_holds(types.SimpleNamespace(a=1), types.SimpleNamespace(a=True), **STRICT)).is_false()
        assert_that(_holds(types.SimpleNamespace(a=1), types.SimpleNamespace(a=1), **STRICT)).is_true()

    def test_a_key_option_that_names_nothing_in_it_does_not_change_the_answer(self):
        users = [_User(active=1)], [_User(active=True)]
        assert_that(_holds(*users, **STRICT)).is_equal_to(_holds(*users, ignore="unrelated", **STRICT)).is_false()

    @pytest.mark.parametrize(
        "options", [STRICT, EXACT, {"tolerance": 0.5, **STRICT}], ids=["strict", "type", "tolerance"]
    )
    def test_a_field_the_objects_own_equality_holds_apart_is_left_to_it(self, options):
        """`==` holds the two equal, so a field it does not read, or reads another way, is not the walk's to fail."""
        assert_that(_holds(_ById(7, 1.0), _ById(7, 9.0), **options)).is_true()
        assert_that(_holds([_ById(7, "a")], [_ById(7, None)], **options)).is_true()
        assert_that(_holds({"k": _ById(7, [1])}, {"k": _ById(7, [True, 2])}, **options)).is_true()

    def test_a_field_it_holds_equal_is_still_asked_its_type(self):
        assert_that(_holds(_ById(7, 1), _ById(7, True), **STRICT)).is_false()
        assert_that(_holds(_ById(7, [1]), _ById(7, [True]), **STRICT)).is_false()
        assert_that(_holds(_ById(1, "a"), _ById(True, "a"), **STRICT)).is_false()

    def test_a_field_one_side_lacks_is_outside_the_equality_that_held_them(self):
        cached, bare = _ById(7, "a"), _ById(7, "a")
        cached.total = 3
        assert_that(_holds(cached, bare, **STRICT)).is_true()
        assert_that(_holds(bare, cached, **STRICT)).is_true()

    def test_two_objects_their_own_equality_holds_apart_are_not_taken_apart(self):
        """Taken apart, two objects with no ``==`` of their own would be equal, where ``==`` says they are not."""

        class Plain:
            def __init__(self, value: int) -> None:
                self.value = value

        assert_that(_holds(Plain(1), Plain(1), **STRICT)).is_false()
        assert_that(_holds([Plain(1)], [Plain(1)], **EXACT)).is_false()
        same = Plain(1)
        assert_that(_holds([same], [same], **STRICT)).is_true()

    def test_two_classes_one_equality_holds_equal_are_not_read_field_by_field(self):
        class Anything:
            def __init__(self, left: object) -> None:
                self.left = left

            def __eq__(self, other: object) -> bool:
                return True

            __hash__ = None

        class Other(Anything):
            pass

        assert_that(_holds([Anything(1)], [Other(True)], **EXACT)).is_true()
        assert_that(_holds([Anything(1)], [Anything(True)], **EXACT)).is_false()

    def test_an_object_that_holds_more_than_its_dict_stays_with_its_own_equality(self):
        class Slotted:
            __slots__ = ("value",)

            def __init__(self, value: object) -> None:
                self.value = value

            def __eq__(self, other: object) -> bool:
                return type(other) is Slotted and self.value == other.value

            __hash__ = None

        assert_that(_holds(Slotted(1), Slotted(True), **STRICT)).is_true()

    def test_a_value_of_a_number_class_is_one_value_whatever_it_carries(self):
        """The limit of the reading: a class of numbers, texts or dates is never a bag of attributes."""

        class Box(numbers.Number):
            def __init__(self, value: object) -> None:
                self.value = value

            def __eq__(self, other: object) -> bool:
                return type(other) is Box and self.value == other.value

            __hash__ = None

        assert_that(_holds(Box(1), Box(True), **STRICT)).is_true()
        assert_that(match.equal_to(Box(True), **STRICT).matches(Box(1))).is_true()

    @pytest.mark.parametrize("strict", [{}, STRICT], ids=["alone", "strict"])
    def test_a_comparator_that_owns_the_object_decides_it_alone(self, strict):
        class Apart:
            def __eq__(self, other: object) -> bool:
                return False

            __hash__ = None

        accepting: dict[str, Any] = {"comparators": {Apart: lambda actual, expected: True}, **strict}
        assert_that(_holds(Apart(), Apart(), **accepting)).is_true()
        assert_that(_holds([Apart()], [Apart()], **accepting)).is_true()
        assert_that(_holds({"k": Apart()}, {"k": Apart()}, comparators={"k": lambda actual, expected: True})).is_true()
        assert_that(_holds([Apart()], [Apart()], comparators={int: lambda actual, expected: True})).is_false()

    def test_a_field_equality_cannot_answer_for_is_walked_with_every_option(self):
        one: list = []
        other: list = []
        one.extend([one, 1.0])
        other.extend([other, 1.25])
        assert_that(_holds(_ById(7, one), _ById(7, other), **STRICT)).is_false()
        assert_that(_holds(_ById(7, one), _ById(7, other), tolerance=0.5, **STRICT)).is_true()
        assert_that(_holds(_ById(7, one), _ById(7, other), tolerance=0.1, **STRICT)).is_false()

    def test_an_object_shared_by_both_sides_is_matched_by_identity_and_not_looked_into(self):
        asked = []

        def refusing(actual: object, expected: object) -> bool:
            asked.append(actual)
            return False

        shared = _User(active=1)
        options: dict[str, Any] = {"comparators": {int: refusing}, **STRICT}
        assert_that(_holds({"u": shared}, {"u": shared}, **options)).is_true()
        assert_that(_holds([shared], [shared], **options)).is_true()
        assert_that(asked).is_empty()
        assert_that(_holds({"u": _User(active=1)}, {"u": _User(active=1)}, **options)).is_false()
        assert_that(asked).is_not_empty().contains_only(1)

    def test_a_field_equality_cannot_answer_for_is_walked(self):
        """A graph ``==`` runs out of stack on is neither held equal nor held apart, so the walk is its judge."""
        one: list = []
        other: list = []
        one.extend([one, 1])
        other.extend([other, True])
        assert_that(_holds(_ById(7, one), _ById(7, other), **STRICT)).is_false()
        assert_that(_holds({"k": _ById(7, one)}, {"k": _ById(7, other)}, **STRICT)).is_false()
        assert_that(match.equal_to(_ById(7, other), **STRICT).matches(_ById(7, one))).is_false()
        again: list = []
        again.extend([again, 1])
        assert_that(_holds(_ById(7, one), _ById(7, again), **STRICT)).is_true()


class TestADequeIsLookedInto:
    @pytest.mark.parametrize("options", [STRICT, EXACT], ids=["strict", "comparator"])
    @pytest.mark.parametrize("wrap", [lambda q: q, lambda q: {"q": q}, lambda q: [q]], ids=["root", "dict", "list"])
    def test_an_item_of_another_type_fails(self, wrap, options):
        one, other = collections.deque([1, 2]), collections.deque([True, 2])
        assert_that(_holds(wrap(one), wrap(other), **options)).is_false()
        assert_that(_holds(wrap(one), wrap(collections.deque([1, 2])), **options)).is_true()

    def test_the_failure_names_the_item(self):
        one, other = collections.deque([{"a": 1}]), collections.deque([{"a": True}])
        assert_that(_paths({"q": one}, {"q": other}, **STRICT)).is_equal_to(["q[0].a"])
        assert_that(_paths(one, other, **STRICT)).is_equal_to(["[0].a"])

    def test_a_tolerance_reaches_its_items(self):
        one, other = collections.deque([1.0, 2.0]), collections.deque([1.0004, 2.0])
        assert_that(_holds(one, other, tolerance=0.001)).is_true()
        assert_that(_holds({"q": one}, {"q": other}, tolerance=0.001)).is_true()
        assert_that(_holds(one, collections.deque([1.5, 2.0]), tolerance=0.001)).is_false()
        assert_that(_holds(one, collections.deque([1.0]), tolerance=0.001)).is_false()

    def test_a_matcher_reads_it_the_same_way(self):
        expected = match.equal_to(collections.deque([True]), **STRICT)
        assert_that(expected.matches(collections.deque([1]))).is_false()
        assert_that(expected.matches(collections.deque([True]))).is_true()

    def test_a_deque_is_no_list(self):
        assert_that(_holds(collections.deque([1]), [1], **STRICT)).is_false()
        assert_that(_holds(collections.deque([1]), [1], tolerance=0.5)).is_false()

    def test_the_room_a_deque_has_is_not_what_it_holds(self):
        assert_that(_holds(collections.deque([1], maxlen=5), collections.deque([1]), **STRICT)).is_true()

    def test_a_deque_of_a_class_of_its_own_stays_with_that_class(self):
        class Ring(collections.deque):
            def __eq__(self, other: object) -> bool:
                return True

            __hash__ = None

        assert_that(_holds(Ring([1]), Ring([True]), **STRICT)).is_true()

    def test_with_no_option_a_failed_pair_prints_as_one_pair(self):
        with pytest.raises(AssertionFailure) as raised:
            assert_that(collections.deque([1, 2])).is_equal_to(collections.deque([1, 3]))
        diff = raised.value.diff
        assert diff is not None
        assert_that(diff.kind).is_equal_to("scalar")
        assert_that(diff.entries).is_length(1)


class TestAMemberMatchedByHashIsLookedInto:
    @pytest.mark.parametrize(
        ("actual", "expected"),
        [
            ({(1, 2): "a"}, {(True, 2): "a"}),
            ({(1, 2)}, {(True, 2)}),
            (frozenset({(1, 2)}), frozenset({(True, 2)})),
            ({frozenset({1})}, {frozenset({True})}),
            ({((1,), 2): "a"}, {((True,), 2): "a"}),
            ({(1, frozenset({2.0})): "a"}, {(1, frozenset({2})): "a"}),
            ({_Point(1, 2): "a"}, {_Point(True, 2): "a"}),
            ({"k": {(0, 1.0)}}, {"k": {(0, 1)}}),
            ([{(1, 2): "a"}], [{(True, 2): "a"}]),
        ],
        ids=["key", "member", "frozenset", "set in a set", "nested", "mixed", "namedtuple", "under a key", "in a list"],
    )
    def test_a_type_inside_a_key_or_a_member_fails(self, actual, expected):
        assert_that(actual).is_equal_to(expected)
        assert_that(_holds(actual, expected, **STRICT)).is_false()
        assert_that(_holds(actual, actual, **STRICT)).is_true()
        assert_that(match.equal_to(expected, **STRICT).matches(actual)).is_false()

    @pytest.mark.parametrize(
        "value",
        [{(1, 2): "a"}, {(True, 2.0), ("x", None)}, {frozenset({1, 2}): [1]}, {_Point(1, "y"): 0}, {((),): 1}],
    )
    def test_members_alike_in_type_all_the_way_down_pass(self, value):
        again = type(value)(value)
        assert_that(_holds(value, again, **STRICT)).is_true()

    def test_two_keys_that_trade_their_types_are_told_apart(self):
        """Both sides hold an `int` and a `bool`, so the classes of the keys alone say nothing."""
        assert_that(_holds({1: "a", False: "b"}, {True: "a", 0: "b"}, **STRICT)).is_false()
        assert_that(_holds({1, False}, {True, 0}, **STRICT)).is_false()
        assert_that(_holds({1: "a", False: "b"}, {False: "b", 1: "a"}, **STRICT)).is_true()

    def test_the_failure_names_the_key(self):
        paths = _paths({"a": 1, (1, 2): "b"}, {"a": 1, (True, 2): "b"}, **STRICT)
        assert_that(paths).is_length(1)
        assert_that(paths[0]).contains("(1, 2)")

    def test_a_key_option_keeps_the_keys_it_leaves_in_under_the_rule(self):
        actual, expected = {(1, 2): "a", "noise": 1}, {(True, 2): "a", "noise": 2}
        assert_that(_holds(actual, expected, ignore="noise", **STRICT)).is_false()
        assert_that(_holds(actual, {(1, 2): "a", "noise": 2}, ignore="noise", **STRICT)).is_true()

    def test_a_key_nested_past_the_recursion_limit_is_read(self):
        """Asked of the reading itself: below 3.12 ``==`` gives up on such a key before anything here is asked."""

        def nested(leaf: object) -> tuple:
            value: tuple = (leaf,)
            for _ in range(5000):
                value = (value,)
            return value

        assert_that(_compare.typed_apart(nested(1), nested(True))).is_true()
        assert_that(_compare.typed_apart(nested(1), nested(1))).is_false()

    def test_a_record_used_as_a_key_is_compared_by_its_class_alone(self):
        """The limit of the rule: a hash reads through tuples and frozensets, and those are what is read here."""

        class Key:
            def __init__(self, part: object) -> None:
                self.part = part

            def __eq__(self, other: object) -> bool:
                return type(other) is Key and self.part == other.part

            def __hash__(self) -> int:
                return hash(self.part)

        assert_that(_holds({Key(1): "a"}, {Key(True): "a"}, **STRICT)).is_true()

    def test_a_tuple_or_a_frozenset_with_an_equality_of_its_own_is_compared_by_its_class_alone(self):
        """Its ``==`` may hold two equal with nothing in them alike, so nothing pairs what they hold."""

        class Loose(frozenset):
            def __eq__(self, other: object) -> bool:
                return type(other) is Loose

            def __hash__(self) -> int:
                return 0

        class Pair(tuple):
            __slots__ = ()

            def __eq__(self, other: object) -> bool:
                return type(other) is Pair

            def __hash__(self) -> int:
                return 0

        pairs: tuple[tuple[Any, Any], ...] = (
            ({Loose({1})}, {Loose({"x"})}),
            ({Loose({1})}, {Loose({True})}),
            ({Pair((1,)): "a"}, {Pair(("x",)): "a"}),
            ({Pair((1,)): "a"}, {Pair((True,)): "a"}),
        )
        for actual, expected in pairs:
            assert_that(actual).is_equal_to(expected)
            assert_that(_holds(actual, expected, **STRICT)).is_true()
            assert_that(match.equal_to(expected, **STRICT).matches(actual)).is_true()

    def test_a_tuple_of_a_class_that_keeps_the_builtin_equality_is_read(self):
        class Named(tuple):
            __slots__ = ()

        class Kept(frozenset):
            __slots__ = ()

        assert_that(_holds({Named((1, 2)): "a"}, {Named((True, 2)): "a"}, **STRICT)).is_false()
        assert_that(_holds({Kept({1})}, {Kept({True})}, **STRICT)).is_false()
        assert_that(_holds({Named((1, 2)): "a"}, {Named((1, 2)): "a"}, **STRICT)).is_true()

    def test_a_comparator_leaves_keys_and_members_to_equality(self):
        assert_that(_holds({(1, 2): "a"}, {(True, 2): "a"}, **EXACT)).is_true()
        assert_that(_holds({(1, 2)}, {(True, 2)}, **EXACT)).is_true()


_ALIKE = {0: (0, False, 0.0), 1: (1, True, 1.0)}
"""The atoms `==` holds equal across types, which are the ones a strict comparison is there to tell apart."""

_ATOMS = st.sampled_from([0, 1, True, False, 0.0, 1.0, "a", None])
_HASHED = st.recursive(
    _ATOMS,
    lambda inner: st.one_of(st.tuples(inner), st.tuples(inner, inner), st.frozensets(inner, max_size=2)),
    max_leaves=4,
)
_VALUES = st.recursive(
    _ATOMS,
    lambda inner: st.one_of(
        st.lists(inner, max_size=3),
        st.lists(inner, max_size=3).map(tuple),
        st.lists(inner, max_size=3).map(collections.deque),
        st.dictionaries(_HASHED, inner, max_size=3),
        st.sets(_HASHED, max_size=3),
        st.dictionaries(st.sampled_from(["a", "b"]), inner, max_size=2).map(lambda fields: _User(**fields)),
    ),
    max_leaves=8,
)


def _retyped(value: Any, data: st.DataObject) -> Any:
    """*value* again, equal to it, with some of its atoms of another type: an oracle-free way to an equal pair."""
    kind = type(value)
    if kind in (list, tuple, collections.deque, set, frozenset):
        return kind(_retyped(item, data) for item in value)
    if kind is dict:
        return {_retyped(key, data): _retyped(item, data) for key, item in value.items()}
    if kind is _User:
        return _User(**{name: _retyped(item, data) for name, item in vars(value).items()})
    if kind in (int, bool, float):
        return data.draw(st.sampled_from(_ALIKE[int(value)]))
    return value


def _typed(value: Any) -> Any:
    """*value* with the type of everything in it, so two of these are equal where the values are and the types are."""
    kind = type(value)
    if kind in (list, tuple, collections.deque):
        return kind, tuple(_typed(item) for item in value)
    if kind in (set, frozenset):
        return kind, frozenset(_typed(item) for item in value)
    if kind is dict:
        return kind, frozenset((_typed(key), _typed(item)) for key, item in value.items())
    if kind is _User:
        return kind, frozenset((name, _typed(item)) for name, item in vars(value).items())
    return kind, value


@settings(deadline=None, max_examples=3000, suppress_health_check=[HealthCheck.too_slow])
@given(value=_VALUES, data=st.data())
def test_a_strict_comparison_holds_exactly_where_every_type_in_the_two_is_the_same(value, data):
    """Held to a reading written apart from the walk: the values with the type of everything in them."""
    other = _retyped(value, data)
    assert_that(value).is_equal_to(other)
    alike = _typed(value) == _typed(other)
    assert_that(_holds(value, other, **STRICT)).is_equal_to(alike)
    assert_that(match.equal_to(other, **STRICT).matches(value)).is_equal_to(alike)
    assert_that(_holds({"at": [value]}, {"at": [other]}, **STRICT)).is_equal_to(alike)
