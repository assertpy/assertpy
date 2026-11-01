"""`log_passes()` reports every assertion that holds inside a block, and changes nothing else.

An assertion that passes said nothing at all before this, and still says nothing outside a block: what one asked
for is read off the stack only when a failure is composed.  Inside a block a pass is a line naming the call, the
value, the place and, against a bound, how far the value was from it.  The hard part is the verdict: returning is
not passing under a soft block, a warn chain or `check()`, and an assertion asked inside another one is not the
test's to read.
"""

import asyncio
import contextlib
import contextvars
import datetime
import decimal
import fractions
import logging
import os
import pathlib
import pickle
import re
import subprocess
import sys
import threading
import time
import types
import warnings

import pytest
from hypothesis import assume, example, given, settings
from hypothesis import strategies as st

from assertpy import (
    AssertionOutcome,
    Requirement,
    VacuousAssertionWarning,
    _satisfies,
    add_extension,
    assert_conforms,
    assert_that,
    assert_warn,
    log_passes,
    remove_extension,
    soft_assertions,
    soft_fail,
)
from assertpy import assertpy as _assertpy
from assertpy._engine._introspection import caller_stacklevel
from assertpy._hints import _SIDE as _SIDES

_FILE = os.path.basename(__file__)


def _here() -> int:
    """The line of the caller, so an expected line names it without counting by hand."""
    return sys._getframe(1).f_lineno


class _Lines:
    """A logger that wants every level and keeps what it was given."""

    def __init__(self, enabled=True):
        self.enabled = enabled
        self.records: list[tuple[int, str]] = []

    def isEnabledFor(self, level):  # noqa: N802 - the name `logging` gives it
        return self.enabled

    def log(self, level, msg):
        self.records.append((level, msg))

    @property
    def lines(self):
        return [msg for _, msg in self.records]


def _outcomes():
    kept: list[AssertionOutcome] = []
    return kept, log_passes(on_pass=kept.append)


def _says(about, written, exact):
    """A number a line wrote is *exact*, or within the twelve digits it was rounded to where it says ``about``."""
    shown = fractions.Fraction(decimal.Decimal(written))
    if about:
        assert_that(abs(shown - exact) / exact).is_less_than_or_equal_to(fractions.Fraction(5, 10**12))
    else:
        assert_that(shown).is_equal_to(exact)


class TestAPassIsOneLine:
    def test_the_default_logger_takes_it_at_info(self, caplog):
        with caplog.at_level(logging.INFO, logger="assertpy.passes"), log_passes():
            line = _here() + 1
            assert_that(1).is_equal_to(1)

        assert_that(caplog.record_tuples).is_equal_to(
            [("assertpy.passes", logging.INFO, f"[{_FILE}:{line}]: is_equal_to(1) passed for <1>")]
        )

    def test_nothing_is_said_outside_a_block(self, caplog):
        with caplog.at_level(logging.DEBUG, logger="assertpy.passes"):
            assert_that(1).is_equal_to(1)

        assert_that(caplog.records).is_empty()

    def test_a_failure_is_raised_as_ever_and_reports_nothing(self):
        lines = _Lines()
        with log_passes(lines), pytest.raises(AssertionError, match="Expected <1> to be equal to <2>"):
            assert_that(1).is_equal_to(2)

        assert_that(lines.records).is_empty()

    def test_each_link_of_a_chain_is_its_own_line_up_to_the_one_that_failed(self):
        lines = _Lines()
        with log_passes(lines), pytest.raises(AssertionError):
            assert_that("foo").is_length(3).starts_with("f").is_equal_to("bar")

        assert_that([line.split(": ", 1)[1] for line in lines.lines]).is_equal_to(
            ["is_length(3) passed for <foo>", "starts_with('f') passed for <foo>"]
        )

    def test_the_description_prefixes_the_line_as_it_prefixes_a_failure(self):
        lines = _Lines()
        with log_passes(lines):
            assert_that(200, "status").is_equal_to(200)

        assert_that(lines.lines[0]).ends_with(": [status] is_equal_to(200) passed for <200>")

    def test_the_level_and_the_logger_are_the_callers(self):
        lines = _Lines()
        with log_passes(lines, level=logging.DEBUG):
            assert_that(1).is_equal_to(1)

        assert_that(lines.records[0][0]).is_equal_to(logging.DEBUG)

    def test_keywords_read_as_a_call_reads(self):
        lines = _Lines()
        with log_passes(lines):
            assert_that(101.5).is_close_to(100, rel=0.02)

        assert_that(lines.lines[0]).contains("is_close_to(100, rel=0.02) passed for <101.5>")

    def test_a_logger_that_does_not_want_the_level_has_nothing_rendered(self):
        class Counted:
            shown = 0

            def __str__(self):
                Counted.shown += 1
                return "counted"

            def __repr__(self):
                Counted.shown += 1
                return "counted"

        value = Counted()
        with log_passes(_Lines(enabled=False)):
            assert_that(value).is_same_as(value)

        assert_that(Counted.shown).is_zero()

    def test_a_line_is_one_line_whatever_the_value_holds(self):
        lines = _Lines()
        with log_passes(lines):
            assert_that("a\nb\rc").is_length(5)

        assert_that(lines.lines[0]).does_not_contain("\n").does_not_contain("\r").contains("a\\nb\\rc")

    def test_a_lone_surrogate_is_escaped_rather_than_left_for_an_encoder_to_refuse(self):
        lines = _Lines()
        with log_passes(lines):
            assert_that("x" + chr(0xD800)).is_length(2)

        assert_that(lines.lines[0]).contains("x\\ud800").does_not_contain(chr(0xD800))

    def test_a_value_or_an_argument_that_cannot_be_rendered_still_passes(self):
        class Unrenderable:
            def __str__(self):
                raise AssertionError("from __str__")

            __repr__ = __str__

            def __eq__(self, other):
                return True

            __hash__ = object.__hash__

        lines = _Lines()
        with log_passes(lines):
            assert_that(Unrenderable()).is_equal_to(1)
            assert_that(1).is_equal_to(Unrenderable())
            assert_that({Unrenderable(): 1}).is_length(1)

        assert_that(["unreprable" in line for line in lines.lines]).is_equal_to([True, True, True])

    def test_a_long_line_keeps_its_two_ends(self):
        lines = _Lines()
        with log_passes(lines):
            assert_that("x" * 20_000).is_equal_to("x" * 20_000)

        assert_that(len(lines.lines[0])).is_less_than(4100)
        assert_that(lines.lines[0]).contains("more chars")


class TestTheGuideShowsTheLinesABlockWrites:
    def test_its_example_writes_the_lines_it_shows(self):
        guide = pathlib.Path(__file__).parent.parent.joinpath("docs", "guides", "errors.md").read_text(encoding="utf-8")
        shown = guide.split("Each line goes to the `assertpy.passes` logger at `INFO`:\n\n```\n", 1)[1].split("```")[0]
        lines = _Lines()
        latency, status = 0.42, 200
        with log_passes(lines):
            assert_that(latency).is_less_than(0.5)
            assert_that(status).is_equal_to(200)
            assert_that(98.7).is_close_to(100, 2)

        assert_that([line.split("]: ", 1)[1] for line in lines.lines]).is_equal_to(
            [line.split("]: ", 1)[1] for line in shown.splitlines()]
        )


class TestTheCallbackTakesTheRecord:
    def test_it_gets_the_value_the_requirement_and_the_place(self):
        kept, block = _outcomes()
        with block:
            line = _here() + 1
            assert_that(4.9).is_less_than(5)

        assert_that(kept).is_length(1)
        outcome = kept[0]
        assert_that(outcome.passed).is_true()
        assert_that(outcome.message).is_empty()
        assert_that(outcome.actual).is_equal_to(4.9)
        assert_that(outcome.requirement).is_equal_to(Requirement("is_less_than", {"other": 5}))
        assert_that(outcome.location).is_equal_to((__file__, line))
        assert_that(outcome.hint).is_equal_to("the value is about 0.1 below the number given")

    def test_defaults_are_bound_as_the_failure_path_binds_them(self):
        kept, block = _outcomes()
        with block:
            assert_that(101.5).is_close_to(100, rel=0.02)

        assert_that(dict(kept[0].requirement.parameters)).is_equal_to({"other": 100, "tolerance": None, "rel": 0.02})

    def test_an_exception_it_raises_comes_out_of_the_assertion_that_passed(self):
        def refuse(outcome):
            raise RuntimeError("callback")

        with log_passes(on_pass=refuse), pytest.raises(RuntimeError, match="callback"):
            assert_that(1).is_equal_to(1)

    def test_an_assertion_it_makes_itself_is_not_reported_and_does_not_recurse(self):
        kept: list[AssertionOutcome] = []

        def checks(outcome):
            assert_that(outcome.passed).is_true()
            kept.append(outcome)

        with log_passes(on_pass=checks):
            assert_that(1).is_equal_to(1)

        assert_that([outcome.requirement.operation for outcome in kept]).is_equal_to(["is_equal_to"])

    def test_an_assertion_a_logger_makes_while_logging_does_not_recurse(self):
        class Asserting(_Lines):
            def log(self, level, msg):
                assert_that(msg).contains("passed")
                super().log(level, msg)

        lines = Asserting()
        with log_passes(lines):
            assert_that(1).is_equal_to(1)

        assert_that(lines.lines).is_length(1)


