import asyncio
import logging
from dataclasses import replace
from functools import partial
from io import StringIO

import pytest

from assertpy import (
    WarningLoggingAdapter,
    add_extension,
    assert_that,
    assert_warn,
    remove_extension,
    soft_assertions,
)
from tests.group_compat import BaseExceptionGroup as _BaseExceptionGroup
from tests.group_compat import ExceptionGroup as _ExceptionGroup
from tests.group_compat import needs_groups


def test_expected_exception():
    assert_that(func_no_arg).raises(RuntimeError).when_called_with()
    assert_that(func_one_arg).raises(RuntimeError).when_called_with("foo")
    assert_that(func_multi_args).raises(RuntimeError).when_called_with("foo", "bar", "baz")
    assert_that(func_kwargs).raises(RuntimeError).when_called_with(foo=1, bar=2, baz=3)
    assert_that(func_all).raises(RuntimeError).when_called_with("a", "b", 3, 4, foo=1, bar=2, baz="dog")


def test_expected_exception_method():
    foo = Foo()
    assert_that(foo.bar).raises(RuntimeError).when_called_with().is_equal_to("method err")


def test_expected_exception_chaining():
    assert_that(func_no_arg).raises(RuntimeError).when_called_with().is_equal_to("no arg err")
    assert_that(func_one_arg).raises(RuntimeError).when_called_with("foo").is_equal_to("one arg err")
    assert_that(func_multi_args).raises(RuntimeError).when_called_with("foo", "bar", "baz").is_equal_to(
        "multi args err"
    )
    assert_that(func_kwargs).raises(RuntimeError).when_called_with(foo=1, bar=2, baz=3).is_equal_to("kwargs err")
    assert_that(func_all).raises(RuntimeError).when_called_with("a", "b", 3, 4, foo=1, bar=2, baz="dog").starts_with(
        "all err: arg1=a, arg2=b, args=(3, 4), kwargs=["
    )


def test_expected_exception_no_arg_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(func_noop).raises(RuntimeError).when_called_with()
    assert_that(str(exc_info.value)).is_equal_to("Expected <func_noop> to raise <RuntimeError> when called with ().")


def test_expected_exception_no_arg_bad_func_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123).raises(int).when_called_with()
    assert_that(str(exc_info.value)).contains("val must be callable")


def test_expected_exception_no_arg_bad_exception_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(func_noop).raises(int).when_called_with()
    assert_that(str(exc_info.value)).contains("given exception arg must be an exception type")


def test_expected_exception_no_arg_wrong_exception_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(func_no_arg).raises(TypeError).when_called_with()
    assert_that(str(exc_info.value)).contains(
        "Expected <func_no_arg> to raise <TypeError> when called with (), but raised <RuntimeError>."
    )


@pytest.mark.parametrize("wrong", [42, ValueError("instance")])
def test_expectation_that_is_not_a_class_is_refused(wrong):
    # `issubclass()` names no assertion, so a non-class read as "issubclass() arg 1 must be a class"
    with pytest.raises(TypeError, match="must be an exception type"):
        assert_that(func_noop).raises(wrong)
    with pytest.raises(TypeError, match="must be an exception type"):
        assert_that(func_noop).does_not_raise(wrong)


def test_expected_exception_no_arg_missing_raises_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(func_noop).when_called_with()
    assert_that(str(exc_info.value)).contains("no expectation set")


def test_expected_exception_one_arg_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(func_noop).raises(RuntimeError).when_called_with("foo")
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <func_noop> to raise <RuntimeError> when called with ('foo')."
    )


def test_expected_exception_multi_args_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(func_noop).raises(RuntimeError).when_called_with("foo", "bar", "baz")
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <func_noop> to raise <RuntimeError> when called with ('foo', 'bar', 'baz')."
    )


def test_expected_exception_kwargs_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(func_noop).raises(RuntimeError).when_called_with(foo=1, bar=2, baz=3)
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <func_noop> to raise <RuntimeError> when called with ('bar': 2, 'baz': 3, 'foo': 1)."
    )


def test_expected_exception_all_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(func_noop).raises(RuntimeError).when_called_with("a", "b", 3, 4, foo=1, bar=2, baz="dog")
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <func_noop> to raise <RuntimeError> when called with "
        "('a', 'b', 3, 4, 'bar': 2, 'baz': 'dog', 'foo': 1)."
    )


def test_expected_exception_arg_passing():
    assert_that(func_all).raises(RuntimeError).when_called_with("a", "b", 3, 4, foo=1, bar=2, baz="dog").is_equal_to(
        "all err: arg1=a, arg2=b, args=(3, 4), kwargs=[('bar', 2), ('baz', 'dog'), ('foo', 1)]"
    )


def func_noop(*args, **kwargs):
    pass


def func_no_arg():
    raise RuntimeError("no arg err")


def func_one_arg(arg):
    raise RuntimeError("one arg err")


def func_multi_args(*args):
    raise RuntimeError("multi args err")


def func_kwargs(**kwargs):
    raise RuntimeError("kwargs err")


def func_all(arg1, arg2, *args, **kwargs):
    raise RuntimeError(
        f"all err: arg1={arg1}, arg2={arg2}, args={args}, "
        f"kwargs={[(key, kwargs[key]) for key in sorted(kwargs.keys())]}"
    )


def test_expected_exception_warn_preserves_logger():
    capture = StringIO()
    logger = logging.getLogger("capture_exc")
    handler = logging.StreamHandler(capture)
    logger.addHandler(handler)
    adapted = WarningLoggingAdapter(logger, None)

    assert_warn(func_no_arg, logger=adapted).raises(RuntimeError).when_called_with().is_equal_to("wrong msg")

    out = capture.getvalue()
    capture.close()

    assert_that(out).contains("Expected <no arg err> to be equal to <wrong msg>, but was not.")


def test_expected_exception_warn_wrong_type_preserves_logger():
    capture = StringIO()
    logger = logging.getLogger("capture_exc2")
    handler = logging.StreamHandler(capture)
    logger.addHandler(handler)
    adapted = WarningLoggingAdapter(logger, None)

    assert_warn(func_no_arg, logger=adapted).raises(ValueError).when_called_with()

    out = capture.getvalue()
    capture.close()

    assert_that(out).contains("Expected <func_no_arg> to raise <ValueError>")


class Foo:
    def bar(self):
        raise RuntimeError("method err")


def safe_add(value):
    return value + 1


def test_does_not_raise_returned_pivots_to_return_value():
    assert_that(safe_add).does_not_raise(ValueError).when_called_with(41).returned().is_equal_to(42)


def test_does_not_raise_hands_the_call_its_keywords():
    assert_that(lambda first, *, second: first + second).does_not_raise(ValueError).when_called_with(
        1, second=2
    ).returned().is_equal_to(3)


