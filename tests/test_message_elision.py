"""Direct tests for the helpers that collapse a value before it goes into a failure message.

Everything here was reachable only through an assertion failure, and the messages those produce were
asserted whole, so the thresholds themselves were never pinned: shifting any of them by one still
produced a plausible-looking message. A value one element or one character either side of a boundary
is the only thing that tells them apart.
"""

import collections

import pytest
from hypothesis import example, given
from hypothesis import strategies as st

from assertpy import assert_that, helpers
from assertpy._engine._diff import _aligned_match_indices
from assertpy.helpers import (
    _ELIDED,
    _both_list_like,
    _elided_seq_repr,
    _elided_text_repr,
    _joined_parts,
)


class TestSequenceElisionBoundaries:
    """A short sequence is printed whole; past either cap only the differing elements are kept.

    Two caps, checked in order: at most 20 elements, and at most 60 characters once rendered. The
    element cap comes first so a long sequence is never rendered just to be measured, which on the
    failure path is the whole value.
    """

    def test_twenty_elements_rendering_to_sixty_characters_is_printed_whole(self):
        seq = [1] * 20
        assert_that(repr(seq)).is_length(60)
        assert_that(_elided_seq_repr(seq, [9] * 20)).is_equal_to(repr(seq))

    def test_twenty_one_elements_are_collapsed(self):
        # the counterpart matches everywhere but the last slot; 21 one-character elements never fit 60
        # characters anyway, so raising the element cap alone cannot change this answer
        assert_that(_elided_seq_repr([*[1] * 20, 2], [1] * 21)).is_equal_to("[.., 2]")

    def test_sixty_one_characters_are_collapsed(self):
        seq = [1] * 19 + [10]
        assert_that(repr(seq)).is_length(61)
        assert_that(_elided_seq_repr(seq, [*[1] * 19, 99])).is_equal_to("[.., 10]")

    def test_a_sequence_longer_than_its_counterpart_does_not_index_past_it(self):
        # the positional fallback pairs by index and has to stop at the shorter side
        assert_that(_elided_seq_repr([7] * 30, [7, 7])).contains("7")

    def test_a_tuple_keeps_its_own_brackets(self):
        actual = (*(1,) * 20, 2)
        assert_that(_elided_seq_repr(actual, (1,) * 21)).is_equal_to("(.., 2)")

    def test_a_tuple_of_one_keeps_its_comma(self):
        # without it `('aaa')` read as that one text in brackets, not as a tuple holding it
        long = "a" * 70
        assert_that(_elided_seq_repr((long,), ("b",))).is_equal_to(f"('{long}',)")
        assert_that(_elided_seq_repr((long,), (long,))).is_equal_to("(..,)")
        assert_that(_elided_seq_repr([long], ["b"])).is_equal_to(f"['{long}']")
        assert_that(_elided_seq_repr((long, long), ("b", "c"))).is_equal_to(f"('{long}', '{long}')")
        with pytest.raises(AssertionError) as caught:
            assert_that((long,)).is_equal_to(("b" * 70,))
        assert_that(str(caught.value)).starts_with(f"Expected <('{long}',)> to be equal to <('{'b' * 70}',)>")


class TestTextElisionBoundary:
    def test_three_lines_are_printed_whole(self):
        text = "a\nb\nc"
        assert_that(_elided_text_repr(text, "a\nb\nZ")).is_equal_to(text)

    def test_four_lines_are_collapsed_to_the_changed_ones(self):
        # the cost of a multi-line value is vertical, and the message prints the value twice
        collapsed = _elided_text_repr("a\nb\nc\nd", "a\nZ\nc\nd")
        # line 1 matched ahead of the change and lines 3-4 matched behind it, so the change is marked
        # on both sides
        assert_that(collapsed).is_equal_to(".., line 2: b, ..")


