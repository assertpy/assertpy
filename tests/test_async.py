import asyncio
import contextlib
import decimal
import fractions
import gc
import inspect
import itertools
import logging
import os
import pathlib
import subprocess
import sys
import textwrap
import threading
import time
import warnings
from collections import Counter, OrderedDict, defaultdict
from dataclasses import dataclass, field
from io import StringIO

import pytest

import assertpy
import assertpy.async_assertions as aa
from assertpy import (
    AssertionFailure,
    WarningLoggingAdapter,
    assert_that,
    assert_warn,
    async_assertions,
    errors,
    soft_assertions,
    soft_fail,
)
from assertpy.async_assertions import _RETRIES, AsyncAssertionBuilder, _change_key, _PollRecorder
from assertpy.errors import _json_safe


class TestEventuallyBasic:
    def test_value_converges(self):
        counter = {"n": 0}

        def get_count():
            counter["n"] += 1
            return counter["n"]

        result = asyncio.run(assert_that(get_count).eventually(timeout=2, interval=0.05).is_equal_to(3))
        assert_that(result).is_not_none()

    def test_immediate_match(self):
        asyncio.run(assert_that(lambda: 42).eventually(timeout=1, interval=0.05).is_equal_to(42))

    def test_timeout_raises(self):
        with pytest.raises(AssertionError, match="not met after"):
            asyncio.run(assert_that(lambda: 0).eventually(timeout=0.2, interval=0.05).is_equal_to(999))

    def test_timeout_message_includes_last_failure(self):
        with pytest.raises(AssertionError, match="to be equal to"):
            asyncio.run(assert_that(lambda: 1).eventually(timeout=0.15, interval=0.05).is_equal_to(999))

    def test_non_callable_raises_type_error(self):
        with pytest.raises(TypeError, match="val must be callable"):
            assert_that(42).eventually()


class TestEventuallyWithAsyncCallable:
    def test_async_callable(self):
        counter = {"n": 0}

        async def get_count():
            counter["n"] += 1
            return counter["n"]

        asyncio.run(assert_that(get_count).eventually(timeout=2, interval=0.05).is_equal_to(3))

    def test_async_callable_timeout(self):
        async def always_zero():
            return 0

        with pytest.raises(AssertionError, match="not met after"):
            asyncio.run(assert_that(always_zero).eventually(timeout=0.15, interval=0.05).is_equal_to(1))

    def test_sync_callable_returning_awaitable(self):
        async def compute():
            return 42

        asyncio.run(assert_that(lambda: compute()).eventually(timeout=1, interval=0.05).is_equal_to(42))


def _ready():
    return 1


_DURATION_SPELLINGS = {
    "sync-timeout": lambda value: assert_that(_ready).eventually_sync(timeout=value),
    "sync-within": lambda value: assert_that(_ready).eventually_sync().within(value),
    "async-timeout": lambda value: assert_that(_ready).eventually(timeout=value),
    "async-within": lambda value: assert_that(_ready).eventually().within(value),
    "sync-interval": lambda value: assert_that(_ready).eventually_sync(interval=value),
    "sync-every": lambda value: assert_that(_ready).eventually_sync().every(value),
    "async-interval": lambda value: assert_that(_ready).eventually(interval=value),
    "async-every": lambda value: assert_that(_ready).eventually().every(value),
}


class TestPollDurations:
    """A timeout or interval is refused where it is given, never inside the loop that uses it.

    A NaN timeout compared false against every clock reading and polled forever; a string or a `Decimal`
    failed in the deadline arithmetic; an interval `time.sleep` cannot take failed in its C code, while the
    async loop slept a negative one as zero.
    """

    @pytest.mark.parametrize("spelling", sorted(_DURATION_SPELLINGS))
    @pytest.mark.parametrize(
        ("value", "refusal"),
        [
            (float("nan"), ValueError),
            (-0.1, ValueError),
            (True, TypeError),
            ("1", TypeError),
            (decimal.Decimal(1), TypeError),
        ],
        ids=["nan", "negative", "bool", "text", "decimal"],
    )
    def test_a_duration_that_is_no_number_of_seconds_is_refused(self, spelling, value, refusal):
        with pytest.raises(refusal, match=r"^given (timeout|interval) arg must be "):
            _DURATION_SPELLINGS[spelling](value)

    @pytest.mark.parametrize("spelling", ["sync-interval", "sync-every", "async-interval", "async-every"])
    @pytest.mark.parametrize("value", [float("inf"), 10**1000], ids=["infinite", "past-the-float-range"])
    def test_an_interval_the_loop_cannot_sleep_is_refused(self, spelling, value):
        with pytest.raises(ValueError, match=r"^given interval arg must be a finite, non-negative number of seconds"):
            _DURATION_SPELLINGS[spelling](value)

    @staticmethod
    def _ready_on_the_second_poll():
        polls = []

        def probe():
            polls.append(1)
            return len(polls)

        return probe, polls

    @pytest.mark.parametrize(
        "timeout",
        [float("inf"), 10**1000, fractions.Fraction(1, 2)],
        ids=["infinite", "past-the-float-range", "fraction"],
    )
    def test_a_timeout_of_any_non_negative_length_keeps_polling_until_it_holds(self, timeout):
        probe, polls = self._ready_on_the_second_poll()
        assert_that(probe).eventually_sync(timeout=timeout, interval=0).is_equal_to(2)
        assert_that(polls).is_length(2)
        probe, polls = self._ready_on_the_second_poll()
        asyncio.run(assert_that(probe).eventually().within(timeout).every(0).is_equal_to(2))
        assert_that(polls).is_length(2)

    def test_a_zero_timeout_polls_once(self):
        probe, polls = self._ready_on_the_second_poll()
        with pytest.raises(AssertionFailure):
            assert_that(probe).eventually_sync(timeout=0, interval=0).is_equal_to(2)
        assert_that(polls).is_length(1)

    @pytest.mark.parametrize("flavour", ["sync", "async"])
    def test_an_interval_longer_than_the_budget_does_not_sleep_past_the_deadline(self, flavour):
        """It slept the whole interval, so a 50 ms budget with a 30 s interval took 30 s to fail."""
        start = time.monotonic()
        with pytest.raises(AssertionFailure):
            if flavour == "sync":
                assert_that(lambda: 1).eventually_sync(timeout=0.05, interval=30).is_equal_to(2)
            else:
                asyncio.run(assert_that(lambda: 1).eventually(timeout=0.05, interval=30).is_equal_to(2))
        assert_that(time.monotonic() - start).is_less_than(5)


class TestEventuallyChaining:
    def test_within(self):
        counter = {"n": 0}

        def get_count():
            counter["n"] += 1
            return counter["n"]

        builder = assert_that(get_count).eventually()
        assert_that(builder).is_instance_of(AsyncAssertionBuilder)
        asyncio.run(builder.within(2).every(0.05).is_equal_to(3))

    def test_various_assertions(self):
        counter = {"n": 0}

        def get_value():
            counter["n"] += 1
            return counter["n"]

        asyncio.run(assert_that(get_value).eventually(timeout=2, interval=0.05).is_greater_than(3))

    def test_string_assertion(self):
        states = iter(["loading", "loading", "ready"])

        def get_status():
            return next(states, "ready")

        asyncio.run(assert_that(get_status).eventually(timeout=1, interval=0.05).is_equal_to("ready"))


class TestEventuallyPrivateAttrs:
    def test_private_attr_raises_attribute_error(self):
        builder = assert_that(lambda: 1).eventually()
        with pytest.raises(AttributeError):
            _ = builder._nonexistent


