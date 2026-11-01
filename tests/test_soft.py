import contextlib
import contextvars
import io
import logging

import pytest

from assertpy import AssertionFailure, assert_all, assert_that, assert_warn, fail, soft_assertions, soft_fail


def test_success():
    with soft_assertions():
        assert_that("foo").is_length(3)
        assert_that("foo").is_not_empty()
        assert_that("foo").is_true()
        assert_that("foo").is_alpha()
        assert_that("123").is_digit()
        assert_that("foo").is_lower()
        assert_that("FOO").is_upper()
        assert_that("foo").is_equal_to("foo")
        assert_that("foo").is_not_equal_to("bar")
        assert_that("foo").is_equal_to_ignoring_case("FOO")
        assert_that({"a": 1}).has_a(1)


def test_failure():
    with pytest.raises(AssertionError) as exc_info, soft_assertions():
        assert_that("foo").is_length(4)
        assert_that("foo").is_empty()
        assert_that("foo").is_false()
        assert_that("foo").is_digit()
        assert_that("123").is_alpha()
        assert_that("foo").is_upper()
        assert_that("FOO").is_lower()
        assert_that("foo").is_equal_to("bar")
        assert_that("foo").is_not_equal_to("foo")
        assert_that("foo").is_equal_to_ignoring_case("BAR")
        assert_that({"a": 1}).has_a(2)
        assert_that({"a": 1}).has_foo(1)
    out = str(exc_info.value)
    assert_that(out).contains("Expected <foo> to be of length <4>, but was <3>.")
    assert_that(out).contains("Expected <foo> to be empty string, but was not.")
    assert_that(out).contains("Expected <foo> to be <False>, but was not.")
    assert_that(out).contains("Expected <foo> to contain only digits, but did not.")
    assert_that(out).contains("Expected <123> to contain only alphabetic chars, but did not.")
    assert_that(out).contains("Expected <foo> to contain only uppercase chars, but did not.")
    assert_that(out).contains("Expected <FOO> to contain only lowercase chars, but did not.")
    assert_that(out).contains("Expected <foo> to be equal to <bar>, but was not.")
    assert_that(out).contains("Expected <foo> to be not equal to <foo>, but was.")
    assert_that(out).contains("Expected <foo> to be case-insensitive equal to <BAR>, but was not.")
    assert_that(out).contains("Expected <1> to be equal to <2> on key <a>, but was not.")
    assert_that(out).contains("Expected key <foo>, but val has no key <foo>.")


def test_failure_chain():
    with pytest.raises(AssertionError) as exc_info, soft_assertions():
        assert_that("foo").is_length(4).is_empty().is_false().is_digit().is_upper().is_equal_to("bar").is_not_equal_to(
            "foo"
        ).is_equal_to_ignoring_case("BAR")
    out = str(exc_info.value)
    assert_that(out).contains("Expected <foo> to be of length <4>, but was <3>.")
    assert_that(out).contains("Expected <foo> to be empty string, but was not.")
    assert_that(out).contains("Expected <foo> to be <False>, but was not.")
    assert_that(out).contains("Expected <foo> to contain only digits, but did not.")
    assert_that(out).contains("Expected <foo> to contain only uppercase chars, but did not.")
    assert_that(out).contains("Expected <foo> to be equal to <bar>, but was not.")
    assert_that(out).contains("Expected <foo> to be not equal to <foo>, but was.")
    assert_that(out).contains("Expected <foo> to be case-insensitive equal to <BAR>, but was not.")


def test_expected_exception_success():
    with soft_assertions():
        assert_that(func_err).raises(RuntimeError).when_called_with("foo").is_equal_to("err")


def test_expected_exception_failure():
    with pytest.raises(AssertionError) as exc_info, soft_assertions():
        assert_that(func_err).raises(RuntimeError).when_called_with("foo").is_equal_to("bar")
        assert_that(func_ok).raises(RuntimeError).when_called_with("baz")
    out = str(exc_info.value)
    assert_that(out).contains("Expected <err> to be equal to <bar>, but was not.")
    assert_that(out).contains("Expected <func_ok> to raise <RuntimeError> when called with ('baz').")


def func_ok(arg):
    pass


def func_err(arg):
    raise RuntimeError("err")


