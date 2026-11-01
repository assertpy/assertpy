import collections
import dataclasses
import sys
import types
import typing

import pytest

from assertpy import AssertionFailure, assert_that, match
from assertpy._engine import _equality


def test_ignore_key():
    assert_that({"a": 1}).is_equal_to({}, ignore="a")
    assert_that({"a": 1, "b": 2}).is_equal_to({"a": 1}, ignore="b")
    assert_that({"a": 1, "b": 2}).is_equal_to({"a": 1, "b": 2}, ignore="c")
    assert_that({"a": 1, "b": {"x": 2, "y": 3}}).is_equal_to({"a": 1}, ignore="b")


def test_ignore_list_of_keys():
    assert_that({"a": 1, "b": 2, "c": 3}).is_equal_to({"a": 1, "b": 2, "c": 3}, ignore=[])
    assert_that({"a": 1, "b": 2, "c": 3}).is_equal_to({"a": 1, "b": 2}, ignore=["c"])
    assert_that({"a": 1, "b": 2, "c": 3}).is_equal_to({"a": 1}, ignore=["b", "c"])
    assert_that({"a": 1, "b": 2, "c": 3}).is_equal_to({}, ignore=["a", "b", "c"])
    assert_that({"a": 1, "b": 2, "c": 3}).is_equal_to({"a": 1, "b": 2, "c": 3}, ignore=["d"])
    assert_that({"a": 1, "b": 2, "c": 3}).is_equal_to({"b": 2}, ignore=["c", "d", "e", "a"])


def test_ignore_set_of_keys():
    assert_that({"a": 1, "b": 2, "c": 3}).is_equal_to({"a": 1}, ignore={"b", "c"})
    assert_that({"a": 1, "b": 2, "c": 3}).is_equal_to({}, ignore=frozenset({"a", "b", "c"}))
    assert_that({"a": 1, "b": 2, "c": 3}).is_equal_to({"a": 1, "b": 2, "c": 3}, ignore=set())
    assert_that({"a": 1, "b": {"x": 2, "y": 3}}).is_equal_to({"a": 1, "b": {"x": 2}}, ignore={("b", "y")})


def test_ignore_bytes_key():
    assert_that({b"a": 1, b"b": 2}).is_equal_to({b"a": 1}, ignore=b"b")


def test_ignore_rejects_one_shot_iterable():
    with pytest.raises(TypeError, match="ignore must be a key"):
        assert_that({"a": 1, "b": 2}).is_equal_to({"a": 1}, ignore=(key for key in ("b",)))
    with pytest.raises(TypeError, match="ignore must be a key"):
        assert_that({"a": 1, "b": 2}).is_equal_to({"a": 1}, ignore={"a": 1}.keys())


def test_ignore_deep_key():
    assert_that({"a": 1, "b": {"x": 2, "y": 3}}).is_equal_to({"a": 1}, ignore="b")
    assert_that({"a": 1, "b": {"x": 2, "y": 3}}).is_equal_to({"a": 1}, ignore=[("b",)])
    assert_that({"a": 1, "b": {"x": 2, "y": 3}}).is_equal_to({"a": 1, "b": {"x": 2}}, ignore=("b", "y"))
    assert_that({"a": 1, "b": {"x": 2, "y": 3}}).is_equal_to({"a": 1, "b": {"x": 2}}, ignore=[("b", "y")])
    assert_that({"a": 1, "b": {"x": 2, "y": 3}}).is_equal_to(
        {"a": 1, "b": {"x": 2}}, ignore=[("b", "y"), ("b", "x", "j")]
    )
    assert_that({"a": 1, "b": {"c": 2, "d": {"e": 3, "f": {"x": 4, "y": 5}}}}).is_equal_to({}, ignore=["a", "b"])
    assert_that({"a": 1, "b": {"c": 2, "d": {"e": 3, "f": {"x": 4, "y": 5}}}}).is_equal_to({"a": 1}, ignore="b")
    assert_that({"a": 1, "b": {"c": 2, "d": {"e": 3, "f": {"x": 4, "y": 5}}}}).is_equal_to(
        {"a": 1, "b": {"c": 2}}, ignore=("b", "d")
    )
    assert_that({"a": 1, "b": {"c": 2, "d": {"e": 3, "f": {"x": 4, "y": 5}}}}).is_equal_to(
        {"a": 1, "b": {"c": 2, "d": {"e": 3}}}, ignore=("b", "d", "f")
    )
    assert_that({"a": 1, "b": {"c": 2, "d": {"e": 3, "f": {"x": 4, "y": 5}}}}).is_equal_to(
        {"a": 1, "b": {"c": 2, "d": {"e": 3, "f": {"x": 4, "y": 6}}}}, ignore=("b", "d", "f", "y")
    )
    assert_that({"a": 1, "b": {"c": 2, "d": {"e": 3, "f": {"x": 4, "y": 5}}}}).is_equal_to(
        {"a": 1, "b": {"c": 2, "d": {"e": 3, "f": {"x": 4, "y": 5}}}}, ignore=("b", "d", "f", "y", "foo")
    )


def test_ordered():
    ordered = collections.OrderedDict([("a", 1), ("b", 2)])
    assert_that(ordered).is_equal_to({"a": 1, "b": 2})


def test_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that({"a": 1, "b": 2}).is_equal_to({"a": 1, "b": 3})
    assert_that(str(exc_info.value)).is_equal_to("Expected <{.., 'b': 2}> to be equal to <{.., 'b': 3}>, but was not.")


def test_failure_single_entry():
    with pytest.raises(AssertionError) as exc_info:
        assert_that({"a": 1}).is_equal_to({"a": 2})
    assert_that(str(exc_info.value)).is_equal_to("Expected <{'a': 1}> to be equal to <{'a': 2}>, but was not.")


def test_failure_multi_entry():
    with pytest.raises(AssertionError) as exc_info:
        assert_that({"a": 1, "b": 2, "c": 3}).is_equal_to({"a": 1, "b": 3, "c": 3})
    # 'a' matched ahead of the changed key and 'c' matched behind it, so 'b' is marked on both sides
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <{.., 'b': 2, ..}> to be equal to <{.., 'b': 3, ..}>, but was not."
    )


def test_failure_multi_entry_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that({"a": 1, "b": 2, "c": 3}).is_equal_to({"a": 1, "b": 3, "c": 4})
    assert_that(str(exc_info.value)).contains("'b': 2").contains("'b': 3").contains("'c': 3").contains(
        "'c': 4"
    ).ends_with("but was not.")


def test_failure_deep_dict():
    with pytest.raises(AssertionError) as exc_info:
        assert_that({"a": 1, "b": {"x": 2, "y": 3}}).is_equal_to({"a": 1, "b": {"x": 2, "y": 4}})
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <{.., 'b': {.., 'y': 3}}> to be equal to <{.., 'b': {.., 'y': 4}}>, but was not."
    )


