"""What each failure says was asked of the value, as data rather than as a sentence.

`expected` carries a different shape per family, the operand for `is_equal_to(2)`, a tuple for
`contains(2)`, a rendered description for `satisfies(...)`, a type for `is_instance_of(str)`, and
nothing at all for `is_empty()`.  A consumer grouping failures across a suite had to read English.
"""

from __future__ import annotations

import ast
import contextvars
import datetime
import functools
import itertools
import logging
import pathlib
import symtable

import pytest

from assertpy import (
    add_extension,
    assert_all,
    assert_conforms,
    assert_that,
    assert_warn,
    fail,
    match,
    remove_extension,
    soft_assertions,
    soft_fail,
)
from assertpy.assertpy import _ASSERTS, ASSERTPY_FILES, NegatedBuilder
from tests.optional import needs

_EARLIER = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
_LATER = datetime.datetime(2026, 1, 2, tzinfo=datetime.timezone.utc)


class TestWhatWasAsked:
    def test_the_operation_is_the_one_the_caller_wrote(self):
        assert_that(assert_that(1).check().is_equal_to(2).requirement.operation).is_equal_to("is_equal_to")

    def test_a_delegating_assertion_answers_its_own_name(self):
        """`is_positive()` asks `is_greater_than(0)` and `contains_key()` asks `contains()` underneath.

        The reader wants the assertion written in the test, so the answer is the outermost one of ours.
        """
        assert_that(assert_that(-1).check().is_positive().requirement.operation).is_equal_to("is_positive")
        assert_that(assert_that({"a": 1}).check().contains_key("b").requirement.operation).is_equal_to("contains_key")

    def test_an_assertion_inside_a_predicate_answers_itself(self):
        """A predicate passed to `satisfies()` is the caller's code, so the walk leaves us there."""

        def predicate(value):
            assert_that(value).is_greater_than(5)
            return True

        with pytest.raises(AssertionError) as caught:
            assert_that(1).satisfies(predicate)
        assert_that(caught.value.requirement.operation).is_equal_to("is_greater_than")

    def test_the_parameters_are_keyed_by_name(self):
        asked = assert_that(1).check().is_close_to(9, 0.1).requirement
        assert_that(asked.parameters).is_equal_to({"other": 9, "tolerance": 0.1, "rel": None})

    def test_two_spellings_of_one_call_read_the_same(self):
        """Bound values, not the call as written, so a consumer groups them as the one requirement."""
        positional = assert_that(1).check().is_close_to(9, 0.1).requirement
        by_keyword = assert_that(1).check().is_close_to(other=9, tolerance=0.1).requirement
        assert_that(positional).is_equal_to(by_keyword)

    def test_a_parameter_left_out_reads_as_its_default(self):
        asked = assert_that([2, 1]).check().is_sorted().requirement
        assert_that(asked.parameters).contains_entry({"reverse": False}).contains_key("key")

    def test_a_variadic_parameter_keeps_its_own_name(self):
        asked = assert_that([1]).check().contains(2, 3).requirement
        assert_that(asked.parameters).contains_entry({"items": (2, 3)})

    def test_an_assertion_that_takes_nothing_says_so(self):
        assert_that(assert_that([1]).check().is_empty().requirement.parameters).is_empty()

    def test_nothing_was_asked_when_the_caller_wrote_the_message(self):
        """`fail()` and a bare `error()` report no operation rather than inventing one."""
        with pytest.raises(AssertionError) as caught, soft_assertions():
            soft_fail("nothing in particular")
        assert_that(caught.value.failures[0].requirement).is_none()