class TestJoinedPartsCap:
    """Collapsing only removes what matched, so a value where nearly everything differs still prints
    in full. The cap on spelled-out parts is what keeps that from becoming a wall of text."""

    def test_five_parts_are_all_spelled_out(self):
        assert_that(_joined_parts([str(index) for index in range(5)])).is_equal_to("0, 1, 2, 3, 4")

    def test_the_sixth_part_turns_into_a_count(self):
        assert_that(_joined_parts([str(index) for index in range(6)])).is_equal_to("0, 1, 2, 3, 4, ... and 1 more")

    def test_the_count_names_how_many_were_dropped(self):
        assert_that(_joined_parts([str(index) for index in range(9)])).is_equal_to("0, 1, 2, 3, 4, ... and 4 more")

    def test_markers_do_not_count_against_the_cap(self):
        """Spending the cap on matches would push out the differing parts the message exists to show."""
        parts = [item for index in range(5) for item in (_ELIDED, str(index))]
        assert_that(_joined_parts(parts)).is_equal_to(".., 0, .., 1, .., 2, .., 3, .., 4")

    def test_a_marker_just_before_the_count_is_dropped(self):
        """The count already stands for everything past the cap, the matched run included."""
        assert_that(_joined_parts([*[str(index) for index in range(5)], _ELIDED, "5"])).is_equal_to(
            "0, 1, 2, 3, 4, ... and 1 more"
        )

    def test_no_marker_survives_past_the_cap(self):
        assert_that(_joined_parts([*[str(index) for index in range(6)], _ELIDED, "6"])).is_equal_to(
            "0, 1, 2, 3, 4, ... and 2 more"
        )

    def test_the_marker_stands_where_the_matched_run_was(self):
        assert_that(_joined_parts([_ELIDED, "x"], opener="[", closer="]")).is_equal_to("[.., x]")
        assert_that(_joined_parts(["x", _ELIDED], opener="[", closer="]")).is_equal_to("[x, ..]")

    def test_an_all_matching_value_is_just_the_marker(self):
        assert_that(_joined_parts([_ELIDED], opener="{", closer="}")).is_equal_to("{..}")


class TestAMatchedRunIsOneMarker:
    """Collapsed where the parts are built, so the join is handed one marker per run, not one per element.

    A marker per matched element held a million references to print three parts, and a helper called per
    element to avoid that cost a failing poll over 200 records a tenth of its time.
    """

    @staticmethod
    def _handed(monkeypatch, render):
        seen: list = []
        real = helpers._joined_parts

        def recording(parts, **options):
            seen.append(list(parts))
            return real(parts, **options)

        monkeypatch.setattr(helpers, "_joined_parts", recording)
        render()
        return seen

    def test_a_long_sequence(self, monkeypatch):
        seen = self._handed(
            monkeypatch, lambda: _elided_seq_repr(list(range(10_000)), [*range(5_000), -1, *range(5_001, 10_000)])
        )
        assert_that(seen).is_equal_to([[_ELIDED, "5000", _ELIDED]])

    def test_a_long_text(self, monkeypatch):
        lines = [f"row {index}" for index in range(1_000)]
        changed = [*lines[:500], "changed", *lines[501:]]
        seen = self._handed(monkeypatch, lambda: _elided_text_repr("\n".join(lines), "\n".join(changed)))
        assert_that(seen).is_equal_to([[_ELIDED, "line 501: row 500", _ELIDED]])

    def test_a_long_mapping_and_the_list_inside_it(self, monkeypatch):
        left = {**{f"k{index}": index for index in range(1_000)}, "rows": list(range(1_000))}
        right = {**left, "k500": -1, "rows": [*range(500), -1, *range(501, 1_000)]}

        def fail():
            with pytest.raises(AssertionError):
                assert_that(left).is_equal_to(right)

        seen = self._handed(monkeypatch, fail)
        assert_that(seen).is_equal_to(
            [
                [_ELIDED, "500", _ELIDED],
                [_ELIDED, "'k500': 500", _ELIDED, "'rows': [.., 500, ..]"],
                [_ELIDED, "-1", _ELIDED],
                [_ELIDED, "'k500': -1", _ELIDED, "'rows': [.., -1, ..]"],
            ]
        )


@given(
    st.lists(st.integers(min_value=0, max_value=9), min_size=21, max_size=60),
    st.sets(st.integers(min_value=0, max_value=59), max_size=5),
    st.booleans(),
)
# shifted with no alignment worth taking, where the positional fallback runs one past the counterpart
@example(value=[0] * 21, changed={0}, shifted=True)
def test_every_matched_run_is_one_marker_in_its_place(value, changed, shifted):
    """Read off the tokens before the cap, since past it the count deliberately throws content away.

    *shifted* puts an extra element in front, which sends the pair down the alignment path #41 was on.
    """
    counterpart = [99 if index in changed else item for index, item in enumerate(value)]
    if shifted:
        value = [42, *value]
    matched = _aligned_match_indices(value, counterpart)
    if matched is None:
        matched = {index for index, item in enumerate(value) if index < len(counterpart) and item == counterpart[index]}
    expected: list = []
    for index, item in enumerate(value):
        if index in matched:
            if not expected or expected[-1] is not _ELIDED:
                expected.append(_ELIDED)
        else:
            expected.append(repr(item))
    seen: list = []
    real = helpers._joined_parts
    helpers._joined_parts = lambda parts, **options: (seen.append(list(parts)), real(parts, **options))[1]
    try:
        _elided_seq_repr(value, counterpart)
    finally:
        helpers._joined_parts = real
    assert_that(seen).is_equal_to([expected])


