"""A failed ``contains`` says what a failed ``is_equal_to`` says: the nearest thing there is, and why it is not it.

Two things are held.  The closest element is named for a row of any kind, a dict, a dataclass, a named tuple,
and for a key whose value reads the same in another type, the id a payload spells as text.  And one line is
said of the item that was not found where a fact about that item explains it: it is a NaN, an element reads
the same and is of another plain type, or an element prints the same and their class compares by identity.

The line is about the item sought.  A NaN elsewhere in the collection explains nothing about a ``2`` that is
missing from it, so nothing is said then.
"""

from __future__ import annotations

import collections
import dataclasses
import enum

import pytest

from assertpy import AssertionFailure, assert_that, match, soft_assertions
from assertpy._hints import not_found, reads_as

_NAN_SOUGHT = "the item not found is a NaN, and one NaN is not equal to another"
_IDENTITY_SOUGHT = (
    "an element prints the same as the item not found, and their class leaves __eq__ to object,"
    " which compares by identity"
)
_TYPED = "an element reads the same as the item not found and is of another type: "


@dataclasses.dataclass
class User:
    id: int
    name: str
    email: str = "x"


class _Hidden:
    def __init__(self, held: int) -> None:
        self.held = held

    def __repr__(self) -> str:
        return "hidden"


class _Judged:
    """Prints the same whatever it holds, and compares by what it holds."""

    def __init__(self, held: int) -> None:
        self.held = held

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _Judged) and self.held == other.held

    __hash__ = None  # ty: ignore[invalid-assignment]  # a class that defines `__eq__` alone is unhashable anyway

    def __repr__(self) -> str:
        return "judged"


class _Never:
    """A matcher of a caller's own that nothing matches, and that prints the same every time."""

    def matches(self, value: object) -> bool:
        return False

    def describe(self) -> str:
        return "never"

    def describe_mismatch(self, value: object) -> str:
        return "was something"

    def __repr__(self) -> str:
        return "never"


class _Colour(enum.Enum):
    RED = 1
    GREEN = 2


def _message(call) -> str:
    with pytest.raises(AssertionFailure) as caught:
        call()
    return caught.value._message


class TestTheItemNotFoundIsExplained:
    def test_a_nan(self):
        message = _message(lambda: assert_that([float("nan"), 1]).contains(float("nan")))
        assert_that(message.splitlines()).is_equal_to(
            ["Expected <[nan, 1]> to contain item <nan>, but did not.", _NAN_SOUGHT]
        )

    def test_a_nan_elsewhere_in_the_collection_explains_nothing(self):
        message = _message(lambda: assert_that([float("nan"), 1]).contains(2))
        assert_that(message).is_equal_to("Expected <[nan, 1]> to contain item <2>, but did not.")

    def test_the_very_nan_the_collection_holds_is_found(self):
        nan = float("nan")
        assert_that([nan, 1]).contains(nan)

    def test_an_instance_that_prints_like_one_in_the_collection_and_compares_by_identity(self):
        for held, sought in ((ValueError("x"), ValueError("x")), (_Hidden(1), _Hidden(2))):
            message = _message(lambda held=held, sought=sought: assert_that([held]).contains(sought))
            assert_that(message.splitlines()[1]).is_equal_to(_IDENTITY_SOUGHT)

    @pytest.mark.parametrize(
        ("held", "sought"),
        [
            pytest.param([1, 2], None, id="None"),
            pytest.param([_Colour.RED], _Colour.GREEN, id="an enum member"),
            pytest.param([_Hidden(1)], object(), id="an object of another class"),
            pytest.param([User(1, "a")], User(1, "a", "y"), id="a class with an equality of its own"),
            pytest.param([_Judged(1)], _Judged(2), id="one that prints the same and has an equality of its own"),
            pytest.param([7, 8], 9, id="a number that is not there"),
            pytest.param([7.5], "7", id="texts that differ"),
            pytest.param([b"7"], "7", id="bytes are no plain text"),
        ],
    )
    def test_nothing_is_said_where_no_fact_about_the_item_explains_it(self, held, sought):
        assert_that(not_found(sought, held)).is_none()

    @pytest.mark.parametrize(
        ("held", "sought", "types"),
        [
            ([7, 8], "7", "int, not str"),
            (["7"], 7, "str, not int"),
            ([1.5], "1.5", "float, not str"),
            (["True"], True, "str, not bool"),
        ],
    )
    def test_a_plain_value_that_reads_the_same_in_another_type(self, held, sought, types):
        message = _message(lambda: assert_that(held).contains(sought))
        assert_that(message.splitlines()[1]).is_equal_to(f"{_TYPED}{types}")

    def test_a_key_that_reads_the_same_in_another_type(self):
        message = _message(lambda: assert_that({"7": 1}).contains(7))
        assert_that(message.splitlines()).is_equal_to(
            [
                "Expected <{'7': 1}> to contain key <7>, but did not.",
                "a key reads the same as the key not found and is of another type: str, not int",
            ]
        )

    def test_two_plain_values_of_one_type_or_of_no_plain_type_do_not_read_as_each_other(self):
        assert_that(reads_as(7, "7")).is_true()
        assert_that(reads_as("7", "7")).is_false()
        assert_that(reads_as(7, 7.0)).is_false()
        assert_that(reads_as(b"7", "b'7'")).is_false()

    def test_one_item_not_found_among_several_asked_for_has_its_line(self):
        message = _message(lambda: assert_that([1, 5]).contains(float("nan"), 5))
        assert_that(message.splitlines()).is_equal_to(
            ["Expected <[1, 5]> to contain items <nan, 5>, but did not contain <nan>.", _NAN_SOUGHT]
        )

    def test_several_items_not_found_have_none(self):
        message = _message(lambda: assert_that([1]).contains(float("nan"), 5))
        assert_that(message).is_equal_to("Expected <[1]> to contain items <nan, 5>, but did not contain <nan, 5>.")

    def test_a_matcher_not_matched_has_none(self):
        message = _message(lambda: assert_that([1.0]).contains(match.is_instance_of(str)))
        assert_that(message.splitlines()).is_length(1)
        message = _message(lambda: assert_that([1.0, 2.0]).contains(1.0, match.is_instance_of(str)))
        assert_that(message.splitlines()).is_length(1)

    def test_a_matcher_is_no_item_even_beside_one_that_prints_like_it(self):
        # read as an item, it would be an instance that prints like an element and compares by identity
        message = _message(lambda: assert_that([_Never(), 1]).contains(1, _Never()))
        assert_that(message.splitlines()).is_length(1)

    def test_a_soft_block_keeps_the_line(self):
        with pytest.raises(AssertionError) as caught, soft_assertions():
            assert_that([7, 8]).contains("7")
        assert_that(str(caught.value)).contains(f"{_TYPED}int, not str")

    def test_an_element_that_cannot_be_printed_costs_only_the_line(self):
        class Unprintable:
            def __repr__(self) -> str:
                raise RuntimeError("no repr")

        class Raising:
            def __iter__(self):
                raise RuntimeError("no iteration")

        assert_that(not_found(Unprintable(), [Unprintable()])).is_equal_to(_IDENTITY_SOUGHT)
        assert_that(not_found(1, Raising())).is_none()

    def test_a_class_given_an_equality_while_it_is_printed_is_not_said_to_compare_by_identity(self):
        class Shifting:
            def __repr__(self) -> str:
                type(self).__eq__ = lambda self, other: False  # ty: ignore[invalid-assignment]  # the point of the test
                return "shifting"

        assert_that(not_found(Shifting(), [Shifting()])).is_none()

    def test_the_line_is_asked_for_past_the_printing_of_the_sentence(self):
        class Late:
            printed = 0

            def __repr__(self) -> str:
                kind = type(self)
                kind.printed += 1
                if kind.printed == 3:
                    kind.__eq__ = lambda self, other: False  # ty: ignore[invalid-assignment]  # the point of the test
                return "late"

        message = _message(lambda: assert_that([Late(), 1]).contains(1, Late()))
        assert_that(message).is_equal_to("Expected <[late, 1]> to contain items <1, late>, but did not contain <late>.")


