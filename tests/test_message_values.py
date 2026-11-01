"""A value a failure message prints is capped, in every assertion and not in one.

`is_equal_to` capped the values of its first line.  A hundred other messages printed theirs whole, so a failed
``is_length`` over 300 rows put 15 000 characters ahead of the length it was about, and a value of megabytes went
into the log as one line.

Held two ways.  By the tree: no f-string field calls `_safe_str`, `_safe_repr`, `str` or `repr` on a value.
That is the reach of the search and no more: a value put in a variable first, or through ``format``, passes
it.  By a run of each family of assertion over a value far past the cap: the line stays within reach of it,
says how much it left out, still ends in what was asked, and the failure holds the value whole.

A capped value keeps both its ends.  Two texts held against each other are cut around the place they part by
the rule of the assertion, so a comparison that ignores case is not shown a difference of case.  A value
within the cap prints as it always did, a text with line breaks in it included: the break is not escaped, and
the predicate then stands on a later line.
"""

from __future__ import annotations

import ast
import pathlib
import sys

import pytest

from assertpy import AssertionFailure, assert_that, errors, match, soft_assertions

_PACKAGE = pathlib.Path(__file__).resolve().parent.parent / "assertpy"
_RAW = frozenset({"_safe_str", "_safe_repr", "str", "repr"})
_CAP = 4000
_ROWS = [{"id": index, "name": f"user{index}", "tags": ["a", "b"]} for index in range(300)]
_TEXT = "lorem ipsum " * 1500


def _raw_interpolations() -> list[str]:
    """Every f-string field outside the renderer module that prints a value through a call with no cap."""
    found = []
    for path in sorted(_PACKAGE.rglob("*.py")):
        if path.name == "errors.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.FormattedValue):
                continue
            called = node.value
            if not (isinstance(called, ast.Call) and isinstance(called.func, ast.Name) and called.func.id in _RAW):
                continue
            found.append(f"{path.relative_to(_PACKAGE).as_posix()}:{node.lineno} {called.func.id}")
    return found


def test_no_message_prints_a_value_without_the_cap():
    assert_that(_raw_interpolations()).described_as(
        "a value interpolated raw: print it through _capped, _capped_repr or _capped_format"
    ).is_empty()


def test_the_search_sees_what_it_looks_for(tmp_path, monkeypatch):
    planted = tmp_path / "planted.py"
    planted.write_text("def message(value):\n    return f'Expected <{_safe_str(value)}> to be so'\n", encoding="utf-8")
    monkeypatch.setattr(sys.modules[__name__], "_PACKAGE", tmp_path)
    assert_that(_raw_interpolations()).is_equal_to(["planted.py:2 _safe_str"])


_FAILING = {
    "is_length": (lambda: assert_that(_ROWS).is_length(299), "to be of length <299>, but was <300>."),
    "is_empty": (lambda: assert_that(_ROWS).is_empty(), "to be empty, but was not."),
    "is_none": (lambda: assert_that(_ROWS).is_none(), "to be <None>, but was not."),
    "is_instance_of": (lambda: assert_that(_ROWS).is_instance_of(dict), "but was not."),
    "contains": (lambda: assert_that(_ROWS).contains({"id": -1}), "but did not."),
    "is_subset_of": (lambda: assert_that(_ROWS).is_subset_of([1]), None),
    "is_sorted": (lambda: assert_that([*range(3000), 0]).is_sorted(), None),
    "contains_key": (
        lambda: assert_that({"items": _ROWS}).contains_key("missing"),
        "to contain key <missing>, but did not.",
    ),
    "contains_entry": (lambda: assert_that({"items": _ROWS, "n": 1}).contains_entry({"n": 2}), None),
    "contains_value": (lambda: assert_that({"items": _ROWS}).contains_value(1), None),
    "starts_with": (lambda: assert_that(_TEXT).starts_with("dolor"), "to start with <dolor>, but did not."),
    "matches": (lambda: assert_that(_TEXT).matches(r"^\d+$"), "but did not."),
    "satisfies": (lambda: assert_that(_ROWS).satisfies(match.has_length(1)), "with length <300>."),
    "is_in": (lambda: assert_that(1).is_in(*range(2, 3000)), "but was not."),
    "is_equal_to_ignoring_case": (lambda: assert_that(_TEXT).is_equal_to_ignoring_case("x"), "but was not."),
    "is_same_as": (lambda: assert_that(_ROWS).is_same_as(list(_ROWS)), "but was not."),
}


