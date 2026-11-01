"""A failed comparison says where its differences sit, when they repeat at a few places down a sequence.

Forty rows that differ in one field are forty rows of diff to read before that can be said.  Past the fiftieth
the rows are not printed, so one difference of another field among them went unseen.  The line counts every
entry of the diff, printed or not, and names each place as the path with every position made ``[*]``.

It is read off the entries the comparison already made: no value is compared again and none is printed.  It
stands under whatever line says why, and where two places would read the same it is not said at all.
"""

from __future__ import annotations

import dataclasses

import pytest

from assertpy import AssertionFailure, assert_that, soft_assertions
from assertpy._hints import placed
from assertpy.errors import DiffEntry, DiffResult, Step, _render_diff


def _rows(count: int, stamp: str = "10:00") -> list[dict[str, object]]:
    return [{"id": index, "name": f"user{index}", "updated_at": f"{stamp}:{index:02d}"} for index in range(count)]


def _failure(actual: object, expected: object, **options: object) -> AssertionFailure:
    with pytest.raises(AssertionFailure) as caught:
        assert_that(actual).is_equal_to(expected, **options)
    return caught.value


def _lines(failure: AssertionFailure) -> list[str]:
    return failure._message.splitlines()[1:]


@dataclasses.dataclass
class _User:
    id: int
    seen: str


class _Counted:
    asked = 0

    def __init__(self, held: int) -> None:
        self.held = held

    def __eq__(self, other: object) -> bool:
        type(self).asked += 1
        return isinstance(other, _Counted) and self.held == other.held

    __hash__ = None  # ty: ignore[invalid-assignment]  # a class that defines `__eq__` alone is unhashable anyway

    def __repr__(self) -> str:
        type(self).asked += 1000
        return f"counted({self.held})"


class TestWhereTheDifferencesSit:
    def test_one_field_down_a_list(self):
        failure = _failure(_rows(40), _rows(40, "11:00"))
        assert_that(_lines(failure)).is_equal_to(["all 40 differences here are at <[*].updated_at>"])

    def test_the_fifty_first_difference_is_counted_though_it_is_not_printed(self):
        actual, expected = _rows(51), _rows(51, "11:00")
        expected[50] = dict(actual[50], name="other")
        failure = _failure(actual, expected)
        assert_that(_lines(failure)).is_equal_to(
            ["the 51 differences here are at <[*].updated_at> (50) and <[*].name> (1)"]
        )
        assert_that(_render_diff(failure.diff)).does_not_contain("[50].name").contains("... and 1 more")

    def test_under_a_key_and_through_a_record(self):
        failure = _failure({"items": _rows(4)}, {"items": _rows(4, "11:00")})
        assert_that(_lines(failure)).is_equal_to(["all 4 differences here are at <items[*].updated_at>"])
        users = _failure([_User(index, "x") for index in range(3)], [_User(index, "y") for index in range(3)])
        assert_that(_lines(users)).is_equal_to(["all 3 differences here are at <[*].seen>"])

    def test_three_places_by_how_many_and_then_by_which_came_first(self):
        actual = [{"a": 1, "b": 1, "c": 1}, {"a": 1, "b": 1, "c": 1}, {"a": 1, "b": 9, "c": 9}]
        expected = [{"a": 2, "b": 2, "c": 2}, {"a": 2, "b": 2, "c": 1}, {"a": 2, "b": 9, "c": 9}]
        assert_that(_lines(_failure(actual, expected))).is_equal_to(
            ["the 6 differences here are at <[*].a> (3), <[*].b> (2) and <[*].c> (1)"]
        )

    def test_the_place_met_first_is_not_named_first_for_that(self):
        actual = [{"a": 1, "b": 1}, {"a": 1, "b": 1}, {"a": 1, "b": 1}]
        expected = [{"a": 2, "b": 2}, {"a": 1, "b": 2}, {"a": 1, "b": 2}]
        assert_that(_lines(_failure(actual, expected))).is_equal_to(
            ["the 4 differences here are at <[*].b> (3) and <[*].a> (1)"]
        )

    def test_a_field_missing_in_every_row_is_a_difference_at_it(self):
        expected = [{key: value for key, value in row.items() if key != "updated_at"} for row in _rows(3)]
        assert_that(_lines(_failure(_rows(3), expected))).contains("all 3 differences here are at <[*].updated_at>")

    def test_it_stands_under_the_line_that_says_why(self):
        failure = _failure([{"id": index} for index in range(4)], [{"id": str(index)} for index in range(4)])
        assert_that(_lines(failure)).is_equal_to(
            [
                "every difference here is the same text against a value of another type",
                "all 4 differences here are at <[*].id>",
            ]
        )
        beside_a_nan = _failure([{"n": float("nan")} for _ in range(3)], [{"n": float("nan")} for _ in range(3)])
        assert_that(_lines(beside_a_nan)[-1]).is_equal_to("all 3 differences here are at <[*].n>")
        assert_that(_lines(beside_a_nan)[0]).starts_with("a NaN takes part in this comparison")

    def test_a_soft_block_keeps_it(self):
        with pytest.raises(AssertionError) as caught, soft_assertions():
            assert_that(_rows(3)).is_equal_to(_rows(3, "11:00"))
        assert_that(str(caught.value)).contains("all 3 differences here are at <[*].updated_at>")

    def test_under_a_key_option_it_counts_what_was_compared(self):
        actual, expected = _rows(3), [dict(row, name="other") for row in _rows(3, "11:00")]
        failure = _failure(actual, expected, ignore="updated_at")
        assert_that(_lines(failure)).is_equal_to(["all 3 differences here are at <[*].name>"])