class TestTheClosestElement:
    def test_a_dict_row(self):
        rows = [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}]
        message = _message(lambda: assert_that(rows).contains({"id": 2, "name": "c"}))
        assert_that(message).ends_with("Closest element <{'id': 2, 'name': 'b'}> differs at name ('b' != 'c').")

    def test_a_dataclass_row(self):
        with pytest.raises(AssertionFailure) as caught:
            assert_that([User(1, "a"), User(2, "b")]).contains(User(2, "c"))
        assert_that(caught.value._message).ends_with(
            "Closest element <User(id=2, name='b', email='x')> differs at .name ('b' != 'c')."
        )
        assert_that([(entry.path, entry.actual, entry.expected) for entry in caught.value.diff.entries]).is_equal_to(
            [(".name", "b", "c")]
        )

    def test_a_named_tuple_row(self):
        point = collections.namedtuple("point", "x y")
        message = _message(lambda: assert_that([point(1, 2), point(3, 4)]).contains(point(3, 5)))
        assert_that(message).contains("Closest element <point(x=3, y=4)> differs at")

    def test_the_row_with_the_fewest_differences_is_the_one_named(self):
        rows = [User(1, "a", "p"), User(1, "b", "q"), User(2, "b", "q")]
        message = _message(lambda: assert_that(rows).contains(User(1, "b", "r")))
        assert_that(message).contains(
            "Closest element <User(id=1, name='b', email='q')> differs at .email ('q' != 'r')."
        )

    def test_a_key_that_reads_the_same_in_another_type_makes_a_row_the_closest(self):
        message = _message(lambda: assert_that([{"id": 7}]).contains({"id": "7"}))
        assert_that(message).is_equal_to(
            "Expected <[{'id': 7}]> to contain item <{'id': '7'}>, but did not."
            " Closest element <{'id': 7}> differs at id (7 != '7')."
        )

    def test_a_row_that_shares_nothing_is_not_offered(self):
        message = _message(lambda: assert_that([User(1, "a", "p")]).contains(User(2, "c", "q")))
        assert_that(message).does_not_contain("Closest element")

    def test_a_row_of_another_shape_is_not_offered(self):
        message = _message(lambda: assert_that([{"id": 2, "name": "b", "email": "x"}]).contains(User(2, "c")))
        assert_that(message).does_not_contain("Closest element")

    def test_a_row_that_cannot_be_read_costs_the_closest_element_and_not_the_failure(self):
        token = dataclasses.make_dataclass("Token", [("value", str), ("kind", str)], eq=False)
        held, sought = token("a", "k"), token("b", "k")
        del held.value
        with pytest.raises(AssertionFailure) as caught:
            assert_that([held]).contains(sought)
        assert_that(caught.value._message).contains("to contain item <Token(value='b', kind='k')>, but did not.")
        assert_that(caught.value._message).does_not_contain("Closest element")

    def test_two_records_the_walk_finds_nothing_under_get_the_line_and_no_closest_element(self):
        token = dataclasses.make_dataclass("Token", [("value", str)], eq=False)
        message = _message(lambda: assert_that([token("a")]).contains(token("a")))
        assert_that(message.splitlines()).is_equal_to(
            ["Expected <[Token(value='a')]> to contain item <Token(value='a')>, but did not.", _IDENTITY_SOUGHT]
        )