class TestNegation:
    def test_a_negated_failure_says_it_was_negated(self):
        asked = assert_that(1).check().not_.is_equal_to(1).requirement
        assert_that(asked.negated).is_true()
        assert_that(asked.operation).is_equal_to("is_equal_to")

    def test_a_positive_failure_says_it_was_not(self):
        assert_that(assert_that(1).check().is_equal_to(2).requirement.negated).is_false()

    def test_the_negated_parameters_read_like_the_positive_ones(self):
        """Bound through the signature rather than off the stack, and the two have to agree."""
        positive = assert_that([1, 2]).check().is_sorted(reverse=True).requirement
        negated = assert_that([2, 1]).check().not_.is_sorted(reverse=True).requirement
        assert_that(negated.parameters).is_equal_to(positive.parameters)

    def test_a_callable_with_no_signature_still_names_what_was_asked(self):
        """`inspect.signature` refuses some C callables, and composing a failure must not raise instead."""
        asked = NegatedBuilder(assert_that(1))._asked(itertools.repeat, "repeat", 5, times=2)
        assert_that(asked.parameters).is_equal_to({"args": (5,), "kwargs": {"times": 2}})
        assert_that(asked.negated).is_true()


class TestEveryDeliveryCarriesTheSame:
    """The record is the same object on all four paths, so a consumer reads one shape everywhere."""

    def test_raising_and_check_agree(self):
        with pytest.raises(AssertionError) as caught:
            assert_that(1).is_equal_to(2)
        assert_that(caught.value.requirement).is_equal_to(assert_that(1).check().is_equal_to(2).requirement)

    def test_soft_agrees(self):
        with pytest.raises(AssertionError) as caught, soft_assertions():
            assert_that(1).is_equal_to(2)
        assert_that(caught.value.failures[0].requirement).is_equal_to(assert_that(1).check().is_equal_to(2).requirement)

    def test_a_polling_timeout_carries_the_assertion_that_kept_failing(self):
        """A timeout is that assertion's failure with a wait in front of it, so it answers that name."""
        with pytest.raises(AssertionError) as caught:
            assert_that(lambda: 1).eventually_sync(timeout=0.05, interval=0.01).is_equal_to(2)
        assert_that(caught.value.requirement.operation).is_equal_to("is_equal_to")

    def test_a_warn_mode_failure_reaches_the_same_composer(self, caplog):
        with caplog.at_level(logging.WARNING):
            assert_warn(1).is_equal_to(2)
        assert_that(caplog.text).contains("to be equal to")


def _raise_value_error():
    raise ValueError("not ready")


def _raise_bare_assertion():
    raise AssertionError("the probe's own check")


def _soft_block():
    with soft_assertions():
        assert_that(1).is_equal_to(2)


class TestNoSingleAssertionFailed:
    """`None` wherever the failure is not one assertion's, and the stability page names each such shape."""

    @pytest.mark.parametrize(
        "raising",
        [
            pytest.param(lambda: fail("mine"), id="fail"),
            pytest.param(lambda: assert_that(1).error("mine"), id="bare-error"),
            pytest.param(
                lambda: assert_that(_raise_value_error).raises(ValueError).when_called_with().errors(),
                id="errors-precondition",
            ),
        ],
    )
    def test_no_operation_is_named(self, raising):
        with pytest.raises(AssertionError) as caught:
            raising()
        assert_that(caught.value.requirement).is_none()

    @pytest.mark.parametrize(
        "gathering",
        [
            pytest.param(_soft_block, id="soft-block"),
            pytest.param(lambda: assert_all(lambda: assert_that(1).is_equal_to(2)), id="assert-all"),
        ],
    )
    def test_a_failure_gathering_others_leaves_it_to_each(self, gathering):
        with pytest.raises(AssertionError) as caught:
            gathering()
        assert_that(caught.value.requirement).is_none()
        assert_that([entry.requirement.operation for entry in caught.value.failures]).is_equal_to(["is_equal_to"])

    @pytest.mark.parametrize(
        "polling",
        [
            pytest.param(
                lambda: (
                    assert_that(_raise_value_error).eventually_sync(timeout=0.05, interval=0.01).ignoring(ValueError)
                ),
                id="ignored-exception",
            ),
            pytest.param(
                lambda: assert_that(_raise_bare_assertion).eventually_sync(timeout=0.05, interval=0.01),
                id="bare-assertion-error",
            ),
        ],
    )
    def test_a_timeout_whose_probe_raised_names_nothing(self, polling):
        with pytest.raises(AssertionError) as caught:
            polling().is_equal_to(2)
        assert_that(caught.value.requirement).is_none()

    def test_a_timeout_whose_probe_asserted_names_that_assertion(self):
        """Whatever the last attempt raised, so an assertion inside the probe answers instead of the chain's."""

        def probe():
            assert_that(1).is_equal_to(3)

        with pytest.raises(AssertionError) as caught:
            assert_that(probe).eventually_sync(timeout=0.05, interval=0.01).is_equal_to(2)
        assert_that(caught.value.requirement.parameters).contains_entry({"other": 3})


