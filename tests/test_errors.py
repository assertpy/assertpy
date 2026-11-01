import dataclasses

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st

from assertpy import AssertionFailure, DiffEntry, DiffResult, assert_that, errors, fail, soft_assertions
from assertpy.errors import _first_difference
from assertpy.outcome import MISSING


class TestAssertionFailure:
    def test_is_subclass_of_assertion_error(self):
        assert_that(issubclass(AssertionFailure, AssertionError)).is_true()

    def test_caught_by_except_assertion_error(self):
        try:
            raise AssertionFailure("test message")
        except AssertionError as ex:
            assert_that(str(ex)).is_equal_to("test message")

    def test_message(self):
        err = AssertionFailure("something went wrong")
        assert_that(str(err)).is_equal_to("something went wrong")

    def test_actual_and_expected(self):
        err = AssertionFailure("msg", actual=1, expected=2)
        assert_that(err.actual).is_equal_to(1)
        assert_that(err.expected).is_equal_to(2)
        assert_that(err.diff).is_none()

    def test_actual_none(self):
        err = AssertionFailure("msg", actual=None, expected=42)
        assert_that(err.actual).is_none()
        assert_that(err.expected).is_equal_to(42)

    def test_diff(self):
        diff = DiffResult(
            kind="dict",
            entries=[DiffEntry(path="root.a", actual=1, expected=2)],
        )
        err = AssertionFailure("msg", actual={"a": 1}, expected={"a": 2}, diff=diff)
        assert_that(err.diff).is_not_none()
        assert_that(err.diff.kind).is_equal_to("dict")
        assert_that(err.diff.entries).is_length(1)

    def test_defaults(self):
        err = AssertionFailure("msg")
        assert_that(err.actual).is_none()
        assert_that(err.expected).is_none()
        assert_that(err.diff).is_none()


class TestDiffEntry:
    def test_str(self):
        entry = DiffEntry(path="root.a", actual=1, expected=2)
        assert_that(str(entry)).is_equal_to("  at root.a: actual=<1>, expected=<2>")

    def test_defaults(self):
        entry = DiffEntry(path="root")
        assert_that(entry.actual).is_none()
        assert_that(entry.expected).is_none()

    def test_str_survives_raising_str(self):
        class Bad:
            def __str__(self):
                raise ValueError("boom")

            def __repr__(self):
                return "Bad()"

        assert_that(str(DiffEntry(path="a", actual=Bad(), expected=1))).contains("Bad()")


class TestDiffResult:
    def test_str_empty(self):
        diff = DiffResult(kind="dict")
        assert_that(str(diff)).is_equal_to("")

    def test_str_with_entries(self):
        diff = DiffResult(
            kind="dict",
            entries=[
                DiffEntry(path="root.a", actual=1, expected=2),
                DiffEntry(path="root.b", actual="x", expected="y"),
            ],
        )
        result = str(diff)
        assert_that(result).starts_with("diff (dict):")
        assert_that(result).contains("root.a")
        assert_that(result).contains("root.b")


class TestDiffInMessage:
    """Off pytest (no plugin to render a report section), the structured diff rides on ``str(exc)``."""

    def _failure(self):
        entries = [DiffEntry(path="a", actual=1, expected=2)]
        return AssertionFailure("boom", diff=DiffResult(kind="dict", entries=entries))

    def test_message_carries_the_diff_when_enabled(self, monkeypatch):
        monkeypatch.setattr(errors, "_RENDER_DIFF_IN_MESSAGE", True)
        rendered = str(self._failure())
        assert_that(rendered).starts_with("boom\n")
        assert_that(rendered).contains("diff (dict):")
        assert_that(rendered).contains("- 1")
        assert_that(rendered).contains("+ 2")

    def test_message_is_bare_when_disabled(self, monkeypatch):
        monkeypatch.setattr(errors, "_RENDER_DIFF_IN_MESSAGE", False)
        assert_that(str(self._failure())).is_equal_to("boom")

    def test_no_diff_leaves_the_message_untouched(self, monkeypatch):
        monkeypatch.setattr(errors, "_RENDER_DIFF_IN_MESSAGE", True)
        assert_that(str(AssertionFailure("boom"))).is_equal_to("boom")

    def test_empty_diff_adds_no_trailing_newline(self, monkeypatch):
        monkeypatch.setattr(errors, "_RENDER_DIFF_IN_MESSAGE", True)
        exc = AssertionFailure("boom", diff=DiffResult(kind="dict", entries=[]))
        assert_that(str(exc)).is_equal_to("boom")