class TestElisionReachesTheMessage:
    """The same thresholds, through the failure they exist for, so a change of caller wiring shows up
    here rather than only in the unit tests above."""

    def test_a_long_list_failure_names_only_the_differing_element(self):
        actual, expected = list(range(30)), [*range(29), 99]
        with pytest.raises(AssertionError) as exc_info:
            assert_that(actual).is_equal_to(expected)
        message = str(exc_info.value)
        assert_that(message).contains("..").contains("29").contains("99")
        assert_that(message).does_not_contain("15")


class TestNamedtuplesAreNotTreatedAsPlainSequences:
    """A namedtuple carries field names, so it is compared and printed field-wise.  Dropping either
    side's guard would send a pair down the positional path, where the failure reads as a bare tuple
    and the field that changed is identified by index instead of by name."""

    _Point = collections.namedtuple("_Point", ["x", "y"])

    def test_a_namedtuple_pair_is_not_list_like(self):
        assert_that(_both_list_like(self._Point(1, 2), self._Point(1, 3))).is_false()

    def test_a_namedtuple_on_one_side_alone_is_enough(self):
        assert_that(_both_list_like(self._Point(1, 2), (1, 3))).is_false()
        assert_that(_both_list_like((1, 2), self._Point(1, 3))).is_false()

    def test_a_plain_tuple_pair_is_list_like(self):
        assert_that(_both_list_like((1, 2), (1, 3))).is_true()

    def test_the_failure_names_the_field_not_the_index(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that(self._Point(1, 2)).is_equal_to(self._Point(1, 3))
        assert_that(str(exc_info.value)).contains("y=2").contains("y=3")


class TestElisionMarkerPlacement:
    """``..`` stands where the collapsed elements were, so a changed head reads differently from a
    changed tail.

    A single leading marker said only *that* something matched, never where: a sequence differing
    from its counterpart by one extra element at the front printed that element behind the marker,
    as ``[.., 0]``, which reads as a changed tail.
    """

    def test_a_changed_head_keeps_the_marker_behind_it(self):
        seq = [0, *range(1, 40)]
        assert_that(_elided_seq_repr(seq, list(range(1, 40)))).is_equal_to("[0, ..]")

    def test_a_changed_tail_keeps_the_marker_in_front(self):
        assert_that(_elided_seq_repr([*[1] * 20, 2], [1] * 21)).is_equal_to("[.., 2]")

    def test_a_changed_middle_is_marked_on_both_sides(self):
        assert_that(_elided_seq_repr([*[1] * 10, 2, *[1] * 10], [1] * 21)).is_equal_to("[.., 2, ..]")

    def test_two_separate_changes_keep_the_run_between_them(self):
        value = list(range(40))
        value[5], value[30] = 98, 99
        assert_that(_elided_seq_repr(value, list(range(40)))).is_equal_to("[.., 98, .., 99, ..]")

    def test_a_changed_head_reaches_the_failure_message(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that([0, *range(1, 40)]).is_equal_to(list(range(1, 40)))
        assert_that(str(exc_info.value)).contains("<[0, ..]>")

    def test_a_changed_first_line_keeps_the_marker_behind_it(self):
        # the text path collapses by line and marks the run the same way
        assert_that(_elided_text_repr("X\nb\nc\nd", "a\nb\nc\nd")).is_equal_to("line 1: X, ..")

    def test_a_changed_first_key_keeps_the_marker_behind_it(self):
        # and so does the mapping path, where the run is the keys that matched
        with pytest.raises(AssertionError) as exc_info:
            assert_that({"a": 1, "b": 2}).is_equal_to({"a": 9, "b": 2})
        assert_that(str(exc_info.value)).contains("<{'a': 1, ..}>")