def test_fail():
    with pytest.raises(AssertionError) as exc_info, soft_assertions():
        fail()
    out = str(exc_info.value)
    assert_that(out).is_equal_to("Fail!")


def test_fail_with_msg():
    with pytest.raises(AssertionError) as exc_info, soft_assertions():
        fail("foobar")
    out = str(exc_info.value)
    assert_that(out).is_equal_to("Fail: foobar!")


def test_fail_with_soft_failing_asserts():
    with pytest.raises(AssertionError) as exc_info, soft_assertions():
        assert_that("foo").is_length(4)
        assert_that("foo").is_empty()
        fail("foobar")
        assert_that("foo").is_not_equal_to("foo")
        assert_that("foo").is_equal_to_ignoring_case("BAR")
    out = str(exc_info.value)
    assert_that(out).is_equal_to("Fail: foobar!")
    assert_that(out).does_not_contain("Expected <foo> to be of length <4>, but was <3>.")
    assert_that(out).does_not_contain("Expected <foo> to be empty string, but was not.")
    assert_that(out).does_not_contain("Expected <foo> to be not equal to <foo>, but was.")
    assert_that(out).does_not_contain("Expected <foo> to be case-insensitive equal to <BAR>, but was not.")


def test_double_fail():
    with pytest.raises(AssertionError) as exc_info, soft_assertions():
        fail()
        fail("foobar")
    out = str(exc_info.value)
    assert_that(out).is_equal_to("Fail!")


def test_nested():
    with pytest.raises(AssertionError) as exc_info, soft_assertions():
        assert_that("a").is_equal_to("A")
        with soft_assertions():
            assert_that("b").is_equal_to("B")
            with soft_assertions():
                assert_that("c").is_equal_to("C")
            assert_that("b").is_equal_to("B2")
        assert_that("a").is_equal_to("A2")
    out = str(exc_info.value)
    assert_that(out).contains("1. Expected <a> to be equal to <A>, but was not.")
    assert_that(out).contains("2. Expected <b> to be equal to <B>, but was not.")
    assert_that(out).contains("3. Expected <c> to be equal to <C>, but was not.")
    assert_that(out).contains("4. Expected <b> to be equal to <B2>, but was not.")
    assert_that(out).contains("5. Expected <a> to be equal to <A2>, but was not.")


def test_raises_no_exception_chaining():
    with pytest.raises(AssertionError) as exc_info, soft_assertions():
        assert_that(lambda x: 1 / x).raises(ZeroDivisionError).when_called_with(1).is_equal_to("dog").matches("cat")
    out = str(exc_info.value)
    assert_that(out).contains("Expected <<lambda>> to raise <ZeroDivisionError> when called with (1).")
    assert_that(out).does_not_contain("TypeError")


def test_raises_wrong_exception_chaining():
    with pytest.raises(AssertionError) as exc_info, soft_assertions():
        assert_that({}.__getitem__).raises(RuntimeError).when_called_with("a").contains("dog")
    out = str(exc_info.value)
    assert_that(out).contains("Expected <__getitem__> to raise <RuntimeError>")
    assert_that(out).contains("but raised <KeyError>")
    assert_that(out).does_not_contain("TypeError")


def test_raises_mixed_chaining():
    with pytest.raises(AssertionError) as exc_info, soft_assertions():
        assert_that(lambda x: 1 / x).raises(ZeroDivisionError).when_called_with(1).is_equal_to("dog")
        assert_that({}.__getitem__).raises(RuntimeError).when_called_with("a").contains("dog")
        assert_that(lambda x: 1 / x).raises(ZeroDivisionError).when_called_with(0).matches("dog")
    out = str(exc_info.value)
    assert_that(out).contains("1.")
    assert_that(out).contains("2.")
    assert_that(out).contains("3.")
    assert_that(out).does_not_contain("TypeError")


def test_recursive_nesting():
    def recurs(i):
        if i <= 0:
            return
        with soft_assertions():
            recurs(i - 1)
            assert_that(i).is_equal_to(7)

    try:
        recurs(10)
    except AssertionError as exc:
        out = str(exc)
        assert_that(out).contains("1. Expected <1> to be equal to <7>, but was not.")
        assert_that(out).contains("2. Expected <2> to be equal to <7>, but was not.")
        assert_that(out).contains("3. Expected <3> to be equal to <7>, but was not.")
        assert_that(out).contains("4. Expected <4> to be equal to <7>, but was not.")
        assert_that(out).contains("5. Expected <5> to be equal to <7>, but was not.")
        assert_that(out).contains("6. Expected <6> to be equal to <7>, but was not.")


