from collections import namedtuple
from dataclasses import dataclass

import pytest

from assertpy import AssertionFailure, assert_that, match
from assertpy._engine._diff import _walk_leaves

Pair = namedtuple("Pair", ["a", "b"])


@dataclass
class Point:
    x: int
    y: int


class FakeModel:
    """Minimal pydantic-style model: anything exposing ``model_dump()`` walks like a model."""

    def __init__(self, **data):
        self._data = data

    def model_dump(self):
        return dict(self._data)


def _leaf_texts(walk):
    """The leaf walk keyed by its rendered path, which is what these tests are about.

    `_walk_leaves` yields the path object, so the rendered text and the machine steps cannot drift.
    These tests pin the text, rendered the way the entry builder renders it: the root is ``.``.
    """
    return {path.text or ".": leaf for path, leaf in walk}


class TestWalkLeavesTraversal:
    def test_top_level_dict(self):
        leaves = _leaf_texts(_walk_leaves({"a": 1, "b": 2}))
        assert_that(leaves).is_equal_to({"a": 1, "b": 2})

    def test_nested_dict_paths_are_dotted(self):
        leaves = _leaf_texts(_walk_leaves({"outer": {"inner": 1}}))
        assert_that(leaves).is_equal_to({"outer.inner": 1})

    def test_top_level_list_paths_are_indexed(self):
        leaves = _leaf_texts(_walk_leaves([10, 20]))
        assert_that(leaves).is_equal_to({"[0]": 10, "[1]": 20})

    def test_nested_list_paths(self):
        leaves = _leaf_texts(_walk_leaves([[1, 2]]))
        assert_that(leaves).is_equal_to({"[0][0]": 1, "[0][1]": 2})

    def test_top_level_dataclass(self):
        leaves = _leaf_texts(_walk_leaves(Point(1, 2)))
        assert_that(leaves).is_equal_to({"x": 1, "y": 2})

    def test_nested_dataclass(self):
        leaves = _leaf_texts(_walk_leaves({"p": Point(1, 2)}))
        assert_that(leaves).is_equal_to({"p.x": 1, "p.y": 2})

    def test_top_level_namedtuple(self):
        leaves = _leaf_texts(_walk_leaves(Pair(1, 2)))
        assert_that(leaves).is_equal_to({"a": 1, "b": 2})

    def test_nested_namedtuple(self):
        leaves = _leaf_texts(_walk_leaves({"pair": Pair(1, 2)}))
        assert_that(leaves).is_equal_to({"pair.a": 1, "pair.b": 2})

    def test_top_level_model(self):
        leaves = _leaf_texts(_walk_leaves(FakeModel(x=1, y=2)))
        assert_that(leaves).is_equal_to({"x": 1, "y": 2})

    def test_nested_model(self):
        leaves = _leaf_texts(_walk_leaves({"m": FakeModel(x=1)}))
        assert_that(leaves).is_equal_to({"m.x": 1})

    def test_bare_scalar_is_root_leaf(self):
        leaves = [(path.text or ".", leaf) for path, leaf in _walk_leaves(5)]
        assert_that(leaves).is_equal_to([(".", 5)])

    def test_set_is_single_leaf(self):
        value = frozenset({1, 2})
        leaves = [(path.text or ".", leaf) for path, leaf in _walk_leaves(value)]
        assert_that(leaves).is_equal_to([(".", value)])

    def test_a_value_met_again_inside_itself_is_no_leaf(self):
        data = {"a": 1}
        data["self"] = data
        leaves = _leaf_texts(_walk_leaves(data))
        assert_that(leaves).is_equal_to({"a": 1})

    def test_a_graph_with_no_leaf_yields_none(self):
        only = {}
        only["self"] = only
        assert_that(list(_walk_leaves(only))).is_empty()

    def test_a_none_past_a_cycle_is_still_reached(self):
        data = {"a": [None]}
        data["self"] = data
        leaves = _leaf_texts(_walk_leaves(data))
        assert_that(leaves).is_equal_to({"a[0]": None})

    def test_circular_through_list_is_guarded(self):
        lst = [1]
        lst.append(lst)
        leaves = _leaf_texts(_walk_leaves(lst))
        assert_that(leaves).is_equal_to({"[0]": 1})

    def test_circular_through_dataclass_is_guarded(self):
        @dataclass
        class Node:
            value: int
            child: object = None

        node = Node(1)
        node.child = node
        leaves = _leaf_texts(_walk_leaves(node))
        assert_that(leaves).is_equal_to({"value": 1})

    def test_circular_through_namedtuple_is_guarded(self):
        holder = []
        pair = Pair(holder, 2)
        holder.append(pair)
        leaves = _leaf_texts(_walk_leaves(pair))
        assert_that(leaves).is_equal_to({"b": 2})

    def test_circular_through_model_is_guarded(self):
        holder = []
        model = FakeModel(items=holder)
        holder.append(model)
        leaves = _leaf_texts(_walk_leaves(model))
        assert_that(leaves).is_equal_to({})

    def test_empty_container_yields_no_leaves(self):
        assert_that(list(_walk_leaves({}))).is_empty()
        assert_that(list(_walk_leaves([]))).is_empty()