def test_failure_deep_dict_single_key():
    with pytest.raises(AssertionError) as exc_info:
        assert_that({"a": 1, "b": {"x": 2, "y": 3}}).is_equal_to({"a": 1, "b": {"x": 2}})
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <{.., 'b': {.., 'y': 3}}> to be equal to <{.., 'b': {..}}>, but was not."
        "\nevery shared key matches, and actual carries keys the expected side does not"
    )


def test_failure_very_deep_dict():
    with pytest.raises(AssertionError) as exc_info:
        assert_that({"a": 1, "b": {"c": 2, "d": {"e": 3, "f": {"x": 4, "y": 5}}}}).is_equal_to(
            {"a": 1, "b": {"c": 2, "d": {"e": 3, "f": {"x": 4, "y": 6}}}}
        )
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <{.., 'b': {.., 'd': {.., 'f': {.., 'y': 5}}}}> to be equal to "
        "<{.., 'b': {.., 'd': {.., 'f': {.., 'y': 6}}}}>, but was not."
    )


def test_failure_ignore():
    with pytest.raises(AssertionError) as exc_info:
        assert_that({"a": 1, "b": 2}).is_equal_to({"a": 1, "b": 3}, ignore="c")
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <{.., 'b': 2}> to be equal to <{.., 'b': 3}> ignoring keys <c>, but was not."
    )


def test_failure_ignore_single_entry():
    with pytest.raises(AssertionError) as exc_info:
        assert_that({"a": 1}).is_equal_to({"a": 2}, ignore="c")
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <{'a': 1}> to be equal to <{'a': 2}> ignoring keys <c>, but was not."
    )


def test_failure_ignore_multi_keys():
    with pytest.raises(AssertionError) as exc_info:
        assert_that({"a": 1}).is_equal_to({"a": 2}, ignore=["x", "y", "z"])
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <{'a': 1}> to be equal to <{'a': 2}> ignoring keys <'x', 'y', 'z'>, but was not."
    )


def test_failure_ignore_multi_deep_keys():
    with pytest.raises(AssertionError) as exc_info:
        assert_that({"a": 1}).is_equal_to({"a": 2}, ignore=[("q", "r", "s"), ("x", "y", "z")])
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <{'a': 1}> to be equal to <{'a': 2}> ignoring keys <'q.r.s', 'x.y.z'>, but was not."
    )


def test_failure_ignore_mixed_keys():
    with pytest.raises(AssertionError) as exc_info:
        assert_that({"a": 1}).is_equal_to({"a": 2}, ignore=["b", ("c"), ("d", "e"), ("q", "r", "s"), ("x", "y", "z")])
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <{'a': 1}> to be equal to <{'a': 2}> ignoring keys <'b', 'c', 'd.e', 'q.r.s', 'x.y.z'>, but was not."
    )


def test_failure_int_keys():
    with pytest.raises(AssertionError) as exc_info:
        assert_that({1: "a", 2: "b"}).is_equal_to({1: "a", 3: "b"})
    assert_that(str(exc_info.value)).is_equal_to("Expected <{.., 2: 'b'}> to be equal to <{.., 3: 'b'}>, but was not.")


def test_failure_deep_int_keys():
    with pytest.raises(AssertionError) as exc_info:
        assert_that({1: "a", 2: {3: "b", 4: "c"}}).is_equal_to({1: "a", 2: {3: "b", 5: "c"}}, ignore=(2, 3))
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <{.., 2: {4: 'c'}}> to be equal to <{.., 2: {5: 'c'}}> ignoring keys <2.3>, but was not."
    )


def test_failure_tuple_keys():
    with pytest.raises(AssertionError) as exc_info:
        assert_that({(1, 2): "a", (3, 4): "b"}).is_equal_to({(1, 2): "a", (3, 4): "c"})
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <{.., (3, 4): 'b'}> to be equal to <{.., (3, 4): 'c'}>, but was not."
    )


def test_failure_tuple_keys_ignore():
    with pytest.raises(AssertionError) as exc_info:
        assert_that({(1, 2): "a", (3, 4): "b"}).is_equal_to({(1, 2): "a", (3, 4): "c"}, ignore=(1, 2))
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <{(3, 4): 'b'}> to be equal to <{(3, 4): 'c'}> ignoring keys <1.2>, but was not."
    )


def test_failure_deep_tuple_keys_ignore():
    with pytest.raises(AssertionError) as exc_info:
        assert_that({(1, 2): "a", (3, 4): {(5, 6): "b", (7, 8): "c"}}).is_equal_to(
            {(1, 2): "a", (3, 4): {(5, 6): "b", (7, 8): "d"}}, ignore=((3, 4), (5, 6))
        )
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <{.., (3, 4): {(7, 8): 'c'}}> to be equal to <{.., (3, 4): {(7, 8): 'd'}}>"
        " ignoring keys <(3, 4).(5, 6)>, but was not."
    )


def test_failure_single_item_tuple_keys_ignore():
    # due to unpacking-fu, single item tuple keys must be tupled in ignore statement, so this works:
    assert_that({(1,): "a", (2,): "b"}).is_equal_to({(1,): "a", (2,): "c"}, ignore=((2,),))

    with pytest.raises(AssertionError) as exc_info:
        assert_that({(1,): "a", (2,): "b"}).is_equal_to({(1,): "a"}, ignore=(2,))
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <{.., (2,): 'b'}> to be equal to <{..}> ignoring keys <2>, but was not."
        "\nevery shared key matches, and actual carries keys the expected side does not"
    )


def test_failure_single_item_tuple_keys_ignore_error_msg():
    with pytest.raises(AssertionError) as exc_info:
        assert_that({(1,): "a"}).is_equal_to({(1,): "b"}, ignore=((2,),))
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <{(1,): 'a'}> to be equal to <{(1,): 'b'}> ignoring keys <2>, but was not."
    )


def test_include_key():
    assert_that({"a": 1, "b": 2}).is_equal_to({"a": 1}, include="a")
    assert_that({"a": 1, "b": {"x": 2, "y": 3}}).is_equal_to({"a": 1}, include="a")
    assert_that({"a": 1, "b": {"x": 2, "y": 3}}).is_equal_to({"b": {"x": 2, "y": 3}}, include="b")


def test_include_list_of_keys():
    assert_that({"a": 1, "b": 2, "c": 3}).is_equal_to({"a": 1, "b": 2, "c": 3}, include=["a", "b", "c"])
    assert_that({"a": 1, "b": 2, "c": 3}).is_equal_to({"a": 1, "b": 2}, include=["a", "b"])
    assert_that({"a": 1, "b": 2, "c": 3}).is_equal_to({"a": 1}, include=["a"])
    assert_that({"a": 1, "b": 2, "c": 3}).is_equal_to({"b": 2}, include=["b"])
    assert_that({"a": 1, "b": 2, "c": 3}).is_equal_to({"c": 3}, include=["c"])


