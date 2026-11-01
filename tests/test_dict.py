import collections
from types import MappingProxyType

import pytest

from assertpy import assert_that


def test_is_length():
    assert_that({"a": 1, "b": 2}).is_length(2)


def test_is_length_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that({"a": 1, "b": 2, "c": 3}).is_length(4)
    assert_that(str(exc_info.value)).contains("to be of length <4>, but was <3>.")


def test_contains():
    assert_that({"a": 1, "b": 2, "c": 3}).contains("a")
    assert_that({"a": 1, "b": 2, "c": 3}).contains("a", "b")

    ordered = collections.OrderedDict([("z", 9), ("x", 7), ("y", 8)])
    assert_that(ordered).contains("x")


def test_contains_empty_arg_failure():
    with pytest.raises(ValueError) as exc_info:
        assert_that({"a": 1, "b": 2, "c": 3}).contains()
    assert_that(str(exc_info.value)).is_equal_to("one or more args must be given")


def test_contains_single_item_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that({"a": 1, "b": 2, "c": 3}).contains("x")
    assert_that(str(exc_info.value)).contains("to contain key <x>, but did not.")


def test_contains_single_item_dict_like_failure():
    ordered = collections.OrderedDict([("z", 9), ("x", 7), ("y", 8)])
    with pytest.raises(AssertionError) as exc_info:
        assert_that(ordered).contains("a")
    assert_that(str(exc_info.value)).ends_with("to contain key <a>, but did not.")


def test_contains_multi_item_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that({"a": 1, "b": 2, "c": 3}).contains("a", "x", "z")
    assert_that(str(exc_info.value)).contains("to contain keys <'a', 'x', 'z'>, but did not contain keys <'x', 'z'>.")


def test_contains_multi_item_single_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that({"a": 1, "b": 2, "c": 3}).contains("a", "b", "z")
    assert_that(str(exc_info.value)).contains("to contain keys <'a', 'b', 'z'>, but did not contain key <z>.")


def test_contains_only():
    assert_that({"a": 1, "b": 2, "c": 3}).contains_only("a", "b", "c")
    assert_that({"a", "b", "c"}).contains_only("a", "b", "c")


def test_contains_only_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that({"a": 1, "b": 2}).contains_only("a", "x")
    assert_that(str(exc_info.value)).contains(
        "to contain only <'a', 'x'>, but did contain <b> and did not contain <x>."
    )


def test_contains_only_multi_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that({"a": 1, "b": 2}).contains_only("x", "y")
    assert_that(str(exc_info.value)).contains("to contain only <'x', 'y'>, but did contain <'")


def test_contains_key():
    assert_that({"a": 1, "b": 2, "c": 3}).contains_key("a")
    assert_that({"a": 1, "b": 2, "c": 3}).contains_key("a", "b")

    ordered = collections.OrderedDict([("z", 9), ("x", 7), ("y", 8)])
    assert_that(ordered).contains_key("x")


def test_contains_key_bad_val_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123).contains_key(1)
    assert_that(str(exc_info.value)).contains("must be dict-like")


def test_does_not_contain_key():
    assert_that({"a": 1, "b": 2, "c": 3}).does_not_contain_key("x")
    assert_that({"a": 1, "b": 2, "c": 3}).does_not_contain_key("x", "y")


def test_does_not_contain_key_bad_val_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123).does_not_contain_key(1)
    assert_that(str(exc_info.value)).contains("must be dict-like")


def test_contains_key_single_item_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that({"a": 1, "b": 2, "c": 3}).contains_key("x")
    assert_that(str(exc_info.value)).ends_with("to contain key <x>, but did not.")


def test_contains_key_multi_item_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that({"a": 1, "b": 2, "c": 3}).contains_key("a", "x", "z")
    assert_that(str(exc_info.value)).ends_with("to contain keys <'a', 'x', 'z'>, but did not contain keys <'x', 'z'>.")


def test_does_not_contain():
    assert_that({"a": 1, "b": 2, "c": 3}).does_not_contain("x")
    assert_that({"a": 1, "b": 2, "c": 3}).does_not_contain("x", "y")