class TestSoftFailuresCarryTheirDiff:
    """A collected failure keeps the paths its hard counterpart would have shown."""

    def test_nested_difference_names_its_path(self):
        with pytest.raises(AssertionError) as exc_info, soft_assertions():
            assert_that({"a": {"b": 1}}).is_equal_to({"a": {"b": 2}})
        assert_that(str(exc_info.value)).contains("a.b: 1 != 2")

    def test_missing_item_is_named_without_its_empty_counterpart(self):
        with pytest.raises(AssertionError) as exc_info, soft_assertions():
            assert_that([1, 2]).contains(3)
        message = str(exc_info.value)
        assert_that(message).contains("missing: 3")
        assert_that(message).does_not_contain("None")

    def test_extra_item_is_named_without_its_empty_counterpart(self):
        with pytest.raises(AssertionError) as exc_info, soft_assertions():
            assert_that({1, 2, 3}).is_equal_to({1, 2})
        message = str(exc_info.value)
        assert_that(message).contains("extra: 3")
        assert_that(message).does_not_contain("None")

    def test_many_differences_are_capped(self):
        with pytest.raises(AssertionError) as exc_info, soft_assertions():
            assert_that({f"k{i}": i for i in range(9)}).is_equal_to({f"k{i}": -i for i in range(9)})
        # on the indented diff lines: the headline's own cap is worded identically, so contains() would pass
        diff_lines = [line for line in str(exc_info.value).splitlines() if line.startswith("   ")]
        assert_that(diff_lines).is_length(6)
        assert_that(diff_lines[-1].strip()).is_equal_to("... and 3 more")

    def test_a_scalar_failure_adds_no_line(self):
        with pytest.raises(AssertionError) as exc_info, soft_assertions():
            assert_that(1).is_equal_to(2)
        assert_that(str(exc_info.value).splitlines()).is_length(2)

    def test_a_short_line_of_text_adds_no_line_either(self):
        with pytest.raises(AssertionError) as exc_info, soft_assertions():
            assert_that("hello").is_equal_to("hallo")
        assert_that(str(exc_info.value).splitlines()).is_length(2)

    def test_a_long_line_of_text_is_windowed_onto_its_difference(self):
        # without the window the collected failure said only that two 181-character payloads were unequal
        actual, expected = "x" * 90 + "A" + "y" * 90, "x" * 90 + "B" + "y" * 90
        with pytest.raises(AssertionError) as exc_info, soft_assertions():
            assert_that(actual).is_equal_to(expected)
        detail = str(exc_info.value).splitlines()[-1]
        assert_that(detail).starts_with("   line 1: ").contains("xA").contains("xB")
        assert_that(detail).described_as("both sides are cut, not one").contains("more chars) != ")

    def test_a_long_bytes_value_is_windowed_the_same_way(self):
        actual, expected = b"a" * 80 + b"X" + b"b" * 80, b"a" * 80 + b"Y" + b"b" * 80
        with pytest.raises(AssertionError) as exc_info, soft_assertions():
            assert_that(actual).is_equal_to(expected)
        # on the detail line: the headline carries both values, so `contains("aX")` passed against the entry
        detail = str(exc_info.value).splitlines()[-1]
        assert_that(detail).starts_with("   line 1: ").contains("aX").contains("aY")

    def test_a_message_of_several_lines_stays_one_entry(self):
        # the hint adds a second line; rendered flat, the location landed at its end and the entry read as two
        with pytest.raises(AssertionError) as exc_info, soft_assertions():
            assert_that({"a": b"x", "b": b"y"}).is_equal_to({"a": "x", "b": "y"})
            assert_that(1).is_equal_to(2)
        first, second, *_rest, last = str(exc_info.value).splitlines()
        assert_that(first).is_equal_to("soft assertion failures:")
        assert_that(second).starts_with("1. Expected").ends_with("]")
        assert_that(_rest[0]).is_equal_to("   every difference here is one of bytes against decoded text")
        assert_that(last).starts_with("2. Expected <1>")


