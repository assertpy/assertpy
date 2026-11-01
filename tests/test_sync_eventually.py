import asyncio
import logging
from contextlib import nullcontext
from io import StringIO

import pytest

from assertpy import (
    AssertionFailure,
    WarningLoggingAdapter,
    assert_that,
    assert_warn,
    soft_assertions,
)
from assertpy.async_assertions import SyncAssertionBuilder


def _unreachable():
    raise ConnectionError("down")


class TestEventuallySyncBasic:
    def test_value_converges(self):
        counter = {"n": 0}

        def get_count():
            counter["n"] += 1
            return counter["n"]

        result = assert_that(get_count).eventually_sync(timeout=2, interval=0.01).is_equal_to(3)
        assert_that(result).is_not_none()

    def test_immediate_match(self):
        assert_that(lambda: 42).eventually_sync(timeout=1, interval=0.01).is_equal_to(42)

    def test_returned_builder_chains(self):
        assert_that(lambda: 42).eventually_sync(timeout=1, interval=0.01).is_equal_to(42).is_greater_than(41)

    def test_timeout_raises(self):
        with pytest.raises(AssertionError, match="not met after"):
            assert_that(lambda: 0).eventually_sync(timeout=0.1, interval=0.02).is_equal_to(999)

    def test_timeout_message_includes_summary_and_last_failure(self):
        with pytest.raises(AssertionFailure, match=r"\(value unchanged across \d+ polls\).*to be equal to"):
            assert_that(lambda: 1).eventually_sync(timeout=0.1, interval=0.02).is_equal_to(999)

    def test_non_callable_raises_type_error(self):
        with pytest.raises(TypeError, match="val must be callable, since eventually_sync"):
            assert_that(42).eventually_sync()

    def test_async_probe_raises_type_error(self):
        async def probe():
            return 42  # pragma: no cover - the coroutine is closed before running

        with pytest.raises(TypeError, match=r"use eventually\(\) and await it"):
            assert_that(probe).eventually_sync(timeout=1, interval=0.01).is_equal_to(42)

    def test_non_coroutine_awaitable_probe_raises_type_error(self):
        class FutureLike:
            def __await__(self):
                return iter(())

        with pytest.raises(TypeError, match=r"use eventually\(\) and await it"):
            assert_that(lambda: FutureLike()).eventually_sync(timeout=1, interval=0.01).is_equal_to(42)


class TestTheValueBehindTheChain:
    """`.val` is declared on the poller because every other name means "poll for this".

    Left to `__getattr__`, reading it would have polled once and handed back a function, which is the
    kind of answer that looks like a value until it is used.
    """

    def test_it_hands_back_what_the_passing_poll_saw(self):
        states = iter(["pending", "ready"])
        chain = assert_that(lambda: next(states, "ready")).eventually_sync(timeout=1, interval=0.01)
        assert_that(chain.is_equal_to("ready").val).is_equal_to("ready")

    def test_it_refuses_before_anything_has_passed(self):
        chain = assert_that(lambda: 1).eventually_sync(timeout=1, interval=0.01)
        with pytest.raises(AttributeError, match="once an assertion on this chain has passed"):
            _ = chain.val


class TestEventuallySyncChaining:
    def test_within_and_every(self):
        counter = {"n": 0}

        def get_count():
            counter["n"] += 1
            return counter["n"]

        builder = assert_that(get_count).eventually_sync()
        assert_that(builder).is_instance_of(SyncAssertionBuilder)
        builder.within(2).every(0.01).is_equal_to(3)

    def test_various_assertions(self):
        counter = {"n": 0}

        def get_value():
            counter["n"] += 1
            return counter["n"]

        assert_that(get_value).eventually_sync(timeout=2, interval=0.01).is_greater_than(3)

    def test_string_assertion(self):
        states = iter(["loading", "loading", "ready"])

        def get_status():
            return next(states, "ready")

        assert_that(get_status).eventually_sync(timeout=1, interval=0.01).is_equal_to("ready")

    def test_private_attr_raises_attribute_error(self):
        builder = assert_that(lambda: 1).eventually_sync()
        with pytest.raises(AttributeError):
            _ = builder._nonexistent