class TestTheArgumentsAreChecked:
    def test_a_logger_beside_a_callback_is_refused(self):
        with pytest.raises(TypeError, match="logger arg must be None when on_pass is given"):
            log_passes(_Lines(), on_pass=print)

    def test_a_callback_must_be_callable(self):
        with pytest.raises(TypeError, match="on_pass arg must be callable"):
            log_passes(on_pass="print")  # ty: ignore[invalid-argument-type]  # the refusal is the point

    def test_a_logger_must_log(self):
        with pytest.raises(TypeError, match="logger arg must be a logger"):
            log_passes(object())  # ty: ignore[invalid-argument-type]  # the refusal is the point

    @pytest.mark.parametrize("level", [True, "INFO", 20.0])
    def test_a_level_is_an_int(self, level):
        with pytest.raises(TypeError, match="level arg must be an int logging level"):
            log_passes(level=level)


class TestOnlyAVerdictIsAPass:
    def test_a_soft_failure_is_collected_and_not_reported(self):
        lines = _Lines()
        with log_passes(lines), pytest.raises(AssertionError), soft_assertions():
            assert_that(1).is_equal_to(1)
            assert_that(1).is_equal_to(2)
            assert_that(1).not_.is_equal_to(1)
            soft_fail("by hand")

        assert_that(lines.lines).is_length(1)
        assert_that(lines.lines[0]).contains("is_equal_to(1) passed")

    def test_a_soft_failure_in_a_step_a_blocking_poll_replays_inside_an_extension_is_the_extensions(self):
        ran = []

        def first(value):
            if ran:
                soft_fail("only when replayed")
            ran.append(value)
            return True

        def polls(self):
            chain = assert_that(lambda: 1).eventually_sync(timeout=5, interval=0).satisfies(first)
            # replays `satisfies(first)` first, which now fails softly, and then passes
            chain.is_equal_to(1)
            return self

        add_extension(polls)
        try:
            kept, block = _outcomes()
            with block, pytest.raises(AssertionError, match="only when replayed"), soft_assertions():
                assert_that(0).polls()
        finally:
            remove_extension(polls)

        assert_that(kept).is_empty()

    def test_a_warned_failure_is_logged_as_a_warning_and_not_as_a_pass(self):
        lines = _Lines()
        warned: list[AssertionOutcome] = []
        with log_passes(lines):
            assert_warn(1, on_failure=warned.append).is_equal_to(2)
            assert_warn(1, on_failure=warned.append).not_.is_equal_to(1)
            assert_warn(1, on_failure=warned.append).is_equal_to(1)

        assert_that(warned).is_length(2)
        assert_that(lines.lines).is_length(1)

    def test_a_verdict_asked_for_is_answered_and_not_reported(self):
        lines = _Lines()
        with log_passes(lines):
            assert_that(assert_that(1).check().is_equal_to(1).passed).is_true()
            assert_that(assert_that(1).check().not_.is_equal_to(2).passed).is_true()

        assert_that([line.split(": ", 1)[1] for line in lines.lines]).is_equal_to(
            ["is_true() passed for <True>", "is_true() passed for <True>"]
        )

    def test_nothing_asked_inside_a_verdict_is_reported_either(self):
        kept, block = _outcomes()
        with block:
            held = assert_that(5).check().satisfies(lambda value: assert_that(value).is_positive())
            failed = assert_that(-5).check().satisfies(lambda value: value > 0)

        assert_that((held.passed, failed.passed)).is_equal_to((True, False))
        assert_that(kept).is_empty()

    def test_a_negation_that_held_is_reported_as_one(self):
        kept, block = _outcomes()
        lines = _Lines()
        with block:
            assert_that(3).not_.is_less_than(2)
        with log_passes(lines):
            assert_that(3).not_.is_less_than(2)

        assert_that(kept).is_length(1)
        assert_that(lines.lines).is_length(1)
        assert_that(kept[0].requirement).is_equal_to(Requirement("is_less_than", {"other": 2}, negated=True))
        assert_that(lines.lines[0]).ends_with(
            "not_.is_less_than(2) passed for <3>, the value is 1 above the number given"
        )

    def test_a_negation_that_failed_reports_nothing(self):
        lines = _Lines()
        with log_passes(lines), pytest.raises(AssertionError):
            assert_that(1).not_.is_less_than(2)

        assert_that(lines.records).is_empty()


class TestOneLinePerAssertionTheTestAsked:
    def test_a_delegating_assertion_reports_itself_and_not_its_delegate(self):
        kept, block = _outcomes()
        with block:
            assert_that(5).is_positive()
            assert_that({"a": 1}).contains_key("a")

        assert_that([outcome.requirement.operation for outcome in kept]).is_equal_to(["is_positive", "contains_key"])

    def test_an_assertion_inside_a_predicate_is_part_of_the_one_it_is_inside(self):
        kept, block = _outcomes()
        with block:
            assert_that([1, 2]).all_satisfy(lambda item: assert_that(item).is_positive())

        assert_that([outcome.requirement.operation for outcome in kept]).is_equal_to(["all_satisfy"])

    def test_a_pivot_reports_the_value_it_pivoted_to(self):
        lines = _Lines()
        with log_passes(lines):
            assert_that([{"x": 1}, {"x": 2}]).extracting("x").contains(2)

        assert_that(lines.lines).is_length(1)
        assert_that(lines.lines[0]).ends_with("contains(2) passed for <[1, 2]>")

    def test_a_dynamic_assertion_reports_its_name(self):
        lines = _Lines()
        with log_passes(lines):
            assert_that({"name": "x"}).has_name("x")

        assert_that(lines.lines[0]).ends_with("has_name('x') passed for <{'name': 'x'}>")

    def test_a_negated_dynamic_assertion_binds_its_operand_by_name(self):
        kept, block = _outcomes()
        with block:
            assert_that({"a": 1}).not_.has_a(2)

        assert_that(kept[0].requirement).is_equal_to(Requirement("has_a", {"other": 2}, negated=True))


class TestAnExtensionReportsItself:
    def test_it_is_one_line_under_its_own_name(self):
        def is_5(self):
            return self.is_equal_to(5)

        add_extension(is_5)
        try:
            kept, block = _outcomes()
            with block:
                assert_that(5).is_5()
        finally:
            remove_extension(is_5)

        assert_that([outcome.requirement.operation for outcome in kept]).is_equal_to(["is_5"])

    def test_one_that_failed_reports_nothing(self):
        def is_5(self):
            return self if self.val == 5 else self.error(f"{self.val} is not 5")

        add_extension(is_5)
        try:
            lines = _Lines()
            with log_passes(lines), pytest.raises(AssertionError, match="6 is not 5"):
                assert_that(6).is_5()
        finally:
            remove_extension(is_5)

        assert_that(lines.records).is_empty()

    def test_one_that_failed_softly_reports_nothing(self):
        def noted(self):
            soft_fail("noted")
            return self

        add_extension(noted)
        try:
            lines = _Lines()
            with log_passes(lines), pytest.raises(AssertionError, match="noted"), soft_assertions():
                assert_that(1).noted()
        finally:
            remove_extension(noted)

        assert_that(lines.records).is_empty()

    def test_a_callable_object_reaches_a_pivot_and_reports_there(self):
        class AllPositive:
            __name__ = "all_positive"

            def __call__(self, builder):
                return builder.all_satisfy(lambda value: value > 0)

        extension = AllPositive()
        add_extension(extension)
        try:
            kept, block = _outcomes()
            with block:
                assert_that([{"x": 1}]).extracting("x").all_positive()
        finally:
            remove_extension(extension)

        assert_that([outcome.requirement.operation for outcome in kept]).is_equal_to(["all_positive"])

    def test_one_that_took_a_built_in_name_reports_once(self):
        def is_positive(self):
            return self.is_greater_than(0)

        add_extension(is_positive, override=True)
        try:
            kept, block = _outcomes()
            with block:
                assert_that(5).is_positive()
        finally:
            remove_extension(is_positive)

        assert_that([outcome.requirement.operation for outcome in kept]).is_equal_to(["is_positive"])

    def test_the_call_it_ran_in_is_over_for_a_context_copied_inside_it(self):
        copied: list[contextvars.Context] = []

        def copies(self):
            copied.append(contextvars.copy_context())
            return self

        add_extension(copies)
        try:
            kept, block = _outcomes()
            with block:
                assert_that(1).copies()
                copied[0].run(lambda: assert_that(2).is_equal_to(2))
        finally:
            remove_extension(copies)

        assert_that([outcome.requirement.operation for outcome in kept]).is_equal_to(["copies", "is_equal_to"])