class TestStructuredErrorFromAssertions:
    def test_is_equal_to_raises_assertion_failure(self):
        try:
            assert_that(1).is_equal_to(2)
        except AssertionFailure as ex:
            assert_that(ex.actual).is_equal_to(1)
            assert_that(ex.expected).is_equal_to(2)
            assert_that(ex.diff).is_not_none()
            assert_that(ex.diff.kind).is_equal_to("scalar")
            assert_that(ex.diff.entries).is_length(1)
            assert_that(ex.diff.entries[0].path).is_equal_to(".")
            assert_that(ex.diff.entries[0].actual).is_equal_to(1)
            assert_that(ex.diff.entries[0].expected).is_equal_to(2)
        except AssertionError:
            raise AssertionError("expected AssertionFailure, got plain AssertionError") from None

    def test_is_equal_to_string_raises_assertion_failure(self):
        try:
            assert_that("foo").is_equal_to("bar")
        except AssertionFailure as ex:
            assert_that(ex.actual).is_equal_to("foo")
            assert_that(ex.expected).is_equal_to("bar")

    def test_is_equal_to_dict_raises_assertion_failure(self):
        try:
            assert_that({"a": 1, "b": 2}).is_equal_to({"a": 1, "b": 3})
        except AssertionFailure as ex:
            assert_that(ex.actual).is_equal_to({"a": 1, "b": 2})
            assert_that(ex.expected).is_equal_to({"a": 1, "b": 3})
            assert_that(ex.diff).is_not_none()
            assert_that(ex.diff.kind).is_equal_to("dict")
            assert_that(ex.diff.entries).is_length(1)
            assert_that(ex.diff.entries[0].path).is_equal_to("b")
            assert_that(ex.diff.entries[0].actual).is_equal_to(2)
            assert_that(ex.diff.entries[0].expected).is_equal_to(3)

    def test_is_equal_to_dict_nested_diff(self):
        try:
            assert_that({"x": {"y": 1}}).is_equal_to({"x": {"y": 2}})
        except AssertionFailure as ex:
            assert_that(ex.diff).is_not_none()
            assert_that(ex.diff.entries).is_length(1)
            assert_that(ex.diff.entries[0].path).is_equal_to("x.y")

    def test_is_equal_to_dict_missing_keys_diff(self):
        try:
            assert_that({"a": 1, "b": 2}).is_equal_to({"a": 1, "c": 3})
        except AssertionFailure as ex:
            assert_that(ex.diff).is_not_none()
            paths = [entry.path for entry in ex.diff.entries]
            assert_that(paths).contains("b")
            assert_that(paths).contains("c")

    def test_is_equal_to_dict_with_ignore_raises_assertion_failure(self):
        try:
            assert_that({"a": 1, "b": 2, "c": 3}).is_equal_to({"a": 1, "b": 99}, ignore="c")
        except AssertionFailure as ex:
            assert_that(ex.actual).is_equal_to({"a": 1, "b": 2, "c": 3})
            assert_that(ex.expected).is_equal_to({"a": 1, "b": 99})

    def test_is_not_equal_to_raises_the_same_class_as_a_comparison(self):
        # these two once raised a bare AssertionError, so a handler read a different shape per assertion
        with pytest.raises(AssertionFailure) as failure:
            assert_that(1).is_not_equal_to(1)
        assert_that(failure.value.actual).is_equal_to(1)

    def test_is_true_raises_the_same_class_as_a_comparison(self):
        with pytest.raises(AssertionFailure) as failure:
            assert_that(False).is_true()
        assert_that(failure.value.actual).is_false()

    def test_a_negated_assertion_that_fails_raises_it_too(self):
        # NegatedBuilder inverts by catching, so its own failure is the path where nothing was caught
        with pytest.raises(AssertionFailure) as failure:
            assert_that(5).not_.is_positive()
        assert_that(str(failure.value)).is_equal_to("Expected <5> to NOT satisfy: is_positive()")
        assert_that(failure.value.actual).is_equal_to(5)

    def test_a_soft_block_raises_it_too(self):
        with pytest.raises(AssertionFailure) as failure, soft_assertions():
            assert_that(1).is_equal_to(2)
        assert_that(str(failure.value)).contains("soft assertion failures")

    def test_fail_raises_it_too(self):
        with pytest.raises(AssertionFailure) as failure:
            fail("should have raised")
        assert_that(str(failure.value)).is_equal_to("Fail: should have raised!")

    def test_soft_assertions_still_work(self):
        try:
            with soft_assertions():
                assert_that(1).is_equal_to(2)
                assert_that("a").is_equal_to("b")
        except AssertionError as ex:
            assert_that(str(ex)).contains("1.")
            assert_that(str(ex)).contains("2.")

    def test_is_equal_to_pass_does_not_raise(self):
        assert_that(42).is_equal_to(42)
        assert_that("foo").is_equal_to("foo")
        assert_that({"a": 1}).is_equal_to({"a": 1})


