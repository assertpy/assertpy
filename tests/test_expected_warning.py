import logging
import warnings
from functools import partial
from io import StringIO

import pytest

from assertpy import WarningLoggingAdapter, assert_that, assert_warn, soft_assertions

_calls = []


def warn_deprecation(*args, **kwargs):
    warnings.warn("deprecated since 2.6", DeprecationWarning, stacklevel=2)


def warn_user(*args, **kwargs):
    warnings.warn("user warning", UserWarning, stacklevel=2)


def no_warn(*args, **kwargs):
    pass


def warn_then_raise():
    warnings.warn("before boom", UserWarning, stacklevel=2)
    raise RuntimeError("boom")


def warn_with_args(arg1, arg2, *, keyword):
    _calls.append((arg1, arg2, keyword))
    warnings.warn("args ok", UserWarning, stacklevel=2)


def test_warns_success():
    assert_that(warn_deprecation).warns(DeprecationWarning).when_called_with()


def test_warns_default_matches_any_warning():
    assert_that(warn_user).warns().when_called_with()


def test_warns_matches_subclass():
    assert_that(warn_deprecation).warns(Warning).when_called_with()


def test_warns_chains_on_message():
    assert_that(warn_deprecation).warns(DeprecationWarning).when_called_with().is_equal_to("deprecated since 2.6")
    assert_that(warn_deprecation).warns(DeprecationWarning).when_called_with().matches(r"since 2\.6")


def test_warns_passes_args_and_kwargs():
    _calls.clear()
    assert_that(warn_with_args).warns(UserWarning).when_called_with("a", "b", keyword="c")
    assert_that(_calls).is_equal_to([("a", "b", "c")])


def test_warns_failure_no_warning():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(no_warn).warns(DeprecationWarning).when_called_with()
    assert_that(str(exc_info.value)).is_equal_to("Expected <no_warn> to warn <DeprecationWarning> when called with ().")


def test_warns_failure_wrong_category():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(warn_user).warns(DeprecationWarning).when_called_with()
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <warn_user> to warn <DeprecationWarning> when called with (), but warned <UserWarning>."
    )


def test_warns_val_not_callable():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123).warns(UserWarning)
    assert_that(str(exc_info.value)).contains("val must be callable")


def test_warns_arg_not_a_warning():
    with pytest.raises(TypeError) as exc_info:
        assert_that(no_warn).warns(ValueError)
    assert_that(str(exc_info.value)).contains("given warning arg must be a warning type")


def test_does_not_warn_success():
    assert_that(no_warn).does_not_warn(DeprecationWarning).when_called_with()


def test_does_not_warn_other_category_is_ignored():
    assert_that(warn_user).does_not_warn(DeprecationWarning).when_called_with()


def test_does_not_warn_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(warn_user).does_not_warn(UserWarning).when_called_with()
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <warn_user> to not warn <UserWarning> when called with (), but did warn <UserWarning>."
    )


def test_warns_bypasses_show_once_dedup():
    # without simplefilter("always") the second identical warning would be swallowed by __warningregistry__
    assert_that(warn_user).warns(UserWarning).when_called_with()
    assert_that(warn_user).warns(UserWarning).when_called_with()


def test_warns_captures_under_filterwarnings_error():
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert_that(warn_user).warns(UserWarning).when_called_with()


def test_warns_propagates_exception_from_callable():
    with pytest.raises(RuntimeError) as exc_info:
        assert_that(warn_then_raise).warns(UserWarning).when_called_with()
    assert_that(str(exc_info.value)).is_equal_to("boom")


def test_warns_in_soft_assertions_collects():
    with pytest.raises(AssertionError) as exc_info:  # noqa: SIM117  # nested with is clearer than a combined one here
        with soft_assertions():
            assert_that(no_warn).warns(DeprecationWarning).when_called_with()
            assert_that(1).is_equal_to(2)
    message = str(exc_info.value)
    assert_that(message).contains("Expected <no_warn> to warn <DeprecationWarning>")
    assert_that(message).contains("Expected <1> to be equal to <2>")


def test_warns_in_warn_mode_logs():
    capture = StringIO()
    logger = logging.getLogger("capture_warns")
    handler = logging.StreamHandler(capture)
    logger.addHandler(handler)
    adapted = WarningLoggingAdapter(logger, None)

    assert_warn(no_warn, logger=adapted).warns(DeprecationWarning).when_called_with()

    out = capture.getvalue()
    capture.close()
    assert_that(out).contains("Expected <no_warn> to warn <DeprecationWarning> when called with ().")


def test_warns_wrong_category_in_warn_mode_logs():
    capture = StringIO()
    logger = logging.getLogger("capture_warns_wrong")
    handler = logging.StreamHandler(capture)
    logger.addHandler(handler)
    adapted = WarningLoggingAdapter(logger, None)

    assert_warn(warn_user, logger=adapted).warns(DeprecationWarning).when_called_with()

    out = capture.getvalue()
    capture.close()
    assert_that(out).contains(
        "Expected <warn_user> to warn <DeprecationWarning> when called with (), but warned <UserWarning>."
    )


def test_does_not_warn_failure_in_warn_mode_logs():
    capture = StringIO()
    logger = logging.getLogger("capture_does_not_warn")
    handler = logging.StreamHandler(capture)
    logger.addHandler(handler)
    adapted = WarningLoggingAdapter(logger, None)

    assert_warn(warn_user, logger=adapted).does_not_warn(UserWarning).when_called_with()

    out = capture.getvalue()
    capture.close()
    assert_that(out).contains(
        "Expected <warn_user> to not warn <UserWarning> when called with (), but did warn <UserWarning>."
    )


