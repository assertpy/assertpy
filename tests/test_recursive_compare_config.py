import copy
import dataclasses
import datetime
import decimal
import re
import types
import uuid
from collections import OrderedDict, UserDict, namedtuple
from dataclasses import dataclass
from typing import ClassVar

import pytest

from assertpy import AssertionFailure, assert_that, match, soft_assertions
from assertpy._engine._compare import _build_compare_config
from assertpy._engine._diff import _build_equality_diff

Pair = namedtuple("Pair", ["a", "b"])


@dataclass
class Point:
    x: float
    y: float


class FakeModel:
    def __init__(self, **data):
        self._data = data

    def model_dump(self):
        return dict(self._data)


@dataclass
class Row:
    box: dict
    tag: str


@dataclass
class Bag:
    items: set
    tag: str


@dataclass
class PointTwin:
    x: float
    y: float


_PointPair = namedtuple("_PointPair", ["x", "y"])
_PointPairTwin = namedtuple("_PointPairTwin", ["x", "y"])


class TestToleranceScalar:
    def test_a_scalar_beyond_tolerance_reports_both_sides(self):
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that(1.0).is_equal_to(9.0, tolerance=0.5)
        rows = [(entry.path, entry.actual, entry.expected) for entry in exc_info.value.diff.entries]
        assert_that(rows).is_equal_to([(".", 1.0, 9.0)])

    def test_within_tolerance_passes(self):
        assert_that(1.0).is_equal_to(1.0001, tolerance=0.001)

    def test_at_tolerance_boundary_passes(self):
        assert_that(1.0).is_equal_to(1.001, tolerance=0.001)

    def test_just_beyond_tolerance_fails(self):
        with pytest.raises(AssertionFailure):
            assert_that(1.0).is_equal_to(1.0011, tolerance=0.001)

    def test_far_beyond_tolerance_fails(self):
        with pytest.raises(AssertionFailure):
            assert_that(1.0).is_equal_to(5.0, tolerance=0.001)

    def test_int_leaf_within_tolerance(self):
        assert_that(100).is_equal_to(101, tolerance=2)

    def test_nan_never_within_tolerance(self):
        with pytest.raises(AssertionFailure):
            assert_that(float("nan")).is_equal_to(float("nan"), tolerance=0.001)

    def test_expected_nan_never_within_tolerance(self):
        with pytest.raises(AssertionFailure):
            assert_that(1.0).is_equal_to(float("nan"), tolerance=0.001)

    def test_bool_excluded_from_tolerance(self):
        with pytest.raises(AssertionFailure):
            assert_that(True).is_equal_to(False, tolerance=5)

    def test_equal_infinities_within_tolerance(self):
        # inf == inf must be within any tolerance (abs(inf - inf) is NaN, which broke the check)
        assert_that(float("inf")).is_equal_to(float("inf"), tolerance=0.001)
        assert_that(float("-inf")).is_equal_to(float("-inf"), tolerance=0.001)
        with pytest.raises(AssertionFailure):
            assert_that(float("inf")).is_equal_to(float("-inf"), tolerance=0.001)


class TestToleranceNested:
    def test_a_list_element_beyond_tolerance_reports_both_sides(self):
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that([1.0, 2.0]).is_equal_to([1.0, 5.0], tolerance=0.001)
        rows = [(entry.path, entry.actual, entry.expected) for entry in exc_info.value.diff.entries]
        assert_that(rows).is_equal_to([("[1]", 2.0, 5.0)])

    def test_a_dataclass_field_beyond_tolerance_reports_both_sides(self):
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that(Point(1.0, 2.0)).is_equal_to(Point(1.0, 9.0), tolerance=0.001)
        rows = [(entry.path, entry.actual, entry.expected) for entry in exc_info.value.diff.entries]
        assert_that(rows).is_equal_to([(".y", 2.0, 9.0)])

    def test_a_namedtuple_field_beyond_tolerance_reports_both_sides(self):
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that(Pair(1.0, 2.0)).is_equal_to(Pair(1.0, 9.0), tolerance=0.001)
        rows = [(entry.path, entry.actual, entry.expected) for entry in exc_info.value.diff.entries]
        assert_that(rows).is_equal_to([(".b", 2.0, 9.0)])

    def test_dict_all_within_tolerance(self):
        assert_that({"a": 1.0, "b": 2.0}).is_equal_to({"a": 1.0005, "b": 2.0}, tolerance=0.001)

    def test_dict_leaf_beyond_tolerance_fails(self):
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that({"a": 1.0}).is_equal_to({"a": 1.5}, tolerance=0.001)
        assert_that(exc_info.value.diff.entries[0].path).is_equal_to("a")

    def test_nested_dict_all_tolerated_passes(self):
        assert_that({"x": {"y": 1.0}}).is_equal_to({"x": {"y": 1.0001}}, tolerance=0.001)

    def test_nested_dict_partial_reports_only_real_diff(self):
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that({"x": {"y": 1.0, "z": 5}}).is_equal_to({"x": {"y": 1.0001, "z": 9}}, tolerance=0.001)
        paths = [entry.path for entry in exc_info.value.diff.entries]
        assert_that(paths).is_equal_to(["x.z"])

    def test_list_within_tolerance(self):
        assert_that([1.0, 2.0]).is_equal_to([1.0001, 2.0], tolerance=0.001)

    def test_list_leaf_beyond_tolerance_fails(self):
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that([1.0, 2.0]).is_equal_to([1.0, 5.0], tolerance=0.001)
        assert_that(exc_info.value.diff.entries[0].path).is_equal_to("[1]")

    def test_dataclass_field_within_tolerance(self):
        assert_that(Point(1.0, 2.0)).is_equal_to(Point(1.0001, 2.0), tolerance=0.001)

    def test_dataclass_field_beyond_tolerance_fails(self):
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that(Point(1.0, 2.0)).is_equal_to(Point(1.0, 9.0), tolerance=0.001)
        assert_that(exc_info.value.diff.entries[0].path).is_equal_to(".y")

    def test_namedtuple_field_within_tolerance(self):
        assert_that(Pair(1.0, 2.0)).is_equal_to(Pair(1.0001, 2.0), tolerance=0.001)

    def test_model_field_within_tolerance(self):
        assert_that(FakeModel(a=1.0, b=2.0)).is_equal_to(FakeModel(a=1.0001, b=2.0), tolerance=0.001)


class TestComparators:
    def test_type_comparator_passes(self):
        assert_that([1, 2]).is_equal_to([10, 20], comparators={int: lambda actual, expected: True})

    def test_type_comparator_fails(self):
        with pytest.raises(AssertionFailure):
            assert_that([1]).is_equal_to([2], comparators={int: lambda actual, expected: actual == expected})

    def test_field_name_comparator_passes(self):
        assert_that({"id": 1, "x": 5}).is_equal_to(
            {"id": 999, "x": 5}, comparators={"id": lambda actual, expected: True}
        )

    def test_field_name_wins_over_type(self):
        comparators = {"id": lambda actual, expected: True, int: lambda actual, expected: actual == expected}
        assert_that({"id": 1, "n": 5}).is_equal_to({"id": 99, "n": 5}, comparators=comparators)
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that({"id": 1, "n": 5}).is_equal_to({"id": 99, "n": 6}, comparators=comparators)
        assert_that(exc_info.value.diff.entries[0].path).is_equal_to("n")

    def test_exact_type_wins_over_isinstance(self):
        class MyInt(int):
            pass

        calls = []
        comparators = {
            MyInt: lambda actual, expected: calls.append("exact") or True,
            int: lambda actual, expected: calls.append("isinstance") or True,
        }
        assert_that([MyInt(1)]).is_equal_to([MyInt(9)], comparators=comparators)
        assert_that(calls).is_equal_to(["exact"])

    def test_isinstance_fallback(self):
        class MyInt(int):
            pass

        assert_that([MyInt(1)]).is_equal_to([MyInt(9)], comparators={int: lambda actual, expected: True})

    def test_no_matching_comparator_falls_back_to_equality(self):
        with pytest.raises(AssertionFailure):
            assert_that([1]).is_equal_to([2], comparators={str: lambda actual, expected: True})

    def test_scalar_comparator_equal(self):
        assert_that(5).is_equal_to(6, comparators={int: lambda actual, expected: True})

    def test_scalar_comparator_leaf(self):
        with pytest.raises(AssertionFailure):
            assert_that(5).is_equal_to(6, comparators={int: lambda actual, expected: False})

    def test_container_comparator_at_top(self):
        assert_that([1]).is_equal_to([2], comparators={list: lambda actual, expected: True})

    def test_namedtuple_field_comparator_leaf(self):
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that(Pair(1, 2)).is_equal_to(
                Pair(1, 9), comparators={int: lambda actual, expected: actual == expected}
            )
        assert_that(exc_info.value.diff.entries[0].path).is_equal_to(".b")

    def test_model_field_comparator_leaf(self):
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that(FakeModel(a=1, b=2)).is_equal_to(
                FakeModel(a=1, b=9), comparators={int: lambda actual, expected: actual == expected}
            )
        assert_that(exc_info.value.diff.entries[0].path).is_equal_to(".b")

    def test_nested_namedtuple_field_comparator_leaf(self):
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that({"p": Pair(1, 2)}).is_equal_to(
                {"p": Pair(1, 9)}, comparators={int: lambda actual, expected: actual == expected}
            )
        assert_that(exc_info.value.diff.entries[0].path).is_equal_to("p.b")

    def test_nested_model_field_comparator_leaf(self):
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that({"m": FakeModel(a=1, b=2)}).is_equal_to(
                {"m": FakeModel(a=1, b=9)}, comparators={int: lambda actual, expected: actual == expected}
            )
        assert_that(exc_info.value.diff.entries[0].path).is_equal_to("m.b")

    def test_a_comparator_owns_an_aligned_element_the_walker_would_decompose(self):
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that([{"v": 1}, {"pad": 1}]).is_equal_to(
                [{"v": 1}, {"extra": 9}, {"pad": 1}],
                comparators={dict: lambda actual, expected: False},
            )
        rows = [(entry.path, entry.actual, entry.expected) for entry in exc_info.value.diff.entries]
        assert_that(rows).contains(("[0]", {"v": 1}, {"v": 1}), ("[1]", {"pad": 1}, {"pad": 1}))

    def test_an_exact_type_outranks_a_supertype_registered_before_it(self):
        """Field name, then exact type, then isinstance: a `bool` leaf belongs to the `bool` entry even
        though the `int` entry was written first and `isinstance` would accept it."""
        comparators = {int: lambda actual, expected: False, bool: lambda actual, expected: True}
        assert_that({"n": True}).is_equal_to({"n": False}, comparators=comparators)