class TestMessageTruncation:
    """Rendered failure text is capped; the structured payload always keeps the full data."""

    def test_huge_operand_repr_is_capped(self):
        huge = "x" * 10_000
        with pytest.raises(AssertionError) as exc_info:
            assert_that(huge).is_equal_to("y")
        message = str(exc_info.value)
        assert_that(len(message)).is_less_than(10_000)
        assert_that(message).contains("more chars")

    def test_is_not_equal_to_huge_operands_capped(self):
        huge = "x" * 10_000
        with pytest.raises(AssertionError) as exc_info:
            assert_that(huge).is_not_equal_to(huge)
        message = str(exc_info.value)
        assert_that(len(message)).is_less_than(10_000)
        assert_that(message).contains("more chars")

    def test_huge_dict_message_is_capped_but_payload_is_full(self):
        actual = {index: index for index in range(10_000)}
        expected = {index: index + 1 for index in range(10_000)}
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that(actual).is_equal_to(expected)
        failure = exc_info.value
        assert_that(len(str(failure))).is_less_than(20_000)
        assert_that(failure.diff.entries).is_length(10_000)
        assert_that(failure.actual).is_length(10_000)

    def test_diff_str_renders_at_most_fifty_entries(self):
        entries = [DiffEntry(path=str(index), actual=index, expected=index + 1) for index in range(60)]
        rendered = str(DiffResult(kind="dict", entries=entries))
        assert_that(rendered).contains("... and 10 more entries")
        # header + 50 visible entries (3 lines each: path, -actual, +expected) + the truncation line
        assert_that(rendered.splitlines()).is_length(152)

    def test_diff_str_at_fifty_entries_is_not_truncated(self):
        entries = [DiffEntry(path=str(index), actual=index, expected=index + 1) for index in range(50)]
        rendered = str(DiffResult(kind="dict", entries=entries))
        assert_that(rendered).does_not_contain("more entries")
        assert_that(rendered.splitlines()).is_length(151)

    def test_diff_entry_huge_leaf_is_capped(self):
        entry = DiffEntry(path="k", actual="x" * 10_000, expected="y")
        assert_that(len(str(entry))).is_less_than(6_000)
        assert_that(str(entry)).contains("more chars")


def test_is_equal_to_error_survives_raising_str_operand():
    class Bad:
        def __str__(self):
            raise ValueError("boom")

        def __repr__(self):
            return "Bad()"

    with pytest.raises(AssertionError):
        assert_that(Bad()).is_equal_to(42)