def warn_and_return_list(*args, **kwargs):
    warnings.warn("dep since 2.7", DeprecationWarning, stacklevel=2)
    return [1, 2, 3]


def quiet_return_ok(*args, **kwargs):
    return "ok"


def test_warns_returned_pivots_to_return_value():
    assert_that(warn_and_return_list).warns(DeprecationWarning).when_called_with().returned().is_equal_to([1, 2, 3])


def test_warns_returned_after_message_assertion():
    assert_that(warn_and_return_list).warns(DeprecationWarning).when_called_with().matches(
        "since 2.7"
    ).returned().is_equal_to([1, 2, 3])


def test_does_not_warn_returned_pivots_to_return_value():
    assert_that(quiet_return_ok).does_not_warn(DeprecationWarning).when_called_with().returned().is_equal_to("ok")


def test_does_not_warn_hands_the_call_its_arguments():
    assert_that(lambda first, *, second: first + second).does_not_warn(UserWarning).when_called_with(
        1, second=2
    ).returned().is_equal_to(3)


@pytest.mark.parametrize(
    ("call", "reason"),
    [
        (lambda: assert_that(no_warn).warns(UserWarning).when_called_with(), "to warn <UserWarning>"),
        (lambda: assert_that(warn_user).warns(DeprecationWarning).when_called_with(), "but warned <UserWarning>"),
        (lambda: assert_that(warn_user).does_not_warn(UserWarning).when_called_with(), "but did warn <UserWarning>"),
    ],
    ids=["warned-nothing", "warned-another-category", "warned-what-it-must-not"],
)
def test_a_soft_warning_failure_leaves_a_chain_that_names_it(call, reason):
    """The chain after it went on without the reason, so a `check()` there failed with an empty message."""
    with pytest.raises(AssertionError), soft_assertions():
        verdict = call().check().is_equal_to("anything")
    assert_that(verdict.passed).is_false()
    assert_that(verdict.message).contains(reason)


def test_the_warning_message_keeps_what_the_chain_was_given():
    capture = StringIO()
    logger = logging.getLogger("capture_warning_message")
    logger.addHandler(logging.StreamHandler(capture))
    adapted = WarningLoggingAdapter(logger, None)

    assert_warn(warn_user, "noisy", logger=adapted).warns(UserWarning).when_called_with().is_equal_to("other")

    assert_that(capture.getvalue()).contains("[noisy] Expected <user warning> to be equal to <other>")


def test_warns_partial_without_name_fails_cleanly():
    # a callable lacking __name__ (functools.partial) must fail cleanly, not raise AttributeError
    def emit(level):
        if level > 5:
            warnings.warn("hi", UserWarning, stacklevel=2)

    with pytest.raises(AssertionError):
        assert_that(partial(emit, 3)).warns(UserWarning).when_called_with()
    with pytest.raises(AssertionError):
        assert_that(partial(emit, 9)).does_not_warn(UserWarning).when_called_with()


def test_custom_logger_survives_collection_transform():
    # a transform must forward the caller's logger, or a later warning goes to the library default
    capture = StringIO()
    logger = logging.getLogger("test_transform_logger")
    logger.addHandler(logging.StreamHandler(capture))
    adapted = WarningLoggingAdapter(logger, None)

    assert_warn([1, -2, 3], logger=adapted).filtered_on(lambda item: item > 0).contains(999)
    assert_that(capture.getvalue()).contains("to contain")


class TestSeveralCategoriesAnyOneOfWhichWillDo:
    @pytest.mark.parametrize(
        "named",
        [(UserWarning, DeprecationWarning), UserWarning | DeprecationWarning, (RuntimeWarning, (DeprecationWarning,))],
        ids=["tuple", "union", "nested"],
    )
    def test_a_warning_of_any_of_them_is_caught(self, named):
        assert_that(warn_deprecation).warns(named).when_called_with().is_equal_to("deprecated since 2.6")

    def test_none_of_them_warned_names_them_all(self):
        with pytest.raises(AssertionError) as failure:
            assert_that(warn_user).warns((DeprecationWarning, RuntimeWarning)).when_called_with()
        assert_that(str(failure.value)).starts_with(
            "Expected <warn_user> to warn <DeprecationWarning, RuntimeWarning> when called with (),"
            " but warned <UserWarning>."
        )

    def test_does_not_warn_any_of_them(self):
        assert_that(warn_user).does_not_warn((DeprecationWarning, RuntimeWarning)).when_called_with()
        with pytest.raises(AssertionError) as failure:
            assert_that(warn_user).does_not_warn(DeprecationWarning | UserWarning).when_called_with()
        assert_that(str(failure.value)).starts_with(
            "Expected <warn_user> to not warn <DeprecationWarning | UserWarning> when called with (), but did warn"
            " <UserWarning>."
        )

    @pytest.mark.parametrize(
        "wrong", [(), (UserWarning, ValueError), UserWarning | int], ids=["empty", "an-error", "int"]
    )
    def test_every_member_has_to_be_a_warning(self, wrong):
        with pytest.raises(TypeError) as refusal:
            assert_that(warn_user).warns(wrong)
        assert_that(str(refusal.value)).starts_with(
            "given warning arg must be a warning type, or a union or a non-empty tuple of them, but was <"
        )