class TestTheBlockIsWhereTheBuilderWasMadeAndRun:
    def test_a_builder_made_before_the_block_reports_nothing(self):
        lines = _Lines()
        made = assert_that(1)
        with log_passes(lines):
            made.is_equal_to(1)

        assert_that(lines.records).is_empty()

    def test_a_builder_made_inside_reports_nothing_once_the_block_closed(self):
        lines = _Lines()
        with log_passes(lines):
            made = assert_that(1)
        made.is_equal_to(1)

        assert_that(lines.records).is_empty()

    def test_a_block_entered_again_reports_into_its_innermost_entry(self):
        lines = _Lines()
        block = log_passes(lines)
        with block:
            with block:
                assert_that(1).is_equal_to(1)
            assert_that(2).is_equal_to(2)

        assert_that(lines.lines).is_length(2)

    def test_a_task_outliving_its_entry_is_not_brought_back_by_a_later_one(self):
        lines = _Lines()
        block = log_passes(lines)
        made: list[object] = []

        async def scenario():
            go_on = asyncio.Event()

            async def late():
                await go_on.wait()
                made.append(assert_that("late"))
                made[0].is_equal_to("late")

            with block:
                task = asyncio.get_running_loop().create_task(late())
                await asyncio.sleep(0)
            with block:
                go_on.set()
                await task

        asyncio.run(scenario())

        assert_that(lines.records).is_empty()
        assert_that(type(made[0])).is_same_as(_assertpy._ExtendedBuilder)

    def test_a_task_started_inside_reports_into_the_block_while_it_is_open(self):
        lines = _Lines()

        async def scenario():
            async def inner():
                assert_that("inner").is_equal_to("inner")

            with log_passes(lines):
                await asyncio.get_running_loop().create_task(inner())

        asyncio.run(scenario())

        assert_that(lines.lines).is_length(1)

    def test_a_block_in_another_thread_does_not_reach_this_one(self):
        lines, mine = _Lines(), _Lines()
        opened, done = threading.Event(), threading.Event()

        def holds_a_block():
            with log_passes(lines):
                opened.set()
                done.wait(5)

        other = threading.Thread(target=holds_a_block)
        other.start()
        try:
            opened.wait(5)
            assert_that(1).is_equal_to(1)
            made = assert_that(2)
            with log_passes(mine):
                made.is_equal_to(2)
        finally:
            done.set()
            other.join(5)

        assert_that(lines.records).is_empty()
        assert_that(mine.records).is_empty()
        # nor is it of the observed class: an assertion beside another thread's block pays one read, no more
        assert_that(type(made)).is_same_as(_assertpy._ExtendedBuilder)

    def test_a_builder_reports_into_the_entry_it_was_made_in_and_into_no_later_one(self):
        first, second = _Lines(), _Lines()
        with log_passes(first):
            made = assert_that(1)
            made.is_equal_to(1)
        with log_passes(second):
            made.is_equal_to(1)

        assert_that(first.lines).is_length(1)
        assert_that(second.records).is_empty()

    def test_a_builder_made_in_an_outer_entry_reports_into_it_from_an_inner_one(self):
        outer, inner = _Lines(), _Lines()
        with log_passes(outer):
            made = assert_that(1)
            with log_passes(inner):
                made.is_equal_to(1)
                assert_that(2).is_equal_to(2)

        assert_that(outer.lines).is_length(1)
        assert_that(inner.lines).is_length(1)

    def test_a_pivot_reports_where_the_builder_it_came_from_reports(self):
        lines = _Lines()
        before = assert_that([{"x": 1}])
        with log_passes(lines):
            before.extracting("x").contains(1)
            inside = assert_that([{"x": 2}])
        with log_passes(lines):
            inside.extracting("x").contains(2)

        assert_that(lines.records).is_empty()

    def test_tasks_sharing_one_block_may_leave_it_in_any_order(self):
        lines = _Lines()
        block = log_passes(lines)

        async def scenario():
            leave_first, entered = asyncio.Event(), asyncio.Event()

            async def first():
                with block:
                    entered.set()
                    await leave_first.wait()
                    assert_that("first").is_equal_to("first")

            async def second():
                await entered.wait()
                with block:
                    leave_first.set()
                    await asyncio.sleep(0)
                    await asyncio.sleep(0)
                    assert_that("second").is_equal_to("second")

            await asyncio.gather(first(), second())

        asyncio.run(scenario())

        assert_that(lines.lines).is_length(2)
        assert_that(_assertpy._made_builder).is_same_as(_assertpy._ExtendedBuilder)

    def test_threads_sharing_one_block_each_leave_their_own_entry(self):
        lines = _Lines()
        block = log_passes(lines)
        inside, leave = threading.Barrier(2), threading.Event()

        def holds(word, first_out):
            with block:
                inside.wait(5)
                if not first_out:
                    leave.wait(5)
                assert_that(word).is_equal_to(word)
            if first_out:
                leave.set()

        workers = [threading.Thread(target=holds, args=("a", True)), threading.Thread(target=holds, args=("b", False))]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(5)

        assert_that(lines.lines).is_length(2)
        assert_that(_assertpy._made_builder).is_same_as(_assertpy._ExtendedBuilder)

    def test_a_block_closed_by_the_assertion_it_is_watching_takes_nothing_from_it(self):
        lines = _Lines()
        stack = contextlib.ExitStack()
        stack.enter_context(log_passes(lines))
        assert_that(5).satisfies(lambda value: stack.close() is None)

        assert_that(lines.records).is_empty()

    def test_a_block_closed_by_the_assertion_it_is_watching_asks_its_logger_nothing(self):
        class Refusing(_Lines):
            def isEnabledFor(self, level):  # noqa: N802 - the name `logging` gives it
                raise AssertionError("asked after the block closed")

        stack = contextlib.ExitStack()
        stack.enter_context(log_passes(Refusing()))

        assert_that(assert_that(5).satisfies(lambda value: stack.close() is None).val).is_equal_to(5)

    def test_a_block_closed_inside_a_poll_takes_nothing_the_attempt_held(self):
        lines = _Lines()
        stack = contextlib.ExitStack()
        stack.enter_context(log_passes(lines))

        def probe():
            assert_that(1).is_equal_to(1)
            return 5

        assert_that(probe).eventually_sync(timeout=5, interval=0).satisfies(lambda value: stack.close() is None)

        assert_that(lines.records).is_empty()

    def test_an_assertion_inside_one_that_reports_nothing_reports_on_its_own(self):
        kept, block = _outcomes()
        with block:
            kept_past = assert_that(5)
        with block:
            kept_past.satisfies(lambda value: assert_that(value).is_positive())

        assert_that([outcome.requirement.operation for outcome in kept]).is_equal_to(["is_positive"])

    def test_once_every_block_closed_a_builder_is_plain_again(self):
        with log_passes(_Lines()):
            pass

        assert_that(type(assert_that(1))).is_same_as(_assertpy._ExtendedBuilder)
        # what keeps an assertion outside every block free: `_builder()` makes the class itself, with no test first
        assert_that(_assertpy._made_builder).is_same_as(_assertpy._ExtendedBuilder)