class TestEventuallySyncIgnoring:
    def test_ignored_exception_is_retried(self):
        calls = {"n": 0}

        def probe():
            calls["n"] += 1
            if calls["n"] < 3:
                raise ConnectionError("not ready")
            return 42

        assert_that(probe).eventually_sync(timeout=2, interval=0.01, ignoring=ConnectionError).is_equal_to(42)
        assert_that(calls["n"]).is_equal_to(3)

    def test_exception_not_ignored_propagates_immediately(self):
        calls = {"n": 0}

        def probe():
            calls["n"] += 1
            raise ConnectionError("not ready")

        with pytest.raises(ConnectionError, match="not ready"):
            assert_that(probe).eventually_sync(timeout=2, interval=0.01).is_equal_to(42)
        assert_that(calls["n"]).is_equal_to(1)

    def test_ignored_exception_until_timeout_reports_last_failure(self):
        def probe():
            raise ConnectionError("still booting")

        with pytest.raises(AssertionError, match=r"not met after .* ConnectionError\('still booting'\)"):
            assert_that(probe).eventually_sync(timeout=0.1, interval=0.02, ignoring=ConnectionError).is_none()

    def test_ignoring_chainable_on_builder(self):
        calls = {"n": 0}

        def probe():
            calls["n"] += 1
            if calls["n"] < 2:
                raise ConnectionError("not ready")
            return "ok"

        assert_that(probe).eventually_sync().within(2).every(0.01).ignoring(ConnectionError).is_equal_to("ok")

    def test_ignoring_rejects_non_exception_type(self):
        with pytest.raises(TypeError, match="Exception subclass"):
            assert_that(lambda: 1).eventually_sync(ignoring=42)

    def test_ignoring_method_rejects_non_exception_type(self):
        with pytest.raises(TypeError, match="Exception subclass"):
            assert_that(lambda: 1).eventually_sync().ignoring(int)


class TestEventuallySyncFailureModes:
    def test_soft_collects_timeout_failure_and_continues(self):
        with pytest.raises(AssertionError) as exc_info, soft_assertions():
            assert_that(lambda: 1).eventually_sync(timeout=0.1, interval=0.02).is_equal_to(2)
            assert_that("after-eventually-marker").is_equal_to("other")
        text = str(exc_info.value)
        assert_that(text).contains("soft assertion failures")
        assert_that(text).contains("not met after")
        assert_that(text).contains("after-eventually-marker")

    def test_soft_passing_eventually_collects_nothing(self):
        with soft_assertions():
            assert_that(lambda: 42).eventually_sync(timeout=1, interval=0.01).is_equal_to(42)

    def test_warn_logs_timeout_failure_without_raising(self):
        capture = StringIO()
        logger = logging.getLogger("capture-eventually-sync-warn")
        logger.addHandler(logging.StreamHandler(capture))
        adapted = WarningLoggingAdapter(logger, None)

        assert_warn(lambda: 1, logger=adapted).eventually_sync(timeout=0.1, interval=0.02).is_equal_to(2)
        assert_that(capture.getvalue()).contains("not met after").contains("to be equal to <2>")


class TestEventuallySyncTrace:
    def test_timeout_failure_carries_the_trace(self):
        states = iter([ConnectionError("boot"), {"s": "PENDING"}])

        def probe():
            state = next(states, {"s": "PENDING"})
            if isinstance(state, Exception):
                raise state
            return state

        with pytest.raises(AssertionFailure) as exc_info:
            assert_that(probe).eventually_sync(timeout=0.5, interval=0.01, ignoring=ConnectionError).is_equal_to(
                {"s": "PAID"}
            )
        trace = exc_info.value.trace
        assert_that(trace).is_not_none()
        assert_that(trace.samples[0].outcome).is_equal_to("error")
        assert_that(trace.samples[1].outcome).is_equal_to("fail")
        assert_that(trace.samples[1].value).is_equal_to({"s": "PENDING"})
        assert_that(trace.total_polls).is_greater_than_or_equal_to(2)
        assert_that(str(exc_info.value)).contains("(probe recovered after 1 raising poll;")

    @pytest.mark.parametrize("mode", ["hard", "soft"])
    def test_a_timeout_records_the_value_the_assertion_saw_in_either_mode(self, mode):
        """Collected by a soft block, the timeout was recorded over `None`, where the raised one kept `-1`."""
        with pytest.raises(AssertionFailure) as exc_info, soft_assertions() if mode == "soft" else nullcontext():
            assert_that(lambda: -1).eventually_sync(timeout=0, interval=0).is_positive()
        record = exc_info.value.failures[0] if mode == "soft" else exc_info.value._outcome
        assert_that(record.actual).is_equal_to(-1)

    def test_a_soft_timeout_whose_last_poll_raised_an_ignored_error_is_still_collected(self):
        """That last failure carries no value at all, and the collected timeout records none."""
        with pytest.raises(AssertionFailure) as exc_info, soft_assertions():
            assert_that(_unreachable).eventually_sync(timeout=0, interval=0, ignoring=ConnectionError).is_positive()
        assert_that(exc_info.value.failures[0].actual).is_none()

    def test_a_timeout_collected_by_a_soft_block_keeps_its_trace(self):
        # a collected timeout dropped the telemetry: `error()` had nowhere to put a trace, only the raising path did
        with pytest.raises(AssertionFailure) as exc_info, soft_assertions():
            assert_that(lambda: {"s": "PENDING"}).eventually_sync(timeout=0.05, interval=0.01).is_equal_to(
                {"s": "PAID"}
            )
        collected = exc_info.value.failures[0]
        assert_that(collected.trace).is_not_none()
        assert_that(collected.trace.total_polls).is_greater_than_or_equal_to(1)
        assert_that(collected.trace.summary).contains("unchanged")


