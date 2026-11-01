import pytest

from assertpy import AssertionOutcome, assert_that, assert_warn, soft_assertions


def _inert_builder():
    """The proxy a failed `raises(...)` hands back under warn mode, where the chain goes on absorbing."""

    def boom() -> int:
        raise ValueError("x")

    return assert_warn(boom).raises(TypeError).when_called_with()


class TestValue:
    def test_value_returns_the_original_object(self):
        payload = {"a": 1}
        assert_that(assert_that(payload).value).is_same_as(payload)

    def test_value_after_passing_chain(self):
        assert_that(assert_that("foo").is_length(3).starts_with("f").value).is_equal_to("foo")

    def test_value_after_narrowing_assertions(self):
        order = {"status": "PAID"}
        assert_that(assert_that(order).is_not_none().is_instance_of(dict).value).is_same_as(order)

    def test_value_after_extracting_pivot(self):
        assert_that(assert_that([{"a": 1}, {"a": 2}]).extracting("a").value).is_equal_to([1, 2])

    def test_value_after_decoded_as_pivot(self):
        assert_that(assert_that(b"hi").decoded_as().value).is_equal_to("hi")

    def test_satisfies_with_typeis_predicate_runs_as_a_normal_predicate(self):
        class Order: ...

        class PaidOrder(Order): ...

        def is_paid(order):
            return isinstance(order, PaidOrder)

        paid = PaidOrder()
        assert_that(assert_that(paid).satisfies(is_paid).value).is_same_as(paid)
        with pytest.raises(AssertionError):
            assert_that(Order()).satisfies(is_paid)

    def test_value_passing_chain_in_soft_block_still_works(self):
        with soft_assertions():
            got = assert_that("foo").is_not_none().value
        assert_that(got).is_equal_to("foo")

    def test_value_after_failed_soft_assertion_raises_carrying_root_failure(self):
        # extract-and-continue is incoherent under collect-and-continue: refuse loudly and surface the cause
        with pytest.raises(TypeError) as exc, soft_assertions():
            _ = assert_that(None).is_not_none().value
        message = str(exc.value)
        assert_that(message).contains("cannot extract .value").contains("Expected not <None>, but was.")

    def test_taint_reason_is_the_root_failure_not_the_consequent(self):
        with pytest.raises(TypeError) as exc, soft_assertions():
            _ = assert_that(None).is_not_none().is_instance_of(str).value
        message = str(exc.value)
        assert_that(message).contains("Expected not <None>, but was.").does_not_contain("instance of class")

    def test_taint_covers_any_failed_assertion_not_only_narrowing(self):
        # extract only what was established: a failed `is_greater_than` taints `.value` as a failed `is_not_none` would
        with pytest.raises(TypeError, match=r"cannot extract .value.*to be greater than"), soft_assertions():
            _ = assert_that(3).is_greater_than(10).value

    def test_value_after_failed_warn_assertion_raises(self):
        with pytest.raises(TypeError, match=r"cannot extract .value"):
            _ = assert_warn(None).is_not_none().value

    @pytest.mark.parametrize("name", ["value", "val"])
    def test_an_inert_builder_refuses_the_value_rather_than_absorbing_it(self, name):
        """The defect this whole family is: an absorbing proxy answering an accessor with its lambda.

        Both names are declared as data on the typed surface, one by the builder and one by a polling
        chain, and every lambda is truthy, so reading either looked like a value that had been checked.
        Stated over the names rather than one at a time, since the proxy absorbs by default and a new
        accessor arrives absorbed.
        """
        with pytest.raises(TypeError) as refused:
            getattr(_inert_builder(), name)
        assert_that(str(refused.value)).described_as(f"why {name} is refused").contains("soft or warn mode").contains(
            "to raise <TypeError>"
        )

    def test_an_inert_builder_answers_a_verdict_carrying_the_failure_that_made_it_inert(self):
        """`check()` promises a verdict rather than a raise, so it answers with the failure it has.

        Absorbed, it handed back the proxy itself, whose `passed` is the absorbing lambda: declared
        `bool` and truthy, so a failed chain read as a pass.
        """
        outcome = _inert_builder().check().is_equal_to(1)
        assert_that(outcome).is_instance_of(AssertionOutcome)
        assert_that(outcome.passed).described_as("a chain that already failed").is_false()
        assert_that(outcome.message).described_as("the failure that made it inert").contains("to raise <TypeError>")

    def test_val_on_an_inert_chain_refuses_the_way_value_does(self):
        # a polling chain declares `val` where the builder declares `value`, and an inert builder
        # absorbed it: the typed accessor handed back the absorbing lambda instead of the value
        def never() -> str | None:
            return None

        with pytest.raises(TypeError, match=r"cannot extract .val"), soft_assertions():
            _ = assert_that(never).eventually_sync(timeout=0.02, interval=0.01).is_not_none().val

    def test_val_on_a_chain_that_passed_still_hands_the_value_back(self):
        got = assert_that(lambda: "ready").eventually_sync(timeout=0.5, interval=0.01).is_not_none().val
        assert_that(got).is_equal_to("ready")

    def test_taint_is_per_value_pivot_washes_orthogonal_failure(self):
        # the taint is per-value: after a failed orthogonal assertion a real sub-value still extracts cleanly
        captured = []
        with pytest.raises(AssertionError, match="soft assertion failures"), soft_assertions():
            captured.append(assert_that([{"a": 1}]).is_length(9).extracting("a").value)
        assert_that(captured).is_equal_to([[1]])

    def test_pivot_after_failed_is_not_none_raises_in_the_pivot_not_at_value(self):
        # a pivot cannot reach `.value` from an unvalidated None: it raises in the pivot's own input check first
        with pytest.raises(TypeError, match="val must be iterable"), soft_assertions():
            _ = assert_that(None).is_not_none().extracting("total").value

    def test_strict_value_is_never_tainted(self):
        assert_that(assert_that(5).is_greater_than(0).value).is_equal_to(5)