@pytest.mark.parametrize(
    ("call", "reason"),
    [
        (lambda: assert_that(func_noop).raises(ValueError).when_called_with(), "to raise <ValueError>"),
        (lambda: assert_that(func_no_arg).does_not_raise(RuntimeError).when_called_with(), "but did raise"),
    ],
    ids=["raised-nothing", "raised-what-it-must-not"],
)
def test_a_soft_call_failure_leaves_a_chain_that_names_it(call, reason):
    with pytest.raises(AssertionError), soft_assertions():
        verdict = call().check().is_equal_to("anything")
    assert_that(verdict.passed).is_false()
    assert_that(verdict.message).contains(reason)


def test_returned_without_return_value_fails():
    with pytest.raises(TypeError) as exc_info:
        assert_that(func_no_arg).raises(RuntimeError).when_called_with().returned()
    assert_that(str(exc_info.value)).contains("no return value captured")


class TestDoesNotRaise:
    def test_no_exception(self):
        def safe_func(x):
            return x + 1

        assert_that(safe_func).does_not_raise(ValueError).when_called_with(1)

    def test_different_exception(self):
        def raises_type_error():
            raise TypeError("oops")

        assert_that(raises_type_error).does_not_raise(ValueError).when_called_with()

    def test_raises_expected_failure(self):
        def raises_value_error():
            raise ValueError("bad value")

        with pytest.raises(AssertionError) as exc_info:
            assert_that(raises_value_error).does_not_raise(ValueError).when_called_with()
        assert_that(str(exc_info.value)).contains("to not raise <ValueError>")
        assert_that(str(exc_info.value)).contains("but did raise")

    def test_raises_subclass_failure(self):
        def raises_file_not_found():
            raise FileNotFoundError("missing")

        with pytest.raises(AssertionError) as exc_info:
            assert_that(raises_file_not_found).does_not_raise(OSError).when_called_with()
        assert_that(str(exc_info.value)).contains("to not raise <OSError>")

    def test_not_callable_failure(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that(42).does_not_raise(ValueError)
        assert_that(str(exc_info.value)).is_equal_to("val must be callable, but was <42> (int)")

    def test_not_exception_failure(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that(lambda: None).does_not_raise(str)
        assert_that(str(exc_info.value)).is_equal_to(
            "given exception arg must be an exception type, or a union or a non-empty tuple of them,"
            " but was <<class 'str'>> (type)"
        )

    def test_raises_expected_soft_mode(self):
        def raises_value_error():
            raise ValueError("bad value")

        with pytest.raises(AssertionError) as exc_info, soft_assertions():
            assert_that(raises_value_error).does_not_raise(ValueError).when_called_with()
        assert_that(str(exc_info.value)).contains("to not raise <ValueError>")


class _ConfigError(Exception):
    def __init__(self, message, code):
        super().__init__(message)
        self.code = code


def _raise_config():
    raise _ConfigError("bad config", 42)


def _raise_wrapped_from():
    try:
        raise KeyError("missing")
    except KeyError as exc:
        raise ValueError("wrapped") from exc


def _raise_during_handling():
    try:
        raise ZeroDivisionError
    except ZeroDivisionError:
        raise RuntimeError("during handling")  # noqa: B904  # intentional implicit __context__ (no `from`)


def _raise_suppressed():
    try:
        raise ZeroDivisionError
    except ZeroDivisionError:
        raise ValueError("clean") from None


def _raise_deep_chain():
    try:
        try:
            raise KeyError("root")
        except KeyError as exc:
            raise TimeoutError("middle") from exc
    except TimeoutError as exc:
        raise ValueError("top") from exc


def _raise_group():
    raise _ExceptionGroup("boom", [ValueError("v"), KeyError("k")])


def _raise_nested_group():
    raise _ExceptionGroup("boom", [ValueError("v"), _ExceptionGroup("inner", [TypeError("deep")])])


class TestRaisedPivot:
    def test_pivots_to_exception_object(self):
        err = assert_that(_raise_config).raises(_ConfigError).when_called_with().raised().value
        assert_that(err.code).is_equal_to(42)

    def test_raised_object_supports_core_assertions(self):
        assert_that(_raise_config).raises(_ConfigError).when_called_with().raised().is_instance_of(_ConfigError)

    def test_raised_without_capture_fails(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that(_raise_config).raised()
        assert_that(str(exc_info.value)).contains("no exception captured")

    @pytest.mark.parametrize(
        ("chain", "typed_as", "caught"),
        [
            (lambda: assert_that(_raise_config).raises(Exception).when_called_with(), Exception, _ConfigError),
            (lambda: assert_that(_raise_wrapped_from).raises(ValueError).when_called_with(), ValueError, ValueError),
            (
                lambda: assert_that(_raise_wrapped_from).raises(ValueError).when_called_with().caused_by(LookupError),
                LookupError,
                KeyError,
            ),
            (
                lambda: assert_that(_raise_deep_chain).raises(ValueError).when_called_with().has_root_cause(KeyError),
                KeyError,
                KeyError,
            ),
            (
                lambda: assert_that(_raise_wrapped_from).raises(ValueError).when_called_with().not_.caused_by(OSError),
                ValueError,
                ValueError,
            ),
            (
                lambda: assert_that(_raise_deep_chain).raises(ValueError).when_called_with().contains("top"),
                ValueError,
                ValueError,
            ),
        ],
        ids=["a-subclass", "as-named", "a-cause", "the-root", "a-negated-pivot", "after-text"],
    )
    def test_what_it_hands_back_is_what_the_type_names(self, chain, typed_as, caught):
        """The declaration types `raised()` by the class `raises()` or the last pivot named."""
        assert_that(type(chain().raised().value)).is_same_as(caught).is_subclass_of(typed_as)

    @pytest.mark.parametrize("pivot", ["caused_by", "has_root_cause", "error_of"])
    def test_a_pivot_that_failed_softly_hands_back_no_exception(self, pivot):
        """The chain goes inert, and its `.value` refuses rather than hand back what the type does not name."""
        with pytest.raises(AssertionError), soft_assertions():
            chain = getattr(assert_that(_raise_wrapped_from).raises(ValueError).when_called_with(), pivot)(OSError)
            with pytest.raises(TypeError) as refusal:
                _ = chain.raised().value
        # read outside the block: a `match=` failing inside it is an AssertionError the outer `raises` swallows
        assert_that(str(refusal.value)).contains("cannot extract .value")

    @needs_groups
    def test_a_member_of_a_group_is_what_the_type_names(self):
        chain = assert_that(_raise_nested_group).raises(_ExceptionGroup).when_called_with()
        assert_that(chain.error_of(TypeError).raised().value).is_instance_of(TypeError)
        assert_that(chain.not_.error_of(OSError).raised().value).is_instance_of(_ExceptionGroup)


class TestCausedBy:
    def test_explicit_cause(self):
        assert_that(_raise_wrapped_from).raises(ValueError).when_called_with().caused_by(KeyError)

    def test_implicit_context_cause(self):
        assert_that(_raise_during_handling).raises(RuntimeError).when_called_with().caused_by(ZeroDivisionError)

    def test_pivots_to_cause_message(self):
        chain = assert_that(_raise_wrapped_from).raises(ValueError).when_called_with().caused_by(KeyError)
        chain.is_equal_to("'missing'")

    def test_wrong_cause_fails(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that(_raise_wrapped_from).raises(ValueError).when_called_with().caused_by(TypeError)
        assert_that(str(exc_info.value)).contains("to be caused by <TypeError>").contains("<KeyError>")

    def test_no_cause_fails(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that(_raise_config).raises(_ConfigError).when_called_with().caused_by(KeyError)
        assert_that(str(exc_info.value)).contains("the cause was no cause")

    def test_suppressed_context_has_no_cause(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that(_raise_suppressed).raises(ValueError).when_called_with().caused_by(ZeroDivisionError)
        assert_that(str(exc_info.value)).contains("the cause was no cause")

    def test_wrong_cause_soft_collects(self):
        with pytest.raises(AssertionError) as exc_info, soft_assertions():
            assert_that(_raise_wrapped_from).raises(ValueError).when_called_with().caused_by(TypeError)
        assert_that(str(exc_info.value)).contains("to be caused by <TypeError>")

    def test_pivot_carries_the_cause_object(self):
        chain = assert_that(_raise_wrapped_from).raises(ValueError).when_called_with().caused_by(KeyError)
        chain.raised().is_instance_of(KeyError)

    def test_caused_by_without_capture_fails(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that(_raise_config).caused_by(KeyError)
        assert_that(str(exc_info.value)).contains("no exception captured")


class TestACauseMayBeOneOfSeveral:
    """The cause is read with `isinstance`, so a union or a tuple of classes is what it takes."""

    @pytest.mark.parametrize("pivot", ["caused_by", "has_root_cause"])
    @pytest.mark.parametrize(
        "expected",
        [KeyError | OSError, (KeyError, OSError), ((OSError,), (KeyError | TypeError,))],
        ids=["union", "tuple", "nested"],
    )
    def test_one_of_them_holds(self, pivot, expected):
        chain = assert_that(_raise_wrapped_from).raises(ValueError).when_called_with()
        assert_that(getattr(chain, pivot)(expected).raised().value).is_instance_of(KeyError)

    @pytest.mark.parametrize(
        ("pivot", "words"), [("caused_by", "to be caused by"), ("has_root_cause", "to have root cause")]
    )
    @pytest.mark.parametrize(
        ("expected", "named"),
        [
            (TypeError | OSError, "TypeError | OSError"),
            ((TypeError, OSError), "TypeError, OSError"),
            ((TypeError, (OSError | ArithmeticError,)), "TypeError, OSError | ArithmeticError"),
        ],
        ids=["union", "tuple", "nested"],
    )
    def test_none_of_them_fails_naming_all_of_them(self, pivot, words, expected, named):
        chain = assert_that(_raise_wrapped_from).raises(ValueError).when_called_with()
        with pytest.raises(AssertionError) as exc_info:
            getattr(chain, pivot)(expected)
        assert_that(str(exc_info.value)).contains(f"{words} <{named}>")

    @pytest.mark.parametrize("pivot", ["caused_by", "has_root_cause"])
    @pytest.mark.parametrize(
        "expected",
        [
            KeyError | list[str],
            list[str] | KeyError,
            OSError | list[str],
            (KeyError, list[str]),
            (list[str], KeyError),
            (OSError, (list[str],)),
            "KeyError",
        ],
        ids=[
            "union-first-matches",
            "union-generic-first",
            "union-none-match",
            "tuple-first-matches",
            "tuple-generic-first",
            "nested-none-match",
            "text",
        ],
    )
    def test_what_isinstance_cannot_take_is_refused_whichever_member_comes_first(self, pivot, expected):
        chain = assert_that(_raise_wrapped_from).raises(ValueError).when_called_with()
        with pytest.raises(TypeError, match="given exception arg must be a class"):
            getattr(chain, pivot)(expected)

    @pytest.mark.parametrize("pivot", ["caused_by", "has_root_cause"])
    def test_a_member_is_asked_only_about_the_cause_itself(self, pivot):
        class AsksOnlyForExceptions(type):
            def __instancecheck__(cls, instance):
                return bool(instance.args)

        class WithArguments(metaclass=AsksOnlyForExceptions):
            pass

        chain = assert_that(_raise_wrapped_from).raises(ValueError).when_called_with()
        assert_that(getattr(chain, pivot)((TypeError, WithArguments)).raised().value).is_instance_of(KeyError)

    def test_a_group_member_is_still_asked_for_by_one_class(self):
        with pytest.raises(TypeError, match="must be an exception type"):
            assert_that(_raise_group).raises(_ExceptionGroup).when_called_with().error_of(KeyError | OSError)


_PIVOTS = {
    "caused_by": lambda chain: chain.caused_by(KeyError),
    "has_root_cause": lambda chain: chain.has_root_cause(KeyError),
    "raised": lambda chain: chain.raised(),
}


class TestWhatAPivotCarries:
    """A pivot hands on the chain's description and mode, and a failed one says what it was asked."""

    @pytest.mark.parametrize("pivot", list(_PIVOTS))
    def test_what_it_hands_on_keeps_the_description(self, pivot):
        chain = assert_that(_raise_wrapped_from, "saving a row").raises(ValueError).when_called_with()
        with pytest.raises(AssertionError) as exc_info:
            _PIVOTS[pivot](chain).is_equal_to("other")
        assert_that(str(exc_info.value)).starts_with("[saving a row] Expected <").contains("to be equal to <other>")

    @pytest.mark.parametrize("pivot", list(_PIVOTS))
    def test_what_it_hands_on_is_still_collected_under_soft_assertions(self, pivot):
        with pytest.raises(AssertionError) as exc_info, soft_assertions():
            _PIVOTS[pivot](assert_that(_raise_wrapped_from).raises(ValueError).when_called_with()).is_equal_to("other")
            assert_that(1).is_equal_to(2)
        assert_that(str(exc_info.value)).contains("to be equal to <other>").contains("Expected <1> to be equal to <2>")

    @pytest.mark.parametrize("pivot", list(_PIVOTS))
    def test_what_it_hands_on_warns_to_the_same_logger(self, pivot):
        capture = StringIO()
        logger = logging.getLogger(f"what_a_pivot_carries_{pivot}")
        handler = logging.StreamHandler(capture)
        logger.addHandler(handler)
        try:
            chain = assert_warn(_raise_wrapped_from, logger=WarningLoggingAdapter(logger, None))
            _PIVOTS[pivot](chain.raises(ValueError).when_called_with()).is_equal_to("other")
        finally:
            logger.removeHandler(handler)
        assert_that(capture.getvalue()).contains("to be equal to <other>")

    @pytest.mark.parametrize(
        ("pivot", "words"), [("caused_by", "to be caused by"), ("has_root_cause", "to have root cause")]
    )
    def test_a_failure_names_the_caught_exception(self, pivot, words):
        chain = assert_that(_raise_wrapped_from).raises(ValueError).when_called_with()
        with pytest.raises(AssertionError) as exc_info:
            getattr(chain, pivot)(TypeError | OSError)
        assert_that(str(exc_info.value)).starts_with(f"Expected <ValueError> {words} <TypeError | OSError>")

    @pytest.mark.parametrize("pivot", ["caused_by", "has_root_cause"])
    def test_without_a_capture_the_refusal_names_the_pivot(self, pivot):
        with pytest.raises(TypeError, match=rf"no exception captured; {pivot}\(\) is only valid after"):
            getattr(assert_that(_raise_wrapped_from), pivot)(KeyError)

    @pytest.mark.parametrize(
        ("pivot", "words"), [("caused_by", "to be caused by"), ("has_root_cause", "to have root cause")]
    )
    def test_a_pivot_that_failed_softly_says_why_it_holds_no_value(self, pivot, words):
        with pytest.raises(AssertionError), soft_assertions():
            chain = getattr(assert_that(_raise_wrapped_from).raises(ValueError).when_called_with(), pivot)(OSError)
            with pytest.raises(TypeError) as refusal:
                _ = chain.value
        assert_that(str(refusal.value)).contains(f"soft or warn mode - Expected <ValueError> {words} <OSError>")


class TestHasRootCause:
    def test_single_level_root(self):
        assert_that(_raise_wrapped_from).raises(ValueError).when_called_with().has_root_cause(KeyError)

    def test_deep_chain_root(self):
        assert_that(_raise_deep_chain).raises(ValueError).when_called_with().has_root_cause(KeyError)

    def test_pivots_to_root_message(self):
        chain = assert_that(_raise_deep_chain).raises(ValueError).when_called_with().has_root_cause(KeyError)
        chain.is_equal_to("'root'")

    def test_wrong_root_fails(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that(_raise_deep_chain).raises(ValueError).when_called_with().has_root_cause(TypeError)
        assert_that(str(exc_info.value)).contains("root cause <TypeError>").contains("<KeyError>")

    def test_wrong_root_soft_collects(self):
        with pytest.raises(AssertionError) as exc_info, soft_assertions():
            assert_that(_raise_deep_chain).raises(ValueError).when_called_with().has_root_cause(TypeError)
        assert_that(str(exc_info.value)).contains("root cause")

    def test_cyclic_cause_chain_terminates(self):
        first = ValueError("a")
        second = KeyError("b")
        first.__cause__ = second
        second.__cause__ = first

        def raise_cyclic():
            raise first

        assert_that(raise_cyclic).raises(ValueError).when_called_with().has_root_cause(KeyError)

    def test_cycle_not_returning_to_head_terminates(self):
        head = ValueError("head")
        mid = KeyError("mid")
        tail = TypeError("tail")
        head.__cause__ = mid
        mid.__cause__ = tail
        tail.__cause__ = mid

        def raise_head():
            raise head

        assert_that(raise_head).raises(ValueError).when_called_with().has_root_cause(TypeError)

    def test_pivot_carries_the_root_object(self):
        chain = assert_that(_raise_deep_chain).raises(ValueError).when_called_with().has_root_cause(KeyError)
        chain.raised().is_instance_of(KeyError)


@needs_groups
class TestContainsError:
    def test_group_contains_all(self):
        assert_that(_raise_group).raises(_ExceptionGroup).when_called_with().contains_error(ValueError, KeyError)

    def test_group_missing_type_fails(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that(_raise_group).raises(_ExceptionGroup).when_called_with().contains_error(TypeError)
        assert_that(str(exc_info.value)).contains("to contain <TypeError>")

    def test_not_a_group_fails(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that(_raise_config).raises(_ConfigError).when_called_with().contains_error(ValueError)
        assert_that(str(exc_info.value)).contains("to be an exception group")

    def test_missing_type_soft_collects(self):
        with pytest.raises(AssertionError) as exc_info, soft_assertions():
            assert_that(_raise_group).raises(_ExceptionGroup).when_called_with().contains_error(TypeError)
        assert_that(str(exc_info.value)).contains("to contain <TypeError>")

    def test_not_a_group_soft_collects(self):
        with pytest.raises(AssertionError) as exc_info, soft_assertions():
            assert_that(_raise_config).raises(_ConfigError).when_called_with().contains_error(ValueError)
        assert_that(str(exc_info.value)).contains("to be an exception group")


@needs_groups
class TestGroupPivots:
    def test_errors_yields_the_leaves(self):
        # the types in order: a length alone would hold if the view kept the group and dropped a leaf
        caught = assert_that(_raise_group).raises(_ExceptionGroup).when_called_with()
        assert_that([type(leaf) for leaf in caught.errors().value]).is_equal_to([ValueError, KeyError])

    def test_errors_flattens_nesting(self):
        caught = assert_that(_raise_nested_group).raises(_ExceptionGroup).when_called_with()
        assert_that([type(leaf) for leaf in caught.errors().value]).is_equal_to([ValueError, TypeError])
        caught.errors().extracting("args").is_equal_to([("v",), ("deep",)])

    def test_errors_reaches_collection_assertions(self):
        caught = assert_that(_raise_group).raises(_ExceptionGroup).when_called_with()
        caught.errors().extracting("args").contains(("v",), ("k",))

    def test_errors_on_a_plain_exception_fails(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that(_raise_config).raises(_ConfigError).when_called_with().errors()
        assert_that(str(exc_info.value)).contains("to be an exception group")

    def test_error_of_pivots_to_that_message(self):
        assert_that(_raise_group).raises(_ExceptionGroup).when_called_with().error_of(KeyError).contains("k")

    def test_error_of_reaches_into_nesting(self):
        caught = assert_that(_raise_nested_group).raises(_ExceptionGroup).when_called_with()
        caught.error_of(TypeError).contains("deep")

    def test_error_of_carries_the_object(self):
        caught = assert_that(_raise_group).raises(_ExceptionGroup).when_called_with()
        caught.error_of(KeyError).raised().is_instance_of(KeyError)

    def test_error_of_missing_type_fails(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that(_raise_group).raises(_ExceptionGroup).when_called_with().error_of(TypeError)
        assert_that(str(exc_info.value)).contains("to contain <TypeError>")

    def test_error_of_on_a_plain_exception_fails(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that(_raise_config).raises(_ConfigError).when_called_with().error_of(ValueError)
        assert_that(str(exc_info.value)).contains("to be an exception group")

    def test_does_not_contain_error_passes(self):
        assert_that(_raise_group).raises(_ExceptionGroup).when_called_with().does_not_contain_error(TypeError)

    def test_does_not_contain_error_present_fails(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that(_raise_group).raises(_ExceptionGroup).when_called_with().does_not_contain_error(ValueError)
        assert_that(str(exc_info.value)).contains("to not contain <ValueError>")

    def test_does_not_contain_error_on_a_plain_exception_fails(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that(_raise_config).raises(_ConfigError).when_called_with().does_not_contain_error(ValueError)
        assert_that(str(exc_info.value)).contains("to be an exception group")

    def test_soft_collects_every_group_failure(self):
        with pytest.raises(AssertionError) as exc_info, soft_assertions():
            assert_that(_raise_group).raises(_ExceptionGroup).when_called_with().error_of(TypeError)
            assert_that(_raise_group).raises(_ExceptionGroup).when_called_with().does_not_contain_error(ValueError)
            assert_that(_raise_config).raises(_ConfigError).when_called_with().errors()
        collected = str(exc_info.value)
        assert_that(collected).contains("to contain <TypeError>", "to not contain <ValueError>")
        assert_that(collected).contains("to be an exception group")

    def test_the_leaves_view_does_not_carry_the_exception(self):
        # `_ListAssertion` declares no `raised()`, so the runtime must not offer one: the hole closes both ways
        caught = assert_that(_raise_group).raises(_ExceptionGroup).when_called_with()
        with pytest.raises(TypeError, match="no exception captured"):
            caught.errors().raised()

    def test_a_pivot_without_a_caught_exception_names_itself(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that(lambda: 1).does_not_raise(ValueError).when_called_with().errors()
        assert_that(str(exc_info.value)).contains("errors() is only valid after")

    def test_an_empty_call_is_refused_by_both_forms(self):
        # these two used to pass on a call with nothing to look for, which is the failure mode itself
        caught = assert_that(_raise_group).raises(_ExceptionGroup).when_called_with()
        with pytest.raises(ValueError, match="one or more args"):
            caught.contains_error()
        with pytest.raises(ValueError, match="one or more args"):
            caught.does_not_contain_error()

    def test_a_deeply_nested_group_is_still_answered(self):
        group = _ExceptionGroup("leaf", [ValueError("v")])
        for _ in range(3000):
            group = _ExceptionGroup("outer", [group])

        def raise_deep():
            raise group

        caught = assert_that(raise_deep).raises(_ExceptionGroup).when_called_with()
        caught.contains_error(ValueError)
        caught.error_of(ValueError).contains("v")
        caught.errors().is_length(1)

    def test_a_group_that_lies_about_its_own_members_is_answered_the_same_way(self):
        class _LyingGroup(_ExceptionGroup):
            def subgroup(self, condition):
                return None

        def raise_lying():
            raise _LyingGroup("boom", [ValueError("v")])

        caught = assert_that(raise_lying).raises(_LyingGroup).when_called_with()
        caught.contains_error(ValueError)
        caught.error_of(ValueError).contains("v")
        with pytest.raises(AssertionError):
            caught.does_not_contain_error(ValueError)

    @pytest.mark.parametrize("wrong", [str, 42, ValueError("instance"), (TypeError, int), ()])
    def test_anything_but_an_exception_type_is_refused(self, wrong):
        caught = assert_that(_raise_group).raises(_ExceptionGroup).when_called_with()
        for call in (caught.contains_error, caught.does_not_contain_error, caught.error_of):
            with pytest.raises(TypeError, match="must be an exception type"):
                call(wrong)

    def test_a_member_is_picked_by_one_class_where_several_are_any_of_them(self):
        caught = assert_that(_raise_group).raises(_ExceptionGroup).when_called_with()
        caught.contains_error((TypeError, KeyError))
        with pytest.raises(TypeError, match="must be an exception type"):
            caught.error_of((TypeError, KeyError))

    def test_a_group_type_reaches_the_group_itself_from_every_form(self):
        caught = assert_that(_raise_nested_group).raises(_ExceptionGroup).when_called_with()
        caught.contains_error(_ExceptionGroup)
        caught.error_of(_ExceptionGroup).contains("boom")
        with pytest.raises(AssertionError):
            caught.does_not_contain_error(_ExceptionGroup)

    def test_the_first_leaf_of_a_type_is_the_one_pivoted_to(self):
        first, second = ValueError("first"), ValueError("second")

        def raise_two():
            raise _ExceptionGroup("boom", [_ExceptionGroup("inner", [first]), second])

        caught = assert_that(raise_two).raises(_ExceptionGroup).when_called_with()
        assert caught.error_of(ValueError).raised().value is first

    def test_a_bare_base_exception_is_a_leaf_like_any_other(self):
        def raise_base():
            raise _BaseExceptionGroup("cancelled", [KeyboardInterrupt(), ValueError("v")])

        caught = assert_that(raise_base).raises(_BaseExceptionGroup).when_called_with()
        caught.errors().is_length(2)
        caught.contains_error(KeyboardInterrupt)
        caught.error_of(KeyboardInterrupt).raised().is_instance_of(KeyboardInterrupt)

    def test_soft_keeps_chaining_after_a_pivot_on_a_plain_exception(self):
        with pytest.raises(AssertionError) as exc_info, soft_assertions():
            assert_that(_raise_config).raises(_ConfigError).when_called_with().error_of(ValueError).contains("nope")
            assert_that(_raise_config).raises(_ConfigError).when_called_with().does_not_contain_error(ValueError)
        assert_that(str(exc_info.value)).contains("to be an exception group")


def test_raises_partial_without_name_fails_cleanly():
    def boom(x):
        if x > 5:
            raise ValueError("big")

    with pytest.raises(AssertionError):
        assert_that(partial(boom, 3)).raises(ValueError).when_called_with()
    with pytest.raises(AssertionError):
        assert_that(partial(boom, 9)).raises(KeyError).when_called_with()


class TestAnInterruptIsNotAMismatch:
    """Ctrl+C and ``sys.exit()`` belong to the runner, and both capture paths used to keep them."""

    @staticmethod
    def _interrupt():
        raise KeyboardInterrupt

    @staticmethod
    def _exit():
        raise SystemExit(3)

    def test_raises_lets_an_interrupt_through_instead_of_reporting_it(self):
        with pytest.raises(KeyboardInterrupt):
            assert_that(self._interrupt).raises(ValueError).when_called_with()

    def test_does_not_raise_lets_an_interrupt_through_instead_of_swallowing_it(self):
        with pytest.raises(KeyboardInterrupt):
            assert_that(self._interrupt).does_not_raise(ValueError).when_called_with()

    def test_an_exit_travels_the_same_way(self):
        with pytest.raises(SystemExit):
            assert_that(self._exit).does_not_raise(ValueError).when_called_with()

    def test_asking_for_one_by_name_still_catches_it(self):
        assert_that(self._interrupt).raises(KeyboardInterrupt).when_called_with()
        assert_that(self._exit).raises(SystemExit).when_called_with()

    def test_a_named_interrupt_that_does_arrive_is_still_refused_by_the_negative_form(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that(self._exit).does_not_raise(SystemExit).when_called_with()
        assert_that(str(exc_info.value)).contains("did raise <SystemExit>")

    def test_an_ordinary_mismatch_is_still_reported(self):
        def boom():
            raise TypeError("wrong one")

        with pytest.raises(AssertionError) as exc_info:
            assert_that(boom).raises(ValueError).when_called_with()
        assert_that(str(exc_info.value)).contains("but raised <TypeError>")


@needs_groups
class TestMatchesErrorTree:
    """The shape of the group, which `contains_error` deliberately says nothing about.

    That one searches the whole tree for a type, so a group that grew a third failure, or one whose
    members moved into a subgroup, still passes it. These read the tree.
    """

    def test_the_flat_shape_matches(self):
        assert_that(_raise_group).raises(_ExceptionGroup).when_called_with().matches_error_tree(ValueError, KeyError)

    def test_order_is_not_part_of_the_shape(self):
        """An `asyncio.TaskGroup` reports its failures in the order the tasks finished, not a chosen one."""
        assert_that(_raise_group).raises(_ExceptionGroup).when_called_with().matches_error_tree(KeyError, ValueError)

    def test_the_nested_shape_matches(self):
        assert_that(_raise_nested_group).raises(_ExceptionGroup).when_called_with().matches_error_tree(
            ValueError, [TypeError]
        )

    def test_a_flat_spec_refuses_a_nested_group(self):
        """The gap this exists for: `contains_error(ValueError, TypeError)` passes on this very group."""
        assert_that(_raise_nested_group).raises(_ExceptionGroup).when_called_with().contains_error(
            ValueError, TypeError
        )
        with pytest.raises(AssertionError) as exc_info:
            assert_that(_raise_nested_group).raises(_ExceptionGroup).when_called_with().matches_error_tree(
                ValueError, TypeError
            )
        assert_that(str(exc_info.value)).contains("[ValueError, TypeError]", "[ValueError, [TypeError]]")

    def test_a_nested_spec_refuses_a_flat_group(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that(_raise_group).raises(_ExceptionGroup).when_called_with().matches_error_tree(
                ValueError, [KeyError]
            )
        assert_that(str(exc_info.value)).contains("[ValueError, [KeyError]]")

    def test_an_extra_exception_refuses(self):
        def raise_three():
            raise _ExceptionGroup("boom", [ValueError("v"), KeyError("k"), TypeError("t")])

        with pytest.raises(AssertionError) as exc_info:
            assert_that(raise_three).raises(_ExceptionGroup).when_called_with().matches_error_tree(ValueError, KeyError)
        assert_that(str(exc_info.value)).contains("[ValueError, KeyError, TypeError]")

    def test_a_type_matches_a_subgroup_node(self):
        """`isinstance` is what the rest of the family uses, and a group is an exception."""
        assert_that(_raise_nested_group).raises(_ExceptionGroup).when_called_with().matches_error_tree(
            ValueError, Exception
        )

    @pytest.mark.parametrize(
        "spec",
        [(Exception, ValueError), (ValueError, Exception)],
        ids=["the wide entry written first", "written second"],
    )
    def test_the_verdict_does_not_depend_on_how_the_spec_is_ordered(self, spec):
        """A complete matching, not a greedy walk.

        Measured against `pytest.RaisesGroup`, which pairs greedily: it accepts the second spelling and
        refuses the first, on the same group.
        """
        assert_that(_raise_group).raises(_ExceptionGroup).when_called_with().matches_error_tree(*spec)

    def test_two_of_one_type_need_two_of_them(self):
        with pytest.raises(AssertionError):
            assert_that(_raise_group).raises(_ExceptionGroup).when_called_with().matches_error_tree(
                ValueError, ValueError
            )

    def test_a_deep_tree_matches_entry_for_entry(self):
        def raise_deep():
            raise _ExceptionGroup("l0", [_ExceptionGroup("l1", [_ExceptionGroup("l2", [ValueError("v")])])])

        assert_that(raise_deep).raises(_ExceptionGroup).when_called_with().matches_error_tree([[ValueError]])

    def test_a_type_entry_leaves_the_subgroup_it_matches_unconstrained(self):
        def raise_nested():
            raise _ExceptionGroup("failed", [_ExceptionGroup("inner", [ValueError("a"), KeyError("b")])])

        assert_that(raise_nested).raises(_ExceptionGroup).when_called_with().matches_error_tree(Exception)

    def test_two_classes_of_one_name_are_told_apart_in_the_message(self):
        expected = type("Error", (Exception,), {"__module__": "service.first"})
        raised = type("Error", (Exception,), {"__module__": "service.second"})

        def raise_theirs():
            raise _ExceptionGroup("failed", [raised("b")])

        with pytest.raises(AssertionError) as exc_info:
            assert_that(raise_theirs).raises(_ExceptionGroup).when_called_with().matches_error_tree(expected)
        assert_that(str(exc_info.value)).contains("<[service.first.Error]>", "<[service.second.Error]>")

    def test_two_classes_alike_to_the_qualified_name_get_an_ordinal(self):
        def make_error():
            class Error(Exception):
                pass

            return Error

        expected, raised = make_error(), make_error()

        def raise_theirs():
            raise _ExceptionGroup("failed", [raised("b")])

        with pytest.raises(AssertionError) as exc_info:
            assert_that(raise_theirs).raises(_ExceptionGroup).when_called_with().matches_error_tree(expected)
        assert_that(str(exc_info.value)).contains("Error#1]>", "Error#2]>")

    def test_an_unhashable_class_is_still_named(self):
        """A metaclass can refuse to be hashed, and the message still has to arrive.

        The other three group assertions report against such a class and carry on, so this one raising
        `TypeError` instead would be the family disagreeing with itself.
        """
        raised = type("Unhashable", (type,), {"__hash__": None})("Error", (Exception,), {})

        def raise_theirs():
            raise _ExceptionGroup("failed", [raised("w")])

        with pytest.raises(AssertionError) as exc_info:
            assert_that(raise_theirs).raises(_ExceptionGroup).when_called_with().matches_error_tree(ValueError)
        assert_that(str(exc_info.value)).contains("<[ValueError]>", "<[Error]>")

    def test_two_classes_equal_to_each_other_are_still_told_apart(self):
        collapsing = type("Collapsing", (type,), {"__eq__": lambda cls, other: True, "__hash__": lambda cls: 0})
        expected = collapsing("Error", (Exception,), {"__module__": "svc"})
        raised = collapsing("Error", (Exception,), {"__module__": "svc"})

        def raise_theirs():
            raise _ExceptionGroup("failed", [raised("w")])

        with pytest.raises(AssertionError) as exc_info:
            assert_that(raise_theirs).raises(_ExceptionGroup).when_called_with().matches_error_tree(expected)
        assert_that(str(exc_info.value)).contains("<[svc.Error#1]>", "<[svc.Error#2]>")

    def test_a_name_nothing_collides_with_stays_short(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that(_raise_group).raises(_ExceptionGroup).when_called_with().matches_error_tree(
                TypeError, TypeError
            )
        assert_that(str(exc_info.value)).contains("<[TypeError, TypeError]>", "<[ValueError, KeyError]>")

    def test_a_wide_group_of_one_type_matches_entry_for_entry(self):
        def raise_wide():
            raise _ExceptionGroup("wide", [ValueError(str(index)) for index in range(1100)])

        assert_that(raise_wide).raises(_ExceptionGroup).when_called_with().matches_error_tree(*[Exception] * 1100)

    def test_a_mismatch_against_a_deep_tree_still_reports(self):
        def raise_very_deep():
            error: BaseException = ValueError("leaf")
            for _ in range(3000):
                error = _ExceptionGroup("nested", [error])
            raise error

        with pytest.raises(AssertionError) as exc_info:
            assert_that(raise_very_deep).raises(_ExceptionGroup).when_called_with().matches_error_tree(ValueError)
        assert_that(str(exc_info.value)).contains("[[[")

    def test_no_arguments_is_refused(self):
        with pytest.raises(ValueError, match="one or more args"):
            assert_that(_raise_group).raises(_ExceptionGroup).when_called_with().matches_error_tree()

    @pytest.mark.parametrize(
        ("spec", "expected"),
        [
            (("ValueError",), "an exception type"),
            ((ValueError, (KeyError,)), "a list for a subgroup"),
            ((ValueError, []), "a non-empty subgroup"),
            ((ValueError, [42]), "an exception type"),
        ],
        ids=["a string", "a tuple", "an empty subgroup", "a bad type inside one"],
    )
    def test_a_malformed_spec_is_refused_before_the_group_is_read(self, spec, expected):
        with pytest.raises(TypeError) as exc_info:
            assert_that(_raise_group).raises(_ExceptionGroup).when_called_with().matches_error_tree(*spec)
        assert_that(str(exc_info.value)).contains(expected)

    def test_not_a_group_fails(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that(_raise_config).raises(_ConfigError).when_called_with().matches_error_tree(ValueError)
        assert_that(str(exc_info.value)).contains("to be an exception group")

    def test_not_a_group_soft_collects(self):
        with pytest.raises(AssertionError) as exc_info, soft_assertions():
            assert_that(_raise_config).raises(_ConfigError).when_called_with().matches_error_tree(ValueError)
        assert_that(str(exc_info.value)).contains("to be an exception group")

    def test_a_mismatch_soft_collects(self):
        with pytest.raises(AssertionError) as exc_info, soft_assertions():
            assert_that(_raise_group).raises(_ExceptionGroup).when_called_with().matches_error_tree(TypeError)
        assert_that(str(exc_info.value)).contains("to match <[TypeError]>")

    def test_the_chain_continues_after_it_holds(self):
        assert_that(_raise_group).raises(_ExceptionGroup).when_called_with().matches_error_tree(
            ValueError, KeyError
        ).errors().is_length(2)


_NOT_A_GROUP = "Expected the raised <_ConfigError> to be an exception group, but it was not."

_GROUP_QUESTIONS = {
    "contains_error": lambda chain: chain.contains_error(ValueError),
    "does_not_contain_error": lambda chain: chain.does_not_contain_error(ValueError),
    "error_of": lambda chain: chain.error_of(ValueError),
    "matches_error_tree": lambda chain: chain.matches_error_tree(ValueError),
}


class TestNegationKeepsTheGroupRequirement:
    """The group family asks what a group holds, and a plain exception answers neither that nor its negation.

    Inverted, the failure saying the caught exception is not a group read as a pass, so
    `not_.contains_error(ValueError)` held for a plain `ValueError`.
    """

    @pytest.mark.parametrize("question", list(_GROUP_QUESTIONS))
    def test_a_plain_exception_fails_it_either_way_with_the_same_message(self, question):
        caught = assert_that(_raise_config).raises(_ConfigError).when_called_with()
        for asked in (caught, caught.not_):
            with pytest.raises(AssertionError) as exc_info:
                _GROUP_QUESTIONS[question](asked)
            assert_that(str(exc_info.value)).is_equal_to(_NOT_A_GROUP)

    @pytest.mark.parametrize("question", list(_GROUP_QUESTIONS))
    def test_check_answers_the_positive_failure_asked_through_not(self, question):
        caught = assert_that(_raise_config).raises(_ConfigError).when_called_with()
        positive = _GROUP_QUESTIONS[question](caught.check())
        negated = _GROUP_QUESTIONS[question](caught.check().not_)
        assert_that(negated.passed).is_false()
        assert_that(negated.message).is_equal_to(_NOT_A_GROUP)
        assert_that(negated.requirement).is_equal_to(replace(positive.requirement, negated=True))
        assert_that(replace(negated, requirement=None)).is_equal_to(replace(positive, requirement=None))

    @pytest.mark.parametrize("question", list(_GROUP_QUESTIONS))
    def test_a_soft_block_collects_it_either_way_where_the_positive_lands(self, question):
        with pytest.raises(AssertionError) as exc_info, soft_assertions() as soft, soft.group("plain"):
            _GROUP_QUESTIONS[question](assert_that(_raise_config).raises(_ConfigError).when_called_with())
            negated = _GROUP_QUESTIONS[question](
                assert_that(_raise_config).raises(_ConfigError).when_called_with().not_
            )
            with pytest.raises(TypeError) as refusal:
                _ = negated.value
        positive, collected = exc_info.value.failures
        assert_that(collected.message).is_equal_to(positive.message).is_equal_to(_NOT_A_GROUP)
        assert_that(collected.group).is_equal_to(positive.group).is_equal_to("plain")
        assert_that(collected.location).is_equal_to(positive.location)
        assert_that(collected.location[0]).ends_with("test_expected_exception.py")
        assert_that(str(refusal.value)).contains(f"soft or warn mode - {_NOT_A_GROUP}")

    @pytest.mark.parametrize("question", list(_GROUP_QUESTIONS))
    def test_warn_logs_it_under_not_and_the_value_refuses(self, question):
        capture = StringIO()
        logger = logging.getLogger(f"negated_group_requirement_{question}")
        handler = logging.StreamHandler(capture)
        logger.addHandler(handler)
        try:
            caught = assert_warn(_raise_config, logger=WarningLoggingAdapter(logger, None))
            negated = _GROUP_QUESTIONS[question](caught.raises(_ConfigError).when_called_with().not_)
        finally:
            logger.removeHandler(handler)
        assert_that(capture.getvalue()).contains(_NOT_A_GROUP)
        with pytest.raises(TypeError) as refusal:
            _ = negated.value
        assert_that(str(refusal.value)).contains(f"soft or warn mode - {_NOT_A_GROUP}")

    @pytest.mark.parametrize("question", list(_GROUP_QUESTIONS))
    def test_a_poll_never_holds_it_under_not(self, question):
        chain = assert_that(lambda: _raise_config).eventually_sync(timeout=0.05, interval=0.01)
        with pytest.raises(AssertionError) as exc_info:
            _GROUP_QUESTIONS[question](chain.raises(_ConfigError).when_called_with().not_)
        assert_that(str(exc_info.value)).contains(f"Last failure: {_NOT_A_GROUP}")

    def test_an_async_poll_never_holds_it_under_not(self):
        async def poll():
            chain = assert_that(lambda: _raise_config).eventually(timeout=0.05, interval=0.01)
            await chain.raises(_ConfigError).when_called_with().not_.contains_error(ValueError)

        with pytest.raises(AssertionError) as exc_info:
            asyncio.run(poll())
        assert_that(str(exc_info.value)).contains(f"Last failure: {_NOT_A_GROUP}")

    def test_an_extension_that_goes_on_after_it_still_reports_it_under_not(self):
        """Check mode does not stop an extension at a failure, and the one after it is not the one to report."""

        def is_a_group_saying_so(self):
            self.contains_error(ValueError)
            self.does_not_contain_error(KeyError)
            self.not_.error_of(KeyError)
            return self.is_equal_to("a message it does not have")

        add_extension(is_a_group_saying_so)
        try:
            caught = assert_that(_raise_config).raises(_ConfigError).when_called_with()
            with pytest.raises(AssertionError) as exc_info:
                caught.not_.is_a_group_saying_so()
        finally:
            remove_extension(is_a_group_saying_so)
        assert_that(str(exc_info.value)).is_equal_to(_NOT_A_GROUP)

    def test_a_verdict_an_extension_asks_for_itself_stays_its_own_under_not(self):
        def is_plain(self):
            if self.check().contains_error(ValueError).passed:
                self.error("Expected a plain exception, but it was a group.")
            return self

        add_extension(is_plain)
        try:
            caught = assert_that(_raise_config).raises(_ConfigError).when_called_with()
            with pytest.raises(AssertionError) as exc_info:
                caught.not_.is_plain()
        finally:
            remove_extension(is_plain)
        assert_that(str(exc_info.value)).is_equal_to("Expected <bad config> to NOT satisfy: is_plain()")

    def test_two_negations_report_it_as_one_does(self):
        def holds_no_value_error(self):
            return self.not_.contains_error(ValueError)

        add_extension(holds_no_value_error)
        try:
            caught = assert_that(_raise_config).raises(_ConfigError).when_called_with()
            outcome = caught.check().not_.holds_no_value_error()
            with pytest.raises(AssertionError) as exc_info:
                caught.not_.holds_no_value_error()
        finally:
            remove_extension(holds_no_value_error)
        assert_that(outcome.passed).is_false()
        assert_that(outcome.message).is_equal_to(_NOT_A_GROUP)
        assert_that(str(exc_info.value)).is_equal_to(_NOT_A_GROUP)

    @needs_groups
    @pytest.mark.parametrize(
        ("question", "holds"),
        [
            (lambda chain: chain.contains_error(ValueError), True),
            (lambda chain: chain.contains_error(TypeError), False),
            (lambda chain: chain.does_not_contain_error(TypeError), True),
            (lambda chain: chain.does_not_contain_error(ValueError), False),
            (lambda chain: chain.error_of(KeyError), True),
            (lambda chain: chain.error_of(TypeError), False),
            (lambda chain: chain.matches_error_tree(KeyError, ValueError), True),
            (lambda chain: chain.matches_error_tree(ValueError), False),
        ],
        ids=[
            "contains-held",
            "contains-missed",
            "not-contain-held",
            "not-contain-missed",
            "error-of-held",
            "error-of-missed",
            "tree-held",
            "tree-missed",
        ],
    )
    def test_on_a_group_not_still_inverts_the_question(self, question, holds):
        caught = assert_that(_raise_group).raises(_ExceptionGroup).when_called_with()
        passing, failing = (caught, caught.not_) if holds else (caught.not_, caught)
        question(passing)
        with pytest.raises(AssertionError) as exc_info:
            question(failing)
        assert_that(str(exc_info.value)).does_not_contain("to be an exception group")


def _raise_key():
    raise KeyError("k")


def _raise_value():
    raise ValueError("v")


def _interrupted():
    raise KeyboardInterrupt


class TestSeveralClassesAnyOneOfWhichWillDo:
    """A tuple or a union of classes, as `except`, `isinstance` and `pytest.raises` take one.

    `caused_by` and `has_root_cause` took one since 2.27, and `raises`, `does_not_raise`, `contains_error`
    and `does_not_contain_error` refused it, so the other spelling was `raises(BaseException)` and a check of
    `raised()` afterwards.
    """

    @pytest.mark.parametrize(
        "named",
        [(TypeError, KeyError), TypeError | KeyError, (TypeError, (OSError | KeyError,))],
        ids=["tuple", "union", "nested"],
    )
    def test_any_one_of_them_raised_is_caught(self, named):
        assert_that(assert_that(_raise_key).raises(named).when_called_with().raised().value).is_instance_of(KeyError)

    def test_none_of_them_raised_names_them_all(self):
        with pytest.raises(AssertionError) as failure:
            assert_that(_raise_value).raises((TypeError, KeyError)).when_called_with()
        assert_that(str(failure.value)).starts_with(
            "Expected <_raise_value> to raise <TypeError, KeyError> when called with (), but raised <ValueError>."
        )
        assert_that(failure.value.expected).is_equal_to((TypeError, KeyError))

    def test_a_union_is_named_as_it_is_written(self):
        with pytest.raises(AssertionError, match=r"to raise <TypeError \| KeyError> when called with \(\)\."):
            assert_that(lambda: None).raises(TypeError | KeyError).when_called_with()

    def test_the_classes_are_kept_as_written(self):
        with pytest.raises(AssertionError) as failure:
            assert_that(lambda: None).raises((KeyError,)).when_called_with()
        assert_that(failure.value.expected).is_equal_to((KeyError,))

    def test_a_runner_signal_still_leaves_unless_it_is_named(self):
        with pytest.raises(KeyboardInterrupt):
            assert_that(_interrupted).raises((TypeError, KeyError)).when_called_with()
        assert_that(_interrupted).raises((TypeError, KeyboardInterrupt)).when_called_with()

    def test_does_not_raise_any_of_them(self):
        assert_that(_raise_value).does_not_raise((TypeError, KeyError)).when_called_with()
        with pytest.raises(AssertionError) as failure:
            assert_that(_raise_key).does_not_raise(TypeError | KeyError).when_called_with()
        assert_that(str(failure.value)).starts_with(
            "Expected <_raise_key> to not raise <TypeError | KeyError> when called with (), but did raise <KeyError>."
        )

    @pytest.mark.parametrize(
        "wrong",
        [(), ((),), (ValueError, int), ValueError | int, (ValueError, "KeyError")],
        ids=["empty", "nested-empty", "a-class-that-is-no-exception", "a-union-with-one", "a-name"],
    )
    def test_every_member_is_read_before_anything_is_called(self, wrong):
        called = []
        for expect in (assert_that(called.append).raises, assert_that(called.append).does_not_raise):
            with pytest.raises(TypeError) as refusal:
                expect(wrong)
            assert_that(str(refusal.value)).starts_with(
                "given exception arg must be an exception type, or a union or a non-empty tuple of them, but was <"
            )
        assert_that(called).is_empty()

    @needs_groups
    def test_in_a_group_alternatives_sit_inside_one_argument_and_every_argument_is_asked(self):
        caught = assert_that(_raise_group).raises(_ExceptionGroup).when_called_with()
        caught.contains_error((TypeError, KeyError)).contains_error(OSError | ValueError, KeyError)
        with pytest.raises(AssertionError) as failure:
            caught.contains_error((TypeError, KeyError), (OSError, LookupError | TypeError), OSError)
        assert_that(str(failure.value)).starts_with(
            "Expected the raised exception group to contain <OSError>, but it did not."
        )

    @needs_groups
    def test_in_a_group_none_of_them_may_be_held(self):
        caught = assert_that(_raise_group).raises(_ExceptionGroup).when_called_with()
        caught.does_not_contain_error((TypeError, OSError))
        with pytest.raises(AssertionError) as failure:
            caught.does_not_contain_error(TypeError | KeyError)
        assert_that(str(failure.value)).starts_with(
            "Expected the raised exception group to not contain <TypeError | KeyError>, but it did."
        )