class TestAPollReportsTheAttemptThatPassed:
    def test_a_blocking_chain_reports_each_step_once(self):
        polls = iter([1, 2, 3, 4, 5, 6])
        lines = _Lines()
        with log_passes(lines):
            assert_that(lambda: next(polls)).eventually_sync(timeout=5, interval=0).is_greater_than(2).is_less_than(10)

        assert_that([line.split(": ", 1)[1] for line in lines.lines]).is_equal_to(
            [
                "is_greater_than(2) passed for <3>, the value is 1 above the number given",
                "is_less_than(10) passed for <4>, the value is 6 below the number given",
            ]
        )

    def test_an_awaited_chain_reports_each_step_of_its_last_attempt(self):
        polls = iter([1, 2, 3])
        lines = _Lines()

        async def scenario():
            with log_passes(lines):
                await (
                    assert_that(lambda: next(polls)).eventually(timeout=5, interval=0).is_greater_than(0).is_equal_to(3)
                )

        asyncio.run(scenario())

        assert_that([line.split(": ", 1)[1].split(" passed")[0] for line in lines.lines]).is_equal_to(
            ["is_greater_than(0)", "is_equal_to(3)"]
        )
        assert_that(["<3>" in line for line in lines.lines]).contains_only(True)

    def test_a_line_shows_the_value_as_it_was_when_it_was_checked(self):
        def appended(self):
            self.val.append("later")
            return self

        async def scenario():
            with log_passes(lines):
                await assert_that(lambda: ["first"]).eventually(timeout=5, interval=0).contains("first").appended()

        add_extension(appended)
        try:
            lines = _Lines()
            asyncio.run(scenario())
        finally:
            remove_extension(appended)

        assert_that(lines.lines[0]).ends_with("contains('first') passed for <['first']>")

    def test_a_context_copied_in_an_attempt_that_failed_reports_on_its_own(self):
        copied: list[contextvars.Context] = []

        def copies(self):
            copied.append(contextvars.copy_context())
            return self

        add_extension(copies)
        polls = iter([1, 2, 3])
        try:
            kept, block = _outcomes()
            with block:
                assert_that(lambda: next(polls)).eventually_sync(timeout=5, interval=0).copies().is_equal_to(3)
                # the second copy was taken in the attempt that read 2 and failed
                copied[1].run(lambda: assert_that("later").is_equal_to("later"))
        finally:
            remove_extension(copies)

        assert_that([outcome.actual for outcome in kept]).is_equal_to([1, 3, "later"])

    def test_a_callback_that_raises_after_a_poll_passed_is_not_retried(self):
        calls = []

        def probe():
            calls.append(1)
            return 1

        def refuse(outcome):
            raise AssertionError("from the callback")

        with log_passes(on_pass=refuse), pytest.raises(AssertionError, match="from the callback"):
            assert_that(probe).eventually_sync(timeout=5, interval=0).is_equal_to(1)

        assert_that(calls).is_length(1)

    def test_a_poll_asks_the_logger_before_it_hands_a_held_line_on(self):
        lines = _Lines(enabled=False)
        with log_passes(lines):
            assert_that(lambda: 1).eventually_sync(timeout=5, interval=0).is_equal_to(1)

        assert_that(lines.records).is_empty()

    def test_a_callback_failing_on_a_pass_the_probe_made_is_not_retried_by_either_poll(self):
        calls = []

        def probe():
            calls.append(1)
            assert_that(1).is_equal_to(1)
            return 1

        def refuse(outcome):
            raise AssertionError("from the callback")

        async def awaited():
            await assert_that(probe).eventually(timeout=5, interval=0).is_equal_to(1)

        with log_passes(on_pass=refuse), pytest.raises(AssertionError, match="from the callback"):
            assert_that(probe).eventually_sync(timeout=5, interval=0).is_equal_to(1)
        with log_passes(on_pass=refuse), pytest.raises(AssertionError, match="from the callback"):
            asyncio.run(awaited())

        assert_that(calls).is_length(2)

    def test_a_poll_renders_nothing_for_a_logger_that_does_not_want_the_level(self):
        class Counted:
            shown = 0

            def __str__(self):
                Counted.shown += 1
                return "counted"

            __repr__ = __str__

        value = Counted()

        async def awaited():
            await assert_that(lambda: value).eventually(timeout=5, interval=0).is_same_as(value)

        with log_passes(_Lines(enabled=False)):
            assert_that(lambda: value).eventually_sync(timeout=5, interval=0).is_same_as(value)
            asyncio.run(awaited())

        assert_that(Counted.shown).is_zero()

    def test_a_pass_into_another_entry_is_decided_by_that_entry_after_the_attempt(self):
        quiet, loud = _Lines(enabled=False), _Lines()
        with log_passes(quiet):
            made_earlier = assert_that(1)
            with log_passes(loud):
                assert_that(lambda: made_earlier.is_equal_to(1).val).eventually_sync(timeout=5, interval=0).is_equal_to(
                    1
                )

        assert_that(quiet.records).is_empty()
        assert_that(loud.lines).is_length(1)

    def test_a_poll_asks_the_logger_once_before_an_attempt_and_not_inside_it(self):
        class Counting(_Lines):
            asked = 0

            def isEnabledFor(self, level):  # noqa: N802 - the name `logging` gives it
                Counting.asked += 1
                return True

        lines = Counting()
        with log_passes(lines):
            assert_that(lambda: 1).eventually_sync(timeout=5, interval=0).is_equal_to(1)

        assert_that((Counting.asked, len(lines.lines))).is_equal_to((1, 1))

    def test_a_poll_inside_an_assertion_is_part_of_its_line(self):
        kept, block = _outcomes()
        with block:
            assert_that(5).satisfies(
                lambda value: (
                    assert_that(lambda: value).eventually_sync(timeout=5, interval=0).is_equal_to(5) is not None
                )
            )

        assert_that([outcome.requirement.operation for outcome in kept]).is_equal_to(["satisfies"])

    def test_a_poll_beside_another_threads_block_reports_nothing(self):
        lines = _Lines()
        opened, done = threading.Event(), threading.Event()

        def holds_a_block():
            with log_passes(lines):
                opened.set()
                done.wait(5)

        other = threading.Thread(target=holds_a_block)
        other.start()
        try:
            opened.wait(5)
            assert_that(lambda: 1).eventually_sync(timeout=5, interval=0).is_equal_to(1)
        finally:
            done.set()
            other.join(5)

        assert_that(lines.records).is_empty()

    def test_a_logger_that_fails_asking_its_level_is_not_retried_by_either_poll(self):
        class Refusing(_Lines):
            def isEnabledFor(self, level):  # noqa: N802 - the name `logging` gives it
                raise AssertionError("from the logger")

        calls = []

        def probe():
            calls.append(1)
            return 1

        async def awaited():
            await assert_that(probe).eventually(timeout=5, interval=0).is_equal_to(1)

        with log_passes(Refusing()), pytest.raises(AssertionError, match="from the logger"):
            assert_that(probe).eventually_sync(timeout=5, interval=0).is_equal_to(1)
        with log_passes(Refusing()), pytest.raises(AssertionError, match="from the logger"):
            asyncio.run(awaited())

        # asked once before the first attempt, outside the retry, so the probe never ran
        assert_that(calls).is_empty()

    def test_a_logger_polling_while_asked_its_level_reports_nothing_and_does_not_recurse(self):
        class Polling(_Lines):
            def isEnabledFor(self, level):  # noqa: N802 - the name `logging` gives it
                assert_that(lambda: "asked").eventually_sync(timeout=5, interval=0).is_equal_to("asked")
                return True

        async def awaited():
            await assert_that(lambda: 2).eventually(timeout=5, interval=0).is_equal_to(2)

        lines = Polling()
        with log_passes(lines):
            assert_that(lambda: 1).eventually_sync(timeout=5, interval=0).is_equal_to(1)
            asyncio.run(awaited())

        assert_that([line.split(": ", 1)[1] for line in lines.lines]).is_equal_to(
            ["is_equal_to(1) passed for <1>", "is_equal_to(2) passed for <2>"]
        )

    def test_a_poll_inside_an_attempt_that_failed_reports_with_the_attempt_that_passed(self):
        sync_reads, async_reads = iter([1, 2]), iter([1, 2])

        def probe():
            assert_that(lambda: "inner").eventually_sync(timeout=5, interval=0).is_equal_to("inner")
            return next(sync_reads)

        async def async_probe():
            await assert_that(lambda: "inner").eventually(timeout=5, interval=0).is_equal_to("inner")
            return next(async_reads)

        async def awaited():
            await assert_that(async_probe).eventually(timeout=5, interval=0).is_equal_to(2)

        kept, block = _outcomes()
        with block:
            assert_that(probe).eventually_sync(timeout=5, interval=0).is_equal_to(2)
            asyncio.run(awaited())

        assert_that([outcome.actual for outcome in kept]).is_equal_to(["inner", 2, "inner", 2])

    def test_a_poll_inside_an_attempt_asks_the_logger_nothing(self):
        class Counting(_Lines):
            asked = 0

            def isEnabledFor(self, level):  # noqa: N802 - the name `logging` gives it
                Counting.asked += 1
                return True

        reads = iter([1, 2])

        def probe():
            assert_that(lambda: "inner").eventually_sync(timeout=5, interval=0).is_equal_to("inner")
            return next(reads)

        lines = Counting()
        with log_passes(lines):
            assert_that(probe).eventually_sync(timeout=5, interval=0).is_equal_to(2)

        # once before each of the two outer attempts
        assert_that((Counting.asked, len(lines.lines))).is_equal_to((2, 2))

    def test_a_callback_failing_on_a_pass_a_poll_inside_an_attempt_made_is_not_retried(self):
        calls = []

        def probe():
            calls.append(1)
            assert_that(lambda: 1).eventually_sync(timeout=1, interval=0).is_equal_to(1)
            return 1

        def refuse(outcome):
            raise AssertionError("from the callback")

        with log_passes(on_pass=refuse), pytest.raises(AssertionError, match="from the callback"):
            assert_that(probe).eventually_sync(timeout=1, interval=0).is_equal_to(1)

        assert_that(calls).is_length(1)

    def test_a_task_running_while_a_failed_attempt_waits_to_retry_reports_on_its_own(self):
        reads, started = iter([1, 2]), []

        async def later():
            assert_that("later").is_equal_to("later")

        def probe():
            read = next(reads)
            if read == 1:
                started.append(asyncio.get_running_loop().create_task(later()))
            return read

        async def awaited():
            await assert_that(probe).eventually(timeout=5, interval=0).is_equal_to(2)

        kept, block = _outcomes()
        with block:
            asyncio.run(awaited())

        assert_that([outcome.actual for outcome in kept]).is_equal_to(["later", 2])

    def test_a_context_run_while_a_failed_attempt_waits_to_retry_reports_on_its_own(self, monkeypatch):
        reads, copied = iter([1, 2]), []

        def probe():
            copied.append(contextvars.copy_context())
            return next(reads)

        def backoff(seconds):
            copied[-1].run(lambda: assert_that("later").is_equal_to("later"))

        monkeypatch.setattr(
            "assertpy.async_assertions.time", types.SimpleNamespace(monotonic=time.monotonic, sleep=backoff)
        )
        kept, block = _outcomes()
        with block:
            assert_that(probe).eventually_sync(timeout=5, interval=0).is_equal_to(2)

        assert_that([outcome.actual for outcome in kept]).is_equal_to(["later", 2])

    def test_a_pass_into_another_entry_is_rendered_before_that_entry_is_asked_and_logged_only_if_it_wants(self):
        class Counted:
            shown = 0

            def __str__(self):
                Counted.shown += 1
                return "counted"

            __repr__ = __str__

        value, outer = Counted(), _Lines(enabled=False)
        with log_passes(outer):
            made_earlier = assert_that(value)
            with log_passes(_Lines(enabled=False)):
                assert_that(lambda: made_earlier.is_same_as(value).val).eventually_sync(
                    timeout=5, interval=0
                ).is_same_as(value)

        # the exception the guide names: rendered when checked, refused by the outer logger after the poll
        assert_that(Counted.shown).is_positive()
        assert_that(outer.records).is_empty()

    def test_a_callback_failing_in_a_block_a_probe_opened_is_part_of_the_attempt_and_retried(self):
        calls = []

        def refuse_once(outcome):
            if len(calls) in (1, 3):
                raise AssertionError("from the callback")

        def probe():
            calls.append(1)
            with log_passes(on_pass=refuse_once):
                assert_that(1).is_equal_to(1)
            return 1

        async def awaited():
            await assert_that(probe).eventually(timeout=5, interval=0).is_equal_to(1)

        # the limit the guide names: a block entered while an attempt runs belongs to it
        assert_that(probe).eventually_sync(timeout=5, interval=0).is_equal_to(1)
        asyncio.run(awaited())

        assert_that(calls).is_length(4)

    def test_a_logger_failing_once_in_a_block_a_probe_opened_is_retried(self):
        asked = []

        class FailsOnce(_Lines):
            def isEnabledFor(self, level):  # noqa: N802 - the name `logging` gives it
                asked.append(level)
                if len(asked) == 1:
                    raise AssertionError("from the logger")
                return True

        calls = []

        def probe():
            calls.append(1)
            with log_passes(FailsOnce()):
                assert_that(1).is_equal_to(1)
            return 1

        assert_that(probe).eventually_sync(timeout=5, interval=0).is_equal_to(1)

        assert_that(calls).is_length(2)

    def test_a_logger_failing_once_for_a_poll_inside_a_probe_is_retried_by_either_outer_poll(self):
        asked = []

        class FailsOnce(_Lines):
            def isEnabledFor(self, level):  # noqa: N802 - the name `logging` gives it
                asked.append(level)
                if len(asked) == 1:
                    raise AssertionError("from the logger")
                return True

        calls = []

        def probe():
            calls.append(1)
            with log_passes(FailsOnce()):
                # asked before the inner poll's first attempt, which is inside the outer poll's retry
                assert_that(lambda: 1).eventually_sync(timeout=1, interval=0).is_equal_to(1)
            return 1

        async def awaited():
            await assert_that(probe).eventually(timeout=5, interval=0).is_equal_to(1)

        assert_that(probe).eventually_sync(timeout=5, interval=0).is_equal_to(1)
        asked.clear()
        asyncio.run(awaited())

        assert_that(calls).is_length(4)

    def test_an_error_a_callback_raised_is_retried_when_a_later_probe_raises_it_again(self):
        def refuse(outcome):
            raise AssertionError("from the callback")

        with log_passes(on_pass=refuse):
            with pytest.raises(AssertionError) as outside:
                assert_that(1).is_equal_to(1)
            with pytest.raises(AssertionError) as from_a_poll:
                assert_that(lambda: 1).eventually_sync(timeout=1, interval=0).is_equal_to(1)

        def raised_again_once(caught):
            reads = iter([1, 2, 1, 2])

            def probe():
                if next(reads) == 1:
                    raise caught
                return 2

            async def awaited():
                await assert_that(probe).eventually(timeout=5, interval=0).is_equal_to(2)

            assert_that(probe).eventually_sync(timeout=5, interval=0).is_equal_to(2)
            asyncio.run(awaited())

        raised_again_once(outside.value)
        raised_again_once(from_a_poll.value)

    def test_a_callback_failing_in_a_task_the_probe_awaits_is_retried_eager_or_not(self):
        calls = []

        def refuse_once(outcome):
            if len(calls) in (1, 3):
                raise AssertionError("from the callback")

        async def child():
            with log_passes(on_pass=refuse_once):
                assert_that(1).is_equal_to(1)

        async def probe():
            calls.append(1)
            await asyncio.get_running_loop().create_task(child())
            return 1

        async def awaited(factory):
            asyncio.get_running_loop().set_task_factory(factory)
            await assert_that(probe).eventually(timeout=5, interval=0).is_equal_to(1)

        asyncio.run(awaited(None))
        # an eager task starts on the probe's own stack, which changes nothing here
        asyncio.run(awaited(getattr(asyncio, "eager_task_factory", None)))

        assert_that(calls).is_length(4)

    def test_a_callback_failing_after_a_poll_passed_leaves_the_error_as_it_was_raised(self):
        calls = []

        def refuse(outcome):
            raise AssertionError("from the callback")

        def probe():
            calls.append(1)
            return 1

        with log_passes(on_pass=refuse), pytest.raises(AssertionError) as raised:
            assert_that(probe).eventually_sync(timeout=1, interval=0).is_equal_to(1)

        assert_that(calls).is_length(1)
        assert_that(raised.value.__dict__).is_empty()
        assert_that(pickle.loads(pickle.dumps(raised.value)).args).is_equal_to(("from the callback",))

    def test_an_exception_whose_class_hides_its_dict_is_retried_or_raised_as_itself(self):
        class HiddenDictError(AssertionError):
            @property
            def __dict__(self):
                raise RuntimeError("no __dict__ here")

        reads = iter([1, 2])

        def probe():
            if next(reads) == 1:
                raise HiddenDictError("not yet")
            return 2

        assert_that(probe).eventually_sync(timeout=5, interval=0).is_equal_to(2)

        raised = HiddenDictError("from the callback")
        calls = []

        def refuse(outcome):
            raise raised

        def probing():
            calls.append(1)
            return 1

        with log_passes(on_pass=refuse), pytest.raises(HiddenDictError) as caught:
            assert_that(probing).eventually_sync(timeout=1, interval=0).is_equal_to(1)

        assert_that(caught.value).is_same_as(raised)
        assert_that(calls).is_length(1)

    def test_a_callback_failing_for_a_poll_outside_every_block_is_not_retried_by_either_poll(self):
        calls = []

        def refuse(outcome):
            raise AssertionError("from the callback")

        def probe():
            calls.append(1)
            made_in_the_block.is_equal_to(1)
            return 1

        async def awaited():
            await assert_that(probe).eventually(timeout=1, interval=0).is_equal_to(1)

        with log_passes(on_pass=refuse):
            made_in_the_block = assert_that(1)
            # a fresh context is outside every block, though the block it reports into is open
            with pytest.raises(AssertionError, match="from the callback"):
                contextvars.Context().run(
                    lambda: assert_that(probe).eventually_sync(timeout=1, interval=0).is_equal_to(1)
                )
            with pytest.raises(AssertionError, match="from the callback"):
                contextvars.Context().run(asyncio.run, awaited())

        assert_that(calls).is_length(2)

    def test_an_assertion_a_probe_runs_in_a_fresh_context_is_handed_on_as_it_comes_and_retried(self):
        calls = []

        def refuse_once(outcome):
            if len(calls) in (1, 3):
                raise AssertionError("from the callback")

        def probe():
            calls.append(1)
            # the limit the guide names: the attempt holds what runs in its own context
            contextvars.Context().run(made_in_the_block.is_equal_to, 1)
            return 1

        async def awaited():
            await assert_that(probe).eventually(timeout=5, interval=0).is_equal_to(1)

        with log_passes(on_pass=refuse_once):
            made_in_the_block = assert_that(1)
            assert_that(probe).eventually_sync(timeout=5, interval=0).is_equal_to(1)
            asyncio.run(awaited())

        assert_that(calls).is_length(4)

    def test_a_poll_outside_every_block_reports_only_its_passing_attempt_into_a_block_open_elsewhere(self):
        reads = iter([1, 2])

        def probe():
            made_in_the_block.is_equal_to("seen")
            return next(reads)

        kept, block = _outcomes()
        with block:
            made_in_the_block = assert_that("seen")
            contextvars.Context().run(lambda: assert_that(probe).eventually_sync(timeout=5, interval=0).is_equal_to(2))

        assert_that([outcome.actual for outcome in kept]).is_equal_to(["seen"])

    def test_a_callback_failing_in_a_block_another_task_entered_during_the_attempt_is_retried(self):
        calls, made = [], []

        def refuse_once(outcome):
            if len(calls) == 1:
                raise AssertionError("from the callback")

        async def scenario():
            go, entered, done = asyncio.Event(), asyncio.Event(), asyncio.Event()

            async def enters_a_block():
                await go.wait()
                with log_passes(on_pass=refuse_once):
                    made.append(assert_that(1))
                    entered.set()
                    await done.wait()

            other = asyncio.create_task(enters_a_block())

            async def probe():
                calls.append(1)
                go.set()
                await entered.wait()
                made[0].is_equal_to(1)
                return 1

            try:
                await assert_that(probe).eventually(timeout=5, interval=0).is_equal_to(1)
            finally:
                done.set()
                await other

        asyncio.run(scenario())

        assert_that(calls).is_length(2)

    def test_a_block_opened_inside_a_probe_hands_on_its_passes_in_every_attempt_under_a_block_too(self):
        sync_reads, async_reads, inside = iter([1, 2]), iter([1, 2]), []

        def probe(reads):
            with log_passes(on_pass=inside.append):
                assert_that("probed").is_equal_to("probed")
            return next(reads)

        async def awaited():
            await assert_that(lambda: probe(async_reads)).eventually(timeout=5, interval=0).is_equal_to(2)

        kept, block = _outcomes()
        with block:
            assert_that(lambda: probe(sync_reads)).eventually_sync(timeout=5, interval=0).is_equal_to(2)
            asyncio.run(awaited())

        assert_that([outcome.actual for outcome in inside]).is_equal_to(["probed"] * 4)
        assert_that([outcome.actual for outcome in kept]).is_equal_to([2, 2])

    def test_a_poll_inside_a_block_a_probe_opened_hands_its_passes_to_that_block(self):
        reads, inside = iter([1, 2]), []

        def probe():
            with log_passes(on_pass=inside.append):
                assert_that(lambda: "inner").eventually_sync(timeout=5, interval=0).is_equal_to("inner")
            return next(reads)

        kept, block = _outcomes()
        with block:
            assert_that(probe).eventually_sync(timeout=5, interval=0).is_equal_to(2)

        assert_that([outcome.actual for outcome in inside]).is_equal_to(["inner", "inner"])
        assert_that([outcome.actual for outcome in kept]).is_equal_to([2])

    def test_a_block_entered_before_a_poll_in_a_context_copied_earlier_is_held_by_its_attempts(self):
        calls = []

        def refuse(outcome):
            raise AssertionError("from the callback")

        def probe():
            calls.append(1)
            made_in_the_later_block.is_equal_to(1)
            return 1

        async def awaited():
            await assert_that(probe).eventually(timeout=1, interval=0).is_equal_to(1)

        with log_passes(_Lines()):
            copied = contextvars.copy_context()
            # entered inside the first block, so only when it was entered tells it from one the probe opened
            with log_passes(on_pass=refuse):
                made_in_the_later_block = assert_that(1)
                with pytest.raises(AssertionError, match="from the callback"):
                    copied.run(lambda: assert_that(probe).eventually_sync(timeout=1, interval=0).is_equal_to(1))
                with pytest.raises(AssertionError, match="from the callback"):
                    copied.run(asyncio.run, awaited())

        assert_that(calls).is_length(2)

    def test_a_logger_failing_to_log_fails_the_assertion_and_is_not_retried_by_either_poll(self):
        class Failing(_Lines):
            def log(self, level, msg):
                raise AssertionError("from the logger")

        calls = []

        def probe():
            calls.append(1)
            return 1

        async def awaited():
            await assert_that(probe).eventually(timeout=5, interval=0).is_equal_to(1)

        with log_passes(Failing()):
            with pytest.raises(AssertionError, match="from the logger"):
                assert_that(1).is_equal_to(1)
            with pytest.raises(AssertionError, match="from the logger"):
                assert_that(probe).eventually_sync(timeout=5, interval=0).is_equal_to(1)
            with pytest.raises(AssertionError, match="from the logger"):
                asyncio.run(awaited())

        assert_that(calls).is_length(2)

    def test_a_standard_logger_whose_handler_fails_fails_the_assertion(self):
        class Failing(logging.Handler):
            def emit(self, record):
                raise RuntimeError("from the handler")

        logger, handler = logging.getLogger("tests.log_passes.failing_handler"), Failing()
        logger.addHandler(handler)
        logger.propagate = False
        logger.setLevel(logging.INFO)
        try:
            # `Handler.handle` calls `emit` unguarded: only handlers that catch their own error call `handleError`
            with log_passes(logger), pytest.raises(RuntimeError, match="from the handler"):
                assert_that(1).is_equal_to(1)
        finally:
            logger.removeHandler(handler)

    def test_a_pass_into_another_entry_shows_the_value_as_it_was_when_it_was_checked(self):
        outer, items = _Lines(), ["first"]

        def probe():
            made_earlier.contains("first")
            items.append("later")
            return 1

        with log_passes(outer):
            made_earlier = assert_that(items)
            with log_passes(_Lines()):
                assert_that(probe).eventually_sync(timeout=5, interval=0).is_equal_to(1)

        assert_that(outer.lines).is_length(1)
        assert_that(outer.lines[0]).ends_with("contains('first') passed for <['first']>")