class TestTheAggregateHandsBackWhatItCollected:
    """A soft block used to flatten every failure into one string at its boundary: the collector held
    tuples of (group, location, message, diff) and the raise turned them into a numbered list. The text
    is unchanged, and the parts it was rendered from now ride on the exception."""

    def test_the_aggregate_carries_one_record_per_collected_failure(self):
        with pytest.raises(AssertionFailure) as failure, soft_assertions():
            assert_that({"a": 1}).is_equal_to({"a": 2})
            assert_that("foo").is_length(4)
        assert_that(failure.value.failures).is_length(2)
        assert_that([outcome.message for outcome in failure.value.failures]).is_equal_to(
            [
                "Expected <{'a': 1}> to be equal to <{'a': 2}>, but was not.",
                "Expected <foo> to be of length <4>, but was <3>.",
            ]
        )

    def test_each_record_keeps_the_structure_the_message_had_flattened(self):
        with pytest.raises(AssertionFailure) as failure, soft_assertions():
            assert_that({"a": 1}).is_equal_to({"a": 2})
        collected = failure.value.failures[0]
        assert_that(collected.actual).is_equal_to({"a": 1})
        assert_that(collected.expected).is_equal_to({"a": 2})
        assert_that(collected.diff.kind).is_equal_to("dict")
        assert_that([step.value for step in collected.diff.entries[0].steps]).is_equal_to(["a"])

    def test_a_record_knows_where_it_was_collected(self):
        with pytest.raises(AssertionFailure) as failure, soft_assertions():
            assert_that(1).is_equal_to(2)
        location = failure.value.failures[0].location
        assert_that(location[0]).ends_with("test_soft.py")
        assert_that(location[1]).is_instance_of(int)

    def test_a_grouped_failure_keeps_its_label(self):
        with pytest.raises(AssertionFailure) as failure, soft_assertions() as sa:
            with sa.group("Body"):
                assert_that(1).is_equal_to(2)
            assert_that(3).is_equal_to(4)
        assert_that([outcome.group for outcome in failure.value.failures]).is_equal_to(["Body", None])

    def test_a_negated_failure_is_collected_as_a_record_too(self):
        with pytest.raises(AssertionFailure) as failure, soft_assertions():
            assert_that(5).not_.is_positive()
        collected = failure.value.failures[0]
        assert_that(collected.message).is_equal_to("Expected <5> to NOT satisfy: is_positive()")
        assert_that(collected.actual).is_equal_to(5)

    def test_soft_fail_is_collected_as_a_record_too(self):
        with pytest.raises(AssertionFailure) as failure, soft_assertions():
            soft_fail("manual")
        assert_that(failure.value.failures[0].message).is_equal_to("Fail: manual!")

    def test_a_failure_that_was_raised_carries_no_collection(self):
        with pytest.raises(AssertionFailure) as failure:
            assert_that(1).is_equal_to(2)
        assert_that(failure.value.failures).is_empty()

    def test_a_negation_that_held_leaves_nothing_behind(self):
        # the rollback is a slice of the collected list, which only works while the sink stays an append
        with soft_assertions():
            assert_that(-5).not_.is_positive()