@pytest.mark.parametrize("name", sorted(_FAILING))
def test_a_value_far_past_the_cap_leaves_the_message_within_reach_of_it(name):
    call, ending = _FAILING[name]
    with pytest.raises(AssertionFailure) as caught:
        call()
    first = caught.value._message.splitlines()[0]
    # at most three values to a line, each cut at the cap, and the words between them
    assert_that(len(first)).is_less_than(3 * _CAP + 500)
    assert_that(first).contains("more chars)")
    if ending is not None:
        assert_that(first).ends_with(ending)


def test_the_failure_holds_the_value_whole_and_the_message_both_its_ends():
    with pytest.raises(AssertionFailure) as caught:
        assert_that(_ROWS).is_length(299)
    assert_that(caught.value.actual).is_same_as(_ROWS)
    whole = str(_ROWS)
    assert_that(caught.value._message).is_equal_to(
        f"Expected <{whole[:3000]}... ({len(whole) - _CAP} more chars) ...{whole[-1000:]}>"
        " to be of length <299>, but was <300>."
    )


def test_the_end_of_a_long_text_is_in_a_message_about_its_end():
    text = "lorem ipsum " * 1500 + "the very end"
    with pytest.raises(AssertionFailure) as caught:
        assert_that(text).ends_with("the end")
    assert_that(caught.value._message).starts_with(f"Expected <({len(text) - _CAP} more chars) ...").ends_with(
        "ipsum the very end> to end with <the end>, but did not."
    )


class TestTwoTextsHeldAgainstEachOther:
    """Each cut around the place the two part by the rule of the assertion, where either is past the cap.

    Capped by their ends, two long texts that part in the middle read the same.  Cut at the first raw
    difference, a comparison that ignores case showed a difference of case and hid the one that failed it.
    """

    _ONE = "a" * 3500 + "X" + "a" * 3500
    _OTHER = "a" * 3500 + "Y" + "a" * 3500

    def _message(self, call) -> str:
        with pytest.raises(AssertionFailure) as caught:
            call()
        return caught.value._message

    @pytest.mark.parametrize(
        "name",
        [
            "is_equal_to_ignoring_case",
            "is_equal_to_ignoring_whitespace",
            "starts_with",
            "ends_with",
            "starts_with_ignoring_case",
            "ends_with_ignoring_case",
        ],
    )
    @pytest.mark.parametrize(("head", "tail"), [(3500, 3500), (100, 9000), (9000, 100)])
    def test_the_place_they_part_is_in_both(self, name, head, tail):
        # in the middle, near the start and near the end: a cut that is always at one end shows one of these
        one, other = "a" * head + "X" + "a" * tail, "a" * head + "Y" + "a" * tail
        message = self._message(lambda: getattr(assert_that(one), name)(other))
        assert_that(message).contains("aXa").contains("aYa")
        assert_that(len(message)).is_less_than(2 * _CAP + 200)

    @pytest.mark.parametrize(("head", "tail"), [(3500, 3500), (100, 9000), (9000, 100)])
    def test_a_field_asked_by_name(self, head, tail):
        one, other = "a" * head + "X" + "a" * tail, "a" * head + "Y" + "a" * tail
        holder = type("Holder", (), {"body": one})()
        message = self._message(lambda: assert_that(holder).has_body(other))
        assert_that(message).contains("aXa").contains("aYa").ends_with("on attribute <body>, but was not.")

    def test_a_difference_of_case_ahead_of_the_place_a_prefix_parts_is_not_what_is_shown(self):
        one = "A" + "a" * 99 + "X" + "a" * 9000
        other = "a" * 100 + "Y" + "a" * 9000
        message = self._message(lambda: assert_that("z" * 5000 + one).ends_with_ignoring_case(other))
        assert_that(message).contains("aXa").contains("aYa")
        message = self._message(lambda: assert_that(one + "z").starts_with_ignoring_case(other + "y" * 5000))
        assert_that(message).contains("aXa").contains("aYa")

    def test_a_difference_of_case_ahead_of_the_one_that_failed_is_not_what_is_shown(self):
        one = "a" * 100 + "A" + "a" * 6000 + "X" + "a" * 3000
        other = "a" * 100 + "a" + "a" * 6000 + "Y" + "a" * 3000
        message = self._message(lambda: assert_that(one).is_equal_to_ignoring_case(other))
        assert_that(message).contains("aXa").contains("aYa").does_not_contain("aAa")

    @pytest.mark.parametrize(
        "name", ["is_equal_to_ignoring_case", "starts_with_ignoring_case", "ends_with_ignoring_case"]
    )
    def test_a_place_found_in_lowered_text_is_put_back_in_the_raw_one(self, name):
        # each `İ` lowers to two characters, so the place found runs 3000 ahead of the raw one on either side
        stretched = "İ" * 3000
        one = stretched + "a" * 3000 + "X" + "a" * 5000 + stretched
        other = stretched + "a" * 3000 + "Y" + "a" * 5000 + stretched
        message = self._message(lambda: getattr(assert_that(one), name)(other))
        assert_that(message).contains("aXa").contains("aYa")

    def test_a_text_that_lowers_longer_and_runs_out_is_cut_at_its_end(self):
        message = self._message(lambda: assert_that("İ" * 5000).starts_with_ignoring_case("İ" * 5000 + "x"))
        assert_that(message).starts_with("Expected <(1000 more chars) ...İ").contains("...İİ")

    def test_spacing_ahead_of_the_difference_that_failed_is_stepped_over_on_each_side(self):
        one = "select  a,\n b " + "x" * 6000 + " from one " + "y" * 3000
        other = "select a, b " + "x" * 6000 + " from other " + "y" * 3000
        message = self._message(lambda: assert_that(one).is_equal_to_ignoring_whitespace(other))
        assert_that(message).contains("x from one y").contains("x from other y")

    def test_a_long_ending_that_parts_far_from_the_end(self):
        message = self._message(lambda: assert_that("z" + self._ONE).ends_with(self._OTHER))
        assert_that(message).contains("aXa").contains("aYa")

    def test_a_text_that_runs_out_is_shown_at_its_end(self):
        message = self._message(lambda: assert_that("a" * 5000).starts_with("a" * 6000))
        assert_that(message).starts_with("Expected <(1000 more chars) ...aaa").contains(
            f"to start with <(2000 more chars) ...{'a' * _CAP}>"
        )

    def test_two_texts_within_the_cap_print_whole(self):
        message = self._message(lambda: assert_that("abc").is_equal_to_ignoring_case("abd"))
        assert_that(message).is_equal_to("Expected <abc> to be case-insensitive equal to <abd>, but was not.")

    def test_what_is_left_out_is_counted_on_each_side_of_the_cut(self):
        message = self._message(lambda: assert_that(self._ONE).is_equal_to_ignoring_case(self._OTHER))
        assert_that(message).starts_with(
            f"Expected <(1500 more chars) ...{'a' * 2000}X{'a' * 1999}... (1501 more chars)>"
        )