class TestAWarningStillPointsAtTheTest:
    def test_a_vacuous_pass_warns_at_the_line_that_asked(self, monkeypatch):
        monkeypatch.setattr(_satisfies, "_VACUOUS_GUARD", True)
        with log_passes(_Lines()), warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            line = _here() + 1
            assert_that([]).all_satisfy(lambda item: None)

        vacuous = [warning for warning in caught if issubclass(warning.category, VacuousAssertionWarning)]
        assert_that([(warning.filename, warning.lineno) for warning in vacuous]).is_equal_to([(__file__, line)])

    def test_the_level_counts_out_to_the_first_frame_outside_the_package(self):
        assert_that(caller_stacklevel()).is_equal_to(1)


class TestTheMarginOfABound:
    @pytest.mark.parametrize(
        ("value", "call", "args", "margin"),
        [
            (4, "is_less_than", (5,), "the value is 1 below the number given"),
            (5, "is_less_than_or_equal_to", (5,), "the value is the number given"),
            (6, "is_greater_than", (5,), "the value is 1 above the number given"),
            (5, "is_greater_than_or_equal_to", (5,), "the value is the number given"),
            (4.9, "is_less_than", (5,), "the value is about 0.1 below the number given"),
            (0.5, "is_less_than", (0.75,), "the value is 0.25 below the number given"),
            (
                decimal.Decimal("0.50"),
                "is_less_than",
                (decimal.Decimal("0.75"),),
                "the value is 0.25 below the number given",
            ),
            (
                fractions.Fraction(1, 3),
                "is_less_than",
                (1,),
                "the value is about 0.666666666667 below the number given",
            ),
            (
                decimal.Decimal("0.5"),
                "is_less_than",
                (fractions.Fraction(3, 4),),
                "the value is 0.25 below the number given",
            ),
            (
                0.1,
                "is_greater_than_or_equal_to",
                (fractions.Fraction(1, 10),),
                "the value is about 5.55111512313E-18 above the number given",
            ),
            (7, "is_between", (5, 10), "the value is 2 above the low end and 3 below the high end"),
            (5, "is_between", (5, 10), "the value is the low end"),
            (10, "is_between", (5, 10), "the value is the high end"),
            (3, "is_not_between", (5, 10), "the value is 2 below the low end"),
            (12, "is_not_between", (5, 10), "the value is 2 above the high end"),
            (123.5, "is_close_to", (123, 1), "the two are 0.5 apart, 0.5 less than the tolerance"),
            (124, "is_close_to", (123, 1), "the two are 1 apart, which is the tolerance"),
            (123, "is_close_to", (123, 1), "the two are equal"),
            (130, "is_not_close_to", (123, 1), "the two are 7 apart, 6 more than the tolerance"),
            (
                datetime.timedelta(milliseconds=420),
                "is_less_than",
                (datetime.timedelta(milliseconds=500),),
                "the value is 0:00:00.080000 below the duration given",
            ),
            (
                datetime.date(2026, 10, 30),
                "is_greater_than",
                (datetime.date(2026, 10, 1),),
                "the value is 29 days after the date given",
            ),
            (
                datetime.date(2026, 10, 2),
                "is_greater_than",
                (datetime.date(2026, 10, 1),),
                "the value is 1 day after the date given",
            ),
            (
                datetime.datetime(2026, 1, 1, 12),
                "is_before",
                (datetime.datetime(2026, 1, 1, 13),),
                "the value is 1:00:00 before the moment given",
            ),
            (
                datetime.datetime(2026, 1, 1, 12),
                "is_before_or_equal_to",
                (datetime.datetime(2026, 1, 1, 12),),
                "the two are the same moment",
            ),
            (
                datetime.datetime(2026, 1, 1, 12),
                "is_close_to",
                (datetime.datetime(2026, 1, 1, 12, 0, 30), datetime.timedelta(minutes=1)),
                "the two are 0:00:30 apart, 0:00:30 less than the tolerance",
            ),
        ],
    )
    def test_it_is_said_beside_the_pass(self, value, call, args, margin):
        kept, block = _outcomes()
        with block:
            getattr(assert_that(value), call)(*args)

        assert_that(kept[0].hint).is_equal_to(margin)

    @pytest.mark.parametrize(
        ("value", "call", "bound", "margin"),
        [
            (datetime.timedelta(0), "is_less_than", datetime.timedelta.max, "999999999 days, 23:59:59.999999 below"),
            (datetime.timedelta.max, "is_greater_than", datetime.timedelta(0), "999999999 days, 23:59:59.999999 above"),
            (datetime.timedelta.min, "is_less_than", datetime.timedelta(0), "999999999 days, 0:00:00 below"),
        ],
    )
    def test_a_duration_distance_the_class_holds_is_measured_whichever_side_is_larger(self, value, call, bound, margin):
        kept, block = _outcomes()
        with block:
            getattr(assert_that(value), call)(bound)

        assert_that(kept[0].hint).is_equal_to(f"the value is {margin} the duration given")

    def test_a_relative_tolerance_names_the_allowance_it_came_to(self):
        kept, block = _outcomes()
        with block:
            assert_that(101.5).is_close_to(100, rel=fractions.Fraction(2, 100))

        assert_that(kept[0].hint).is_equal_to("the two are 1.5 apart, 0.5 less than the allowance of 2")

    def test_an_infinite_relative_tolerance_is_no_allowance_to_measure(self):
        kept, block = _outcomes()
        with block:
            assert_that(1).is_close_to(1000, rel=float("inf"))

        assert_that(kept[0].hint).is_none()

    def test_an_infinite_absolute_tolerance_beside_a_relative_one_is_no_allowance_to_measure(self):
        kept, block = _outcomes()
        with block:
            assert_that(101).is_close_to(100, float("inf"), rel=fractions.Fraction(1, 50))

        assert_that(kept[0].hint).is_none()

    def test_the_larger_allowance_is_the_one_measured_against(self):
        kept, block = _outcomes()
        with block:
            assert_that(101).is_close_to(100, 5, rel=fractions.Fraction(1, 100))

        assert_that(kept[0].hint).is_equal_to("the two are 1 apart, 4 less than the allowance of 5")

    def test_a_negation_measures_the_other_side(self):
        kept, block = _outcomes()
        with block:
            assert_that(7).not_.is_between(1, 5)

        assert_that(kept[0].hint).is_equal_to("the value is 2 above the high end")

    def test_a_negated_moment_is_measured_on_the_side_it_fell(self):
        kept, block = _outcomes()
        with block:
            assert_that(datetime.datetime(2026, 1, 1, 12)).not_.is_before(datetime.datetime(2026, 1, 1, 11))

        assert_that(kept[0].hint).is_equal_to("the value is 1:00:00 after the moment given")

    @pytest.mark.parametrize(
        ("value", "call", "args"),
        [
            (True, "is_greater_than", (0,)),
            (float("inf"), "is_greater_than", (1,)),
            (1, "is_less_than", (float("inf"),)),
            (2**4000, "is_greater_than", (1,)),
            (decimal.Decimal("1E+2000"), "is_greater_than", (1,)),
            (decimal.Decimal("9E+1000"), "is_greater_than", (1,)),
            (decimal.Decimal("1E-1001"), "is_greater_than", (0,)),
            # below 10**-1000, though its ratio, 1 / (2**10 * 10**997), fits the 3322 bits a ratio may take
            (decimal.Decimal("9.765625E-1001"), "is_greater_than", (0,)),
            ("b", "is_greater_than", ("a",)),
            (5, "is_positive", ()),
            (5, "is_equal_to", (5,)),
            (fractions.Fraction(2**4000, 3), "is_greater_than", (1,)),
            (decimal.Decimal("1." + "0" * 1200 + "1"), "is_greater_than", (1,)),
            # 1001 digits, though the whole number they write fits the 3322 bits a ratio may take
            (decimal.Decimal("1" + "0" * 999 + "1"), "is_greater_than", (1,)),
            (datetime.timedelta.max, "is_greater_than", (datetime.timedelta.min,)),
            (datetime.timedelta.min, "is_less_than", (datetime.timedelta.max,)),
            (float("inf"), "is_close_to", (float("inf"), 1)),
            (1, "is_close_to", (5, float("inf"))),
            (
                datetime.datetime(2026, 1, 2),
                "is_between",
                (datetime.datetime(2026, 1, 1), datetime.datetime(2026, 1, 3)),
            ),
        ],
    )
    def test_none_is_said_where_no_distance_is_measured(self, value, call, args):
        kept, block = _outcomes()
        with block:
            getattr(assert_that(value), call)(*args)

        assert_that(kept[0].hint).is_none()

    def test_none_is_said_where_the_window_reached_what_the_distance_did_not(self):
        kept, block = _outcomes()
        with block:
            # within 0.2 through the window round -0.9, while the exact distance is past it
            assert_that(-1.1).is_close_to(-0.9, 0.2)

        assert_that(kept[0].passed).is_true()
        assert_that(kept[0].hint).is_none()

    def test_a_default_context_a_caller_changed_moves_no_margin(self):
        script = (
            "import decimal\n"
            "decimal.DefaultContext.traps[decimal.Inexact] = True\n"
            "decimal.DefaultContext.rounding = decimal.ROUND_DOWN\n"
            "decimal.DefaultContext.Emax = 10\n"
            "decimal.DefaultContext.capitals = 0\n"
            "from assertpy import assert_that, log_passes\n"
            "kept = []\n"
            "with log_passes(on_pass=kept.append):\n"
            "    assert_that(0.42).is_less_than(0.5)\n"
            "    assert_that(10**40 + 1).is_greater_than(0)\n"
            "    assert_that(10**40).is_greater_than(0)\n"
            "for outcome in kept:\n"
            "    print(outcome.hint)\n"
        )
        done = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, check=False)

        assert_that(done.stderr).is_empty()
        assert_that(done.stdout.splitlines()).is_equal_to(
            [
                "the value is about 0.08 below the number given",
                "the value is about 1E+40 above the number given",
                # exact: with the default `Emax` copied it overflowed, and `Overflow` is an `Inexact`
                "the value is 1E+40 above the number given",
            ]
        )

    def test_a_subclass_of_a_number_is_not_measured(self):
        class Loud(int):
            def __sub__(self, other):
                raise AssertionError("asked")

            __rsub__ = __sub__

        kept, block = _outcomes()
        with block:
            assert_that(Loud(5)).is_greater_than(1)

        assert_that(kept[0].hint).is_none()


