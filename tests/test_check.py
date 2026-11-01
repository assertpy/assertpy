"""`check()` runs an assertion for its verdict instead of for its failure.

The library had three non-raising exits before this and none of them was a result: warn mode writes to
a logger and returns the builder, a soft block collects into a private contextvar, and a matcher's
`matches()` answers a bare bool with no message, values or diff. This is the one that hands the caller
what the assertion decided.
"""

import logging

import pytest

from assertpy import (
    AssertionFailure,
    AssertionOutcome,
    add_extension,
    assert_that,
    assert_warn,
    remove_extension,
    soft_assertions,
)


class TestTheVerdictComesBackInsteadOfBeingRaised:
    def test_a_passing_assertion_answers_truthy(self):
        outcome = assert_that(5).check().is_positive()
        assert_that(outcome.passed).is_true()
        assert_that(bool(outcome)).is_true()

    def test_a_failing_assertion_answers_falsy_and_does_not_raise(self):
        outcome = assert_that(-5).check().is_positive()
        assert_that(outcome.passed).is_false()
        assert_that(bool(outcome)).is_false()

    def test_a_passing_outcome_carries_the_value_and_no_message(self):
        outcome = assert_that([1, 2]).check().is_not_empty()
        assert_that(outcome.actual).is_equal_to([1, 2])
        assert_that(outcome.message).is_empty()

    def test_a_failing_outcome_carries_everything_the_exception_would_have(self):
        outcome = assert_that({"a": 1}).check().is_equal_to({"a": 2})
        assert_that(outcome.message).is_equal_to("Expected <{'a': 1}> to be equal to <{'a': 2}>, but was not.")
        assert_that(outcome.actual).is_equal_to({"a": 1})
        assert_that(outcome.expected).is_equal_to({"a": 2})
        assert_that(outcome.diff.kind).is_equal_to("dict")
        assert_that([entry.path for entry in outcome.diff.entries]).is_equal_to(["a"])

    def test_the_description_prefixes_the_message_as_it_would_a_raised_one(self):
        outcome = assert_that(-5).described_as("the balance").check().is_positive()
        assert_that(outcome.message).starts_with("[the balance] ")

    def test_one_call_composes_one_failure_however_many_parts_it_names(self):
        # the invariant the sink rests on: every `self.error(...)` returns at once, so several problems are one message
        outcome = assert_that([1, 2]).check().contains(9, 8)
        assert_that(outcome.passed).is_false()
        assert_that(outcome.message).contains("9")
        assert_that(outcome.message).contains("8")


class TestTheBuilderIsUnchangedAfterwards:
    def test_the_next_assertion_on_the_same_builder_still_raises(self):
        builder = assert_that(-5)
        builder.check().is_positive()
        with pytest.raises(AssertionFailure):
            builder.is_positive()

    def test_a_failed_check_does_not_taint_the_value(self):
        # soft and warn refuse `.value` after a failure: a check asked a question, it asserted nothing
        builder = assert_that(-5)
        builder.check().is_positive()
        assert_that(builder.value).is_equal_to(-5)

    def test_a_bad_argument_still_raises_rather_than_becoming_a_verdict(self):
        # TypeError means the call itself is wrong, which is not something the value can be at fault for
        with pytest.raises(TypeError):
            assert_that([1]).check().all_fields_satisfy(42)

    def test_the_mode_is_put_back_even_when_the_call_raises(self):
        builder = assert_that([1])
        with pytest.raises(TypeError):
            builder.check().all_fields_satisfy(42)
        assert_that(builder.kind).is_none()


class TestCheckInsideTheOtherModes:
    def test_a_check_inside_a_soft_block_collects_nothing(self):
        with soft_assertions():
            outcome = assert_that(-5).check().is_positive()
            assert_that(outcome.passed).is_false()

    def test_a_soft_assertion_after_a_check_still_collects(self):
        with pytest.raises(AssertionFailure) as failure, soft_assertions():
            assert_that(-5).check().is_positive()
            assert_that(-5).is_positive()
        assert_that(str(failure.value)).contains("to be greater than <0>")

    def test_a_check_in_warn_mode_answers_instead_of_logging(self, caplog):
        with caplog.at_level(logging.WARNING, logger="assertpy"):
            outcome = assert_warn(-5).check().is_positive()
        assert_that(outcome.passed).is_false()
        assert_that(caplog.text).is_empty()


class TestNegationIsProxiedRatherThanRefused:
    def test_a_negation_that_holds_answers_truthy(self):
        assert_that(assert_that(-5).check().not_.is_positive().passed).is_true()

    def test_a_negation_that_fails_carries_its_own_message(self):
        outcome = assert_that(5).check().not_.is_positive()
        assert_that(outcome.passed).is_false()
        assert_that(outcome.message).is_equal_to("Expected <5> to NOT satisfy: is_positive()")
        assert_that(outcome.actual).is_equal_to(5)

    def test_a_negation_leaves_no_collected_failure_behind(self):
        # the inner assertion lands in the sink first, and a negation that held has to clear it
        builder = assert_that(-5)
        builder.check().not_.is_positive()
        assert_that(builder.check().is_negative().passed).is_true()