class TestEveryFailureCarriesTheValueUnderTest:
    """Before this, `actual` reached the exception only when an assertion passed it explicitly, which
    34 of 163 failure sites did. The message of every one of them reads "Expected <val> to ...", so the
    subject was always there in text and almost never in the structured channel."""

    def test_a_failure_that_never_named_actual_still_carries_it(self):
        with pytest.raises(AssertionFailure) as failure:
            assert_that([1, 2]).contains_exactly(1)
        assert_that(failure.value.actual).is_equal_to([1, 2])

    def test_the_record_says_the_value_was_filled_in_rather_than_named(self):
        with pytest.raises(AssertionFailure) as failure:
            assert_that([1, 2]).contains_exactly(1)
        assert_that(failure.value._outcome.actual_provided).is_false()

    def test_an_assertion_that_names_its_own_actual_is_marked_as_such(self):
        with pytest.raises(AssertionFailure) as failure:
            assert_that({"a": 1}).is_equal_to({"a": 2})
        assert_that(failure.value._outcome.actual_provided).is_true()
        assert_that(failure.value.actual).is_equal_to({"a": 1})

    def test_an_expected_of_none_is_told_from_no_expected_at_all(self):
        # `expected is not None` cannot answer this, which is why the record carries a sentinel
        with pytest.raises(AssertionFailure) as failure:
            assert_that({}).is_equal_to(None)
        assert_that(failure.value._outcome.has_expected).is_true()
        assert_that(failure.value.expected).is_none()

    @pytest.mark.parametrize(
        ("call", "named"),
        [
            (lambda: assert_that({}).is_equal_to(None), True),
            (lambda: assert_that(-1).is_positive(), True),
            (lambda: assert_that([]).is_not_empty(), False),
            (lambda: assert_that(None).is_not_none(), False),
            (lambda: assert_that([1, 1]).does_not_contain_duplicates(), False),
        ],
        ids=["compared against None", "boundary", "negation", "about the value alone", "no operand"],
    )
    def test_the_flag_a_reporter_reads_says_the_same_as_the_record(self, call, named):
        """The reading a reporter outside this package can do, which used to need the private record."""
        with pytest.raises(AssertionFailure) as failure:
            call()
        assert_that(failure.value.has_expected).is_equal_to(named)
        assert_that(failure.value.has_expected).is_equal_to(failure.value._outcome.has_expected)

    def test_a_failure_built_outside_an_assertion_falls_back_to_the_older_reading(self):
        # it carries no record, so the flag answers from the attribute, which is all there is there
        assert_that(AssertionFailure("plain").has_expected).is_false()
        assert_that(AssertionFailure("plain", expected=0).has_expected).is_true()

    def test_the_two_failures_this_library_builds_without_a_record_still_answer(self):
        """`fail()` and the aggregate a soft block raises are built directly, not composed.

        Both name no expectation and hold ``None``, so the fallback is right about them.  Pinned
        because the property's own words say so, and a promise nothing tests is a promise that rots.
        """
        with pytest.raises(AssertionFailure) as raised:
            fail("boom")
        assert_that(raised.value._outcome).is_none()
        assert_that(raised.value.has_expected).is_false()

        with pytest.raises(AssertionFailure) as aggregate, soft_assertions():
            assert_that(1).is_equal_to(2)
        assert_that(aggregate.value._outcome).is_none()
        assert_that(aggregate.value.has_expected).is_false()

    def test_a_failure_built_outside_an_assertion_has_no_record(self):
        assert_that(AssertionFailure("plain")._outcome).is_none()

    def test_the_sentinel_reprs_as_itself(self):
        assert_that(repr(MISSING)).is_equal_to("MISSING")