def test_include_set_of_keys():
    assert_that({"a": 1, "b": 2, "c": 3}).is_equal_to({"a": 1, "b": 2}, include={"a", "b"})
    assert_that({"a": 1, "b": 2, "c": 3}).is_equal_to({"a": 1}, include=frozenset({"a"}))


def test_include_rejects_one_shot_iterable():
    with pytest.raises(TypeError, match="include must be a key"):
        assert_that({"a": 1, "b": 2}).is_equal_to({"a": 1}, include=(key for key in ("a",)))


def test_include_deep_key():
    assert_that({"a": 1, "b": {"x": 2, "y": 3}}).is_equal_to({"b": {"x": 2, "y": 3}}, include="b")
    assert_that({"a": 1, "b": {"x": 2, "y": 3}}).is_equal_to({"b": {"x": 2}}, include=("b", "x"))
    assert_that({"a": 1, "b": {"c": 2, "d": {"e": 3, "f": {"x": 4, "y": 5}}}}).is_equal_to(
        {"b": {"c": 2, "d": {"e": 3, "f": {"x": 4, "y": 5}}}}, include="b"
    )
    assert_that({"a": 1, "b": {"c": 2, "d": {"e": 3, "f": {"x": 4, "y": 5}}}}).is_equal_to(
        {"b": {"c": 2}}, include=("b", "c")
    )
    assert_that({"a": 1, "b": {"c": 2, "d": {"e": 3, "f": {"x": 4, "y": 5}}}}).is_equal_to(
        {"b": {"d": {"e": 3, "f": {"x": 4, "y": 5}}}}, include=("b", "d")
    )
    assert_that({"a": 1, "b": {"c": 2, "d": {"e": 3, "f": {"x": 4, "y": 5}}}}).is_equal_to(
        {
            "b": {
                "d": {
                    "e": 3,
                }
            }
        },
        include=("b", "d", "e"),
    )
    assert_that({"a": 1, "b": {"c": 2, "d": {"e": 3, "f": {"x": 4, "y": 5}}}}).is_equal_to(
        {"b": {"d": {"f": {"x": 4, "y": 5}}}}, include=("b", "d", "f")
    )
    assert_that({"a": 1, "b": {"c": 2, "d": {"e": 3, "f": {"x": 4, "y": 5}}}}).is_equal_to(
        {"b": {"d": {"f": {"x": 4}}}}, include=("b", "d", "f", "x")
    )
    assert_that({"a": 1, "b": {"c": 2, "d": {"e": 3, "f": {"x": 4, "y": 5}}}}).is_equal_to(
        {"b": {"d": {"f": {"y": 5}}}}, include=("b", "d", "f", "y")
    )


def test_failure_include():
    with pytest.raises(AssertionError) as exc_info:
        assert_that({"a": 1}).is_equal_to({"a": 2}, include="a")
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <{'a': 1}> to be equal to <{'a': 2}> including keys <a>, but was not."
    )


def test_failure_include_missing():
    with pytest.raises(AssertionError) as exc_info:
        assert_that({"a": 1}).is_equal_to({"a": 1}, include="b")
    assert_that(str(exc_info.value)).is_equal_to("Expected <{'a': 1}> to include key <b>, but did not include key <b>.")


def test_failure_include_multiple_missing():
    with pytest.raises(AssertionError) as exc_info:
        assert_that({"a": 1}).is_equal_to({"a": 1}, include=["b", "c"])
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <{'a': 1}> to include keys <'b', 'c'>, but did not include keys <'b', 'c'>."
    )


def test_failure_include_deep_missing():
    with pytest.raises(AssertionError) as exc_info:
        assert_that({"a": {"b": 2}}).is_equal_to({"a": {"c": 3}}, include=("a", "c"))
    assert_that(str(exc_info.value)).is_equal_to("Expected <{'b': 2}> to include key <c>, but did not include key <c>.")


def test_failure_include_multi_keys():
    with pytest.raises(AssertionError) as exc_info:
        assert_that({"a": 1, "b": 2}).is_equal_to({"a": 1, "b": 3}, include=["a", "b"])
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <{.., 'b': 2}> to be equal to <{.., 'b': 3}> including keys <'a', 'b'>, but was not."
    )


def test_failure_include_deep_keys():
    with pytest.raises(AssertionError) as exc_info:
        assert_that({"a": {"b": 1}}).is_equal_to({"a": {"b": 2}}, include=("a", "b"))
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <{'a': {'b': 1}}> to be equal to <{'a': {'b': 2}}> including keys <a.b>, but was not."
    )


def test_ignore_and_include_key():
    assert_that({"a": 1}).is_equal_to({}, ignore="a", include="a")
    assert_that({"a": 1, "b": 2}).is_equal_to({"a": 1}, ignore="b", include="a")
    assert_that({"a": 1, "b": {"x": 2, "y": 3}}).is_equal_to({"b": {"y": 3}}, ignore=("b", "x"), include="b")


def test_ignore_and_include_list_of_keys():
    assert_that({"a": 1, "b": 2, "c": 3}).is_equal_to({"a": 1, "c": 3}, ignore=["b"], include=["a", "b", "c"])
    assert_that({"a": 1, "b": 2, "c": 3}).is_equal_to({"a": 1, "b": 2}, ignore=["c"], include=["a", "b"])
    assert_that({"a": 1, "b": 2, "c": 3}).is_equal_to({"a": 1}, ignore=["b", "c"], include=["a", "b"])
    assert_that({"a": 1, "b": 2, "c": 3}).is_equal_to({"a": 1}, ignore=["c"], include=["a"])
    assert_that({"a": 1, "b": 2, "c": 3}).is_equal_to({"b": 2}, ignore=["a"], include=["b"])
    assert_that({"a": 1, "b": 2, "c": 3}).is_equal_to({"c": 3}, ignore=["b"], include=["c"])


def test_ignore_and_include_deep_key():
    assert_that({"a": 1, "b": {"x": 2, "y": 3}}).is_equal_to({"b": {"x": 2, "y": 3}}, ignore="a", include="b")
    assert_that({"a": 1, "b": {"x": 2, "y": 3}}).is_equal_to({"b": {"x": 2}}, ignore=("b", "y"), include=("b", "x"))
    assert_that({"a": 1, "b": {"c": 2, "d": {"e": 3, "f": {"x": 4, "y": 5}}}}).is_equal_to(
        {"b": {"c": 2, "d": {"e": 3}}}, ignore=("b", "d", "f"), include="b"
    )


def test_ignore_deep_sibling_key():
    actual = {"a": 1, "b": {"c": 2, "d": {"e": 3}}}
    expected = {"a": 1, "b": {"c": 3, "d": {"e": 3}}}
    assert_that(actual).is_equal_to(expected, ignore=("b", "c"))


