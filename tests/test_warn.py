import logging
from io import StringIO
from unittest.mock import patch

import assertpy.assertpy as assertpy_module
from assertpy import WarningLoggingAdapter, assert_that, assert_warn


def test_success():
    assert_warn("foo").is_length(3)
    assert_warn("foo").is_not_empty()
    assert_warn("foo").is_true()
    assert_warn("foo").is_alpha()
    assert_warn("123").is_digit()
    assert_warn("foo").is_lower()
    assert_warn("FOO").is_upper()
    assert_warn("foo").is_equal_to("foo")
    assert_warn("foo").is_not_equal_to("bar")
    assert_warn("foo").is_equal_to_ignoring_case("FOO")


def test_failures():
    capture = StringIO()
    logger = logging.getLogger("capture")
    handler = logging.StreamHandler(capture)
    logger.addHandler(handler)
    adapted = WarningLoggingAdapter(logger, None)

    assert_warn("foo", logger=adapted).is_length(4)
    assert_warn("foo", logger=adapted).is_empty()
    assert_warn("foo", logger=adapted).is_false()
    assert_warn("foo", logger=adapted).is_digit()
    assert_warn("123", logger=adapted).is_alpha()
    assert_warn("foo", logger=adapted).is_upper()
    assert_warn("FOO", logger=adapted).is_lower()
    assert_warn("foo", logger=adapted).is_equal_to("bar")
    assert_warn("foo", logger=adapted).is_not_equal_to("foo")
    assert_warn("foo", logger=adapted).is_equal_to_ignoring_case("BAR")

    out = capture.getvalue()
    capture.close()

    assert_that(out).contains("[test_warn.py:29]: Expected <foo> to be of length <4>, but was <3>.")
    assert_that(out).contains("[test_warn.py:30]: Expected <foo> to be empty string, but was not.")
    assert_that(out).contains("[test_warn.py:31]: Expected <foo> to be <False>, but was not.")
    assert_that(out).contains("[test_warn.py:32]: Expected <foo> to contain only digits, but did not.")
    assert_that(out).contains("[test_warn.py:33]: Expected <123> to contain only alphabetic chars, but did not.")
    assert_that(out).contains("[test_warn.py:34]: Expected <foo> to contain only uppercase chars, but did not.")
    assert_that(out).contains("[test_warn.py:35]: Expected <FOO> to contain only lowercase chars, but did not.")
    assert_that(out).contains("[test_warn.py:36]: Expected <foo> to be equal to <bar>, but was not.")
    assert_that(out).contains("[test_warn.py:37]: Expected <foo> to be not equal to <foo>, but was.")
    assert_that(out).contains("[test_warn.py:38]: Expected <foo> to be case-insensitive equal to <BAR>, but was not.")


def test_chained_failure():
    capture2 = StringIO()
    logger = logging.getLogger("capture2")
    handler = logging.StreamHandler(capture2)
    logger.addHandler(handler)
    adapted = WarningLoggingAdapter(logger, None)

    assert_warn("foo", logger=adapted).is_length(4).is_in("bar").does_not_contain_duplicates()

    out = capture2.getvalue()
    capture2.close()

    assert_that(out).contains("[test_warn.py:62]: Expected <foo> to be of length <4>, but was <3>.")
    assert_that(out).contains("[test_warn.py:62]: Expected <foo> to be in <bar>, but was not.")
    assert_that(out).contains("[test_warn.py:62]: Expected <foo> to not contain duplicates, but <o> was repeated.")


