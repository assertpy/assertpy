import logging
from io import StringIO

import pytest

from assertpy import (
    AssertionFailure,
    WarningLoggingAdapter,
    add_extension,
    assert_that,
    assert_warn,
    match,
    remove_extension,
    soft_assertions,
)


class TestNotBasic:
    def test_not_is_none(self):
        assert_that(5).not_.is_none()

    def test_not_is_empty(self):
        assert_that([1, 2]).not_.is_empty()

    def test_not_is_equal_to(self):
        assert_that(5).not_.is_equal_to(10)

    def test_not_is_positive_on_negative(self):
        assert_that(-5).not_.is_positive()

    def test_not_is_alpha(self):
        assert_that("abc123").not_.is_alpha()

    def test_not_is_sorted(self):
        assert_that([3, 1, 2]).not_.is_sorted()

    def test_not_contains(self):
        assert_that([1, 2, 3]).not_.contains(5)

    def test_not_is_in(self):
        assert_that(42).not_.is_in(1, 2, 3)

    def test_not_is_instance_of(self):
        assert_that("hello").not_.is_instance_of(int)

    def test_not_is_length(self):
        assert_that([1, 2]).not_.is_length(5)


class TestNotFailure:
    def test_not_is_positive_on_positive(self):
        with pytest.raises(AssertionError, match="to NOT satisfy"):
            assert_that(5).not_.is_positive()

    def test_not_is_none_on_none(self):
        with pytest.raises(AssertionError, match="to NOT satisfy"):
            assert_that(None).not_.is_none()

    def test_not_is_equal_to_on_equal(self):
        with pytest.raises(AssertionError, match="to NOT satisfy"):
            assert_that(5).not_.is_equal_to(5)

    def test_not_is_empty_on_empty(self):
        with pytest.raises(AssertionError, match="to NOT satisfy"):
            assert_that([]).not_.is_empty()

    def test_not_contains_on_present(self):
        with pytest.raises(AssertionError, match="to NOT satisfy"):
            assert_that([1, 2, 3]).not_.contains(2)

    def test_failure_message_format(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that(5).not_.is_positive()
        assert_that(str(exc_info.value)).contains("Expected <5> to NOT satisfy: is_positive()")


class TestNotDescribedAs:
    def test_description_in_error(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that(5).described_as("my check").not_.is_positive()
        assert_that(str(exc_info.value)).starts_with("[my check]")

    def test_description_preserved_on_success(self):
        result = assert_that(-5).described_as("my check").not_.is_positive()
        assert_that(result.description).is_equal_to("my check")


class TestNotChaining:
    def test_chain_after_not(self):
        assert_that(5).not_.is_none().is_positive()

    def test_chain_after_not_with_description(self):
        assert_that(5).described_as("val").not_.is_none().is_positive()

    def test_chain_multiple_assertions_after_not(self):
        assert_that("hello").not_.is_empty().is_length(5).is_alpha()


class TestNotSoftAssertions:
    def test_soft_not_collects_error(self):
        with pytest.raises(AssertionError) as exc_info, soft_assertions():
            assert_that(5).not_.is_positive()
            assert_that(None).not_.is_none()
        msg = str(exc_info.value)
        assert_that(msg).contains("is_positive()")
        assert_that(msg).contains("is_none()")

    def test_soft_not_success_does_not_add_error(self):
        with soft_assertions():
            assert_that(-5).not_.is_positive()
            assert_that(5).not_.is_none()

    def test_soft_passing_negation_returns_value(self):
        with soft_assertions():
            builder = assert_that(5).not_.is_equal_to(6)
            value = builder.value
        assert_that(value).is_equal_to(5)

    def test_soft_failing_negation_taints_value(self):
        with pytest.raises(AssertionError), soft_assertions():
            builder = assert_that(5).not_.is_equal_to(5)
            with pytest.raises(TypeError):
                _ = builder.value

    def test_soft_prior_failure_taint_survives_passing_negation(self):
        with pytest.raises(AssertionError), soft_assertions():
            builder = assert_that(5).is_equal_to(6)
            passed = builder.not_.is_equal_to(7)
            with pytest.raises(TypeError):
                _ = passed.value

    def test_soft_prior_failure_then_failing_negation_keeps_first_taint(self):
        with pytest.raises(AssertionError), soft_assertions():
            builder = assert_that(5).is_equal_to(6)
            failed = builder.not_.is_equal_to(5)
            with pytest.raises(TypeError):
                _ = failed.value


class TestNotWarnMode:
    def test_warn_not_logs_warning(self):
        capture = StringIO()
        logger = logging.getLogger("test_not_warn")
        handler = logging.StreamHandler(capture)
        logger.addHandler(handler)

        adapted = WarningLoggingAdapter(logger, None)
        assert_warn("hello", logger=adapted).not_.is_alpha()

        out = capture.getvalue()
        capture.close()
        assert_that(out).contains("to NOT satisfy: is_alpha()")

    def test_warn_passing_negation_returns_value(self):
        assert_that(assert_warn(5).not_.is_equal_to(6).value).is_equal_to(5)

    def test_warn_failing_negation_taints_value(self):
        builder = assert_warn(5).not_.is_equal_to(5)
        with pytest.raises(TypeError):
            _ = builder.value

    def test_warn_prior_failure_then_failing_negation_keeps_first_taint(self):
        builder = assert_warn(5).is_equal_to(6)
        failed = builder.not_.is_equal_to(5)
        with pytest.raises(TypeError):
            _ = failed.value

    def test_warn_not_success_does_not_log(self):
        capture = StringIO()
        logger = logging.getLogger("test_not_warn_success")
        handler = logging.StreamHandler(capture)
        logger.addHandler(handler)

        adapted = WarningLoggingAdapter(logger, None)
        assert_warn("abc123", logger=adapted).not_.is_alpha()

        out = capture.getvalue()
        capture.close()
        assert_that(out).is_empty()


class TestNotNamesWhatItWasAskedAbout:
    """A negated failure carries the arguments, or it names the relation and not the subject.

    ``starts_with()`` says which relation held; ``starts_with('a')`` says what held.  The direct
    spellings have always named the operand, and the proxy is the one place that did not.
    """

    def test_a_positional_argument(self):
        with pytest.raises(AssertionError) as caught:
            assert_that("abc").not_.starts_with("a")
        assert_that(str(caught.value)).is_equal_to("Expected <abc> to NOT satisfy: starts_with('a')")

    def test_several_arguments(self):
        with pytest.raises(AssertionError) as caught:
            assert_that(3).not_.is_between(1, 5)
        assert_that(str(caught.value)).is_equal_to("Expected <3> to NOT satisfy: is_between(1, 5)")

    def test_a_keyword_argument(self):
        with pytest.raises(AssertionError) as caught:
            assert_that({"n": 1}).not_.is_equal_to({"n": 1}, strict_types=True)
        assert_that(str(caught.value)).is_equal_to(
            "Expected <{'n': 1}> to NOT satisfy: is_equal_to({'n': 1}, strict_types=True)"
        )

    def test_an_assertion_that_takes_none_reads_as_before(self):
        with pytest.raises(AssertionError) as caught:
            assert_that(5).not_.is_positive()
        assert_that(str(caught.value)).is_equal_to("Expected <5> to NOT satisfy: is_positive()")

    def test_the_soft_block_collects_the_same_sentence(self):
        with pytest.raises(AssertionFailure) as caught, soft_assertions():
            assert_that("abc").not_.starts_with("a")
        assert_that(str(caught.value)).contains("starts_with('a')")

    def test_check_mode_records_the_same_sentence(self):
        outcome = assert_that("abc").check().not_.starts_with("a")
        assert_that(outcome.message).is_equal_to("Expected <abc> to NOT satisfy: starts_with('a')")


class TestNotDoesNotInvertAnErrorFromTheValue:
    """Negation inverts this library's verdict, and an ``AssertionError`` from your code is not one.

    The proxy used to catch every ``AssertionError``, so a comparison that broke while being negated
    read as "the assertion failed, so the negation held" and the test went green over the break.  The
    four sources below are the four places user code runs inside an assertion.
    """

    @staticmethod
    def _foreign(caught):
        """The error travelled out as it was raised, rather than being read as a verdict."""
        assert_that(isinstance(caught.value, AssertionFailure)).is_false()
        return assert_that(str(caught.value))

    def test_an_equality_that_raises(self):
        class Broken:
            __hash__ = None

            def __eq__(self, other):
                raise AssertionError("comparison implementation broke")

        with pytest.raises(AssertionError) as caught:
            assert_that(Broken()).not_.is_equal_to(1)
        self._foreign(caught).is_equal_to("comparison implementation broke")

    def test_a_comparator_that_raises(self):
        def broken(left, right):
            raise AssertionError("comparator broke")

        with pytest.raises(AssertionError) as caught:
            assert_that({"n": 1}).not_.is_equal_to({"n": 2}, comparators={int: broken})
        self._foreign(caught).is_equal_to("comparator broke")

    def test_a_property_that_raises(self):
        # a dynamic `has_*` reads the property while the proxy resolves the attribute, before there is
        # a verdict to invert. Pinned so moving resolution inside the try does not lose it silently
        class Record:
            @property
            def name(self):
                raise AssertionError("property broke")

        with pytest.raises(AssertionError) as caught:
            assert_that(Record()).not_.has_name("ada")
        self._foreign(caught).is_equal_to("property broke")

    def test_an_extension_that_raises_on_its_own(self, _broken_extension):
        with pytest.raises(AssertionError) as caught:
            assert_that(1).not_.breaks_outright()
        self._foreign(caught).is_equal_to("extension broke")

    def test_warn_mode_does_not_invert_it_either(self):
        class Broken:
            __hash__ = None

            def __eq__(self, other):
                raise AssertionError("comparison implementation broke")

        with pytest.raises(AssertionError) as caught:
            assert_warn(Broken()).not_.is_equal_to(1)
        self._foreign(caught).is_equal_to("comparison implementation broke")

    def test_a_nested_assertion_inside_a_comparator(self):
        # a comparator asserting with this library raises our own failure, which is still not the verdict
        def asserts_inside(left, right):
            assert_that(left).is_equal_to(right)
            return True

        with pytest.raises(AssertionFailure) as caught:
            assert_that({"n": 1}).not_.is_equal_to({"n": 2}, comparators={int: asserts_inside})
        assert_that(str(caught.value)).starts_with("Expected <1> to be equal to <2>")

    def test_a_nested_assertion_inside_a_comparator_in_warn_mode(self):
        def asserts_inside(left, right):
            assert_that(left).is_equal_to(right)
            return True

        with pytest.raises(AssertionFailure) as caught:
            assert_warn({"n": 1}).not_.is_equal_to({"n": 2}, comparators={int: asserts_inside})
        assert_that(str(caught.value)).starts_with("Expected <1> to be equal to <2>")

    def test_a_nested_assertion_in_a_soft_block_is_collected_rather_than_lost(self):
        # soft collects rather than raises, so the honest outcome here is both failures, not silence
        def asserts_inside(left, right):
            assert_that(left).is_equal_to(right)
            return True

        with pytest.raises(AssertionFailure) as caught, soft_assertions():
            assert_that({"n": 1}).not_.is_equal_to({"n": 2}, comparators={int: asserts_inside})
        collected = [outcome.message.splitlines()[0] for outcome in caught.value.failures]
        assert_that(collected).is_length(2)
        assert_that(collected[0]).is_equal_to("Expected <1> to be equal to <2>, but was not.")

    def test_the_library_own_failure_still_inverts(self):
        assert_that(5).not_.is_equal_to(6)
        assert_warn(5).not_.is_equal_to(6)

    def test_an_extension_reporting_a_verdict_still_inverts(self, _five_extension):
        # the documented way an extension fails is `self.error(...)`, and that is a verdict
        assert_that(6).not_.is_five()
        with pytest.raises(AssertionFailure, match=r"to NOT satisfy: is_five\(\)"):
            assert_that(5).not_.is_five()


@pytest.fixture
def _five_extension():
    """The extension from the guide, which reports its verdict with `self.error(...)`."""

    def is_five(self):
        if self.val != 5:
            return self.error(f"{self.val} is NOT 5!")
        return self

    add_extension(is_five)
    try:
        yield
    finally:
        remove_extension(is_five)


@pytest.fixture
def _broken_extension():
    """An extension that raises rather than reporting a verdict, taken back off the global registry."""

    def breaks_outright(self):
        raise AssertionError("extension broke")

    add_extension(breaks_outright)
    try:
        yield
    finally:
        remove_extension(breaks_outright)


class TestNotAttributes:
    def test_non_callable_attr_passthrough(self):
        builder = assert_that(5).described_as("test")
        negated = builder.not_
        assert_that(negated.val).is_equal_to(5)
        assert_that(negated.description).is_equal_to("test")


class TestNotWithMatchers:
    def test_not_satisfies(self):
        assert_that(-5).not_.satisfies(match.is_positive())

    def test_not_satisfies_failure(self):
        with pytest.raises(AssertionError, match="to NOT satisfy"):
            assert_that(5).not_.satisfies(match.is_positive())

    def test_not_each(self):
        assert_that([1, -2, 3]).not_.each(match.is_positive())


def test_not_rejects_eventually_with_clear_error():
    with pytest.raises(TypeError, match="cannot be negated"):
        assert_that(lambda: 1).not_.eventually()


def test_not_rejects_eventually_sync_with_clear_error():
    with pytest.raises(TypeError, match="cannot be negated"):
        assert_that(lambda: 1).not_.eventually_sync()


def test_not_rejects_described_as_with_clear_error():
    # described_as() configures the chain; negating it produced a bogus "to NOT satisfy" failure
    with pytest.raises(TypeError, match=r"call described_as\(\) before not_"):
        assert_that(1).not_.described_as("desc")


def test_described_as_before_not_keeps_working():
    with pytest.raises(AssertionError, match=r"\[desc\] Expected <1> to NOT satisfy: is_equal_to\(1\)"):
        assert_that(1).described_as("desc").not_.is_equal_to(1)


def test_not_rejects_extracting_with_clear_error():
    # extracting() pivots to a new value; negating it raised on success instead of asserting anything
    with pytest.raises(TypeError, match=r"negate the assertion after extracting\(\)"):
        assert_that([{"a": 1}]).not_.extracting("a")


def test_extracting_before_not_keeps_working():
    assert_that([{"a": 1}]).extracting("a").not_.contains(2)


@pytest.mark.parametrize(
    "step", ["filtered_on", "mapped", "flat_mapped", "first", "last", "element", "single", "decoded_as", "at_json_path"]
)
def test_not_rejects_pipeline_transformers_with_clear_error(step):
    with pytest.raises(TypeError, match=f"negate the assertion after {step}"):
        getattr(assert_that([1]).not_, step)


def test_pipeline_transformer_before_not_keeps_working():
    assert_that([1, -2, 3]).filtered_on(lambda x: x > 0).not_.is_empty()
    assert_that([10, 20]).first().not_.is_equal_to(20)


def test_hybrid_pivots_stay_negatable():
    # both assert (the pattern must match) and pivot, so negating them is meaningful and stays allowed
    assert_that("abc").not_.matches_with_groups(r"(\d+)")
    assert_that("abc").not_.extracting_group(r"(\d+)", 1)