class TestAnErrorOutOfTheBlockKeepsWhatWasCollected:
    """An exception from inside the block still wins, and the failures gathered before it survive.

    They used to be dropped on the floor. A soft block exists to gather failures, so a timeout three
    assertions in took all three with it, and the reader saw only the timeout. Reported by an external
    review of the shipped library.

    A note rather than a replacement or an `ExceptionGroup`: the type and the message stay exactly what
    the block raised, so `except TimeoutError` around it keeps working and the traceback still points at
    what actually stopped the test.
    """

    def test_the_exception_is_unchanged(self):
        with pytest.raises(ValueError, match="service did not answer") as failure, soft_assertions():
            assert_that(1).is_equal_to(2)
            raise ValueError("service did not answer")
        assert_that(type(failure.value)).is_equal_to(ValueError)
        assert_that(str(failure.value)).is_equal_to("service did not answer")

    def test_the_note_is_part_of_what_pytest_matches_against(self):
        """A consequence worth stating rather than discovering: `pytest.raises(match=...)` searches the
        notes as well as the message, so an anchored pattern that used to end at the message no longer
        matches. The message itself is untouched, which is what `str(exc)` and every handler sees.
        """
        with pytest.raises(ValueError, match="soft assertion failures") as failure, soft_assertions():
            assert_that(1).is_equal_to(2)
            raise ValueError("boom")
        assert_that(str(failure.value)).described_as("the message stays the message").is_equal_to("boom")

    def test_the_collected_failures_travel_with_it(self):
        with pytest.raises(ValueError) as failure, soft_assertions():
            assert_that(1).is_equal_to(2)
            assert_that("a").is_equal_to("b")
            raise ValueError("boom")
        notes = getattr(failure.value, "__notes__", [])
        assert_that(notes).is_length(1)
        assert_that(notes[0]).contains("soft assertion failures:")
        assert_that(notes[0]).contains("<1> to be equal to <2>").contains("<a> to be equal to <b>")

    def test_a_block_that_collected_nothing_adds_no_note(self):
        with pytest.raises(ValueError) as failure, soft_assertions():
            assert_that(1).is_equal_to(1)
            raise ValueError("boom")
        assert_that(getattr(failure.value, "__notes__", [])).is_empty()

    def test_the_next_block_starts_clean(self):
        with contextlib.suppress(ValueError), soft_assertions():
            assert_that(1).is_equal_to(2)
            raise ValueError("boom")
        with pytest.raises(AssertionFailure) as failure, soft_assertions():
            assert_that("x").is_equal_to("y")
        assert_that(str(failure.value)).does_not_contain("<1> to be equal to <2>")

    def test_python_310_keeps_them_reachable_without_add_note(self):
        """`add_note` arrived in 3.11 and this package supports 3.10.

        There the note cannot be printed by the interpreter's own traceback, but the failures can still
        travel on the exception, and losing them is the thing this whole branch exists to stop. The
        absence is emulated rather than skipped, so the branch is covered on every interpreter.
        """

        class WithoutAddNoteError(ValueError):
            add_note = None

        with pytest.raises(WithoutAddNoteError) as failure, soft_assertions():
            assert_that(1).is_equal_to(2)
            raise WithoutAddNoteError("boom")
        notes = getattr(failure.value, "__notes__", [])
        assert_that(notes).is_length(1)
        assert_that(notes[0]).contains("<1> to be equal to <2>")
        assert_that(str(failure.value)).described_as("the message is still the message").is_equal_to("boom")

    def test_only_the_outermost_block_annotates(self):
        # a nested block hands failures upward, so annotating on the inner exit reports them twice
        with pytest.raises(ValueError) as failure, soft_assertions():
            assert_that(1).is_equal_to(2)
            with soft_assertions():
                assert_that(3).is_equal_to(4)
            raise ValueError("boom")
        notes = getattr(failure.value, "__notes__", [])
        assert_that(notes).is_length(1)
        assert_that(notes[0]).contains("<1> to be equal to <2>").contains("<3> to be equal to <4>")

    def test_an_error_thrown_inside_the_inner_block_is_annotated_once_on_the_way_out(self):
        # both exits see it; the inner one leaves the failures alone, so the note is written where they collect
        with pytest.raises(ValueError) as failure, soft_assertions():
            assert_that(1).is_equal_to(2)
            with soft_assertions():
                assert_that(3).is_equal_to(4)
                raise ValueError("boom")
        notes = getattr(failure.value, "__notes__", [])
        assert_that(notes).is_length(1)
        assert_that(notes[0]).contains("<1> to be equal to <2>").contains("<3> to be equal to <4>")