class TestEventuallyIgnoring:
    def test_ignored_exception_is_retried(self):
        calls = {"n": 0}

        def probe():
            calls["n"] += 1
            if calls["n"] < 3:
                raise ConnectionError("not ready")
            return 42

        asyncio.run(assert_that(probe).eventually(timeout=2, interval=0.05, ignoring=ConnectionError).is_equal_to(42))
        assert_that(calls["n"]).is_equal_to(3)

    def test_exception_not_ignored_propagates_immediately(self):
        calls = {"n": 0}

        def probe():
            calls["n"] += 1
            raise ConnectionError("not ready")

        with pytest.raises(ConnectionError, match="not ready"):
            asyncio.run(assert_that(probe).eventually(timeout=2, interval=0.05).is_equal_to(42))
        assert_that(calls["n"]).is_equal_to(1)

    def test_other_exception_still_propagates(self):
        def probe():
            raise KeyError("missing")

        with pytest.raises(KeyError, match="missing"):
            asyncio.run(
                assert_that(probe).eventually(timeout=1, interval=0.05, ignoring=ConnectionError).is_equal_to(42)
            )

    def test_ignoring_tuple_of_exceptions(self):
        errors = iter([ConnectionError("boot"), TimeoutError("slow")])

        def probe():
            error = next(errors, None)
            if error is not None:
                raise error
            return "ready"

        asyncio.run(
            assert_that(probe)
            .eventually(timeout=2, interval=0.05, ignoring=(ConnectionError, TimeoutError))
            .is_equal_to("ready")
        )

    def test_ignored_exception_until_timeout_reports_last_failure(self):
        def probe():
            raise ConnectionError("still booting")

        with pytest.raises(AssertionError, match=r"not met after .* ConnectionError\('still booting'\)"):
            asyncio.run(assert_that(probe).eventually(timeout=0.15, interval=0.05, ignoring=ConnectionError).is_none())

    def test_ignoring_chainable_on_builder(self):
        calls = {"n": 0}

        def probe():
            calls["n"] += 1
            if calls["n"] < 2:
                raise ConnectionError("not ready")
            return "ok"

        asyncio.run(assert_that(probe).eventually().within(2).every(0.05).ignoring(ConnectionError).is_equal_to("ok"))

    def test_mixed_exception_and_assertion_failures(self):
        states = iter([ConnectionError("boot"), "loading", "ready"])

        def probe():
            state = next(states, "ready")
            if isinstance(state, Exception):
                raise state
            return state

        asyncio.run(
            assert_that(probe).eventually(timeout=2, interval=0.05, ignoring=ConnectionError).is_equal_to("ready")
        )

    def test_async_probe_with_ignored_exception(self):
        calls = {"n": 0}

        async def probe():
            calls["n"] += 1
            if calls["n"] < 2:
                raise ConnectionError("not ready")
            return 7

        asyncio.run(assert_that(probe).eventually(timeout=2, interval=0.05, ignoring=ConnectionError).is_equal_to(7))

    def test_ignoring_rejects_non_exception_type(self):
        with pytest.raises(TypeError, match="Exception subclass"):
            assert_that(lambda: 1).eventually(ignoring=42)

    def test_ignoring_rejects_non_exception_in_tuple(self):
        with pytest.raises(TypeError, match="Exception subclass"):
            assert_that(lambda: 1).eventually(ignoring=(ValueError, "oops"))

    def test_ignoring_rejects_base_exception_only_classes(self):
        with pytest.raises(TypeError, match="Exception subclass"):
            assert_that(lambda: 1).eventually(ignoring=KeyboardInterrupt)

    def test_ignoring_method_rejects_non_exception_type(self):
        with pytest.raises(TypeError, match="Exception subclass"):
            assert_that(lambda: 1).eventually().ignoring(int)


class TestEventuallyFailureModes:
    """Polling always retries on hard failures; the final timeout failure honors the builder's mode."""

    def test_soft_collects_timeout_failure_and_continues(self):
        async def scenario():
            with soft_assertions():
                await assert_that(lambda: 1).eventually(timeout=0.15, interval=0.05).is_equal_to(2)
                assert_that("after-eventually-marker").is_equal_to("other")

        with pytest.raises(AssertionError) as exc_info:
            asyncio.run(scenario())
        text = str(exc_info.value)
        assert_that(text).contains("soft assertion failures")
        assert_that(text).contains("not met after")
        assert_that(text).contains("after-eventually-marker")

    def test_soft_passing_eventually_collects_nothing(self):
        async def scenario():
            with soft_assertions():
                await assert_that(lambda: 42).eventually(timeout=1, interval=0.05).is_equal_to(42)

        asyncio.run(scenario())

    def test_soft_timeout_message_keeps_single_description_prefix(self):
        async def scenario():
            with soft_assertions():
                await (
                    assert_that(lambda: 1)
                    .described_as("probe-label")
                    .eventually(timeout=0.15, interval=0.05)
                    .is_equal_to(2)
                )

        with pytest.raises(AssertionError) as exc_info:
            asyncio.run(scenario())
        assert_that(str(exc_info.value).count("[probe-label]")).is_equal_to(1)

    def test_warn_logs_timeout_failure_without_raising(self):
        capture = StringIO()
        logger = logging.getLogger("capture-eventually-warn")
        logger.addHandler(logging.StreamHandler(capture))
        adapted = WarningLoggingAdapter(logger, None)

        async def scenario():
            await assert_warn(lambda: 1, logger=adapted).eventually(timeout=0.15, interval=0.05).is_equal_to(2)

        asyncio.run(scenario())
        assert_that(capture.getvalue()).contains("not met after").contains("to be equal to <2>")


class TestPollRecorder:
    """Unit coverage of collapsing and first+last retention, deterministic via direct record() calls."""

    def test_identical_polls_collapse_into_repeats(self):
        recorder = _PollRecorder()
        for _ in range(4):
            recorder.record(elapsed=0.1, outcome="fail", value=1, detail="same")
        trace = recorder.build(elapsed=1.0)
        assert_that(trace.samples).is_length(1)
        assert_that(trace.samples[0].repeats).is_equal_to(4)
        assert_that(trace.total_polls).is_equal_to(4)

    def test_collapse_applies_inside_the_tail_window(self):
        recorder = _PollRecorder(head=1, tail=3)
        recorder.record(elapsed=0.0, outcome="fail", value=0, detail="d0")
        recorder.record(elapsed=0.1, outcome="fail", value=1, detail="d1")
        recorder.record(elapsed=0.2, outcome="fail", value=1, detail="d1")
        trace = recorder.build(elapsed=1.0)
        assert_that(trace.samples).is_length(2)
        assert_that(trace.samples[1].repeats).is_equal_to(2)
        assert_that(trace.samples[1].elapsed).is_equal_to(0.1)

    def test_retention_keeps_first_and_last_and_counts_dropped(self):
        recorder = _PollRecorder(head=2, tail=3)
        for index in range(10):
            recorder.record(elapsed=float(index), outcome="fail", value=index, detail=f"d{index}")
        trace = recorder.build(elapsed=10.0)
        assert_that([sample.value for sample in trace.samples]).is_equal_to([0, 1, 7, 8, 9])
        assert_that(trace.dropped).is_equal_to(5)
        assert_that(trace.total_polls).is_equal_to(10)

    def test_error_and_fail_outcomes_do_not_collapse_together(self):
        recorder = _PollRecorder()
        recorder.record(elapsed=0.0, outcome="error", value=None, detail="ConnectionError('x')")
        recorder.record(elapsed=0.1, outcome="fail", value=None, detail="ConnectionError('x')")
        assert_that(recorder.build(elapsed=1.0).samples).is_length(2)