def test_ignore_nested_deep_sibling_key():
    actual = {"a": 1, "b": {"c": 2, "d": {"e": 3}}}
    expected = {"a": 1, "b": {"c": 2, "d": {"e": 4}}}
    assert_that(actual).is_equal_to(expected, ignore=("b", "d"))


def test_failure_deep_mismatch_when_ignoring_nested_deep_key():
    actual = {"a": 1, "b": {"c": 2, "d": {"e": 3}}}
    expected = {"a": 1, "b": {"c": 3, "d": {"e": 4}}}
    with pytest.raises(AssertionError) as exc_info:
        assert_that(actual).is_equal_to(expected, ignore=("b", "d"))
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <{.., 'b': {'c': 2}}> to be equal to <{.., 'b': {'c': 3}}> ignoring keys <b.d>, but was not."
    )


def test_failure_top_mismatch_when_ignoring_single_nested_key():
    actual = {"a": 1, "b": {"c": 2}}
    expected = {"a": 2, "b": {"c": 3}}
    with pytest.raises(AssertionError) as exc_info:
        assert_that(actual).is_equal_to(expected, ignore=("b", "c"))
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <{'a': 1, ..}> to be equal to <{'a': 2, ..}> ignoring keys <b.c>, but was not."
    )


def test_failure_top_mismatch_when_ignoring_single_nested_sibling_key():
    actual = {"a": 1, "b": {"c": 2, "d": {"e": 3}}}
    expected = {"a": 2, "b": {"c": 2, "d": {"e": 4}}}
    with pytest.raises(AssertionError) as exc_info:
        assert_that(actual).is_equal_to(expected, ignore=("b", "d"))
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <{'a': 1, ..}> to be equal to <{'a': 2, ..}> ignoring keys <b.d>, but was not."
    )


def test_failure_deep_mismatch_when_ignoring_double_nested_sibling_key():
    actual = {"a": 1, "b": {"c": 2, "d": {"e": 3}, "f": {"g": 5}}}
    expected = {"a": 1, "b": {"c": 2, "d": {"e": 4}, "f": {"g": 5}}}
    with pytest.raises(AssertionError) as exc_info:
        assert_that(actual).is_equal_to(expected, ignore=("b", "f", "g"))
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <{.., 'b': {.., 'd': {'e': 3}, ..}}> to be equal to "
        "<{.., 'b': {.., 'd': {'e': 4}, ..}}> ignoring keys <b.f.g>, but was not."
    )


def test_ignore_all_nested_keys():
    assert_that({"a": {"b": 1}}).is_equal_to({}, ignore="a")
    assert_that({"a": {"b": 1}}).is_equal_to({"a": {}}, ignore=[("a", "b")])
    assert_that({"a": {"b": 1, "c": 2}}).is_equal_to({"a": {}}, ignore=[("a", "b"), ("a", "c")])
    assert_that({"a": 1, "b": {"c": 2}}).is_equal_to({"b": {}}, ignore=["a", ("b", "c")])


class _BadRepr:
    """Identity equality on purpose: two instances must actually differ so the repr gets rendered."""

    def __repr__(self):
        raise RuntimeError("broken repr")