class TestTheSurfacesThatNameThemselves:
    def test_a_dynamic_assertion_names_the_attribute(self):
        asked = assert_that({"a": 1}).check().has_a(2).requirement
        assert_that(asked.operation).is_equal_to("has_a")
        assert_that(asked.parameters).is_equal_to({"other": 2})

    def test_a_dynamic_assertion_on_a_missing_attribute_names_it_too(self):
        asked = assert_that({"a": 1}).check().has_b(2).requirement
        assert_that(asked.operation).is_equal_to("has_b")

    def test_an_extension_names_itself(self):
        def is_a_perfect_square(self):
            root = int(self.val**0.5)
            if root * root != self.val:
                return self.error(f"Expected <{self.val}> to be a perfect square.")
            return self

        add_extension(is_a_perfect_square)
        try:
            asked = assert_that(3).check().is_a_perfect_square().requirement
            assert_that(asked.operation).is_equal_to("is_a_perfect_square")
        finally:
            remove_extension(is_a_perfect_square)

    def test_a_module_level_assertion_names_itself(self):
        """The one assertion that is a module function, so no frame of ours holds a builder."""
        pydantic = needs("pydantic")

        class Order(pydantic.BaseModel):
            total: int

        with pytest.raises(AssertionError) as caught:
            assert_conforms({"total": "not a number"}, Order)
        assert_that(caught.value.requirement.operation).is_equal_to("assert_conforms")


def _corpus():
    """A failing call per family, wide enough that a walk answering by accident cannot pass it.

    Hand-written because a failing call cannot be derived: every assertion needs operands of its own.
    `test_the_corpus_is_wide_enough` keeps it from quietly shrinking to the cases that happen to work.
    """
    return [
        ("is_equal_to", lambda: assert_that(1).check().is_equal_to(2)),
        ("is_not_equal_to", lambda: assert_that(1).check().is_not_equal_to(1)),
        ("is_same_as", lambda: assert_that([1]).check().is_same_as([1])),
        ("is_true", lambda: assert_that(False).check().is_true()),
        ("is_none", lambda: assert_that(1).check().is_none()),
        ("is_not_none", lambda: assert_that(None).check().is_not_none()),
        ("is_type_of", lambda: assert_that(1).check().is_type_of(str)),
        ("is_instance_of", lambda: assert_that(1).check().is_instance_of(str)),
        ("is_length", lambda: assert_that("abc").check().is_length(9)),
        ("contains", lambda: assert_that([1]).check().contains(2)),
        ("contains_only", lambda: assert_that([1, 2]).check().contains_only(1)),
        ("does_not_contain", lambda: assert_that([1]).check().does_not_contain(1)),
        ("contains_duplicates", lambda: assert_that([1, 2]).check().contains_duplicates()),
        ("is_empty", lambda: assert_that([1]).check().is_empty()),
        ("is_not_empty", lambda: assert_that([]).check().is_not_empty()),
        ("is_in", lambda: assert_that(1).check().is_in(2, 3)),
        ("is_not_in", lambda: assert_that(1).check().is_not_in(1, 2)),
        ("is_greater_than", lambda: assert_that(1).check().is_greater_than(2)),
        ("is_between", lambda: assert_that(1).check().is_between(5, 9)),
        ("is_close_to", lambda: assert_that(1).check().is_close_to(9, 0.1)),
        ("is_positive", lambda: assert_that(-1).check().is_positive()),
        ("is_nan", lambda: assert_that(1.0).check().is_nan()),
        ("is_even", lambda: assert_that(3).check().is_even()),
        ("starts_with", lambda: assert_that("abc").check().starts_with("z")),
        ("ends_with", lambda: assert_that("abc").check().ends_with("z")),
        ("matches", lambda: assert_that("abc").check().matches(r"^z")),
        ("is_alpha", lambda: assert_that("1").check().is_alpha()),
        ("is_upper", lambda: assert_that("abc").check().is_upper()),
        ("contains_ignoring_case", lambda: assert_that("abc").check().contains_ignoring_case("Z")),
        ("is_unicode", lambda: assert_that(b"x").check().is_unicode()),
        ("contains_key", lambda: assert_that({"a": 1}).check().contains_key("b")),
        ("contains_value", lambda: assert_that({"a": 1}).check().contains_value(2)),
        ("contains_entry", lambda: assert_that({"a": 1}).check().contains_entry({"a": 2})),
        ("satisfies", lambda: assert_that(1).check().satisfies(match.greater_than(5))),
        ("all_satisfy", lambda: assert_that([1]).check().all_satisfy(match.greater_than(5))),
        ("any_satisfy", lambda: assert_that([1]).check().any_satisfy(match.greater_than(5))),
        ("satisfies_exactly", lambda: assert_that([1]).check().satisfies_exactly(match.greater_than(5))),
        ("is_sorted", lambda: assert_that([2, 1]).check().is_sorted()),
        ("is_subset_of", lambda: assert_that([1, 9]).check().is_subset_of([1, 2])),
        ("has_same_size_as", lambda: assert_that([1]).check().has_same_size_as([1, 2])),
        ("exists", lambda: assert_that(pathlib.Path("no-such-file.txt")).check().exists()),
        ("is_before", lambda: assert_that(_LATER).check().is_before(_EARLIER)),
        ("is_callable", lambda: assert_that(1).check().is_callable()),
        ("is_iterable", lambda: assert_that(1).check().is_iterable()),
    ]