def test_does_not_contain_empty_arg_failure():
    with pytest.raises(ValueError) as exc_info:
        assert_that({"a": 1, "b": 2, "c": 3}).does_not_contain()
    assert_that(str(exc_info.value)).is_equal_to("one or more args must be given")


def test_does_not_contain_single_item_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that({"a": 1, "b": 2, "c": 3}).does_not_contain("a")
    assert_that(str(exc_info.value)).contains("to not contain item <a>, but did.")


def test_does_not_contain_list_item_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that({"a": 1, "b": 2, "c": 3}).does_not_contain("x", "y", "a")
    assert_that(str(exc_info.value)).contains("to not contain items <'x', 'y', 'a'>, but did contain <a>.")


def test_is_empty():
    assert_that({}).is_empty()


def test_is_empty_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that({"a": 1, "b": 2}).is_empty()
    assert_that(str(exc_info.value)).contains("to be empty, but was not.")


def test_is_not_empty():
    assert_that({"a": 1, "b": 2}).is_not_empty()
    assert_that({"a", "b"}).is_not_empty()


def test_is_not_empty_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that({}).is_not_empty()
    assert_that(str(exc_info.value)).is_equal_to("Expected not empty, but was empty.")


def test_contains_value():
    assert_that({"a": 1, "b": 2, "c": 3}).contains_value(1)
    assert_that({"a": 1, "b": 2, "c": 3}).contains_value(1, 2)


def test_contains_value_empty_arg_failure():
    with pytest.raises(ValueError) as exc_info:
        assert_that({"a": 1, "b": 2, "c": 3}).contains_value()
    assert_that(str(exc_info.value)).is_equal_to("one or more value args must be given")


def test_contains_value_bad_val_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that("foo").contains_value("x")
    assert_that(str(exc_info.value)).contains("must be dict-like")


def test_contains_value_single_item_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that({"a": 1, "b": 2, "c": 3}).contains_value(4)
    assert_that(str(exc_info.value)).contains("to contain values <4>, but did not contain <4>.")


def test_contains_value_multi_item_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that({"a": 1, "b": 2, "c": 3}).contains_value(1, 4, 5)
    assert_that(str(exc_info.value)).contains("to contain values <1, 4, 5>, but did not contain <4, 5>.")


def test_does_not_contain_value():
    assert_that({"a": 1, "b": 2, "c": 3}).does_not_contain_value(4)
    assert_that({"a": 1, "b": 2, "c": 3}).does_not_contain_value(4, 5)


def test_does_not_contain_value_bad_val_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123).does_not_contain_value(1)
    assert_that(str(exc_info.value)).contains("must be dict-like")


def test_does_not_contain_value_empty_arg_failure():
    with pytest.raises(ValueError) as exc_info:
        assert_that({"a": 1, "b": 2, "c": 3}).does_not_contain_value()
    assert_that(str(exc_info.value)).is_equal_to("one or more value args must be given")


def test_does_not_contain_value_single_item_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that({"a": 1, "b": 2, "c": 3}).does_not_contain_value(1)
    assert_that(str(exc_info.value)).contains("to not contain values <1>, but did contain <1>.")


def test_does_not_contain_value_list_item_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that({"a": 1, "b": 2, "c": 3}).does_not_contain_value(4, 5, 1)
    assert_that(str(exc_info.value)).contains("to not contain values <4, 5, 1>, but did contain <1>.")


def test_does_not_contain_value_list_multi_item_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that({"a": 1, "b": 2, "c": 3}).does_not_contain_value(4, 1, 2)
    assert_that(str(exc_info.value)).contains("to not contain values <4, 1, 2>, but did contain <1, 2>.")


def test_contains_entry():
    assert_that({"a": 1, "b": 2, "c": 3}).contains_entry({"a": 1})
    assert_that({"a": 1, "b": 2, "c": 3}).contains_entry({"a": 1}, {"b": 2})
    assert_that({"a": 1, "b": 2, "c": 3}).contains_entry({"a": 1}, {"b": 2}, {"c": 3})
    assert_that({"a": 1, "b": 2, "c": 3}).contains_entry(a=1)
    assert_that({"a": 1, "b": 2, "c": 3}).contains_entry(a=1, b=2)
    assert_that({"a": 1, "b": 2, "c": 3}).contains_entry(a=1, b=2, c=3)
    assert_that({"a": 1, "b": 2, "c": 3}).contains_entry({"a": 1}, b=2)
    assert_that({"a": 1, "b": 2, "c": 3}).contains_entry({"b": 2}, a=1, c=3)