class TestTheNoteNeverReplacesTheException:
    """Attaching the note is a diagnostic hung on somebody else's exception, so it fails open.

    It did not. `add_note` refuses when `__notes__` is already something other than a list, and that
    `TypeError` replaced the exception the user raised, leaving theirs in `__context__`: exactly
    backwards for a mechanism whose whole job is not losing information. Reported by an external review
    of the shipped code, which is where all three shapes below come from.
    """

    def test_a_tuple_of_notes_is_not_fatal(self):
        original = ValueError("original")
        original.__notes__ = ("existing",)
        with pytest.raises(ValueError, match="original") as failure, soft_assertions():
            assert_that(1).is_equal_to(2)
            raise original
        assert_that(type(failure.value)).is_equal_to(ValueError)
        assert_that(list(failure.value.__notes__)).is_length(2)
        assert_that(failure.value.__notes__[-1]).contains("<1> to be equal to <2>")

    def test_an_add_note_that_raises_is_not_fatal(self):
        class HostileError(ValueError):
            def add_note(self, note):
                raise RuntimeError("no notes here")

        with pytest.raises(HostileError, match="original") as failure, soft_assertions():
            assert_that(1).is_equal_to(2)
            raise HostileError("original")
        assert_that(getattr(failure.value, "__notes__", [])).is_length(1)

    def test_an_add_note_that_is_not_callable_is_not_fatal(self):
        class OddError(ValueError):
            add_note = "not a method"

        with pytest.raises(OddError, match="original") as failure, soft_assertions():
            assert_that(1).is_equal_to(2)
            raise OddError("original")
        assert_that(getattr(failure.value, "__notes__", [])).is_length(1)

    def test_an_add_note_that_silently_does_nothing_still_records(self):
        """The reason the call is made unbound rather than through the instance.

        An override that raises is caught by the guard around it. One that accepts the note and drops
        it is not: nothing signals the loss, and the failures would be gone with no error anywhere.
        `BaseException.add_note` steps around the override entirely.
        """

        class SwallowingError(ValueError):
            def add_note(self, note):
                return None

        with pytest.raises(SwallowingError, match="original") as failure, soft_assertions():
            assert_that(1).is_equal_to(2)
            raise SwallowingError("original")
        notes = getattr(failure.value, "__notes__", [])
        assert_that(notes).described_as("the override never got the chance to drop it").is_length(1)
        assert_that(notes[0]).contains("<1> to be equal to <2>")

    def test_an_exception_that_refuses_the_attribute_is_not_fatal(self):
        class SealedError(ValueError):
            __slots__ = ()

            def add_note(self, note):
                raise RuntimeError("no notes here")

            def __setattr__(self, name, value):
                raise AttributeError(name)

        with pytest.raises(SealedError, match="original") as failure, soft_assertions():
            assert_that(1).is_equal_to(2)
            raise SealedError("original")
        assert_that(str(failure.value)).is_equal_to("original")


class TestTheInvariantBehindAllOfThem:
    """One rule, stated once: annotating an exception never changes which exception the caller sees.

    The tests above name the shapes that broke it. This one says the rule itself, over generated
    exception types, so a shape nobody thought of is covered by the same statement.
    """

    @staticmethod
    def _hostile(kind: str) -> type[BaseException]:
        if kind == "add_note raises":
            return type("RaisesError", (ValueError,), {"add_note": lambda self, note: 1 / 0})
        if kind == "add_note is not callable":
            return type("NotCallableError", (ValueError,), {"add_note": "text"})
        if kind == "attributes are refused":
            return type(
                "SealedError",
                (ValueError,),
                {"__setattr__": lambda self, name, value: (_ for _ in ()).throw(AttributeError(name))},
            )
        return ValueError

    @pytest.mark.parametrize(
        "kind",
        ["plain", "add_note raises", "add_note is not callable", "attributes are refused"],
    )
    @pytest.mark.parametrize("notes", [None, [], ["existing"], ("existing",), "not a sequence"])
    def test_the_caller_sees_the_exception_that_was_raised(self, kind, notes):
        raised = self._hostile(kind)("original")
        if notes is not None:
            try:
                raised.__notes__ = notes
            except AttributeError:
                pytest.skip("this shape refuses attributes, which the None case already covers")

        with pytest.raises(BaseException) as failure, soft_assertions():
            assert_that(1).is_equal_to(2)
            raise raised

        assert_that(failure.value).described_as("the same object, not a replacement").is_same_as(raised)
        assert_that(str(failure.value)).is_equal_to("original")
        assert_that(failure.value.__context__).described_as("nothing was raised over it").is_none()

    def test_the_next_block_is_clean_after_a_failed_attachment(self):
        sealed = self._hostile("attributes are refused")("original")
        with contextlib.suppress(ValueError), soft_assertions():
            assert_that(1).is_equal_to(2)
            raise sealed
        with pytest.raises(AssertionFailure) as failure, soft_assertions():
            assert_that("x").is_equal_to("y")
        assert_that(str(failure.value)).does_not_contain("<1> to be equal to <2>")