class TestSummaryUnderWindowOverflow:
    """The summary reads a bounded window, so a long poll drops middle samples before classifying."""

    def _summary_of(self, values):
        recorder = _PollRecorder()
        for index, value in enumerate(values):
            recorder.record(elapsed=index * 0.1, outcome="fail", value=value, detail=f"got {value}")
        trace = recorder.build(elapsed=len(values) * 0.1)
        assert_that(trace.dropped).is_greater_than(0)
        return trace.summary

    def test_a_long_monotonic_walk_is_not_mistaken_for_a_cycle(self):
        assert_that(self._summary_of([f"step{i}" for i in range(40)])).does_not_contain("cycles")

    def test_a_long_monotonic_walk_with_plateaus_is_not_mistaken_for_a_cycle(self):
        assert_that(self._summary_of([f"step{i // 4}" for i in range(120)])).does_not_contain("cycles")

    def test_the_change_count_is_over_the_run_not_over_the_window(self):
        """The one sentence a reader acts on, and it was counting the wrong polls.

        A probe returning a new value every poll for 1337 polls was summarised as "value changed 24
        times", because the window keeps 25 samples and the count came from those.  Steady drift is what
        that reads as; a value that never settled at all is what it was.
        """
        recorder = _PollRecorder()
        for index in range(60):
            recorder.record(elapsed=index * 0.1, outcome="fail", value=f"v{index}", detail=f"got v{index}")
        trace = recorder.build(elapsed=6.0)
        assert_that(trace.dropped).described_as("the guard: without a drop this proves nothing").is_positive()
        assert_that(trace.summary).contains("value changed 59 times")

    def test_a_change_the_snapshot_cuts_away_is_still_a_change(self):
        """The sample kept per poll is a diagnostic snapshot, and it is cut.

        Containers lose everything past their hundredth item, so a queue that only moved past that point
        compared equal to itself and the run read as `value unchanged` while the value changed on every
        poll.  Measured on a 200-item list whose 151st entry moves: 29 polls, 28 changes, and `unchanged`
        before the fix.
        """
        step = [0]

        def probing():
            step[0] += 1
            rows = list(range(200))
            rows[150] = f"changed on poll {step[0]}"
            return rows

        with pytest.raises(AssertionFailure) as failure:
            assert_that(probing).eventually_sync(timeout=0.15, interval=0.005).is_equal_to("never")
        assert_that(failure.value.trace.summary).does_not_contain("unchanged")
        assert_that(failure.value.trace.summary).contains("value changed")

    def test_a_value_that_returns_to_itself_is_not_called_unchanged(self):
        recorder = _PollRecorder()
        for index in range(60):
            recorder.record(elapsed=index * 0.1, outcome="fail", value=index % 2, detail=f"got {index % 2}")
        trace = recorder.build(elapsed=6.0)
        assert_that(trace.summary).does_not_contain("unchanged")

    def test_the_polls_kept_are_counted_as_polls(self):
        """A retained sample can stand for many polls, so counting samples is not counting polls.

        The recorder collapses identical consecutive polls into one record with a repeat count, and the
        cycle sentence names polls.  Over a probe alternating every other poll, "in the 25 polls kept"
        described fifty of them.
        """
        recorder = _PollRecorder()
        for index in range(120):
            value = "up" if (index // 2) % 2 else "down"
            recorder.record(elapsed=index * 0.1, outcome="fail", value=value, detail=f"got {value}")
        trace = recorder.build(elapsed=12.0)
        assert_that(trace.dropped).described_as("the guard: without a drop this proves nothing").is_positive()
        kept_polls = sum(sample.repeats for sample in trace.samples)
        assert_that(kept_polls).described_as("samples stand for more polls than there are samples").is_greater_than(
            len(trace.samples)
        )
        assert_that(trace.summary).is_equal_to(f"value cycles between 2 states in the {kept_polls} polls kept")

    def test_values_that_differ_past_the_snapshot_are_not_a_cycle(self):
        """Recurrence was read off the sample, and the sample is cut.

        Five hundred-item lists whose first entry alternates and whose last is unique to each poll are
        five different values.  Compared as snapshots they looked like two states repeating, and the
        summary's cycle line is the one that tells a reader waiting longer will not help.
        """
        recorder = _PollRecorder()
        for index in range(5):
            value = ["up" if index % 2 else "down", *range(99), f"unique {index}"]
            recorder.record(
                elapsed=index * 0.1,
                outcome="fail",
                value=_json_safe(value),
                detail="Expected <...> to be equal to <ready>, but was not.",
                raw=value,
            )
        summary = recorder.build(elapsed=0.5).summary
        assert_that(summary).does_not_contain("cycles")
        assert_that(summary).contains("value changed 4 times")

    def test_polls_that_differ_only_past_the_snapshot_are_not_one_poll(self):
        # identical has to mean identical: two values differing past the cut were folded into one record
        recorder = _PollRecorder()
        for index in range(3):
            value = [*range(150), f"unique {index}"]
            recorder.record(
                elapsed=index * 0.1,
                outcome="fail",
                value=_json_safe(value),
                detail="Expected <...> to be equal to <ready>, but was not.",
                raw=value,
            )
        assert_that(recorder.build(elapsed=0.3).samples).is_length(3)

    def test_a_cycle_is_still_detected_after_samples_are_dropped(self):
        # read off the window: once anything was dropped the sentence must say which polls it is about
        values = ["up" if i % 2 else "down" for i in range(40)]
        assert_that(self._summary_of(values)).is_equal_to("value cycles between 2 states in the 25 polls kept")


class TestTraceSummary:
    """Driven through the recorder rather than through hand-built samples.

    The summary states facts about the run and reads shape off the samples that survived the window, so a
    test that hands it a sample list decides both halves itself.  One of them was wrong that way: repeats
    collapse identical polls, so a count of retained samples is not a count of polls, and only a recorder
    that actually collapsed something shows the difference.
    """

    @staticmethod
    def _summary(events, elapsed=5.0, recorder=None):
        """Feed polls to a recorder and return the summary it builds.

        An error poll carries the exception itself, not a string that looks like one: the type in the
        summary is taken from the exception now, and a test that hands over `"ConnectionError('boot')"`
        proves nothing about where that name came from.
        """
        recorder = recorder or _PollRecorder()
        for index, (outcome, value, exc) in enumerate(events):
            recorder.record(
                elapsed=float(index),
                outcome=outcome,
                value=value,
                detail=repr(exc) if outcome == "error" else f"got {value}",
                raw=value,
                error_type=type(exc) if outcome == "error" else None,
            )
        return recorder.build(elapsed=elapsed).summary

    @staticmethod
    def _error(exc=None):
        return ("error", None, exc or ConnectionError("boot"))

    @staticmethod
    def _fail(value):
        return ("fail", value, None)

    def test_all_errors_single_type(self):
        assert_that(self._summary([self._error()] * 7)).is_equal_to("probe raised ConnectionError on all 7 polls")

    def test_all_errors_mixed_types(self):
        events = [self._error(), self._error(TimeoutError("slow")), self._error(), self._error()]
        assert_that(self._summary(events)).is_equal_to("probe raised exceptions on all 4 polls")

    def test_two_exception_classes_that_print_alike_are_still_two_types(self):
        """The type comes from the exception, not from the text its `__repr__` produced.

        Parsing the rendering called two classes one type whenever their reprs agreed, and one class
        several whenever its repr varied, which is the caller's code deciding what our summary claims.
        """

        class FirstError(RuntimeError):
            def __repr__(self):
                return "same text"

        class SecondError(RuntimeError):
            def __repr__(self):
                return "same text"

        events = [("error", None, FirstError()), ("error", None, SecondError())]
        assert_that(self._summary(events)).is_equal_to("probe raised exceptions on all 2 polls")

    def test_one_class_printing_differently_is_still_one_type(self):
        class VaryingError(RuntimeError):
            def __repr__(self):
                return f"varies {id(self)}"

        events = [("error", None, VaryingError()) for _ in range(3)]
        assert_that(self._summary(events)).is_equal_to("probe raised VaryingError on all 3 polls")

    def test_a_type_only_in_the_dropped_middle_is_still_counted(self):
        """The universal half of that sentence, over a run whose middle is gone.

        Reading the type off the retained samples claimed `ConnectionError on all 60 polls` for a run
        that also raised a `ValueError`, because the one poll that did fell out of the window.
        """
        events = [self._error(ConnectionError(f"h{i}")) for i in range(5)]
        events.append(self._error(ValueError("only in the middle")))
        events += [self._error(ConnectionError(f"t{i}")) for i in range(54)]
        recorder = _PollRecorder()
        summary = self._summary(events, recorder=recorder)
        assert_that(recorder.dropped).described_as("the guard: without a drop this proves nothing").is_positive()
        assert_that(summary).is_equal_to("probe raised exceptions on all 60 polls")

    def test_many_distinct_messages_of_one_type_still_name_that_type(self):
        # the sentence needs "one type" or "several", and a set of what it saw would grow with the run
        events = [self._error(ConnectionError(f"attempt {index}")) for index in range(200)]
        recorder = _PollRecorder()
        assert_that(self._summary(events, recorder=recorder)).is_equal_to(
            "probe raised ConnectionError on all 200 polls"
        )
        assert_that(recorder.mixed_error_types).is_false()

    def test_recovered_then_stable(self):
        events = [self._error()] * 3 + [self._fail({"s": 1})] * 2
        assert_that(self._summary(events)).is_equal_to(
            "probe recovered after 3 raising polls; value then never changed"
        )

    def test_recovered_then_changing(self):
        events = [self._error(), self._fail({"s": 1}), self._fail({"s": 2})]
        assert_that(self._summary(events)).is_equal_to(
            "probe recovered after 1 raising poll; value then changed 1 time"
        )

    def test_a_probe_that_ended_raising_is_not_called_recovered(self):
        # "recovered" is about order, not totals: raise, return, raise again ended raising whatever the totals say
        events = [self._fail("A"), self._error(), self._fail("A"), self._error()]
        assert_that(self._summary(events)).is_equal_to("probe raised on 2 of 4 polls; value then never changed")

    def test_the_recovery_line_counts_only_what_followed_the_last_error(self):
        # "value *then* changed" is about after the recovery, and the run-wide total counted movement before it
        events = [self._fail("A"), self._fail("B"), self._error(), self._fail("C")]
        assert_that(self._summary(events)).is_equal_to(
            "probe recovered after 1 raising poll; value then changed 1 time"
        )

    def test_a_run_that_mostly_raised_still_says_it_raised(self):
        """One unrenderable value must not swallow the account of the polls that raised.

        The sentence about comparison used to come first and use the whole poll count, so five raising
        polls beside one hostile value read as `value could not be compared across 6 polls`, describing
        values that existed on one of them.
        """

        class HostileValue:
            def __repr__(self):
                raise ValueError("no repr")

        recorder = _PollRecorder()
        for index in range(5):
            recorder.record(
                elapsed=index * 0.1,
                outcome="error",
                value=None,
                detail="ConnectionError('x')",
                error_type=ConnectionError,
            )
        recorder.record(elapsed=0.5, outcome="fail", value=None, detail="got it", raw=HostileValue())
        summary = recorder.build(elapsed=1.0).summary
        assert_that(summary).contains("probe recovered after 5 raising polls")
        assert_that(summary).contains("value could not be compared")

    def test_a_value_that_moved_across_a_raising_poll_is_not_called_unchanged(self):
        events = [self._fail("A"), self._error(), self._fail("B")]
        assert_that(self._summary(events)).contains("value then changed 1 time")

    def test_value_never_changed(self):
        assert_that(self._summary([self._fail(1)] * 9)).is_equal_to("value unchanged across 9 polls")

    def test_value_changed_reports_last_change(self):
        assert_that(self._summary([self._fail(1), self._fail(2), self._fail(3)], elapsed=5.0)).is_equal_to(
            "value changed 2 times; last change 3.0s before the deadline"
        )

    def test_a_repeating_value_is_reported_as_a_cycle(self):
        # "changed 4 times" reads like slow progress; the probe is really stuck alternating
        events = [self._fail("up" if index % 2 else "down") for index in range(5)]
        assert_that(self._summary(events)).is_equal_to("value cycles between 2 states across 5 polls")

    def test_returning_to_an_earlier_value_once_is_a_cycle(self):
        events = [self._fail(1), self._fail(2), self._fail(3), self._fail(1)]
        assert_that(self._summary(events)).is_equal_to("value cycles between 3 states across 4 polls")

    def test_steady_progress_is_not_reported_as_a_cycle(self):
        # the guard that matters: a value walking through new states must keep the last-change wording
        events = [self._fail(index) for index in range(4)]
        assert_that(self._summary(events, elapsed=5.0)).is_equal_to(
            "value changed 3 times; last change 2.0s before the deadline"
        )

    def test_dropped_fail_samples_not_reported_as_all_raised(self):
        # "all polls" is decided by the counts, not by what the window kept
        events = [self._fail(index) for index in range(4)] + [
            self._error(f"ConnectionError('e{i}')") for i in range(26)
        ]
        summary = self._summary(events)
        assert_that(summary).does_not_contain("on all")
        assert_that(summary).contains("raised on 26 of 30 polls")


class _OrderedChild(OrderedDict):
    """An ordered mapping by inheritance: the comparison comes with the class."""


class _LooksLikeAList:
    """A value whose repr is this rendering's own punctuation, which it must not be read as."""

    def __repr__(self):
        return "[1,2]"


class _Prints:
    """A leaf that prints exactly what it is told to, for building renderings that could run together."""

    def __init__(self, text):
        self.text = text

    def __repr__(self):
        return self.text


class TestACollectedTimeoutKeepsItsStructuredData:
    """A collected timeout is the same failure as a raised one, minus the raising.

    The values and the diff used to reach the reader only by being rendered inside the text the message
    quotes, which happens off pytest and nowhere else: under pytest the collected timeout carried no
    structured data at all, and once that rendering stopped duplicating the diff it carried none anywhere.
    """

    @staticmethod
    def _collected(expected={"n": -1}, probe=None):  # noqa: B006  # read, never mutated
        # the value is fixed and the poll count is not: pinning it fails on a loaded CI rather than on a defect
        with pytest.raises(AssertionFailure) as failure, soft_assertions():
            assert_that(probe or (lambda: {"n": 5})).eventually_sync(timeout=0.05, interval=0.01).is_equal_to(expected)
        return failure.value

    def test_the_difference_travels_with_the_collected_failure(self):
        outcome = self._collected().failures[0]
        assert_that(outcome.diff).is_not_none()
        assert_that(str(self._collected())).contains("n: 5 != -1")

    def test_the_trace_still_travels_too(self):
        assert_that(str(self._collected())).contains("value unchanged")

    def test_an_assertion_that_named_nothing_adds_nothing(self):
        # `is_not_empty()` names neither side, and `error()` decides that from which arguments arrive
        with pytest.raises(AssertionFailure) as failure, soft_assertions():
            assert_that(list).eventually_sync(timeout=0.05, interval=0.01).is_not_empty()
        outcome = failure.value.failures[0]
        assert_that(outcome.actual_provided).is_false()
        assert_that(outcome.has_expected).is_false()

    def test_a_failure_built_by_hand_falls_back_to_its_values(self):
        # these build failures directly, so the values themselves are all there is to go on, as the plugin does
        built = AssertionFailure("no record here", actual={"a": 1}, expected={"a": 2})
        assert_that(aa._structured_of(built)).is_equal_to({"actual": {"a": 1}, "expected": {"a": 2}})
        assert_that(aa._structured_of(AssertionFailure("nothing named"))).is_empty()

    def test_a_probe_whose_value_cannot_be_rendered_claims_nothing_about_movement(self):
        """The key is built from somebody else's object, and reading it runs their code.

        A value that cannot be rendered at all leaves nothing to compare, and every such value used to
        come back as the same placeholder: a probe returning a fresh unequal object every poll read as
        `value unchanged`.  Now the run says what it knows.
        """

        class HostileValue:
            def __repr__(self):
                raise RuntimeError("repr is not available")

        with pytest.raises(AssertionFailure) as failure:
            assert_that(HostileValue).eventually_sync(timeout=0.05, interval=0.01).is_equal_to("never")
        assert_that(failure.value.trace.total_polls).is_positive()
        assert_that(failure.value.trace.summary).is_equal_to(
            f"value could not be compared across {failure.value.trace.total_polls} polls"
        )

    @pytest.mark.parametrize(
        ("left", "right", "equal"),
        [
            pytest.param((1,), [1], False, id="a-tuple-is-not-a-list"),
            pytest.param({1: "x"}, {"1": "x"}, False, id="an-int-key-is-not-a-string-key"),
            pytest.param({1: "a", "b": 2}, {"b": 2, 1: "a"}, True, id="mixed-keys-in-another-order"),
            pytest.param({"a": {1, 2}}, {"a": {2, 1}}, True, id="a-nested-set-in-another-order"),
            pytest.param("x", type("StrSubclass", (str,), {})("x"), True, id="a-str-subclass"),
            pytest.param(({"a": 1, "b": 2},), ({"b": 2, "a": 1},), True, id="a-dict-inside-a-tuple"),
            # opposite orders on purpose: 0 and 8 share a bucket, so the equal sets really do iterate differently
            pytest.param({*[0, 8]}, {*[8, 0]}, True, id="a-set-whose-members-collide"),
            pytest.param(_LooksLikeAList(), [1, 2], False, id="a-leaf-that-prints-like-a-list"),
            pytest.param(["a,b"], ["a", "b"], False, id="a-string-holding-the-separator"),
            pytest.param([_Prints("a"), _Prints("bc")], [_Prints("avbc")], False, id="parts-that-would-run-together"),
            # the one mapping whose own `==` reads order, so sorting it hid a real transition
            pytest.param(
                OrderedDict([("a", 1), ("b", 2)]), OrderedDict([("b", 2), ("a", 1)]), False, id="an-ordered-dict"
            ),
            pytest.param(
                _OrderedChild([("a", 1), ("b", 2)]),
                _OrderedChild([("b", 2), ("a", 1)]),
                False,
                id="a-subclass-of-an-ordered-dict",
            ),
            pytest.param(
                defaultdict(int, {"a": 1, "b": 2}), defaultdict(int, {"b": 2, "a": 1}), True, id="a-defaultdict"
            ),
            pytest.param(Counter("ab"), Counter("ba"), True, id="a-counter"),
        ],
    )
    def test_the_change_key_follows_equality_not_rendering(self, left, right, equal):
        """What the key has to agree with is `==`, as far as a rendering can.

        JSON was the first attempt and erased the two unequal pairs here: `(1,)` and `[1]` both render as
        `[1]`, and a mapping's keys all become strings. Plain `repr` is the other direction, and calls two
        equal dicts different because their insertion order is.
        """
        assert_that(_change_key(left) == _change_key(right)).described_as(f"{left!r} vs {right!r}").is_equal_to(equal)

    def test_a_hard_timeout_carries_which_side_was_named(self):
        """A raised timeout is the same failure as a collected one, so it needs the same record.

        Without it the report falls back to reading "was this named" off a test against `None`, which is
        wrong in both directions: `is_equal_to(None)` lost its expected value, a probe returning `None`
        lost its actual one, and an assertion naming neither gained a block of values.
        """
        with pytest.raises(AssertionFailure) as failure:
            assert_that(lambda: 5).eventually_sync(timeout=0.05, interval=0.01).is_equal_to(None)
        assert_that(failure.value._outcome.has_expected).is_true()

        with pytest.raises(AssertionFailure) as failure:
            assert_that(lambda: None).eventually_sync(timeout=0.05, interval=0.01).is_equal_to("something")
        assert_that(failure.value._outcome.actual_provided).is_true()

        with pytest.raises(AssertionFailure) as failure:
            assert_that(list).eventually_sync(timeout=0.05, interval=0.01).is_not_empty()
        assert_that(failure.value._outcome.actual_provided).is_false()
        assert_that(failure.value._outcome.has_expected).is_false()

    def test_two_values_that_print_alike_are_one_value_to_this_key(self):
        """The recorded boundary, not an accident: a rendering cannot reproduce `==`.

        A dataclass that hides a field from its own repr has two unequal instances that print the same,
        and this key calls them one value.  The alternative, refusing to compare anything that is not a
        scalar or a builtin container, would silence the trend line for every probe that returns an
        object of the caller's own, which is most of them.
        """

        @dataclass(frozen=True)
        class State:
            visible: int = 0
            hidden: int = field(default=0, repr=False)

        assert_that(_change_key(State(hidden=1))).is_equal_to(_change_key(State(hidden=2)))
        assert_that(State(hidden=1)).is_not_equal_to(State(hidden=2))

    def test_a_value_that_reaches_back_to_itself_is_still_a_key(self):
        # a probe returning a structure that contains itself must not send the walk round forever
        cyclic: list = [1]
        cyclic.append(cyclic)
        assert_that(_change_key(cyclic)).is_not_none()

    def test_two_values_that_differ_only_in_key_order_did_not_change(self):
        recorder = _PollRecorder()
        for value in ({"a": 1, "b": 2}, {"b": 2, "a": 1}, {"a": 1, "b": 2}):
            recorder.record(elapsed=0.1, outcome="fail", value=value, detail="got it", raw=value)
        assert_that(recorder.build(elapsed=1.0).summary).is_equal_to("value unchanged across 3 polls")

    def test_the_type_reaches_the_summary_from_the_exception_not_its_text(self):
        """End to end, because the recorder is told the type by the polling loop.

        Two classes whose `__repr__` agrees are two types, and the loop is where that is decided: a test
        that hands the recorder a type name proves nothing about the hand-off.
        """

        class FirstError(RuntimeError):
            def __repr__(self):
                return "same text"

        class SecondError(RuntimeError):
            def __repr__(self):
                return "same text"

        raised = itertools.count(1)

        def probe():
            raise FirstError() if next(raised) % 2 else SecondError()

        with pytest.raises(AssertionFailure) as failure:
            assert_that(probe).eventually_sync(
                timeout=0.05, interval=0.01, ignoring=(FirstError, SecondError)
            ).is_equal_to("never")
        assert_that(failure.value.trace.summary).contains("probe raised exceptions on all")

    def test_a_probe_that_raises_its_own_assert_is_a_raise_not_a_value(self):
        """The probe never returned, so there is no value to call unchanged.

        `AssertionError` from inside the probe is indistinguishable from one raised by the assertion if
        you look only at the exception: a probe that never got past its own `assert` was recorded as a
        failed value and the run read as `value unchanged across N polls`.
        """

        def broken_probe():
            raise AssertionError("the probe itself is broken")

        with pytest.raises(AssertionFailure) as failure:
            assert_that(broken_probe).eventually_sync(timeout=0.05, interval=0.01).is_equal_to("ready")
        assert_that(failure.value.trace.summary).contains("probe raised AssertionError on all")

    def test_an_ignored_exception_that_cannot_be_reprd_is_still_retried(self):
        class HostileError(RuntimeError):
            def __repr__(self):
                raise ValueError("repr is not available")

        calls = itertools.count(1)

        def probe():
            if next(calls) < 3:
                raise HostileError("not ready")
            return "ready"

        assert_that(probe).eventually_sync(timeout=0.5, interval=0.01, ignoring=HostileError).is_equal_to("ready")

    def test_an_expected_none_is_still_a_named_expectation(self):
        # "was this named" cannot be read off a test against None: both spellings were dropped from the record
        outcome = self._collected(expected=None).failures[0]
        assert_that(outcome.has_expected).is_true()
        assert_that(outcome.expected).is_none()

    def test_an_actual_none_is_still_a_provided_value(self):
        outcome = self._collected(expected="something", probe=lambda: None).failures[0]
        assert_that(outcome.actual_provided).is_true()
        assert_that(outcome.actual).is_none()


class TestTheTimeoutMessageQuotesOnlyTheHeadline:
    """Outside pytest a failure renders its diff into `str()`, and the timeout message quotes that text.

    Carrying the same diff itself, the timed-out failure then printed the block twice: once inside the
    sentence and once under it.  Under pytest the plugin turns the in-message rendering off, so this only
    ever showed up on the surface that rendering was added for.
    """

    @staticmethod
    def _timed_out(monkeypatch):
        monkeypatch.setattr(errors, "_RENDER_DIFF_IN_MESSAGE", True)
        counter = itertools.count()
        with pytest.raises(AssertionFailure) as failure:
            assert_that(lambda: next(counter)).eventually_sync(timeout=0.05, interval=0.01).is_equal_to(-1)
        return str(failure.value)

    def test_the_diff_is_rendered_once(self, monkeypatch):
        assert_that(self._timed_out(monkeypatch).count("diff (scalar)")).is_equal_to(1)

    def test_the_quoted_failure_is_still_there(self, monkeypatch):
        text = self._timed_out(monkeypatch)
        assert_that(text).contains("Last failure: Expected <").contains("to be equal to <-1>")


class TestEventuallyTrace:
    def test_timeout_failure_carries_the_trace(self):
        states = iter([ConnectionError("boot"), {"s": "PENDING"}])

        def probe():
            state = next(states, {"s": "PENDING"})
            if isinstance(state, Exception):
                raise state
            return state

        async def scenario():
            await (
                assert_that(probe)
                .eventually(timeout=1.0, interval=0.01, ignoring=ConnectionError)
                .is_equal_to({"s": "PAID"})
            )

        with pytest.raises(AssertionFailure) as exc_info:
            asyncio.run(scenario())
        trace = exc_info.value.trace
        assert_that(trace).is_not_none()
        assert_that(trace.samples[0].outcome).is_equal_to("error")
        assert_that(trace.samples[0].value).is_none()
        assert_that(trace.samples[1].outcome).is_equal_to("fail")
        assert_that(trace.samples[1].value).is_equal_to({"s": "PENDING"})
        assert_that(trace.total_polls).is_greater_than_or_equal_to(2)
        assert_that(str(exc_info.value)).contains("(probe recovered after 1 raising poll;")

    def test_samples_are_point_in_time_snapshots_of_a_mutating_probe(self):
        live = {"step": 0}

        def probe():
            live["step"] += 1
            return live

        async def scenario():
            await assert_that(probe).eventually(timeout=1.0, interval=0.01).is_equal_to({"step": -1})

        with pytest.raises(AssertionFailure) as exc_info:
            asyncio.run(scenario())
        samples = exc_info.value.trace.samples
        assert_that(len(samples)).is_greater_than_or_equal_to(2)
        assert_that(samples[0].value).is_not_equal_to(samples[-1].value)
        assert_that(samples[0].value).is_equal_to({"step": 1})

    def test_unchanged_value_produces_unchanged_summary(self):
        async def scenario():
            await assert_that(lambda: 7).eventually(timeout=0.15, interval=0.03).is_equal_to(8)

        with pytest.raises(AssertionFailure, match=r"\(value unchanged across \d+ polls\)"):
            asyncio.run(scenario())

    def test_soft_mode_message_carries_the_summary(self):
        async def scenario():
            with soft_assertions():
                await assert_that(lambda: 7).eventually(timeout=0.15, interval=0.03).is_equal_to(8)

        with pytest.raises(AssertionError) as exc_info:
            asyncio.run(scenario())
        assert_that(str(exc_info.value)).contains("value unchanged across")


class TestContextVarsIsolation:
    def test_soft_assertions_thread_isolation(self):
        errors_from_threads = {}

        def thread_func(thread_id):
            try:
                with soft_assertions():
                    assert_that(f"thread-{thread_id}-marker").is_equal_to("wrong")
            except AssertionError as exc:
                errors_from_threads[thread_id] = str(exc)

        threads = [threading.Thread(target=thread_func, args=(i,)) for i in range(3)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert_that(errors_from_threads).is_length(3)
        for thread_id, error_msg in errors_from_threads.items():
            assert_that(error_msg).contains(f"thread-{thread_id}-marker")
            other_ids = [i for i in range(3) if i != thread_id]
            for other_id in other_ids:
                assert_that(error_msg).does_not_contain(f"thread-{other_id}-marker")

    def test_soft_assertions_async_isolation(self):
        async def task_func(task_id):
            with soft_assertions():
                assert_that(task_id).is_equal_to(-1)

        async def run_tasks():
            tasks = [asyncio.create_task(task_func(i)) for i in range(3)]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            return results

        results = asyncio.run(run_tasks())
        assert_that(results).is_length(3)
        for i, result in enumerate(results):
            assert_that(result).is_instance_of(AssertionError)
            assert_that(str(result)).contains(str(i))

    def test_soft_fail_thread_isolation(self):
        errors_from_threads = []

        def thread_func(thread_id):
            try:
                with soft_assertions():
                    soft_fail(f"error from thread {thread_id}")
            except AssertionError as exc:
                errors_from_threads.append((thread_id, str(exc)))

        threads = [threading.Thread(target=thread_func, args=(i,)) for i in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert_that(errors_from_threads).is_length(2)
        for thread_id, error_msg in errors_from_threads:
            assert_that(error_msg).contains(f"thread {thread_id}")

    def test_nested_soft_assertions_still_work(self):
        with pytest.raises(AssertionError, match="soft assertion failures"), soft_assertions():
            assert_that(1).is_equal_to(2)
            with soft_assertions():
                assert_that(3).is_equal_to(4)
            assert_that(5).is_equal_to(6)


class TestRealPollTimings:
    """The recorder unit tests hand-feed `elapsed`, so the live poll never had its clock pinned.

    Every sample and the trace total come from the same `time.monotonic()` reading. If it stops
    arriving, nothing fails until the summary reaches its "value changed N times" branch and subtracts
    one timestamp from another, and the assertion turns into a TypeError.
    """

    def test_a_mutating_sync_probe_times_out_with_real_timings(self):
        counter = itertools.count()
        with pytest.raises(AssertionError) as exc_info:
            assert_that(lambda: next(counter)).eventually_sync(timeout=0.12, interval=0.02).is_equal_to(-1)
        trace = exc_info.value.trace
        assert_that(str(exc_info.value)).contains("last change")
        assert_that(trace.elapsed).is_instance_of(float).is_greater_than_or_equal_to(0)
        for sample in trace.samples:
            assert_that(sample.elapsed).is_instance_of(float).is_between(0, 5)

    def test_a_mutating_async_probe_times_out_with_real_timings(self):
        counter = itertools.count()
        with pytest.raises(AssertionError) as exc_info:
            asyncio.run(assert_that(lambda: next(counter)).eventually(timeout=0.12, interval=0.02).is_equal_to(-1))
        trace = exc_info.value.trace
        assert_that(str(exc_info.value)).contains("last change")
        assert_that(trace.elapsed).is_instance_of(float).is_greater_than_or_equal_to(0)
        for sample in trace.samples:
            assert_that(sample.elapsed).is_instance_of(float).is_between(0, 5)


class TestRetryCollection:
    """A poll that converged late is recorded, so the plugin can name it after the run."""

    @pytest.fixture(autouse=True)
    def _clean(self, monkeypatch):
        monkeypatch.setattr(aa, "_COLLECT_RETRIES", True)
        _RETRIES.clear()
        yield
        _RETRIES.clear()

    def test_nothing_is_collected_without_the_plugin(self, monkeypatch):
        # the plugin is the only consumer: off pytest the list would grow for the life of the process
        monkeypatch.setattr(aa, "_COLLECT_RETRIES", False)
        states = itertools.chain(["PENDING"] * 2, itertools.repeat("READY"))
        assert_that(lambda: next(states)).eventually_sync(timeout=2, interval=0.02).is_equal_to("READY")
        assert_that(_RETRIES).is_empty()

    def test_a_retried_poll_is_recorded_with_its_budget(self):
        states = itertools.chain(["PENDING"] * 2, itertools.repeat("READY"))
        assert_that(lambda: next(states)).eventually_sync(timeout=2, interval=0.02).is_equal_to("READY")
        assert_that(_RETRIES).is_length(1)
        attempts, elapsed, budget = _RETRIES[0]
        assert_that(attempts).is_equal_to(3)
        assert_that(budget).is_equal_to(2)
        assert_that(elapsed).is_greater_than(0)

    def test_a_first_attempt_pass_records_nothing(self):
        assert_that(lambda: "READY").eventually_sync(timeout=2, interval=0.02).is_equal_to("READY")
        assert_that(_RETRIES).is_empty()

    def test_the_async_path_records_too(self):
        states = itertools.chain(["PENDING"] * 2, itertools.repeat("READY"))
        asyncio.run(assert_that(lambda: next(states)).eventually(timeout=2, interval=0.02).is_equal_to("READY"))
        assert_that(_RETRIES).is_length(1)

    def test_the_async_first_attempt_pass_records_nothing(self):
        # the sync mirror existed, so the async gate could turn into a disjunction and call every clean poll a retry
        asyncio.run(assert_that(lambda: "READY").eventually(timeout=2, interval=0.02).is_equal_to("READY"))
        assert_that(_RETRIES).is_empty()

    def test_the_async_path_collects_nothing_without_the_plugin(self, monkeypatch):
        monkeypatch.setattr(aa, "_COLLECT_RETRIES", False)
        states = itertools.chain(["PENDING"] * 2, itertools.repeat("READY"))
        asyncio.run(assert_that(lambda: next(states)).eventually(timeout=2, interval=0.02).is_equal_to("READY"))
        assert_that(_RETRIES).is_empty()

    def test_an_untraced_async_poll_still_passes(self):
        asyncio.run(assert_that(lambda: 7).eventually(timeout=1, interval=0.02, trace=False).is_equal_to(7))

    def test_a_timeout_records_nothing(self):
        with pytest.raises(AssertionError):
            assert_that(lambda: "PENDING").eventually_sync(timeout=0.1, interval=0.02).is_equal_to("READY")
        assert_that(_RETRIES).is_empty()


class TestATaskThatOutlivesItsSoftBlock:
    """A context variable is copied by value into a new task, so the parent's exit is invisible to it.

    The list is shared, though, and that was the hole: a task created inside the block and awaited
    after it appended its failure to a list nobody would ever read, and the test passed having checked
    nothing. Reported by an external review of the shipped code.

    The block now carries a flag beside its failures, so a child can tell that nobody is listening and
    fails on the spot instead.
    """

    def test_a_failure_after_the_block_closed_is_raised_not_swallowed(self):
        async def scenario():
            started = asyncio.Event()

            async def child():
                await started.wait()
                assert_that(1).is_equal_to(2)

            with soft_assertions():
                task = asyncio.create_task(child())
            started.set()
            await task

        with pytest.raises(AssertionFailure, match="to be equal to"):
            asyncio.run(scenario())

    def test_a_task_awaited_inside_the_block_is_still_collected(self):
        async def scenario():
            async def child():
                assert_that(1).is_equal_to(2)

            with soft_assertions():
                await asyncio.create_task(child())
                assert_that(3).is_equal_to(4)

        with pytest.raises(AssertionFailure) as failure:
            asyncio.run(scenario())
        assert_that(str(failure.value).count("to be equal to")).is_equal_to(2)

    def test_gathered_children_are_collected_together(self):
        async def scenario():
            async def child(value):
                assert_that(value).is_equal_to(0)

            with soft_assertions():
                await asyncio.gather(child(1), child(2))

        with pytest.raises(AssertionFailure) as failure:
            asyncio.run(scenario())
        assert_that(str(failure.value).count("to be equal to")).is_equal_to(2)

    def test_a_builder_made_inside_the_block_fails_when_used_after_it(self):
        """The narrower half of the same hole, and the one a checker cannot see.

        `assert_that()` called in the orphaned task builds an ordinary builder, because it asks whether
        anything is collecting. A builder *made inside* the block already carries soft mode with it, so
        the decision falls to the delivery step instead.
        """

        async def scenario():
            started = asyncio.Event()
            holder = {}

            async def child():
                await started.wait()
                holder["builder"].is_equal_to(2)

            with soft_assertions():
                holder["builder"] = assert_that(1)
                task = asyncio.create_task(child())
            started.set()
            await task

        with pytest.raises(AssertionFailure, match="to be equal to"):
            asyncio.run(scenario())

    def test_the_next_block_in_the_same_task_is_clean(self):
        async def scenario():
            started = asyncio.Event()

            async def child():
                await started.wait()
                with contextlib.suppress(AssertionFailure):
                    assert_that("orphan").is_equal_to("wrong")

            with soft_assertions():
                task = asyncio.create_task(child())
            started.set()
            await task
            with soft_assertions():
                assert_that("fresh").is_equal_to("wrong")

        with pytest.raises(AssertionFailure) as failure:
            asyncio.run(scenario())
        assert_that(str(failure.value)).contains("fresh").does_not_contain("orphan")


class TestAChainIsACoroutine:
    """Below 3.15 `asyncio.run()` and `Task` accept a coroutine and nothing else."""

    @staticmethod
    def _slow_chain(timeout: float = 5.0):
        """A chain over a value that never satisfies it, so it is still polling when asked about."""
        return assert_that(lambda: 1).eventually(timeout=timeout, interval=0.01).is_equal_to(2)

    def test_a_chain_is_a_coroutine_to_asyncio(self):
        chain = assert_that(lambda: 1).eventually(timeout=1, interval=0.01).is_equal_to(1)
        assert_that(asyncio.iscoroutine(chain)).described_as("asyncio.iscoroutine").is_true()
        assert_that(asyncio.run(chain).val).is_equal_to(1)

    def test_chains_run_together_through_gather(self):
        async def scenario():
            done = await asyncio.gather(
                assert_that(lambda: 1).eventually(timeout=1, interval=0.01).is_equal_to(1),
                assert_that(lambda: 2).eventually(timeout=1, interval=0.01).is_equal_to(2),
            )
            return [one.val for one in done]

        assert_that(asyncio.run(scenario())).is_equal_to([1, 2])

    def test_a_task_describes_itself_without_reading_a_step_as_a_code_object(self):
        """`Task.__repr__` probes the coroutine attributes of whatever it drives."""

        async def scenario():
            chain = self._slow_chain()
            task = asyncio.ensure_future(chain)
            await asyncio.sleep(0.05)
            shown = repr(task)
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            return shown

        assert_that(asyncio.run(scenario())).contains("Task").contains("pending")

    def test_a_running_chain_answers_the_coroutine_attributes(self):
        async def scenario():
            chain = self._slow_chain()
            task = asyncio.ensure_future(chain)
            await asyncio.sleep(0.05)
            seen = {
                "running": chain.cr_running,
                "code": chain.cr_code is not None,
                "frame": chain.cr_frame is not None,
                "await": chain.cr_await is not None,
            }
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            return seen

        assert_that(asyncio.run(scenario())).is_equal_to({"running": False, "code": True, "frame": True, "await": True})

    def test_a_chain_reports_the_state_a_coroutine_would(self):
        """Which attributes `inspect` reads changed in 3.11 and again in 3.14, so the family forwards."""

        async def real():
            await asyncio.sleep(5)

        chain, coro = self._slow_chain(), real()
        assert_that(inspect.getcoroutinestate(chain)).is_equal_to(inspect.getcoroutinestate(coro))
        chain.close()
        coro.close()
        assert_that(inspect.getcoroutinestate(chain)).is_equal_to(inspect.getcoroutinestate(coro))

    def test_a_suspended_chain_says_so(self):
        async def scenario():
            chain = self._slow_chain()
            task = asyncio.ensure_future(chain)
            await asyncio.sleep(0.05)
            seen = inspect.getcoroutinestate(chain)
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            return seen

        assert_that(asyncio.run(scenario())).is_equal_to(inspect.CORO_SUSPENDED)

    def test_a_chain_with_nothing_recorded_has_no_coroutine_to_describe(self):
        with pytest.raises(AttributeError):
            assert_that(lambda: 1).eventually(timeout=1).cr_code  # noqa: B018 - reading it is the point

    def test_a_generator_probe_refuses_instead_of_joining_the_chain(self):
        """A coroutine has no generator attributes, so a probe for one must not join the chain."""
        chain = self._slow_chain()
        for name in ("gi_code", "gi_frame", "gi_running", "gi_yieldfrom"):
            assert_that(hasattr(chain, name)).described_as(name).is_false()
        chain.close()

    def test_a_cancelled_chain_stops_where_it_was(self):
        async def scenario():
            task = asyncio.ensure_future(self._slow_chain(timeout=30))
            await asyncio.sleep(0.05)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            return task.cancelled()

        assert_that(asyncio.run(scenario())).is_true()

    def test_awaiting_the_same_chain_twice_refuses_the_way_a_coroutine_does(self):
        async def scenario():
            chain = assert_that(lambda: 1).eventually(timeout=1, interval=0.01).is_equal_to(1)
            await chain
            await chain

        with pytest.raises(RuntimeError, match="already awaited"):
            asyncio.run(scenario())

    def test_awaiting_a_chain_that_asserts_nothing_refuses(self):
        with pytest.raises(TypeError, match="no assertion was called"):
            asyncio.run(assert_that(lambda: 1).eventually(timeout=1, interval=0.01))

    def test_closing_a_chain_that_recorded_nothing_is_quiet(self):
        assert_that(lambda: 1).eventually(timeout=1).close()

    def test_a_closed_chain_refuses_to_run(self):
        chain = assert_that(lambda: 1).eventually(timeout=1, interval=0.01).is_equal_to(2)
        chain.close()
        with pytest.raises(RuntimeError, match="already awaited"):
            asyncio.run(chain)

    def test_a_chain_closed_after_it_ran_refuses_too(self):
        chain = assert_that(lambda: 1).eventually(timeout=1, interval=0.01).is_equal_to(1)
        asyncio.run(chain)
        chain.close()
        with pytest.raises(RuntimeError, match="already awaited"):
            asyncio.run(chain)

    def test_the_settled_value_is_not_read_off_the_chain(self):
        chain = assert_that(lambda: 1).eventually(timeout=1, interval=0.01).is_equal_to(1)
        with pytest.raises(AttributeError, match="val is available on the builder"):
            chain.val  # noqa: B018 - reading it is the whole point
        chain.close()


class TestAForgottenAwaitStaysLoud:
    """A recording has no coroutine to raise Python's own "never awaited", so it raises its own."""

    @staticmethod
    def _dropped(build):
        gc.collect()
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            build()
            gc.collect()
        return [str(one.message) for one in caught]

    def test_a_dropped_chain_warns_and_names_its_last_call(self):
        warned = self._dropped(lambda: assert_that(lambda: 1).eventually(timeout=1).is_equal_to(2))
        assert_that(warned).is_length(1)
        assert_that(warned[0]).contains("never awaited").contains("is_equal_to()")

    def test_a_chain_of_several_calls_warns_once(self):
        """Every call builds a new link, and warning per link would put three lines under one mistake."""
        warned = self._dropped(
            lambda: assert_that(lambda: 1).eventually(timeout=1).is_instance_of(int).not_.is_equal_to(2).is_positive()
        )
        assert_that(warned).is_length(1)
        assert_that(warned[0]).contains("is_positive()")

    def test_a_chain_that_only_got_introspected_warns_once(self):
        """Reading `cr_code` makes the coroutine, and Python warns about one it collects unawaited."""

        def introspected():
            chain = assert_that(lambda: 1).eventually(timeout=1).is_equal_to(2)
            assert_that(chain.cr_code).is_not_none()

        warned = self._dropped(introspected)
        assert_that(warned).is_length(1)
        assert_that(warned[0]).contains("never awaited")

    def test_an_introspected_link_that_handed_its_steps_on_is_quiet(self):
        """A link keeps the coroutine introspection made, and Python warns about one it collects."""

        def introspected_link():
            base = assert_that(lambda: 1).eventually(timeout=1).is_equal_to(1)
            assert_that(base.cr_code).is_not_none()
            base.is_positive().close()

        assert_that(self._dropped(introspected_link)).is_empty()

    def test_an_await_that_never_advanced_is_the_chain_warning_not_pythons(self):
        """`__await__()` can be called and its iterator dropped, which runs no poll."""

        def unadvanced():
            chain = assert_that(lambda: 1).eventually(timeout=1).is_equal_to(2)
            chain.__await__()

        warned = self._dropped(unadvanced)
        assert_that(warned).is_length(1)
        assert_that(warned[0]).contains("never awaited").contains("is_equal_to()")

    def test_a_chain_that_asserts_nothing_yet_is_quiet(self):
        assert_that(self._dropped(lambda: assert_that(lambda: 1).eventually(timeout=1))).is_empty()

    def test_an_awaited_chain_is_quiet(self):
        def awaited():
            asyncio.run(assert_that(lambda: 1).eventually(timeout=1, interval=0.01).is_equal_to(1))

        assert_that(self._dropped(awaited)).is_empty()

    def test_a_closed_chain_is_quiet(self):
        """Closing is a discard somebody asked for, and Python says nothing about a closed coroutine."""

        def closed():
            assert_that(lambda: 1).eventually(timeout=1).is_equal_to(2).close()

        assert_that(self._dropped(closed)).is_empty()

    def test_a_chain_closed_after_it_started_is_quiet(self):
        async def scenario():
            chain = assert_that(lambda: 1).eventually(timeout=30, interval=0.01).is_equal_to(2)
            task = asyncio.ensure_future(chain)
            await asyncio.sleep(0.05)
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            chain.close()

        assert_that(self._dropped(lambda: asyncio.run(scenario()))).is_empty()


class TestAForgottenAwaitUnderErrorFilters:
    """Raised from `__del__`, so pytest reports it through the unraisable hook, not to the caller.

    A child process rather than `catch_warnings` for that reason.
    """

    SUITE = textwrap.dedent("""
        import gc

        from assertpy import assert_that


        def test_a_forgotten_await():
            assert_that(lambda: 1).eventually(timeout=1).is_equal_to(2)
            gc.collect()


        def test_an_awaited_chain():
            import asyncio

            asyncio.run(assert_that(lambda: 1).eventually(timeout=1, interval=0.01).is_equal_to(1))
            gc.collect()
    """)

    @staticmethod
    def _run(tmp_path, ini):
        (tmp_path / "pytest.ini").write_text(ini, encoding="utf-8")
        (tmp_path / "test_forgotten.py").write_text(TestAForgottenAwaitUnderErrorFilters.SUITE, encoding="utf-8")
        # the child runs from tmp_path, so it is told where the package is rather than left to find it
        environment = {**os.environ, "PYTHONPATH": str(pathlib.Path(assertpy.__file__).parent.parent)}
        return subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "--no-header", "-p", "no:randomly", "--rootdir", str(tmp_path)],
            capture_output=True,
            text=True,
            check=False,
            cwd=tmp_path,
            env=environment,
        )

    def test_the_run_goes_red(self, tmp_path):
        result = self._run(tmp_path, "[pytest]\nfilterwarnings = error\n")
        assert_that(result.stdout).described_as("child stdout").does_not_contain("INTERNALERROR")
        assert_that(result.returncode).described_as("child exit code").is_not_zero()
        assert_that(result.stdout).contains("1 failed", "1 passed")

    def test_only_the_forgotten_one_goes_red(self, tmp_path):
        result = self._run(tmp_path, "[pytest]\nfilterwarnings = error\n")
        assert_that(result.stdout).contains("test_a_forgotten_await")
        assert_that(result.stdout).does_not_contain("test_an_awaited_chain -")

    def test_without_the_filter_it_is_a_warning(self, tmp_path):
        result = self._run(tmp_path, "[pytest]\n")
        assert_that(result.returncode).described_as("child exit code").is_zero()
        assert_that(result.stdout).contains("2 passed")


def _refusal_of(chain) -> str:
    """Why the chain refuses to hand its value back, as the text of the refusal."""
    try:
        _ = chain.val
    except TypeError as refused:
        return str(refused)
    return "it did not refuse"


class TestAPollDeliversItsOwnFailure:
    """A poll waits and then fails by itself, so there is no verdict to hand back and no value to carry on."""

    def test_check_after_a_sync_poll_is_refused(self):
        with pytest.raises(TypeError, match="check\\(\\) cannot follow a poll"):
            assertpy.assert_that(lambda: 1).eventually_sync(timeout=0.1, interval=0.01).check()

    def test_check_after_an_async_poll_is_refused(self):
        chain = assertpy.assert_that(lambda: 1).eventually(timeout=0.1, interval=0.01)
        with pytest.raises(TypeError, match="check\\(\\) cannot follow a poll"):
            chain.check()
        chain.close()

    def test_value_on_a_sync_chain_names_the_accessor_a_chain_has(self):
        """Left to the hook it was recorded as an assertion and failed inside the replay.

        The message there named a type (`'str' object is not callable`) rather than the mistake, which
        is reading the builder's accessor on a chain that hands its value back under `val`.
        """
        chain = assertpy.assert_that(lambda: "ready").eventually_sync(timeout=0.3, interval=0.01)
        with pytest.raises(TypeError, match="value cannot be read on a polling chain"):
            _ = chain.value

    def test_value_on_an_async_chain_points_at_the_builder_awaiting_it_returns(self):
        chain = assertpy.assert_that(lambda: "ready").eventually(timeout=0.3, interval=0.01)
        with pytest.raises(AttributeError, match="value is available on the builder"):
            _ = chain.value
        chain.close()

    def test_a_timed_out_soft_chain_asserts_nothing_more(self):
        """It timed out without a value, so everything after it was asked about `None`."""
        with pytest.raises(assertpy.AssertionFailure) as caught, assertpy.soft_assertions():
            timed_out = assertpy.assert_that(lambda: 1).eventually_sync(timeout=0.04, interval=0.01).is_equal_to(2)
            timed_out.is_none()
            timed_out.is_equal_to(7)
        report = str(caught.value)
        assertpy.assert_that(report.count("condition not met")).described_as("entries").is_equal_to(1)
        assertpy.assert_that(report).does_not_contain("<None>")

    def test_a_timed_out_chain_carries_its_timeout_into_what_it_hands_back(self):
        """The failure a reader acts on is the timeout, so the inert chain has to carry it.

        Built without it, `check()` answered `passed=False` with an empty message and the refusals on
        `.val` and `.value` named the rule rather than the wait that ran out.

        Read outside the block: an assertion written inside one is collected, so a test that checks the
        outcome there cannot fail on what it found.
        """
        read = {}
        with pytest.raises(assertpy.AssertionFailure), assertpy.soft_assertions():
            timed_out = assertpy.assert_that(lambda: 1).eventually_sync(timeout=0.04, interval=0.01).is_equal_to(2)
            read["outcome"] = timed_out.check().is_equal_to(7)
            read["refusal"] = _refusal_of(timed_out)
        assertpy.assert_that(read["outcome"].passed).described_as("a chain that timed out").is_false()
        assertpy.assert_that(read["outcome"].message).described_as("the verdict's message").contains(
            "condition not met"
        )
        assertpy.assert_that(read["refusal"]).described_as("why .val refuses").contains("condition not met")

    def test_an_awaited_timed_out_chain_carries_its_timeout_too(self):
        """The same claim for the awaitable chain, asked rather than inferred from the shared path."""

        async def collected():
            return await assertpy.assert_that(lambda: 1).eventually(timeout=0.04, interval=0.01).is_equal_to(2)

        read = {}
        with pytest.raises(assertpy.AssertionFailure), assertpy.soft_assertions():
            timed_out = asyncio.run(collected())
            read["outcome"] = timed_out.check().is_equal_to(7)
            read["refusal"] = _refusal_of(timed_out)
        assertpy.assert_that(read["outcome"].passed).described_as("an awaited chain that timed out").is_false()
        assertpy.assert_that(read["outcome"].message).described_as("the verdict's message").contains(
            "condition not met"
        )
        assertpy.assert_that(read["refusal"]).described_as("why .val refuses").contains("condition not met")

    def test_a_timed_out_warn_chain_asserts_nothing_more(self):
        capture = StringIO()
        logger = logging.getLogger("poll-warn-capture")
        logger.handlers.clear()
        logger.addHandler(logging.StreamHandler(capture))
        adapted = assertpy.WarningLoggingAdapter(logger, None)
        timed_out = (
            assertpy.assert_warn(lambda: 1, logger=adapted).eventually_sync(timeout=0.04, interval=0.01).is_equal_to(2)
        )
        timed_out.is_none()
        logged = capture.getvalue()
        assertpy.assert_that(logged.count("condition not met")).described_as("warnings").is_equal_to(1)
        assertpy.assert_that(logged).does_not_contain("<None>")

    @pytest.mark.parametrize("timeout", [0.04, 0.123456789], ids=["short", "past-six-digits"])
    def test_the_budget_is_printed_as_it_was_given(self, timeout):
        with pytest.raises(assertpy.AssertionFailure) as caught:
            assertpy.assert_that(lambda: 1).eventually_sync(timeout=timeout, interval=0.01).is_equal_to(2)
        assertpy.assert_that(str(caught.value)).contains(f"after {timeout} seconds")

    def test_a_hint_the_quoted_failure_carries_is_not_repeated(self):
        with pytest.raises(assertpy.AssertionFailure) as caught, assertpy.soft_assertions():
            assertpy.assert_that(lambda: [1, 2]).eventually_sync(timeout=0.04, interval=0.01).is_equal_to([2, 1])
        assertpy.assert_that(str(caught.value).count("same elements, in a different order")).is_equal_to(1)


class TestTheChangeKeyRendersAsItAlwaysDid:
    """A key that renders differently reads as a value that moved, which is what the poll report is about."""

    @pytest.mark.parametrize(
        ("value", "rendered"),
        [
            pytest.param(1, "v1:1", id="int"),
            pytest.param(1.0, "v3:1.0", id="float-that-equals-the-int"),
            pytest.param(None, "v4:None", id="none"),
            pytest.param("x:1", "v5:'x:1'", id="string-with-punctuation"),
            pytest.param("[1, 2]", "v8:'[1, 2]'", id="string-that-looks-like-a-list"),
            pytest.param([], "l", id="empty-list"),
            pytest.param([1, 2], "l4:v1:14:v1:2", id="list"),
            pytest.param((1, 2), "t4:v1:14:v1:2", id="tuple"),
            pytest.param({1, 2}, "s4:v1:14:v1:2", id="set"),
            pytest.param({"a": 1}, "d6:v3:'a'4:v1:1", id="dict"),
            pytest.param(OrderedDict([("b", 1), ("a", 2)]), "o6:v3:'b'4:v1:16:v3:'a'4:v1:2", id="ordered-dict"),
            pytest.param({"a": [1, {2}]}, "d6:v3:'a'16:l4:v1:17:s4:v1:2", id="nested"),
        ],
    )
    def test_a_value_renders_to_exactly_this(self, value, rendered):
        assertpy.assert_that(async_assertions._canonical(value)).is_equal_to(rendered)

    def test_a_leaf_that_appears_twice_is_rendered_twice(self):
        """Only a container can reach back to itself, so sharing a leaf is not a cycle."""
        shared = [1]
        assertpy.assert_that(async_assertions._canonical([shared, shared])).is_equal_to("l7:l4:v1:17:l4:v1:1")

    def test_a_container_that_holds_itself_is_marked(self):
        cyclic: list[object] = []
        cyclic.append(cyclic)
        assertpy.assert_that(async_assertions._canonical(cyclic)).is_equal_to("l1:c")

    def test_two_values_that_differ_only_in_type_do_not_share_a_key(self):
        distinct = {async_assertions._canonical(value) for value in ([1], (1,), {1}, "1", 1, 1.0, True, {"1": 1})}
        assertpy.assert_that(distinct).is_length(8)