class TestConfigValidation:
    def test_tolerance_not_real_raises(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that(1).is_equal_to(1, tolerance="x")
        assert_that(str(exc_info.value)).is_equal_to("given tolerance arg must be a real number")

    def test_tolerance_bool_raises(self):
        with pytest.raises(TypeError):
            assert_that(1).is_equal_to(1, tolerance=True)

    def test_tolerance_complex_raises(self):
        with pytest.raises(TypeError):
            assert_that(1).is_equal_to(1, tolerance=1j)

    def test_tolerance_nan_raises(self):
        with pytest.raises(ValueError) as exc_info:
            assert_that(1).is_equal_to(1, tolerance=float("nan"))
        assert_that(str(exc_info.value)).is_equal_to("given tolerance arg must not be NaN")

    def test_tolerance_negative_raises(self):
        with pytest.raises(ValueError) as exc_info:
            assert_that(1).is_equal_to(1, tolerance=-1)
        assert_that(str(exc_info.value)).is_equal_to("given tolerance arg must not be negative")

    def test_comparators_not_dict_raises(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that(1).is_equal_to(1, comparators=[lambda actual, expected: True])
        assert_that(str(exc_info.value)).is_equal_to("given comparators arg must be a dict")

    def test_comparator_not_callable_raises(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that(1).is_equal_to(1, comparators={int: "nope"})
        assert_that(str(exc_info.value)).is_equal_to("each comparator must be callable")

    def test_ignore_null_not_a_bool_raises(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that(1).is_equal_to(1, ignore_null="yes")
        assert_that(str(exc_info.value)).is_equal_to("given ignore_null arg must be a bool")

    def test_strict_types_not_a_bool_raises(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that(1).is_equal_to(1, strict_types="yes")
        assert_that(str(exc_info.value)).is_equal_to("given strict_types arg must be a bool")

    def test_the_two_argument_form_leaves_both_flags_off(self):
        """Snapshot capture builds a config from tolerance and comparators alone, and neither flag may
        switch itself on there: with one defaulted on, nothing is ever at its defaults."""
        assert_that(_build_compare_config(None, None)).is_none()
        config = _build_compare_config(0.5, None)
        assert_that(config.ignore_null).is_false()
        assert_that(config.strict_types).is_false()


class TestRegexTypeIgnoreInclude:
    def test_ignore_by_regex(self):
        assert_that({"_id": 1, "name": "a"}).is_equal_to({"_id": 999, "name": "a"}, ignore=re.compile(r"^_"))

    def test_ignore_by_regex_still_catches_real_diff(self):
        with pytest.raises(AssertionFailure):
            assert_that({"_id": 1, "name": "a"}).is_equal_to({"_id": 1, "name": "b"}, ignore=re.compile(r"^_"))

    def test_ignore_by_type(self):
        assert_that({"x": 1.5, "n": "a"}).is_equal_to({"x": 9.9, "n": "a"}, ignore=float)

    def test_include_by_regex(self):
        assert_that({"a1": 1, "a2": 2, "b": 99}).is_equal_to({"a1": 1, "a2": 2, "b": 0}, include=re.compile(r"^a"))

    def test_include_by_type(self):
        assert_that({"x": 1, "n": "a"}).is_equal_to({"x": 1, "n": "different"}, include=int)

    def test_include_regex_no_match_does_not_report_missing(self):
        assert_that({"b": 1}).is_equal_to({"b": 1}, include=re.compile(r"^a"))


class TestDiffMessageConsistency:
    def test_tolerated_leaf_absent_from_diff_and_message(self):
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that({"a": 1.0, "b": 5}).is_equal_to({"a": 1.0001, "b": 9}, tolerance=0.001)
        message = str(exc_info.value)
        paths = [entry.path for entry in exc_info.value.diff.entries]
        assert_that(paths).is_equal_to(["b"])
        assert_that(message).does_not_contain("1.0001")
        assert_that(message).contains("'b'")

    def test_comparator_equal_leaf_absent_from_diff(self):
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that({"id": 1, "n": 5}).is_equal_to(
                {"id": 999, "n": 9}, comparators={"id": lambda actual, expected: True}
            )
        paths = [entry.path for entry in exc_info.value.diff.entries]
        assert_that(paths).is_equal_to(["n"])


class TestConfigWithFilter:
    def test_ignore_combined_with_tolerance(self):
        assert_that({"id": 1, "v": 1.0}).is_equal_to({"id": 999, "v": 1.0001}, ignore="id", tolerance=0.001)

    def test_seq_filter_item_within_tolerance(self):
        assert_that([1.0]).is_equal_to([1.0001], include="x", tolerance=0.001)

    def test_seq_filter_item_beyond_tolerance_fails(self):
        with pytest.raises(AssertionFailure):
            assert_that([1.0]).is_equal_to([1.5], include="x", tolerance=0.001)

    def test_nested_dict_vs_scalar_under_config_fails_cleanly(self):
        # one side dict-nested, the other scalar: a clean difference, not a TypeError from descending
        with pytest.raises(AssertionFailure):
            assert_that({"a": {"x": 1.0}}).is_equal_to({"a": 5.0}, tolerance=0.001)

    def test_tolerated_key_does_not_short_circuit_later_keys(self):
        # the set iterates 0 then 1, and only key 1 differs, so both keys must be checked and not just the first
        with pytest.raises(AssertionFailure):
            assert_that({0: 1.0, 1: 5.0}).is_equal_to({0: 1.0001, 1: 9.0}, tolerance=0.001)


class TestNoConfigUnchanged:
    def test_plain_equal_dict_passes(self):
        assert_that({"a": 1}).is_equal_to({"a": 1})

    def test_plain_unequal_scalar_fails(self):
        with pytest.raises(AssertionFailure):
            assert_that(1).is_equal_to(2)


@dataclass
class OptUser:
    name: str
    age: int | None = None
    score: float | None = None


class TestIgnoreNull:
    def test_object_expected_null_field_ignored(self):
        assert_that(OptUser("A", 30, 9.5)).is_equal_to(OptUser("A"), ignore_null=True)

    def test_object_non_null_field_still_compared(self):
        with pytest.raises(AssertionFailure):
            assert_that(OptUser("A", 30)).is_equal_to(OptUser("B", 30), ignore_null=True)

    def test_dict_expected_null_value_ignored(self):
        assert_that({"a": 1, "b": 5}).is_equal_to({"a": 1, "b": None}, ignore_null=True)

    def test_actual_null_vs_expected_value_not_masked(self):
        # safety: only expected-None fields are skipped, so an unexpectedly-None actual is still caught
        with pytest.raises(AssertionFailure):
            assert_that(OptUser("A", None)).is_equal_to(OptUser("A", 30), ignore_null=True)

    def test_nested_expected_null_field_ignored(self):
        assert_that({"user": {"name": "A", "age": 30}}).is_equal_to(
            {"user": {"name": "A", "age": None}}, ignore_null=True
        )

    def test_list_elements_are_not_null_fields(self):
        # a None *element* has no field name, so ignore_null must not skip it
        with pytest.raises(AssertionFailure):
            assert_that([1, 5]).is_equal_to([1, None], ignore_null=True)

    def test_combined_with_tolerance(self):
        assert_that(OptUser("A", 30, 1.0)).is_equal_to(OptUser("A", None, 1.0001), ignore_null=True, tolerance=0.001)

    def test_ignore_null_not_a_bool_fails(self):
        with pytest.raises(TypeError, match="ignore_null"):
            assert_that({}).is_equal_to({}, ignore_null="yes")


_ELIDED = re.compile(r"[\[{]\.\.")


def _elision_matrix():
    """(label, actual, expected, kwargs) across the shapes whose failure message gets reduced."""
    shapes = [
        ("flat_dict", {"a": 1.0}, {"a": 1.001}, {"a": 9.0}),
        ("nested_dict", {"n": {"a": 1.0}}, {"n": {"a": 1.001}}, {"n": {"a": 9.0}}),
        ("dict_to_list_dicts", {"d": [{"a": 1.0}]}, {"d": [{"a": 1.001}]}, {"d": [{"a": 9.0}]}),
        ("dict_to_list_lists", {"d": [[1.0]]}, {"d": [[1.001]]}, {"d": [[9.0]]}),
        ("dict_to_tuple", {"d": (1.0,)}, {"d": (1.001,)}, {"d": (9.0,)}),
        ("dict_to_dataclass", {"d": Point(1.0, 2.0)}, {"d": Point(1.001, 2.0)}, {"d": Point(9.0, 2.0)}),
        ("dict_to_namedtuple", {"d": Pair(1.0, 2.0)}, {"d": Pair(1.001, 2.0)}, {"d": Pair(9.0, 2.0)}),
        ("dict_to_model", {"d": FakeModel(a=1.0)}, {"d": FakeModel(a=1.001)}, {"d": FakeModel(a=9.0)}),
        (
            "deep_payload",
            {"ok": True, "data": [{"id": 1, "o": {"s": 1.0}}]},
            {"ok": True, "data": [{"id": 1, "o": {"s": 1.001}}]},
            {"ok": True, "data": [{"id": 1, "o": {"s": 9.0}}]},
        ),
    ]
    configs = [
        ("no_config", {}),
        ("tolerance", {"tolerance": 0.01}),
        ("comparators", {"comparators": {float: lambda x, y: abs(x - y) < 0.01}}),
        ("ignore_null", {"ignore_null": True}),
    ]
    specs = [("no_spec", {}), ("ignore_bare", {"ignore": "a"}), ("ignore_tuple", {"ignore": ("d", "a")})]
    for name, actual, near, far in shapes:
        variants = [("near", near), ("far", far), ("extra_key", {**actual, "zz": 1})]
        for variant, expected in variants:
            for config_name, config in configs:
                for spec_name, spec in specs:
                    label = f"{name}/{variant}/{config_name}/{spec_name}"
                    yield label, actual, expected, {**config, **spec}


def _elided_failure(actual, expected, kwargs):
    """Return the failure whose message hides the equal parts, or ``None`` when the invariant is moot.

    A plain ``AssertionError``, or a message that names both values outright, is readable on its own
    and carries no diff by design, so only the elided form takes part in the sweep.
    """
    try:
        assert_that(actual).is_equal_to(expected, **kwargs)
    except AssertionFailure as failure:
        return failure if _ELIDED.search(str(failure).splitlines()[0]) else None
    except AssertionError:
        return None
    return None


class TestElidedFailureAlwaysCarriesDiff:
    """A message that hides the equal parts must be explained by the structured diff.

    The dict failure message is reduced to the differing keys (``{.., 'b': 2}``), which is only
    readable because the diff spells out what changed.  The verdict and the diff are produced at
    separate call sites, so drift between them yields a failure that claims inequality while showing
    nothing - a real 2026-07 defect.  This pins the pairing across a shape/config/spec matrix rather
    than for one hand-picked case.
    """

    def test_every_elided_failure_is_explained_by_its_diff(self):
        violations = [
            f"{label}: {str(failure).splitlines()[0]}"
            for label, actual, expected, kwargs in _elision_matrix()
            if (failure := _elided_failure(actual, expected, kwargs)) is not None
            and (failure.diff is None or not failure.diff.entries)
        ]
        assert_that(violations).is_empty()

    def test_the_matrix_actually_exercises_elided_failures(self):
        # a guard on the guard: if the message stops eliding, the sweep above would go vacuous
        elided = [
            label
            for label, actual, expected, kwargs in _elision_matrix()
            if _elided_failure(actual, expected, kwargs) is not None
        ]
        assert_that(elided).is_not_empty()
        assert_that(len(elided)).is_greater_than(20)


class TestConfigThroughNestedContainers:
    """A container reached through a dict keeps the compare config.

    The equality decision delegates to the same structural walker that renders the diff, so every shape
    the walker decomposes is compared under the config.  It used to fall back to plain equality there, so
    tolerance / comparators / ignore_null silently stopped applying below the first non-dict container -
    the shape of almost every JSON API response.
    """

    def test_tolerance_reaches_dicts_inside_a_nested_list(self):
        assert_that({"d": [{"s": 1.0}]}).is_equal_to({"d": [{"s": 1.001}]}, tolerance=0.01)

    def test_tolerance_reaches_a_nested_list_of_lists(self):
        assert_that({"d": [[1.0]]}).is_equal_to({"d": [[1.001]]}, tolerance=0.01)

    def test_tolerance_reaches_a_nested_tuple(self):
        assert_that({"d": ({"s": 1.0},)}).is_equal_to({"d": ({"s": 1.001},)}, tolerance=0.01)

    def test_tolerance_reaches_a_nested_dataclass(self):
        assert_that({"d": Point(1.0, 2.0)}).is_equal_to({"d": Point(1.001, 2.0)}, tolerance=0.01)

    def test_tolerance_reaches_a_nested_namedtuple(self):
        assert_that({"d": Pair(1.0, 2.0)}).is_equal_to({"d": Pair(1.001, 2.0)}, tolerance=0.01)

    def test_tolerance_reaches_a_nested_model(self):
        assert_that({"d": FakeModel(s=1.0)}).is_equal_to({"d": FakeModel(s=1.001)}, tolerance=0.01)

    def test_tolerance_reaches_a_list_of_dataclasses(self):
        assert_that({"d": [Point(1.0, 2.0)]}).is_equal_to({"d": [Point(1.001, 2.0)]}, tolerance=0.01)

    def test_comparators_reach_a_nested_list(self):
        close = {float: lambda actual, expected: abs(actual - expected) < 0.01}
        assert_that({"d": [{"s": 1.0}]}).is_equal_to({"d": [{"s": 1.001}]}, comparators=close)

    def test_ignore_null_reaches_a_nested_list(self):
        assert_that({"d": [{"a": 1, "b": 5}]}).is_equal_to({"d": [{"a": 1, "b": None}]}, ignore_null=True)

    def test_identical_container_short_circuits_on_identity(self):
        shared = [float("nan")]
        assert_that({"d": shared, "k": 1}).is_equal_to({"d": shared, "k": 2}, ignore="k")

    def test_length_mismatch_still_fails(self):
        with pytest.raises(AssertionError):
            assert_that({"d": [{"s": 1.0}]}).is_equal_to({"d": [{"s": 1.0}, {"s": 2.0}]}, tolerance=0.01)

    def test_leaf_outside_tolerance_still_fails(self):
        with pytest.raises(AssertionError):
            assert_that({"d": [1.0]}).is_equal_to({"d": [9.0]}, tolerance=0.01)

    def test_dataclass_outside_tolerance_still_fails(self):
        with pytest.raises(AssertionError):
            assert_that({"d": Point(1.0, 2.0)}).is_equal_to({"d": Point(9.0, 2.0)}, tolerance=0.01)

    def test_dict_element_difference_still_fails(self):
        with pytest.raises(AssertionError):
            assert_that({"d": [{"s": 1.0, "n": "a"}]}).is_equal_to({"d": [{"s": 1.0, "n": "b"}]}, tolerance=0.01)

    def test_inner_list_difference_still_fails(self):
        with pytest.raises(AssertionError):
            assert_that({"d": [[1.0]]}).is_equal_to({"d": [[9.0]]}, tolerance=0.01)

    def test_undecomposable_leaf_difference_still_fails(self):
        with pytest.raises(AssertionError):
            assert_that({"d": "a"}).is_equal_to({"d": "b"}, tolerance=0.01)

    def test_plain_difference_without_config_still_fails(self):
        with pytest.raises(AssertionError):
            assert_that({"d": [1, 2], "k": 1}).is_equal_to({"d": [1, 9], "k": 2}, ignore="k")

    def test_tolerance_reaches_a_dict_inside_a_shifted_list(self):
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that([{"v": 1.0}, {"pad": 1}]).is_equal_to([{"v": 1.2}, {"extra": 9}, {"pad": 1}], tolerance=0.5)
        rows = [(entry.path, entry.actual, entry.expected) for entry in exc_info.value.diff.entries]
        assert_that(rows).is_equal_to([("expected[1]", None, {"extra": 9})])

    def test_tolerance_reaches_a_dict_inside_a_record_field(self):
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that(Row({"v": 1.0}, "a")).is_equal_to(Row({"v": 1.2}, "b"), tolerance=0.5)
        rows = [(entry.path, entry.actual, entry.expected) for entry in exc_info.value.diff.entries]
        assert_that(rows).is_equal_to([(".tag", "a", "b")])


class _Opaque:
    """A value the diff ladder cannot take apart and no atomic list will ever name."""

    def __init__(self, amount):
        self.amount = amount

    def __eq__(self, other):
        return isinstance(other, _Opaque) and self.amount == other.amount

    __hash__ = None

    def __repr__(self):
        return f"_Opaque({self.amount})"


class TestStrictTypes:
    """`==` alone lets a type change pass at any depth, so `strict_types` closes it."""

    @pytest.mark.parametrize(
        ("actual", "expected"),
        [
            (True, 1),
            (0, False),
            (1, 1.0),
            (decimal.Decimal(1), 1),
            ([True], [1]),
            ({"active": True}, {"active": 1}),
            ({"a": {"b": [{"c": True}]}}, {"a": {"b": [{"c": 1}]}}),
            (OrderedDict(a=1), {"a": 1}),
            ((1, True), (1, 1)),
            (Point(1, 2), Point(1.0, 2)),
        ],
        ids=str,
    )
    def test_a_type_change_is_caught_at_any_depth(self, actual, expected):
        assert_that(actual).is_equal_to(expected)
        with pytest.raises(AssertionError):
            assert_that(actual).is_equal_to(expected, strict_types=True)

    def test_a_comparator_decides_the_root_ahead_of_strict_types(self):
        """As it decides `[1]` against `["1"]`: the root failed with an empty diff, which said the pair was equal."""
        comparators = {int: lambda actual, expected: True}
        assert_that(1).is_equal_to("1", strict_types=True, comparators=comparators)
        assert_that([1]).is_equal_to(["1"], strict_types=True, comparators=comparators)
        assert_that(match.equal_to("1", strict_types=True, comparators=comparators).matches(1)).is_true()

    def test_equal_payload_still_passes(self):
        payload = {"id": 1, "tags": ["a"], "meta": {"ok": True, "n": None}}
        assert_that(payload).is_equal_to(dict(payload), strict_types=True)

    @pytest.mark.parametrize(
        ("actual", "expected"),
        [
            ({1, 2}, {1, 2}),
            ({"s": {1, 2}}, {"s": {1, 2}}),
            ({"s": frozenset({1})}, {"s": frozenset({1})}),
            ([{1}], [{1}]),
            ({"s": {"a": {1}}}, {"s": {"a": {1}}}),
        ],
        ids=str,
    )
    def test_an_equal_set_is_not_read_as_a_difference(self, actual, expected):
        # the walk may only enter what the walker takes apart; a set is not, and entering one invents a difference
        assert_that(actual).is_equal_to(expected, strict_types=True)
        assert_that(match.equal_to(expected, strict_types=True).matches(actual)).is_true()

    def test_a_differing_set_is_still_reported(self):
        with pytest.raises(AssertionError):
            assert_that({"s": {1}}).is_equal_to({"s": {2}}, strict_types=True)

    def test_an_undecomposable_item_survives_the_filtered_sequence_path(self):
        assert_that([{1}]).is_equal_to([{1}], strict_types=True, ignore="absent")
        with pytest.raises(AssertionError):
            assert_that([{1}]).is_equal_to([{2}], strict_types=True, ignore="absent")

    @pytest.mark.parametrize(
        "value",
        [
            uuid.UUID(int=1),
            decimal.Decimal(3),
            datetime.date(2026, 1, 1),
            {1, 2},
            frozenset({1}),
            "abc",
            b"ab",
            _Opaque(1),
        ],
        ids=str,
    )
    def test_an_undecomposable_value_at_the_top_level_is_equal_to_its_copy(self, value):
        # the builder's ladder knows sets, strings and bytes, so a forced descent reads "ran out" as equality too
        assert_that(value).is_equal_to(copy.deepcopy(value), strict_types=True)

    @pytest.mark.parametrize(
        ("actual", "expected"),
        [
            (uuid.UUID(int=1), uuid.UUID(int=2)),
            (datetime.date(2026, 1, 1), datetime.date(2026, 1, 2)),
            ("abc", "abd"),
            (_Opaque(1), _Opaque(2)),
        ],
        ids=str,
    )
    def test_a_differing_undecomposable_value_is_still_reported(self, actual, expected):
        with pytest.raises(AssertionError):
            assert_that(actual).is_equal_to(expected, strict_types=True)

    def test_an_undecomposable_field_of_a_namedtuple_survives(self):
        pair = namedtuple("pair", ["first", "second"])
        assert_that(pair(1, {2})).is_equal_to(pair(1, {2}), strict_types=True)
        with pytest.raises(AssertionError):
            assert_that(pair(1, {2})).is_equal_to(pair(1, {3}), strict_types=True)

    def test_matchers_stay_exempt(self):
        assert_that({"id": 7}).is_equal_to({"id": match.greater_than(0)}, strict_types=True)
        assert_that({"u": {"age": 30}}).is_equal_to({"u": {"age": match.between(18, 120)}}, strict_types=True)
        assert_that([1, 5]).is_equal_to([1, match.greater_than(4)], strict_types=True)

    def test_a_comparator_still_owns_its_leaves(self):
        assert_that({"a": True}).is_equal_to({"a": 1}, strict_types=True, comparators={bool: lambda x, y: True})

    def test_strictness_wins_over_tolerance(self):
        assert_that(1).is_equal_to(1.0, tolerance=0.5)
        with pytest.raises(AssertionError):
            assert_that(1).is_equal_to(1.0, tolerance=0.5, strict_types=True)

    @pytest.mark.parametrize(
        ("actual", "expected"),
        [
            ({True: "a"}, {1: "a"}),
            ({1: "a"}, {1.0: "a"}),
            ({1}, {1.0}),
            ({True}, {1}),
            (frozenset({1}), frozenset({True})),
            ({"s": {1}}, {"s": {1.0}}),
        ],
        ids=str,
    )
    def test_a_hash_matched_key_or_member_is_compared_by_type_too(self, actual, expected):
        """The one place the flag's name promised something it did not deliver.

        A dict key and a set element are found by hash, and `1`, `1.0` and `True` hash alike, so the
        pair was matched before anything looked at its type. Everything else about `strict_types` works
        pair by pair, and a key never becomes a pair. Reported by an external review of the shipped
        library, reproduced, and now closed on both sides: the container's own walk and the matcher.
        """
        with pytest.raises(AssertionError):
            assert_that(actual).is_equal_to(expected, strict_types=True)
        assert_that(match.equal_to(expected, strict_types=True).matches(actual)).is_false()

    @pytest.mark.parametrize(
        ("actual", "expected"),
        [({1: "a"}, {1: "a"}), ({"s": {1, 2}}, {"s": {2, 1}}), (frozenset({1}), frozenset({1}))],
        ids=str,
    )
    def test_the_same_keys_of_the_same_types_still_match(self, actual, expected):
        assert_that(actual).is_equal_to(expected, strict_types=True)

    def test_the_diff_names_the_key_rather_than_the_whole_mapping(self):
        with pytest.raises(AssertionFailure) as failure:
            assert_that({True: "a", "ok": 1}).is_equal_to({1: "a", "ok": 1}, strict_types=True)
        assert_that(str(failure.value)).contains("only their types differ")
        diff = failure.value.diff
        assert_that(diff).is_not_none()
        assert_that([(entry.actual, entry.expected) for entry in diff.entries]).is_equal_to([(True, 1)])
        assert_that(diff.entries[0].steps[-1].kind).described_as("reported against the key").is_equal_to("key")

    def test_a_key_matched_by_hash_is_found_whichever_side_stores_it(self):
        # `{True} & {1}` hands back whichever side the set drew from, losing the type being compared
        for actual, expected in (({True: "a"}, {1: "a"}), ({1: "a"}, {True: "a"})):
            with pytest.raises(AssertionError):
                assert_that(actual).is_equal_to(expected, strict_types=True)

    @pytest.mark.parametrize("bad", ["yes", 1, None])
    def test_non_bool_is_rejected(self, bad):
        with pytest.raises(TypeError, match="strict_types arg must be a bool"):
            assert_that(1).is_equal_to(1, strict_types=bad)

    def test_an_aligned_equal_element_with_no_inside_is_not_reported(self):
        """The aligned pairing descends on its own, and a strict descent into a value it cannot take
        apart means the pair was already equal."""
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that([_Opaque(1), _Opaque(2)]).is_equal_to([_Opaque(0), _Opaque(1), _Opaque(2)], strict_types=True)
        rows = [(entry.path, entry.actual, entry.expected) for entry in exc_info.value.diff.entries]
        assert_that(rows).is_equal_to([("expected[0]", None, _Opaque(0))])

    def test_a_key_only_one_side_has_is_not_reported_as_a_key_type_difference(self):
        """A key with no counterpart is a missing key, and the type check has no pair to make of it."""
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that({"a": 1, "b": 2}).is_equal_to({"a": 1}, strict_types=True)
        rows = [(entry.path, entry.actual, entry.expected) for entry in exc_info.value.diff.entries]
        assert_that(rows).is_equal_to([("b", 2, None)])

    def test_a_self_referential_pair_is_walked_under_the_flag_and_left_to_python_without_it(self):
        # bare `==` on two distinct self-referential structures exhausts the stack (CPython's guard covers `a is b`,
        # not this); under the flag the walk is the library's own, and a pair met again is equal
        actual = {"x": 1}
        actual["self"] = actual
        expected = {"x": 1}
        expected["self"] = expected
        with pytest.raises(RecursionError):
            assert_that(actual).is_equal_to(expected)
        assert_that(actual).is_equal_to(expected, strict_types=True)
        expected["x"] = True
        with pytest.raises(AssertionFailure) as caught:
            assert_that(actual).is_equal_to(expected, strict_types=True)
        assert_that([entry.path for entry in caught.value.diff.entries]).contains("x")

    @pytest.mark.parametrize(
        "config",
        [
            {"strict_types": True},
            {"tolerance": 0.1},
            {"comparators": {str: lambda actual, expected: actual == expected}},
        ],
        ids=["strict_types", "tolerance", "comparators"],
    )
    def test_a_record_that_holds_itself_is_equal_to_one_built_alike_under_a_config(self, config):
        """The walk is the verdict there, and stopped at the pair it was already inside by reporting it: two records
        built alike failed with a diff that named no difference."""

        @dataclass
        class Account:
            id: int
            balance: float
            owner: "Account | None" = None

        def ring(length, balance=5.0, id=1):
            nodes = [Account(id, balance) for _ in range(length)]
            for index, node in enumerate(nodes):
                node.owner = nodes[(index + 1) % length]
            return nodes[0]

        for length in (1, 2, 3):
            assert_that(ring(length)).described_as(str(length)).is_equal_to(ring(length), **config)
            with pytest.raises(AssertionFailure) as caught:
                assert_that(ring(length)).is_equal_to(ring(length, id=2), **config)
            found = [(entry.path, entry.actual, entry.expected) for entry in caught.value.diff.entries]
            # each node once, the one the walk started at included
            named = [".".join(["", *["owner"] * hops, "id"]) for hops in range(length)]
            assert_that(found).described_as(str(length)).is_equal_to([(path, 1, 2) for path in named])
        # a ring against a chain that ends differs where the chain ends
        chain = Account(1, 5.0, Account(1, 5.0, Account(1, 5.0)))
        with pytest.raises(AssertionFailure) as caught:
            assert_that(ring(1)).is_equal_to(chain, **config)
        found = [(entry.path, entry.expected) for entry in caught.value.diff.entries]
        assert_that(found).is_equal_to([(".owner.owner.owner", None)])
        # rings of two and of three read alike however far they are followed, and are equal, as two such dicts are
        assert_that(ring(2)).is_equal_to(ring(3), **config)
        # a pair is left behind once the walk is out of it: met again beside it, it is walked again
        shared, differing = Account(1, 5.0), Account(2, 5.0)
        with pytest.raises(AssertionFailure) as caught:
            assert_that([shared, shared]).is_equal_to([differing, differing], **config)
        assert_that([entry.path for entry in caught.value.diff.entries]).is_equal_to(["[0].id", "[1].id"])
        # two nodes that hold each other, compared from either end
        one, other = Account(1, 5.0), Account(1, 5.0)
        one.owner, other.owner = other, one
        assert_that(one).is_equal_to(other, **config)
        other.id = 2
        with pytest.raises(AssertionFailure) as caught:
            assert_that(one).is_equal_to(other, **config)
        assert_that([entry.path for entry in caught.value.diff.entries]).is_equal_to([".id", ".owner.id"])

    def test_without_a_config_the_diff_of_a_pair_met_again_holds_what_differs_alone(self):
        @dataclass
        class Account:
            id: int
            owner: "Account | None" = None

        left, right = Account(1), Account(2)
        left.owner, right.owner = left, right
        with pytest.raises(AssertionFailure) as caught:
            assert_that(left).is_equal_to(right, ignore="missing")
        # asked under a key spec the root is one question and the same pair below it another, so both are read
        assert_that([(entry.path, entry.actual) for entry in caught.value.diff.entries]).is_equal_to(
            [("id", 1), ("owner.id", 1)]
        )
        entries = _build_equality_diff(left, right).entries
        assert_that([(entry.path, entry.actual) for entry in entries]).is_equal_to([(".id", 1)])

    @pytest.mark.parametrize(
        ("actual", "expected"),
        [
            ({"cfg": OrderedDict(a=1)}, {"cfg": {"a": 1}}),
            ({"o": {"cfg": OrderedDict(a=1)}}, {"o": {"cfg": {"a": 1}}}),
            ([OrderedDict(a=1)], [{"a": 1}]),
            ({"t": (1, 2)}, {"t": [1, 2]}),
        ],
        ids=str,
    )
    def test_a_container_type_change_is_caught_below_the_top_level(self, actual, expected):
        with pytest.raises(AssertionError):
            assert_that(actual).is_equal_to(expected, strict_types=True)

    def test_a_shared_subnode_is_not_walked_twice(self):
        # forcing the walk gives up CPython's identity shortcut, and a shared subnode is where it does real work
        shared = {"k": 1}
        shared["self"] = shared
        assert_that({"cfg": shared, "n": 1}).is_equal_to({"cfg": shared, "n": 1}, strict_types=True)

    def test_the_same_nan_object_still_compares_equal(self):
        # `nan != nan`, so without the shortcut a strict run would disagree with a plain one over nothing typed
        nan = float("nan")
        assert_that([nan]).is_equal_to([nan])
        assert_that([nan]).is_equal_to([nan], strict_types=True)
        assert_that({"v": nan}).is_equal_to({"v": nan}, strict_types=True)

    def test_negation_goes_through_not_(self):
        assert_that({"a": True}).not_.is_equal_to({"a": 1}, strict_types=True)
        with pytest.raises(TypeError, match="unexpected keyword argument"):
            assert_that(True).is_not_equal_to(1, strict_types=True)

    def test_two_equal_sets_in_a_record_field_are_not_reported(self):
        assert_that(Bag({1, 2}, "a")).is_equal_to(Bag({1, 2}, "a"), strict_types=True)

    def test_a_matcher_stays_exempt_on_the_actual_side_too(self):
        # the exemption reads both operands, so the spelling with the spec on the left is exempt as well
        assert_that(match.greater_than(0)).is_equal_to(5, strict_types=True)
        assert_that({"id": match.greater_than(0)}).is_equal_to({"id": 7}, strict_types=True)
        assert_that([match.greater_than(4)]).is_equal_to([5], strict_types=True)

    @pytest.mark.parametrize(
        ("actual", "expected"),
        [
            ([Point(1, 2)], [PointTwin(1, 2)]),
            ([_PointPair(1, 2)], [_PointPairTwin(1, 2)]),
            ([Point(1, 2)], [{"x": 1, "y": 2}]),
        ],
        ids=["dataclasses", "namedtuples", "object-against-dict"],
    )
    def test_elements_of_another_class_fail_under_ignore(self, actual, expected):
        """Each element was taken apart with no parent walk to compare the two classes, and the pair passed."""
        assert_that(actual).is_equal_to(expected, ignore="z")
        with pytest.raises(AssertionFailure):
            assert_that(actual).is_equal_to(expected, ignore="z", strict_types=True)
        assert_that(match.equal_to(expected, ignore="z", strict_types=True).matches(actual)).is_false()

    def test_a_nested_path_into_another_class_still_shows_why_it_failed(self):
        """Filtering the nested fields copied them into a plain mapping, and the diff lost the class it failed on."""
        with pytest.raises(AssertionFailure) as caught:
            assert_that(Row({"p": Point(1, 2)}, "a")).is_equal_to(
                Row({"p": PointTwin(1, 3)}, "a"), ignore=("box", "p", "y"), strict_types=True
            )
        assert_that([entry.path for entry in caught.value.diff.entries]).is_equal_to(["box.p"])
        assert_that(str(caught.value)).contains("only their types differ")

    def test_the_keyed_type_check_needs_both_sides_to_be_that_container(self):
        """An exempt matcher reaches the key comparison as the counterpart of a real container, and
        nothing there can iterate it: both sides have to be the container kind."""
        assert_that({"cfg": {"a": 1}}).is_equal_to({"cfg": match.is_instance_of(dict)}, strict_types=True)
        assert_that({"tags": {1, 2}}).is_equal_to({"tags": match.is_instance_of(set)}, strict_types=True)


class TestStrictTypesOnStdlibScalars:
    """A timestamp, a decimal or a UUID is a value, not a container, and is treated as one.

    They are listed as atomic for cost - walking past them ran the whole introspection ladder to come
    back with nothing - so what needs pinning is that listing them changed no verdict.
    """

    @pytest.mark.parametrize(
        ("actual", "expected"),
        [
            (datetime.date(2026, 1, 1), datetime.datetime(2026, 1, 1)),
            (decimal.Decimal(1), 1.0),
            (decimal.Decimal(1), 1),
            (uuid.uuid5(uuid.NAMESPACE_DNS, "x"), str(uuid.uuid5(uuid.NAMESPACE_DNS, "x"))),
            (datetime.timedelta(0), 0),
        ],
        ids=str,
    )
    def test_a_type_difference_is_still_caught(self, actual, expected):
        with pytest.raises(AssertionFailure):
            assert_that({"v": actual}).is_equal_to({"v": expected}, strict_types=True)

    def test_the_same_type_still_passes(self):
        moment = datetime.datetime(2026, 1, 1, 12, 30)
        assert_that({"at": moment, "amount": decimal.Decimal("1.5")}).is_equal_to(
            {"at": moment, "amount": decimal.Decimal("1.5")}, strict_types=True
        )

    def test_a_subclass_with_structure_is_still_walked(self):
        class Stamped(datetime.datetime):
            pass

        moment = Stamped(2026, 1, 1)
        assert_that({"at": moment}).is_equal_to({"at": moment}, strict_types=True)
        with pytest.raises(AssertionFailure):
            assert_that({"at": moment}).is_equal_to({"at": datetime.datetime(2026, 1, 1)}, strict_types=True)

    @pytest.mark.parametrize("text", ["a", "a\nb"], ids=["one line", "two lines"])
    def test_a_text_subclass_equal_at_the_root_passes(self, text):
        """Equal and of one type, it was diffed line by line, and a diff with no line in it failed at the root."""

        class Label(str):
            pass

        class Blob(bytes):
            pass

        assert_that(Label(text)).is_equal_to(Label(text), strict_types=True)
        assert_that(Blob(text.encode())).is_equal_to(Blob(text.encode()), strict_types=True)


class TestConfigSurvivesTheFilteredPaths:
    """`ignore` / `include` route the comparison through a separate walk, which must carry the config.

    Every knob was only ever tested on the plain path or on scalar elements, so dropping the config on
    the filtered list and object paths changed nothing the suite looked at: tolerance stopped being
    applied to dict-valued elements and to object fields, silently turning a pass into a failure.
    """

    def test_tolerance_reaches_dict_valued_list_elements(self):
        assert_that([{"value": 1.0, "id": 1}]).is_equal_to([{"value": 1.05, "id": 99}], ignore="id", tolerance=0.1)
        with pytest.raises(AssertionFailure):
            assert_that([{"value": 1.0, "id": 1}]).is_equal_to([{"value": 1.5, "id": 99}], ignore="id", tolerance=0.1)

    def test_tolerance_reaches_object_fields(self):
        assert_that(Point(1.0, 1.0)).is_equal_to(Point(1.05, 99.0), ignore="y", tolerance=0.1)
        with pytest.raises(AssertionFailure):
            assert_that(Point(1.0, 1.0)).is_equal_to(Point(1.5, 99.0), ignore="y", tolerance=0.1)

    def test_a_plain_object_is_opened_to_a_tolerance_by_a_key_option_beside_it(self):
        """A value option leaves a plain object to its own ``==``, and a key option reads it by its attributes."""

        class Price:
            def __init__(self, amount: float) -> None:
                self.amount = amount

        with pytest.raises(AssertionFailure):
            assert_that(Price(1.0)).is_equal_to(Price(1.0), tolerance=0.1)
        assert_that(Price(1.0)).is_equal_to(Price(1.0), ignore="absent")
        with pytest.raises(AssertionFailure):
            assert_that(Price(1.0)).is_equal_to(Price(1.05), ignore="absent")
        assert_that(Price(1.0)).is_equal_to(Price(1.05), ignore="absent", tolerance=0.1)
        with pytest.raises(AssertionFailure):
            assert_that(Price(1.0)).is_equal_to(Price(1.5), ignore="absent", tolerance=0.1)

    @pytest.mark.parametrize("key_option", [{"ignore": "note"}, {"include": "amount"}], ids=["ignore", "include"])
    def test_under_a_key_option_the_equality_of_a_plain_object_is_not_asked(self, key_option):
        class Price:
            __hash__ = None

            def __init__(self, amount: float, note: str) -> None:
                self.amount = amount
                self.note = note

            def __eq__(self, other: object) -> bool:
                raise RuntimeError("its own == was asked")

        assert_that(Price(1.0, "a")).is_equal_to(Price(1.0, "b"), **key_option)
        assert_that(Price(1.0, "a")).is_equal_to(Price(1.05, "b"), **key_option, tolerance=0.1)
        with pytest.raises(AssertionFailure):
            assert_that(Price(1.0, "a")).is_equal_to(Price(1.05, "b"), **key_option)
        with pytest.raises(RuntimeError, match="its own == was asked"):
            assert_that(Price(1.0, "a")).is_equal_to(Price(1.0, "a"), tolerance=0.1)

    def test_strict_types_reaches_a_nested_list_element(self):
        assert_that([[1]]).is_equal_to([[1]], strict_types=True, ignore="absent")
        with pytest.raises(AssertionFailure):
            assert_that([[1]]).is_equal_to([[True]], strict_types=True, ignore="absent")
        with pytest.raises(AssertionFailure):
            assert_that([(1, 2)]).is_equal_to([(True, 2)], strict_types=True, ignore="absent")

    def test_an_element_pair_where_only_one_side_introspects(self):
        # the pair guard is a conjunction: taking either side alone walks a None as if it were a mapping
        with pytest.raises(AssertionFailure) as failure:
            assert_that([1]).is_equal_to([Point(1.0, 2.0)], ignore="id")
        rows = [(entry.path, entry.actual, entry.expected) for entry in failure.value.diff.entries]
        assert_that(rows).is_equal_to([("[0]", 1, Point(1.0, 2.0))])
        with pytest.raises(AssertionFailure) as failure:
            assert_that([Point(1.0, 2.0)]).is_equal_to([1], ignore="id")
        rows = [(entry.path, entry.actual, entry.expected) for entry in failure.value.diff.entries]
        assert_that(rows).is_equal_to([("[0]", Point(1.0, 2.0), 1)])

    def test_a_length_mismatch_carries_both_sides_on_the_exception(self):
        # the message names both sequences, so dropping the structured `actual` cost only the report attachment
        with pytest.raises(AssertionFailure) as failure:
            assert_that([{"a": 1}]).is_equal_to([{"a": 1}, {"b": 2}], ignore="x")
        assert_that(failure.value.actual).is_equal_to([{"a": 1}])
        assert_that(failure.value.expected).is_equal_to([{"a": 1}, {"b": 2}])


class TestConfigEchoedOnFailure:
    """The settings that were in force are named in the message, which is what a reader is asking
    when a field they thought was tolerated or ignored still failed the comparison."""

    def test_a_plain_failure_says_nothing_about_config(self):
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that({"a": 1}).is_equal_to({"a": 2})
        assert_that(str(exc_info.value)).does_not_contain("compared with")

    @pytest.mark.parametrize(
        ("kwargs", "expected"),
        [
            ({"tolerance": 0.001}, "compared with tolerance=0.001"),
            ({"ignore_null": True}, "compared with ignore_null=True"),
            ({"strict_types": True}, "compared with strict_types=True"),
        ],
    )
    def test_each_setting_names_itself(self, kwargs, expected):
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that({"a": 1.0, "b": 2}).is_equal_to({"a": 9.0, "b": 3}, **kwargs)
        assert_that(str(exc_info.value)).contains(expected)

    def test_comparators_are_named_by_key(self):
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that({"n": "A", "b": 2}).is_equal_to(
                {"n": "bb", "b": 3},
                comparators={
                    "n": lambda actual, expected: actual.lower() == expected.lower(),
                    float: lambda actual, expected: True,
                },
            )
        assert_that(str(exc_info.value)).contains("comparators for float, n")

    def test_several_settings_read_as_one_list(self):
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that({"a": 1.0, "b": 2}).is_equal_to({"a": 9.0, "b": 3}, tolerance=0.1, strict_types=True)
        assert_that(str(exc_info.value)).contains("compared with tolerance=0.1, strict_types=True")

    def test_it_reaches_a_scalar_failure_too(self):
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that(True).is_equal_to(1, strict_types=True)
        assert_that(str(exc_info.value)).contains("compared with strict_types=True")

    def test_it_coexists_with_the_ignore_clause(self):
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that({"a": 1, "b": 2.0}).is_equal_to({"a": 9, "b": 5.0}, ignore="a", tolerance=0.1)
        message = str(exc_info.value)
        assert_that(message).contains("ignoring keys <a>")
        assert_that(message).contains("compared with tolerance=0.1")

    def test_the_original_sentence_stays_a_prefix(self):
        # the note is appended on its own line and never rewrites the sentence an existing `match=` reads
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that({"a": 1.0}).is_equal_to({"a": 9.0}, tolerance=0.1)
        first_line = str(exc_info.value).splitlines()[0]
        assert_that(first_line).is_equal_to("Expected <{'a': 1.0}> to be equal to <{'a': 9.0}>, but was not.")

    def test_a_config_with_nothing_in_it_adds_nothing_to_the_sentence(self):
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that({"a": 1}).is_equal_to({"a": 2}, comparators={})
        first_line = str(exc_info.value).splitlines()[0]
        assert_that(first_line).is_equal_to("Expected <{'a': 1}> to be equal to <{'a': 2}>, but was not.")


class TestDecisionSentinelsReachTheDiff:
    """`_node_decision` answers with a sentinel string the walkers branch on.  A leaf verdict that
    does not arrive as `"leaf"` is read as "descend", and descending into a scalar yields nothing, so
    the difference disappears from the diff instead of being reported."""

    def test_a_value_outside_tolerance_is_reported_as_a_leaf(self):
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that({"a": 1.0}).is_equal_to({"a": 9.0}, tolerance=0.1)
        assert_that([entry.path for entry in exc_info.value.diff.entries]).is_equal_to(["a"])

    def test_a_comparator_rejecting_a_pair_is_reported_as_a_leaf(self):
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that({"a": 1}).is_equal_to({"a": 2}, comparators={"a": lambda actual, expected: False})
        assert_that([entry.path for entry in exc_info.value.diff.entries]).is_equal_to(["a"])

    def test_a_comparator_keyed_by_type_owns_its_leaves(self):
        assert_that({"a": 1.4, "b": 2.4}).is_equal_to(
            {"a": 1.0, "b": 2.0}, comparators={float: lambda actual, expected: round(actual) == round(expected)}
        )
        with pytest.raises(AssertionFailure):
            assert_that({"a": 1.4}).is_equal_to(
                {"a": 9.0}, comparators={float: lambda actual, expected: round(actual) == round(expected)}
            )

    def test_a_comparator_owning_a_container_field_stops_the_descent(self):
        # a scalar leaf reads the same either way. A container is where "this leaf differs" and "walk inside
        # it" part company: the path is the field, not a key underneath it.
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that({"a": {"x": 1}}).is_equal_to({"a": {"x": 2}}, comparators={"a": lambda actual, expected: False})
        assert_that([entry.path for entry in exc_info.value.diff.entries]).is_equal_to(["a"])

    def test_the_same_nan_on_both_sides_is_equal_below_the_root_and_not_at_it(self):
        """A tolerance only widens `==`, and a container's `==` holds the very NaN it holds on both sides."""
        nan = float("nan")
        assert_that({"a": nan}).is_equal_to({"a": nan}, tolerance=0.5)
        assert_that([nan]).is_equal_to([nan], tolerance=0.5)
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that(nan).is_equal_to(nan, tolerance=0.5)
        assert_that([entry.path for entry in exc_info.value.diff.entries]).is_equal_to(["."])


class TestBuilderAndMatcherDecideAlike:
    """One relation, two spellings, and they have disagreed twice now.

    First the matcher walked its own route and accepted mapping keys the builder refused. Then the
    builder's key check asked `isinstance(..., dict)` while everything else in the engine judges a
    mapping structurally, so `UserDict` and `MappingProxyType` split them again. The rule is stated
    here over every container category the engine claims to support, rather than per bug.
    """

    _MAPPINGS: ClassVar = [dict, OrderedDict, UserDict, types.MappingProxyType]
    _PAIRS: ClassVar = [
        ({True: "a"}, {1: "a"}),
        ({1: "a"}, {1.0: "a"}),
        ({1: "a"}, {1: "a"}),
        ({"k": {True: 1}}, {"k": {1: 1}}),
        ({"k": 1}, {"k": 1}),
    ]

    @pytest.mark.parametrize("factory", _MAPPINGS, ids=lambda kind: kind.__name__)
    @pytest.mark.parametrize(("actual", "expected"), _PAIRS, ids=str)
    def test_a_mapping_gets_the_same_verdict_from_both(self, factory, actual, expected):
        left, right = factory(actual), factory(expected)
        try:
            assert_that(left).is_equal_to(right, strict_types=True)
            builder_passed = True
        except AssertionError:
            builder_passed = False
        matcher_passed = match.equal_to(right, strict_types=True).matches(left)
        assert_that(matcher_passed).described_as(f"{factory.__name__}: builder said {builder_passed}").is_equal_to(
            builder_passed
        )

    @pytest.mark.parametrize("factory", [set, frozenset], ids=lambda kind: kind.__name__)
    @pytest.mark.parametrize(("actual", "expected"), [({1}, {1.0}), ({True}, {1}), ({1, 2}, {2, 1})], ids=str)
    def test_a_set_gets_the_same_verdict_from_both(self, factory, actual, expected):
        left, right = factory(actual), factory(expected)
        try:
            assert_that(left).is_equal_to(right, strict_types=True)
            builder_passed = True
        except AssertionError:
            builder_passed = False
        assert_that(match.equal_to(right, strict_types=True).matches(left)).is_equal_to(builder_passed)


@dataclass
class _Order:
    total: float


@dataclass
class _Invoice:
    total: float


@dataclass
class _Reading:
    value: float
    taken_at: int = dataclasses.field(compare=False)


@dataclass
class _Account:
    id: int
    name: str


class _RaisingEqualityList(list):
    def __eq__(self, other):
        raise RuntimeError("no equality here")

    __hash__ = None


@dataclass(eq=False)
class _RefusingBase:
    total: float

    def __eq__(self, other):
        raise RuntimeError("asked the base")


@dataclass(eq=False)
class _AnsweringChild(_RefusingBase):
    def __eq__(self, other):
        return False


class _TupleFriendlyList(list):
    def __eq__(self, other):
        return list(self) == list(other) if isinstance(other, tuple) else super().__eq__(other)

    __hash__ = None


@dataclass(eq=False)
class _ByTotal:
    total: float
    note: str

    def __eq__(self, other):
        return self.total == getattr(other, "total", None)


@dataclass(eq=False)
class _ByTotalToo:
    total: float
    note: str


class _Money(decimal.Decimal):
    pass


class _Label(str):
    pass


_OPTIONS = [
    pytest.param({"tolerance": 0.01}, id="tolerance"),
    pytest.param({"ignore_null": True}, id="ignore_null"),
    pytest.param({"comparators": {str: lambda actual, expected: actual.lower() == expected.lower()}}, id="comparators"),
    pytest.param({"strict_types": True}, id="strict_types"),
]


class TestAnOptionOnlyRelaxesTheLeaves:
    """An option says how leaves compare, and never makes equal what `==` rejects by kind or by order.

    With any option the verdict came from the structural walk, which compared parts: a list against a
    tuple, or two dataclasses of different classes, had no differing part and passed.
    """

    @pytest.mark.parametrize("options", _OPTIONS)
    def test_a_list_is_not_a_tuple(self, options):
        assert_that(assert_that([1.0, 2.0]).check().is_equal_to((1.0, 2.0), **options).passed).is_false()
        assert_that(assert_that({"xs": [1.0]}).check().is_equal_to({"xs": (1.0,)}, **options).passed).is_false()

    @pytest.mark.parametrize("options", _OPTIONS)
    def test_two_dataclass_classes_are_not_equal(self, options):
        assert_that(assert_that(_Order(1.0)).check().is_equal_to(_Invoice(1.0), **options).passed).is_false()

    @pytest.mark.parametrize("options", [option for option in _OPTIONS if option.id != "strict_types"])
    def test_an_equality_of_its_own_is_still_asked(self, options):
        """The kind decides only where both sides' `__eq__` decline the pair; a type may accept the other kind."""
        assert_that(_TupleFriendlyList([1.0, 2.0])).is_equal_to((1.0, 2.001), **{**options, "tolerance": 0.01})
        assert_that(_ByTotal(1.0, "x")).is_equal_to(_ByTotalToo(1.001, "x"), **{**options, "tolerance": 0.01})

    @pytest.mark.parametrize(
        "options",
        [pytest.param({}, id="no options"), *(option for option in _OPTIONS if option.id != "strict_types")],
    )
    def test_an_equality_that_raises_is_handed_on(self, options):
        """`==` is asked, where `!=` went through the inherited `list.__ne__` and never reached `__eq__`."""
        with pytest.raises(RuntimeError, match="no equality here"):
            assert_that(_RaisingEqualityList([1.0])).is_equal_to((1.001,), **options)

    def test_a_decline_probe_that_raises_where_eq_did_not_decides_nothing(self):
        """`==` asks the subclass first and has its answer, while the probe of each side asks the base as well."""
        assert_that(_RefusingBase(1.0)).is_equal_to(_AnsweringChild(1.001), tolerance=0.01)

    @pytest.mark.parametrize("options", _OPTIONS)
    def test_the_matcher_agrees(self, options):
        assert_that(match.equal_to((1.0, 2.0), **options).matches([1.0, 2.0])).is_false()
        assert_that(match.equal_to(_Invoice(1.0), **options).matches(_Order(1.0))).is_false()

    @pytest.mark.parametrize("options", _OPTIONS)
    def test_the_order_of_an_ordered_dict_still_counts(self, options):
        first = OrderedDict([("a", 1), ("b", 2)])
        second = OrderedDict([("b", 2), ("a", 1)])
        outcome = assert_that(first).check().is_equal_to(second, **options)
        assert_that(outcome.passed).is_false()
        assert_that([(entry.path, entry.actual, entry.expected) for entry in outcome.diff.entries]).is_equal_to(
            [(".", ["a", "b"], ["b", "a"])]
        )
        assert_that(match.equal_to(second, **options).matches(first)).is_false()

    def test_a_filtered_ordered_dict_keeps_its_order_too(self):
        first = OrderedDict([("a", 1), ("b", 2), ("c", 3)])
        second = OrderedDict([("b", 2), ("a", 1), ("c", 4)])
        assert_that(assert_that(first).check().is_equal_to(second, ignore="c").passed).is_false()
        assert_that(assert_that(first).check().is_equal_to(OrderedDict(first), ignore="c").passed).is_true()

    @pytest.mark.parametrize("options", [*_OPTIONS, pytest.param({"ignore": "unrelated"}, id="ignore")])
    def test_a_field_left_out_of_equality_stays_out(self, options):
        assert_that(_Reading(1.0, taken_at=1)).is_equal_to(_Reading(1.0, taken_at=2), **options)


_UTC = datetime.timezone.utc
_NOON_UTC = datetime.datetime(2026, 1, 1, 12, tzinfo=_UTC)
_NOON_MSK = _NOON_UTC.astimezone(datetime.timezone(datetime.timedelta(hours=3)))
_SAME_ZONE = {
    datetime.datetime: lambda actual, expected: actual == expected and actual.utcoffset() == expected.utcoffset()
}


@dataclass
class _Holder:
    value: object


_SHAPES = [
    pytest.param(lambda value: value, id="root"),
    pytest.param(lambda value: {"k": value}, id="dict"),
    pytest.param(lambda value: [value], id="list"),
    pytest.param(lambda value: (value,), id="tuple"),
    pytest.param(_Holder, id="dataclass"),
    pytest.param(lambda value: Pair(value, 0), id="namedtuple"),
    pytest.param(lambda value: [{"k": value}], id="dict-in-list"),
    pytest.param(lambda value: {"k": [value]}, id="list-in-dict"),
]


class TestEveryShapeAnswersAlike:
    """A comparator decides every leaf it matches, and a tolerance only widens `==`, whatever holds the pair.

    A dict was walked leaf by leaf while a list, a tuple or a dataclass was asked `==` first and left alone
    when it held, so a comparator stricter than `==` failed `{"k": x}` and passed `[x]`, and the very NaN
    both sides hold failed a tolerance in a dict and passed it in a list.
    """

    @pytest.mark.parametrize("shape", _SHAPES)
    def test_a_comparator_stricter_than_equality_fails_the_pair_in_every_shape(self, shape):
        assert _NOON_UTC == _NOON_MSK
        outcome = assert_that(shape(_NOON_UTC)).check().is_equal_to(shape(_NOON_MSK), comparators=_SAME_ZONE)
        assert_that(outcome.passed).is_false()
        assert_that(match.equal_to(shape(_NOON_MSK), comparators=_SAME_ZONE).matches(shape(_NOON_UTC))).is_false()

    @pytest.mark.parametrize("shape", _SHAPES)
    def test_a_comparator_looser_than_equality_passes_the_pair_in_every_shape(self, shape):
        loose = {datetime.datetime: lambda actual, expected: actual.date() == expected.date()}
        later = _NOON_UTC + datetime.timedelta(hours=1)
        assert_that(shape(_NOON_UTC)).is_equal_to(shape(later), comparators=loose)
        assert_that(match.equal_to(shape(later), comparators=loose).matches(shape(_NOON_UTC))).is_true()

    @pytest.mark.parametrize("shape", [param for param in _SHAPES if param.id != "root"])
    def test_the_same_nan_under_a_tolerance_is_equal_in_every_container(self, shape):
        nan = float("nan")
        assert_that(shape(nan)).is_equal_to(shape(nan), tolerance=0.5)
        assert_that(match.equal_to(shape(nan), tolerance=0.5).matches(shape(nan))).is_true()

    def test_a_comparator_owns_a_root_mapping_too(self):
        comparators = {dict: lambda actual, expected: actual.keys() == expected.keys()}
        assert_that({"a": 1}).is_equal_to({"a": 2}, comparators=comparators)
        assert_that(match.equal_to({"a": 2}, comparators=comparators).matches({"a": 1})).is_true()

    def test_the_comparator_is_asked_only_where_a_leaf_matches_it(self):
        calls = []

        def on_floats(actual, expected):
            calls.append((actual, expected))
            return actual == expected

        assert_that([{"a": 1.5, "b": "x"}, [2.5]]).is_equal_to(
            [{"a": 1.5, "b": "x"}, [2.5]], comparators={float: on_floats}
        )
        assert_that(calls).is_equal_to([(1.5, 1.5), (2.5, 2.5)])

    def test_a_container_both_sides_share_is_equal_to_itself(self):
        """Identity holds a shared container equal without asking a comparator about what it holds, as `==` does."""
        shared = [1.0]
        never = {float: lambda actual, expected: False}
        assert_that({"k": shared}).is_equal_to({"k": shared}, comparators=never)
        assert_that(assert_that({"k": [1.0]}).check().is_equal_to({"k": [1.0]}, comparators=never).passed).is_false()

    def test_a_set_member_is_not_paired_with_a_comparator(self):
        """A set has no positions to pair its members by, so `==` decides it whatever a comparator would say."""
        never = {int: lambda actual, expected: False}
        always = {int: lambda actual, expected: True}
        assert_that({"s": {1, 2}}).is_equal_to({"s": {1, 2}}, comparators=never)
        assert_that(assert_that({1}).check().is_equal_to({2}, comparators=always).passed).is_false()


class TestKeySelectorsReachEveryShape:
    """`ignore` and `include` mean the same thing on every shape they accept, and are never dropped in silence."""

    @pytest.mark.parametrize("spelled", [0, [0]], ids=["bare", "listed"])
    def test_a_falsy_key_is_ignored(self, spelled):
        assert_that({0: "a", 1: "b"}).is_equal_to({1: "b"}, ignore=spelled)
        assert_that({"": "a", "k": "b"}).is_equal_to({"k": "b"}, ignore="")

    def test_a_falsy_key_is_included(self):
        assert_that({0: "a", 1: "b"}).is_equal_to({0: "a", 1: "c"}, include=0)
        outcome = assert_that({1: "b"}).check().is_equal_to({1: "b"}, include=0)
        assert_that(outcome.message).starts_with("Expected <{1: 'b'}> to include key <0>")

    def test_an_empty_selector_still_asks_for_nothing(self):
        assert_that(5).is_equal_to(5, ignore=[])
        assert_that({"a": 1}).is_equal_to({"a": 1}, include=[])

    @pytest.mark.parametrize(("left", "right"), [(_Money("1.00"), _Money("2.00")), (_Label("a"), _Label("b"))])
    def test_a_builtin_subclass_is_compared_by_value(self, left, right):
        assert_that(assert_that([left]).check().is_equal_to([right], ignore="id").passed).is_false()
        assert_that([left]).is_equal_to([type(left)(left)], ignore="id")

    def test_a_path_into_a_dataclass_held_by_a_mapping(self):
        assert_that({"user": _Account(1, "a")}).is_equal_to({"user": _Account(2, "a")}, ignore=[("user", "id")])
        outcome = (
            assert_that({"user": _Account(1, "a")})
            .check()
            .is_equal_to({"user": _Account(2, "b")}, ignore=[("user", "id")])
        )
        assert_that(outcome.passed).is_false()
        assert_that([entry.path for entry in outcome.diff.entries]).is_equal_to(["user.name"])

    def test_an_object_against_a_mapping_answers_as_its_list_spelling(self):
        assert_that(_Account(1, "a")).is_equal_to({"id": 9, "name": "a"}, ignore="id")
        assert_that({"id": 9, "name": "a"}).is_equal_to(_Account(1, "a"), ignore="id")
        assert_that([_Account(1, "a")]).is_equal_to([{"id": 9, "name": "a"}], ignore="id")

    def test_a_missing_include_key_is_one_failure(self):
        outcome = assert_that({"a": 1}).check().is_equal_to({"a": 1}, include="b")
        assert_that(outcome.message).starts_with("Expected <{'a': 1}> to include key <b>")
        with pytest.raises(AssertionError) as caught, soft_assertions():
            assert_that({"a": 1}).is_equal_to({"a": 1}, include="b")
        assert_that(caught.value.failures).is_length(1)

    def test_the_matcher_takes_the_builders_route(self):
        assert_that(match.equal_to(_Account(2, "a"), ignore="id").matches(_Account(1, "a"))).is_true()
        assert_that(match.equal_to(_Account(2, "b"), ignore="id").matches(_Account(1, "a"))).is_false()
        assert_that(match.equal_to([_Account(2, "a")], ignore="id").matches([_Account(1, "a")])).is_true()
        assert_that(
            match.equal_to([_Account(2, "a")], include="name").matches([_Account(1, "a"), _Account(3, "c")])
        ).is_false()
        assert_that(match.equal_to([_Account(2, "a")], include="nothing").matches([_Account(1, "a")])).is_false()

    def test_a_value_without_fields_is_refused_by_both(self):
        with pytest.raises(TypeError, match="ignore/include requires"):
            assert_that(5).is_equal_to(5, ignore="x")
        assert_that(match.equal_to(5, ignore="x").matches(5)).is_false()
        assert_that(match.equal_to([5], ignore="x").matches([5])).is_true()
        assert_that(match.equal_to([5], ignore="x").matches([6])).is_false()

    def test_strict_types_reads_only_the_keys_still_compared(self):
        assert_that({True: "a", "keep": 1}).is_equal_to({1: "a", "keep": 1}, include="keep", strict_types=True)
        assert_that({True: "a", "keep": 1}).is_equal_to({1: "a", "keep": 1}, ignore=True, strict_types=True)
        outcome = assert_that({True: "a", "keep": 1}).check().is_equal_to({1: "a", "keep": 1}, strict_types=True)
        assert_that(outcome.passed).is_false()