def test_a_pattern_is_capped_as_any_operand_is():
    pattern = "^" + "a" * 9000 + "$"
    for call in (
        lambda: assert_that("b").matches(pattern),
        lambda: assert_that("a" * 9000).does_not_match(pattern),
    ):
        with pytest.raises(AssertionFailure) as caught:
            call()
        assert_that(len(caught.value._message)).is_less_than(2 * _CAP + 200)
        assert_that(caught.value._message).contains("more chars)")


def test_a_number_held_against_the_value_is_capped_and_cannot_break_the_message():
    # past 4300 digits `str()` of an int raises, which used to come out of the assertion in place of its failure
    for divisor in (10**4200, 10**5000):
        with pytest.raises(AssertionFailure) as caught:
            assert_that(7).is_divisible_by(divisor)
        assert_that(len(caught.value._message)).is_less_than(_CAP + 200)
    with pytest.raises(AssertionFailure) as caught:
        assert_that(1).is_close_to(10**4100, 10**4100 - 5)
    # the value held against and the tolerance, each with its own count of what was left out
    assert_that(caught.value._message.count("more chars)")).is_equal_to(2)
    with pytest.raises(AssertionFailure) as caught:
        assert_that(1).is_not_close_to(2, 10**4200)
    assert_that(caught.value._message.count("more chars)")).is_equal_to(1)
    assert_that(match.close_to(1, 10**4200).describe()).contains("more chars)")


def test_a_group_asked_of_a_pattern_is_capped():
    with pytest.raises(AssertionFailure) as caught:
        assert_that("ab").extracting_group(r"(?P<first>a)", "x" * 9000)
    assert_that(len(caught.value._message)).is_less_than(_CAP + 200)
    assert_that(caught.value._message).contains("more chars)")


def test_a_row_a_soft_block_keeps_is_capped():
    rows = {"a": ["x" * 9000], "b": 1, "c": "y" * 9000}
    with pytest.raises(AssertionError) as caught, soft_assertions():
        assert_that(rows).is_equal_to({"a": ["x" * 8999 + "z"], "b": 2})
    report = str(caught.value)
    assert_that(len(report)).is_less_than(5 * _CAP)
    assert_that(report).contains("xz'").contains("b: 1 != 2")