class TestAContractReportsItself:
    def test_a_payload_that_conforms_is_one_line_naming_the_model(self):
        pydantic = pytest.importorskip("pydantic")

        class Order(pydantic.BaseModel):
            id: int

        kept, block = _outcomes()
        lines = _Lines()
        with block:
            assert_conforms({"id": 1}, Order)
            assert_conforms([{"id": 1}], Order, exact=True, each=True)
        with log_passes(lines):
            assert_conforms({"id": 1}, Order)

        assert_that([outcome.requirement.operation for outcome in kept]).is_equal_to(["assert_conforms"] * 2)
        assert_that(dict(kept[1].requirement.parameters)).is_equal_to(
            {"model": Order, "description": "", "exact": True, "each": True}
        )
        assert_that(lines.lines[0]).contains("assert_conforms(<class ").contains(" passed for <{'id': 1}>")

    def test_one_that_does_not_reports_nothing(self):
        pydantic = pytest.importorskip("pydantic")

        class Order(pydantic.BaseModel):
            id: int

        lines = _Lines()
        with log_passes(lines), pytest.raises(AssertionError):
            assert_conforms({"id": "x"}, Order)

        assert_that(lines.records).is_empty()

    def test_one_inside_a_predicate_is_part_of_the_assertion_it_is_inside(self):
        pydantic = pytest.importorskip("pydantic")

        class Order(pydantic.BaseModel):
            id: int

        kept, block = _outcomes()
        with block:
            assert_that({"id": 1}).satisfies(lambda payload: assert_conforms(payload, Order))

        assert_that([outcome.requirement.operation for outcome in kept]).is_equal_to(["satisfies"])

    def test_an_assertion_its_validator_makes_is_part_of_it(self):
        pydantic = pytest.importorskip("pydantic")

        class Order(pydantic.BaseModel):
            id: int

            @pydantic.field_validator("id")
            @classmethod
            def positive(cls, value):
                assert_that(value).is_positive()
                return value

        kept, block = _outcomes()
        with block:
            assert_conforms({"id": 1}, Order)

        assert_that([outcome.requirement.operation for outcome in kept]).is_equal_to(["assert_conforms"])

    def test_a_logger_asking_a_contract_of_its_own_does_not_recurse(self):
        pydantic = pytest.importorskip("pydantic")

        class Order(pydantic.BaseModel):
            id: int

        class Asking(_Lines):
            def isEnabledFor(self, level):  # noqa: N802 - the name `logging` gives it
                assert_conforms({"id": 1}, Order)
                return True

        lines = Asking()
        with log_passes(lines):
            assert_conforms({"id": 2}, Order)

        assert_that(lines.lines).is_length(1)