@pytest.mark.parametrize(("name", "call"), _corpus(), ids=[name for name, _ in _corpus()])
def test_every_family_names_the_assertion_that_failed(name, call):
    """The walk reads a stack, so what holds it is a run rather than a reading of the source."""
    asked = call().requirement
    assert_that(asked).described_as(f"what {name}() said was asked").is_not_none()
    assert_that(asked.operation).is_equal_to(name)


def test_the_corpus_is_wide_enough():
    """A corpus that shrank to the easy cases would agree with every claim above it."""
    covered = {name for name, _ in _corpus()}
    assert_that(covered).described_as("families the corpus covers").is_length_between(40, 200)


def test_a_call_the_signature_refuses_still_names_what_was_asked():
    """The guard for a call the assertion took and `bind()` would not: composing must not raise instead."""
    builder = assert_that(1)
    asked = NegatedBuilder(builder)._asked(builder.is_close_to, "is_close_to", 1, 2, 3, 4)
    assert_that(asked.operation).is_equal_to("is_close_to")
    assert_that(asked.parameters).is_equal_to({"args": (1, 2, 3, 4), "kwargs": {}})


class TestExtensionsNameThemselves:
    """Not read off the stack: a frame cannot be tied back to a registration.

    Two instances of one callable class share `__call__`'s code, two functions from one decorator
    factory share the wrapper's, and a `functools.partial` runs no Python frame of its own.
    """

    def test_an_extension_that_delegates_still_answers_its_own_name(self):
        def is_custom(self):
            return self.is_positive()

        add_extension(is_custom)
        try:
            assert_that(assert_that(-1).check().is_custom().requirement.operation).is_equal_to("is_custom")
        finally:
            remove_extension(is_custom)

    def test_a_callable_object_extension_names_itself_and_drops_both_receivers(self):
        class Judge:
            __name__ = "is_judged"

            def __call__(self, builder, threshold):
                if builder.val < threshold:
                    return builder.error(f"Expected <{builder.val}> to reach {threshold}.")
                return builder

        judge = Judge()
        add_extension(judge)
        try:
            asked = assert_that(1).check().is_judged(5).requirement
            assert_that(asked.operation).is_equal_to("is_judged")
            assert_that(asked.parameters).is_equal_to({"threshold": 5})
        finally:
            remove_extension(judge)

    def test_a_decorated_extension_answers_the_name_it_was_registered_under(self):
        def announced(func):
            @functools.wraps(func)
            def wrapper(self, *args, **kwargs):
                return func(self, *args, **kwargs)

            return wrapper

        @announced
        def is_worth_it(self, floor):
            if self.val < floor:
                return self.error(f"Expected <{self.val}> to clear {floor}.")
            return self

        add_extension(is_worth_it)
        try:
            assert_that(assert_that(1).check().is_worth_it(5).requirement.operation).is_equal_to("is_worth_it")
        finally:
            remove_extension(is_worth_it)

    def test_an_ordinary_assertion_beside_a_registered_extension_is_not_claimed(self):
        """The name is set for the length of the extension's call and no longer."""

        def is_shadowed(self):
            return self.is_positive()

        add_extension(is_shadowed)
        try:
            assert_that(assert_that(1).check().is_equal_to(2).requirement.operation).is_equal_to("is_equal_to")
        finally:
            remove_extension(is_shadowed)

    def test_an_extension_that_calls_another_answers_the_one_the_caller_wrote(self):
        """The same rule a built-in follows: `is_positive()` reports itself, not `is_greater_than()`."""

        def is_inner(self):
            return self.error(f"Expected <{self.val}> to be something else.")

        def is_outer(self):
            return self.is_inner()

        add_extension(is_inner)
        add_extension(is_outer)
        try:
            assert_that(assert_that(1).check().is_outer().requirement.operation).is_equal_to("is_outer")
        finally:
            remove_extension(is_outer)
            remove_extension(is_inner)

    def test_an_extension_whose_signature_cannot_be_read_still_names_itself(self):
        """The name comes from the registration, so only its parameters depend on introspection."""

        def is_variadic(*args):
            return args[0].error("variadic")

        is_variadic.__name__ = "is_variadic"
        add_extension(is_variadic)
        try:
            asked = assert_that(1).check().is_variadic(7).requirement
            assert_that(asked.operation).is_equal_to("is_variadic")
            assert_that(asked.parameters).described_as("the builder is not an argument").does_not_contain_key("self")
        finally:
            remove_extension(is_variadic)

    def test_an_extension_whose_signature_cannot_be_read_at_all_names_itself(self):
        """`__signature__` set to something `inspect` refuses, which some libraries really do."""

        class Odd:
            __name__ = "is_odd_shape"
            __signature__ = "not a signature"

            def __call__(self, builder):
                return builder.error(f"Expected <{builder.val}> to be otherwise.")

        odd = Odd()
        add_extension(odd)
        try:
            asked = assert_that(1).check().is_odd_shape().requirement
            assert_that(asked.operation).is_equal_to("is_odd_shape")
            assert_that(asked.parameters).is_equal_to({"args": (), "kwargs": {}})
        finally:
            remove_extension(odd)

    def test_a_partial_extension_names_itself(self):
        """A `functools.partial` runs no Python frame of its own, which a stack read could not see."""

        def is_over(self, floor):
            return self.error(f"Expected <{self.val}> over {floor}.") if self.val < floor else self

        over_five = functools.partial(is_over, floor=5)
        over_five.__name__ = "is_over_five"
        add_extension(over_five)
        try:
            assert_that(assert_that(1).check().is_over_five().requirement.operation).is_equal_to("is_over_five")
        finally:
            remove_extension(over_five)

    def test_two_instances_of_one_callable_class_stay_apart(self):
        """They share one `__call__` code object, so anything keyed by code would confuse the two."""

        class AtLeast:
            def __init__(self, name, floor):
                self.__name__ = name
                self.floor = floor

            def __call__(self, builder):
                return builder.error(f"Expected <{builder.val}> to reach {self.floor}.")

        first, second = AtLeast("is_at_least_five", 5), AtLeast("is_at_least_nine", 9)
        add_extension(first)
        add_extension(second)
        try:
            assert_that(assert_that(1).check().is_at_least_five().requirement.operation).is_equal_to("is_at_least_five")
            assert_that(assert_that(1).check().is_at_least_nine().requirement.operation).is_equal_to("is_at_least_nine")
        finally:
            remove_extension(first)
            remove_extension(second)