class TestEveryDifferenceCarriesAMachineReadablePath:
    """`path` is written for a person and cannot be read back: a mapping key goes through `str()`, so
    `{3: ...}` and `{"3": ...}` render the same, and a key holding a dot or a bracket has no grammar to
    parse it with. `steps` is the same location in the form a program can act on."""

    def test_a_nested_mapping_key_keeps_its_own_type(self):
        with pytest.raises(AssertionFailure) as failure:
            assert_that({"outer": {3: "a"}}).is_equal_to({"outer": {3: "b"}})
        entry = failure.value.diff.entries[0]
        assert_that(entry.path).is_equal_to("outer.3")
        assert_that([(step.kind, step.value) for step in entry.steps]).is_equal_to([("key", "outer"), ("key", 3)])

    def test_an_integer_key_is_told_from_the_string_that_renders_the_same(self):
        with pytest.raises(AssertionFailure) as integer_key:
            assert_that({3: "a"}).is_equal_to({3: "b"})
        with pytest.raises(AssertionFailure) as string_key:
            assert_that({"3": "a"}).is_equal_to({"3": "b"})
        assert_that(integer_key.value.diff.entries[0].path).is_equal_to(string_key.value.diff.entries[0].path)
        assert_that(integer_key.value.diff.entries[0].steps[0].value).is_equal_to(3)
        assert_that(string_key.value.diff.entries[0].steps[0].value).is_equal_to("3")

    def test_a_sequence_position_is_an_index_not_a_bracketed_string(self):
        with pytest.raises(AssertionFailure) as failure:
            assert_that([{"n": 1}]).is_equal_to([{"n": 2}])
        entry = failure.value.diff.entries[0]
        assert_that(entry.path).is_equal_to("[0].n")
        assert_that([(step.kind, step.value) for step in entry.steps]).is_equal_to([("index", 0), ("key", "n")])

    def test_a_field_step_names_the_attribute(self):
        @dataclasses.dataclass
        class Point:
            x: int

        with pytest.raises(AssertionFailure) as failure:
            assert_that(Point(1)).is_equal_to(Point(2))
        entry = failure.value.diff.entries[0]
        assert_that(entry.path).is_equal_to(".x")
        assert_that([(step.kind, step.value) for step in entry.steps]).is_equal_to([("attr", "x")])

    def test_a_shifted_sequence_names_the_side_its_index_belongs_to(self):
        # once alignment shifts the two apart, an index without a side names two different elements
        with pytest.raises(AssertionFailure) as failure:
            assert_that([1, 2, 3, 4]).is_equal_to([0, 1, 2, 3, 4])
        one_sided = [entry for entry in failure.value.diff.entries if entry.absent is not None]
        assert_that(one_sided).is_not_empty()
        assert_that({step.side for entry in one_sided for step in entry.steps}).does_not_contain(None)

    def test_a_set_member_has_no_position_so_the_step_carries_the_member(self):
        with pytest.raises(AssertionFailure) as failure:
            assert_that({1, 2}).is_equal_to({1, 3})
        kinds = {step.kind for entry in failure.value.diff.entries for step in entry.steps}
        values = {step.value for entry in failure.value.diff.entries for step in entry.steps}
        assert_that(kinds).is_equal_to({"item"})
        assert_that(values).is_equal_to({2, 3})

    def test_a_text_difference_steps_by_line_number(self):
        with pytest.raises(AssertionFailure) as failure:
            assert_that("a\nb").is_equal_to("a\nc")
        entry = failure.value.diff.entries[0]
        assert_that(entry.path).is_equal_to("line 2")
        assert_that([(step.kind, step.value) for step in entry.steps]).is_equal_to([("line", 2)])

    def test_the_whole_value_differing_takes_no_steps_at_all(self):
        with pytest.raises(AssertionFailure) as failure:
            assert_that(1).is_equal_to(2)
        assert_that(failure.value.diff.entries[0].path).is_equal_to(".")
        assert_that(failure.value.diff.entries[0].steps).is_empty()

    def test_the_steps_walk_back_into_the_value_they_came_from(self):
        # the whole point: a reader can reach the differing part without parsing the rendered path
        actual = {"users": [{"roles": {7: "admin"}}]}
        with pytest.raises(AssertionFailure) as failure:
            assert_that(actual).is_equal_to({"users": [{"roles": {7: "guest"}}]})
        cursor = failure.value.actual
        for step in failure.value.diff.entries[0].steps:
            cursor = cursor[step.value]
        assert_that(cursor).is_equal_to("admin")


class TestFindingTheFirstDifference:
    """The window around a change is cut there, and the search for it used to run character by character."""

    @pytest.mark.parametrize(
        ("actual", "expected", "at"),
        [
            pytest.param("abc", "abd", 2, id="last"),
            pytest.param("abc", "xbc", 0, id="first"),
            pytest.param("abc", "abc", 3, id="equal"),
            pytest.param("", "abc", 0, id="empty-left"),
            pytest.param("abc", "", 0, id="empty-right"),
            pytest.param("abc", "abcdef", 3, id="prefix"),
            pytest.param("\U0001f600x", "\U0001f600y", 1, id="astral"),
        ],
    )
    def test_it_lands_where_the_character_walk_lands(self, actual, expected, at):
        assert_that(_first_difference(actual, expected)).is_equal_to(at)

    @settings(max_examples=300, deadline=None)
    @given(actual=st.text(alphabet="ab", max_size=12), expected=st.text(alphabet="ab", max_size=12))
    @example(actual="", expected="")
    @example(actual="ab", expected="ab")
    def test_it_agrees_with_the_character_walk(self, actual, expected):
        shared = min(len(actual), len(expected))
        walked = next((index for index in range(shared) if actual[index] != expected[index]), shared)
        assert_that(_first_difference(actual, expected)).is_equal_to(walked)