def test_fmt_items_empty(builder):
    assert_that(builder._fmt_items([])).is_equal_to("<>")


def test_fmt_items_single(builder):
    assert_that(builder._fmt_items([1])).is_equal_to("<1>")
    assert_that(builder._fmt_items(["foo"])).is_equal_to("<foo>")
    assert_that(builder._fmt_items([("bar", "baz")])).is_equal_to("<('bar', 'baz')>")


def test_fmt_items_multiple(builder):
    assert_that(builder._fmt_items([1, 2, 3])).is_equal_to("<1, 2, 3>")
    assert_that(builder._fmt_items(["a", "b", "c"])).is_equal_to("<'a', 'b', 'c'>")


def test_fmt_args_kwargs_empty(builder):
    assert_that(builder._fmt_args_kwargs()).is_equal_to("")


def test_fmt_args_kwargs_single_arg(builder):
    assert_that(builder._fmt_args_kwargs(1)).is_equal_to("1")
    assert_that(builder._fmt_args_kwargs("foo")).is_equal_to("'foo'")


def test_fmt_args_kwargs_multiple_args(builder):
    assert_that(builder._fmt_args_kwargs(1, 2, 3)).is_equal_to("1, 2, 3")
    assert_that(builder._fmt_args_kwargs("a", "b", "c")).is_equal_to("'a', 'b', 'c'")


def test_fmt_args_kwargs_single_kwarg(builder):
    assert_that(builder._fmt_args_kwargs(a=1)).is_equal_to("'a': 1")
    assert_that(builder._fmt_args_kwargs(f="foo")).is_equal_to("'f': 'foo'")


def test_fmt_args_kwargs_multiple_kwargs(builder):
    assert_that(builder._fmt_args_kwargs(a=1, b=2, c=3)).is_equal_to("'a': 1, 'b': 2, 'c': 3")
    assert_that(builder._fmt_args_kwargs(a="a", b="b", c="c")).is_equal_to("'a': 'a', 'b': 'b', 'c': 'c'")


def test_fmt_args_kwargs_multiple_both(builder):
    assert_that(builder._fmt_args_kwargs(1, 2, 3, a=4, b=5, c=6)).is_equal_to("1, 2, 3, 'a': 4, 'b': 5, 'c': 6")
    assert_that(builder._fmt_args_kwargs("a", "b", "c", d="g", e="h", f="i")).is_equal_to(
        "'a', 'b', 'c', 'd': 'g', 'e': 'h', 'f': 'i'"
    )


def test_check_dict_like_empty_dict(builder):
    # the old form asserted nothing: the method returns None and reports by raising, so it passed whatever it did
    assert_that(builder._require_dict_like).does_not_raise(TypeError).when_called_with({})


def test_check_dict_like_not_iterable(builder):
    assert_that(builder._require_dict_like).raises(TypeError).when_called_with(123).is_equal_to(
        "val must be dict-like (this one is not iterable), but was <123> (int)"
    )


def test_check_dict_like_missing_keys(builder):
    assert_that(builder._require_dict_like).raises(TypeError).when_called_with("foo").is_equal_to(
        "val must be dict-like (this one has no keys()), but was <'foo'> (str)"
    )


def test_check_dict_like_bool(builder):
    assert_that(builder._is_dict_like({})).is_true()
    assert_that(builder._is_dict_like(123)).is_false()
    assert_that(builder._is_dict_like("foo")).is_false()