class TestTheTwoCapturesAgree:
    """One is read off the frame and the other bound from the signature, so they are held to each other."""

    @pytest.mark.parametrize(
        ("name", "value", "args", "kwargs"),
        [
            ("is_equal_to", 1, (2,), {}),
            ("is_greater_than", 1, (2,), {}),
            ("is_between", 1, (5, 9), {}),
            ("is_close_to", 1, (9, 0.1), {}),
            ("is_length", "abc", (9,), {}),
            ("contains", [1], (2,), {}),
            ("is_in", 1, (2, 3), {}),
            ("starts_with", "abc", ("z",), {}),
            ("matches", "abc", (r"^z",), {}),
            ("contains_key", {"a": 1}, ("b",), {}),
            ("contains_entry", {"a": 1}, ({"a": 2},), {}),
            ("is_sorted", [2, 1], (), {}),
            ("is_sorted", [1, 2], (), {"reverse": True}),
            ("is_instance_of", 1, (str,), {}),
            ("is_empty", [1], (), {}),
            ("is_positive", -1, (), {}),
        ],
    )
    def test_the_frame_and_the_signature_read_the_same(self, name, value, args, kwargs):
        positive = getattr(assert_that(value).check(), name)(*args, **kwargs).requirement
        negated = NegatedBuilder(assert_that(value))._asked(getattr(assert_that(value), name), name, *args, **kwargs)
        assert_that(dict(negated.parameters)).described_as(f"{name} bound from its signature").is_equal_to(
            dict(positive.parameters)
        )