class TestDictErrorSurvivesBrokenRepr:
    """Error rendering must produce the AssertionError, never leak a user's raising __repr__."""

    def test_broken_repr_value_still_renders_the_failure(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that({"a": _BadRepr(), "b": 1}).is_equal_to({"a": _BadRepr(), "b": 2})
        assert_that(str(exc_info.value)).contains("unreprable _BadRepr")

    def test_broken_repr_key_still_renders_the_failure(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that({_BadRepr(): 1, "b": 1}).is_equal_to({_BadRepr(): 1, "b": 2})
        assert_that(str(exc_info.value)).contains("to be equal to")


def test_ignore_include_applies_to_dict_elements_in_a_list():
    assert_that([{"a": 1, "b": 2}]).is_equal_to([{"a": 1, "b": 999}], ignore="b")
    assert_that([{"a": 1, "b": 2}]).is_equal_to([{"a": 1, "b": 999}], include="a")
    with pytest.raises(AssertionError):
        assert_that([{"a": 1, "b": 2}]).is_equal_to([{"a": 9, "b": 2}], ignore="b")


def test_cyclic_dict_under_ignore_is_treated_as_equal():
    # a revisited pair counts as equal rather than recursing; without it the walk never sees the repeat
    def holding_a_ring(tag):
        ring = {"k": 1}
        ring["self"] = ring
        return {"t": tag, "ring": ring}

    assert_that(holding_a_ring(1)).is_equal_to(holding_a_ring(2), ignore="t")


@pytest.mark.parametrize(
    "option",
    [{"ignore": "k"}, {"include": "self"}, {"include": ("self", "k")}, {"ignore": "k", "strict_types": True}],
    ids=repr,
)
def test_a_key_spec_applies_at_its_own_level_of_a_cyclic_dict_as_of_a_flat_one(option):
    # the pair met again below was called equal as the one above, which was asked with the key left out
    actual = {"k": 1}
    actual["self"] = actual
    expected = {"k": 2}
    expected["self"] = expected
    flat_actual, flat_expected = {"k": 1, "self": {"k": 1}}, {"k": 2, "self": {"k": 2}}
    with pytest.raises(AssertionError) as flat:
        assert_that(flat_actual).is_equal_to(flat_expected, **option)
    with pytest.raises(AssertionError) as cyclic:
        assert_that(actual).is_equal_to(expected, **option)
    assert_that([(entry.path, entry.actual, entry.expected) for entry in cyclic.value.diff.entries]).is_equal_to(
        [(entry.path, entry.actual, entry.expected) for entry in flat.value.diff.entries]
    )


_Held = collections.namedtuple("_Held", "to")


def _knotted(value: object) -> tuple:
    """A tuple that leads back to itself through a list and a second tuple, which is the one made again."""
    inner: list = []
    outer = (inner,)
    inner.append((outer, value))
    return outer


class _Kept(list):
    """A list of a class of its own, which is rebuilt by its class and so cannot be put on record empty."""


@dataclasses.dataclass
class _Link:
    next: "_Link | None" = None
    value: int = 0
    items: list = dataclasses.field(default_factory=list)


def _ring(value, length=1, make=_Link):
    """*length* nodes holding *value*, each one's ``next`` the following one and the last one's the first."""
    nodes = [make(value=value) for _ in range(length)]
    for index, node in enumerate(nodes):
        node.next = nodes[(index + 1) % length]
    return nodes[0]


def _dict_ring(value, length=1):
    nodes = [{"value": value} for _ in range(length)]
    for index, node in enumerate(nodes):
        node["next"] = nodes[(index + 1) % length]
    return nodes[0]


class TestAValueThatHoldsItselfUnderIgnoreAndInclude:
    """Taken apart field by field, a dataclass, an attrs instance or a model that leads back to itself came apart
    without end, whether or not the field that led back was compared."""

    @pytest.mark.parametrize("length", [1, 2, 3])
    def test_the_field_that_leads_back_is_left_out(self, length):
        assert_that(_ring(1, length)).is_equal_to(_ring(1, length), ignore="next")
        assert_that(_ring(1, length)).is_equal_to(_ring(1, length), include="value")
        assert_that(match.equal_to(_ring(1, length), ignore="next").matches(_ring(1, length))).is_true()

    @pytest.mark.parametrize("ring", [_ring, _dict_ring])
    @pytest.mark.parametrize("length", [1, 2, 3])
    def test_the_field_that_leads_back_is_compared_and_a_pair_met_again_is_equal(self, ring, length):
        assert_that(ring(1, length)).is_equal_to(ring(1, length), ignore="items")

    @pytest.mark.parametrize("ring", [_ring, _dict_ring])
    def test_a_difference_beside_the_cycle_fails_and_is_named(self, ring):
        with pytest.raises(AssertionFailure) as caught:
            assert_that(ring(1, 2)).is_equal_to(ring(2, 2), ignore="items")
        assert_that([entry.path for entry in caught.value.diff.entries]).contains("value")
        with pytest.raises(AssertionFailure) as caught:
            assert_that(ring(1)).is_equal_to(ring(2), include="value")
        assert_that([(entry.path, entry.actual, entry.expected) for entry in caught.value.diff.entries]).is_equal_to(
            [("value", 1, 2)]
        )

    def test_a_value_reached_twice_without_a_cycle_is_compared_both_times(self):
        shared, other = _Link(value=1), _Link(value=2)
        actual = [_Link(value=0, items=[shared, shared])]
        assert_that(actual).is_equal_to([_Link(value=0, items=[_Link(value=1), _Link(value=1)])], ignore="next")
        with pytest.raises(AssertionFailure):
            assert_that(actual).is_equal_to([_Link(value=0, items=[_Link(value=1), other])], ignore="next")

    def test_an_attrs_instance_and_a_model_that_hold_themselves(self):
        attrs = pytest.importorskip("attrs", reason="attrs not installed")
        pydantic = pytest.importorskip("pydantic", reason="pydantic not installed")

        @attrs.define
        class Knot:
            value: int = 0
            next: object = None

        class Chain(pydantic.BaseModel):
            value: int = 0
            next: typing.Any = None

        for make in (Knot, Chain):
            assert_that(_ring(1, 2, make)).is_equal_to(_ring(1, 2, make), ignore="next")
            assert_that(_ring(1, 2, make)).is_equal_to(_ring(1, 2, make), ignore="other")
            with pytest.raises(AssertionFailure):
                assert_that(_ring(1, 2, make)).is_equal_to(_ring(2, 2, make), ignore="other")

    @pytest.mark.parametrize(
        "held_in",
        [
            lambda value: {"to": value},
            lambda value: [value],
            lambda value: (value,),
            lambda value: _Held(value),
            lambda value: ((value,), 0),
            lambda value: _Kept([value]),
            _knotted,
            lambda value: _Held(_knotted(value)),
        ],
        ids=[
            "a dict",
            "a list",
            "a tuple",
            "a namedtuple",
            "a tuple in a tuple",
            "a list subclass",
            "a tuple that holds itself through a list",
            "a namedtuple holding such a tuple",
        ],
    )
    def test_a_record_behind_a_container_met_again_is_taken_apart_as_the_first_time(self, held_in):
        """The container met again was left as it was, and the record behind it was then compared whole: against
        a dict of the same fields it differed there, and one level up it had not."""

        def looped():
            first, second = _Link(), _Link()
            first.next = held_in(second)
            second.next = first.next
            return first

        def as_dicts(value=0):
            first: dict = {"next": None, "value": 0, "items": []}
            second: dict = {"next": None, "value": value, "items": []}
            first["next"] = held_in(second)
            second["next"] = first["next"]
            return first

        assert_that(as_dicts()).is_equal_to(looped(), ignore="missing")
        assert_that(looped()).is_equal_to(as_dicts(), ignore="missing")
        with pytest.raises(AssertionFailure):
            assert_that(looped()).is_equal_to(as_dicts(1), ignore="missing")

    def test_a_cycle_through_a_list_is_read_where_the_lists_own_comparison_does_not_end(self):
        """A list is compared by its own ``==``, and where Python does not finish that on a graph that holds
        itself, the pair is walked: met again inside itself, it is equal as far as that pair goes."""
        actual, expected = _Link(value=1), _Link(value=1)
        actual.items.append(actual)
        expected.items.append(expected)
        assert_that(actual).is_equal_to(expected, ignore="items")
        assert_that(actual).is_equal_to(expected, ignore="next")
        assert_that([actual]).is_equal_to([expected], ignore="next")
        expected.value = 2
        for one, other in ((actual, expected), ([actual], [expected])):
            with pytest.raises(AssertionFailure):
                assert_that(one).is_equal_to(other, ignore="next")

    def test_a_field_compared_through_a_key_is_held_raw_where_its_tuple_was_met_again(self):
        """A tuple met again is put back rebuilt, except in a field attrs compares through a key, which reads the
        value as it is held: here the class of what the tuple holds."""
        attrs = pytest.importorskip("attrs", reason="attrs not installed")

        @attrs.define
        class Keyed:
            keyed: object = attrs.field(eq=lambda held: held and type(held[0]).__name__, default=None)
            plain: object = None
            back: object = None

        def looped(shared):
            inner = Keyed()
            held = (inner,)
            outer = Keyed(keyed=held, plain=held if shared else (inner,))
            inner.back = outer
            return outer

        assert_that(looped(shared=True)).is_equal_to(looped(shared=False), ignore="missing")
        assert_that(looped(shared=False)).is_equal_to(looped(shared=True), ignore="missing")

    def test_the_plain_way_gives_up_on_a_value_that_holds_itself_long_before_the_frames_run_out(self):
        """Left to `RecursionError`, a raised limit ran out of C stack first, which ends the process."""
        with pytest.raises(_equality._NestedTooDeepError):
            _equality._flattened(_ring(1), frozenset({"dataclass"}))

    def test_where_the_plain_way_runs_out_of_frames_the_one_that_remembers_is_tried(self):
        """It takes a frame a level where the plain one takes two, so it fits where that one did not."""
        nested: object = 1
        for _ in range(60):
            nested = [nested]
        record, through = _Link(items=[nested]), frozenset({"dataclass"})
        expected = _equality._flattened(record, through)
        frame, depth = sys._getframe(), 0
        while frame is not None:
            frame, depth = frame.f_back, depth + 1
        limit = sys.getrecursionlimit()
        sys.setrecursionlimit(depth + 100)
        try:
            with pytest.raises(RecursionError):
                _equality._flattened(record, through)
            taken = _equality._fields_through(record, through)
        finally:
            sys.setrecursionlimit(limit)
        assert_that(taken).is_equal_to(expected)

    def test_a_record_nested_deeper_than_the_plain_way_goes_is_compared(self):
        def chain(last):
            head = _Link(value=last)
            for _ in range(80):
                head = _Link(next=head)
            return head

        assert_that(chain(1)).is_equal_to(chain(1), ignore="items")
        with pytest.raises(AssertionFailure) as caught:
            assert_that(chain(1)).is_equal_to(chain(2), ignore="items")
        assert_that([entry.path for entry in caught.value.diff.entries]).is_equal_to(["next." * 80 + "value"])

    def test_both_ways_of_taking_apart_agree_where_nothing_leads_back(self):
        """The way that remembers runs only where the plain one gives up, so nothing else compares them."""
        attrs = pytest.importorskip("attrs", reason="attrs not installed")
        pydantic = pytest.importorskip("pydantic", reason="pydantic not installed")
        point = collections.namedtuple("point", "x y")

        class Falsy:
            """A key that is there and says it is not: asked for its truth, the plain way took the field apart."""

            def __call__(self, held):
                return held

            def __bool__(self):
                return False

        @attrs.define
        class Tagged:
            name: str = attrs.field(eq=str.lower)
            hidden: int = attrs.field(eq=False, default=0)
            inner: object = None
            raw: object = attrs.field(eq=Falsy(), default=None)

        @dataclasses.dataclass
        class Row:
            key: int
            cells: object
            note: str = dataclasses.field(default="", compare=False)

        class Sheet(pydantic.BaseModel):
            rows: list
            meta: dict

        kept = type("Kept", (dict,), {})
        row = Row(1, [point(1, Row(2, ("a", {"k": Row(3, kept(n=1))})))], note="left out")
        values = [
            (row, frozenset({"dataclass"})),
            (Tagged("A", 1, Tagged("b", 2, [row]), raw=Tagged("c")), frozenset({"attrs"})),
            (
                Sheet(rows=[row, row], meta={"r": row, "nested": Sheet(rows=[], meta={})}),
                frozenset({"model", "dataclass"}),
            ),
        ]
        for value, through in values:
            plain = _equality._flattened(value, through)
            assert_that(_equality._flattened_once(value, through, {})).is_equal_to(plain)
            assert_that(repr(_equality._flattened_once(value, through, {}))).is_equal_to(repr(plain))
        for taken in (_equality._flattened(row, values[0][1]), _equality._flattened_once(row, values[0][1], {})):
            deepest = taken["cells"][0].y["cells"][1]["k"]["cells"]
            assert_that((type(deepest), deepest.kind)).is_equal_to((_equality.TakenApart, kept))

    @pytest.mark.parametrize("length", [0, 1])
    def test_a_record_used_as_a_dict_key_stays_a_key(self, length):
        """Taken apart like a value, a frozen dataclass used as a key could not be hashed, cycle or not."""

        @dataclasses.dataclass(frozen=True)
        class Key:
            value: int

        def holder(count):
            link = _ring(1, length) if length else _Link(value=1)
            link.items = {Key(1): count, (Key(2), "b"): [Key(3)]}
            return link

        assert_that(holder(0)).is_equal_to(holder(0), ignore="next")
        with pytest.raises(AssertionFailure):
            assert_that(holder(0)).is_equal_to(holder(1), ignore="next")

    def test_a_tuple_met_again_while_it_is_taken_apart_stays_as_it_is(self):
        held: list = []
        pair = (_Link(value=1), held)
        held.append(pair)
        assert_that(_Link(value=0, items=[pair])).is_equal_to(_Link(value=0, items=[pair]), ignore="next")


class TestTheDiffHonoursTheFilters:
    """The verdict and the report must agree on which keys took part.  Before this, `ignore` and
    `include` reached only the sentence: a failure said "including keys <b>" and then printed a diff
    whose first entry was a key that had never been compared."""

    def test_an_ignored_key_is_absent_from_the_diff(self):
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that({"a": 1, "b": 2}).is_equal_to({"a": 9, "b": 3}, ignore="a")
        assert_that([entry.path for entry in exc_info.value.diff.entries]).is_equal_to(["b"])

    def test_only_included_keys_reach_the_diff(self):
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that({"a": 1, "b": 2}).is_equal_to({"a": 9, "b": 3}, include="b")
        assert_that([entry.path for entry in exc_info.value.diff.entries]).is_equal_to(["b"])

    def test_a_nested_ignored_path_is_absent_from_the_diff(self):
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that({"o": {"x": 1, "y": 2}}).is_equal_to({"o": {"x": 9, "y": 3}}, ignore=("o", "x"))
        assert_that([entry.path for entry in exc_info.value.diff.entries]).is_equal_to(["o.y"])

    def test_an_ignored_key_is_absent_from_the_printed_values(self):
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that({"a": 1, "b": 2}).is_equal_to({"a": 9, "b": 3}, ignore="a")
        assert_that(str(exc_info.value)).does_not_contain("9")

    def test_the_unfiltered_pair_is_still_what_the_failure_carries(self):
        # the filter is a reporting concern: `actual` and `expected` stay the values the caller passed
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that({"a": 1, "b": 2}).is_equal_to({"a": 9, "b": 3}, ignore="a")
        assert_that(exc_info.value.actual).is_equal_to({"a": 1, "b": 2})
        assert_that(exc_info.value.expected).is_equal_to({"a": 9, "b": 3})

    def test_filtering_leaves_an_unfiltered_comparison_alone(self):
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that({"a": 1, "b": 2}).is_equal_to({"a": 9, "b": 3})
        assert_that([entry.path for entry in exc_info.value.diff.entries]).is_equal_to(["a", "b"])


class TestAMisspeltOptionIsRefused:
    """A silently ignored option is the worst kind of green test: the reader is certain they tightened
    the comparison, the comparison was never tightened, and nothing says so.  No error, no warning,
    and no type error either, because a ``**kwargs`` signature makes every spelling legal to a checker.

    The matcher spelling of the same option has always failed loudly, because a real parameter list
    gets that from the interpreter for free.  These pin the same manners on the kwargs entry point.
    """

    def test_the_correct_spelling_still_takes_effect(self):
        with pytest.raises(AssertionFailure):
            assert_that({"c": 1}).is_equal_to({"c": True}, strict_types=True)

    @pytest.mark.parametrize(
        ("typo", "suggestion"),
        [
            ("strict_type", "strict_types"),
            ("tolerence", "tolerance"),
            ("ignore_nul", "ignore_null"),
            ("comparator", "comparators"),
            ("includes", "include"),
        ],
    )
    def test_a_near_miss_names_the_option_it_meant(self, typo, suggestion):
        with pytest.raises(TypeError) as exc_info:
            assert_that({"c": 1}).is_equal_to({"c": True}, **{typo: True})
        assert_that(str(exc_info.value)).contains(typo).contains(f"did you mean {suggestion!r}?")

    def test_a_word_resembling_nothing_is_still_refused(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that({"c": 1}).is_equal_to({"c": 1}, nonsense=1)
        assert_that(str(exc_info.value)).contains("nonsense").does_not_contain("did you mean")

    def test_several_unknown_options_are_all_named(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that({"c": 1}).is_equal_to({"c": 1}, nonsense=1, drivel=2)
        message = str(exc_info.value)
        assert_that(message).contains("arguments").contains("nonsense").contains("drivel")

    def test_every_documented_option_is_accepted(self):
        # the guard is a list, and a list can fall behind the parameters it guards
        assert_that({"a": 1.0, "b": 2}).is_equal_to(
            {"a": 1.0, "b": 2},
            ignore=[],
            include=None,
            tolerance=0.1,
            comparators={},
            ignore_null=False,
            strict_types=False,
        )


@dataclasses.dataclass
class _Holder:
    v: int
    next: object = None


class TestADictBesideARecordIsReadAsDeep:
    """A record is taken apart all the way down for a key option, and so is the dict it is compared with.

    Read one level deep, the dict held an equal record whole against the fields of the one the record holds,
    and the comparison failed on two values that are equal.
    """

    @pytest.mark.parametrize("option", [{"ignore": "v"}, {"ignore": "missing"}, {"include": "next"}])
    def test_at_the_top_on_either_side(self, option):
        record, payload = _Holder(0, _Holder(1)), {"v": 0, "next": _Holder(1)}
        assert_that(record).is_equal_to(payload, **option)
        assert_that(payload).is_equal_to(record, **option)

    def test_as_an_element_of_a_sequence(self):
        assert_that([_Holder(0, [_Holder(1)])]).is_equal_to([{"v": 9, "next": [_Holder(1)]}], ignore="v")

    def test_under_a_path_that_enters_both(self):
        actual, expected = {"o": {"v": 0, "next": _Holder(1)}}, {"o": _Holder(9, _Holder(1))}
        assert_that(actual).is_equal_to(expected, ignore=("o", "v"))
        assert_that(expected).is_equal_to(actual, ignore=("o", "v"))

    def test_a_record_under_them_that_differs_still_fails_at_its_field(self):
        record, payload = _Holder(0, _Holder(1)), {"v": 0, "next": _Holder(2)}
        with pytest.raises(AssertionFailure) as caught:
            assert_that(record).is_equal_to(payload, ignore="missing")
        assert_that([entry.path for entry in caught.value.diff.entries]).is_equal_to(["next.v"])

    def test_the_failure_hands_back_the_dict_it_was_given_and_not_the_copy_it_read(self):
        record, payload = _Holder(0, _Holder(1)), {"v": 0, "next": _Holder(2)}
        with pytest.raises(AssertionFailure) as caught:
            assert_that(payload).is_equal_to(record, ignore="missing")
        assert_that(caught.value.actual).is_same_as(payload)
        assert_that(caught.value.actual["next"]).is_same_as(payload["next"])
        with pytest.raises(AssertionFailure) as caught:
            assert_that(record).is_equal_to(payload, ignore="missing")
        assert_that(caught.value.expected).is_same_as(payload)

    def test_a_record_with_no_equality_of_its_own_is_read_by_its_fields_on_either_side(self):
        # under a key option the fields are what is compared, as they are under a record
        token = dataclasses.make_dataclass("Token", [("value", str)], eq=False)
        assert_that(_Holder(0, token("a"))).is_equal_to({"v": 9, "next": token("a")}, ignore="v")
        assert_that(_Holder(0, token("a"))).is_equal_to(_Holder(9, token("a")), ignore="v")
        with pytest.raises(AssertionFailure):
            assert_that(_Holder(0, token("a"))).is_equal_to({"v": 9, "next": token("b")}, ignore="v")

    def test_a_record_under_two_dicts_is_read_by_its_fields_only_where_a_path_enters_it(self):
        actual, expected = {"v": 0, "next": _Holder(1)}, {"v": 9, "next": {"v": 1, "next": None}}
        with pytest.raises(AssertionFailure):
            assert_that(actual).is_equal_to(expected, ignore="v")
        assert_that(actual).is_equal_to(expected, ignore=["v", ("next", "missing")])

    def test_the_diff_of_a_failed_sequence_goes_as_deep_on_the_dict_side(self):
        actual, expected = [{"v": 0, "next": _Holder(1)}], [_Holder(0, _Holder(2))]
        with pytest.raises(AssertionFailure) as caught:
            assert_that(actual).is_equal_to(expected, ignore="missing")
        assert_that([entry.path for entry in caught.value.diff.entries]).is_equal_to(["[0].next.v"])

    def test_a_dict_that_is_a_record_as_well_keeps_its_keys(self):
        @dataclasses.dataclass
        class Keyed(dict):
            v: int

        @dataclasses.dataclass
        class Record:
            v: int

        held = Keyed(1)
        held["extra"] = 2
        for value, other in ((held, Record(1)), (Record(1), held)):
            with pytest.raises(AssertionFailure):
                assert_that(value).is_equal_to(other, ignore="missing")
        assert_that(held).is_equal_to({"extra": 2}, ignore="missing")
        assert_that(_equality.as_fields(held, Record(1))).is_same_as(held)

    def test_what_is_a_dict_is_asked_of_the_class_and_not_of_the_value(self):
        class SaysDict:
            __class__ = property(lambda self: dict)

            def __init__(self):
                self.v = 0
                self.next = None

        says = SaysDict()
        assert_that(isinstance(says, dict)).is_true()
        assert_that(_equality.as_fields(says)).is_not_same_as(says)
        assert_that(_equality.as_fields({"v": 0}, says)).is_equal_to({"v": 0})
        assert_that(says).is_equal_to(_Holder(0), ignore="missing")
        assert_that(_Holder(0)).is_equal_to(says, ignore="missing")
        assert_that({"o": says}).is_equal_to({"o": _Holder(9)}, ignore=("o", "v"))

    @pytest.mark.parametrize("kind", [dict, list, tuple])
    def test_a_value_that_says_what_it_is_not_is_left_whole_where_it_is_held(self, kind):
        says = type("Says", (), {"__class__": property(lambda self: kind), "_fields": ()})()
        assert_that(isinstance(says, kind)).is_true()
        a_list_that_says = type("AListThatSays", (list,), {"__class__": property(lambda self: kind)})([1])
        a_tuple_that_says = type("ATupleThatSays", (tuple,), {"__class__": property(lambda self: kind)})((1,))
        ring = {"v": 0, "next": says, "more": a_list_that_says, "and": a_tuple_that_says}
        ring["me"] = ring
        for payload in ({"v": 0, "next": says}, {"v": 0, "next": [says]}, _Holder(0, says), ring):
            with pytest.raises(AssertionFailure):
                assert_that(payload).is_equal_to(_Holder(0, _Holder(1)), ignore="missing")

    def test_a_dict_that_is_a_record_is_read_where_it_is_held_as_its_own_equality_reads_it(self):
        @dataclasses.dataclass
        class Keyed(dict):
            v: int

        @dataclasses.dataclass
        class Plain:
            v: int

        held = Keyed(1)
        held["extra"] = 2
        assert_that(held == Keyed(1)).is_true()
        # by its fields, which is how a record holding it was always read: its own `==` does not read its keys
        assert_that(_Holder(0, held)).is_equal_to(_Holder(0, Plain(1)), ignore="missing")
        assert_that({"v": 0, "next": held}).is_equal_to(_Holder(0, Plain(1)), ignore="missing")

    @pytest.mark.parametrize(
        "mapping",
        [types.MappingProxyType, lambda held: collections.ChainMap(held)],
        ids=["a mapping proxy", "a chain map"],
    )
    def test_a_mapping_that_is_no_dict_is_read_by_its_keys_beside_a_record(self, mapping):
        record = _Holder(0, None)
        assert_that(mapping({"v": 0, "next": None})).is_equal_to(record, ignore="missing")
        assert_that(record).is_equal_to(mapping({"v": 0, "next": None}), ignore="missing")
        assert_that(record).is_equal_to(mapping({"v": 9, "next": None}), ignore="v")
        for value, other in ((mapping({"v": 1, "next": None}), record), (record, mapping({"v": 1, "next": None}))):
            with pytest.raises(AssertionFailure) as caught:
                assert_that(value).is_equal_to(other, ignore="missing")
            assert_that([entry.path for entry in caught.value.diff.entries]).is_equal_to(["v"])
        with pytest.raises(AssertionFailure):
            assert_that(mapping({"v": 0, "next": None, "more": 1})).is_equal_to(record, ignore="missing")

    def test_a_record_that_answers_as_a_mapping_is_still_read_by_its_fields(self):
        @dataclasses.dataclass
        class Row:
            v: int
            next: object = None

            def keys(self):
                return ["column"]

            def __getitem__(self, key):
                return "cell"

            def __iter__(self):
                return iter(self.keys())

        assert_that(Row(0)).is_equal_to(_Holder(0), ignore="missing")
        assert_that(_Holder(0)).is_equal_to(Row(0), ignore="missing")
        with pytest.raises(AssertionFailure):
            assert_that(Row(1)).is_equal_to(_Holder(0), ignore="missing")

    def test_a_dict_beside_a_model_is_read_through_the_dataclasses_a_model_is_read_through(self):
        pydantic = pytest.importorskip("pydantic")

        class Shape(pydantic.BaseModel):
            at: _Holder
            name: str = "s"

        shape, payload = Shape(at=_Holder(1)), {"at": {"v": 1, "next": None}, "name": "s"}
        assert_that(payload).is_equal_to(shape, ignore="missing")
        assert_that(shape).is_equal_to(payload, ignore="missing")
        assert_that({"at": _Holder(1), "name": "s"}).is_equal_to(shape, ignore="missing")

    def test_the_matcher_answers_as_the_builder_does(self):
        record, payload = _Holder(0, _Holder(1)), {"v": 0, "next": _Holder(1)}
        assert_that(match.equal_to(payload, ignore="v").matches(record)).is_true()
        assert_that(match.equal_to(record, ignore="v").matches(payload)).is_true()


class TestWhatARecordHoldsIsRebuiltAsItIs:
    """Taken apart for a key option, a value under a record is rebuilt, and the rebuilt one compares as the held one."""

    def test_an_ordered_dict_keeps_its_order(self):
        ordered = collections.OrderedDict
        one, other = _Holder(0, ordered(a=1, b=2)), _Holder(9, ordered(b=2, a=1))
        with pytest.raises(AssertionFailure) as caught:
            assert_that(one).is_equal_to(other, ignore="v")
        assert_that([(entry.path, entry.actual, entry.expected) for entry in caught.value.diff.entries]).is_equal_to(
            [("next", ["a", "b"], ["b", "a"])]
        )
        with pytest.raises(AssertionFailure):
            assert_that(one).is_equal_to({"v": 9, "next": ordered(b=2, a=1)}, ignore="v")
        assert_that(one).is_equal_to(_Holder(9, ordered(a=1, b=2)), ignore="v")
        # against a plain dict an ordered one is equal whatever the order, as its own ``==`` has it
        assert_that(one).is_equal_to(_Holder(9, {"b": 2, "a": 1}), ignore="v")

    def test_an_ordered_dict_past_the_depth_the_plain_way_goes_keeps_its_order_too(self):
        ordered = collections.OrderedDict
        deep: object = None
        for _ in range(70):
            deep = [deep]
        one = _Holder(0, {"o": ordered(a=1, b=2), "deep": deep})
        with pytest.raises(AssertionFailure):
            assert_that(one).is_equal_to(_Holder(9, {"o": ordered(b=2, a=1), "deep": deep}), ignore="v")
        assert_that(one).is_equal_to(_Holder(9, {"o": ordered(a=1, b=2), "deep": deep}), ignore="v")

    def test_an_ordered_dict_of_a_class_of_its_own_keeps_the_class_and_runs_none_of_its_code(self):
        class Recorded(collections.OrderedDict):
            calls: typing.ClassVar[list[str]] = []

            def __init__(self, *args, **kwargs):
                self.calls.append("init")
                super().__init__(*args, **kwargs)

            def __setitem__(self, key, value):
                self.calls.append("set")
                super().__setitem__(key, value)

        one, other = _Holder(0, Recorded(a=1)), _Holder(9, Recorded(a=1))
        Recorded.calls.clear()
        assert_that(one).is_equal_to(other, ignore="v", strict_types=True)
        assert_that(Recorded.calls).is_empty()
        with pytest.raises(AssertionFailure):
            assert_that(one).is_equal_to(_Holder(9, collections.OrderedDict(a=1)), ignore="v", strict_types=True)

    def test_a_list_of_a_class_of_its_own_is_built_one_way_whichever_way_it_is_taken_apart(self):
        # built from a generator on the plain way and from a list past its depth, this one came out as two
        class Reversing(list):
            def __init__(self, items):
                super().__init__(items)
                if not isinstance(items, list):
                    self.reverse()

        deep: object = None
        for _ in range(70):
            deep = [deep]
        record = _Holder(0, {"value": Reversing([1, 2]), "deep": deep})
        assert_that(record).is_equal_to(
            {"v": 0, "next": {"value": Reversing([1, 2]), "deep": None}}, ignore=("next", "deep")
        )
