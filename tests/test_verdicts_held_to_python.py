"""Verdicts that were false, each held to what Python or the assertion of the same name says.

A list passed for a tuple under a key option, a file for its own child, an empty prefix for every text.  A NaN the
value holds was not found by two of the sequence assertions, a path of no keys raised `IndexError`, and a key left
out under `strict_types` still failed the pair it was left out of.
"""

from __future__ import annotations

import asyncio
import datetime
import gc
import warnings
from typing import TYPE_CHECKING

import pytest

from assertpy import AssertionFailure, assert_that, match
from assertpy._engine._equality import key_specs_given, normalize_key_specs
from assertpy.contains import _sequence_break

if TYPE_CHECKING:
    import pathlib


def _passes(check) -> bool:
    try:
        check()
    except AssertionFailure:
        return False
    return True


class TestAListIsNoTupleUnderAKeyOption:
    @pytest.mark.parametrize(
        "option",
        [{"ignore": "b"}, {"include": "a"}, {"ignore": "b", "tolerance": 0.5}],
        ids=["ignore", "include", "ignore-and-tolerance"],
    )
    @pytest.mark.parametrize(
        ("held", "wanted"),
        [([{"a": 1}], ({"a": 1},)), (({"a": 1},), [{"a": 1}]), ([1, 2], (1, 2)), ([], ())],
        ids=["records", "tuple-first", "scalars", "empty"],
    )
    def test_it_fails_as_it_does_with_no_option(self, option, held, wanted):
        assert_that(held == wanted).is_false()
        assert_that(_passes(lambda: assert_that(held).is_equal_to(wanted, **option))).is_false()
        assert_that(match.equal_to(wanted, **option).matches(held)).is_false()
        assert_that(assert_that(held).check().is_equal_to(wanted, **option).passed).is_false()
        assert_that(held).not_.is_equal_to(wanted, **option)

    @pytest.mark.parametrize(
        ("held", "wanted"),
        [([{"a": 1, "b": 2}], [{"a": 1, "b": 9}]), (({"a": 1, "b": 2},), ({"a": 1, "b": 9},))],
        ids=["two-lists", "two-tuples"],
    )
    def test_two_of_one_kind_are_still_compared_by_what_is_kept(self, held, wanted):
        assert_that(held).is_equal_to(wanted, ignore="b")
        assert_that(match.equal_to(wanted, ignore="b").matches(held)).is_true()
        assert_that(_passes(lambda: assert_that(held).is_equal_to(wanted, ignore="a"))).is_false()

    def test_a_list_of_a_class_of_its_own_is_a_list(self):
        rows = type("Rows", (list,), {})
        assert_that(_passes(lambda: assert_that(rows([1, 2])).is_equal_to((1, 2), ignore="b"))).is_false()
        assert_that(rows([{"a": 1, "b": 2}])).is_equal_to([{"a": 1, "b": 9}], ignore="b")

    def test_a_list_whose_own_equality_takes_a_tuple_keeps_taking_it(self):
        taking = type("Taking", (list,), {"__eq__": lambda self, other: list(self) == list(other), "__hash__": None})
        assert_that(taking([1, 2]) == (1, 2)).is_true()
        assert_that(taking([1, 2])).is_equal_to((1, 2), ignore="b")
        assert_that((1, 2)).is_equal_to(taking([1, 2]), ignore="b")
        assert_that(match.equal_to((1, 2), ignore="b").matches(taking([1, 2]))).is_true()
        assert_that(match.equal_to(taking([1, 2]), ignore="b").matches((1, 2))).is_true()


class TestAFileIsNoChildOfItself:
    def test_a_file_named_as_its_own_parent_fails(self, tmp_path: pathlib.Path):
        held = tmp_path / "held.txt"
        held.write_text("x", encoding="utf-8")
        assert_that(_passes(lambda: assert_that(str(held)).is_child_of(str(held)))).is_false()
        assert_that(_passes(lambda: assert_that(held).is_child_of(held))).is_false()
        assert_that(str(held)).is_child_of(str(tmp_path))
        assert_that(held).is_child_of(tmp_path.parent)