class TestAnExtensionAnswersOnlyForItsOwnValue:
    """The name belongs to a call, not to everything that runs while it is on the stack."""

    def test_an_assertion_about_another_value_answers_itself(self):
        """Exactly as an assertion inside a `satisfies()` predicate does."""

        def is_paired_with_five(self):
            return assert_that(self.val + 1).check().is_equal_to(5)

        add_extension(is_paired_with_five)
        try:
            assert_that(assert_that(1).is_paired_with_five().requirement.operation).is_equal_to("is_equal_to")
        finally:
            remove_extension(is_paired_with_five)

    def test_a_pivot_inside_an_extension_answers_the_assertion_after_it(self):
        def is_first_item_five(self):
            return self.builder(self.val[0]).check().is_equal_to(5)

        add_extension(is_first_item_five)
        try:
            assert_that(assert_that([1]).is_first_item_five().requirement.operation).is_equal_to("is_equal_to")
        finally:
            remove_extension(is_first_item_five)

    def test_the_extension_still_answers_for_the_builder_it_was_called_on(self):
        def is_never_happy(self):
            return self.error(f"Expected <{self.val}> to be otherwise.")

        add_extension(is_never_happy)
        try:
            assert_that(assert_that(1).check().is_never_happy().requirement.operation).is_equal_to("is_never_happy")
        finally:
            remove_extension(is_never_happy)

    def test_a_nested_extension_on_another_value_answers_itself(self):
        """Skipping registration whenever any extension was running left this one unnamed."""

        def is_inner_unhappy(self):
            return self.error(f"Expected <{self.val}> to be otherwise.")

        def is_outer_delegating(self):
            return assert_that(self.val + 1).check().is_inner_unhappy()

        add_extension(is_inner_unhappy)
        add_extension(is_outer_delegating)
        try:
            asked = assert_that(1).is_outer_delegating().requirement
            assert_that(asked.operation).is_equal_to("is_inner_unhappy")
        finally:
            remove_extension(is_outer_delegating)
            remove_extension(is_inner_unhappy)

    def test_a_failure_after_the_call_returned_is_not_claimed(self):
        """A task started inside the call inherits the context and never sees the reset."""
        escaped = {}

        def is_escaping(self):
            escaped["builder"] = self
            escaped["context"] = contextvars.copy_context()
            return self

        add_extension(is_escaping)
        try:
            assert_that(1).is_escaping()
            later = escaped["context"].run(lambda: escaped["builder"].check().is_equal_to(2))
            assert_that(later.requirement.operation).described_as("named after the call ended").is_equal_to(
                "is_equal_to"
            )
        finally:
            remove_extension(is_escaping)

    def test_an_extension_that_negates_still_answers_its_own_name(self):
        """The negated proxy says what it is, and a live extension on the same builder outranks it."""

        def is_never_itself(self):
            return self.not_.is_equal_to(self.val)

        add_extension(is_never_itself)
        try:
            asked = assert_that(1).check().is_never_itself().requirement
            assert_that(asked.operation).is_equal_to("is_never_itself")
            assert_that(asked.negated).described_as("the extension was not asked negated").is_false()
        finally:
            remove_extension(is_never_itself)

    def test_an_extension_that_asks_a_dynamic_assertion_answers_its_own_name(self):
        def is_shaped(self):
            return self.has_missing_field(1)

        add_extension(is_shaped)
        try:
            assert_that(assert_that({"a": 1}).check().is_shaped().requirement.operation).is_equal_to("is_shaped")
        finally:
            remove_extension(is_shaped)