def _asks_a_held_negation(builder):
    builder.not_.is_equal_to(7)


def _asks_a_passing_check(builder):
    builder.check().is_equal_to(12)


def _asks_a_refused_check(builder):
    with pytest.raises(ValueError, match="one or more args"):
        builder.check().contains_error()


def _fails_again(builder):
    builder.is_equal_to(13)


def _fails_a_negation(builder):
    builder.not_.is_equal_to(12)


class TestAVerdictAskedInsideKeepsTheFailureAroundIt:
    """An extension goes on after a failure in check mode, and a verdict it asked for next used to wipe it.

    Both inner proxies cleared the one sink the enclosing verdict reads, so `check()` answered a pass and
    `not_` a failure for an extension whose strict run fails at its first step.
    """

    @pytest.mark.parametrize(
        "ask", [_asks_a_held_negation, _asks_a_passing_check, _asks_a_refused_check, _fails_again, _fails_a_negation]
    )
    def test_check_and_not_both_read_the_earlier_failure(self, ask):
        def is_below_ten(self):
            self.is_less_than(10)
            ask(self)
            return self

        add_extension(is_below_ten)
        try:
            outcome = assert_that(12).check().is_below_ten()
            assert_that(12).not_.is_below_ten()
        finally:
            remove_extension(is_below_ten)
        assert_that(outcome.passed).is_false()
        assert_that(outcome.message).is_equal_to("Expected <12> to be less than <10>, but was not.")


def carries_code(self, code):
    self.extracting_group(r"code=(\d+)", 1).is_equal_to(code)
    return self


def lacks_code(self, code):
    self.extracting_group(r"code=(\d+)", 1).not_.is_equal_to(code)
    return self


def carries_code_other_than(self, avoided, code):
    pivot = self.extracting_group(r"code=(\d+)", 1)
    if pivot.check().is_equal_to(avoided).passed:
        return self.error(f"Expected a code other than <{avoided}>, but it was.")
    pivot.is_equal_to(code)
    return self


def names_a_code(self):
    self.matches_with_groups(r"(?P<code>\d+)").has_cod("404")
    return self


def refuses_to_start(self):
    self.raises(ValueError).when_called_with()
    return self


def keeps_its_pivot_then_refuses(self, kept):
    kept.append(self.extracting_group(r"code=(\d+)", 1))
    return self.is_length("three")


def keeps_its_pivot(self, kept):
    code = self.extracting_group(r"code=(\d+)", 1)
    kept.extend((code, code.extracting_group(r"(\d)", 1)))
    return self


def _starts():
    return None


@pytest.fixture()
def _pivoting_extensions():
    extensions = (
        carries_code,
        lacks_code,
        carries_code_other_than,
        names_a_code,
        refuses_to_start,
        keeps_its_pivot,
        keeps_its_pivot_then_refuses,
    )
    for extension in extensions:
        add_extension(extension)
    yield
    for extension in extensions:
        remove_extension(extension)


