import subprocess
import sys
from collections import namedtuple
from collections.abc import Mapping
from dataclasses import dataclass

import pytest

from assertpy import assert_that, match
from assertpy._engine import _diff as _diff_module
from assertpy._engine._compare import _build_compare_config
from assertpy._engine._diff import _build_equality_diff, _sub_diff_entries
from assertpy._engine._path import _Path
from assertpy.errors import DiffEntry, DiffResult, _cut, _within_budget
from assertpy.helpers import HelpersMixin
from assertpy.pytest_plugin import _format_diff


class _Boxed:
    """Unhashable, so the alignment keys on the repr - which every instance shares."""

    __hash__ = None

    def __init__(self, value):
        self.value = value

    def __eq__(self, other):
        return isinstance(other, _Boxed) and self.value == other.value

    def __repr__(self):
        return "<boxed>"


class _FakeModel:
    """A pydantic-shaped object: the engine reads ``model_dump()`` and never imports pydantic."""

    def __init__(self, **fields):
        self._fields = fields

    def model_dump(self):
        return dict(self._fields)

    def __eq__(self, other):
        return isinstance(other, _FakeModel) and self._fields == other._fields

    def __hash__(self):
        return id(self)

    def __repr__(self):
        return f"_FakeModel({sorted(self._fields)})"


class TestBuildEqualityDiffSequence:
    def test_lists_equal_length_one_diff(self):
        result = _build_equality_diff([1, 2, 3], [1, 9, 3])
        assert_that(result.kind).is_equal_to("sequence")
        assert_that(result.entries).is_length(1)
        assert_that(result.entries[0].path).is_equal_to("[1]")
        assert_that(result.entries[0].actual).is_equal_to(2)
        assert_that(result.entries[0].expected).is_equal_to(9)

    def test_actual_longer(self):
        result = _build_equality_diff([1, 2, 3], [1])
        assert_that(result.kind).is_equal_to("sequence")
        assert_that(result.entries).is_length(2)
        assert_that(result.entries[0].actual).is_equal_to(2)
        assert_that(result.entries[0].expected).is_none()
        assert_that(result.entries[1].actual).is_equal_to(3)
        assert_that(result.entries[1].expected).is_none()

    def test_expected_longer(self):
        result = _build_equality_diff([1], [1, 2, 3])
        assert_that(result.kind).is_equal_to("sequence")
        assert_that(result.entries).is_length(2)
        assert_that(result.entries[0].actual).is_none()
        assert_that(result.entries[0].expected).is_equal_to(2)

    def test_tuples(self):
        result = _build_equality_diff((1, 2), (1, 3))
        assert_that(result.kind).is_equal_to("sequence")
        assert_that(result.entries).is_length(1)
        assert_that(result.entries[0].path).is_equal_to("[1]")

    def test_all_different(self):
        result = _build_equality_diff([1, 2], [3, 4])
        assert_that(result.kind).is_equal_to("sequence")
        assert_that(result.entries).is_length(2)

    def test_empty_vs_nonempty(self):
        result = _build_equality_diff([], [1, 2])
        assert_that(result.kind).is_equal_to("sequence")
        assert_that(result.entries).is_length(2)
        assert_that(result.entries[0].actual).is_none()
        assert_that(result.entries[0].expected).is_equal_to(1)


class TestBuildEqualityDiffSet:
    def test_a_set_against_a_non_set_is_a_scalar_difference(self):
        with pytest.raises(AssertionError):
            assert_that({1, 2}).is_equal_to([1, 2])
        assert_that(_build_equality_diff({1, 2}, [1, 2]).kind).is_equal_to("scalar")
        assert_that(_build_equality_diff(frozenset({1, 2}), 7).kind).is_equal_to("scalar")

    def test_extra_items(self):
        result = _build_equality_diff({1, 2, 3}, {1})
        assert_that(result.kind).is_equal_to("set")
        extra = [entry for entry in result.entries if entry.path == "extra"]
        assert_that(extra).is_length(2)
        assert_that([entry.expected for entry in extra]).each(match.is_none())

    def test_missing_items(self):
        result = _build_equality_diff({1}, {1, 2, 3})
        assert_that(result.kind).is_equal_to("set")
        missing = [entry for entry in result.entries if entry.path == "missing"]
        assert_that(missing).is_length(2)
        assert_that([entry.actual for entry in missing]).each(match.is_none())

    def test_both_extra_and_missing(self):
        result = _build_equality_diff({1, 2}, {2, 3})
        assert_that(result.kind).is_equal_to("set")
        extra = [entry for entry in result.entries if entry.path == "extra"]
        missing = [entry for entry in result.entries if entry.path == "missing"]
        assert_that(extra).is_length(1)
        assert_that(extra[0].actual).is_equal_to(1)
        assert_that(missing).is_length(1)
        assert_that(missing[0].expected).is_equal_to(3)

    def test_frozenset(self):
        result = _build_equality_diff(frozenset({1, 2}), frozenset({2, 3}))
        assert_that(result.kind).is_equal_to("set")
        assert_that(result.entries).is_length(2)

    def test_members_that_cannot_be_ordered_are_sorted_by_their_repr(self):
        # sorting the members themselves raises as soon as a set holds more than one type
        result = _build_equality_diff({1, "a"}, {2, "b"})
        extra = [entry.actual for entry in result.entries if entry.path == "extra"]
        missing = [entry.expected for entry in result.entries if entry.path == "missing"]
        assert_that(extra).is_equal_to(["a", 1])
        assert_that(missing).is_equal_to(["b", 2])


class TestBuildEqualityDiffString:
    def test_single_line_diff(self):
        result = _build_equality_diff("hello", "world")
        assert_that(result.kind).is_equal_to("string")
        assert_that(result.entries).is_length(1)
        assert_that(result.entries[0].path).is_equal_to("line 1")
        assert_that(result.entries[0].actual).is_equal_to("hello")
        assert_that(result.entries[0].expected).is_equal_to("world")

    def test_multiline_one_changed(self):
        result = _build_equality_diff("a\nb\nc", "a\nX\nc")
        assert_that(result.kind).is_equal_to("string")
        assert_that(result.entries).is_length(1)
        assert_that(result.entries[0].path).is_equal_to("line 2")
        assert_that(result.entries[0].actual).is_equal_to("b")
        assert_that(result.entries[0].expected).is_equal_to("X")

    def test_actual_more_lines(self):
        result = _build_equality_diff("a\nb\nc", "a")
        assert_that(result.kind).is_equal_to("string")
        assert_that(result.entries).is_length(2)
        assert_that(result.entries[0].actual).is_equal_to("b")
        assert_that(result.entries[0].expected).is_none()

    def test_expected_more_lines(self):
        result = _build_equality_diff("a", "a\nb\nc")
        assert_that(result.kind).is_equal_to("string")
        assert_that(result.entries).is_length(2)
        assert_that(result.entries[0].actual).is_none()
        assert_that(result.entries[0].expected).is_equal_to("b")

    def test_str_subclass_against_plain_str(self):
        # StrEnum members are str subclasses compared to plain strings, so the text path cannot need an exact type
        class _Tag(str):
            pass

        result = _build_equality_diff(_Tag("hello"), "world")
        assert_that(result.kind).is_equal_to("string")

    def test_bytes_are_diffed_as_text_but_never_mixed_with_str(self):
        assert_that(_build_equality_diff(b"abc", b"aXc").kind).is_equal_to("string")
        assert_that(_build_equality_diff(bytearray(b"abc"), b"aXc").kind).is_equal_to("string")
        assert_that(_build_equality_diff(b"abc", "abc").kind).is_equal_to("scalar")

    def test_identical_content_different_object(self):
        left = "hello"
        right = "".join(["h", "e", "l", "l", "o"])
        result = _build_equality_diff(left, right)
        assert_that(result.kind).is_equal_to("string")
        assert_that([entry.path for entry in result.entries]).is_in([], ["."])


class TestBuildEqualityDiffScalar:
    def test_int(self):
        result = _build_equality_diff(1, 2)
        assert_that(result.kind).is_equal_to("scalar")
        assert_that(result.entries).is_length(1)
        assert_that(result.entries[0].path).is_equal_to(".")
        assert_that(result.entries[0].actual).is_equal_to(1)
        assert_that(result.entries[0].expected).is_equal_to(2)

    def test_mixed_types(self):
        result = _build_equality_diff(42, "forty-two")
        assert_that(result.kind).is_equal_to("scalar")
        assert_that(result.entries).is_length(1)

    def test_none_vs_value(self):
        result = _build_equality_diff(None, 42)
        assert_that(result.kind).is_equal_to("scalar")

    def test_bool(self):
        result = _build_equality_diff(True, False)
        assert_that(result.kind).is_equal_to("scalar")


class TestBuildEqualityDiffDataclass:
    def test_field_difference(self):
        @dataclass
        class User:
            name: str
            age: int

        result = _build_equality_diff(User("Alice", 30), User("Alice", 31))
        assert_that(result.kind).is_equal_to("dataclass")
        assert_that(result.entries).is_length(1)
        assert_that(result.entries[0].path).is_equal_to(".age")
        assert_that(result.entries[0].actual).is_equal_to(30)
        assert_that(result.entries[0].expected).is_equal_to(31)

    def test_multiple_differences(self):
        @dataclass
        class Point:
            x: int
            y: int

        result = _build_equality_diff(Point(1, 2), Point(3, 4))
        assert_that(result.kind).is_equal_to("dataclass")
        assert_that(result.entries).is_length(2)

    def test_all_same(self):
        @dataclass
        class Item:
            name: str

        # handed over as unequal, with no field to show for it: the pair is the entry
        result = _build_equality_diff(Item("a"), Item("a"))
        assert_that(result.kind).is_equal_to("dataclass")
        assert_that([(entry.path, entry.actual) for entry in result.entries]).is_equal_to([(".", Item("a"))])

    def test_different_dataclass_types(self):
        @dataclass
        class A:
            x: int
            y: int

        @dataclass
        class B:
            x: int
            z: int

        result = _build_equality_diff(A(1, 2), B(1, 99))
        assert_that(result.kind).is_equal_to("dataclass")
        paths = [entry.path for entry in result.entries]
        assert_that(paths).contains(".y")
        assert_that(paths).contains(".z")
        y_entry = next(entry for entry in result.entries if entry.path == ".y")
        z_entry = next(entry for entry in result.entries if entry.path == ".z")
        assert_that(y_entry.expected).is_none()
        assert_that(z_entry.actual).is_none()


class TestBuildEqualityDiffNamedtuple:
    def test_field_difference(self):
        Point = namedtuple("Point", ["x", "y"])
        result = _build_equality_diff(Point(1, 2), Point(1, 99))
        assert_that(result.kind).is_equal_to("namedtuple")
        assert_that(result.entries).is_length(1)
        assert_that(result.entries[0].path).is_equal_to(".y")
        assert_that(result.entries[0].actual).is_equal_to(2)
        assert_that(result.entries[0].expected).is_equal_to(99)

    def test_all_same(self):
        Point = namedtuple("Point", ["x", "y"])
        result = _build_equality_diff(Point(1, 2), Point(1, 2))
        assert_that(result.kind).is_equal_to("namedtuple")
        assert_that([(entry.path, entry.actual) for entry in result.entries]).is_equal_to([(".", Point(1, 2))])

    def test_different_types_with_fields(self):
        A = namedtuple("A", ["x", "y"])
        B = namedtuple("B", ["x", "z"])
        result = _build_equality_diff(A(1, 2), B(1, 99))
        assert_that(result.kind).is_equal_to("namedtuple")
        paths = [entry.path for entry in result.entries]
        assert_that(paths).contains(".y")
        assert_that(paths).contains(".z")


class TestBuildEqualityDiffRecursive:
    def test_dict_in_list(self):
        actual = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
        expected = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Robert"}]
        result = _build_equality_diff(actual, expected)
        assert_that(result.kind).is_equal_to("sequence")
        assert_that(result.entries).is_length(1)
        assert_that(result.entries[0].path).is_equal_to("[1].name")
        assert_that(result.entries[0].actual).is_equal_to("Bob")
        assert_that(result.entries[0].expected).is_equal_to("Robert")

    def test_dict_in_list_added_key(self):
        actual = [{"a": 1}]
        expected = [{"a": 1, "b": 2}]
        result = _build_equality_diff(actual, expected)
        assert_that(result.kind).is_equal_to("sequence")
        assert_that(result.entries[0].path).is_in("[1].b", "[0].b")
        assert_that(result.entries[0].actual).is_none()
        assert_that(result.entries[0].expected).is_equal_to(2)

    def test_dataclass_in_list(self):
        @dataclass
        class Item:
            name: str
            value: int

        actual = [Item("x", 1), Item("y", 2)]
        expected = [Item("x", 1), Item("y", 99)]
        result = _build_equality_diff(actual, expected)
        assert_that(result.kind).is_equal_to("sequence")
        assert_that(result.entries).is_length(1)
        assert_that(result.entries[0].path).is_equal_to("[1].value")
        assert_that(result.entries[0].actual).is_equal_to(2)
        assert_that(result.entries[0].expected).is_equal_to(99)

    def test_non_dict_elements_stay_flat(self):
        result = _build_equality_diff([1, "a"], [1, "b"])
        assert_that(result.kind).is_equal_to("sequence")
        assert_that(result.entries).is_length(1)
        assert_that(result.entries[0].path).is_equal_to("[1]")
        assert_that(result.entries[0].actual).is_equal_to("a")

    def test_recursive_dict_removed_key(self):
        actual = [{"a": 1, "b": 2}]
        expected = [{"a": 1}]
        result = _build_equality_diff(actual, expected)
        assert_that([entry.path for entry in result.entries]).contains("[0].b")