class TestAllFieldsSatisfy:
    def test_flat_dict_pass(self):
        assert_that({"a": 1, "b": 2}).all_fields_satisfy(match.is_positive())

    def test_nested_pass_with_callable(self):
        assert_that({"a": 1, "nested": {"b": 2}}).all_fields_satisfy(lambda x: x > 0)

    def test_list_pass(self):
        assert_that([1, [2, 3]]).all_fields_satisfy(match.is_positive())

    def test_returns_self_for_chaining(self):
        assert_that({"a": 1}).all_fields_satisfy(match.is_positive()).has_no_none_fields()

    def test_single_failure_reports_path(self):
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that({"a": 1, "b": {"c": -2}}).all_fields_satisfy(match.is_positive())
        message = str(exc_info.value)
        assert_that(message).contains("1 field did not")
        diff = exc_info.value.diff
        assert_that(diff.kind).is_equal_to("match")
        assert_that(diff.entries).is_length(1)
        assert_that(diff.entries[0].path).is_equal_to("b.c")
        assert_that(diff.entries[0].actual).is_equal_to(-2)
        assert_that(diff.entries[0].expected).is_equal_to("a positive value")

    def test_multiple_failures_pluralize(self):
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that([-1, -2, 3]).all_fields_satisfy(match.is_positive())
        assert_that(str(exc_info.value)).contains("2 fields did not")
        assert_that(exc_info.value.diff.entries).is_length(2)

    def test_failing_callable_described_in_diff(self):
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that([5]).all_fields_satisfy(lambda x: x < 0)
        assert_that(exc_info.value.diff.entries[0].expected).contains("lambda")

    def test_failing_unnamed_callable_described_in_diff(self):
        # a callable object (no __name__) reads as "the given predicate", not a raw <object at 0x...> repr
        class _Negative:
            def __call__(self, value):
                return value < 0

        with pytest.raises(AssertionFailure) as exc_info:
            assert_that([5]).all_fields_satisfy(_Negative())
        assert_that(exc_info.value.diff.entries[0].expected).is_equal_to("the given predicate")

    def test_bad_matcher_raises_type_error(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that([1]).all_fields_satisfy(42)
        assert_that(str(exc_info.value)).is_equal_to(
            "given matcher arg must be a Matcher or a callable, but was <42> (int)"
        )

    def test_bad_matcher_on_empty_raises_type_error(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that([]).all_fields_satisfy("not a matcher")
        assert_that(str(exc_info.value)).is_equal_to(
            "given matcher arg must be a Matcher or a callable, but was <'not a matcher'> (str)"
        )

    def test_empty_container_passes(self):
        assert_that({}).all_fields_satisfy(match.is_positive())


class TestHasNoNoneFields:
    def test_pass(self):
        assert_that({"id": 1, "profile": {"name": "Alice"}}).has_no_none_fields()

    def test_dataclass_pass(self):
        assert_that(Point(1, 2)).has_no_none_fields()

    def test_top_level_none_fails(self):
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that({"id": 1, "name": None}).has_no_none_fields()
        diff = exc_info.value.diff
        assert_that(diff.entries).is_length(1)
        assert_that(diff.entries[0].path).is_equal_to("name")
        assert_that(diff.entries[0].expected).is_equal_to("a non-None value")

    def test_nested_none_fails(self):
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that({"a": 1, "b": {"c": None}}).has_no_none_fields()
        assert_that(exc_info.value.diff.entries[0].path).is_equal_to("b.c")

    def test_bare_none_fails(self):
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that(None).has_no_none_fields()
        assert_that(exc_info.value.diff.entries[0].path).is_equal_to(".")
