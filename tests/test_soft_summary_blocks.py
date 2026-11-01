"""Off pytest the summary a soft block raises is the only place its diffs are read, so each is drawn as a block."""

import os

import pytest

import assertpy.assertpy as assertpy_module
from assertpy import AssertionFailure, assert_that, errors, soft_assertions
from assertpy.errors import DiffEntry, DiffResult
from assertpy.outcome import AssertionOutcome


@pytest.fixture
def off_pytest(monkeypatch):
    monkeypatch.setattr(errors, "_RENDER_DIFF_IN_MESSAGE", True)


def _raised(*asks):
    with pytest.raises(AssertionFailure) as raised, soft_assertions():
        for ask in asks:
            ask()
    return raised.value


def _caught(asks):
    """What *asks* raised, whatever it is, so a wrong exception reads as a failed assertion rather than an error."""
    try:
        asks()
    except Exception as e:  # the type is what the test asserts on
        return e
    return None


def _entry(failure, number, indent=""):
    outcome = failure.failures[number - 1]
    file, line = outcome.location
    return f"{indent}{number}. {outcome.message.splitlines()[0]}  [{os.path.basename(file)}:{line}]"


def _block(outcome, indent="   "):
    return [f"{indent}{line}" for line in str(outcome.diff).splitlines()]


def _wide(n):
    """A failure whose block runs to 19 656 characters: fifty rows of 300 characters."""
    return lambda: assert_that({f"k{i}": str(n) * 300 for i in range(50)}).is_equal_to(
        {f"k{i}": "x" * 300 for i in range(50)}
    )


@pytest.mark.usefixtures("off_pytest")
class TestEachDiffIsDrawnUnderItsEntry:
    def test_each_entry_carries_the_block_a_raised_failure_prints(self):
        failure = _raised(lambda: assert_that({2: 4}).is_equal_to({2: 3}), lambda: assert_that([1, 2]).contains(3))
        assert_that(str(failure).splitlines()).is_equal_to(
            [
                "soft assertion failures:",
                _entry(failure, 1),
                "   diff (dict):",
                "     2:",
                "       - 4",
                "       + 3",
                _entry(failure, 2),
                *_block(failure.failures[1]),
            ]
        )

    def test_a_grouped_entry_draws_its_block_at_its_groups_indent(self):
        with pytest.raises(AssertionFailure) as raised, soft_assertions() as block, block.group("billing"):
            assert_that({2: 4}).is_equal_to({2: 3})
        failure = raised.value
        assert_that(str(failure).splitlines()).is_equal_to(
            [
                "soft assertion failures:",
                "  [billing]",
                _entry(failure, 1, "    "),
                *_block(failure.failures[0], "       "),
            ]
        )

    def test_the_message_itself_keeps_the_compact_rows(self):
        failure = _raised(lambda: assert_that({2: 4}).is_equal_to({2: 3}))
        assert_that(failure.args[0]).is_equal_to(assertpy_module._format_soft_errors(list(failure.failures)))
        assert_that(failure.args[0].splitlines()[-1]).is_equal_to("   2: 4 != 3")

    def test_an_aggregate_of_ones_own_keeps_its_message(self):
        diff = DiffResult(kind="dict", entries=[DiffEntry(path="k", actual=1, expected=0)])
        mine = AssertionFailure("mine", failures=(AssertionOutcome(message="collected", diff=diff),))
        assert_that(str(mine)).is_equal_to("mine")