class TestContainsDiff:
    @pytest.mark.parametrize(
        ("ask", "rows"),
        [
            (lambda: assert_that([{"id": 1}]).contains({"id": 99}), ["  missing: {'id': 99}"]),
            (lambda: assert_that([1, 2]).contains(3, 4), ["  missing: 3, 4"]),
            (lambda: assert_that([1, 2]).contains_only(1, 3), ["  extra:   2", "  missing: 3"]),
            (lambda: assert_that([{1}]).contains({2}), ["  missing: {2}"]),
        ],
        ids=["a dict", "two items", "one too many and one short", "a set looked for"],
    )
    def test_the_items_are_printed_as_they_are_with_no_braces_round_them(self, ask, rows):
        # braces round a dict looked for in a list read `missing: {{'id': 99}}`, a set no Python holds
        with pytest.raises(AssertionError) as exc_info:
            ask()
        assert_that(str(exc_info.value.diff).splitlines()).is_equal_to(["diff (contains):", *rows])

    def test_two_sets_found_unequal_that_hold_the_same_members_differ_as_a_pair(self):
        # a diff with no entry rendered as nothing, under a failure that said the two were not equal
        class Odd(set):
            def __eq__(self, other: object) -> bool:
                return False

            __hash__ = None  # ty: ignore[invalid-assignment, invalid-method-override]  # a set is unhashable anyway

        for held in (Odd(), Odd({1})):
            operand = set(held)
            result = _build_equality_diff(held, operand)
            assert_that((result.kind, len(result.entries))).is_equal_to(("scalar", 1))
            assert_that(result.entries[0].actual).is_same_as(held)
            assert_that(result.entries[0].expected).is_same_as(operand)
            with pytest.raises(AssertionError) as plain:
                assert_that(held).is_equal_to(operand)
            with pytest.raises(AssertionError) as named:
                assert_that({"items": held}).has_items(operand)
            for failure in (plain.value, named.value):
                assert_that([(entry.actual, entry.expected) for entry in failure.diff.entries]).is_length(1)
        config = _build_compare_config(None, None, strict_types=True)
        assert_that(_build_equality_diff({1}, {1}, config=config).entries).is_empty()

    def test_the_members_of_a_set_keep_the_braces_of_a_set(self):
        rendered = str(_build_equality_diff({1, 3}, {1, 2}))
        assert_that(rendered.splitlines()).is_equal_to(["diff (set):", "  extra:   {3}", "  missing: {2}"])

    def test_color_wraps_the_row_whichever_way_it_is_written(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that([{"id": 1}]).contains({"id": 99})
        assert_that(_format_diff(exc_info.value.diff, color=True)).ends_with("\033[32mmissing: {'id': 99}\033[0m")
        colored = _format_diff(_build_equality_diff({1, 3}, {1, 2}), color=True)
        assert_that(colored).contains("\033[31mextra:   {3}\033[0m").ends_with("\033[32mmissing: {2}\033[0m")

    def test_contains_missing_items_diff(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that([1, 2, 3]).contains(7, 9)
        exc = exc_info.value
        assert_that(getattr(exc, "diff", None)).is_not_none()
        assert_that(exc.diff.kind).is_equal_to("contains")
        missing = [entry for entry in exc.diff.entries if entry.path == "missing"]
        assert_that(missing).is_length(2)

    def test_contains_single_item_diff(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that([1, 2]).contains(9)
        exc = exc_info.value
        assert_that(getattr(exc, "diff", None)).is_not_none()
        assert_that(exc.diff.kind).is_equal_to("contains")
        missing = [entry for entry in exc.diff.entries if entry.path == "missing"]
        assert_that(missing).is_length(1)
        assert_that(missing[0].expected).is_equal_to(9)

    def test_contains_exactly_missing_and_extra(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that(["a", "b", "c"]).contains_exactly("a", "c", "d")
        exc = exc_info.value
        assert_that(exc.diff.kind).is_equal_to("contains")
        extra = [entry for entry in exc.diff.entries if entry.path == "extra"]
        missing = [entry for entry in exc.diff.entries if entry.path == "missing"]
        assert_that(extra).is_length(1)
        assert_that(extra[0].actual).is_equal_to("b")
        assert_that(missing).is_length(1)
        assert_that(missing[0].expected).is_equal_to("d")

    def test_contains_only_reports_both_halves_at_once(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that(["a", "b", "x"]).contains_only("a", "b", "c")
        exc = exc_info.value
        assert_that(str(exc)).contains("but did contain <x> and did not contain <c>.")
        assert_that(exc.diff.kind).is_equal_to("contains")
        assert_that([entry.actual for entry in exc.diff.entries if entry.path == "extra"]).is_equal_to(["x"])
        assert_that([entry.expected for entry in exc.diff.entries if entry.path == "missing"]).is_equal_to(["c"])

    def test_contains_only_keeps_the_single_fault_wording(self):
        with pytest.raises(AssertionError) as extra_info:
            assert_that(["a", "b", "x"]).contains_only("a", "b")
        assert_that(str(extra_info.value)).ends_with("to contain only <'a', 'b'>, but did contain <x>.")
        with pytest.raises(AssertionError) as missing_info:
            assert_that(["a", "b"]).contains_only("a", "b", "c")
        assert_that(str(missing_info.value)).ends_with("to contain only <'a', 'b', 'c'>, but did not contain <c>.")

    def test_contains_exactly_order_only_points_at_the_first_disagreeing_index(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that([1, 2, 3]).contains_exactly(3, 2, 1)
        exc = exc_info.value
        assert_that(str(exc)).contains("Same items, but the order differs at index 0.")
        assert_that(exc.diff.kind).is_equal_to("sequence")
        assert_that(exc.diff.entries).is_length(1)
        assert_that(exc.diff.entries[0].path).is_equal_to("[0]")
        assert_that(exc.diff.entries[0].actual).is_equal_to(1)
        assert_that(exc.diff.entries[0].expected).is_equal_to(3)

    def test_contains_exactly_order_only_skips_the_matching_prefix(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that(["GET", "POST", "PUT"]).contains_exactly("GET", "PUT", "POST")
        assert_that(str(exc_info.value)).contains("the order differs at index 1.")

    def test_contains_exactly_wrong_items_still_reports_extra_and_missing(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that([1, 2, 3]).contains_exactly(1, 2, 4)
        exc = exc_info.value
        assert_that(str(exc)).does_not_contain("order differs")
        assert_that(exc.diff.kind).is_equal_to("contains")


class TestIsEqualToWithDiff:
    def test_a_key_only_actual_has_carries_the_value_it_holds(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that({"a": 1, "b": 2}).is_equal_to({"a": 1})
        rows = [(entry.path, entry.actual, entry.absent) for entry in exc_info.value.diff.entries]
        assert_that(rows).is_equal_to([("b", 2, "expected")])

    def test_list_failure_includes_diff(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that([1, 2, 3]).is_equal_to([1, 9, 3])
        exc = exc_info.value
        assert_that(getattr(exc, "diff", None)).is_not_none()
        assert_that(exc.diff.kind).is_equal_to("sequence")
        assert_that(exc.diff.entries).is_length(1)

    def test_set_failure_includes_diff(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that({1, 2}).is_equal_to({2, 3})
        assert_that(exc_info.value.diff.kind).is_equal_to("set")

    def test_string_failure_includes_diff(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that("hello").is_equal_to("world")
        assert_that(exc_info.value.diff.kind).is_equal_to("string")

    def test_scalar_failure_includes_diff(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that(42).is_equal_to(99)
        assert_that(exc_info.value.diff.kind).is_equal_to("scalar")

    def test_success_no_exception(self):
        assert_that([1, 2, 3]).is_equal_to([1, 2, 3])
        assert_that({1, 2}).is_equal_to({1, 2})
        assert_that("hello").is_equal_to("hello")
        assert_that(42).is_equal_to(42)


class TestListMessageCollapse:
    def test_list_in_dict_collapses_to_changed_element(self):
        with pytest.raises(AssertionError) as exc:
            assert_that({"rows": [{"id": 1, "v": "x"}, {"id": 2, "v": "y"}, {"id": 3, "v": "z"}]}).is_equal_to(
                {"rows": [{"id": 1, "v": "x"}, {"id": 2, "v": "CHANGED"}, {"id": 3, "v": "z"}]}
            )
        msg = str(exc.value)
        assert_that(msg).contains("[.., {.., 'v': 'y'}, ..]")
        assert_that(msg).does_not_contain("'id': 1").does_not_contain("'id': 3")

    def test_scalar_list_collapses(self):
        with pytest.raises(AssertionError) as exc:
            assert_that({"a": [1, 2, 3, 4, 5]}).is_equal_to({"a": [1, 2, 999, 4, 5]})
        assert_that(str(exc.value)).contains("'a': [.., 3, ..]")

    def test_tuple_renders_with_parens(self):
        with pytest.raises(AssertionError) as exc:
            assert_that({"t": (1, 2, 3)}).is_equal_to({"t": (1, 9, 3)})
        assert_that(str(exc.value)).contains("'t': (.., 2, ..)")

    def test_nested_list_of_lists(self):
        with pytest.raises(AssertionError) as exc:
            assert_that({"m": [[1, 2], [3, 4]]}).is_equal_to({"m": [[1, 2], [3, 99]]})
        assert_that(str(exc.value)).contains("[.., [.., 4]]")

    def test_extra_element_shown(self):
        with pytest.raises(AssertionError) as exc:
            assert_that({"a": [1, 2, 3]}).is_equal_to({"a": [1, 2]})
        assert_that(str(exc.value)).contains("'a': [.., 3]")

    def test_tolerance_mismatch_shows_element_as_leaf(self):
        with pytest.raises(AssertionError) as exc:
            assert_that({"a": [1.0, 2.0, 3.0]}).is_equal_to({"a": [1.0, 2.5, 3.0]}, tolerance=0.1)
        assert_that(str(exc.value)).contains("'a': [.., 2.0, ..]")

    def test_pure_dict_message_unchanged(self):
        with pytest.raises(AssertionError) as exc:
            assert_that({"user": {"id": 1, "zip": "10001"}}).is_equal_to({"user": {"id": 1, "zip": "99999"}})
        assert_that(str(exc.value)).contains("{.., 'zip': '10001'}")

    def test_self_referential_list_is_guarded(self):
        circular = [1]
        circular.append(circular)
        with pytest.raises(AssertionError) as exc:
            assert_that({"x": circular}).is_equal_to({"x": [1, [99]]})
        assert_that(str(exc.value)).contains("<circular ref>")

    def test_list_versus_dict_at_same_key_renders_without_crash(self):
        # a list against a mapping must not reach the list collapser, which would index the mapping by position
        with pytest.raises(AssertionError) as exc:
            assert_that({"a": [1, 2]}).is_equal_to({"a": {"x": 1}})
        assert_that(str(exc.value)).contains("'a': [1, 2]")

    def test_fully_differing_list_has_no_ellipsis(self):
        with pytest.raises(AssertionError) as exc:
            assert_that({"a": [1, 2]}).is_equal_to({"a": [9, 8]})
        assert_that(str(exc.value)).contains("'a': [1, 2]").does_not_contain("..")

    def test_multiple_extra_elements_are_all_shown(self):
        with pytest.raises(AssertionError) as exc:
            assert_that({"a": [1, 2, 3, 4]}).is_equal_to({"a": [1, 2]})
        assert_that(str(exc.value)).contains("[.., 3, 4]")


class TestDiffResultStr:
    def test_empty_entries(self):
        diff = DiffResult(kind="scalar", entries=[])
        assert_that(str(diff)).is_equal_to("")

    def test_with_entries(self):
        diff = DiffResult(
            kind="sequence",
            entries=[DiffEntry(path="[0]", actual=1, expected=2)],
        )
        output = str(diff)
        assert_that(output).contains("diff (sequence):")
        assert_that(output).contains("[0]")

    def test_entry_str(self):
        entry = DiffEntry(path="[1]", actual="a", expected="b")
        assert_that(str(entry)).contains("at [1]")
        assert_that(str(entry)).contains("actual=<a>")
        assert_that(str(entry)).contains("expected=<b>")


class TestStringDiffCarets:
    """String diffs point at the intra-line change with difflib carets instead of dumping whole lines."""

    def test_carets_mark_the_changed_span(self):
        diff = DiffResult(
            kind="string",
            entries=[DiffEntry(path="line 1", actual="the quick fox", expected="the quick cat")],
        )
        output = _format_diff(diff)
        assert_that(output).contains("- the quick fox")
        assert_that(output).contains("+ the quick cat")
        assert_that(output).contains("^")

    def test_long_lines_are_windowed(self):
        diff = DiffResult(
            kind="string",
            entries=[DiffEntry(path="line 1", actual="a" * 300, expected="b" * 300)],
        )
        output = _format_diff(diff)
        assert_that(output).contains("...")
        assert_that(max(len(line) for line in output.splitlines())).is_less_than(200)

    def test_the_window_marks_a_cut_head_with_an_ellipsis(self):
        # `contains("...")` alone is satisfied by the tail marker, so the head was free to render as anything
        diff = DiffResult(
            kind="string",
            entries=[DiffEntry(path="line 1", actual="x" * 300 + "a", expected="x" * 300 + "b")],
        )
        output = _format_diff(diff)
        assert_that(output).does_not_contain("None")
        for line in output.splitlines():
            if line.strip().startswith(("-", "+")):
                assert_that(line.strip()[2:]).starts_with("...")

    def test_a_line_that_is_a_prefix_of_the_other(self):
        # no index of the shared prefix differs, so the sentinel has to be a position the arithmetic subtracts from
        diff = DiffResult(
            kind="string",
            entries=[DiffEntry(path="line 1", actual="x" * 300, expected="x" * 100)],
        )
        output = _format_diff(diff)
        assert_that(output).contains("- ").contains("+ ")

    def test_a_change_deep_inside_a_long_line_keeps_its_carets(self):
        # a plain prefix cut would show 300 identical characters and hide the difference
        diff = DiffResult(
            kind="string",
            entries=[
                DiffEntry(
                    path="line 1",
                    actual="x" * 300 + "NEEDLE" + "y" * 50,
                    expected="x" * 300 + "HAYSTK" + "y" * 50,
                )
            ],
        )
        output = _format_diff(diff)
        assert_that(output).contains("NEEDLE").contains("HAYSTK").contains("^")

    def test_a_windowed_string_block_stays_small(self):
        diff = DiffResult(
            kind="string",
            entries=[DiffEntry(path=f"line {i}", actual="a" * 500_000, expected="b" * 500_000) for i in range(50)],
        )
        assert_that(len(_format_diff(diff))).is_less_than(25_000)

    def test_many_long_entries_hit_the_block_budget(self):
        # the entry cap is lifted so the byte budget stops it, and a windowed text leaf makes rows shorter
        diff = DiffResult(
            kind="sequence",
            entries=[DiffEntry(path=f"[{i}]", actual="a" * 5_000, expected="b" * 5_000) for i in range(60)],
        )
        output = _format_diff(diff, max_entries=0)
        assert_that(len(output)).is_less_than(21_000)
        assert_that(output).contains("more diff lines")

    def test_the_block_budget_counts_one_separator_per_line(self):
        # sized to sit just under the limit, where the miscount is what decides elision
        entries = [DiffEntry(path=f"[{index}]", actual="a" * 90, expected="b" * 90) for index in range(97)]
        output = _format_diff(DiffResult(kind="sequence", entries=entries), max_entries=0)
        assert_that(output).does_not_contain("more diff lines")

    def test_removed_line_renders_minus_only(self):
        diff = DiffResult(
            kind="string", entries=[DiffEntry(path="line 2", actual="gone", expected=None, absent="expected")]
        )
        assert_that(_format_diff(diff)).contains("line 2: - 'gone'")

    def test_added_line_renders_plus_only(self):
        diff = DiffResult(
            kind="string", entries=[DiffEntry(path="line 2", actual=None, absent="actual", expected="new")]
        )
        assert_that(_format_diff(diff)).contains("line 2: + 'new'")


class TestPytestPluginDiffRendering:
    def test_diff_appears_in_report(self, tmp_path):
        test_file = tmp_path / "test_sample.py"
        test_file.write_text(
            "from assertpy import assert_that\n"
            "def test_list_diff():\n"
            "    assert_that([1, 2, 3]).is_equal_to([1, 9, 3])\n",
        )
        (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
        result = subprocess.run(
            [sys.executable, "-m", "pytest", str(test_file), "-v", "--no-header", "--tb=short"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert_that(result.stdout).contains("AssertionFailure")
        assert_that(result.stdout).contains("Structured Diff")

    def test_scalar_diff_in_report(self, tmp_path):
        test_file = tmp_path / "test_sample.py"
        test_file.write_text(
            "from assertpy import assert_that\ndef test_scalar():\n    assert_that(42).is_equal_to(99)\n",
        )
        (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
        result = subprocess.run(
            [sys.executable, "-m", "pytest", str(test_file), "-v", "--no-header", "--tb=short"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert_that(result.stdout).contains("AssertionFailure")

    def test_diff_disabled_via_ini(self, tmp_path):
        test_file = tmp_path / "test_sample.py"
        test_file.write_text(
            "from assertpy import assert_that\ndef test_x():\n    assert_that([1]).is_equal_to([2])\n",
        )
        (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                str(test_file),
                "-v",
                "--no-header",
                "--tb=short",
                "-o",
                "assertpy_diff=off",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert_that(result.stdout).does_not_contain("Structured Diff")

    def test_matches_structure_diff_in_report(self, tmp_path):
        test_file = tmp_path / "test_sample.py"
        test_file.write_text(
            "from assertpy import assert_that, match\n"
            "def test_structure():\n"
            "    assert_that({'role': 'guest', 'address': {'city': 'LA'}}).matches_structure({\n"
            "        'role': match.is_in('admin', 'user'),\n"
            "        'address': match.structure({'city': match.equal_to('NYC')}),\n"
            "    })\n",
        )
        (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
        result = subprocess.run(
            [sys.executable, "-m", "pytest", str(test_file), "-v", "--no-header", "--tb=short"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert_that(result.stdout).contains("diff (match)")
        assert_that(result.stdout).contains("address.city")


class TestFormatDiffMatchKind:
    def test_renders_predicate_and_actual(self):
        diff = DiffResult(
            kind="match",
            entries=[DiffEntry(path="role", actual="guest", expected="a value in <('admin', 'user')>")],
        )
        output = _format_diff(diff)
        assert_that(output).contains("diff (match):")
        assert_that(output).contains("role: expected a value in <('admin', 'user')>, but was 'guest'")


class TestFormatDiffTruncation:
    def test_truncation_when_over_max(self):
        entries = [DiffEntry(path=f"[{i}]", actual=i, expected=i + 100) for i in range(10)]
        diff = DiffResult(kind="sequence", entries=entries)
        output = _format_diff(diff, max_entries=3)
        assert_that(output).contains("... and 7 more entries")

    def test_no_truncation_when_under_max(self):
        entries = [DiffEntry(path="[0]", actual=1, expected=2)]
        diff = DiffResult(kind="sequence", entries=entries)
        output = _format_diff(diff, max_entries=50)
        assert_that(output).does_not_contain("more entries")

    def test_no_truncation_when_zero(self):
        entries = [DiffEntry(path=f"[{i}]", actual=i, expected=i + 100) for i in range(100)]
        diff = DiffResult(kind="sequence", entries=entries)
        output = _format_diff(diff, max_entries=0)
        assert_that(output).does_not_contain("more entries")
        assert_that(output).contains("[99]")


class TestNestedDataclassDiff:
    def test_nested_dataclass_fields_expanded(self):
        @dataclass
        class Address:
            city: str
            zip_code: str

        @dataclass
        class User:
            name: str
            address: Address

        actual = User("Alice", Address("NYC", "10001"))
        expected = User("Alice", Address("LA", "90210"))
        result = _build_equality_diff(actual, expected)
        assert_that(result.kind).is_equal_to("dataclass")
        paths = [entry.path for entry in result.entries]
        assert_that(paths).contains(".address.city")
        assert_that(paths).contains(".address.zip_code")
        assert_that(paths).does_not_contain(".address")

    def test_nested_dataclass_mixed_fields(self):
        @dataclass
        class Inner:
            x: int
            y: int

        @dataclass
        class Outer:
            name: str
            inner: Inner

        actual = Outer("a", Inner(1, 2))
        expected = Outer("b", Inner(1, 3))
        result = _build_equality_diff(actual, expected)
        paths = [entry.path for entry in result.entries]
        assert_that(paths).contains(".name")
        assert_that(paths).contains(".inner.y")
        assert_that(paths).does_not_contain(".inner.x")

    def test_deeply_nested_dataclass(self):
        @dataclass
        class Level3:
            value: int

        @dataclass
        class Level2:
            child: Level3

        @dataclass
        class Level1:
            child: Level2

        actual = Level1(Level2(Level3(1)))
        expected = Level1(Level2(Level3(99)))
        result = _build_equality_diff(actual, expected)
        paths = [entry.path for entry in result.entries]
        assert_that(paths).is_equal_to([".child.child.value"])
        assert_that(result.entries[0].actual).is_equal_to(1)
        assert_that(result.entries[0].expected).is_equal_to(99)

    def test_nested_namedtuple_fields_expanded(self):
        Inner = namedtuple("Inner", ["a", "b"])
        Outer = namedtuple("Outer", ["name", "inner"])
        actual = Outer("same", Inner(1, 2))
        expected = Outer("same", Inner(1, 99))
        result = _build_equality_diff(actual, expected)
        assert_that(result.kind).is_equal_to("namedtuple")
        paths = [entry.path for entry in result.entries]
        assert_that(paths).contains(".inner.b")
        assert_that(paths).does_not_contain(".inner")

    def test_nested_dict_inside_dataclass_expanded(self):
        @dataclass
        class Config:
            name: str
            settings: dict

        actual = Config("app", {"debug": True, "port": 8080})
        expected = Config("app", {"debug": False, "port": 8080})
        result = _build_equality_diff(actual, expected)
        paths = [entry.path for entry in result.entries]
        assert_that(paths).contains(".settings.debug")

    def test_list_of_nested_dataclasses(self):
        @dataclass
        class Inner:
            value: int

        @dataclass
        class Wrapper:
            inner: Inner

        actual = [Wrapper(Inner(1)), Wrapper(Inner(2))]
        expected = [Wrapper(Inner(1)), Wrapper(Inner(99))]
        result = _build_equality_diff(actual, expected)
        assert_that(result.kind).is_equal_to("sequence")
        paths = [entry.path for entry in result.entries]
        assert_that(paths).contains("[1].inner.value")


class TestPydanticDiff:
    def test_pydantic_model_field_diff(self):
        pytest.importorskip("pydantic", reason="pydantic not installed")
        from pydantic import BaseModel

        class UserModel(BaseModel):
            name: str
            age: int

        result = _build_equality_diff(UserModel(name="Alice", age=30), UserModel(name="Bob", age=30))
        assert_that(result.kind).is_equal_to("model")
        assert_that(result.entries).is_length(1)
        assert_that(result.entries[0].path).is_equal_to(".name")
        assert_that(result.entries[0].actual).is_equal_to("Alice")
        assert_that(result.entries[0].expected).is_equal_to("Bob")

    def test_nested_pydantic_model_diff(self):
        pytest.importorskip("pydantic", reason="pydantic not installed")
        from pydantic import BaseModel

        class AddressModel(BaseModel):
            city: str
            zip_code: str

        class UserModel(BaseModel):
            name: str
            address: AddressModel

        actual = UserModel(name="Alice", address=AddressModel(city="NYC", zip_code="10001"))
        expected = UserModel(name="Alice", address=AddressModel(city="LA", zip_code="90210"))
        result = _build_equality_diff(actual, expected)
        assert_that(result.kind).is_equal_to("model")
        paths = [entry.path for entry in result.entries]
        assert_that(paths).contains(".address.city")
        assert_that(paths).contains(".address.zip_code")

    def test_pydantic_is_equal_to_without_filter(self):
        pytest.importorskip("pydantic", reason="pydantic not installed")
        from pydantic import BaseModel

        class Item(BaseModel):
            sku: str
            price: float

        with pytest.raises(AssertionError) as exc_info:
            assert_that(Item(sku="A", price=10.0)).is_equal_to(Item(sku="A", price=20.0))
        exc = exc_info.value
        assert_that(getattr(exc, "diff", None)).is_not_none()
        assert_that(exc.diff.kind).is_equal_to("model")
        assert_that(exc.diff.entries[0].path).is_equal_to(".price")

    def test_pydantic_in_list_diff(self):
        pytest.importorskip("pydantic", reason="pydantic not installed")
        from pydantic import BaseModel

        class Item(BaseModel):
            name: str
            qty: int

        actual = [Item(name="A", qty=1), Item(name="B", qty=2)]
        expected = [Item(name="A", qty=1), Item(name="B", qty=99)]
        result = _build_equality_diff(actual, expected)
        assert_that(result.kind).is_equal_to("sequence")
        paths = [entry.path for entry in result.entries]
        assert_that(paths).contains("[1].qty")

    def test_pydantic_format_diff_renders(self):
        pytest.importorskip("pydantic", reason="pydantic not installed")
        from pydantic import BaseModel

        class Simple(BaseModel):
            x: int

        result = _build_equality_diff(Simple(x=1), Simple(x=2))
        output = _format_diff(result)
        assert_that(output).contains("diff (model):")
        assert_that(output).contains(".x:")


class TestModelDumpDiff:
    """Tests for model_dump() duck-type diff (covers Pydantic path without pydantic dep)."""

    def test_model_dump_field_diff(self):
        class FakeModel:
            def __init__(self, x, y):
                self._x = x
                self._y = y

            def model_dump(self):
                return {"x": self._x, "y": self._y}

            def __eq__(self, other):
                return isinstance(other, FakeModel) and self.model_dump() == other.model_dump()

        result = _build_equality_diff(FakeModel(1, 2), FakeModel(1, 99))
        assert_that(result.kind).is_equal_to("model")
        assert_that(result.entries).is_length(1)
        assert_that(result.entries[0].path).is_equal_to(".y")

    def test_model_dump_extra_key(self):
        class ModelA:
            def model_dump(self):
                return {"x": 1, "y": 2}

            def __eq__(self, other):
                return False

        class ModelB:
            def model_dump(self):
                return {"x": 1}

            def __eq__(self, other):
                return False

        result = _build_equality_diff(ModelA(), ModelB())
        assert_that(result.kind).is_equal_to("model")
        paths = [entry.path for entry in result.entries]
        assert_that(paths).contains(".y")
        entry = next(entry for entry in result.entries if entry.path == ".y")
        assert_that(entry.expected).is_none()
        assert_that(entry.actual).is_equal_to(2)

    def test_model_dump_missing_key(self):
        class ModelA:
            def model_dump(self):
                return {"x": 1}

            def __eq__(self, other):
                return False

        class ModelB:
            def model_dump(self):
                return {"x": 1, "z": 3}

            def __eq__(self, other):
                return False

        result = _build_equality_diff(ModelA(), ModelB())
        entry = next(entry for entry in result.entries if entry.path == ".z")
        assert_that(entry.actual).is_none()
        assert_that(entry.expected).is_equal_to(3)

    def test_model_dump_nested_dict_in_sub_diff(self):
        class Outer:
            def model_dump(self):
                return {"nested": {"a": 1, "b": 2}}

            def __eq__(self, other):
                return False

        class Outer2:
            def model_dump(self):
                return {"nested": {"a": 1, "b": 99}}

            def __eq__(self, other):
                return False

        result = _build_equality_diff(Outer(), Outer2())
        paths = [entry.path for entry in result.entries]
        assert_that(paths).contains(".nested.b")

    def test_model_dump_scalar_field_in_sub_diff(self):
        class Outer:
            def model_dump(self):
                return {"val": 10}

            def __eq__(self, other):
                return False

        class Outer2:
            def model_dump(self):
                return {"val": 20}

            def __eq__(self, other):
                return False

        result = _sub_diff_entries(Outer(), Outer2(), _Path("root"))
        assert_that(result).is_not_none()
        assert_that(result[0].path).is_equal_to("root.val")

    def test_model_dump_in_sub_diff_extra_key(self):
        class ModelA:
            def model_dump(self):
                return {"x": 1, "y": 2}

            def __eq__(self, other):
                return False

        class ModelB:
            def model_dump(self):
                return {"x": 1}

            def __eq__(self, other):
                return False

        result = _sub_diff_entries(ModelA(), ModelB(), _Path("item"))
        assert_that(result).is_not_none()
        entry = next(entry for entry in result if entry.path == "item.y")
        assert_that(entry.expected).is_none()

    def test_model_dump_in_sub_diff_missing_key(self):
        class ModelA:
            def model_dump(self):
                return {"x": 1}

            def __eq__(self, other):
                return False

        class ModelB:
            def model_dump(self):
                return {"x": 1, "z": 3}

            def __eq__(self, other):
                return False

        result = _sub_diff_entries(ModelA(), ModelB(), _Path("item"))
        entry = next(entry for entry in result if entry.path == "item.z")
        assert_that(entry.actual).is_none()
        assert_that(entry.expected).is_equal_to(3)

    def test_model_dump_in_sub_diff_nested_recurse(self):
        class Inner:
            def model_dump(self):
                return {"val": 42}

            def __eq__(self, other):
                return False

        class Outer:
            def model_dump(self):
                return {"child": {"val": 42}}

            def __eq__(self, other):
                return False

        class Outer2:
            def model_dump(self):
                return {"child": {"val": 99}}

            def __eq__(self, other):
                return False

        result = _sub_diff_entries(Outer(), Outer2(), _Path("root"))
        assert_that(result).is_not_none()
        paths = [entry.path for entry in result]
        assert_that(paths).contains("root.child.val")

    def test_nested_model_field_the_expected_side_lacks_keeps_its_value_and_says_which_side_is_absent(self):
        """A one-sided field of a model reached through a container reports the value and the absent side."""

        class ModelA:
            def model_dump(self):
                return {"x": 1, "y": 2}

            def __eq__(self, other):
                return False

        class ModelB:
            def model_dump(self):
                return {"x": 1}

            def __eq__(self, other):
                return False

        with pytest.raises(AssertionError) as exc_info:
            assert_that([ModelA()]).is_equal_to([ModelB()])
        entry = next(entry for entry in exc_info.value.diff.entries if entry.path == "[0].y")
        assert_that(entry.actual).is_equal_to(2)
        assert_that(entry.expected).is_none()
        assert_that(entry.absent).is_equal_to("expected")
        assert_that(_format_diff(exc_info.value.diff)).contains("[0].y: - 2")

    def test_nested_model_field_outside_the_tolerance_keeps_both_numbers(self):
        """A tolerance makes a nested model's field a leaf, and a leaf still carries both sides."""

        class Reading:
            def __init__(self, celsius):
                self.celsius = celsius

            def model_dump(self):
                return {"celsius": self.celsius}

            def __eq__(self, other):
                return isinstance(other, Reading) and self.celsius == other.celsius

        with pytest.raises(AssertionError) as exc_info:
            assert_that([Reading(2.0)]).is_equal_to([Reading(9.0)], tolerance=0.5)
        entry = next(entry for entry in exc_info.value.diff.entries if entry.path == "[0].celsius")
        assert_that(entry.actual).is_equal_to(2.0)
        assert_that(entry.expected).is_equal_to(9.0)
        assert_that(_format_diff(exc_info.value.diff)).contains("- 2.0").contains("+ 9.0")


class TestSubDiffNamedtupleCoverage:
    def test_a_namedtuple_against_a_plain_tuple_is_diffed_as_a_sequence(self):
        Point = namedtuple("Point", "x y")
        with pytest.raises(AssertionError) as exc_info:
            assert_that({"p": Point(1, 2)}).is_equal_to({"p": (1, 9)})
        assert_that([entry.path for entry in exc_info.value.diff.entries]).is_equal_to(["p[1]"])

    def test_namedtuple_in_sub_diff_extra_field(self):
        A = namedtuple("A", ["x", "y"])
        B = namedtuple("B", ["x"])
        result = _sub_diff_entries(A(1, 2), B(1), _Path("item"))
        assert_that(result).is_not_none()
        entry = next(entry for entry in result if entry.path == "item.y")
        assert_that(entry.expected).is_none()

    def test_namedtuple_in_sub_diff_missing_field(self):
        A = namedtuple("A", ["x"])
        B = namedtuple("B", ["x", "z"])
        result = _sub_diff_entries(A(1), B(1, 3), _Path("item"))
        assert_that(result).is_not_none()
        entry = next(entry for entry in result if entry.path == "item.z")
        assert_that(entry.actual).is_none()
        assert_that(entry.expected).is_equal_to(3)

    def test_namedtuple_missing_field_sentinel(self):
        A = namedtuple("A", ["x", "y"])
        B = namedtuple("B", ["x"])
        result = _sub_diff_entries(A(1, 2), B(1), _Path("root"))
        assert_that(result).is_not_none()
        has_y = any(entry.path == "root.y" and entry.expected is None for entry in result)
        assert_that(has_y).is_true()

    def test_namedtuple_nested_recurse_in_sub_diff(self):
        Inner = namedtuple("Inner", ["a", "b"])
        Outer = namedtuple("Outer", ["name", "inner"])
        actual = Outer("same", Inner(1, 2))
        expected = Outer("same", Inner(1, 99))
        result = _sub_diff_entries(actual, expected, _Path("root"))
        assert_that(result).is_not_none()
        paths = [entry.path for entry in result]
        assert_that(paths).contains("root.inner.b")

    def test_namedtuple_scalar_diff_in_sub_diff(self):
        Point = namedtuple("Point", ["x", "y"])
        result = _sub_diff_entries(Point(1, 2), Point(1, 99), _Path("item"))
        assert_that(result).is_not_none()
        assert_that(result[0].path).is_equal_to("item.y")
        assert_that(result[0].actual).is_equal_to(2)
        assert_that(result[0].expected).is_equal_to(99)


class TestAPairMetAgainIsNoEntry:
    """A value that leads back to itself is read as far as it differs: the way back is not a row."""

    def test_a_value_compared_with_itself_has_nothing_under_it(self):
        circular = [1]
        circular.append(circular)
        assert_that(_sub_diff_entries(circular, circular, _Path("x"))).is_equal_to([])

    def test_no_entry_holds_a_value_neither_side_has(self):
        actual = {"x": 1}
        actual["self"] = actual
        expected = {"x": 2}
        expected["self"] = expected
        entries = _sub_diff_entries(actual, expected)
        assert_that([(entry.path, entry.actual, entry.expected) for entry in entries]).is_equal_to([("x", 1, 2)])


class TestSubDiffDataclassMissingField:
    def test_dataclass_missing_field_in_sub_diff(self):
        @dataclass
        class A:
            x: int
            y: int

        @dataclass
        class B:
            x: int

        result = _sub_diff_entries(A(1, 2), B(1), _Path("root"))
        assert_that(result).is_not_none()
        entry = next(entry for entry in result if entry.path == "root.y")
        assert_that(entry.expected).is_none()

    def test_dataclass_nested_recurse_in_sub_diff(self):
        @dataclass
        class Inner:
            val: int

        @dataclass
        class Outer:
            inner: Inner

        result = _sub_diff_entries(Outer(Inner(1)), Outer(Inner(99)), _Path("root"))
        assert_that(result).is_not_none()
        paths = [entry.path for entry in result]
        assert_that(paths).contains("root.inner.val")


class TestCircularRefProtection:
    def test_circular_dict_does_not_recurse_infinitely(self):
        left = {"x": 1}
        left["self"] = left
        right = {"x": 2, "self": "nope"}
        with pytest.raises(AssertionError):
            assert_that(left).is_equal_to(right)

    def test_circular_dict_in_sub_diff(self):
        inner_a = {"val": 1}
        inner_a["loop"] = inner_a
        inner_b = {"val": 2}
        inner_b["loop"] = inner_b
        result = _sub_diff_entries(inner_a, inner_b, _Path("root"))
        assert_that([(entry.path, entry.actual, entry.expected) for entry in result]).is_equal_to([("root.val", 1, 2)])

    def test_asymmetric_circular_ref_in_sub_diff(self):
        # one side met again beside a new partner is a new pair: it is walked until the finite side ends
        actual = {"name": "x"}
        actual["ref"] = actual
        expected = {"name": "y", "ref": {"name": "z"}}
        result = _sub_diff_entries(actual, expected, _Path("root"))
        rows = [(entry.path, entry.actual, entry.expected, entry.absent) for entry in result]
        assert_that(rows).is_equal_to(
            [
                ("root.name", "x", "y", None),
                ("root.ref.name", "x", "z", None),
                ("root.ref.ref", actual, None, "expected"),
            ]
        )

    def test_circular_list_item_in_diff(self):
        inner_a = {"val": 1}
        inner_a["self"] = inner_a
        inner_b = {"val": 2}
        inner_b["self"] = inner_b
        result = _build_equality_diff([inner_a], [inner_b])
        assert_that(result.kind).is_equal_to("sequence")
        assert_that([(entry.path, entry.actual, entry.expected) for entry in result.entries]).is_equal_to(
            [("[0].val", 1, 2)]
        )

    def test_circular_in_dict_err(self):
        actual = {"a": 1}
        actual["self"] = actual
        expected = {"a": 2}
        expected["self"] = expected
        with pytest.raises(AssertionError) as exc_info:
            assert_that(actual).is_equal_to(expected)
        diff = exc_info.value.diff
        assert_that([(entry.path, entry.actual, entry.expected) for entry in diff.entries]).is_equal_to([("a", 1, 2)])

    def test_mutual_circular_ref(self):
        left = {"key": "a_val"}
        right = {"key": "b_val"}
        left["ref"] = right
        right["ref"] = left
        with pytest.raises(AssertionError):
            assert_that(left).is_equal_to({"key": "other", "ref": {"key": "other2", "ref": "x"}})


class TestDictListValueDiff:
    def test_list_values_in_dict_are_expanded(self):
        actual = {"items": [{"sku": "A", "qty": 2}, {"sku": "B", "qty": 1}]}
        expected = {"items": [{"sku": "A", "qty": 2}, {"sku": "B", "qty": 3}]}
        with pytest.raises(AssertionError) as exc_info:
            assert_that(actual).is_equal_to(expected)
        diff = exc_info.value.diff
        assert_that(diff).is_not_none()
        paths = [entry.path for entry in diff.entries]
        assert_that(paths).contains("items[1].qty")

    def test_list_of_scalars_in_dict(self):
        actual = {"tags": [1, 2, 3]}
        expected = {"tags": [1, 2, 99]}
        with pytest.raises(AssertionError) as exc_info:
            assert_that(actual).is_equal_to(expected)
        diff = exc_info.value.diff
        paths = [entry.path for entry in diff.entries]
        assert_that(paths).contains("tags[2]")

    def test_nested_dict_with_list_of_dicts(self):
        actual = {"config": {"rules": [{"name": "r1", "active": True}, {"name": "r2", "active": False}]}}
        expected = {"config": {"rules": [{"name": "r1", "active": True}, {"name": "r2", "active": True}]}}
        with pytest.raises(AssertionError) as exc_info:
            assert_that(actual).is_equal_to(expected)
        diff = exc_info.value.diff
        paths = [entry.path for entry in diff.entries]
        assert_that(paths).contains("config.rules[1].active")

    def test_list_length_mismatch_in_dict(self):
        actual = {"items": [1, 2]}
        expected = {"items": [1, 2, 3]}
        with pytest.raises(AssertionError) as exc_info:
            assert_that(actual).is_equal_to(expected)
        diff = exc_info.value.diff
        paths = [entry.path for entry in diff.entries]
        assert_that(paths).contains("items[2]")

    def test_actual_list_longer_in_dict(self):
        actual = {"items": [1, 2, 3]}
        expected = {"items": [1, 2]}
        with pytest.raises(AssertionError) as exc_info:
            assert_that(actual).is_equal_to(expected)
        diff = exc_info.value.diff
        paths = [entry.path for entry in diff.entries]
        assert_that(paths).contains("items[2]")
        entry = next(entry for entry in diff.entries if entry.path == "items[2]")
        assert_that(entry.actual).is_equal_to(3)
        assert_that(entry.expected).is_none()


class _ReadOnlyMapping(Mapping):
    """A dict-like that is not a ``dict`` subclass, to exercise the duck mapping-like diff path."""

    def __init__(self, data):
        self._data = dict(data)

    def __getitem__(self, key):
        return self._data[key]

    def __iter__(self):
        return iter(self._data)

    def __len__(self):
        return len(self._data)

    def __eq__(self, other):
        return isinstance(other, _ReadOnlyMapping) and self._data == other._data

    def __hash__(self):
        return id(self)

    def __repr__(self):
        return f"_ReadOnlyMapping({self._data!r})"


class TestDiffEngineHarmonization:
    """The dict path and the base path share one nested diff engine (``_sub_diff_entries``).

    A nested non-dict structure (dataclass, model, namedtuple, list-of-lists, mapping) is therefore
    decomposed to its differing path inside a dict exactly as it already was inside a list, and the
    key ordering is repr-stable on both sides so mixed-type keys no longer raise.
    """

    @staticmethod
    def _diff_of(actual, expected, **kwargs):
        with pytest.raises(AssertionError) as exc_info:
            assert_that(actual).is_equal_to(expected, **kwargs)
        return exc_info.value.diff

    def _paths(self, actual, expected, **kwargs):
        return [entry.path for entry in self._diff_of(actual, expected, **kwargs).entries]

    def test_a_key_only_the_actual_side_has_keeps_its_value(self):
        diff = self._diff_of({"a": 1, "b": 2}, {"a": 1})
        rows = [(entry.path, entry.actual, entry.absent) for entry in diff.entries]
        assert_that(rows).is_equal_to([("b", 2, "expected")])

    def test_dict_with_dataclass_value_decomposes(self):
        @dataclass
        class Point:
            x: int
            y: int

        assert_that(self._paths({"p": Point(1, 2)}, {"p": Point(1, 3)})).contains("p.y")

    def test_dict_with_model_value_decomposes(self):
        class FakeModel:
            def __init__(self, **fields):
                self.__dict__.update(fields)

            def model_dump(self):
                return dict(self.__dict__)

            def __eq__(self, other):
                return isinstance(other, FakeModel) and self.model_dump() == other.model_dump()

        assert_that(self._paths({"u": FakeModel(a=1, b=2)}, {"u": FakeModel(a=1, b=3)})).contains("u.b")

    def test_dict_with_namedtuple_value_uses_field_name(self):
        Pair = namedtuple("Pair", ["a", "b"])
        paths = self._paths({"p": Pair(1, 2)}, {"p": Pair(1, 3)})
        assert_that(paths).contains("p.b")
        assert_that(paths).does_not_contain("p[1]")

    def test_dict_with_list_of_lists_decomposes(self):
        assert_that(self._paths({"m": [[1, 2]]}, {"m": [[1, 9]]})).contains("m[0][1]")

    def test_list_with_mapping_value_decomposes(self):
        paths = self._paths([_ReadOnlyMapping({"a": 1})], [_ReadOnlyMapping({"a": 2})])
        assert_that(paths).contains("[0].a")

    def test_deep_crossover_dict_list_dict_dataclass(self):
        @dataclass
        class Point:
            x: int
            y: int

        actual = {"users": [{"profile": Point(1, 2)}]}
        expected = {"users": [{"profile": Point(1, 3)}]}
        assert_that(self._paths(actual, expected)).contains("users[0].profile.y")

    def test_mixed_type_keys_do_not_raise(self):
        diff = self._diff_of({1: "a", "b": 2}, {1: "z", "b": 2})
        assert_that([entry.path for entry in diff.entries]).contains("1")
        entry = next(entry for entry in diff.entries if entry.path == "1")
        assert_that(entry.actual).is_equal_to("a")
        assert_that(entry.expected).is_equal_to("z")

    def test_keys_keep_the_order_they_were_written_in(self):
        # sorted by repr this read 1, 10, 2; insertion order is as deterministic and is the one the reader chose
        paths = self._paths({1: "a", 2: "b", 10: "c"}, {1: "z", 2: "y", 10: "x"})
        assert_that(paths).is_equal_to(["1", "2", "10"])

    def test_keys_of_mixed_types_do_not_need_an_ordering(self):
        # `sorted` on {1, "a"} raises, and walking the two sides in order never compares keys at all
        paths = self._paths({1: "a", "b": "c"}, {1: "z", "b": "y"})
        assert_that(paths).is_equal_to(["1", "b"])

    def test_a_key_only_the_expected_side_has_comes_after_the_actual_ones(self):
        paths = self._paths({"b": 1}, {"b": 2, "a": 3})
        assert_that(paths).is_equal_to(["b", "a"])

    def test_the_headline_and_the_diff_read_the_keys_in_the_same_order(self):
        # the headline sorted by repr while the diff walked the mapping, so a key sat in two different places
        written = {"zebra": 1, "apple": 2, "mango": 3}
        with pytest.raises(AssertionError) as failure:
            assert_that(written).is_equal_to({"zebra": 9, "apple": 9, "mango": 9})
        headline = str(failure.value)
        in_headline = sorted(written, key=headline.index)
        assert_that(in_headline).is_equal_to(["zebra", "apple", "mango"])
        assert_that(self._paths(written, {"zebra": 9, "apple": 9, "mango": 9})).is_equal_to(in_headline)

    def test_top_level_mapping_still_decomposes(self):
        paths = self._paths(_ReadOnlyMapping({"a": 1, "b": 2}), _ReadOnlyMapping({"a": 1, "b": 9}))
        assert_that(paths).is_equal_to(["b"])

    def test_mapping_value_in_dict_still_decomposes(self):
        actual = {"u": _ReadOnlyMapping({"a": 1, "b": 2})}
        expected = {"u": _ReadOnlyMapping({"a": 1, "b": 9})}
        assert_that(self._paths(actual, expected)).contains("u.b")


class TestDictCircularRefNotEqual:
    def test_circular_dict_not_equal_returns_false(self):
        mapping = {"x": 1}
        mapping["self"] = mapping
        twin = {"x": 1}
        twin["self"] = twin
        mixin = type("M", (HelpersMixin,), {"val": None, "description": "", "kind": None, "expected": None})()
        assert_that(mixin._dict_not_equal(mapping, twin, ignore="missing")).is_false()


class TestDiffOrderingActualGreater:
    """The field/element diff must report a difference when actual is greater than expected.

    Each case has a differing slot where actual > expected, and the diff must still surface it. The
    symmetric actual < expected direction is already covered by the diff tests above.
    """

    def test_build_namedtuple_actual_greater(self):
        Point = namedtuple("Point", ["x", "y"])
        result = _build_equality_diff(Point(1, 9), Point(1, 2))
        entry = next(entry for entry in result.entries if entry.path == ".y")
        assert_that(entry.actual).is_equal_to(9)
        assert_that(entry.expected).is_equal_to(2)

    def test_build_dataclass_actual_greater(self):
        @dataclass
        class Dc:
            a: int
            b: int

        result = _build_equality_diff(Dc(1, 9), Dc(1, 2))
        entry = next(entry for entry in result.entries if entry.path == ".b")
        assert_that(entry.actual).is_equal_to(9)
        assert_that(entry.expected).is_equal_to(2)

    def test_build_model_actual_greater(self):
        class FakeModel:
            def __init__(self, **fields):
                self.__dict__.update(fields)

            def model_dump(self):
                return dict(self.__dict__)

        result = _build_equality_diff(FakeModel(a=1, b=9), FakeModel(a=1, b=2))
        entry = next(entry for entry in result.entries if entry.path == ".b")
        assert_that(entry.actual).is_equal_to(9)
        assert_that(entry.expected).is_equal_to(2)

    def test_build_sequence_actual_greater(self):
        result = _build_equality_diff([1, 9, 3], [1, 2, 3])
        entry = next(entry for entry in result.entries if entry.path == "[1]")
        assert_that(entry.actual).is_equal_to(9)
        assert_that(entry.expected).is_equal_to(2)

    def test_build_string_actual_greater_line(self):
        result = _build_equality_diff("a\nz\nc", "a\nb\nc")
        entry = next(entry for entry in result.entries if entry.path == "line 2")
        assert_that(entry.actual).is_equal_to("z")
        assert_that(entry.expected).is_equal_to("b")

    def test_sub_dict_actual_greater(self):
        result = _sub_diff_entries({"k": 9}, {"k": 2}, _Path("root"))
        entry = next(entry for entry in result if entry.path == "root.k")
        assert_that(entry.actual).is_equal_to(9)
        assert_that(entry.expected).is_equal_to(2)

    def test_sub_dataclass_actual_greater(self):
        @dataclass
        class Dc:
            a: int

        result = _sub_diff_entries(Dc(9), Dc(2), _Path("root"))
        entry = next(entry for entry in result if entry.path == "root.a")
        assert_that(entry.actual).is_equal_to(9)
        assert_that(entry.expected).is_equal_to(2)

    def test_sub_namedtuple_actual_greater(self):
        Pair = namedtuple("Pair", ["x"])
        result = _sub_diff_entries(Pair(9), Pair(2), _Path("root"))
        entry = next(entry for entry in result if entry.path == "root.x")
        assert_that(entry.actual).is_equal_to(9)
        assert_that(entry.expected).is_equal_to(2)

    def test_sub_model_actual_greater(self):
        class FakeModel:
            def __init__(self, **fields):
                self.__dict__.update(fields)

            def model_dump(self):
                return dict(self.__dict__)

        result = _sub_diff_entries(FakeModel(a=9), FakeModel(a=2), _Path("root"))
        entry = next(entry for entry in result if entry.path == "root.a")
        assert_that(entry.actual).is_equal_to(9)
        assert_that(entry.expected).is_equal_to(2)


class TestNestedSubDiffDecomposition:
    """Nested diffs (_sub_diff_entries) decompose sequences and report dataclass fields fully, matching
    the top-level _build_equality_diff. The nested-completeness feature; sets/strings stay leaves."""

    def test_nested_list_in_dataclass_decomposes(self):
        @dataclass
        class Box:
            items: list

        result = _build_equality_diff(Box([1, 2, 3]), Box([1, 9, 3]))
        entry = next(entry for entry in result.entries if entry.path == ".items[1]")
        assert_that(entry.actual).is_equal_to(2)
        assert_that(entry.expected).is_equal_to(9)

    def test_nested_list_in_model_decomposes(self):
        class FakeModel:
            def __init__(self, **fields):
                self.__dict__.update(fields)

            def model_dump(self):
                return dict(self.__dict__)

        result = _build_equality_diff(FakeModel(items=[1, 2]), FakeModel(items=[1, 9]))
        entry = next(entry for entry in result.entries if entry.path == ".items[1]")
        assert_that(entry.actual).is_equal_to(2)
        assert_that(entry.expected).is_equal_to(9)

    def test_sub_sequence_decomposes(self):
        result = _sub_diff_entries([1, 2, 3], [1, 9, 3], _Path("root"))
        assert_that(result).is_not_none()
        entry = next(entry for entry in result if entry.path == "root[1]")
        assert_that(entry.actual).is_equal_to(2)
        assert_that(entry.expected).is_equal_to(9)

    def test_sub_dataclass_reports_expected_only_field(self):
        @dataclass
        class One:
            x: int

        @dataclass
        class Two:
            x: int
            y: int

        result = _sub_diff_entries(One(1), Two(1, 2), _Path("root"))
        assert_that(result).is_not_none()
        entry = next(entry for entry in result if entry.path == "root.y")
        assert_that(entry.actual).is_none()
        assert_that(entry.expected).is_equal_to(2)

    def test_sub_dataclass_keeps_declaration_field_order(self):
        @dataclass
        class NonAlpha:
            z: int
            a: int

        result = _sub_diff_entries(NonAlpha(1, 1), NonAlpha(9, 9), _Path("root"))
        assert_that([entry.path for entry in result]).is_equal_to(["root.z", "root.a"])

    def test_nested_list_of_dataclass_in_dataclass_recurses(self):
        @dataclass
        class Inner:
            v: int

        @dataclass
        class Outer:
            items: list

        result = _build_equality_diff(Outer([Inner(1)]), Outer([Inner(9)]))
        entry = next(entry for entry in result.entries if entry.path == ".items[0].v")
        assert_that(entry.actual).is_equal_to(1)
        assert_that(entry.expected).is_equal_to(9)

    def test_nested_set_in_dataclass_stays_leaf(self):
        @dataclass
        class Box:
            tags: set

        result = _build_equality_diff(Box({1, 2}), Box({1, 9}))
        entry = next(entry for entry in result.entries if entry.path == ".tags")
        assert_that(entry.actual).is_equal_to({1, 2})
        assert_that(entry.expected).is_equal_to({1, 9})


class TestMixedKindPairsStayAssertions:
    """A structured value compared against a plain one still fails as an assertion, not as a crash.

    Each guard here is a conjunction: both sides must be a namedtuple, both a dataclass, both a model.
    The suite only ever compared like with like, so nothing held the guards to `and` - and reading
    `_fields`, `dataclasses.fields()` or `model_dump()` off the other side turns a verdict into an
    AttributeError or TypeError that no caller expects.
    """

    def test_namedtuple_against_a_plain_tuple(self):
        Point = namedtuple("Point", ["x", "y"])
        with pytest.raises(AssertionError):
            assert_that(Point(1, 2)).is_equal_to((1, 3))
        assert_that(_build_equality_diff(Point(1, 2), (1, 3)).kind).is_equal_to("sequence")
        assert_that(_build_equality_diff((1, 3), Point(1, 2)).kind).is_equal_to("sequence")

    def test_dataclass_against_a_dict(self):
        @dataclass
        class Plain:
            x: int

        with pytest.raises(AssertionError):
            assert_that(Plain(1)).is_equal_to({"x": 1})
        assert_that(_build_equality_diff(Plain(1), {"x": 1}).kind).is_equal_to("scalar")
        assert_that(_build_equality_diff({"x": 1}, Plain(1)).kind).is_equal_to("scalar")

    def test_dataclass_against_a_scalar(self):
        @dataclass
        class Plain:
            x: int

        with pytest.raises(AssertionError):
            assert_that(Plain(1)).is_equal_to(5)
        assert_that(_build_equality_diff(Plain(1), 5).kind).is_equal_to("scalar")

    def test_model_dump_object_against_a_dict(self):
        class Model:
            def __init__(self, a):
                self.a = a

            def model_dump(self):
                return {"a": self.a}

        with pytest.raises(AssertionError):
            assert_that(Model(1)).is_equal_to({"a": 1})
        assert_that(_build_equality_diff(Model(1), {"a": 1}).kind).is_equal_to("scalar")
        assert_that(_build_equality_diff({"a": 1}, Model(1)).kind).is_equal_to("scalar")

    def test_a_model_dump_object_against_a_dict_under_a_key(self):
        with pytest.raises(AssertionError):
            assert_that({"k": _FakeModel(a=1)}).is_equal_to({"k": {"a": 1}})
        with pytest.raises(AssertionError):
            assert_that({"k": {"a": 1}}).is_equal_to({"k": _FakeModel(a=1)})

    def test_an_attrs_instance_against_a_dict_under_a_key(self):
        class Bag:
            __attrs_attrs__ = (namedtuple("Attribute", "name")("load"),)

            def __init__(self, load):
                self.load = load

        with pytest.raises(AssertionError):
            assert_that({"k": Bag(1)}).is_equal_to({"k": {"load": 1}})
        with pytest.raises(AssertionError):
            assert_that({"k": {"load": 1}}).is_equal_to({"k": Bag(1)})


class TestSequenceAlignment:
    """A shifted sequence is paired by alignment, so one insertion reads as one entry."""

    def test_an_aligned_equal_block_the_config_accepts_adds_no_row(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that([1.0, 2.0, 3.0]).is_equal_to([0.0, 1.0, 2.0, 3.0], tolerance=0.5)
        rows = [(entry.path, entry.actual, entry.expected) for entry in exc_info.value.diff.entries]
        assert_that(rows).is_equal_to([("expected[0]", None, 0.0)])

    def test_an_aligned_equal_block_adds_no_rows(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that([1.0, 2.0, 3.0, 4.0]).is_equal_to([0.0, 1.0, 2.0, 3.0, 4.0], tolerance=0.5)
        rows = [(entry.path, entry.actual, entry.expected) for entry in exc_info.value.diff.entries]
        assert_that(rows).is_equal_to([("expected[0]", None, 0.0)])

    def test_a_truncated_tail_keeps_the_index_reading(self):
        # a tie keeps the index reading, so the entries stay [3]/[4] rather than naming a side that has not shifted
        with pytest.raises(AssertionError) as exc_info:
            assert_that([1, 2, 3, 4, 5]).is_equal_to([1, 2, 3])
        assert_that([entry.path for entry in exc_info.value.diff.entries]).is_equal_to(["[3]", "[4]"])
        assert_that([entry.steps[-1].side for entry in exc_info.value.diff.entries]).is_equal_to([None, None])

    def test_an_unequal_length_tie_keeps_the_index_reading(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that([1, 2, 3, 4, 5]).is_equal_to([1, 2, 3])
        assert_that([entry.path for entry in exc_info.value.diff.entries]).is_equal_to(["[3]", "[4]"])

    def test_an_aligned_pair_is_still_decomposed_to_the_field_that_differs(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that([{"a": 1}, {"a": 2}]).is_equal_to([{"a": 0}, {"a": 1}, {"a": 9}])
        rows = [(entry.path, entry.actual, entry.expected) for entry in exc_info.value.diff.entries]
        assert_that(rows).contains(("[1].a", 2, 9))

    def test_a_sequence_at_exactly_the_cap_is_still_aligned(self):
        size = _diff_module._ALIGN_MAX_ELEMENTS
        result = _build_equality_diff(list(range(1, size)), list(range(size)))
        assert_that(result.entries).is_length(1)
        assert_that(result.entries[0].path).is_equal_to("expected[0]")

    def test_a_repeated_element_is_never_treated_as_junk(self):
        # difflib's autojunk junks any value over 1% of a 200+ element sequence, which is what alignment matches on
        expected = ["a"] * 250
        result = _build_equality_diff(["x", *expected], expected)
        assert_that([entry.path for entry in result.entries]).is_equal_to(["actual[0]"])

    def test_a_repeated_unhashable_element_is_never_treated_as_junk(self):
        expected = [{"v": "a"} for _ in range(250)]
        result = _build_equality_diff([{"v": "x"}, *expected], expected)
        assert_that([entry.path for entry in result.entries]).is_equal_to(["actual[0]"])

    def test_two_differing_positions_still_buy_an_alignment(self):
        result = _build_equality_diff([1, 2, 3], [1, 2, 9, 3])
        assert_that([(entry.path, entry.expected) for entry in result.entries]).is_equal_to([("expected[2]", 9)])

    def test_an_element_inserted_at_the_head(self):
        result = _build_equality_diff([0, *range(1, 40)], list(range(1, 40)))
        assert_that(result.kind).is_equal_to("sequence")
        assert_that(result.entries).is_length(1)
        assert_that(result.entries[0].path).is_equal_to("actual[0]")
        assert_that(result.entries[0].actual).is_equal_to(0)
        assert_that(result.entries[0].expected).is_none()

    def test_an_element_missing_from_the_middle(self):
        result = _build_equality_diff([1, 2, 4, 5], [1, 2, 3, 4, 5])
        assert_that(result.entries).is_length(1)
        assert_that(result.entries[0].path).is_equal_to("expected[2]")
        assert_that(result.entries[0].expected).is_equal_to(3)

    def test_a_one_sided_entry_names_the_sequence_it_indexes(self):
        # after a shift the index spaces disagree, and numbering both as [i] put two unrelated entries on one path
        entries = _build_equality_diff([9, 1, 2, 3, 9], [1, 2, 3]).entries
        paths = [entry.path for entry in entries]
        assert_that(paths).is_equal_to(sorted(set(paths), key=paths.index))
        assert_that(paths).contains("actual[0]", "actual[4]")

    def test_unhashable_elements_are_aligned_on_their_reprs(self):
        # difflib cannot index dicts, the shape of most API payloads, so the alignment keys on reprs
        actual = [{"id": index} for index in range(20)]
        result = _build_equality_diff(actual, actual[1:])
        assert_that(result.entries).is_length(1)
        assert_that(result.entries[0].path).is_equal_to("actual[0]")

    def test_hashable_elements_are_aligned_as_themselves_and_not_as_their_reprs(self):
        """The repr keying is the fallback, so two distinct objects that read alike do not pair."""

        class Twin:
            def __repr__(self):
                return "<twin>"

        result = _build_equality_diff([Twin(), Twin()], [Twin()])
        rows = [(entry.path, entry.absent) for entry in result.entries]
        assert_that(rows).is_equal_to([("[0]", None), ("[1]", "expected")])

    def test_a_substitution_stays_positional(self):
        result = _build_equality_diff([1, 2, 3], [1, 9, 3])
        assert_that([(entry.path, entry.actual, entry.expected) for entry in result.entries]).is_equal_to(
            [("[1]", 2, 9)]
        )

    def test_a_reversal_keeps_the_index_reading(self):
        # four insertions and deletions aligned, two substitutions positionally, and the shorter reading wins
        result = _build_equality_diff([1, 2, 3], [3, 2, 1])
        assert_that([(entry.path, entry.actual, entry.expected) for entry in result.entries]).is_equal_to(
            [("[0]", 1, 3), ("[2]", 3, 1)]
        )

    def test_a_tuple_pair_reads_as_a_record(self):
        result = _build_equality_diff((1, 2), (2, 3))
        assert_that([(entry.path, entry.actual, entry.expected) for entry in result.entries]).is_equal_to(
            [("[0]", 1, 2), ("[1]", 2, 3)]
        )

    def test_a_single_difference_never_asks_for_an_alignment(self):
        actual = [{"id": index} for index in range(200)]
        expected = [dict(item) for item in actual]
        expected[199]["id"] = -1
        result = _build_equality_diff(actual, expected)
        assert_that(result.entries).is_length(1)
        assert_that(result.entries[0].path).is_equal_to("[199].id")

    def test_a_sequence_past_the_cap_stays_positional(self):
        size = _diff_module._ALIGN_MAX_ELEMENTS + 1
        result = _build_equality_diff(list(range(size)), list(range(1, size)))
        assert_that(result.entries).is_length(size)
        assert_that(result.entries[0].path).is_equal_to("[0]")

    def test_an_equal_length_pair_is_never_aligned(self):
        # a rotation reads shorter aligned, given up so two equal-length record sequences pay nothing for it
        result = _build_equality_diff([1, 2, 3, 4], [2, 3, 4, 1])
        assert_that([entry.path for entry in result.entries]).is_equal_to(["[0]", "[1]", "[2]", "[3]"])

    def test_an_aligned_block_still_pairs_its_elements(self):
        result = _build_equality_diff([0, 1, 2, 3, 9], [1, 2, 3, 8])
        rows = [(entry.path, entry.actual, entry.expected) for entry in result.entries]
        assert_that(rows).contains(("actual[0]", 0, None), ("[4]", 9, 8))

    def test_an_aligned_pair_beyond_tolerance_is_one_leaf(self):
        with pytest.raises(AssertionError):
            assert_that([0.0, 1.0, 2.0, 9.0]).is_equal_to([1.0, 2.0, 8.0], tolerance=0.5)
        result = _build_equality_diff(
            [0.0, 1.0, 2.0, 9.0],
            [1.0, 2.0, 8.0],
            config=_build_compare_config(0.5, None),
        )
        rows = [(entry.path, entry.actual, entry.expected) for entry in result.entries]
        assert_that(rows).contains(("[3]", 9.0, 8.0))

    def test_an_aligned_equal_block_is_still_offered_to_the_config(self):
        # difflib matched the block on ==, which is the whole test only until a comparator narrows it
        called = []

        def picky(left, right):
            called.append((left, right))
            return left == right

        with pytest.raises(AssertionError):
            assert_that([0, 1.0, 2.0]).is_equal_to([1.0, 2.0], comparators={float: picky})
        assert_that(called).contains((1.0, 1.0), (2.0, 2.0))

    def test_the_verdict_still_belongs_to_the_config(self):
        assert_that([1.0, 2.0, 3.0]).is_equal_to([1.001, 2.0, 3.0], tolerance=0.01)
        with pytest.raises(AssertionError):
            assert_that([1.0, 2.0, 3.0]).is_equal_to([1.5, 2.0, 3.0], tolerance=0.01)

    def test_a_single_differing_position_never_renders_an_element_repr(self):
        """One differing position cannot be beaten, so the repr-keyed alignment is never paid for."""

        rendered = []

        class Counted:
            __hash__ = None

            def __init__(self, value):
                self.value = value

            def __eq__(self, other):
                return isinstance(other, Counted) and self.value == other.value

            def __repr__(self):
                rendered.append(self.value)
                return f"Counted({self.value})"

        actual = [Counted(1), Counted(2), Counted(3)]
        assert_that(_diff_module._alignment_opcodes_if_useful(actual, [*actual, Counted(4)])).is_none()
        assert_that(rendered).is_empty()
        assert_that(_diff_module._alignment_opcodes_if_useful(actual, [Counted(0), *actual])).is_not_none()
        assert_that(rendered).is_not_empty()

    def test_a_repr_matched_pair_that_is_not_equal_is_still_reported(self):
        """Reprs decide the pairing, so a pair difflib calls equal has only been shown to print alike."""

        result = _build_equality_diff([_Boxed(1), _Boxed(2)], [_Boxed(3)])
        rows = [(entry.path, entry.actual, entry.expected) for entry in result.entries]
        assert_that(rows).is_equal_to([("[0]", _Boxed(1), _Boxed(3)), ("[1]", _Boxed(2), None)])

    def test_a_pair_equal_under_eq_is_not_reported_whatever_its_ne_says(self):
        """The walk reads ``==``, as difflib does for hashable elements, and ``!=`` may disagree with both."""

        class Split:
            def __hash__(self):
                return 7

            def __eq__(self, other):
                return isinstance(other, Split)

            def __ne__(self, other):
                return True

        result = _build_equality_diff([0, Split(), 2, 3], [9, 0, Split(), 2, 3])
        assert_that([(entry.path, entry.absent) for entry in result.entries]).is_equal_to([("expected[0]", "actual")])

    def test_elements_that_are_equal_but_print_differently_are_paired_by_value(self):
        """`2 == 2.0` is a match difflib finds only on the values; on the reprs it reads as a third
        difference, and the shift the reader wanted disappears into it."""

        result = _build_equality_diff([1, "a", 2], [3, 2.0])
        assert_that([(entry.path, entry.absent) for entry in result.entries]).is_equal_to(
            [("[0]", None), ("actual[1]", "expected")]
        )

    def test_a_repr_matched_run_is_revalidated_against_the_element_it_was_paired_with(self):
        """Pairing the run against any other element can call a differing pair equal and drop it."""

        result = _build_equality_diff([_Boxed(1), _Boxed(2)], [_Boxed(1), _Boxed(3), _Boxed(9), _Boxed(2)])
        assert_that([(entry.path, entry.absent) for entry in result.entries]).is_equal_to(
            [("[1]", None), ("[2]", "actual"), ("[3]", "actual")]
        )

    def test_a_repr_matched_pair_inside_a_winning_alignment_is_reported_with_the_shift(self):
        """Splitting the matched run must report the odd pair without costing the shift its win."""

        actual = [{"id": 0}, {"id": 1}, _Boxed(1), {"id": 3}, {"id": 4}]
        expected = [{"id": 9}, {"id": 0}, {"id": 1}, _Boxed(2), {"id": 3}, {"id": 4}]
        result = _build_equality_diff(actual, expected)
        assert_that([(entry.path, entry.absent) for entry in result.entries]).is_equal_to(
            [("expected[0]", "actual"), ("[2]", None)]
        )


class TestCaretsReachNestedTextLeaves:
    """A text leaf inside a container gets the same caret guide a bare string does.

    This is where the guide earns the most: a one-character change deep inside a URL, a token or an
    id printed as two near-identical rows and left the reader to find it by eye.  pytest reaches this
    only at ``-vv``, and then by diffing the whole pretty-printed structure, which drops the path;
    naming the path *and* the character is the point of doing it per leaf.
    """

    _LEFT = "GET /api/v2/orders?status=shipped&page=3&limit=50"
    _RIGHT = "GET /api/v2/orders?status=shipped&page=4&limit=50"

    @staticmethod
    def _caret_rows(output):
        return [line.strip() for line in output.splitlines() if line.strip().startswith("?")]

    def test_a_string_value_in_a_dict(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that({"url": self._LEFT}).is_equal_to({"url": self._RIGHT})
        output = _format_diff(exc_info.value.diff)
        assert_that(output).contains("url:")
        assert_that(self._caret_rows(output)).is_length(2)

    def test_a_string_element_in_a_list(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that([self._LEFT]).is_equal_to([self._RIGHT])
        output = _format_diff(exc_info.value.diff)
        assert_that(output).contains("[0]:")
        assert_that(self._caret_rows(output)).is_length(2)

    def test_a_string_deep_in_a_nested_dict_keeps_its_path(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that({"req": {"url": self._LEFT}}).is_equal_to({"req": {"url": self._RIGHT}})
        output = _format_diff(exc_info.value.diff)
        assert_that(output).contains("req.url:")
        assert_that(self._caret_rows(output)).is_not_empty()

    def test_a_string_field_of_a_dataclass(self):
        @dataclass
        class Request:
            url: str

        with pytest.raises(AssertionError) as exc_info:
            assert_that(Request(self._LEFT)).is_equal_to(Request(self._RIGHT))
        output = _format_diff(exc_info.value.diff)
        assert_that(self._caret_rows(output)).is_not_empty()

    def test_bytes_leaves_are_guided_too(self):
        output = _format_diff(
            DiffResult(kind="dict", entries=[DiffEntry(path="body", actual=b"tok-abc", expected=b"tok-abd")])
        )
        assert_that(self._caret_rows(output)).is_not_empty()

    def test_a_number_pair_gets_no_caret(self):
        output = _format_diff(DiffResult(kind="dict", entries=[DiffEntry(path="n", actual=1, expected=2)]))
        assert_that(self._caret_rows(output)).is_empty()

    def test_a_text_against_a_non_text_gets_no_caret(self):
        output = _format_diff(DiffResult(kind="dict", entries=[DiffEntry(path="v", actual="1", expected=1)]))
        assert_that(self._caret_rows(output)).is_empty()
        assert_that(output).contains("'1'").contains("+ 1")

    def test_a_one_sided_entry_is_unchanged(self):
        output = _format_diff(
            DiffResult(kind="dict", entries=[DiffEntry(path="gone", actual="x", expected=None, absent="expected")])
        )
        assert_that(self._caret_rows(output)).is_empty()
        assert_that(output).contains("gone: - 'x'")

    def test_a_long_leaf_is_windowed_around_its_difference(self):
        # cutting from the start would hide the very change being reported
        left, right = "z" * 300 + "abc", "z" * 300 + "abd"
        output = _format_diff(DiffResult(kind="dict", entries=[DiffEntry(path="k", actual=left, expected=right)]))
        assert_that(output).contains("...")
        assert_that(self._caret_rows(output)).is_not_empty()

    def test_a_difference_past_the_row_cap_is_still_marked(self):
        # windowing after capping cut both sides at the same offset, leaving two identical strings: ndiff
        # called them a match and the row lost its `-`/`+`. The window is taken over the whole repr for this
        left, right = "z" * 600 + "abc", "z" * 600 + "abd"
        output = _format_diff(DiffResult(kind="dict", entries=[DiffEntry(path="k", actual=left, expected=right)]))
        marked = [line.strip() for line in output.splitlines() if line.strip().startswith(("-", "+"))]
        assert_that(marked).is_length(2)
        assert_that(self._caret_rows(output)).is_length(2)

    def test_two_non_text_values_with_the_same_repr_still_read_as_differing(self):
        # not text, so they never reach the guide: `_both_texts` declining keeps a common row from claiming a match
        class SameRepr:
            def __repr__(self):
                return "<obj>"

        entry = DiffEntry(path="k", actual=SameRepr(), expected=SameRepr())
        output = _format_diff(DiffResult(kind="dict", entries=[entry]))
        assert_that(self._caret_rows(output)).is_empty()
        assert_that(output).contains("- <obj>").contains("+ <obj>")


class TestTheBlockBudgetCutsRatherThanDrops:
    """The row that crosses the limit is truncated, not discarded.

    Discarding it is invisible on a block of many rows and destroys the diff on a block of few: the
    `set` and `contains` kinds join every item into a single row, so a large set difference rendered
    as the header and a count with not one item shown.
    """

    def test_the_crossing_row_is_truncated_with_a_marker(self):
        assert_that(_within_budget(["aaaaa", "b" * 40], limit=20)).is_equal_to("aaaaa\nbbbbbbbbbbbbb...")

    def test_a_block_that_fits_is_untouched(self):
        assert_that(_within_budget(["a", "b"], limit=20)).is_equal_to("a\nb")

    def test_a_limit_reached_exactly_at_a_row_boundary_drops_the_next_row(self):
        # no room for one character of the next row, so there is nothing to truncate and it is counted instead
        assert_that(_within_budget(["a" * 19, "b"], limit=20)).is_equal_to("a" * 19 + "\n  ... and 1 more diff lines")

    def test_rows_after_the_cut_are_counted(self):
        cut = _within_budget(["aaaaa", "b" * 40, "c", "d"], limit=20)
        assert_that(cut).contains("... and 2 more diff lines")

    def test_a_large_set_difference_still_shows_items(self):
        entries = [DiffEntry(path="extra", actual="x" * 3_000, expected=None, absent="expected") for _ in range(60)]
        rendered = _format_diff(DiffResult(kind="set", entries=entries), max_entries=0)
        assert_that(len(rendered)).is_less_than(21_000)
        assert_that(rendered).contains("xxx")

    def test_a_clipped_coloured_row_keeps_its_reset(self):
        # the reset closes the colour, and cutting it off stains everything the terminal prints after the block
        entries = [DiffEntry(path="extra", actual="x" * 3_000, expected=None, absent="expected") for _ in range(60)]
        rendered = _format_diff(DiffResult(kind="set", entries=entries), max_entries=0, color=True)
        opens = sum(rendered.count(code) for code in ("\033[31m", "\033[32m", "\033[36m"))
        assert_that(rendered.count("\033[0m")).is_equal_to(opens)

    def test_a_cut_never_leaves_half_an_escape_sequence(self):
        # the terminal completes a truncated escape with whatever bytes follow it
        assert_that(_cut("abc\033[31mdef", 6)).is_equal_to("abc...")

    def test_a_cut_that_closes_nothing_adds_no_reset(self):
        assert_that(_cut("plain text here", 6)).is_equal_to("plain ...")

    def test_a_cut_past_a_reset_adds_no_second_one(self):
        assert_that(_cut("\033[31mabc\033[0mdef", 30)).is_equal_to("\033[31mabc\033[0mdef...")


class TestConfigLeafRowsHoldBothSides:
    """A leaf the config rejected is one row, and the row carries the pair that earned the verdict."""

    def test_a_sequence_element_beyond_tolerance(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that([1.0, 2.0, 3.0]).is_equal_to([1.0, 9.0, 3.0], tolerance=0.5)
        rows = [(entry.path, entry.actual, entry.expected) for entry in exc_info.value.diff.entries]
        assert_that(rows).is_equal_to([("[1]", 2.0, 9.0)])

    def test_a_dataclass_field_beyond_tolerance(self):
        @dataclass
        class Reading:
            value: float
            unit: str

        with pytest.raises(AssertionError) as exc_info:
            assert_that(Reading(1.0, "m")).is_equal_to(Reading(2.0, "m"), tolerance=0.5)
        rows = [(entry.path, entry.actual, entry.expected) for entry in exc_info.value.diff.entries]
        assert_that(rows).is_equal_to([(".value", 1.0, 2.0)])

    def test_a_comparator_refusing_the_root_names_the_root(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that(1).is_equal_to("1", strict_types=True, comparators={int: lambda actual, expected: False})
        rows = [(entry.path, entry.actual, entry.expected) for entry in exc_info.value.diff.entries]
        assert_that(rows).is_equal_to([(".", 1, "1")])

    def test_a_strict_type_difference_at_the_root(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that(1).is_equal_to("1", strict_types=True)
        diff = exc_info.value.diff
        assert_that(diff.kind).is_equal_to("scalar")
        assert_that([(entry.path, entry.actual, entry.expected) for entry in diff.entries]).is_equal_to([(".", 1, "1")])

    def test_a_namedtuple_field_beyond_tolerance(self):
        Point = namedtuple("Point", ["x", "y"])
        with pytest.raises(AssertionError) as exc_info:
            assert_that(Point(1.0, 2.0)).is_equal_to(Point(1.0, 9.0), tolerance=0.5)
        rows = [(entry.path, entry.actual, entry.expected) for entry in exc_info.value.diff.entries]
        assert_that(rows).is_equal_to([(".y", 2.0, 9.0)])

    def test_a_model_field_beyond_tolerance(self):
        class Reading:
            def __init__(self, value, unit):
                self._fields = {"value": value, "unit": unit}

            def model_dump(self):
                return dict(self._fields)

            def __eq__(self, other):
                return isinstance(other, Reading) and self._fields == other._fields

        with pytest.raises(AssertionError) as exc_info:
            assert_that(Reading(1.0, "m")).is_equal_to(Reading(2.0, "m"), tolerance=0.5)
        rows = [(entry.path, entry.actual, entry.expected) for entry in exc_info.value.diff.entries]
        assert_that(rows).is_equal_to([(".value", 1.0, 2.0)])

    def test_a_strict_type_difference_in_a_model_field_stays_one_row(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that(_FakeModel(a=[1, 2])).is_equal_to(_FakeModel(a=(1, 2)), strict_types=True)
        rows = [(entry.path, entry.actual, entry.expected) for entry in exc_info.value.diff.entries]
        assert_that(rows).is_equal_to([(".a", [1, 2], (1, 2))])

    def test_a_model_field_equal_under_a_strict_descent_holds_no_row(self):
        config = _build_compare_config(None, None, strict_types=True)
        result = _build_equality_diff(_FakeModel(tags={1, 2}), _FakeModel(tags={1, 2}), config=config)
        assert_that(result.entries).is_equal_to([])
        assert_that(_FakeModel(tags={1, 2})).is_equal_to(_FakeModel(tags={1, 2}), strict_types=True)

    def test_a_strict_descent_into_a_value_with_no_inside_holds_no_row(self):
        class Box:
            def __init__(self, value):
                self.value = value

            def __eq__(self, other):
                return isinstance(other, Box) and self.value == other.value

        config = _build_compare_config(None, None, strict_types=True)
        result = _build_equality_diff(Box(1), Box(1), config=config)
        assert_that(result.kind).is_equal_to("scalar")
        assert_that(result.entries).is_equal_to([])


class TestCycleGuardOnEveryDescent:
    """A value that contains itself is read to where it differs, and the way back into it is no row."""

    def test_a_self_referential_list_reports_the_cycle_at_its_own_index(self):
        actual = [1, 2]
        actual.append(actual)
        expected = [1, 9]
        expected.append(expected)
        with pytest.raises(AssertionError) as exc_info:
            assert_that(actual).is_equal_to(expected)
        rows = [(entry.path, entry.actual) for entry in exc_info.value.diff.entries]
        assert_that(rows).is_equal_to([("[1]", 2)])

    def test_a_self_referential_list_survives_an_aligned_pairing(self):
        actual = [1, 2, 3]
        actual.append(actual)
        expected = [0, 1, 2, 3]
        expected.append(expected)
        with pytest.raises(AssertionError) as exc_info:
            assert_that(actual).is_equal_to(expected)
        rows = [(entry.path, entry.actual) for entry in exc_info.value.diff.entries]
        assert_that(rows).is_equal_to([("expected[0]", None)])

    def test_a_self_referential_dataclass_reports_the_cycle_at_its_own_field(self):
        @dataclass
        class Node:
            tag: str
            child: object = None

        actual, expected = Node("a"), Node("b")
        actual.child, expected.child = actual, expected
        with pytest.raises(AssertionError) as exc_info:
            assert_that(actual).is_equal_to(expected)
        rows = [(entry.path, entry.actual) for entry in exc_info.value.diff.entries]
        assert_that(rows).is_equal_to([(".tag", "a")])

    def test_a_self_referential_dataclass_nested_in_a_dict_reports_the_cycle(self):
        @dataclass
        class Node:
            tag: str
            child: object = None

        actual, expected = Node("a"), Node("b")
        actual.child, expected.child = actual, expected
        with pytest.raises(AssertionError) as exc_info:
            assert_that({"n": actual}).is_equal_to({"n": expected})
        rows = [(entry.path, entry.actual) for entry in exc_info.value.diff.entries]
        assert_that(rows).is_equal_to([("n.tag", "a")])

    def test_a_self_referential_namedtuple_reports_the_cycle_at_its_own_field(self):
        Box = namedtuple("Box", "tag holder")
        actual_holder, expected_holder = [], []
        actual, expected = Box("a", actual_holder), Box("b", expected_holder)
        actual_holder.append(actual)
        expected_holder.append(expected)
        with pytest.raises(AssertionError) as exc_info:
            assert_that(actual).is_equal_to(expected)
        rows = [(entry.path, entry.actual) for entry in exc_info.value.diff.entries]
        # the holders differ as the boxes they hold do, which is the row above and not a second one
        assert_that(rows).is_equal_to([(".tag", "a")])

    def test_a_self_referential_namedtuple_nested_in_a_dict_reports_the_cycle(self):
        Box = namedtuple("Box", "tag holder")
        actual_holder, expected_holder = [], []
        actual, expected = Box("a", actual_holder), Box("b", expected_holder)
        actual_holder.append(actual)
        expected_holder.append(expected)
        with pytest.raises(AssertionError) as exc_info:
            assert_that({"b": actual}).is_equal_to({"b": expected})
        rows = [(entry.path, entry.actual) for entry in exc_info.value.diff.entries]
        assert_that(rows).is_equal_to([("b.tag", "a")])

    def test_a_cycle_on_the_expected_side_alone_is_reported(self):
        # the looping side is walked beside the finite one until that one ends, which is the difference
        expected = {"tag": "x"}
        expected["child"] = expected
        actual = {"tag": "y", "child": {"tag": "x", "child": {"tag": "x"}}}
        with pytest.raises(AssertionError) as exc_info:
            assert_that(actual).is_equal_to(expected)
        rows = [(entry.path, entry.actual, entry.expected, entry.absent) for entry in exc_info.value.diff.entries]
        assert_that(rows).is_equal_to([("tag", "y", "x", None), ("child.child.child", None, expected, "actual")])

    def test_a_cycle_on_only_one_side_of_a_nested_namedtuple_is_reported(self):
        Box = namedtuple("Box", "tag holder")
        holder = []
        looping = Box("a", holder)
        holder.append(looping)
        finite = Box("c", [Box("d", [])])
        with pytest.raises(AssertionError) as exc_info:
            assert_that({"b": looping}).is_equal_to({"b": finite})
        rows = [(entry.path, entry.actual, entry.absent) for entry in exc_info.value.diff.entries]
        assert_that(rows).is_equal_to(
            [("b.tag", "a", None), ("b.holder[0].tag", "a", None), ("b.holder[0].holder[0]", looping, "expected")]
        )
        with pytest.raises(AssertionError) as exc_info:
            assert_that({"b": finite}).is_equal_to({"b": looping})
        rows = [(entry.path, entry.expected, entry.absent) for entry in exc_info.value.diff.entries]
        assert_that(rows).is_equal_to(
            [("b.tag", "a", None), ("b.holder[0].tag", "a", None), ("b.holder[0].holder[0]", looping, "actual")]
        )

    def test_a_cycle_on_one_side_only_is_walked_until_the_other_side_ends(self):
        looping = [1]
        looping.append(looping)
        finite = [2, [2, [2]]]
        entries = _build_equality_diff(looping, finite).entries
        assert_that([(entry.path, entry.actual, entry.expected, entry.absent) for entry in entries]).is_equal_to(
            [
                ("[0]", 1, 2, None),
                ("[1][0]", 1, 2, None),
                ("[1][1][0]", 1, 2, None),
                ("[1][1][1]", looping, None, "expected"),
            ]
        )
        entries = _build_equality_diff(finite, looping).entries
        assert_that([(entry.path, entry.absent) for entry in entries]).is_equal_to(
            [("[0]", None), ("[1][0]", None), ("[1][1][0]", None), ("[1][1][1]", "actual")]
        )

    def test_a_model_field_that_points_back_at_the_model(self):
        class Model:
            def __init__(self):
                self.child = None

            def model_dump(self):
                return {"child": self.child}

        actual, expected = Model(), Model()
        actual.child, expected.child = actual, expected
        # nothing under the pair differs, so the pair handed over as unequal is the entry
        entries = _build_equality_diff(actual, expected).entries
        assert_that([(entry.path, entry.actual, entry.expected) for entry in entries]).is_equal_to(
            [(".", actual, expected)]
        )

    def test_a_none_on_one_side_is_a_value_and_not_a_cycle(self):
        """``None`` is a value at every depth, so its id never belongs in the seen set."""

        @dataclass
        class Node:
            tag: str
            child: object = None

        for actual, expected, path in (
            ({"n": Node("a", None)}, {"n": Node("a", 2)}, "n.child"),
            ({"m": _FakeModel(load=None)}, {"m": _FakeModel(load=2)}, "m.load"),
            ({"xs": [None]}, {"xs": [2]}, "xs[0]"),
        ):
            with pytest.raises(AssertionError) as exc_info:
                assert_that(actual).is_equal_to(expected)
            rows = [(entry.path, entry.actual, entry.expected) for entry in exc_info.value.diff.entries]
            assert_that(rows).is_equal_to([(path, None, 2)])

    def test_a_self_referential_model_nested_in_a_dict_reports_the_cycle(self):
        looping = _FakeModel(tag="a")
        looping._fields["child"] = looping
        finite = _FakeModel(tag="c", child=_FakeModel(tag="c", child=_FakeModel(tag="c")))
        with pytest.raises(AssertionError) as exc_info:
            assert_that({"m": looping}).is_equal_to({"m": finite})
        rows = [(entry.path, entry.actual, entry.absent) for entry in exc_info.value.diff.entries]
        assert_that(rows).is_equal_to(
            [
                ("m.tag", "a", None),
                ("m.child.tag", "a", None),
                ("m.child.child.tag", "a", None),
                ("m.child.child.child", looping, "expected"),
            ]
        )


class TestOneSidedEntriesNameTheAbsentSide:
    """``absent`` is what tells a position nobody has from one holding ``None``."""

    def test_a_sequence_position_only_the_expected_side_has(self):
        entries = _build_equality_diff([1, 2], [1, 2, 3]).entries
        assert_that([(entry.path, entry.absent) for entry in entries]).is_equal_to([("[2]", "actual")])

    def test_a_sequence_position_only_the_actual_side_has(self):
        entries = _build_equality_diff([1, 2, 3], [1, 2]).entries
        assert_that([(entry.path, entry.absent) for entry in entries]).is_equal_to([("[2]", "expected")])

    def test_an_aligned_insertion_and_deletion(self):
        inserted = _build_equality_diff([0, *range(1, 40)], list(range(1, 40))).entries
        assert_that([(entry.path, entry.absent) for entry in inserted]).is_equal_to([("actual[0]", "expected")])
        deleted = _build_equality_diff([1, 2, 4, 5], [1, 2, 3, 4, 5]).entries
        assert_that([(entry.path, entry.absent) for entry in deleted]).is_equal_to([("expected[2]", "actual")])

    def test_a_dataclass_field_only_one_side_declares(self):
        @dataclass
        class Wide:
            a: int
            b: int

        @dataclass
        class Narrow:
            a: int

        extra = _build_equality_diff(Wide(1, 2), Narrow(1)).entries
        assert_that([(entry.path, entry.actual, entry.absent) for entry in extra]).is_equal_to([(".b", 2, "expected")])
        missing = _build_equality_diff(Narrow(1), Wide(1, 2)).entries
        assert_that([(entry.path, entry.expected, entry.absent) for entry in missing]).is_equal_to(
            [(".b", 2, "actual")]
        )

    def test_a_namedtuple_field_only_one_side_declares(self):
        Point = namedtuple("Point", "x y")
        Wide = namedtuple("Wide", "x y z")
        extra = _build_equality_diff(Wide(1, 2, 3), Point(1, 2)).entries
        assert_that([(entry.path, entry.actual, entry.absent) for entry in extra]).is_equal_to([(".z", 3, "expected")])
        missing = _build_equality_diff(Point(1, 2), Wide(1, 2, 3)).entries
        assert_that([(entry.path, entry.expected, entry.absent) for entry in missing]).is_equal_to(
            [(".z", 3, "actual")]
        )

    def test_a_dict_key_only_the_expected_side_has(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that({"a": 1}).is_equal_to({"a": 1, "b": 2})
        entries = exc_info.value.diff.entries
        assert_that([(entry.path, entry.expected, entry.absent) for entry in entries]).is_equal_to([("b", 2, "actual")])

    def test_a_model_field_only_one_side_declares(self):
        class Model:
            def __init__(self, **fields):
                self._fields = fields

            def model_dump(self):
                return dict(self._fields)

            def __eq__(self, other):
                return False

        extra = _build_equality_diff(Model(a=1, b=2), Model(a=1)).entries
        assert_that([(entry.path, entry.actual, entry.absent) for entry in extra]).is_equal_to([(".b", 2, "expected")])
        missing = _build_equality_diff(Model(a=1), Model(a=1, b=2)).entries
        assert_that([(entry.path, entry.expected, entry.absent) for entry in missing]).is_equal_to(
            [(".b", 2, "actual")]
        )

    def test_a_nested_namedtuple_field_only_one_side_declares(self):
        Point = namedtuple("Point", "x y")
        Wide = namedtuple("Wide", "x y z")
        with pytest.raises(AssertionError) as exc_info:
            assert_that({"p": Wide(1, 2, 3)}).is_equal_to({"p": Point(1, 2)})
        extra = [(entry.path, entry.actual, entry.absent) for entry in exc_info.value.diff.entries]
        assert_that(extra).is_equal_to([("p.z", 3, "expected")])
        with pytest.raises(AssertionError) as exc_info:
            assert_that({"p": Point(1, 2)}).is_equal_to({"p": Wide(1, 2, 3)})
        missing = [(entry.path, entry.expected, entry.absent) for entry in exc_info.value.diff.entries]
        assert_that(missing).is_equal_to([("p.z", 3, "actual")])

    def test_a_set_member_only_one_side_has(self):
        result = _build_equality_diff({1}, {1, 2})
        rows = [(entry.path, entry.expected, entry.absent) for entry in result.entries]
        assert_that(rows).is_equal_to([("missing", 2, "actual")])
        assert_that(str(result)).contains("missing: {2}")

    def test_a_nested_model_field_only_one_side_declares(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that({"m": _FakeModel(a=1, b=2)}).is_equal_to({"m": _FakeModel(a=1)})
        extra = [(entry.path, entry.actual, entry.absent) for entry in exc_info.value.diff.entries]
        assert_that(extra).is_equal_to([("m.b", 2, "expected")])
        with pytest.raises(AssertionError) as exc_info:
            assert_that({"m": _FakeModel(a=1)}).is_equal_to({"m": _FakeModel(a=1, b=2)})
        missing = [(entry.path, entry.expected, entry.absent) for entry in exc_info.value.diff.entries]
        assert_that(missing).is_equal_to([("m.b", 2, "actual")])


class TestFieldNamedConfigReachesRecordFields:
    """``ignore_null`` and a comparator keyed by name match on the field's own name."""

    def test_ignore_null_reaches_a_namedtuple_field_by_name(self):
        Point = namedtuple("Point", "x y")
        with pytest.raises(AssertionError) as exc_info:
            assert_that(Point(1, 2)).is_equal_to(Point(9, None), ignore_null=True)
        assert_that([entry.path for entry in exc_info.value.diff.entries]).is_equal_to([".x"])

    def test_a_comparator_keyed_by_name_reaches_a_namedtuple_field(self):
        Point = namedtuple("Point", "x y")
        with pytest.raises(AssertionError) as exc_info:
            assert_that(Point(1, 2)).is_equal_to(Point(9, 5), comparators={"y": lambda left, right: True})
        assert_that([entry.path for entry in exc_info.value.diff.entries]).is_equal_to([".x"])

    def test_ignore_null_reaches_a_nested_namedtuple_field_by_name(self):
        Point = namedtuple("Point", "x y")
        with pytest.raises(AssertionError) as exc_info:
            assert_that({"p": Point(1, 2)}).is_equal_to({"p": Point(9, None)}, ignore_null=True)
        assert_that([entry.path for entry in exc_info.value.diff.entries]).is_equal_to(["p.x"])

    def test_ignore_null_reaches_a_model_field_by_name(self):
        class Model:
            def __init__(self, **fields):
                self._fields = fields

            def model_dump(self):
                return dict(self._fields)

        with pytest.raises(AssertionError) as exc_info:
            assert_that(Model(a=1, b=2)).is_equal_to(Model(a=9, b=None), ignore_null=True)
        assert_that([entry.path for entry in exc_info.value.diff.entries]).is_equal_to([".a"])

    def test_a_config_reaches_a_value_inside_a_namedtuple_field(self):
        # the tolerance has to survive the descent into the field, not just be offered to the field
        Bag = namedtuple("Bag", "name items")
        with pytest.raises(AssertionError) as exc_info:
            assert_that(Bag("a", [1.0, 5.0])).is_equal_to(Bag("b", [1.0, 5.0001]), tolerance=0.001)
        rows = [(entry.path, entry.actual, entry.expected) for entry in exc_info.value.diff.entries]
        assert_that(rows).is_equal_to([(".name", "a", "b")])

    def test_a_config_reaches_a_value_inside_a_model_field(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that(_FakeModel(name="a", items=[1.0, 5.0])).is_equal_to(
                _FakeModel(name="b", items=[1.0, 5.0001]), tolerance=0.001
            )
        rows = [(entry.path, entry.actual, entry.expected) for entry in exc_info.value.diff.entries]
        assert_that(rows).is_equal_to([(".name", "a", "b")])

    def test_a_config_reaches_a_value_inside_a_nested_namedtuple_field(self):
        Bag = namedtuple("Bag", "name items")
        with pytest.raises(AssertionError) as exc_info:
            assert_that({"b": Bag("a", [1.0, 5.0])}).is_equal_to({"b": Bag("c", [1.0, 5.0001])}, tolerance=0.001)
        rows = [(entry.path, entry.actual, entry.expected) for entry in exc_info.value.diff.entries]
        assert_that(rows).is_equal_to([("b.name", "a", "c")])

    def test_a_config_reaches_a_value_inside_a_nested_model_field(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that({"m": _FakeModel(name="a", items=[1.0, 5.0])}).is_equal_to(
                {"m": _FakeModel(name="c", items=[1.0, 5.0001])}, tolerance=0.001
            )
        rows = [(entry.path, entry.actual, entry.expected) for entry in exc_info.value.diff.entries]
        assert_that(rows).is_equal_to([("m.name", "a", "c")])

    def test_ignore_null_reaches_a_nested_model_field_by_name(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that({"m": _FakeModel(a=1, b=2)}).is_equal_to({"m": _FakeModel(a=9, b=None)}, ignore_null=True)
        assert_that([entry.path for entry in exc_info.value.diff.entries]).is_equal_to(["m.a"])


class TestTextDiffLineNumbers:
    def test_lines_only_one_side_has_are_numbered_from_one(self):
        shorter = _build_equality_diff("a", "a\nb\nc").entries
        assert_that([(entry.path, entry.absent) for entry in shorter]).is_equal_to(
            [("line 2", "actual"), ("line 3", "actual")]
        )
        longer = _build_equality_diff("a\nb\nc", "a").entries
        assert_that([(entry.path, entry.absent) for entry in longer]).is_equal_to(
            [("line 2", "expected"), ("line 3", "expected")]
        )

    def test_two_strings_differing_only_in_a_trailing_newline_keep_both_sides(self):
        # splitlines() drops the difference, so the fallback entry is the only place it survives
        entries = _build_equality_diff("a\n", "a").entries
        assert_that([(entry.path, entry.actual, entry.expected) for entry in entries]).is_equal_to([(".", "a\n", "a")])


class TestAComparatorOwnsTheWholeValue:
    """A comparator asked about a container answers for the container, not for its parts."""

    def test_a_comparator_verdict_on_a_list_field_is_one_row(self):
        @dataclass
        class Basket:
            name: str
            items: list

        with pytest.raises(AssertionError) as exc_info:
            assert_that(Basket("a", [1, 2])).is_equal_to(
                Basket("b", [1, 3]), comparators={list: lambda left, right: False}
            )
        rows = [(entry.path, entry.actual, entry.expected) for entry in exc_info.value.diff.entries]
        assert_that(rows).is_equal_to([(".name", "a", "b"), (".items", [1, 2], [1, 3])])

    def test_a_comparator_verdict_on_a_namedtuple_list_field_is_one_row(self):
        Bag = namedtuple("Bag", "name items")
        with pytest.raises(AssertionError) as exc_info:
            assert_that(Bag("a", [1, 2])).is_equal_to(Bag("b", [1, 3]), comparators={list: lambda left, right: False})
        rows = [(entry.path, entry.actual, entry.expected) for entry in exc_info.value.diff.entries]
        assert_that(rows).is_equal_to([(".name", "a", "b"), (".items", [1, 2], [1, 3])])

    def test_a_comparator_verdict_on_a_nested_namedtuple_list_field_is_one_row(self):
        Bag = namedtuple("Bag", "name items")
        with pytest.raises(AssertionError) as exc_info:
            assert_that({"bag": Bag("a", [1, 2])}).is_equal_to(
                {"bag": Bag("b", [1, 3])}, comparators={list: lambda left, right: False}
            )
        rows = [(entry.path, entry.actual, entry.expected) for entry in exc_info.value.diff.entries]
        assert_that(rows).is_equal_to([("bag.name", "a", "b"), ("bag.items", [1, 2], [1, 3])])

    def test_a_comparator_verdict_on_a_nested_model_field_is_one_row(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that({"m": _FakeModel(name="a", items=[1, 2])}).is_equal_to(
                {"m": _FakeModel(name="b", items=[1, 3])}, comparators={list: lambda left, right: False}
            )
        rows = [(entry.path, entry.actual, entry.expected) for entry in exc_info.value.diff.entries]
        assert_that(rows).is_equal_to([("m.name", "a", "b"), ("m.items", [1, 2], [1, 3])])


class TestStrictTypesLooksPastAnEqualContainer:
    """A strict descent ends where the value stops coming apart, and that ending means equal."""

    def test_an_equal_set_it_had_to_look_inside_is_not_a_row(self):
        Bag = namedtuple("Bag", "name tags")
        with pytest.raises(AssertionError) as exc_info:
            assert_that({"name": "a", "tags": {1, 2}}).is_equal_to({"name": "b", "tags": {1, 2}}, strict_types=True)
        rows = [(entry.path, entry.actual) for entry in exc_info.value.diff.entries]
        assert_that(rows).is_equal_to([("name", "a")])
        with pytest.raises(AssertionError) as exc_info:
            assert_that({"b": Bag("a", {1, 2})}).is_equal_to({"b": Bag("c", {1, 2})}, strict_types=True)
        rows = [(entry.path, entry.actual) for entry in exc_info.value.diff.entries]
        assert_that(rows).is_equal_to([("b.name", "a")])
        with pytest.raises(AssertionError) as exc_info:
            assert_that({"m": _FakeModel(name="a", tags={1, 2})}).is_equal_to(
                {"m": _FakeModel(name="c", tags={1, 2})}, strict_types=True
            )
        rows = [(entry.path, entry.actual) for entry in exc_info.value.diff.entries]
        assert_that(rows).is_equal_to([("m.name", "a")])

    def test_a_key_whose_type_differs_is_reported_under_that_key(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that({True: "a"}).is_equal_to({1: "a"}, strict_types=True)
        rows = [(entry.path, entry.actual, entry.expected) for entry in exc_info.value.diff.entries]
        assert_that(rows).is_equal_to([("True", True, 1)])