_NUMBERS = st.one_of(
    st.integers(min_value=-(10**30), max_value=10**30),
    st.floats(allow_nan=False, allow_infinity=False),
    # inside what a margin measures: the numbers past it are `test_none_is_said_where_no_distance_is_measured`'s
    st.decimals(allow_nan=False, allow_infinity=False).filter(
        lambda number: -300 <= number.adjusted() <= 300 and len(number.as_tuple().digits) <= 100
    ),
    st.fractions(min_value=-(10**30), max_value=10**30, max_denominator=10**12),
)
_VALUES = st.one_of(
    _NUMBERS,
    st.sampled_from([float("nan"), float("inf"), -float("inf"), True]),
    st.text(max_size=5),
    st.lists(st.integers(-3, 3), max_size=4),
)
_ONE_OPERAND = _VALUES.map(lambda other: (other,))
_ASKS = st.one_of(
    st.tuples(st.sampled_from(sorted(_SIDES)), _ONE_OPERAND),
    st.tuples(st.sampled_from(["is_between", "is_not_between"]), st.tuples(_NUMBERS, _NUMBERS)),
    st.tuples(
        st.sampled_from(["is_close_to", "is_not_close_to"]),
        st.tuples(_NUMBERS, st.one_of(st.integers(0, 10), st.floats(0, 10), st.fractions(0, 10))),
    ),
    st.tuples(st.sampled_from(["is_equal_to", "is_not_equal_to", "contains", "is_length"]), _ONE_OPERAND),
    st.tuples(st.sampled_from(["is_positive", "is_negative", "is_zero", "is_empty"]), st.just(())),
)
_MODES = ("strict", "soft", "warn", "check", "negated")