class TestEventuallyTraceOptOut:
    def test_sync_trace_false_plain_message_and_no_trace(self):
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that(lambda: 7).eventually_sync(timeout=0.1, interval=0.02, trace=False).is_equal_to(8)
        assert_that(exc_info.value.trace).is_none()
        message = str(exc_info.value)
        assert_that(message).starts_with("Expected condition not met after 0.1 seconds. Last failure:")
        assert_that(message).does_not_contain("value unchanged across")

    def test_async_trace_false_plain_message_and_no_trace(self):
        async def scenario():
            await assert_that(lambda: 7).eventually(timeout=0.1, interval=0.02, trace=False).is_equal_to(8)

        with pytest.raises(AssertionFailure) as exc_info:
            asyncio.run(scenario())
        assert_that(exc_info.value.trace).is_none()
        assert_that(str(exc_info.value)).starts_with("Expected condition not met after 0.1 seconds. Last failure:")

    def test_trace_default_still_records(self):
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that(lambda: 7).eventually_sync(timeout=0.1, interval=0.02).is_equal_to(8)
        assert_that(exc_info.value.trace).is_not_none()


class TestEventuallyIgnoresSeveralClasses:
    @pytest.mark.parametrize(
        "ignoring", [(ConnectionError, KeyError), ConnectionError | KeyError, ((KeyError,), ConnectionError)]
    )
    def test_any_one_of_them_is_retried(self, ignoring):
        calls = {"n": 0}

        def probe():
            calls["n"] += 1
            if calls["n"] == 1:
                raise ConnectionError("not ready")
            if calls["n"] == 2:
                raise KeyError("not yet")
            return 42

        assert_that(probe).eventually_sync(timeout=2, interval=0.01, ignoring=ignoring).is_equal_to(42)
        assert_that(calls["n"]).is_equal_to(3)

    def test_the_method_takes_them_too(self):
        calls = {"n": 0}

        def probe():
            calls["n"] += 1
            if calls["n"] < 2:
                raise KeyError("not ready")
            return "ok"

        assert_that(probe).eventually_sync().within(2).every(0.01).ignoring(ConnectionError | KeyError).is_equal_to(
            "ok"
        )

    def test_nothing_named_retries_nothing_as_before(self):
        def probe():
            raise ConnectionError("down")

        for ignoring in ((), ((),)):
            with pytest.raises(ConnectionError):
                assert_that(probe).eventually_sync(timeout=2, interval=0.01, ignoring=ignoring).is_equal_to(42)

    @pytest.mark.parametrize("wrong", [(ValueError, KeyboardInterrupt), ValueError | SystemExit, (ValueError, int)])
    def test_a_member_the_loop_must_never_swallow_is_refused(self, wrong):
        with pytest.raises(TypeError) as refusal:
            assert_that(lambda: 1).eventually_sync(ignoring=wrong)
        assert_that(str(refusal.value)).starts_with(
            "given ignoring arg must be an Exception subclass, or a union or a tuple of them, but was <"
        )