class TestWhereNothingIsSaid:
    @pytest.mark.parametrize(
        ("actual", "expected"),
        [
            pytest.param(_rows(2), _rows(2, "11:00"), id="two differences"),
            pytest.param({"a": 1, "b": 2, "c": 3}, {"a": 2, "b": 3, "c": 4}, id="no position on the path"),
            pytest.param([1, 2, 3, 4], [5, 6, 7, 8], id="no name on the path"),
            pytest.param([[1], [2], [3]], [[4], [5], [6]], id="positions alone"),
            pytest.param(
                [{"a": 1, "b": 1, "c": 1, "d": 1}] * 2, [{"a": 2, "b": 2, "c": 2, "d": 2}] * 2, id="four places"
            ),
            pytest.param([{"a": 1}, {"b": 1}, {"c": 1}], [{"a": 2}, {"b": 2}, {"c": 2}], id="three places, none twice"),
            pytest.param([{1: "x"}] * 3, [{1: "y"}] * 3, id="a key that is no text"),
            pytest.param({"s": {1, 2, 3}}, {"s": {4, 5, 6}}, id="members of a set"),
        ],
    )
    def test_no_line(self, actual, expected):
        failure = _failure(actual, expected)
        assert_that([line for line in _lines(failure) if "differences here are at" in line]).is_empty()

    def test_a_key_and_a_field_of_one_name_are_two_places_that_read_as_one(self):
        entries = [
            DiffEntry(path=f"[{index}].name", actual=1, expected=2, steps=(Step("index", index), Step(kind, "name")))
            for index, kind in enumerate(["key", "key", "attr", "attr"])
        ]
        assert_that(placed(DiffResult(kind="sequence", entries=entries))).is_none()
        alike = [dataclasses.replace(entry, steps=(entry.steps[0], Step("key", "name"))) for entry in entries]
        assert_that(placed(DiffResult(kind="sequence", entries=alike))).is_equal_to(
            "all 4 differences here are at <[*].name>"
        )

    def test_a_key_holding_a_dot_is_quoted_and_so_is_not_the_path_it_looks_like(self):
        nested = [
            DiffEntry(path="x", actual=1, expected=2, steps=(Step("index", 0), Step("key", "a"), Step("key", "b")))
        ]
        dotted = [DiffEntry(path="x", actual=1, expected=2, steps=(Step("index", 0), Step("key", "a.b")))]
        assert_that(placed(DiffResult(kind="sequence", entries=[*nested * 2, *dotted * 2]))).is_equal_to(
            "the 4 differences here are at <[*].a.b> (2) and <[*]['a.b']> (2)"
        )

    def test_a_member_of_a_set_or_a_line_of_a_text_is_no_place(self):
        for last in (Step("item", 7), Step("line", 2)):
            entries = [
                DiffEntry(
                    path="x", actual=1, absent="expected", steps=(Step("index", index), Step("key", "tags"), last)
                )
                for index in range(3)
            ]
            assert_that(placed(DiffResult(kind="sequence", entries=entries))).is_none()

    def test_a_name_that_is_no_identifier_is_quoted_and_cannot_break_the_line(self):
        rows = [{"a.b": 1, "x\ny": 1, "first name": 1} for _ in range(3)]
        other = [{"a.b": 2, "x\ny": 2, "first name": 2} for _ in range(3)]
        (line,) = _lines(_failure(rows, other))
        assert_that(line).is_equal_to(
            "the 9 differences here are at <[*]['a.b']> (3), <[*]['x\\ny']> (3) and <[*]['first name']> (3)"
        )

    def test_a_name_too_long_to_be_a_line_is_not_said(self):
        key = "k" * 300
        failure = _failure([{key: 1}] * 3, [{key: 2}] * 3)
        assert_that(_lines(failure)).is_empty()
        assert_that(_lines(_failure([{"k" * 150: 1}] * 3, [{"k" * 150: 2}] * 3))).is_length(1)

    def test_a_diff_of_another_kind_and_no_diff(self):
        entries = [
            DiffEntry(path="x", actual=1, expected=2, steps=(Step("index", index), Step("key", "a")))
            for index in range(3)
        ]
        assert_that(placed(DiffResult(kind="contains", entries=entries))).is_none()
        assert_that(placed(DiffResult(kind="sequence", entries=entries))).is_not_none()
        assert_that(placed(None)).is_none()


class TestItIsReadOffTheEntries:
    def test_no_value_is_compared_or_printed_for_it(self):
        entries = [
            DiffEntry(
                path=f"[{index}].held",
                actual=_Counted(index),
                expected=_Counted(index + 1),
                steps=(Step("index", index), Step("key", "held")),
            )
            for index in range(200)
        ]
        _Counted.asked = 0
        assert_that(placed(DiffResult(kind="sequence", entries=entries))).is_equal_to(
            "all 200 differences here are at <[*].held>"
        )
        assert_that(_Counted.asked).is_zero()

    def test_text_that_is_json_is_stepped_through(self):
        entries = [
            DiffEntry(
                path=f"[{index}].id",
                actual=1,
                expected=2,
                steps=(Step("json", None), Step("index", index), Step("key", "id")),
            )
            for index in range(3)
        ]
        assert_that(placed(DiffResult(kind="sequence", entries=entries))).is_equal_to(
            "all 3 differences here are at <[*].id>"
        )