def test_failures_with_renamed_import():
    from assertpy import assert_warn as warn

    capture3 = StringIO()
    logger = logging.getLogger("capture3")
    handler = logging.StreamHandler(capture3)
    logger.addHandler(handler)
    adapted = WarningLoggingAdapter(logger, None)

    warn("foo", logger=adapted).is_length(4)
    warn("foo", logger=adapted).is_empty()
    warn("foo", logger=adapted).is_false()
    warn("foo", logger=adapted).is_digit()
    warn("123", logger=adapted).is_alpha()
    warn("foo", logger=adapted).is_upper()
    warn("FOO", logger=adapted).is_lower()
    warn("foo", logger=adapted).is_equal_to("bar")
    warn("foo", logger=adapted).is_not_equal_to("foo")
    warn("foo", logger=adapted).is_equal_to_ignoring_case("BAR")

    out = capture3.getvalue()
    capture3.close()

    assert_that(out).contains("[test_warn.py:81]: Expected <foo> to be of length <4>, but was <3>.")
    assert_that(out).contains("[test_warn.py:82]: Expected <foo> to be empty string, but was not.")
    assert_that(out).contains("[test_warn.py:83]: Expected <foo> to be <False>, but was not.")
    assert_that(out).contains("[test_warn.py:84]: Expected <foo> to contain only digits, but did not.")
    assert_that(out).contains("[test_warn.py:85]: Expected <123> to contain only alphabetic chars, but did not.")
    assert_that(out).contains("[test_warn.py:86]: Expected <foo> to contain only uppercase chars, but did not.")
    assert_that(out).contains("[test_warn.py:87]: Expected <FOO> to contain only lowercase chars, but did not.")
    assert_that(out).contains("[test_warn.py:88]: Expected <foo> to be equal to <bar>, but was not.")
    assert_that(out).contains("[test_warn.py:89]: Expected <foo> to be not equal to <foo>, but was.")
    assert_that(out).contains("[test_warn.py:90]: Expected <foo> to be case-insensitive equal to <BAR>, but was not.")


def test_failure_without_locatable_caller_frame():
    # a user file living under a directory named "assertpy" can shadow every stack frame; the
    capture = StringIO()
    logger = logging.getLogger("capture-unwind")
    logger.addHandler(logging.StreamHandler(capture))
    adapted = WarningLoggingAdapter(logger, None)

    # every frame reads as internal, so there is no handover to a user frame to report
    class _EverythingIsInternal(frozenset):
        def __contains__(self, item):
            return True

    with patch.object(assertpy_module, "ASSERTPY_FILES", _EverythingIsInternal()):
        assert_warn("foo", logger=adapted).is_equal_to("bar")

    assert_that(capture.getvalue()).starts_with("Expected <foo> to be equal to <bar>, but was not.")


def _captured_warn(subject, expected):
    """Run one warn-mode comparison against a private logger and return what it wrote."""
    capture = StringIO()
    logger = logging.getLogger("capture_diff")
    logger.handlers.clear()
    logger.addHandler(logging.StreamHandler(capture))
    assert_warn(subject, logger=WarningLoggingAdapter(logger, None)).is_equal_to(expected)
    return capture.getvalue()


def test_warn_carries_the_diff_paths():
    # warn never fails the test, so this line is the only thing the reader ever sees: dropping the
    out = _captured_warn({"a": {"b": 1}}, {"a": {"b": 2}})
    assert_that(out).contains("a.b: 1 != 2")


def test_warn_on_a_scalar_stays_a_single_line():
    out = _captured_warn(1, 2)
    assert_that(out.strip().splitlines()).is_length(1)


def test_a_pivot_keeps_the_warn_logger():
    """Six pivots built the next builder without the logger, so warn mode fell back to the root one."""
    capture = StringIO()
    logger = logging.getLogger("pivot-capture")
    logger.handlers.clear()
    logger.addHandler(logging.StreamHandler(capture))
    adapted = WarningLoggingAdapter(logger, None)

    assert_warn(b"abc", logger=adapted).decoded_as("utf-8").is_equal_to("xyz")
    assert_warn("a1", logger=adapted).matches_with_groups(r"(a)(\d)").is_equal_to(("x", "y"))
    assert_warn({"a": 1}, logger=adapted).at_json_path("$.a").is_equal_to(2)

    assert_that(capture.getvalue().count("Expected")).described_as("warnings").is_equal_to(3)