class TestDrawnWhenRead:
    """At each read with the switch on, from the diffs as they are then, as a single raised failure's diff is."""

    @pytest.mark.usefixtures("off_pytest")
    def test_each_read_draws_the_diffs_as_they_are_then_as_a_single_failure_does(self):
        failure = _raised(lambda: assert_that({2: 4}).is_equal_to({2: 3}))
        single = _caught(lambda: assert_that({2: 4}).is_equal_to({2: 3}))
        assert_that(str(failure)).contains("diff (dict):")
        assert_that(str(single)).contains("diff (dict):")
        failure.failures[0].diff.entries.clear()
        single.diff.entries.clear()
        assert_that(str(failure)).does_not_contain("diff (dict):")
        assert_that(str(single)).does_not_contain("diff (dict):")

    def test_nothing_is_drawn_when_raised(self, monkeypatch):
        drawn = []

        def counted(diff):
            drawn.append(diff)
            return errors._render_diff(diff)

        monkeypatch.setattr(errors, "_RENDER_DIFF_IN_MESSAGE", True)
        monkeypatch.setattr(assertpy_module, "_render_diff", counted)
        failure = _raised(lambda: assert_that({2: 4}).is_equal_to({2: 3}))
        assert_that(drawn).is_empty()
        str(failure)
        assert_that(drawn).is_length(1)

    def test_under_pytest_the_message_stays_compact_and_a_read_with_the_switch_on_draws_the_blocks(self, monkeypatch):
        failure = _raised(lambda: assert_that({2: 4}).is_equal_to({2: 3}))
        assert_that(str(failure)).is_equal_to(failure.args[0])
        monkeypatch.setattr(errors, "_RENDER_DIFF_IN_MESSAGE", True)
        assert_that(str(failure)).contains("diff (dict):")
        monkeypatch.setattr(errors, "_RENDER_DIFF_IN_MESSAGE", False)
        assert_that(str(failure)).is_equal_to(failure.args[0])


@pytest.mark.usefixtures("off_pytest")
class TestTheRoomForBlocks:
    def test_past_twenty_the_rest_keep_their_rows_and_the_last_line_names_them(self):
        failure = _raised(*[lambda n=n: assert_that({"k": n}).is_equal_to({"k": -1}) for n in range(21)])
        lines = str(failure).splitlines()
        assert_that(lines.count("   diff (dict):")).is_equal_to(20)
        assert_that(lines[-3:]).is_equal_to(
            [
                _entry(failure, 21),
                "   k: 20 != -1",
                "Not drawn as a block for lack of room: failure 21. The diff of each is on `failures`.",
            ]
        )

    def test_a_failure_without_a_diff_is_not_named_at_the_end(self):
        failure = _raised(
            *[lambda n=n: assert_that({"k": n}).is_equal_to({"k": -1}) for n in range(20)],
            lambda: assert_that(False).is_true(),
        )
        assert_that(str(failure).splitlines()[-1]).is_equal_to(_entry(failure, 21))

    def test_a_block_too_wide_for_what_is_left_costs_no_later_one_its_block(self):
        failure = _raised(_wide(1), _wide(2), _wide(3), _wide(4), lambda: assert_that([1]).contains(3))
        lines = str(failure).splitlines()
        assert_that(lines.count("   diff (dict):")).is_equal_to(3)
        assert_that(lines[-4:]).is_equal_to(
            [
                _entry(failure, 5),
                *_block(failure.failures[4]),
                "Not drawn as a block for lack of room: failure 4. The diff of each is on `failures`.",
            ]
        )

    def test_a_block_too_wide_for_what_is_left_takes_one_of_the_twenty(self, monkeypatch):
        drawn = []

        def counted(diff):
            drawn.append(diff)
            return errors._render_diff(diff)

        monkeypatch.setattr(assertpy_module, "_render_diff", counted)
        last = str(_raised(*[_wide(n) for n in range(25)])).splitlines()[-1]
        assert_that(drawn).is_length(20)
        assert_that(last).is_equal_to(
            "Not drawn as a block for lack of room: failures 4 to 25. The diff of each is on `failures`."
        )

    def test_an_empty_diff_takes_no_place_among_the_twenty(self):
        empty = [AssertionOutcome(message=f"empty {n}", diff=DiffResult(kind="dict", entries=[])) for n in range(20)]
        real = AssertionOutcome(
            message="real", diff=DiffResult(kind="dict", entries=[DiffEntry(path="k", actual=1, expected=0)])
        )
        lines = assertpy_module._format_soft_errors([*empty, real], blocks=True).splitlines()
        assert_that(lines[-5:]).is_equal_to(["21. real", "   diff (dict):", "     k:", "       - 1", "       + 0"])

    def test_a_diff_that_cannot_be_drawn_takes_one_of_the_twenty(self, monkeypatch):
        def refuses_the_first_twenty(diff):
            if diff.entries[0].actual < 20:
                raise ValueError("cannot draw")
            return errors._render_diff(diff)

        monkeypatch.setattr(assertpy_module, "_render_diff", refuses_the_first_twenty)
        failure = _raised(*[lambda n=n: assert_that({"k": n}).is_equal_to({"k": -1}) for n in range(21)])
        assert_that(str(failure).splitlines()[-1]).is_equal_to(
            "Not drawn as a block for lack of room: failure 21. The diff of each is on `failures`."
        )

    def test_a_diff_that_cannot_be_drawn_keeps_its_rows_and_says_why(self, monkeypatch):
        def refuses(diff):
            raise ValueError("cannot draw")

        monkeypatch.setattr(assertpy_module, "_render_diff", refuses)
        failure = _raised(lambda: assert_that({2: 4}).is_equal_to({2: 3}))
        assert_that(str(failure).splitlines()).is_equal_to(
            [
                "soft assertion failures:",
                _entry(failure, 1),
                "   2: 4 != 3",
                "   (no block: drawing it raised ValueError)",
            ]
        )

    def test_an_exception_that_escaped_the_block_carries_the_blocks_in_its_note(self):
        def asks():
            with soft_assertions():
                for n in range(21):
                    assert_that({"k": n}).is_equal_to({"k": -1})
                raise RuntimeError("boom")

        with pytest.raises(RuntimeError) as raised:
            asks()
        note = raised.value.__notes__[-1].splitlines()
        assert_that(note.count("   diff (dict):")).is_equal_to(20)
        assert_that(note[-1]).is_equal_to("Not drawn as a block for lack of room: failure 21.")