def test_contains_entry_bad_val_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that("foo").contains_entry({"a": 1})
    assert_that(str(exc_info.value)).contains("must be dict-like")


def test_contains_entry_empty_arg_failure():
    with pytest.raises(ValueError) as exc_info:
        assert_that({"a": 1, "b": 2, "c": 3}).contains_entry()
    assert_that(str(exc_info.value)).is_equal_to("one or more entry args must be given")


def test_contains_entry_bad_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that({"a": 1, "b": 2, "c": 3}).contains_entry("x")
    assert_that(str(exc_info.value)).is_equal_to("given entry arg must be a dict, but was <'x'> (str)")


def test_contains_entry_bad_arg_too_big_failure():
    with pytest.raises(ValueError) as exc_info:
        assert_that({"a": 1, "b": 2, "c": 3}).contains_entry({"a": 1, "b": 2})
    assert_that(str(exc_info.value)).is_equal_to("given entry args must contain exactly one key-value pair")


def test_contains_entry_bad_key_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that({"a": 1, "b": 2, "c": 3}).contains_entry({"x": 1})
    assert_that(str(exc_info.value)).contains("to contain entries <{'x': 1}>, but did not contain <{'x': 1}>.")


def test_contains_entry_bad_value_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that({"a": 1, "b": 2, "c": 3}).contains_entry({"a": 2})
    assert_that(str(exc_info.value)).contains("to contain entries <{'a': 2}>, but did not contain <{'a': 2}>.")


def test_contains_entry_bad_keys_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that({"a": 1, "b": 2, "c": 3}).contains_entry({"a": 1}, {"x": 2})
    assert_that(str(exc_info.value)).contains(
        "to contain entries <{'a': 1}, {'x': 2}>, but did not contain <{'x': 2}>."
    )


def test_contains_entry_bad_values_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that({"a": 1, "b": 2, "c": 3}).contains_entry({"a": 1}, {"b": 4})
    assert_that(str(exc_info.value)).contains(
        "to contain entries <{'a': 1}, {'b': 4}>, but did not contain <{'b': 4}>."
    )


def test_does_not_contain_entry():
    assert_that({"a": 1, "b": 2, "c": 3}).does_not_contain_entry({"a": 2})
    assert_that({"a": 1, "b": 2, "c": 3}).does_not_contain_entry({"a": 2}, {"b": 1})
    assert_that({"a": 1, "b": 2, "c": 3}).does_not_contain_entry(a=2)
    assert_that({"a": 1, "b": 2, "c": 3}).does_not_contain_entry(a=2, b=3)
    assert_that({"a": 1, "b": 2, "c": 3}).does_not_contain_entry({"x": 4}, y=5, z=6)


def test_does_not_contain_entry_bad_val_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that("foo").does_not_contain_entry({"a": 1})
    assert_that(str(exc_info.value)).contains("must be dict-like")


def test_does_not_contain_entry_empty_arg_failure():
    with pytest.raises(ValueError) as exc_info:
        assert_that({"a": 1, "b": 2, "c": 3}).does_not_contain_entry()
    assert_that(str(exc_info.value)).is_equal_to("one or more entry args must be given")


def test_does_not_contain_entry_bad_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that({"a": 1, "b": 2, "c": 3}).does_not_contain_entry("x")
    assert_that(str(exc_info.value)).is_equal_to("given entry arg must be a dict, but was <'x'> (str)")


def test_does_not_contain_entry_bad_arg_too_big_failure():
    with pytest.raises(ValueError) as exc_info:
        assert_that({"a": 1, "b": 2, "c": 3}).does_not_contain_entry({"a": 1, "b": 2})
    assert_that(str(exc_info.value)).is_equal_to("given entry args must contain exactly one key-value pair")


def test_does_not_contain_entry_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that({"a": 1, "b": 2, "c": 3}).does_not_contain_entry({"a": 1})
    assert_that(str(exc_info.value)).contains("to not contain entries <{'a': 1}>, but did contain <{'a': 1}>.")


