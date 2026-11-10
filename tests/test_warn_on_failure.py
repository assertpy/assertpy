"""`assert_warn(on_failure=...)`: each failure handed to the caller as its record instead of logged as text."""

import asyncio
import logging
import os
import sys
from unittest.mock import patch

import pytest

from assertpy import AssertionOutcome, assert_that, assert_warn
from assertpy.assertpy import _Subscribed


def test_a_failure_reaches_the_callback_as_its_record():
    got = []
    assert_warn({"a": 1}, on_failure=got.append).is_equal_to({"a": 2})
    assert_that(got).is_length(1)
    outcome = got[0]
    assert_that(outcome).is_instance_of(AssertionOutcome)
    assert_that(outcome.message).is_equal_to("Expected <{'a': 1}> to be equal to <{'a': 2}>, but was not.")
    assert_that((outcome.actual, outcome.expected)).is_equal_to(({"a": 1}, {"a": 2}))
    assert_that(str(outcome.diff).splitlines()).is_equal_to(["diff (dict):", "  a:", "    - 1", "    + 2"])
    assert_that(outcome.requirement.operation).is_equal_to("is_equal_to")


def test_the_record_is_located_where_the_assertion_was_written():
    got = []
    line = sys._getframe().f_lineno + 1
    assert_warn(1, on_failure=got.append).is_equal_to(2)
    assert_that(got[0].location).is_not_none()
    file, at = got[0].location
    assert_that((os.path.basename(file), at)).is_equal_to(("test_warn_on_failure.py", line))


def test_each_link_of_a_chain_is_handed_over_once():
    got = []
    assert_warn("foo", on_failure=got.append).is_length(4).is_upper().starts_with("f").ends_with("x")
    assert_that([outcome.requirement.operation for outcome in got]).is_equal_to(["is_length", "is_upper", "ends_with"])


def test_nothing_is_logged():
    with patch.object(logging.Logger, "warning") as logged:
        assert_warn(1, on_failure=lambda outcome: None).is_equal_to(2)
    assert_that(logged.call_count).is_zero()


def test_a_passing_chain_hands_over_nothing():
    got = []
    assert_warn("foo", on_failure=got.append).is_length(3).is_lower()
    assert_that(got).is_empty()


def test_a_negation_is_handed_over_as_negated():
    got = []
    assert_warn(1, on_failure=got.append).not_.is_equal_to(1)
    outcome = got[0]
    assert_that(outcome.message).is_equal_to("Expected <1> to NOT satisfy: is_equal_to(1)")
    assert_that(outcome.actual).is_equal_to(1)
    assert_that(outcome.requirement).is_not_none()
    assert_that((outcome.requirement.operation, outcome.requirement.negated)).is_equal_to(("is_equal_to", True))


def test_a_pivot_and_an_extraction_keep_the_callback():
    got = []
    assert_warn(b"abc", on_failure=got.append).decoded_as("utf-8").is_equal_to("xyz")
    assert_warn([{"a": 1}], on_failure=got.append).extracting("a").contains(2)
    assert_that(got).is_length(2)


@pytest.mark.needs("jsonpath_ng")
def test_a_json_path_pivot_keeps_the_callback():
    got = []
    assert_warn({"a": 1}, on_failure=got.append).at_json_path("$.a").is_equal_to(2)
    assert_that(got).is_length(1)


def test_an_expected_exception_chain_keeps_the_callback():
    def raises_key_error():
        raise KeyError("k")

    got = []
    assert_warn(lambda: None, on_failure=got.append).raises(ValueError).when_called_with()
    assert_warn(raises_key_error, on_failure=got.append).raises(KeyError).when_called_with().is_equal_to("'x'")
    assert_that([outcome.requirement.operation for outcome in got]).is_equal_to(["when_called_with", "is_equal_to"])


def test_a_poll_that_timed_out_is_handed_over_with_its_trace():
    got = []
    assert_warn(lambda: 1, on_failure=got.append).eventually_sync(timeout=0.05, interval=0.01).is_equal_to(2)
    assert_that(got).is_length(1)
    assert_that(got[0].trace).is_not_none()


def test_an_awaited_poll_that_timed_out_is_handed_over():
    got = []

    async def scenario():
        await assert_warn(lambda: 1, on_failure=got.append).eventually(timeout=0.05, interval=0.01).is_equal_to(2)

    asyncio.run(scenario())
    assert_that(got).is_length(1)
    assert_that(got[0].trace).is_not_none()


def test_the_value_is_unverified_after_a_failure_handed_over():
    chain = assert_warn(1, on_failure=lambda outcome: None)
    chain.is_equal_to(2)
    assert_that(lambda: chain.value).raises(TypeError).when_called_with().contains("soft or warn mode")


def test_an_exception_the_callback_raises_comes_out_of_the_assertion_and_the_value_stays_unverified():
    def refuses(outcome):
        raise RuntimeError("the handler refused")

    chain = assert_warn(1, on_failure=refuses)
    assert_that(chain.is_equal_to).raises(RuntimeError).when_called_with(2).is_equal_to("the handler refused")
    assert_that(lambda: chain.value).raises(TypeError).when_called_with().contains("soft or warn mode")


def test_an_assertion_error_the_callback_raises_comes_out_too():
    def escalates(outcome):
        raise AssertionError(outcome.message)

    assert_that(assert_warn(1, on_failure=escalates).is_equal_to).raises(AssertionError).when_called_with(
        2
    ).is_equal_to("Expected <1> to be equal to <2>, but was not.")


def test_an_exception_the_logger_raises_comes_out_too():
    class Refusing:
        def warning(self, msg):
            raise OSError("disk full")

    assert_that(assert_warn(1, logger=Refusing()).is_equal_to).raises(OSError).when_called_with(2).is_equal_to(
        "disk full"
    )


def test_an_explicit_none_logs_as_before():
    with patch.object(logging.Logger, "warning") as logged:
        assert_warn(1, logger=logging.getLogger("on-failure-none"), on_failure=None).is_equal_to(2)
    assert_that(logged.call_count).is_equal_to(1)


def test_a_logger_beside_the_callback_is_refused():
    assert_that(assert_warn).raises(TypeError).when_called_with(
        1, logger=logging.getLogger("both"), on_failure=print
    ).starts_with(
        "given logger arg must be None when on_failure is given, which takes each failure in its place, but was <"
    )


def test_a_callback_that_cannot_be_called_is_refused():
    assert_that(assert_warn).raises(TypeError).when_called_with(1, on_failure="print").is_equal_to(
        "given on_failure arg must be callable, but was <'print'> (str)"
    )


def test_code_logging_through_the_chains_logger_reaches_the_callback_as_a_record():
    got = []
    _Subscribed(got.append).warning("logged by an extension")
    assert_that(got).is_length(1)
    assert_that(got[0].message).is_equal_to("logged by an extension")
    assert_that(got[0].location).is_not_none()
    assert_that(os.path.basename(got[0].location[0])).is_equal_to("test_warn_on_failure.py")