@pytest.mark.usefixtures("_pivoting_extensions")
class TestAPivotInsideAnExtensionAnswersForIt:
    """A pivot inherits check mode, and its failures landed in a sink of its own that nobody read.

    An extension asserting through `extracting_group()` held under `check()` while its strict run failed,
    and failed under `not_` whatever the pivot answered.
    """

    def test_check_reads_what_the_strict_run_raises(self):
        with pytest.raises(AssertionError) as strict:
            assert_that("code=404").carries_code("200")
        outcome = assert_that("code=404").check().carries_code("200")
        assert_that(outcome.passed).is_false()
        assert_that(outcome.message).is_equal_to(str(strict.value)).is_equal_to(
            "Expected <404> to be equal to <200>, but was not."
        )
        assert_that(assert_that("code=404").check().carries_code("404").passed).is_true()

    def test_not_inverts_what_the_pivot_answered(self):
        assert_that("code=404").not_.carries_code("200")
        with pytest.raises(AssertionError) as exc_info:
            assert_that("code=404").not_.carries_code("404")
        assert_that(str(exc_info.value)).is_equal_to("Expected <code=404> to NOT satisfy: carries_code('404')")

    def test_a_negation_asked_of_the_pivot_is_read_and_restored_where_the_run_keeps_it(self):
        assert_that(assert_that("code=404").check().lacks_code("200").passed).is_true()
        outcome = assert_that("code=404").check().lacks_code("404")
        assert_that(outcome.message).is_equal_to("Expected <404> to NOT satisfy: is_equal_to('404')")
        assert_that("code=404").not_.lacks_code("404")

    def test_a_verdict_asked_of_the_pivot_stays_the_extension_own(self):
        outcome = assert_that("code=404").check().carries_code_other_than("500", "200")
        assert_that(outcome.message).is_equal_to("Expected <404> to be equal to <200>, but was not.")
        assert_that(assert_that("code=404").check().carries_code_other_than("500", "404").passed).is_true()

    def test_a_prerequisite_the_pivot_misses_is_delivered_as_it_stands(self):
        missing = "Expected key <cod>, but val has no key <cod>.\na key is spelled almost the same: <code>"
        with pytest.raises(AssertionError) as exc_info:
            assert_that("code=404").not_.names_a_code()
        outcome = assert_that("code=404").check().not_.names_a_code()
        assert_that(str(exc_info.value)).is_equal_to(missing)
        assert_that(outcome.message).is_equal_to(missing)

    def test_an_expectation_configured_inside_answers_for_it_too(self):
        outcome = assert_that(_starts).check().refuses_to_start()
        assert_that(outcome.passed).is_false()
        assert_that(outcome.message).is_equal_to("Expected <_starts> to raise <ValueError> when called with ().")
        assert_that(_starts).not_.refuses_to_start()

    def test_a_pivot_kept_past_the_run_asserts_in_the_mode_its_chain_is_back_in(self):
        """Left in check mode, a pivot an extension held on to swallowed every failure after the run."""
        kept = []
        chain = assert_that("code=404")
        assert_that(chain.check().keeps_its_pivot(kept).passed).is_true()
        with pytest.raises(AssertionError, match="to NOT satisfy"):
            chain.not_.keeps_its_pivot(kept)
        for pivot, value in zip(kept, ("404", "4", "404", "4"), strict=True):
            with pytest.raises(AssertionError, match=f"Expected <{value}> to be equal to <200>"):
                pivot.is_equal_to("200")
        assert_that(chain.check().is_equal_to("code=404").passed).is_true()
        with pytest.raises(AssertionError) as soft_run, soft_assertions():
            assert_that("code=404").check().keeps_its_pivot(kept)
            kept[-2].is_equal_to("200")
            kept[-1].is_equal_to("200")
        assert_that([failure.message for failure in soft_run.value.failures]).is_equal_to(
            ["Expected <404> to be equal to <200>, but was not.", "Expected <4> to be equal to <200>, but was not."]
        )

    def test_a_pivot_kept_from_a_run_that_raised_is_released_too(self):
        kept = []
        with pytest.raises(TypeError):
            assert_that("code=404").check().keeps_its_pivot_then_refuses(kept)
        with pytest.raises(AssertionError, match="Expected <404> to be equal to <200>"):
            kept[0].is_equal_to("200")


class TestCheckAnswersWithTheFirstFailure:
    """Check mode goes on past a failure, and an assertion failing twice answered with the second one.

    The strict run stops at the first, so `check()` and the failure it stands in for named different items.
    A sequence under a key option was the assertion that failed once per item.  It fails once for the two
    sequences now, and `check()` answers with what the strict run raises.
    """

    def test_a_comparison_failing_on_two_items(self):
        subject, expected = [{"a": 1}, {"a": 2}], [{"a": 9}, {"a": 8}]
        with pytest.raises(AssertionError) as strict:
            assert_that(subject).is_equal_to(expected, ignore="b")
        outcome = assert_that(subject).check().is_equal_to(expected, ignore="b")
        assert_that(outcome.message).is_equal_to(strict.value._message).contains("<[{'a': 1}, {'a': 2}]>")
        assert_that([entry.path for entry in outcome.diff.entries]).is_equal_to(["[0].a", "[1].a"])


class TestTheReturnedRecordIsThePublicType:
    def test_it_is_the_exported_outcome(self):
        assert_that(assert_that(5).check().is_positive()).is_instance_of(AssertionOutcome)

    def test_a_non_callable_attribute_is_handed_straight_back(self):
        assert_that(assert_that(5).check().val).is_equal_to(5)
        assert_that(assert_that(5, "why").check().description).is_equal_to("why")

    @pytest.mark.parametrize("name", ["val", "value"])
    def test_a_callable_value_is_handed_back_as_the_value_and_is_not_called(self, name):
        calls = []

        def subject():
            calls.append(1)

        for proxy in (
            assert_that(subject).check(),
            assert_that(subject).check().not_,
            assert_that(subject).not_,
            assert_that([subject]).first().check(),
        ):
            assert_that(getattr(proxy, name)).is_same_as(subject)
        assert_that(calls).is_empty()

    @pytest.mark.parametrize("name", ["val", "value"])
    def test_a_value_that_is_itself_a_negation_is_handed_back_as_the_value(self, name):
        subject = assert_that(5).not_

        assert_that(getattr(assert_that(subject).check(), name)).is_same_as(subject)
        assert_that(getattr(assert_that(subject).check().not_, name)).is_same_as(subject)