def test_does_not_contain_entry_multiple_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that({"a": 1, "b": 2, "c": 3}).does_not_contain_entry({"a": 2}, {"b": 2})
    assert_that(str(exc_info.value)).contains(
        "to not contain entries <{'a': 2}, {'b': 2}>, but did contain <{'b': 2}>."
    )


def test_dynamic_assertion():
    fred = {"first_name": "Fred", "last_name": "Smith", "shoe_size": 12}
    assert_that(fred).is_type_of(dict)

    assert_that(fred["first_name"]).is_equal_to("Fred")
    assert_that(fred["last_name"]).is_equal_to("Smith")
    assert_that(fred["shoe_size"]).is_equal_to(12)

    assert_that(fred).has_first_name("Fred")
    assert_that(fred).has_last_name("Smith")
    assert_that(fred).has_shoe_size(12)


def test_dynamic_assertion_failure_str():
    fred = {"first_name": "Fred", "last_name": "Smith", "shoe_size": 12}

    with pytest.raises(AssertionError) as exc_info:
        assert_that(fred).has_first_name("Foo")
    assert_that(str(exc_info.value)).contains("Expected <Fred> to be equal to <Foo> on key <first_name>, but was not.")


def test_dynamic_assertion_failure_int():
    fred = {"first_name": "Fred", "last_name": "Smith", "shoe_size": 12}

    with pytest.raises(AssertionError) as exc_info:
        assert_that(fred).has_shoe_size(34)
    assert_that(str(exc_info.value)).contains("Expected <12> to be equal to <34> on key <shoe_size>, but was not.")


def test_dynamic_assertion_bad_key_failure():
    fred = {"first_name": "Fred", "last_name": "Smith", "shoe_size": 12}

    with pytest.raises(AssertionError) as exc_info:
        assert_that(fred).has_foo("Fred")
    assert_that(str(exc_info.value)).is_equal_to("Expected key <foo>, but val has no key <foo>.")


def test_dynamic_assertion_on_reserved_word():
    fred = {"def": "Fred"}
    assert_that(fred).is_type_of(dict)
    assert_that(fred["def"]).is_equal_to("Fred")
    assert_that(fred).has_def("Fred")


def test_dynamic_assertion_on_dict_method():
    fred = {"update": "Foo"}
    fred.update({"update": "Fred"})
    assert_that(fred).is_type_of(dict)
    assert_that(fred["update"]).is_equal_to("Fred")
    assert_that(fred).has_update("Fred")


def test_subset_of_compares_the_values_behind_the_keys():
    """The mapping branch is the one place a superset is refused by shape rather than by comparison.

    The values are compared too, which is what keeps the superset type from binding to the subject's
    value type: a superset may carry other keys, but a shared key has to carry a matching value.
    """
    assert_that({"a": 1}).is_subset_of({"a": 1, "b": 2})
    # keys the subject does not have are free, and so are their values and their types
    assert_that({"a": 1}).is_subset_of({"a": 1, "b": object()})
    assert_that({"a": 1}).is_subset_of({"a": 1, 2: "extra"})
    try:
        assert_that({"a": 1}).is_subset_of({"a": object()})
    except AssertionError as failure:
        assert_that(str(failure)).contains("to be subset of")
    else:  # pragma: no cover - the mismatched value is expected to fail
        raise AssertionError("expected a differing value to fail")


def test_subset_of_refuses_a_superset_that_is_not_dict_like():
    """The refusal the mapping narrowing rests on: a shape rejected by name, not by comparison.

    This is why `*supersets` is narrowed here and nowhere else.  The other views compare by `==` and
    accept anything, so a type refusing an argument there would refuse working code.
    """
    with pytest.raises(TypeError, match="must be dict-like"):
        assert_that({"a": 1}).is_subset_of(["a"])

    # and what it does take: anything with `keys`, iteration and subscripting, `Mapping` or not
    class Structural:
        def keys(self):
            return ["a"]

        def __iter__(self):
            return iter(["a"])

        def __getitem__(self, key):
            return 1

    assert_that({"a": 1}).is_subset_of(Structural())
    assert_that({"a": 1}).is_subset_of(MappingProxyType({"a": 1}))