class TestTheSummaryIsADiagnostic:
    @staticmethod
    def _refuses(errs, **_):
        raise ValueError("cannot draw")

    def test_a_summary_that_cannot_be_drawn_leaves_the_escaping_exception_as_it_was(self, monkeypatch):
        monkeypatch.setattr(assertpy_module, "_format_soft_errors", self._refuses)

        def asks():
            with soft_assertions():
                assert_that(1).is_equal_to(2)
                raise RuntimeError("boom")

        raised = _caught(asks)
        assert_that(raised).is_instance_of(RuntimeError)
        assert_that(raised.args).is_equal_to(("boom",))
        assert_that(raised.__notes__[-1]).is_equal_to(
            "soft assertion failures: 1 collected, and drawing them raised ValueError"
        )

    @pytest.mark.parametrize("switch", [False, True])
    def test_a_summary_that_cannot_be_drawn_still_raises_the_failure(self, monkeypatch, switch):
        monkeypatch.setattr(errors, "_RENDER_DIFF_IN_MESSAGE", switch)
        monkeypatch.setattr(assertpy_module, "_format_soft_errors", self._refuses)

        def asks():
            with soft_assertions():
                assert_that(1).is_equal_to(2)

        failure = _caught(asks)
        monkeypatch.setattr(errors, "_RENDER_DIFF_IN_MESSAGE", True)
        assert_that(failure).is_instance_of(AssertionFailure)
        assert_that(failure.failures).is_length(1)
        assert_that(_caught(lambda: str(failure)) or str(failure)).is_equal_to(
            "soft assertion failures: 1 collected, and drawing them raised ValueError"
        )

    def test_under_pytest_the_blocks_are_drawn_from_the_diffs_as_they_are_at_the_first_read(self, monkeypatch):
        failure = _raised(lambda: assert_that({2: 4}).is_equal_to({2: 3}))
        failure.failures[0].diff.entries.clear()
        monkeypatch.setattr(errors, "_RENDER_DIFF_IN_MESSAGE", True)
        assert_that(str(failure)).does_not_contain("diff (dict):")