class TestAMatcherRefusesWhatEveryTextHolds:
    @pytest.mark.parametrize(
        ("build", "named"),
        [
            (lambda: match.starts_with(""), "prefix"),
            (lambda: match.starts_with(b""), "prefix"),
            (lambda: match.starts_with(bytearray()), "prefix"),
            (lambda: match.ends_with(""), "suffix"),
            (lambda: match.ends_with(b""), "suffix"),
            (lambda: match.matches_regex(""), "pattern"),
        ],
        ids=["prefix", "bytes-prefix", "bytearray-prefix", "suffix", "bytes-suffix", "pattern"],
    )
    def test_an_empty_argument_is_refused_where_it_is_written(self, build, named):
        assert_that(build).raises(ValueError).when_called_with().is_equal_to(f"given {named} arg must not be empty")

    @pytest.mark.parametrize(
        ("ask", "named"),
        [
            (lambda: assert_that("foo").starts_with(""), "prefix"),
            (lambda: assert_that("foo").ends_with(""), "suffix"),
            (lambda: assert_that("foo").matches(""), "pattern"),
        ],
        ids=["prefix", "suffix", "pattern"],
    )
    def test_in_the_words_of_the_assertion_of_the_same_name(self, ask, named):
        assert_that(ask).raises(ValueError).when_called_with().is_equal_to(f"given {named} arg must not be empty")

    @pytest.mark.parametrize(
        "build",
        [
            lambda: match.starts_with(type("Text", (str,), {})("")),
            lambda: match.ends_with(type("Raw", (bytes,), {})(b"")),
            lambda: match.starts_with(type("Grown", (bytearray,), {})()),
            lambda: match.matches_regex(type("Text", (str,), {})("")),
        ],
        ids=["str", "bytes", "bytearray", "pattern"],
    )
    def test_an_empty_text_of_a_class_of_its_own_is_refused_too(self, build):
        assert_that(build).raises(ValueError).when_called_with().ends_with("arg must not be empty")

    def test_what_is_not_empty_is_taken_as_before(self):
        assert_that("foobar").satisfies(match.starts_with("foo") & match.ends_with("bar") & match.matches_regex("ob"))
        assert_that(b"foobar").satisfies(match.starts_with(b"foo") & match.ends_with(bytearray(b"bar")))

    @pytest.mark.parametrize(
        ("build", "named", "shown"),
        [
            (lambda: match.starts_with(5), "prefix", "<5> (int)"),
            (lambda: match.starts_with([1]), "prefix", "<[1]> (list)"),
            (lambda: match.ends_with(None), "suffix", "<None> (NoneType)"),
            (lambda: match.ends_with(memoryview(b"x")), "suffix", None),
            (lambda: match.contains_string(["a"]), "substring", "<['a']> (list)"),
        ],
        ids=["int-prefix", "list-prefix", "none-suffix", "memoryview-suffix", "list-substring"],
    )
    def test_what_no_text_starts_ends_or_holds_is_refused_where_it_is_written(self, build, named, shown):
        """A list or a number built a matcher that matched nothing at all and said nothing about why."""
        said = assert_that(build).raises(TypeError).when_called_with().value
        assert_that(said).starts_with(f"given {named} arg must be a string or bytes, but was ")
        if shown is not None:
            assert_that(said).ends_with(shown)

    @pytest.mark.parametrize("delta", [float("inf"), float("nan"), 1e20], ids=["inf", "nan", "past-a-timedelta"])
    def test_a_delta_no_timedelta_holds_is_refused(self, delta):
        said = assert_that(lambda: match.is_now(delta)).raises(ValueError).when_called_with().value
        assert_that(said).starts_with("given delta arg must be a number of seconds a timedelta holds, but was <")

    def test_a_delta_a_timedelta_holds_is_taken(self):
        assert_that(datetime.datetime.now()).satisfies(match.is_now(10**8))


class TestTheVeryObjectIsFoundInASequence:
    def test_a_nan_the_value_holds_is_found_by_every_sibling(self):
        nan = float("nan")
        held = [1, nan, 2]
        assert_that(held).contains(nan).contains_sequence(nan).contains_in_order(nan)
        assert_that(held).contains_sequence(1, nan, 2).contains_in_order(1, nan).contains_in_order(nan, 2)

    def test_a_run_of_no_items_is_found_as_it_was(self):
        def found(values: list[int]) -> object:
            try:
                return _sequence_break(values, ())
            except IndexError as raised:
                return raised

        assert_that(found([1, 2])).is_none()
        assert_that(found([])).is_none()
        assert_that(_sequence_break([1, 2], (2,))).is_none()
        assert_that(_sequence_break([1, 2], (1, 3))).is_equal_to(1)
        assert_that(_sequence_break([], (1,))).is_equal_to(0)

    def test_another_nan_is_not(self):
        held = [1, float("nan"), 2]
        other = float("nan")
        assert_that(_passes(lambda: assert_that(held).contains_sequence(other))).is_false()
        assert_that(_passes(lambda: assert_that(held).contains_in_order(other))).is_false()

    def test_the_run_named_in_a_failure_counts_it(self):
        nan = float("nan")
        outcome = assert_that([1, nan]).check().contains_sequence(nan, 5, 6)
        assert_that(outcome.passed).is_false()
        assert_that(outcome.message).contains("The longest run that matched was <nan>.")