class TestAFailureReachesSomebody:
    """A soft failure appended to a block nobody reads is a test that passed without asserting."""

    def test_a_negated_failure_raises_once_the_block_has_closed(self):
        with soft_assertions():
            outliving = assert_that(5)
        with pytest.raises(AssertionFailure, match="NOT satisfy"):
            outliving.not_.is_equal_to(5)

    def test_a_negated_failure_is_still_collected_inside_the_block(self):
        with pytest.raises(AssertionFailure, match="NOT satisfy"), soft_assertions():
            assert_that(5).not_.is_equal_to(5)

    def test_a_task_outliving_the_block_opens_its_own(self):
        """The inherited block has closed, so collecting into it raised at the first failure instead."""
        collected = []

        def outliving():
            try:
                with soft_assertions():
                    assert_that(1).is_equal_to(2)
                    assert_that(3).is_equal_to(4)
            except AssertionFailure as raised:
                collected.append(str(raised))

        with soft_assertions():
            inherited = contextvars.copy_context()
        # the block is closed by now, and the copy still carries it, which is what an outliving task holds
        inherited.run(outliving)
        assert_that(collected).is_length(1)
        assert_that(collected[0].count("Expected")).described_as("failures in one report").is_equal_to(2)


class TestAssertAllRunsWhatItWasGiven:
    """Its callables are the assertions, so a coroutine is a mistake and each failure has its own line."""

    def test_an_async_callable_is_refused(self):
        async def probe():
            assert_that(1).is_equal_to(2)

        with pytest.raises(TypeError, match="handed back a coroutine"):
            assert_all(probe)

    def test_each_failure_is_located_where_it_was_written(self):
        def first():
            assert_that(1).is_equal_to(2)

        def second():
            assert_that(3).is_equal_to(4)

        with pytest.raises(AssertionFailure) as caught:
            assert_all(first, second)
        lines = sorted(
            int(line.rsplit(":", 1)[1].rstrip("]")) for line in str(caught.value).splitlines() if line.endswith("]")
        )
        assert_that(lines).is_length(2)
        assert_that(lines[0]).described_as("two distinct lines").is_not_equal_to(lines[1])

    def test_an_ordinary_callable_still_runs(self):
        with pytest.raises(AssertionFailure, match="Expected"):
            assert_all(lambda: assert_that(1).is_equal_to(2))


class TestAnInertChainHandsBackNothing:
    """`.value` promises a value every assertion on it passed, and absorbed calls have asserted nothing."""

    def test_value_after_a_failed_raises_refuses(self):
        with contextlib.suppress(AssertionFailure), soft_assertions():
            chain = assert_that(lambda: None).raises(ValueError).when_called_with()
            with pytest.raises(TypeError, match=r"cannot extract \.value"):
                _ = chain.value

    def test_the_chain_itself_still_absorbs(self):
        with contextlib.suppress(AssertionFailure), soft_assertions():
            chain = assert_that(lambda: None).raises(ValueError).when_called_with()
            assert_that(chain.is_equal_to(1).is_none()).is_not_none()

    def test_not_stays_on_the_inert_chain(self):
        """Absorbed, `not_` was the absorbing lambda, and the assertion named after it an `AttributeError`."""
        with pytest.raises(AssertionFailure) as exc_info, soft_assertions():
            chain = assert_that(lambda: None).raises(ValueError).when_called_with()
            assert_that(chain.not_.is_equal_to(1).not_.is_none()).is_same_as(chain)
        assert_that(exc_info.value.failures).is_length(1)

    def test_a_verdict_asked_through_not_is_the_failure_that_made_it_inert(self):
        capture = io.StringIO()
        logger = logging.getLogger("inert_negated_verdict")
        handler = logging.StreamHandler(capture)
        logger.addHandler(handler)
        try:
            chain = assert_warn(lambda: None, logger=logger).raises(ValueError).when_called_with()
        finally:
            logger.removeHandler(handler)
        negated = chain.check().not_.is_equal_to(1)
        assert_that(negated.passed).is_false()
        assert_that(negated.message).is_equal_to(chain.check().is_equal_to(1).message).is_in(
            *capture.getvalue().splitlines()
        )