def _verdict(value, name, args, mode):
    """What the assertion decided outside of any reading of it: passed, failed, or the refusal it raised."""
    try:
        if mode == "strict":
            getattr(assert_that(value), name)(*args)
        elif mode == "negated":
            getattr(assert_that(value).not_, name)(*args)
        elif mode == "soft":
            with soft_assertions():
                getattr(assert_that(value), name)(*args)
        elif mode == "warn":
            warned: list[AssertionOutcome] = []
            getattr(assert_warn(value, on_failure=warned.append), name)(*args)
            return "failed" if warned else "passed"
        else:
            return "checked" if getattr(assert_that(value).check(), name)(*args).passed else "failed"
    except AssertionError:
        return "failed"
    except (TypeError, ValueError) as refusal:
        return f"refused: {type(refusal).__name__}"
    return "passed"


class TestAPropertyOfEveryAssertion:
    @settings(deadline=None, max_examples=300)
    @given(value=_VALUES, ask=_ASKS, mode=st.sampled_from(_MODES))
    @example(value=4.9, ask=("is_less_than", (5,)), mode="soft")
    @example(value=1, ask=("is_less_than", (2,)), mode="negated")
    @example(value=float("nan"), ask=("is_close_to", (float("nan"), 1)), mode="warn")
    def test_a_block_changes_no_verdict_and_reports_exactly_the_passes(self, value, ask, mode):
        name, args = ask
        outside = _verdict(value, name, args, mode)
        kept, block = _outcomes()
        with block:
            inside = _verdict(value, name, args, mode)

        assert_that(inside).is_equal_to(outside)
        assert_that(kept).is_length(1 if outside == "passed" else 0)

    @settings(deadline=None, max_examples=500)
    @given(value=_NUMBERS, other=_NUMBERS)
    @example(value=4.9, other=5)
    @example(value=0.1, other=fractions.Fraction(1, 10))
    @example(value=decimal.Decimal("0.50"), other=decimal.Decimal("0.75"))
    @example(value=2**53 + 1, other=float(2**53))
    def test_the_margin_of_a_single_bound_is_the_exact_distance_on_the_side_the_verdict_found(self, value, other):
        exact = fractions.Fraction(value) - fractions.Fraction(other)
        name = "is_less_than_or_equal_to" if exact <= 0 else "is_greater_than"
        kept, block = _outcomes()
        with block:
            try:
                getattr(assert_that(value), name)(other)
            except TypeError:
                # a pair the ordering engine refuses, a `Decimal` beside a `float` among them, asserts nothing
                assume(False)

        hint = kept[0].hint
        if not exact:
            assert_that(hint).is_equal_to("the value is the number given")
            return
        found = re.fullmatch(r"the value is (about )?(\S+) (below|above) the number given", hint or "")
        assert_that(found).described_as(hint).is_not_none()
        assert_that(found.group(3)).is_equal_to("below" if exact < 0 else "above")
        _says(found.group(1), found.group(2), abs(exact))

    @settings(deadline=None, max_examples=500)
    @given(
        value=_NUMBERS,
        other=_NUMBERS,
        tolerance=st.one_of(st.none(), st.integers(0, 10**6), st.fractions(0, 10**6)),
        rel=st.one_of(st.none(), st.fractions(0, 10, max_denominator=10**6)),
    )
    @example(value=-1.1, other=-0.9, tolerance=fractions.Fraction(1, 5), rel=None)
    @example(value=98.7, other=100, tolerance=None, rel=fractions.Fraction(1, 50))
    @example(value=98.7, other=100, tolerance=fractions.Fraction(1, 2), rel=fractions.Fraction(1, 100))
    def test_a_closeness_line_says_the_exact_distance_and_what_is_left_of_the_allowance(
        self, value, other, tolerance, rel
    ):
        assume(tolerance is not None or rel is not None)
        distance = abs(fractions.Fraction(value) - fractions.Fraction(other))
        given = [tolerance] if tolerance is not None else []
        if rel is not None:
            given.append(rel * abs(fractions.Fraction(other)))
        allowed = max(given)
        kept, block = _outcomes()
        with block:
            try:
                passed = assert_that(value).check().is_close_to(other, tolerance, rel=rel).passed
                if passed:
                    assert_that(value).is_close_to(other, tolerance, rel=rel)
                else:
                    assert_that(value).is_not_close_to(other, tolerance, rel=rel)
            except TypeError:
                assume(False)

        hint = kept[0].hint
        if hint is None:
            # said nothing only where the window reached what the exact distance did not
            assert_that(passed and distance > allowed).is_true()
            return
        if not distance:
            assert_that(hint).is_equal_to("the two are equal")
            return
        said = re.fullmatch(
            r"the two are (about )?(\S+) apart, (?:which is|(about )?(\S+) (less|more) than) "
            r"(?:the tolerance|the allowance of (about )?(\S+))",
            hint,
        )
        assert_that(said).described_as(hint).is_not_none()
        _says(said.group(1), said.group(2), distance)
        assert_that(hint.endswith("the tolerance")).is_equal_to(rel is None)
        if rel is not None:
            _says(said.group(6), said.group(7), allowed)
        if distance == allowed:
            assert_that(said.group(4)).is_none()
            return
        _says(said.group(3), said.group(4), abs(allowed - distance))
        assert_that(said.group(5)).is_equal_to("less" if distance < allowed else "more")