def test_what_decides_a_membership_failure_is_past_the_value_and_whole():
    with pytest.raises(AssertionFailure) as caught:
        assert_that(_ROWS).contains_sequence({"id": 5}, {"id": 4})
    assert_that(caught.value._message).ends_with(
        "to contain sequence <{'id': 5}, {'id': 4}>, but did not. No run started with <{'id': 5}>."
    )
    with pytest.raises(AssertionFailure) as caught:
        assert_that([*range(3000), -7]).is_subset_of(range(3000))
    assert_that(caught.value._message).ends_with("but <-7> was missing.")
    with pytest.raises(AssertionFailure) as caught:
        assert_that([*range(1500), -1, *range(1500, 3000)]).is_sorted()
    assert_that(caught.value._message).ends_with("to be sorted, but subset <1499, -1> at index 1499 is not.")


def test_a_value_at_the_cap_is_printed_whole():
    exactly = "x" * _CAP
    with pytest.raises(AssertionFailure) as caught:
        assert_that(exactly).is_length(1)
    assert_that(caught.value._message).is_equal_to(f"Expected <{exactly}> to be of length <1>, but was <{_CAP}>.")


def test_a_soft_block_keeps_the_capped_line():
    with pytest.raises(AssertionError) as caught, soft_assertions():
        assert_that(_ROWS).is_length(299)
    assert_that(len(str(caught.value))).is_less_than(_CAP + 500)


def test_a_value_a_matcher_prints_is_capped():
    with pytest.raises(AssertionFailure) as caught:
        assert_that(_TEXT).satisfies(match.is_in(1, 2))
    assert_that(len(caught.value._message)).is_less_than(_CAP + 300)
    assert_that(caught.value._message).contains("more chars)").ends_with("which is not in <(1, 2)>.")


def test_an_operand_and_a_list_of_items_are_capped_too():
    with pytest.raises(AssertionFailure) as caught:
        assert_that("a").is_equal_to_ignoring_case(_TEXT)
    assert_that(len(caught.value._message)).is_less_than(_CAP + 200)
    with pytest.raises(AssertionFailure) as caught:
        assert_that([0]).contains(*range(1, 3000))
    assert_that(len(caught.value._message.splitlines()[0])).is_less_than(2 * _CAP + 200)


class TestWhereTheWholeValueIsAskedFor:
    """One switch lifts the cap, and the pytest plugin turns it on at ``-vv``."""

    def test_a_value_an_operand_and_a_list_of_items_print_whole(self, monkeypatch):
        monkeypatch.setattr(errors, "_WHOLE_VALUES", True)
        with pytest.raises(AssertionFailure) as caught:
            assert_that(_ROWS).is_length(299)
        assert_that(caught.value._message).is_equal_to(f"Expected <{_ROWS}> to be of length <299>, but was <300>.")
        with pytest.raises(AssertionFailure) as caught:
            assert_that([0]).contains(*range(1, 3000))
        assert_that(caught.value._message).does_not_contain("more chars)")

    def test_two_texts_held_against_each_other_print_whole(self, monkeypatch):
        monkeypatch.setattr(errors, "_WHOLE_VALUES", True)
        one, other = "a" * 6000 + "X", "a" * 6000 + "Y"
        with pytest.raises(AssertionFailure) as caught:
            assert_that(one).is_equal_to_ignoring_case(other)
        assert_that(caught.value._message).is_equal_to(
            f"Expected <{one}> to be case-insensitive equal to <{other}>, but was not."
        )

    def test_the_two_values_of_an_equality_print_whole(self, monkeypatch):
        monkeypatch.setattr(errors, "_WHOLE_VALUES", True)
        one, other = object.__new__(_Wide), object.__new__(_Wide)
        with pytest.raises(AssertionFailure) as caught:
            assert_that(one).is_equal_to(other)
        assert_that(caught.value._message).does_not_contain("more chars)").contains("w" * 9000)

    def test_a_row_of_a_diff_and_a_value_of_a_report_stay_cut(self, monkeypatch):
        monkeypatch.setattr(errors, "_WHOLE_VALUES", True)
        assert_that(errors._truncated("x" * 9000, 400)).is_length(400 + len("... (8600 more chars)"))
        assert_that(errors._json_safe("x" * 9000)).ends_with("... (5000 more chars)")

    def test_without_it_the_cap_holds(self):
        assert_that(errors._WHOLE_VALUES).is_false()
        assert_that(errors._truncated("x" * 9000)).ends_with("... (5000 more chars)")


class _Wide:
    def __repr__(self) -> str:
        return "w" * 9000