class TestOneEntryCostsItselfAlone:
    class _Unsplittable(str):
        def splitlines(self, keepends=False):
            raise ValueError("cannot split")

    @pytest.mark.parametrize("blocks", [False, True])
    def test_a_failure_that_cannot_be_drawn_costs_its_own_entry_alone(self, blocks):
        diff = DiffResult(kind="dict", entries=[DiffEntry(path="k", actual=1, expected=0)])
        good = AssertionOutcome(message="good", diff=diff)
        broken = AssertionOutcome(message=self._Unsplittable("broken"), diff=diff)
        drawn = _caught(lambda: assertpy_module._format_soft_errors([good, broken, good], blocks=blocks))
        lines = (
            repr(drawn) if drawn else assertpy_module._format_soft_errors([good, broken, good], blocks=blocks)
        ).splitlines()
        assert_that(lines).contains("1. good", "2. (this failure could not be drawn: ValueError)", "3. good")
        assert_that(lines.count("2. (this failure could not be drawn: ValueError)")).is_equal_to(1)


class TestAGroupLabelCostsItsEntryAlone:
    class _Unwritable(str):
        def __format__(self, spec):
            raise ValueError("cannot write")

    class _Incomparable:
        def __eq__(self, other):
            raise ValueError("cannot compare")

        __hash__ = object.__hash__

        def __format__(self, spec):
            return "odd"

    @staticmethod
    def _lines(outcomes, blocks):
        drawn = _caught(lambda: assertpy_module._format_soft_errors(outcomes, blocks=blocks))
        return (repr(drawn) if drawn else assertpy_module._format_soft_errors(outcomes, blocks=blocks)).splitlines()

    @pytest.mark.parametrize("blocks", [False, True])
    def test_the_entry_after_a_label_that_cannot_be_written_still_gets_its_group(self, blocks):
        outcomes = [
            AssertionOutcome(message="good", group="a"),
            AssertionOutcome(message="broken", group=self._Unwritable("b")),
            AssertionOutcome(message="good", group="b"),
        ]
        assert_that(self._lines(outcomes, blocks)).is_equal_to(
            [
                "soft assertion failures:",
                "  [a]",
                "    1. good",
                "    2. (this failure could not be drawn: ValueError)",
                "  [b]",
                "    3. good",
            ]
        )

    @pytest.mark.parametrize("blocks", [False, True])
    def test_a_label_that_cannot_be_compared_costs_the_entries_after_it_nothing(self, blocks):
        odd = self._Incomparable()
        outcomes = [
            AssertionOutcome(message="first", group=odd),
            AssertionOutcome(message="second", group=odd),
            AssertionOutcome(message="third", group="c"),
        ]
        assert_that(self._lines(outcomes, blocks)).is_equal_to(
            ["soft assertion failures:", "  [odd]", "    1. first", "    2. second", "  [c]", "    3. third"]
        )

    @pytest.mark.parametrize("blocks", [False, True])
    def test_a_label_that_cannot_be_written_costs_its_own_entry_alone(self, blocks):
        diff = DiffResult(kind="dict", entries=[DiffEntry(path="k", actual=1, expected=0)])
        outcomes = [
            AssertionOutcome(message="good", diff=diff, group="a"),
            AssertionOutcome(message="broken", diff=diff, group=self._Unwritable("b")),
            AssertionOutcome(message="good", diff=diff, group="c"),
        ]
        drawn = _caught(lambda: assertpy_module._format_soft_errors(outcomes, blocks=blocks))
        lines = (repr(drawn) if drawn else assertpy_module._format_soft_errors(outcomes, blocks=blocks)).splitlines()
        assert_that(lines).contains(
            "  [a]", "    1. good", "    2. (this failure could not be drawn: ValueError)", "  [c]", "    3. good"
        )


class TestTheBlockLetsGo:
    def test_a_block_left_holds_nothing_it_collected(self):
        with pytest.raises(AssertionFailure), soft_assertions():
            block = assertpy_module._soft_err.get()
            assert_that({2: 4}).is_equal_to({2: 3}, ignore="x")
        assert_that((block.failures, block.compared)).is_equal_to(([], {}))
