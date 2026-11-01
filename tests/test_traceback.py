import sys
import traceback

import pytest

from assertpy import AssertionFailure, assert_that, fail


def test_traceback():
    try:
        assert_that("foo").is_equal_to("bar")
        fail("should have raised error")
    except AssertionError as ex:
        assert_that(str(ex)).is_equal_to("Expected <foo> to be equal to <bar>, but was not.")
        assert_that(ex).is_instance_of(AssertionError)
        assert_that(ex).is_instance_of(AssertionFailure)

        _, _, tb = sys.exc_info()
        assert_that(tb).is_not_none()

        if sys.version_info[0] == 3 and sys.version_info[1] >= 5:
            frames = [
                (frame.f_code.co_filename, frame.f_code.co_name, lineno) for frame, lineno in traceback.walk_tb(tb)
            ]

            assert_that(frames).is_length(3)

            assert_that(frames[0][0]).ends_with("test_traceback.py")
            assert_that(frames[0][1]).is_equal_to("test_traceback")
            assert_that(frames[0][2]).is_equal_to(11)

            assert_that(frames[1][0]).ends_with("base.py")
            assert_that(frames[1][1]).is_equal_to("is_equal_to")
            assert_that(frames[1][2]).is_greater_than(40)

            assert_that(frames[2][0]).ends_with("assertpy.py")
            assert_that(frames[2][1]).is_equal_to("error")
            assert_that(frames[2][2]).is_greater_than(100)


class TestExceptionContext:
    """Which exception a failure drags along above itself.

    Chaining is Python's own behavior and a plain ``assert`` does it too, so the line is not "never
    chain".  A caught exception is suppressed only where we wrote the ``try`` ourselves *and* its text
    is already inside our message, which makes it pure duplication.  Everything else keeps the chain,
    and the two tests below that assert a context *survives* are the ones that stop this being
    "fixed" one day by a blanket ``from None`` inside ``error()``.
    """

    def test_callers_own_context_survives(self):
        # the caller wrote this try/except, so the ValueError is their context and not ours to drop
        with pytest.raises(AssertionError) as exc_info:
            try:
                raise ValueError("the original problem")
            except ValueError:
                assert_that("actual").is_equal_to("expected")
        assert_that(exc_info.value.__suppress_context__).is_false()
        assert_that(exc_info.value.__context__).is_instance_of(ValueError)

    def test_raises_keeps_the_exception_it_caught(self):
        # here the chained exception is the caller's bug, and its traceback is the point of the failure
        def boom():
            raise KeyError("missing")

        with pytest.raises(AssertionError) as exc_info:
            assert_that(boom).raises(ValueError).when_called_with()
        assert_that(exc_info.value.__suppress_context__).is_false()
        assert_that(exc_info.value.__context__).is_instance_of(KeyError)

    def test_wrapped_plumbing_is_dropped(self):
        # the IndexError comes from our own group lookup and says nothing the message does not
        with pytest.raises(AssertionError) as exc_info:
            assert_that("abc").extracting_group(r"(a)", 9)
        assert_that(exc_info.value.__suppress_context__).is_true()

    def test_error_suppresses_only_when_asked(self):
        for suppress, expected in ((True, True), (False, False)):
            with pytest.raises(AssertionError) as exc_info:
                try:
                    raise ValueError("plumbing")
                except ValueError:
                    assert_that("v").error("boom", suppress_context=suppress)
            assert_that(exc_info.value.__suppress_context__).is_equal_to(expected)