class TestAPathOfNoKeysNamesNothing:
    def test_it_is_told_from_a_key_that_is_falsy(self):
        assert_that([key_specs_given(()), key_specs_given(0), key_specs_given(""), key_specs_given([])]).is_equal_to(
            [False, True, True, False]
        )
        assert_that(normalize_key_specs((), "ignore")).is_empty()
        assert_that(normalize_key_specs([(), "a", ("b", "c")], "ignore")).is_equal_to(["a", ("b", "c")])
        assert_that(normalize_key_specs(("b", "c"), "ignore")).is_equal_to([("b", "c")])

    def test_an_empty_tuple_of_a_class_of_its_own_is_a_key(self):
        named = type("Named", (tuple,), {})()
        assert_that(key_specs_given(named)).is_true()
        assert_that(normalize_key_specs(named, "ignore")).is_equal_to([named])
        assert_that(normalize_key_specs([named], "ignore")).is_equal_to([named])
        assert_that({named: 1, "a": 1}).is_equal_to({named: 2, "a": 1}, ignore=named)

    @pytest.mark.parametrize(
        "option",
        [{"ignore": ()}, {"include": ()}, {"ignore": [()]}, {"ignore": [(), ("a", "b")]}],
        ids=["ignore", "include", "in-a-list", "beside-a-path"],
    )
    def test_the_comparison_runs_as_with_no_key_named(self, option):
        assert_that({"a": {"c": 1}}).is_equal_to({"a": {"c": 1}}, **option)
        assert_that(_passes(lambda: assert_that({"a": {"c": 1}}).is_equal_to({"a": {"c": 2}}, **option))).is_false()
        assert_that(match.equal_to({"a": {"c": 1}}, **option).matches({"a": {"c": 1}})).is_true()


class TestAKeyLeftOutUnderStrictTypes:
    @pytest.mark.parametrize(
        ("held", "wanted", "paths"),
        [
            ({"d": {"d": 0}}, {"d": {"d": 0, "c": None}}, [("d", "c")]),
            ({"d": {"d": 0}}, {"d": {"d": 0, "c": None}}, [("d", "c"), ("d", "d")]),
            ({"d": {"x": 1}}, {"d": {"y": 2}}, [("d", "x"), ("d", "y")]),
            ({"d": {"d": 0, "c": 1}}, {"d": {"d": 0}}, [("d", "c")]),
            ({"d": {True: 0}}, {"d": {1: 0}}, [("d", True)]),
            ({"d": {True: 0, "e": 5}}, {"d": {1: 0, "e": 5}}, [("d", 1)]),
        ],
        ids=[
            "one-path",
            "both-paths",
            "nothing-kept",
            "absent-on-the-other-side",
            "a-key-of-another-type",
            "a-key-of-another-type-beside-one-kept",
        ],
    )
    def test_it_does_not_fail_the_mapping_it_is_left_out_of(self, held, wanted, paths):
        assert_that(held).is_equal_to(wanted, ignore=paths)
        assert_that(held).is_equal_to(wanted, ignore=paths, strict_types=True)
        assert_that(match.equal_to(wanted, ignore=paths, strict_types=True).matches(held)).is_true()

    @pytest.mark.parametrize(
        ("held", "wanted", "option"),
        [
            ({"k": {True: "a"}}, {"k": {1: "a"}}, {}),
            ({"k": {True: "a", "z": 1}}, {"k": {1: "a", "z": 2}}, {"ignore": [("k", "z")]}),
            ({"k": {1}}, {"k": {1.0}}, {}),
            ({"d": {"d": 0}}, {"d": {"d": False, "c": None}}, {"ignore": [("d", "c")]}),
            ({"d": {1: 0, "e": True}}, {"d": {1: 0, "e": 1}}, {"ignore": [("d", 1)]}),
        ],
        ids=["key-types", "key-types-beside-a-path", "set-members", "value-type", "value-type-beside-a-key-left-out"],
    )
    def test_a_type_that_differs_in_what_is_kept_fails_under_strict_types_alone(self, held, wanted, option):
        assert_that(held).is_equal_to(wanted, **option)
        assert_that(_passes(lambda: assert_that(held).is_equal_to(wanted, strict_types=True, **option))).is_false()

    @pytest.mark.parametrize(
        ("held", "wanted"),
        [({"d": {"d": 0}}, {"d": {"d": 0, "c": None}}), ({"k": {1, 2}}, {"k": {1.0}})],
        ids=["a-key-not-left-out", "sets-of-two-sizes"],
    )
    def test_two_that_differ_still_differ(self, held, wanted):
        assert_that(_passes(lambda: assert_that(held).is_equal_to(wanted, strict_types=True))).is_false()


class TestAChainThatOnlyDescribesIsNotAwaited:
    def test_awaiting_it_is_refused_as_a_bare_chain_is(self):
        async def probe() -> int:
            return 1

        async def asked() -> str:
            try:
                await assert_that(probe).eventually(timeout=0.2, interval=0.01).described_as("x")
            except TypeError as refusal:
                return str(refusal)
            return "awaited"

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            said = asyncio.run(asked())
            gc.collect()
        assert_that(said).starts_with("no assertion was called on this eventually() chain")
        assert_that([str(each.message) for each in caught]).is_empty()

    def test_a_described_chain_with_an_assertion_is_awaited(self):
        async def probe() -> int:
            return 1

        async def asked() -> int:
            settled = await assert_that(probe).eventually(timeout=0.2, interval=0.01).described_as("x").is_equal_to(1)
            return settled.value

        assert_that(asyncio.run(asked())).is_equal_to(1)