def _read_off_the_frame(function):
    """The parameters `_bound_parameters` reads: all declared ones but the first, which is the receiver."""
    arguments = function.args
    named = [*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs][1:]
    return {argument.arg for argument in [*named, arguments.vararg, arguments.kwarg] if argument is not None}


def _rebound_by_closure(table, names):
    """Parameters a nested scope rebinds through `nonlocal`, which the enclosing scope's own flags do not show."""
    for child in table.get_children():
        for name in names & set(child.get_identifiers()):
            if child.lookup(name).is_nonlocal() and child.lookup(name).is_assigned():
                yield name
        yield from _rebound_by_closure(child, names)


def _function_tables(table):
    for child in table.get_children():
        if isinstance(child, symtable.Function):
            yield child
        yield from _function_tables(child)


class TestTheFrameReadsWhatWasPassed:
    """The stack is read when the failure is composed, so a parameter answers with its value at that moment.

    An assertion that rebinds one before failing reports its own copy, while `not_`, bound through the
    signature, reports the caller's. `conforms_to_openapi` did, with the spec it normalised to string keys.

    So it is a source rule rather than a proof: no assertion rebinds a parameter the frame reads, in its own
    scope or through a closure, not even to the same object, because the frame cannot tell `spec = spec`
    from `spec = copy(spec)`.
    """

    def test_no_assertion_rebinds_a_parameter_the_frame_reads(self):
        """The compiler's symbol table says what a scope binds, a walrus in a comprehension and `import as` included."""
        rebound, unmatched, checked = [], [], set()
        for filename in sorted(ASSERTPY_FILES):
            source = pathlib.Path(filename).read_text(encoding="utf-8")
            read = {
                (function.name, function.lineno): _read_off_the_frame(function)
                for function in ast.walk(ast.parse(source))
                if isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)) and function.name in _ASSERTS
            }
            tables = {
                (table.get_name(), table.get_lineno()): table
                for table in _function_tables(symtable.symtable(source, filename, "exec"))
            }
            checked |= {name for name, _ in read}
            for (name, lineno), names in read.items():
                table = tables.get((name, lineno))
                if table is None:
                    unmatched.append(f"{pathlib.Path(filename).name}:{lineno} {name}")
                    continue
                rebound += [
                    f"{pathlib.Path(filename).name}:{lineno} {name}({parameter})"
                    for parameter in sorted(names)
                    if table.lookup(parameter).is_assigned() or table.lookup(parameter).is_imported()
                ]
                rebound += [
                    f"{pathlib.Path(filename).name}:{lineno} {name}({parameter}, through a closure)"
                    for parameter in sorted(set(_rebound_by_closure(table, names)))
                ]
        assert_that(sorted(_ASSERTS - checked)).described_as("assertions with no definition checked").is_empty()
        assert_that(unmatched).described_as("assertions the symbol table did not place, left unchecked").is_empty()
        assert_that(rebound).is_empty()
